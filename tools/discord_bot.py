"""Forever XP Discord bot jobs, run from GitHub Actions.

  python3 tools/discord_bot.py validate                 # check discord/server.json (no token needed)
  python3 tools/discord_bot.py setup [--dry-run]        # apply discord/server.json to the server
  python3 tools/discord_bot.py post-notes OLD.json NEW.json   # post new Blizzard changes and news to the feed channel

Needs DISCORD_BOT_TOKEN (GitHub secret) and DISCORD_GUILD_ID (GitHub variable). The bot never
deletes anything except roles named in retired_roles, never pings anyone (allowed_mentions is empty on every message), and only
needs: View Channels, Send Messages, Embed Links, Read Message History, Manage Channels and
Manage Roles. It never needs Administrator.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://discord.com/api/v10"
UA = "DiscordBot (https://github.com/Jweyant/forever-xp, 1.0)"
TYPES = {"text": 0, "voice": 2, "category": 4, "announcement": 5, "forum": 15}
# Permission bits (https://discord.com/developers/docs/topics/permissions)
VIEW, SEND, EMBED, HISTORY = 1 << 10, 1 << 11, 1 << 14, 1 << 16
CREATE_PUBLIC_THREADS, CREATE_PRIVATE_THREADS, SEND_IN_THREADS = 1 << 35, 1 << 36, 1 << 38
READONLY_DENY = SEND | CREATE_PUBLIC_THREADS | CREATE_PRIVATE_THREADS | SEND_IN_THREADS
BOT_ALLOW = VIEW | SEND | EMBED | HISTORY
NAME_RE = re.compile(r"^[a-z0-9-]{1,90}$")
ROLE_NAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9 &'-]{0,58}[A-Za-z0-9])?$")
ROLE_KEYS = {"name", "color", "hoist"}
MAX_ROLES = 50
CHANNEL_KEYS = {"name", "type", "topic", "readonly", "tags", "aliases", "feed"}
# Links the feed may post: Blizzard's forum posts and news articles, nothing else.
BLIZZARD_URL = re.compile(r"^https://(?:us\.forums\.blizzard\.com|worldofwarcraft\.blizzard\.com)/[A-Za-z0-9/_%.~-]{1,300}$")


def log(msg):
    print(msg, flush=True)


# ---- validation (runs on every pull request, no token) ----------------------------------------
def validate(cfg):
    problems, seen, feeds = [], set(), []
    for cat in cfg.get("categories", []):
        if not cat.get("name") or len(cat["name"]) > 90:
            problems.append(f"category name missing or too long: {cat.get('name')!r}")
        for ch in cat.get("channels", []):
            name, kind = ch.get("name", ""), ch.get("type")
            if kind not in ("text", "voice", "announcement", "forum"):
                problems.append(f"{name}: unknown type {kind!r}")
            if kind != "voice" and not NAME_RE.match(name):
                problems.append(f"{name}: text channel names must be lowercase letters, digits and dashes")
            if set(ch) - CHANNEL_KEYS:
                problems.append(f"{name}: unknown keys {sorted(set(ch) - CHANNEL_KEYS)}")
            aliases = ch.get("aliases", [])
            if not isinstance(aliases, list) or any(not isinstance(a, str) or not NAME_RE.match(a) for a in aliases):
                problems.append(f"{name}: aliases must be channel names")
                aliases = []
            for n in [name, *aliases]:
                if n.lower() in seen:
                    problems.append(f"{n}: listed twice")
                seen.add(n.lower())
            if ch.get("feed") is True:
                feeds.append(name)
                if kind not in ("text", "announcement"):
                    problems.append(f"{name}: the feed must be a text or announcement channel")
            elif "feed" in ch:
                problems.append(f"{name}: feed must be true or left out")
            if len(ch.get("topic", "")) > 1024:
                problems.append(f"{name}: topic over 1024 characters")
            tags = ch.get("tags", [])
            if tags and kind != "forum":
                problems.append(f"{name}: only forum channels have tags")
            if len(tags) > 20 or any(len(t) > 20 for t in tags):
                problems.append(f"{name}: at most 20 tags of up to 20 characters")
    if len(feeds) > 1:
        problems.append(f"only one feed channel, not {', '.join(feeds)}")
    roles = cfg.get("roles", [])
    if len(roles) > MAX_ROLES:
        problems.append(f"at most {MAX_ROLES} roles")
    retired = cfg.get("retired_roles", [])
    if not isinstance(retired, list) or len(retired) > MAX_ROLES:
        problems.append(f"retired_roles must be a list of at most {MAX_ROLES} names")
        retired = []
    listed = {r.get("name", "").lower() for r in roles if isinstance(r, dict) and isinstance(r.get("name"), str)}
    for name in retired:
        if not isinstance(name, str) or not ROLE_NAME_RE.match(name):
            problems.append(f"retired role {name!r}: names are 1-60 letters, digits, spaces, & ' or -")
        elif name.lower() in listed:
            problems.append(f"retired role {name}: also listed in roles")
    seen_roles = set()
    for r in roles:
        name = r.get("name") if isinstance(r, dict) else None
        if not isinstance(name, str) or not ROLE_NAME_RE.match(name):
            problems.append(f"role {name!r}: names are 1-60 letters, digits, spaces, & ' or -")
            continue
        if set(r) - ROLE_KEYS:
            problems.append(f"role {name}: unknown keys {sorted(set(r) - ROLE_KEYS)}")
        if "color" in r and not re.match(r"^#[0-9A-Fa-f]{6}$", str(r["color"])):
            problems.append(f"role {name}: color must look like #RRGGBB")
        if "hoist" in r and not isinstance(r["hoist"], bool):
            problems.append(f"role {name}: hoist must be true or false")
        if name.lower() in seen_roles:
            problems.append(f"role {name}: listed twice")
        seen_roles.add(name.lower())
    return problems


# ---- Discord REST ------------------------------------------------------------------------------
class Discord:
    def __init__(self, token, dry=False):
        if not token:
            sys.exit("DISCORD_BOT_TOKEN is not set.")
        self.h = {"Authorization": f"Bot {token}", "User-Agent": UA, "Content-Type": "application/json"}
        self.dry = dry

    def call(self, method, path, body=None, *, write=False):
        if write and self.dry:
            log(f"  [dry run] {method} {path}")
            return {}
        data = json.dumps(body).encode() if body is not None else None
        for _ in range(5):
            req = urllib.request.Request(API + path, data=data, method=method, headers=self.h)
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    raw = r.read()
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    wait = float(json.loads(e.read() or b"{}").get("retry_after", 2))
                    time.sleep(min(wait, 30) + 0.25)
                    continue
                detail = e.read()[:300].decode("utf-8", "replace")
                raise SystemExit(f"Discord API {method} {path} failed: {e.code} {detail}")
        raise SystemExit(f"Discord API {method} {path}: still rate limited")


def merge_overwrites(existing, wanted):
    """Keep every overwrite already on the channel (moderators etc.) and set ours on top."""
    out = {o["id"]: {"id": o["id"], "type": o["type"], "allow": str(o.get("allow", "0")), "deny": str(o.get("deny", "0"))} for o in existing or []}
    for w in wanted:
        cur = out.get(w["id"], {"id": w["id"], "type": w["type"], "allow": "0", "deny": "0"})
        allow, deny = int(cur["allow"]), int(cur["deny"])
        allow = (allow | w.get("allow", 0)) & ~w.get("deny", 0)
        deny = (deny | w.get("deny", 0)) & ~w.get("allow", 0)
        out[w["id"]] = {"id": w["id"], "type": w["type"], "allow": str(allow), "deny": str(deny)}
    return list(out.values())


def setup(cfg, d, guild):
    me = d.call("GET", "/users/@me")
    roles = d.call("GET", f"/guilds/{guild}/roles")
    bot_role = next((r for r in roles if (r.get("tags") or {}).get("bot_id") == me["id"]), None)
    channels = d.call("GET", f"/guilds/{guild}/channels")
    log(f"Server has {len(channels)} channels and {len(roles)} roles. Bot: {me['username']}")

    def find(name, types, aliases=()):
        """The channel with this name, or failing that one with an old name (so renames don't duplicate)."""
        for n in (name, *aliases):
            hit = next((c for c in channels if c["type"] in types and c["name"].lower() == n.lower()), None)
            if hit:
                return hit
        return None

    order = []
    for cat in cfg["categories"]:
        c = find(cat["name"], (4,), cat.get("aliases", ()))
        if not c:
            log(f"+ category {cat['name']}")
            c = d.call("POST", f"/guilds/{guild}/channels", {"name": cat["name"], "type": 4}, write=True) or {"id": f"new-{cat['name']}", "type": 4, "name": cat["name"]}
            channels.append(c)
        elif c["name"] != cat["name"]:
            log(f"~ rename category {c['name']} -> {cat['name']}")
            d.call("PATCH", f"/channels/{c['id']}", {"name": cat["name"]}, write=True)
        order.append(c["id"])
        for ch in cat["channels"]:
            kind = TYPES[ch["type"]]
            family = (0, 5) if kind in (0, 5) else (kind,)
            x = find(ch["name"], family, ch.get("aliases", ()))
            overwrites = []
            if ch.get("readonly"):
                overwrites.append({"id": guild, "type": 0, "deny": READONLY_DENY})
                if bot_role:
                    overwrites.append({"id": bot_role["id"], "type": 0, "allow": BOT_ALLOW})
            body = {"parent_id": c["id"]}
            if "topic" in ch and kind != 2:
                body["topic"] = ch["topic"]
            if kind == 15 and ch.get("tags"):
                have = {t["name"]: t for t in (x or {}).get("available_tags", [])}
                body["available_tags"] = list(have.values()) + [{"name": t} for t in ch["tags"] if t not in have]
            if not x:
                log(f"+ {ch['type']} {ch['name']} in {cat['name']}")
                body.update({"name": ch["name"], "type": kind})
                if overwrites:
                    body["permission_overwrites"] = merge_overwrites([], overwrites)
                x = d.call("POST", f"/guilds/{guild}/channels", body, write=True) or {"id": f"new-{ch['name']}"}
                channels.append({**x, "name": ch["name"], "type": kind})
            else:
                if x["name"] != ch["name"]:
                    body["name"] = ch["name"]
                if x["type"] != kind:
                    body["type"] = kind
                if overwrites:
                    body["permission_overwrites"] = merge_overwrites(x.get("permission_overwrites"), overwrites)
                changed = {k for k, v in body.items() if x.get(k) != v}
                if changed:
                    log(f"~ {ch['name']}: {', '.join(sorted(changed))}")
                    d.call("PATCH", f"/channels/{x['id']}", body, write=True)
            order.append(x["id"])

    positions = [{"id": cid, "position": i} for i, cid in enumerate(order) if not str(cid).startswith("new-")]
    if positions:
        log(f"~ order {len(positions)} channels as in discord/server.json")
        d.call("PATCH", f"/guilds/{guild}/channels", positions, write=True)

    sync_roles(cfg, d, guild, roles, me)
    log("Done.")


def role_look(r):
    """The parts of a role the bot manages: color and hoist. Never permissions or mentionable."""
    return {"color": int(r["color"][1:], 16) if r.get("color") else 0, "hoist": bool(r.get("hoist", False))}


def sync_roles(cfg, d, guild, roles, me):
    """Create missing roles (no permissions, not mentionable), keep color and hoist as configured,
    and order them as listed. Deletes a role only when its name is in retired_roles. Only roles
    below the bot's own role can be changed; anything above it is reported and left alone. Never
    touches a role's permissions."""
    wanted = cfg.get("roles", [])
    retired = {n.lower() for n in cfg.get("retired_roles", [])} - {r["name"].lower() for r in wanted}
    if not wanted and not retired:
        return

    def index(rs):
        return {r["name"].lower(): r for r in rs if r["id"] != guild and not r.get("managed")}

    def top_of_bot(rs):
        return max((r.get("position", 0) for r in rs if (r.get("tags") or {}).get("bot_id") == me["id"]), default=0)

    bot_top = top_of_bot(roles)
    for x in roles:
        if x["id"] == guild or x.get("managed") or x["name"].lower() not in retired:
            continue
        if x.get("position", 0) >= bot_top:
            log(f"! role {x['name']} is above the bot's role, so it wasn't removed")
            continue
        log(f"- role {x['name']} (retired)")
        d.call("DELETE", f"/guilds/{guild}/roles/{x['id']}", write=True)
    have = index(roles)
    for r in wanted:
        look, x = role_look(r), have.get(r["name"].lower())
        if not x:
            log(f"+ role {r['name']}")
            d.call("POST", f"/guilds/{guild}/roles", {"name": r["name"], **look, "mentionable": False, "permissions": "0"}, write=True)
            continue
        changed = sorted(k for k, v in look.items() if x.get(k) != v)
        if not changed:
            continue
        if x.get("position", 0) >= bot_top:
            log(f"! role {x['name']} is above the bot's role, so its {', '.join(changed)} wasn't updated")
            continue
        log(f"~ role {x['name']}: {', '.join(changed)}")
        d.call("PATCH", f"/guilds/{guild}/roles/{x['id']}", {k: look[k] for k in changed}, write=True)

    if not getattr(d, "dry", False):
        roles = d.call("GET", f"/guilds/{guild}/roles")
        bot_top = top_of_bot(roles)
    have = index(roles)
    present = [have[r["name"].lower()] for r in wanted if r["name"].lower() in have]
    above = [x["name"] for x in present if x.get("position", 0) >= bot_top]
    if above:
        log(f"! not ordering roles: {', '.join(above)} sit above the bot's role. Drag the bot's role above them in Server Settings > Roles.")
        return
    slots = sorted({x.get("position", 0) for x in present}, reverse=True)
    if len(slots) < len(present):  # tied positions: use a fresh block just above the lowest one
        low = min(slots)
        slots = list(range(low + len(present) - 1, low - 1, -1))
        if slots[0] >= bot_top:
            log("! not ordering roles: not enough room below the bot's role. Drag the bot's role to the top in Server Settings > Roles.")
            return
    moves = [{"id": x["id"], "position": p} for x, p in zip(present, slots) if x.get("position") != p]
    if moves:
        log(f"~ order {len(present)} roles as in discord/server.json")
        d.call("PATCH", f"/guilds/{guild}/roles", moves, write=True)


# ---- patch notes -------------------------------------------------------------------------------
MD = re.compile(r"([\\*_~`|>#\[\]()])")


def plain(s, n=300):
    """Blizzard's text as plain Discord text: markdown escaped, no mentions, no invite links."""
    s = re.sub(r"\s+", " ", str(s)).strip()
    s = s.replace("@", "@​").replace("discord.gg/", "discord​.gg/")
    s = MD.sub(r"\\\1", s)
    return s if len(s) <= n else s[: n - 1] + "…"


def feed_channel(cfg):
    """(name, aliases) of the channel marked "feed": true in discord/server.json."""
    for cat in cfg.get("categories", []):
        for ch in cat.get("channels", []):
            if ch.get("feed") is True:
                return ch["name"], ch.get("aliases", [])
    return None, []


def safe_url(u):
    return u if isinstance(u, str) and BLIZZARD_URL.match(u) else None


def post(d, target, content):
    msg = d.call("POST", f"/channels/{target['id']}/messages",
                 {"content": content[:2000], "allowed_mentions": {"parse": []}, "flags": 4}, write=True)
    if target["type"] == 5 and msg.get("id"):
        d.call("POST", f"/channels/{target['id']}/messages/{msg['id']}/crosspost", write=True)
    time.sleep(1.5)


def post_notes(cfg, old_path, new_path, d, guild, max_messages=6, max_articles=3):
    """Post Blizzard's new WoW Forever changes (class, racial and every other development note) and
    new news articles to the feed channel. Known issues are left to the site."""
    if not Path(old_path).exists():
        log("No previous notes file, so this is the first run: nothing posted.")
        return
    old_doc, new_doc = json.loads(Path(old_path).read_text()), json.loads(Path(new_path).read_text())
    old = {r["id"] for r in old_doc.get("rows", [])}
    new_rows = [r for r in new_doc.get("rows", []) if r["id"] not in old and r.get("kind") != "Known issues"]
    # Articles: only once the previous file has an article list, so the first run doesn't repost them all.
    new_articles = []
    if isinstance(old_doc.get("articles"), list):
        seen = {x.get("url") for x in old_doc["articles"]}
        new_articles = [x for x in new_doc.get("articles", []) if safe_url(x.get("url")) and x["url"] not in seen]
    if not new_rows and not new_articles:
        log("No new changes.")
        return
    name, aliases = feed_channel(cfg)
    if not name:
        sys.exit("No feed channel in discord/server.json.")
    channels = d.call("GET", f"/guilds/{guild}/channels")
    target = None
    for n in (name, *aliases):
        target = target or next((c for c in channels if c["name"] == n and c["type"] in (0, 5)), None)
    if not target:
        sys.exit(f"No #{name} channel; run setup first.")

    for x in new_articles[:max_articles]:
        post(d, target, f"**New from Blizzard:** {plain(x.get('title', 'WoW Forever news'), 150)}\n<{x['url']}>")
        log(f"posted article {x['url']}")

    groups = {}
    for r in new_rows:
        groups.setdefault(r.get("url", ""), []).append(r)
    for url, rows in list(groups.items())[:max_messages]:
        date = rows[0].get("date", "")
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(date)):
            date = ""
        cls = sum(1 for r in rows if r.get("cls"))
        race = sum(1 for r in rows if r.get("race"))
        parts = [f"{len(rows)} change{'s' if len(rows) != 1 else ''}"]
        if cls:
            parts.append(f"{cls} class")
        if race:
            parts.append(f"{race} racial")
        head = f"**New WoW Forever changes from Blizzard** ({', '.join(parts)}{', ' + date if date else ''})"
        lines, used = [], len(head) + 200
        # Class and racial changes first, then everything else, each in Blizzard's order.
        for r in sorted(rows, key=lambda r: 0 if r.get("cls") or r.get("race") else 1):
            where = " › ".join([r.get("section", "")] + list(r.get("path", [])))
            line = f"• {plain(where, 60)}: {plain(r.get('text', ''))}"
            if used + len(line) > 1700:
                break
            lines.append(line)
            used += len(line) + 1
        more = len(rows) - len(lines)
        tail = []
        if more:
            tail.append(f"…and {more} more.")
        if safe_url(url):
            tail.append(f"Blizzard's post: <{url}>")
        tail.append("Search every change: <https://forever-xp.com/changes/" + (f"?date={date}" if date else "") + ">")
        post(d, target, "\n".join([head, *lines, *tail]))
        log(f"posted {len(lines)} of {len(rows)} changes from {url}")
    if len(groups) > max_messages:
        log(f"{len(groups) - max_messages} more posts' worth held back to avoid flooding the channel.")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate")
    s = sub.add_parser("setup")
    s.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("post-notes")
    p.add_argument("old")
    p.add_argument("new")
    p.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    cfg = json.loads((ROOT / "discord" / "server.json").read_text())
    problems = validate(cfg)
    if problems:
        sys.exit("discord/server.json:\n  " + "\n  ".join(problems))
    if a.cmd == "validate":
        log("discord/server.json looks good.")
        return
    guild = os.environ.get("DISCORD_GUILD_ID", "")
    if not guild.isdigit():
        sys.exit("DISCORD_GUILD_ID must be the server's numeric ID.")
    d = Discord(os.environ.get("DISCORD_BOT_TOKEN"), dry=a.dry_run)
    if a.cmd == "setup":
        setup(cfg, d, guild)
    else:
        post_notes(cfg, a.old, a.new, d, guild)


if __name__ == "__main__":
    main()

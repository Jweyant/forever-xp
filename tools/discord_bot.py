"""Forever XP Discord bot jobs, run from GitHub Actions.

  python3 tools/discord_bot.py validate                 # check discord/server.json (no token needed)
  python3 tools/discord_bot.py setup [--dry-run]        # apply discord/server.json to the server
  python3 tools/discord_bot.py post-notes OLD.json NEW.json   # post new Blizzard changes and news to the feed channel
  python3 tools/discord_bot.py post-date 2026-10-26 NOTES.json...  # (re)post one day's changes (run by hand)

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


BRAND = 0xE8B92E  # the site's gold
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
SITE_CHANGES = "https://forever-xp.com/changes/"


def label(s, n=100):
    """Short text for embed titles and field names: one line, no markdown characters, no pings."""
    s = re.sub(r"[\\*_~`|>#\[\]]", "", re.sub(r"\s+", " ", str(s))).replace("@", "@\u200b").strip()
    return (s if len(s) <= n else s[: n - 1] + "…") or "Other"


def nice_date(date):
    y, m, d = (int(x) for x in date.split("-"))
    return f"{MONTHS[m - 1]} {d}"


def post(d, target, embed):
    msg = d.call("POST", f"/channels/{target['id']}/messages",
                 {"embeds": [embed], "allowed_mentions": {"parse": []}}, write=True)
    if target["type"] == 5 and msg.get("id"):
        d.call("POST", f"/channels/{target['id']}/messages/{msg['id']}/crosspost", write=True)
    time.sleep(1.5)
    return msg


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
    new_articles += new_announcements(old_doc, new_doc)
    send_feed(cfg, d, guild, new_rows, new_articles, max_messages, max_articles)


def new_announcements(old_doc, new_doc, days=3, today=None):
    """Blizzard announcements (News page entries) that weren't in the previous file, oldest first.
    Nothing until the previous file has the list, so the first run doesn't repost old news; topics
    whose changes are posted anyway, and anything older than a few days, are left out."""
    if not isinstance(old_doc.get("announcements"), list):
        return []
    seen = {x.get("id") for x in old_doc["announcements"] if isinstance(x, dict)}
    since = time.strftime("%Y-%m-%d", time.gmtime((today or time.time()) - days * 86400))
    out = []
    for x in new_doc.get("announcements", []) or []:
        if (isinstance(x, dict) and x.get("id") not in seen and not x.get("notes") and safe_url(x.get("url"))
                and re.match(r"^\d{4}-\d{2}-\d{2}$", str(x.get("date"))) and x["date"] >= since):
            out.append({"title": x.get("title"), "url": x["url"], "description": x.get("excerpt")})
    return out[::-1]


def post_date(cfg, paths, date, d, guild, max_messages=6):
    """Post every development note Blizzard dated `date` (YYYY-MM-DD), merged from the given notes
    files. For catching the channel up by hand; the hourly feed only posts what's new."""
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date or ""):
        sys.exit("The date must look like 2026-10-26.")
    rows = {}
    for p in paths:
        if Path(p).exists():
            for r in json.loads(Path(p).read_text()).get("rows", []):
                rows[r["id"]] = r
    picked = [r for r in rows.values() if r.get("date") == date and r.get("kind") != "Known issues"]
    log(f"{len(picked)} changes dated {date}")
    if not picked:
        return
    target = feed_target(cfg, d, guild)
    # Replace the bot's own earlier posts for this day (found by their link to the day's changes),
    # so re-running gives one clean post. Never touches anyone else's messages.
    me = d.call("GET", "/users/@me")
    marker = f"changes/?date={date}"
    for m in d.call("GET", f"/channels/{target['id']}/messages?limit=50") or []:
        if (m.get("author") or {}).get("id") == me.get("id") and marker in json.dumps([m.get("content", ""), m.get("embeds", [])]):
            log(f"- replacing earlier post {m['id']}")
            d.call("DELETE", f"/channels/{target['id']}/messages/{m['id']}", write=True)
    send_feed(cfg, d, guild, picked, [], max_messages, 0, target=target)


def feed_target(cfg, d, guild):
    name, aliases = feed_channel(cfg)
    if not name:
        sys.exit("No feed channel in discord/server.json.")
    channels = d.call("GET", f"/guilds/{guild}/channels")
    for n in (name, *aliases):
        hit = next((c for c in channels if c["name"] == n and c["type"] in (0, 5)), None)
        if hit:
            return hit
    sys.exit(f"No #{name} channel; run setup first.")


def group_rows(rows):
    """[(kind, name, lines)]: class changes (by class), then racial (by race), then the rest (by
    section), each in Blizzard's order. Lines are Discord-safe."""
    groups = {}
    for r in rows:
        if r.get("cls"):
            kind, name = 0, r["cls"]
        elif r.get("race"):
            kind, name = 1, r["race"]
        else:
            kind, name = 2, r.get("section") or "Other"
        sub = [str(x) for x in r.get("path", []) if str(x) != name]
        g = groups.setdefault((kind, name), [kind, len(groups), label(name, 60), []])
        prefix = f"**{plain(' › '.join(sub), 60)}:** " if sub else ""
        g[3].append(f"• {prefix}{plain(r.get('text', ''), 500)}")
    return [(k, n, lines) for k, _, n, lines in sorted(groups.values(), key=lambda g: (g[0], g[1]))]


def change_embeds(rows, url, date, limit=5500):
    """One Blizzard post's changes as embeds: a title with the counts, a summary line per kind,
    then a field per class, race or section. Long groups and long days split cleanly."""
    groups = group_rows(rows)
    n = len(rows)
    kinds = {k: sum(len(lines) for kk, _, lines in groups if kk == k) for k in (0, 1, 2)}
    what = "racial " if kinds[1] == n else "class " if kinds[0] == n else ""
    title = f"{n} {what}change{'s' if n != 1 else ''} from Blizzard" + (f", {nice_date(date)}" if date else "")
    site = SITE_CHANGES + (f"?date={date}" if date else "")
    summary = []
    for k, word in ((0, "Class"), (1, "Racial")):
        names = sorted(((len(lines), name) for kk, name, lines in groups if kk == k), key=lambda x: -x[0])
        if names:
            summary.append(f"**{word}:** " + " · ".join(f"{name} {c}" for c, name in names[:12]))
    if kinds[2] and (kinds[0] or kinds[1]):
        summary.append(f"**Other:** {kinds[2]} change{'s' if kinds[2] != 1 else ''}")
    links = ([f"[Blizzard's post]({url})"] if safe_url(url) else []) + [f"[All changes on forever-xp.com]({site})"]
    fields = []
    for _, name, lines in groups:
        cur, first = [], True
        for line in lines:
            line = line if len(line) <= 1000 else line[:999] + "…"
            if cur and len("\n".join(cur)) + 1 + len(line) > 1024:
                fields.append({"name": name if first else "\u200b", "value": "\n".join(cur)})
                cur, first = [], False
            cur.append(line)
        if cur:
            fields.append({"name": name if first else "\u200b", "value": "\n".join(cur)})
    embeds = []
    cur = {"title": title, "url": site, "color": BRAND, "description": "\n".join(summary + [" · ".join(links)]), "fields": []}
    size = len(title) + len(cur["description"])
    for f in fields:
        fs = len(f["name"]) + len(f["value"])
        if len(cur["fields"]) == 25 or size + fs > limit:
            embeds.append(cur)
            cur = {"title": f"{title} (continued)", "url": site, "color": BRAND, "fields": []}
            size = len(cur["title"])
        cur["fields"].append(f)
        size += fs
    embeds.append(cur)
    embeds[-1]["footer"] = {"text": "Forever XP · forever-xp.com"}
    return embeds


def send_feed(cfg, d, guild, new_rows, new_articles, max_messages, max_articles, target=None):
    if not new_rows and not new_articles:
        log("No new changes.")
        return
    target = target or feed_target(cfg, d, guild)

    for x in new_articles[:max_articles]:
        about = label(x["description"], 300) if x.get("description") else "New WoW Forever news from Blizzard."
        post(d, target, {"title": label(x.get("title", "WoW Forever news"), 200), "url": x["url"], "color": BRAND,
                         "description": about, "footer": {"text": "Forever XP · forever-xp.com/news/"}})
        log(f"posted article {x['url']}")

    groups = {}
    for r in new_rows:
        groups.setdefault(r.get("url", ""), []).append(r)
    sent = 0
    for url, rows in groups.items():
        date = rows[0].get("date", "")
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(date)):
            date = ""
        embeds = change_embeds(rows, url, date)
        for e in embeds:
            if sent >= max_messages:
                log("message limit reached; the rest is on the site.")
                return
            post(d, target, e)
            sent += 1
        log(f"posted {len(rows)} changes from {url} in {len(embeds)} message(s)")


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
    q = sub.add_parser("post-date")
    q.add_argument("date")
    q.add_argument("notes", nargs="+")
    q.add_argument("--dry-run", action="store_true")
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
    elif a.cmd == "post-date":
        post_date(cfg, a.notes, a.date, d, guild)
    else:
        post_notes(cfg, a.old, a.new, d, guild)


if __name__ == "__main__":
    main()

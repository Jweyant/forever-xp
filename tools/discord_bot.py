"""Forever XP Discord bot jobs, run from GitHub Actions.

  python3 tools/discord_bot.py validate                 # check discord/server.json (no token needed)
  python3 tools/discord_bot.py setup [--dry-run]        # apply discord/server.json to the server
  python3 tools/discord_bot.py post-notes OLD.json NEW.json   # post new Blizzard changes to #patch-notes

Needs DISCORD_BOT_TOKEN (GitHub secret) and DISCORD_GUILD_ID (GitHub variable). The bot never
deletes anything, never pings anyone (allowed_mentions is empty on every message), and only
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


def log(msg):
    print(msg, flush=True)


# ---- validation (runs on every pull request, no token) ----------------------------------------
def validate(cfg):
    problems, seen = [], set()
    for cat in cfg.get("categories", []):
        if not cat.get("name") or len(cat["name"]) > 90:
            problems.append(f"category name missing or too long: {cat.get('name')!r}")
        for ch in cat.get("channels", []):
            name, kind = ch.get("name", ""), ch.get("type")
            if kind not in ("text", "voice", "announcement", "forum"):
                problems.append(f"{name}: unknown type {kind!r}")
            if kind != "voice" and not NAME_RE.match(name):
                problems.append(f"{name}: text channel names must be lowercase letters, digits and dashes")
            if name.lower() in seen:
                problems.append(f"{name}: listed twice")
            seen.add(name.lower())
            if len(ch.get("topic", "")) > 1024:
                problems.append(f"{name}: topic over 1024 characters")
            tags = ch.get("tags", [])
            if tags and kind != "forum":
                problems.append(f"{name}: only forum channels have tags")
            if len(tags) > 20 or any(len(t) > 20 for t in tags):
                problems.append(f"{name}: at most 20 tags of up to 20 characters")
    for r in cfg.get("roles", []):
        if not re.match(r"^#[0-9A-Fa-f]{6}$", r.get("color", "")):
            problems.append(f"role {r.get('name')}: color must look like #RRGGBB")
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
        names = {name.lower(), *[a.lower() for a in aliases]}
        return next((c for c in channels if c["type"] in types and c["name"].lower() in names), None)

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
            x = find(ch["name"], family)
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

    names = {r["name"].lower() for r in roles}
    for r in cfg.get("roles", []):
        if r["name"].lower() in names:
            continue
        log(f"+ role {r['name']}")
        d.call("POST", f"/guilds/{guild}/roles", {"name": r["name"], "color": int(r["color"][1:], 16),
                                                  "hoist": False, "mentionable": False, "permissions": "0"}, write=True)
    log("Done.")


# ---- patch notes -------------------------------------------------------------------------------
MD = re.compile(r"([\\*_~`|>#\[\]()])")


def plain(s, n=300):
    """Blizzard's text as plain Discord text: markdown escaped, no mentions, no invite links."""
    s = re.sub(r"\s+", " ", str(s)).strip()
    s = s.replace("@", "@​").replace("discord.gg/", "discord​.gg/")
    s = MD.sub(r"\\\1", s)
    return s if len(s) <= n else s[: n - 1] + "…"


def post_notes(old_path, new_path, d, guild, max_messages=6):
    if not Path(old_path).exists():
        log("No previous notes file, so this is the first run: nothing posted.")
        return
    old = {r["id"] for r in json.loads(Path(old_path).read_text()).get("rows", [])}
    new_rows = [r for r in json.loads(Path(new_path).read_text()).get("rows", []) if r["id"] not in old and r.get("kind") != "Known issues"]
    if not new_rows:
        log("No new changes.")
        return
    channels = d.call("GET", f"/guilds/{guild}/channels")
    target = next((c for c in channels if c["name"] == "patch-notes" and c["type"] in (0, 5)), None)
    if not target:
        sys.exit("No #patch-notes channel; run setup first.")
    groups = {}
    for r in new_rows:
        groups.setdefault(r["url"], []).append(r)
    for url, rows in list(groups.items())[:max_messages]:
        date = rows[0]["date"]
        head = f"**New WoW Forever changes from Blizzard** ({date}, {len(rows)} change{'s' if len(rows) != 1 else ''})"
        lines, used = [], len(head) + 200
        for r in rows:
            where = " › ".join([r.get("section", "")] + r.get("path", []))
            line = f"• {plain(where, 60)}: {plain(r['text'])}"
            if used + len(line) > 1700:
                break
            lines.append(line)
            used += len(line) + 1
        more = len(rows) - len(lines)
        tail = []
        if more:
            tail.append(f"…and {more} more.")
        if url.startswith("https://us.forums.blizzard.com/"):
            tail.append(f"Blizzard's post: <{url}>")
        tail.append(f"Search every change: <https://forever-xp.com/changes/?date={date}>")
        content = "\n".join([head, *lines, *tail])
        msg = d.call("POST", f"/channels/{target['id']}/messages",
                     {"content": content[:2000], "allowed_mentions": {"parse": []}, "flags": 4}, write=True)
        log(f"posted {len(lines)} of {len(rows)} changes from {url}")
        if target["type"] == 5 and msg.get("id"):
            d.call("POST", f"/channels/{target['id']}/messages/{msg['id']}/crosspost", write=True)
        time.sleep(1.5)
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
        post_notes(a.old, a.new, d, guild)


if __name__ == "__main__":
    main()

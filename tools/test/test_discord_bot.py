"""Offline tests for tools/discord_bot.py: config validation, safe message text, and a setup
run against a fake Discord API (no token, no network)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import discord_bot as bot  # noqa: E402

CFG = json.loads((Path(__file__).resolve().parents[2] / "discord" / "server.json").read_text())


class FakeDiscord:
    def __init__(self, channels, roles):
        self.channels, self.roles, self.calls, self.n = channels, roles, [], 900

    def call(self, method, path, body=None, *, write=False):
        self.calls.append((method, path, body))
        if path == "/users/@me":
            return {"id": "42", "username": "forever-xp"}
        if path.endswith("/roles") and method == "GET":
            return [dict(r) for r in self.roles]
        if path.endswith("/roles") and method == "POST":   # Discord adds new roles at the bottom
            for r in self.roles:
                if r.get("position", 0) >= 1:
                    r["position"] += 1
            self.n += 1
            self.roles.append({"id": str(self.n), "position": 1, **body})
            return self.roles[-1]
        if path.endswith("/roles") and method == "PATCH":
            for m in body:
                next(r for r in self.roles if r["id"] == m["id"])["position"] = m["position"]
            return self.roles
        if "/roles/" in path and method == "DELETE":
            self.roles = [r for r in self.roles if r["id"] != path.rsplit("/", 1)[1]]
            return {}
        if "/roles/" in path and method == "PATCH":
            next(r for r in self.roles if r["id"] == path.rsplit("/", 1)[1]).update(body)
            return {}
        if path.endswith("/channels") and method == "GET":
            return self.channels
        if method == "POST" and path.endswith("/channels"):
            self.n += 1
            return {"id": str(self.n), **body}
        if method == "POST" and path.endswith("/messages"):
            return {"id": "m1"}
        return {}


class Tests(unittest.TestCase):
    def test_config_is_valid(self):
        self.assertEqual(bot.validate(CFG), [])

    def test_validation_catches_bad_input(self):
        bad = {"categories": [{"name": "X", "channels": [{"name": "Bad Name!", "type": "text"}, {"name": "f", "type": "voice", "tags": ["a"]}]}],
               "roles": [{"name": "r", "color": "red"}]}
        self.assertEqual(len(bot.validate(bad)), 3)

    def test_validation_catches_bad_roles(self):
        bad = {"categories": [], "roles": [
            {"name": "@everyone"}, {"name": "Mage", "permissions": "8"}, {"name": "Rogue", "hoist": "yes"},
            {"name": "mage"}, {"name": " Padded "}, {"name": "x" * 61}]}
        problems = bot.validate(bad)
        self.assertEqual(len(problems), 6, problems)
        self.assertTrue(any("unknown keys" in p for p in problems))   # permissions can't be set from the file

    def test_plain_text_cannot_ping_or_format(self):
        s = bot.plain("@everyone **free gold** at discord.gg/scam [click](http://x)")
        self.assertNotIn("@everyone", s)
        self.assertNotIn("**", s.replace("\\*", ""))
        self.assertNotIn("discord.gg/", s)

    def test_setup_creates_missing_and_keeps_existing(self):
        guild = "1"
        channels = [{"id": "10", "type": 4, "name": "Text Channels"}, {"id": "11", "type": 0, "name": "general", "parent_id": "10"},
                    {"id": "12", "type": 5, "name": "announcements", "parent_id": None,
                     "permission_overwrites": [{"id": "77", "type": 0, "allow": "8192", "deny": "0"}]}]
        roles = [{"id": "1", "name": "@everyone", "position": 0}, {"id": "50", "name": "forever-xp", "position": 2, "managed": True, "tags": {"bot_id": "42"}},
                 {"id": "51", "name": "Contributor", "position": 1, "color": 0xE8B92E, "hoist": True}]
        d = FakeDiscord(channels, roles)
        bot.setup(CFG, d, guild)
        posts = [b["name"] for m, p, b in d.calls if m == "POST" and p.endswith("/channels")]
        self.assertIn("patch-notes", posts)
        self.assertNotIn("general", posts)          # existing channel reused
        self.assertNotIn("Gameplay", posts)         # "Text Channels" renamed, not duplicated
        self.assertFalse(any(m == "DELETE" for m, _, _ in d.calls))
        ann = next(b for m, p, b in d.calls if m == "PATCH" and p == "/channels/12")
        ow = {o["id"]: o for o in ann["permission_overwrites"]}
        self.assertIn("77", ow)                      # moderator overwrite kept
        self.assertTrue(int(ow["1"]["deny"]) & bot.SEND)    # members can't post
        self.assertTrue(int(ow["50"]["allow"]) & bot.SEND)  # the bot can
        new_roles = [b["name"] for m, p, b in d.calls if m == "POST" and p.endswith("/roles")]
        self.assertNotIn("Contributor", new_roles)
        self.assertIn("Moderator", new_roles)
        self.assertTrue(all(b["permissions"] == "0" and not b["mentionable"] for m, p, b in d.calls if m == "POST" and p.endswith("/roles")))

    def test_only_retired_roles_are_removed(self):
        cfg = {"categories": [], "roles": [{"name": "Moderator"}], "retired_roles": ["Mage", "Horde", "Druid"]}
        roles = [{"id": "1", "name": "@everyone", "position": 0},
                 {"id": "61", "name": "mage", "position": 1}, {"id": "62", "name": "Hunter", "position": 2},
                 {"id": "63", "name": "Horde", "position": 3, "managed": True},
                 {"id": "50", "name": "Forever XP", "position": 4, "managed": True, "tags": {"bot_id": "42"}},
                 {"id": "64", "name": "Druid", "position": 5}]
        d = FakeDiscord([], roles)
        bot.setup(cfg, d, "1")
        deleted = [p.rsplit("/", 1)[1] for m, p, _ in d.calls if m == "DELETE"]
        self.assertEqual(deleted, ["61"])   # not Hunter (not retired), not a managed role, not one above the bot

    def test_retired_roles_are_validated(self):
        problems = bot.validate({"categories": [], "roles": [{"name": "Moderator"}], "retired_roles": ["moderator", "@everyone"]})
        self.assertEqual(len(problems), 2, problems)

    def test_roles_not_in_the_file_are_left_alone(self):
        roles = [{"id": "1", "name": "@everyone", "position": 0}, {"id": "60", "name": "Raid leader", "position": 1, "color": 0xB3261E},
                 {"id": "50", "name": "Forever XP", "position": 2, "managed": True, "tags": {"bot_id": "42"}}]
        d = FakeDiscord([], roles)
        bot.setup(CFG, d, "1")
        other = next(r for r in d.roles if r["id"] == "60")
        self.assertEqual(other["color"], 0xB3261E)
        self.assertFalse(any("/roles/60" in p for m, p, _ in d.calls))
        moves = [m for meth, p, b in d.calls if meth == "PATCH" and p.endswith("/roles") for m in b]
        self.assertFalse(any(m["id"] == "60" for m in moves))

    def test_roles_end_up_in_listed_order_without_permissions(self):
        roles = [{"id": "1", "name": "@everyone", "position": 0},
                 {"id": "51", "name": "Moderator", "position": 1, "color": 0, "hoist": False, "permissions": "8192"},
                 {"id": "52", "name": "contributor", "position": 2, "color": 0xE8B92E, "hoist": True},
                 {"id": "50", "name": "Forever XP", "position": 3, "managed": True, "tags": {"bot_id": "42"}}]
        d = FakeDiscord([], roles)
        bot.setup(CFG, d, "1")
        by_pos = [r["name"].lower() for r in sorted(d.roles, key=lambda r: -r["position"]) if not r.get("managed") and r["id"] != "1"]
        self.assertEqual(by_pos, [r["name"].lower() for r in CFG["roles"]])
        self.assertEqual(max(d.roles, key=lambda r: r["position"])["id"], "50")   # bot role still on top
        mod = next(r for r in d.roles if r["id"] == "51")
        self.assertEqual((mod["color"], mod["hoist"], mod["permissions"]), (0x3BA55C, True, "8192"))  # look fixed, hand-set permissions kept
        for m, p, b in d.calls:
            if m == "PATCH" and "/roles" in p and isinstance(b, dict):
                self.assertFalse({"permissions", "mentionable", "name"} & set(b))
        self.assertTrue(all(b["permissions"] == "0" and not b["mentionable"] for m, p, b in d.calls if m == "POST" and p.endswith("/roles")))
        self.assertEqual(sum(1 for r in d.roles if r["name"].lower() == "contributor"), 1)  # matched case-insensitively
        self.assertFalse(any(m == "DELETE" for m, _, _ in d.calls))

    def test_roles_above_the_bot_are_left_alone(self):
        cfg = {"categories": [], "roles": [{"name": "Mage", "color": "#3FC7EB"}, {"name": "Hunter", "color": "#AAD372"}]}
        roles = [{"id": "1", "name": "@everyone", "position": 0},
                 {"id": "50", "name": "Forever XP", "position": 1, "managed": True, "tags": {"bot_id": "42"}},
                 {"id": "51", "name": "Mage", "position": 2, "color": 0, "hoist": True}]
        d = FakeDiscord([], roles)
        bot.setup(cfg, d, "1")
        self.assertFalse(any(m == "PATCH" and "/roles" in p for m, p, _ in d.calls))
        self.assertIn("Hunter", [b["name"] for m, p, b in d.calls if m == "POST" and p.endswith("/roles")])

    def test_post_notes_only_new_and_never_pings(self):
        with tempfile.TemporaryDirectory() as t:
            old, new = Path(t, "old.json"), Path(t, "new.json")
            old.write_text(json.dumps({"rows": [{"id": "a"}]}))
            new.write_text(json.dumps({"rows": [
                {"id": "a", "date": "2026-10-16", "kind": "Development notes", "section": "Classes", "path": [], "text": "old", "url": "https://us.forums.blizzard.com/x"},
                {"id": "b", "date": "2026-10-30", "kind": "Development notes", "section": "Classes", "path": ["Mage"], "text": "@here new thing", "url": "https://us.forums.blizzard.com/y"},
                {"id": "c", "date": "2026-10-30", "kind": "Known issues", "section": "Known issues", "path": [], "text": "issue", "url": "https://us.forums.blizzard.com/y"},
            ]}))
            d = FakeDiscord([{"id": "5", "type": 5, "name": "patch-notes"}], [])
            bot.post_notes(old, new, d, "1")
            msgs = [b for m, p, b in d.calls if m == "POST" and p.endswith("/messages")]
            self.assertEqual(len(msgs), 1)
            self.assertEqual(msgs[0]["allowed_mentions"], {"parse": []})
            self.assertIn("new thing", msgs[0]["content"])
            self.assertNotIn("@here", msgs[0]["content"])
            self.assertNotIn("issue", msgs[0]["content"])
            self.assertTrue(any(p.endswith("/crosspost") for m, p, b in d.calls))

    def test_first_run_posts_nothing(self):
        d = FakeDiscord([], [])
        bot.post_notes("/nonexistent/old.json", "/nonexistent/new.json", d, "1")
        self.assertEqual(d.calls, [])


if __name__ == "__main__":
    unittest.main()

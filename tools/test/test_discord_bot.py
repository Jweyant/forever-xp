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
            return self.roles
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
        roles = [{"id": "1", "name": "@everyone"}, {"id": "50", "name": "forever-xp", "tags": {"bot_id": "42"}}, {"id": "51", "name": "Mage"}]
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
        self.assertNotIn("Mage", new_roles)
        self.assertIn("Warrior", new_roles)
        self.assertTrue(all(b["permissions"] == "0" and not b["mentionable"] for m, p, b in d.calls if m == "POST" and p.endswith("/roles")))

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

"""Offline tests for tools/discord_bot.py: config validation, safe message text, and a setup
run against a fake Discord API (no token, no network)."""
import json
import time
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import discord_bot as bot  # noqa: E402

CFG = json.loads((Path(__file__).resolve().parents[2] / "discord" / "server.json").read_text())


class FakeDiscord:
    def __init__(self, channels, roles, messages=()):
        self.channels, self.roles, self.calls, self.n = channels, roles, [], 900
        self.messages = list(messages)

    def call(self, method, path, body=None, *, write=False):
        self.calls.append((method, path, body))
        if path == "/users/@me":
            return {"id": "42", "username": "forever-xp"}
        if method == "GET" and "/messages" in path:
            return list(self.messages)
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


def shown(body):
    """All the text a posted message shows (embeds included)."""
    return json.dumps(body, ensure_ascii=False)


def posts(d):
    return [b for m, p, b in d.calls if m == "POST" and p.endswith("/messages")]


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
        self.assertIn("forever-announcements", posts)
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
            d = FakeDiscord([{"id": "5", "type": 5, "name": "forever-announcements"}], [])
            bot.post_notes(CFG, old, new, d, "1")
            msgs = posts(d)
            self.assertEqual(len(msgs), 1)
            self.assertEqual(msgs[0]["allowed_mentions"], {"parse": []})
            self.assertNotIn("content", msgs[0])
            self.assertIn("new thing", shown(msgs[0]))
            self.assertNotIn("@here", shown(msgs[0]))
            self.assertNotIn("issue", shown(msgs[0]))
            self.assertTrue(any(p.endswith("/crosspost") for m, p, b in d.calls))

    def test_feed_puts_class_and_racial_first_and_posts_new_articles(self):
        with tempfile.TemporaryDirectory() as t:
            old, new = Path(t, "old.json"), Path(t, "new.json")
            u = "https://us.forums.blizzard.com/en/wow/t/notes/1"
            old.write_text(json.dumps({"rows": [], "articles": [{"title": "Old", "url": "https://worldofwarcraft.blizzard.com/en-us/news/1"}]}))
            new.write_text(json.dumps({"rows": [
                {"id": "q", "date": "2026-10-30", "kind": "Development notes", "section": "Quests", "path": [], "text": "quest fix", "url": u},
                {"id": "m", "date": "2026-10-30", "kind": "Development notes", "section": "Classes", "path": ["Mage"], "text": "mage change", "url": u, "cls": "Mage"},
                {"id": "h", "date": "2026-10-30", "kind": "Development notes", "section": "Races", "path": ["Human"], "text": "human change", "url": u, "race": "Human"},
            ], "articles": [
                {"title": "Old", "url": "https://worldofwarcraft.blizzard.com/en-us/news/1"},
                {"title": "Launch @everyone **now**", "url": "https://worldofwarcraft.blizzard.com/en-us/news/2"},
                {"title": "Elsewhere", "url": "https://evil.example/news"},
            ]}))
            d = FakeDiscord([{"id": "5", "type": 0, "name": "patch-notes"}], [])   # found by its old name
            bot.post_notes(CFG, old, new, d, "1")
            msgs = posts(d)
            self.assertEqual(len(msgs), 2)
            article = msgs[0]["embeds"][0]
            self.assertTrue(article["url"].endswith("news/2"))
            self.assertNotIn("@everyone", article["title"])
            self.assertNotIn("*", article["title"])
            self.assertFalse(any("evil.example" in shown(m) for m in msgs))
            e = msgs[1]["embeds"][0]
            self.assertEqual(e["title"], "3 changes from Blizzard, Oct 30")
            self.assertIn("**Class:** Mage 1", e["description"])
            self.assertIn("**Racial:** Human 1", e["description"])
            self.assertEqual([f["name"] for f in e["fields"]], ["Mage", "Human", "Quests"])  # class, race, then the rest
            self.assertEqual(e["url"], "https://forever-xp.com/changes/?date=2026-10-30")

    def test_articles_wait_for_a_previous_list(self):
        with tempfile.TemporaryDirectory() as t:
            old, new = Path(t, "old.json"), Path(t, "new.json")
            old.write_text(json.dumps({"rows": []}))
            new.write_text(json.dumps({"rows": [], "articles": [{"title": "A", "url": "https://worldofwarcraft.blizzard.com/en-us/news/2"}]}))
            d = FakeDiscord([{"id": "5", "type": 5, "name": "forever-announcements"}], [])
            bot.post_notes(CFG, old, new, d, "1")
            self.assertEqual(d.calls, [])

    def test_recent_announcements_not_yet_in_the_channel_are_posted_safely(self):
        today = time.strftime("%Y-%m-%d")
        base = "https://us.forums.blizzard.com/en/wow/t/"
        with tempfile.TemporaryDirectory() as t:
            old, new = Path(t, "old.json"), Path(t, "new.json")
            old.write_text(json.dumps({"rows": []}))   # no announcements list yet: recent ones still go out
            new.write_text(json.dumps({"rows": [], "announcements": [
                {"id": 4, "date": today, "title": "Realms are up @everyone", "url": base + "realms/4", "excerpt": "Queues **now** [x](https://evil.example)"},
                {"id": 3, "date": today, "title": "Hotfixes", "url": base + "hotfixes/3", "notes": 1},
                {"id": 2, "date": "2026-01-01", "title": "Too old", "url": base + "old/2"},
                {"id": 5, "date": today, "title": "Elsewhere", "url": "https://evil.example/t/x/5"},
                {"id": 1, "date": today, "title": "Already posted", "url": base + "seen/1"},
                {"id": 6, "date": today, "title": "Someone else posted it", "url": base + "other/6"},
            ]}))
            channel = [
                {"author": {"id": "42"}, "embeds": [{"url": base + "seen/1"}]},          # the bot's own post
                {"author": {"id": "77"}, "embeds": [{"url": base + "other/6"}]},         # not the bot's: doesn't count
            ]
            d = FakeDiscord([{"id": "5", "type": 5, "name": "forever-announcements"}], [], messages=channel)
            bot.post_notes(CFG, old, new, d, "1")
            msgs = posts(d)
            self.assertEqual([m["embeds"][0]["url"] for m in msgs], [base + "other/6", base + "realms/4"])
            e = msgs[1]["embeds"][0]
            self.assertNotIn("@everyone", e["title"])
            self.assertNotIn("*", e["description"])
            self.assertNotIn("[", e["description"])
            self.assertTrue(all(m["allowed_mentions"] == {"parse": []} for m in msgs))

    def test_recent_means_the_last_week_oldest_first(self):
        now = time.time()
        day = lambda n: time.strftime("%Y-%m-%d", time.gmtime(now - n * 86400))  # noqa: E731
        doc = {"announcements": [{"id": i, "date": day(n), "title": str(n), "url": f"https://us.forums.blizzard.com/en/wow/t/a/{i}"}
                                 for i, n in ((1, 0), (2, 6), (3, 9))]}
        self.assertEqual([x["title"] for x in bot.recent_announcements(doc, today=now)], ["6", "0"])

    def test_renamed_channel_is_renamed_not_duplicated(self):
        cfg = {"categories": [{"name": "Start Here", "channels": [
            {"name": "forever-announcements", "aliases": ["patch-notes"], "type": "announcement", "feed": True}]}]}
        d = FakeDiscord([{"id": "4", "type": 4, "name": "Start Here"}, {"id": "5", "type": 5, "name": "patch-notes", "parent_id": "4"}], [])
        bot.setup(cfg, d, "1")
        self.assertFalse(any(m == "POST" and p.endswith("/channels") for m, p, _ in d.calls))
        self.assertTrue(any(m == "PATCH" and p == "/channels/5" and b.get("name") == "forever-announcements" for m, p, b in d.calls))

    def test_feed_and_alias_validation(self):
        bad = {"categories": [{"name": "X", "channels": [
            {"name": "a", "type": "text", "feed": True}, {"name": "b", "type": "voice", "feed": True},
            {"name": "c", "type": "text", "aliases": ["a"]}, {"name": "d", "type": "text", "webhook": "x"}]}]}
        problems = bot.validate(bad)
        self.assertTrue(any("only one feed" in p for p in problems), problems)
        self.assertTrue(any("text or announcement" in p for p in problems), problems)
        self.assertTrue(any("listed twice" in p for p in problems), problems)
        self.assertTrue(any("unknown keys" in p for p in problems), problems)

    def test_post_date_posts_that_day_only(self):
        with tempfile.TemporaryDirectory() as t:
            a, b = Path(t, "a.json"), Path(t, "b.json")
            u = "https://us.forums.blizzard.com/en/wow/t/notes/1"
            a.write_text(json.dumps({"rows": [{"id": "1", "date": "2026-10-26", "kind": "Development notes", "section": "Races", "path": ["Human"], "text": "today", "url": u, "race": "Human"},
                                              {"id": "2", "date": "2026-10-20", "kind": "Development notes", "section": "Quests", "path": [], "text": "older", "url": u}]}))
            b.write_text(json.dumps({"rows": [{"id": "3", "date": "2026-10-26", "kind": "Known issues", "section": "Known issues", "path": [], "text": "issue", "url": u}]}))
            mine = {"id": "m1", "author": {"id": "42"}, "content": "old post <https://forever-xp.com/changes/?date=2026-10-26>"}
            other_day = {"id": "m2", "author": {"id": "42"}, "embeds": [{"url": "https://forever-xp.com/changes/?date=2026-10-20"}]}
            someone = {"id": "m3", "author": {"id": "7"}, "content": "https://forever-xp.com/changes/?date=2026-10-26"}
            d = FakeDiscord([{"id": "5", "type": 5, "name": "forever-announcements"}], [], [mine, other_day, someone])
            bot.post_date(CFG, [a, b], "2026-10-26", d, "1")
            msgs = posts(d)
            self.assertEqual(len(msgs), 1)
            self.assertIn("today", shown(msgs[0]))
            self.assertNotIn("older", shown(msgs[0]))
            self.assertNotIn("issue", shown(msgs[0]))
            self.assertEqual(msgs[0]["embeds"][0]["title"], "1 racial change from Blizzard, Oct 26")
            deleted = [p for m, p, _ in d.calls if m == "DELETE"]
            self.assertEqual(deleted, ["/channels/5/messages/m1"])   # only the bot's own post for that day
            with self.assertRaises(SystemExit):
                bot.post_date(CFG, [a], "2026-10-26; rm -rf /", d, "1")

    def test_long_days_split_within_discord_limits(self):
        u = "https://us.forums.blizzard.com/en/wow/t/notes/1"
        rows = [{"id": str(i), "date": "2026-10-26", "kind": "Development notes", "section": "Classes", "path": ["Warrior", "Fury"] if i % 2 else ["Mage"],
                 "text": "x" * 450, "url": u, "cls": "Warrior" if i % 2 else "Mage"} for i in range(60)]
        embeds = bot.change_embeds(rows, u, "2026-10-26")
        self.assertGreater(len(embeds), 1)
        for e in embeds:
            self.assertLessEqual(len(e["fields"]), 25)
            self.assertLessEqual(len(e.get("title", "")) + len(e.get("description", "")) + sum(len(f["name"]) + len(f["value"]) for f in e["fields"]), 6000)
            for f in e["fields"]:
                self.assertLessEqual(len(f["value"]), 1024)
                self.assertTrue(f["name"])
        self.assertEqual(sum(f["value"].count("• ") for e in embeds for f in e["fields"]), 60)   # nothing dropped
        self.assertIn("**Fury:**", shown(embeds))
        self.assertTrue(embeds[0]["title"].startswith("60 class changes"))

    def test_first_run_posts_nothing(self):
        d = FakeDiscord([], [])
        bot.post_notes(CFG, "/nonexistent/old.json", "/nonexistent/new.json", d, "1")
        self.assertEqual(d.calls, [])


if __name__ == "__main__":
    unittest.main()

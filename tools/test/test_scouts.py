"""Scout leaderboard: per-player counts under one-way handles, weekly window, discoveries need confirmation."""
import json
import re
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ingest_logs  # noqa: E402

A = "a" * 32
B = "b" * 32
LOG_A = f"logs/{A}-{'1' * 16}.lua"
LOG_B = f"logs/{B}-{'2' * 16}.lua"
NOW = 2_000_000_000


class Scouts(unittest.TestCase):
    def run_scouts(self, sessions, events):
        db = sqlite3.connect(":memory:")
        db.executescript(ingest_logs.SCHEMA)
        for sid, char, source, start in sessions:
            db.execute("INSERT INTO sessions (id, char_id, start, source) VALUES (?,?,?,?)", (sid, char, start, source))
        for sid, k, t, q, m, extra in events:
            db.execute("INSERT INTO events (session_id, k, t, q, map, json) VALUES (?,?,?,?,?,?)",
                       (sid, k, t, q, m, json.dumps(extra or {})))
        with tempfile.TemporaryDirectory() as d:
            ingest_logs.write_scouts(db, Path(d), now=NOW)
            return json.loads((Path(d) / "scouts.json").read_text())

    def test_board(self):
        old = NOW - 30 * 86400
        out = self.run_scouts(
            [(1, "c1", LOG_A, old), (2, "c2", LOG_A, NOW - 3600), (3, "c3", LOG_B, NOW - 1800)],
            [(1, "accept", 10, 5, 1411, None), (1, "turnin", 70, 5, 1411, None),             # A: quest 5, a month ago
             (1, "loot", 80, None, 1411, {"item": 100, "src": 7}),                            # A finds item 100 first
             (2, "accept", 1, 6, 1413, None), (2, "turnin", 60, 6, 1413, None),               # A (alt): quest 6 this week
             (3, "loot", 5, None, 1411, {"item": 100, "src": 7}),                             # B confirms item 100
             (3, "loot", 9, None, 1411, {"item": 200, "src": 8}),                             # B alone: no discovery
             (3, "loot", 9, None, 1411, {"item": "x", "src": 8})])                            # bad id: skipped
        a, b = ingest_logs.scout_handle("i:" + A), ingest_logs.scout_handle("i:" + B)
        board = {r["handle"]: r for r in out["board"]}
        self.assertEqual(board[a], {"handle": a, "quests": 2, "drops": 1, "discoveries": 1, "zones": 2, "sessions": 2, "score": 6})
        self.assertEqual(board[b], {"handle": b, "quests": 0, "drops": 2, "discoveries": 0, "zones": 1, "sessions": 1, "score": 2})
        self.assertEqual([r["handle"] for r in out["board"]], [a, b])
        self.assertEqual(out["totals"], {"scouts": 2, "sessions": 3, "quests": 2, "drops": 2, "discoveries": 1})
        week = {r["handle"]: r for r in out["week_board"]}
        self.assertEqual(week[a]["quests"], 1)  # only quest 6 is this week
        self.assertEqual(week[b]["drops"], 2)
        self.assertEqual(out["week"], {"scouts": 2, "quests": 1, "drops": 2})

    def test_handles_are_anonymous(self):
        out = self.run_scouts([(1, "c1", LOG_A, NOW)], [(1, "loot", 1, None, 1411, {"item": 1, "src": 2})])
        text = json.dumps(out)
        self.assertNotIn(A, text)
        self.assertNotIn("\"c1\"", text)
        self.assertRegex(out["board"][0]["handle"], r"^Scout [0-9a-f]{6}$")
        self.assertNotIn("1411", text)  # zones are a count, not ids

    def test_handle_matches_the_uploader(self):
        # Same vector as uploader/scout_test.go: the uploader shows players this name.
        self.assertEqual(ingest_logs.scout_handle("i:" + "a" * 32), "Scout 97800d")

    def test_empty(self):
        out = self.run_scouts([], [])
        self.assertEqual(out["board"], [])
        self.assertEqual(out["totals"]["scouts"], 0)


if __name__ == "__main__":
    unittest.main()

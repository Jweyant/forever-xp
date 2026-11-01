"""Quest timing from ForeverScout logs: attributed play time, not wall-clock accept -> turn-in."""
import csv
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ingest_logs  # noqa: E402


def timing(sessions, events, crumbs=()):
    db = sqlite3.connect(":memory:")
    db.executescript(ingest_logs.SCHEMA)
    for sid, char, start in sessions:
        db.execute("INSERT INTO sessions (id, char_id, start) VALUES (?,?,?)", (sid, char, start))
    for sid, t, k, q, xp, src in events:
        db.execute("INSERT INTO events (session_id, t, k, q, xp, src) VALUES (?,?,?,?,?,?)", (sid, t, k, q, xp, src))
    for sid, t in crumbs:
        db.execute("INSERT INTO crumbs (session_id, t, map, x, y) VALUES (?,?,0,0,0)", (sid, t))
    with tempfile.TemporaryDirectory() as d:
        ingest_logs.write_timing(db, Path(d))
        db.close()
        with (Path(d) / "quest_timing.csv").open() as f:
            return {int(r["quest_id"]): r for r in csv.DictReader(f)}


def every(sid, a, b, step=10):
    return [(sid, t) for t in range(a, b + 1, step)]


class Timing(unittest.TestCase):
    def test_single_quest_counts_active_time(self):
        out = timing([(1, "c", 1000)],
                     [(1, 0, "accept", 5, None, None), (1, 300, "turnin", 5, 500, "q")],
                     every(1, 0, 300))
        self.assertEqual(out[5]["median_seconds"], "300")
        self.assertEqual(out[5]["median_xp"], "500")

    def test_idle_time_is_capped(self):
        # One hour standing still in the middle: counts as IDLE_CAP, not 3600 seconds.
        out = timing([(1, "c", 1000)],
                     [(1, 0, "accept", 5, None, None), (1, 60, "obj", 5, None, None),
                      (1, 3660, "obj", 5, None, None), (1, 3720, "turnin", 5, 500, "q")])
        self.assertEqual(out[5]["median_seconds"], str(60 + ingest_logs.IDLE_CAP + 60))
        self.assertEqual(out[5]["wall_seconds"], "3720")

    def test_shared_travel_is_split_and_progress_is_owned(self):
        # Two quests carried together: 100 s of running split, then 60 s of kills for quest 7 only.
        out = timing([(1, "c", 1000)],
                     [(1, 0, "accept", 6, None, None), (1, 0, "accept", 7, None, None),
                      (1, 100, "zone", None, None, None),
                      (1, 160, "obj", 7, None, None), (1, 160, "turnin", 7, 400, "q"),
                      (1, 200, "turnin", 6, 300, "q")])
        self.assertEqual(out[7]["median_seconds"], "110")   # 50 shared + 60 own
        self.assertEqual(out[6]["median_seconds"], "90")    # 50 shared + 40 alone

    def test_quest_spanning_sessions_skips_logged_out_time(self):
        out = timing([(1, "c", 1000), (2, "c", 90000)],
                     [(1, 0, "accept", 5, None, None), (1, 120, "logout", None, None, None),
                      (2, 0, "login", None, None, None), (2, 90, "turnin", 5, 500, "q")],
                     every(1, 0, 120) + every(2, 0, 90))
        self.assertEqual(out[5]["median_seconds"], "210")

    def test_abandoned_and_unseen_accepts_are_left_out(self):
        out = timing([(1, "c", 1000)],
                     [(1, 0, "accept", 5, None, None), (1, 50, "abandon", 5, None, None),
                      (1, 60, "turnin", 5, 500, "q"),          # turned in without an accept on record
                      (1, 70, "turnin", 9, 500, "q")])
        self.assertEqual(out, {})

    def test_kill_xp_counts_toward_xp_per_minute(self):
        out = timing([(1, "c", 1000)],
                     [(1, 0, "accept", 5, None, None), (1, 30, "xp", None, 100, "k"),
                      (1, 60, "turnin", 5, 500, "q")], every(1, 0, 60))
        self.assertEqual(float(out[5]["xp_per_minute"]), 600.0)

    def test_players_and_median(self):
        ev = []
        sessions = []
        for i, secs in enumerate((100, 200, 9000), 1):
            sessions.append((i, f"c{i}", 1000))
            ev += [(i, 0, "accept", 5, None, None), (i, secs, "turnin", 5, 500, "q")]
        crumbs = [c for i, secs in enumerate((100, 200, 9000), 1) for c in every(i, 0, secs)]
        out = timing(sessions, ev, crumbs)
        self.assertEqual(out[5]["players"], "3")
        self.assertEqual(out[5]["median_seconds"], "200")   # the 2.5-hour outlier doesn't drag it

    def test_bad_values_are_ignored(self):
        out = timing([(1, "c", "x"), (2, "d", 1000)],
                     [(1, 0, "accept", 5, None, None), (1, 60, "turnin", 5, 500, "q"),
                      (2, -5, "accept", 6, None, None), (2, 0, "accept", 6, None, None),
                      (2, 30, "turnin", 6, "lots", "q")], every(2, 0, 30))
        self.assertNotIn(5, out)
        self.assertEqual(out[6]["median_xp"], "0")


if __name__ == "__main__":
    unittest.main()

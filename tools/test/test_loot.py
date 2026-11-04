"""Loot aggregation: players are counted per install (alts on one uploader count once), never below the threshold."""
import csv
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ingest_logs  # noqa: E402

INSTALL_A = "logs/" + "a" * 32 + "-" + "1" * 16 + ".lua"
INSTALL_B = "logs/" + "b" * 32 + "-" + "2" * 16 + ".lua"


class Loot(unittest.TestCase):
    def run_loot(self, sessions, loots, names=None):
        db = sqlite3.connect(":memory:")
        db.executescript(ingest_logs.SCHEMA)
        for sid, char, source in sessions:
            db.execute("INSERT INTO sessions (id, char_id, start, source) VALUES (?,?,?,?)", (sid, char, sid, source))
        db.execute("INSERT INTO events (session_id, k, json) VALUES (1, 'newnpc', ?)", (json.dumps({"npc": 7, "name": "Kobold Vermin"}),))
        for sid, item, src, kind in loots:
            db.execute("INSERT INTO events (session_id, k, json) VALUES (?,?,?)",
                       (sid, "loot", json.dumps({"item": item, "src": src, "kind": kind, "map": 1429})))
        with tempfile.TemporaryDirectory() as d:
            ingest_logs.write_loot(db, Path(d), linked=names)
            return list(csv.DictReader(io.StringIO((Path(d) / "loot.csv").read_text())))

    def test_alts_on_one_install_count_as_one_player(self):
        rows = self.run_loot([(1, "char1", INSTALL_A), (2, "char2", INSTALL_A), (3, "char3", INSTALL_B)],
                             [(1, 100, 7, "Creature"), (2, 100, 7, "Creature"), (3, 100, 7, "Creature"), (3, 100, 7, "Creature")])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], "Kobold Vermin")
        self.assertEqual(rows[0]["players"], "2")
        self.assertEqual(rows[0]["looted"], "4")

    def test_hand_submitted_logs_fall_back_to_the_character(self):
        rows = self.run_loot([(1, "char1", "logs/manual.lua"), (2, "char2", "logs/manual.lua")],
                             [(1, 200, 55, "GameObject"), (2, 200, 55, "GameObject")])
        self.assertEqual(rows[0]["source"], "Object #55")
        self.assertEqual(rows[0]["players"], "2")

    def test_first_looter_is_credited_only_when_linked_and_confirmed(self):
        names = {ingest_logs.scout_hash("i:" + "a" * 32): "Kinos", ingest_logs.scout_hash("i:" + "b" * 32): "Bee"}
        sessions = [(1, "c1", INSTALL_A), (2, "c2", INSTALL_B)]        # A's session starts first (start = id)
        # a drop two players saw: A was first. A drop only B saw: not confirmed, so no credit.
        rows = self.run_loot(sessions, [(1, 100, 7, "Creature"), (2, 100, 7, "Creature"), (2, 300, 7, "Creature")], names)
        by = {r["item"]: r["first_by"] for r in rows}
        self.assertEqual(by, {"100": "Kinos", "300": ""})
        # the first looter hasn't linked: nobody is credited, even though the second has
        rows = self.run_loot(sessions, [(1, 100, 7, "Creature"), (2, 100, 7, "Creature")], {ingest_logs.scout_hash("i:" + "b" * 32): "Bee"})
        self.assertEqual(rows[0]["first_by"], "")
        # no names list (accounts API unreachable): no credits at all
        self.assertEqual(self.run_loot(sessions, [(1, 100, 7, "Creature"), (2, 100, 7, "Creature")])[0]["first_by"], "")
        # hand-sent logs can't be linked
        rows = self.run_loot([(1, "c1", "logs/manual.lua"), (2, "c2", "logs/manual.lua")], [(1, 5, 9, "Creature"), (2, 5, 9, "Creature")],
                             {ingest_logs.scout_hash("c:c1"): "Sneaky"})
        self.assertEqual(rows[0]["first_by"], "")

    def test_bad_item_ids_are_skipped(self):
        rows = self.run_loot([(1, "c", INSTALL_A)], [(1, "nope", 7, "Creature"), (1, 0, 7, "Creature")])
        self.assertEqual(rows, [])

    def test_player_key(self):
        self.assertEqual(ingest_logs.player_key("c1", INSTALL_A), "i:" + "a" * 32)
        self.assertEqual(ingest_logs.player_key("c1", "logs/x.lua"), "c:c1")
        self.assertEqual(ingest_logs.player_key("c1", None), "c:c1")


if __name__ == "__main__":
    unittest.main()

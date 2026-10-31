"""Objective areas: player positions are aggregated, thresholded and validated before publishing."""
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import build_quests  # noqa: E402
import ingest_logs  # noqa: E402


class ObjectiveAreas(unittest.TestCase):
    def run_areas(self, events):
        db = sqlite3.connect(":memory:")
        db.executescript(ingest_logs.SCHEMA)
        for sid, char in ((1, "a"), (2, "b"), (3, "c")):
            db.execute("INSERT INTO sessions (id, char_id, start) VALUES (?,?,?)", (sid, char, sid))
        for sid, q, oi, m, x, y in events:
            db.execute("INSERT INTO events (session_id, k, q, map, x, y, json) VALUES (?,?,?,?,?,?,?)",
                       (sid, "obj", q, m, x, y, json.dumps({"oi": oi})))
        with tempfile.TemporaryDirectory() as d:
            ingest_logs.write_objective_areas(db, Path(d))
            return json.loads((Path(d) / "objective_areas.json").read_text())

    def test_needs_two_players_per_cell(self):
        areas = self.run_areas([(1, 33, 1, 1429, 43.1, 57.2), (2, 33, 1, 1429, 43.9, 57.9), (3, 33, 1, 1429, 80, 80)])
        self.assertEqual(areas, {"33": {"1": {"map": 1429, "cells": [[43.0, 57.0, 2]]}}})

    def test_drops_bad_values(self):
        bad = [(1, 0, 1, 1429, 5, 5), (2, 0, 1, 1429, 5, 5),            # no quest
               (1, 33, 99, 1429, 5, 5), (2, 33, 99, 1429, 5, 5),        # objective index out of range
               (1, 33, 1, 1429, 150, 5), (2, 33, 1, 1429, 150, 5),      # off the map
               (1, "x", 1, 1429, 5, 5), (2, "x", 1, 1429, 5, 5)]        # not a number
        self.assertEqual(self.run_areas(bad), {})


class ObjectiveSpawns(unittest.TestCase):
    def test_kill_and_item_objectives(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.executescript("CREATE TABLE npcs (id INTEGER PRIMARY KEY, name TEXT, json TEXT);"
                         "CREATE TABLE objects (id INTEGER PRIMARY KEY, name TEXT, json TEXT);"
                         "CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT, json TEXT);")
        db.execute("INSERT INTO npcs VALUES (6, 'Kobold Vermin', ?)", (json.dumps({"spawns": {"12": [[40.2, 80.4], [41, 81], [-1, 5]]}}),))
        db.execute("INSERT INTO items VALUES (750, 'Tough Wolf Meat', ?)", (json.dumps({"npcDrops": [6]}),))
        out = build_quests.objective_spawns(db, {"1": [{"1": 6}], "3": [{"1": 750}]}, {12: "elwynn forest"})
        self.assertEqual([o["n"] for o in out], ["Kobold Vermin", "Tough Wolf Meat"])
        self.assertEqual(out[0]["a"], [[40, 80], [41, 81]])  # the off-map point is dropped
        self.assertEqual(out[1]["t"], "item")


if __name__ == "__main__":
    unittest.main()

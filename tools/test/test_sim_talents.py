"""Sim setups' talents by name: rewritten for a changed tree, refused when the build can't be made."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import sim_talents as st  # noqa: E402

# A two-tree class: (name, ranks, row)
TREES = [("Arms", [("Heroic", 3, 0), ("Tactics", 5, 0), ("Rend", 3, 1), ("Mortal", 1, 2)]),
         ("Fury", [("Cruelty", 5, 0), ("Wrath", 5, 0)])]


class Encode(unittest.TestCase):
    def test_round_trip(self):
        picks = {"Arms": {"Heroic": 3, "Tactics": 5, "Rend": 3, "Mortal": 1}, "Fury": {"Cruelty": 5}}
        build, notes, errors = st.encode(TREES, picks)
        self.assertEqual((build, notes, errors), ("3531-5", [], []))
        self.assertEqual(st.decode(TREES, build), picks)

    def test_moved_talents_follow_their_names(self):
        moved = [("Arms", [("Tactics", 5, 0), ("Heroic", 3, 0), ("Rend", 3, 1), ("Mortal", 1, 2)]), TREES[1]]
        build, _, errors = st.encode(moved, {"Arms": {"Heroic": 3, "Tactics": 5, "Rend": 3, "Mortal": 1}})
        self.assertEqual((build, errors), ("5331", []))

    def test_fewer_ranks_and_removed_talents_leave_points_unspent(self):
        cut = [("Arms", [("Heroic", 3, 0), ("Tactics", 3, 0), ("Rend", 3, 1)]), TREES[1]]
        build, notes, errors = st.encode(cut, {"Arms": {"Heroic": 3, "Tactics": 5, "Rend": 3, "Mortal": 1}})
        self.assertEqual(build, "333")
        self.assertEqual(errors, [])
        self.assertTrue(any("Tactics" in n and "2 left unspent" in n for n in notes))
        self.assertTrue(any("Mortal" in n and "no longer in the tree" in n for n in notes))

    def test_builds_that_cant_be_made_are_errors(self):
        _, _, errors = st.encode(TREES, {"Arms": {"Heroic": 1, "Mortal": 1}})   # row 3 needs 10 points above
        self.assertTrue(any("row 3 needs 10" in e for e in errors))
        _, _, errors = st.encode(TREES, {"Holy": {"Heroic": 1}})
        self.assertTrue(any("no tree" in e for e in errors))
        big = [("A", [(f"t{i}", 5, 0) for i in range(12)])]
        _, _, errors = st.encode(big, {"A": {f"t{i}": 5 for i in range(12)}})
        self.assertTrue(any("more than 51" in e for e in errors))


class Repository(unittest.TestCase):
    def test_every_setup_matches_its_names(self):
        problems, _ = st.run(ROOT / "gamedata" / "simconfigs", [ROOT / "gamedata" / "talents.json"], "--check")
        self.assertEqual(problems, [])

    def test_write_rewrites_only_the_talents_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "simconfigs"
            shutil.copytree(ROOT / "gamedata" / "simconfigs", cfg)
            f = cfg / "warrior_arms.siml"
            before = f.read_text()
            f.write_text(before.replace('talents "30323213132215201-5505-2"', 'talents "1"'))
            problems, _ = st.run(cfg, [ROOT / "gamedata" / "talents.json"], "--check")
            self.assertTrue(any("doesn't match" in p for p in problems))
            problems, messages = st.run(cfg, [ROOT / "gamedata" / "talents.json"], "--write")
            self.assertEqual(problems, [])
            self.assertEqual(f.read_text(), before)
            self.assertTrue(any("-> 30323213132215201-5505-2" in m for m in messages))

    def test_newest_talents_file_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = json.loads((ROOT / "gamedata" / "talents.json").read_text())
            old["builds"]["forever"] = "1.60.1.1"
            p = Path(tmp) / "old.json"
            p.write_text(json.dumps(old))
            problems, _ = st.run(ROOT / "gamedata" / "simconfigs", [p, ROOT / "gamedata" / "talents.json"], "--check")
            self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()

"""Quest time estimates: real objective counts from cmangos, text fallback, and the floors
that keep no quest looking seconds long."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import guidegen  # noqa: E402
import quest_counts  # noqa: E402


class CmangosCounts(unittest.TestCase):
    def test_counts_from_rows(self):
        rows = [{"entry": 5441, "ReqCreatureOrGOId1": 10556, "ReqCreatureOrGOCount1": 5},
                {"entry": 789, "ReqItemId1": 4862, "ReqItemCount1": 10},
                {"entry": 7, "ReqCreatureOrGOId1": -2060, "ReqCreatureOrGOCount1": 4},   # gameobject
                {"entry": 8, "ReqCreatureOrGOId1": 11, "ReqCreatureOrGOCount1": 1},      # default: left out
                {"entry": "x"}]
        self.assertEqual(quest_counts.counts_from_rows(rows),
                         {"5441": {"npc:10556": 5}, "789": {"item:4862": 10}, "7": {"obj:2060": 4}})

    def test_committed_file_has_lazy_peons(self):
        import json
        counts = json.loads((Path(__file__).resolve().parents[1] / "quest_counts.json").read_text())
        self.assertEqual(counts["5441"], {"npc:10556": 5})
        self.assertGreater(len(counts), 1000)


class SettleCounts(unittest.TestCase):
    def obj(self, count):
        return ("kill", 10556, "Lazy Peon", [], count, 1)

    def test_lone_number_settles_a_lone_unknown(self):
        out = guidegen.settle_counts([self.obj(0)], "Wake up 5 peons, then return the blackjack.")
        self.assertEqual(out[0][4], 5)

    def test_level_and_big_numbers_never_count(self):
        out = guidegen.settle_counts([self.obj(0)], "Reach level 10 and visit post 5441.")
        self.assertEqual(out[0][4], 1)

    def test_two_unknowns_stay_at_one(self):
        out = guidegen.settle_counts([self.obj(0), self.obj(0)], "Collect 8 things.")
        self.assertEqual([o[4] for o in out], [1, 1])

    def test_known_counts_pass_through(self):
        out = guidegen.settle_counts([self.obj(12)], "Kill 8 of something else.")
        self.assertEqual(out[0][4], 12)


if __name__ == "__main__":
    unittest.main()

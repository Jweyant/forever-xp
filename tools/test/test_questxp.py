"""Offline tests for tools/questxp.py: reading opendata safely and estimating quest XP."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import questxp  # noqa: E402


def write(root, rel, rows):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(r if isinstance(r, str) else json.dumps(r) for r in rows) + "\n")


class OpenData(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = self.dir.name

    def tearDown(self):
        self.dir.cleanup()

    def test_reads_exact_xp_and_rejects_bad_values(self):
        write(self.root, "data/client/quests.jsonl", [
            {"quest_id": 92745, "quest_level": 14, "min_level": 9, "objectives": "Slay\x07 4 Diggers.", "rewards": {"xp": 490}},
            {"quest_id": "1", "rewards": {"xp": 100}},              # id not an int
            {"quest_id": 5, "rewards": {"xp": True}},                # bool is not a number here
            {"quest_id": 6, "rewards": {"xp": 10 ** 9}},             # out of range
            {"quest_id": 7, "rewards": "<script>"},
            "not json", "[1, 2]",
        ])
        q = questxp.opendata_quests(self.root)
        self.assertEqual(q[92745], {"xp": 490, "lv": 14, "req": 9, "obj": "Slay 4 Diggers."})
        self.assertNotIn("1", q)
        self.assertEqual(q.get(5), {})
        self.assertEqual(q.get(6), {})
        self.assertEqual(q.get(7), {})

    def test_givers_take_the_most_seen_holder_and_need_two_sightings(self):
        write(self.root, "data/world/quest_givers.jsonl", [
            {"quest_id": 10, "role": "start", "holder_kind": "npc", "holder_id": 1, "n": 3, "coords": {"map_id": 0, "zone_id": 12, "x": 41.23, "y": 65.1}},
            {"quest_id": 10, "role": "start", "holder_kind": "npc", "holder_id": 2, "n": 9},
            {"quest_id": 11, "role": "start", "holder_kind": "npc", "holder_id": 3, "n": 1},
            {"quest_id": 12, "role": "start", "holder_kind": "player", "holder_id": 4, "n": 50},
            {"quest_id": 13, "role": "end", "holder_kind": "npc", "holder_id": 5, "n": 4, "coords": {"x": 140, "y": -2}},
        ])
        g = questxp.opendata_givers(self.root)
        self.assertEqual(g[(10, "start")]["id"], 2)
        self.assertNotIn((11, "start"), g)
        self.assertNotIn((12, "start"), g)
        self.assertNotIn("x", g[(13, "end")])

    def test_missing_checkout_is_empty(self):
        self.assertEqual(questxp.opendata_quests(Path(self.root) / "nope"), {})


class Estimate(unittest.TestCase):
    def test_median_by_level_and_kind(self):
        est = questxp.Estimator([(10, x, False) for x in (400, 420, 440, 460, 480)] +
                                [(10, x, True) for x in (85, 85, 210, 210, 210)])
        self.assertEqual(est(10), 440)
        self.assertEqual(est(10, talk=True), 210)
        self.assertEqual(est(11), 440)          # borrows neighbouring levels
        self.assertIsNone(est(0))
        self.assertIsNone(est(70))

    def test_talk_detection(self):
        self.assertTrue(questxp.is_talk("Speak with Elaadrin Evengale when you are prepared."))
        self.assertTrue(questxp.is_talk("Take the letter to Gryan Stoutmantle."))
        self.assertFalse(questxp.is_talk("Bring a Wind-Infused Bough to Belann Windwood."))
        self.assertFalse(questxp.is_talk("Speak to the elder, then kill 8 boars."))
        self.assertFalse(questxp.is_talk(None))


if __name__ == "__main__":
    unittest.main()

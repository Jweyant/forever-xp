"""Chained quests are scored together: next-in-chain links, same-name single prerequisites,
and totals over the scored parts only."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import site_data  # noqa: E402

# Elixir of Agony-shaped chain: 5 parts linked by next, one part (515) not scored.
ALL = [
    {"id": 509, "n": "Elixir of Agony", "lv": 28, "next": 513},
    {"id": 513, "n": "Elixir of Agony", "lv": 28, "pre": [509], "next": 515},
    {"id": 515, "n": "Elixir of Agony", "lv": 30, "pre": [513], "next": 517},
    {"id": 517, "n": "Elixir of Agony", "lv": 30, "pre": [515], "next": 524},
    {"id": 524, "n": "Elixir of Agony", "lv": 30, "pre": [517]},
    # same-name pair linked only by a single pre
    {"id": 100, "n": "Westfall Stew", "lv": 9},
    {"id": 101, "n": "Westfall Stew", "lv": 10, "pre": [100]},
    # a different-name single pre with ONE follower is a linear continuation
    {"id": 300, "n": "The Hunt Continues", "lv": 7},
    {"id": 301, "n": "The Hunt Completed", "lv": 8, "pre": [300]},
    # a hub quest many others require is not a chain
    {"id": 200, "n": "Welcome!", "lv": 5},
    {"id": 201, "n": "Something Else", "lv": 6, "pre": [200]},
    {"id": 202, "n": "A Third Thing", "lv": 6, "pre": [200]},
    # a group prerequisite bundles the finale with members that feed nothing else
    {"id": 2, "n": "Sharptalon's Claw", "lv": 30},
    {"id": 23, "n": "Ursangous's Paw", "lv": 30},
    {"id": 247, "n": "The Hunt Completed", "lv": 30, "pre": [2, 23]},
]
SHOWN = {
    509: {"id": 509, "name": "Elixir of Agony", "xp": 2300, "minutes": 5.4},
    513: {"id": 513, "name": "Elixir of Agony", "xp": 1150, "minutes": 4.8},
    517: {"id": 517, "name": "Elixir of Agony", "xp": 1200, "minutes": 6.8},
    524: {"id": 524, "name": "Elixir of Agony", "xp": 3650, "minutes": 0.3},
    100: {"id": 100, "name": "Westfall Stew", "xp": 400, "minutes": 2.0},
    101: {"id": 101, "name": "Westfall Stew", "xp": 600, "minutes": 3.0},
    300: {"id": 300, "name": "The Hunt Continues", "xp": 450, "minutes": 4.0},
    301: {"id": 301, "name": "The Hunt Completed", "xp": 600, "minutes": 0.2},
    2: {"id": 2, "name": "Sharptalon's Claw", "xp": 2450, "minutes": 8.0},
    23: {"id": 23, "name": "Ursangous's Paw", "xp": 2450, "minutes": 9.0},
    247: {"id": 247, "name": "The Hunt Completed", "xp": 3400, "minutes": 0.3},
    200: {"id": 200, "name": "Welcome!", "xp": 100, "minutes": 1.0},
    201: {"id": 201, "name": "Something Else", "xp": 100, "minutes": 1.0},
    202: {"id": 202, "name": "A Third Thing", "xp": 100, "minutes": 1.0},
}


class Chains(unittest.TestCase):
    def setUp(self):
        self.out = site_data.quest_chains(ALL, SHOWN)

    def test_next_links_make_one_chain_with_real_part_numbers(self):
        c = self.out[524]
        self.assertEqual((c["part"], c["parts"], c["name"]), (5, 5, "Elixir of Agony"))
        self.assertEqual(self.out[509]["part"], 1)
        # totals over the four scored parts
        self.assertEqual(c["xp"], 2300 + 1150 + 1200 + 3650)
        self.assertEqual(c["minutes"], round(5.4 + 4.8 + 6.8 + 0.3, 1))
        self.assertEqual(c["xp_per_min"], int(c["xp"] / c["minutes"]))
        self.assertNotIn(515, self.out)  # unscored part carries no chain row

    def test_same_name_single_pre_links(self):
        self.assertEqual(self.out[100]["parts"], 2)
        self.assertEqual(self.out[101]["part"], 2)

    def test_lone_follower_is_a_continuation(self):
        self.assertEqual(self.out[301]["parts"], 2)
        self.assertEqual(self.out[301]["name"], "The Hunt Continues")

    def test_group_prerequisites_bundle_the_finale(self):
        c = self.out[247]
        self.assertEqual(c["parts"], 3)
        self.assertEqual(c["xp"], 2450 + 2450 + 3400)
        self.assertEqual(c["minutes"], round(8.0 + 9.0 + 0.3, 1))
        self.assertIn(2, self.out)
        self.assertIn(23, self.out)

    def test_hub_quests_do_not_chain(self):
        self.assertNotIn(200, self.out)
        self.assertNotIn(201, self.out)
        self.assertNotIn(202, self.out)


if __name__ == "__main__":
    unittest.main()

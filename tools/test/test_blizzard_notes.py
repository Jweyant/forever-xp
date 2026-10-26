"""Offline tests for tools/blizzard_notes.py: finding the Forever forum categories and staff note
topics without touching the network."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import blizzard_notes as bn  # noqa: E402

CATEGORIES = {"category_list": {"categories": [
    {"id": 172, "slug": "classic-discussion", "name": "WoW Classic General Discussion", "subcategory_list": []},
    {"id": 346, "slug": "wow-forever", "name": "WoW: Forever", "subcategory_list": [
        {"id": 347, "slug": "world-of-warcraft-forever-general-discussion", "name": "General Discussion"},
        {"id": 360, "slug": "launch-bug-report", "name": "Bug Report"},  # new at launch, found via its parent
    ]},
    {"id": 300, "slug": "in-development", "name": "In Development", "subcategory_list": [
        {"id": 349, "slug": "wow-forever-beta-discussion", "name": "WoW: Forever Beta Discussion"},
        {"id": "x", "slug": "forever-but-bad-id"},
    ]},
]}}


class Discovery(unittest.TestCase):
    def setUp(self):
        self.real_get, self.real_sleep = bn.get, bn.time.sleep
        bn.time.sleep = lambda s: None

    def tearDown(self):
        bn.get, bn.time.sleep = self.real_get, self.real_sleep

    def test_finds_every_forever_category_including_new_ones(self):
        bn.get = lambda url: CATEGORIES
        self.assertEqual(bn.forever_categories(), [346, 347, 349, 360])

    def test_falls_back_to_the_known_list(self):
        def down(url):
            raise OSError("forum down")
        bn.get = down
        self.assertEqual(bn.forever_categories(), bn.CATEGORIES)

    def test_staff_note_topics_are_found_in_any_forever_category(self):
        def fake(url):
            if "categories.json" in url:
                return CATEGORIES
            if "category%3A360" in url:
                return {"topics": [{"id": 9001, "title": "WoW Forever Hotfixes - November 4"},
                                   {"id": 9002, "title": "Launch day realm queues"}]}
            if "category%3A347" in url:
                return {"topics": [{"id": 9003, "title": "WoW Forever Launch Known Issues"}]}
            return {"topics": []}
        bn.get = fake
        found = bn.discover()
        self.assertEqual(found.get(9001), "Development notes")
        self.assertEqual(found.get(9003), "Known issues")
        self.assertNotIn(9002, found)


if __name__ == "__main__":
    unittest.main()

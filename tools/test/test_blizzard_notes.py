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


class Sections(unittest.TestCase):
    BASE = {"kind": "Development notes", "date": "2026-10-27", "url": "https://us.forums.blizzard.com/en/wow/t/x/1/8"}
    # Blizzard's follow-up post of Oct 27: bold race headings, then a plain lead-in for Skyborne.
    POST = ("<p>Additional updates to Racial Abilities and Talents include:</p>"
            "<p><strong>Undead</strong></p><ul><li>Touch of the Grave internal cooldown reduced to 15 seconds.</li></ul>"
            "<p>We’d also like to clarify that for Skyborne:</p>"
            "<ul><li>Charged persists through death, and is removed upon entering a raid.</li></ul>")

    def rows(self, cooked):
        return bn.finish(bn.parse_post(cooked, dict(self.BASE)))

    def test_plain_lead_in_naming_a_race_starts_its_group(self):
        by_text = {r["text"][:7]: r for r in self.rows(self.POST)}
        self.assertEqual(by_text["Charged"]["race"], "Skyborne")
        self.assertEqual((by_text["Charged"]["section"], by_text["Charged"]["path"]), ("Races", ["Skyborne"]))
        self.assertEqual(by_text["Touch o"]["race"], "Undead")

    def test_lead_in_naming_several_or_none_keeps_the_heading(self):
        post = ("<p><strong>Undead</strong></p>"
                "<p>Changes for Orcs and Trolls:</p><ul><li>Something changed.</li></ul>"
                "<p>Also note this:</p><ul><li>Another thing changed.</li></ul>")
        self.assertEqual({r["race"] for r in self.rows(post)}, {"Undead"})

    def test_plural_and_two_word_names(self):
        self.assertEqual(bn.named_in("A clarification for Night Elves:"), ["Night Elf"])
        self.assertEqual(bn.named_in("Dwarves and Gnomes:"), ["Dwarf", "Gnome"])
        self.assertEqual(bn.named_in("For Hunters:"), ["Hunter"])


if __name__ == "__main__":
    unittest.main()

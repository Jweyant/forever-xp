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


class Announcements(unittest.TestCase):
    RAW = {"id": 2394467, "title": "Overly Restrictive Name Check and Fix Incoming - October 27",
           "slug": "overly-restrictive-name-check-and-fix-incoming-october-27", "created_at": "2026-10-28T01:28:00.000Z",
           "category_id": 347, "excerpt": "In WoW Forever, we’ve been working on the restricted name list&hellip;", "user": "Kaivax"}

    def test_a_staff_topic_becomes_a_news_entry(self):
        a = bn.announcement(dict(self.RAW))
        self.assertEqual(a["url"], "https://us.forums.blizzard.com/en/wow/t/overly-restrictive-name-check-and-fix-incoming-october-27/2394467")
        self.assertEqual((a["date"], a["category"], a["kind"]), ("2026-10-28", "General Discussion", "Forum post"))
        self.assertEqual(a["excerpt"], "In WoW Forever, we’ve been working on the restricted name list…")
        self.assertNotIn("notes", a)

    def test_articles_and_note_topics_are_marked(self):
        art = bn.announcement(dict(self.RAW, user="BlizzardEntertainment", title="Your Next Adventure Starts in the Portal Room"))
        self.assertEqual(art["kind"], "Article")
        notes = bn.announcement(dict(self.RAW, title="WoW Forever Hotfixes - November 4"))
        self.assertEqual(notes["notes"], 1)

    def test_hostile_fields_are_cleaned_or_rejected(self):
        a = bn.announcement(dict(self.RAW, slug='x"><script>alert(1)</script>/../../evil', excerpt='<img src=x onerror=alert(1)><b>Hi</b> there'))
        self.assertTrue(bn.ANNOUNCEMENT_URL.match(a["url"]), a["url"])
        self.assertNotIn("<", a["excerpt"])
        self.assertEqual(a["excerpt"], "Hi there")
        for bad in ({"id": "1"}, {"id": -4}, {"title": ""}, {"title": None}, {"created_at": "yesterday"}):
            self.assertIsNone(bn.announcement(dict(self.RAW, **bad)), bad)
        self.assertIsNone(bn.announcement("not a dict"))

    def test_earlier_finds_are_kept_but_checked(self):
        old = bn.announcement(dict(self.RAW, id=2393431, title="Name Reservation Issue for Oceanic Players", slug="name-reservation-issue"))
        forged = dict(old, id=5, url="https://evil.example/t/x/5")
        news = bn.announcements({self.RAW["id"]: dict(self.RAW)}, previous=[old, forged, "junk", {"id": 6}])
        self.assertEqual([a["id"] for a in news], [2394467, 2393431])

    def test_this_runs_copy_wins_and_the_list_is_capped(self):
        old = dict(bn.announcement(dict(self.RAW)), title="Old title")
        news = bn.announcements({self.RAW["id"]: dict(self.RAW)}, previous=[old])
        self.assertEqual(news[0]["title"], self.RAW["title"])
        many = [bn.announcement(dict(self.RAW, id=i, title=f"Post {i}")) for i in range(1, bn.MAX_ANNOUNCEMENTS + 20)]
        self.assertEqual(len(bn.announcements({}, previous=many)), bn.MAX_ANNOUNCEMENTS)

    def test_blue_tracker_keeps_only_topic_starts_in_forever_categories(self):
        real = bn.get
        try:
            bn.get = lambda url: [
                {"topic_id": 1, "post_number": 1, "category_id": 347, "topic_title": "Realm list", "topic_slug": "realm-list",
                 "created_at": "2026-11-03T18:00:00Z", "excerpt": "Here are the realms", "username": "NewCM"},
                {"topic_id": 2, "post_number": 3, "category_id": 347, "topic_title": "A reply", "created_at": "2026-11-03T18:00:00Z"},
                {"topic_id": 3, "post_number": 1, "category_id": 171, "topic_title": "Midnight news", "created_at": "2026-11-03T18:00:00Z"},
            ]
            self.assertEqual(list(bn.tracker([346, 347])), [1])
        finally:
            bn.get = real

    def test_link_previews_and_invisible_characters_are_left_out(self):
        a = bn.announcement(dict(self.RAW, title="Podcast ft. ‪@Shobek‬", excerpt="[Your Next Adventure | Episode 6] Whether you’re new"))
        self.assertEqual(a["title"], "Podcast ft. @Shobek")
        self.assertEqual(a["excerpt"], "Whether you’re new")

    def test_a_post_in_two_sections_on_one_day_is_listed_once(self):
        first = dict(self.RAW, id=2390465, category_id=349, title="Thank You For Testing the WoW Forever Beta")
        news = bn.announcements({1: first, 2: dict(first, id=2390466, category_id=347)})
        self.assertEqual([a["id"] for a in news], [2390465])

    def test_category_names_are_shortened(self):
        self.assertEqual(bn.short_category("World of Warcraft: Forever General Discussion"), "General Discussion")
        self.assertEqual(bn.short_category("WoW: Forever Beta Discussion"), "Beta Discussion")
        self.assertEqual(bn.short_category("WoW: Forever"), "WoW Forever")


if __name__ == "__main__":
    unittest.main()

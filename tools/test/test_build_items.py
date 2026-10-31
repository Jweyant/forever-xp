"""Offline tests for tools/build_items.py: item display ids (the 3D model an item uses)."""
import sys
import json
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_items  # noqa: E402
import mysqldump  # noqa: E402

IMA = ("ID,ItemID,ItemAppearanceModifierID,ItemAppearanceID,OrderIndex,TransmogSourceTypeEnum\n"
       "10,19019,0,500,0,0\n"
       "11,19019,1,501,1,0\n"     # a later appearance of the same item: ignored
       "12,22632,0,502,0,0\n"
       "13,55555,0,999,0,0\n"     # appearance id with no ItemAppearance row: no display id
       "14,66666,0,503,0,0\n")    # appearance whose display info id is 0: no display id
APP = ("ID,DisplayType,ItemDisplayInfoID,DefaultIconFileDataID,UiOrder\n"
       "500,0,30606,1,0\n"
       "501,0,30607,1,0\n"
       "502,0,193838,1,0\n"
       "503,0,0,1,0\n")

ITEM_TEMPLATE = """DROP TABLE IF EXISTS `item_template`;
CREATE TABLE `item_template` (
  `entry` mediumint(8) unsigned NOT NULL DEFAULT 0,
  `displayid` mediumint(8) unsigned NOT NULL DEFAULT 0,
  `name` varchar(255) NOT NULL
);
INSERT INTO `item_template` VALUES (19019,30606,'Thunderfury'),(77777,0,'No art'),(88888,12345,'Not kept');
"""


class DisplayIds(unittest.TestCase):
    def test_maps_items_to_their_default_appearance(self):
        with tempfile.TemporaryDirectory() as cache:
            d = Path(cache) / build_items.FOREVER_BUILD
            d.mkdir(parents=True)
            (d / "ItemModifiedAppearance.csv").write_text(IMA)
            (d / "ItemAppearance.csv").write_text(APP)
            self.assertEqual(build_items.display_ids(cache, False), {19019: 30606, 22632: 193838})

    def test_missing_tables_mean_no_display_ids_not_a_crash(self):
        with tempfile.TemporaryDirectory() as cache:
            self.assertEqual(build_items.display_ids(cache, False), {})

    def test_cmangos_item_template_is_the_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            sql = Path(tmp) / "cmangos.sql"
            sql.write_text(ITEM_TEMPLATE)
            d = mysqldump.read(sql, ["item_template"])
            keep = {19019, 77777}
            display = {r["entry"]: r["displayid"] for r in d["item_template"]
                       if r.get("entry") in keep and isinstance(r.get("displayid"), int) and r["displayid"] > 0}
            self.assertEqual(display, {19019: 30606})  # 0 and not-kept display ids stay out

    def test_forever_changes(self):
        items = {1: {"ilvl": 30, "q": 3, "req": 25}, 2: {"ilvl": 20, "q": 2, "req": 15}, 3: {"ilvl": 10, "q": 2, "req": 5}}
        classic = {2: {"ItemLevel": 18, "Quality": 2, "RequiredLevel": 13}, 3: {"ItemLevel": 10, "Quality": 2, "RequiredLevel": 5}}
        self.assertEqual(build_items.forever_changes(items, classic), (1, 1))
        self.assertEqual(items[1].get("new"), 1)
        self.assertEqual(items[2]["chg"], [["item level", 18, 20], ["required level", 13, 15]])
        self.assertNotIn("chg", items[3])
        self.assertEqual(build_items.forever_changes({4: {}}, {}), (0, 0))  # no classic data: mark nothing

    def test_other_items(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "q.sqlite"
            db = sqlite3.connect(path)
            db.executescript("CREATE TABLE zones (id INTEGER, name TEXT); CREATE TABLE npcs (id INTEGER, name TEXT, zone_id INTEGER);"
                             "CREATE TABLE objects (id INTEGER, name TEXT); CREATE TABLE quests (id INTEGER, name TEXT, json TEXT);"
                             "CREATE TABLE items (id INTEGER, name TEXT, json TEXT);")
            db.execute("INSERT INTO zones VALUES (12, 'Elwynn_Forest')")
            db.execute("INSERT INTO npcs VALUES (299, 'Young Wolf', 12)")
            db.execute("INSERT INTO quests VALUES (33, 'Wolves Across the Border', ?)", (json.dumps({"objectives": [None, None, [[750]]]}),))
            rows = [(750, "Tough Wolf Meat", {"class": 12, "npcDrops": [299]}), (19019, "Thunderfury", {"class": 2}),
                    (5, "Test Potion", {"class": 0}), (6, "Gear Item", {"class": 0})]
            db.executemany("INSERT INTO items VALUES (?,?,?)", [(i, n, json.dumps(j)) for i, n, j in rows])
            db.commit()
            out = build_items.other_items(path, {6}, {750: {"Quality": 1}})
        self.assertEqual(out, [{"id": 750, "n": "Tough Wolf Meat", "q": 1, "c": "Quest item",
                                "d": [["Young Wolf", "Elwynn Forest"]], "qu": [[33, "Wolves Across the Border"]]}])


if __name__ == "__main__":
    unittest.main()

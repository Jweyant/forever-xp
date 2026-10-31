"""Offline tests for tools/build_items.py: item display ids (the 3D model an item uses)."""
import sys
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


if __name__ == "__main__":
    unittest.main()

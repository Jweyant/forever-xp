"""The gear job's change check: rebuild when the client build or a source moved, or when unsure."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gear_gate  # noqa: E402

REPORT = """# Gear database

Forever client build 1.60.1.70888.

- Equippable items: 11357

Sources: cmangos c33f90b, AtlasLoot 8e99341, opendata 4f68475, wowsims e855db5, wowsims-items 65d253a, Questie 7f6d6dd
"""
HEADS = {"wowsims-items": "65d253a" + "0" * 33, "Questie": "7f6d6dd" + "a" * 33}


class Gate(unittest.TestCase):
    def test_reads_the_report(self):
        build, shas = gear_gate.recorded(REPORT)
        self.assertEqual(build, "1.60.1.70888")
        self.assertEqual(shas["wowsims"], "e855db5")
        self.assertEqual(shas["questie"], "7f6d6dd")

    def test_nothing_changed(self):
        self.assertEqual(gear_gate.reasons(REPORT, "1.60.1.70888", HEADS), [])

    def test_a_new_build_or_a_moved_source_rebuilds(self):
        self.assertEqual(gear_gate.reasons(REPORT, "1.60.1.70901", HEADS), ["client build 1.60.1.70888 -> 1.60.1.70901"])
        moved = dict(HEADS, **{"wowsims-items": "1234567" + "0" * 33})
        self.assertEqual(gear_gate.reasons(REPORT, "1.60.1.70888", moved), ["wowsims-items 65d253a -> 1234567"])

    def test_anything_unreadable_rebuilds(self):
        self.assertTrue(gear_gate.reasons("", "1.60.1.70888", HEADS))                       # no report
        self.assertTrue(gear_gate.reasons(REPORT, "1.60.1.70888", {"wowsims": ""}))         # ls-remote failed
        self.assertTrue(gear_gate.reasons(REPORT, "1.60.1.70888", {"wowsims": "$(rm -rf)"}))
        self.assertTrue(gear_gate.reasons(REPORT, "1.60.1.70888", {"newsource": "a" * 40}))  # not recorded yet
        odd = REPORT.replace("wowsims e855db5", "wowsims <script>")
        self.assertEqual(gear_gate.recorded(odd)[1].get("wowsims"), None)


if __name__ == "__main__":
    unittest.main()

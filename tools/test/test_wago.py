"""Offline tests for tools/wago.py: picking the newest client build from wago.tools' list."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import wago  # noqa: E402

BUILDS = {
    "wow": [{"version": "12.1.5.70575"}],
    "wowf": [{"version": "1.60.1.70245"}, {"version": "1.60.1.70532"}],
    "wow_classic_beta": [{"version": "1.60.2.70999"}, {"version": "1.60.1.70532"}],
    "wow_classic_era": [{"version": "1.15.9.69722"}, {"version": "1.15.9.70003"}],
    "wow_classic_era_ptr": [{"version": "1.15.9.71000"}],
}


class Pick(unittest.TestCase):
    def test_prefers_the_live_forever_client(self):
        self.assertEqual(wago.pick(BUILDS, wago.FOREVER_PRODUCTS, wago.FOREVER_VERSION), ("1.60.1.70532", "wowf"))

    def test_falls_back_to_the_beta_when_there_is_no_live_build(self):
        b = {k: v for k, v in BUILDS.items() if k != "wowf"}
        self.assertEqual(wago.pick(b, wago.FOREVER_PRODUCTS, wago.FOREVER_VERSION), ("1.60.2.70999", "wow_classic_beta"))

    def test_newest_by_build_number_and_never_the_ptr(self):
        self.assertEqual(wago.pick(BUILDS, wago.CLASSIC_PRODUCTS, wago.CLASSIC_VERSION), ("1.15.9.70003", "wow_classic_era"))

    def test_hostile_versions_are_ignored(self):
        b = {"wowf": [{"version": "1.60.1.70532/../../etc"}, {"version": "1.60.1.70600?x=1"}, {"version": 7},
                      {"version": "1.60.1.70533"}, "junk"]}
        self.assertEqual(wago.pick(b, wago.FOREVER_PRODUCTS, wago.FOREVER_VERSION), ("1.60.1.70533", "wowf"))

    def test_forced_build_must_look_like_a_build(self):
        self.assertEqual(wago.forever_build("1.60.3.71234"), ("1.60.3.71234", "forced"))
        with self.assertRaises(SystemExit):
            wago.forever_build("../../secrets")


if __name__ == "__main__":
    unittest.main()

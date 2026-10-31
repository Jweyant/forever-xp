"""Offline tests for tools/check_talent_order.py and the talent builds in the sim setups."""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import check_talent_order as cto  # noqa: E402
import site_data  # noqa: E402

TALENTS = json.loads((ROOT / "gamedata" / "talents.json").read_text())


def fake_engine(root, cls, ids, sizes):
    (root / "proto").mkdir(parents=True, exist_ok=True)
    (root / "sim" / cls.lower()).mkdir(parents=True, exist_ok=True)
    fields = "\n".join(f"    int32 t{i} = {i + 1} [(talent_spell_id) = {s}];" for i, s in enumerate(ids))
    (root / "proto" / f"{cls.lower()}.proto").write_text(f"message {cls}Talents {{\n{fields}\n}}\n")
    (root / "sim" / cls.lower() / f"{cls.lower()}.go").write_text(
        "var TalentTreeSizes = [3]int{%d, %d, %d}\n" % tuple(sizes))


class TalentOrder(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.warrior = next(t for t in TALENTS["talents"] if t[1] == "Warrior")
        self.ids = [t[11] for _, _, _, tals in self.warrior[2] for t in tals]
        self.sizes = [len(tals) for _, _, _, tals in self.warrior[2]]
        cfg = self.tmp / "configs"
        cfg.mkdir()
        (cfg / "index.json").write_text(json.dumps([{"key": "WARRIOR.arms", "file": "w.siml"}]))
        self.siml = cfg / "w.siml"
        self.talents_json = self.tmp / "talents.json"
        self.talents_json.write_text(json.dumps({"talents": [self.warrior]}))

    def run_check(self, build, engine_ids):
        self.siml.write_text(f'siml 1\nspec dps_warrior\ntalents "{build}"\n')
        fake_engine(self.tmp / "eng", "Warrior", engine_ids, self.sizes)
        return cto.check(self.talents_json, self.tmp / "eng", self.tmp / "configs")

    def test_same_order_passes(self):
        errors, warnings = self.run_check("30325213132515201-0505-2", self.ids)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_swap_under_points_fails(self):
        swapped = self.ids[:]
        swapped[0], swapped[1] = swapped[1], swapped[0]
        errors, warnings = self.run_check("30325213132515201-0505-2", swapped)
        self.assertEqual(len(errors), 1)  # "30..." : only the first of the two swapped talents holds points
        self.assertTrue(warnings)

    def test_swap_without_points_only_warns(self):
        swapped = self.ids[:]
        a = self.sizes[0]  # first two Fury talents
        swapped[a], swapped[a + 1] = swapped[a + 1], swapped[a]
        errors, warnings = self.run_check("30325213132515201--2", swapped)
        self.assertEqual(errors, [])
        self.assertEqual(len(warnings), 1)


class SetupBuilds(unittest.TestCase):
    def test_every_setup_build_fits_forever_trees(self):
        trees = {name.upper(): [[t[4] for t in tals] for _, _, _, tals in tr] for _, name, tr in TALENTS["talents"]}
        for cls, file, build in cto.setups(ROOT / "gamedata" / "simconfigs"):
            self.assertRegex(build, r"^[0-9-]+$", file)
            parts = build.split("-")
            ranks = trees[cls.upper()]
            self.assertLessEqual(len(parts), 3, file)
            spent = 0
            for ti, part in enumerate(parts):
                self.assertLessEqual(len(part), len(ranks[ti]), f"{file}: tree {ti + 1} is too long")
                for k, ch in enumerate(part):
                    self.assertLessEqual(int(ch), ranks[ti][k], f"{file}: tree {ti + 1} talent {k + 1}")
                    spent += int(ch)
            self.assertLessEqual(spent, 51, file)


class PlannerHitTalents(unittest.TestCase):
    def test_every_hit_talent_is_in_forever_and_talks_about_hit(self):
        found = {}
        for _, _, trees in TALENTS["talents"]:
            for _, _, _, tals in trees:
                for t in tals:
                    if t[11] in site_data.HIT_TALENTS:
                        found[t[11]] = t
        self.assertEqual(set(found), set(site_data.HIT_TALENTS), "a hit talent isn't in Forever's trees")
        for spell, t in found.items():
            self.assertRegex(t[8][0], re.compile(r"chance to hit|hit chance", re.I), t[3])
            kind, _ = site_data.HIT_TALENTS[spell]
            self.assertRegex(kind, r"^(phys|all|spell:(all|[a-z]+(,[a-z]+)*))$")

    def test_planner_data_has_hit_values_per_rank(self):
        classes = []
        for cid, name, trees in TALENTS["talents"]:
            classes.append({"slug": site_data.slugify(name)})
        out = site_data.planner_talents(classes, TALENTS["talents"])
        self.assertEqual(set(out), {"WARRIOR", "PALADIN", "HUNTER", "ROGUE", "PRIEST", "SHAMAN", "MAGE", "WARLOCK", "DRUID"})
        for cls, c in out.items():
            for h in c["hit"]:
                ranks = c["trees"][h["tree"]][1][h["i"]][1]
                self.assertEqual(len(h["pct"]), ranks, h["name"])
                self.assertTrue(all(0 < p <= 20 for p in h["pct"]), h["name"])


if __name__ == "__main__":
    unittest.main()

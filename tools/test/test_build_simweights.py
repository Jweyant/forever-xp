"""Offline tests for tools/build_simweights.py: reading wowsims presets as text, never as code."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_simweights as bs  # noqa: E402

FURY = """import * as PresetUtils from '@app/preset_utils';
// Measured on the Pre-BiS Fury gear with the Fury talents.
export const PreBiSFuryEpWeights = PresetUtils.makePresetEpWeights(
	'Pre-BiS - Fury',
	Stats.fromMap(
		{
			[Stat.StatStrength]: 2.2,
			[Stat.StatHitRating]: 2.29, // a comment with a ) in it
			[Stat.StatArmorPenetration]: 0.41,
			[Stat.StatCritRating]: 2.92 * Mechanics.SOMETHING,
			[Stat.StatHasteRating]: 1e9,
		},
		{
			[PseudoStat.PseudoStatMainHandDps]: 9.89,
			[PseudoStat.PseudoStatOffHandDps]: 3.15,
		},
	),
);
export const OtherEpWeights = PresetUtils.makePresetEpWeights('Not In The Map', Stats.fromMap({ [Stat.StatAgility]: 1 }));
"""
FERAL_EP = """export const CatEp = Stats.fromMap({ [Stat.StatAgility]: 0.5159, [Stat.StatAttackPower]: 0.2047 });
export const HybridEp = CatEp.add(BearEp).scale(0.5);
"""
FERAL_PRESETS = """import { CatEp, HybridEp } from '../feral_ep';
export const DefaultEp = CatEp;
export const DefaultEpWeights = PresetUtils.makePresetEpWeights('Cat', DefaultEp);
export const HybridEpWeights = PresetUtils.makePresetEpWeights('Hybrid', HybridEp);
"""
ESCAPE = """import { Sneaky } from '../../../../outside';
export const X = PresetUtils.makePresetEpWeights('Cat', Sneaky);
"""


def tree(files):
    d = tempfile.TemporaryDirectory()
    for rel, text in files.items():
        p = Path(d.name) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return d


class SimWeights(unittest.TestCase):
    def test_reads_plain_numbers_and_drops_everything_else(self):
        with tree({"ui/specs/warrior/dps/presets.ts": FURY}) as d:
            out = bs.build(d, "0" * 40)
        fury = out["specs"]["WARRIOR.fury"][0]
        self.assertEqual(fury["label"], "Pre-BiS - Fury")
        # Armor pen isn't on Forever items, an expression isn't a number, 1e9 is out of bounds.
        self.assertEqual(fury["w"], {"str": 2.2, "hit": 2.29, "dps": 9.89, "dps_oh": 3.15})
        self.assertEqual(fury["note"], "Measured on the Pre-BiS Fury gear with the Fury talents.")
        self.assertIn("warrior/dps: Not In The Map", out["report"]["unmapped"])
        skipped = out["report"]["skipped_stats"]
        self.assertIn("StatArmorPenetration", skipped)
        self.assertIn("StatCritRating (not a plain number)", skipped)
        self.assertIn("StatHasteRating (out of bounds)", skipped)

    def test_follows_aliases_and_imports_but_not_computed_values(self):
        with tree({"ui/specs/druid/feral_ep.ts": FERAL_EP, "ui/specs/druid/feralcat/presets.ts": FERAL_PRESETS}) as d:
            out = bs.build(d, "0" * 40)
        self.assertEqual(out["specs"]["DRUID.cat"][0]["w"], {"agi": 0.5159, "ap": 0.2047})
        self.assertEqual(len(out["specs"]["DRUID.cat"]), 1)  # Hybrid is computed in code: skipped

    def test_imports_cannot_leave_the_specs_folder(self):
        with tree({"ui/specs/druid/feralcat/presets.ts": ESCAPE,
                   "outside.ts": "export const Sneaky = Stats.fromMap({ [Stat.StatAgility]: 9 });"}) as d:
            out = bs.build(d, "0" * 40)
        self.assertNotIn("DRUID.cat", out["specs"])

    def test_notes_are_short_plain_text(self):
        hostile = "// <img src=x onerror=alert(1)> " + "a" * 400 + "\n" + FURY.split("\n", 2)[2]
        with tree({"ui/specs/warrior/dps/presets.ts": hostile}) as d:
            note = bs.build(d, "0" * 40)["specs"]["WARRIOR.fury"][0]["note"]
        self.assertNotIn("<", note)
        self.assertLessEqual(len(note), 300)

    def test_the_mapping_only_names_real_specs(self):
        specs = {"WARRIOR": {"arms", "fury", "prot"}, "PALADIN": {"holy", "prot", "ret"},
                 "PRIEST": {"disc", "holy", "shadow"}, "ROGUE": {"assa", "combat", "sub"},
                 "SHAMAN": {"ele", "enh", "resto"}, "DRUID": {"balance", "cat", "bear", "resto"}}
        for _, key in bs.SPEC_MAP:
            cls, spec = key.split(".")
            self.assertIn(spec, specs[cls], key)


if __name__ == "__main__":
    unittest.main()

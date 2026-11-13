"""Talent builds: the recommended-builds extractor and the player-popularity aggregation."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import build_talent_builds  # noqa: E402


class Extractor(unittest.TestCase):
    def test_reads_simconfigs_and_wowsims(self):
        with tempfile.TemporaryDirectory() as tmp:
            sc = Path(tmp) / "simconfigs"
            sc.mkdir()
            (sc / "index.json").write_text(json.dumps([
                {"key": "HUNTER.sv", "label": "Planner BIS", "note": "our run", "file": "hunter.siml", "specDir": "hunter/dps"},
                {"key": "X", "label": "escape", "file": "../../etc/passwd", "specDir": "hunter/dps"},
            ]))
            (sc / "hunter.siml").write_text('spec hunter\ntalents "-00530501114-550200030050220151"\n')
            ws = Path(tmp) / "wowsims" / "ui" / "specs" / "hunter" / "dps" / "builds"
            ws.mkdir(parents=True)
            (ws / "sv_weave.siml").write_text('talents "-00530501114-550200030050220151"\n')
            (ws / "smoke_testing.siml").write_text('talents "5-5"\n')          # testing setups stay out
            (ws / "bad.siml").write_text('talents "99<script>"\n')             # invalid string stays out
            (ws / "aff.build.json").write_text(json.dumps({"player": {"talentsString": "255-1"}}))
            (ws.parent / "presets.ts").write_text(
                "export const A = PresetUtils.makePresetTalents('Arcane', SavedTalents.create({ talentsString: '0502-1' }));\n"
                "export const B = { name: 'Asn Muti', data: SavedTalents.create({ talentsString: '005323-1' }) };\n"
                "export const C = PresetUtils.makePresetTalents('Smoke Testing', SavedTalents.create({ talentsString: '1' }));\n")
            o = build_talent_builds.ours(sc)
            w = build_talent_builds.wowsims(Path(tmp) / "wowsims")
        self.assertEqual(o, {"hunter": [{"n": "Planner BIS", "t": "-00530501114-550200030050220151", "note": "our run"}]})
        self.assertEqual(w, {"hunter": [{"n": "Arcane", "t": "0502-1"}, {"n": "Asn Muti", "t": "005323-1"},
                                        {"n": "Aff", "t": "255-1"}, {"n": "SV Weave", "t": "-00530501114-550200030050220151"}]})

    def test_valid(self):
        self.assertTrue(build_talent_builds.valid("-00530501114-550200030050220151"))
        for bad in ("", "---", "6-1", "5" * 31, "51-", None, "5-5-5-5", "5" * 15 + "-" + "5" * 15):  # last: 150 points
            self.assertFalse(bool(build_talent_builds.valid(bad)), bad)


GUIDES_LUA = """
local _, ns = ...
ns.talents = {
  WARRIOR = {
    { name = "Arms", { "Improved Heroic Strike", 0, 0, 3 }, { "Deflection", 0, 1, 5 }, { "Mortal Strike", 6, 1, 1 } },
    { name = "Fury", { "Cruelty", 0, 2, 5 } },
    { name = "Protection", { "Shield Specialization", 0, 1, 5 } },
  },
  MAGE = {
    { name = "Arcane", { "Arcane Subtlety", 0, 0, 2 } },
    { name = "Fire", { "Improved Fireball", 0, 1, 5 } },
    { name = "Frost", { "Frost Warding", 0, 0, 2 } },
  },
}
ns.guides = {
  WARRIOR = {
    { id = "arms-warrior-pvp-guide", title = "Arms Warrior PvP guide: Mortal Strike burst", spec = "Arms", kind = "Endgame PvP", from = 10, to = 60, order = "000000010101010102" },
    { id = "arms-warrior-leveling", title = "Arms leveling", spec = "Arms", kind = "Leveling", from = 10, to = 60, order = "0000" },
    { id = "prot-warrior-raid", title = "Protection raid: main tank", spec = "Protection", kind = "Endgame PvE", from = 10, to = 60, order = "2020" },
    { id = "fury-warrior-pvp-guide", title = "Fury PvP: too many points", spec = "Fury", kind = "Endgame PvP", from = 10, to = 60, order = "101010101010" },
  },
  MAGE = {
    { id = "frost-mage-pvp-guide", title = "Frost PvP", spec = "Frost", kind = "Endgame PvP", from = 10, to = 60, order = "2020" },
  },
}
"""
OUR_TALENTS = {"talents": [
    [1, "Warrior", [[161, "Arms", 0, [[1, 0, 0, "Improved Heroic Strike", 3, None, None, "i", ["d"], 0, 0, 1],
                                      [2, 0, 1, "Deflection", 5, None, None, "i", ["d"], 0, 0, 2],
                                      [3, 6, 1, "Mortal Strike", 1, None, None, "i", ["d"], 0, 0, 3]]],
                    [164, "Fury", 0, [[4, 0, 2, "Cruelty", 5, None, None, "i", ["d"], 0, 0, 4]]],
                    [163, "Protection", 0, [[5, 0, 1, "Shield Specialization", 5, None, None, "i", ["d"], 0, 0, 5]]]]],
    [8, "Mage", [[81, "Arcane", 0, [[6, 0, 0, "Arcane Subtlety", 2, None, None, "i", ["d"], 0, 0, 6]]],
                 [41, "Fire", 0, [[7, 0, 1, "Improved Fireball", 5, None, None, "i", ["d"], 0, 0, 7]]],
                 [61, "Frost", 0, [[8, 0, 0, "Frost Warding", 3, None, None, "i", ["d"], 0, 0, 8]]]]],  # rank drifted: 3 vs their 2
]}


class Community(unittest.TestCase):
    def test_imports_only_matching_classes_and_valid_orders(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "Guides.lua").write_text(GUIDES_LUA)
            talents = Path(tmp) / "talents.json"
            talents.write_text(json.dumps(OUR_TALENTS))
            out = build_talent_builds.community(tmp, talents)
        # Arms PvP: 3 points in talent 0, 5 in talent 1, 1 in talent 2 (index 2 = Mortal Strike) -> "351"
        self.assertEqual(out, {"warrior": [{"n": "Arms PvP", "t": "351", "k": "pvp", "note": "Mortal Strike burst"},
                                           {"n": "Protection PvE", "t": "--2", "k": "pve", "note": "main tank"}]})
        # The leveling guide is skipped (kind), Fury PvP is skipped (6 points into a 5-rank talent),
        # and Mage is skipped entirely: Frost Warding's rank drifted, so the whole class fails the gate.
class PatchGates(unittest.TestCase):
    def test_presets_drop_where_the_order_moved_or_ranks_shrank(self):
        moved = {"warrior": [(1, 2)]}           # tree 1, position 2 disagrees with the engine
        ranks = {"warrior": [[3, 5, 1], [5, 5, 5], [5]]}
        ok = build_talent_builds.ok_for
        self.assertTrue(ok("warrior", "301-550", moved, ranks))      # no points at the moved spot
        self.assertFalse(ok("warrior", "301-551", moved, ranks))     # a point where orders disagree
        self.assertFalse(ok("warrior", "305", moved, ranks))         # rank 5 into a 1-rank talent
        self.assertFalse(ok("warrior", "3011", moved, ranks))        # more digits than the tree has
        self.assertTrue(ok("rogue", "999", moved, {}))               # no gate data: passes (tests)
        self.assertFalse(ok("priest", "5", {"priest": None}, {}))     # engine order unreadable: nothing passes


class EngineFormat(unittest.TestCase):
    def test_reads_both_proto_styles_and_refuses_a_mismatch(self):
        import check_talent_order as cto
        for opts in ("", ", (talent_max_rank) = 5"):
            with tempfile.TemporaryDirectory() as tmp:
                (Path(tmp) / "proto").mkdir()
                (Path(tmp) / "sim" / "rogue").mkdir(parents=True)
                (Path(tmp) / "proto" / "rogue.proto").write_text(
                    "message RogueTalents {\n    int32 a = 1 [(talent_spell_id) = 11%s];\n"
                    "    int32 b = 2 [(talent_spell_id) = 22%s];\n    bool c = 3 [(talent_spell_id) = 33];\n}\n" % (opts, opts))
                go = Path(tmp) / "sim" / "rogue" / "rogue.go"
                go.write_text("var TalentTreeSizes = [3]int{1, 1, 1}\n")
                self.assertEqual(cto.engine(tmp, "Rogue"), [[11], [22], [33]])
                go.write_text("var TalentTreeSizes = [3]int{1, 1, 2}\n")   # one more than the proto lists
                self.assertIsNone(cto.engine(tmp, "Rogue"))


if __name__ == "__main__":
    unittest.main()

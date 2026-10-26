"""Offline tests for tools/build_talents.py: tooltip text, the arithmetic parser, hotfixes, and a
small Forever trait tree turned into calculator data (no network)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_talents as bt  # noqa: E402


def spells(**over):
    T = {
        "SpellName": [{"ID": "100", "Name_lang": "Lingering Rage"}, {"ID": "200", "Name_lang": "Deep Wounds"},
                      {"ID": "300", "Name_lang": "Furious Precision"}, {"ID": "400", "Name_lang": "Sweeping Strikes"},
                      {"ID": "500", "Name_lang": "Rend"}],
        "Spell": [
            {"ID": "100", "Description_lang": "Increases the time before your Rage begins to decay by ${$s1/1000} sec."},
            {"ID": "200", "Description_lang": "Your critical strikes cause the target to bleed for $o1% of your weapon damage over $d."},
            {"ID": "300", "Description_lang": "Increases your chance to hit with off-hand attacks by $m1%.$?s400[ Also works with Sweeping Strikes.][]"},
            {"ID": "400", "Description_lang": "Your next $n melee $lattack:attacks; strike an additional target."},
            {"ID": "500", "Description_lang": "Wounds the target for $s1 damage every $t1 sec. $@spelldesc200"},
        ],
        "SpellEffect": [
            {"ID": "1", "SpellID": "100", "EffectIndex": "0", "DifficultyID": "0", "EffectBasePointsF": "2000"},
            {"ID": "2", "SpellID": "200", "EffectIndex": "0", "DifficultyID": "0", "EffectBasePointsF": "20",
             "EffectAuraPeriod": "3000"},
            {"ID": "3", "SpellID": "300", "EffectIndex": "0", "DifficultyID": "0", "EffectBasePointsF": "4"},
            {"ID": "4", "SpellID": "500", "EffectIndex": "0", "DifficultyID": "0", "EffectBasePointsF": "-7",
             "EffectAuraPeriod": "3000"},
        ],
        "SpellMisc": [{"ID": "9", "SpellID": "200", "DifficultyID": "0", "DurationIndex": "5", "SpellIconFileDataID": "77"},
                      {"ID": "8", "SpellID": "100", "DifficultyID": "0", "DurationIndex": "0", "SpellIconFileDataID": "78"}],
        "SpellDuration": [{"ID": "5", "Duration": "12000"}],
        "SpellRadius": [],
        "SpellAuraOptions": [{"ID": "1", "SpellID": "400", "DifficultyID": "0", "ProcCharges": "1"}],
    }
    T.update(over)
    return bt.Spells(T)


class Tooltips(unittest.TestCase):
    def test_expression_and_rank_values(self):
        S = spells()
        self.assertEqual(S.render("100"), "Increases the time before your Rage begins to decay by 2 sec.")
        third = S.render("100", lambda s, i: 6000.0)
        self.assertTrue(third.endswith("by 6 sec."))

    def test_periodic_total_and_duration(self):
        self.assertEqual(spells().render("200"),
                         "Your critical strikes cause the target to bleed for 80% of your weapon damage over 12 sec.")

    def test_conditional_shows_the_plain_text(self):
        self.assertEqual(spells().render("300"), "Increases your chance to hit with off-hand attacks by 4%.")

    def test_plural_follows_the_number(self):
        self.assertEqual(spells().render("400"), "Your next 1 melee attack strike an additional target.")

    def test_negative_values_and_spell_references(self):
        out = spells().render("500")
        self.assertTrue(out.startswith("Wounds the target for 7 damage every 3 sec. Your critical strikes"))

    def test_unknown_tokens_are_counted_not_executed(self):
        S = spells(Spell=[{"ID": "100", "Description_lang": "x ${__import__('os').system('true')} $<secret> y"}])
        self.assertEqual(S.render("100"), "x ? ? y")
        self.assertTrue(S.unknown)


class Arithmetic(unittest.TestCase):
    def test_parser(self):
        self.assertEqual(bt.Expr("2+3*4").eval(), 14)
        self.assertEqual(bt.Expr("(2+3)*4").eval(), 20)
        self.assertEqual(bt.Expr("max(2,7)/2").eval(), 3.5)
        self.assertEqual(bt.Expr("1/0").eval(), 0)
        self.assertEqual(bt.Expr("-3+1").eval(), -2)

    def test_rejects_anything_else(self):
        for bad in ("__import__", "a.b", "open(1)", "1;2", "'x'"):
            with self.assertRaises(ValueError):
                bt.Expr(bad).eval()


class Packing(unittest.TestCase):
    def test_template(self):
        self.assertEqual(bt.pack(["Hit +4%.", "Hit +7%.", "Hit +10%."]), ["Hit +{0}%.", [[4.0], [7.0], [10.0]]])

    def test_same_text(self):
        self.assertEqual(bt.pack(["Learn it.", "Learn it."]), ["Learn it.", 0])

    def test_different_words(self):
        self.assertEqual(bt.pack(["1 sec", "1 min"]), [["1 sec", "1 min"]])


class Hotfixes(unittest.TestCase):
    def test_add_replace_remove_and_cancel(self):
        cols = ["Name_lang", "ID", "SpellID", "Ranks_0", "Ranks_1"]
        rows = [{"Name_lang": "Old", "ID": "1", "SpellID": "10", "Ranks_0": "1", "Ranks_1": "2"},
                {"Name_lang": "Gone", "ID": "2", "SpellID": "20", "Ranks_0": "0", "Ranks_1": "0"}]
        fixes = [
            {"record_id": 1, "status": 1, "data": ["New", 1, 11, [3, 4]]},
            {"record_id": 2, "status": 2, "data": []},
            {"record_id": 3, "status": 1, "data": ["Added", 3, 30, [0, 0]]},
            {"record_id": 3, "status": 3, "data": []},
            {"record_id": 4, "status": 1, "data": ["Too", "short"]},
        ]
        report = []
        out = {r["ID"]: r for r in bt.apply_hotfixes(rows, cols, fixes, report, "X")}
        self.assertEqual(out["1"]["Name_lang"], "New")
        self.assertEqual(out["1"]["Ranks_1"], "4")
        self.assertNotIn("2", out)
        self.assertNotIn("3", out)
        self.assertNotIn("4", out)
        self.assertIn("1 skipped", report[0])


def trait_tables():
    nodes, entries, defs, nxe, groups, gconds = [], [], [], [], [], []
    tals = [  # (node, section, col, row, spell, ranks)
        (1, 0, 0, 0, "100", 5), (2, 0, 0, 2, "200", 3), (3, 1, 1, 1, "300", 3), (4, 2, 3, 0, "400", 1)]
    for node, sec, col, row, sid, ranks in tals:
        x = bt.LEFT + sec * bt.SECTION + col * bt.GRID + (60 if sec == 2 else 0)
        nodes.append({"ID": str(node), "TraitTreeID": "1117", "PosX": str(x), "PosY": str(2130 + row * bt.GRID),
                      "Type": "0", "Flags": "0"})
        entries.append({"ID": str(node * 10), "TraitDefinitionID": str(node * 100), "MaxRanks": str(ranks)})
        defs.append({"ID": str(node * 100), "SpellID": sid, "OverrideName_lang": "", "OverrideIcon": "0",
                     "OverrideDescription_lang": ""})
        nxe.append({"ID": str(node), "TraitNodeID": str(node), "TraitNodeEntryID": str(node * 10), "_Index": "0"})
        groups.append({"ID": str(node), "TraitNodeGroupID": f"g{row}", "TraitNodeID": str(node)})
    gconds = [{"ID": "1", "TraitCondID": "c2", "TraitNodeGroupID": "g2"}, {"ID": "2", "TraitCondID": "c1", "TraitNodeGroupID": "g1"}]
    tabs = []
    # Only the Warrior tree has talents in this fixture; the other classes get tabs and one empty node.
    for cid in bt.CLASS_NAME:
        if cid != 1:
            tabs += [{"ID": f"{cid}{k}", "Name_lang": f"T{k}", "ClassMask": str(1 << (cid - 1)), "OrderIndex": str(k)} for k in range(3)]
            nodes.append({"ID": f"n{cid}", "TraitTreeID": f"t{cid}", "PosX": str(bt.LEFT), "PosY": "2130"})
    return {
        "TraitTree": [{"ID": "1117"}], "TraitNode": nodes, "TraitNodeEntry": entries, "TraitDefinition": defs,
        "TraitNodeXTraitNodeEntry": nxe, "TraitNodeGroupXTraitNode": groups, "TraitNodeGroupXTraitCond": gconds,
        "TraitCond": [{"ID": "c1", "SpentAmountRequired": "5"}, {"ID": "c2", "SpentAmountRequired": "10"}],
        "TraitNodeXTraitCond": [],
        "TraitEdge": [{"ID": "1", "LeftTraitNodeID": "1", "RightTraitNodeID": "2", "Type": "2", "VisualStyle": "1"}],
        "TraitDefinitionEffectPoints": [{"ID": "1", "TraitDefinitionID": "300", "EffectIndex": "0", "OperationType": "0", "CurveID": "9"}],
        "CurvePoint": [{"ID": str(k), "CurveID": "9", "Pos_0": str(k), "Pos_1": str(v)} for k, v in ((1, 4), (2, 7), (3, 10))],
        "SkillLineXTraitTree": [{"ID": str(i), "SkillLineID": str(s), "TraitTreeID": "1117" if c == 1 else f"t{c}"}
                                for i, (s, c) in enumerate(bt.SKILL_CLASS.items())],
        "TalentTab": [{"ID": "161", "Name_lang": "Arms", "ClassMask": "1", "OrderIndex": "0"},
                      {"ID": "164", "Name_lang": "Fury", "ClassMask": "1", "OrderIndex": "1"},
                      {"ID": "163", "Name_lang": "Protection", "ClassMask": "1", "OrderIndex": "2"}] + tabs,
    }


class ForeverTrees(unittest.TestCase):
    def test_warrior_tree(self):
        T = trait_tables()
        report = []
        out = bt.forever_talents(T, spells(), {78: "spell_nature_bloodlust"}, report)
        war = out[0]
        self.assertEqual(war[1], "Warrior")
        arms, fury, prot = war[2]
        self.assertEqual([arms[1], fury[1], prot[1]], ["Arms", "Fury", "Protection"])
        self.assertEqual(arms[2], "ability_warrior_savageblow")
        lr, dw = arms[3]
        self.assertEqual(lr[:5], [1, 0, 0, "Lingering Rage", 5])
        self.assertEqual(lr[7], "spell_nature_bloodlust")
        self.assertEqual(lr[8][0], "Increases the time before your Rage begins to decay by {0} sec.")
        self.assertEqual([v[0] for v in lr[8][1]], [2, 4, 6, 8, 10])
        self.assertEqual(lr[9], 1, "no client rank values -> marked as estimated")
        self.assertEqual(dw[1:3], [2, 0])
        self.assertEqual(dw[5:7], [1, 5], "Deep Wounds needs all 5 ranks of the talent above it")
        self.assertEqual(dw[10], 10)
        fp = fury[3][0]
        self.assertEqual(fp[8], ["Increases your chance to hit with off-hand attacks by {0}%.", [[4.0], [7.0], [10.0]]])
        self.assertEqual(fp[9], 0)
        self.assertEqual(prot[3][0][1:3], [0, 3], "third tree is offset by 60 units but still column 3")

    def test_off_grid_node_fails_loudly(self):
        T = trait_tables()
        T["TraitNode"][0]["PosX"] = str(bt.LEFT + 2 * bt.SECTION + 5 * bt.GRID)
        with self.assertRaises(SystemExit) as e:
            bt.forever_talents(T, spells(), {}, [])
        self.assertIn("off the 3x4 grid", str(e.exception))

    def test_parked_node_is_skipped(self):
        T = trait_tables()
        T["TraitNode"].append({"ID": "99", "TraitTreeID": "1117", "PosX": "102800", "PosY": "5740"})
        T["TraitNode"].append({"ID": "98", "TraitTreeID": "1117", "PosX": "6820", "PosY": "39300"})
        report = []
        bt.forever_talents(T, spells(), {}, report)
        self.assertEqual(sum("outside the three trees" in r for r in report), 2)

    def test_hotfix_collision_moves_the_other_talent(self):
        T = trait_tables()
        # node 2 (Deep Wounds, row 2 col 0) gets a node 5 hotfixed onto its spot
        T["TraitNode"].append({"ID": "5", "TraitTreeID": "1117", "PosX": str(bt.LEFT), "PosY": str(2130 + 2 * bt.GRID)})
        T["TraitNodeEntry"].append({"ID": "50", "TraitDefinitionID": "500", "MaxRanks": "1"})
        T["TraitDefinition"].append({"ID": "500", "SpellID": "500", "OverrideName_lang": ""})
        T["TraitNodeXTraitNodeEntry"].append({"ID": "5", "TraitNodeID": "5", "TraitNodeEntryID": "50", "_Index": "0"})
        bt.HOTFIXED["TraitNode"] = {"5"}
        try:
            report = []
            out = bt.forever_talents(T, spells(), {}, report)
        finally:
            bt.HOTFIXED.clear()
        arms = out[0][2][0][3]
        spots = {t[3]: (t[1], t[2]) for t in arms}
        self.assertEqual(spots["Rend"], (2, 0))
        self.assertEqual(spots["Deep Wounds"], (2, 1))
        self.assertTrue(any("a hotfix moved Rend onto Deep Wounds" in r for r in report))

    def test_collision_without_hotfix_fails(self):
        T = trait_tables()
        T["TraitNode"].append({"ID": "5", "TraitTreeID": "1117", "PosX": str(bt.LEFT), "PosY": str(2130 + 2 * bt.GRID)})
        T["TraitNodeEntry"].append({"ID": "50", "TraitDefinitionID": "500", "MaxRanks": "1"})
        T["TraitDefinition"].append({"ID": "500", "SpellID": "500", "OverrideName_lang": ""})
        T["TraitNodeXTraitNodeEntry"].append({"ID": "5", "TraitNodeID": "5", "TraitNodeEntryID": "50", "_Index": "0"})
        with self.assertRaises(SystemExit) as e:
            bt.forever_talents(T, spells(), {}, [])
        self.assertIn("share a spot", str(e.exception))


if __name__ == "__main__":
    unittest.main()

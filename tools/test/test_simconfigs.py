"""Offline checks for gamedata/simconfigs: the setups the Sim weights workflow runs."""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIGS = ROOT / "gamedata" / "simconfigs"

SPECS = {"WARRIOR": {"arms", "fury", "prot"}, "PALADIN": {"holy", "prot", "ret"},
         "HUNTER": {"bm", "mm", "sv"}, "ROGUE": {"assa", "combat", "sub"},
         "PRIEST": {"disc", "holy", "shadow"}, "SHAMAN": {"ele", "enh", "resto"},
         "MAGE": {"arcane", "fire", "frost"}, "WARLOCK": {"aff", "demo", "destro"},
         "DRUID": {"balance", "cat", "bear", "resto"}}
ENTRY_KEYS = {"key", "label", "note", "file", "specDir", "aplJson", "hps"}
SAFE = re.compile(r"^[ -~·]*$")  # printable ASCII plus the separator dot the labels use


class SimConfigs(unittest.TestCase):
    def setUp(self):
        self.index = json.loads((CONFIGS / "index.json").read_text())

    def test_entries_are_well_formed(self):
        self.assertTrue(self.index)
        for e in self.index:
            self.assertFalse(set(e) - ENTRY_KEYS, e)
            cls, _, spec = e["key"].partition(".")
            self.assertIn(spec, SPECS.get(cls, set()), e["key"])
            self.assertTrue(SAFE.match(e["label"]) and len(e["label"]) <= 60, e["label"])
            self.assertTrue(SAFE.match(e["note"]) and len(e["note"]) <= 300)
            self.assertTrue(re.fullmatch(r"[a-z0-9_]+\.siml", e["file"]), e["file"])
            self.assertTrue(re.fullmatch(r"[a-z]+/[a-z]+", e["specDir"]), e["specDir"])
            if e.get("aplJson"):
                self.assertTrue(re.fullmatch(r"ui/specs/[a-z/_]+\.apl\.json", e["aplJson"]), e["aplJson"])

    def test_setups_exist_and_their_gear_is_in_the_item_database(self):
        items = {i["id"] for i in json.loads((ROOT / "gamedata" / "items.json").read_text())["items"]}
        for e in self.index:
            text = (CONFIGS / e["file"]).read_text()
            self.assertTrue(text.startswith("siml 1"), e["file"])
            self.assertIn("\nspec ", text)
            self.assertIn("\ntalents ", text)
            self.assertIn("ep_weights_stats(", text)
            ids = [int(m) for m in re.findall(r'\{"id":\s*(\d+)\}', text)]
            self.assertGreaterEqual(len(ids), 15, e["file"])
            missing = [i for i in ids if i not in items]
            self.assertFalse(missing, f"{e['file']}: not in gamedata/items.json: {missing}")

    def test_the_engine_pin_is_the_same_everywhere(self):
        gomod = (ROOT / "tools" / "simrunner" / "go.mod").read_text()
        pseudo = re.search(r"github\.com/wowsims/forever v0\.0\.0-\d{14}-([0-9a-f]{12})", gomod)
        self.assertIsNotNone(pseudo, "go.mod must pin wowsims/forever to a pseudo-version")
        workflow = (ROOT / ".github" / "workflows" / "sim-weights.yml").read_text()
        env = re.search(r"WOWSIMS_COMMIT:\s*([0-9a-f]{40})", workflow)
        self.assertIsNotNone(env, "the workflow must pin WOWSIMS_COMMIT")
        self.assertTrue(env.group(1).startswith(pseudo.group(1)),
                        "go.mod and sim-weights.yml pin different wowsims commits")


if __name__ == "__main__":
    unittest.main()

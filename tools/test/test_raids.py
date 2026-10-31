"""Dungeon and raid builder, and boss-kill aggregation from player logs."""
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import build_raids  # noqa: E402
import ingest_logs  # noqa: E402

ATLASLOOT = '''
data["MoltenCore"] = {
	MapID = 2717,
	InstanceID = 409,
	ContentType = RAID40_CONTENT,
	items = {
		{	--MCLucifron
			name = AL["Lucifron"],
			npcID = 12118,
			[NORMAL_DIFF] = {
				{ 1, 16800 },	-- Arcanist Boots
				{ 2, 18879 },	-- Heavy Dark Iron Ring
				{ 3, 18879 },	-- listed twice
			},
		},
		{	--MCTrash
			name = AL["Trash"],
			[NORMAL_DIFF] = {
				{ 1, 17010 },
			},
		},
	},
}
data["Ragefire"] = {
	MapID = 2437,
	InstanceID = 389,
	ContentType = DUNGEON_CONTENT,
	LevelRange = {10, 13, 18},
	items = {
		{	--RFCTaragaman
			name = AL["Taragaman the Hungerer"],
			npcID = 11520,
			[NORMAL_DIFF] = {
				{ 1, 14149 },
			},
		},
	},
}
data["SomeBattleground"] = {
	ContentType = BG_CONTENT,
	items = { { name = AL["X"], npcID = 1, [NORMAL_DIFF] = { { 1, 12345 } } } },
}
'''


class AtlasLoot(unittest.TestCase):
    def test_parses_raids_and_dungeons(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "AtlasLootClassic_DungeonsAndRaids"
            d.mkdir()
            (d / "data.lua").write_text(ATLASLOOT)
            raids = build_raids.atlasloot_raids(tmp)
        self.assertEqual([(r["name"], r["kind"], r["size"]) for r in raids],
                         [("Molten Core", "raid", 40), ("Ragefire Chasm", "dungeon", 5)])
        mc = raids[0]
        self.assertEqual(mc["bosses"], [{"name": "Lucifron", "npc": 12118, "items": [16800, 18879]}])
        self.assertEqual(mc["other"], [{"name": "Trash", "items": [17010]}])
        self.assertEqual(raids[1]["lv"], [10, 18])


class Build(unittest.TestCase):
    def test_loot_prefers_forever_data_and_player_confirmations(self):
        raids = [{"key": "MoltenCore", "name": "Molten Core", "kind": "raid", "size": 40, "area": 2717, "map": 409,
                  "bosses": [{"name": "Lucifron", "npc": 12118, "items": [16800, 18879]}], "other": []}]
        inst = {409: {"maxPlayers": 40, "levelMin": 60, "levelMax": 60, "reset_delay": 7}}
        ctpl = {12118: {"MaxLevel": 63, "MaxLevelHealth": 351780, "Armor": 3795, "ResistanceFire": 93, "ResistanceShadow": 0}}
        chance = {12118: {18879: 3.36}}
        enc = {"lucifron": {"kills": 4, "wipes": 1, "median_kill_seconds": 95}}
        seen = {"lucifron": {18879: 3, 290001: 2}}  # 290001: a new Forever drop no other source lists
        out = build_raids.build(raids, inst, ctpl, chance, {2717: ["Searing Gorge", 34.8, 85.3]}, {}, enc, seen,
                                gear={18879}, other={7068}, qdrops={12118: [7068]})
        r = out[0]
        self.assertEqual((r["slug"], r["lv"], r["reset"], r["entrance"]), ("molten-core", [60, 60], 7, ["Searing Gorge", 34.8, 85.3]))
        b = r["bosses"][0]
        self.assertEqual(b["loot"], [[18879, 3.4, 3], [7068, None], [290001, None, 2]])
        self.assertEqual(b["classic_only"], 1)  # Arcanist Boots isn't in Forever's item data
        self.assertEqual(b["res"], {"fire": 93})
        self.assertEqual(b["seen"]["kills"], 4)


class Encounters(unittest.TestCase):
    def run_enc(self, rows):
        db = sqlite3.connect(":memory:")
        db.executescript(ingest_logs.SCHEMA)
        for sid, char, start in ((1, "a", 1000), (2, "b", 1010), (3, "c", 5000)):
            db.execute("INSERT INTO sessions (id, char_id, start) VALUES (?,?,?)", (sid, char, start))
        for sid, t, e in rows:
            db.execute("INSERT INTO events (session_id, t, k, json) VALUES (?,?,?,?)", (sid, t, "enc", json.dumps(e)))
        with tempfile.TemporaryDirectory() as d:
            ingest_logs.write_encounters(db, Path(d))
            return (Path(d) / "encounters.csv").read_text().splitlines()

    def test_one_pull_logged_by_two_players_counts_once(self):
        kill = {"name": "Lucifron", "ok": True, "dur": 90}
        lines = self.run_enc([(1, 100, kill), (2, 92, kill),                       # same pull, two players
                              (3, 50, {"name": "Lucifron", "ok": True, "dur": 110}),  # a later kill
                              (3, 10, {"name": "Lucifron", "ok": False, "dur": 40})])
        self.assertEqual(lines[1], '"Lucifron",2,1,100,3,3')

    def test_needs_two_players_and_drops_bad_rows(self):
        lines = self.run_enc([(1, 10, {"name": "Solo Boss", "ok": True, "dur": 60}),
                              (1, 20, {"name": "", "ok": True}), (2, 20, {"name": "X", "ok": True, "dur": -5}),
                              (2, 30, {"name": "Y", "ok": True, "dur": "abc"})])
        self.assertEqual(lines, ["encounter,kills,wipes,median_kill_seconds,groups,players"])


if __name__ == "__main__":
    unittest.main()

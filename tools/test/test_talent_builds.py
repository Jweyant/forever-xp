"""Talent builds: the recommended-builds extractor and the player-popularity aggregation."""
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import build_talent_builds  # noqa: E402
import ingest_logs  # noqa: E402


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


class Popularity(unittest.TestCase):
    def run_builds(self, rows, encs=()):
        db = sqlite3.connect(":memory:")
        db.executescript(ingest_logs.SCHEMA)
        chars = sorted({r[0] for r in rows} | {c for c, _ in encs})
        for i, char in enumerate(chars, 1):
            db.execute("INSERT INTO sessions (id, char_id, class, start) VALUES (?,?,?,?)", (i, char, "HUNTER", 1000))
        sid = {c: i for i, c in enumerate(chars, 1)}
        for char, t, e in rows:
            db.execute("INSERT INTO events (session_id, t, k, json) VALUES (?,?,?,?)", (sid[char], t, "talents", json.dumps(e)))
        for char, t in encs:
            db.execute("INSERT INTO events (session_id, t, k, json) VALUES (?,?,?,?)", (sid[char], t, "enc", "{}"))
        with tempfile.TemporaryDirectory() as d:
            ingest_logs.write_talent_builds(db, Path(d))
            return json.loads((Path(d) / "talent_builds.json").read_text())

    def test_last_build_wins_and_groups_split(self):
        out = self.run_builds(
            [("a", 10, {"b": "5-1"}), ("a", 99, {"b": "255-1", "bg": True}),   # respecced: only 255-1 counts
             ("b", 10, {"b": "255-1"}),
             ("c", 10, {"b": "255-1"}), ("d", 10, {"b": "111"})],              # d's build is alone: not shown
            encs=[("b", 20), ("c", 20)])
        self.assertEqual(out, {"hunter": {"players": 4, "all": [["255-1", 3]], "pve": [["255-1", 2]]}})
        # "pvp" absent: only one battleground character; "111" absent: below two characters.

    def test_bad_rows_stay_out(self):
        out = self.run_builds([("a", 1, {"b": "<img>"}), ("b", 1, {"b": "9" * 40}),
                               ("c", 1, {"b": "55-" + "5" * 14}), ("d", 1, {"b": "55-" + "5" * 14})])
        # the last two share a valid 72-point... no: 2+70=72 > 60, so out too.
        self.assertEqual(out, {})


if __name__ == "__main__":
    unittest.main()

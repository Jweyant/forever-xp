"""Merge ForeverScout logs from many players and compare them with Questie's data.

Usage:
  python3 ingest_logs.py --questie data/forever_questdb.sqlite \
      --maps data/questiedb/uiMapIdToAreaId.json --out out/ <log files...>

Each log file is either a SavedVariables file (WTF/.../SavedVariables/ForeverScout.lua)
or a text file containing one or more "FSCOUT1:{...}" strings from /fscout export.

Outputs in --out:
  logs.sqlite              sessions, events and route points from every player
  findings.md              what differs from Questie, with how many players saw it
  questie_candidates.lua   draft Correction entries for QuestieDB (review before submitting)
  quest_timing.csv         per-quest time-to-complete and XP per minute, for routing
"""
import argparse
import json
import math
import re
import sqlite3
import sys
import statistics
from collections import defaultdict
from pathlib import Path

import luadata

GIVER_TOLERANCE = 3.0   # map-percent distance before we call an NPC "moved"
FULL_XP_LEVEL_GAP = 5   # Classic rule: full quest XP until player level > quest level + 5


# --------------------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------------------
def as_list(v):
    if v is None:
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, dict):
        return [v[k] for k in sorted(v)]
    return [v]


def load_file(path):
    """Yield (charId, char_meta, session) from one log file.

    Logs come from the public, so they are read as data only (tools/luadata.py), never run as Lua.
    Files that aren't plain data are skipped with a warning.
    """
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    try:
        if "FSCOUT1:" in text:
            payloads = [luadata.loads_value(m.group(1))
                        for m in re.finditer(r"FSCOUT1:(\{.*?\})(?=\s*(?:FSCOUT1:|$))", text, re.S)]
            for payload in payloads:
                if not isinstance(payload, dict):
                    continue
                meta = {k: payload.get(k) for k in ("race", "class", "faction")}
                for s in as_list(payload.get("sessions")):
                    yield payload.get("charId"), meta, s
            return
        env = luadata.loads_assignments(text)
    except luadata.LuaDataError as e:
        print(f"skipping {path}: not a plain ForeverScout data file ({e})", file=sys.stderr)
        return
    db = env.get("ForeverScoutDB") or {}
    if not isinstance(db, dict):
        return
    for char_id, char in (db.get("chars") or {}).items():
        if not isinstance(char, dict):
            continue
        meta = {k: char.get(k) for k in ("race", "class", "faction")}
        for s in as_list(char.get("sessions")):
            yield char_id, meta, s


# --------------------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY, char_id TEXT, race TEXT, class TEXT,
  faction TEXT, start INTEGER, build TEXT, addon TEXT, start_level INTEGER, duration INTEGER,
  source TEXT, UNIQUE(char_id, start));
CREATE TABLE IF NOT EXISTS events (session_id INTEGER, t INTEGER, k TEXT, lvl INTEGER, map INTEGER,
  x REAL, y REAL, q INTEGER, by TEXT, xp INTEGER, d INTEGER, src TEXT, mob INTEGER, json TEXT);
CREATE TABLE IF NOT EXISTS crumbs (session_id INTEGER, t INTEGER, map INTEGER, x REAL, y REAL, flags TEXT);
CREATE INDEX IF NOT EXISTS e_k ON events(k); CREATE INDEX IF NOT EXISTS e_q ON events(q);
"""


def ingest(db, files):
    added = skipped = 0
    for path in files:
        for char_id, meta, s in load_file(path):
            if not isinstance(s, dict):
                continue
            cur = db.execute(
                "INSERT OR IGNORE INTO sessions (char_id, race, class, faction, start, build, addon,"
                " start_level, duration, source) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (char_id, meta.get("race"), meta.get("class"), meta.get("faction"), s.get("start"),
                 s.get("build"), s.get("addon"), s.get("startLevel"), s.get("duration"), str(path)))
            if cur.rowcount == 0:
                skipped += 1
                continue
            sid = cur.lastrowid
            added += 1
            db.executemany(
                "INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [(sid, e.get("t"), e.get("k"), e.get("lvl"), e.get("map"), e.get("x"), e.get("y"),
                  e.get("q"), e.get("by"), e.get("xp"), e.get("d"), e.get("src"), e.get("mob"),
                  json.dumps(e)) for e in as_list(s.get("events")) if isinstance(e, dict)])
            rows = []
            for c in as_list(s.get("crumbs")):
                parts = str(c).split(",")
                if len(parts) >= 4:
                    t, m, x, y = parts[:4]
                    rows.append((sid, int(float(t)), int(float(m)), float(x), float(y),
                                 parts[4] if len(parts) > 4 else ""))
            db.executemany("INSERT INTO crumbs VALUES (?,?,?,?,?,?)", rows)
    db.commit()
    return added, skipped


# --------------------------------------------------------------------------------------
# Comparison with Questie
# --------------------------------------------------------------------------------------
class Questie:
    def __init__(self, sqlite_path, maps_path):
        self.db = sqlite3.connect(sqlite_path)
        self.ui_to_area = {int(k): v for k, v in json.loads(Path(maps_path).read_text()).items()}
        self.quests = {r[0]: json.loads(r[1]) for r in self.db.execute("SELECT id, json FROM quests")}
        self.npc_names = dict(self.db.execute("SELECT id, name FROM npcs"))
        self._spawns = {}

    def spawns(self, npc_id):
        if npc_id not in self._spawns:
            row = self.db.execute("SELECT json FROM npcs WHERE id=?", (npc_id,)).fetchone()
            sp = json.loads(row[0]).get("spawns") if row else None
            if isinstance(sp, list):
                sp = {i + 1: v for i, v in enumerate(sp)}
            self._spawns[npc_id] = {int(k): v for k, v in (sp or {}).items()}
        return self._spawns[npc_id]

    def ref_list(self, quest_id, field):
        """NPC/object ids that start or finish a quest in Questie, as 'n123'/'o456'."""
        q = self.quests.get(quest_id) or {}
        ref = q.get(field) or []
        if isinstance(ref, dict):
            ref = [ref.get(str(i)) for i in (1, 2, 3)]
        out = set()
        for prefix, ids in zip(("n", "o", "i"), ref + [None] * (3 - len(ref))):
            for i in ids or []:
                out.add(f"{prefix}{i}")
        return out

    def nearest_spawn(self, npc_id, ui_map, x, y):
        area = self.ui_to_area.get(ui_map)
        coords = self.spawns(npc_id).get(area) if area else None
        if not coords or x is None:
            return None
        return min(math.dist((x, y), tuple(c[:2])) for c in coords)


def analyze(db, questie, out_dir):
    findings = defaultdict(lambda: {"chars": set(), "examples": []})

    def note(key, char, example):
        f = findings[key]
        f["chars"].add(char)
        if len(f["examples"]) < 3:
            f["examples"].append(example)

    rows = db.execute("""SELECT s.char_id, e.k, e.q, e.by, e.xp, e.lvl, e.map, e.x, e.y, e.json
                         FROM events e JOIN sessions s ON s.id = e.session_id""").fetchall()
    new_quests, new_npcs = {}, {}
    for char, k, q, by, xp, lvl, ui_map, x, y, raw in rows:
        e = json.loads(raw)
        if k in ("accept", "newquest") and q and q not in questie.quests:
            nq = new_quests.setdefault(q, {"chars": set(), "title": None, "objective": None,
                                           "by": defaultdict(int), "qlvl": None, "pos": []})
            nq["chars"].add(char)
            nq["title"] = nq["title"] or e.get("title")
            nq["objective"] = nq["objective"] or e.get("objective")
            nq["qlvl"] = nq["qlvl"] or e.get("qlvl")
            if by and k == "accept":
                nq["by"][by] += 1
            if x is not None:
                nq["pos"].append((ui_map, x, y))
            note(("quest-missing", q), char, f"level {lvl}, map {ui_map} ({x}, {y})")
        if k == "newnpc":
            n = e.get("npc")
            nn = new_npcs.setdefault(n, {"chars": set(), "name": e.get("name"), "lvls": set(), "pos": []})
            nn["chars"].add(char)
            if e.get("mlvl"):
                nn["lvls"].add(e["mlvl"])
            if x is not None:
                nn["pos"].append((ui_map, x, y))
        if k in ("accept", "turnin") and q in questie.quests:
            field = "startedBy" if k == "accept" else "finishedBy"
            expected = questie.ref_list(q, field)
            if by and expected and by not in expected:
                note((f"{field}-differs", q, by), char,
                     f"saw {by}, Questie has {sorted(expected)}")
            if by and by.startswith("n"):
                npc = int(by[1:])
                d = questie.nearest_spawn(npc, ui_map, x, y)
                if d is not None and d > GIVER_TOLERANCE:
                    note(("npc-moved", npc), char, f"seen at map {ui_map} ({x}, {y}), {d:.1f} from nearest Questie spawn")
        if k == "turnin" and q in questie.quests and xp:
            qlvl = questie.quests[q].get("questLevel") or 0
            row = questie.db.execute("SELECT xp FROM quests WHERE id=?", (q,)).fetchone()
            expected_xp = row[0] if row else None
            if expected_xp and lvl and lvl <= qlvl + FULL_XP_LEVEL_GAP and xp != expected_xp:
                note(("xp-differs", q), char, f"got {xp} XP at level {lvl}, Questie has {expected_xp}")

    write_findings(out_dir, findings, new_quests, new_npcs, questie)
    write_candidates(out_dir, new_quests, new_npcs, findings, questie)
    write_timing(db, out_dir)


def write_findings(out_dir, findings, new_quests, new_npcs, questie):
    lines = ["# ForeverScout findings vs Questie", "",
             "Players = distinct characters that saw it. Treat 1-player findings as unconfirmed.", ""]
    lines += ["## Quests not in Questie", ""]
    for q, d in sorted(new_quests.items()):
        givers = ", ".join(f"{b} ({c}x)" for b, c in d["by"].items()) or "unknown"
        lines.append(f"- **{q}** {d['title'] or '?'} — level {d['qlvl'] or '?'}, giver {givers}, players {len(d['chars'])}")
    lines += ["", "## NPCs not in Questie", ""]
    for n, d in sorted(new_npcs.items()):
        lines.append(f"- **{n}** {d['name'] or '?'} — level {sorted(d['lvls']) or '?'}, "
                     f"{len(d['pos'])} sightings, players {len(d['chars'])}")
    for title, kind in (("Quest giver differs", "startedBy-differs"), ("Turn-in NPC differs", "finishedBy-differs"),
                        ("NPC not where Questie places it", "npc-moved"), ("Quest XP differs", "xp-differs")):
        items = [(k, v) for k, v in findings.items() if k[0] == kind]
        lines += ["", f"## {title}", ""]
        if not items:
            lines.append("_none_")
        for key, v in sorted(items, key=lambda kv: -len(kv[1]["chars"])):
            ident = key[1]
            label = questie.quests.get(ident, {}).get("name") if kind != "npc-moved" else questie.npc_names.get(ident)
            lines.append(f"- **{ident}** {label or ''} — players {len(v['chars'])}: {'; '.join(v['examples'])}")
    (out_dir / "findings.md").write_text("\n".join(lines) + "\n")


def average_pos(positions, ui_to_area):
    by_area = defaultdict(list)
    for ui_map, x, y in positions:
        area = ui_to_area.get(ui_map)
        if area:
            by_area[area].append((x, y))
    return {a: [round(statistics.mean(p[0] for p in pts), 2), round(statistics.mean(p[1] for p in pts), 2)]
            for a, pts in by_area.items()}


def write_candidates(out_dir, new_quests, new_npcs, findings, questie):
    lines = [
        "-- DRAFT corrections generated from ForeverScout logs. Review every entry before",
        "-- submitting to QuestieDB (src/corrections/Forever/forever*Fixes.lua).",
        "-- 'players' = distinct characters that observed it; prefer entries seen by 2+.",
        "", "-- ForeverQuestFixes:Load() additions", "return {", "  quests = {"]
    for q, d in sorted(new_quests.items()):
        givers = sorted(d["by"], key=lambda b: -d["by"][b])
        npc_ids = [int(b[1:]) for b in givers if b.startswith("n")][:1]
        lines.append(f"    [{q}] = {{ -- players: {len(d['chars'])}")
        lines.append(f"      [questKeys.name] = {json.dumps(d['title'] or '')},")
        if npc_ids:
            lines.append(f"      [questKeys.startedBy] = {{{{{npc_ids[0]}}}}},")
        if d["qlvl"]:
            lines.append(f"      [questKeys.questLevel] = {d['qlvl']},")
        if d["objective"]:
            lines.append(f"      [questKeys.objectivesText] = {{{json.dumps(d['objective'])}}},")
        lines.append("    },")
    lines += ["  },", "  npcs = {"]
    for n, d in sorted(new_npcs.items()):
        spawns = average_pos(d["pos"], questie.ui_to_area)
        lvls = sorted(d["lvls"])
        spawn_txt = ", ".join(f"[{a}] = {{{{{c[0]}, {c[1]}}}}}" for a, c in spawns.items())
        lines.append(f"    [{n}] = {{ -- players: {len(d['chars'])}")
        lines.append(f"      [npcKeys.name] = {json.dumps(d['name'] or '')},")
        if lvls:
            lines.append(f"      [npcKeys.minLevel] = {lvls[0]}, [npcKeys.maxLevel] = {lvls[-1]},")
        if spawn_txt:
            lines.append(f"      [npcKeys.spawns] = {{{spawn_txt}}},")
            lines.append(f"      [npcKeys.zoneID] = {next(iter(spawns))},")
        lines.append("    },")
    lines += ["  },", "}"]
    (out_dir / "questie_candidates.lua").write_text("\n".join(lines) + "\n")


def write_timing(db, out_dir):
    """Accept -> turn-in time and XP per minute for each quest, per character."""
    rows = db.execute("""SELECT s.char_id, e.session_id, e.k, e.q, e.t, e.xp FROM events e
                         JOIN sessions s ON s.id = e.session_id
                         WHERE e.k IN ('accept','turnin') ORDER BY e.session_id, e.t""").fetchall()
    accepted = {}
    per_quest = defaultdict(list)
    for char, sid, k, q, t, xp in rows:
        if k == "accept":
            accepted[(sid, q)] = t
        elif (sid, q) in accepted:
            per_quest[q].append((t - accepted.pop((sid, q)), xp or 0, char))
    out = ["quest_id,players,median_seconds,median_xp,xp_per_minute"]
    for q, samples in sorted(per_quest.items()):
        secs = statistics.median(s[0] for s in samples)
        xp = statistics.median(s[1] for s in samples)
        xpm = round(xp / (secs / 60), 1) if secs > 0 else ""
        out.append(f"{q},{len({s[2] for s in samples})},{secs},{xp},{xpm}")
    (out_dir / "quest_timing.csv").write_text("\n".join(out) + "\n")


def write_loot(db, out_dir):
    """Which NPC or object dropped which item, from ForeverScout 'loot' events."""
    zones = {}
    zfile = Path(__file__).parent / "zone_sizes.json"
    if zfile.exists():
        zones = {int(k): v.get("name") for k, v in json.loads(zfile.read_text()).items()}
    names = {}
    for (raw,) in db.execute("SELECT json FROM events WHERE k = 'newnpc'"):
        e = json.loads(raw)
        if e.get("npc") and e.get("name"):
            names[e["npc"]] = e["name"]
    seen = defaultdict(set)
    for char, raw in db.execute("""SELECT s.char_id, e.json FROM events e JOIN sessions s ON s.id = e.session_id
                                   WHERE e.k = 'loot'"""):
        e = json.loads(raw)
        if not e.get("item"):
            continue
        src = e.get("src")
        label = names.get(src) or (f"Object #{src}" if e.get("kind") == "GameObject" else f"NPC #{src}" if src else "")
        seen[(int(e["item"]), label, zones.get(e.get("map"), ""))].add(char)
    out = ["item,source,zone,players"]
    for (item, label, zone), chars in sorted(seen.items()):
        out.append(",".join([str(item), '"' + label.replace('"', "'") + '"', '"' + (zone or "") + '"', str(len(chars))]))
    (out_dir / "loot.csv").write_text("\n".join(out) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--questie", required=True)
    ap.add_argument("--maps", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("files", nargs="+")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(out / "logs.sqlite")
    db.executescript(SCHEMA)
    added, skipped = ingest(db, a.files)
    print(f"sessions added: {added}, already present: {skipped}")
    analyze(db, Questie(a.questie, a.maps), out)
    write_loot(db, out)
    for name in ("findings.md", "questie_candidates.lua", "quest_timing.csv", "loot.csv"):
        print("wrote", out / name)


if __name__ == "__main__":
    main()

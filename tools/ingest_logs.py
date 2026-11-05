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
import hashlib
import json
import math
import re
import sqlite3
import sys
import time
import statistics
from collections import Counter, defaultdict
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


def load_file(path, board=None):
    """Yield (charId, char_meta, session) from one log file.

    With a `board` dict, also note the player's in-game leaderboard choice there (board_choice).

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
    if board is not None:
        board_choice(board, path, db.get("settings"))
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


def ingest(db, files, board=None):
    added = skipped = 0
    for path in files:
        for char_id, meta, s in load_file(path, board):
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


# Gaps longer than this with no event or breadcrumb count as away from keyboard, not questing.
IDLE_CAP = 120
# Samples longer than this many hours of attributed play are dropped as broken logs.
MAX_SAMPLE_SECONDS = 4 * 3600


def write_timing(db, out_dir):
    """Time each quest really cost, per character, from accept to turn-in.

    Wall time from accept to turn-in overstates a quest: players carry several quests at once,
    stop for a meal, or log out and finish it the next evening. So time is attributed:
      - each character's sessions are joined on one clock (session start + event time), so a
        quest accepted one evening and handed in the next still counts, but the time logged out
        doesn't;
      - the time between two activity marks (any event or position breadcrumb) is capped at
        IDLE_CAP seconds, so standing still for an hour adds two minutes, not sixty;
      - a stretch that ends in objective progress or a turn-in for a quest goes to that quest;
        any other stretch (running, flying, killing) is split evenly between the quests in the log.
    Kill XP is attributed the same way, so XP per minute counts quest and kill XP, like the
    route model. Only accept -> turn-in pairs count; abandoned quests and quests already in the
    log when recording began are left out. `wall_seconds` keeps the raw accept -> turn-in median."""
    sessions = db.execute("SELECT id, char_id, start FROM sessions WHERE start IS NOT NULL").fetchall()
    by_char = defaultdict(list)
    for sid, char, start in sessions:
        if isinstance(start, (int, float)):
            by_char[char].append((start, sid))
    per_quest = defaultdict(list)
    for char, sess in by_char.items():
        marks = []  # (absolute time, session id, kind, quest, xp, src)
        for start, sid in sess:
            for t, k, q, xp, src in db.execute("SELECT t, k, q, xp, src FROM events WHERE session_id = ?", (sid,)):
                if isinstance(t, (int, float)) and t >= 0:
                    marks.append((start + t, sid, k, q if isinstance(q, int) else None,
                                  xp if isinstance(xp, int) and xp > 0 else 0, src))
            for (t,) in db.execute("SELECT t FROM crumbs WHERE session_id = ?", (sid,)):
                if isinstance(t, (int, float)) and t >= 0:
                    marks.append((start + t, sid, "crumb", None, 0, None))
        marks.sort(key=lambda m: (m[0], m[2] != "accept"))
        active = {}  # quest -> {"t0", "secs", "kxp"}
        prev = None
        for when, sid, k, q, xp, src in marks:
            if prev is not None and prev[1] == sid and active:
                dt = min(max(when - prev[0], 0), IDLE_CAP)
                own = q if q in active and k in ("obj", "turnin") else None
                share = [own] if own else list(active)
                for aq in share:
                    active[aq]["secs"] += dt / len(share)
            if k == "xp" and src == "k" and active and xp:
                for aq in active:
                    active[aq]["kxp"] += xp / len(active)
            if k == "accept" and q:
                active[q] = {"t0": when, "secs": 0.0, "kxp": 0.0}
            elif k == "abandon" and q in active:
                del active[q]
            elif k == "turnin" and q in active:
                a = active.pop(q)
                if 0 < a["secs"] <= MAX_SAMPLE_SECONDS:
                    per_quest[q].append((a["secs"], when - a["t0"], xp, a["kxp"], char))
            prev = (when, sid)
    out = ["quest_id,players,median_seconds,median_xp,xp_per_minute,wall_seconds,samples"]
    for q, samples in sorted(per_quest.items()):
        secs = statistics.median(s[0] for s in samples)
        wall = statistics.median(s[1] for s in samples)
        xp = statistics.median(s[2] for s in samples)
        kxp = statistics.median(s[3] for s in samples)
        xpm = round((xp + kxp) / (secs / 60), 1) if secs > 0 else ""
        out.append(f"{q},{len({s[4] for s in samples})},{round(secs)},{xp},{xpm},{round(wall)},{len(samples)}")
    (out_dir / "quest_timing.csv").write_text("\n".join(out) + "\n")


INSTALL_RE = re.compile(r"([0-9a-f]{32})-[0-9a-f]{16}\.lua$")


def player_key(char_id, source):
    """One player, not one character: logs that came through the uploader are named
    logs/<install>-<slot>.lua (tools/pull_logs.py), so alts on the same install count once.
    Logs attached by hand have no install id and fall back to the character id."""
    m = INSTALL_RE.search(str(source or ""))
    return "i:" + m.group(1) if m else "c:" + str(char_id)


def write_loot(db, out_dir, linked=None):
    """Which NPC or object dropped which item, from ForeverScout 'loot' events.

    players = distinct players (installs) who looted it from that source in that zone;
    looted = how many times it was seen dropping there, across everyone;
    first_by = the board name of the first player to loot it, when that player has linked their
    account and a second player has since seen the same drop (`linked`: see load_scout_names).
    Otherwise empty: unlinked, hidden or hand-sent logs are never credited by name."""
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
    looted = defaultdict(int)
    first = {}  # drop -> (time, player) of its earliest loot
    for char, source, start, t, raw in db.execute("""SELECT s.char_id, s.source, s.start, e.t, e.json FROM events e
                                           JOIN sessions s ON s.id = e.session_id WHERE e.k = 'loot'"""):
        e = json.loads(raw)
        try:
            item = int(e.get("item") or 0)
        except (TypeError, ValueError):
            continue
        if item <= 0:
            continue
        src = e.get("src")
        # kind is "object"/"npc" from ForeverScout 0.4 on, "GameObject"/"Creature" before.
        label = names.get(src) or (f"Object #{src}" if e.get("kind") in ("GameObject", "object") else f"NPC #{src}" if src else "")
        key = (item, str(label), zones.get(e.get("map")) or "")
        who = player_key(char, source)
        seen[key].add(who)
        looted[key] += 1
        try:
            when = int(start or 0) + int(t or 0)
        except (TypeError, ValueError):
            when = 0
        if key not in first or when < first[key][0]:
            first[key] = (when, who)
    linked = linked or {}
    out = ["item,source,zone,players,looted,first_by"]
    for key, players in sorted(seen.items()):
        item, label, zone = key
        who = first[key][1]
        by = linked.get(scout_hash(who), "") if len(players) >= 2 and who.startswith("i:") else ""
        out.append(",".join([str(item), '"' + label.replace('"', "'") + '"', '"' + zone + '"',
                             str(len(players)), str(looted[key]), '"' + by + '"']))
    (out_dir / "loot.csv").write_text("\n".join(out) + "\n")


# The uploader shows players the same name (uploader/app.go scoutName); keep the two in step.
SCOUT_SALT = "forever-xp scout|"
WEEK = 7 * 86400
BOARD_SIZE = 50
WEEK_BOARD_SIZE = 10


def scout_hash(key):
    """One-way hash of a player key (the install id, or the character id for hand-sent logs).
    The accounts API stores the same hash for a linked install (site/api/app.js SCOUT_SALT)."""
    ident = key.split(":", 1)[1] if ":" in key else key
    return hashlib.sha256((SCOUT_SALT + ident).encode()).hexdigest()


def scout_handle(key):
    """Anonymous name for a player key: "Scout" plus the first 6 hex digits of scout_hash(). The
    uploader shows players this name; the board shows it only for names it can't use."""
    return "Scout " + scout_hash(key)[:6]


BOARD_NAME = re.compile(r"^[A-Za-z0-9 _'-]{2,20}$")


def load_scout_names(path):
    """The linked players from the accounts API (/api/scouts/names): {install hash: name}. Every key
    and name is re-checked against the allow-list here, so a bad response can't put odd text on the
    board. None when the file is missing or unreadable (the board is then left as it was)."""
    try:
        doc = json.loads(Path(path).read_text())
    except (OSError, ValueError, TypeError):
        return None
    names = doc.get("names") if isinstance(doc, dict) else None
    if not isinstance(names, dict):
        return None
    return {h: n for h, n in names.items()
            if isinstance(h, str) and re.fullmatch(r"[0-9a-f]{64}", h) and isinstance(n, str) and BOARD_NAME.match(n)}


GAME_NAME = re.compile(r"[^\W\d_]{2,12}")  # a WoW character name: 2-12 letters, accents allowed


def board_choice(board, path, settings):
    """Record one log file's in-game leaderboard choice in `board`: {player key: (boardAt, name or None)}.

    The addon sets settings.boardName (one character's name, or false) and settings.boardAt when the
    player answers "Show my name on the leaderboard?" (addon/ForeverScout/Core.lua ns.SetBoard). An
    install can have several log files; the newest choice wins, so "hide my name" sticks. Only
    uploader logs count (hand-sent logs have no install to tie a name to)."""
    m = INSTALL_RE.search(str(path or ""))
    if not m or not isinstance(settings, dict):
        return
    at, name = settings.get("boardAt"), settings.get("boardName")
    if isinstance(at, bool) or not isinstance(at, (int, float)):
        return
    key = "i:" + m.group(1)
    if key not in board or at > board[key][0]:
        board[key] = (at, name if isinstance(name, str) and GAME_NAME.fullmatch(name) else None)


def with_board_names(names, board):
    """The names the board and the "first logged by" credit may use: {install hash: name}.

    Account links from the site (`names`) come first. Then players who chose to show their
    character name in game (`board`, from board_choice), oldest choice first; a name already taken
    (any case) by a linked player or an earlier install is skipped, so nobody can take another
    player's name. None stays None (the accounts API couldn't be read: leave the board as it is)."""
    if names is None:
        return None
    out = dict(names)
    taken = {n.casefold() for n in out.values()}
    for key, (_, name) in sorted(board.items(), key=lambda kv: (kv[1][0], kv[0])):
        h = scout_hash(key)
        if name and h not in out and name.casefold() not in taken:
            out[h] = name
            taken.add(name.casefold())
    return out


def write_scouts(db, out_dir, now=None, names=None):
    """Contributor leaderboard, scouts.json.

    Only named players appear on the board: those who linked their install to a forever-xp.com
    account (their chosen or Discord name) and those who chose in game to show their character name
    (`names`: install hash -> name, from with_board_names).
    Everyone's logs still count in the totals and in every other table. With `names=None` (the
    accounts API couldn't be read) nothing is written, so the last published board stays.

    Per player (install): quests timed (accept -> turn-in), drops logged (distinct item, source
    and zone), discoveries (first to loot a drop that another player then confirmed), zones and
    sessions. Points: 1 per quest timed, 1 per drop, 3 per discovery. `week` counts only events
    in the last seven days. Nothing per character, no install ids, no map ids: handles and counts.
    """
    if names is None:
        print("scouts.json: linked names unavailable; leaving the published board as it is")
        return
    now = int(now if now is not None else time.time())
    since = now - WEEK
    starts, owner = {}, {}
    sessions = defaultdict(int)
    for sid, char, source, start in db.execute("SELECT id, char_id, source, start FROM sessions"):
        key = player_key(char, source)
        owner[sid], starts[sid] = key, int(start or 0)
        sessions[key] += 1

    quests, week_quests = defaultdict(set), defaultdict(set)
    zones = defaultdict(set)
    accepted = {}
    drops, week_drops = defaultdict(set), defaultdict(set)
    first = {}  # drop -> (time, player) of its earliest loot
    looters = defaultdict(set)
    rows = db.execute("SELECT session_id, k, t, q, map, json FROM events WHERE k IN ('accept','turnin','loot')"
                      " ORDER BY session_id, t")
    for sid, k, t, q, m, raw in rows:
        key = owner.get(sid)
        if key is None:
            continue
        try:
            when = starts[sid] + int(t or 0)
        except (TypeError, ValueError):
            continue
        if isinstance(m, int) and m > 0:
            zones[key].add(m)
        if k in ("accept", "turnin"):
            try:
                q = int(q or 0)
            except (TypeError, ValueError):
                continue
            if q <= 0:
                continue
            if k == "accept":
                accepted[(sid, q)] = when
            elif accepted.pop((sid, q), None) is not None:
                quests[key].add(q)
                if when >= since:
                    week_quests[key].add(q)
            continue
        try:
            e = json.loads(raw or "{}")
            drop = (int(e.get("item") or 0), str(e.get("src") or ""), int(m or 0))
        except (TypeError, ValueError, AttributeError):
            continue
        if drop[0] <= 0:
            continue
        drops[key].add(drop)
        looters[drop].add(key)
        if when >= since:
            week_drops[key].add(drop)
        if drop not in first or when < first[drop][0]:
            first[drop] = (when, key)

    found, week_found = defaultdict(int), defaultdict(int)
    for drop, (when, key) in first.items():
        if len(looters[drop]) >= 2:  # confirmed by someone else
            found[key] += 1
            if when >= since:
                week_found[key] += 1

    def score(q, d, f):
        return q + d + 3 * f

    players = set(sessions)
    linked = {k: names[scout_hash(k)] for k in players if k.startswith("i:") and scout_hash(k) in names}
    board = [{"handle": linked[k], "quests": len(quests[k]), "drops": len(drops[k]), "discoveries": found[k],
              "zones": len(zones[k]), "sessions": sessions[k],
              "score": score(len(quests[k]), len(drops[k]), found[k])} for k in players if k in linked]
    board = [r for r in board if r["score"] > 0 or r["sessions"] > 0]
    board.sort(key=lambda r: (-r["score"], -r["quests"], r["handle"]))
    active = {k for k in players if week_quests[k] or week_drops[k]}
    week_board = [{"handle": linked[k], "quests": len(week_quests[k]), "drops": len(week_drops[k]),
                   "score": score(len(week_quests[k]), len(week_drops[k]), week_found[k])} for k in active if k in linked]
    week_board.sort(key=lambda r: (-r["score"], -r["quests"], r["handle"]))
    out = {
        "updated": now,
        "totals": {"scouts": len(players), "linked": len(linked), "sessions": sum(sessions.values()),
                   "quests": len(set().union(*quests.values())), "drops": len(first),
                   "discoveries": sum(found.values())},
        "week": {"scouts": len(active), "quests": len(set().union(*week_quests.values())),
                 "drops": len(set().union(*week_drops.values()))},
        "board": board[:BOARD_SIZE],
        "week_board": week_board[:WEEK_BOARD_SIZE],
    }
    (out_dir / "scouts.json").write_text(json.dumps(out, separators=(",", ":"), sort_keys=True))

def write_encounters(db, out_dir, window=180, min_players=2):
    """Boss kills and wipes from ForeverScout "enc" events, as encounters.csv:
    encounter,kills,wipes,median_kill_seconds,groups,players.

    Everyone in a group logs the same pull, so pulls of the same boss and outcome that end within
    `window` seconds of each other count once. A boss is only published once at least `min_players`
    different characters logged it. Only these totals leave the run."""
    pulls = []
    for char, start, t, raw in db.execute("""SELECT s.char_id, s.start, e.t, e.json FROM events e
                                             JOIN sessions s ON s.id = e.session_id WHERE e.k = 'enc'"""):
        try:
            e = json.loads(raw)
            name = str(e.get("name") or "").strip()[:80]
            end = int(start) + int(t)
            dur = int(e["dur"]) if e.get("dur") is not None else None
        except (TypeError, ValueError, KeyError):
            continue
        if not name or (dur is not None and not 0 < dur < 4 * 3600):
            continue
        pulls.append((name, bool(e.get("ok")), end, dur, char))
    pulls.sort(key=lambda p: (p[0], p[1], p[2]))
    stats = defaultdict(lambda: {"kills": [], "wipes": 0, "chars": set()})
    last = {}
    for name, ok, end, dur, char in pulls:
        s = stats[name]
        s["chars"].add(char)
        key = (name, ok)
        if key in last and end - last[key] <= window:
            continue  # the same pull, logged by another member of the group
        last[key] = end
        if ok:
            s["kills"].append(dur)
        else:
            s["wipes"] += 1
    out = ["encounter,kills,wipes,median_kill_seconds,groups,players"]
    for name, s in sorted(stats.items()):
        if len(s["chars"]) < min_players:
            continue
        durs = [d for d in s["kills"] if d]
        med = int(statistics.median(durs)) if durs else ""
        out.append(f'"{name.replace(chr(34), chr(39))}",{len(s["kills"])},{s["wipes"]},{med},{len(s["kills"]) + s["wipes"]},{len(s["chars"])}')
    (out_dir / "encounters.csv").write_text("\n".join(out) + "\n")

def write_objective_areas(db, out_dir, cell=2.0, min_players=2):
    """Where players actually progress each quest objective, as coarse grid cells.

    Output objective_areas.json: {quest: {objective: {"map": uiMapId, "cells": [[x, y, players], ...]}}}.
    Positions are snapped to `cell`-percent squares and a square is only published once at least
    `min_players` different characters progressed there, so no single player's path is exposed.
    """
    hits = defaultdict(set)  # (quest, objective, map, cx, cy) -> characters
    for char, q, raw, m, x, y in db.execute("""SELECT s.char_id, e.q, e.json, e.map, e.x, e.y FROM events e
                                               JOIN sessions s ON s.id = e.session_id WHERE e.k = 'obj'"""):
        try:
            oi = int(json.loads(raw).get("oi") or 0)
            q, m, x, y = int(q or 0), int(m or 0), float(x), float(y)
        except (TypeError, ValueError):
            continue
        if q <= 0 or not 0 < oi <= 10 or m <= 0 or not (0 <= x <= 100 and 0 <= y <= 100):
            continue
        hits[(q, oi, m, int(x // cell), int(y // cell))].add(char)
    areas = {}
    for (q, oi, m, cx, cy), chars in sorted(hits.items()):
        if len(chars) < min_players:
            continue
        slot = areas.setdefault(str(q), {}).setdefault(str(oi), {"map": m, "cells": []})
        if slot["map"] == m:  # keep the objective's main map only
            slot["cells"].append([round((cx + 0.5) * cell, 1), round((cy + 0.5) * cell, 1), len(chars)])
    (out_dir / "objective_areas.json").write_text(json.dumps(areas, separators=(",", ":"), sort_keys=True))


BUILD_RE = re.compile(r"^[0-5]{0,30}(-[0-5]{0,30}){0,2}$")


FAMILY_POINTS = 3   # builds this many points apart or fewer are one family, shown by its most used member


def client_build(v):
    """"1.60.1.70755" -> (1, 60, 1, 70755), or None."""
    m = re.fullmatch(r"(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,7})", str(v or ""))
    return tuple(int(x) for x in m.groups()) if m else None


def load_trees(path):
    """The current talent trees from gamedata/talents.json: {"client": (build tuple), "classes":
    {class slug: {"ranks": [[max ranks per talent] per tree], "sig": hash of names, ranks and order}}}.
    None if the file can't be read."""
    try:
        g = json.loads(Path(path).read_text())
        client = client_build((g.get("builds") or {}).get("forever"))
        classes = {}
        for _, name, trees in g["talents"]:
            ranks = [[int(t[4]) for t in tals] for _, _, _, tals in trees]
            shape = [[(t[3], int(t[4])) for t in tals] for _, _, _, tals in trees]
            classes[str(name).lower()] = {"ranks": ranks,
                                          "sig": hashlib.sha256(json.dumps(shape).encode()).hexdigest()[:16]}
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        return None
    return {"client": client, "classes": classes} if client and classes else None


def fits_trees(b, ranks):
    """True if every digit of the build fits the current trees (lengths and max ranks)."""
    parts = b.split("-")
    if len(parts) > len(ranks):
        return False
    for part, tree in zip(parts, ranks):
        if len(part) > len(tree) or any(int(ch) > r for ch, r in zip(part, tree)):
            return False
    return True


def build_distance(a, b):
    """How many points apart two builds are: the sum of per-talent differences."""
    pa, pb = a.split("-"), b.split("-")
    d = 0
    for i in range(max(len(pa), len(pb))):
        x = pa[i] if i < len(pa) else ""
        y = pb[i] if i < len(pb) else ""
        n = max(len(x), len(y))
        d += sum(abs(int(x[k] if k < len(x) else 0) - int(y[k] if k < len(y) else 0)) for k in range(n))
    return d


def build_families(counter, min_players):
    """Group builds within FAMILY_POINTS of each other. Each family is shown by its most used member,
    which must itself be used by min_players characters (so no single character's build is shown);
    the family's count adds every close build's characters. Returns [[build, characters, close builds]]."""
    heads = []   # [build, characters, close builds]
    for b, n in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0])):
        home = next((h for h in heads if build_distance(h[0], b) <= FAMILY_POINTS), None)
        if home:
            home[1] += n
            home[2] += 1
        elif n >= min_players:
            heads.append([b, n, 0])
    heads.sort(key=lambda h: (-h[1], h[0]))
    return heads


def write_talent_builds(db, out_dir, min_players=2, trees=None, previous=None, now=None):
    """Every talent build players use, per class, as talent_builds.json:
    {class: {"players": N, "groups": {"all"/"pve"/"pvp"/"ranked": {"n": characters,
    "builds": [[string, characters, close builds], ...]}}}, "_trees": {...}}.

    A character counts once, with the last build they logged. "pve" is characters who logged a
    dungeon or raid boss, "pvp" characters who entered a battleground, "ranked" characters whose
    logs carry an honor rank (the addon reads the character's own rank, nothing about others).
    Builds within FAMILY_POINTS points of each other count as one family, shown by its most used
    member; that member must be used by `min_players` characters, so nobody's build is shown alone.

    The addon logs a build as one digit per talent in the game's tree order, so a patch that moves
    talents changes what an old string means. With `trees` (load_trees), only logs that can be read
    on today's trees count: from exactly the client build the trees come from (a newer client waits
    for the next talent refresh), made after the trees last changed, and fitting today's ranks. `previous` (the last published talent_builds.json) tells when
    each class's trees last changed: a change within the same client build (a hotfix) restarts that
    class's count from `now`; a new client build is already covered by the build check."""
    now = int(now if now is not None else time.time())
    prev_trees = (previous or {}).get("_trees") if isinstance(previous, dict) else None
    prev_trees = prev_trees if isinstance(prev_trees, dict) else {}
    since, meta = {}, {}
    if trees:
        client = ".".join(map(str, trees["client"]))
        for cls, info in trees["classes"].items():
            p = prev_trees.get(cls) if isinstance(prev_trees.get(cls), dict) else {}
            if p.get("sig") == info["sig"]:
                start = int(p.get("since") or 0)
            elif p.get("sig") and p.get("client") == client:
                start = now    # same client, different trees: a hotfix moved talents
            else:
                start = 0      # first run or a new client build: the build check is enough
            since[cls] = start
            meta[cls] = {"sig": info["sig"], "client": client, "since": start}
    latest = {}   # char -> (when, class, build)
    flags = defaultdict(lambda: {"pvp": False, "pve": False, "ranked": False})
    for char, cls, start, sbuild, t, k, raw in db.execute(
            """SELECT s.char_id, s.class, s.start, s.build, e.t, e.k, e.json
               FROM events e JOIN sessions s ON s.id = e.session_id WHERE e.k IN ('talents', 'enc')"""):
        if k == "enc":
            flags[char]["pve"] = True
            continue
        try:
            e = json.loads(raw)
            b = e.get("b").rstrip("-") if isinstance(e.get("b"), str) else None
            when = int(start or 0) + int(t or 0)
        except (TypeError, ValueError, AttributeError):
            continue
        if not (isinstance(b, str) and BUILD_RE.fullmatch(b) and b.strip("-") and not b.endswith("-")
                and sum(int(d) for d in b if d.isdigit()) <= 60):
            continue
        cls = str(cls or "").strip().lower()
        if not re.fullmatch(r"[a-z]+", cls):
            continue
        if trees:
            info = trees["classes"].get(cls)
            got = client_build(sbuild)
            if not info or got != trees["client"] or when < since.get(cls, 0) or not fits_trees(b, info["ranks"]):
                continue
        if e.get("bg"):
            flags[char]["pvp"] = True
        rank = e.get("rank")
        if isinstance(rank, (int, float)) and 1 <= rank <= 14:
            flags[char]["ranked"] = True
        if char not in latest or when >= latest[char][0]:
            latest[char] = (when, cls, b)
    counts = defaultdict(lambda: {"players": 0, "all": Counter(), "pve": Counter(), "pvp": Counter(), "ranked": Counter()})
    for char, (_, cls, b) in latest.items():
        c = counts[cls]
        c["players"] += 1
        c["all"][b] += 1
        for group in ("pve", "pvp", "ranked"):
            if flags[char][group]:
                c[group][b] += 1
    out = {}
    for cls, c in sorted(counts.items()):
        groups = {}
        for group in ("all", "pve", "pvp", "ranked"):
            rows = build_families(c[group], min_players)
            if rows:
                groups[group] = {"n": sum(c[group].values()), "builds": rows}
        if groups:
            out[cls] = {"players": c["players"], "groups": groups}
    if meta:
        out["_trees"] = meta
    (out_dir / "talent_builds.json").write_text(json.dumps(out, separators=(",", ":"), sort_keys=True))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--questie", required=True)
    ap.add_argument("--maps", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--names", help="JSON from the accounts API /api/scouts/names: who the leaderboard may name")
    ap.add_argument("--talents", help="gamedata/talents.json (the newest copy): only builds readable on today's trees count")
    ap.add_argument("--previous-builds", help="the last published talent_builds.json, to tell when the trees changed")
    ap.add_argument("files", nargs="+")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(out / "logs.sqlite")
    db.executescript(SCHEMA)
    board = {}
    added, skipped = ingest(db, a.files, board)
    print(f"sessions added: {added}, already present: {skipped}")
    analyze(db, Questie(a.questie, a.maps), out)
    names = with_board_names(load_scout_names(a.names) if a.names else None, board)
    write_loot(db, out, linked=names)
    write_objective_areas(db, out)
    write_scouts(db, out, names=names)
    write_encounters(db, out)
    previous = None
    if a.previous_builds:
        try:
            previous = json.loads(Path(a.previous_builds).read_text())
        except (OSError, ValueError):
            previous = None
    trees = load_trees(a.talents) if a.talents else None
    if a.talents and not trees:
        sys.exit(f"{a.talents}: can't read the talent trees")
    write_talent_builds(db, out, trees=trees, previous=previous)
    for name in ("findings.md", "questie_candidates.lua", "quest_timing.csv", "loot.csv", "objective_areas.json", "scouts.json", "encounters.csv", "talent_builds.json"):
        print("wrote", out / name)


if __name__ == "__main__":
    main()

"""Build a queryable SQLite database from the QuestieDB JSON export.

Usage: python3 build_sqlite.py <export_dir> <out.sqlite>
"""
import json
import sqlite3
import sys
from pathlib import Path

HORDE_BITS = 2 | 16 | 32 | 128      # Orc, Undead, Tauren, Troll
ALLIANCE_BITS = 1 | 4 | 8 | 64      # Human, Dwarf, Night Elf, Gnome
LEGACY_RACE_MASK = 0xFF             # Forever adds Skyborne races in high bits (32/33)
HORDE_SKYBORNE = 1 << 33
ALLIANCE_SKYBORNE = 1 << 32


def faction(mask):
    if not mask:
        return "both"
    h = bool(mask & HORDE_BITS or mask & HORDE_SKYBORNE)
    a = bool(mask & ALLIANCE_BITS or mask & ALLIANCE_SKYBORNE)
    return "both" if h and a else "horde" if h else "alliance" if a else "none"


def as_map(t):
    """Lua tables keyed 1..n serialize as JSON arrays; normalize to {int_key: value}."""
    if isinstance(t, list):
        return {i + 1: v for i, v in enumerate(t)}
    return {int(k): v for k, v in (t or {}).items()}


def first_spawn(entity):
    spawns = as_map((entity or {}).get("spawns"))
    for zone, coords in spawns.items():
        if coords:
            return int(zone), coords[0][0], coords[0][1]
    return None, None, None


def main(src, out):
    src = Path(src)
    load = lambda name: json.loads((src / name).read_text())
    quests, npcs = load("quests.json"), load("npcs.json")
    objects, items = load("objects.json"), load("items.json")
    xp = load("questXP.json")
    zone_ids = load("zoneIDs.json")
    zone_names = {v: k for k, v in zone_ids.items()}

    npc_by_id = {n["id"]: n for n in npcs}
    obj_by_id = {o["id"]: o for o in objects}

    db = sqlite3.connect(out)
    db.executescript("""
    DROP TABLE IF EXISTS quests; DROP TABLE IF EXISTS npcs; DROP TABLE IF EXISTS objects;
    DROP TABLE IF EXISTS items; DROP TABLE IF EXISTS zones;
    CREATE TABLE zones (id INTEGER PRIMARY KEY, name TEXT);
    CREATE TABLE quests (
        id INTEGER PRIMARY KEY, name TEXT, quest_level INTEGER, required_level INTEGER,
        required_max_level INTEGER, faction TEXT, required_races INTEGER, required_classes INTEGER,
        zone_or_sort INTEGER, zone_name TEXT, xp INTEGER,
        start_type TEXT, start_id INTEGER, start_name TEXT, start_zone INTEGER, start_x REAL, start_y REAL,
        end_type TEXT, end_id INTEGER, end_name TEXT, end_zone INTEGER, end_x REAL, end_y REAL,
        pre_quest_single TEXT, pre_quest_group TEXT, next_in_chain INTEGER,
        breadcrumb_for INTEGER, exclusive_to TEXT, repeatable INTEGER, objectives_text TEXT,
        json TEXT);
    CREATE TABLE npcs (id INTEGER PRIMARY KEY, name TEXT, min_level INTEGER, max_level INTEGER,
        rank INTEGER, zone_id INTEGER, friendly_to TEXT, spawn_count INTEGER, json TEXT);
    CREATE TABLE objects (id INTEGER PRIMARY KEY, name TEXT, zone_id INTEGER, spawn_count INTEGER, json TEXT);
    CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT, json TEXT);
    """)

    db.executemany("INSERT INTO zones VALUES (?,?)", [(v, k) for k, v in zone_ids.items()])

    def endpoint(ref):
        """ref is startedBy/finishedBy: [[npcs],[objects],[items]]"""
        ref = ref or []
        if isinstance(ref, dict):  # sparse Lua table, e.g. objects-only {"2": [...]}
            ref = [ref.get(str(i)) for i in (1, 2, 3)]
        if len(ref) > 0 and ref[0]:
            nid = ref[0][0]
            z, x, y = first_spawn(npc_by_id.get(nid))
            return "npc", nid, (npc_by_id.get(nid) or {}).get("name"), z, x, y
        if len(ref) > 1 and ref[1]:
            oid = ref[1][0]
            z, x, y = first_spawn(obj_by_id.get(oid))
            return "object", oid, (obj_by_id.get(oid) or {}).get("name"), z, x, y
        if len(ref) > 2 and ref[2]:
            return "item", ref[2][0], None, None, None, None
        return (None,) * 6

    rows = []
    for q in quests:
        races = q.get("requiredRaces") or 0
        xp_entry = xp.get(str(q["id"]))
        zone = q.get("zoneOrSort") or 0
        rows.append((
            q["id"], q.get("name"), q.get("questLevel"), q.get("requiredLevel"),
            q.get("requiredMaxLevel") or None, faction(races), races, q.get("requiredClasses") or 0,
            zone, zone_names.get(zone) if zone > 0 else None,
            xp_entry[1] if xp_entry else None,
            *endpoint(q.get("startedBy")), *endpoint(q.get("finishedBy")),
            json.dumps(q.get("preQuestSingle") or []), json.dumps(q.get("preQuestGroup") or []),
            q.get("nextQuestInChain") or None, q.get("breadcrumbForQuestId") or None,
            json.dumps(q.get("exclusiveTo") or []), 1 if (q.get("specialFlags") or 0) & 1 else 0,
            " ".join(q.get("objectivesText") or []), json.dumps(q),
        ))
    db.executemany(f"INSERT INTO quests VALUES ({','.join('?' * 31)})", rows)

    def friendly(n):
        fa = n.get("friendlyToFaction")
        return fa if isinstance(fa, str) else None

    db.executemany("INSERT INTO npcs VALUES (?,?,?,?,?,?,?,?,?)", [
        (n["id"], n.get("name"), n.get("minLevel"), n.get("maxLevel"), n.get("rank"),
         n.get("zoneID"), friendly(n), sum(len(v or []) for v in as_map(n.get("spawns")).values()),
         json.dumps(n)) for n in npcs])
    db.executemany("INSERT INTO objects VALUES (?,?,?,?,?)", [
        (o["id"], o.get("name"), o.get("zoneID"),
         sum(len(v or []) for v in as_map(o.get("spawns")).values()), json.dumps(o)) for o in objects])
    db.executemany("INSERT INTO items VALUES (?,?,?)",
                   [(i["id"], i.get("name"), json.dumps(i)) for i in items])

    db.executescript("""
    CREATE INDEX q_level ON quests(quest_level); CREATE INDEX q_zone ON quests(zone_or_sort);
    CREATE INDEX q_faction ON quests(faction); CREATE INDEX n_name ON npcs(name);
    """)
    db.commit()
    for t in ("quests", "npcs", "objects", "items", "zones"):
        print(t, db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

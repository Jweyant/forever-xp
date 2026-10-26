"""Build gamedata/quests.json: every WoW Forever quest, for the website.

Source: Questie's Forever database (QuestieDB, GPLv3 per the Questie team's licensing note),
exported by tools/refresh_questie_data.sh into data/questiedb/ and data/forever_questdb.sqlite.
Zone names come from the Forever client's AreaTable (wago.tools) when cached, otherwise from
Questie's zone constants.

Quests whose IDs aren't in Classic Era (cmangos classic-db, --cmangos) are marked "new"; quests
that exist in both but changed level, required level or name get "chg".

Usage: python3 tools/build_quests.py [--cache .cache/wago] [--cmangos cmangos.sql] [--out gamedata/quests.json]
"""
import argparse
import csv
import json
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QSORT = {-1: "Epic", -24: "Herbalism", -61: "Warlock", -81: "Warrior", -82: "Shaman", -101: "Fishing",
         -121: "Blacksmithing", -141: "Paladin", -161: "Mage", -162: "Rogue", -181: "Alchemy",
         -182: "Leatherworking", -201: "Engineering", -221: "Treasure map", -261: "Hunter", -262: "Priest",
         -263: "Druid", -264: "Tailoring", -284: "Special", -304: "Cooking", -324: "First Aid",
         -344: "Legendary", -364: "Darkmoon Faire", -365: "Ahn'Qiraj War", -366: "Lunar Festival",
         -367: "Reputation", -368: "Invasion", -369: "Midsummer", -370: "Brewfest", -22: "Seasonal"}
CLASS_BITS = {1: "Warrior", 2: "Paladin", 4: "Hunter", 8: "Rogue", 16: "Priest", 64: "Shaman", 128: "Mage",
              256: "Warlock", 1024: "Druid"}


def pretty_const(name):
    words = name.replace("_", " ").title()
    words = re.sub(r"\b(Of|The|And)\b", lambda m: m.group(1).lower(), words).replace(" S ", "'s ")
    return words[:1].upper() + words[1:]


def zone_names(cache, questie_dir):
    names = {}
    # tools/build_items.py caches tables per build (<cache>/<build>/); take the newest download.
    found = sorted(Path(cache).glob("*/AreaTable.csv"), key=lambda p: p.stat().st_mtime) if Path(cache).exists() else []
    area = found[-1] if found else Path(cache) / "AreaTable.csv"
    if area.exists():
        with area.open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                names[int(r["ID"])] = r.get("AreaName_lang") or r.get("ZoneName")
    zfile = Path(questie_dir) / "zoneIDs.json"
    if zfile.exists():
        z = json.loads(zfile.read_text())
        pairs = z.items() if isinstance(z, dict) else []
        for k, v in pairs:
            if isinstance(v, int) and v not in names:
                names[v] = pretty_const(k)
    dfile = Path(questie_dir) / "dungeons.json"
    if dfile.exists():
        for k, v in json.loads(dfile.read_text()).items():
            if isinstance(v, (list, tuple)) and v:
                names.setdefault(int(k), v[0])
            elif isinstance(v, dict) and v.get("1"):
                names.setdefault(int(k), v["1"])
    return names


def cap(s):
    return s[:1].upper() + s[1:] if s else s


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=str(ROOT / ".cache" / "wago"))
    ap.add_argument("--questie", default=str(ROOT / "data" / "questiedb"))
    ap.add_argument("--sqlite", default=str(ROOT / "data" / "forever_questdb.sqlite"))
    ap.add_argument("--out", default=str(ROOT / "gamedata" / "quests.json"))
    ap.add_argument("--cmangos", help="cmangos classic-db SQL dump, to mark quests new to Forever")
    a = ap.parse_args()

    classic = {}
    if a.cmangos:
        sys.path.insert(0, str(ROOT / "tools"))
        import mysqldump
        for q in mysqldump.read(a.cmangos, ["quest_template"])["quest_template"]:
            classic[q["entry"]] = q

    zones = zone_names(a.cache, a.questie)
    items = {i["id"]: i for i in json.loads((Path(a.questie) / "items.json").read_text())}
    rewards = defaultdict(list)
    for i in items.values():
        for q in i.get("questRewards") or []:
            rewards[q].append(i["id"])
    db = sqlite3.connect(a.sqlite)
    db.row_factory = sqlite3.Row

    def place(kind, zid, x, y, name, eid):
        if not name:
            return None
        p = {"n": name, "t": kind or "npc"}
        if eid:
            p["id"] = eid
        if zid:
            p["z"] = cap(zones.get(zid) or f"Zone {zid}")
        if x is not None and x >= 0:
            p["x"], p["y"] = round(x, 1), round(y, 1)
        return p

    out = []
    for r in db.execute("SELECT * FROM quests ORDER BY id"):
        raw = json.loads(r["json"])
        zs = r["zone_or_sort"] or 0
        zone = zones.get(zs) if zs > 0 else QSORT.get(zs)
        if not zone and r["start_zone"]:
            zone = zones.get(r["start_zone"])
        q = {"id": r["id"], "n": r["name"], "lv": r["quest_level"], "req": r["required_level"] or 0,
             "z": cap(zone or "Other")}
        side = {"horde": "H", "alliance": "A"}.get((r["faction"] or "").lower())
        if side:
            q["side"] = side
        if r["required_classes"]:
            q["cls"] = [v for b, v in CLASS_BITS.items() if r["required_classes"] & b]
        if r["xp"]:
            q["xp"] = r["xp"]
        s = place(r["start_type"], r["start_zone"], r["start_x"], r["start_y"], r["start_name"], r["start_id"])
        e = place(r["end_type"], r["end_zone"], r["end_x"], r["end_y"], r["end_name"], r["end_id"])
        if s:
            q["start"] = s
        if e and (not s or e["n"] != s["n"] or e.get("z") != s.get("z")):
            q["end"] = e
        text = raw.get("objectivesText") or []
        if text:
            q["obj"] = " ".join(t for t in text if t)[:600]
        pre = (json.loads(r["pre_quest_single"] or "[]") or []) + (json.loads(r["pre_quest_group"] or "[]") or [])
        if pre:
            q["pre"] = pre[:6]
        if r["next_in_chain"]:
            q["next"] = r["next_in_chain"]
        if r["repeatable"]:
            q["rep"] = 1
        if rewards.get(r["id"]):
            q["rew"] = [{"id": i, "n": items[i]["name"]} for i in rewards[r["id"]][:8]]
        reps = raw.get("reputationReward") or []
        if reps:
            q["repu"] = len(reps)
        if classic:
            c = classic.get(r["id"])
            if not c:
                q["new"] = 1
            else:
                chg = []
                if (c.get("QuestLevel") or 0) > 0 and q["lv"] > 0 and c["QuestLevel"] != q["lv"]:
                    chg.append(f"level {c['QuestLevel']} to {q['lv']}")
                if (c.get("MinLevel") or 0) and q["req"] and c["MinLevel"] != q["req"]:
                    chg.append(f"required level {c['MinLevel']} to {q['req']}")
                alnum = lambda t: re.sub(r"[^a-z0-9]+", "", (t or "").lower())  # noqa: E731
                if c.get("Title") and alnum(c["Title"]) != alnum(q["n"]):
                    chg.append(f"renamed from {c['Title']}")
                if chg:
                    q["chg"] = chg
        out.append(q)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False))
    new = sum(1 for q in out if q.get("new"))
    print(f"{len(out)} quests ({new} new to Forever, {sum(1 for q in out if q.get('chg'))} changed), "
          f"{len({q['z'] for q in out})} zones -> {a.out}")


if __name__ == "__main__":
    main()

"""Build gamedata/raids.json: every dungeon and raid with its bosses, loot, levels and player data.

Sources (all open):
  - AtlasLoot Classic (GPL-2.0): raids, boss order, boss NPC IDs and loot tables
  - cmangos classic-db (GPL-3.0): raid size, level range, reset days; boss level, health,
    armor and resistances; drop chances (classic data, Forever may differ)
  - Questie's Forever database (GPLv3): entrances, the quests that belong to each instance, and
    boss drops Questie knows for Forever (mostly quest items and recipes)
  - ForeverScout player data (gamedata/players/): kills, wipes and kill times per boss, and which
    drops players confirmed in Forever. Only aggregates; nothing per player.

Usage:
  python3 tools/build_raids.py --atlasloot ext/AtlasLootClassic --cmangos ext/cmangos.sql \
      --questie data/questiedb --out gamedata/raids.json
"""
import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

# AtlasLoot content types we build pages for, plus world bosses.
RAID_TYPES = ("RAID20_CONTENT", "RAID40_CONTENT", "RAID_CONTENT")
DUNGEON_TYPES = ("DUNGEON_CONTENT",)


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower().replace("'", "")).strip("-")


def camel_words(key):
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", key).replace("Ahn Qiraj", "Ahn'Qiraj").replace("Ahn'qiraj", "Ahn'Qiraj").strip()


NAMES = {"TheRuinsofAhnQiraj": "Ruins of Ahn'Qiraj", "TheTempleofAhnQiraj": "Temple of Ahn'Qiraj",
         "Onyxia": "Onyxia's Lair", "WorldBosses": "World bosses", "Zul'Gurub": "Zul'Gurub",
         "Ragefire": "Ragefire Chasm", "TheTempleOfAtal'Hakkar": "The Temple of Atal'Hakkar"}


def atlasloot_raids(path):
    """[{key, name, kind, size, lv, area, map, bosses: [{name, npc, items}], other: [{name, items}]}] in AtlasLoot order."""
    text = (Path(path) / "AtlasLootClassic_DungeonsAndRaids" / "data.lua").read_text(encoding="utf-8", errors="replace")
    raids = []
    for block in re.split(r'\ndata\["', text)[1:]:
        key = block.split('"', 1)[0]
        head = block.split("items =", 1)[0]
        ctype = re.search(r"ContentType = (\w+)", head)
        kind = "raid" if key == "WorldBosses" or (ctype and ctype.group(1) in RAID_TYPES) else \
            "dungeon" if ctype and ctype.group(1) in DUNGEON_TYPES else None
        if not kind:
            continue
        lr = re.search(r"LevelRange = (?:GetForVersion\()?\{(\d+), (\d+), (\d+)\}", head)
        num = lambda name: int(m.group(1)) if (m := re.search(name + r" = (\d+)", head)) else None  # noqa: E731
        size = 20 if ctype and "20" in ctype.group(1) else 40 if ctype and "40" in ctype.group(1) else 5 if kind == "dungeon" else None
        r = {"key": key, "name": NAMES.get(key, camel_words(key)), "kind": kind, "size": size, "area": num("MapID"), "map": num("InstanceID"),
             **({"lv": [int(lr.group(1)), int(lr.group(3))]} if lr else {}),
             "bosses": [], "other": []}
        for entry in re.finditer(r'\{\s*(?:--[^\n]*)?\n\s*name = AL\["([^"]+)"\](.*?)(?=\n\t\t\},|\Z)', block, re.S):
            name, body = entry.group(1), entry.group(2)
            items, seen = [], set()
            for m in re.finditer(r"\{\s*\d+,\s*(\d{3,6})\s*[,}]", body):
                iid = int(m.group(1))
                if iid not in seen:
                    seen.add(iid)
                    items.append(iid)
            if not items:
                continue
            npc = re.search(r"npcID = \{?\s*(\d+)", body)
            (r["bosses"] if npc else r["other"]).append({"name": name, **({"npc": int(npc.group(1))} if npc else {}), "items": items})
        if r["bosses"] or r["other"]:
            raids.append(r)
    return raids


def cmangos_data(sql):
    import mysqldump
    d = mysqldump.read(sql, ["instance_template", "creature_template", "creature_loot_template", "reference_loot_template"])
    inst = {i["map"]: i for i in d["instance_template"]}
    ctpl = {c["Entry"]: c for c in d["creature_template"]}
    refs = defaultdict(list)
    for r in d["reference_loot_template"]:
        refs[r["entry"]].append(r)
    loot = defaultdict(list)
    for r in d["creature_loot_template"]:
        loot[r["entry"]].append(r)

    def chances(rows, scale=1.0, depth=0):
        """item -> drop chance in percent. Grouped zero-chance rows share what's left of their group."""
        out = defaultdict(float)
        groups = defaultdict(list)
        for r in rows:
            groups[r.get("groupid") or 0].append(r)
        for gid, grp in groups.items():
            explicit = sum(abs(r["ChanceOrQuestChance"] or 0) for r in grp)
            equal = [r for r in grp if not r["ChanceOrQuestChance"]]
            share = max(0.0, 100.0 - explicit) / len(equal) if gid and equal else 0.0
            for r in grp:
                c = abs(r["ChanceOrQuestChance"] or 0) or share
                if r.get("mincountOrRef") and r["mincountOrRef"] < 0:
                    if depth < 3:
                        times = max(1, r.get("maxcount") or 1)
                        for i, v in chances(refs.get(-r["mincountOrRef"], []), scale * (c or 100) / 100 * times, depth + 1).items():
                            out[i] += v
                elif r.get("item"):
                    out[r["item"]] += c * scale
        return out

    return inst, ctpl, {cid: chances(rows) for cid, rows in loot.items()}


def questie_data(qdir):
    """area id -> entrance [zone name, x, y]; area id -> [[quest id, name, level]]."""
    qdir = Path(qdir)
    entr, quests = {}, defaultdict(list)
    if not qdir.exists():
        return entr, quests
    zones = {}
    zpath = qdir / "zoneIDs.json"
    if zpath.exists():
        z = json.loads(zpath.read_text())
        zones = {int(v): k.replace("_", " ").title() for k, v in z.items()} if isinstance(z, dict) else {}
    dpath = qdir / "dungeons.json"
    if dpath.exists():
        for area, v in json.loads(dpath.read_text()).items():
            try:
                pts = (v.get("4") if isinstance(v, dict) else v[3]) or []
                zid, x, y = pts[0][0], pts[0][1], pts[0][2]
                entr[int(area)] = [zones.get(int(zid)) or "", round(float(x), 1), round(float(y), 1)]
            except (IndexError, KeyError, TypeError, ValueError):
                continue
    qpath = qdir / "quests.json"
    if qpath.exists():
        for q in json.loads(qpath.read_text()):
            try:
                area = int(q.get("zoneOrSort") or 0)
                if area > 0:
                    quests[area].append([int(q["id"]), str(q.get("name") or ""), int(q.get("questLevel") or 0)])
            except (TypeError, ValueError):
                continue
    return entr, quests


def questie_drops(qdir):
    """NPC id -> item ids Questie's Forever database says it drops."""
    import ast
    out = defaultdict(list)
    p = Path(qdir) / "items.json"
    if not p.exists():
        return out
    for i in json.loads(p.read_text()):
        nd = i.get("npcDrops") or []
        if isinstance(nd, str):
            try:
                nd = ast.literal_eval(nd)
            except (ValueError, SyntaxError):
                nd = []
        for n in nd if isinstance(nd, list) else []:
            try:
                out[int(n)].append(int(i["id"]))
            except (TypeError, ValueError, KeyError):
                pass
    return out


def player_data(pdir):
    """Boss name (lower case) -> encounter stats; source name (lower case) -> {item: players who saw it drop}."""
    pdir = Path(pdir)
    enc, seen = {}, {}
    p = pdir / "encounters.csv"
    if p.exists():
        with p.open() as f:
            for r in csv.DictReader(f):
                try:
                    enc[r["encounter"].strip().lower()] = {k: int(float(r[k])) for k in ("kills", "wipes", "median_kill_seconds", "groups") if r.get(k)}
                except (KeyError, ValueError):
                    continue
    p = pdir / "loot.csv"
    if p.exists():
        with p.open() as f:
            for r in csv.DictReader(f):
                try:
                    seen.setdefault(r["source"].strip().lower(), {})[int(r["item"])] = int(r["players"])
                except (KeyError, ValueError):
                    continue
    return enc, seen


def build(raids, inst, ctpl, chance, entr, quests, enc, seen, gear, other, qdrops=None):
    """Loot per boss, in order: AtlasLoot's list where Forever's item data has the item, Questie's
    Forever drops, then anything players confirmed (which can include items no other source has).
    Each loot row is [item, chance or None, players who saw it or absent]."""
    qdrops = qdrops or {}
    known = set(gear) | set(other)
    out = []
    for r in raids:
        it = inst.get(r["map"]) or {}
        rec = {"slug": slug(r["name"]), "name": r["name"], "kind": r.get("kind", "raid"), "size": it.get("maxPlayers") or r["size"]}
        if r.get("lv"):
            rec["lv"] = r["lv"]
        elif it.get("levelMin"):
            rec["lv"] = [it["levelMin"], it.get("levelMax") or it["levelMin"]]
        if it.get("reset_delay"):
            rec["reset"] = it["reset_delay"]
        if r["area"] in entr:
            rec["entrance"] = entr[r["area"]]
        if quests.get(r["area"]):
            rec["quests"] = sorted(quests[r["area"]], key=lambda q: (q[2], q[0]))[:40]
        bosses = []
        for b in r["bosses"]:
            c = ctpl.get(b["npc"]) or {}
            ch = chance.get(b["npc"], {})
            boss = {"name": b["name"], "npc": b["npc"]}
            for key, col in (("lv", "MaxLevel"), ("hp", "MaxLevelHealth"), ("armor", "Armor")):
                if isinstance(c.get(col), (int, float)) and c[col] > 0:
                    boss[key] = int(c[col])
            res = {s: int(c[f"Resistance{s.title()}"]) for s in ("fire", "frost", "nature", "shadow", "arcane", "holy")
                   if isinstance(c.get(f"Resistance{s.title()}"), int) and c[f"Resistance{s.title()}"] > 0}
            if res:
                boss["res"] = res
            confirmed = seen.get(b["name"].lower(), {})
            order, missing = [], 0
            for iid in b["items"]:
                if iid in known:
                    order.append(iid)
                else:
                    missing += 1
            for iid in qdrops.get(b["npc"], []) + sorted(confirmed):
                if iid not in order and (iid in known or iid in confirmed):
                    order.append(iid)
            loot = []
            for iid in order:
                row = [iid, round(min(ch[iid], 100), 1) if ch.get(iid) else None]
                if confirmed.get(iid):
                    row.append(confirmed[iid])
                loot.append(row)
            boss["loot"] = loot
            if missing:
                boss["classic_only"] = missing
            e = enc.get(b["name"].lower())
            if e:
                boss["seen"] = e
            bosses.append(boss)
        rec["bosses"] = bosses
        rec["other"] = [{"name": o["name"], "loot": [[i] for i in o["items"] if i in known]} for o in r["other"]]
        rec["other"] = [o for o in rec["other"] if o["loot"]]
        out.append(rec)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--atlasloot", required=True)
    ap.add_argument("--cmangos")
    ap.add_argument("--questie", default=str(ROOT / "data" / "questiedb"))
    ap.add_argument("--items", default=str(ROOT / "gamedata" / "items.json"))
    ap.add_argument("--other", default=str(ROOT / "gamedata" / "other-items.json"))
    ap.add_argument("--players", default=str(ROOT / "gamedata" / "players"))
    ap.add_argument("--out", default=str(ROOT / "gamedata" / "raids.json"))
    a = ap.parse_args()
    raids = atlasloot_raids(a.atlasloot)
    inst, ctpl, chance = cmangos_data(a.cmangos) if a.cmangos else ({}, {}, {})
    entr, quests = questie_data(a.questie)
    enc, seen = player_data(a.players)
    qdrops = questie_drops(a.questie)
    g = json.loads(Path(a.items).read_text())
    gear = {i["id"] for i in (g["items"] if isinstance(g, dict) else g)}
    other = {o["id"] for o in json.loads(Path(a.other).read_text())} if Path(a.other).exists() else set()
    out = build(raids, inst, ctpl, chance, entr, quests, enc, seen, gear, other, qdrops)
    Path(a.out).write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False))
    print(f"{sum(1 for r in out if r['kind'] == 'dungeon')} dungeons, {sum(1 for r in out if r['kind'] == 'raid')} raids, {sum(len(r['bosses']) for r in out)} bosses, "
          f"{sum(len(b['loot']) for r in out for b in r['bosses'])} boss drops -> {a.out}")


if __name__ == "__main__":
    main()

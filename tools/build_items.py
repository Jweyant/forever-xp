"""Build the gear database for the BIS planner.

Stats come from the WoW Forever game client (via wago.tools DB2 CSV exports): Forever reworked
itemization (ratings, spell power, removed and added items), so the client is the source of truth.
Where items come from comes from open-source projects:
  - cmangos classic-db (GPL-3.0): creature/boss loot, vendors, quest rewards, crafting spells
  - AtlasLoot Classic (GPL-2.0): instance and boss names, PvP and faction reward lists
  - ForeverScout player logs (out/loot.csv, when present): drops seen in Forever itself

Usage:
  python3 tools/build_items.py --cache .cache/wago --cmangos path/to/ClassicDB.sql \
      --atlasloot path/to/AtlasLootClassic --out gamedata/items.json [--download]

--download fetches any missing CSVs from wago.tools (needs internet; used by CI).
"""
import argparse
import csv
import io
import json
import math
import re
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import mysqldump  # noqa: E402

FOREVER_BUILD = "1.60.1.70532"
TABLES = ["ItemSparse", "Item", "RandPropPoints", "ItemArmorQuality", "ItemArmorTotal", "ArmorLocation",
          "ItemArmorShield", "ItemDamageOneHand", "ItemDamageOneHandCaster", "ItemDamageTwoHand",
          "ItemDamageTwoHandCaster", "ItemDamageRanged", "ItemDamageThrown", "ItemDamageWand",
          "ItemEffect", "ItemXItemEffect", "ItemSet", "ItemSetSpell", "Spell", "SpellName", "SpellEffect"]

# Modern item stat ids used by the Forever client -> our stat keys.
STAT = {3: "agi", 4: "str", 5: "int", 6: "spi", 7: "sta", 12: "def", 13: "dodge", 14: "parry", 15: "block",
        16: "hit", 17: "hit", 18: "spellhit", 19: "crit", 20: "crit", 21: "spellcrit", 31: "hit", 32: "crit",
        35: "resil", 36: "haste", 37: "expertise", 38: "ap", 39: "rap", 41: "heal", 42: "sp", 43: "mp5",
        45: "sp", 46: "hp5", 47: "spen", 48: "blockv", 1: "hp", 0: "mana",
        51: "fire_res", 52: "frost_res", 53: "holy_res", 54: "shadow_res", 55: "nature_res", 56: "arcane_res"}
# InventoryType -> RandPropPoints column index.
SLOT_IDX = {1: 0, 5: 0, 7: 0, 17: 0, 20: 0, 3: 1, 6: 1, 8: 1, 10: 1, 12: 1, 2: 2, 9: 2, 11: 2, 16: 2,
            13: 3, 14: 3, 21: 3, 22: 3, 23: 2, 15: 4, 25: 4, 26: 4, 28: 4}
SLOTS = {1: "head", 2: "neck", 3: "shoulder", 5: "chest", 20: "chest", 6: "waist", 7: "legs", 8: "feet",
         9: "wrist", 10: "hands", 11: "finger", 12: "trinket", 16: "back", 13: "onehand", 21: "mainhand",
         22: "offhand", 14: "shield", 23: "holdable", 17: "twohand", 15: "ranged", 25: "ranged", 26: "ranged",
         28: "relic"}
ARMOR_SUB = {0: "misc", 1: "cloth", 2: "leather", 3: "mail", 4: "plate", 6: "shield", 7: "libram", 8: "idol",
             9: "totem"}
WEAPON_SUB = {0: "axe1", 1: "axe2", 2: "bow", 3: "gun", 4: "mace1", 5: "mace2", 6: "polearm", 7: "sword1",
              8: "sword2", 10: "staff", 13: "fist", 14: "misc", 15: "dagger", 16: "thrown", 18: "crossbow",
              19: "wand", 20: "fishing"}
# Equip-spell auras -> stats (for effects the client still stores as spells).
AURA = {13: "sp", 135: "heal", 99: "ap", 124: "rap", 52: "crit_pct", 57: "spellcrit_pct", 54: "hit_pct",
        55: "spellhit_pct", 85: "mp5", 161: "hp5", 49: "dodge_pct", 47: "parry_pct", 51: "block_pct",
        158: "blockv", 123: "spen"}
SCHOOLS = {2: "holy", 4: "fire", 8: "nature", 16: "frost", 32: "shadow", 64: "arcane"}
FACTION_RACES = {"alliance": 1 | 4 | 8 | 64, "horde": 2 | 16 | 32 | 128}


def load_csv(cache, table, download):
    path = Path(cache) / f"{table}.csv"
    if not path.exists():
        if not download:
            raise SystemExit(f"missing {path}; run with --download")
        url = f"https://wago.tools/db2/{table}/csv?build={FOREVER_BUILD}"
        req = urllib.request.Request(url, headers={"User-Agent": "forever-xp data build (github.com/Jweyant/forever-xp)"})
        data = urllib.request.urlopen(req, timeout=120).read()
        if data[:1] in (b"{", b"<"):
            raise SystemExit(f"wago.tools refused {table}: {data[:120]!r}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def num(v, cast=float):
    try:
        return cast(v)
    except (TypeError, ValueError):
        return 0


def by_level(rows, key="ItemLevel"):
    out = {}
    for r in rows:
        lvl = num(r.get(key) or r.get("ID"), int)
        out[lvl] = r
    return out


def client_items(cache, download):
    T = {t: load_csv(cache, t, download) for t in TABLES}
    item = {r["ID"]: r for r in T["Item"]}
    rpp = {num(r["ID"], int): r for r in T["RandPropPoints"]}
    aq = {num(r["ID"], int): r for r in T["ItemArmorQuality"]}
    at = by_level(T["ItemArmorTotal"])
    loc = {num(r["ID"], int): r for r in T["ArmorLocation"]}
    shield = by_level(T["ItemArmorShield"])
    dmg = {k: by_level(T[k]) for k in TABLES if k.startswith("ItemDamage")}
    spell_desc = {r["ID"]: r.get("Description_lang", "") for r in T["Spell"]}
    spell_name = {r["ID"]: r["Name_lang"] for r in T["SpellName"]}
    spell_eff = defaultdict(list)
    for e in T["SpellEffect"]:
        if e.get("DifficultyID", "0") == "0":
            spell_eff[e["SpellID"]].append(e)
    effect = {r["ID"]: r for r in T["ItemEffect"]}
    item_effects = defaultdict(list)
    for x in T["ItemXItemEffect"]:
        if x["ItemEffectID"] in effect:
            item_effects[x["ItemID"]].append(effect[x["ItemEffectID"]])
    sets = {r["ID"]: r["Name_lang"] for r in T["ItemSet"]}
    set_bonus = defaultdict(list)
    for r in T["ItemSetSpell"]:
        set_bonus[r["ItemSetID"]].append(r)

    def spell_stats(sid):
        out = {}
        for e in spell_eff.get(sid, []):
            aura = num(e.get("EffectAura"), int)
            val = num(e.get("EffectBasePointsF") or e.get("EffectBasePoints"))
            key = AURA.get(aura)
            if not key or not val:
                continue
            if aura == 13:
                mask = num(e.get("EffectMiscValue_0"), int)
                if mask & 126 == 126:
                    key = "sp"
                else:
                    for bit, school in SCHOOLS.items():
                        if mask & bit:
                            out[f"sp_{school}"] = out.get(f"sp_{school}", 0) + val
                    continue
            out[key] = out.get(key, 0) + val
        return out

    items, sets_out = {}, {}
    for s in T["ItemSparse"]:
        iid = s["ID"]
        inv = num(s["InventoryType"], int)
        if inv not in SLOTS:
            continue
        q = num(s["OverallQualityID"], int)
        it = item.get(iid, {})
        cls, sub = num(it.get("ClassID"), int), num(it.get("SubclassID"), int)
        if cls not in (2, 4):
            continue
        ilvl, req = num(s["ItemLevel"], int), num(s["RequiredLevel"], int)
        name = s["Display_lang"]
        if (not name or re.search(r"\b(test|testing|deprecated|unused|monster|NPC|\[PH\]|PH|QA ?test\w*)\b", name, re.I)
                or re.match(r"^\d+ (Epic|Green|Blue|Rare|Uncommon|Purple) ", name) or name.startswith(("zz", "QA"))):
            continue
        stats = {}
        prow = rpp.get(ilvl)
        qn = "Epic" if q >= 4 else "Superior" if q == 3 else "Good"
        for i in range(10):
            st, pct = num(s.get(f"StatModifier_bonusStat_{i}"), int), num(s.get(f"StatPercentEditor_{i}"))
            if st < 0 or not pct or not prow:
                continue
            budget = num(prow.get(f"{qn}F_{SLOT_IDX.get(inv, 0)}") or prow.get(f"{qn}_{SLOT_IDX.get(inv, 0)}"))
            amount = round(budget * pct / 10000)
            key = STAT.get(st)
            if key and amount:
                stats[key] = stats.get(key, 0) + amount
        # Armor
        if cls == 4 and sub in (1, 2, 3, 4) and inv in loc and ilvl in aq and ilvl in at:
            mat = ["", "Cloth", "Leather", "Mail", "Plate"][sub]
            mod = loc[inv].get({"Mail": "Chainmodifier"}.get(mat, mat + "modifier"))
            stats["armor"] = round(num(aq[ilvl].get(f"Qualitymod_{q}")) * num(at[ilvl].get(mat)) * num(mod))
        elif cls == 4 and sub == 6 and ilvl in shield:
            stats["armor"] = round(num(shield[ilvl].get(f"Quality_{q}")))
        if cls == 4 and inv == 16 and ilvl in aq and ilvl in at:  # cloaks use cloth values
            stats["armor"] = round(num(aq[ilvl].get(f"Qualitymod_{q}")) * num(at[ilvl].get("Cloth")) * num(loc.get(16, {}).get("Clothmodifier")))
        # Weapon damage
        weapon = None
        if cls == 2:
            delay = num(s.get("ItemDelay"), int)
            if sub in (2, 3, 18):
                table = "ItemDamageRanged"
            elif sub == 16:
                table = "ItemDamageThrown"
            elif sub == 19:
                table = "ItemDamageWand"
            elif inv == 17:
                table = "ItemDamageTwoHandCaster" if "sp" in stats or "heal" in stats else "ItemDamageTwoHand"
            else:
                table = "ItemDamageOneHandCaster" if "sp" in stats or "heal" in stats else "ItemDamageOneHand"
            row = dmg[table].get(ilvl)
            if row and delay:
                dps = num(row.get(f"Quality_{q}"))
                var = num(s.get("DmgVariance"))
                spd = delay / 1000
                weapon = {"min": round(dps * spd * (1 - var / 2)), "max": round(dps * spd * (1 + var / 2)),
                          "speed": spd, "dps": round(dps, 1)}
                stats["dps"] = round(dps, 1)
        # Effects
        effects = []
        for e in item_effects.get(iid, []):
            sid = e["SpellID"]
            trig = num(e.get("TriggerType"), int)  # 0 use, 1 equip, 2 chance on hit
            if trig == 1:
                for k, v in spell_stats(sid).items():
                    stats[k] = stats.get(k, 0) + v
                if spell_stats(sid):
                    continue
            text = re.sub(r"\$\w+", "", spell_desc.get(sid, "") or spell_name.get(sid, "")).strip()
            if text:
                effects.append({"on": ["use", "equip", "hit"][trig] if trig < 3 else "other", "text": text[:220]})
        rec = {"id": int(iid), "name": name, "q": q, "ilvl": ilvl, "req": req, "slot": SLOTS[inv], "inv": inv,
               "type": (ARMOR_SUB.get(sub) if cls == 4 else WEAPON_SUB.get(sub)) or "misc", "cls": cls,
               "stats": stats}
        if weapon:
            rec["weapon"] = weapon
        if effects:
            rec["fx"] = effects
        ac, ar = num(s.get("AllowableClass"), int), num(s.get("AllowableRace_0"), int)
        if ac not in (0, -1) and ac & 0x7FF != 0x7FF:
            rec["classes"] = ac
        if ar not in (0, -1):
            if ar & FACTION_RACES["alliance"] and not ar & FACTION_RACES["horde"]:
                rec["side"] = "A"
            elif ar & FACTION_RACES["horde"] and not ar & FACTION_RACES["alliance"]:
                rec["side"] = "H"
        if num(s.get("Bonding"), int) == 1:
            rec["bop"] = 1
        if num(s.get("RequiredPVPRank"), int):
            rec["pvprank"] = num(s.get("RequiredPVPRank"), int)
        set_id = s.get("ItemSet")
        if set_id and set_id != "0" and set_id in sets:
            rec["set"] = int(set_id)
            if set_id not in sets_out:
                bonuses = []
                for b in sorted(set_bonus.get(set_id, []), key=lambda r: num(r["Threshold"], int)):
                    st = spell_stats(b["SpellID"])
                    bonuses.append({"n": num(b["Threshold"], int), "stats": st,
                                    "text": "" if st else re.sub(r"\$\w+", "", spell_desc.get(b["SpellID"], ""))[:200]})
                sets_out[set_id] = {"name": sets[set_id], "bonuses": bonuses}
        items[int(iid)] = rec
    return items, sets_out


INSTANCE_NAMES = {
    "Ragefire": "Ragefire Chasm", "TheTempleOfAtal'Hakkar": "Sunken Temple", "TheRuinsofAhnQiraj": "Ruins of Ahn'Qiraj",
    "TheTempleofAhnQiraj": "Temple of Ahn'Qiraj", "Zul'Farrak": "Zul'Farrak", "Zul'Gurub": "Zul'Gurub",
    "ScarletMonasteryGraveyard": "Scarlet Monastery: Graveyard", "ScarletMonasteryLibrary": "Scarlet Monastery: Library",
    "ScarletMonasteryArmory": "Scarlet Monastery: Armory", "ScarletMonasteryCathedral": "Scarlet Monastery: Cathedral",
    "DireMaulEast": "Dire Maul East", "DireMaulWest": "Dire Maul West", "DireMaulNorth": "Dire Maul North",
    "TheStockade": "The Stockade", "TheDeadmines": "The Deadmines", "WorldBosses": "World bosses",
}


def camel_words(key):
    if key in INSTANCE_NAMES:
        return INSTANCE_NAMES[key]
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", key).strip()


def atlasloot(path):
    """item id -> list of sources from AtlasLoot Classic."""
    src = defaultdict(list)
    root = Path(path)
    dr = (root / "AtlasLootClassic_DungeonsAndRaids" / "data.lua").read_text(encoding="utf-8", errors="replace")
    for block in re.split(r'\ndata\["', dr)[1:]:
        key = block.split('"', 1)[0]
        content = "raid" if "RAID" in block[:1200].split("items =")[0] else "dungeon"
        lr = re.search(r"LevelRange = (?:GetForVersion\()?\{(\d+), (\d+), (\d+)\}", block)
        inst = camel_words(key)
        for boss in re.finditer(r'name = AL\["([^"]+)"\](.*?)(?=\n\t\t\},|\n\t\t\{ --|\Z)', block, re.S):
            bname, body = boss.group(1), boss.group(2)
            for m in re.finditer(r"\{\s*\d+,\s*(\d{3,6})\s*[,}]", body):
                src[int(m.group(1))].append({"t": content, "z": inst, "n": bname,
                                             **({"lv": [int(lr.group(1)), int(lr.group(3))]} if lr else {})})
    for mod, kind in (("AtlasLootClassic_PvP", "pvp"), ("AtlasLootClassic_Factions", "rep")):
        txt = (root / mod / "data.lua").read_text(encoding="utf-8", errors="replace")
        for block in re.split(r'\ndata\["', txt)[1:]:
            key = block.split('"', 1)[0]
            label = camel_words(key)
            for sub in re.finditer(r'name = (?:AL|ALIL)\["([^"]+)"\](.*?)(?=name = (?:AL|ALIL)\[|\Z)', block, re.S):
                for m in re.finditer(r"\{\s*\d+,\s*(\d{3,6})\s*[,}]", sub.group(2)):
                    src[int(m.group(1))].append({"t": kind, "z": label, "n": sub.group(1)})
    return src


def cmangos_sources(sql, keep):
    d = mysqldump.read(sql, ["creature_loot_template", "reference_loot_template", "creature_template",
                             "creature", "npc_vendor", "npc_vendor_template", "quest_template",
                             "gameobject_loot_template", "spell_template", "instance_template"])
    ctpl = {c["Entry"]: c for c in d["creature_template"]}
    cmap = {}
    for c in d["creature"]:
        cmap.setdefault(c["id"], c["map"])
    instances = {i["map"]: i for i in d["instance_template"]}
    refs = defaultdict(list)
    for r in d["reference_loot_template"]:
        refs[r["entry"]].append(r)
    ref_users = defaultdict(int)
    for r in d["creature_loot_template"]:
        if r["mincountOrRef"] and r["mincountOrRef"] < 0:
            ref_users[-r["mincountOrRef"]] += 1

    def expand(rows, depth=0):
        for r in rows:
            if r["mincountOrRef"] and r["mincountOrRef"] < 0 and depth < 4:
                ref = -r["mincountOrRef"]
                if ref_users[ref] > 40:  # shared world-drop table
                    for x in refs.get(ref, []):
                        if x["item"] in keep:
                            yield x["item"], None, "world"
                    continue
                yield from ((i, c, k) for i, c, k in expand(refs.get(ref, []), depth + 1))
            elif r["item"] in keep:
                yield r["item"], r["ChanceOrQuestChance"], "drop"

    src = defaultdict(list)
    by_creature = defaultdict(list)
    for r in d["creature_loot_template"]:
        by_creature[r["entry"]].append(r)
    world = set()
    for cid, rows in by_creature.items():
        c = ctpl.get(cid)
        if not c:
            continue
        for item, chance, kind in expand(rows):
            if kind == "world":
                world.add(item)
                continue
            m = cmap.get(cid)
            rec = {"t": "drop", "n": c["Name"], "lv": c.get("MaxLevel")}
            if chance:
                rec["ch"] = round(abs(chance), 2)
            if c.get("Rank", 0) == 3:
                rec["boss"] = 1
            if m in instances:
                rec["inst"] = 1
            src[item].append(rec)
    for item, lst in list(src.items()):
        drops = [x for x in lst if x["t"] == "drop"]
        if len(drops) > 8 and not any(x.get("boss") for x in drops):
            world.add(item)
            src[item] = [x for x in lst if x["t"] != "drop"]
    for item in world:
        src[item].append({"t": "world"})
    vend = list(d["npc_vendor"])
    tmpl = defaultdict(list)
    for v in d["npc_vendor_template"]:
        tmpl[v["entry"]].append(v)
    for v in vend:
        rows = tmpl.get(v["item"]) if v["item"] in tmpl and v["item"] not in keep else [v]
        for r in rows or []:
            if r["item"] in keep and v["entry"] in ctpl:
                src[r["item"]].append({"t": "vendor", "n": ctpl[v["entry"]]["Name"]})
    for q in d["quest_template"]:
        ids = [q.get(f"RewChoiceItemId{i}") for i in range(1, 7)] + [q.get(f"RewItemId{i}") for i in range(1, 5)]
        for item in ids:
            if item in keep:
                rec = {"t": "quest", "n": q["Title"], "lv": q.get("QuestLevel"), "qid": q["entry"],
                       "min": q.get("MinLevel") or 0}
                if q.get("RequiredClasses"):
                    rec["qcls"] = q["RequiredClasses"]
                src[item].append(rec)
    for sp in d["spell_template"]:
        for i in (1, 2, 3):
            if sp.get(f"Effect{i}") == 24 and sp.get(f"EffectItemType{i}") in keep:
                src[sp[f"EffectItemType{i}"]].append({"t": "craft", "n": sp["SpellName"]})
    return src


def rank_sources(lst):
    order = {"raid": 0, "dungeon": 1, "pvp": 2, "rep": 3, "quest": 4, "craft": 5, "vendor": 6, "drop": 7,
             "world": 8, "logged": -1}
    seen, out = set(), []
    for s in sorted(lst, key=lambda s: (order.get(s["t"], 9), -s.get("ch", 0))):
        key = (s["t"], s.get("n"), s.get("z"))
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out[:4]


def effective_level(rec, sources):
    """Level a character realistically needs to get and use the item.

    Many items (quest rewards especially) have no required level in the client, so use the
    easiest way to get it: the quest's minimum level, the dungeon's level range, or a raid at 60.
    """
    if rec["req"]:
        return rec["req"]
    best = None
    for s in sources or []:
        if s["t"] == "quest":
            v = s.get("min") or max(1, (s.get("lv") or rec["ilvl"]) - 4)
        elif s["t"] == "dungeon" and isinstance(s.get("lv"), list):
            v = s["lv"][0]
        elif s["t"] == "raid":
            v = 60
        elif s["t"] == "drop" and s.get("lv"):
            v = max(1, s["lv"] - 3)
        else:
            continue
        best = v if best is None else min(best, v)
    return best if best is not None else max(1, min(60, rec["ilvl"] - 5))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=".cache/wago")
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--cmangos")
    ap.add_argument("--atlasloot")
    ap.add_argument("--out", default="gamedata/items.json")
    ap.add_argument("--report", default="gamedata/items-report.md")
    a = ap.parse_args()

    items, sets = client_items(a.cache, a.download)
    keep = set(items)
    al = atlasloot(a.atlasloot) if a.atlasloot else {}
    cm = cmangos_sources(a.cmangos, keep) if a.cmangos else {}
    logged = defaultdict(list)
    loot_csv = Path("out/loot.csv")
    if loot_csv.exists():
        with loot_csv.open() as f:
            for r in csv.DictReader(f):
                logged[int(r["item"])].append({"t": "logged", "n": r.get("source") or "", "z": r.get("zone") or "",
                                               "seen": int(r.get("players") or 1)})
    no_src = 0
    for iid, rec in items.items():
        s = rank_sources(logged.get(iid, []) + al.get(iid, []) + cm.get(iid, []))
        if s:
            rec["src"] = s
        else:
            no_src += 1
        rec["lvl"] = effective_level(rec, s)
    out = {"build": FOREVER_BUILD, "items": sorted(items.values(), key=lambda r: r["id"]), "sets": sets}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False))
    by_q = defaultdict(int)
    for r in items.values():
        by_q[r["q"]] += 1
    Path(a.report).write_text(
        f"# Gear database\n\nForever client build {FOREVER_BUILD}.\n\n"
        f"- Equippable items: {len(items)} (by quality: {dict(sorted(by_q.items()))})\n"
        f"- Item sets: {len(sets)}\n- Items with a known source: {len(items) - no_src}\n"
        f"- Items with no known source yet: {no_src}\n")
    print(f"{len(items)} items, {len(sets)} sets, {len(items) - no_src} with sources -> {a.out}")


if __name__ == "__main__":
    main()

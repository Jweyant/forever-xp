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
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import mysqldump  # noqa: E402
import wago  # noqa: E402

FOREVER_BUILD = wago.FOREVER_FALLBACK  # replaced in main() by the newest Forever build
TABLES = ["ItemSparse", "Item", "RandPropPoints", "ItemArmorQuality", "ItemArmorTotal", "ArmorLocation",
          "ItemArmorShield", "ItemDamageOneHand", "ItemDamageOneHandCaster", "ItemDamageTwoHand",
          "ItemDamageTwoHandCaster", "ItemDamageRanged", "ItemDamageThrown", "ItemDamageWand",
          "ItemEffect", "ItemXItemEffect", "ItemSet", "ItemSetSpell", "Spell", "SpellName", "SpellEffect",
          "AreaTable"]  # AreaTable: zone names for tools/build_quests.py

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
    path = Path(cache) / FOREVER_BUILD / f"{table}.csv"
    if not path.exists():
        if not download:
            raise SystemExit(f"missing {path}; run with --download")
        url = f"{wago.WAGO}/db2/{table}/csv?build={FOREVER_BUILD}"
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


def icon_names(cache, download):
    """IconFileDataID -> icon file name (for render.worldofwarcraft.com/us/icons/56/<name>.jpg)."""
    path = Path(cache) / "icons.json"
    if not path.exists():
        if not download:
            return {}
        req = urllib.request.Request("https://wago.tools/api/files?search=interface/icons/",
                                     headers={"User-Agent": "forever-xp data build (github.com/Jweyant/forever-xp)"})
        path.write_bytes(urllib.request.urlopen(req, timeout=180).read())
    raw = json.loads(path.read_text())
    # The render service names icons with hyphens where the file name has spaces.
    return {int(k): v.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower().replace(" ", "-")
            for k, v in raw.items() if v.startswith("interface/icons/")}


def wowsims_icons(path):
    """ItemID -> icon name from wowsims/forever's item database (MIT), for items the client
    tables leave without a named icon. Names wowsims couldn't resolve ("unknown_...") are skipped."""
    if not path or not Path(path).exists():
        return {}
    db = json.loads(Path(path).read_text())
    out = {}
    for e in (db.get("items") or []) + (db.get("itemIcons") or []):
        icon = str(e.get("icon") or "").lower().replace(" ", "-")
        if re.fullmatch(r"[a-z0-9_-]+", icon) and not icon.startswith("unknown_") and str(e.get("id", "")).isdigit():
            out.setdefault(int(e["id"]), icon)
    return out


def display_ids(cache, download):
    """ItemID -> ItemDisplayInfoID (the 3D model an item uses), via ItemModifiedAppearance ->
    ItemAppearance. Loaded tolerantly outside TABLES: if the Forever build doesn't ship these
    tables, items simply carry no display id (cmangos fills what it can, the site skips the rest).
    """
    try:
        ima = load_csv(cache, "ItemModifiedAppearance", download)
        app = load_csv(cache, "ItemAppearance", download)
    except (SystemExit, OSError) as e:
        print(f"display ids: tables unavailable ({e}); relying on cmangos displayid", file=sys.stderr)
        return {}
    info = {r.get("ID"): num(r.get("ItemDisplayInfoID"), int) for r in app}
    best = {}
    for r in ima:
        iid = num(r.get("ItemID"), int)
        order = num(r.get("OrderIndex"), int)
        did = info.get(r.get("ItemAppearanceID"), 0)
        # The default appearance is the lowest OrderIndex.
        if iid and did and (iid not in best or order < best[iid][0]):
            best[iid] = (order, did)
    return {iid: v[1] for iid, v in best.items()}


def appearance_icons(cache, download):
    """ItemID -> icon file ID from the item's default appearance (ItemAppearance.DefaultIconFileDataID).
    Newer items often leave Item.IconFileDataID empty and only set the icon here."""
    try:
        ima = load_csv(cache, "ItemModifiedAppearance", download)
        app = load_csv(cache, "ItemAppearance", download)
    except (SystemExit, OSError):
        return {}
    icon = {r.get("ID"): num(r.get("DefaultIconFileDataID"), int) for r in app}
    best = {}
    for r in ima:
        iid, order = num(r.get("ItemID"), int), num(r.get("OrderIndex"), int)
        fid = icon.get(r.get("ItemAppearanceID"), 0)
        if iid and fid and (iid not in best or order < best[iid][0]):
            best[iid] = (order, fid)
    return {iid: v[1] for iid, v in best.items()}


def client_icons_and_quality(cache, download, wowsims=None):
    """ItemID -> (icon name or None, quality or None) for every item in the client, gear or not.
    Icon: the item's own icon, else its default appearance's, else wowsims' name. Quality from
    ItemSparse. The tables are cached, so this re-reads files client_items already fetched."""
    names = icon_names(cache, download)
    app = appearance_icons(cache, download)
    out = {}
    for r in load_csv(cache, "Item", download):
        iid = num(r.get("ID"), int)
        if iid:
            out[iid] = [names.get(num(r.get("IconFileDataID"), int)) or names.get(app.get(iid, 0)) or (wowsims or {}).get(iid), None]
    for s in load_csv(cache, "ItemSparse", download):
        iid, q = num(s.get("ID"), int), num(s.get("OverallQualityID"), int)
        if iid in out and q is not None and 0 <= q <= 7:
            out[iid][1] = q
    return {k: tuple(v) for k, v in out.items()}


def client_item_text(cache, download):
    """ItemID -> tooltip fields for non-gear items, from the client: ds flavor text, u "Use:" texts,
    st stack size, b binding (1 picked up, 2 equipped), sp sell price in copper, il item level.
    Missing tables or columns just leave fields out."""
    try:
        sparse = load_csv(cache, "ItemSparse", download)
        effect = {r["ID"]: r for r in load_csv(cache, "ItemEffect", download)}
        links = load_csv(cache, "ItemXItemEffect", download)
        spell_desc = {r["ID"]: r.get("Description_lang", "") for r in load_csv(cache, "Spell", download)}
        spell_name = {r["ID"]: r.get("Name_lang", "") for r in load_csv(cache, "SpellName", download)}
    except (SystemExit, OSError, KeyError):
        return {}
    uses = defaultdict(list)
    for x in links:
        e = effect.get(x.get("ItemEffectID"))
        if not e or num(e.get("TriggerType"), int) not in (0, 5):  # 0 on use, 5 learn (recipes)
            continue
        sid = e.get("SpellID")
        text = cleanup_spell_text(spell_desc.get(sid, "") or spell_name.get(sid, ""))
        iid = num(x.get("ItemID"), int)
        if text and iid and text not in uses[iid]:
            uses[iid].append(text[:220])
    out = {}
    for s in sparse:
        iid = num(s.get("ID"), int)
        if not iid:
            continue
        rec = {}
        desc = cleanup_spell_text(s.get("Description_lang") or "")
        if desc:
            rec["ds"] = desc[:200]
        if uses.get(iid):
            rec["u"] = uses[iid][:3]
        for key, col, lo, hi in (("st", "Stackable", 2, 1000), ("b", "Bonding", 1, 2), ("sp", "SellPrice", 1, 10**8),
                                 ("il", "ItemLevel", 1, 400)):
            v = num(s.get(col), int)
            if v is not None and lo <= v <= hi:
                rec[key] = v
        if rec:
            out[iid] = rec
    return out


def cleanup_spell_text(s):
    """Client text holds unresolved spell variables ($s1, $d, $/1000;s1) and markup; drop them."""
    s = re.sub(r"\$\/?\d*;?[a-zA-Z]+\d*", "", str(s or ""))
    s = re.sub(r"\|c[0-9a-fA-F]{8}|\|r|\|n", " ", s)
    return re.sub(r"\s{2,}", " ", s).strip()


def client_items(cache, download):
    T = {t: load_csv(cache, t, download) for t in TABLES}
    icons = icon_names(cache, download)
    dids = display_ids(cache, download)
    app_icons = appearance_icons(cache, download)
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
        icon = icons.get(num(it.get("IconFileDataID"), int)) or icons.get(app_icons.get(int(iid), 0))
        if icon:
            rec["icon"] = icon
        did = dids.get(int(iid))
        if did:
            rec["did"] = did
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
                             "gameobject_loot_template", "spell_template", "instance_template",
                             "item_template"])
    # Fallback display ids for items the client's appearance tables miss (classic-era art).
    display = {r["entry"]: r["displayid"] for r in d["item_template"]
               if r.get("entry") in keep and isinstance(r.get("displayid"), int) and r["displayid"] > 0}
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
    classic = {r["entry"]: r for r in d["item_template"] if isinstance(r.get("entry"), int)}
    return src, display, classic


def questie_sources(qdir, keep):
    """Item sources from Questie's Forever database: drops, chests, vendors and quest rewards."""
    q = Path(qdir)
    items = json.loads((q / "items.json").read_text())
    npcs = {n["id"]: n for n in json.loads((q / "npcs.json").read_text())}
    objs = {o["id"]: o for o in json.loads((q / "objects.json").read_text())}
    quests = {x["id"]: x for x in json.loads((q / "quests.json").read_text())}
    dungeons = {}
    for k, v in json.loads((q / "dungeons.json").read_text()).items():
        if isinstance(v, list) and v:
            dungeons[int(k)] = v[0]
    zone_names = {}
    zfile = q / "zoneIDs.json"
    if zfile.exists():
        for k, v in json.loads(zfile.read_text()).items():
            if isinstance(v, int):
                w = re.sub(r"\b(Of|The|And)\b", lambda m: m.group(1).lower(), k.replace("_", " ").title())
                zone_names[v] = w[:1].upper() + w[1:]
    zone_names.update(dungeons)
    src = defaultdict(list)
    for it in items:
        iid = it["id"]
        if iid not in keep:
            continue
        drops = it.get("npcDrops") or []
        for nid in drops[:12]:
            n = npcs.get(nid)
            if not n or not n.get("name"):
                continue
            z = n.get("zoneID")
            rec = {"t": "drop", "n": n["name"], "lv": n.get("maxLevel")}
            if z in zone_names:
                rec["z"] = zone_names[z]
            if z in dungeons:
                rec["t"] = "dungeon"
                if n.get("rank") == 3 or n.get("maxLevel", 0) >= 63:
                    rec["boss"] = 1
            elif n.get("rank") == 3:
                rec["boss"] = 1
            src[iid].append(rec)
        if len(drops) > 12 and not any(s.get("boss") for s in src[iid]):
            src[iid] = [{"t": "world"}]
        for oid in (it.get("objectDrops") or [])[:3]:
            o = objs.get(oid)
            if o and o.get("name"):
                src[iid].append({"t": "chest", "n": o["name"], **({"z": zone_names[o["zoneID"]]} if o.get("zoneID") in zone_names else {})})
        for vid in (it.get("vendors") or [])[:3]:
            n = npcs.get(vid)
            if n and n.get("name"):
                src[iid].append({"t": "vendor", "n": n["name"], **({"z": zone_names[n["zoneID"]]} if n.get("zoneID") in zone_names else {})})
        for qid in (it.get("questRewards") or [])[:3]:
            x = quests.get(qid)
            if x:
                rec = {"t": "quest", "n": x["name"], "lv": x.get("questLevel"), "qid": qid, "min": x.get("requiredLevel") or 0}
                if x.get("requiredClasses"):
                    rec["qcls"] = x["requiredClasses"]
                src[iid].append(rec)
    return src


def apply_quest_faction(items, quests_path=Path("gamedata/quests.json")):
    """Items only obtainable from one faction's quests belong to that faction.

    The client doesn't mark quest rewards by side, so a Horde planner would otherwise suggest
    Stormwind quest rewards. Uses the quest list built from Questie (gamedata/quests.json).
    """
    if not quests_path.exists():
        return 0
    side = {q["id"]: q.get("side") for q in json.loads(quests_path.read_text())}
    n = 0
    for rec in items.values():
        if rec.get("side") or not rec.get("src"):
            continue
        sides = set()
        for s in rec["src"]:
            if s["t"] != "quest":
                sides = None
                break
            sides.add(side.get(s.get("qid")))
        if sides and len(sides) == 1 and None not in sides:
            rec["side"] = sides.pop()
            n += 1
    return n


# Classic PvP rank titles, Alliance / Horde, by RequiredPVPRank (1-14).
PVP_RANKS = {1: ("Private", "Scout"), 2: ("Corporal", "Grunt"), 3: ("Sergeant", "Sergeant"),
             4: ("Master Sergeant", "Senior Sergeant"), 5: ("Sergeant Major", "First Sergeant"),
             6: ("Knight", "Stone Guard"), 7: ("Knight-Lieutenant", "Blood Guard"), 8: ("Knight-Captain", "Legionnaire"),
             9: ("Knight-Champion", "Centurion"), 10: ("Lieutenant Commander", "Champion"),
             11: ("Commander", "Lieutenant General"), 12: ("Marshal", "General"),
             13: ("Field Marshal", "Warlord"), 14: ("Grand Marshal", "High Warlord")}


def pvp_rank_source(rec):
    """Items that need a PvP rank are rank rewards, whatever else we know about them."""
    rank = rec.get("pvprank")
    if not rank:
        return None
    names = PVP_RANKS.get(rank)
    if names:
        side = rec.get("side")
        title = names[0] if side == "A" else names[1] if side == "H" else f"{names[0]} / {names[1]}"
        return {"t": "pvp", "n": f"Rank {rank} ({title})", "z": "PvP rank reward"}
    return {"t": "pvp", "n": f"Rank {rank}", "z": "PvP rank reward"}


JOURNAL_TABLES = ["JournalInstance", "JournalEncounter", "JournalEncounterItem", "Map"]
JOURNAL_NOTE = []  # what the journal step found, for the report


def _col(row, *names):
    """A column by any of several names, since DB2 exports rename fields between builds."""
    for n in names:
        if n in row:
            return row[n]
    lower = {k.lower(): v for k, v in row.items()}
    for n in names:
        if n.lower() in lower:
            return lower[n.lower()]
    return None


def journal_sources(cache, download, keep):
    """item id -> boss-drop sources from the client's dungeon journal (JournalEncounterItem).

    The journal is the one place the Forever client itself says which boss drops what, so it
    covers new dungeon and raid items that no open-source loot table knows yet.
    """
    src = defaultdict(list)
    tables = {}
    JOURNAL_NOTE.clear()
    for t in JOURNAL_TABLES:
        try:
            tables[t] = load_csv(cache, t, download)
            cols = list(tables[t][0].keys())[:12] if tables[t] else []
            JOURNAL_NOTE.append(f"{t}: {len(tables[t])} rows, columns {cols}")
        except (SystemExit, OSError, urllib.error.URLError) as e:  # table missing in this build or wago down
            JOURNAL_NOTE.append(f"{t}: unavailable ({str(e)[:160]})")
            print(f"dungeon journal: {t} unavailable ({e}); skipping", file=sys.stderr)
            return {}
    # Map -> instance type (1 dungeon, 2 raid)
    map_type = {}
    for r in tables["Map"]:
        mid, itype = num(_col(r, "ID"), int), num(_col(r, "InstanceType"), int)
        if mid is not None:
            map_type[mid] = itype
    inst = {}
    for r in tables["JournalInstance"]:
        iid = num(_col(r, "ID"), int)
        if iid is None:
            continue
        mid = num(_col(r, "MapID", "Map"), int)
        inst[iid] = {"name": _col(r, "Name_lang", "Name") or "", "kind": "raid" if map_type.get(mid) == 2 else "dungeon"}
    enc = {}
    for r in tables["JournalEncounter"]:
        eid = num(_col(r, "ID"), int)
        if eid is None:
            continue
        enc[eid] = {"name": _col(r, "Name_lang", "Name") or "", "inst": num(_col(r, "JournalInstanceID", "InstanceID"), int)}
    n = 0
    for r in tables["JournalEncounterItem"]:
        item = num(_col(r, "ItemID"), int)
        e = enc.get(num(_col(r, "JournalEncounterID", "EncounterID"), int))
        if item in keep and e and e["name"]:
            i = inst.get(e["inst"]) or {"name": "", "kind": "dungeon"}
            rec = {"t": i["kind"], "n": e["name"], "boss": 1}
            if i["name"]:
                rec["z"] = i["name"]
            src[item].append(rec)
            n += 1
    JOURNAL_NOTE.append(f"{n} boss drops for {len(src)} items ({len(inst)} instances, {len(enc)} encounters)")
    print(f"dungeon journal: {n} boss drops for {len(src)} items")
    return src

# Player logs are public input: a drop is only published once this many different players saw it.
MIN_LOGGED_PLAYERS = 2


def read_loot_csv(path):
    """gamedata/players/loot.csv (tools/ingest_logs.py) -> {item id: [logged source, ...]}.
    Rows seen by fewer than MIN_LOGGED_PLAYERS players are left out."""
    logged = defaultdict(list)
    with Path(path).open() as f:
        for r in csv.DictReader(f):
            try:
                iid, players = int(r.get("item") or 0), int(r.get("players") or 0)
            except ValueError:
                continue
            if iid <= 0 or players < MIN_LOGGED_PLAYERS:
                continue
            logged[iid].append({"t": "logged", "n": str(r.get("source") or "")[:80], "z": str(r.get("zone") or "")[:60],
                                "seen": players})
    return logged


def _norm(s):
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


def confirm_sources(logged, known):
    """Fold player sightings into the sources other databases already list.

    A sighting whose NPC or object name matches a known source confirms it (`seen` = players),
    which ranks it first. Sightings that match nothing stay as "logged" sources: drops Forever
    added or changed that no database has yet."""
    out = [dict(s) for s in known]
    rest = []
    for lg in logged:
        n = _norm(lg.get("n"))
        hit = [s for s in out if n and _norm(s.get("n")) == n] if n else []
        if hit:
            for s in hit:
                s["seen"] = max(s.get("seen", 0), lg["seen"])
        else:
            rest.append(lg)
    return rest + out


def rank_sources(lst):
    order = {"raid": 0, "dungeon": 1, "pvp": 2, "rep": 3, "quest": 4, "craft": 5, "vendor": 6, "chest": 7,
             "drop": 8, "world": 9, "logged": -1}
    seen, out = set(), []
    for s in sorted(lst, key=lambda s: (0 if s.get("seen") else 1, order.get(s["t"], 9), -s.get("ch", 0))):
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
    if rec["req"] and rec["req"] > 1:  # Forever's new items often carry 1 as "unset"
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


# Item classes kept for the non-gear list (weapons and armor come from the client gear tables).
OTHER_CLASSES = {0: "Consumable", 1: "Container", 3: "Gem", 5: "Reagent", 6: "Projectile", 7: "Trade goods",
                 9: "Recipe", 11: "Quiver", 12: "Quest item", 13: "Key", 15: "Miscellaneous"}
JUNK_NAME = re.compile(r"\b(test|testing|deprecated|unused|monster|NPC|\[PH\]|PH|QA ?test\w*)\b", re.I)


def _ids(v):
    """Questie ID lists arrive as lists, {"1": ..} maps, or Python-literal strings."""
    if isinstance(v, str):
        try:
            import ast
            v = ast.literal_eval(v)
        except (ValueError, SyntaxError):
            return []
    if isinstance(v, dict):
        v = [v[k] for k in sorted(v, key=lambda k: int(k) if str(k).isdigit() else 0)]
    out = []
    for x in v if isinstance(v, list) else []:
        if isinstance(x, (list, dict)):
            x = _ids(x)[:1]
            x = x[0] if x else None
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            pass
    return out


def other_items(sqlite_path, gear_ids, classic, max_names=3):
    """Every non-gear Forever item Questie knows (consumables, trade goods, recipes, quest items...),
    with where it comes from and which quests use it. Compact keys for the item list:
    id, n name, q quality, c category, rl required level, d drops from [[npc, zone]], v sold by,
    o found in (objects), qs starts quest, qr reward from quests, qu used by quests (quests as [id, name]).
    main() adds icon (and the client's quality) afterwards from client_icons_and_quality()."""
    import sqlite3
    if not sqlite_path or not Path(sqlite_path).exists():
        return []
    db = sqlite3.connect(sqlite_path)
    zones = dict(db.execute("SELECT id, name FROM zones"))
    npcs = {i: (n, z) for i, n, z in db.execute("SELECT id, name, zone_id FROM npcs")}
    objects = {i: n for i, n in db.execute("SELECT id, name FROM objects")}
    quests = {}
    used_by = defaultdict(set)
    for qid, name, raw in db.execute("SELECT id, name, json FROM quests"):
        quests[qid] = name
        q = json.loads(raw)
        objs = q.get("objectives") or []
        groups = [objs.get(k) for k in ("1", "2", "3")] if isinstance(objs, dict) else (objs if isinstance(objs, list) else [])
        for iid in _ids(groups[2] if len(groups) > 2 and groups[2] else []):
            used_by[iid].add(qid)
        for iid in _ids([q.get("sourceItemId")]):
            used_by[iid].add(qid)
    zname = lambda z: (zones.get(z) or "").replace("_", " ").title() if z else ""  # noqa: E731
    out = []
    for iid, name, raw in db.execute("SELECT id, name, json FROM items ORDER BY id"):
        it = json.loads(raw)
        cls = it.get("class")
        cls = int(cls) if str(cls).lstrip("-").isdigit() else -1
        if iid in gear_ids or cls not in OTHER_CLASSES or not name or JUNK_NAME.search(name) or name.startswith(("zz", "QA")):
            continue
        c = classic.get(iid) or {}
        rec = {"id": iid, "n": name, "q": c.get("Quality") if isinstance(c.get("Quality"), int) else 1, "c": OTHER_CLASSES[cls]}
        rl = it.get("requiredLevel")
        if str(rl).isdigit() and int(rl) > 1:
            rec["rl"] = int(rl)
        drops = [[npcs[n][0], zname(npcs[n][1])] for n in _ids(it.get("npcDrops")) if n in npcs][:max_names]
        vend = sorted({npcs[n][0] for n in _ids(it.get("vendors")) if n in npcs})[:max_names]
        objs = sorted({objects[o] for o in _ids(it.get("objectDrops")) if o in objects})[:max_names]
        start = [[q, quests[q]] for q in _ids([it.get("startQuest")]) if q in quests]
        rew = [[q, quests[q]] for q in _ids(it.get("questRewards")) if q in quests][:max_names]
        used = [[q, quests[q]] for q in sorted(used_by.get(iid, set()) | set(_ids(it.get("relatedQuests")))) if q in quests][:max_names]
        for key, val in (("d", drops), ("v", vend), ("o", objs), ("qr", rew), ("qu", used)):
            if val:
                rec[key] = val
        if start:
            rec["qs"] = start[0]
        out.append(rec)
    return out


def forever_changes(items, classic):
    """Mark items that are new to Forever (no classic item with that ID) or changed from classic
    (item level, quality or required level). Returns (new, changed) counts. Without classic data,
    nothing is marked."""
    if not classic:
        return 0, 0
    new = changed = 0
    for iid, rec in items.items():
        c = classic.get(iid)
        if not c:
            rec["new"] = 1
            new += 1
            continue
        chg = []
        for key, label in (("ItemLevel", "item level"), ("Quality", "quality"), ("RequiredLevel", "required level")):
            old, now = c.get(key), rec.get({"ItemLevel": "ilvl", "Quality": "q", "RequiredLevel": "req"}[key])
            if isinstance(old, int) and isinstance(now, int) and old != now and (key != "RequiredLevel" or old > 0):
                chg.append([label, old, now])
        if chg:
            rec["chg"] = chg
            changed += 1
    return new, changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=".cache/wago")
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--cmangos")
    ap.add_argument("--atlasloot")
    ap.add_argument("--wowsims-db", help="wowsims/forever assets/database/db.json (MIT), a last fallback for item icons")
    ap.add_argument("--questie", help="data/questiedb export from tools/refresh_questie_data.sh")
    ap.add_argument("--out", default="gamedata/items.json")
    ap.add_argument("--questie-sqlite", default="data/forever_questdb.sqlite", help="from tools/refresh_questie_data.sh, for non-gear items")
    ap.add_argument("--other-out", default="gamedata/other-items.json")
    ap.add_argument("--report", default="gamedata/items-report.md")
    ap.add_argument("--build", help="Forever client build to read (default: the newest on wago.tools)")
    a = ap.parse_args()
    global FOREVER_BUILD
    FOREVER_BUILD, product = wago.forever_build(a.build)
    print(f"Forever client build {FOREVER_BUILD} ({product})")

    items, sets = client_items(a.cache, a.download)
    ws = wowsims_icons(a.wowsims_db)
    for iid, rec in items.items():
        if not rec.get("icon") and ws.get(iid):
            rec["icon"] = ws[iid]
    keep = set(items)
    al = atlasloot(a.atlasloot) if a.atlasloot else {}
    cm, cm_did, classic = cmangos_sources(a.cmangos, keep) if a.cmangos else ({}, {}, {})
    qs = questie_sources(a.questie, keep) if a.questie else {}
    jn = journal_sources(a.cache, a.download, keep)
    logged = {}
    loot_csv = Path("out/loot.csv")
    if not loot_csv.exists():  # published aggregate from the player-data workflow
        loot_csv = Path("gamedata/players/loot.csv")
    if loot_csv.exists():
        logged = read_loot_csv(loot_csv)
    no_src = 0
    for iid, rec in items.items():
        s = rank_sources(confirm_sources(logged.get(iid, []), al.get(iid, []) + jn.get(iid, []) + qs.get(iid, []) + cm.get(iid, [])))
        pvp = pvp_rank_source(rec)
        if pvp:
            # AtlasLoot's PvP entries only say "Weapons" or "Armor"; the rank is the useful part.
            had = False
            for x in s:
                if x["t"] == "pvp":
                    x["n"], had = pvp["n"], True
            if not had:
                s = rank_sources(s + [pvp])
        if s:
            rec["src"] = s
        else:
            no_src += 1
        rec["lvl"] = effective_level(rec, s)
        if "did" not in rec and cm_did.get(iid):
            rec["did"] = cm_did[iid]
    apply_quest_faction(items)
    new, changed = forever_changes(items, classic)
    out = {"build": FOREVER_BUILD, "items": sorted(items.values(), key=lambda r: r["id"]), "sets": sets}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False))
    other = other_items(a.questie_sqlite, set(items), classic)
    client = client_icons_and_quality(a.cache, a.download, ws) if other else {}
    text = client_item_text(a.cache, a.download) if other else {}
    for rec in other:
        icon, q = client.get(rec["id"], (None, None))
        if icon:
            rec["icon"] = icon
        if q is not None:
            rec["q"] = q
        rec.update(text.get(rec["id"], {}))
    if other:
        Path(a.other_out).write_text(json.dumps(other, separators=(",", ":"), ensure_ascii=False))
    by_q = defaultdict(int)
    for r in items.values():
        by_q[r["q"]] += 1
    Path(a.report).write_text(
        f"# Gear database\n\nForever client build {FOREVER_BUILD}.\n\n"
        f"- Equippable items: {len(items)} (by quality: {dict(sorted(by_q.items()))})\n"
        f"- Item sets: {len(sets)}\n- Items with a known source: {len(items) - no_src}\n"
        f"- Items with no known source yet: {no_src}\n"
        f"- Items with a display id (3D model): {sum(1 for r in items.values() if r.get('did'))}\n"
        f"- New in Forever (not in the classic item list): {new}\n- Changed in Forever: {changed}\n"
        f"- Other items (consumables, trade goods, recipes, quest items...): {len(other)}"
        f" ({sum(1 for r in other if r.get('icon'))} with an icon)\n"
        + ("\nDungeon journal:\n" + "".join(f"- {line}\n" for line in JOURNAL_NOTE) if JOURNAL_NOTE else ""))
    print(f"{len(items)} items, {len(sets)} sets, {len(items) - no_src} with sources -> {a.out}")


if __name__ == "__main__":
    main()

"""Write the BIS planner's item data for the ForeverScout addon.

Reads gamedata/items.json (the same file the site's planner uses) and writes
addon/ForeverScout_Data/Data.lua: one Lua table per equippable item with the fields the in-game
planner scores and shows (stats, slot, class and side limits, where it comes from).

Usage:
  python3 tools/build_addon_data.py            # writes addon/ForeverScout_Data/Data.lua
  python3 tools/build_addon_data.py --check    # exit 1 if Data.lua is out of date
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "gamedata" / "items.json"
OUT = ROOT / "addon" / "ForeverScout_Data" / "Data.lua"

# Slots the paper doll can hold. Shirts, tabards, ammo and bags are left out.
SLOTS = {"head", "neck", "shoulder", "back", "chest", "wrist", "hands", "waist", "legs", "feet",
         "finger", "trinket", "mainhand", "offhand", "onehand", "twohand", "ranged", "relic",
         "shield", "holdable"}
# Short keys keep the file small; Planner.lua reads these names.
STAT_KEYS = {"str", "agi", "sta", "int", "spi", "armor", "ap", "rap", "crit", "hit", "haste", "sp", "heal",
             "mp5", "hp5", "def", "dodge", "parry", "block", "blockv", "spen", "expertise", "dps",
             "spellcrit", "spellhit", "sp_fire", "sp_frost", "sp_shadow", "sp_nature", "sp_arcane",
             "sp_holy", "fire_res", "frost_res", "shadow_res", "nature_res", "arcane_res",
             "crit_pct", "hit_pct", "spellcrit_pct", "spellhit_pct"}
SRC_KINDS = {"chest", "raid", "dungeon", "pvp", "rep", "quest", "craft", "vendor", "drop", "world", "logged"}
MAX_TEXT = 80
QUESTS = ROOT / "gamedata" / "quests.json"
ZONES = ROOT / "tools" / "zone_sizes.json"

# Quest givers and zone map IDs, so the addon can say where a quest starts and pin it on the map.
_quests = {q["id"]: q for q in json.loads(QUESTS.read_text())} if QUESTS.exists() else {}
_zone_map = {z["name"]: int(mid) for mid, z in json.loads(ZONES.read_text()).items()} if ZONES.exists() else {}


def lua_str(s):
    s = "".join(ch if ch.isprintable() else " " for ch in str(s))[:MAX_TEXT]
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def lua_num(v):
    v = float(v)
    if v.is_integer():
        return str(int(v))
    return repr(round(v, 2))


def ident(s):
    return s if s.replace("_", "a").isalnum() and not s[0].isdigit() else None


def source(s):
    kind = s.get("t")
    if kind not in SRC_KINDS:
        return None
    parts = ["t=" + lua_str(kind)]
    if s.get("n"):
        parts.append("n=" + lua_str(s["n"]))
    if s.get("z"):
        parts.append("z=" + lua_str(s["z"]))
    lv = s.get("lv")
    if isinstance(lv, (int, float)):
        parts.append("lv=" + lua_num(lv))
    elif isinstance(lv, list) and lv and all(isinstance(x, (int, float)) for x in lv):
        parts.append("lv=" + lua_num(lv[0]))
    if isinstance(s.get("ch"), (int, float)) and s["ch"] > 0:
        parts.append("ch=" + lua_num(s["ch"]))
    if s.get("boss"):
        parts.append("boss=1")
    if isinstance(s.get("qid"), int):
        parts.append("qid=%d" % s["qid"])
        q = _quests.get(s["qid"])
        if q:
            if isinstance(q.get("req"), int) and q["req"] > 1:
                parts.append("rq=%d" % q["req"])
            if q.get("pre"):
                parts.append("pre=%d" % len(q["pre"]))
            if q.get("side") in ("A", "H"):
                parts.append("sd=" + lua_str(q["side"]))
            st = q.get("start")
            if isinstance(st, dict) and st.get("n"):
                parts.append("g=" + lua_str(st["n"]))
                if st.get("t") == "object":
                    parts.append("go=1")
                if st.get("z"):
                    parts.append("gz=" + lua_str(st["z"]))
                    if st["z"] in _zone_map and isinstance(st.get("x"), (int, float)) and isinstance(st.get("y"), (int, float)):
                        parts.append("m=%d" % _zone_map[st["z"]])
                        parts.append("x=%s" % lua_num(st["x"]))
                        parts.append("y=%s" % lua_num(st["y"]))
    elif s.get("z") in _zone_map:
        parts.append("m=%d" % _zone_map[s["z"]])
    if isinstance(s.get("qcls"), int):
        parts.append("qcls=%d" % s["qcls"])
    return "{" + ",".join(parts) + "}"


def item_line(it):
    f = []
    f.append("n=" + lua_str(it["name"]))
    f.append("q=%d" % int(it["q"]))
    f.append("il=%d" % int(it["ilvl"]))
    lv = int(it.get("lvl", it.get("req", 0)) or 0)
    f.append("lv=%d" % lv)
    if int(it.get("req") or 0) <= 1 and lv > 1:
        f.append("e=1")  # level estimated from the item level or its source, not a client requirement
    f.append("s=" + lua_str(it["slot"]))
    f.append("ty=" + lua_str(it.get("type") or "misc"))
    f.append("c=%d" % int(it["cls"]))
    if it.get("classes"):
        f.append("cm=%d" % int(it["classes"]))
    if it.get("side") in ("A", "H"):
        f.append("sd=" + lua_str(it["side"]))
    if it.get("weapon"):
        w = it["weapon"]
        f.append("w={%s,%s,%s}" % (lua_num(w.get("min", 0)), lua_num(w.get("max", 0)), lua_num(w.get("speed", 0))))
    if it.get("icon"):
        f.append("i=" + lua_str("".join(ch for ch in it["icon"] if ch.isalnum() or ch in "_-")))
    if it.get("set"):
        f.append("set=%d" % int(it["set"]))
    stats = []
    for k, v in (it.get("stats") or {}).items():
        if k in STAT_KEYS and isinstance(v, (int, float)) and v:
            stats.append("%s=%s" % (k, lua_num(v)))
    f.append("st={" + ",".join(stats) + "}")
    srcs = [x for x in (source(s) for s in it.get("src") or []) if x]
    if srcs:
        f.append("src={" + ",".join(srcs[:4]) + "}")
    fx = [x for x in (it.get("fx") or []) if isinstance(x.get("text"), str) and x["text"]]
    if fx:
        f.append("fx={" + ",".join("{%s,%s}" % (lua_str(x.get("on") or "equip"), lua_str(x["text"])) for x in fx[:3]) + "}")
    return "[%d]={%s}," % (int(it["id"]), ",".join(f))


SIMWEIGHTS = ROOT / "gamedata" / "simweights.json"
SIM_KEYS = {"str", "agi", "sta", "int", "spi", "ap", "rap", "crit", "hit", "haste", "expertise", "sp", "heal",
            "mp5", "spen", "sp_arcane", "sp_fire", "sp_frost", "sp_holy", "sp_nature", "sp_shadow", "def", "dodge",
            "parry", "block", "blockv", "armor", "dps", "dps_oh", "dps_ranged"}


def sim_lines():
    """ForeverScoutData.SIM: the sim-measured stat weights the site uses, filtered the same way
    (site/src/scripts/gear/model.ts simPresets): known keys, finite numbers no larger than 100."""
    if not SIMWEIGHTS.exists():
        return ["ForeverScoutData.SIM = { specs = {} }"]
    d = json.loads(SIMWEIGHTS.read_text())
    src = d.get("source") if isinstance(d.get("source"), dict) else {}
    commit = src.get("commit") if isinstance(src.get("commit"), str) and re.fullmatch(r"[0-9a-f]{7,40}", src.get("commit")) else ""
    out = ["ForeverScoutData.SIM = { commit = %s, specs = {" % lua_str(commit)]
    specs = d.get("specs") if isinstance(d.get("specs"), dict) else {}
    for key in sorted(specs):
        if not re.fullmatch(r"[A-Z]+\.[a-z]+", key) or not isinstance(specs[key], list):
            continue
        presets = []
        for pz in specs[key]:
            if not isinstance(pz, dict) or not isinstance(pz.get("label"), str) or not isinstance(pz.get("w"), dict):
                continue
            w = []
            for k, v in pz["w"].items():
                try:
                    n = float(v)
                except (TypeError, ValueError):
                    continue
                if k in SIM_KEYS and n == n and abs(n) <= 100:
                    w.append("%s=%s" % (k, repr(round(n, 6))))
            if w:
                presets.append("{label=%s,w={%s}}" % (lua_str(pz["label"][:60]), ",".join(w)))
        if presets:
            out.append("[%s]={%s}," % (lua_str(key), ",".join(presets)))
    out.append("} }")
    return out


def build():
    data = json.loads(SRC.read_text())
    items = [it for it in data["items"] if it.get("slot") in SLOTS and int(it.get("q", 0)) >= 1]
    items.sort(key=lambda it: int(it["id"]))
    lines = [
        "-- Generated by tools/build_addon_data.py from gamedata/items.json. Do not edit by hand.",
        "-- Fields: n name, q quality, il item level, lv level needed, s slot, ty type, c item class",
        "-- (2 weapon, 4 armor), e level is an estimate, cm class mask, sd side, w {min,max,speed}, i icon, st stats, src sources, fx effects.",
        "-- Source fields: t kind, n name, z zone, lv level, ch drop %, boss, qid quest, rq quest level needed, pre earlier quests",
        "-- in the chain, sd faction, g quest giver, go giver is an object, gz giver zone, m uiMapID, x y map percent.",
        "-- Loaded on demand by ForeverScout when the BIS planner opens (see ForeverScout_Data.toc).",
        "ForeverScoutData = { BUILD = %s, ITEMS = {}, SETS = {} }" % lua_str(data.get("build", "")),
    ]
    # Lua 5.1 limits each function to 2^18 constants, so the items go in chunks of their own.
    CHUNK = 400
    for i in range(0, len(items), CHUNK):
        lines.append("do local I = ForeverScoutData.ITEMS; (function() local T = {")
        lines.extend(item_line(it) for it in items[i:i + CHUNK])
        lines.append("} for k, v in pairs(T) do I[k] = v end end)() end")
    sets = data.get("sets") or {}
    lines.append("do local S = ForeverScoutData.SETS; (function() local T = {")
    for sid, s in sorted(sets.items(), key=lambda kv: int(kv[0])):
        bon = []
        for b in s.get("bonuses") or []:
            txt = b.get("text") or ", ".join("+%s %s" % (lua_num(v), k) for k, v in (b.get("stats") or {}).items())
            if txt:
                bon.append("{%d,%s}" % (int(b.get("n", 0)), lua_str(txt)))
        lines.append("[%d]={n=%s,b={%s}}," % (int(sid), lua_str(s.get("name", "")), ",".join(bon)))
    lines.append("} for k, v in pairs(T) do S[k] = v end end)() end")
    lines.extend(sim_lines())
    return "\n".join(lines) + "\n", len(items)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    text, n = build()
    if args.check:
        if OUT.exists() and OUT.read_text() == text:
            print("Data.lua is up to date (%d items)" % n)
            return 0
        print("Data.lua is out of date; run tools/build_addon_data.py")
        return 1
    OUT.write_text(text)
    print("wrote %s: %d items, %d KB" % (OUT.relative_to(ROOT), n, len(text) // 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())

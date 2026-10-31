"""Sanity check: every data point the addon carries matches the site's data, field by field.

Compares addon/ForeverScout_Data/Data.lua (loaded under Lua 5.1) with the files the site is built
from: gamedata/items.json (items, stats, sources, sets), gamedata/quests.json (quest givers,
positions, levels, chains), tools/zone_sizes.json (map IDs) and gamedata/simweights.json (stat
weights). Also checks that the addon's WeightsFor() returns the same numbers as the site's
weightsFor() for every class, spec and goal.

  python3 tools/build_addon_data.py
  python3 tools/test/test_addon_data.py          # exit 1 on any mismatch
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import build_addon_data as bad  # noqa: E402

DATA = ROOT / "addon" / "ForeverScout_Data" / "Data.lua"
PLANNER = ROOT / "addon" / "ForeverScout" / "Planner.lua"

problems = []
checked = {"items": 0, "fields": 0, "sources": 0, "quests": 0, "sets": 0, "sim": 0, "weights": 0}


def bad_(msg):
    problems.append(msg)


def lua_to_py(v):
    """Lua table -> dict/list, recursively."""
    from lupa import lua51
    if not isinstance(v, (int, float, str, bool)) and v is not None and lua51.lua_type(v) == "table":
        keys = list(v.keys())
        if keys and all(isinstance(k, int) for k in keys) and sorted(keys) == list(range(1, len(keys) + 1)):
            return [lua_to_py(v[k]) for k in range(1, len(keys) + 1)]
        return {k: lua_to_py(v[k]) for k in keys}
    return v


def load_addon():
    from lupa import lua51
    L = lua51.LuaRuntime()
    boot = L.eval("""function(data, planner)
      local ns = {}
      assert(loadstring(data, "Data.lua"))("ForeverScout_Data", {})
      assert(loadstring(planner, "Planner.lua"))("ForeverScout", ns)
      assert(ns.Planner.LoadData())
      return ForeverScoutData, ns.Planner
    end""")
    return boot(DATA.read_text(), PLANNER.read_text())


def num_eq(a, b, tol=1e-6):
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return a == b


def check_items(addon, items, quests, zone_map):
    addon_items = addon.ITEMS
    site = {it["id"]: it for it in items if it.get("slot") in bad.SLOTS and int(it.get("q", 0)) >= 1}
    addon_ids = set(addon_items.keys())
    for iid in sorted(set(site) - addon_ids):
        bad_(f"item {iid} {site[iid]['name']!r} is on the site but missing from the addon")
    for iid in sorted(addon_ids - set(site)):
        bad_(f"item {iid} is in the addon but not an equippable site item")
    for iid, it in site.items():
        a = addon_items[iid] if iid in addon_ids else None
        if a is None:
            continue
        checked["items"] += 1
        a = lua_to_py(a)
        exp = {
            "n": bad.lua_str(it["name"])[1:-1].replace('\\"', '"').replace("\\\\", "\\"),
            "q": int(it["q"]), "il": int(it["ilvl"]), "lv": int(it.get("lvl", it.get("req", 0)) or 0),
            "s": it["slot"], "ty": it.get("type") or "misc", "c": int(it["cls"]),
            "cm": int(it["classes"]) if it.get("classes") else None,
            "sd": it["side"] if it.get("side") in ("A", "H") else None,
            "set": int(it["set"]) if it.get("set") else None,
            "i": "".join(ch for ch in it["icon"] if ch.isalnum() or ch in "_-") if it.get("icon") else None,
            "e": 1 if int(it.get("req") or 0) <= 1 and int(it.get("lvl") or 0) > 1 else None,
        }
        for k, v in exp.items():
            checked["fields"] += 1
            got = a.get(k)
            if v is None and got is None:
                continue
            if isinstance(v, (int, float)) and got is not None and num_eq(v, got):
                continue
            if v != got:
                bad_(f"item {iid} {it['name']!r}: {k} site={v!r} addon={got!r}")
        # weapon
        w = it.get("weapon")
        if w:
            aw = a.get("w") or []
            if len(aw) != 3 or not all(num_eq(x, y, 0.01) for x, y in zip(aw, [w.get("min", 0), w.get("max", 0), w.get("speed", 0)])):
                bad_(f"item {iid} {it['name']!r}: weapon site={w} addon={aw}")
        elif a.get("w"):
            bad_(f"item {iid} {it['name']!r}: addon has a weapon the site lacks")
        # stats
        st_site = {k: v for k, v in (it.get("stats") or {}).items() if k in bad.STAT_KEYS and isinstance(v, (int, float)) and v}
        st_addon = a.get("st") or {}
        for k in set(st_site) | set(st_addon):
            checked["fields"] += 1
            if k not in st_site or k not in st_addon or not num_eq(st_site[k], st_addon[k], 0.006):
                bad_(f"item {iid} {it['name']!r}: stat {k} site={st_site.get(k)} addon={st_addon.get(k)}")
        # effects
        fx_site = [x for x in (it.get("fx") or []) if isinstance(x.get("text"), str) and x["text"]][:3]
        fx_addon = a.get("fx") or []
        if len(fx_site) != len(fx_addon):
            bad_(f"item {iid} {it['name']!r}: {len(fx_site)} effects on the site, {len(fx_addon)} in the addon")
        # sources
        src_site = [s for s in (it.get("src") or []) if s.get("t") in bad.SRC_KINDS][:4]
        src_addon = a.get("src") or []
        if len(src_site) != len(src_addon):
            bad_(f"item {iid} {it['name']!r}: {len(src_site)} sources on the site, {len(src_addon)} in the addon")
            continue
        for s, sa in zip(src_site, src_addon):
            checked["sources"] += 1
            for k in ("t", "n", "z"):
                v = s.get(k)
                if isinstance(v, str):
                    v = v[: bad.MAX_TEXT]
                if (v or None) != (sa.get(k) or None):
                    bad_(f"item {iid} {it['name']!r}: source {k} site={v!r} addon={sa.get(k)!r}")
            lv = s.get("lv")
            lv = lv[0] if isinstance(lv, list) and lv else lv
            if isinstance(lv, (int, float)) and not num_eq(lv, sa.get("lv")):
                bad_(f"item {iid} {it['name']!r}: source level site={lv} addon={sa.get('lv')}")
            if isinstance(s.get("ch"), (int, float)) and s["ch"] > 0 and not num_eq(s["ch"], sa.get("ch"), 0.006):
                bad_(f"item {iid} {it['name']!r}: drop chance site={s['ch']} addon={sa.get('ch')}")
            if bool(s.get("boss")) != bool(sa.get("boss")):
                bad_(f"item {iid} {it['name']!r}: boss flag site={s.get('boss')} addon={sa.get('boss')}")
            if isinstance(s.get("qid"), int):
                if sa.get("qid") != s["qid"]:
                    bad_(f"item {iid} {it['name']!r}: quest id site={s['qid']} addon={sa.get('qid')}")
                q = quests.get(s["qid"])
                if q:
                    checked["quests"] += 1
                    want = {
                        "rq": q["req"] if isinstance(q.get("req"), int) and q["req"] > 1 else None,
                        "pre": len(q["pre"]) if q.get("pre") else None,
                        "sd": q["side"] if q.get("side") in ("A", "H") else None,
                    }
                    stt = q.get("start") if isinstance(q.get("start"), dict) else None
                    if stt and stt.get("n"):
                        want["g"] = stt["n"][: bad.MAX_TEXT]
                        want["gz"] = stt.get("z")[: bad.MAX_TEXT] if stt.get("z") else None
                        if stt.get("z") in zone_map and isinstance(stt.get("x"), (int, float)):
                            want["m"], want["x"], want["y"] = zone_map[stt["z"]], stt["x"], stt["y"]
                    for k, v in want.items():
                        got = sa.get(k)
                        if v is None and got is None:
                            continue
                        if isinstance(v, (int, float)) and got is not None and num_eq(v, got, 0.06):
                            continue
                        if v != got:
                            bad_(f"item {iid} {it['name']!r}: quest {s['qid']} {k} site={v!r} addon={got!r}")


def check_sets(addon, sets):
    a_sets = lua_to_py(addon.SETS)
    for sid, s in sets.items():
        checked["sets"] += 1
        a = a_sets.get(int(sid))
        if not a:
            bad_(f"set {sid} {s.get('name')!r} missing from the addon")
            continue
        if a.get("n") != s.get("name", "")[: bad.MAX_TEXT]:
            bad_(f"set {sid}: name site={s.get('name')!r} addon={a.get('n')!r}")
        want = [b for b in (s.get("bonuses") or []) if b.get("text") or b.get("stats")]
        if len(want) != len(a.get("b") or []):
            bad_(f"set {sid} {s.get('name')!r}: {len(want)} bonuses on the site, {len(a.get('b') or [])} in the addon")


def check_sim(addon, simweights):
    a = lua_to_py(addon.SIM)
    specs = simweights.get("specs") or {}
    for key, presets in specs.items():
        checked["sim"] += 1
        ap = (a.get("specs") or {}).get(key)
        if not ap:
            bad_(f"sim weights for {key} missing from the addon")
            continue
        if len(ap) != len(presets):
            bad_(f"sim {key}: {len(presets)} presets on the site, {len(ap)} in the addon")
            continue
        for p, q in zip(presets, ap):
            for k, v in p["w"].items():
                if k in bad.SIM_KEYS and abs(float(v)) <= 100 and not num_eq(v, q["w"].get(k), 1e-5):
                    bad_(f"sim {key} {p['label']!r}: {k} site={v} addon={q['w'].get(k)}")


def check_weights(planner):
    """Site weightsFor vs addon WeightsFor, every class/spec/goal."""
    out = subprocess.run(["node", "--experimental-strip-types", "--no-warnings", "--import", str(ROOT / "tools/test/node-json-hook.mjs"), str(ROOT / "tools/test/weights_ref.ts")],
                         check=True, capture_output=True, text=True, cwd=ROOT)
    ref = json.loads(out.stdout)
    for key, w in ref.items():
        cls, spec, goal = key.split("|")
        got = lua_to_py(planner.WeightsFor(cls, spec, goal))
        checked["weights"] += 1
        for k in set(w) | set(got):
            if not num_eq(w.get(k, 0), got.get(k, 0), 1e-6):
                bad_(f"weights {key}: {k} site={w.get(k)} addon={got.get(k)}")


def main():
    text, _ = bad.build()
    if DATA.read_text() != text:
        bad_("Data.lua is stale: run tools/build_addon_data.py")
    items = json.loads((ROOT / "gamedata/items.json").read_text())
    quests = {q["id"]: q for q in json.loads((ROOT / "gamedata/quests.json").read_text())}
    zone_map = {z["name"]: int(mid) for mid, z in json.loads((ROOT / "tools/zone_sizes.json").read_text()).items()}
    sim = json.loads((ROOT / "gamedata/simweights.json").read_text()) if (ROOT / "gamedata/simweights.json").exists() else {}
    addon, planner = load_addon()
    check_items(addon, items["items"], quests, zone_map)
    check_sets(addon, items.get("sets") or {})
    check_sim(addon, sim)
    check_weights(planner)
    print("checked: " + ", ".join(f"{v} {k}" for k, v in checked.items()))
    if problems:
        for p in problems[:40]:
            print("MISMATCH " + p)
        if len(problems) > 40:
            print(f"... and {len(problems) - 40} more")
        print(f"{len(problems)} mismatches")
        return 1
    print("addon data matches the site")
    return 0


if __name__ == "__main__":
    sys.exit(main())

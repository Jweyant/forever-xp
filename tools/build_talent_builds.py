"""Build gamedata/talent-builds.json: recommended talent builds per class, from two sources.

  - ours: the builds our own stat-weight sims run (gamedata/simconfigs/), PvE.
  - wowsims: the preset builds wowsims/forever (MIT) ships per spec, PvE. Read from the pinned
    checkout the sim-weights workflow already makes, so the presets only change with the pin.

Build strings are one digit per talent in tree order, trees joined by "-": the same format as the
site's talent calculator hash and the sim configs, and tools/check_talent_order.py guards that the
order means the same talents to us and to wowsims. Player-measured popularity is separate
(tools/ingest_logs.py -> gamedata/players/talent_builds.json).

Usage:
  python3 -I tools/build_talent_builds.py --simconfigs gamedata/simconfigs --wowsims ext/wowsims \
      --out gamedata/talent-builds.json
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_talent_order  # noqa: E402  (shared talent-order machinery)
import luadata  # noqa: E402  (tools/luadata.py: safe Lua-literal parser, no code execution)

BUILD_RE = re.compile(r"^[0-5]{0,30}(-[0-5]{0,30}){0,2}$")
# Spec shorthands in wowsims file names, shown upper case.
SHORT = {"sv": "SV", "mm": "MM", "bm": "BM", "apl": "APL", "aoe": "AoE"}


def valid(s):
    """A canonical build string: digits 0-5 per tree, no trailing dash, at most 60 points."""
    return (isinstance(s, str) and 0 < len(s.replace("-", "")) and not s.endswith("-")
            and BUILD_RE.fullmatch(s) and sum(int(d) for d in s if d.isdigit()) <= 60)


def pretty(stem):
    return " ".join(SHORT.get(w, w.capitalize()) for w in stem.replace(".build", "").split("_"))


def talents_in(path):
    """The talents string in a sim setup: .siml (talents "...") or wowsims .build.json (talentsString)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.name.endswith(".build.json"):
        try:
            v = json.loads(text).get("player", {}).get("talentsString") or json.loads(text).get("talentsString")
        except (json.JSONDecodeError, AttributeError):
            return None
        return v if isinstance(v, str) else None
    m = re.search(r'^talents\s+"([0-9-]*)"', text, re.M)
    return m.group(1) if m else None


def canon(t):
    return t.rstrip("-") if isinstance(t, str) else t


def ours(simconfigs):
    """Per class slug: the builds our sim runs use, with their labels and notes."""
    root = Path(simconfigs)
    out = {}
    idx = root / "index.json"
    if not idx.exists():
        return out
    for c in json.loads(idx.read_text()):
        f = root / str(c.get("file", ""))
        slug = str(c.get("specDir", "")).split("/")[0].lower()
        if not f.is_file() or f.parent != root or not re.fullmatch(r"[a-z]+", slug):
            continue
        t = canon(talents_in(f))
        if valid(t):
            out.setdefault(slug, []).append({"n": str(c.get("label", f.stem))[:60], "t": t,
                                             "note": str(c.get("note", ""))[:300]})
    return out


# A talent preset defined inline in a spec's presets.ts, in either spelling:
#   makePresetTalents('Name', SavedTalents.create({ talentsString: '...' }))
#   { name: 'Name', data: SavedTalents.create({ talentsString: '...' }) }
PRESET_RE = re.compile(r"(?:makePresetTalents\(\s*|name:\s*)['\"]([^'\"]{1,60})['\"],(?:\s*data:)?\s*"
                       r"SavedTalents\.create\(\{[^}]{0,120}?talentsString:\s*['\"]([0-9-]{1,100})['\"]", re.S)


def tree_ranks(talents_json):
    """Class slug -> per tree, each talent's max rank, in build-string order."""
    g = json.loads(Path(talents_json).read_text())
    return {name.lower(): [[t[4] for t in tals] for _, _, _, tals in trees] for _, name, trees in g["talents"]}


def fits(build, ranks):
    """Whether a build string fits a class's current trees: no digit past a talent's max rank or a
    tree's length. Catches presets written against an older tree after a patch reshuffles it."""
    for ti, part in enumerate(build.split("-")):
        if ti >= len(ranks) or len(part) > len(ranks[ti]):
            return False
        if any(int(d) > ranks[ti][k] for k, d in enumerate(part)):
            return False
    return True


def ok_for(slug, build, moved, ranks):
    """A preset passes when it has no points where our order and the engine's disagree, and it
    fits our current rank caps. With no gate data (tests, no --talents), everything passes."""
    diffs = moved.get(slug)
    if diffs is not None:
        parts = build.split("-")
        for ti, k in diffs:
            if ti < len(parts) and k < len(parts[ti]) and parts[ti][k] != "0":
                return False
    return fits(build, ranks[slug]) if slug in ranks else True


def wowsims(checkout, talents_json=None):
    """Per class slug: every preset build, from ui/specs/<class>/<spec>/builds/ files (named after
    the file) and the makePresetTalents(...) presets defined inline in each spec's presets.ts.

    Preset strings are written in the pinned engine's talent order. With `talents_json` given, a
    preset is dropped when it puts points anywhere our current order disagrees with the engine's
    (a patch moved talents and wowsims hasn't caught up), or when it no longer fits our trees'
    rank caps — so a reshuffled tree can't mislabel a build."""
    out = {}
    base = Path(checkout) / "ui" / "specs"
    if not base.exists():
        return out
    moved, ranks = {}, {}
    if talents_json:
        ranks = tree_ranks(talents_json)
        for cname, trees in check_talent_order.ours(talents_json).items():
            eng = check_talent_order.engine(checkout, cname)
            if eng is not None:
                moved[cname.lower()] = check_talent_order.differences(trees, eng)
    for f in sorted(base.glob("*/*/presets.ts")):
        slug, spec = (s.lower() for s in f.relative_to(base).parts[:2])
        if not re.fullmatch(r"[a-z]+", slug):
            continue
        for name, raw in PRESET_RE.findall(f.read_text(encoding="utf-8", errors="replace")):
            tal = canon(raw)
            if "test" in name.lower() or not valid(tal):
                continue
            rec = {"n": name[:60], "t": tal}
            if spec != "dps":
                rec["spec"] = spec[:20]
            lst = out.setdefault(slug, [])
            if ok_for(slug, tal, moved, ranks) and not any(x["t"] == tal for x in lst):
                lst.append(rec)
    for f in sorted(base.glob("*/*/builds/*")):
        if f.suffix not in (".siml", ".json") or not f.is_file() or "test" in f.stem.lower():
            continue  # wowsims' own testing setups aren't recommendations
        slug = f.relative_to(base).parts[0].lower()
        t = canon(talents_in(f))
        if re.fullmatch(r"[a-z]+", slug) and valid(t):
            rec = {"n": pretty(f.stem)[:60], "t": t}
            spec = f.relative_to(base).parts[1].lower()
            if spec not in ("dps",):  # healer, protection... worth naming; dps is the default read
                rec["spec"] = spec[:20]
            lst = out.setdefault(slug, [])
            if ok_for(slug, t, moved, ranks) and not any(x["t"] == t for x in lst):
                lst.append(rec)
    return {k: v for k, v in out.items() if v}


CLASS_TOKEN = {"WARRIOR": "warrior", "PALADIN": "paladin", "HUNTER": "hunter", "ROGUE": "rogue",
               "PRIEST": "priest", "SHAMAN": "shaman", "MAGE": "mage", "WARLOCK": "warlock", "DRUID": "druid"}


def _lua_list(v):
    """luadata turns Lua arrays into lists or {1: ..} maps; give back a plain list."""
    if isinstance(v, dict):
        return [v[k] for k in sorted((k for k in v if isinstance(k, int)), key=int)]
    return v if isinstance(v, list) else []


def community(path, talents_json):
    """Per class slug: the "Endgame PvP" builds from the WoW Forever Builds addon (MIT), decoded
    into our build strings. Its Guides.lua lists each class's trees as {name, row, col, maxRank}
    in the same row-then-column order our client data uses, and each guide's `order` holds two
    characters per point: the tree (0-2) and the talent's index in that tree, base 36.

    A class's builds are imported ONLY when its trees match our client data exactly (same names,
    positions and ranks, in order) — on any drift the indexes could point at the wrong talent, so
    the whole class is skipped until the addon regenerates."""
    src = Path(path) / "Guides.lua"
    if not src.exists():
        return {}
    text = src.read_text(encoding="utf-8", errors="replace")
    try:
        their = luadata.loads_value(text[text.index("ns.talents =") + 12:text.index("ns.guides =")].strip())
        guides = luadata.loads_value(text[text.index("ns.guides =") + 11:].strip().rstrip())
    except (ValueError, luadata.LuaDataError):
        return {}
    ours_trees = {name: trees for _, name, trees in json.loads(Path(talents_json).read_text())["talents"]}
    ok = {}  # class token -> [per tree: [maxRank per talent]] for matched classes
    for cname, trees in ours_trees.items():
        token = next((k for k, v in CLASS_TOKEN.items() if v == cname.lower()), None)
        th = _lua_list(their.get(token)) if isinstance(their, dict) else None
        if not th or len(th) != len(trees):
            continue
        ranks, match = [], True
        for i, (_, tname, _, tals) in enumerate(trees):
            tt = th[i] if isinstance(th[i], dict) else {}
            rows = [_lua_list(x) for x in _lua_list(tt)]
            if tt.get("name") != tname or [(t[3], t[1], t[2], t[4]) for t in tals] != [tuple(x[:4]) for x in rows]:
                match = False
                break
            ranks.append([t[4] for t in tals])
        if match:
            ok[token] = ranks
    out = {}
    pairs = [(tok, g) for tok, lst in (guides.items() if isinstance(guides, dict) else []) if isinstance(tok, str)
             for g in _lua_list(lst) if isinstance(g, dict)]
    for token, g in pairs:
        if g.get("kind") != "Endgame PvP":
            continue
        order, spec, title = str(g.get("order", "")), str(g.get("spec", ""))[:30], str(g.get("title", ""))
        if token not in ok or token not in CLASS_TOKEN or not re.fullmatch(r"[0-9a-z]{2,120}", order) or len(order) % 2:
            continue
        ranks = ok[token]
        pts = [[0] * len(r) for r in ranks]
        good = True
        for a, b in zip(order[::2], order[1::2]):
            tree, idx = int(a, 36), int(b, 36)
            if tree >= len(pts) or idx >= len(pts[tree]) or pts[tree][idx] >= ranks[tree][idx]:
                good = False
                break
            pts[tree][idx] += 1
        if not good:
            continue
        t = canon("-".join("".join(str(n) for n in p).rstrip("0") for p in pts))
        if not valid(t):
            continue
        note = title.split(": ", 1)[1][:120] if ": " in title else ""
        rec = {"n": f"{spec} PvP", "t": t, **({"note": note} if note else {})}
        lst = out.setdefault(CLASS_TOKEN[token], [])
        if not any(x["t"] == t for x in lst):
            lst.append(rec)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--simconfigs", default="gamedata/simconfigs")
    ap.add_argument("--wowsims", required=True, help="pinned wowsims/forever checkout")
    ap.add_argument("--community", help="pinned Boco10/WoWForeverBuilds-Addon checkout, for its PvP builds")
    ap.add_argument("--talents", default="gamedata/talents.json", help="our client talent data, the match gate for --community")
    ap.add_argument("--out", default="gamedata/talent-builds.json")
    a = ap.parse_args()
    classes = {}
    for slug, lst in ours(a.simconfigs).items():
        classes.setdefault(slug, {})["ours"] = lst
    for slug, lst in wowsims(a.wowsims, a.talents if Path(a.talents).exists() else None).items():
        classes.setdefault(slug, {})["wowsims"] = lst
    if a.community:
        for slug, lst in community(a.community, a.talents).items():
            classes.setdefault(slug, {})["community"] = lst
    out = {"source": {"name": "wowsims/forever presets and forever-xp sim setups",
                      "url": "https://github.com/wowsims/forever", "license": "MIT"},
           "classes": classes}
    Path(a.out).write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False, sort_keys=True))
    n = sum(len(v) for c in classes.values() for v in c.values())
    print(f"{n} builds for {len(classes)} classes -> {a.out}")
    if not classes:
        sys.exit("no builds found; wrong --wowsims path?")


if __name__ == "__main__":
    main()

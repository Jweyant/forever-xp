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


def wowsims(checkout):
    """Per class slug: every preset build, from ui/specs/<class>/<spec>/builds/ files (named after
    the file) and the makePresetTalents(...) presets defined inline in each spec's presets.ts."""
    out = {}
    base = Path(checkout) / "ui" / "specs"
    if not base.exists():
        return out
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
            if not any(x["t"] == tal for x in lst):
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
            if not any(x["t"] == t for x in lst):
                lst.append(rec)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--simconfigs", default="gamedata/simconfigs")
    ap.add_argument("--wowsims", required=True, help="pinned wowsims/forever checkout")
    ap.add_argument("--out", default="gamedata/talent-builds.json")
    a = ap.parse_args()
    classes = {}
    for slug, lst in ours(a.simconfigs).items():
        classes.setdefault(slug, {})["ours"] = lst
    for slug, lst in wowsims(a.wowsims).items():
        classes.setdefault(slug, {})["wowsims"] = lst
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

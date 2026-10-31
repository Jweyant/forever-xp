"""Stat weights for the BIS planner, from wowsims/forever's published presets.

wowsims/forever (https://github.com/wowsims/forever, MIT) is a Forever-native combat simulator. Its
spec UIs ship stat weights (EP) measured with the sim, each with the gear and talents it was measured
on (`PresetUtils.makePresetEpWeights(...)` in ui/specs/<class>/<spec>/presets.ts). This tool reads
those files AS TEXT from a checkout pinned to one commit: nothing from that repository is executed.
Everything taken from it is third-party data, so:
  - only the spec presets named in SPEC_MAP are used (an allow-list keyed by folder and label);
  - only the stats in STAT_MAP are kept, and only plain number literals within BOUNDS;
  - labels and notes are short plain text, shown on the site with textContent.

Usage:
  python3 tools/build_simweights.py --wowsims ext/wowsims --commit <40-hex sha> --out gamedata/simweights.json
"""
import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path

REPO = "https://github.com/wowsims/forever"
SITE = "https://wowsims.com/forever"

# (spec folder, preset label) -> our "CLASS.spec" key. Listed in preference order: the first preset for
# a spec is its default (the same one wowsims' spec page loads by default where it sets one).
# Not mapped on purpose: shaman/elemental "Testing" (its label says it's not settled) and priest/dps
# "Smite" (no matching spec here).
SPEC_MAP = [
    (("warrior/dps", "Pre-BiS - Fury"), "WARRIOR.fury"),
    (("warrior/dps", "Pre-BiS - Arms"), "WARRIOR.arms"),
    (("warrior/protection", "Pre-BiS (Defense Cap)"), "WARRIOR.prot"),
    (("warrior/protection", "Pre-BiS (Threat)"), "WARRIOR.prot"),
    (("paladin/retribution", "Twist of Light"), "PALADIN.ret"),
    (("paladin/retribution", "Holy Shock"), "PALADIN.ret"),
    (("priest/dps", "Shadow"), "PRIEST.shadow"),
    (("priest/healer", "Holy Raid Healing"), "PRIEST.holy"),
    (("priest/healer", "Holy Single-Target"), "PRIEST.holy"),
    (("priest/healer", "Disc Raid Healing"), "PRIEST.disc"),
    (("priest/healer", "Disc Single-Target"), "PRIEST.disc"),
    (("rogue/dps", "Assassination"), "ROGUE.assa"),
    (("rogue/dps", "Combat Sinister"), "ROGUE.combat"),
    (("rogue/dps", "Combat Daggers"), "ROGUE.combat"),
    (("rogue/dps", "Subtlety"), "ROGUE.sub"),
    (("shaman/enhancement", "Pre-BiS"), "SHAMAN.enh"),
    (("druid/balance", "P1"), "DRUID.balance"),
    (("druid/balance", "Pre-BiS"), "DRUID.balance"),
    (("druid/feralcat", "Cat"), "DRUID.cat"),
    (("druid/feralbear", "Bear"), "DRUID.bear"),
]
# The feral "Hybrid" presets are computed in TypeScript (the average of Cat and Bear), not written as
# numbers, so they can't be read as data; Cat and Bear cover the two specs.

# wowsims stat -> the planner's stat key. Everything else is dropped (and listed in the report):
# stats Forever items in our database don't carry (armor penetration, feral attack power, physical
# damage) and pseudo-stats we don't model yet.
STAT_MAP = {
    "StatStrength": "str", "StatAgility": "agi", "StatStamina": "sta", "StatIntellect": "int",
    "StatSpirit": "spi", "StatAttackPower": "ap", "StatRangedAttackPower": "rap",
    "StatHitRating": "hit", "StatCritRating": "crit", "StatHasteRating": "haste",
    "StatExpertiseRating": "expertise", "StatSpellDamage": "sp", "StatHealingPower": "heal",
    "StatMP5": "mp5", "StatSpellPiercing": "spen",
    "StatArcaneDamage": "sp_arcane", "StatFireDamage": "sp_fire", "StatFrostDamage": "sp_frost",
    "StatHolyDamage": "sp_holy", "StatNatureDamage": "sp_nature", "StatShadowDamage": "sp_shadow",
    "StatDefenseRating": "def", "StatDodgeRating": "dodge", "StatParryRating": "parry",
    "StatBlockRating": "block", "StatBlockValue": "blockv", "StatArmor": "armor",
    "PseudoStatMainHandDps": "dps", "PseudoStatOffHandDps": "dps_oh", "PseudoStatRangedDps": "dps_ranged",
}
BOUNDS = (-5.0, 100.0)
NUMBER = re.compile(r"-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
ENTRY = re.compile(r"\[(?:Stat|PseudoStat)\.([A-Za-z0-9_]+)\]\s*:\s*([^,\n}]+)")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def call_body(text, start):
    """Text between the '(' at `start` and its matching ')', skipping strings and comments."""
    depth, i, n = 0, start, len(text)
    while i < n:
        c = text[i]
        if c in "'\"`":
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if text[j] == "\\" else 1
            i = j + 1
            continue
        if text.startswith("//", i):
            i = text.find("\n", i)
            i = n if i < 0 else i
            continue
        if text.startswith("/*", i):
            i = text.find("*/", i + 2)
            i = n if i < 0 else i + 2
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[start + 1:i]
        i += 1
    return None


def strip_comments(s):
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.S)
    return re.sub(r"//[^\n]*", "", s)


def entries(body, skipped):
    """[Stat.X]: <number literal> pairs from a Stats.fromMap(...) body -> {our key: value}."""
    out = {}
    for name, raw in ENTRY.findall(strip_comments(body)):
        raw = raw.strip()
        key = STAT_MAP.get(name)
        if key is None:
            skipped[name] = skipped.get(name, 0) + 1
            continue
        if not NUMBER.fullmatch(raw):
            skipped[f"{name} (not a plain number)"] = skipped.get(f"{name} (not a plain number)", 0) + 1
            continue
        v = float(raw)
        if not math.isfinite(v) or not BOUNDS[0] <= v <= BOUNDS[1]:
            skipped[f"{name} (out of bounds)"] = skipped.get(f"{name} (out of bounds)", 0) + 1
            continue
        out[key] = round(v, 4)
    return out


def leading_comment(text, pos):
    """The // comment lines right above the statement that starts at `pos`, as one short line."""
    line_start = text.rfind("\n", 0, pos) + 1
    lines = text[:line_start].rstrip("\n").split("\n")
    got = []
    while lines and lines[-1].strip().startswith("//"):
        got.append(lines.pop().strip()[2:].strip())
    note = " ".join(reversed(got))
    note = re.sub(r"[\x00-\x1f\x7f<>]", "", note)
    return note[:300]


def resolve_stats(path, ident, root, depth=0):
    """Find `const <ident> = Stats.fromMap(...)` (or an alias of it) in `path` or a file it imports."""
    if depth > 3 or not IDENT.match(ident):
        return None, ""
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(rf"(?:export\s+)?const\s+{ident}\s*=\s*Stats\.fromMap\(", text)
    if m:
        return call_body(text, m.end() - 1), leading_comment(text, m.start())
    m = re.search(rf"(?:export\s+)?const\s+{ident}\s*=\s*([A-Za-z_][A-Za-z0-9_]*)\s*;", text)
    if m:
        return resolve_stats(path, m.group(1), root, depth + 1)
    for names, rel in re.findall(r"import\s*\{([^}]*)\}\s*from\s*'(\.[^']*)'", text):
        if ident in [x.strip().split(" as ")[0] for x in names.split(",")]:
            target = (path.parent / (rel + ".ts")).resolve()
            if root.resolve() in target.parents and target.is_file():
                return resolve_stats(target, ident, root, depth + 1)
    return None, ""


def presets_in(path, root):
    """[(label, body, note)] for every makePresetEpWeights call in a presets.ts file."""
    text = path.read_text(encoding="utf-8", errors="replace")
    found = []
    for m in re.finditer(r"makePresetEpWeights\(", text):
        body = call_body(text, m.end() - 1)
        if body is None:
            continue
        lm = re.match(r"\s*(['\"])(.{1,60}?)\1\s*,\s*", body)
        if not lm:
            continue
        label, rest = lm.group(2), body[lm.end():]
        stmt = text.rfind("export const", 0, m.start())
        note = leading_comment(text, stmt) if stmt >= 0 else ""
        sm = re.match(r"Stats\.fromMap\(", rest)
        if sm:
            stats_body = call_body(rest, sm.end() - 1)
        else:
            im = re.match(r"([A-Za-z_][A-Za-z0-9_]*)", rest)
            stats_body, ref_note = resolve_stats(path, im.group(1), root) if im else (None, "")
            note = note or ref_note
        if stats_body:
            found.append((label, stats_body, note))
    return found


def build(wowsims, commit):
    specs_dir = Path(wowsims) / "ui" / "specs"
    wanted = {key: spec for key, spec in SPEC_MAP}
    specs, skipped_stats, unmapped, seen = {}, {}, [], set()
    for path in sorted(specs_dir.glob("*/*/presets.ts")):
        folder = f"{path.parent.parent.name}/{path.parent.name}"
        for label, body, note in presets_in(path, specs_dir):
            key = (folder, label)
            if key not in wanted:
                unmapped.append(f"{folder}: {label}")
                continue
            w = entries(body, skipped_stats)
            if not w:
                continue
            seen.add(key)
            specs.setdefault(wanted[key], []).append((key, {"label": label, "w": w, "note": note}))
    order = {key: i for i, (key, _) in enumerate(SPEC_MAP)}
    out_specs = {s: [p for _, p in sorted(v, key=lambda kv: order[kv[0]])] for s, v in sorted(specs.items())}
    missing = [f"{f}: {l}" for (f, l), _ in SPEC_MAP if (f, l) not in seen]
    return {
        "source": {"name": "wowsims/forever", "url": REPO, "site": SITE, "commit": commit, "license": "MIT"},
        "specs": out_specs,
        "report": {"specs": len(out_specs), "presets": sum(len(v) for v in out_specs.values()),
                   "missing": missing, "unmapped": unmapped, "skipped_stats": dict(sorted(skipped_stats.items()))},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wowsims", required=True, help="checkout of wowsims/forever at --commit")
    ap.add_argument("--commit", required=True, help="the pinned 40-hex commit the checkout must be at")
    ap.add_argument("--out", default="gamedata/simweights.json")
    a = ap.parse_args()
    if not COMMIT.match(a.commit):
        raise SystemExit("--commit must be a full 40-character commit SHA")
    head = subprocess.run(["git", "-C", a.wowsims, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    if head != a.commit:
        raise SystemExit(f"checkout is at {head or '?'}, not the pinned {a.commit}")
    data = build(a.wowsims, a.commit)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    r = data["report"]
    print(f"{r['presets']} presets for {r['specs']} specs -> {a.out}")
    for k in ("missing", "unmapped"):
        if r[k]:
            print(f"{k}: " + "; ".join(r[k]))
    if r["skipped_stats"]:
        print("skipped stats: " + ", ".join(f"{k} x{v}" for k, v in r["skipped_stats"].items()))
    if r["missing"]:
        print("warning: some mapped presets were not found; check SPEC_MAP against the pinned commit", file=sys.stderr)


if __name__ == "__main__":
    main()

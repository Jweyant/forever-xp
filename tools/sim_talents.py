"""Our sim setups' talents, kept by name so a talent-tree change can't silently break them.

gamedata/simconfigs/index.json gives each setup its build as talent names and points, per tree:

    "talents": {"Arms": {"Improved Heroic Strike": 3, "Mortal Strike": 1}, "Fury": {"Cruelty": 5}}

The `talents "..."` line in the .siml file is that build written in the current tree order. When
Blizzard moves, adds or re-ranks talents, the same names give a new string:

    --check   exit 1 if any .siml line differs from its names (the offline tests run this)
    --write   rewrite the .siml lines from the names (the Sim weights workflow runs this before the sims)

A talent that lost ranks keeps as many points as it still has; one that left the game drops out.
Either way the run says how many points were left unspent. A build that no longer works (a talent
without the points above it that its row needs) is an error, so the sims don't publish weights for a
build nobody can make.

    python3 -I tools/sim_talents.py gamedata/simconfigs gamedata/talents.json [more.json ...] [--check|--write]

Given more than one talents file it uses the one from the newest Forever client build.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_talent_order  # noqa: E402

TALENTS_LINE = re.compile(r'^talents "([0-9-]*)"$', re.M)
MAX_POINTS = 51


def class_trees(talents_json):
    """Class name -> [(tree name, [(talent name, max ranks, row), ...]), ...] in build-string order."""
    g = json.loads(Path(talents_json).read_text())
    return {name: [(tname, [(t[3], t[4], t[1]) for t in tals]) for _, tname, _, tals in trees]
            for _, name, trees in g["talents"]}


def decode(trees, build):
    """A build string -> {tree name: {talent name: points}} (the inverse of encode)."""
    out = {}
    for (tname, tals), part in zip(trees, build.split("-")):
        picks = {tals[k][0]: int(ch) for k, ch in enumerate(part) if k < len(tals) and ch != "0"}
        if picks:
            out[tname] = picks
    return out


def encode(trees, picks):
    """{tree: {talent: points}} -> (build string, notes, errors) for these trees."""
    notes, errors, parts = [], [], []
    known = {tname for tname, _ in trees}
    for tname in picks:
        if tname not in known:
            errors.append(f"{tname}: no tree with that name")
    spent_total = 0
    for tname, tals in trees:
        want = dict(picks.get(tname, {}))
        digits, by_row = [], {}
        for name, ranks, row in tals:
            pts = int(want.pop(name, 0))
            if pts > ranks:
                notes.append(f"{tname}/{name}: {pts} points but it has {ranks} ranks now; {pts - ranks} left unspent")
                pts = ranks
            digits.append(str(pts))
            if pts:
                by_row[row] = by_row.get(row, 0) + pts
        for name, pts in want.items():
            notes.append(f"{tname}/{name}: no longer in the tree; {pts} point{'s' if pts != 1 else ''} left unspent")
        above = 0
        for row in sorted(by_row):
            if above < 5 * row:
                errors.append(f"{tname}: row {row + 1} needs {5 * row} points above it, the build has {above}")
            above += by_row[row]
        spent_total += above
        parts.append("".join(digits).rstrip("0"))
    if spent_total > MAX_POINTS:
        errors.append(f"{spent_total} points, more than {MAX_POINTS}")
    return "-".join(parts).rstrip("-"), notes, errors


def run(configs, talents_files, mode):
    """Check or rewrite every setup's talents line. Returns (problems, messages)."""
    talents = check_talent_order.newest(talents_files)
    trees = class_trees(talents)
    index = json.loads((Path(configs) / "index.json").read_text())
    problems, messages = [], []
    for e in index:
        if "talents" not in e:
            problems.append(f"{e['file']}: no talents by name in index.json")
            continue
        cls = e["key"].split(".")[0].capitalize()
        if cls not in trees:
            problems.append(f"{e['file']}: no {cls} trees in {talents}")
            continue
        build, notes, errors = encode(trees[cls], e["talents"])
        messages += [f"{e['file']}: {n}" for n in notes]
        problems += [f"{e['file']}: {x}" for x in errors]
        if errors:
            continue
        path = Path(configs) / e["file"]
        text = path.read_text()
        m = TALENTS_LINE.search(text)
        if not m:
            problems.append(f"{e['file']}: no talents line")
            continue
        if m.group(1) == build:
            continue
        if mode == "--write":
            path.write_text(text[:m.start(1)] + build + text[m.end(1):])
            messages.append(f"{e['file']}: talents {m.group(1)} -> {build}")
        else:
            problems.append(f"{e['file']}: talents line {m.group(1)} doesn't match its names ({build}); run with --write")
    return problems, messages


def main(argv):
    mode = next((a for a in argv if a in ("--check", "--write")), "--check")
    args = [a for a in argv[1:] if a not in ("--check", "--write")]
    if len(args) < 2:
        raise SystemExit(__doc__.strip().splitlines()[-1].strip())
    problems, messages = run(args[0], args[1:], mode)
    for m in messages:
        print(m)
    for p in problems:
        print(f"error: {p}")
    if problems:
        return 1
    print(f"sim talents: every setup's build {'is written' if mode == '--write' else 'matches its talent names'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

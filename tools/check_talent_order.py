"""Checks that our talent data and the wowsims/forever engine read a talent build string the same way.

A build string is one digit per talent, in tree order. Our order comes from Forever's trait tables
(gamedata/talents.json, tools/build_talents.py); the engine's from the field order of each class's
talents message in its proto files. If the two drift (a talent added, removed or moved in one but not
the other), the same string means different talents to each.

Fails when a sim setup in gamedata/simconfigs/ puts points where the two disagree, since that run
would sim a different build than the one we name. Other differences are printed as warnings.

Given more than one talents file (main's copy and the `data` branch's, where the daily refresh
lands), it checks the one from the newest Forever client build, as the site deploy would use.

    python3 -I tools/check_talent_order.py ext/wowsims gamedata/simconfigs gamedata/talents.json [more.json ...]
"""
import json
import re
import sys
from pathlib import Path


def ours(talents_json):
    """Class name -> list of trees, each a list of spell ids in build-string order."""
    g = json.loads(Path(talents_json).read_text())
    return {name: [[t[11] for t in tals] for _, _, _, tals in trees] for _, name, trees in g["talents"]}


def engine(checkout, cls):
    """The engine's talent spell ids in field order, split into trees by its TalentTreeSizes, or None."""
    lower = cls.lower()
    proto = Path(checkout) / "proto" / f"{lower}.proto"
    go = Path(checkout) / "sim" / lower / f"{lower}.go"
    if not proto.is_file() or not go.is_file():
        return None
    msg = re.search(r"message %sTalents \{(.*?)\n\}" % cls, proto.read_text(), re.S)
    sizes = re.search(r"TalentTreeSizes = \[3\]int\{\s*(\d+),\s*(\d+),\s*(\d+)\s*\}", go.read_text())
    if not msg or not sizes:
        return None
    fields = sorted((int(n), int(s)) for n, s in re.findall(r"= (\d+) \[\(talent_spell_id\) = (\d+)\]", msg.group(1)))
    ids = [s for _, s in fields]
    trees, at = [], 0
    for n in map(int, sizes.groups()):
        trees.append(ids[at:at + n])
        at += n
    return trees


def setups(configs):
    """(class name, setup file, talent string) for every setup in the index."""
    index = json.loads((Path(configs) / "index.json").read_text())
    for e in index:
        cls = e["key"].split(".")[0].capitalize()
        text = (Path(configs) / e["file"]).read_text()
        m = re.search(r'^talents "([0-9-]*)"$', text, re.M)
        yield cls, e["file"], m.group(1) if m else ""


def differences(a, b):
    """(tree, position) wherever two tree lists name different talents, counting missing ones."""
    out = []
    for ti in range(max(len(a), len(b))):
        ta = a[ti] if ti < len(a) else []
        tb = b[ti] if ti < len(b) else []
        for k in range(max(len(ta), len(tb))):
            if (ta[k] if k < len(ta) else None) != (tb[k] if k < len(tb) else None):
                out.append((ti, k))
    return out


def check(talents_json, checkout, configs):
    """Returns (errors, warnings) as lists of text."""
    mine = ours(talents_json)
    errors, warnings, diffs = [], [], {}
    for cls, trees in mine.items():
        eng = engine(checkout, cls)
        if eng is None:
            warnings.append(f"{cls}: no talents message in the engine checkout")
            continue
        d = differences(trees, eng)
        diffs[cls] = set(d)
        if d:
            warnings.append(f"{cls}: talent order differs from the engine at {len(d)} position(s), "
                            f"first tree {d[0][0] + 1} position {d[0][1] + 1}")
    for cls, file, s in setups(configs):
        if cls not in mine:
            errors.append(f"{file}: no talent data for {cls}")
            continue
        for ti, part in enumerate(s.split("-")):
            for k, ch in enumerate(part):
                if ch != "0" and (ti, k) in diffs.get(cls, set()):
                    errors.append(f"{file}: puts points in tree {ti + 1} position {k + 1}, where our talent "
                                  f"data and the engine name different talents")
    return errors, warnings


def build_of(path):
    """The Forever client build a talents file was made from, as a number tuple; () if unreadable."""
    try:
        b = json.loads(Path(path).read_text())["builds"]["forever"]
        return tuple(int(x) for x in re.fullmatch(r"\d+(?:\.\d+){3}", b).group(0).split("."))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return ()


def newest(paths):
    """The readable talents file from the newest client build (the first one on a tie)."""
    usable = [p for p in paths if build_of(p)]
    if not usable:
        raise SystemExit("no readable talents file")
    return max(usable, key=lambda p: (build_of(p), -paths.index(p)))


def main(argv):
    if len(argv) < 4:
        raise SystemExit(__doc__.strip().splitlines()[-1].strip())
    talents = newest(argv[3:])
    b = ".".join(map(str, build_of(talents)))
    print(f"talent data: {talents} (Forever {b})")
    errors, warnings = check(talents, argv[1], argv[2])
    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"error: {e}")
    if errors:
        raise SystemExit(1)
    print("talent order: every sim setup's build reads the same in our data and the engine")


if __name__ == "__main__":
    main(sys.argv)

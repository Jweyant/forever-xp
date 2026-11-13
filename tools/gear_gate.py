"""Decide whether the gear data needs rebuilding: has anything it's built from changed?

Compares what the last build recorded in gamedata/items-report.md (the client build and the
short commit of each source) with what's current. Used by the gear-data workflow's frequent
check, so a new client build or new item data reaches the site within hours, not a day.

  python3 tools/gear_gate.py --report items-report.md --build 1.60.1.70888 \
      --head wowsims=<sha> --head Questie=<sha>

Prints the reasons and writes run=true|false to $GITHUB_OUTPUT. Anything it can't read counts as
changed, so a broken check rebuilds instead of silently going stale.
"""
import argparse
import os
import re
import sys

BUILD = re.compile(r"^Forever client build (\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,7})\.?\s*$", re.M)
SOURCES = re.compile(r"^Sources: (.+)$", re.M)
SHA = re.compile(r"^[0-9a-f]{7,40}$")
NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,30}$")


def recorded(report):
    """(client build, {source name: short commit}) from an items report; missing parts are None/{}."""
    m = BUILD.search(report or "")
    build = m.group(1) if m else None
    shas = {}
    s = SOURCES.search(report or "")
    for part in (s.group(1).split(",") if s else []):
        bits = part.split()
        if len(bits) == 2 and NAME.match(bits[0]) and SHA.match(bits[1]):
            shas[bits[0].lower()] = bits[1]
    return build, shas


def reasons(report, build, heads):
    """Why a rebuild is needed, as a list of plain sentences; empty when nothing changed.
    heads: {source name: current commit}. A source the report doesn't list, or a commit that
    isn't one, counts as changed."""
    old_build, old = recorded(report)
    out = []
    if not old_build:
        out.append("the last build's report has no client build")
    elif build != old_build:
        out.append(f"client build {old_build} -> {build}")
    for name, sha in sorted(heads.items()):
        was = old.get(name.lower())
        if not SHA.match(sha or ""):
            out.append(f"{name}: couldn't read its newest commit")
        elif not was:
            out.append(f"{name}: not in the last build's report")
        elif not sha.startswith(was):
            out.append(f"{name} {was} -> {sha[:len(was)]}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--build", required=True)
    ap.add_argument("--head", action="append", default=[], help="name=commit, repeatable")
    a = ap.parse_args()
    try:
        report = open(a.report, encoding="utf-8").read()
    except OSError:
        report = ""
    heads = dict(h.split("=", 1) for h in a.head if "=" in h)
    why = reasons(report, a.build, heads)
    for w in why:
        print(f"changed: {w}")
    if not why:
        print("Nothing the gear data is built from has changed.")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"run={'true' if why else 'false'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

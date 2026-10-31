"""Extract how many of each objective a classic quest really needs, from cmangos classic-db.

Writes tools/quest_counts.json: {"<quest id>": {"npc:<id>" | "obj:<id>" | "item:<id>": count}},
keeping only counts above 1 (1 is the guide generator's default). The guide time model
(tools/guidegen.py) uses these instead of guessing counts from the objective text, which read
"Wake up 5 peons" as one peon and made quests look seconds long.

Usage: python3 tools/quest_counts.py --cmangos ext/cmangos.sql [--out tools/quest_counts.json]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import mysqldump  # noqa: E402


def counts_from_rows(rows):
    out = {}
    for r in rows:
        qid = r.get("entry")
        if not isinstance(qid, int):
            continue
        c = {}
        for i in (1, 2, 3, 4):
            target = r.get(f"ReqCreatureOrGOId{i}") or 0
            n = r.get(f"ReqCreatureOrGOCount{i}") or 0
            if target and n > 1:
                c[("npc:%d" % target) if target > 0 else ("obj:%d" % -target)] = n
            item = r.get(f"ReqItemId{i}") or 0
            n = r.get(f"ReqItemCount{i}") or 0
            if item and n > 1:
                c["item:%d" % item] = n
        if c:
            out[str(qid)] = c
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cmangos", required=True)
    ap.add_argument("--out", default=str(Path(__file__).parent / "quest_counts.json"))
    a = ap.parse_args()
    d = mysqldump.read(Path(a.cmangos), ["quest_template"])
    out = counts_from_rows(d["quest_template"])
    Path(a.out).write_text(json.dumps(out, separators=(",", ":"), sort_keys=True) + "\n")
    print(f"{len(out)} quests with objective counts -> {a.out}")


if __name__ == "__main__":
    main()

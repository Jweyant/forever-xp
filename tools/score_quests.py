"""Score every quest in a level band on its own: XP per minute including travel.

Usage: python3 tools/score_quests.py --min 18 --max 31 --race Troll --class Hunter \
          --zones 1413,1442,1440,1441,1424 --out reports/quest-scores-18-31.csv
"""
import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from guidegen import (CLASS_BITS, DIALOG_SEC, KILL_SEC, LOOT_OBJECT_SEC, DEFAULT_DROP_RATE,
                      RACE_BITS, RUN_YPS, Data, Generator, as_list, mob_xp)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min", type=int, default=18)
    ap.add_argument("--max", type=int, default=31)
    ap.add_argument("--race", default="Troll")
    ap.add_argument("--class", dest="cls", default="Hunter")
    ap.add_argument("--zones", default="1413,1442,1440,1441,1424")
    ap.add_argument("--out", default="reports/quest-scores.csv")
    a = ap.parse_args()
    zones = {int(z) for z in a.zones.split(",")}
    d = Data()
    g = Generator(d, {"guide": {"name": "score", "for": a.race, "class": a.cls}, "steps": []})
    g.step_no, g.step_only = 0, None
    race_bit, class_bit = RACE_BITS[a.race], CLASS_BITS[a.cls.upper()]
    rows = []
    for qid, q in d.quests.items():
        ql = q.get("questLevel") or 0
        if not (a.min <= ql <= a.max):
            continue
        races = (q.get("requiredRaces") or 0) & 0xFF
        if races and not races & race_bit:
            continue
        classes = q.get("requiredClasses") or 0
        if classes and not classes & class_bit:
            continue
        if (q.get("specialFlags") or 0) & 1:
            continue  # repeatable
        g.s.pos = None
        start, giver, _ = g.endpoint(qid, "startedBy")
        if not start or start[0] not in zones:
            continue
        g.s.pos = start
        level = max(ql - 1, 1)
        seconds, kill_xp, notes = 2 * DIALOG_SEC, 0, []
        for kind, oid, oname, pts, count, mlvl in g.objective_points(qid):
            where = g.nearest(pts)
            if not where:
                notes.append(f"no location: {oname}")
                continue
            seconds += g.distance(g.s.pos, where) / RUN_YPS
            g.s.pos = where
            kills = count if kind == "kill" else (count / DEFAULT_DROP_RATE if kind == "loot" else 0)
            seconds += kills * KILL_SEC + (count * LOOT_OBJECT_SEC if kind == "object" else 0)
            kill_xp += int(kills * mob_xp(level, mlvl or level))
            if mlvl and mlvl >= ql + 3:
                notes.append(f"{oname} level {mlvl}")
        end, ender, _ = g.endpoint(qid, "finishedBy")
        if end:
            seconds += g.distance(g.s.pos, end) / RUN_YPS
        xp = (d.xp.get(qid) or [0, 0])[1]
        elite = "elite" if (q.get("questFlags") or 0) & 64 or "group" in " ".join(as_list(q.get("objectivesText"))).lower() else ""
        rows.append({
            "zone": start[0], "quest": qid, "name": q.get("name"), "level": ql, "req": q.get("requiredLevel"),
            "xp": xp, "kill_xp": kill_xp, "minutes": round(seconds / 60, 1),
            "xp_per_min": round((xp + kill_xp) / max(seconds / 60, 0.5)),
            "giver": giver, "gx": start[1], "gy": start[2],
            "ender": ender, "ez": end[0] if end else "", "ex": end[1] if end else "", "ey": end[2] if end else "",
            "pre": as_list(q.get("preQuestSingle")) or as_list(q.get("preQuestGroup")) or "",
            "next": q.get("nextQuestInChain") or "", "flags": elite, "notes": "; ".join(notes),
        })
    rows.sort(key=lambda r: (r["zone"], -r["xp_per_min"]))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} quests -> {a.out}")


if __name__ == "__main__":
    main()

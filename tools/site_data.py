"""Build the JSON the website reads, from the files already in this repo.

Inputs (all committed, nothing downloaded):
  routes/*.yaml                  guide order, plus "# Skipped:" notes
  reports/*.md                   per-guide estimates written by tools/guidegen.py
  reports/quest-scores-*.csv     per-quest XP/minute written by tools/score_quests.py
  tools/zone_sizes.json          uiMapId -> zone name
  out/quest_timing.csv           measured timings from ForeverScout logs (optional; used when present)

Output: site/src/data/{guides,quests,zones,meta}.json

Usage: python3 tools/site_data.py
"""
import csv
import json
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "src" / "data"

# Below this many XP per minute (quest on its own, travel included) a quest is a skip candidate.
SKIP_XP_PER_MIN = 250

ACTION_KEYS = ("accept", "turnin", "complete")


def ids(v):
    if v is None:
        return []
    if isinstance(v, list):
        return [int(x) for x in v if isinstance(x, int) or str(x).isdigit()]
    return [int(v)] if str(v).isdigit() else []


def slug_of(path):
    return path.stem


def parse_skips(text):
    """'# Skipped: 4767 Wind Rider and 5062/5088 (Thunder Bluff trips), ...' -> {id: reason}"""
    block = []
    on = False
    for line in text.splitlines():
        if not line.startswith("#"):
            if on:
                break
            continue
        body = line.lstrip("#").strip()
        if body.lower().startswith("skipped:"):
            on = True
            body = body[len("skipped:"):].strip()
        if on:
            block.append(body)
    out = {}
    for part in re.split(r",\s*(?![^()]*\))", " ".join(block)):
        part = part.strip().rstrip(".")
        if not part:
            continue
        reason = ""
        m = re.search(r"\(([^)]*)\)", part)
        if m:
            reason = m.group(1)
        for qid in re.findall(r"\b(\d{3,5})\b", part.split("(")[0]):
            out[int(qid)] = {"note": part, "reason": reason}
    return out


def md_tables(text):
    """Yield (heading, rows as dicts) for every markdown table under a ## heading."""
    heading, header, rows = None, None, []
    for line in text.splitlines() + [""]:
        if line.startswith("## "):
            heading = line[3:].strip()
            continue
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if header is None:
                header = cells
            elif set("".join(cells)) <= set("-: "):
                continue
            else:
                rows.append(dict(zip(header, cells)))
        elif header is not None:
            yield heading, rows
            header, rows = None, []


def num(s, cast=float):
    try:
        return cast(s)
    except (TypeError, ValueError):
        return None


def parse_report(path):
    text = path.read_text()
    title = text.splitlines()[0].lstrip("# ").strip()
    m = re.search(r"Estimated finish: level ([\d.]+) after (\d+) minutes\. Quests still in log: \[([^\]]*)\]", text)
    issues = []
    if "## Issues" in text:
        sect = text.split("## Issues", 1)[1].split("\n## ", 1)[0]
        issues = [l[2:].strip() for l in sect.splitlines() if l.startswith("- ")]
    quests, steps = [], []
    for heading, rows in md_tables(text):
        if heading and heading.startswith("Quests by XP"):
            for r in rows:
                qid, _, name = r["quest"].partition(" ")
                quests.append({"id": int(qid), "name": name, "xp": num(r["xp"], int),
                               "minutes": num(r["minutes spent on objectives"]),
                               "xp_per_min": num(r["xp/min"], int)})
        elif heading == "Step by step":
            for r in rows:
                steps.append({"n": num(r["#"], int), "level": num(r["level"]),
                              "minutes": num(r["minutes"]), "xp": num(r["xp"], int),
                              "text": r["step"]})
    return {
        "title": title,
        "end_level": float(m.group(1)) if m else None,
        "minutes": int(m.group(2)) if m else None,
        "left_in_log": ids([x.strip() for x in m.group(3).split(",")]) if m and m.group(3).strip() else [],
        "issues": issues,
        "quests": quests,
        "steps": steps,
    }


def main():
    zones_raw = json.loads((ROOT / "tools" / "zone_sizes.json").read_text())
    zone_name = {int(k): v["name"] for k, v in zones_raw.items()}

    guides = []
    route_quests = {}   # quest id -> list of guide slugs
    skip_notes = {}
    for rp in sorted((ROOT / "routes").glob("*.yaml")):
        text = rp.read_text()
        spec = yaml.safe_load(text)
        g = spec["guide"]
        slug = slug_of(rp)
        qids = []
        for st in spec.get("steps", []):
            for k in ACTION_KEYS:
                for q in ids(st.get(k)):
                    if q not in qids:
                        qids.append(q)
        for q in qids:
            route_quests.setdefault(q, []).append(slug)
        for q, note in parse_skips(text).items():
            skip_notes[q] = {**note, "guide": slug}
        rep_path = ROOT / "reports" / f"{slug}.md"
        rep = parse_report(rep_path) if rep_path.exists() else {}
        m = re.match(r"(\d+)-(\d+)", g["name"])
        faction = "Horde" if slug.startswith("horde") else "Alliance" if slug.startswith("alliance") else ""
        guides.append({
            "slug": slug,
            "name": g["name"],
            "zone": re.sub(r"^\d+-\d+\s+", "", g["name"]),
            "from": int(m.group(1)) if m else None,
            "to": int(m.group(2)) if m else None,
            "faction": faction,
            "for": g.get("for"),
            "class": g.get("class"),
            "next": g.get("next"),
            "quest_ids": qids,
            "step_count": len(spec.get("steps", [])),
            **{k: rep.get(k) for k in ("end_level", "minutes", "left_in_log", "issues", "quests", "steps")},
        })
    guides.sort(key=lambda x: (x["faction"], x["from"] or 0))

    # Measured timings, once ForeverScout logs have been ingested.
    measured = {}
    timing = ROOT / "out" / "quest_timing.csv"
    if timing.exists():
        with timing.open() as f:
            for r in csv.DictReader(f):
                q = num(r.get("quest"), int)
                if q:
                    measured[q] = {"minutes": num(r.get("median_minutes")),
                                   "xp_per_min": num(r.get("xp_per_min")),
                                   "players": num(r.get("players"), int)}

    quests = {}
    for sp in sorted((ROOT / "reports").glob("quest-scores-*.csv")):
        with sp.open() as f:
            for r in csv.DictReader(f):
                qid = int(r["quest"])
                z = num(r["zone"], int)
                notes = [n.strip() for n in (r.get("notes") or "").split(";") if n.strip()]
                quests[qid] = {
                    "id": qid, "name": r["name"], "level": num(r["level"], int),
                    "req": num(r["req"], int), "xp": num(r["xp"], int),
                    "kill_xp": num(r["kill_xp"], int), "minutes": num(r["minutes"]),
                    "xp_per_min": num(r["xp_per_min"], int), "giver": r["giver"] or None,
                    "ender": r["ender"] or None, "zone_id": z, "zone": zone_name.get(z),
                    "pre": ids([x for x in re.findall(r"\d+", r.get("pre") or "")]),
                    "next": num(r.get("next"), int),
                    "unlocated": any(n.startswith("no location") for n in notes),
                    "source": "score",
                }
    # Quests that only appear in guide reports (levels outside the scored bands).
    for g in guides:
        for rq in g.get("quests") or []:
            q = quests.setdefault(rq["id"], {"id": rq["id"], "name": rq["name"], "xp": rq["xp"],
                                            "minutes": rq["minutes"], "xp_per_min": rq["xp_per_min"],
                                            "zone": g["zone"], "source": "guide"})
            q.setdefault("objective_minutes", rq["minutes"])

    for qid, q in quests.items():
        q["guides"] = route_quests.get(qid, [])
        q["in_route"] = bool(q["guides"])
        if qid in skip_notes:
            q["skip_note"] = skip_notes[qid]
        if qid in measured:
            q["measured"] = measured[qid]
        rate = (q.get("measured") or {}).get("xp_per_min") or q.get("xp_per_min")
        if q["in_route"]:
            q["verdict"] = "do"
        elif q.get("unlocated"):
            q["verdict"] = "unknown"
        elif qid in skip_notes or (rate is not None and rate < SKIP_XP_PER_MIN):
            q["verdict"] = "skip"
        else:
            q["verdict"] = "optional"

    zones = {}
    for q in quests.values():
        name = q.get("zone") or "Unknown"
        z = zones.setdefault(name, {"name": name, "slug": re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-"),
                                    "quests": 0, "do": 0, "skip": 0, "optional": 0, "unknown": 0,
                                    "rates": []})
        z["quests"] += 1
        z[q["verdict"]] += 1
        if q.get("xp_per_min"):
            z["rates"].append(q["xp_per_min"])
    for z in zones.values():
        z["median_xp_per_min"] = int(statistics.median(z["rates"])) if z["rates"] else None
        del z["rates"]

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "guides.json").write_text(json.dumps(guides, indent=1))
    (OUT / "quests.json").write_text(json.dumps(sorted(quests.values(), key=lambda q: q["id"]), indent=1))
    (OUT / "zones.json").write_text(json.dumps(sorted(zones.values(), key=lambda z: z["name"]), indent=1))
    (OUT / "meta.json").write_text(json.dumps({
        "built": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "skip_threshold": SKIP_XP_PER_MIN,
        "measured_quests": len(measured),
        "quests": len(quests),
        "guides": len(guides),
    }, indent=1))
    print(f"{len(guides)} guides, {len(quests)} quests, {len(zones)} zones, {len(measured)} measured -> {OUT}")


if __name__ == "__main__":
    main()

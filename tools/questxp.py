"""Quest XP for quests the databases don't have a number for yet.

Two sources, used only to fill gaps (Questie's value always wins):

1. opendata (https://github.com/wowlayerup-forever/opendata, data CC BY 4.0): quest templates
   read from players' WoW Forever client caches, so their XP is the game's own number
   (`data/client/quests.jsonl`), and, once players record them, who starts and ends each quest
   (`data/world/quest_givers.jsonl`). Third-party data: every field is type- and range-checked
   and nothing in it is executed or shown as HTML.
2. An estimate: the median XP of Classic quests at the same level that ask for the same kind of
   thing (talk/deliver versus kill/collect). For one quest it is often off by 20% or more, but
   over a zone's worth of quests it lands within about 5%, which is what route level estimates
   need. Estimated values are marked (`xpe`) wherever they're shown.

ForeverScout logs replace both with measured values once players run the routes.
"""
import json
import re
import statistics
from pathlib import Path

MAX_XP = 200_000
MAX_LINE = 1 << 16
# Objective text that only sends you to someone: these quests sit in Classic's low XP tiers.
TALK = re.compile(r"^\s*(speak|talk|report|deliver|return|travel|go|take|seek out|find|meet|visit)\b"
                  r"(?!.*\b(kill|slay|destroy|collect|gather|obtain|recover|retrieve)\b)", re.I)
CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _int(v, lo, hi):
    return v if isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi else None


def _text(v, limit=600):
    if not isinstance(v, str):
        return None
    v = CTRL.sub("", v).strip()
    return v[:limit] or None


def read_jsonl(path):
    """Yield dict rows from a JSON-lines file, skipping anything that isn't one."""
    path = Path(path)
    if not path.is_file():
        return
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            if len(line) > MAX_LINE:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                yield row


def opendata_quests(root):
    """{quest_id: {xp, lv, req, obj}} from opendata's client-cache quest templates."""
    out = {}
    for r in read_jsonl(Path(root) / "data" / "client" / "quests.jsonl"):
        qid = _int(r.get("quest_id"), 1, 10_000_000)
        if not qid:
            continue
        rew = r.get("rewards") if isinstance(r.get("rewards"), dict) else {}
        e = {"xp": _int(rew.get("xp"), 1, MAX_XP), "lv": _int(r.get("quest_level"), 1, 80),
             "req": _int(r.get("min_level"), 1, 80), "obj": _text(r.get("objectives"))}
        out[qid] = {k: v for k, v in e.items() if v}
    return out


def opendata_givers(root, min_seen=2):
    """{(quest_id, "start"|"end"): {t, id, zone, x, y, n}}: the most-seen holder per role."""
    best = {}
    for r in read_jsonl(Path(root) / "data" / "world" / "quest_givers.jsonl"):
        qid = _int(r.get("quest_id"), 1, 10_000_000)
        hid = _int(r.get("holder_id"), 1, 100_000_000)
        seen = _int(r.get("n"), 0, 10_000_000) or 0
        role, kind = r.get("role"), r.get("holder_kind")
        if not qid or not hid or role not in ("start", "end") or kind not in ("npc", "object", "item") or seen < min_seen:
            continue
        e = {"t": kind, "id": hid, "n": seen}
        c = r.get("coords") if isinstance(r.get("coords"), dict) else {}
        x, y, zone = c.get("x"), c.get("y"), _int(c.get("zone_id"), 1, 10_000_000)
        if isinstance(x, (int, float)) and isinstance(y, (int, float)) and 0 <= x <= 100 and 0 <= y <= 100:
            e.update(x=round(float(x), 1), y=round(float(y), 1))
        if zone:
            e["zone"] = zone
        key = (qid, role)
        if key not in best or seen > best[key]["n"]:
            best[key] = e
    return best


def opendata_names(root):
    """{("npc"|"object"|"item", id): name} from opendata's client tables."""
    names = {}
    for kind, file, key in (("npc", "npcs", "npc_id"), ("object", "objects", "object_id"), ("item", "items", "item_id")):
        for r in read_jsonl(Path(root) / "data" / "client" / f"{file}.jsonl"):
            i, n = _int(r.get(key), 1, 100_000_000), _text(r.get("name"), 120)
            if i and n:
                names[(kind, i)] = n
    return names


def is_talk(objective_text):
    return bool(objective_text) and bool(TALK.match(objective_text))


class Estimator:
    """Median XP by quest level and kind, from quests whose XP is known."""

    def __init__(self, known):
        """known: iterable of (level, xp, talk)."""
        self.by = {}
        for lv, xp, talk in known:
            if 0 < lv <= 60 and xp:
                self.by.setdefault((lv, bool(talk)), []).append(xp)

    def __call__(self, level, talk=False):
        if not 0 < level <= 60:
            return None
        for spread in (0, 1, 2):
            vals = [x for d in range(-spread, spread + 1) for x in self.by.get((level + d, bool(talk)), [])]
            if len(vals) >= 5:
                return int(round(statistics.median(vals) / 5) * 5)
        return None

"""ForeverXP guide generator.

Turns a short route spec (YAML: the order of quest actions) into a RestedXP-format guide,
filling coordinates, NPC names and zones from the Forever Questie export, and checking the
route as it goes: prerequisites, faction/race/class, quest-log size, level requirements.
It also estimates XP, level and time at every step, and writes a report with XP/minute per
quest so slow quests can be cut.

Usage:
  python3 tools/guidegen.py routes/horde-01-12-durotar.yaml --out guides/ --report reports/

Route spec format (see routes/*.yaml):
  guide: {name, next, group, for, start_level, version}
  steps:
    - accept: [ids]            # goes to the giver of the first quest
    - turnin: [ids]
    - complete: [ids]          # goes to where the objectives are, nearest to you
    - goto: [uiMapId, x, y]    # free movement, with optional text
    - home / hs / fp / fly / train / tame / vendor: value
    - text: "shown on the step"
    - only: "Hunter"           # RXP class/race tag for the whole step
    - xp: 10                   # wait/grind until this level (makes the step a gate)
    - where: [uiMapId, x, y]   # on a complete step: where to go for objectives Questie can't place
"""
import argparse
import json
import math
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# Classic XP needed to go from level N to N+1.
XP_TO_NEXT = {1: 400, 2: 900, 3: 1400, 4: 2100, 5: 2800, 6: 3600, 7: 4500, 8: 5400, 9: 6500,
              10: 7600, 11: 8800, 12: 10100, 13: 11400, 14: 12900, 15: 14400, 16: 16000,
              17: 17700, 18: 19400, 19: 21300, 20: 23200, 21: 25200, 22: 27300, 23: 29400,
              24: 31700, 25: 34000, 26: 36400, 27: 38900, 28: 41400, 29: 44300, 30: 47400}
RACE_BITS = {"Human": 1, "Orc": 2, "Dwarf": 4, "NightElf": 8, "Undead": 16, "Tauren": 32,
             "Gnome": 64, "Troll": 128}
CLASS_BITS = {"WARRIOR": 1, "PALADIN": 2, "HUNTER": 4, "ROGUE": 8, "PRIEST": 16,
              "SHAMAN": 64, "MAGE": 128, "WARLOCK": 256, "DRUID": 1024}

RUN_YPS = 7.0            # run speed, yards per second
DIALOG_SEC = 6           # per accept / turn-in
KILL_SEC = 18            # per kill including finding the next mob (low level ranged)
LOOT_OBJECT_SEC = 10     # per world object
DEFAULT_DROP_RATE = 0.5  # unknown drop rates
QUEST_LOG_MAX = 20
# Mobs killed while running between objectives (outside towns). An assumption to be replaced
# by measured values from ForeverScout logs.
TRAVEL_KILLS_PER_100YD = 0.3
TRAVEL_KILL_MIN_YD = 150


def quest_xp_at(base, player_level, quest_level):
    """Classic reduction for quests far below the player's level."""
    if not base:
        return 0
    diff = player_level - quest_level
    if diff <= 5:
        return base
    return int(base * {6: 0.8, 7: 0.6, 8: 0.4, 9: 0.2}.get(diff, 0.1))


def mob_xp(player_level, mob_level):
    base = player_level * 5 + 45
    if mob_level >= player_level:
        return int(base * (1 + 0.05 * min(mob_level - player_level, 4)))
    zd = 5 if player_level < 8 else 6 if player_level < 10 else 7 if player_level < 12 else 8 if player_level < 16 else 9
    gray = player_level - zd
    if mob_level <= gray:
        return 0
    return int(base * (1 - (player_level - mob_level) / zd))


def as_map(t):
    if isinstance(t, list):
        return {i + 1: v for i, v in enumerate(t)}
    return {int(k): v for k, v in (t or {}).items()}


def as_list(t):
    if t is None:
        return []
    if isinstance(t, dict):
        return [t[k] for k in sorted(t, key=lambda k: int(k))]
    return t


class Data:
    def __init__(self):
        self.db = sqlite3.connect(DATA / "forever_questdb.sqlite")
        self.quests = {r[0]: json.loads(r[1]) for r in self.db.execute("SELECT id, json FROM quests")}
        self.xp = {int(k): v for k, v in json.loads((DATA / "questiedb/questXP.json").read_text()).items()}
        self.area_to_ui = {int(k): v for k, v in json.loads((DATA / "questiedb/areaIdToUiMapId.json").read_text()).items()}
        sizes = json.loads((ROOT / "tools/zone_sizes.json").read_text())
        self.size = {int(k): (v["width_yd"], v["height_yd"]) for k, v in sizes.items()}
        self.bounds = {int(k): (v["map_id"], v["bounds"]) for k, v in sizes.items()}
        self._npc, self._obj, self._item = {}, {}, {}

    def _load(self, table, cache, i):
        if i not in cache:
            row = self.db.execute(f"SELECT json FROM {table} WHERE id=?", (i,)).fetchone()
            cache[i] = json.loads(row[0]) if row else None
        return cache[i]

    def npc(self, i): return self._load("npcs", self._npc, i)
    def obj(self, i): return self._load("objects", self._obj, i)
    def item(self, i): return self._load("items", self._item, i)

    def spawns(self, entity):
        """[(uiMapId, x, y)] for an NPC/object record."""
        out = []
        for area, coords in as_map((entity or {}).get("spawns")).items():
            ui = self.area_to_ui.get(area)
            if not ui:
                continue
            for c in coords or []:
                if c and len(c) >= 2 and c[0] >= 0:
                    out.append((ui, c[0], c[1]))
        return out

    def ref(self, quest, field):
        """startedBy / finishedBy -> (kind, id) of the first NPC or object."""
        r = quest.get(field) or []
        if isinstance(r, dict):
            r = [r.get(str(i)) for i in (1, 2, 3)]
        for kind, ids in zip(("npc", "object", "item"), list(r) + [None] * 3):
            if ids:
                return kind, ids[0]
        return None, None


@dataclass
class State:
    level: int = 1
    xp: int = 0
    pos: tuple = None            # (uiMapId, x, y)
    seconds: float = 0
    log: set = field(default_factory=set)
    done: set = field(default_factory=set)
    issues: list = field(default_factory=list)

    def add_xp(self, amount):
        self.xp += amount
        while self.level in XP_TO_NEXT and self.xp >= XP_TO_NEXT[self.level]:
            self.xp -= XP_TO_NEXT[self.level]
            self.level += 1

    @property
    def level_float(self):
        need = XP_TO_NEXT.get(self.level, 1)
        return self.level + self.xp / need


class Generator:
    def __init__(self, data, spec):
        self.d = data
        self.spec = spec
        g = spec["guide"]
        self.races = [r for r in re.split(r"[/ ]", g.get("for", "")) if r in RACE_BITS]
        self.race_mask = sum(RACE_BITS[r] for r in self.races)
        self.class_name = g.get("class", "HUNTER").upper()
        self.faction = g.get("faction", "Horde")
        self.sim_race = g.get("sim_race", self.races[-1] if self.races else "")
        self.s = State(level=g.get("start_level", 1), xp=g.get("start_xp", 0))
        self.lines = []
        self.report = []
        self.quest_stats = {}
        self.in_town = False

    # ---------------------------------------------------------------- helpers
    def warn(self, msg):
        self.s.issues.append(f"step {self.step_no}: {msg}")

    def q(self, qid):
        q = self.d.quests.get(qid)
        if not q:
            self.warn(f"quest {qid} is not in the Questie data (new Forever quest?)")
        return q or {"name": f"Quest {qid}", "id": qid}

    def name(self, qid):
        return self.q(qid).get("name", str(qid))

    def world(self, p):
        """Map percent -> (continent, world x, world y) using Forever map bounds."""
        info = self.d.bounds.get(p[0])
        if not info:
            return None
        cont, b = info
        wy = b["left"] - p[1] / 100 * (b["left"] - b["right"])
        wx = b["top"] - p[2] / 100 * (b["top"] - b["bottom"])
        return cont, wx, wy

    def distance(self, a, b):
        if not a or not b:
            return 0
        wa, wb = self.world(a), self.world(b)
        if wa and wb and wa[0] == wb[0]:
            return math.hypot(wa[1] - wb[1], wa[2] - wb[2])
        if a[0] == b[0]:
            w, h = self.d.size.get(a[0], (5000, 3333))
            return math.hypot((a[1] - b[1]) / 100 * w, (a[2] - b[2]) / 100 * h)
        return 1500  # different continent or unknown map

    def move(self, to):
        if to:
            dist = self.distance(self.s.pos, to)
            self.s.seconds += dist / RUN_YPS
            if dist >= TRAVEL_KILL_MIN_YD and not self.in_town:
                kills = int(dist / 100 * TRAVEL_KILLS_PER_100YD)
                for _ in range(kills):
                    self.s.add_xp(mob_xp(self.s.level, max(self.s.level - 1, 1)))
                self.s.seconds += kills * KILL_SEC * 0.6
            self.s.pos = to

    def nearest(self, points, k=8):
        """Centroid of the k points closest to where we are (one hunting area)."""
        if not points:
            return None
        here = self.s.pos or points[0]
        pts = sorted(points, key=lambda p: self.distance(here, p))
        ui = pts[0][0]
        pick = [p for p in pts if p[0] == ui][:k]
        return (ui, round(sum(p[1] for p in pick) / len(pick), 2), round(sum(p[2] for p in pick) / len(pick), 2))

    def endpoint(self, qid, field):
        kind, i = self.d.ref(self.q(qid), field)
        if kind == "npc":
            ent = self.d.npc(i)
            pts = self.d.spawns(ent)
            return (self.nearest(pts, 1) if pts else None), (ent or {}).get("name"), i
        if kind == "object":
            ent = self.d.obj(i)
            pts = self.d.spawns(ent)
            return (self.nearest(pts, 1) if pts else None), (ent or {}).get("name"), None
        return None, None, None

    def goto(self, pos, text=None):
        if pos and pos == self.s.pos and not text and self.lines and not self.lines[-1].startswith("step"):
            return
        if pos:
            self.lines.append(f"    .goto {pos[0]},{pos[1]},{pos[2]}" + (f" >> {text}" if text else ""))
            self.move(pos)

    # ------------------------------------------------------------- validation
    def check_eligible(self, qid):
        q = self.q(qid)
        races = q.get("requiredRaces") or 0
        legacy = races & 0xFF
        if legacy and self.race_mask and not (legacy & self.race_mask):
            self.warn(f"{qid} {self.name(qid)} is not available to {'/'.join(self.races)}")
        classes = q.get("requiredClasses") or 0
        if classes and not (classes & CLASS_BITS.get(self.class_name, 0)) and not self.step_only:
            self.warn(f"{qid} {self.name(qid)} is class-restricted; tag the step with only:")
        req = q.get("requiredLevel") or 0
        if req and self.s.level < req:
            self.warn(f"{qid} {self.name(qid)} needs level {req}, estimated level here {self.s.level_float:.1f}")
        single = as_list(q.get("preQuestSingle"))
        if single and not any(p in self.s.done for p in single):
            self.warn(f"{qid} {self.name(qid)} needs one of {single} turned in first")
        for p in as_list(q.get("preQuestGroup")):
            if p not in self.s.done:
                self.warn(f"{qid} {self.name(qid)} needs {p} turned in first")

    # ------------------------------------------------------------- objectives
    def objective_points(self, qid):
        """Where to do each objective: [(kind, id, name, points, count_guess, mob_level)]."""
        q = self.q(qid)
        text = " ".join(as_list(q.get("objectivesText")))
        out = []

        def count_for(name):
            if name:
                m = re.search(r"(\d+)\s+(?:\w+\s+){0,3}?" + re.escape(name.split()[0]), text)
                if m:
                    return int(m.group(1))
            return 1

        def first(entry):
            if isinstance(entry, dict):
                return entry.get("1")
            if isinstance(entry, list):
                return entry[0] if entry else None
            return entry

        slots = as_map(q.get("objectives"))  # 1 creature, 2 object, 3 item, 4 rep, 5 kill credit
        creature = as_list(slots.get(1))
        obj = as_list(slots.get(2))
        items = as_list(slots.get(3))
        for kc in as_list(slots.get(5)):
            kc = as_list(kc) if not isinstance(kc, dict) else [kc.get(str(i)) for i in (1, 2, 3)]
            base = kc[1] if len(kc) > 1 else None
            if base:
                creature.append([base])
        for e in creature:
            nid = first(e)
            n = self.d.npc(nid) or {}
            out.append(("kill", nid, n.get("name"), self.d.spawns(n), count_for(n.get("name")), n.get("maxLevel") or 1))
        for e in obj:
            oid = first(e)
            o = self.d.obj(oid) or {}
            out.append(("object", oid, o.get("name"), self.d.spawns(o), count_for(o.get("name")), 0))
        for e in items:
            iid = first(e)
            it = self.d.item(iid) or {}
            iname = it.get("name")
            pts, lvls, kind = [], [], "loot"
            for nid in as_list(it.get("npcDrops")):
                n = self.d.npc(nid) or {}
                pts += self.d.spawns(n)
                if n.get("maxLevel"):
                    lvls.append(n["maxLevel"])
            lvl = min(lvls) if lvls else 0
            for oid in as_list(it.get("objectDrops")):
                pts += self.d.spawns(self.d.obj(oid))
                kind = "object" if not it.get("npcDrops") else kind
            out.append((kind, iid, iname, pts, count_for(iname), lvl))
        return out

    # ------------------------------------------------------------------ steps
    def applies(self, tag):
        """Same rules as RXP's applies(): '/' = or, space = and, '!' = not."""
        if not tag:
            return True
        for alt in tag.split("/"):
            ok = True
            for tok in alt.split():
                neg = tok.startswith("!")
                tok = tok.lstrip("!")
                hit = tok.upper() == self.class_name or tok == self.sim_race or tok == self.faction
                if hit == neg:
                    ok = False
                    break
            if ok:
                return True
        return False

    def emit_step(self, st):
        only = st.get("only")
        self.step_only = only
        if not self.applies(only):
            # Emit the step for other characters, but don't simulate it for ours.
            saved, saved_issues = self.s, list(self.s.issues)
            import copy
            self.s = copy.deepcopy(saved)
            self._emit(st, only)
            self.s = saved
            self.s.issues = saved_issues
            self.report.pop() if self.report and self.report[-1][0] == self.step_no else None
            return
        self._emit(st, only)

    def _emit(self, st, only):
        self._step_start = len(self.lines)
        self.lines.append("step" + (f" << {only}" if only else ""))
        if st.get("label"):
            self.lines.append(f"    #label {st['label']}")
        if st.get("completewith"):
            self.lines.append(f"    #completewith {st['completewith']}")
        self.in_town = bool(st.get("town"))
        t0, xp0 = self.s.seconds, self.s.xp + sum(XP_TO_NEXT[l] for l in range(1, self.s.level))

        if "goto" in st:
            g = st["goto"]
            self.goto((int(g[0]), float(g[1]), float(g[2])), st.get("text"))

        for kind in ("turnin", "accept"):
            ids = st.get(kind)
            if ids is None:
                continue
            ids = ids if isinstance(ids, list) else [ids]
            field_ = "startedBy" if kind == "accept" else "finishedBy"
            pos, who, npc_id = self.endpoint(ids[0], field_)
            if kind == "turnin" and "accept" in st and st.get("_turnin_first") is None:
                pass
            self.goto(pos)
            if who and npc_id and f"    .target {who}" not in self.lines[self._step_start:]:
                self.lines.append(f"    .target {who}")
            for qid in ids:
                self.check_eligible(qid) if kind == "accept" else None
                if kind == "accept":
                    if len(self.s.log) >= QUEST_LOG_MAX:
                        self.warn("quest log is full (20)")
                    self.s.log.add(qid)
                    self.lines.append(f"    .accept {qid} >> Accept {self.name(qid)}")
                else:
                    if qid not in self.s.log:
                        self.warn(f"turning in {qid} {self.name(qid)} that was never accepted")
                    self.s.log.discard(qid)
                    self.s.done.add(qid)
                    q = self.q(qid)
                    xp_base = (self.d.xp.get(qid) or [0, 0])[1]
                    gained = quest_xp_at(xp_base, self.s.level, q.get("questLevel") or 1)
                    self.s.add_xp(gained)
                    self.lines.append(f"    .turnin {qid} >> Turn in {self.name(qid)}")
                    self.quest_stats.setdefault(qid, {"xp": 0, "seconds": 0})["xp"] += gained
                self.s.seconds += DIALOG_SEC

        if "complete" in st:
            ids = st["complete"] if isinstance(st["complete"], list) else [st["complete"]]
            for qid in ids:
                if qid not in self.s.log:
                    self.warn(f"completing {qid} {self.name(qid)} before accepting it")
                start_t = self.s.seconds
                objectives = self.objective_points(qid)
                if not objectives:
                    self.lines.append(f"    .complete {qid},1")
                for idx, (kind, oid, oname, pts, count, mlvl) in enumerate(objectives, 1):
                    where = self.nearest(pts)
                    if not where and st.get("where"):
                        # the route names the spot for objectives Questie has no location for
                        w = st["where"]
                        where = (int(w[0]), float(w[1]), float(w[2]))
                    if where:
                        self.goto(where)
                    else:
                        self.warn(f"no location known for {oname or oid} ({qid} {self.name(qid)})")
                    self.lines.append(f"    .complete {qid},{idx}")
                    if kind in ("kill", "loot") and oname and kind == "kill":
                        self.lines.append(f"    .mob {oname}")
                    kills = count if kind == "kill" else math.ceil(count / DEFAULT_DROP_RATE) if kind == "loot" else 0
                    if kind == "loot" and where:
                        near = []
                        for nid in as_list((self.d.item(oid) or {}).get("npcDrops")):
                            n = self.d.npc(nid)
                            if not n:
                                continue
                            d_min = min((self.distance(where, p) for p in self.d.spawns(n)), default=1e9)
                            if d_min < 250:
                                near.append((d_min, n["name"]))
                        for _, nm in sorted(set(near))[:3]:
                            self.lines.append(f"    .mob {nm}")
                    for _ in range(kills):
                        self.s.add_xp(mob_xp(self.s.level, mlvl or self.s.level))
                    self.s.seconds += kills * KILL_SEC + (count * LOOT_OBJECT_SEC if kind == "object" else 0)
                self.quest_stats.setdefault(qid, {"xp": 0, "seconds": 0})["seconds"] += self.s.seconds - start_t

        if "travel" in st:
            # Zeppelin/boat/long flight: reposition without counting running or kills.
            self.lines.append(f"    >>{st['travel']}")
            self.s.seconds += st.get("travel_seconds", 180)
            if st.get("travel_to"):
                t_ = st["travel_to"]
                self.s.pos = (int(t_[0]), float(t_[1]), float(t_[2]))

        for cmd in ("home", "hs", "fp", "fly", "train", "tame", "vendor", "trainer"):
            if cmd in st:
                val = st[cmd]
                if cmd == "hs":
                    self.lines.append(f"    .hs >> Hearth to {val}")
                    self.s.seconds += 15
                    if st.get("hs_to"):
                        h = st["hs_to"]
                        self.s.pos = (int(h[0]), float(h[1]), float(h[2]))
                elif cmd == "home":
                    self.lines.append(f"    .home >> Set your Hearthstone to {val}")
                elif cmd == "fly":
                    self.lines.append(f"    .fly {val} >> Fly to {val}")
                    self.s.seconds += st.get("fly_seconds", 120)
                    if st.get("fly_to"):
                        f_ = st["fly_to"]
                        self.s.pos = (int(f_[0]), float(f_[1]), float(f_[2]))
                elif cmd == "fp":
                    self.lines.append(f"    .fp {val} >> Get the {val} flight path")
                elif cmd == "tame":
                    self.lines.append(f"    .tame {val}")
                    self.s.seconds += 30
                elif cmd == "train":
                    self.lines.append(f"    .trainer >> Train your class spells")
                    self.s.seconds += 20

        if "xp" in st:
            target = float(st["xp"])
            self.lines.append(f"    .xp {st['xp']} >> Grind to level {st['xp']}")
            while self.s.level_float < target:
                self.s.add_xp(mob_xp(self.s.level, self.s.level))
                self.s.seconds += KILL_SEC

        if st.get("text"):
            self.lines.append(f"    >>{st['text']}")
        if self.lines[-1].startswith("step"):
            self.lines.pop()
            return

        xp_total = self.s.xp + sum(XP_TO_NEXT[l] for l in range(1, self.s.level))
        self.report.append((self.step_no, self.s.level_float, self.s.seconds / 60,
                            (xp_total - xp0), self.s.seconds - t0, self._summary(st)))

    def _summary(self, st):
        parts = []
        for k in ("accept", "complete", "turnin"):
            if k in st:
                ids = st[k] if isinstance(st[k], list) else [st[k]]
                parts.append(f"{k} " + ", ".join(self.name(i) for i in ids))
        for k in ("home", "hs", "fly", "fp", "train", "xp", "goto"):
            if k in st and k not in ("goto",):
                parts.append(f"{k} {st[k]}")
        return "; ".join(parts) or st.get("text", "")

    # ------------------------------------------------------------------- run
    def run(self):
        g = self.spec["guide"]
        head = [f"#version {g.get('version', 1)}", "#forever", f"#group {g.get('group', 'ForeverXP')}",
                f"<< Horde" if g.get("faction", "Horde") == "Horde" else "<< Alliance",
                f"#defaultfor {g['for']}" if g.get("for") else None,
                f"#name {g['name']}", f"#next {g['next']}" if g.get("next") else None,
                f"#displayname {g['display']}" if g.get("display") else None]
        self.lines = [h for h in head if h]
        if g.get("start"):
            s = g["start"]
            self.s.pos = (int(s[0]), float(s[1]), float(s[2]))
        for i, st in enumerate(self.spec["steps"], 1):
            self.step_no = i
            self.emit_step(st)
        return "\n".join(self.lines) + "\n"


def lua_long_string(text):
    level = 0
    while ("]" + "=" * level + "]") in text:
        level += 1
    eq = "=" * level
    return f"[{eq}[\n{text}]{eq}]"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("routes", nargs="+")
    ap.add_argument("--out", default=str(ROOT / "guides/ForeverXP_Guides"))
    ap.add_argument("--report", default=str(ROOT / "reports"))
    ap.add_argument("--strict", action="store_true", help="exit non-zero on any warning")
    a = ap.parse_args()
    data = Data()
    out_dir, rep_dir = Path(a.out), Path(a.report)
    out_dir.mkdir(parents=True, exist_ok=True)
    rep_dir.mkdir(parents=True, exist_ok=True)
    files, total_issues = [], 0
    carry = None
    for route in a.routes:
        spec = yaml.safe_load(Path(route).read_text())
        gen = Generator(data, spec)
        if carry and not spec["guide"].get("start_level"):
            gen.s.level, gen.s.xp, gen.s.pos = carry.level, carry.xp, carry.pos
            gen.s.done, gen.s.log = set(carry.done), set(carry.log)
        text = gen.run()
        carry = gen.s
        stem = Path(route).stem
        lua = f"-- Generated by tools/guidegen.py from routes/{Path(route).name}. Do not edit by hand.\n" \
              f"RXPGuides.RegisterGuide({lua_long_string(text)})\n"
        (out_dir / f"{stem}.lua").write_text(lua)
        files.append(f"{stem}.lua")
        # report
        rows = ["| # | level | minutes | xp | step |", "|---|---|---|---|---|"]
        for n, lvl, mins, dxp, secs, summ in gen.report:
            rows.append(f"| {n} | {lvl:.2f} | {mins:.1f} | {dxp} | {summ} |")
        qrows = ["| quest | xp | minutes spent on objectives | xp/min |", "|---|---|---|---|"]
        for qid, st in sorted(gen.quest_stats.items(), key=lambda kv: -(kv[1]['xp'] / max(kv[1]['seconds'], 30))):
            mins = st["seconds"] / 60
            qrows.append(f"| {qid} {gen.name(qid)} | {st['xp']} | {mins:.1f} | {st['xp'] / max(mins, 0.5):.0f} |")
        issues = gen.s.issues
        total_issues += len(issues)
        (rep_dir / f"{stem}.md").write_text(
            f"# {spec['guide']['name']}\n\nEstimated finish: level {gen.s.level_float:.2f} after "
            f"{gen.s.seconds / 60:.0f} minutes. Quests still in log: {sorted(gen.s.log)}\n\n"
            "Estimates use Classic XP rules and generic kill/travel times until ForeverScout logs "
            "replace them with measured values.\n\n"
            "## Issues\n\n" + ("\n".join(f"- {i}" for i in issues) or "_none_") +
            "\n\n## Quests by XP per minute of objective time\n\n" + "\n".join(qrows) +
            "\n\n## Step by step\n\n" + "\n".join(rows) + "\n")
        print(f"{stem}: level {gen.s.level_float:.2f}, {gen.s.seconds / 60:.0f} min, {len(issues)} issues")
        for i in issues:
            print("  !", i)
    return 1 if (a.strict and total_issues) else 0


if __name__ == "__main__":
    sys.exit(main())

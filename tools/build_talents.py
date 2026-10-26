"""Build the talent calculator data from the WoW Forever game client.

WoW Forever keeps its talents in the modern trait tables (TraitTree, TraitNode, TraitNodeEntry,
TraitDefinition, TraitEdge, TraitCond ...), the same system retail's talent screen uses. The old
`Talent` table is still in the client, but it holds Classic Era's talents, not Forever's. So:

  - Forever talents: trait tables + Spell tables of the Forever build, with Blizzard's server
    hotfixes for that build applied on top (the game patches talents with hotfixes between builds).
  - Classic Era talents: the `Talent` table of the Classic Era build, for the "what changed" list.

Everything comes from wago.tools DB2 exports. Everything read here is third-party data: it is
parsed as CSV/JSON only, numbers are coerced, and the tooltip formatter evaluates Blizzard's
`${...}` arithmetic with its own small parser (never eval). The site escapes all text it shows.

Usage:
  python3 tools/build_talents.py --download --hotfixes --cache .cache/wago --out gamedata/talents.json
"""
import argparse
import csv
import html
import json
import math
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

WAGO = "https://wago.tools"
UA = {"User-Agent": "forever-xp data build (github.com/Jweyant/forever-xp)"}
FOREVER_BUILD = "1.60.1.70532"
CLASSIC_BUILD = "1.15.9.70003"

TRAIT_TABLES = ["TraitTree", "TraitNode", "TraitNodeEntry", "TraitDefinition", "TraitEdge", "TraitCond",
                "TraitNodeGroupXTraitNode", "TraitNodeGroupXTraitCond", "TraitNodeXTraitNodeEntry",
                "TraitNodeXTraitCond", "TraitDefinitionEffectPoints", "CurvePoint", "SkillLineXTraitTree"]
SPELL_TABLES = ["Spell", "SpellName", "SpellEffect", "SpellMisc", "SpellDuration", "SpellRadius", "SpellAuraOptions"]
FOREVER_TABLES = TRAIT_TABLES + SPELL_TABLES + ["TalentTab"]
CLASSIC_TABLES = ["Talent", "TalentTab"] + SPELL_TABLES

# Class trait trees are tied to the class's skill line. These are the classic class skill lines.
SKILL_CLASS = {26: 1, 184: 2, 50: 3, 38: 4, 613: 5, 373: 7, 237: 8, 354: 9, 574: 11}
CLASS_NAME = {1: "Warrior", 2: "Paladin", 3: "Hunter", 4: "Rogue", 5: "Priest", 7: "Shaman", 8: "Mage",
              9: "Warlock", 11: "Druid"}
# Tree header icons (the game's talent tab icons), checked against render.worldofwarcraft.com.
TREE_ICON = {
    ("Warrior", "Arms"): "ability_warrior_savageblow", ("Warrior", "Fury"): "ability_warrior_innerrage",
    ("Warrior", "Protection"): "ability_warrior_defensivestance",
    ("Paladin", "Holy"): "spell_holy_holybolt", ("Paladin", "Protection"): "spell_holy_devotionaura",
    ("Paladin", "Retribution"): "spell_holy_auraoflight",
    ("Hunter", "Beast Mastery"): "ability_hunter_beasttaming", ("Hunter", "Marksmanship"): "ability_marksmanship",
    ("Hunter", "Survival"): "ability_hunter_swiftstrike",
    ("Rogue", "Assassination"): "ability_rogue_eviscerate", ("Rogue", "Combat"): "ability_backstab",
    ("Rogue", "Subtlety"): "ability_stealth",
    ("Priest", "Discipline"): "spell_holy_wordfortitude", ("Priest", "Holy"): "spell_holy_guardianspirit",
    ("Priest", "Shadow"): "spell_shadow_shadowwordpain",
    ("Shaman", "Elemental"): "spell_nature_lightning", ("Shaman", "Enhancement"): "spell_nature_lightningshield",
    ("Shaman", "Restoration"): "spell_nature_magicimmunity",
    ("Mage", "Arcane"): "spell_holy_magicalsentry", ("Mage", "Fire"): "spell_fire_firebolt02",
    ("Mage", "Frost"): "spell_frost_frostbolt02",
    ("Warlock", "Affliction"): "spell_shadow_deathcoil", ("Warlock", "Demonology"): "spell_shadow_metamorphosis",
    ("Warlock", "Destruction"): "spell_shadow_rainoffire",
    ("Druid", "Balance"): "spell_nature_starfall", ("Druid", "Feral Combat"): "ability_racial_bearform",
    ("Druid", "Restoration"): "spell_nature_healingtouch",
}
GRID = 600          # trait node spacing in the client's tree coordinates
SECTION = 4000      # each spec tree sits 4000 units to the right of the previous one
LEFT = 1020         # x of column 0 in the first spec tree


# ---------------------------------------------------------------- loading

def fetch(url, timeout=180):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout).read()


def load(cache, build, table, download):
    """One DB2 table of one build as a list of dicts (all values are strings)."""
    path = Path(cache) / build / f"{table}.csv"
    if not path.exists():
        if not download:
            raise SystemExit(f"missing {path}; run with --download")
        data = fetch(f"{WAGO}/db2/{table}/csv?build={urllib.parse.quote(build)}")
        if data[:1] in (b"{", b"<"):
            raise SystemExit(f"wago.tools refused {table} for {build}: {data[:120]!r}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def header(cache, build, table):
    with (Path(cache) / build / f"{table}.csv").open(encoding="utf-8", newline="") as f:
        return next(csv.reader(f))


def icon_names(cache, download):
    """IconFileDataID -> icon name, from wago.tools' listfile (shared with tools/build_items.py)."""
    path = Path(cache) / "icons.json"
    if not path.exists():
        if not download:
            return {}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(fetch(f"{WAGO}/api/files?search=interface/icons/"))
    raw = json.loads(path.read_text())
    out = {}
    for k, v in raw.items():
        if isinstance(v, str) and v.startswith("interface/icons/"):
            name = v.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()
            if re.fullmatch(r"[a-z0-9_-]+", name):
                out[int(k)] = name
    return out


def num(v, cast=float):
    try:
        return cast(v)
    except (TypeError, ValueError):
        try:
            return cast(float(v))
        except (TypeError, ValueError):
            return cast(0)


# ---------------------------------------------------------------- hotfixes

DATA_PAGE = re.compile(r'data-page="([^"]+)"')


def hotfix_pages(build, table, max_pages=400):
    """Every hotfix wago.tools has seen for this build and table, oldest push first."""
    rows, page = [], 1
    search = f"{build.rsplit('.', 1)[-1]} {table.lower()} ["
    while page <= max_pages:
        url = f"{WAGO}/hotfixes?{urllib.parse.urlencode({'search': search, 'page': page})}"
        m = DATA_PAGE.search(fetch(url, timeout=60).decode("utf-8", "replace"))
        if not m:
            raise SystemExit(f"wago.tools hotfix page for {table} had no data")
        hot = json.loads(html.unescape(m.group(1)))["props"]["hotfixes"]
        rows += [h for h in hot.get("data", []) if isinstance(h, dict)]
        if page >= int(hot.get("last_page") or 1):
            break
        page += 1
        time.sleep(0.4)  # be polite to wago.tools
    want = int(build.rsplit(".", 1)[-1])
    rows = [h for h in rows if h.get("table_name", "").lower() == table.lower() and num(h.get("build"), int) == want
            and h.get("locale") == "enUS"]
    rows.sort(key=lambda h: (num(h.get("push_id"), int), num(h.get("id"), int)))
    return rows


def flatten(v):
    if isinstance(v, list):
        for x in v:
            yield from flatten(x)
    else:
        yield v


def apply_hotfixes(rows, cols, fixes, report, table):
    """Apply hotfix rows to a table. Status 1 adds or replaces a record, 2 removes it, 3 cancels an
    earlier hotfix (back to the client's record), 4 is not public."""
    if "ID" not in cols:
        return rows
    client = {r["ID"]: r for r in rows}
    live = dict(client)
    applied = skipped = 0
    for h in fixes:
        rid = str(num(h.get("record_id"), int))
        status = num(h.get("status"), int)
        if status == 1:
            flat = ["" if x is None else str(x) for x in flatten(h.get("data", []))]
            if len(flat) != len(cols):
                skipped += 1
                continue
            rec = dict(zip(cols, flat))
            rec["ID"] = rid
            live[rid] = rec
        elif status == 2:
            live.pop(rid, None)
        elif status == 3:
            if rid in client:
                live[rid] = client[rid]
            else:
                live.pop(rid, None)
        else:
            continue
        applied += 1
    report.append(f"{table}: {applied} hotfixes applied" + (f", {skipped} skipped (column mismatch)" if skipped else ""))
    return list(live.values())


# ---------------------------------------------------------------- spell text

class Spells:
    """Spell lookups for one build, and Blizzard tooltip text -> plain text."""

    def __init__(self, T):
        self.name = {r["ID"]: r.get("Name_lang", "") for r in T["SpellName"]}
        self.desc = {r["ID"]: r.get("Description_lang", "") for r in T["Spell"]}
        self.eff = {}
        for e in T["SpellEffect"]:
            if e.get("DifficultyID", "0") in ("0", ""):
                self.eff[(e["SpellID"], num(e.get("EffectIndex"), int))] = e
        self.misc = {}
        for m in T["SpellMisc"]:
            if m.get("DifficultyID", "0") in ("0", "") and m.get("SpellID"):
                self.misc[m["SpellID"]] = m
        self.dur = {r["ID"]: num(r.get("Duration")) for r in T["SpellDuration"]}
        self.rad = {r["ID"]: num(r.get("Radius")) for r in T["SpellRadius"]}
        self.aura = {}
        for a in T["SpellAuraOptions"]:
            if a.get("DifficultyID", "0") in ("0", "") and a.get("SpellID"):
                self.aura[a["SpellID"]] = a
        self.unknown = defaultdict(int)

    def icon_id(self, sid):
        return num(self.misc.get(sid, {}).get("SpellIconFileDataID"), int)

    def base(self, sid, i):
        e = self.eff.get((sid, i))
        if not e:
            return 0.0
        v = e.get("EffectBasePointsF")
        return num(v) if v not in (None, "") else num(e.get("EffectBasePoints"))

    def duration_ms(self, sid):
        return self.dur.get(self.misc.get(sid, {}).get("DurationIndex", ""), 0.0)

    # value(sid, i) may be overridden per rank for the talent's own spell
    def render(self, sid, value=None, depth=0):
        text = self.desc.get(sid, "") or ""
        value = value or (lambda s, i: self.base(s, i))
        return Tooltip(self, sid, value, depth).run(text)


def fmt_num(v, dec=None):
    if dec is not None:
        return f"{abs(v):.{dec}f}"
    v = abs(v)
    if abs(v - round(v)) < 1e-6:
        return str(int(round(v)))
    return f"{v:.2f}".rstrip("0").rstrip(".")


def fmt_dur(ms):
    s = abs(ms) / 1000
    if s >= 3600 and s % 3600 == 0:
        return f"{int(s // 3600)} hr"
    if s >= 60 and s % 60 == 0:
        return f"{int(s // 60)} min"
    return f"{fmt_num(s)} sec"


class Expr:
    """Tiny arithmetic parser for ${...}: numbers, + - * /, parentheses, comparisons and a few
    functions. Anything else is an error (the caller then shows the raw text)."""
    FUNCS = {"max": max, "min": min, "floor": math.floor, "ceil": math.ceil, "abs": abs, "round": round,
             "gt": lambda a, b: float(a > b), "lt": lambda a, b: float(a < b), "gte": lambda a, b: float(a >= b),
             "lte": lambda a, b: float(a <= b), "eq": lambda a, b: float(a == b),
             "cond": lambda c, a, b=0.0: a if c else b, "clamp": lambda v, a, b: min(max(v, a), b)}
    TOK = re.compile(r"\s*(?:(\d+(?:\.\d+)?)|([A-Za-z_]+)|(<=|>=|==|!=|[-+*/(),<>?:]))")

    def __init__(self, s):
        self.toks, pos = [], 0
        while pos < len(s):
            m = self.TOK.match(s, pos)
            if not m or m.end() == pos:
                if s[pos:].strip() == "":
                    break
                raise ValueError(f"bad token at {s[pos:pos + 10]!r}")
            self.toks.append(m.group(1) and ("n", float(m.group(1))) or m.group(2) and ("f", m.group(2).lower())
                             or ("o", m.group(3)))
            pos = m.end()
        self.i = 0

    def eval(self):
        v = self.cmp()
        if self.i != len(self.toks):
            raise ValueError("trailing tokens")
        return v

    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else (None, None)

    def take(self, op):
        if self.peek() == ("o", op):
            self.i += 1
            return True
        return False

    def cmp(self):
        v = self.add()
        while True:
            for op, f in (("<=", lambda a, b: a <= b), (">=", lambda a, b: a >= b), ("<", lambda a, b: a < b),
                          (">", lambda a, b: a > b), ("==", lambda a, b: a == b), ("!=", lambda a, b: a != b)):
                if self.take(op):
                    v = float(f(v, self.add()))
                    break
            else:
                return v

    def add(self):
        v = self.mul()
        while True:
            if self.take("+"):
                v += self.mul()
            elif self.take("-"):
                v -= self.mul()
            else:
                return v

    def mul(self):
        v = self.unary()
        while True:
            if self.take("*"):
                v *= self.unary()
            elif self.take("/"):
                d = self.unary()
                v = v / d if d else 0.0
            else:
                return v

    def unary(self):
        if self.take("-"):
            return -self.unary()
        if self.take("+"):
            return self.unary()
        kind, val = self.peek()
        if kind == "n":
            self.i += 1
            return val
        if kind == "f" and val in self.FUNCS:
            self.i += 1
            if not self.take("("):
                raise ValueError("expected (")
            args = [self.cmp()]
            while self.take(","):
                args.append(self.cmp())
            if not self.take(")"):
                raise ValueError("expected )")
            return float(self.FUNCS[val](*args))
        if self.take("("):
            v = self.cmp()
            if not self.take(")"):
                raise ValueError("expected )")
            return v
        raise ValueError(f"unexpected {val!r}")


VAR = re.compile(r"(\d*)([a-zA-Z])(\d?)")
STAT_VARS = {"pl": 60, "PL": 60, "lvl": 60, "LVL": 60}


class Tooltip:
    def __init__(self, spells, sid, value, depth):
        self.S, self.sid, self.value, self.depth = spells, sid, value, depth

    def var(self, spell, letter, idx):
        S = self.S
        sid = spell or self.sid
        i = max(0, (int(idx) if idx else 1) - 1)
        val = self.value if sid == self.sid else (lambda s, k: S.base(s, k))
        if letter in "smMw":
            return val(sid, i)
        if letter == "o":
            e = S.eff.get((sid, i), {})
            period = num(e.get("EffectAuraPeriod"))
            dur = S.duration_ms(sid)
            return val(sid, i) * (dur / period) if period else val(sid, i)
        if letter == "t":
            return num(S.eff.get((sid, i), {}).get("EffectAuraPeriod")) / 1000
        if letter in "aA":
            e = S.eff.get((sid, i), {})
            return S.rad.get(e.get("EffectRadiusIndex_0", ""), 0.0)
        if letter == "h":
            return num(S.aura.get(sid, {}).get("ProcChance"))
        if letter == "u":
            return num(S.aura.get(sid, {}).get("CumulativeAura"))
        if letter == "n":
            return num(S.aura.get(sid, {}).get("ProcCharges"))
        if letter == "x":
            return num(S.eff.get((sid, i), {}).get("EffectChainTargets"))
        if letter == "e":
            return num(S.eff.get((sid, i), {}).get("EffectAmplitude"))
        if letter == "b":
            return num(S.eff.get((sid, i), {}).get("EffectPointsPerResource"))
        if letter == "q":
            return num(S.eff.get((sid, i), {}).get("EffectMiscValue_0"))
        if letter in "dD":
            return S.duration_ms(sid)
        raise KeyError(letter)

    def run(self, text):
        out, i = [], 0
        while i < len(text):
            c = text[i]
            if c != "$":
                out.append(c)
                i += 1
                continue
            m = re.match(r"\$([lL])([^:;]*):([^;]*);", text[i:])
            if m:  # singular:plural; follows the last number shown
                nums_before = re.findall(r"\d+(?:\.\d+)?", "".join(out))
                one = bool(nums_before) and abs(float(nums_before[-1]) - 1) < 1e-9
                out.append(m.group(2) if one else m.group(3))
                i += m.end()
                continue
            j, piece = self.token(text, i)
            out.append(piece)
            i = j
        return re.sub(r"[ \t]+", " ", "".join(out)).replace("\r", "").strip()

    def bracket(self, text, i):
        """text[i] == '[' -> (end index after ']', inner text), with nesting."""
        depth, j = 0, i
        while j < len(text):
            if text[j] == "[":
                depth += 1
            elif text[j] == "]":
                depth -= 1
                if depth == 0:
                    return j + 1, text[i + 1:j]
            j += 1
        return len(text), text[i + 1:]

    def token(self, text, i):
        rest = text[i + 1:]
        # $?cond[a][b]  (chains: $?c1[a]?c2[b][c]). We don't know the player's state, so we show
        # the final "otherwise" text, which describes the talent on its own.
        if rest.startswith("?"):
            j = i + 2
            branches = []
            while j < len(text):
                k = text.find("[", j)
                if k < 0:
                    break
                j, inner = self.bracket(text, k)
                branches.append(inner)
                if j < len(text) and text[j] == "?":
                    j += 1
                    continue
                if j < len(text) and text[j] == "[":
                    j, inner = self.bracket(text, j)
                    branches.append(inner)
                break
            pick = branches[-1] if len(branches) >= 2 else ""
            return j, self.run(pick)
        m = re.match(r"\{(.*?)\}(?:\.(\d))?", rest, re.S)
        if m and rest.startswith("{"):
            inner = re.sub(r"\$(\w+)", lambda mm: self.expr_var(mm.group(1)), m.group(1))
            try:
                v = Expr(inner).eval()
                return i + 1 + m.end(), fmt_num(v, int(m.group(2)) if m.group(2) else None)
            except (ValueError, TypeError, ZeroDivisionError, OverflowError):
                self.S.unknown["expr"] += 1
                return i + 1 + m.end(), "?"
        m = re.match(r"([/*])([\d.]+);(\d*)([a-zA-Z])(\d?)", rest)
        if m:
            try:
                v = self.var(m.group(3), m.group(4), m.group(5))
            except KeyError:
                self.S.unknown[m.group(4)] += 1
                return i + 1 + m.end(), "?"
            f = float(m.group(2)) or 1.0
            v = v / f if m.group(1) == "/" else v * f
            return i + 1 + m.end(), fmt_num(v)
        m = re.match(r"@(spelldesc|spelltooltip|spellname|spellaura|spellicon)(\d+)", rest)
        if m:
            sid = m.group(2)
            if m.group(1) == "spellname":
                return i + 1 + m.end(), self.S.name.get(sid, "")
            if m.group(1) in ("spelldesc", "spelltooltip") and self.depth < 3:
                return i + 1 + m.end(), self.S.render(sid, depth=self.depth + 1)
            return i + 1 + m.end(), ""
        m = re.match(r"([gG])([^:;]*):([^;]*);", rest)
        if m:
            return i + 1 + m.end(), m.group(2)
        m = re.match(r"<\w+>", rest)
        if m:
            self.S.unknown["<var>"] += 1
            return i + 1 + m.end(), "?"
        m = VAR.match(rest)
        if m and (m.group(2) in "smMwotaAhunxebqdD"):
            spell, letter, idx = m.groups()
            try:
                v = self.var(spell, letter, idx)
            except KeyError:
                self.S.unknown[letter] += 1
                return i + 1 + m.end(), "?"
            if letter in "dD":
                return i + 1 + m.end(), fmt_dur(v)
            return i + 1 + m.end(), fmt_num(v)
        if m:
            self.S.unknown[m.group(2)] += 1
            return i + 1 + m.end(), "?"
        return i + 1, "$"

    def expr_var(self, name):
        if name in STAT_VARS:
            return str(STAT_VARS[name])
        m = re.fullmatch(r"(\d*)([a-zA-Z])(\d?)", name)
        if m:
            try:
                return repr(float(self.var(*m.groups())))
            except KeyError:
                pass
        if name.lower() in Expr.FUNCS:
            return name.lower()
        self.S.unknown[f"${name}"] += 1
        return "0"


def pack(texts):
    """Per-rank texts -> [template, values per rank] when only numbers differ, [text, 0] when every
    rank reads the same, else [[texts]] (the formats talents.ts understands)."""
    if all(t == texts[0] for t in texts):
        return [texts[0], 0]
    parts = [re.split(r"(\d+(?:\.\d+)?)", t) for t in texts]
    if len({len(p) for p in parts}) == 1 and all(p[k] == parts[0][k] for p in parts for k in range(0, len(parts[0]), 2)):
        tmpl, idx, cols = [], 0, []
        for k, piece in enumerate(parts[0]):
            if k % 2 == 0:
                tmpl.append(piece.replace("{", "(").replace("}", ")"))
                continue
            vals = [p[k] for p in parts]
            if all(v == vals[0] for v in vals):
                tmpl.append(vals[0])
            else:
                tmpl.append("{%d}" % idx)
                cols.append([float(v) for v in vals])
                idx += 1
        return ["".join(tmpl), [[c[r] for c in cols] for r in range(len(texts))]]
    return [texts]


# ---------------------------------------------------------------- Forever (trait tables)

def forever_talents(T, S, icons, report):
    defs = {r["ID"]: r for r in T["TraitDefinition"]}
    entries = {r["ID"]: r for r in T["TraitNodeEntry"]}
    node_entries = defaultdict(list)
    for r in sorted(T["TraitNodeXTraitNodeEntry"], key=lambda r: num(r.get("_Index"), int)):
        node_entries[r["TraitNodeID"]].append(r["TraitNodeEntryID"])
    curve = defaultdict(list)
    for p in T["CurvePoint"]:
        curve[p["CurveID"]].append((num(p["Pos_0"]), num(p["Pos_1"])))
    points = {}
    for r in T["TraitDefinitionEffectPoints"]:
        if num(r.get("OperationType"), int) == 0:
            points[(r["TraitDefinitionID"], num(r["EffectIndex"], int))] = sorted(curve.get(r["CurveID"], []))
    # Tier requirements: node -> node groups -> conditions "spend N points".
    groups = defaultdict(list)
    for r in T["TraitNodeGroupXTraitNode"]:
        groups[r["TraitNodeID"]].append(r["TraitNodeGroupID"])
    group_conds = defaultdict(list)
    for r in T["TraitNodeGroupXTraitCond"]:
        group_conds[r["TraitNodeGroupID"]].append(r["TraitCondID"])
    node_conds = defaultdict(list)
    for r in T.get("TraitNodeXTraitCond", []):
        node_conds[r.get("TraitNodeID")].append(r.get("TraitCondID"))
    conds = {r["ID"]: r for r in T["TraitCond"]}
    edges = defaultdict(list)
    for e in T["TraitEdge"]:
        edges[e["RightTraitNodeID"]].append(e["LeftTraitNodeID"])
    tabs = defaultdict(list)
    for t in T["TalentTab"]:
        if t.get("Name_lang"):
            tabs[num(t["ClassMask"], int)].append((num(t["OrderIndex"], int), t["ID"], t["Name_lang"]))
    tree_class = {}
    for r in T["SkillLineXTraitTree"]:
        cid = SKILL_CLASS.get(num(r["SkillLineID"], int))
        if cid:
            tree_class[r["TraitTreeID"]] = cid
    if sorted(tree_class.values()) != sorted(SKILL_CLASS.values()):
        raise SystemExit(f"expected one trait tree per class, got {tree_class}")

    def curve_at(pts, rank):
        for x, y in pts:
            if abs(x - rank) < 1e-6:
                return y
        if not pts:
            return None
        lo = [p for p in pts if p[0] <= rank]
        hi = [p for p in pts if p[0] >= rank]
        if lo and hi:
            (x0, y0), (x1, y1) = lo[-1], hi[0]
            return y0 if x1 == x0 else y0 + (y1 - y0) * (rank - x0) / (x1 - x0)
        return (lo or hi)[-1 if lo else 0][1]

    classes, estimated, multi_prereq = [], 0, 0
    for tree_id, cid in sorted(tree_class.items(), key=lambda kv: kv[1]):
        cname = CLASS_NAME[cid]
        names = [n for _, _, n in sorted(tabs[1 << (cid - 1)])]
        tab_ids = [i for _, i, _ in sorted(tabs[1 << (cid - 1)])]
        if len(names) != 3:
            raise SystemExit(f"{cname}: expected 3 talent tabs, got {names}")
        nodes = [n for n in T["TraitNode"] if n["TraitTreeID"] == tree_id]
        top = min(num(n["PosY"], int) for n in nodes)
        sections = [[] for _ in range(3)]
        for n in nodes:
            x, y = num(n["PosX"], int), num(n["PosY"], int)
            sec = (x - LEFT + GRID) // SECTION
            col = round((x - LEFT - sec * SECTION) / GRID)
            row = round((y - top) / GRID)
            if not 0 <= sec < 3:
                # Nodes parked far outside the three trees aren't shown in the game's talent frame.
                report.append(f"{cname}: node {n['ID']} at ({x},{y}) is outside the three trees; skipped")
                continue
            if not (0 <= col <= 3 and 0 <= row <= 10):
                raise SystemExit(f"{cname}: node {n['ID']} at ({x},{y}) is off the 3x4 grid")
            ents = [entries[e] for e in node_entries.get(n["ID"], []) if e in entries]
            if not ents:
                report.append(f"{cname}: node {n['ID']} has no entry; skipped")
                continue
            ent = ents[0]
            d = defs.get(ent["TraitDefinitionID"], {})
            sid = d.get("SpellID", "")
            name = d.get("OverrideName_lang") or S.name.get(sid, "")
            if not name:
                report.append(f"{cname}: node {n['ID']} has no name; skipped")
                continue
            ranks = max(1, num(ent.get("MaxRanks"), int))
            icon_id = num(d.get("OverrideIcon"), int) or S.icon_id(sid)
            icon = icons.get(icon_id)
            if not icon:
                report.append(f"{cname}: no icon file for {name} (file {icon_id})")
            need = 0
            for g in groups.get(n["ID"], []):
                for c in group_conds.get(g, []):
                    need = max(need, num(conds.get(c, {}).get("SpentAmountRequired"), int))
            for c in node_conds.get(n["ID"], []):
                need = max(need, num(conds.get(c, {}).get("SpentAmountRequired"), int))
            def_id = d.get("ID", "")
            est = False
            texts = []
            for r in range(1, ranks + 1):
                def value(s, i, r=r):
                    pts = points.get((def_id, i))
                    if pts:
                        v = curve_at(pts, r)
                        if v is not None:
                            return v
                    return S.base(s, i) * (r if ranks > 1 else 1)
                if d.get("OverrideDescription_lang"):
                    texts.append(Tooltip(S, sid, value, 0).run(d["OverrideDescription_lang"]))
                else:
                    texts.append(S.render(sid, value))
            if ranks > 1 and not any((def_id, i) in points for i in range(8)):
                est = True
                estimated += 1
            prereqs = edges.get(n["ID"], [])
            if len(prereqs) > 1:
                multi_prereq += 1
            sections[sec].append({"node": n["ID"], "row": row, "col": col, "name": name, "ranks": ranks,
                                  "req": prereqs[0] if prereqs else None, "icon": icon, "desc": pack(texts),
                                  "est": est, "need": need, "spell": num(sid, int), "def": def_id})
        trees = []
        for k, tals in enumerate(sections):
            seen = {}
            for t in tals:
                if (t["row"], t["col"]) in seen:
                    raise SystemExit(f"{cname} {names[k]}: {t['name']} and {seen[(t['row'], t['col'])]} share a spot")
                seen[(t["row"], t["col"])] = t["name"]
            tals.sort(key=lambda t: (t["row"], t["col"]))
            trees.append([num(tab_ids[k], int), names[k], tals])
        classes.append([cid, cname, trees])
    # Prerequisite ranks: the trait system wants the earlier talent fully learned.
    ranks_of = {t["node"]: t["ranks"] for c in classes for tr in c[2] for t in tr[2]}
    out = []
    for cid, cname, trees in classes:
        otrees = []
        for tab_id, tname, tals in trees:
            rows = []
            for t in tals:
                req = t["req"] if t["req"] in ranks_of else None
                rows.append([num(t["node"], int), t["row"], t["col"], t["name"], t["ranks"],
                             num(req, int) if req else None, ranks_of.get(req) if req else None,
                             t["icon"], t["desc"], int(t["est"]), t["need"], t["spell"]])
            otrees.append([tab_id, tname, TREE_ICON.get((cname, tname)), rows])
        out.append([cid, cname, otrees])
    report.append(f"Forever: {sum(len(tr[3]) for c in out for tr in c[2])} talents; {estimated} multi-rank talents "
                  f"without client rank values (scaled from rank 1); {multi_prereq} with more than one prerequisite")
    return out


# ---------------------------------------------------------------- Classic Era (Talent table)

def classic_talents(T, S):
    tabs = {r["ID"]: r for r in T["TalentTab"]}
    out = []
    for t in T["Talent"]:
        tab = tabs.get(t.get("TabID"))
        if not tab or not tab.get("Name_lang"):
            continue
        mask = num(tab.get("ClassMask"), int)
        cid = next((c for c in CLASS_NAME if mask == 1 << (c - 1)), None)
        if not cid:
            continue
        spells = [t.get(f"SpellRank_{k}") for k in range(9)]
        spells = [s for s in spells if s and s != "0"]
        if not spells:
            continue
        name = S.name.get(spells[0], "")
        if not name:
            continue
        out.append({"cls": CLASS_NAME[cid], "tree": tab["Name_lang"], "name": name, "ranks": len(spells),
                    "row": num(t.get("TierID"), int), "col": num(t.get("ColumnIndex"), int),
                    "text": S.render(spells[-1]), "spells": [num(s, int) for s in spells]})
    out.sort(key=lambda r: (r["cls"], r["tree"], r["row"], r["col"]))
    return out


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=".cache/wago")
    ap.add_argument("--download", action="store_true", help="fetch missing tables from wago.tools")
    ap.add_argument("--hotfixes", action="store_true", help="apply wago.tools' server hotfixes for the Forever build")
    ap.add_argument("--forever", default=FOREVER_BUILD)
    ap.add_argument("--classic", default=CLASSIC_BUILD)
    ap.add_argument("--out", default="gamedata/talents.json")
    args = ap.parse_args()

    report = []
    F = {t: load(args.cache, args.forever, t, args.download) for t in FOREVER_TABLES}
    if args.hotfixes:
        for t in FOREVER_TABLES:
            fixes = hotfix_pages(args.forever, t)
            if fixes:
                F[t] = apply_hotfixes(F[t], header(args.cache, args.forever, t), fixes, report, t)
    C = {t: load(args.cache, args.classic, t, args.download) for t in CLASSIC_TABLES}
    icons = icon_names(args.cache, args.download)
    SF, SC = Spells(F), Spells(C)
    forever = forever_talents(F, SF, icons, report)
    classic = classic_talents(C, SC)
    for label, S in (("Forever", SF), ("Classic", SC)):
        if S.unknown:
            report.append(f"{label} tooltip tokens shown as '?': " + ", ".join(f"{k} x{v}" for k, v in sorted(S.unknown.items())))
    data = {
        "builds": {"forever": args.forever, "classic": args.classic},
        "hotfixes": bool(args.hotfixes),
        "source": {"site": WAGO, "forever": "trait tables (TraitTree, TraitNode, TraitEdge, TraitCond, ...) and spells",
                   "classic": "Talent table and spells"},
        # [classId, class, [[tabId, tree, treeIcon, [[nodeId, row, col, name, ranks, prereqNodeId,
        #   prereqRank, icon, text, estimated, pointsNeeded, spellId], ...]], ...]]
        "talents": forever,
        "classic": classic,
        "report": report,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False))
    print("\n".join(report))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()

"""Collect Blizzard's official WoW Forever change notes into gamedata/blizzard-notes.json.

Source: posts by Blizzard staff on the official World of Warcraft forums (Discourse JSON API),
starting with the pinned "WoW Forever Beta Development Notes" thread. Each bullet becomes one row
with its date, section, class or race, any developer note, and a link back to the post, so the
site can show every change in one filterable table. Text stays Blizzard's; every row links to
the original post.

It also lists Blizzard's announcements: every topic a Blizzard employee started in a WoW Forever
forum category (name reservation, realm news, articles, podcasts), as a title, date, short plain
text excerpt and a link, for the site's News page. Announcements found before are kept
(--previous), since the forum's blue tracker only reaches back about a week.

Usage:
  python3 tools/blizzard_notes.py                      # fetch from the forums (GitHub Actions)
  python3 tools/blizzard_notes.py --from-dir snapshots  # parse saved <topic>.json files instead
"""
import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORUM = "https://us.forums.blizzard.com/en/wow"
UA = "forever-xp.com notes collector (+https://github.com/Jweyant/forever-xp)"

# Topics always collected. Discovery below adds new staff topics whose titles look like notes.
TOPICS = {
    2360696: "Development notes",   # WoW Forever Beta Development Notes
    2369360: "Development notes",   # Warrior Updates in Today's Beta Build
    2352687: "Known issues",        # WoW Forever Beta Known Issues
}
# Forum categories to watch for new staff notes. Each run looks up every category whose name or
# parent mentions Forever (so a new launch or bug-report category is picked up by itself); these
# are used if that lookup fails: 346 WoW: Forever, 347 General Discussion, 348 Community
# Connections, 349 Beta Discussion.
CATEGORIES = [346, 347, 348, 349]
CATEGORY_NAMES = {346: "WoW Forever", 347: "General Discussion", 348: "Community Connections", 349: "Beta Discussion"}
# BlizzardEntertainment posts the news site's articles to the forums.
STAFF = ["Kaivax", "Linxy", "Aggrend", "Blizzard", "BlizzardEntertainment"]
MAX_ANNOUNCEMENTS = 300
NOTE_TITLE = re.compile(r"(development notes|patch notes|release notes|launch notes|update notes|hotfix|known issues|"
                        r"bug fixes|class (changes|updates|tuning)|"
                        r"\b(warrior|paladin|hunter|rogue|priest|shaman|mage|warlock|druid) updates)", re.I)
# Official overview articles on the WoW website, listed on the changes page as further reading.
ARTICLES = [
    ("Rulesets: choose how your journey plays", "https://worldofwarcraft.blizzard.com/news/24302070/"),
    ("Dungeons in WoW Forever", "https://worldofwarcraft.blizzard.com/en-us/news/24301455"),
    ("The Campfire system", "https://worldofwarcraft.blizzard.com/en-us/news/24301516/"),
    ("Raids in WoW Forever", "https://worldofwarcraft.blizzard.com/en-us/news/24303009/"),
    ("Character creation and names", "https://worldofwarcraft.blizzard.com/en-us/news/24303866/"),
]

CLASSES = ["Warrior", "Paladin", "Hunter", "Rogue", "Priest", "Shaman", "Mage", "Warlock", "Druid"]
RACES = ["Human", "Dwarf", "Night Elf", "Gnome", "Orc", "Undead", "Tauren", "Troll", "Skyborne"]
SPECS = {"Arms", "Fury", "Protection", "Holy", "Retribution", "Beast Mastery", "Marksmanship", "Survival",
         "Assassination", "Combat", "Subtlety", "Discipline", "Shadow", "Elemental", "Enhancement",
         "Restoration", "Arcane", "Fire", "Frost", "Affliction", "Demonology", "Destruction", "Balance",
         "Feral", "Feral Combat", "Pets"}
DEV_NOTE = re.compile(r"^developers?[’']?\s*notes?\s*:\s*", re.I)


# --- a tiny DOM, enough for Discourse's "cooked" HTML -------------------------------------------
class Node:
    def __init__(self, tag, parent=None):
        self.tag, self.parent, self.kids = tag, parent, []

    def text(self, skip_lists=False):
        out = []
        for k in self.kids:
            if isinstance(k, str):
                out.append(k)
            elif skip_lists and k.tag in ("ul", "ol"):
                continue
            elif k.tag == "br":
                out.append(" ")
            else:
                out.append(k.text(skip_lists))
        return "".join(out)

    def find(self, tags):
        return [k for k in self.kids if isinstance(k, Node) and k.tag in tags]

    def bold(self):
        first = next((k for k in self.kids if not (isinstance(k, str) and not k.strip())), None)
        if isinstance(first, Node) and first.tag == "p":
            return first.bold()
        return isinstance(first, Node) and first.tag in ("strong", "b")


class Tree(HTMLParser):
    VOID = {"br", "img", "hr", "input", "meta", "link", "source"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root")
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        n = Node(tag, self.cur)
        self.cur.kids.append(n)
        if tag not in self.VOID:
            self.cur = n

    def handle_endtag(self, tag):
        n = self.cur
        while n is not self.root and n.tag != tag:
            n = n.parent
        if n is not self.root:
            self.cur = n.parent

    def handle_data(self, data):
        self.cur.kids.append(data)


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def tag_for(path, text):
    """Class, race and spec mentioned by the section path (or, failing that, the text)."""
    cls = next((c for c in CLASSES for p in path if p.lower() == c.lower()), None)
    race = next((r for r in RACES for p in path if p.lower() == r.lower()), None)
    spec = next((p for p in path if p in SPECS), None)
    if not cls:
        hits = [c for c in CLASSES if re.search(rf"\b{c}s?\b", text)]
        if len(hits) == 1:
            cls = hits[0]
    return cls, race, spec


def looks_like_group(li, label, kids):
    if not kids:
        return False
    if li.bold():
        return True
    return len(label) <= 48 and not label.endswith((".", "!", ")")) or label.endswith(":") \
        or re.match(r"^[A-Z][\w’' !-]+\([^)]*\)$", label) is not None


def walk_list(lst, path, rows, base):
    for li in lst.find(("li",)):
        label = clean(li.text(skip_lists=True))
        kids = [k for sub in li.find(("ul", "ol")) for k in sub.find(("li",))]
        if not label:
            for sub in li.find(("ul", "ol")):
                walk_list(sub, path, rows, base)
            continue
        if DEV_NOTE.match(label):
            note = DEV_NOTE.sub("", label)
            if rows and rows[-1]["path"] == path and rows[-1]["url"] == base["url"]:
                rows[-1].setdefault("note", []).append(note)
            else:  # a note that opens a group explains the whole group
                rows.append(dict(base, path=path, text=note, dev=1))
            continue
        if looks_like_group(li, label, kids):
            for sub in li.find(("ul", "ol")):
                walk_list(sub, path + [label.rstrip(":")], rows, base)
            continue
        row = dict(base, path=path, text=label)
        rows.append(row)
        grand = any(k.find(("ul", "ol")) for k in kids)
        if grand:  # children are groups of their own (e.g. "Racial abilities updated" > Tauren > ...)
            for sub in li.find(("ul", "ol")):
                walk_list(sub, path, rows, base)
            continue
        for k in kids:
            t = clean(k.text())
            if not t:
                continue
            if DEV_NOTE.match(t):
                row.setdefault("note", []).append(DEV_NOTE.sub("", t))
            else:
                row.setdefault("detail", []).append(t)


PLURAL = {"Night Elf": "Night Elves", "Dwarf": "Dwarves"}


def named_in(label):
    """The races and classes a sentence names, e.g. "for Skyborne:" -> ["Skyborne"]."""
    return [x for x in RACES + CLASSES
            if re.search(rf"\b(?:{re.escape(x)}s?|{re.escape(PLURAL.get(x, x))})\b", label)]


def parse_post(cooked, base):
    t = Tree()
    t.feed(cooked)
    rows, section, path = [], None, []
    for n in t.root.kids:
        if isinstance(n, str):
            continue
        if n.tag in ("h1", "h2", "h3", "h4", "h5") or (n.tag == "p" and n.bold()):
            label = clean(n.text())
            if not label or len(label) > 80 or label.upper() == "CHANGE LOG":
                continue
            if re.match(r"^[A-Z][a-z]+ \d{1,2}, 20\d\d$", label):  # dated sub-heading (known issues)
                base = dict(base, date=time.strftime("%Y-%m-%d", time.strptime(label, "%B %d, %Y")))
                continue
            section, path = label, []
        elif n.tag in ("ul", "ol"):
            walk_list(n, path, rows, dict(base, section=section or base.get("kind", "Notes")))
        elif n.tag == "p" and section and base.get("kind") == "Known issues":
            txt = clean(n.text())
            if txt and len(txt) > 12:
                rows.append(dict(base, section=section, path=[], text=txt))
        elif n.tag == "p":
            # A plain lead-in such as "We'd also like to clarify that for Skyborne:" starts a new group
            # when it names one race or class; otherwise its list would land under the previous heading.
            label = clean(n.text())
            named = named_in(label) if label.endswith(":") and len(label) <= 120 else []
            if len(named) == 1:
                section, path = named[0], []
    return rows


SECTION_NAMES = {"bugfixes": "Bug fixes", "bug fixes": "Bug fixes", "changes and updates": "Changes and updates",
                 "user interface": "User interface", "player versus player": "PvP", "pvp": "PvP",
                 "legacy system": "Legacy system", "cooldown manager": "Cooldown manager",
                 "gamepad support": "Gamepad support", "resolved issues": "Resolved issues"}
DATE_IN = re.compile(r"(January|February|March|April|May|June|July|August|September|October|November|December) (\d{1,2})(?:, (20\d\d))?")


def normalize(r):
    section, path = r["section"] or r["kind"], list(r["path"])
    if section == r["kind"] and path:           # notes without top-level headings
        section, path = path[0], path[1:]
    if section in CLASSES:                       # class-only threads ("Warrior Updates")
        section, path = "Classes", [section] + path
    elif section in RACES:                       # a race heading on its own ("Orc", "for Skyborne:")
        section, path = "Races", [section] + path
    if re.search(r"known issues?", section, re.I):
        r["kind"] = "Known issues"
    if section == r["kind"]:
        section = "General"
    if r["kind"] == "Known issues":
        m = DATE_IN.search(section)
        if m:
            year = m.group(3) or r["date"][:4]
            r["date"] = time.strftime("%Y-%m-%d", time.strptime(f"{m.group(1)} {m.group(2)} {year}", "%B %d %Y"))
        section = "Known issues"
    r["section"] = SECTION_NAMES.get(section.lower(), section[:1].upper() + section[1:])
    r["path"] = path
    return r


def finish(rows):
    out, seen = [], {}
    # Oldest first, so a change repeated in a later post keeps its first date.
    for r in sorted((normalize(r) for r in rows), key=lambda r: r["date"]):
        cls, race, spec = tag_for(r["path"], r["text"])
        if race and r["section"] == "Changes and updates":
            r["section"] = "Races"
        norm = re.sub(r"[^a-z0-9]+", " ", r["text"].lower()).strip()
        dup = f'{r["kind"]}|{cls}|{norm}'
        if dup in seen:
            continue
        key = hashlib.sha1(f'{r["kind"]}|{r["date"]}|{"/".join(r["path"])}|{r["text"]}'.encode()).hexdigest()[:10]
        seen[dup] = key
        row = {"id": key, "date": r["date"], "kind": r["kind"], "section": r["section"], "path": r["path"],
               "text": r["text"], "url": r["url"]}
        for k, v in (("cls", cls), ("race", race), ("spec", spec)):
            if v:
                row[k] = v
        if r.get("dev"):
            row["dev"] = 1
        for k in ("detail", "note"):
            if r.get(k):
                row[k] = r[k]
        out.append(row)
    out.sort(key=lambda r: r["date"], reverse=True)
    return out


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def forever_categories():
    """IDs of every forum category (and subcategory) about WoW Forever."""
    try:
        res = get(f"{FORUM}/categories.json?include_subcategories=true")
    except Exception as e:  # noqa: BLE001 - fall back to the known list
        print(f"categories: {e}", file=sys.stderr)
        return list(CATEGORIES)
    found = []

    def walk(cats, parent=""):
        for c in cats or []:
            if not isinstance(c, dict) or not isinstance(c.get("id"), int):
                continue
            text = f"{c.get('slug', '')} {c.get('name', '')} {parent}".lower()
            if "forever" in text:
                found.append(c["id"])
                name = short_category(c.get("name"))
                if name:
                    CATEGORY_NAMES[c["id"]] = name
            walk(c.get("subcategory_list"), str(c.get("slug", "")))

    walk((res.get("category_list") or {}).get("categories"))
    return sorted(set(found)) or list(CATEGORIES)


def short_category(name):
    """"World of Warcraft: Forever General Discussion" -> "General Discussion"."""
    if not isinstance(name, str):
        return ""
    name = clean(name)[:60]
    short = re.sub(r"^(World of Warcraft|WoW):?\s*Forever[:\s-]*", "", name, flags=re.I).strip()
    return short or "WoW Forever"


def discover(announce=None):
    """New staff note topics ({topic id: kind}). With a dict for `announce`, also fills it with
    every staff-started topic seen ({topic id: raw search result}) for the News page."""
    found = {}
    cats = forever_categories()
    print(f"watching forum categories {cats}", file=sys.stderr)
    for user in STAFF:
        for cat in cats:
            q = urllib.parse.quote(f"@{user} category:{cat} in:first order:latest")
            try:
                res = get(f"{FORUM}/search.json?q={q}")
            except Exception as e:  # noqa: BLE001 - discovery is best effort
                print(f"search {user}/{cat}: {e}", file=sys.stderr)
                continue
            blurbs = {p.get("topic_id"): p.get("blurb") for p in res.get("posts", []) or []
                      if isinstance(p, dict) and p.get("post_number") == 1}
            for t in res.get("topics", []) or []:
                if not isinstance(t, dict) or not isinstance(t.get("id"), int):
                    continue
                if NOTE_TITLE.search(t.get("title", "")) and t["id"] not in TOPICS:
                    found[t["id"]] = "Known issues" if "known issues" in t["title"].lower() else "Development notes"
                if announce is not None:
                    announce[t["id"]] = {"id": t["id"], "title": t.get("title"), "slug": t.get("slug"),
                                         "created_at": t.get("created_at"), "category_id": t.get("category_id", cat),
                                         "excerpt": blurbs.get(t["id"]) or t.get("excerpt"), "user": user}
            time.sleep(1)
    return found


def tracker_posts():
    """The forum's blue tracker: Blizzard employees' latest posts anywhere on the WoW forums (about
    a week's worth), or None if it can't be read."""
    try:
        res = get(f"{FORUM}/groups/blizzard-tracker/posts.json")
    except Exception as e:  # noqa: BLE001 - best effort
        print(f"blue tracker: {e}", file=sys.stderr)
        return None
    posts = res if isinstance(res, list) else (res.get("posts") if isinstance(res, dict) else None)
    return [p for p in posts or [] if isinstance(p, dict)]


STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


def latest_blue(posts, cats):
    """When the newest staff post in the Forever categories was made (any post, including a reply
    like "we've updated the notes"), as YYYY-MM-DDTHH:MM:SSZ, or "" if there's none."""
    stamps = [p["created_at"][:19] + "Z" for p in posts or []
              if p.get("category_id") in cats and isinstance(p.get("created_at"), str) and STAMP.match(p["created_at"])]
    return max(stamps, default="")


def tracker(cats, posts=None):
    """Topics started in the Forever categories by any Blizzard employee, from the forum's blue
    tracker (the last week or so). Catches staff who aren't in STAFF."""
    posts = tracker_posts() if posts is None else posts
    out = {}
    for p in posts or []:
        if not isinstance(p, dict) or p.get("post_number") != 1 or p.get("category_id") not in cats:
            continue
        tid = p.get("topic_id")
        if isinstance(tid, int):
            out[tid] = {"id": tid, "title": p.get("topic_title"), "slug": p.get("topic_slug"),
                        "created_at": p.get("created_at"), "category_id": p.get("category_id"),
                        "excerpt": p.get("excerpt"), "user": p.get("username")}
    return out


DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ANNOUNCEMENT_URL = re.compile(rf"^{re.escape(FORUM)}/t/[a-z0-9-]{{1,120}}/\d{{1,12}}$")


# Invisible direction and zero-width characters, which can make text display other than it reads.
INVISIBLE = re.compile(r"[​-‏‪-‮⁠-⁩﻿]")


def plain(s, n):
    """One line of plain text (a title or category), entities decoded, at most n characters."""
    text = clean(INVISIBLE.sub("", s)) if isinstance(s, str) else ""
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def excerpt_text(s, n=280):
    """Plain text from a post excerpt, which may be HTML: tags dropped, entities decoded, and a
    leading "[link title]" (Discourse's preview of a linked page) left out."""
    if not isinstance(s, str):
        return ""
    t = Tree()
    t.feed(s)
    text = re.sub(r"^\[[^\]]{1,200}\]\s*", "", clean(INVISIBLE.sub("", t.root.text())))
    cut = bool(re.search(r"(…|\.\.\.)$", text))
    text = re.sub(r"\s*(…|\.\.\.)$", "", text)
    if len(text) > n - 1:
        text, cut = text[: n - 1].rstrip(), True
    return text + "…" if cut and text else text


def announcement(raw):
    """A News page entry from a search or tracker result, or None if anything's off. Links are
    built here from the topic id and a cleaned slug, never taken from the forum's data."""
    if not isinstance(raw, dict):
        return None
    tid, cat = raw.get("id"), raw.get("category_id")
    title = plain(raw.get("title"), 200)
    date = str(raw.get("created_at") or "")[:10]
    if not isinstance(tid, int) or tid <= 0 or not title or not DAY.match(date):
        return None
    slug = re.sub(r"-+", "-", re.sub(r"[^a-z0-9-]", "", str(raw.get("slug") or "").lower())).strip("-")[:120] or "topic"
    out = {"id": tid, "date": date, "title": title, "url": f"{FORUM}/t/{slug}/{tid}",
           "category": CATEGORY_NAMES.get(cat, "WoW Forever") if isinstance(cat, int) else "WoW Forever",
           "kind": "Article" if raw.get("user") == "BlizzardEntertainment" else "Forum post"}
    excerpt = excerpt_text(raw.get("excerpt"))
    if excerpt and excerpt.lower() != title.lower():
        out["excerpt"] = excerpt
    if NOTE_TITLE.search(title):
        out["notes"] = 1  # its changes are on the Changes page
    return out


def kept(previous):
    """Announcements from an earlier run, re-checked before they're trusted again."""
    out = {}
    for a in previous if isinstance(previous, list) else []:
        if not isinstance(a, dict) or not isinstance(a.get("id"), int) or not isinstance(a.get("title"), str):
            continue
        if not isinstance(a.get("url"), str) or not ANNOUNCEMENT_URL.match(a["url"]) or not DAY.match(str(a.get("date"))):
            continue
        entry = {"id": a["id"], "date": a["date"], "title": plain(a["title"], 200), "url": a["url"],
                 "category": plain(a.get("category"), 60) or "WoW Forever",
                 "kind": "Article" if a.get("kind") == "Article" else "Forum post"}
        excerpt = excerpt_text(a.get("excerpt"))
        if excerpt and excerpt.lower() != entry["title"].lower():
            entry["excerpt"] = excerpt
        if a.get("notes") == 1:
            entry["notes"] = 1
        if entry["title"]:
            out[a["id"]] = entry
    return out


def announcements(found, previous=None):
    """Newest first: this run's finds, plus earlier ones this run didn't see again."""
    out = kept(previous)
    for raw in found.values():
        a = announcement(raw)
        if a:
            out[a["id"]] = a
    # The same post in two forum sections on the same day is shown once (the first one posted).
    seen, unique = set(), []
    for a in sorted(out.values(), key=lambda a: (a["date"], a["id"])):
        key = (a["date"], a["title"].lower())
        if key not in seen:
            seen.add(key)
            unique.append(a)
    return sorted(unique, key=lambda a: (a["date"], a["id"]), reverse=True)[:MAX_ANNOUNCEMENTS]


def collect(topics, load):
    rows, sources = [], []
    for tid, kind in topics.items():
        try:
            t = load(tid)
        except Exception as e:  # noqa: BLE001
            print(f"topic {tid}: {e}", file=sys.stderr)
            continue
        posts = t["post_stream"]["posts"]
        # Long threads only include the first ~20 posts; fetch the rest of the staff posts too.
        have = {p["id"] for p in posts}
        missing = [i for i in t["post_stream"]["stream"] if i not in have]
        if missing and callable(getattr(load, "more", None)):
            posts += load.more(tid, missing)
        n = 0
        for p in posts:
            if not p.get("staff") or not p.get("cooked"):
                continue
            url = f"{FORUM}/t/{t['slug']}/{tid}/{p['post_number']}"
            base = {"kind": kind, "date": p["created_at"][:10], "url": url}
            got = parse_post(p["cooked"], base)
            rows += got
            n += len(got)
        sources.append({"id": tid, "title": t["title"], "url": f"{FORUM}/t/{t['slug']}/{tid}", "kind": kind,
                        "updated": t.get("last_posted_at", "")[:10], "rows": n})
        time.sleep(1)
    return rows, sources


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-dir", help="read <topic id>.json snapshots instead of fetching")
    ap.add_argument("--out", default=str(ROOT / "gamedata" / "blizzard-notes.json"))
    ap.add_argument("--no-discover", action="store_true")
    ap.add_argument("--previous", help="an earlier notes file whose announcements are kept")
    ap.add_argument("--quick", action="store_true",
                    help="collect only if Blizzard staff posted in the Forever forums since the previous file")
    a = ap.parse_args()

    previous, seen_before = [], ""
    if a.previous:
        try:
            prev_doc = json.loads(Path(a.previous).read_text())
            previous = prev_doc.get("announcements", [])
            if isinstance(prev_doc.get("blue_seen"), str) and STAMP.match(prev_doc["blue_seen"]):
                seen_before = prev_doc["blue_seen"][:19] + "Z"
        except (OSError, ValueError, AttributeError) as e:
            print(f"previous notes: {e}", file=sys.stderr)

    topics = dict(TOPICS)
    found = {}
    latest = ""
    if a.from_dir:
        snap = Path(a.from_dir)
        load = lambda tid: json.loads((snap / f"{tid}.json").read_text())  # noqa: E731
        topics = {tid: k for tid, k in topics.items() if (snap / f"{tid}.json").exists()}
    else:
        cats = forever_categories()
        posts = tracker_posts()
        latest = latest_blue(posts, cats)
        # The quick check (every 15 minutes) costs two requests. It collects only when there's a
        # staff post newer than the last one seen; the hourly full run also catches edited posts.
        if a.quick and (posts is None or not latest or latest <= seen_before):
            print(f"quick check: nothing new from Blizzard (newest staff post {latest or 'unknown'})")
            if os.environ.get("GITHUB_OUTPUT"):  # tells the workflow to skip committing and posting
                with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
                    f.write("skipped=true\n")
            return
        if a.quick:
            print(f"quick check: new staff post at {latest}, collecting")
        if not a.no_discover:
            topics.update(discover(found))
            found.update(tracker(cats, posts))

        def load(tid):
            return get(f"{FORUM}/t/{tid}.json")

        def more(tid, ids):
            out = []
            for i in range(0, len(ids), 20):
                q = "&".join(f"post_ids[]={x}" for x in ids[i:i + 20])
                out += get(f"{FORUM}/t/{tid}/posts.json?{q}")["post_stream"]["posts"]
                time.sleep(1)
            return out
        load.more = more

    rows, sources = collect(topics, load)
    rows = finish(rows)
    if not rows:
        sys.exit("No notes parsed; keeping the existing file.")
    news = announcements(found, previous)
    out = {"updated": time.strftime("%Y-%m-%d"), "blue_seen": max(seen_before, latest), "sources": sources,
           "articles": [{"title": t, "url": u} for t, u in ARTICLES], "announcements": news, "rows": rows}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1, ensure_ascii=False))
    kinds = {}
    for r in rows:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    print(f"{len(rows)} rows from {len(sources)} topics {kinds}, {len(news)} announcements -> {a.out}")


if __name__ == "__main__":
    main()

"""Tell IndexNow search engines (Bing and others) which forever-xp.com pages changed in a deploy.

  python3 tools/indexnow.py prepare --dist site/dist --previous prev.json --manifest new.json --out changed.txt
  python3 tools/indexnow.py submit --list changed.txt

`prepare` fingerprints every page listed in the built sitemap, compares with the previous deploy's
fingerprints (kept in the GitHub Actions cache, never fetched from the web), and writes the URLs
that were added, changed or removed. `submit` sends them to api.indexnow.org in batches.

Fingerprints ignore build noise (hashed /_astro/ asset names, inline scripts), so a code change
that only renames bundles doesn't resubmit every page. The previous fingerprints file is checked
before use: anything that isn't a map of site paths to hex digests is ignored.
"""
import argparse
import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path

HOST = "forever-xp.com"
SITE = f"https://{HOST}"
KEY = "abd72ec4825ef51808bf640b6a31717b"  # public by design: served at /<key>.txt
ENDPOINT = "https://api.indexnow.org/indexnow"
BATCH = 10_000
PATH = re.compile(r"^/[A-Za-z0-9._~%/-]{0,300}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")
ASSET = re.compile(r"/_astro/[A-Za-z0-9._-]+")
# Only used to fingerprint our own build output, never to sanitize anything.
SCRIPT = re.compile(r"<script\b[^>]*>.*?</script(?:\s+[^>]*)?\s*>", re.S | re.I)
MAX_REMOVED = 500  # more than this looks like a broken build, not real removals


def site_paths(dist):
    """Paths of the pages in the built sitemap(s), e.g. "/changes/"."""
    paths = set()
    for sm in sorted(Path(dist).glob("sitemap-*.xml")):
        if sm.name == "sitemap-index.xml":
            continue
        for url in LOC.findall(sm.read_text(encoding="utf-8")):
            if url.startswith(SITE + "/"):
                p = url[len(SITE):]
                if PATH.match(p):
                    paths.add(p)
    return paths


def page_file(dist, path):
    rel = path.lstrip("/")
    f = Path(dist) / rel / "index.html" if path.endswith("/") else Path(dist) / rel
    return f if f.is_file() else None


def fingerprint(html):
    text = SCRIPT.sub("", html)
    text = ASSET.sub("/_astro/x", text)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def manifest(dist):
    out = {}
    for p in site_paths(dist):
        f = page_file(dist, p)
        if f:
            out[p] = fingerprint(f.read_text(encoding="utf-8", errors="replace"))
    return out


def load_previous(path):
    """The previous deploy's fingerprints, or None if missing or not in the expected shape."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    clean = {k: v for k, v in data.items() if isinstance(k, str) and PATH.match(k) and isinstance(v, str) and DIGEST.match(v)}
    return clean if len(clean) == len(data) else None


def changed(prev, cur):
    """URLs to submit: new or changed pages, plus removed ones (unless suspiciously many)."""
    if prev is None:
        return sorted(SITE + p for p in cur)
    paths = {p for p, h in cur.items() if prev.get(p) != h}
    removed = set(prev) - set(cur)
    if len(removed) <= MAX_REMOVED:
        paths |= removed
    return sorted(SITE + p for p in paths)


def submit(urls, send=None):
    """POST in batches; returns the HTTP status of each batch."""
    send = send or _post
    statuses = []
    for i in range(0, len(urls), BATCH):
        body = {"host": HOST, "key": KEY, "keyLocation": f"{SITE}/{KEY}.txt", "urlList": urls[i:i + BATCH]}
        statuses.append(send(body))
    return statuses


def _post(body):
    req = urllib.request.Request(
        ENDPOINT, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "forever-xp deploy (github.com/Jweyant/forever-xp)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--dist", required=True)
    p.add_argument("--previous", required=True)
    p.add_argument("--manifest", required=True)
    p.add_argument("--out", required=True)
    s = sub.add_parser("submit")
    s.add_argument("--list", required=True)
    a = ap.parse_args(argv)

    if a.cmd == "prepare":
        if not (Path(a.dist) / f"{KEY}.txt").is_file():
            sys.exit(f"{KEY}.txt is missing from {a.dist}; search engines couldn't verify submissions")
        cur = manifest(a.dist)
        if not cur:
            sys.exit("no pages found in the built sitemap")
        prev = load_previous(a.previous)
        urls = changed(prev, cur)
        Path(a.manifest).write_text(json.dumps(cur, sort_keys=True), encoding="utf-8")
        Path(a.out).write_text("".join(u + "\n" for u in urls), encoding="utf-8")
        print(f"indexnow: {len(cur)} pages, {len(urls)} to submit" + (" (no previous fingerprints)" if prev is None else ""))
        return 0

    urls = [u for u in Path(a.list).read_text(encoding="utf-8").split() if u.startswith(SITE + "/")]
    if not urls:
        print("indexnow: nothing changed")
        return 0
    statuses = submit(urls)
    print(f"indexnow: submitted {len(urls)} URLs, responses {statuses}")
    return 0 if all(s in (200, 202) for s in statuses) else 1


if __name__ == "__main__":
    sys.exit(main())

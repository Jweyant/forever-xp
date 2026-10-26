"""Which game client build the data builders read from wago.tools.

Blizzard ships new WoW Forever builds without notice, so the builders don't pin one: they take
the newest build wago.tools lists for the Forever product (the live client first, the beta if
there's no live build yet), and the newest Classic Era build for comparisons. A build can still
be forced with --build / --forever / --classic or the FOREVER_BUILD / CLASSIC_BUILD variables.

wago.tools' build list is third-party data: a version is used only if it is exactly four
dot-separated numbers, since it ends up in URLs and cache paths.
"""
import json
import os
import re
import sys
import urllib.request

WAGO = "https://wago.tools"
UA = {"User-Agent": "forever-xp data build (github.com/Jweyant/forever-xp)"}
VERSION = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,7}$")

# Product names on wago.tools, in order of preference.
FOREVER_PRODUCTS = ("wowf", "wow_classic_beta")
CLASSIC_PRODUCTS = ("wow_classic_era",)
# Forever is 1.60 and up; Classic Era is 1.15.
FOREVER_VERSION = re.compile(r"^1\.(?:6\d|[7-9]\d)\.")
CLASSIC_VERSION = re.compile(r"^1\.1[45]\.")
# Used only when wago.tools can't be reached.
FOREVER_FALLBACK = "1.60.1.70532"
CLASSIC_FALLBACK = "1.15.9.70003"


def fetch(url, timeout=180):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout).read()


def valid(version):
    return isinstance(version, str) and bool(VERSION.match(version))


def build_number(version):
    return int(version.rsplit(".", 1)[-1])


def pick(builds, products, version_re):
    """Newest valid build of the first product (in order) that has one, as (version, product)."""
    for product in products:
        found = [b.get("version") for b in builds.get(product) or [] if isinstance(b, dict)]
        found = [v for v in found if valid(v) and version_re.match(v)]
        if found:
            return max(found, key=build_number), product
    return None, None


def _resolve(override_env, products, version_re, fallback, override=None):
    forced = override or os.environ.get(override_env)
    if forced:
        if not valid(forced):
            raise SystemExit(f"{override_env}={forced!r} is not a build version like 1.60.1.70532")
        return forced, "forced"
    try:
        builds = json.loads(fetch(f"{WAGO}/api/builds", timeout=60))
    except Exception as e:  # noqa: BLE001 - fall back rather than fail the whole refresh
        print(f"wago.tools build list unavailable ({e}); using {fallback}", file=sys.stderr)
        return fallback, "fallback"
    version, product = pick(builds if isinstance(builds, dict) else {}, products, version_re)
    if not version:
        print(f"no build found for {products}; using {fallback}", file=sys.stderr)
        return fallback, "fallback"
    return version, product


def forever_build(override=None):
    """(version, where it came from) of the newest WoW Forever client build."""
    return _resolve("FOREVER_BUILD", FOREVER_PRODUCTS, FOREVER_VERSION, FOREVER_FALLBACK, override)


def classic_build(override=None):
    """(version, where it came from) of the newest Classic Era client build."""
    return _resolve("CLASSIC_BUILD", CLASSIC_PRODUCTS, CLASSIC_VERSION, CLASSIC_FALLBACK, override)

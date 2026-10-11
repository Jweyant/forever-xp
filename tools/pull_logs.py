"""Download every uploaded ForeverScout log from the upload server.

Usage:
  FSCOUT_ADMIN_TOKEN=... python3 tools/pull_logs.py --server https://foreverscout.<you>.workers.dev --dest logs/

Only logs that changed since the last pull are downloaded. Files land in <dest>/<install>-<slot>.lua,
ready for tools/ingest_logs.py.
"""
import argparse
import gzip
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path


def call(server, path, token):
    req = urllib.request.Request(server.rstrip("/") + path, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", required=True)
    ap.add_argument("--dest", default="logs")
    a = ap.parse_args()
    token = os.environ.get("FSCOUT_ADMIN_TOKEN")
    if not token:
        sys.exit("Set FSCOUT_ADMIN_TOKEN")

    dest = Path(a.dest)
    dest.mkdir(parents=True, exist_ok=True)
    index_path = dest / ".pulled.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {}

    cursor, fetched, unchanged = None, 0, 0
    while True:
        query = "?cursor=" + urllib.parse.quote(cursor) if cursor else ""
        page = json.loads(call(a.server, "/v1/logs" + query, token))
        for log in page["logs"]:
            key, etag = log["key"], log["etag"]
            if index.get(key) == etag:
                unchanged += 1
                continue
            _, install, slot_file = key.split("/")
            data = gzip.decompress(call(a.server, "/v1/logs/" + urllib.parse.quote(key, safe=""), token))
            (dest / f"{install}-{slot_file.replace('.lua.gz', '.lua')}").write_bytes(data)
            index[key] = etag
            fetched += 1
        cursor = page.get("cursor")
        if not cursor:
            break
    index_path.write_text(json.dumps(index, indent=1))
    print(f"downloaded {fetched}, unchanged {unchanged}, total {len(index)} -> {dest}")


if __name__ == "__main__":
    main()

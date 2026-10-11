# ForeverScout upload server

A Cloudflare Worker that receives logs from the ForeverScout Uploader and stores them in R2.
It runs on Cloudflare's free tier at this project's scale (free plan: 100k requests/day,
10 GB of R2 storage).

## Deploy (one time, about 10 minutes)

You need a free Cloudflare account and Node.js.

```bash
cd server
npx wrangler login                              # opens a browser to sign in to Cloudflare
npx wrangler r2 bucket create foreverscout-logs
npx wrangler secret put ADMIN_TOKEN             # paste a long random string; keep it private
npx wrangler deploy                             # prints https://foreverscout.<you>.workers.dev
```

Then in GitHub, under Settings > Secrets and variables > Actions > Variables, set `UPLOAD_URL`
to that address. The next tagged release builds uploaders that send to it.

## Pull logs for analysis

```bash
FSCOUT_ADMIN_TOKEN=<your token> python3 tools/pull_logs.py \
    --server https://foreverscout.<you>.workers.dev --dest logs/
python3 tools/ingest_logs.py --questie data/forever_questdb.sqlite \
    --maps data/questiedb/uiMapIdToAreaId.json --out out/ logs/*.lua
```

## What it accepts

- `POST /v1/upload`: gzip of a `ForeverScout.lua` SavedVariables file. It is rejected unless the
  file starts with `ForeverScoutDB = {` and has sharing turned on. Limits: 8 MB compressed and
  20 MB uncompressed, at most one upload per minute per account folder.
- Each install/account-folder pair keeps only its latest copy. The file is cumulative, so
  storage stays small.
- `GET /v1/logs` and `GET /v1/logs/<key>` need `Authorization: Bearer <ADMIN_TOKEN>`.

Anyone can technically POST a fake file. The ingest step never trusts a finding until 2 or more
separate players confirm it, and it reads log files in a sandbox with no Lua libraries.

## Test locally

```bash
npm test                                     # unit tests with an in-memory bucket
ADMIN_TOKEN=dev node test/devserver.js 8787  # local server for the uploader to hit
```

# ForeverScout upload server

A Cloudflare Worker that receives logs from the ForeverScout Uploader and stores them in R2.

## Deploy

GitHub Actions deploys it (`.github/workflows/deploy-server.yml`) whenever `server/` changes on
`main`, or when you run the workflow by hand from the Actions tab. One-time setup:

1. **Cloudflare:** open R2 in the dashboard and enable it. It asks for a payment method even for
   the free tier.
2. **Cloudflare:** go to My Profile > API Tokens > Create Token, use the **Edit Cloudflare
   Workers** template, and add the permission **Account > Workers R2 Storage > Edit**. Under Zone
   Resources, include your domain. Copy the token.
3. **GitHub** (Settings > Secrets and variables > Actions):
   - Secret `CLOUDFLARE_API_TOKEN`: the token
   - Secret `CLOUDFLARE_ACCOUNT_ID`: from the Cloudflare dashboard home page
   - Secret `FSCOUT_ADMIN_TOKEN`: any long random string; you'll use it to download logs
   - Variable `UPLOAD_HOST`: e.g. `upload.yourdomain.com`
4. Go to Actions > **Deploy upload server** > Run workflow.

Cloudflare creates the DNS record and certificate for `UPLOAD_HOST`. The release workflow reads
the same variable, so the uploader apps in the next release send to `https://UPLOAD_HOST`.

Manual deploy instead: `npx wrangler login`, `npx wrangler r2 bucket create foreverscout-logs`,
`npx wrangler secret put ADMIN_TOKEN`, then `npx wrangler deploy` (add a `[[routes]]` entry with
`custom_domain = true` to `wrangler.toml` to use your domain).

## Pull logs for analysis

```bash
FSCOUT_ADMIN_TOKEN=<your token> python3 tools/pull_logs.py \
    --server https://upload.yourdomain.com --dest logs/
python3 tools/ingest_logs.py --questie data/forever_questdb.sqlite \
    --maps data/questiedb/uiMapIdToAreaId.json --out out/ logs/*.lua
```

## What it accepts

- `POST /v1/upload`: gzip of a `ForeverScout.lua` SavedVariables file. It is rejected unless the
  file starts with `ForeverScoutDB = {` and has sharing turned on. Uploads are size- and
  rate-limited; IP addresses are never stored.
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

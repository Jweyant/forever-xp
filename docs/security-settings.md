# Security settings checklist

Settings that live outside the code. Last reviewed 2026-10-25.

## Cloudflare (done 2026-10-25)

- [x] Minimum TLS 1.2
- [x] SSL/TLS mode Full (strict)
- [x] HSTS: 6 months, include subdomains, nosniff (no preload yet)
- [x] DNSSEC on (DS record added automatically by Cloudflare Registrar)
- [x] Rate limit: more than 5 non-GET requests in 10 seconds per IP to `upload.forever-xp.com` is blocked for 10 seconds
- [x] Bot Fight Mode on, Cloudflare managed free ruleset on
- [ ] **Two-factor sign-in on the Cloudflare account** (Profile > Authentication). Most important item on this list.
- [ ] Replace the GitHub deploy token "Edit Cloudflare Workers" with a narrower one (below)

### Narrower deploy token

Create a custom token (My Profile > API Tokens > Create Token > Custom) named `forever-xp GitHub deploy`:

| Scope | Permission |
|---|---|
| Account > Cloudflare Pages | Edit |
| Account > Workers Scripts | Edit |
| Account > Workers R2 Storage | Edit |
| Account > Account Settings | Read |
| Zone (forever-xp.com only) > Workers Routes | Edit |
| Zone (forever-xp.com only) > DNS | Edit |

Set **Zone Resources** to *Include > Specific zone > forever-xp.com*, and a TTL (for example one
year) with a calendar reminder. Paste it into GitHub as the `CLOUDFLARE_API_TOKEN` secret, run the
two deploy workflows once to confirm, then delete the old token.

## GitHub (done 2026-10-25)

- [x] **Rulesets** (imported from `.github/rulesets/`): `Protect main` requires a reviewed pull request
  for every change to `main`, and blocks force pushes and deletion; `Protect release tags` stops anyone
  else creating, moving or deleting `v*` tags. Repository admins (you) can bypass both.
  GitHub doesn't allow the Actions bot as a bypass on personal repos, so scheduled data refreshes
  commit to the `data` branch instead (`tools/push_data.sh`) and the site deploy uses whichever copy
  of each data file is newer. Merge `data` into `main` with a pull request whenever you like.
- [x] **Actions > General:** approval required for all external contributors; default workflow
  permissions read-only; Actions can't create or approve pull requests.
- [x] **Advanced Security:** private vulnerability reporting, dependency graph, Dependabot alerts,
  Dependabot security updates, secret protection and push protection all on.
- [ ] Optional: Actions > General > "Require actions to be pinned to a full-length commit SHA"
  (every workflow already is), and Dependabot malware alerts.
- [ ] **Account:** two-factor on your GitHub account, with a passkey or security key.
- [ ] **General:** "Automatically delete head branches" on; Wikis off unless you'll use them.

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

## GitHub (needs the repo owner; the API used for automation can't change these)

- [ ] **Rulesets:** Settings > Rules > Rulesets > New ruleset > Import a ruleset, once for each file in
  `.github/rulesets/`. `protect-main` requires a reviewed pull request for every change to `main`
  (you and the data bot can bypass); `protect-release-tags` stops anyone else creating `v*` tags.
- [ ] **Actions > General:** "Require approval for all external contributors"; Workflow permissions
  "Read repository contents"; untick "Allow GitHub Actions to create and approve pull requests".
- [ ] **Code security:** turn on Dependabot alerts, Dependabot security updates, secret scanning
  and push protection, and **Private vulnerability reporting** (SECURITY.md points people there).
- [ ] **Account:** two-factor on your GitHub account, with a passkey or security key.
- [ ] **General:** "Automatically delete head branches" on; Wikis off unless you'll use them.

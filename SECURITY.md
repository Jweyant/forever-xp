# Security

## Reporting

Report security problems privately through GitHub's **Report a vulnerability** button on the
Security tab, not in a public issue.

## How player data is handled

- The upload server only accepts ForeverScout files with sharing turned on, limits size,
  re-uploads and new logs per network address, and never stores IP addresses.
- Logs are read as plain data (`tools/luadata.py`). They are never run as Lua.
- Drops from player logs only count once at least two different players have reported them.
- Downloading logs needs the admin token, which lives only in GitHub Actions secrets.

## The website

- Static pages on Cloudflare Pages with a strict Content-Security-Policy (inline scripts allowed
  only by hash, generated at build time by `tools/csp.mjs`), HSTS, `nosniff`, `frame-ancestors 'none'`
  and a locked-down Permissions-Policy.
- Text from outside sources (Questie, Blizzard's forum posts, the game client) is escaped before
  it reaches the page; nothing from those sources is rendered as HTML.
- TLS 1.2 or newer, Full (strict) to the origin, DNSSEC, and a rate limit on the upload server.

## Dependencies and code scanning

Dependabot opens weekly update PRs for the site, server, uploader and GitHub Actions. Every Action
is pinned to a commit SHA. CodeQL scans JavaScript/TypeScript, Python, Go and the workflows on
every pull request.

## Changes to this repository

Only maintainers can push. Everything else arrives as a pull request, which needs the
maintainer's review (`.github/CODEOWNERS` plus the `protect-main` ruleset in
`docs/security-settings.md`) before it can be merged. Workflows triggered by
pull requests from forks get no secrets and can't deploy.

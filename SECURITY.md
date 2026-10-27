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

## Secure development

Security is part of every change. The rules every contributor follows (and the checklist for
each pull request) are in [`CLAUDE.md`](CLAUDE.md#secure-development-rules). In short: treat all
outside input as untrusted, allow-list it, escape it, keep the CSP strict, and keep secrets out
of code.

Every pull request runs:
- **CodeQL** on the site, tools, server, uploader and workflows. Merges are blocked on any
  high-severity finding.
- **A hostile-input browser test** (`site/tests/security.mjs`) that pushes attack strings through
  every link, saved-data, search and import path and fails on any injected HTML or script.
- **Dependency audits**: `npm audit` for the site and `govulncheck` for the uploader.

## Dependencies and code scanning

Dependabot opens weekly update PRs for the site, server, uploader and GitHub Actions. Every Action
is pinned to a commit SHA. CodeQL scans JavaScript/TypeScript, Python, Go and the workflows on
every pull request.

## Changes to this repository

Only maintainers can push. Everything else arrives as a pull request, which needs the
maintainer's review (`.github/CODEOWNERS`) before it can be merged. Workflows triggered by
pull requests from forks get no secrets and can't deploy.

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

## Changes to this repository

Only maintainers can push. Everything else arrives as a pull request, which needs the
maintainer's review (`.github/CODEOWNERS`) before it can be merged. Workflows triggered by
pull requests from forks get no secrets and can't deploy.

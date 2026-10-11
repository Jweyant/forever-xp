# Contributing

## Logs

The most useful contribution right now is a ForeverScout log. Every level range helps,
especially brand-new Forever zones and quests. Submit logs with the
[Submit a log](../../issues/new?template=submit-log.yml) issue form.

## Code

- Keep ForeverScout read-only. It records game events and never automates gameplay.
- Never store character names, realms, GUIDs or chat.
- Before opening a pull request that changes the addon, run the mocked-client test:

  ```bash
  lua5.1 tools/test/simulate_session.lua addon/ForeverScout /tmp/ForeverScout.lua
  ```

## Fixes for Questie

Confirmed findings (seen by 2 or more players) go upstream to
[QuestieDB](https://github.com/Questie/QuestieDB) as corrections in
`src/corrections/Forever/forever*Fixes.lua`. Check Questie's Discord first to avoid duplicating
their work.

## Releases

Maintainers: bump nothing by hand. Push a tag such as `v0.2.0`. GitHub Actions stamps the version,
publishes the zip to Releases, and uploads it to CurseForge once that's configured
(see `.github/workflows/release.yml`).

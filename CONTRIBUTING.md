# Contributing

## Reports

Found a wrong step, a missing quest or an item with the wrong source? Open a
[bug report](../../issues/new?template=bug.yml) or post it in the Discord.

## Code

Read the security rules in [`CLAUDE.md`](CLAUDE.md#secure-development-rules) first; every pull
request is checked against them.

- The site is built from data. Fix a wrong number in the builder (`tools/`) or its source, not in
  the generated files under `gamedata/` or `reports/`.
- Routes are the hand-written part: edit `routes/*.yaml`, then run `tools/guidegen.py`.
- Run the checks listed under "Before every push" in `CLAUDE.md`.

## Fixes for Questie

Confirmed fixes go upstream to [QuestieDB](https://github.com/Questie/QuestieDB) as corrections in
`src/corrections/Forever/forever*Fixes.lua`. Check Questie's Discord first to avoid duplicating
their work.

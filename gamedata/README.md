# Game client data

`client-<build>.json` is read from the WoW Forever and Classic Era game client tables
(Talent, TalentTab, ChrClasses, Spell, SpellName, SpellEffect, SpellMisc, SpellDuration,
SpellRadius, SpellAuraOptions, ItemSparse, QuestV2) via [wago.tools](https://wago.tools).
`tools/site_data.py` turns it into the talent calculator and the Forever vs Classic changes page.

- `talents`: per class, tree and talent: `[id, tier, column, name, ranks, prereqId, prereqRank, icon, text, estimated]`.
  `text` is `[template, values-per-rank]`, `[text, 0]` when every rank reads the same, or `[[rank texts]]`.
- `estimated` = 1 when the Forever client only stores rank 1's numbers; later ranks are scaled from Classic Era.
- `classic`: Classic Era side of every talent that differs, `[id, name, ranks, tier, column, tree, top-rank text]`.
- `stats`: `[forever, classic, only in forever, only in classic]` counts of items, quest IDs and spells.

Refresh it after each Forever patch with the new build numbers.

## quests.json

Every WoW Forever quest (about 5,200), built by `tools/build_quests.py` from
[Questie](https://github.com/Questie/Questie)'s Forever database. The Questie team licenses
its data under GPLv3, the same license as this repo, though they note they can't speak for
every past contributor. Fields: `id`, `n` name, `lv` quest level, `req` required level, `z` zone
or category, `side` (A or H), `cls` class restriction, `xp`, `start` and `end` ({n, t, id, z, x, y}),
`obj` objective text, `pre` prerequisites, `next` next in chain, `rep` repeatable, `rew` reward items,
`repu` number of reputation rewards. Refreshed weekly by the "Refresh gear data" workflow.

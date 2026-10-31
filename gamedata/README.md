# Game client data

## talents.json

The talent calculator and the datamined talent changes, built daily by `tools/build_talents.py`
(the **Talent data** workflow) from [wago.tools](https://wago.tools):

- **Forever talents** come from the client's trait tables (TraitTree, TraitNode, TraitNodeEntry,
  TraitDefinition, TraitEdge for the arrows, TraitCond for points needed, and the curves that give
  each rank's numbers), with Blizzard's server hotfixes for the build applied on top. WoW Forever
  doesn't use the classic `Talent` table; that table in the client still holds Classic Era's talents.
- **Classic Era talents** come from the Classic Era client's `Talent` table, for comparison.
- `talents`: `[classId, class, [[tabId, tree, treeIcon, [[nodeId, row, col, name, ranks,
  prereqNodeId, prereqRank, icon, text, estimated, pointsNeeded, spellId], ...]], ...]]`.
  `text` is `[template, values-per-rank]`, `[text, 0]` when every rank reads the same, or `[[rank texts]]`.
- `report`: what the build noticed (hotfixes applied, nodes outside the trees, tooltip values that
  depend on your character's stats and show as "?").

## simweights.json

The BIS planner's stat weights, from Forever XP's own simulation runs: `tools/simrunner` (the
**Sim weights** workflow) sims the setups in `gamedata/simconfigs/` on the
[wowsims/forever](https://github.com/wowsims/forever) combat engine (MIT), pinned by commit.
Every published number comes from these runs.

- `specs`: `{"CLASS.spec": [{label, w: {stat: weight}, note}]}`, default preset first. Weights are
  per point, relative to the setup's reference stat; `dps` / `dps_oh` are weapon DPS.
- `report`: stats a run dropped (out of bounds, or not carried by Forever items).
- The engine is the wowsims team's work (MIT); the setups, runs and this data are forever-xp's.

## client-<build>.json

`client-<build>.json` is read from the WoW Forever and Classic Era game client tables
(Talent, TalentTab, ChrClasses, Spell, SpellName, SpellEffect, SpellMisc, SpellDuration,
SpellRadius, SpellAuraOptions, ItemSparse, QuestV2) via [wago.tools](https://wago.tools).
Its `talents` and `classic` lists are the old talent-table reading and are no longer used (see
talents.json); `tools/site_data.py` still takes the item, quest and spell counts (`stats`) and
`epics` from it.

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
`repu` number of reputation rewards. Refreshed daily by the "Refresh gear data" workflow.

Where Questie has no value yet (mostly Forever's new quests), `tools/questxp.py` fills the gap:
XP and objective text from [opendata](https://github.com/wowlayerup-forever/opendata)'s client-cache
quest templates (data © its contributors, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/);
marked `xps: "opendata"`), quest givers from its player observations (`src: "opendata"` on the
place), and otherwise an estimate from Classic quests of the same level and kind (`xpe: 1`). An
estimate is often off by 20% for a single quest but close over a zone. ForeverScout logs replace
all of these with measured values.

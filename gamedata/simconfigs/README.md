# Sim setups

Forever XP's own stat-weight simulations: one SIML setup per spec, run by `tools/simrunner` in the
**Sim weights** workflow, writing `gamedata/simweights.json` for the BIS planner. Every published
number comes from these runs; nothing published by wowsims ships.

- The combat engine is [wowsims/forever](https://github.com/wowsims/forever) (MIT), pinned by
  commit in `tools/simrunner/go.mod` and `.github/workflows/sim-weights.yml` (the offline test
  checks the two agree).
- A setup is a `.siml` file, the engine's text format for a full character: gear (the BIS planner's
  own suggested set, as raw item IDs), talents, consumables, buffs, debuffs, encounter, and — in
  its `sim:` section — which stats to weigh (`ep_weights_stats`) and the reference stat. The
  format is documented in the engine's `sim/siml/SPEC.md`.
- `index.json` lists the setups: the planner spec each feeds (`key`), the label and note the site
  shows, where the setup is staged in the engine checkout so its `use` lines resolve (`specDir`),
  and for specs whose engine rotations are JSON rather than SIML, the APL file to load (`aplJson`).
- Rotations currently come from the engine's defaults at the pinned commit; builds are standard
  ones until the planner's own talent builds feed in (Phase 2 of the BIS plan).

## Adding a spec

1. Copy a setup, set gear from the planner's suggestion for that spec, the talents string, and the
   stats to weigh.
2. Add its `index.json` entry, keyed to the planner's `CLASS.spec`.
3. Push: the workflow runs the sims and commits the refreshed `simweights.json` to the branch, so
   the pull request shows the real output.

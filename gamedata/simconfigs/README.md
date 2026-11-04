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
2. Add its `index.json` entry, keyed to the planner's `CLASS.spec`, with the build as talent names
   and points per tree (`"talents": {"Arms": {"Mortal Strike": 1, ...}}`). Then run
   `python3 -I tools/sim_talents.py gamedata/simconfigs gamedata/talents.json --write` to write the
   setup's `talents` line, and `--check` to confirm it.
3. Push: the workflow runs the sims and commits the refreshed `simweights.json` to the branch, so
   the pull request shows the real output.

## When the talent trees change

The builds are kept by talent name, so a patch that moves, adds or re-ranks talents needs no edit:
the talent refresh (every 3 hours) starts this workflow when the trees change, and it rewrites each
setup's `talents` line for the new trees before simming. A talent that lost ranks keeps what it
still has, one that left the game drops out, and the run notes the unspent points. A build that
can no longer be made (not enough points above a talent's row) stops the run, and the last weights
stay published until the setup's names are fixed.

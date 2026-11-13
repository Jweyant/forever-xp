# Forever XP

Free, open tools for **World of Warcraft: Forever** at [forever-xp.com](https://forever-xp.com):
leveling routes (including what to skip), quest and item databases, a BIS planner, a talent
calculator and every change Blizzard has made.

The site keeps itself current. Scheduled jobs read the Forever game client and open databases,
rebuild the data in `gamedata/`, and redeploy the site. Nothing is collected from players.

| What | From | How often |
|---|---|---|
| Items, quests, dungeon and raid loot | Forever client (wago.tools), wowsims/forever's item data, Questie, cmangos, AtlasLoot | Daily, and within 3 hours of a new client build or new item data |
| Talents | Forever client with Blizzard's hotfixes | Every 3 hours |
| Blizzard's change notes and news | Official forum staff posts | Hourly |
| Talent builds and stat weights | Our own sim runs on the wowsims/forever engine | When the engine, builds or setups change |

## Repository layout

| Path | What it is |
|---|---|
| `tools/refresh_questie_data.sh` | Builds a local copy of Questie's Forever database (JSON + SQLite) in `data/` |
| `tools/export_questiedb.lua`, `tools/build_sqlite.py` | The two steps that script runs |
| `tools/build_items.py`, `tools/build_raids.py` | Build the gear database and the dungeon and raid pages from the game client and open databases |
| `tools/build_talents.py`, `tools/build_talent_builds.py` | Read Forever's talent trees and collect talent builds |
| `tools/simrunner/` | Runs our stat-weight simulations on the wowsims/forever engine |
| `viewer/` | The 3D gear viewer (Cloudflare Worker) |
| `tools/build_quests.py` | Turns the Questie export into `gamedata/quests.json`, every Forever quest, for the site's quest database |
| `tools/blizzard_notes.py` | Collects Blizzard's official WoW Forever notes into `gamedata/blizzard-notes.json` (hourly) |
| `tools/csp.mjs` | Writes the site's security headers after each build |
| `routes/*.yaml` | Route order for each guide (the only part written by hand) |
| `tools/score_quests.py` | Scores every quest in a level band by XP/minute, for choosing what to keep or skip |
| `tools/guidegen.py` | Builds RestedXP-format guides from routes + Questie data, with checks and estimates |
| `guides/ForeverXP_Guides/` | The generated guide addon (requires RestedXP Guides) |
| `reports/` | Per-guide estimates: level, time, XP per minute per quest, issues |
| `site/` | The forever-xp.com website (Astro, Cloudflare Pages) |
| `tools/site_data.py` | Builds the website's data from routes, reports and game data |
| `gamedata/` | Talent, item, quest and spell data read from the Forever and Classic Era clients |

### Working with the data

```bash
tools/refresh_questie_data.sh            # Linux x64; needs git and python3
```

### Questie's data

Questie's data is **not** stored in this repository. QuestieDB currently has no license file,
so we generate it locally instead of redistributing it. Its Forever data is Classic data with
converted coordinates, which means new Forever content is incomplete. Gaps are filled from
[opendata](https://github.com/wowlayerup-forever/opendata) (CC BY 4.0) where it has them.

## Roadmap

- [x] Horde 1–30 and Alliance 1–20 routes for every race
- [ ] Alliance 20–30 and both factions 30–60
- [x] Item, quest, dungeon and raid databases that refresh on their own
- [x] BIS planner with our own stat weights (more specs to come)
- [x] Talent calculator and Blizzard's change list

## License

GPL-3.0. See [LICENSE](LICENSE). Not affiliated with Blizzard Entertainment, Questie or RestedXP.

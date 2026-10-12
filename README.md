# Forever XP

Free, open leveling guides for **World of Warcraft: Forever**, built from real player data.

Paid guides and Questie's database are still catching up to Forever's new quests, zones and
changes. This project collects anonymous route data from players, then uses it to:

1. build fast, free leveling routes (including what to skip), and
2. send confirmed fixes back to [Questie](https://github.com/Questie/Questie) so every player benefits.

## Help out: run ForeverScout

Two one-time installs, then it's fully automatic.

1. **The addon.** Download `ForeverScout-x.y.z.zip` from [Releases](../../releases) (CurseForge
   listing coming soon) and unzip the `ForeverScout` folder into your Forever client's
   `Interface\AddOns\` folder. On first login, click **Share automatically**.
2. **The uploader app.** Download `ForeverScoutUploader.exe` (or the Mac build) from the same
   release, double-click it and choose **Yes**. It starts with your computer and sends your log
   after each logout or `/reload`.

That's it. Play normally.

```
 in game                      your computer                    project
ForeverScout addon  ──saves──▶ ForeverScout.lua ──uploader──▶ upload server ──▶ guides + Questie fixes
(records quests, XP,          (SavedVariables)   (only if you
 positions, timing)                               opted in)
```

It records quests, XP, positions and timing. It never records your character name, realm,
chat or anything outside questing. You can turn sharing off any time with `/fscout share off`.
Details: [addon](addon/ForeverScout/README.md), [uploader](uploader/README.md).

Prefer not to install the uploader? Attach your zipped `ForeverScout.lua` to a
[Submit a log](../../issues/new?template=submit-log.yml) issue instead.

Have Questie installed too? `/fscout report` lists quests and NPCs missing from Questie's
database, ready to paste into Questie's Discord.

## Repository layout

| Path | What it is |
|---|---|
| `addon/ForeverScout/` | The logger addon |
| `uploader/` | Companion app (Go) that uploads opted-in logs automatically |
| `server/` | Upload server (Cloudflare Worker + R2) |
| `tools/pull_logs.py` | Downloads uploaded logs for analysis |
| `tools/refresh_questie_data.sh` | Builds a local copy of Questie's Forever database (JSON + SQLite) in `data/` |
| `tools/export_questiedb.lua`, `tools/build_sqlite.py` | The two steps that script runs |
| `tools/ingest_logs.py` | Merges player logs and compares them with Questie |
| `tools/test/simulate_session.lua` | Runs the addon against a mocked game client, no game needed |

### Working with the data

```bash
tools/refresh_questie_data.sh            # Linux x64; needs git and python3

python3 -m pip install lupa
python3 tools/ingest_logs.py --questie data/forever_questdb.sqlite \
    --maps data/questiedb/uiMapIdToAreaId.json --out out/ logs/*
```

`ingest_logs.py` accepts SavedVariables files and pasted `/fscout export` strings, de-duplicates
sessions, and writes:

- `out/findings.md`: quests and NPCs missing from Questie, moved NPCs, different quest givers
  and different XP, with how many players saw each one
- `out/questie_candidates.lua`: draft corrections in QuestieDB's format, for review
- `out/quest_timing.csv`: median time and XP per minute for every quest, for route scoring
- `out/logs.sqlite`: everything merged

### Questie's data

Questie's data is **not** stored in this repository. QuestieDB currently has no license file,
so we generate it locally instead of redistributing it. Its Forever data is Classic data with
converted coordinates, which means new Forever content is incomplete. Player logs fill
that gap.

## Roadmap

- [x] Local export of Questie's Forever database
- [x] ForeverScout logger and log ingest / Questie diff
- [x] Automatic uploads (uploader app + server)
- [ ] Deploy the upload server
- [ ] First in-game test on the live Forever client
- [ ] CurseForge listing
- [ ] Route scorer: XP per minute including travel, skip list
- [ ] Horde 1–30 guide (Guidelime format)
- [ ] Alliance 1–30 guide

## License

GPL-3.0. See [LICENSE](LICENSE). Not affiliated with Blizzard Entertainment, Questie or RestedXP.

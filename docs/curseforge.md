# ForeverScout on CurseForge

<https://www.curseforge.com/wow/addons/foreverscout>

Tagged releases are uploaded to CurseForge by `.github/workflows/release.yml`, alongside the
GitHub Release.

## Releasing

Push a tag: `git tag v0.3.0 && git push origin v0.3.0`. Tags with `beta` or `alpha` go up as
beta or alpha files.

## Project description

> **ForeverScout** quietly records your questing route in WoW Forever: which quests you take and
> turn in, how much XP each one gives, how long it really takes, and which mobs and chests drop
> which items. That data builds the free leveling routes, quest XP-per-minute scores and BIS item
> sources on **[forever-xp.com](https://forever-xp.com)**, and missing quests get sent back to
> Questie.
>
> - `/fscout bis` (or the minimap button) opens a best-in-slot planner in game: your gear next to
>   the best item for every slot for your spec, goal and level, where each item comes from, and
>   pins on the world map and minimap. Same picks as forever-xp.com/bis.
> - `/fscout` shows what's been recorded and whether sharing is on
> - `/fscout gear` copies your equipped gear into the forever-xp.com BIS planner
> - `/fscout report` lists quests and NPCs missing from Questie
> - `/fscout pause` and `/fscout resume` stop and start recording
>
> No names, realms, chat, gold or bag contents are recorded. Sharing is opt-in: the addon asks
> once, and the free ForeverScout Uploader app sends your log after you log out.
>
> Source code: [github.com/Jweyant/forever-xp](https://github.com/Jweyant/forever-xp). Join the
> community on [Discord](https://discord.gg/z8DfMK7Uw).

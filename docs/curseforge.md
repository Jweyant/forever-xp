# Publishing ForeverScout on CurseForge

The release workflow (`.github/workflows/release.yml`) already uploads every tagged release to
CurseForge once these are set. It also keeps publishing the GitHub Release as before.

## One-time setup (maintainer)

1. Sign in at <https://www.curseforge.com> and choose **Create a project** for World of Warcraft.
   - Name: **ForeverScout**
   - Summary: *Records your WoW Forever questing route and loot to build free leveling guides and BIS data for forever-xp.com.*
   - Category: Quests & Leveling (also Data Export)
   - Logo: `site/public/brand/curseforge-400.png`
   - Description: paste the text below.
   - License: GNU GPLv3. Source: <https://github.com/Jweyant/forever-xp>
2. Wait for CurseForge to approve the project, then copy its numeric **Project ID** from the
   project page sidebar.
3. Create an API token at <https://legacy.curseforge.com/account/api-tokens>.
4. In GitHub: **Settings > Secrets and variables > Actions**
   - Secret `CF_API_TOKEN`: the token
   - Variable `CF_PROJECT_ID`: the project ID
   - Variable `CF_GAME_VERSIONS`: `1.60.1` (WoW Forever's version name on CurseForge; check the
     project's file upload page if Blizzard ships a new client version)
5. Put the project link in `site/src/config.ts` (`curseforge:`) so the site's addon page shows a
   CurseForge button.

## Releasing

Push a tag: `git tag v0.3.0 && git push origin v0.3.0`. Tags with `beta` or `alpha` go up as
beta or alpha files. The `protect-release-tags` ruleset means only the maintainer can create
release tags.

## Description to paste

> **ForeverScout** quietly records your questing route in WoW Forever: which quests you take and
> turn in, how much XP each one gives, how long it really takes, and which mobs and chests drop
> which items. That data builds the free leveling routes, quest XP-per-minute scores and BIS
> item sources on **[forever-xp.com](https://forever-xp.com)**, and missing quests get sent back
> to Questie.
>
> - `/fscout` shows what's been recorded this session
> - `/fscout gear` copies your equipped gear into the forever-xp.com BIS planner
> - `/fscout report` lists quests and NPCs missing from Questie
>
> No names, realms, chat, gold or bag contents are recorded. Sharing is opt-in.
> Join the community on [Discord](https://discord.gg/z8DfMK7Uw).

# Community setup and growth

## Discord

Invite: <https://discord.gg/z8DfMK7Uw> (set in `site/src/config.ts`).

Suggested channels:

| Channel | Type | Use |
|---|---|---|
| #announcements | Announcement | New guides, tools and data refreshes (follow it from other servers) |
| #forever-announcements | Announcement | Each new Blizzard change and news article, linked to forever-xp.com/changes |
| #bis-and-gearing | Forum | One thread per class or spec |
| #leveling-routes | Forum | Route feedback, faster paths, skip suggestions |
| #quest-data | Forum | Wrong coordinates, missing quests (feeds Questie fixes) |
| #site-feedback | Forum | Bugs and ideas for the site |
| #foreverscout-help | Text | Addon and uploader help |

Turn on **Server Settings > Widget** if you want a live member count; the community page
already shows one from the invite.

The channel layout, roles and the automatic #forever-announcements feed are handled by the Forever XP bot:
see [`docs/discord.md`](discord.md).

## Comments on pages (giscus)

Quest, item and guide pages can show a discussion thread backed by GitHub Discussions:

1. Repo **Settings > General > Features**: turn on **Discussions**, and create a category named
   "Site comments" (Announcement type, so only giscus creates threads).
2. Install the giscus app on the repo: <https://github.com/apps/giscus>.
3. At <https://giscus.app> enter `Jweyant/forever-xp`, pick the category, and copy `data-repo-id`
   and `data-category-id` into `site/src/config.ts` (`giscus.repoId`, `giscus.categoryId`).

Until then the pages point people to the Discord instead.

## Getting the site seen

Launch is November 4, and character creation opens October 27, so the next ten days matter most.

- **Search:** submit `https://forever-xp.com/sitemap-index.xml` in Google Search Console and Bing
  Webmaster Tools (verify with a DNS TXT record in Cloudflare). Every quest and item now has its
  own page with a description, which is what people search for.
- **Reddit:** post the BIS planner and the changes table to r/classicwow and the WoW Forever
  subreddit. Lead with the tool, not the site.
- **Discord servers:** share in class Discords (Warrior, Mage and so on) and the big WoW Forever
  community servers, with a link to that class's filtered changes, for example
  `forever-xp.com/changes/?cls=Warrior`.
- **Streamers and guides:** offer BIS links for their specs; every plan link shows a preview card.
- **Addon listing:** ForeverScout on CurseForge (see `docs/curseforge.md`) links back to the site.
- **Questie:** keep sending fixes; credit in their changelog brings data-minded players.

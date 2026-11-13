# forever-xp.com

The website: guides, quest XP per minute, the skip list, the item and quest databases, the BIS
planner, the talent calculator and Forever's changes. Static pages built with Astro and hosted on
Cloudflare Pages.

```bash
cd site
npm install
npm run data     # tools/site_data.py: routes/ + reports/ -> src/data/*.json
npm run dev      # http://localhost:4321
npm run build    # -> dist/
```

Every number comes from files already in the repo (`gamedata/`, `routes/`, `reports/`), which the
scheduled workflows refresh from the game client and open databases.

Deploys run from `.github/workflows/deploy-site.yml`.

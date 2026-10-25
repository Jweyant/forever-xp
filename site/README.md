# forever-xp.com

The website: guides, quest XP per minute, the skip list, ForeverScout install pages, and (next)
the talent calculator and Forever vs Classic changes. Static pages built with Astro and hosted on
Cloudflare Pages.

```bash
cd site
npm install
npm run data     # tools/site_data.py: routes/ + reports/ -> src/data/*.json
npm run dev      # http://localhost:4321
npm run build    # -> dist/
```

Every number comes from files already in the repo. When `out/quest_timing.csv` exists (from
`tools/ingest_logs.py`), measured timings replace the estimates automatically.

Deploys run from `.github/workflows/deploy-site.yml`.

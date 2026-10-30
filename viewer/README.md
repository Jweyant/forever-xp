# 3D gear viewer

A Cloudflare Worker serving `viewer.forever-xp.com`: the page the BIS planner embeds to show a
character in 3D, drawn by Wowhead's model viewer with the planner's gear on it.

## How it stays contained

The model viewer is third-party code (`wow.zamimg.com`), so it runs on this origin and never on
forever-xp.com:

- The main site only talks to this page with an iframe and `postMessage`, sending numbers
  (race, gender, `[slot, displayId]` pairs). `public/gear_params.js` checks the sender's origin
  and every value against allow-lists; `frame-ancestors` only lets the site embed the page.
- This origin has no cookies, no accounts and no data of its own.
- The page's CSP allows same-origin requests only, and the only route out is the `/zam/*` proxy
  in `src/index.js`, which serves nothing but the model viewer's own files (path, extension and
  query allow-lists, GET/HEAD, per-IP rate limit, content types normalised).

So even a hostile model-viewer build could only fetch model files and draw pixels.

## Standalone use

The page also reads gear from its URL hash, for testing:
`https://viewer.forever-xp.com/#r=8&g=0&i=1:30606,5:30990`
(`r` race model 1–8, `g` 0/1, `i` comma-separated `slot:displayId` pairs).

## Notes

- Wowhead's viewer and model files are theirs, fetched live and never stored here; the proxy
  caches a day at Cloudflare to keep requests down. This use is the community dressing-room
  pattern, fine for a free fan site, but Wowhead can change or close it at any time — the site
  treats 3D as an extra view and keeps its own drawn figure as the default.
- Items new to Forever that Wowhead has no art for yet just don't render on the model.
- Deploys mirror `server/`: the **Deploy 3D viewer** workflow runs `npm ci`, the tests,
  `npm run vendor` (copies the pinned jQuery and wow-model-viewer files into `public/vendor/`)
  and `wrangler deploy` when `viewer/` changes on main. It needs the same Cloudflare secrets
  plus a `VIEWER_HOST` repository variable (the hostname; Cloudflare creates DNS and the
  certificate). Changing the hostname also means updating `frame-ancestors` here, `SITE.viewer3d`
  in `site/src/config.ts`, and `frame-src` in `tools/csp.mjs`.

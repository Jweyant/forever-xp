# Working on forever-xp

Security comes first on every change, not as a last step. The maintainer's standing rule:
**treat security as a priority all the time.** Before writing code, ask what input it touches
and how it could be abused; before pushing, run the checks below.

## Secure development rules

1. **Everything from outside is untrusted**: the address bar (path, query, hash), browser storage,
   form fields and pasted text (the gear import), uploaded player logs, and third-party data
   (Questie, the game client, cmangos, AtlasLoot, Blizzard's forum posts, Discord's API), and
   anything the accounts API stores or returns (plan names and data are shown with textContent).
2. **Allow-list, don't block-list.** Check a value against the exact set it may be, using own-key
   checks (`Object.prototype.hasOwnProperty.call`, the planner's `has()`), never a plain
   `obj[key]` truthiness test, which lets `constructor` and `__proto__` through.
3. **Numbers are numbers.** Coerce numeric fields with `num()` (site/src/scripts/items.ts) or
   `Number()` before they go into markup, URLs or styles.
4. **No untrusted text as HTML.** Prefer `textContent` and Astro's `{}` (which escapes). When a
   template string is unavoidable, every interpolated value goes through `esc()`, icon names
   through `ICON()` (which strips everything but `[a-z0-9_-]`), JSON in a page through
   `jsonForHtml()`. No `set:html` with data that didn't come from this repo's own constants or
   an escaping helper.
5. **No inline scripts or event handlers** (`onerror=`, `onclick=`). The CSP blocks them; use
   module scripts and `addEventListener`. Inline `is:inline` scripts must stay tiny and constant,
   since `tools/csp.mjs` hashes them.
6. **Keep the CSP strict.** No `'unsafe-inline'` or `'unsafe-eval'` in `script-src`, no new script
   or frame hosts without a written reason in the pull request.
7. **Secrets** live only in GitHub Actions secrets or Worker secrets. Never in code, logs, URLs or
   artifacts. Workflows that run on pull requests from forks get none.
8. **Dependencies**: exact versions, a release at least two weeks old, `npm audit` clean.
   GitHub Actions are pinned to full commit SHAs.
9. **Player privacy**: never collect names, realms, GUIDs, chat, gold or IP addresses.
   Player logs are parsed as data (`tools/luadata.py`), never executed.
10. **Least privilege**: workflows declare only the `permissions` they need; the Cloudflare token
    is scoped to forever-xp.com.

## Before every push

```bash
cd site
npm run data && npm run build          # also writes dist/_headers with the CSP
npm run test:security                  # hostile-input browser test, must pass
npm run test:api                       # accounts API tests (sessions, CSRF, validation)
npm audit --audit-level=high           # must be clean
```

CI runs the same checks plus CodeQL on every pull request; `main` only changes through a
reviewed pull request with those checks green.

## Per-change checklist

- [ ] What new input does this read? Is it allow-listed or escaped where it's used?
- [ ] Any new `innerHTML`, `insertAdjacentHTML`, `set:html`, `href`/`src` built from data?
- [ ] Any new third-party host, dependency, secret or workflow permission? Justified in the PR?
- [ ] If it adds a page or form that reads the URL, add a case to `site/tests/security.mjs`.
- [ ] `npm run test:security` and CodeQL green.

## Repo map

- `site/` Astro site (Cloudflare Pages). `src/scripts/` client code, `tests/security.mjs` hostile-input test.
  `site/api/app.js` the accounts API (Pages Function at `/api/*`, D1, Discord sign-in), `site/api/schema.sql`.
- `server/` upload Worker (Cloudflare). `uploader/` desktop uploader (Go). `addon/` ForeverScout.
- `tools/` data builders (Python), `tools/csp.mjs` security headers, `tools/push_data.sh` data commits.
  `tools/build_talents.py` reads Forever's talent trees (trait tables + hotfixes) from wago.tools.
- `discord/server.json` Discord layout, `tools/discord_bot.py` bot jobs (setup, patch-notes feed), `docs/discord.md`.
- `docs/security-settings.md` settings outside the code; `SECURITY.md` reporting and controls.

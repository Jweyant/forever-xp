# Player accounts

Optional accounts let players keep BIS plans and talent builds on any device. Signing in is with
Discord; every tool still works without an account.

## How it works

| Piece | Choice |
|---|---|
| Sign-in | Discord OAuth2, authorization code with PKCE, scope `identify` only |
| API | A Cloudflare Pages Function at `forever-xp.com/api/*` (`site/functions/api/[[path]].js` → `site/api/app.js`), deployed with the site |
| Storage | Cloudflare D1 (`site/api/schema.sql`) |
| Session | `__Host-fxp_sid` cookie: random 256-bit ID, HttpOnly, Secure, SameSite=Lax, 30 days. Only its SHA-256 hash is stored |
| Limits | 50 saved plans per player, 2 KB each, 8 KB request bodies |

Endpoints: `POST /api/auth/login` (form field `return=/path/`), `GET /api/auth/callback`, `POST /api/auth/logout`,
`GET|DELETE /api/me`, `GET|POST /api/plans`, `PUT|DELETE /api/plans/<id>`.
Scout leaderboard links: `GET /api/scouts`, `POST /api/scouts/claim`, `PATCH|DELETE /api/scouts/claim/<hash>`,
the public `GET /api/scouts/names` that the player-data workflow reads, and `GET /api/scouts/discord`, which
lists the Discord IDs of linked players for the Discord role job. That last route needs the
`SCOUT_ROLES_TOKEN` secret as a bearer token and doesn't exist until the secret is set.

What we store: a random user ID, the Discord user ID, the Discord display name, session hashes,
sign-in state for up to 10 minutes, the plans a player saves, and the ForeverScout installs a player
linked (a one-way hash of each install id, an optional custom board name, a show/hide flag; up to 3
installs per player). Discord's access token is used
once to read the user's ID and name, then revoked; it is never stored.

## Security

- **Sign-in:** a random `state` is stored server-side and bound to the browser by a `__Host-fxp_oauth` cookie. It's checked in constant time, used once, and expires after 10 minutes. PKCE (S256) is sent on top of the client secret.
- **Return paths:** after sign-in, the return path must match `^/(?:[a-z0-9-]+/)*$`, so it can't be sent to another site.
- **Writes:** anything that changes data needs the session cookie, an `Origin` header that is exactly `https://forever-xp.com`, and a JSON body (`application/json` forces a CORS preflight from anywhere else). This is on top of SameSite=Lax.
- **Saved data:** each plan is checked against the exact formats the site writes. BIS state uses `[A-Za-z0-9=&._,:%-]`. Talents use `<class>#<digits and dashes>`, with the class from an allow-list. Names are plain text with control characters removed, up to 60 characters.
- **Showing it:** the site shows everything from the API with `textContent`. Links to saved plans are rebuilt from checked parts, never used as given. `tests/security.mjs` feeds the account page hostile API data.
- **Scout links:** the claim code is the uploader's install id, exactly 32 lowercase hex characters; only `sha256("forever-xp scout|" + id)` is stored. An install belongs to one account. Board names are letters, digits, space, `_ ' -` (3-20 for a custom name; a Discord name has everything else removed, and falls back to `Scout a1b2c3` if under 2 characters are left), so they can't carry markup, links or mentions. The workflow re-checks every name before it reaches the board.
- **Responses:** API responses send `Cache-Control: no-store`, `nosniff`, `Referrer-Policy: no-referrer` and a `default-src 'none'` CSP.
- **Logging and secrets:** nothing logs tokens, codes, cookies or bodies. The Discord client secret lives only in Cloudflare's encrypted Pages secrets.
- **Deleting an account:** "Delete my account" removes the user, every session and every plan in one transaction.
- **Tests:** `npm run test:api` runs the API against real SQLite with Discord faked. It covers state, PKCE, single use and expiry, session hashing, CSRF, validation, caps, owner isolation and deletion.

## Setup

The API needs a D1 database bound as `DB` (schema in `site/api/schema.sql`) and the Pages
variables `DISCORD_CLIENT_ID` and `DISCORD_CLIENT_SECRET` (as a secret), with
`https://<site>/api/auth/callback` as a redirect on the Discord application. Without them,
`/api/*` answers `503 accounts-off`. `accounts` in `site/src/config.ts` shows or hides the
sign-in buttons.

## Later

- Offer to import plans saved in the browser on first sign-in.
- Public profiles and shared guild plans, if players want them.

# Player accounts (plan)

Today everything a player does on the site (BIS plans, owned items, talent builds) lives in the
page address and the browser's local storage. That keeps the site free, fast and private, but it
doesn't follow a player to another device. This is the plan for optional accounts.

## Goals

- Save BIS plans, owned items, talent builds and the imported character, and see them on any device.
- Sign in with Discord, since that's where the community lives. No passwords to store.
- Keep every tool usable without an account. Signing in only adds syncing.
- Store as little as possible: a Discord user ID, a display name, and the saved data.

## Design

| Piece | Choice | Why |
|---|---|---|
| Sign-in | Discord OAuth2 (`identify` scope only) | No passwords; ties into the Discord server |
| API | A Cloudflare Worker at `api.forever-xp.com` | Same account as the site and upload server |
| Storage | Cloudflare D1 (SQLite) | Free tier is plenty; easy backups |
| Session | HttpOnly, Secure, SameSite=Lax cookie holding a random session ID; sessions in D1 | No tokens in JavaScript |
| Limits | Per-user caps (for example 50 plans, 64 KB each) and Cloudflare rate limiting | Keeps abuse and cost down |

Tables: `users (id, discord_id, name, created)`, `sessions (id, user_id, expires)`,
`plans (id, user_id, kind, name, data, updated)` where `kind` is `bis`, `talents` or `character`
and `data` is the same string the site already puts in the address bar.

## Security notes

- OAuth `state` parameter checked on return; PKCE on the authorization request.
- CSRF: state-changing requests need the session cookie plus a same-origin `Origin` header.
- The API validates every saved string against the same formats the site parses, and never
  renders stored data as HTML.
- The Discord client secret lives only in Worker secrets.
- A "Delete my account" button removes the user, sessions and plans in one go.

## Rollout

1. Worker and D1 schema, sign-in and sign-out, behind a hidden flag.
2. "Save to my account" on the BIS planner and talent calculator; local data offered for import on first sign-in.
3. A "My plans" page.
4. Later: public profiles and shared guild plans, if players want them.

Cost on Cloudflare's free tier should be zero at the expected traffic. The Discord application
needs to be created by the server owner (Discord Developer Portal), with the redirect URL
`https://api.forever-xp.com/auth/callback`.

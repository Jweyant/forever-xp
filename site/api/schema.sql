-- Forever XP accounts (Cloudflare D1). Apply with:
--   npx wrangler d1 execute forever-xp-accounts --remote --file site/api/schema.sql
-- Stores only: a random user ID, the Discord user ID, a display name, a hash of each session ID,
-- short-lived sign-in state, and saved plans.
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  discord_id TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  created INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  id_hash TEXT PRIMARY KEY,          -- SHA-256 of the cookie value, never the value itself
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires INTEGER NOT NULL,
  created INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS sessions_expires ON sessions(expires);
CREATE TABLE IF NOT EXISTS oauth_states (
  state TEXT PRIMARY KEY,
  verifier TEXT NOT NULL,
  return_to TEXT NOT NULL,
  expires INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS plans (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK (kind IN ('bis', 'talents')),
  name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 60),
  data TEXT NOT NULL CHECK (length(data) BETWEEN 1 AND 2048),
  updated INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS plans_user ON plans(user_id, updated);

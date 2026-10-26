// Forever XP accounts API: Discord sign-in and saved BIS plans and talent builds.
// Runs as a Cloudflare Pages Function at forever-xp.com/api/* (same origin as the site, so the
// session cookie is first-party and the site's CSP needs nothing new). See docs/accounts.md.
//
// Security:
// - Sign-in is Discord OAuth2 (authorization code, scope `identify`) with a single-use `state`
//   bound to the browser by a __Host- cookie, and PKCE. Discord's access token is used once to read
//   the user's ID and name, then revoked; it is never stored.
// - Sessions are random 256-bit IDs in a __Host- HttpOnly Secure SameSite=Lax cookie. Only a
//   SHA-256 hash of the ID is stored, so a database leak doesn't hand out sessions.
// - Every request that changes something needs the session cookie, an Origin header that is
//   exactly the site, and a JSON body (which forces a CORS preflight from any other origin).
// - Everything saved is checked against the exact formats the site itself writes; names are plain
//   text the site shows with textContent.
// - Nothing here logs tokens, codes, cookies or request bodies.

const DISCORD = "https://discord.com";
const SESSION_COOKIE = "__Host-fxp_sid";
const STATE_COOKIE = "__Host-fxp_oauth";
const SESSION_DAYS = 30;
const STATE_MINUTES = 10;
const MAX_PLANS = 50;
const MAX_BODY = 8 * 1024;
const KINDS = new Set(["bis", "talents"]);
const CLASS_SLUGS = new Set(["warrior", "paladin", "hunter", "rogue", "priest", "shaman", "mage", "warlock", "druid"]);
// What the site writes after "#": the BIS planner's state, and "<class>#<points>" for talents.
const BIS_DATA = /^[A-Za-z0-9=&._,:%-]{1,2048}$/;
const TALENT_DATA = /^([a-z]+)#([0-9-]{0,200})$/;
// Pages a sign-in may return to.
const RETURN_PATH = /^\/(?:[a-z0-9-]+\/)*$/;

// ---------------------------------------------------------------- helpers

const enc = new TextEncoder();
const b64url = (bytes) => btoa(String.fromCharCode(...new Uint8Array(bytes))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const randomId = (n = 32) => b64url(crypto.getRandomValues(new Uint8Array(n)));
const sha256 = async (s) => new Uint8Array(await crypto.subtle.digest("SHA-256", enc.encode(s)));
const hex = (bytes) => [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
const now = () => Math.floor(Date.now() / 1000);

function sameString(a, b) {
  // constant-time comparison for equal-length strings
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}

function cookies(request) {
  const out = {};
  for (const part of (request.headers.get("Cookie") || "").split(";")) {
    const i = part.indexOf("=");
    if (i > 0) out[part.slice(0, i).trim()] = part.slice(i + 1).trim();
  }
  return out;
}

const cookie = (name, value, maxAge) =>
  `${name}=${value}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${maxAge}`;

const SECURITY_HEADERS = {
  "Cache-Control": "no-store",
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "no-referrer",
  "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
};

function json(body, status = 200, extra = {}) {
  const h = new Headers({ "Content-Type": "application/json; charset=utf-8", ...SECURITY_HEADERS });
  for (const [k, v] of Object.entries(extra)) {
    if (Array.isArray(v)) v.forEach((x) => h.append(k, x));
    else h.set(k, v);
  }
  return new Response(JSON.stringify(body), { status, headers: h });
}

function redirect(location, setCookies = []) {
  const h = new Headers({ Location: location, ...SECURITY_HEADERS });
  setCookies.forEach((c) => h.append("Set-Cookie", c));
  return new Response(null, { status: 302, headers: h });
}

const fail = (status, error) => json({ error }, status);

export function safeReturn(p) {
  return typeof p === "string" && p.length <= 120 && RETURN_PATH.test(p) ? p : "/";
}

/** Clean a plan name: plain text, no control characters, 1-60 characters. */
export function cleanName(v) {
  if (typeof v !== "string") return null;
  const s = v.replace(/[\t\n\r\f\v]+/g, " ").replace(/[\p{C}]/gu, "").replace(/\s+/g, " ").trim();
  return s.length >= 1 && s.length <= 60 ? s : null;
}

/** The saved data must be exactly what the site writes for that kind. */
export function validData(kind, data) {
  if (typeof data !== "string") return false;
  if (kind === "bis") return BIS_DATA.test(data);
  if (kind === "talents") {
    const m = TALENT_DATA.exec(data);
    return !!m && CLASS_SLUGS.has(m[1]);
  }
  return false;
}

async function readJson(request) {
  const type = (request.headers.get("Content-Type") || "").split(";")[0].trim().toLowerCase();
  if (type !== "application/json") return { error: "json-required" };
  const len = Number(request.headers.get("Content-Length") || 0);
  if (len > MAX_BODY) return { error: "too-large" };
  const text = await request.text();
  if (text.length > MAX_BODY) return { error: "too-large" };
  try {
    const v = JSON.parse(text);
    return v && typeof v === "object" && !Array.isArray(v) ? { value: v } : { error: "bad-json" };
  } catch {
    return { error: "bad-json" };
  }
}

// ---------------------------------------------------------------- sessions

async function currentUser(request, env) {
  const sid = cookies(request)[SESSION_COOKIE];
  if (!sid || !/^[A-Za-z0-9_-]{43}$/.test(sid)) return null;
  const idHash = hex(await sha256(sid));
  const row = await env.DB.prepare(
    "SELECT u.id, u.name, u.created FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.id_hash = ? AND s.expires > ?",
  ).bind(idHash, now()).first();
  return row ? { ...row, idHash } : null;
}

// ---------------------------------------------------------------- routes

async function login(request, env, origin) {
  const url = new URL(request.url);
  const state = randomId();
  const verifier = randomId();
  const challenge = b64url(await sha256(verifier));
  await env.DB.prepare("INSERT INTO oauth_states (state, verifier, return_to, expires) VALUES (?, ?, ?, ?)")
    .bind(state, verifier, safeReturn(url.searchParams.get("return")), now() + STATE_MINUTES * 60).run();
  const auth = new URL("/oauth2/authorize", DISCORD);
  auth.search = new URLSearchParams({
    client_id: env.DISCORD_CLIENT_ID, response_type: "code", redirect_uri: `${origin}/api/auth/callback`,
    scope: "identify", state, code_challenge: challenge, code_challenge_method: "S256", prompt: "none",
  }).toString();
  return redirect(auth.toString(), [cookie(STATE_COOKIE, state, STATE_MINUTES * 60)]);
}

async function callback(request, env, origin, ctx) {
  const url = new URL(request.url);
  const state = url.searchParams.get("state") || "";
  const code = url.searchParams.get("code") || "";
  const clearState = cookie(STATE_COOKIE, "", 0);
  const back = (path, flag) => redirect(`${path}?signin=${flag}`, [clearState]);
  if (!sameString(cookies(request)[STATE_COOKIE] || "", state) || !/^[A-Za-z0-9_-]{43}$/.test(state)) return back("/", "failed");
  // single use: take the row and delete it in one go
  const row = await env.DB.prepare("DELETE FROM oauth_states WHERE state = ? RETURNING verifier, return_to, expires").bind(state).first();
  if (!row || row.expires < now()) return back("/", "failed");
  const returnTo = safeReturn(row.return_to);
  if (url.searchParams.get("error") || !/^[A-Za-z0-9]{1,128}$/.test(code)) return back(returnTo, "cancelled");

  const tokenRes = await fetch(`${DISCORD}/api/oauth2/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded", Accept: "application/json" },
    body: new URLSearchParams({
      client_id: env.DISCORD_CLIENT_ID, client_secret: env.DISCORD_CLIENT_SECRET, grant_type: "authorization_code",
      code, redirect_uri: `${origin}/api/auth/callback`, code_verifier: row.verifier,
    }),
  });
  if (!tokenRes.ok) return back(returnTo, "failed");
  const token = await tokenRes.json().catch(() => ({}));
  if (typeof token.access_token !== "string") return back(returnTo, "failed");
  const meRes = await fetch(`${DISCORD}/api/v10/users/@me`, { headers: { Authorization: `Bearer ${token.access_token}` } });
  // we only needed the identity: revoke the token right away
  ctx.waitUntil(fetch(`${DISCORD}/api/oauth2/token/revoke`, {
    method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ token: token.access_token, token_type_hint: "access_token", client_id: env.DISCORD_CLIENT_ID, client_secret: env.DISCORD_CLIENT_SECRET }),
  }).catch(() => {}));
  if (!meRes.ok) return back(returnTo, "failed");
  const me = await meRes.json().catch(() => ({}));
  if (typeof me.id !== "string" || !/^\d{15,22}$/.test(me.id)) return back(returnTo, "failed");
  const name = cleanName(me.global_name) || cleanName(me.username) || "Adventurer";

  const t = now();
  let user = await env.DB.prepare("SELECT id FROM users WHERE discord_id = ?").bind(me.id).first();
  if (user) await env.DB.prepare("UPDATE users SET name = ? WHERE id = ?").bind(name, user.id).run();
  else {
    user = { id: randomId(16) };
    await env.DB.prepare("INSERT INTO users (id, discord_id, name, created) VALUES (?, ?, ?, ?)").bind(user.id, me.id, name, t).run();
  }
  const sid = randomId();
  await env.DB.prepare("INSERT INTO sessions (id_hash, user_id, expires, created) VALUES (?, ?, ?, ?)")
    .bind(hex(await sha256(sid)), user.id, t + SESSION_DAYS * 86400, t).run();
  ctx.waitUntil(env.DB.batch([
    env.DB.prepare("DELETE FROM sessions WHERE expires < ?").bind(t),
    env.DB.prepare("DELETE FROM oauth_states WHERE expires < ?").bind(t),
  ]).catch(() => {}));
  return redirect(`${returnTo}?signin=ok`, [clearState, cookie(SESSION_COOKIE, sid, SESSION_DAYS * 86400)]);
}

async function listPlans(env, user) {
  const { results } = await env.DB.prepare("SELECT id, kind, name, data, updated FROM plans WHERE user_id = ? ORDER BY updated DESC")
    .bind(user.id).all();
  return results || [];
}

async function createPlan(request, env, user) {
  const body = await readJson(request);
  if (body.error) return fail(400, body.error);
  const { kind, name, data } = body.value;
  if (!KINDS.has(kind)) return fail(400, "bad-kind");
  const clean = cleanName(name);
  if (!clean) return fail(400, "bad-name");
  if (!validData(kind, data)) return fail(400, "bad-data");
  const count = await env.DB.prepare("SELECT COUNT(*) AS n FROM plans WHERE user_id = ?").bind(user.id).first();
  if ((count?.n || 0) >= MAX_PLANS) return fail(409, "too-many-plans");
  const id = randomId(12);
  await env.DB.prepare("INSERT INTO plans (id, user_id, kind, name, data, updated) VALUES (?, ?, ?, ?, ?, ?)")
    .bind(id, user.id, kind, clean, data, now()).run();
  return json({ id }, 201);
}

async function updatePlan(request, env, user, id) {
  const body = await readJson(request);
  if (body.error) return fail(400, body.error);
  const plan = await env.DB.prepare("SELECT kind FROM plans WHERE id = ? AND user_id = ?").bind(id, user.id).first();
  if (!plan) return fail(404, "not-found");
  const name = body.value.name === undefined ? undefined : cleanName(body.value.name);
  if (name === null) return fail(400, "bad-name");
  const data = body.value.data;
  if (data !== undefined && !validData(plan.kind, data)) return fail(400, "bad-data");
  await env.DB.prepare("UPDATE plans SET name = COALESCE(?, name), data = COALESCE(?, data), updated = ? WHERE id = ? AND user_id = ?")
    .bind(name ?? null, data ?? null, now(), id, user.id).run();
  return json({ ok: true });
}

async function deleteAccount(env, user) {
  await env.DB.batch([
    env.DB.prepare("DELETE FROM plans WHERE user_id = ?").bind(user.id),
    env.DB.prepare("DELETE FROM sessions WHERE user_id = ?").bind(user.id),
    env.DB.prepare("DELETE FROM users WHERE id = ?").bind(user.id),
  ]);
  return json({ ok: true }, 200, { "Set-Cookie": cookie(SESSION_COOKIE, "", 0) });
}

// ---------------------------------------------------------------- entry

export async function handle(request, env, ctx = { waitUntil() {} }) {
  const url = new URL(request.url);
  const origin = env.SITE_ORIGIN || "https://forever-xp.com";
  if (!env.DB || !env.DISCORD_CLIENT_ID || !env.DISCORD_CLIENT_SECRET) return fail(503, "accounts-off");
  const path = url.pathname.replace(/\/+$/, "") || "/";
  const method = request.method;

  if (method === "GET" && path === "/api/auth/login") return login(request, env, origin);
  if (method === "GET" && path === "/api/auth/callback") return callback(request, env, origin, ctx);

  // Everything else is JSON for the signed-in user. Writes must come from the site itself.
  const writes = method !== "GET" && method !== "HEAD";
  if (writes && request.headers.get("Origin") !== origin) return fail(403, "bad-origin");
  const user = await currentUser(request, env);

  if (path === "/api/me" && method === "GET") {
    if (!user) return fail(401, "signed-out");
    return json({ name: user.name, created: user.created });
  }
  if (!user) return fail(401, "signed-out");

  if (path === "/api/auth/logout" && method === "POST") {
    await env.DB.prepare("DELETE FROM sessions WHERE id_hash = ?").bind(user.idHash).run();
    return json({ ok: true }, 200, { "Set-Cookie": cookie(SESSION_COOKIE, "", 0) });
  }
  if (path === "/api/me" && method === "DELETE") return deleteAccount(env, user);
  if (path === "/api/plans" && method === "GET") return json({ plans: await listPlans(env, user) });
  if (path === "/api/plans" && method === "POST") return createPlan(request, env, user);
  const m = /^\/api\/plans\/([A-Za-z0-9_-]{16})$/.exec(path);
  if (m && method === "PUT") return updatePlan(request, env, user, m[1]);
  if (m && method === "DELETE") {
    const r = await env.DB.prepare("DELETE FROM plans WHERE id = ? AND user_id = ?").bind(m[1], user.id).run();
    return r.meta?.changes ? json({ ok: true }) : fail(404, "not-found");
  }
  return fail(404, "not-found");
}

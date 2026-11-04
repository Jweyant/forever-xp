// Tests for the accounts API (site/api/app.js) against real SQLite (node:sqlite) standing in for
// D1, with Discord's endpoints faked. Run: node --test site/api/
import { test, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { DatabaseSync } from "node:sqlite";
import { handle, safeReturn, cleanName, validData, boardName } from "./app.js";

const ORIGIN = "https://forever-xp.com";
const SCHEMA = readFileSync(new URL("./schema.sql", import.meta.url), "utf8");

// Minimal D1 shim over node:sqlite.
class Stmt {
  constructor(db, sql) { this.db = db; this.sql = sql; this.args = []; }
  bind(...a) { this.args = a; return this; }
  async first() { return this.db.prepare(this.sql).get(...this.args) ?? null; }
  async all() { return { results: this.db.prepare(this.sql).all(...this.args) }; }
  async run() { const r = this.db.prepare(this.sql).run(...this.args); return { meta: { changes: Number(r.changes) } }; }
  runSync() { this.db.prepare(this.sql).run(...this.args); }
}
class D1 {
  constructor() { this.db = new DatabaseSync(":memory:"); this.db.exec("PRAGMA foreign_keys = ON;"); this.db.exec(SCHEMA); }
  prepare(sql) { return new Stmt(this.db, sql); }
  async batch(list) { this.db.exec("BEGIN"); try { list.forEach((s) => s.runSync()); this.db.exec("COMMIT"); } catch (e) { this.db.exec("ROLLBACK"); throw e; } return []; }
  count(table) { return this.db.prepare(`SELECT COUNT(*) AS n FROM ${table}`).get().n; }
}

let env, discordUser, calls;
const ctx = { waitUntil: (p) => p };
beforeEach(() => {
  env = { DB: new D1(), DISCORD_CLIENT_ID: "123", DISCORD_CLIENT_SECRET: "shh", SITE_ORIGIN: ORIGIN };
  discordUser = { id: "123456789012345678", username: "jw", global_name: "JW" };
  calls = [];
  globalThis.fetch = async (url, init = {}) => {
    calls.push({ url: String(url), init });
    if (String(url).endsWith("/api/oauth2/token")) {
      const body = new URLSearchParams(init.body);
      if (body.get("code") !== "goodcode" || !body.get("code_verifier")) return new Response("{}", { status: 400 });
      return Response.json({ access_token: "discord-token", token_type: "Bearer" });
    }
    if (String(url).endsWith("/users/@me")) return Response.json(discordUser);
    if (String(url).endsWith("/token/revoke")) return new Response("", { status: 200 });
    throw new Error(`unexpected fetch ${url}`);
  };
});

const req = (path, { method = "GET", cookie = "", origin, body, type = "application/json" } = {}) => {
  const headers = new Headers();
  if (cookie) headers.set("Cookie", cookie);
  if (origin) headers.set("Origin", origin);
  if (body !== undefined) headers.set("Content-Type", type);
  return new Request(`${ORIGIN}${path}`, { method, headers, body: body === undefined ? undefined : typeof body === "string" ? body : JSON.stringify(body) });
};
const setCookies = (res) => res.headers.getSetCookie();
const cookieValue = (res, name) => setCookies(res).map((c) => c.split(";")[0]).find((c) => c.startsWith(`${name}=`))?.split("=")[1];

const startLogin = (returnPath = "/bis/", { origin = ORIGIN } = {}) =>
  handle(req("/api/auth/login", { method: "POST", origin, type: "application/x-www-form-urlencoded", body: `return=${encodeURIComponent(returnPath)}` }), env, ctx);

async function signIn(returnPath = "/bis/") {
  const start = await startLogin(returnPath);
  const state = new URL(start.headers.get("Location")).searchParams.get("state");
  const stateCookie = cookieValue(start, "__Host-fxp_oauth");
  const done = await handle(req(`/api/auth/callback?code=goodcode&state=${state}`, { cookie: `__Host-fxp_oauth=${stateCookie}` }), env, ctx);
  return { start, done, sid: cookieValue(done, "__Host-fxp_sid"), state, stateCookie };
}

test("accounts stay off until configured", async () => {
  const res = await handle(req("/api/me"), { DB: null }, ctx);
  assert.equal(res.status, 503);
});

test("login sends you to Discord with state, PKCE and identify only", async () => {
  const { start } = await signIn();
  assert.equal(start.status, 303);
  const loc = new URL(start.headers.get("Location"));
  assert.equal(loc.origin, "https://discord.com");
  assert.equal(loc.searchParams.get("scope"), "identify");
  assert.equal(loc.searchParams.get("code_challenge_method"), "S256");
  assert.match(loc.searchParams.get("code_challenge"), /^[A-Za-z0-9_-]{43}$/);
  assert.equal(loc.searchParams.get("redirect_uri"), `${ORIGIN}/api/auth/callback`);
  const c = setCookies(start).find((x) => x.startsWith("__Host-fxp_oauth="));
  assert.match(c, /HttpOnly/); assert.match(c, /Secure/); assert.match(c, /SameSite=Lax/); assert.match(c, /Path=\//);
});

test("callback signs you in, stores only a session hash, and never keeps Discord's token", async () => {
  const { done, sid } = await signIn("/talents/");
  assert.equal(done.status, 302);
  assert.equal(done.headers.get("Location"), "/talents/?signin=ok");
  assert.match(sid, /^[A-Za-z0-9_-]{43}$/);
  const sc = setCookies(done).find((x) => x.startsWith("__Host-fxp_sid="));
  for (const flag of [/; HttpOnly/, /; Secure/, /; SameSite=Lax/, /; Path=\/;/, /; Max-Age=2592000$/]) assert.match(sc, flag);
  assert.doesNotMatch(sc, /Domain=/i, "__Host- cookies are host-only");
  assert.ok(setCookies(done).some((x) => /^__Host-fxp_oauth=; .*Max-Age=0$/.test(x)), "sign-in state cookie cleared");
  const row = env.DB.db.prepare("SELECT id_hash FROM sessions").get();
  assert.notEqual(row.id_hash, sid);
  assert.match(row.id_hash, /^[0-9a-f]{64}$/);
  const dump = JSON.stringify(env.DB.db.prepare("SELECT * FROM users").all()) + JSON.stringify(env.DB.db.prepare("SELECT * FROM sessions").all());
  assert.ok(!dump.includes("discord-token"));
  assert.ok(calls.some((c) => c.url.endsWith("/token/revoke")), "token revoked after use");
  const me = await handle(req("/api/me", { cookie: `__Host-fxp_sid=${sid}` }), env, ctx);
  assert.equal(me.status, 200);
  assert.equal((await me.json()).name, "JW");
});

test("callback refuses a missing, mismatched, expired or reused state", async () => {
  const start = await startLogin("/");
  const state = new URL(start.headers.get("Location")).searchParams.get("state");
  const other = "A".repeat(43);
  let r = await handle(req(`/api/auth/callback?code=goodcode&state=${state}`), env, ctx);
  assert.equal(r.headers.get("Location"), "/?signin=failed", "no state cookie");
  r = await handle(req(`/api/auth/callback?code=goodcode&state=${state}`, { cookie: `__Host-fxp_oauth=${other}` }), env, ctx);
  assert.equal(r.headers.get("Location"), "/?signin=failed", "cookie doesn't match");
  r = await handle(req(`/api/auth/callback?code=goodcode&state=${state}`, { cookie: `__Host-fxp_oauth=${state}` }), env, ctx);
  assert.match(r.headers.get("Location"), /signin=ok/);
  r = await handle(req(`/api/auth/callback?code=goodcode&state=${state}`, { cookie: `__Host-fxp_oauth=${state}` }), env, ctx);
  assert.equal(r.headers.get("Location"), "/?signin=failed", "state is single use");
  const s2 = await startLogin("/");
  const st2 = new URL(s2.headers.get("Location")).searchParams.get("state");
  env.DB.db.prepare("UPDATE oauth_states SET expires = 1").run();
  r = await handle(req(`/api/auth/callback?code=goodcode&state=${st2}`, { cookie: `__Host-fxp_oauth=${st2}` }), env, ctx);
  assert.equal(r.headers.get("Location"), "/?signin=failed", "expired");
  assert.equal(env.DB.count("sessions"), 1);
});

test("a bad code or a Discord error doesn't sign you in", async () => {
  const start = await startLogin("/bis/");
  const state = new URL(start.headers.get("Location")).searchParams.get("state");
  const r = await handle(req(`/api/auth/callback?code=badcode&state=${state}`, { cookie: `__Host-fxp_oauth=${state}` }), env, ctx);
  assert.equal(r.headers.get("Location"), "/bis/?signin=failed");
  assert.equal(env.DB.count("sessions"), 0);
});

test("sign-in starts only from a form on the site; a plain visit goes to the account page", async () => {
  for (const method of ["GET", "HEAD"]) {
    const r = await handle(req("/api/auth/login?return=/bis/", { method }), env, ctx);
    assert.equal(r.status, 303, method);
    assert.equal(r.headers.get("Location"), "/account/", method);
    assert.equal(r.headers.get("X-Robots-Tag"), "noindex, nofollow");
  }
  assert.equal((await startLogin("/bis/", { origin: "" })).status, 403, "no Origin");
  assert.equal((await startLogin("/bis/", { origin: "https://evil.com" })).status, 403, "other Origin");
  const json = await handle(req("/api/auth/login", { method: "POST", origin: ORIGIN, body: { return: "/bis/" } }), env, ctx);
  assert.equal(json.status, 400, "form body only");
  const big = await handle(req("/api/auth/login", { method: "POST", origin: ORIGIN, type: "application/x-www-form-urlencoded", body: `return=${"a".repeat(2000)}` }), env, ctx);
  assert.equal(big.status, 400, "size limit");
  assert.equal(env.DB.count("oauth_states"), 0, "nothing stored unless sign-in really started");
});

test("sign-in only returns to pages on this site", () => {
  for (const bad of ["//evil.com/", "https://evil.com/", "/\\evil.com/", "/bis/?x=1", "/bis", "javascript:alert(1)", "/a/../", "/%2F%2Fevil/", null, 42]) {
    assert.equal(safeReturn(bad), "/", String(bad));
  }
  assert.equal(safeReturn("/talents/warlock/"), "/talents/warlock/");
});

test("writes need the site's Origin and a JSON body", async () => {
  const { sid } = await signIn();
  const cookie = `__Host-fxp_sid=${sid}`;
  const plan = { kind: "bis", name: "Raid", data: "c=WARRIOR&s=fury&plan=0-12640" };
  let r = await handle(req("/api/plans", { method: "POST", cookie, body: plan }), env, ctx);
  assert.equal(r.status, 403, "no Origin");
  r = await handle(req("/api/plans", { method: "POST", cookie, origin: "https://evil.com", body: plan }), env, ctx);
  assert.equal(r.status, 403, "other Origin");
  r = await handle(req("/api/plans", { method: "POST", cookie, origin: ORIGIN, body: "kind=bis", type: "application/x-www-form-urlencoded" }), env, ctx);
  assert.equal(r.status, 400, "form posts are refused");
  r = await handle(req("/api/plans", { method: "POST", cookie, origin: ORIGIN, body: plan }), env, ctx);
  assert.equal(r.status, 201);
  r = await handle(req("/api/auth/logout", { method: "POST", cookie }), env, ctx);
  assert.equal(r.status, 403, "logout needs Origin too");
});

test("plans are validated, capped and private to their owner", async () => {
  const a = await signIn();
  const ca = `__Host-fxp_sid=${a.sid}`;
  const post = (body, cookie = ca) => handle(req("/api/plans", { method: "POST", cookie, origin: ORIGIN, body }), env, ctx);
  assert.equal((await post({ kind: "admin", name: "x", data: "c=1" })).status, 400);
  assert.equal((await post({ kind: "bis", name: "", data: "c=1" })).status, 400);
  assert.equal((await post({ kind: "bis", name: "x".repeat(61), data: "c=1" })).status, 400);
  assert.equal((await post({ kind: "bis", name: "x", data: "<script>alert(1)</script>" })).status, 400);
  assert.equal((await post({ kind: "talents", name: "x", data: "hacker#5555" })).status, 400);
  assert.equal((await post({ kind: "talents", name: "x", data: "warlock#55\"><img>" })).status, 400);
  const ok = await post({ kind: "talents", name: "  Affli\u0000ction‮  build ", data: "warlock#3032501001-35320031002" });
  assert.equal(ok.status, 201);
  const { id } = await ok.json();
  const list = await (await handle(req("/api/plans", { cookie: ca }), env, ctx)).json();
  assert.equal(list.plans[0].name, "Affliction build", "control characters removed");

  // another player can't see, change or delete it
  discordUser = { id: "999999999999999999", username: "other" };
  const b = await signIn();
  const cb = `__Host-fxp_sid=${b.sid}`;
  assert.deepEqual((await (await handle(req("/api/plans", { cookie: cb }), env, ctx)).json()).plans, []);
  assert.equal((await handle(req(`/api/plans/${id}`, { method: "PUT", cookie: cb, origin: ORIGIN, body: { name: "mine" } }), env, ctx)).status, 404);
  assert.equal((await handle(req(`/api/plans/${id}`, { method: "DELETE", cookie: cb, origin: ORIGIN }), env, ctx)).status, 404);

  for (let i = 1; i < 50; i++) assert.equal((await post({ kind: "bis", name: `p${i}`, data: "c=WARRIOR" })).status, 201);
  assert.equal((await post({ kind: "bis", name: "one too many", data: "c=WARRIOR" })).status, 409);
});

test("signing out and deleting the account remove everything", async () => {
  const { sid } = await signIn();
  const cookie = `__Host-fxp_sid=${sid}`;
  await handle(req("/api/plans", { method: "POST", cookie, origin: ORIGIN, body: { kind: "bis", name: "a", data: "c=MAGE" } }), env, ctx);
  const del = await handle(req("/api/me", { method: "DELETE", cookie, origin: ORIGIN }), env, ctx);
  assert.equal(del.status, 200);
  assert.match(setCookies(del)[0], /Max-Age=0/);
  assert.equal(env.DB.count("users"), 0);
  assert.equal(env.DB.count("sessions"), 0);
  assert.equal(env.DB.count("plans"), 0);
  assert.equal((await handle(req("/api/me", { cookie }), env, ctx)).status, 401);
});

test("junk cookies and expired sessions are signed out", async () => {
  assert.equal((await handle(req("/api/me", { cookie: "__Host-fxp_sid=' OR 1=1 --" }), env, ctx)).status, 401);
  const { sid } = await signIn();
  env.DB.db.prepare("UPDATE sessions SET expires = 1").run();
  assert.equal((await handle(req("/api/me", { cookie: `__Host-fxp_sid=${sid}` }), env, ctx)).status, 401);
});

test("name and data helpers", () => {
  assert.equal(cleanName("  a\tb  "), "a b");
  assert.equal(cleanName(5), null);
  assert.ok(validData("bis", "c=WARRIOR&s=fury&g=pve&l=60&f=H&r=orc.M&plan=0-12640.1-23053"));
  assert.ok(!validData("bis", "c=WARRIOR#x"));
  assert.ok(validData("talents", "druid#"));
  assert.ok(!validData("talents", "constructor#1"));
});

// ---------------------------------------------------------------- scout claims

const INSTALL = "a".repeat(32);
const claim = (cookie, body, method = "POST", path = "/api/scouts/claim") =>
  handle(req(path, { method, cookie, origin: ORIGIN, body }), env, ctx);

test("claiming a scout stores only the hash, and the board name defaults to the Discord name", async () => {
  const { sid } = await signIn();
  const cookie = `__Host-fxp_sid=${sid}`;
  const r = await claim(cookie, { code: INSTALL });
  assert.equal(r.status, 201);
  const { id } = await r.json();
  assert.match(id, /^[0-9a-f]{64}$/);
  assert.ok(id.startsWith("97800d"), "same hash as the uploader's Scout 97800d");
  const dump = JSON.stringify(env.DB.db.prepare("SELECT * FROM scout_claims").all());
  assert.ok(!dump.includes(INSTALL), "the install id itself is never stored");
  const mine = await (await handle(req("/api/scouts", { cookie }), env, ctx)).json();
  assert.deepEqual(mine.scouts.map((s) => [s.handle, s.name, s.shown, s.visible]), [["Scout 97800d", null, "JW", true]]);
  const names = await (await handle(req("/api/scouts/names"), env, ctx)).json();
  assert.deepEqual(names, { names: { [id]: "JW" } });
  assert.equal((await claim(cookie, { code: INSTALL })).status, 200, "claiming your own install again is fine");
});

test("the public names list needs no sign-in and hides what players hid", async () => {
  const { sid } = await signIn();
  const cookie = `__Host-fxp_sid=${sid}`;
  const { id } = await (await claim(cookie, { code: INSTALL, name: "Kinos" })).json();
  assert.deepEqual((await (await handle(req("/api/scouts/names"), env, ctx)).json()).names, { [id]: "Kinos" });
  assert.equal((await claim(cookie, { visible: false }, "PATCH", `/api/scouts/claim/${id}`)).status, 200);
  assert.deepEqual((await (await handle(req("/api/scouts/names"), env, ctx)).json()).names, {});
  assert.equal((await claim(cookie, { name: null, visible: true }, "PATCH", `/api/scouts/claim/${id}`)).status, 200);
  assert.deepEqual((await (await handle(req("/api/scouts/names"), env, ctx)).json()).names, { [id]: "JW" }, "clearing the custom name goes back to Discord's");
});

test("claim codes and names are checked against exact formats", async () => {
  const { sid } = await signIn();
  const cookie = `__Host-fxp_sid=${sid}`;
  for (const code of ["", "a".repeat(31), "A".repeat(32), "g".repeat(32), `${"a".repeat(32)}0`, "__proto__", null, 7, ["a".repeat(32)]]) {
    assert.equal((await claim(cookie, { code })).status, 400, String(code));
  }
  for (const name of ["ab", "x".repeat(21), "<img src=x>", "a.b.com", "https://evil.com", "Scout 97800d", "scout ABCDEF", "Kinos‮", 5, {}]) {
    assert.equal((await claim(cookie, { code: INSTALL, name })).status, 400, String(name));
  }
  assert.equal(env.DB.count("scout_claims"), 0);
  assert.equal((await claim(cookie, { code: INSTALL, name: "  Old   Kinos  " })).status, 201);
  assert.equal(env.DB.db.prepare("SELECT display_name FROM scout_claims").get().display_name, "Old Kinos");
});

test("an install can be claimed by one account only, and an account holds up to three", async () => {
  const a = await signIn();
  const ca = `__Host-fxp_sid=${a.sid}`;
  assert.equal((await claim(ca, { code: INSTALL })).status, 201);
  discordUser = { id: "999999999999999999", username: "other", global_name: "Other" };
  const b = await signIn();
  const cb = `__Host-fxp_sid=${b.sid}`;
  assert.equal((await claim(cb, { code: INSTALL })).status, 409, "already claimed by someone else");
  const mine = (await (await handle(req("/api/scouts", { cookie: cb }), env, ctx)).json()).scouts;
  assert.deepEqual(mine, []);
  const id = env.DB.db.prepare("SELECT install_hash FROM scout_claims").get().install_hash;
  assert.equal((await claim(cb, { name: "Mine" }, "PATCH", `/api/scouts/claim/${id}`)).status, 404, "can't edit another player's");
  assert.equal((await claim(cb, null, "DELETE", `/api/scouts/claim/${id}`)).status, 404, "can't unlink another player's");
  for (const c of ["b", "c", "d", "e"]) {
    const res = await claim(cb, { code: c.repeat(32) });
    assert.equal(res.status, c === "e" ? 409 : 201, c);
  }
});

test("Discord names the board can't show fall back to the scout handle", async () => {
  discordUser = { id: "123456789012345678", username: "x", global_name: "🔥🔥" };
  const { sid } = await signIn();
  const { id } = await (await claim(`__Host-fxp_sid=${sid}`, { code: INSTALL })).json();
  assert.deepEqual((await (await handle(req("/api/scouts/names"), env, ctx)).json()).names, { [id]: "Scout 97800d" });
  assert.equal(boardName(null, "Ünï<b>cöde</b> Name!!", "f".repeat(64)), "nbcdeb Name");
  assert.equal(boardName(null, "Zoë <3 Kinos", "f".repeat(64)), "Zo 3 Kinos");
  assert.equal(boardName(null, "x".repeat(40), "f".repeat(64)), "x".repeat(20));
});

test("scout writes need sign-in, the site's Origin and JSON; unlinking and deleting the account remove claims", async () => {
  const { sid } = await signIn();
  const cookie = `__Host-fxp_sid=${sid}`;
  assert.equal((await handle(req("/api/scouts/claim", { method: "POST", body: { code: INSTALL } }), env, ctx)).status, 403, "no Origin");
  assert.equal((await handle(req("/api/scouts/claim", { method: "POST", origin: ORIGIN, body: { code: INSTALL } }), env, ctx)).status, 401, "signed out");
  assert.equal((await handle(req("/api/scouts/claim", { method: "POST", cookie, origin: ORIGIN, body: `code=${INSTALL}`, type: "application/x-www-form-urlencoded" }), env, ctx)).status, 400);
  const { id } = await (await claim(cookie, { code: INSTALL })).json();
  assert.equal((await claim(cookie, null, "DELETE", `/api/scouts/claim/${id}`)).status, 200);
  assert.equal(env.DB.count("scout_claims"), 0);
  await claim(cookie, { code: INSTALL });
  assert.equal((await handle(req("/api/me", { method: "DELETE", cookie, origin: ORIGIN }), env, ctx)).status, 200);
  assert.equal(env.DB.count("scout_claims"), 0);
  assert.deepEqual((await (await handle(req("/api/scouts/names"), env, ctx)).json()).names, {});
});

test("the Discord role list needs its own secret token and lists only visible claims", async () => {
  const { sid } = await signIn();
  const cookie = `__Host-fxp_sid=${sid}`;
  const { id } = await (await claim(cookie, { code: INSTALL })).json();
  const ask = (auth) => handle(new Request(`${ORIGIN}/api/scouts/discord`, { headers: auth ? { Authorization: auth } : {} }), env, ctx);
  assert.equal((await ask("Bearer anything")).status, 404, "route doesn't exist until the secret is set");
  env.SCOUT_ROLES_TOKEN = "t".repeat(40);
  assert.equal((await ask()).status, 401);
  assert.equal((await ask("Bearer " + "x".repeat(40))).status, 401);
  assert.equal((await ask("t".repeat(40))).status, 401, "scheme required");
  assert.equal((await ask(`Bearer ${"t".repeat(40)}`)).status, 200);
  assert.deepEqual(await (await ask(`Bearer ${"t".repeat(40)}`)).json(), { ids: ["123456789012345678"] });
  await claim(cookie, { visible: false }, "PATCH", `/api/scouts/claim/${id}`);
  assert.deepEqual(await (await ask(`Bearer ${"t".repeat(40)}`)).json(), { ids: [] }, "hidden players lose the role");
  env.SCOUT_ROLES_TOKEN = "short";
  assert.equal((await ask("Bearer short")).status, 404, "a weak token is treated as not set");
  assert.equal((await handle(new Request(`${ORIGIN}/api/scouts/discord`, { method: "POST", headers: { Origin: ORIGIN, Authorization: `Bearer ${"t".repeat(40)}` } }), env, ctx)).status, 401, "writes still need a session");
});

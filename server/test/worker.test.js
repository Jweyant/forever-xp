import { test } from "node:test";
import assert from "node:assert/strict";
import { gzipSync, gunzipSync } from "node:zlib";
import worker from "../src/index.js";
import { mockBucket } from "./mock-r2.js";

const INSTALL = "0123456789abcdef0123456789abcdef";
const SLOT = "fedcba9876543210";
const GOOD = '\nForeverScoutDB = {\n\t["settings"] = {\n\t\t["share"] = true,\n\t},\n}\n';

const env = () => ({ LOGS: mockBucket(), ADMIN_TOKEN: "secret-token" });

function post(body, headers = {}) {
  return new Request("https://x/v1/upload", {
    method: "POST",
    body,
    headers: { "x-fscout-install": INSTALL, "x-fscout-slot": SLOT, ...headers },
  });
}

test("accepts a shared ForeverScout file and stores it once per slot", async () => {
  const e = env();
  const res = await worker.fetch(post(gzipSync(GOOD)), e);
  assert.equal(res.status, 200);
  const key = `logs/${INSTALL}/${SLOT}.lua.gz`;
  assert.equal(gunzipSync(e.LOGS.store.get(key).body).toString(), GOOD);
});

test("rejects files with sharing off, non-ForeverScout files, bad gzip and bad ids", async () => {
  const e = env();
  assert.equal((await worker.fetch(post(gzipSync(GOOD.replace("true", "false"))), e)).status, 422);
  assert.equal((await worker.fetch(post(gzipSync("Questie = {}")), e)).status, 422);
  assert.equal((await worker.fetch(post("not gzip"), e)).status, 400);
  assert.equal((await worker.fetch(post(gzipSync(GOOD), { "x-fscout-install": "nope" }), e)).status, 400);
  assert.equal(e.LOGS.store.size, 0);
});

test("rejects decompression bombs", async () => {
  const e = env();
  const huge = gzipSync(GOOD + " ".repeat(25 * 1024 * 1024));
  assert.equal((await worker.fetch(post(huge), e)).status, 413);
});

test("rate limits rapid re-uploads from the same slot", async () => {
  const e = env();
  assert.equal((await worker.fetch(post(gzipSync(GOOD)), e)).status, 200);
  const res = await worker.fetch(post(gzipSync(GOOD)), e);
  assert.equal(res.status, 429);
  assert.ok(Number(res.headers.get("retry-after")) > 0);
});

test("admin endpoints require the token and return stored logs", async () => {
  const e = env();
  await worker.fetch(post(gzipSync(GOOD)), e);
  assert.equal((await worker.fetch(new Request("https://x/v1/logs"), e)).status, 401);
  const auth = { authorization: "Bearer secret-token" };
  const list = await (await worker.fetch(new Request("https://x/v1/logs", { headers: auth }), e)).json();
  assert.equal(list.logs.length, 1);
  const got = await worker.fetch(new Request(`https://x/v1/logs/${list.logs[0].key}`, { headers: auth }), e);
  assert.equal(gunzipSync(Buffer.from(await got.arrayBuffer())).toString(), GOOD);
  const encoded = await worker.fetch(new Request("https://x/v1/logs/%2e%2e%2fsecret", { headers: auth }), e);
  assert.equal(encoded.status, 400);
  const dotted = await worker.fetch(new Request("https://x/v1/logs/../secret", { headers: auth }), e);
  assert.equal(dotted.status, 404); // URL parsing collapses it to /v1/secret
});

test("caps new logs per network address per day, but not updates to existing ones", async () => {
  const e = env();
  const from = (i, ip = "203.0.113.7") => new Request("https://x/v1/upload", {
    method: "POST", body: gzipSync(GOOD),
    headers: { "x-fscout-install": i.toString(16).padStart(32, "0"), "x-fscout-slot": SLOT, "cf-connecting-ip": ip },
  });
  for (let i = 1; i <= 12; i++) assert.equal((await worker.fetch(from(i), e)).status, 200);
  assert.equal((await worker.fetch(from(13), e)).status, 429);
  assert.equal((await worker.fetch(from(13, "198.51.100.2"), e)).status, 200);
  const logs = [...e.LOGS.store.keys()].filter((k) => k.startsWith("logs/"));
  assert.equal(logs.length, 13);
  assert.ok([...e.LOGS.store.keys()].every((k) => !k.includes("203.0.113.7")));
});

// Stands in for Cloudflare's rate-limit binding: `limit` allowed per key, no time window.
function mockBurst(limit) {
  const counts = new Map();
  return {
    keys: counts,
    async limit({ key }) {
      counts.set(key, (counts.get(key) || 0) + 1);
      return { success: counts.get(key) <= limit };
    },
  };
}

test("turns away bursts of writes from one address before reading the body", async () => {
  const e = { ...env(), BURST: mockBurst(5) };
  const from = (ip, i) => new Request("https://x/v1/upload", {
    method: "POST", body: gzipSync(GOOD),
    headers: { "x-fscout-install": INSTALL, "x-fscout-slot": i.toString(16).padStart(16, "0"), "cf-connecting-ip": ip },
  });
  for (let i = 1; i <= 5; i++) assert.equal((await worker.fetch(from("203.0.113.7", i), e)).status, 200);
  const res = await worker.fetch(from("203.0.113.7", 6), e);
  assert.equal(res.status, 429);
  assert.equal(res.headers.get("retry-after"), "10");
  assert.equal((await worker.fetch(from("198.51.100.2", 7), e)).status, 200);
  // Reads aren't counted, and the address is never written to the bucket.
  assert.equal((await worker.fetch(new Request("https://x/health"), e)).status, 200);
  assert.equal(e.BURST.keys.size, 2);
  assert.ok([...e.LOGS.store.keys()].every((k) => !k.includes("203.0.113.7") && !k.includes("198.51.100.2")));
});

test("non-GET requests to the admin paths count toward the burst limit too", async () => {
  const e = { ...env(), BURST: mockBurst(0) };
  const res = await worker.fetch(new Request("https://x/v1/logs", { method: "DELETE", headers: { "cf-connecting-ip": "203.0.113.7" } }), e);
  assert.equal(res.status, 429);
});

test("a failing rate-limit binding doesn't take uploads down", async () => {
  const e = { ...env(), BURST: { limit: async () => { throw new Error("unavailable"); } } };
  assert.equal((await worker.fetch(post(gzipSync(GOOD)), e)).status, 200);
});

test("wrangler.toml declares the burst limit the code expects", async () => {
  const { readFileSync } = await import("node:fs");
  const toml = readFileSync(new URL("../wrangler.toml", import.meta.url), "utf8");
  const block = toml.split("[[ratelimits]]")[1] || "";
  assert.match(block, /^\s*name\s*=\s*"BURST"\s*$/m);
  assert.match(block, /^\s*namespace_id\s*=\s*"\d+"\s*$/m);
  assert.match(block, /^\s*simple\s*=\s*\{\s*limit\s*=\s*5\s*,\s*period\s*=\s*10\s*\}\s*$/m);
});

test("the schedule starts the notes workflow on main: quick, and a full run at the top of the hour", async () => {
  const { startNotesRun } = await import("../src/index.js");
  const calls = [];
  const fake = async (url, init) => { calls.push({ url, init }); return { status: 204 }; };
  const quick = await startNotesRun({ GH_DISPATCH_TOKEN: "tok" }, Date.UTC(2026, 10, 4, 22, 45), fake);
  const full = await startNotesRun({ GH_DISPATCH_TOKEN: "tok" }, Date.UTC(2026, 10, 4, 23, 0), fake);
  assert.deepEqual([quick.full, full.full], [false, true]);
  assert.equal(calls.length, 2);
  for (const c of calls) {
    assert.equal(c.url, "https://api.github.com/repos/Jweyant/forever-xp/actions/workflows/blizzard-notes.yml/dispatches");
    assert.equal(c.init.method, "POST");
    assert.equal(c.init.headers.authorization, "Bearer tok");
  }
  assert.deepEqual(JSON.parse(calls[0].init.body), { ref: "main", inputs: { quick: "true" } });
  assert.deepEqual(JSON.parse(calls[1].init.body), { ref: "main", inputs: { quick: "false" } });
});

test("the schedule does nothing without a token, and never logs the token", async () => {
  const { startNotesRun } = await import("../src/index.js");
  let called = false;
  assert.deepEqual(await startNotesRun({}, Date.now(), async () => { called = true; }), { skipped: true });
  assert.equal(called, false);
  const logged = [];
  const log = console.log;
  console.log = (...a) => logged.push(a.join(" "));
  try {
    await startNotesRun({ GH_DISPATCH_TOKEN: "super-secret" }, Date.now(), async () => ({ status: 401 }));
  } finally {
    console.log = log;
  }
  assert.ok(logged.every((l) => !l.includes("super-secret")));
});

test("the scheduled handler hands the request to waitUntil", async () => {
  const waits = [];
  await worker.scheduled({ scheduledTime: Date.now() }, {}, { waitUntil: (p) => waits.push(p) });
  assert.equal(waits.length, 1);
  await waits[0];
});

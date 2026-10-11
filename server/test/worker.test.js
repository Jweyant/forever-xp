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

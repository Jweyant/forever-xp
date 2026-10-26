// ForeverScout upload server (Cloudflare Worker + R2).
//
//   POST /v1/upload          gzip body of ForeverScout.lua, from the uploader app
//        headers X-FScout-Install (32 hex), X-FScout-Slot (16 hex), X-FScout-Version
//   GET  /v1/logs?cursor=    list stored logs            (Authorization: Bearer ADMIN_TOKEN)
//   GET  /v1/logs/<key>      download one log, gzip      (Authorization: Bearer ADMIN_TOKEN)
//   GET  /health
//
// Each install+slot keeps only its latest upload: the SavedVariables file is cumulative,
// so the newest copy contains everything earlier ones did.

const MAX_GZIP_BYTES = 8 * 1024 * 1024;
const MAX_RAW_BYTES = 20 * 1024 * 1024;
const MIN_SECONDS_BETWEEN_UPLOADS = 60;
// One network address can start at most this many new logs (install+slot) per UTC day. Real players
// have one install and a few characters; this stops one person flooding the bucket with made-up IDs.
const MAX_NEW_LOGS_PER_IP_PER_DAY = 12;
const HEX32 = /^[0-9a-f]{32}$/;
const HEX16 = /^[0-9a-f]{16}$/;

const json = (body, status = 200, headers = {}) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });

async function gunzipLimited(buffer, limit) {
  const stream = new Blob([buffer]).stream().pipeThrough(new DecompressionStream("gzip"));
  const reader = stream.getReader();
  const chunks = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > limit) {
      await reader.cancel();
      throw new Error("too large");
    }
    chunks.push(value);
  }
  const out = new Uint8Array(total);
  let offset = 0;
  for (const c of chunks) {
    out.set(c, offset);
    offset += c.byteLength;
  }
  return new TextDecoder().decode(out);
}

function timingSafeEqual(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

function authorized(request, env) {
  const header = request.headers.get("authorization") || "";
  const token = header.startsWith("Bearer ") ? header.slice(7) : "";
  return Boolean(env.ADMIN_TOKEN) && timingSafeEqual(token, env.ADMIN_TOKEN);
}

async function sha256hex(text) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// Counts new logs per address per day. Only a salted hash of the address is stored, and it
// changes every day, so it can't be used to track anyone.
async function allowNewLog(request, env) {
  const ip = request.headers.get("cf-connecting-ip") || "unknown";
  const day = new Date().toISOString().slice(0, 10);
  const key = `limits/${day}/${(await sha256hex(`${env.ADMIN_TOKEN || ""}|${day}|${ip}`)).slice(0, 32)}`;
  const existing = await env.LOGS.head(key);
  const count = Number(existing?.customMetadata?.count || 0);
  if (count >= MAX_NEW_LOGS_PER_IP_PER_DAY) return false;
  await env.LOGS.put(key, new Uint8Array(0), { customMetadata: { count: String(count + 1) } });
  return true;
}

// At most 5 non-GET requests per 10 seconds from one address (the BURST binding in wrangler.toml).
// Cloudflare keeps the count; the address is only the counter's key and is never stored here. If
// the counter can't be reached, the per-slot and per-day limits below still apply.
async function withinBurst(request, env) {
  if (!env.BURST) return true; // unit tests and the local dev server
  try {
    const { success } = await env.BURST.limit({ key: request.headers.get("cf-connecting-ip") || "unknown" });
    return success !== false;
  } catch {
    return true;
  }
}

async function upload(request, env) {
  const install = request.headers.get("x-fscout-install") || "";
  const slot = request.headers.get("x-fscout-slot") || "";
  if (!HEX32.test(install) || !HEX16.test(slot)) return json({ error: "bad id" }, 400);

  const declared = Number(request.headers.get("content-length") || 0);
  if (declared > MAX_GZIP_BYTES) return json({ error: "too large" }, 413);
  const body = await request.arrayBuffer();
  if (body.byteLength === 0 || body.byteLength > MAX_GZIP_BYTES) return json({ error: "bad size" }, 413);

  let text;
  try {
    text = await gunzipLimited(body, MAX_RAW_BYTES);
  } catch (e) {
    return json({ error: e.message === "too large" ? "too large" : "not gzip" }, e.message === "too large" ? 413 : 400);
  }
  // Must look like a ForeverScout SavedVariables file with sharing turned on.
  if (!/^\s*ForeverScoutDB\s*=\s*\{/.test(text)) return json({ error: "not a ForeverScout file" }, 422);
  if (!/\["share"\]\s*=\s*true/.test(text)) return json({ error: "sharing is off" }, 422);

  const key = `logs/${install}/${slot}.lua.gz`;
  const existing = await env.LOGS.head(key);
  if (existing) {
    const last = Number(existing.customMetadata?.uploadedAt || 0);
    const waited = (Date.now() - last) / 1000;
    if (waited < MIN_SECONDS_BETWEEN_UPLOADS) {
      const retry = Math.ceil(MIN_SECONDS_BETWEEN_UPLOADS - waited);
      return json({ error: "slow down" }, 429, { "retry-after": String(retry) });
    }
  } else if (!(await allowNewLog(request, env))) {
    return json({ error: "too many new logs from this network today" }, 429, { "retry-after": "86400" });
  }

  await env.LOGS.put(key, body, {
    httpMetadata: { contentType: "application/gzip" },
    customMetadata: {
      uploadedAt: String(Date.now()),
      version: (request.headers.get("x-fscout-version") || "").slice(0, 32),
      rawBytes: String(text.length),
    },
  });
  return json({ ok: true });
}

async function listLogs(url, env) {
  const listed = await env.LOGS.list({
    prefix: "logs/",
    cursor: url.searchParams.get("cursor") || undefined,
    limit: 1000,
    include: ["customMetadata"],
  });
  return json({
    logs: listed.objects.map((o) => ({
      key: o.key,
      size: o.size,
      etag: o.etag,
      uploadedAt: Number(o.customMetadata?.uploadedAt || 0),
      version: o.customMetadata?.version || "",
    })),
    cursor: listed.truncated ? listed.cursor : null,
  });
}

async function getLog(key, env) {
  if (!/^logs\/[0-9a-f]{32}\/[0-9a-f]{16}\.lua\.gz$/.test(key)) return json({ error: "bad key" }, 400);
  const obj = await env.LOGS.get(key);
  if (!obj) return json({ error: "not found" }, 404);
  return new Response(obj.body, { headers: { "content-type": "application/gzip", etag: obj.etag } });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    try {
      if (request.method === "GET" && url.pathname === "/health") return json({ ok: true });
      if (request.method !== "GET" && !(await withinBurst(request, env))) {
        return json({ error: "slow down" }, 429, { "retry-after": "10" });
      }
      if (request.method === "POST" && url.pathname === "/v1/upload") return await upload(request, env);
      if (url.pathname.startsWith("/v1/logs")) {
        if (!authorized(request, env)) return json({ error: "unauthorized" }, 401);
        if (request.method !== "GET") return json({ error: "method" }, 405);
        if (url.pathname === "/v1/logs") return await listLogs(url, env);
        return await getLog(decodeURIComponent(url.pathname.slice("/v1/logs/".length)), env);
      }
      return json({ error: "not found" }, 404);
    } catch (err) {
      return json({ error: "server error" }, 500);
    }
  },
};

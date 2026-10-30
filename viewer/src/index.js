// The 3D gear viewer: a page on its own origin (viewer.forever-xp.com) that renders a character
// with Wowhead's model viewer, embedded by the BIS planner as an iframe.
//
// Why a separate worker: the model viewer is third-party code (wow.zamimg.com). It never runs on
// forever-xp.com itself. On this origin there are no cookies, no accounts and no data, the page's
// CSP only allows same-origin requests, and the /zam/* proxy below is the origin's only way out,
// limited to the model viewer's own files. The main site only sends this page numbers
// (race, gender, slot/display-id pairs); viewer/public/gear_params.js validates them.

const ZAM = "https://wow.zamimg.com";

// Only the model viewer's files: path shape, then extension, both allow-lists.
const PATH = /^\/modelviewer\/(classic|live)\/[a-z0-9_./-]+$/i;
const EXT = new Set(["js", "json", "png", "jpg", "jpeg", "webp", "dds", "mo3", "bone", "skin",
  "anim", "db", "wasm", "bin", "skel"]);
const QUERY = /^[a-zA-Z0-9=&._-]*$/;
// Upstream Content-Type is third-party data: anything not on this list serves as octet-stream.
const TYPES = new Set(["application/javascript", "text/javascript", "application/json",
  "image/png", "image/jpeg", "image/webp", "application/octet-stream", "text/plain"]);

/** /zam/<path> -> the wow.zamimg.com path to fetch, or null if it isn't allowed. */
export function zamPath(url) {
  const p = url.pathname.slice("/zam".length);
  if (p.includes("..") || p.includes("//") || p.includes("\\") || !PATH.test(p)) return null;
  const ext = p.slice(p.lastIndexOf(".") + 1).toLowerCase();
  if (!EXT.has(ext)) return null;
  const q = url.search.slice(1);
  return QUERY.test(q) ? p + (q ? `?${q}` : "") : null;
}

// The embedding page (and local dev) may frame this origin; nobody else.
const FRAME_ANCESTORS = "https://forever-xp.com https://www.forever-xp.com https://*.forever-xp.pages.dev";
const CSP = [
  "default-src 'none'",
  "script-src 'self'",            // app.js, the pinned vendor copies, viewer.min.js via /zam/
  "connect-src 'self'",           // model meta/textures go through /zam/ only
  "img-src 'self' blob: data:",
  "style-src 'self' 'unsafe-inline'", // the zam viewer injects inline styles; isolated origin
  "font-src 'self' data:",
  "worker-src blob:",
  `frame-ancestors ${FRAME_ANCESTORS}`,
  "base-uri 'none'",
  "form-action 'none'",
].join("; ");

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/health") return new Response("ok");
    if (url.pathname.startsWith("/zam/")) return proxy(request, url, env);

    const res = await env.ASSETS.fetch(request);
    const h = new Headers(res.headers);
    h.set("X-Content-Type-Options", "nosniff");
    h.set("Referrer-Policy", "no-referrer");
    if ((h.get("Content-Type") || "").includes("text/html")) {
      h.set("Content-Security-Policy", CSP);
      h.set("Cross-Origin-Opener-Policy", "same-origin");
      h.set("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()");
    }
    return new Response(res.body, { status: res.status, headers: h });
  },
};

async function proxy(request, url, env) {
  if (request.method !== "GET" && request.method !== "HEAD") {
    return new Response("Method not allowed", { status: 405, headers: { Allow: "GET, HEAD" } });
  }
  // Browsers label cross-site requests; the proxy serves this origin's page, nothing else.
  const site = request.headers.get("Sec-Fetch-Site");
  if (site && site !== "same-origin" && site !== "none") return new Response("Forbidden", { status: 403 });
  const path = zamPath(url);
  if (!path) return new Response("Not found", { status: 404 });
  if (env.BURST) {
    const { success } = await env.BURST.limit({ key: request.headers.get("CF-Connecting-IP") || "" });
    if (!success) return new Response("Too many requests", { status: 429, headers: { "Retry-After": "10" } });
  }
  const res = await fetch(ZAM + path, {
    method: request.method,
    headers: { "User-Agent": "forever-xp 3D gear viewer (github.com/Jweyant/forever-xp)" },
    cf: { cacheEverything: true, cacheTtl: 86400 },
  });
  const type = (res.headers.get("Content-Type") || "").split(";")[0].trim().toLowerCase();
  return new Response(res.body, {
    status: res.status,
    headers: {
      "Content-Type": TYPES.has(type) ? type : "application/octet-stream",
      "Cache-Control": "public, max-age=86400",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

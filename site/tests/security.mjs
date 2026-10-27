// Hostile-input test for the built site: feeds attack strings through every place a visitor's
// link, saved data or typing reaches (address bar, hash, local storage, search box, gear import)
// and fails if any of it turns into HTML, runs script, or breaks the security headers.
//
//   npm run build && node tests/security.mjs dist
import { chromium } from "playwright";
import { createServer } from "node:http";
import { readFileSync, existsSync, statSync } from "node:fs";
import { join, extname } from "node:path";

const dist = process.argv[2] || "dist";
const failures = [];
const fail = (msg) => { failures.push(msg); console.error(`FAIL ${msg}`); };

// ---- 1. Security headers -------------------------------------------------------------------
const headers = readFileSync(join(dist, "_headers"), "utf8");
const csp = (headers.match(/Content-Security-Policy: (.*)/) || [])[1] || "";
const scriptSrc = (csp.match(/script-src ([^;]*)/) || [])[1] || "";
if (!csp) fail("no Content-Security-Policy in _headers");
if (/'unsafe-inline'|'unsafe-eval'/.test(scriptSrc)) fail("script-src allows unsafe-inline or unsafe-eval");
if (!/frame-ancestors 'none'/.test(csp)) fail("CSP is missing frame-ancestors 'none'");
if (!/object-src 'none'/.test(csp)) fail("CSP is missing object-src 'none'");
for (const h of ["X-Content-Type-Options: nosniff", "X-Frame-Options: DENY", "Referrer-Policy:", "Permissions-Policy:"]) {
  if (!headers.includes(h)) fail(`_headers is missing ${h}`);
}

// ---- 2. Serve the build with the real CSP ----------------------------------------------------
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".xml": "application/xml" };
const server = createServer((req, res) => {
  let p = decodeURIComponent(new URL(req.url, "http://x").pathname);
  let f = join(dist, p);
  if (existsSync(f) && statSync(f).isDirectory()) f = join(f, "index.html");
  if (!existsSync(f)) { res.writeHead(404); return res.end(); }
  const type = TYPES[extname(f)] || "application/octet-stream";
  const h = { "content-type": type };
  if (type === "text/html") h["content-security-policy"] = csp.replace("upgrade-insecure-requests", "");
  res.writeHead(200, h);
  res.end(readFileSync(f));
}).listen(0);
const base = `http://127.0.0.1:${server.address().port}`;

// ---- 3. Attack strings -----------------------------------------------------------------------
const P = `"><img id=xss-probe src=x onerror=window.__xss=1><svg id=xss-probe onload=window.__xss=1></svg><script>window.__xss=1</script>'`;
const E = encodeURIComponent(P);
const zone = (() => { try { return JSON.parse(readFileSync(join("src", "data", "questdb.json"), "utf8"))[0]?.z; } catch { return null; } })();
const slug = zone ? zone.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") : null;
const cases = [
  ["BIS planner link", `/bis/#c=${E}&s=${E}&g=${E}&l=${E}&f=${E}&r=${E}.${E}&src=${E}&cur=0-${E}&plan=0-${E}.1-1&own=${E}&w=${E}:1`],
  ["BIS planner link, prototype names", `/bis/#c=constructor&s=__proto__&g=toString&r=hasOwnProperty.F&f=constructor`],
  ["BIS planner saved state", "/bis/", { storage: { "fxp-gear": `c=${E}&r=${E}&s=${E}` } }],
  ["BIS gear import", "/bis/", { import: `FXPG1:WARRIOR:60:${P}.F:H:head=${P},chest=1` }],
  ["BIS gear import, prototype class", "/bis/", { import: "FXPG1:CONSTRUCTOR:60:Orc.M:H:head=1" }],
  ["Quest search", `/quests/?q=${E}&side=${E}&min=${E}&max=${E}&new=${E}`],
  ["Item database", `/items/?q=${E}&slot=${E}&type=${E}&quality=${E}&min=${E}&max=${E}&src=${E}&stat=${E}&sort=${E}`],
  ["Changes page", `/changes/?q=${E}&src=${E}&area=${E}&race=${E}&date=${E}&cls=${E}&dev=1`],
  ["Talent calculator", `/talents/warrior/#${E}`],
  ["Quest XP table", `/quests/xp/?text=${E}&zone=${E}&verdict=${E}`],
  ...(slug ? [["Zone page", `/quests/zone/${slug}/?text=${E}&side=${E}&new=${E}`]] : []),
  ["Quick search", "/", { search: P }],
  // The accounts API answering with hostile names and plan data (as if the database were tampered with).
  // Signed out: the sign-in buttons must not be plain links into /api/ (checked on every page below).
  ["Signed-out sign-in buttons", "/bis/", { expect: "a[data-save-signin]:not([hidden])[href=\"/account/\"]", api: { "/api/me": { status: 401, body: { error: "signed-out" } } } }],
  ["Account page, hostile saved plans", "/account/", { expect: "[data-plans] tr", api: {
    "/api/me": { name: P },
    "/api/plans": { plans: [
      { id: "AAAAAAAAAAAAAAAA", kind: "bis", name: P, data: P, updated: P },
      { id: "BBBBBBBBBBBBBBBB", kind: "talents", name: P, data: `warlock#${P}`, updated: 1 },
      { id: "CCCCCCCCCCCCCCCC", kind: "talents", name: "ok", data: "javascript:alert(1)//#1", updated: 1 },
      { id: `${P}`, kind: "bis", name: P, data: "c=WARRIOR", updated: 1 },
    ] },
  } }],
];

const browser = await chromium.launch();
for (const [name, path, opts = {}] of cases) {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  const problems = [];
  page.on("dialog", (d) => { problems.push(`dialog opened: ${d.message()}`); d.dismiss().catch(() => {}); });
  page.on("pageerror", (e) => problems.push(`script error: ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error" && /Content Security Policy|Refused to/.test(m.text())) problems.push(`CSP violation: ${m.text().slice(0, 200)}`); });
  if (opts.api) {
    // Test the account code whether or not accounts are switched on in config.ts: mark the page
    // as accounts-on after parsing, before its module scripts run.
    await page.addInitScript(() => document.addEventListener("readystatechange", () => {
      if (document.readyState === "interactive") document.documentElement.dataset.accounts = "on";
    }));
    await page.route("**/api/**", (route) => {
      const path = new URL(route.request().url()).pathname;
      const body = opts.api[path];
      const reply = body && typeof body.status === "number" ? body : body ? { status: 200, body } : { status: 404, body: {} };
      route.fulfill({ status: reply.status, contentType: "application/json", body: JSON.stringify(reply.body) });
    });
  }
  if (opts.storage) {
    await page.addInitScript((s) => { for (const [k, v] of Object.entries(s)) localStorage.setItem(k, v); }, opts.storage);
  }
  await page.goto(base + path, { waitUntil: "load" });
  await page.waitForTimeout(1200);
  if (opts.import) {
    await page.evaluate(() => { const d = document.querySelector(".import"); if (d) d.open = true; });
    await page.fill("#g-import", opts.import);
    await page.click("#g-import-go");
    await page.waitForTimeout(400);
  }
  if (opts.search) {
    await page.keyboard.press("/");
    await page.keyboard.type(opts.search, { delay: 0 });
    await page.waitForTimeout(600);
  }
  const found = await page.evaluate(() => ({
    probe: document.querySelectorAll("#xss-probe, [id='xss-probe']").length,
    ran: !!window.__xss,
    scripts: [...document.querySelectorAll("script:not([src])")].filter((s) => s.textContent.includes("__xss")).length,
    jsLinks: [...document.querySelectorAll("a[href]")].filter((a) => /^\s*javascript:/i.test(a.getAttribute("href") || "")).length,
    apiLinks: [...document.querySelectorAll("a[href]")].filter((a) => new URL(a.href, location.href).pathname.startsWith("/api/")).length,
  }));
  if (found.jsLinks) problems.push(`${found.jsLinks} javascript: link(s) in the page`);
  if (found.apiLinks) problems.push(`${found.apiLinks} plain link(s) into /api/ (sign-in must be a form POST)`);
  if (found.probe) problems.push(`${found.probe} injected element(s) in the page`);
  if (found.ran) problems.push("injected script ran");
  if (found.scripts) problems.push("injected <script> element in the page");
  if (opts.expect && !(await page.$(opts.expect))) problems.push(`nothing rendered for ${opts.expect}, so the case tested nothing`);
  if (problems.length) fail(`${name}: ${problems.join("; ")}`);
  else console.log(`ok   ${name}`);
  await ctx.close();
}
await browser.close();
server.close();

if (failures.length) { console.error(`\n${failures.length} security check(s) failed`); process.exit(1); }
console.log("\nAll security checks passed");

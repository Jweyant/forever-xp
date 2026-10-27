// After `astro build`: hash every inline <script> in the built pages and write dist/_headers with
// a strict Content-Security-Policy and the other security headers Cloudflare Pages should send.
import { createHash } from "node:crypto";
import { readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const dist = process.argv[2] || "dist";
const hashes = new Set();
function walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p);
    else if (name.endsWith(".html")) {
      const html = readFileSync(p, "utf8");
      for (const m of html.matchAll(/<script(?![^>]*\bsrc=)([^>]*)>([\s\S]*?)<\/script>/g)) {
        if (/type="application\/(ld\+)?json"/.test(m[1])) continue;
        if (!m[2].trim()) continue;
        hashes.add(`'sha256-${createHash("sha256").update(m[2]).digest("base64")}'`);
      }
    }
  }
}
walk(dist);
if (hashes.size > 40) console.warn(`csp: ${hashes.size} distinct inline scripts; consider moving some to files`);

const csp = [
  "default-src 'self'",
  `script-src 'self' ${[...hashes].join(" ")} https://static.cloudflareinsights.com https://giscus.app`,
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://giscus.app",
  "font-src 'self' https://fonts.gstatic.com",
  "img-src 'self' data: https://render.worldofwarcraft.com https://avatars.githubusercontent.com",
  "connect-src 'self' https://cloudflareinsights.com https://discord.com https://giscus.app",
  "frame-src https://giscus.app",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self' https://discord.com", // the sign-in form's redirect to Discord
  "object-src 'none'",
  "upgrade-insecure-requests",
].join("; ");

const headers = `/*
  Content-Security-Policy: ${csp}
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()
  Cross-Origin-Opener-Policy: same-origin
  ! Access-Control-Allow-Origin

/_astro/*
  Cache-Control: public, max-age=31536000, immutable

/data/*
  Cache-Control: public, max-age=1800, stale-while-revalidate=86400
`;
writeFileSync(join(dist, "_headers"), headers);
console.log(`csp: wrote ${join(dist, "_headers")} with ${hashes.size} inline script hashes`);

// Draws the share images (Open Graph cards) in site/public/og/: one per site section and one per
// class talent calculator, in the same style as site/public/og.png. Run it when a card's text
// changes and commit the results:
//
//   cd site && node tools/og-cards.mjs
//
// Uses the site's Playwright (a dev dependency). Fonts: Barlow Condensed and Source Sans 3, the
// site's own. With FONT_DIR set to a folder holding the @fontsource/barlow-condensed and
// @fontsource/source-sans-3 packages they're loaded from disk; otherwise from Google Fonts.
// All text here is this repo's own constants, escaped anyway.
import { chromium } from "playwright";
import { readFileSync, mkdirSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "../..");
const out = join(root, "site/public/og");
// Images and fonts go in as data: URLs; Chromium won't load file:// from an in-memory page.
const dataUrl = (file, type) => `data:${type};base64,${readFileSync(file).toString("base64")}`;
const logo = dataUrl(join(root, "site/public/brand/logo-512.png"), "image/png");
const talents = JSON.parse(readFileSync(join(root, "site/src/data/talents.json"), "utf8"));
const CLASS_COLOR = {
  warrior: "#c79c6e", paladin: "#f58cba", hunter: "#abd473", rogue: "#fff569", priest: "#ffffff",
  shaman: "#0070de", mage: "#69ccf0", warlock: "#9482c9", druid: "#ff7d0a",
};
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const list = (a) => (a.length > 1 ? `${a.slice(0, -1).join(", ")} and ${a.at(-1)}` : a[0]);

const cards = [
  { file: "changes", eyebrow: "WoW Forever", title: "Every WoW Forever change", text: "Every Blizzard note and every class, race and talent change in one searchable list. Updated every hour." },
  { file: "bis", eyebrow: "WoW Forever", title: "BIS planner", text: "Best-in-slot gear for every slot. Import your character, pick PvE, PvP or leveling, and see what to chase." },
  { file: "talents", eyebrow: "WoW Forever", title: "Talent calculator", text: "All nine classes, built from the Forever game client, with builds you can share." },
  { file: "guides", eyebrow: "WoW Forever", title: "Leveling guides", text: "Free Horde and Alliance leveling routes, with the time and XP for every step." },
  { file: "quests", eyebrow: "WoW Forever", title: "Quest database", text: "Every quest with its quest giver, map coordinates, objectives and rewards." },
  { file: "quests-xp", eyebrow: "WoW Forever", title: "Quest XP per minute", text: "Every scored quest ranked by XP per minute, travel included, so you know what to skip." },
  { file: "items", eyebrow: "WoW Forever", title: "Item database", text: "Every equippable item with its stats from the game client and where it drops." },
  { file: "scout", eyebrow: "Free addon", title: "ForeverScout", text: "Records how long quests really take, so the leveling routes use real numbers." },
  ...talents.classes.map((c) => ({
    file: `talents-${c.slug}`, eyebrow: "WoW Forever talents", title: `${c.name} talents`, accent: CLASS_COLOR[c.slug],
    text: `${list(c.trees.map((t) => t.name))}. Built from the Forever game client, with builds you can share.`,
  })),
  ...talents.classes.map((c) => ({
    file: `changes-${c.slug}`, eyebrow: "WoW Forever changes", title: `Every ${c.name} change`, accent: CLASS_COLOR[c.slug],
    text: "Blizzard's beta notes and the talent changes read from the Forever client, in one list.",
  })),
  { file: "changes-racials", eyebrow: "WoW Forever changes", title: "Every racial change", text: "Every race's racial changes from Blizzard's beta notes, newest first, each linked to its post." },
];

const fontDir = process.env.FONT_DIR;
const fontCss = fontDir
  ? [
      ["Barlow Condensed", 700, "@fontsource/barlow-condensed/files/barlow-condensed-latin-700-normal.woff2"],
      ["Source Sans 3", 400, "@fontsource/source-sans-3/files/source-sans-3-latin-400-normal.woff2"],
      ["Source Sans 3", 600, "@fontsource/source-sans-3/files/source-sans-3-latin-600-normal.woff2"],
    ].map(([f, w, p]) => {
      const file = join(fontDir, "node_modules", p);
      if (!existsSync(file)) throw new Error(`missing font ${file}`);
      return `@font-face{font-family:"${f}";font-weight:${w};src:url("${dataUrl(file, "font/woff2")}") format("woff2")}`;
    }).join("")
  : "";
const fontLink = fontDir ? "" : '<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@700&family=Source+Sans+3:wght@400;600&display=swap" rel="stylesheet">';

const page = (c) => `<!doctype html><html><head><meta charset="utf-8">${fontLink}<style>${fontCss}
*{margin:0;box-sizing:border-box}
body{width:1200px;height:630px;overflow:hidden;background:radial-gradient(ellipse at 45% 20%,#2a2160 0%,#191838 55%,#121226 100%);font-family:"Source Sans 3",sans-serif;color:#fff;position:relative}
.logo{position:absolute;left:60px;top:150px;width:360px;mix-blend-mode:lighten;-webkit-mask-image:radial-gradient(ellipse 50% 50% at 50% 50%,#000 88%,transparent 100%)}
.col{position:absolute;left:470px;right:70px;top:0;bottom:60px;display:flex;flex-direction:column;justify-content:center}
.eyebrow{font-family:"Barlow Condensed",sans-serif;font-weight:700;font-size:34px;letter-spacing:.06em;text-transform:uppercase;color:#a688f5}
h1{font-family:"Barlow Condensed",sans-serif;font-weight:700;font-size:96px;line-height:1;margin:6px 0 22px;color:${c.accent || "#fff"}}
p{font-size:34px;line-height:1.3;color:#d9d5f0;font-weight:400}
.url{margin-top:26px;font-size:30px;font-weight:600;color:#f2c94c}
.bar{position:absolute;left:0;right:0;bottom:0;height:20px;display:flex;gap:2px}
.bar i{flex:1;background:#0e0e1a}.bar i.p{background:#7c4ddb}.bar i.b{background:#3f7fdc}
</style></head><body>
<img class="logo" src="${logo}" alt="">
<div class="col"><div class="eyebrow">${esc(c.eyebrow)}</div><h1>${esc(c.title)}</h1><p>${esc(c.text)}</p><div class="url">forever-xp.com</div></div>
<div class="bar">${Array.from({ length: 20 }, (_, i) => `<i class="${i < 12 ? "p" : i < 15 ? "b" : ""}"></i>`).join("")}</div>
</body></html>`;

mkdirSync(out, { recursive: true });
const browser = await chromium.launch();
const tab = await browser.newPage({ viewport: { width: 1200, height: 630 } });
for (const c of cards) {
  await tab.setContent(page(c), { waitUntil: "load" });
  await tab.evaluate(() => document.fonts.ready);
  // Shrink the title until it fits on two lines.
  await tab.evaluate(() => {
    const h = document.querySelector("h1");
    let size = 96;
    while (h.getBoundingClientRect().height > size * 2.05 && size > 56) { size -= 4; h.style.fontSize = `${size}px`; }
  });
  await tab.screenshot({ path: join(out, `${c.file}.jpg`), type: "jpeg", quality: 88 });
  console.log(`og: ${c.file}.jpg`);
}
await browser.close();

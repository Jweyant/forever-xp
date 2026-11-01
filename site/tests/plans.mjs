// Sanity test for the BIS planner's suggestions on the built site: loads the planner for every
// class and spec, lets it suggest a plan, and fails on picks no player should be shown:
//   - a Leveling plan with raid drops, PvP rank rewards or raid-tier epics,
//   - an item with no known source while that source is off (the default),
//   - the other faction's PvP or battleground rewards,
//   - an item above the plan's level, the same ring or trinket twice, or a tank without a shield.
//
//   npm run build && node tests/plans.mjs dist
import { chromium } from "playwright";
import { createServer } from "node:http";
import { readFileSync, existsSync, statSync } from "node:fs";
import { join, extname } from "node:path";

const dist = process.argv[2] || "dist";
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml" };
const server = createServer((req, res) => {
  let f = join(dist, decodeURIComponent(new URL(req.url, "http://x").pathname));
  if (existsSync(f) && statSync(f).isDirectory()) f = join(f, "index.html");
  if (!existsSync(f)) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { "content-type": TYPES[extname(f)] || "application/octet-stream" });
  res.end(readFileSync(f));
}).listen(0);
const base = `http://127.0.0.1:${server.address().port}`;

const items = new Map(JSON.parse(readFileSync(join(dist, "data", "items.json"), "utf8")).items.map((i) => [i.id, i]));
const DOLL = ["head", "neck", "shoulder", "back", "chest", "wrist", "hands", "waist", "legs", "feet",
  "finger1", "finger2", "trinket1", "trinket2", "mainhand", "offhand", "ranged"];
const SPECS = { WARRIOR: ["arms", "fury", "prot"], PALADIN: ["holy", "prot", "ret"], HUNTER: ["bm", "mm", "sv"],
  ROGUE: ["assa", "combat", "sub"], PRIEST: ["disc", "holy", "shadow"], SHAMAN: ["ele", "enh", "resto"],
  MAGE: ["arcane", "fire", "frost"], WARLOCK: ["aff", "demo", "destro"], DRUID: ["balance", "cat", "bear", "resto"] };
const RACE = { H: { WARRIOR: "orc", PALADIN: "undead", HUNTER: "troll", ROGUE: "orc", PRIEST: "undead", SHAMAN: "orc", MAGE: "undead", WARLOCK: "orc", DRUID: "tauren" },
  A: { WARRIOR: "human", PALADIN: "human", HUNTER: "dwarf", ROGUE: "human", PRIEST: "human", SHAMAN: "dwarf", MAGE: "human", WARLOCK: "human", DRUID: "nightelf" } };
// The other side's PvP rank titles and battleground factions, as item names start or contain them.
const FOREIGN = {
  H: /^(Private|Corporal|Master Sergeant|Sergeant Major|Knight|Knight-Lieutenant|Knight-Captain|Knight-Champion|Lieutenant Commander|Commander|Marshal|Field Marshal|Grand Marshal)'s |Stormpike|Highlander's|of Arathor|Insignia of the Alliance/,
  A: /^(Scout|Grunt|Senior Sergeant|First Sergeant|Stone Guard|Blood Guard|Legionnaire|Centurion|Champion|Lieutenant General|General|Warlord|High Warlord)'s |Frostwolf|Defiler's|Outrider's|Insignia of the Horde/,
};
const endgame = (it) => it.pvprank || it.q >= 5 || (it.src || []).some((s) => s.t === "raid" || s.t === "pvp") || (it.q >= 3 && it.ilvl >= 66);

const jobs = [];
for (const [c, ss] of Object.entries(SPECS)) for (const s of ss) {
  jobs.push({ c, s, g: "pve", l: 60, f: "H" }, { c, s, g: "pvp", l: 60, f: "A" }, { c, s, g: "level", l: 60, f: "A" }, { c, s, g: "level", l: 35, f: "H" });
}
const failures = [];
const browser = await chromium.launch();
async function worker() {
  const page = await (await browser.newContext()).newPage();
  page.on("pageerror", (e) => failures.push(`page error: ${e.message}`));
  for (let j = jobs.shift(); j; j = jobs.shift()) {
    const tag = `${j.c} ${j.s} ${j.g} level ${j.l} (${j.f})`;
    await page.goto("about:blank");
    await page.goto(`${base}/bis/#c=${j.c}&s=${j.s}&g=${j.g}&l=${j.l}&f=${j.f}&r=${RACE[j.f][j.c]}.M`);
    await page.waitForFunction(() => document.querySelector("#gear")?.getAttribute("aria-busy") === null, null, { timeout: 30000 });
    const raw = await page.evaluate(() => new URLSearchParams(location.hash.slice(1)).get("plan") || "");
    const plan = Object.fromEntries(raw.split(".").filter(Boolean).map((x) => x.split("-").map(Number)).map(([i, id]) => [DOLL[i], id]));
    if (Object.keys(plan).length < 10) failures.push(`${tag}: only ${Object.keys(plan).length} slots filled`);
    for (const [slot, id] of Object.entries(plan)) {
      const it = items.get(id);
      if (!it) { failures.push(`${tag}: ${slot} item ${id} isn't in the database`); continue; }
      const name = `${slot} ${it.name} (${id})`;
      if (j.g === "level" && endgame(it)) failures.push(`${tag}: endgame item in a Leveling plan: ${name}`);
      if (!(it.src || []).length) failures.push(`${tag}: item with no known source: ${name}`);
      if ((it.side && it.side !== j.f) || FOREIGN[j.f].test(it.name)) failures.push(`${tag}: other faction's item: ${name}`);
      if ((it.lvl ?? it.req) > j.l) failures.push(`${tag}: above level ${j.l}: ${name}`);
    }
    if (plan.finger1 && plan.finger1 === plan.finger2) failures.push(`${tag}: the same ring twice`);
    if (plan.trinket1 && plan.trinket1 === plan.trinket2) failures.push(`${tag}: the same trinket twice`);
    if (j.s === "prot" && j.l === 60 && items.get(plan.offhand)?.slot !== "shield") failures.push(`${tag}: tank plan without a shield`);
  }
}
await Promise.all([worker(), worker(), worker(), worker()]);
await browser.close(); server.close();
for (const f of failures) console.error(`FAIL ${f}`);
console.log(failures.length ? `\n${failures.length} problem(s) in suggested plans` : "All suggested plans passed");
process.exit(failures.length ? 1 : 0);

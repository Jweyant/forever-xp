// Shared item helpers: one cached load of the gear database, source text, and the in-game style
// tooltip used by the BIS planner, item links across the site and the item pages.
import { STAT_LABEL, type Item, type Stats } from "./gear/model";

export const QUALITY = ["poor", "common", "uncommon", "rare", "epic", "legendary", "artifact"];
export const ICON = (n: string, size = 56) =>
  `https://render.worldofwarcraft.com/us/icons/${[18, 36, 56].includes(size) ? size : 56}/${String(n).toLowerCase().replace(/ /g, "-").replace(/[^a-z0-9_-]/g, "")}.jpg`;
// Set bonus and effect text from the client can hold unresolved spell variables ($s1, $/1000;s1).
export const cleanFx = (s: string) => s.replace(/\$\/?\d*;?[a-zA-Z]+\d*/g, "?").replace(/ for \./g, ".").replace(/\s{2,}/g, " ");
/** A finite number or 0, for numeric fields that come from data files. */
export const num = (v: unknown) => (Number.isFinite(Number(v)) ? Number(v) : 0);
export const esc = (s: string) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]!));
export type ItemSet = { name: string; bonuses: { n: number; stats: Stats; text: string }[] };
export interface GearDb { build: string; items: Item[]; sets: Record<string, ItemSet> }

let dbPromise: Promise<GearDb & { byId: Map<number, Item> }> | null = null;
export function loadGear() {
  dbPromise ??= fetch("/data/items.json").then((r) => {
    if (!r.ok) throw new Error(`items ${r.status}`);
    return r.json();
  }).then((d: GearDb) => ({ ...d, byId: new Map(d.items.map((i) => [i.id, i])) }));
  return dbPromise;
}

export const SRC_LABEL: Record<string, string> = {
  chest: "Chest", raid: "Raid", dungeon: "Dungeon", pvp: "PvP", rep: "Reputation", quest: "Quest", craft: "Crafted",
  vendor: "Vendor", drop: "Drop", world: "World drop", logged: "Seen in Forever",
};
/** "Confirmed in Forever by 3 players": how many different players' logs saw a source drop this item. */
export function seenText(seen: unknown): string {
  const n = Math.floor(Number(seen));
  if (!Number.isFinite(n) || n < 1) return "";
  return `Confirmed in Forever by ${n} player${n === 1 ? "" : "s"}`;
}
export function srcText(it: Item) {
  const s = it.src?.[0];
  if (!s) return "Source not known yet";
  const where = [s.n, s.z].filter(Boolean).join(", ");
  const seen = seenText(s.seen);
  return `${SRC_LABEL[s.t] || s.t}${where ? ": " + where : ""}${seen ? ` (${seen[0].toLowerCase()}${seen.slice(1)})` : ""}`;
}
/** Dungeon or raid page slug, matching tools/build_raids.py. */
export const instSlug = (name: string) => name.toLowerCase().replace(/'/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
/** The item's main source as HTML, linking quests and (when `instances` has a page for it) dungeons and raids. */
export function srcHtml(it: Item, instances: Set<string> = new Set()) {
  const s = it.src?.[0];
  if (!s) return esc(srcText(it));
  const label = esc(SRC_LABEL[s.t] || s.t);
  const seen = seenText(s.seen);
  const tail = seen ? ` (${esc(seen[0].toLowerCase() + seen.slice(1))})` : "";
  if (s.t === "quest" && num(s.qid) > 0) return `${label}: <a href="/quests/${num(s.qid)}/">${esc(s.n || `Quest ${num(s.qid)}`)}</a>${tail}`;
  const slug = s.z ? instSlug(s.z) : "";
  if ((s.t === "raid" || s.t === "dungeon") && slug && instances.has(slug)) {
    return `${label}: ${s.n ? `${esc(s.n)}, ` : ""}<a href="/raids/${esc(slug)}/">${esc(s.z || "")}</a>${tail}`;
  }
  return esc(srcText(it));
}
export const SLOT_NAME: Record<string, string> = {
  head: "Head", neck: "Neck", shoulder: "Shoulder", back: "Back", chest: "Chest", wrist: "Wrist", hands: "Hands",
  waist: "Waist", legs: "Legs", feet: "Feet", finger: "Finger", trinket: "Trinket", mainhand: "Main Hand",
  offhand: "Off Hand", onehand: "One-Hand", twohand: "Two-Hand", ranged: "Ranged", relic: "Relic", shield: "Off Hand",
  holdable: "Held In Off-hand", shirt: "Shirt", tabard: "Tabard", ammo: "Ammo",
};
const cap = (s: string) => s.replace(/[12]$/, "").replace(/^./, (c) => c.toUpperCase());

/** Tooltip body for an item, in the game's layout. `extra` lines go at the bottom. */
export function tooltipHtml(it: Item, sets: Record<string, ItemSet> = {}, extra: string[] = []) {
  const q = QUALITY[num(it.q)] || "common";
  const L: string[] = [];
  L.push(`<div class="tt-head"><span class="ico qb-${q}">${it.icon ? `<img src="${esc(ICON(it.icon))}" alt="">` : ""}</span>
    <div><p class="tt-name q-${q}">${esc(it.name)}</p><p class="tt-muted">Item level ${num(it.ilvl)}</p></div></div>`);
  if (it.bop) L.push(`<p>Binds when picked up</p>`);
  const slot = SLOT_NAME[it.slot] || cap(it.slot || "");
  const type = it.type && it.type !== "misc" ? cap(it.type) : "";
  if (slot || type) L.push(`<p class="tt-row"><span>${esc(slot)}</span><span>${esc(type)}</span></p>`);
  if (it.weapon) L.push(`<p class="tt-row"><span>${num(it.weapon.min)} – ${num(it.weapon.max)} Damage</span><span>Speed ${num(it.weapon.speed).toFixed(2)}</span></p><p>(${num(it.weapon.dps)} damage per second)</p>`);
  if (it.stats.armor) L.push(`<p>${num(it.stats.armor)} Armor</p>`);
  const primary = ["str", "agi", "sta", "int", "spi"];
  for (const k of primary) if (it.stats[k]) L.push(`<p>+${num(it.stats[k])} ${STAT_LABEL[k]}</p>`);
  for (const [k, v] of Object.entries(it.stats)) {
    if (primary.includes(k) || k === "armor" || k === "dps") continue;
    L.push(`<p class="tt-green">Equip: ${k.endsWith("_pct") ? `Improves ${esc(STAT_LABEL[k]?.replace(" %", "") || k)} by ${num(v)}%` : `+${num(v)} ${esc(STAT_LABEL[k] || k)}`}.</p>`);
  }
  for (const f of it.fx || []) L.push(`<p class="tt-green">${f.on === "use" ? "Use" : f.on === "hit" ? "Chance on hit" : "Equip"}: ${esc(cleanFx(f.text))}</p>`);
  if (it.set && sets[it.set]) {
    const s = sets[it.set];
    L.push(`<p class="tt-gold">${esc(s.name)}</p>`);
    for (const b of s.bonuses) {
      const txt = b.text || Object.entries(b.stats).map(([k, v]) => `+${num(v)} ${STAT_LABEL[k] || k}`).join(", ");
      if (txt) L.push(`<p class="tt-muted">(${num(b.n)}) Set: ${esc(cleanFx(txt))}</p>`);
    }
  }
  if (it.req) L.push(`<p>Requires Level ${num(it.req)}</p>`);
  L.push(`<p class="tt-src">${esc(srcText(it))}</p>`);
  return L.concat(extra).join("");
}

/** Place a tooltip next to an element, inside the viewport. `el` is position:fixed. */
export function placeTip(tip: HTMLElement, anchor: Element) {
  const r = anchor.getBoundingClientRect();
  tip.hidden = false;
  const w = tip.offsetWidth, h = tip.offsetHeight, vw = window.innerWidth, vh = window.innerHeight;
  let x = r.right + 10, y = r.top;
  if (x + w > vw - 8) x = r.left - w - 10;
  if (x < 8) { x = Math.max(8, Math.min(vw - w - 8, r.left)); y = r.bottom + 8; if (y + h > vh - 8) y = r.top - h - 8; }
  y = Math.max(8, Math.min(y, vh - h - 8));
  tip.style.left = `${x}px`; tip.style.top = `${y}px`;
}

/** JSON for a <script type="application/json"> block: no "</script>" or HTML comment can break out. */
export const jsonForHtml = (v: unknown) => JSON.stringify(v).replace(/</g, "\\u003c").replace(/>/g, "\\u003e").replace(/&/g, "\\u0026");

// ---------- Non-gear items (consumables, trade goods, recipes, quest items...) ----------
/** A non-gear item from /data/other-items.json (tools/build_items.py). No page of its own. */
export interface OtherItem {
  id: number; n: string; q: number; c: string; rl?: number; icon?: string;
  ds?: string; u?: string[]; st?: number; b?: number; sp?: number; il?: number;
  d?: [string, string][]; v?: string[]; o?: string[]; qs?: [number, string]; qr?: [number, string][]; qu?: [number, string][];
}
let otherPromise: Promise<{ list: OtherItem[]; byId: Map<number, OtherItem> }> | null = null;
/** Load and validate the non-gear items once per page. */
export function loadOther() {
  otherPromise ??= fetch("/data/other-items.json").then((r) => (r.ok ? r.json() : [])).catch(() => [])
    .then((l: unknown) => {
      const list = (Array.isArray(l) ? l : []).filter((o): o is OtherItem =>
        !!o && typeof o === "object" && num((o as OtherItem).id) > 0 && typeof (o as OtherItem).n === "string" && typeof (o as OtherItem).c === "string");
      return { list, byId: new Map(list.map((o) => [num(o.id), o])) };
    });
  return otherPromise;
}
const txt = (v: unknown) => (typeof v === "string" ? v : "");
const money = (c: number) => {
  const g = Math.floor(c / 10000), s = Math.floor((c % 10000) / 100), cu = c % 100;
  return [g && `${g}g`, s && `${s}s`, cu && `${cu}c`].filter(Boolean).join(" ");
};
/** Tooltip for a non-gear item, in the same style as gear. Every value is escaped or numeric. */
export function otherTooltipHtml(o: OtherItem) {
  const q = QUALITY[num(o.q)] || "common";
  const L: string[] = [];
  L.push(`<div class="tt-head"><span class="ico qb-${q}">${txt(o.icon) ? `<img src="${esc(ICON(txt(o.icon)))}" alt="">` : ""}</span>
    <div><p class="tt-name q-${q}">${esc(txt(o.n))}</p><p class="tt-muted">${esc(txt(o.c))}${num(o.il) > 1 ? `, item level ${num(o.il)}` : ""}</p></div></div>`);
  if (num(o.b) === 1) L.push(`<p>Binds when picked up</p>`);
  else if (num(o.b) === 2) L.push(`<p>Binds when equipped</p>`);
  if (o.c === "Quest item") L.push(`<p>Quest Item</p>`);
  for (const u of (Array.isArray(o.u) ? o.u : []).slice(0, 3)) if (txt(u)) L.push(`<p class="tt-green">${o.c === "Recipe" ? "Use: Teaches" : "Use:"} ${esc(cleanFx(txt(u)))}</p>`);
  if (txt(o.ds)) L.push(`<p class="tt-gold">"${esc(cleanFx(txt(o.ds)))}"</p>`);
  if (num(o.st) > 1) L.push(`<p class="tt-muted">Stacks to ${num(o.st)}</p>`);
  if (num(o.rl) > 1) L.push(`<p>Requires Level ${num(o.rl)}</p>`);
  if (num(o.sp) > 0) L.push(`<p class="tt-muted">Sell price: ${esc(money(num(o.sp)))}</p>`);
  const where = Array.isArray(o.d) && Array.isArray(o.d[0]) ? `Drops from ${txt(o.d[0][0])}` : Array.isArray(o.v) && txt(o.v[0]) ? `Sold by ${txt(o.v[0])}`
    : Array.isArray(o.o) && txt(o.o[0]) ? `Found in ${txt(o.o[0])}` : Array.isArray(o.qr) && Array.isArray(o.qr[0]) ? `Reward from ${txt(o.qr[0][1])}` : "";
  if (where) L.push(`<p class="tt-src">${esc(where)}</p>`);
  return L.join("");
}

// Shared item helpers: one cached load of the gear database, source text, and the in-game style
// tooltip used by the BIS planner, item links across the site and the item pages.
import { STAT_LABEL, type Item, type Stats } from "./gear/model";

export const QUALITY = ["poor", "common", "uncommon", "rare", "epic", "legendary", "artifact"];
export const ICON = (n: string, size = 56) =>
  `https://render.worldofwarcraft.com/us/icons/${[18, 36, 56].includes(size) ? size : 56}/${String(n).toLowerCase().replace(/[^a-z0-9_-]/g, "")}.jpg`;
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

// BIS planner: the character sheet, suggestions, picker, stats and sharing.
// State lives in the URL hash (shareable) and in localStorage (comes back next visit).
import {
  CLASSES, SPECS, GOALS, WEIGHT_KEYS, STAT_LABEL, PAPERDOLL, DOLL_LABEL, SOURCE_KINDS, CRIT_RATING, HIT_RATING,
  weightsFor, canUse, fits, score, sourceKind, canDualWield,
  type Item, type Stats, type Goal, type DollSlot,
} from "./model";
import { loadGear, tooltipHtml, placeTip, srcText, ICON, QUALITY, esc, type ItemSet } from "../items";
import { drawFigure, type FigItem } from "./figure";
import { toggle3d, send3d } from "./viewer3d";
import { afterSignIn } from "../account";
afterSignIn(); // put back a plan the sign-in round trip dropped from the address

// ---------- state ----------
type Side = "H" | "A";
interface State {
  cls: string; spec: string; goal: Goal; level: number; side: Side; race: string; body: "M" | "F";
  sources: Set<string>; cur: Partial<Record<DollSlot, number>>; plan: Partial<Record<DollSlot, number>>;
  owned: Set<number>; custom: Stats | null;
}
const ALL_SOURCES = SOURCE_KINDS.map((s) => s.key);
const RACES: Record<string, { name: string; side: Side | "both"; icon?: string }> = {
  human: { name: "Human", side: "A", icon: "human" }, dwarf: { name: "Dwarf", side: "A", icon: "dwarf" },
  nightelf: { name: "Night Elf", side: "A", icon: "nightelf" }, gnome: { name: "Gnome", side: "A", icon: "gnome" },
  orc: { name: "Orc", side: "H", icon: "orc" }, undead: { name: "Undead", side: "H", icon: "undead" },
  tauren: { name: "Tauren", side: "H", icon: "tauren" }, troll: { name: "Troll", side: "H", icon: "troll" },
  skyborne: { name: "Skyborne", side: "both" },
};
const RACE_TOKEN: Record<string, string> = { scourge: "undead", undead: "undead", nightelf: "nightelf" };
const st: State = {
  cls: "WARRIOR", spec: "fury", goal: "pve", level: 60, side: "H", race: "orc", body: "M",
  sources: new Set(ALL_SOURCES), cur: {}, plan: {}, owned: new Set(), custom: null,
};
let view: "plan" | "cur" = "plan";
let items: Item[] = [];
let byId = new Map<number, Item>();
let sets: Record<string, ItemSet> = {};
const $ = <T extends HTMLElement>(sel: string) => document.querySelector<T>(sel)!;
// Strict allow-list lookups: only the object's own keys count, never inherited ones like "constructor".
const has = (o: object, k: unknown): k is string => typeof k === "string" && Object.prototype.hasOwnProperty.call(o, k);
const toast = (msg: string, action?: { label: string; run: () => void }) =>
  (window as unknown as { fxpToast?: (m: string, a?: typeof action) => void }).fxpToast?.(msg, action);

function weights(): Stats { return st.goal === "custom" && st.custom ? st.custom : weightsFor(st.cls, st.spec, st.goal); }
// Melee weapon DPS matters little to hunters, ranged DPS little to melee, off-hand DPS counts half.
function slotWeights(doll: DollSlot, it: Item): Stats {
  const w = weights();
  if (!it.weapon) return w;
  const hunter = st.cls === "HUNTER";
  let k = 1;
  if (doll === "ranged") k = hunter ? 1 : 0.08;
  else if (hunter) k = 0.15;
  else if (doll === "offhand") k = 0.5;
  if (it.slot === "twohand" && !hunter) k *= 1.9;
  return k === 1 ? w : { ...w, dps: (w.dps || 0) * k };
}
const val = (doll: DollSlot, it: Item | undefined) => (it ? score(it, slotWeights(doll, it)) : 0);
const gearOf = () => (view === "plan" ? st.plan : st.cur);

// ---------- URL + storage ----------
function encode(): string {
  const p = new URLSearchParams();
  p.set("c", st.cls); p.set("s", st.spec); p.set("g", st.goal); p.set("l", String(st.level)); p.set("f", st.side);
  p.set("r", `${st.race}.${st.body}`);
  if (st.sources.size !== ALL_SOURCES.length) p.set("src", [...st.sources].join("."));
  const slots = (o: State["cur"]) => PAPERDOLL.filter((d) => o[d]).map((d) => `${PAPERDOLL.indexOf(d)}-${o[d]}`).join(".");
  if (Object.keys(st.cur).length) p.set("cur", slots(st.cur));
  if (Object.keys(st.plan).length) p.set("plan", slots(st.plan));
  if (st.owned.size) p.set("own", [...st.owned].join("."));
  if (st.goal === "custom" && st.custom) p.set("w", Object.entries(st.custom).filter(([, v]) => v).map(([k, v]) => `${k}:${+v.toFixed(3)}`).join("."));
  return p.toString();
}
function decode(h: string) {
  const p = new URLSearchParams(h.replace(/^#/, ""));
  const c = p.get("c");
  if (has(CLASSES, c)) st.cls = c;
  const specs = SPECS[st.cls];
  st.spec = specs.find((s) => s.key === p.get("s"))?.key ?? specs[0].key;
  st.goal = GOALS.find((g) => g.key === p.get("g"))?.key ?? st.goal;
  const l = Math.round(+(p.get("l") || 60)); if (l >= 1 && l <= 60) st.level = l;
  if (p.get("f") === "A" || p.get("f") === "H") st.side = p.get("f") as Side;
  const [race, body] = (p.get("r") || "").split(".");
  st.race = has(RACES, race) ? race : st.side === "A" ? "human" : "orc";
  st.body = body === "F" ? "F" : "M";
  if (p.get("src")) st.sources = new Set(p.get("src")!.split(".").filter((s) => ALL_SOURCES.includes(s as never)));
  const slots = (v: string | null) => {
    const o: State["cur"] = {};
    for (const part of (v || "").split(".")) { const [i, id] = part.split("-").map(Number); if (PAPERDOLL[i] && id) o[PAPERDOLL[i]] = id; }
    return o;
  };
  st.cur = slots(p.get("cur")); st.plan = slots(p.get("plan"));
  st.owned = new Set((p.get("own") || "").split(".").map(Number).filter(Boolean));
  if (p.get("w")) {
    st.custom = {};
    for (const kv of p.get("w")!.split(".")) { const [k, v] = kv.split(":"); if (k) st.custom[k] = +v; }
  }
}
function save() {
  const h = encode();
  history.replaceState(null, "", `#${h}`);
  try { localStorage.setItem("fxp-gear", h); } catch { /* storage blocked */ }
}

// ---------- import from the game ----------
function importGear(text: string): string {
  const m = text.trim().match(/^FXPG1:([A-Z]+):(\d+):([A-Za-z]+)(?:\.([MF]))?:([AH]):(.*)$/);
  if (!m) return "That doesn't look like a ForeverScout gear string. In game, type /fscout gear and copy the whole line.";
  const [, cls, lvl, raceTok, body, side, rest] = m;
  if (!has(CLASSES, cls)) return "Unknown class in that gear string.";
  if (cls !== st.cls) { st.cls = cls; st.spec = SPECS[cls][0].key; }
  st.level = Math.min(60, Math.max(1, +lvl)); st.side = side as Side;
  const rk = RACE_TOKEN[raceTok.toLowerCase()] || raceTok.toLowerCase();
  if (has(RACES, rk)) st.race = rk;
  if (body) st.body = body as "M" | "F";
  st.cur = {}; let missing = 0, n = 0;
  for (const part of rest.split(",")) {
    const [slot, idRaw] = part.split("=");
    const doll = (PAPERDOLL as readonly string[]).includes(slot) ? (slot as DollSlot) : undefined;
    const id = parseInt(idRaw, 10);
    if (doll && id) { st.cur[doll] = id; n++; if (!byId.has(id)) missing++; }
  }
  st.plan = { ...st.cur }; view = "cur";
  return `Imported ${n} items for your level ${st.level} ${RACES[st.race]?.name || ""} ${CLASSES[cls].name}.` + (missing ? ` ${missing} aren't in the gear database yet and count as zero.` : "");
}

// ---------- suggestions ----------
function candidates(doll: DollSlot): Item[] {
  return items.filter((it) => it.q >= 1 && (it.lvl ?? it.req) <= st.level && (!it.side || it.side === st.side)
    && canUse(it, st.cls, st.level) && fits(doll, it, st.cls) && st.sources.has(sourceKind(it)));
}
function suggest(): State["plan"] {
  const plan: State["plan"] = {};
  const best = (doll: DollSlot, exclude: number[] = []) => {
    let top: Item | undefined, topV = 0;
    for (const it of candidates(doll)) {
      if (exclude.includes(it.id)) continue;
      const v = val(doll, it);
      if (v > topV) { top = it; topV = v; }
    }
    return top;
  };
  for (const d of PAPERDOLL) {
    if (["finger2", "trinket2", "mainhand", "offhand"].includes(d)) continue;
    const it = best(d); if (it) plan[d] = it.id;
  }
  const r2 = best("finger2", plan.finger1 ? [plan.finger1] : []); if (r2) plan.finger2 = r2.id;
  const t2 = best("trinket2", plan.trinket1 ? [plan.trinket1] : []); if (t2) plan.trinket2 = t2.id;
  const mains = candidates("mainhand");
  const twoH = mains.filter((i) => i.slot === "twohand").sort((a, b) => val("mainhand", b) - val("mainhand", a))[0];
  const oneH = mains.filter((i) => i.slot !== "twohand").sort((a, b) => val("mainhand", b) - val("mainhand", a))[0];
  const offs = candidates("offhand").filter((i) => !oneH || i.id !== oneH.id || canDualWield(st.cls));
  const off = offs.filter((i) => !oneH || i.id !== oneH.id).sort((a, b) => val("offhand", b) - val("offhand", a))[0];
  if (twoH && val("mainhand", twoH) >= val("mainhand", oneH) + val("offhand", off)) plan.mainhand = twoH.id;
  else { if (oneH) plan.mainhand = oneH.id; if (off) plan.offhand = off.id; }
  return plan;
}

// ---------- character sheet ----------
const LEFT: DollSlot[] = ["head", "neck", "shoulder", "back", "chest", "wrist"];
const RIGHT: DollSlot[] = ["hands", "waist", "legs", "feet", "finger1", "finger2", "trinket1", "trinket2"];
const BOTTOM: DollSlot[] = ["mainhand", "offhand", "ranged"];
// Empty-slot glyphs: simple line drawings, drawn for this site.
const GLYPH: Record<string, string> = {
  head: "M7 16c0-6 4-10 9-10s9 4 9 10v4h-4v-3c-2-1-8-1-10 0v3H7z", neck: "M9 7c2 6 12 6 14 0M16 13v4m-3 2a3 3 0 1 0 6 0 3 3 0 1 0-6 0",
  shoulder: "M5 20c0-7 5-11 11-11s11 4 11 11l-5-2-6 2-6-2z", back: "M9 6h14l3 20-10 2-10-2z",
  chest: "M8 7l5-2 3 3 3-3 5 2 2 6-3 1v12H9V14l-3-1z", wrist: "M9 11h14v10H9zM9 16h14",
  hands: "M11 26V13a2 2 0 0 1 4 0v-3a2 2 0 0 1 4 0v3a2 2 0 0 1 4 0v8c0 3-2 5-5 5z", waist: "M6 13h20v7H6zM14 13h5v7h-5z",
  legs: "M10 6h12l1 20h-5l-2-12-2 12H9z", feet: "M12 6h6v12l8 4v4H8v-6l4-2z", finger1: "M16 10a7 7 0 1 0 0 14 7 7 0 1 0 0-14zM13 7h6l-3 3z",
  finger2: "M16 10a7 7 0 1 0 0 14 7 7 0 1 0 0-14zM13 7h6l-3 3z", trinket1: "M16 6l8 10-8 10-8-10z", trinket2: "M16 6l8 10-8 10-8-10z",
  mainhand: "M22 5l5 0 0 5-13 13 2 2-3 3-2-2-3 3-2-2 3-3-2-2 3-3 2 2z", offhand: "M16 5l10 3v8c0 6-4 9-10 11C10 25 6 22 6 16V8z",
  ranged: "M9 5c10 3 14 9 14 11S19 24 9 27M9 5v22",
};

function slotButton(d: DollSlot) {
  const gear = gearOf();
  const it = gear[d] ? byId.get(gear[d]!) : undefined;
  const other = (view === "plan" ? st.cur : st.plan)[d];
  const up = view === "plan" && it && val(d, it) - val(d, other ? byId.get(other) : undefined) > 0.05;
  const owned = it && st.owned.has(it.id);
  const q = it ? QUALITY[it.q] || "common" : "";
  return `<button type="button" class="slot ${it ? `qb-${q} full` : "empty"}" data-slot="${d}"
      aria-label="${DOLL_LABEL[d]}: ${it ? esc(it.name) : "empty"}. Click to change${it ? ", right-click to remove" : ""}.">
    <svg viewBox="0 0 32 32" class="glyph" aria-hidden="true"><path d="${GLYPH[d]}"/></svg>
    ${it?.icon ? `<img src="${esc(ICON(it.icon))}" alt="" width="52" height="52" loading="lazy">` : ""}
    ${up ? `<span class="badge up" title="Upgrade over current"></span>` : ""}${owned ? `<span class="badge own" title="Owned">✓</span>` : ""}
  </button>`;
}

/** The figure in the middle, drawn with each equipped item (see figure.ts). */
function figure() {
  const gear = gearOf();
  const items: Partial<Record<DollSlot, FigItem>> = {};
  for (const d of PAPERDOLL) {
    const it = gear[d] ? byId.get(gear[d]!) : undefined;
    if (it) items[d] = { q: Number(it.q), type: it.type, slot: it.slot };
  }
  return drawFigure({ race: has(RACES, st.race) ? st.race : "human", body: st.body === "F" ? "F" : "M", gear: items });
}

function portraitIcon() {
  const r = RACES[st.race];
  return r?.icon ? `achievement_character_${r.icon}_${st.body === "F" ? "female" : "male"}` : `classicon_${st.cls.toLowerCase()}`;
}

function renderDoll() {
  const spec = SPECS[st.cls].find((s) => s.key === st.spec);
  const t = totals(gearOf());
  const doll = $("#g-doll");
  doll.dataset.klass = st.cls.toLowerCase();
  doll.innerHTML = `
    <div class="unit">
      <span class="portrait"><img src="${esc(ICON(portraitIcon()))}" alt="" width="56" height="56"><b class="lvl">${Number(st.level)}</b></span>
      <span class="who"><b>${esc(RACES[st.race]?.name || "")} ${esc(CLASSES[st.cls].name)}</b><span>${esc(spec?.name || "")}, ${st.side === "H" ? "Horde" : "Alliance"}</span></span>
      <span class="pow"><span>${view === "plan" ? "Plan score" : "Current score"}</span><b>${Number(t.v)}</b></span>
    </div>
    <div class="col left">${LEFT.map(slotButton).join("")}</div>
    <div class="figure">${figure()}</div>
    <div class="col right">${RIGHT.map(slotButton).join("")}</div>
    <div class="row bottom">${BOTTOM.map(slotButton).join("")}</div>`;
  document.querySelectorAll<HTMLButtonElement>("[data-view]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.view === view)));
}

function slotTip(d: DollSlot) {
  const id = gearOf()[d];
  const it = id ? byId.get(id) : undefined;
  if (!it) return `<p class="tt-name">${DOLL_LABEL[d]}</p><p class="tt-muted">Empty. Click to choose an item.</p>`;
  const other = (view === "plan" ? st.cur : st.plan)[d];
  const diff = Math.round((val(d, it) - val(d, other ? byId.get(other) : undefined)) * 10) / 10;
  const spec = SPECS[st.cls].find((s) => s.key === st.spec)?.name || "";
  return tooltipHtml(it, sets, [
    `<p class="tt-score">Score ${val(d, it)} for ${esc(spec)}${view === "plan" && other !== it.id ? ` (${diff >= 0 ? "+" : ""}${diff} over current)` : ""}</p>`,
    `<p class="tt-hint">Click to change. Right-click to remove.</p>`,
  ]);
}

// ---------- stats ----------
function totals(o: State["plan"]) {
  const t: Stats = {}; let v = 0;
  for (const d of PAPERDOLL) {
    const it = o[d] ? byId.get(o[d]!) : undefined;
    if (!it) continue;
    v += val(d, it);
    for (const [k, n] of Object.entries(it.stats)) if (k !== "dps") t[k] = (t[k] || 0) + n;
  }
  // Set bonuses that grant stats, once enough pieces are worn.
  const count: Record<string, number> = {};
  for (const d of PAPERDOLL) { const it = o[d] ? byId.get(o[d]!) : undefined; if (it?.set) count[it.set] = (count[it.set] || 0) + 1; }
  for (const [sid, n] of Object.entries(count)) for (const b of sets[sid]?.bonuses || []) if (n >= b.n) for (const [k, x] of Object.entries(b.stats)) t[k] = (t[k] || 0) + x;
  return { t, v: Math.round(v) };
}
const GROUPS: [string, string[]][] = [
  ["Base", ["str", "agi", "sta", "int", "spi", "armor"]],
  ["Physical", ["ap", "rap", "hit", "hit_pct", "crit", "crit_pct", "haste", "expertise"]],
  ["Spell", ["sp", "sp_fire", "sp_frost", "sp_shadow", "sp_nature", "sp_arcane", "sp_holy", "heal", "spellhit", "spellhit_pct", "spellcrit", "spellcrit_pct", "mp5", "spen"]],
  ["Defense", ["def", "dodge", "parry", "block", "blockv", "hp5", "fire_res", "frost_res", "shadow_res", "nature_res", "arcane_res"]],
];
function statValue(k: string, n: number) {
  if (k === "crit" || k === "spellcrit") return `${n} <small>(${(n / CRIT_RATING).toFixed(1)}%)</small>`;
  if (k === "hit" || k === "spellhit") return `${n} <small>(${(n / HIT_RATING).toFixed(1)}%)</small>`;
  if (k.endsWith("_pct")) return `${n}%`;
  return String(Math.round(n * 10) / 10);
}
function renderStats() {
  const cur = totals(st.cur), plan = totals(st.plan), w = weights();
  $("#g-stats").innerHTML = GROUPS.map(([name, keys]) => {
    const rows = keys.filter((k) => cur.t[k] || plan.t[k]);
    if (!rows.length) return "";
    return `<section><h3>${name}</h3><dl>${rows.map((k) => {
      const a = cur.t[k] || 0, b = plan.t[k] || 0, dlt = Math.round((b - a) * 10) / 10;
      return `<div class="${(w[k] || 0) > 0 ? "wanted" : ""}"><dt>${esc(STAT_LABEL[k] || k)}</dt><dd>${statValue(k, view === "plan" ? b : a)}${view === "plan" && dlt ? ` <span class="${dlt > 0 ? "up" : "down"}">${dlt > 0 ? "+" : ""}${dlt}</span>` : ""}</dd></div>`;
    }).join("")}</dl></section>`;
  }).join("") || `<p class="muted">Add some gear to see your stats.</p>`;
  const gain = plan.v - cur.v;
  $("#g-summary").innerHTML = `
    <div><dt>Current gear</dt><dd>${cur.v}</dd></div>
    <div><dt>BIS plan</dt><dd class="xp">${plan.v}</dd></div>
    <div><dt>Gain</dt><dd class="${gain >= 0 ? "up" : "down"}">${gain >= 0 ? "+" : ""}${gain}</dd></div>
    <div><dt>Plan items owned</dt><dd>${PAPERDOLL.filter((d) => st.plan[d] && st.owned.has(st.plan[d]!)).length} of ${PAPERDOLL.filter((d) => st.plan[d]).length}</dd></div>`;
}

// ---------- slot list ----------
function itemCell(id: number | undefined) {
  if (!id) return `<span class="muted">Empty</span>`;
  const it = byId.get(id);
  if (!it) return `<span class="muted">Item #${id} (not in the database yet)</span>`;
  const q = QUALITY[it.q] || "common";
  return `<a class="ilink" href="/items/${it.id}/" data-item="${it.id}"><span class="ico sm qb-${q}">${it.icon ? `<img src="${esc(ICON(it.icon, 36))}" alt="" loading="lazy">` : ""}</span><span><span class="iname-t q-${q}">${esc(it.name)}</span><span class="meta">${esc(srcText(it))}</span></span></a>`;
}
function renderRows() {
  $("#g-rows").innerHTML = PAPERDOLL.map((d) => {
    const c = st.cur[d] ? byId.get(st.cur[d]!) : undefined;
    const p = st.plan[d] ? byId.get(st.plan[d]!) : undefined;
    const dv = Math.round((val(d, p) - val(d, c)) * 10) / 10;
    return `<tr><th scope="row">${DOLL_LABEL[d]}</th>
      <td class="item" data-label="Current">${itemCell(st.cur[d])}</td>
      <td class="item" data-label="Plan">${itemCell(st.plan[d])}</td>
      <td class="num" data-label="Gain"><b class="${dv > 0 ? "up" : dv < 0 ? "down" : ""}">${dv > 0 ? "+" : ""}${p || c ? dv : ""}</b></td>
      <td class="acts"><button type="button" class="link" data-pick="${d}">Change</button>
        ${p ? `<label class="own"><input type="checkbox" data-own="${p.id}"${st.owned.has(p.id) ? " checked" : ""}> Owned</label>` : ""}</td></tr>`;
  }).join("");
}

function renderControls() {
  $("#g-spec").innerHTML = SPECS[st.cls].map((s) => `<option value="${s.key}"${s.key === st.spec ? " selected" : ""}>${s.name}</option>`).join("");
  ($("#g-goal") as HTMLSelectElement).value = st.goal;
  ($("#g-level") as HTMLInputElement).value = String(st.level);
  $("#g-level-out").textContent = String(st.level);
  ($("#g-side") as HTMLSelectElement).value = st.side;
  $("#g-race").innerHTML = Object.entries(RACES).filter(([, r]) => r.side === "both" || r.side === st.side)
    .map(([k, r]) => `<option value="${k}"${k === st.race ? " selected" : ""}>${r.name}</option>`).join("");
  ($("#g-body") as HTMLSelectElement).value = st.body;
  document.querySelectorAll<HTMLInputElement>("[data-src]").forEach((c) => (c.checked = st.sources.has(c.dataset.src!)));
  document.querySelectorAll<HTMLButtonElement>("[data-pickcls]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.pickcls === st.cls)));
  const w = weights();
  $("#g-weights").innerHTML = WEIGHT_KEYS.map((k) => `<label><span>${STAT_LABEL[k] || k}</span>
    <input type="number" step="0.05" data-w="${k}" value="${+(w[k] || 0).toFixed(3)}"${st.goal === "custom" ? "" : " disabled"}></label>`).join("");
  $("#g-weights-note").textContent = st.goal === "custom" ? "Your weights. Changes apply to the next suggestion." : "Starting weights for this spec and goal. Pick Custom weights to edit them.";
}

function render() {
  renderControls(); renderDoll(); renderStats(); renderRows(); save();
  send3d(st.race, st.body, gearOf(), byId); // no-op unless the 3D dialog is open
}

// ---------- editing ----------
function setSlot(target: State["plan"], d: DollSlot, id: number | undefined) {
  if (id) target[d] = id; else delete target[d];
  if (d === "mainhand" && id && byId.get(id)?.slot === "twohand") delete target.offhand;
}
function removeSlot(d: DollSlot) {
  const target = gearOf(), prev = target[d];
  if (!prev) return;
  const prevOff = target.offhand;
  delete target[d];
  render();
  const name = byId.get(prev)?.name || "Item";
  toast(`Removed ${name} from ${DOLL_LABEL[d].toLowerCase()}.`, { label: "Undo", run: () => { target[d] = prev; if (prevOff) target.offhand = prevOff; render(); } });
}

// ---------- picker ----------
let picking: DollSlot | null = null;
function openPicker(d: DollSlot) {
  picking = d;
  ($("#g-target") as HTMLSelectElement).value = view;
  $("#g-picker-title").textContent = `${DOLL_LABEL[d]}`;
  ($("#g-search") as HTMLInputElement).value = "";
  fillPicker();
  ($("#g-picker") as HTMLDialogElement).showModal();
  ($("#g-search") as HTMLInputElement).focus();
}
function fillPicker() {
  if (!picking) return;
  const d = picking;
  const q = ($("#g-search") as HTMLInputElement).value.trim().toLowerCase();
  const all = ($("#g-all") as HTMLInputElement).checked;
  const target = ($("#g-target") as HTMLSelectElement).value === "cur" ? st.cur : st.plan;
  const curV = val(d, target[d] ? byId.get(target[d]!) : undefined);
  const pool = items.filter((it) => fits(d, it, st.cls) && (all || (it.q >= 1 && (it.lvl ?? it.req) <= st.level && (!it.side || it.side === st.side) && canUse(it, st.cls, st.level))));
  const list = pool.filter((it) => !q || it.name.toLowerCase().includes(q) || String(it.id) === q)
    .map((it) => ({ it, v: val(d, it) })).sort((a, b) => b.v - a.v).slice(0, 80);
  $("#g-picker-list").innerHTML = (target[d] ? `<li><button type="button" data-choose="0" class="link">Clear this slot</button></li>` : "")
    + list.map(({ it, v }) => {
      const qn = QUALITY[it.q] || "common", dv = Math.round((v - curV) * 10) / 10;
      return `<li><button type="button" data-choose="${it.id}" class="${target[d] === it.id ? "on" : ""}">
        <span class="ico qb-${qn}">${it.icon ? `<img src="${esc(ICON(it.icon))}" alt="" loading="lazy">` : ""}</span>
        <span class="pn"><span class="iname-t q-${qn}">${esc(it.name)}</span><span class="meta">Item level ${it.ilvl}${it.req ? `, requires ${it.req}` : ""}. ${esc(srcText(it))}</span></span>
        <span class="score">${v}<small class="${dv > 0 ? "up" : dv < 0 ? "down" : ""}">${target[d] === it.id ? "equipped" : `${dv > 0 ? "+" : ""}${dv}`}</small></span></button></li>`;
    }).join("")
    + (list.length ? "" : `<li class="muted">No items match. Try another name, or tick "Show items I can't use yet".</li>`);
}

// ---------- events ----------
function bind() {
  $("#g-spec").addEventListener("change", (e) => { const v = (e.target as HTMLSelectElement).value; st.spec = SPECS[st.cls].find((s) => s.key === v)?.key ?? st.spec; st.custom = null; render(); });
  $("#g-goal").addEventListener("change", (e) => {
    const g = GOALS.find((x) => x.key === (e.target as HTMLSelectElement).value)?.key;
    if (!g) return;
    if (g === "custom" && !st.custom) st.custom = { ...weightsFor(st.cls, st.spec, "pve") };
    st.goal = g; render();
  });
  const lvl = (e: Event) => Math.min(60, Math.max(1, Math.round(+(e.target as HTMLInputElement).value) || 60));
  $("#g-level").addEventListener("input", (e) => { st.level = lvl(e); $("#g-level-out").textContent = String(st.level); });
  $("#g-level").addEventListener("change", (e) => { st.level = lvl(e); render(); });
  $("#g-side").addEventListener("change", (e) => {
    st.side = (e.target as HTMLSelectElement).value === "A" ? "A" : "H";
    if (RACES[st.race].side !== "both" && RACES[st.race].side !== st.side) st.race = st.side === "A" ? "human" : "orc";
    render();
  });
  $("#g-race").addEventListener("change", (e) => { const v = (e.target as HTMLSelectElement).value; if (has(RACES, v)) { st.race = v; render(); } });
  $("#g-body").addEventListener("change", (e) => { st.body = (e.target as HTMLSelectElement).value === "F" ? "F" : "M"; render(); });
  document.querySelectorAll<HTMLInputElement>("[data-src]").forEach((c) => c.addEventListener("change", () => {
    if (c.checked) st.sources.add(c.dataset.src!); else st.sources.delete(c.dataset.src!); render();
  }));
  $("#g-suggest").addEventListener("click", () => {
    const before = { ...st.plan };
    const next = suggest();
    for (const d of PAPERDOLL) { // keep current items that already beat the suggestion
      const c = st.cur[d] ? byId.get(st.cur[d]!) : undefined, s = next[d] ? byId.get(next[d]!) : undefined;
      if (c && (!s || val(d, c) >= val(d, s))) next[d] = c.id;
    }
    st.plan = next; view = "plan"; render();
    const changed = PAPERDOLL.filter((d) => before[d] !== next[d]).length;
    toast(`Suggested ${changed} change${changed === 1 ? "" : "s"} from the sources you allowed.`, { label: "Undo", run: () => { st.plan = before; render(); } });
  });
  $("#g-keep").addEventListener("click", () => { const before = { ...st.plan }; st.plan = { ...st.cur }; render(); toast("Plan reset to your current gear.", { label: "Undo", run: () => { st.plan = before; render(); } }); });
  $("#g-import-go").addEventListener("click", () => { toast(importGear(($("#g-import") as HTMLTextAreaElement).value)); render(); });
  $("#g-copy").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(location.href); toast("Plan link copied. Share it anywhere."); } catch { toast("Copy the address bar to share this plan."); }
  });
  $("#g-rows").addEventListener("click", (e) => { const pick = (e.target as HTMLElement).closest<HTMLElement>("[data-pick]"); if (pick) { view = "plan"; openPicker(pick.dataset.pick as DollSlot); } });
  $("#g-rows").addEventListener("change", (e) => {
    const t = e.target as HTMLInputElement;
    if (t.dataset.own) { const id = +t.dataset.own; if (t.checked) st.owned.add(id); else st.owned.delete(id); render(); }
  });
  $("#g-weights").addEventListener("change", (e) => {
    const t = e.target as HTMLInputElement;
    if (t.dataset.w && st.goal === "custom") { st.custom = { ...(st.custom || {}), [t.dataset.w]: +t.value || 0 }; render(); }
  });
  document.querySelectorAll<HTMLButtonElement>("[data-pickcls]").forEach((b) => b.addEventListener("click", () => {
    const c = b.dataset.pickcls;
    if (!has(CLASSES, c) || st.cls === c) return;
    st.cls = c; st.spec = SPECS[st.cls][0].key; st.custom = null; st.plan = {}; render();
  }));
  document.querySelectorAll<HTMLButtonElement>("[data-view]").forEach((b) => b.addEventListener("click", () => { view = b.dataset.view as "plan" | "cur"; render(); }));
  $("#g-3d-open").addEventListener("click", () => toggle3d(() => send3d(st.race, st.body, gearOf(), byId)));

  // Character sheet: hover for the tooltip, click to change, right-click or long-press to remove.
  const doll = $("#g-doll"), tip = $("#g-tip");
  const slotOf = (e: Event) => (e.target as Element).closest<HTMLElement>("[data-slot],[data-part]");
  const dollSlot = (el: HTMLElement) => (el.dataset.slot || el.dataset.part) as DollSlot;
  const highlight = (d: DollSlot | null) => doll.querySelectorAll<HTMLElement>("[data-slot],[data-part]").forEach((x) => x.classList.toggle("hl", !!d && dollSlot(x) === d));
  doll.addEventListener("click", (e) => { const el = slotOf(e); if (el) { tip.hidden = true; openPicker(dollSlot(el)); } });
  doll.addEventListener("contextmenu", (e) => { const el = slotOf(e); if (!el) return; e.preventDefault(); tip.hidden = true; removeSlot(dollSlot(el)); });
  doll.addEventListener("keydown", (e) => { const el = slotOf(e); if (el && (e.key === "Delete" || e.key === "Backspace")) { e.preventDefault(); removeSlot(dollSlot(el)); } });
  let press = 0, pressed = false;
  doll.addEventListener("touchstart", (e) => { const el = slotOf(e); if (!el) return; pressed = false; press = window.setTimeout(() => { pressed = true; removeSlot(dollSlot(el)); }, 550); }, { passive: true });
  doll.addEventListener("touchend", (e) => { clearTimeout(press); if (pressed) e.preventDefault(); });
  doll.addEventListener("touchmove", () => clearTimeout(press), { passive: true });
  const show = (el: HTMLElement) => { const d = dollSlot(el); highlight(d); tip.innerHTML = slotTip(d); placeTip(tip, doll.querySelector(`[data-slot="${d}"]`) || el); };
  doll.addEventListener("mouseover", (e) => { const el = slotOf(e); if (el) show(el); });
  doll.addEventListener("focusin", (e) => { const el = slotOf(e); if (el) show(el); });
  doll.addEventListener("mouseleave", () => { tip.hidden = true; highlight(null); });
  doll.addEventListener("focusout", () => { tip.hidden = true; highlight(null); });
  window.addEventListener("scroll", () => (tip.hidden = true), { passive: true });

  $("#g-search").addEventListener("input", fillPicker);
  $("#g-all").addEventListener("change", fillPicker);
  $("#g-target").addEventListener("change", fillPicker);
  $("#g-picker-list").addEventListener("click", (e) => {
    const b = (e.target as HTMLElement).closest<HTMLElement>("[data-choose]");
    if (!b || !picking) return;
    const target = ($("#g-target") as HTMLSelectElement).value === "cur" ? st.cur : st.plan;
    view = target === st.cur ? "cur" : "plan";
    setSlot(target, picking, +b.dataset.choose! || undefined);
    ($("#g-picker") as HTMLDialogElement).close(); render();
  });
  $("#g-picker").addEventListener("click", (e) => { if (e.target === e.currentTarget) ($("#g-picker") as HTMLDialogElement).close(); });
}

async function start() {
  try {
    const data = await loadGear();
    items = data.items; sets = data.sets; byId = data.byId;
    $("#g-build").textContent = data.build;
  } catch {
    $("#g-doll").innerHTML = `<p class="muted">The gear database didn't load. Refresh to try again.</p>`;
    return;
  }
  let h = location.hash;
  if (!h) { try { h = localStorage.getItem("fxp-gear") || ""; } catch { /* storage blocked */ } }
  if (h) decode(h);
  $("#g-goal").innerHTML = GOALS.map((g) => `<option value="${g.key}">${g.name}</option>`).join("");
  bind(); render();
  if (!Object.keys(st.plan).length && !Object.keys(st.cur).length) { st.plan = suggest(); render(); }
  $("#gear").removeAttribute("aria-busy");
}
start();

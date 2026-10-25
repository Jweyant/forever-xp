import {
  CLASSES, SPECS, GOALS, WEIGHT_KEYS, STAT_LABEL, PAPERDOLL, DOLL_LABEL, SOURCE_KINDS,
  weightsFor, canUse, fits, score, sourceKind, canDualWield,
  type Item, type Stats, type Goal, type DollSlot,
} from "./model";

// ---------- state ----------
interface State {
  cls: string; spec: string; goal: Goal; level: number; side: "H" | "A";
  sources: Set<string>; cur: Partial<Record<DollSlot, number>>; plan: Partial<Record<DollSlot, number>>;
  owned: Set<number>; custom: Stats | null;
}
const ALL_SOURCES = SOURCE_KINDS.map((s) => s.key);
const st: State = {
  cls: "WARRIOR", spec: "fury", goal: "pve", level: 60, side: "H",
  sources: new Set(ALL_SOURCES), cur: {}, plan: {}, owned: new Set(), custom: null,
};

let view: "plan" | "cur" = "plan";
let items: Item[] = [];
let byId = new Map<number, Item>();
let sets: Record<string, { name: string; bonuses: { n: number; stats: Stats; text: string }[] }> = {};
const $ = <T extends HTMLElement>(sel: string) => document.querySelector<T>(sel)!;
const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]!));

function weights(): Stats { return st.goal === "custom" && st.custom ? st.custom : weightsFor(st.cls, st.spec, st.goal); }

// The same weights, adjusted for where the item sits: melee weapon DPS matters little to hunters,
// ranged weapon DPS matters little to melee, off-hand weapon DPS counts half.
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

// ---------- URL + storage ----------
function encode(): string {
  const p = new URLSearchParams();
  p.set("c", st.cls); p.set("s", st.spec); p.set("g", st.goal); p.set("l", String(st.level)); p.set("f", st.side);
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
  if (p.get("c") && CLASSES[p.get("c")!]) st.cls = p.get("c")!;
  const specs = SPECS[st.cls];
  st.spec = specs.some((s) => s.key === p.get("s")) ? p.get("s")! : specs[0].key;
  if (GOALS.some((g) => g.key === p.get("g"))) st.goal = p.get("g") as Goal;
  const l = +(p.get("l") || 60); if (l >= 1 && l <= 60) st.level = l;
  if (p.get("f") === "A" || p.get("f") === "H") st.side = p.get("f") as "A" | "H";
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
const IMPORT_SLOT: Record<string, DollSlot> = {
  head: "head", neck: "neck", shoulder: "shoulder", back: "back", chest: "chest", wrist: "wrist", hands: "hands",
  waist: "waist", legs: "legs", feet: "feet", finger1: "finger1", finger2: "finger2", trinket1: "trinket1",
  trinket2: "trinket2", mainhand: "mainhand", offhand: "offhand", ranged: "ranged",
};
function importGear(text: string): string {
  const m = text.trim().match(/^FXPG1:([A-Z]+):(\d+):([A-Za-z]+):([AH]):(.*)$/);
  if (!m) return "That doesn't look like a ForeverScout gear string. In game, type /fscout gear and copy the whole line.";
  const [, cls, lvl, , side, rest] = m;
  if (!CLASSES[cls]) return `Unknown class ${cls}.`;
  if (cls !== st.cls) { st.cls = cls; st.spec = SPECS[cls][0].key; }
  st.level = Math.min(60, Math.max(1, +lvl)); st.side = side as "A" | "H";
  st.cur = {}; let missing = 0, n = 0;
  for (const part of rest.split(",")) {
    const [slot, idRaw] = part.split("=");
    const doll = IMPORT_SLOT[slot]; const id = parseInt(idRaw, 10);
    if (doll && id) { st.cur[doll] = id; n++; if (!byId.has(id)) missing++; }
  }
  st.plan = { ...st.cur };
  return `Imported ${n} items for your level ${st.level} ${CLASSES[cls].name}.` + (missing ? ` ${missing} aren't in the gear database yet and count as zero.` : "");
}

// ---------- candidate search ----------
function allowedSource(it: Item) { return st.sources.has(sourceKind(it)); }
function candidates(doll: DollSlot): Item[] {
  return items.filter((it) => it.q >= 1 && (it.lvl ?? it.req) <= st.level && (!it.side || it.side === st.side)
    && canUse(it, st.cls, st.level) && fits(doll, it, st.cls) && allowedSource(it));
}

/** Best item per slot under the current filters. Handles two-hand vs main+off and unique ring/trinket pairs. */
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
  const r1 = plan.finger1; const r2 = best("finger2", r1 ? [r1] : []); if (r2) plan.finger2 = r2.id;
  const t1 = plan.trinket1; const t2 = best("trinket2", t1 ? [t1] : []); if (t2) plan.trinket2 = t2.id;
  // Weapons: best two-hander vs best main hand + off hand.
  const mains = candidates("mainhand");
  const twoH = mains.filter((i) => i.slot === "twohand").sort((a, b) => val("mainhand", b) - val("mainhand", a))[0];
  const oneH = mains.filter((i) => i.slot !== "twohand").sort((a, b) => val("mainhand", b) - val("mainhand", a))[0];
  const offs = candidates("offhand").filter((i) => !oneH || i.id !== oneH.id || canDualWield(st.cls));
  const off = offs.filter((i) => !oneH || i.id !== oneH.id).sort((a, b) => val("offhand", b) - val("offhand", a))[0];
  const pairV = val("mainhand", oneH) + val("offhand", off);
  if (twoH && val("mainhand", twoH) >= pairV) plan.mainhand = twoH.id;
  else { if (oneH) plan.mainhand = oneH.id; if (off) plan.offhand = off.id; }
  return plan;
}

// ---------- rendering ----------
const QUALITY = ["poor", "common", "uncommon", "rare", "epic", "legendary", "artifact"];
const SRC_LABEL: Record<string, string> = { chest: "Chest", raid: "Raid", dungeon: "Dungeon", pvp: "PvP", rep: "Reputation", quest: "Quest", craft: "Crafted", vendor: "Vendor", drop: "Drop", world: "World drop", logged: "Seen in Forever" };
function srcText(it: Item) {
  const s = it.src?.[0];
  if (!s) return "Source not known yet";
  const where = [s.n, s.z].filter(Boolean).join(", ");
  return `${SRC_LABEL[s.t] || s.t}${where ? ": " + where : ""}`;
}
function statLine(it: Item) {
  const parts = Object.entries(it.stats).filter(([k]) => k !== "dps" && k !== "armor").map(([k, v]) => `+${v} ${STAT_LABEL[k] || k}`);
  if (it.weapon) parts.unshift(`${it.weapon.min}–${it.weapon.max}, ${it.weapon.speed.toFixed(1)} speed (${it.weapon.dps} DPS)`);
  if (it.stats.armor) parts.unshift(`${it.stats.armor} armor`);
  return parts.join(", ");
}
function itemCell(id: number | undefined, doll: DollSlot) {
  if (!id) return `<span class="muted">Empty</span>`;
  const it = byId.get(id);
  if (!it) return `<span class="muted">Item #${id} (not in the database yet)</span>`;
  const set = it.set && sets[it.set] ? `<span class="set">${esc(sets[it.set].name)}</span>` : "";
  return `<span class="iname q-${QUALITY[it.q] || "common"}">${esc(it.name)}</span>
    <span class="meta">Item level ${it.ilvl}${it.req ? `, requires ${it.req}` : it.lvl ? `, from level ${it.lvl}` : ""}. ${esc(srcText(it))}. ${set}</span>
    <span class="stats">${esc(statLine(it))}</span>${(it.fx || []).map((f) => `<span class="fx">${f.on === "use" ? "Use" : f.on === "hit" ? "Chance on hit" : "Equip"}: ${esc(f.text)}</span>`).join("")}`;
}

const ICON = (n: string) => `https://render.worldofwarcraft.com/us/icons/56/${n}.jpg`;
const CLASS_ICON: Record<string, string> = {
  WARRIOR: "classicon_warrior", PALADIN: "classicon_paladin", HUNTER: "classicon_hunter", ROGUE: "classicon_rogue",
  PRIEST: "classicon_priest", SHAMAN: "classicon_shaman", MAGE: "classicon_mage", WARLOCK: "classicon_warlock", DRUID: "classicon_druid",
};
const LEFT: DollSlot[] = ["head", "neck", "shoulder", "back", "chest", "wrist"];
const RIGHT: DollSlot[] = ["hands", "waist", "legs", "feet", "finger1", "finger2", "trinket1", "trinket2"];
const BOTTOM: DollSlot[] = ["mainhand", "offhand", "ranged"];
const SLOT_GLYPH: Record<DollSlot, string> = {
  head: "Hd", neck: "Nk", shoulder: "Sh", back: "Bk", chest: "Ch", wrist: "Wr", hands: "Ha", waist: "Wa", legs: "Lg",
  feet: "Ft", finger1: "R1", finger2: "R2", trinket1: "T1", trinket2: "T2", mainhand: "MH", offhand: "OH", ranged: "Rg",
};

function slotButton(d: DollSlot) {
  const id = (view === "plan" ? st.plan : st.cur)[d];
  const it = id ? byId.get(id) : undefined;
  const other = (view === "plan" ? st.cur : st.plan)[d];
  const up = view === "plan" && it && (val(d, it) - val(d, other ? byId.get(other) : undefined)) > 0.05;
  const owned = it && st.owned.has(it.id);
  const q = it ? QUALITY[it.q] || "common" : "empty";
  const img = it?.icon ? `<img src="${ICON(it.icon)}" alt="" width="52" height="52" loading="lazy" onerror="this.remove()">` : "";
  return `<button type="button" class="slot q-b-${q}" data-slot="${d}" aria-label="${DOLL_LABEL[d]}: ${it ? esc(it.name) : "empty"}">
    ${img}<span class="glyph" aria-hidden="true">${SLOT_GLYPH[d]}</span>
    ${up ? `<span class="badge up" title="Upgrade over current">▲</span>` : ""}${owned ? `<span class="badge own" title="Owned">✓</span>` : ""}
  </button>`;
}

function renderDoll() {
  const spec = SPECS[st.cls].find((s) => s.key === st.spec);
  const t = totals(view === "plan" ? st.plan : st.cur);
  $("#g-doll").dataset.klass = st.cls.toLowerCase();
  $("#g-doll").innerHTML = `
    <div class="col left">${LEFT.map(slotButton).join("")}</div>
    <div class="figure">
      <svg viewBox="0 0 200 320" class="silhouette" aria-hidden="true">
        <defs>
          <radialGradient id="aura" cx="50%" cy="42%" r="55%"><stop offset="0" stop-color="var(--cls)" stop-opacity=".55"/><stop offset="1" stop-color="var(--cls)" stop-opacity="0"/></radialGradient>
          <linearGradient id="body" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3a4a5a"/><stop offset="1" stop-color="#1a242e"/></linearGradient>
        </defs>
        <ellipse cx="100" cy="150" rx="98" ry="150" fill="url(#aura)"/>
        <ellipse cx="100" cy="304" rx="62" ry="9" fill="#000" opacity=".35"/>
        <path fill="url(#body)" stroke="var(--cls)" stroke-opacity=".7" stroke-width="1.5" d="M100 22c15 0 25 12 25 27 0 12-6 21-14 25l2 8c18 3 33 9 43 18 9 9 12 26 14 46l6 52c1 8-3 12-9 12-5 0-8-4-9-10l-7-50-6 7 4 60-11 98c-1 7-6 11-12 11s-10-4-10-11l-3-80h-6l-3 80c0 7-4 11-10 11s-11-4-12-11l-11-98 4-60-6-7-7 50c-1 6-4 10-9 10-6 0-10-4-9-12l6-52c2-20 5-37 14-46 10-9 25-15 43-18l2-8c-8-4-14-13-14-25 0-15 10-27 25-27z"/>
        <path d="M70 92c10 6 20 8 30 8s20-2 30-8" fill="none" stroke="var(--cls)" stroke-opacity=".5" stroke-width="2"/>
      </svg>
      <img class="crest" src="${ICON(CLASS_ICON[st.cls])}" alt="" width="44" height="44" onerror="this.remove()">
      <p class="who"><b>${esc(CLASSES[st.cls].name)}</b><span>${esc(spec?.name || "")}, level ${st.level}</span></p>
      <p class="pow"><span>${view === "plan" ? "Plan score" : "Current score"}</span><b>${t.v}</b></p>
    </div>
    <div class="col right">${RIGHT.map(slotButton).join("")}</div>
    <div class="row bottom">${BOTTOM.map(slotButton).join("")}</div>`;
  document.querySelectorAll<HTMLButtonElement>("[data-view]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.view === view)));
}

function tooltipHtml(d: DollSlot) {
  const id = (view === "plan" ? st.plan : st.cur)[d];
  const it = id ? byId.get(id) : undefined;
  if (!it) return `<p class="tt-name">${DOLL_LABEL[d]}</p><p class="tt-muted">Empty. Click to choose an item.</p>`;
  const lines: string[] = [];
  lines.push(`<p class="tt-name q-${QUALITY[it.q]}">${esc(it.name)}</p>`);
  lines.push(`<p class="tt-muted">Item level ${it.ilvl}</p>`);
  if (it.bop) lines.push(`<p>Binds when picked up</p>`);
  lines.push(`<p class="tt-row"><span>${esc(DOLL_LABEL[d])}</span><span>${esc(it.type === "misc" ? "" : it.type.replace(/[12]$/, "").replace(/^./, (c) => c.toUpperCase()))}</span></p>`);
  if (it.weapon) lines.push(`<p class="tt-row"><span>${it.weapon.min} – ${it.weapon.max} Damage</span><span>Speed ${it.weapon.speed.toFixed(2)}</span></p><p>(${it.weapon.dps} damage per second)</p>`);
  if (it.stats.armor) lines.push(`<p>${it.stats.armor} Armor</p>`);
  const primary = ["str", "agi", "sta", "int", "spi"];
  for (const k of primary) if (it.stats[k]) lines.push(`<p>+${it.stats[k]} ${STAT_LABEL[k]}</p>`);
  for (const [k, v] of Object.entries(it.stats)) if (!primary.includes(k) && k !== "armor" && k !== "dps") lines.push(`<p class="tt-green">Equip: +${v} ${STAT_LABEL[k] || k}</p>`);
  for (const f of it.fx || []) lines.push(`<p class="tt-green">${f.on === "use" ? "Use" : f.on === "hit" ? "Chance on hit" : "Equip"}: ${esc(f.text)}</p>`);
  if (it.set && sets[it.set]) lines.push(`<p class="tt-gold">${esc(sets[it.set].name)}</p>`);
  if (it.req) lines.push(`<p>Requires level ${it.req}</p>`);
  lines.push(`<p class="tt-src">${esc(srcText(it))}</p>`);
  lines.push(`<p class="tt-score">Score ${val(d, it)} for ${esc(SPECS[st.cls].find((s) => s.key === st.spec)?.name || "")}</p>`);
  return lines.join("");
}
function showTip(btn: HTMLElement) {
  const tip = $("#g-tip");
  tip.innerHTML = tooltipHtml(btn.dataset.slot as DollSlot);
  tip.hidden = false;
  const r = btn.getBoundingClientRect(), pane = $("#g-doll").getBoundingClientRect();
  const w = tip.offsetWidth, h = tip.offsetHeight;
  let x = r.right - pane.left + 10, y = r.top - pane.top;
  if (r.right + w + 20 > window.innerWidth) x = r.left - pane.left - w - 10;
  if (x < 0) x = Math.max(0, (pane.width - w) / 2);
  y = Math.min(y, Math.max(0, pane.height - h));
  tip.style.left = `${x}px`; tip.style.top = `${y}px`;
}

function totals(o: State["plan"]) {
  const t: Stats = {}; let v = 0;
  for (const d of PAPERDOLL) {
    const it = o[d] ? byId.get(o[d]!) : undefined;
    if (!it) continue;
    v += val(d, it);
    for (const [k, n] of Object.entries(it.stats)) if (k !== "dps") t[k] = (t[k] || 0) + n;
  }
  return { t, v: Math.round(v) };
}

function render() {
  const w = weights();
  $("#g-spec").innerHTML = SPECS[st.cls].map((s) => `<option value="${s.key}"${s.key === st.spec ? " selected" : ""}>${s.name}</option>`).join("");
  ($("#g-goal") as HTMLSelectElement).value = st.goal;
  ($("#g-level") as HTMLInputElement).value = String(st.level);
  $("#g-level-out").textContent = String(st.level);
  ($("#g-side") as HTMLSelectElement).value = st.side;
  document.querySelectorAll<HTMLInputElement>("[data-src]").forEach((c) => (c.checked = st.sources.has(c.dataset.src!)));

  renderDoll();
  document.querySelectorAll<HTMLButtonElement>("[data-pickcls]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.pickcls === st.cls)));
  const cur = totals(st.cur), plan = totals(st.plan);
  $("#g-summary").innerHTML = `
    <div><dt>Current gear</dt><dd>${cur.v}</dd></div>
    <div><dt>Plan</dt><dd class="xp">${plan.v}</dd></div>
    <div><dt>Gain</dt><dd class="${plan.v - cur.v >= 0 ? "up" : "down"}">${plan.v - cur.v >= 0 ? "+" : ""}${plan.v - cur.v}</dd></div>
    <div><dt>Plan items owned</dt><dd>${PAPERDOLL.filter((d) => st.plan[d] && st.owned.has(st.plan[d]!)).length} / ${PAPERDOLL.filter((d) => st.plan[d]).length}</dd></div>`;

  $("#g-rows").innerHTML = PAPERDOLL.map((d) => {
    const c = st.cur[d] ? byId.get(st.cur[d]!) : undefined;
    const p = st.plan[d] ? byId.get(st.plan[d]!) : undefined;
    const dv = Math.round((val(d, p) - val(d, c)) * 10) / 10;
    const own = p && st.owned.has(p.id);
    return `<tr data-doll="${d}">
      <th scope="row">${DOLL_LABEL[d]}</th>
      <td class="item" data-label="Current">${itemCell(st.cur[d], d)}</td>
      <td class="item" data-label="Plan">${itemCell(st.plan[d], d)}</td>
      <td class="num" data-label="Gain"><b class="${dv > 0 ? "up" : dv < 0 ? "down" : ""}">${dv > 0 ? "+" : ""}${p || c ? dv : ""}</b></td>
      <td class="acts">
        <button type="button" class="link" data-pick="${d}">Change</button>
        ${p ? `<label class="own"><input type="checkbox" data-own="${p.id}"${own ? " checked" : ""}> Owned</label>` : ""}
      </td></tr>`;
  }).join("");

  $("#g-weights").innerHTML = WEIGHT_KEYS.map((k) => `<label><span>${STAT_LABEL[k] || k}</span>
    <input type="number" step="0.05" data-w="${k}" value="${+(w[k] || 0).toFixed(3)}"${st.goal === "custom" ? "" : " disabled"}></label>`).join("");
  $("#g-weights-note").textContent = st.goal === "custom" ? "Your weights. Changes apply to the next suggestion." : "Starting weights for this spec and goal. Pick Custom weights to edit them.";

  const keys = Object.keys(plan.t).filter((k) => plan.t[k] || cur.t[k]).sort((a, b) => (w[b] || 0) - (w[a] || 0));
  $("#g-totals").innerHTML = `<thead><tr><th>Stat</th><th class="num">Current</th><th class="num">Plan</th></tr></thead><tbody>${keys.map((k) => `<tr><td>${STAT_LABEL[k] || k}</td><td class="num">${cur.t[k] || 0}</td><td class="num">${plan.t[k] || 0}</td></tr>`).join("")}</tbody>`;
  save();
}

// ---------- item picker ----------
let picking: DollSlot | null = null;
function openPicker(d: DollSlot) {
  picking = d;
  const dlg = $("#g-picker") as HTMLDialogElement;
  $("#g-picker-title").textContent = `${DOLL_LABEL[d]}: choose an item`;
  ($("#g-search") as HTMLInputElement).value = "";
  fillPicker();
  dlg.showModal();
  ($("#g-search") as HTMLInputElement).focus();
}
function fillPicker() {
  if (!picking) return;
  const d = picking;
  const q = ($("#g-search") as HTMLInputElement).value.trim().toLowerCase();
  const all = ($("#g-all") as HTMLInputElement).checked;
  const pool = items.filter((it) => fits(d, it, st.cls) && (all || (it.q >= 1 && (it.lvl ?? it.req) <= st.level && (!it.side || it.side === st.side) && canUse(it, st.cls, st.level))));
  const list = pool.filter((it) => !q || it.name.toLowerCase().includes(q) || String(it.id) === q)
    .map((it) => ({ it, v: val(d, it) })).sort((a, b) => b.v - a.v).slice(0, 60);
  $("#g-picker-list").innerHTML = (st.cur[d] || st.plan[d] ? `<li><button type="button" data-choose="0" class="link">Clear this slot</button></li>` : "")
    + list.map(({ it, v }) => `<li><button type="button" data-choose="${it.id}"><span class="pic q-b-${QUALITY[it.q] || "common"}">${it.icon ? `<img src="${ICON(it.icon)}" alt="" width="36" height="36" loading="lazy" onerror="this.remove()">` : ""}</span><span class="score">${v}</span><span>${itemCell(it.id, d)}</span></button></li>`).join("")
    + (list.length ? "" : `<li class="muted">No items match. Try another name, or tick "Show items I can't use yet".</li>`);
}

// ---------- events ----------
function bind() {
  $("#g-spec").addEventListener("change", (e) => { st.spec = (e.target as HTMLSelectElement).value; st.custom = null; render(); });
  $("#g-goal").addEventListener("change", (e) => {
    const g = (e.target as HTMLSelectElement).value as Goal;
    if (g === "custom" && !st.custom) st.custom = { ...weightsFor(st.cls, st.spec, "pve") };
    st.goal = g; render();
  });
  $("#g-level").addEventListener("input", (e) => { st.level = +(e.target as HTMLInputElement).value; $("#g-level-out").textContent = String(st.level); });
  $("#g-level").addEventListener("change", (e) => { st.level = +(e.target as HTMLInputElement).value; render(); });
  $("#g-side").addEventListener("change", (e) => { st.side = (e.target as HTMLSelectElement).value as "A" | "H"; render(); });
  document.querySelectorAll<HTMLInputElement>("[data-src]").forEach((c) => c.addEventListener("change", () => {
    if (c.checked) st.sources.add(c.dataset.src!); else st.sources.delete(c.dataset.src!); render();
  }));
  $("#g-suggest").addEventListener("click", () => {
    const next = suggest();
    // Keep the current item where it already beats the suggestion (or nothing is allowed).
    for (const d of PAPERDOLL) {
      const c = st.cur[d] ? byId.get(st.cur[d]!) : undefined, s = next[d] ? byId.get(next[d]!) : undefined;
      if (c && (!s || val(d, c) >= val(d, s))) next[d] = c.id;
    }
    st.plan = next; render();
    $("#g-status").textContent = "Suggested the best item for each slot from the sources you've allowed.";
  });
  $("#g-keep").addEventListener("click", () => { st.plan = { ...st.cur }; render(); $("#g-status").textContent = "Plan reset to your current gear."; });
  $("#g-import-go").addEventListener("click", () => {
    const msg = importGear(($("#g-import") as HTMLTextAreaElement).value);
    $("#g-status").textContent = msg; render();
  });
  $("#g-copy").addEventListener("click", async (e) => {
    const b = e.currentTarget as HTMLButtonElement;
    try { await navigator.clipboard.writeText(location.href); b.textContent = "Link copied"; } catch { b.textContent = "Copy the address bar"; }
    setTimeout(() => (b.textContent = "Copy plan link"), 2000);
  });
  $("#g-rows").addEventListener("click", (e) => {
    const t = e.target as HTMLElement;
    const pick = t.closest<HTMLElement>("[data-pick]");
    if (pick) openPicker(pick.dataset.pick as DollSlot);
  });
  $("#g-rows").addEventListener("change", (e) => {
    const t = e.target as HTMLInputElement;
    if (t.dataset.own) { const id = +t.dataset.own; if (t.checked) st.owned.add(id); else st.owned.delete(id); render(); }
  });
  $("#g-weights").addEventListener("change", (e) => {
    const t = e.target as HTMLInputElement;
    if (t.dataset.w && st.goal === "custom") { st.custom = { ...(st.custom || {}), [t.dataset.w]: +t.value || 0 }; render(); }
  });
  document.querySelectorAll<HTMLButtonElement>("[data-pickcls]").forEach((b) => b.addEventListener("click", () => {
    st.cls = b.dataset.pickcls!; st.spec = SPECS[st.cls][0].key; st.custom = null; st.plan = {}; render();
  }));
  document.querySelectorAll<HTMLButtonElement>("[data-view]").forEach((b) => b.addEventListener("click", () => { view = b.dataset.view as "plan" | "cur"; render(); }));
  const doll = $("#g-doll");
  doll.addEventListener("click", (e) => {
    const b = (e.target as HTMLElement).closest<HTMLElement>("[data-slot]");
    if (!b) return;
    ($("#g-target") as HTMLSelectElement).value = view;
    $("#g-tip").hidden = true;
    openPicker(b.dataset.slot as DollSlot);
  });
  doll.addEventListener("mouseover", (e) => { const b = (e.target as HTMLElement).closest<HTMLElement>("[data-slot]"); if (b) showTip(b); });
  doll.addEventListener("focusin", (e) => { const b = (e.target as HTMLElement).closest<HTMLElement>("[data-slot]"); if (b) showTip(b); });
  doll.addEventListener("mouseleave", () => ($("#g-tip").hidden = true));
  doll.addEventListener("focusout", () => ($("#g-tip").hidden = true));
  $("#g-search").addEventListener("input", fillPicker);
  $("#g-all").addEventListener("change", fillPicker);
  $("#g-picker-list").addEventListener("click", (e) => {
    const b = (e.target as HTMLElement).closest<HTMLElement>("[data-choose]");
    if (!b || !picking) return;
    const id = +b.dataset.choose!;
    const target = ($("#g-target") as HTMLSelectElement).value === "cur" ? st.cur : st.plan;
    if (id) target[picking] = id; else delete target[picking];
    if (picking === "mainhand" && id && byId.get(id)?.slot === "twohand") delete target.offhand;
    ($("#g-picker") as HTMLDialogElement).close(); render();
  });
}

async function start() {
  const res = await fetch("/data/items.json");
  if (!res.ok) { $("#g-status").textContent = "The gear database didn't load. Refresh to try again."; return; }
  const data = await res.json();
  items = data.items; sets = data.sets; byId = new Map(items.map((i: Item) => [i.id, i]));
  $("#g-build").textContent = data.build;
  let h = location.hash;
  if (!h) { try { h = localStorage.getItem("fxp-gear") || ""; } catch { /* storage blocked */ } }
  if (h) decode(h);
  $("#g-goal").innerHTML = GOALS.map((g) => `<option value="${g.key}">${g.name}</option>`).join("");
  bind(); render();
  $("#gear").removeAttribute("aria-busy");
}
start();

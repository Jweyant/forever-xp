// Item database page: filters, sorting and paging over the full gear database plus every non-gear
// item (consumables, trade goods, recipes, quest items...), state in the URL.
import { loadGear, loadOther, QUALITY, ICON, esc, num, srcText, srcHtml, SLOT_NAME, type OtherItem } from "./items";
import { STAT_LABEL, sourceKind, type Item } from "./gear/model";

type Other = OtherItem;
// Dungeon and raid pages that exist, from the page (data-instances), so sources only link to real pages.
const INSTANCES = new Set<string>((() => { try { const v = JSON.parse(document.getElementById("idb")?.dataset.instances || "[]"); return Array.isArray(v) ? v.filter((s) => typeof s === "string" && /^[a-z0-9-]+$/.test(s)) : []; } catch { return []; } })());
type Row = { g: Item } | { o: Other };

const $ = <T extends HTMLElement = HTMLInputElement>(id: string) => document.getElementById(id) as T;
const PAGE = 100;
let all: Item[] = [], other: Other[] = [], shown = PAGE, sortKey = "ilvl", dir = -1;
const ids = ["f-q", "f-cat", "f-slot", "f-type", "f-q2", "f-min", "f-max", "f-src", "f-stat", "f-ver"];
const keys = ["q", "cat", "slot", "type", "quality", "min", "max", "src", "stat", "ver"];
const tname = (t: string) => t.replace(/[12]$/, "").replace(/^./, (c) => c.toUpperCase());
const str = (v: unknown) => (typeof v === "string" ? v : "");
const quests = (l: unknown) => (Array.isArray(l) ? l : []).filter((x) => Array.isArray(x) && num(x[0]) > 0)
  .map((x) => `<a href="/quests/${num(x[0])}/">${esc(str(x[1]) || `Quest ${num(x[0])}`)}</a>`).join(", ");
const names = (l: unknown) => (Array.isArray(l) ? l : []).map(str).filter(Boolean).map(esc).join(", ");

/** Where a non-gear item comes from and what uses it, as HTML (every value escaped or numeric). */
function otherDetails(o: Other) {
  const parts: string[] = [];
  const drops = (Array.isArray(o.d) ? o.d : []).filter(Array.isArray).map((x) => esc(str(x[0])) + (str(x[1]) ? ` (${esc(str(x[1]))})` : "")).join(", ");
  if (drops) parts.push(`Drops from ${drops}`);
  if (names(o.v)) parts.push(`Sold by ${names(o.v)}`);
  if (names(o.o)) parts.push(`Found in ${names(o.o)}`);
  if (Array.isArray(o.qs) && num(o.qs[0]) > 0) parts.push(`Starts ${quests([o.qs])}`);
  if (quests(o.qr)) parts.push(`Reward from ${quests(o.qr)}`);
  if (quests(o.qu)) parts.push(`Used in ${quests(o.qu)}`);
  return parts.join("; ") || `<span class="muted">No known source yet</span>`;
}
const otherText = (o: Other) => [o.d?.[0]?.[0], o.v?.[0], o.o?.[0]].map(str).find(Boolean) || "";

function filtered(): Row[] {
  const t = $("f-q").value.trim().toLowerCase(), id = /^\d+$/.test(t) ? +t : 0, cat = $("f-cat").value;
  const slot = $("f-slot").value, type = $("f-type").value, q2 = +$("f-q2").value || 0;
  const min = +$("f-min").value || 0, max = +$("f-max").value || 99, src = $("f-src").value, stat = $("f-stat").value, ver = $("f-ver").value;
  const named = (n: string, i: number) => !t || i === id || n.toLowerCase().includes(t);
  const rows: Row[] = [];
  if (!cat || cat === "gear") {
    for (const it of all) if (named(it.name, it.id) && (!slot || it.slot === slot)
      && (!type || it.type === type) && it.q >= q2 && (it.req || 1) >= min && (it.req || 1) <= max
      && (!src || sourceKind(it) === src) && (!stat || (it.stats[stat] || 0) > 0)
      && (!ver || (ver === "new" ? it.new === 1 : ver === "chg" ? Array.isArray(it.chg) : it.new === 1 || Array.isArray(it.chg)))) rows.push({ g: it });
  }
  // Gear-only filters (slot, type, source, stat, new/changed) leave non-gear items out.
  if (cat !== "gear" && !slot && !type && !src && !stat && !ver) {
    for (const o of other) if ((!cat || o.c === cat) && named(o.n, o.id) && o.q >= q2 && (o.rl || 1) >= min && (o.rl || 1) <= max) rows.push({ o });
  }
  const val = (r: Row): string | number => "g" in r
    ? (sortKey === "name" ? r.g.name : sortKey === "req" ? r.g.req : sortKey === "slot" ? r.g.slot : sortKey === "src" ? srcText(r.g) : r.g.ilvl)
    : (sortKey === "name" ? r.o.n : sortKey === "req" ? r.o.rl || 0 : sortKey === "slot" ? r.o.c : sortKey === "src" ? otherText(r.o) : 0);
  const qual = (r: Row) => ("g" in r ? r.g.q : r.o.q);
  return rows.sort((a, b) => { const x = val(a), y = val(b); return (typeof x === "string" || typeof y === "string" ? String(x).localeCompare(String(y)) : x - y) * dir || qual(b) - qual(a); });
}

function gearRow(it: Item) {
  const q = QUALITY[num(it.q)] || "common";
  const stats = Object.entries(it.stats).filter(([k]) => k !== "armor" && k !== "dps").slice(0, 4).map(([k, v]) => `+${num(v)} ${STAT_LABEL[k] || k}`).join(", ");
  return `<tr><td><a class="ilink" href="/items/${num(it.id)}/" data-item="${num(it.id)}"><span class="ico sm qb-${q}">${it.icon ? `<img src="${esc(ICON(it.icon, 36))}" alt="" loading="lazy">` : ""}</span><span><span class="iname-t q-${q}">${esc(it.name)}</span>${it.new === 1 ? `<span class="tag-new">NEW</span>` : Array.isArray(it.chg) ? `<span class="tag-new tag-chg">CHANGED</span>` : ""}<span class="sub">${esc(stats || (it.weapon ? `${it.weapon.dps} DPS` : it.stats.armor ? `${it.stats.armor} armor` : ""))}</span></span></a></td>
    <td class="num">${num(it.ilvl)}</td><td class="num opt">${num(it.req) || "–"}</td><td class="opt">${esc(SLOT_NAME[it.slot] || it.slot)}${it.type && it.type !== "misc" ? `<span class="sub">${esc(tname(it.type))}</span>` : ""}</td><td class="opt small">${srcHtml(it, INSTANCES)}</td></tr>`;
}
function otherRow(o: Other) {
  const q = QUALITY[num(o.q)] || "common";
  return `<tr><td><span class="ilink" tabindex="0" data-item="${num(o.id)}"><span class="ico sm qb-${q}">${typeof o.icon === "string" && o.icon ? `<img src="${esc(ICON(o.icon, 36))}" alt="" loading="lazy">` : ""}</span><span><span class="iname-t q-${q}">${esc(str(o.n))}</span><span class="sub">Item ID ${num(o.id)}</span></span></span></td>
    <td class="num">–</td><td class="num opt">${num(o.rl) || "–"}</td><td class="opt">${esc(str(o.c))}</td><td class="opt small">${otherDetails(o)}</td></tr>`;
}

function render() {
  const list = filtered();
  $("f-count").textContent = `${list.length.toLocaleString("en-US")} items${list.length > shown ? `, showing ${shown}` : ""}`;
  $("irows").innerHTML = list.slice(0, shown).map((r) => ("g" in r ? gearRow(r.g) : otherRow(r.o))).join("")
    || `<tr><td colspan="5" class="muted">No items match. Clear a filter or two.</td></tr>`;
  $<HTMLButtonElement>("f-more").hidden = list.length <= shown;
  const p = new URLSearchParams();
  ids.forEach((id, i) => { const v = $(id).value.trim(); if (v) p.set(keys[i], v); });
  if (sortKey !== "ilvl" || dir !== -1) p.set("sort", `${sortKey}${dir > 0 ? "" : "-"}`);
  history.replaceState(null, "", p.toString() ? `?${p}` : location.pathname);
}

Promise.all([loadGear(), loadOther()]).then(([db, oth]) => {
  all = db.items.filter((i) => i.q >= 0);
  other = oth.list;
  const cats = [...new Set(other.map((o) => o.c))].sort();
  $("f-cat").insertAdjacentHTML("beforeend", cats.map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join(""));
  const types = [...new Set(all.map((i) => i.type).filter((t) => t && t !== "misc"))].sort();
  $("f-type").insertAdjacentHTML("beforeend", types.map((t) => `<option value="${esc(t)}">${esc(tname(t))}</option>`).join(""));
  const stats = [...new Set(all.flatMap((i) => Object.keys(i.stats)))].filter((k) => k !== "dps").sort((a, b) => (STAT_LABEL[a] || a).localeCompare(STAT_LABEL[b] || b));
  $("f-stat").insertAdjacentHTML("beforeend", stats.map((k) => `<option value="${esc(k)}">${esc(STAT_LABEL[k] || k)}</option>`).join(""));
  const p = new URLSearchParams(location.search);
  ids.forEach((id, i) => { const v = p.get(keys[i]); if (v) $(id).value = v; });
  const s = p.get("sort"); if (s && ["name", "ilvl", "req", "slot", "src"].includes(s.replace(/-$/, ""))) { dir = s.endsWith("-") ? -1 : 1; sortKey = s.replace(/-$/, ""); }
  document.querySelectorAll<HTMLElement>("#itbl th").forEach((th) => th.setAttribute("aria-sort", th.dataset.sort === sortKey ? (dir > 0 ? "ascending" : "descending") : "none"));
  $("idb").setAttribute("aria-busy", "false");
  render();
}).catch(() => { $("f-count").textContent = "The item database didn't load. Refresh to try again."; });

let timer = 0;
ids.forEach((id) => $(id).addEventListener("input", () => { clearTimeout(timer); timer = window.setTimeout(() => { shown = PAGE; render(); }, 100); }));
$("f-more").addEventListener("click", () => { shown += PAGE; render(); });
document.querySelectorAll<HTMLElement>("#itbl th[data-sort] button").forEach((b) => b.addEventListener("click", () => {
  const th = b.parentElement!, k = th.dataset.sort!;
  dir = k === sortKey ? -dir : (k === "name" || k === "slot" || k === "src" ? 1 : -1); sortKey = k;
  document.querySelectorAll<HTMLElement>("#itbl th").forEach((x) => x.setAttribute("aria-sort", x === th ? (dir > 0 ? "ascending" : "descending") : "none"));
  render();
}));

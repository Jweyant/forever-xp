// Item database page: filters, sorting and paging over the full gear database, state in the URL.
import { loadGear, QUALITY, ICON, esc, num, srcText, SLOT_NAME } from "./items";
import { STAT_LABEL, sourceKind, type Item } from "./gear/model";

const $ = <T extends HTMLElement = HTMLInputElement>(id: string) => document.getElementById(id) as T;
const PAGE = 100;
let all: Item[] = [], shown = PAGE, sortKey = "ilvl", dir = -1;
const ids = ["f-q", "f-slot", "f-type", "f-q2", "f-min", "f-max", "f-src", "f-stat"];
const keys = ["q", "slot", "type", "quality", "min", "max", "src", "stat"];
const tname = (t: string) => t.replace(/[12]$/, "").replace(/^./, (c) => c.toUpperCase());

function filtered() {
  const t = $("f-q").value.trim().toLowerCase(), id = /^\d+$/.test(t) ? +t : 0;
  const slot = $("f-slot").value, type = $("f-type").value, q2 = +$("f-q2").value || 0;
  const min = +$("f-min").value || 0, max = +$("f-max").value || 99, src = $("f-src").value, stat = $("f-stat").value;
  const list = all.filter((it) => (!t || it.id === id || it.name.toLowerCase().includes(t)) && (!slot || it.slot === slot)
    && (!type || it.type === type) && it.q >= q2 && (it.req || 1) >= min && (it.req || 1) <= max
    && (!src || sourceKind(it) === src) && (!stat || (it.stats[stat] || 0) > 0));
  const val = (it: Item) => sortKey === "name" ? it.name : sortKey === "req" ? it.req : sortKey === "slot" ? it.slot : sortKey === "src" ? srcText(it) : it.ilvl;
  return list.sort((a, b) => { const x = val(a), y = val(b); return (typeof x === "string" ? x.localeCompare(y as string) : (x as number) - (y as number)) * dir || b.q - a.q; });
}
function render() {
  const list = filtered();
  $("f-count").textContent = `${list.length.toLocaleString("en-US")} items${list.length > shown ? `, showing ${shown}` : ""}`;
  $("irows").innerHTML = list.slice(0, shown).map((it) => {
    const q = QUALITY[num(it.q)] || "common";
    const stats = Object.entries(it.stats).filter(([k]) => k !== "armor" && k !== "dps").slice(0, 4).map(([k, v]) => `+${num(v)} ${STAT_LABEL[k] || k}`).join(", ");
    return `<tr><td><a class="ilink" href="/items/${num(it.id)}/" data-item="${num(it.id)}"><span class="ico sm qb-${q}">${it.icon ? `<img src="${esc(ICON(it.icon, 36))}" alt="" loading="lazy">` : ""}</span><span><span class="iname-t q-${q}">${esc(it.name)}</span><span class="sub">${esc(stats || (it.weapon ? `${it.weapon.dps} DPS` : it.stats.armor ? `${it.stats.armor} armor` : ""))}</span></span></a></td>
      <td class="num">${num(it.ilvl)}</td><td class="num opt">${num(it.req) || "–"}</td><td class="opt">${esc(SLOT_NAME[it.slot] || it.slot)}${it.type && it.type !== "misc" ? `<span class="sub">${esc(tname(it.type))}</span>` : ""}</td><td class="opt small">${esc(srcText(it))}</td></tr>`;
  }).join("") || `<tr><td colspan="5" class="muted">No items match. Clear a filter or two.</td></tr>`;
  $<HTMLButtonElement>("f-more").hidden = list.length <= shown;
  const p = new URLSearchParams();
  ids.forEach((id, i) => { const v = $(id).value.trim(); if (v) p.set(keys[i], v); });
  if (sortKey !== "ilvl" || dir !== -1) p.set("sort", `${sortKey}${dir > 0 ? "" : "-"}`);
  history.replaceState(null, "", p.toString() ? `?${p}` : location.pathname);
}

loadGear().then((db) => {
  all = db.items.filter((i) => i.q >= 0);
  const types = [...new Set(all.map((i) => i.type).filter((t) => t && t !== "misc"))].sort();
  $("f-type").insertAdjacentHTML("beforeend", types.map((t) => `<option value="${esc(t)}">${esc(tname(t))}</option>`).join(""));
  const stats = [...new Set(all.flatMap((i) => Object.keys(i.stats)))].filter((k) => k !== "dps").sort((a, b) => (STAT_LABEL[a] || a).localeCompare(STAT_LABEL[b] || b));
  $("f-stat").insertAdjacentHTML("beforeend", stats.map((k) => `<option value="${esc(k)}">${esc(STAT_LABEL[k] || k)}</option>`).join(""));
  const p = new URLSearchParams(location.search);
  ids.forEach((id, i) => { const v = p.get(keys[i]); if (v) $(id).value = v; });
  const s = p.get("sort"); if (s) { dir = s.endsWith("-") ? -1 : 1; sortKey = s.replace(/-$/, ""); }
  document.querySelectorAll<HTMLElement>("#itbl th").forEach((th) => th.setAttribute("aria-sort", th.dataset.sort === sortKey ? (dir > 0 ? "ascending" : "descending") : "none"));
  $("idb").setAttribute("aria-busy", "false");
  render();
}).catch(() => { $("f-count").textContent = "The gear database didn't load. Refresh to try again."; });

let timer = 0;
ids.forEach((id) => $(id).addEventListener("input", () => { clearTimeout(timer); timer = window.setTimeout(() => { shown = PAGE; render(); }, 100); }));
$("f-more").addEventListener("click", () => { shown += PAGE; render(); });
document.querySelectorAll<HTMLElement>("#itbl th[data-sort] button").forEach((b) => b.addEventListener("click", () => {
  const th = b.parentElement!, k = th.dataset.sort!;
  dir = k === sortKey ? -dir : (k === "name" || k === "slot" || k === "src" ? 1 : -1); sortKey = k;
  document.querySelectorAll<HTMLElement>("#itbl th").forEach((x) => x.setAttribute("aria-sort", x === th ? (dir > 0 ? "ascending" : "descending") : "none"));
  render();
}));

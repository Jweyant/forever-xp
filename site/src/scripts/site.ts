// Runs on every page: theme switch, phone menu, launch banner, quick search, item tooltips,
// broken game icons and a small toast helper other scripts can use.
import { loadGear, tooltipHtml, placeTip, ICON, QUALITY, esc, num } from "./items";

const root = document.documentElement;

// Theme
document.querySelector(".theme")?.addEventListener("click", () => {
  const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  root.dataset.theme = dark ? "light" : "dark";
  try { localStorage.setItem("theme", root.dataset.theme); } catch { /* storage blocked */ }
});

// Launch banner
document.querySelector("[data-hide-launch]")?.addEventListener("click", () => {
  root.dataset.nolaunch = "1";
  try { localStorage.setItem("hide-launch", "1"); } catch { /* storage blocked */ }
});

// Phone menu
const menuBtn = document.querySelector<HTMLButtonElement>(".icon-btn.menu");
const nav = document.getElementById("site-nav");
menuBtn?.addEventListener("click", () => {
  const open = !nav!.classList.contains("open");
  nav!.classList.toggle("open", open);
  menuBtn.setAttribute("aria-expanded", String(open));
});
document.addEventListener("click", (e) => {
  if (nav?.classList.contains("open") && !(e.target as Element).closest(".site-header")) {
    nav.classList.remove("open"); menuBtn?.setAttribute("aria-expanded", "false");
  }
});

// Game icons that fail to load (an icon Blizzard's CDN doesn't have) are hidden, not shown broken.
document.addEventListener("error", (e) => {
  const t = e.target as HTMLElement;
  if (t instanceof HTMLImageElement) t.dataset.broken = "1";
}, true);

// Icons that failed before this script ran.
for (const img of document.images) if (img.complete && img.naturalWidth === 0 && img.getAttribute("src")) img.dataset.broken = "1";

// Toast: window.fxpToast("Removed", { label: "Undo", run })
const toastEl = document.getElementById("toast")!;
let toastTimer = 0;
export function toast(msg: string, action?: { label: string; run: () => void }) {
  toastEl.innerHTML = `<span>${esc(msg)}</span>${action ? `<button type="button">${esc(action.label)}</button>` : ""}`;
  if (action) toastEl.querySelector("button")!.addEventListener("click", () => { action.run(); toastEl.classList.remove("show"); }, { once: true });
  toastEl.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => toastEl.classList.remove("show"), action ? 6000 : 3000);
}
(window as unknown as { fxpToast: typeof toast }).fxpToast = toast;

// ---------- Item tooltips on any [data-item] element ----------
const tip = document.getElementById("tip-global")!;
let tipFor: Element | null = null;
async function showItemTip(el: HTMLElement) {
  tipFor = el;
  const id = +el.dataset.item!;
  try {
    const db = await loadGear();
    if (tipFor !== el) return;
    const it = db.byId.get(id);
    if (!it) return;
    tip.innerHTML = tooltipHtml(it, db.sets, el.dataset.tipHint ? [`<p class="tt-hint">${esc(el.dataset.tipHint)}</p>`] : []);
    placeTip(tip, el);
  } catch { /* gear data unavailable: no tooltip */ }
}
function hideTip() { tipFor = null; tip.hidden = true; }
document.addEventListener("mouseover", (e) => {
  const el = (e.target as Element).closest<HTMLElement>("[data-item]");
  if (el && el !== tipFor) showItemTip(el);
  else if (!el && tipFor) hideTip();
});
document.addEventListener("focusin", (e) => { const el = (e.target as Element).closest<HTMLElement>("[data-item]"); if (el) showItemTip(el); });
document.addEventListener("focusout", hideTip);
window.addEventListener("scroll", () => { if (tipFor) hideTip(); }, { passive: true });

// ---------- Quick search ----------
type QRow = [number, string, number, string, string, string, number?];
type IRow = [number, string, number, string, string, number];
interface Hit { href: string; html: string }
const dlg = document.getElementById("search") as HTMLDialogElement;
const input = document.getElementById("search-q") as HTMLInputElement;
const results = document.getElementById("search-results")!;
let idx: { quests: QRow[]; items: IRow[] } | null = null;
let sel = 0, hits: Hit[] = [];

const PAGES: [string, string, string][] = [
  ["Leveling guides", "/guides/", "Routes"], ["Quest database", "/quests/", "All Forever quests"],
  ["Quest XP per minute", "/quests/xp/", "Fastest quests"], ["Skip list", "/skip/", "Quests to skip"],
  ["Item database", "/items/", "Every item"], ["BIS planner", "/bis/", "Best in slot"],
  ["Talent calculator", "/talents/", "All classes"], ["All Forever changes", "/changes/", "Patch notes"],
  ["ForeverScout addon", "/scout/", "Download"], ["Community and Discord", "/community/", "Discord"],
  ...["Warrior", "Paladin", "Hunter", "Rogue", "Priest", "Shaman", "Mage", "Warlock", "Druid"].map((c) =>
    [`${c} talents`, `/talents/${c.toLowerCase()}/`, "Talent calculator"] as [string, string, string]),
];

async function loadIndex() {
  if (idx) return idx;
  const [q, i] = await Promise.all([
    fetch("/data/quest-index.json").then((r) => (r.ok ? r.json() : [])).catch(() => []),
    fetch("/data/item-index.json").then((r) => (r.ok ? r.json() : [])).catch(() => []),
  ]);
  idx = { quests: q, items: i };
  return idx;
}
function rank(name: string, t: string) {
  const n = name.toLowerCase();
  if (n === t) return 0;
  if (n.startsWith(t)) return 1;
  if (n.includes(` ${t}`)) return 2;
  return n.includes(t) ? 3 : 9;
}
async function runSearch() {
  const t = input.value.trim().toLowerCase();
  if (!t) { results.innerHTML = `<p class="empty">Search ${"5,000+"} quests, every item, talents and guides.</p>`; hits = []; return; }
  const { quests, items } = await loadIndex();
  const id = /^\d+$/.test(t) ? +t : 0;
  const pageHits = PAGES.filter(([n, , s]) => rank(n, t) < 9 || s.toLowerCase().includes(t)).slice(0, 4)
    .map(([n, href, s]) => ({ href, html: `<span class="lv">›</span><span><b>${esc(n)}</b><br><span class="sub">${esc(s)}</span></span><span></span>` }));
  const qs = quests.map((q) => ({ q, r: q[0] === id ? -1 : Math.min(rank(q[1], t), rank(q[5] || "", t) + 2, rank(q[3], t) + 4) }))
    .filter((x) => x.r < 9).sort((a, b) => a.r - b.r || a.q[2] - b.q[2]).slice(0, 7)
    .map(({ q }) => {
      const side = q[4] === "H" || q[4] === "A" ? q[4] : "";
      return { href: `/quests/${num(q[0])}/`, html: `<span class="lv">${num(q[2]) > 0 ? num(q[2]) : "–"}</span><span><b>${esc(q[1])}</b>${q[6] ? `<span class="tag-new">NEW</span>` : ""}<br><span class="sub">${esc(q[3])}${q[5] ? `, from ${esc(q[5])}` : ""}</span></span><span class="sub ${side ? `side-${side}` : ""}">${side === "H" ? "Horde" : side === "A" ? "Alliance" : ""}</span>` };
    });
  const is = items.map((i) => ({ i, r: i[0] === id ? -1 : rank(i[1], t) })).filter((x) => x.r < 9)
    .sort((a, b) => a.r - b.r || b.i[5] - a.i[5]).slice(0, 7)
    .map(({ i }) => {
      const q = QUALITY[num(i[2])] || "common";
      return { href: `/items/${num(i[0])}/`, html: `<span class="ico sm qb-${q}">${i[3] ? `<img src="${esc(ICON(i[3], 36))}" alt="">` : ""}</span><span><b class="q-${q}">${esc(i[1])}</b><br><span class="sub">${esc(i[4])}, item level ${num(i[5])}</span></span><span></span>` };
    });
  hits = [...pageHits, ...qs, ...is];
  sel = 0;
  const group = (title: string, list: Hit[], offset: number) => list.length
    ? `<h3>${title}</h3>${list.map((h, k) => `<a href="${esc(h.href)}" role="option" data-i="${offset + k}" aria-selected="${offset + k === 0}">${h.html}</a>`).join("")}` : "";
  results.innerHTML = (group("Pages", pageHits, 0) + group("Quests", qs, pageHits.length) + group("Items", is, pageHits.length + qs.length))
    || `<p class="empty">Nothing matches "${esc(input.value)}". Try part of a name, or a quest or item ID.</p>`;
}
function move(d: number) {
  if (!hits.length) return;
  sel = (sel + d + hits.length) % hits.length;
  results.querySelectorAll("a").forEach((a) => a.setAttribute("aria-selected", String(+a.dataset.i! === sel)));
  results.querySelector(`a[data-i="${sel}"]`)?.scrollIntoView({ block: "nearest" });
}
function openSearch() {
  if (dlg.open) return;
  dlg.showModal();
  input.select();
  runSearch();
  loadIndex();
}
document.querySelectorAll("[data-open-search]").forEach((b) => b.addEventListener("click", openSearch));
document.addEventListener("keydown", (e) => {
  const typing = (e.target as Element).closest("input, textarea, select, [contenteditable]");
  if (!typing && (e.key === "/" || ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k"))) { e.preventDefault(); openSearch(); }
});
let st = 0;
input.addEventListener("input", () => { clearTimeout(st); st = window.setTimeout(runSearch, 80); });
input.addEventListener("keydown", (e) => {
  if (e.key === "ArrowDown") { e.preventDefault(); move(1); }
  else if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
  else if (e.key === "Enter") { e.preventDefault(); const h = hits[sel]; if (h) location.href = h.href; }
});
dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });

// Copy buttons: <button data-copy="text">
document.addEventListener("click", async (e) => {
  const b = (e.target as Element).closest<HTMLElement>("[data-copy]");
  if (!b) return;
  try { await navigator.clipboard.writeText(b.dataset.copy!); toast("Copied. Paste it in game chat."); }
  catch { toast("Couldn't copy. Select the text and press Ctrl+C."); }
});

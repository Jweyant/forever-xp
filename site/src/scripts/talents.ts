// Talent calculator. Reads the class data embedded in #talent-data, renders three trees,
// and keeps the build in the URL hash (one digit per talent, trees separated by "-").
import { afterSignIn } from "./account";
afterSignIn(); // put back a build the sign-in round trip dropped from the address
type Desc = [string, 0 | number[][]] | [string[]];
interface T { id: number; row: number; col: number; name: string; ranks: number; req: number | null; reqRank: number | null; icon: string | null; desc: Desc; est: boolean; need?: number; new?: boolean }
interface Tree { id: number; name: string; icon?: string | null; talents: T[] }
interface Cls { id: number; name: string; slug: string; trees: Tree[] }

const POINTS_PER_TIER = 5;
const ICON = (n: string) => `https://render.worldofwarcraft.com/us/icons/56/${String(n).toLowerCase().replace(/[^a-z0-9_-]/g, "")}.jpg`;

function fmt(v: number) { v = Math.abs(v); return Number.isInteger(v) ? String(v) : String(+v.toFixed(2)); }
function text(d: Desc, rank: number) {
  if (d.length === 1) { const t = d[0]; return t[Math.min(rank, t.length) - 1]; }
  const [tmpl, vals] = d;
  if (!vals) return tmpl;
  const row = vals[Math.min(rank, vals.length) - 1];
  return tmpl.replace(/\{(\d+)\}/g, (_, i) => fmt(row[+i]));
}
const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]!));

const root = document.getElementById("calc")!;
const cls: Cls = JSON.parse(document.getElementById("talent-data")!.textContent!);
const maxPoints = 51;
const byId = new Map<number, { t: T; tree: number }>();
cls.trees.forEach((tr, i) => tr.talents.forEach((t) => byId.set(t.id, { t, tree: i })));
const pts: number[][] = cls.trees.map((tr) => tr.talents.map(() => 0));

const treeSpent = (i: number) => pts[i].reduce((a, b) => a + b, 0);
const total = () => pts.reduce((s, _, i) => s + treeSpent(i), 0);
const rankOf = (id: number) => { const e = byId.get(id)!; return pts[e.tree][cls.trees[e.tree].talents.indexOf(e.t)]; };
const spentBelow = (i: number, row: number) => cls.trees[i].talents.reduce((s, t, k) => s + (t.row < row ? pts[i][k] : 0), 0);
// Points needed in this tree before a talent opens: the client's own rule, else 5 per row.
const need = (t: T) => (Number.isFinite(t.need) && (t.need as number) > 0 ? Number(t.need) : t.row * POINTS_PER_TIER);

function canAdd(i: number, k: number) {
  const t = cls.trees[i].talents[k];
  if (pts[i][k] >= t.ranks || total() >= maxPoints) return false;
  if (spentBelow(i, t.row) < need(t)) return false;
  if (t.req && rankOf(t.req) < (t.reqRank || 1)) return false;
  return true;
}
// A point can come off if every remaining talent still meets its tier and prerequisite rules.
function canRemove(i: number, k: number) {
  if (pts[i][k] <= 0) return false;
  pts[i][k]--;
  const ok = cls.trees[i].talents.every((t, j) => {
    if (!pts[i][j]) return true;
    if (spentBelow(i, t.row) < need(t)) return false;
    if (t.req && rankOf(t.req) < (t.reqRank || 1)) return false;
    return true;
  });
  pts[i][k]++;
  return ok;
}

function encode() { return pts.map((p) => p.join("").replace(/0+$/, "")).join("-").replace(/-+$/, ""); }
function decode(h: string) {
  const parts = h.replace(/^#/, "").split("-");
  pts.forEach((p, i) => p.forEach((_, k) => { const n = +(parts[i]?.[k] || 0); p[k] = Math.min(n, cls.trees[i].talents[k].ranks); }));
}

let selected: { i: number; k: number } | null = null;

function render() {
  const spent = total();
  root.querySelector<HTMLElement>("[data-left]")!.textContent = String(maxPoints - spent);
  root.querySelector<HTMLElement>("[data-split]")!.textContent = cls.trees.map((_, i) => treeSpent(i)).join(" / ");
  const req = Math.max(10, spent + 9);
  root.querySelector<HTMLElement>("[data-level]")!.textContent = spent ? String(req) : "–";
  cls.trees.forEach((tr, i) => {
    const el = root.querySelector<HTMLElement>(`[data-tree="${i}"]`)!;
    el.querySelector<HTMLElement>("[data-spent]")!.textContent = String(treeSpent(i));
    tr.talents.forEach((t, k) => {
      const b = el.querySelector<HTMLButtonElement>(`.tal[data-k="${k}"]`)!;
      const r = pts[i][k];
      b.dataset.state = r >= t.ranks ? "max" : r > 0 ? "some" : canAdd(i, k) ? "open" : "locked";
      b.querySelector("b")!.textContent = `${r}/${t.ranks}`;
      b.setAttribute("aria-label", `${t.name}, ${r} of ${t.ranks}`);
    });
    el.querySelectorAll<HTMLElement>(".arr").forEach((a) => {
      const t = tr.talents[+a.dataset.a!];
      a.toggleAttribute("data-on", !!t.req && rankOf(t.req) >= (t.reqRank || 1));
    });
  });
  const h = encode();
  history.replaceState(null, "", h ? `#${h}` : location.pathname);
  const share = root.querySelector<HTMLInputElement>("[data-share]")!;
  share.value = location.href;
  showDetail();
}

// Built from DOM nodes with textContent: talent names and tooltips come from the game client.
function el<K extends keyof HTMLElementTagNameMap>(tag: K, className: string, ...kids: (Node | string)[]) {
  const e = document.createElement(tag);
  if (className) e.className = className;
  e.append(...kids);
  return e;
}

function showDetail() {
  const box = root.querySelector<HTMLElement>("[data-detail]")!;
  if (!selected) { box.replaceChildren(el("p", "muted", "Pick a talent to see what each rank does. Click or tap to add a point; right-click or long-press to remove one.")); return; }
  const { i, k } = selected; const t = cls.trees[i].talents[k]; const r = Number(pts[i][k]) || 0;
  const ranks = Number(t.ranks) || 0, reqRank = Number(t.reqRank) || 1;
  const reqT = t.req ? byId.get(t.req)?.t : null;
  const out: Node[] = [el("h3", "", `${t.name} `, el("span", "muted", `${r}/${ranks}`))];
  if (t.new) out.push(el("p", "small new-note", "New in WoW Forever"));
  if (need(t)) out.push(el("p", "small muted", `Needs ${need(t)} points in ${cls.trees[i].name}.${reqT ? ` Needs ${reqRank} in ${reqT.name}.` : ""}`));
  else if (reqT) out.push(el("p", "small muted", `Needs ${reqRank} in ${reqT.name}.`));
  if (r > 0) out.push(el("p", "", el("b", "", `Rank ${r}:`), ` ${text(t.desc, r)}`));
  if (r < ranks) out.push(el("p", r ? "muted" : "", el("b", "", r ? "Next rank:" : "Rank 1:"), ` ${text(t.desc, r + 1)}`));
  if (t.est && ranks > 1) out.push(el("p", "small est", "The Forever client only lists the first rank's numbers for this talent. Later ranks are scaled from Classic Era and may be off."));
  box.replaceChildren(...out);
}

// Arrow from a prerequisite to the talent that needs it, placed on the same grid as the icons.
function arrow(tr: Tree, k: number) {
  const t = tr.talents[k];
  const p = t.req ? tr.talents.find((x) => x.id === t.req) : undefined;
  if (!p) return "";
  const r0 = Number(p.row), r1 = Number(t.row), c0 = Number(p.col), c1 = Number(t.col);
  const dir = c1 >= c0 ? "r" : "l";
  const kind = c0 === c1 ? "v" : r0 === r1 ? "h" : "e";
  const rows = `${Math.min(r0, r1) + 1} / ${Math.max(r0, r1) + 2}`, cols = `${Math.min(c0, c1) + 1} / ${Math.max(c0, c1) + 2}`;
  return `<span class="arr ${kind}" data-dir="${dir}" data-a="${k}" style="grid-row:${rows};grid-column:${cols}" aria-hidden="true"><i class="ln"></i><i class="ln2"></i><i class="hd"></i></span>`;
}

function build() {
  const grid = root.querySelector<HTMLElement>("[data-trees]")!;
  grid.innerHTML = cls.trees.map((tr, i) => {
    const rows = Math.max(7, ...tr.talents.map((t) => Number(t.row) + 1));
    const arrows = tr.talents.map((_, k) => arrow(tr, k)).join("");
    const cells = tr.talents.map((t, k) => {
      const icon = t.icon ? `<img src="${esc(ICON(t.icon))}" alt="" loading="lazy" width="40" height="40">` : "";
      const tag = t.new ? `<em class="new" aria-hidden="true">New</em>` : "";
      return `<button type="button" class="tal" data-k="${k}" style="grid-row:${Number(t.row) + 1};grid-column:${Number(t.col) + 1}" title="${esc(t.name)}">${icon}<span class="ini" aria-hidden="true">${esc(t.name.slice(0, 2))}</span>${tag}<b>0/${Number(t.ranks)}</b></button>`;
    }).join("");
    const head = tr.icon ? `<img class="ti" src="${esc(ICON(tr.icon))}" alt="" width="28" height="28">` : "";
    return `<section class="tree" data-tree="${i}"><h2>${head}<span class="tn">${esc(tr.name)}</span> <span data-spent>0</span></h2><div class="grid" style="grid-template-rows:repeat(${Number(rows)},48px)">${arrows}${cells}</div></section>`;
  }).join("");
  grid.querySelectorAll<HTMLElement>(".tree").forEach((sec) => {
    const tr = cls.trees[+sec.dataset.tree!];
    if (tr.icon) sec.style.setProperty("--tree-bg", `url("${ICON(tr.icon)}")`);
  });
  grid.querySelectorAll<HTMLElement>(".tree").forEach((sec) => {
    const i = +sec.dataset.tree!;
    sec.querySelectorAll<HTMLButtonElement>(".tal").forEach((b) => {
      const k = +b.dataset.k!;
      const add = () => { selected = { i, k }; if (canAdd(i, k)) pts[i][k]++; render(); };
      const remove = () => { selected = { i, k }; if (canRemove(i, k)) pts[i][k]--; render(); };
      b.addEventListener("click", (e) => { if (e.shiftKey) remove(); else add(); });
      b.addEventListener("contextmenu", (e) => { e.preventDefault(); remove(); });
      let timer: number | undefined;
      b.addEventListener("touchstart", () => { timer = window.setTimeout(() => { timer = undefined; remove(); }, 450); }, { passive: true });
      b.addEventListener("touchend", (e) => { if (timer === undefined) e.preventDefault(); clearTimeout(timer); });
      b.addEventListener("focus", () => { selected = { i, k }; showDetail(); });
      b.addEventListener("mouseenter", () => { selected = { i, k }; showDetail(); });
      b.addEventListener("keydown", (e) => { if (e.key === "-" || e.key === "Backspace" || e.key === "Delete") { e.preventDefault(); remove(); } });
    });
  });
  root.querySelector("[data-reset]")!.addEventListener("click", () => { pts.forEach((p) => p.fill(0)); selected = null; render(); });
  root.querySelector("[data-copy]")!.addEventListener("click", async (e) => {
    const btn = e.currentTarget as HTMLButtonElement;
    try { await navigator.clipboard.writeText(location.href); btn.textContent = "Link copied"; }
    catch { root.querySelector<HTMLInputElement>("[data-share]")!.select(); btn.textContent = "Press Ctrl+C to copy"; }
    setTimeout(() => (btn.textContent = "Copy build link"), 2000);
  });
}

build();
if (location.hash) decode(location.hash);
render();

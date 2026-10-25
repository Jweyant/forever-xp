// Talent calculator. Reads the class data embedded in #talent-data, renders three trees,
// and keeps the build in the URL hash (one digit per talent, trees separated by "-").
type Desc = [string, 0 | number[][]] | [string[]];
interface T { id: number; row: number; col: number; name: string; ranks: number; req: number | null; reqRank: number | null; icon: string | null; desc: Desc; est: boolean }
interface Tree { id: number; name: string; talents: T[] }
interface Cls { id: number; name: string; slug: string; trees: Tree[] }

const POINTS_PER_TIER = 5;
const ICON = (n: string) => `https://render.worldofwarcraft.com/us/icons/56/${n}.jpg`;

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

function canAdd(i: number, k: number) {
  const t = cls.trees[i].talents[k];
  if (pts[i][k] >= t.ranks || total() >= maxPoints) return false;
  if (spentBelow(i, t.row) < t.row * POINTS_PER_TIER) return false;
  if (t.req && rankOf(t.req) < (t.reqRank || 1)) return false;
  return true;
}
// A point can come off if every remaining talent still meets its tier and prerequisite rules.
function canRemove(i: number, k: number) {
  if (pts[i][k] <= 0) return false;
  pts[i][k]--;
  const ok = cls.trees[i].talents.every((t, j) => {
    if (!pts[i][j]) return true;
    if (spentBelow(i, t.row) < t.row * POINTS_PER_TIER) return false;
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
      const b = el.querySelector<HTMLButtonElement>(`[data-k="${k}"]`)!;
      const r = pts[i][k];
      b.dataset.state = r >= t.ranks ? "max" : r > 0 ? "some" : canAdd(i, k) ? "open" : "locked";
      b.querySelector("b")!.textContent = `${r}/${t.ranks}`;
      b.setAttribute("aria-label", `${t.name}, ${r} of ${t.ranks}`);
    });
  });
  const h = encode();
  history.replaceState(null, "", h ? `#${h}` : location.pathname);
  const share = root.querySelector<HTMLInputElement>("[data-share]")!;
  share.value = location.href;
  showDetail();
}

function showDetail() {
  const box = root.querySelector<HTMLElement>("[data-detail]")!;
  if (!selected) { box.innerHTML = `<p class="muted">Pick a talent to see what each rank does. Click or tap to add a point; right-click or long-press to remove one.</p>`; return; }
  const { i, k } = selected; const t = cls.trees[i].talents[k]; const r = pts[i][k];
  const reqT = t.req ? byId.get(t.req)?.t : null;
  const lines: string[] = [];
  lines.push(`<h3>${esc(t.name)} <span class="muted">${r}/${t.ranks}</span></h3>`);
  if (t.row) lines.push(`<p class="small muted">Needs ${t.row * POINTS_PER_TIER} points in ${esc(cls.trees[i].name)}.${reqT ? ` Needs ${t.reqRank || 1} in ${esc(reqT.name)}.` : ""}</p>`);
  else if (reqT) lines.push(`<p class="small muted">Needs ${t.reqRank || 1} in ${esc(reqT.name)}.</p>`);
  if (r > 0) lines.push(`<p><b>Rank ${r}:</b> ${esc(text(t.desc, r))}</p>`);
  if (r < t.ranks) lines.push(`<p class="${r ? "muted" : ""}"><b>${r ? "Next rank" : "Rank 1"}:</b> ${esc(text(t.desc, r + 1))}</p>`);
  if (t.est && t.ranks > 1) lines.push(`<p class="small est">The Forever client only lists the first rank's numbers for this talent. Later ranks are scaled from Classic Era and may be off.</p>`);
  box.innerHTML = lines.join("");
}

function build() {
  const grid = root.querySelector<HTMLElement>("[data-trees]")!;
  grid.innerHTML = cls.trees.map((tr, i) => {
    const rows = Math.max(7, ...tr.talents.map((t) => t.row + 1));
    const cells = tr.talents.map((t, k) => {
      const icon = t.icon ? `<img src="${ICON(t.icon)}" alt="" loading="lazy" width="40" height="40" onerror="this.remove()">` : "";
      return `<button type="button" class="tal" data-k="${k}" style="grid-row:${t.row + 1};grid-column:${t.col + 1}" title="${esc(t.name)}">${icon}<span class="ini" aria-hidden="true">${esc(t.name.slice(0, 2))}</span><b>0/${t.ranks}</b></button>`;
    }).join("");
    return `<section class="tree" data-tree="${i}"><h2>${esc(tr.name)} <span data-spent>0</span></h2><div class="grid" style="grid-template-rows:repeat(${rows},48px)">${cells}</div></section>`;
  }).join("");
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

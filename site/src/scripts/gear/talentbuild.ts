// Talent builds in the BIS planner: read a build from the talent calculator's link or its string,
// check it against Forever's trees, and work out the hit chance it gives.
// The build string is the calculator's (and the wowsims engine's) format: one digit per talent in
// tree order, trees separated by "-". Everything here is untrusted text until parseBuild() says ok.
import data from "../../data/plannertalents.json";

interface HitTalent { tree: number; i: number; name: string; kind: string; pct: number[] }
interface ClassTalents { slug: string; trees: [string, [number, number][]][]; hit: HitTalent[] }
const DATA = data as unknown as { build: string; classes: Record<string, ClassTalents> };
const own = (o: object, k: string) => Object.prototype.hasOwnProperty.call(o, k);

export const MAX_POINTS = 51;
export interface Build { str: string; pts: number[][]; split: number[]; spent: number }
export type Parsed = { ok: true; cls: string; build: Build } | { ok: false; error: string };

export function classTalents(cls: string): ClassTalents | null {
  return own(DATA.classes, cls) ? DATA.classes[cls] : null;
}
/** The class a calculator slug names ("warrior" -> "WARRIOR"), or "". */
function classOfSlug(slug: string): string {
  return Object.keys(DATA.classes).find((k) => DATA.classes[k].slug === slug) || "";
}

/** The calculator's own encoding: trailing zeros and empty trailing trees dropped. */
function encode(pts: number[][]): string {
  return pts.map((p) => p.join("").replace(/0+$/, "")).join("-").replace(/-+$/, "");
}

// A link to our own calculator, on the live site, a preview deploy, or as a path.
const LINK = /^(?:https:\/\/(?:www\.)?forever-xp\.com|https:\/\/[a-z0-9-]+\.forever-xp\.pages\.dev)?\/talents\/([a-z]+)\/?#([0-9-]*)$/;
const RAW = /^[0-9-]*$/;

/** Reads a pasted calculator link or build string for `cls`. A link to another class's calculator
 *  comes back with that class, so the planner can switch to it. */
export function parseBuild(input: string, cls: string): Parsed {
  const text = String(input).trim();
  if (text.length > 200) return { ok: false, error: "That's too long to be a talent build." };
  let str = text, c = cls;
  const m = text.match(LINK);
  if (m) {
    c = classOfSlug(m[1]);
    if (!c) return { ok: false, error: "That link isn't to one of this site's class talent calculators." };
    str = m[2];
  } else if (!RAW.test(text)) {
    return { ok: false, error: "Paste a link from this site's talent calculator, or a build like 30325213132515201-0505-2." };
  }
  const ct = classTalents(c);
  if (!ct) return { ok: false, error: "There's no talent data for that class." };
  const parts = str.split("-");
  if (parts.length > ct.trees.length) return { ok: false, error: `A ${c.toLowerCase()} build has only ${ct.trees.length} trees.` };
  const pts = ct.trees.map(([, tals], i) => tals.map((_, k) => Number((parts[i] || "")[k] || 0)));
  for (let i = 0; i < ct.trees.length; i++) {
    const [tname, tals] = ct.trees[i];
    if ((parts[i] || "").length > tals.length) return { ok: false, error: `The ${tname} part of that build is longer than the tree.` };
    for (let k = 0; k < tals.length; k++) {
      if (pts[i][k] > tals[k][1]) return { ok: false, error: `That build puts more points in a ${tname} talent than it has ranks. It may be from an older version of the trees.` };
    }
  }
  const split = pts.map((p) => p.reduce((a, b) => a + b, 0));
  const spent = split.reduce((a, b) => a + b, 0);
  if (spent > MAX_POINTS) return { ok: false, error: `That build spends ${spent} points; a level 60 character has ${MAX_POINTS}.` };
  return { ok: true, cls: c, build: { str: encode(pts), pts, split, spent } };
}

/** The calculator link for a build (constant parts plus a string parseBuild() produced). */
export function calcLink(cls: string, build: Build): string {
  const ct = classTalents(cls);
  return ct ? `/talents/${ct.slug}/${build.str ? `#${build.str}` : ""}` : "/talents/";
}
export const treeNames = (cls: string) => (classTalents(cls)?.trees || []).map(([n]) => n);

export interface HitFrom { name: string; pct: number }
/** Hit % a build's talents give to physical attacks, or to spells of `school`. */
export function talentHit(cls: string, build: Build | null, kind: "phys" | "spell", school?: string): HitFrom[] {
  const ct = classTalents(cls);
  if (!ct || !build) return [];
  const out: HitFrom[] = [];
  for (const h of ct.hit) {
    const rank = build.pts[h.tree]?.[h.i] || 0;
    if (!rank) continue;
    const applies = h.kind === "all" || (kind === "phys" ? h.kind === "phys"
      : h.kind === "spell:all" || (h.kind.startsWith("spell:") && !!school && h.kind.slice(6).split(",").includes(school)));
    const pct = Number(h.pct[rank - 1]);
    if (applies && Number.isFinite(pct) && pct > 0) out.push({ name: h.name, pct });
  }
  return out;
}

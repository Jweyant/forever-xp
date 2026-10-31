import qdbJson from "../data/questdb.json";

export interface Place { n: string; t: string; id?: number; z?: string; x?: number; y?: number; src?: string }
export interface QQuest {
  id: number; n: string; lv: number; req: number; z: string; side?: "A" | "H"; cls?: string[]; xp?: number; xpe?: 1; xps?: string;
  start?: Place; end?: Place; obj?: string; pre?: number[]; next?: number; rep?: 1;
  rew?: { id: number; n: string; q?: number; icon?: string }[]; repu?: number; new?: 1; chg?: string[];
  /** Objective spawn areas from Questie: name, npc/object/item, zone, points on a 0-100 map grid. */
  objs?: { n: string; t: string; z: string; a: [number, number][] }[];
  /** Where ForeverScout players progressed objectives: [x, y, players]. */
  seen?: [number, number, number][];
}
/** The point nearest the middle of a spawn area, for a /way line. */
export function centre(a: [number, number][]): [number, number] | null {
  if (!a.length) return null;
  const mx = a.reduce((s, p) => s + p[0], 0) / a.length, my = a.reduce((s, p) => s + p[1], 0) / a.length;
  return a.reduce((b, p) => ((p[0] - mx) ** 2 + (p[1] - my) ** 2 < (b[0] - mx) ** 2 + (b[1] - my) ** 2 ? p : b));
}
/** Clamp a map coordinate to a plain 0-100 number for markup. */
export const pct = (v: unknown) => Math.min(100, Math.max(0, Number(v) || 0));
export const qdb = qdbJson as QQuest[];
/** Quest XP for display: estimates (no source has the real number yet) get a "~". */
export const xpText = (q: QQuest) => (q.xp ? `${q.xpe ? "~" : ""}${q.xp}` : "–");
export const OPENDATA = "https://github.com/wowlayerup-forever/opendata";
export const qById = new Map(qdb.map((q) => [q.id, q]));

// Questie's chain links are often recorded on only one side (A.next = B without B.pre = [A],
// or B.pre = [A] without A.next = B), so index both directions before walking a chain.
const cameFrom = new Map<number, number[]>(); // B -> quests whose next is B
const leadsTo = new Map<number, number[]>();  // A -> quests whose first prerequisite is A
const push = (m: Map<number, number[]>, k: number, v: number) => { const l = m.get(k); if (l) { if (!l.includes(v)) l.push(v); } else m.set(k, [v]); };
for (const q of qdb) {
  if (q.next && qById.has(q.next) && q.next !== q.id) push(cameFrom, q.next, q.id);
  const p = (q.pre || []).find((id) => id > 0);
  if (p && qById.has(p) && p !== q.id) push(leadsTo, p, q.id);
}
/** The quest before this one in its chain, or undefined. */
export function prevQuest(q: QQuest): number | undefined {
  const own = (q.pre || []).find((id) => id > 0 && qById.has(id) && id !== q.id);
  if (own) return own;
  const from = cameFrom.get(q.id);
  return from && from.length === 1 ? from[0] : undefined;
}
/** Quests that follow this one: its own next, else every quest that names it as prerequisite. */
export function nextQuests(q: QQuest): number[] {
  if (q.next && qById.has(q.next) && q.next !== q.id) return [q.next];
  return leadsTo.get(q.id) ?? [];
}
/** The straight-line chain through a quest, plus any branches where it splits at the end. */
export function questChain(q: QQuest): { chain: number[]; branches: number[]; from: number[] } {
  const seen = new Set([q.id]);
  const back: number[] = [];
  for (let cur = prevQuest(q); cur && !seen.has(cur) && back.length < 20; cur = prevQuest(qById.get(cur)!)) { seen.add(cur); back.unshift(cur); }
  const fwd: number[] = [];
  let tail = q, branches: number[] = [];
  while (fwd.length < 20) {
    const n = nextQuests(tail).filter((id) => !seen.has(id));
    if (n.length !== 1) { branches = n; break; }
    seen.add(n[0]); fwd.push(n[0]); tail = qById.get(n[0])!;
  }
  // When the start of the chain is reached from several quests (often one per faction), list them.
  const first = qById.get(back[0] ?? q.id)!;
  const from = prevQuest(first) ? [] : (cameFrom.get(first.id) ?? []).filter((id) => !seen.has(id));
  const chain = back.length || fwd.length || branches.length || from.length ? [...back, q.id, ...fwd] : [];
  return { chain, branches, from };
}
export const zslug = (z: string) => z.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
export const QUALITY = ["poor", "common", "uncommon", "rare", "epic", "legendary", "artifact"];
export const ICON = (n: string) => `https://render.worldofwarcraft.com/us/icons/56/${n}.jpg`;
export const SIDE_LABEL = { A: "Alliance", H: "Horde" } as const;
const PROF = new Set(["Alchemy", "Blacksmithing", "Cooking", "Crafting", "Engineering", "First Aid", "Fishing", "Herbalism", "Leatherworking", "Tailoring"]);
const CLS = new Set(["Druid", "Hunter", "Mage", "Paladin", "Priest", "Rogue", "Shaman", "Warlock", "Warrior"]);
export function zoneKind(z: string) { return CLS.has(z) ? "Class" : PROF.has(z) ? "Profession" : "Zone"; }

export const qzones = (() => {
  const m = new Map<string, { name: string; slug: string; count: number; min: number; max: number; kind: string }>();
  for (const q of qdb) {
    const e = m.get(q.z) ?? { name: q.z, slug: zslug(q.z), count: 0, min: 99, max: 0, kind: zoneKind(q.z) };
    e.count++;
    if (q.lv > 0) { e.min = Math.min(e.min, q.lv); e.max = Math.max(e.max, q.lv); }
    m.set(q.z, e);
  }
  return [...m.values()].sort((a, b) => a.name.localeCompare(b.name));
})();

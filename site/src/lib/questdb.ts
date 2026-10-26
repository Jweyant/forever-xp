import qdbJson from "../data/questdb.json";

export interface Place { n: string; t: string; id?: number; z?: string; x?: number; y?: number }
export interface QQuest {
  id: number; n: string; lv: number; req: number; z: string; side?: "A" | "H"; cls?: string[]; xp?: number;
  start?: Place; end?: Place; obj?: string; pre?: number[]; next?: number; rep?: 1;
  rew?: { id: number; n: string; q?: number; icon?: string }[]; repu?: number; new?: 1; chg?: string[];
}
export const qdb = qdbJson as QQuest[];
export const qById = new Map(qdb.map((q) => [q.id, q]));
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

import gearJson from "../data/items.json";
import type { Item } from "../scripts/gear/model";
import type { ItemSet } from "../scripts/items";
import { qdb } from "./questdb";

export const gear = gearJson as unknown as { build: string; items: Item[]; sets: Record<string, ItemSet> };
export const itemById = new Map(gear.items.map((i) => [i.id, i]));
// Quests that reward each item, from Questie.
export const rewardedBy = (() => {
  const m = new Map<number, { id: number; n: string; lv: number; z: string; side?: string }[]>();
  for (const q of qdb) for (const r of q.rew || []) {
    if (!m.has(r.id)) m.set(r.id, []);
    m.get(r.id)!.push({ id: q.id, n: q.n, lv: q.lv, z: q.z, side: q.side });
  }
  return m;
})();
export const setItems = (() => {
  const m = new Map<number, Item[]>();
  for (const it of gear.items) if (it.set) { if (!m.has(it.set)) m.set(it.set, []); m.get(it.set)!.push(it); }
  return m;
})();

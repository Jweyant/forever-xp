// Dungeons and raids (gamedata/raids.json, built by tools/build_raids.py from AtlasLoot, cmangos,
// Questie and ForeverScout player data).
import raidsJson from "../data/raids.json";

export interface Boss {
  name: string; npc: number; lv?: number; hp?: number; armor?: number; res?: Record<string, number>;
  /** [item id, drop chance % or null, players who saw it drop in Forever?] */
  loot: [number, number | null, number?][];
  classic_only?: number;
  seen?: { kills?: number; wipes?: number; median_kill_seconds?: number; groups?: number };
}
export interface Instance {
  slug: string; name: string; kind: "dungeon" | "raid"; size?: number; lv?: [number, number]; reset?: number;
  entrance?: [string, number, number]; quests?: [number, string, number][];
  bosses: Boss[]; other: { name: string; loot: [number][] }[];
}
const SLUG = /^[a-z0-9-]+$/;
export const instances = (raidsJson as unknown as Instance[]).filter((r) => r && typeof r.slug === "string" && SLUG.test(r.slug));
export const instanceBySlug = new Map(instances.map((r) => [r.slug, r]));
export const raidSlug = (name: string) => name.toLowerCase().replace(/'/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
export const levelText = (r: Instance) => (r.lv ? (r.lv[0] === r.lv[1] ? `${r.lv[0]}` : `${r.lv[0]}–${r.lv[1]}`) : "–");
export const sizeText = (r: Instance) => (r.kind === "dungeon" ? "5 players" : r.size ? `${r.size} players` : "Open world");
export const mins = (s?: number) => (s ? `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}` : "");

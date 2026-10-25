import guidesJson from "../data/guides.json";
import questsJson from "../data/quests.json";
import zonesJson from "../data/zones.json";
import metaJson from "../data/meta.json";

export type Verdict = "do" | "skip" | "optional" | "unknown";
export interface Quest {
  id: number; name: string; level?: number | null; req?: number | null; xp?: number | null;
  kill_xp?: number | null; minutes?: number | null; xp_per_min?: number | null;
  giver?: string | null; ender?: string | null; zone?: string | null; zone_id?: number | null;
  pre?: number[]; next?: number | null; unlocated?: boolean; source: string;
  guides: string[]; in_route: boolean; verdict: Verdict;
  skip_note?: { note: string; reason: string; guide: string };
  measured?: { minutes: number | null; xp_per_min: number | null; players: number | null };
}
export interface Guide {
  slug: string; name: string; zone: string; from: number; to: number; faction: string;
  for?: string; class?: string; next?: string; quest_ids: number[]; step_count: number;
  end_level: number | null; minutes: number | null; left_in_log: number[]; issues: string[];
  quests: { id: number; name: string; xp: number; minutes: number; xp_per_min: number }[];
  steps: { n: number; level: number; minutes: number; xp: number; text: string }[];
}

export const guides = guidesJson as Guide[];
export const quests = questsJson as Quest[];
export const zones = zonesJson as { name: string; slug: string; quests: number; do: number; skip: number; optional: number; unknown: number; median_xp_per_min: number | null }[];
export const meta = metaJson as { built: string; skip_threshold: number; measured_quests: number; quests: number; guides: number };
export const questById = new Map(quests.map((q) => [q.id, q]));
export const guideBySlug = new Map(guides.map((g) => [g.slug, g]));

export const RELEASES = "https://github.com/Jweyant/forever-xp/releases/latest";
export const REPO = "https://github.com/Jweyant/forever-xp";
export const SUBMIT_LOG = "https://github.com/Jweyant/forever-xp/issues/new?template=submit-log.yml";

export const VERDICT_LABEL: Record<Verdict, string> = {
  do: "In route", skip: "Skip", optional: "Optional", unknown: "No data",
};

export function rateOf(q: Quest) {
  return q.measured?.xp_per_min ?? q.xp_per_min ?? null;
}
export function fmtMinutes(m: number | null | undefined) {
  if (m == null) return "–";
  if (m < 60) return `${Math.round(m)} min`;
  const h = Math.floor(m / 60);
  return `${h} h ${Math.round(m - h * 60)} min`;
}

// The rows behind /changes/ and the per-class and racial pages: Blizzard's development notes plus
// the talent changes read from the Forever client. All text here comes from outside (Blizzard's
// forum posts, the game client) and is only ever rendered through Astro's escaping.
import changesJson from "../data/changes.json";
import notesJson from "../data/notes.json";

interface Note { id: string; date: string; kind: string; section: string; path: string[]; text: string; url: string; cls?: string; race?: string; spec?: string; detail?: string[]; note?: string[]; dev?: 1 }
interface Talent { cls: string | null; tree: string; name: string; was?: string | null; kinds: string[]; forever?: string; est?: boolean }
export type Row = { id: string; date: string; kind: "Blizzard" | "Known issue" | "Datamined"; area: string; path: string[]; text: string; url?: string; cls?: string; race?: string; detail?: string[]; note?: string[]; dev?: boolean; chips?: string[] };

export const notes = notesJson as { updated: string; sources: { id: number; title: string; url: string; kind: string; updated: string; rows: number }[]; articles: { title: string; url: string }[]; announcements?: unknown[]; rows: Note[] };

// Blizzard's announcements for the News page. The collector already checks them; this checks again
// before anything reaches a page, and only ever links to a forum topic.
export type News = { id: number; date: string; title: string; url: string; category: string; kind: "Article" | "Forum post"; excerpt?: string; notes?: boolean };
const FORUM_TOPIC = /^https:\/\/us\.forums\.blizzard\.com\/en\/wow\/t\/[a-z0-9-]{1,120}\/\d{1,12}$/;
const str = (v: unknown, n: number) => (typeof v === "string" ? v.slice(0, n) : "");
export const news: News[] = (Array.isArray(notes.announcements) ? notes.announcements : [])
  .filter((a): a is Record<string, unknown> => !!a && typeof a === "object")
  .filter((a) => Number.isInteger(a.id) && typeof a.title === "string" && a.title && typeof a.date === "string" && /^\d{4}-\d{2}-\d{2}$/.test(a.date) && typeof a.url === "string" && FORUM_TOPIC.test(a.url))
  .map((a) => ({
    id: Number(a.id), date: a.date as string, title: str(a.title, 200), url: a.url as string,
    category: str(a.category, 60) || "WoW Forever", kind: a.kind === "Article" ? "Article" as const : "Forum post" as const,
    excerpt: str(a.excerpt, 300) || undefined, notes: a.notes === 1,
  }))
  .sort((a, b) => b.date.localeCompare(a.date) || b.id - a.id);
const data = changesJson as unknown as { builds: { forever: string }; talents: Talent[] };
export const build = data.builds.forever;

export const CLASSES = ["Warrior", "Paladin", "Hunter", "Rogue", "Priest", "Shaman", "Mage", "Warlock", "Druid"];
export const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-");
export const fmt = (d: string) => (d ? new Date(`${d}T12:00:00Z`).toLocaleDateString("en-US", { month: "short", day: "numeric" }) : "");

const KIND_LABEL: Record<string, string> = { new: "New talent", reworked: "Reworked", renamed: "Renamed", numbers: "New numbers", moved: "Moved", "moved tree": "New tree", ranks: "Ranks changed", removed: "Removed" };
const own = (o: object, k: string) => Object.prototype.hasOwnProperty.call(o, k);
// Talents where the client only stores rank 1's numbers are left out until they can be confirmed.
const sure = (c: Talent) => c.kinds.includes("reworked") || c.kinds.includes("renamed") || !c.est;

export const rows: Row[] = [
  ...notes.rows.map((r) => ({
    id: r.id, date: r.date, kind: (r.kind === "Known issues" ? "Known issue" : "Blizzard") as Row["kind"], area: r.section,
    path: r.path, text: r.text, url: r.url, cls: r.cls, race: r.race, detail: r.detail, note: r.note, dev: !!r.dev,
  })),
  ...data.talents.filter(sure).map((t, i) => ({
    id: `t${i}`, date: "", kind: "Datamined" as const, area: "Talents", path: [t.cls || "", t.tree].filter(Boolean),
    text: `${t.name}${t.was ? ` (was ${t.was})` : ""}: ${t.forever || "Removed."}`, cls: t.cls || undefined,
    chips: t.kinds.map((k) => (own(KIND_LABEL, k) ? KIND_LABEL[k] : k)),
  })),
].sort((a, b) => (b.date || "0").localeCompare(a.date || "0"));

export const races = [...new Set(rows.map((r) => r.race).filter(Boolean))].sort() as string[];

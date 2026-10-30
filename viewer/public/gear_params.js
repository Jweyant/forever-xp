// Validates what the embedding page (or the URL hash) asks the viewer to draw.
// Everything arriving here is untrusted; only numbers from these allow-lists get through.

// Classic character model ids on the model viewer (race * 2 - 1 + gender).
export const RACE_MIN = 1, RACE_MAX = 8; // human..troll
// Model viewer item slots: head, shoulder, shirt, chest, waist, legs, feet, wrists, hands,
// ranged (bow), back, tabard, main hand, off hand, ranged (gun/wand).
export const SLOTS = new Set([1, 3, 4, 5, 6, 7, 8, 9, 10, 15, 16, 19, 21, 22, 26]);
const MAX_ITEMS = 19;

const num = (v, lo, hi) => {
  const n = Math.trunc(Number(v));
  return Number.isFinite(n) && n >= lo && n <= hi ? n : 0;
};

/** {race, gender, items} (untrusted) -> clean {race, gender, items} or null. */
export function parseGear(o) {
  if (!o || typeof o !== "object") return null;
  const race = num(o.race, RACE_MIN, RACE_MAX);
  const gender = num(o.gender, 0, 1);
  if (!race) return null;
  const items = [];
  for (const pair of Array.isArray(o.items) ? o.items.slice(0, MAX_ITEMS) : []) {
    const s = num(Array.isArray(pair) ? pair[0] : null, 1, 28);
    const d = num(Array.isArray(pair) ? pair[1] : null, 1, 9999999);
    if (SLOTS.has(s) && d && !items.some((x) => x[0] === s)) items.push([s, d]);
  }
  return { race, gender, items };
}

/** "#r=8&g=0&i=1:30606,5:30990" -> clean gear or null. */
export function parseHash(hash) {
  const p = new URLSearchParams(String(hash).replace(/^#/, ""));
  return parseGear({
    race: p.get("r"),
    gender: p.get("g"),
    items: (p.get("i") || "").split(",").filter(Boolean).map((x) => x.split(":")),
  });
}

/** Which windows may send gear with postMessage, and the only one we ever target back. */
export function parentAllowed(origin) {
  if (origin === "https://forever-xp.com" || origin === "https://www.forever-xp.com") return true;
  try { // deploy previews
    const u = new URL(origin);
    return u.protocol === "https:" && u.hostname.endsWith(".forever-xp.pages.dev");
  } catch {
    return false;
  }
}

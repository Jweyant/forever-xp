// Reference BIS picks from the site's planner logic, for tools/test/test_planner.py.
// Mirrors site/src/scripts/gear/planner.ts suggest(): a hit-cap-aware search over the hit weight,
// scoring whole sets with set bonuses and racial hit (no talent build: the addon reads talents in game).
// Usage: node --experimental-strip-types --import tools/test/node-json-hook.mjs tools/test/planner_ref.ts
import { readFileSync } from "node:fs";
import {
  CLASSES, SPECS, PAPERDOLL, HIT_RATING, DW_MISS, RACE_HIT, hitCaps, hitRating,
  weightsFor, canUse, fits, score, canDualWield,
} from "../../site/src/scripts/gear/model.ts";
import type { Item, Stats, DollSlot } from "../../site/src/scripts/gear/model.ts";

const data = JSON.parse(readFileSync(new URL("../../gamedata/items.json", import.meta.url), "utf8"));
const items: Item[] = data.items;
const byId = new Map<number, Item>(items.map((i) => [i.id, i]));
const sets: Record<string, { bonuses: { n: number; stats: Stats }[] }> = data.sets || {};

function run(cls: string, spec: string, goal: "pve" | "pvp" | "level", level: number, side: "H" | "A", race: string) {
  const base = weightsFor(cls, spec, goal);
  let hitScale = 1;
  const slotWeights = (doll: DollSlot, it: Item): Stats => {
    const w = hitScale !== 1 && base.hit ? { ...base, hit: base.hit * hitScale } : base;
    if (!it.weapon) return w;
    const hunter = cls === "HUNTER";
    let k = 1;
    if (doll === "ranged") k = hunter ? 1 : 0.08;
    else if (hunter) k = 0.15;
    else if (doll === "offhand") k = Number.isFinite(w.dps_oh) && w.dps ? w.dps_oh / w.dps : 0.5;
    if (it.slot === "twohand" && !hunter) k *= 1.9;
    return k === 1 ? w : { ...w, dps: (w.dps || 0) * k };
  };
  const val = (doll: DollSlot, it: Item | undefined) => (it ? score(it, slotWeights(doll, it)) : 0);
  const candidates = (doll: DollSlot) => items.filter((it) => it.q >= 1 && (it.lvl ?? it.req) <= level && (!it.side || it.side === side)
    && canUse(it, cls, level) && fits(doll, it, cls));
  type Plan = Partial<Record<DollSlot, number>>;
  const specObj = SPECS[cls].find((s) => s.key === spec);
  const hitCtx = () => {
    if (!specObj || specObj.role === "healer") return null;
    const kind = specObj.role === "caster" ? "spell" : "phys";
    const cap = hitCaps(goal)[kind];
    const r = Object.prototype.hasOwnProperty.call(RACE_HIT, race) ? RACE_HIT[race] : 0;
    return { kind: kind as "phys" | "spell", cap, race: r, need: Math.max(0, cap - r) };
  };
  const dualWields = (o: Plan) => cls !== "HUNTER" && !!(o.offhand && byId.get(o.offhand)?.weapon);
  const hitOverflow = (o: Plan, t: Stats) => {
    const h = hitCtx(), w = base.hit || 0;
    if (!h || w <= 0) return 0;
    const over = Math.max(0, hitRating(t, h.kind) - h.need * HIT_RATING);
    const lost = h.kind === "phys" && dualWields(o) ? over - 0.5 * Math.min(over, DW_MISS * HIT_RATING) : over;
    return lost * w;
  };
  const totals = (o: Plan) => {
    const t: Stats = {}; let v = 0;
    for (const d of PAPERDOLL) {
      const it = o[d] ? byId.get(o[d]!) : undefined;
      if (!it) continue;
      v += val(d, it);
      for (const [k, n] of Object.entries(it.stats)) if (k !== "dps") t[k] = (t[k] || 0) + n;
    }
    const count: Record<string, number> = {};
    for (const d of PAPERDOLL) { const it = o[d] ? byId.get(o[d]!) : undefined; if (it?.set) count[it.set] = (count[it.set] || 0) + 1; }
    for (const [sid, n] of Object.entries(count)) for (const b of sets[sid]?.bonuses || []) if (n >= b.n) for (const [k, x] of Object.entries(b.stats)) t[k] = (t[k] || 0) + x;
    return { t, v: Math.round(v - hitOverflow(o, t)) };
  };
  const suggestOnce = (): Plan => {
    const plan: Plan = {};
    const best = (doll: DollSlot, exclude: number[] = []) => {
      let top: Item | undefined, topV = 0;
      for (const it of candidates(doll)) {
        if (exclude.includes(it.id)) continue;
        const v = val(doll, it);
        if (v > topV) { top = it; topV = v; }
      }
      return top;
    };
    for (const d of PAPERDOLL) {
      if (["finger2", "trinket2", "mainhand", "offhand"].includes(d)) continue;
      const it = best(d); if (it) plan[d] = it.id;
    }
    const r2 = best("finger2", plan.finger1 ? [plan.finger1] : []); if (r2) plan.finger2 = r2.id;
    const t2 = best("trinket2", plan.trinket1 ? [plan.trinket1] : []); if (t2) plan.trinket2 = t2.id;
    const mains = candidates("mainhand");
    const twoH = mains.filter((i) => i.slot === "twohand").sort((a, b) => val("mainhand", b) - val("mainhand", a))[0];
    const oneH = mains.filter((i) => i.slot !== "twohand").sort((a, b) => val("mainhand", b) - val("mainhand", a))[0];
    const offs = candidates("offhand").filter((i) => !oneH || i.id !== oneH.id || canDualWield(cls));
    const off = offs.filter((i) => !oneH || i.id !== oneH.id).sort((a, b) => val("offhand", b) - val("offhand", a))[0];
    if (twoH && val("mainhand", twoH) >= val("mainhand", oneH) + val("offhand", off)) plan.mainhand = twoH.id;
    else { if (oneH) plan.mainhand = oneH.id; if (off) plan.offhand = off.id; }
    return plan;
  };
  if (!hitCtx() || !base.hit) return suggestOnce();
  let bestPlan: Plan = {}, bestV = -Infinity;
  for (const m of [1, 0.8, 0.6, 0.45, 0.3, 0.15, 0]) {
    hitScale = m;
    const p = suggestOnce();
    hitScale = 1;
    const v = totals(p).v;
    if (v > bestV) { bestPlan = p; bestV = v; }
  }
  return bestPlan;
}

const out: Record<string, unknown> = {};
for (const cls of Object.keys(CLASSES)) for (const s of SPECS[cls]) for (const goal of ["pve", "pvp", "level"] as const)
  for (const level of [5, 12, 20, 29, 39, 40, 49, 60]) for (const [side, race] of [["H", "orc"], ["A", "dwarf"]] as const)
    out[`${cls}|${s.key}|${goal}|${level}|${side}|${race}`] = run(cls, s.key, goal, level, side, race);
process.stdout.write(JSON.stringify(out));

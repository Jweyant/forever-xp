// Reference BIS picks from the site's planner logic, for tools/test/test_planner.py.
// Usage: node --experimental-strip-types tools/test/planner_ref.ts > /tmp/ref.json
import { readFileSync } from "node:fs";
import { CLASSES, SPECS, PAPERDOLL, weightsFor, canUse, fits, score, sourceKind, canDualWield } from "../../site/src/scripts/gear/model.ts";
import type { Item, Stats, DollSlot } from "../../site/src/scripts/gear/model.ts";

const data = JSON.parse(readFileSync(new URL("../../gamedata/items.json", import.meta.url), "utf8"));
const items: Item[] = data.items;

function run(cls: string, spec: string, goal: "pve" | "pvp" | "level", level: number, side: "H" | "A") {
  const w = weightsFor(cls, spec, goal);
  const slotWeights = (doll: DollSlot, it: Item): Stats => {
    if (!it.weapon) return w;
    const hunter = cls === "HUNTER";
    let k = 1;
    if (doll === "ranged") k = hunter ? 1 : 0.08;
    else if (hunter) k = 0.15;
    else if (doll === "offhand") k = 0.5;
    if (it.slot === "twohand" && !hunter) k *= 1.9;
    return k === 1 ? w : { ...w, dps: (w.dps || 0) * k };
  };
  const val = (doll: DollSlot, it: Item | undefined) => (it ? score(it, slotWeights(doll, it)) : 0);
  const candidates = (doll: DollSlot) => items.filter((it) => it.q >= 1 && (it.lvl ?? it.req) <= level && (!it.side || it.side === side)
    && canUse(it, cls, level) && fits(doll, it, cls));
  const plan: Partial<Record<DollSlot, number>> = {};
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
}

const out: Record<string, unknown> = {};
for (const cls of Object.keys(CLASSES)) for (const s of SPECS[cls]) for (const goal of ["pve", "pvp", "level"] as const)
  for (const level of [5, 12, 20, 29, 39, 40, 49, 60]) for (const side of ["H", "A"] as const)
    out[`${cls}|${s.key}|${goal}|${level}|${side}`] = run(cls, s.key, goal, level, side);
process.stdout.write(JSON.stringify(out));

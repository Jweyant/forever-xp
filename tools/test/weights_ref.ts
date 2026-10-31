// Reference stat weights from the site's model.ts, for tools/test/test_addon_data.py.
// Usage (after `npm run data` in site/): node --experimental-strip-types tools/test/weights_ref.ts
import { CLASSES, SPECS, weightsFor } from "../../site/src/scripts/gear/model.ts";

const out: Record<string, unknown> = {};
for (const cls of Object.keys(CLASSES)) for (const s of SPECS[cls]) for (const goal of ["pve", "pvp", "level"] as const)
  out[`${cls}|${s.key}|${goal}`] = weightsFor(cls, s.key, goal);
process.stdout.write(JSON.stringify(out));

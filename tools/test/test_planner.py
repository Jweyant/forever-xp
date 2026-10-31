"""Check that the addon's Lua planner picks the same items as the site's planner.

Runs tools/test/planner_ref.ts (the site's model.ts under Node) and addon/ForeverScout/Planner.lua
(under Lua 5.1 via lupa) for every class, spec, goal, level and faction, and compares the plans.

  pip install lupa
  python3 tools/test/test_planner.py
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
ADDON = ROOT / "addon" / "ForeverScout"
DATA = ROOT / "addon" / "ForeverScout_Data"


def reference():
    out = subprocess.run(["node", "--experimental-strip-types", "--no-warnings", str(ROOT / "tools/test/planner_ref.ts")],
                         check=True, capture_output=True, text=True, cwd=ROOT)
    return json.loads(out.stdout)


def lua_runtime():
    from lupa import lua51
    L = lua51.LuaRuntime()
    boot = L.eval("""function(data, planner)
      local ns = {}
      assert(loadstring(data, "Data.lua"))("ForeverScout_Data", {})
      assert(loadstring(planner, "Planner.lua"))("ForeverScout", ns)
      assert(ns.Planner.LoadData())
      return function(cls, spec, goal, level, side)
        local plan = ns.Planner.Suggest({ cls = cls, spec = spec, goal = goal, level = level, side = side })
        local out = {}
        for k, v in pairs(plan) do out[#out + 1] = k .. "=" .. v end
        table.sort(out)
        return table.concat(out, ",")
      end
    end""")
    return boot((DATA / "Data.lua").read_text(), (ADDON / "Planner.lua").read_text())


def main():
    ref = reference()
    run = lua_runtime()
    bad = 0
    for key, plan in ref.items():
        cls, spec, goal, level, side = key.split("|")
        want = ",".join(sorted(f"{k}={v}" for k, v in plan.items()))
        got = run(cls, spec, goal, int(level), side)
        if got != want:
            bad += 1
            if bad <= 10:
                w, g = dict(x.split("=") for x in want.split(",") if x), dict(x.split("=") for x in got.split(",") if x)
                diff = {k: (w.get(k), g.get(k)) for k in set(w) | set(g) if w.get(k) != g.get(k)}
                print(f"MISMATCH {key}: site→addon {diff}")
    print(f"{len(ref) - bad}/{len(ref)} plans identical")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

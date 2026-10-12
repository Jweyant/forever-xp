"""Print each 'complete' step's hand-written text next to where the data says the objectives are,
with compass direction and distance from the previous stop, so wrong directions stand out."""
import math, sys, yaml, statistics
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from guidegen import Data, Generator

def compass(dx, dy):
    # map y grows southward
    ang = (math.degrees(math.atan2(dx, -dy)) + 360) % 360
    return ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"][int((ang + 22.5) // 45) % 8]

d = Data()
carry = None
for route in sys.argv[1:]:
    spec = yaml.safe_load(Path(route).read_text())
    g = Generator(d, spec)
    if carry and not spec["guide"].get("start_level"):
        g.s = carry
    g.lines = []
    if spec["guide"].get("start"):
        s = spec["guide"]["start"]; g.s.pos = (int(s[0]), float(s[1]), float(s[2]))
    print(f"\n##### {spec['guide']['name']}")
    for i, st in enumerate(spec["steps"], 1):
        g.step_no = i
        before = g.s.pos
        if "complete" in st and st.get("text"):
            ids = st["complete"] if isinstance(st["complete"], list) else [st["complete"]]
            print(f"\n[{i}] TEXT: {st['text']}")
            for qid in ids:
                for kind, oid, name, pts, count, lvl in g.objective_points(qid):
                    w = g.nearest(pts)
                    if not w or not before:
                        print(f"     {qid} {name}: no location"); continue
                    a, b = g.world(before), g.world(w)
                    dist = g.distance(before, w)
                    dirn = compass(b[2] - a[2], -(b[1] - a[1])) if a and b else "?"
                    # world: x north, y west -> east = -dy, north = dx
                    dirn = compass(-(b[2] - a[2]), -(b[1] - a[1])) if a and b else "?"
                    print(f"     {qid} {name} L{lvl}: map {w[0]} ({w[1]},{w[2]}) {int(dist)}yd {dirn} of previous stop")
        g.emit_step(st)
    carry = g.s

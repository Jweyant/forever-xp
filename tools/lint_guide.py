"""Check generated guides use only RXP commands we know, with numeric quest IDs."""
import re, sys
KNOWN = {"goto", "accept", "turnin", "complete", "target", "mob", "home", "hs", "fly", "fp",
         "trainer", "tame", "xp", "vendor", "train"}
bad = 0
for path in sys.argv[1:]:
    text = open(path).read()
    body = re.search(r"RegisterGuide\(\[=*\[\n(.*)\]=*\]\)", text, re.S).group(1)
    for n, line in enumerate(body.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith(("#", "<<", ">>")) or line == "step" or line.startswith("step <<"):
            continue
        m = re.match(r"^\.(\w+)\s*(.*?)(?:\s*>>.*)?$", line)
        if not m or m.group(1) not in KNOWN:
            print(f"{path}:{n}: unknown line: {line}"); bad += 1; continue
        cmd, args = m.groups()
        parts = [a.strip() for a in args.split(",")] if args else []
        if cmd in ("accept", "turnin") and not (parts and parts[0].isdigit()):
            print(f"{path}:{n}: bad quest id: {line}"); bad += 1
        if cmd == "complete" and not (len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit()):
            print(f"{path}:{n}: bad complete: {line}"); bad += 1
        if cmd == "goto" and not (len(parts) >= 3 and all(re.fullmatch(r"-?\d+(\.\d+)?", p) for p in parts[:3])):
            print(f"{path}:{n}: bad goto: {line}"); bad += 1
print("lint:", "ok" if not bad else f"{bad} problems")
sys.exit(1 if bad else 0)

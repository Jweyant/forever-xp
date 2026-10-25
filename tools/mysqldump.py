"""Tiny reader for MySQL dump files: yields rows of chosen tables as dicts, no database needed."""
import re

_CREATE = re.compile(r"^CREATE TABLE `(\w+)` \(")
_COL = re.compile(r"^\s*`(\w+)`\s")
_INSERT = re.compile(r"^INSERT INTO `(\w+)`(?: \(([^)]*)\))? VALUES ")


def _values(s, i):
    """Parse '(a,'b',NULL),(...)' starting at s[i]; yield tuples."""
    n = len(s)
    while i < n:
        while i < n and s[i] in " ,\n\r\t":
            i += 1
        if i >= n or s[i] != "(":
            return
        i += 1
        row, cur, inq = [], [], False
        while i < n:
            c = s[i]
            if inq:
                if c == "\\":
                    nxt = s[i + 1]
                    cur.append({"n": "\n", "r": "\r", "t": "\t", "0": "\0"}.get(nxt, nxt))
                    i += 2
                    continue
                if c == "'":
                    if i + 1 < n and s[i + 1] == "'":
                        cur.append("'")
                        i += 2
                        continue
                    inq = False
                    i += 1
                    continue
                cur.append(c)
                i += 1
                continue
            if c == "'":
                inq = True
                cur.append("\x01")  # marks "was a string"
                i += 1
            elif c == ",":
                row.append("".join(cur))
                cur = []
                i += 1
            elif c == ")":
                row.append("".join(cur))
                i += 1
                yield [_cast(v) for v in row]
                break
            else:
                cur.append(c)
                i += 1


def _cast(v):
    if v.startswith("\x01"):
        return v[1:]
    v = v.strip()
    if v == "NULL":
        return None
    try:
        return int(v)
    except ValueError:
        try:
            return float(v)
        except ValueError:
            return v


def read(path, tables):
    """{table: [row dicts]} for the requested tables."""
    want = set(tables)
    cols, out = {}, {t: [] for t in tables}
    current = None
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = _CREATE.match(line)
            if m:
                current = m.group(1) if m.group(1) in want else None
                if current:
                    cols[current] = []
                continue
            if current and line.startswith(")"):
                current = None
                continue
            if current:
                c = _COL.match(line)
                if c:
                    cols[current].append(c.group(1))
                continue
            m = _INSERT.match(line)
            if m and m.group(1) in want:
                t = m.group(1)
                names = [x.strip(" `") for x in m.group(2).split(",")] if m.group(2) else cols[t]
                for row in _values(line, m.end()):
                    out[t].append(dict(zip(names, row)))
    return out

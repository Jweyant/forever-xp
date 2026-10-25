"""Read Lua data files (SavedVariables, ForeverScout exports) without running any Lua.

Only literal data is accepted: tables, strings, numbers, true/false/nil, and top-level
`Name = <value>` assignments. Anything else (function calls, operators, code) is rejected, so a
crafted upload can't execute code, loop forever or exhaust memory while being read.
"""
import re

MAX_DEPTH = 64
MAX_ITEMS = 5_000_000

_TOKEN = re.compile(r"""
    (?P<ws>\s+|--\[(?P<eq>=*)\[.*?\](?P=eq)\]|--[^\n]*)
  | (?P<str>"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'|\[(?P<leq>=*)\[.*?\](?P=leq)\])
  | (?P<num>-?(?:0[xX][0-9a-fA-F]+|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?))
  | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<op>[{}\[\]=,;])
""", re.S | re.X)

_ESC = {"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b", "f": "\f", "v": "\v", "\\": "\\",
        '"': '"', "'": "'", "\n": "\n"}


class LuaDataError(ValueError):
    pass


def _unquote(s):
    if s.startswith("["):
        body = s[s.index("[", 1) + 1: s.rindex("]", 0, -1)]
        return body[1:] if body.startswith("\n") else body
    out, i, body = [], 0, s[1:-1]
    while i < len(body):
        c = body[i]
        if c != "\\":
            out.append(c)
            i += 1
            continue
        n = body[i + 1] if i + 1 < len(body) else ""
        if n.isdigit():
            j = i + 1
            while j < len(body) and j < i + 4 and body[j].isdigit():
                j += 1
            out.append(chr(int(body[i + 1:j]) % 256))
            i = j
        elif n == "x":
            out.append(chr(int(body[i + 2:i + 4], 16)))
            i += 4
        else:
            out.append(_ESC.get(n, n))
            i += 2
    return "".join(out)


def _tokens(text):
    pos, n = 0, len(text)
    while pos < n:
        m = _TOKEN.match(text, pos)
        if not m:
            raise LuaDataError(f"unexpected character at {pos}: {text[pos:pos + 20]!r}")
        pos = m.end()
        if m.lastgroup == "ws":
            continue
        kind = m.lastgroup if m.lastgroup in ("str", "num", "name", "op") else ("str" if m.group("str") else "op")
        yield kind, m.group(kind if kind in ("str", "num", "name", "op") else 0)


class _Parser:
    def __init__(self, text):
        self.toks = list(_tokens(text))
        self.i = 0
        self.items = 0

    def peek(self, k=0):
        return self.toks[self.i + k] if self.i + k < len(self.toks) else (None, None)

    def take(self, value=None):
        tok = self.peek()
        if tok[0] is None or (value is not None and tok[1] != value):
            raise LuaDataError(f"expected {value!r}, got {tok[1]!r}")
        self.i += 1
        return tok

    def value(self, depth=0):
        if depth > MAX_DEPTH:
            raise LuaDataError("tables nested too deeply")
        kind, v = self.peek()
        if kind == "op" and v == "{":
            return self.table(depth + 1)
        self.i += 1
        if kind == "str":
            return _unquote(v)
        if kind == "num":
            return int(v, 16) if v.lower().lstrip("-").startswith("0x") else (float(v) if re.search(r"[.eE]", v) else int(v))
        if kind == "name" and v in ("true", "false", "nil"):
            return {"true": True, "false": False, "nil": None}[v]
        raise LuaDataError(f"not a data value: {v!r}")

    def table(self, depth):
        self.take("{")
        out, n = {}, 1
        while self.peek()[1] != "}":
            self.items += 1
            if self.items > MAX_ITEMS:
                raise LuaDataError("too many values")
            kind, v = self.peek()
            if kind == "op" and v == "[":
                self.take("[")
                key = self.value(depth)
                self.take("]")
                self.take("=")
                out[key] = self.value(depth)
            elif kind == "name" and self.peek(1)[1] == "=":
                self.i += 2
                out[v] = self.value(depth)
            else:
                out[n] = self.value(depth)
                n += 1
            if self.peek()[1] in (",", ";"):
                self.i += 1
        self.take("}")
        if out and all(isinstance(k, int) for k in out) and sorted(out) == list(range(1, len(out) + 1)):
            return [out[k] for k in range(1, len(out) + 1)]
        return out


def loads_value(text):
    """Parse a single Lua value, e.g. the payload of an export string."""
    p = _Parser(text)
    v = p.value()
    if p.i != len(p.toks):
        raise LuaDataError("trailing content after value")
    return v


def loads_assignments(text):
    """Parse a SavedVariables file: `Name = value` statements. Returns {Name: value}."""
    p = _Parser(text)
    out = {}
    while p.i < len(p.toks):
        kind, name = p.take()
        if kind != "name":
            raise LuaDataError(f"expected a variable name, got {name!r}")
        p.take("=")
        out[name] = p.value()
        if p.peek()[1] == ";":
            p.i += 1
    return out

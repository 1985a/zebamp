"""MAKI bytecode loader and interpreter (Winamp 3/5 skin scripts).

The binary layout and opcode semantics follow the format documented by the
Webamp project (MIT).  Objects exposed to scripts implement `maki_call()`.
Errors inside a script abort only the current event handler, never the app.
"""
from __future__ import annotations

import json
import logging
import os
import struct

log = logging.getLogger(__name__)

_OBJ_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "maki", "objects.json")
with open(_OBJ_PATH, encoding="utf-8") as _fh:
    CLASSES: dict = json.load(_fh)
_BY_NAME = {c["name"]: g for g, c in CLASSES.items()}


def format_guid(raw_hex: str) -> str:
    """MAKI stores GUIDs as 4 LE uint32; convert to objects.json key form."""
    import re
    m = re.match(r"(........)(....)(....)(..)(..)(..)(..)(..)(..)(..)(..)", raw_hex)
    if not m:
        return raw_hex.lower()
    g = m.groups()
    return (g[0] + g[2] + g[1] + g[6] + g[5] + g[4] + g[3] + g[10] + g[9] + g[8] + g[7]).lower()


def class_name(guid: str) -> str:
    c = CLASSES.get(guid)
    return c["name"] if c else "?"


def find_method(guid: str, name: str):
    """(arity, result type) searching the class and its parents."""
    seen = 0
    g = guid
    while g and seen < 16:
        c = CLASSES.get(g)
        if c is None:
            break
        for f in c["functions"]:
            if f["name"] == name:
                return f["params"], f["result"]
        parent = c.get("parent", "")
        g = _BY_NAME.get(parent)
        seen += 1
    return None


def is_subclass(guid: str, base_name: str) -> bool:
    g = guid
    for _ in range(16):
        c = CLASSES.get(g)
        if c is None:
            return False
        if c["name"] == base_name:
            return True
        g = _BY_NAME.get(c.get("parent", ""))
        if g is None:
            return False
    return False


class Var:
    __slots__ = ("guid", "is_class", "is_global", "members", "type", "value")

    def __init__(self, type_, value=None, guid=None, is_global=False):
        self.type = type_
        self.value = value
        self.guid = guid
        self.is_class = False
        self.members: list[int] = []
        self.is_global = is_global

    def __repr__(self):
        return f"Var({self.type}, {self.value!r})"


PRIMS = {5: "BOOLEAN", 2: "INT", 3: "FLOAT", 4: "DOUBLE", 6: "STRING"}
ARG_TYPES = {16: "line", 17: "line", 18: "line", 25: "line", 1: "var", 3: "var",
             24: "var", 112: "var", 96: "var", 104: "count"}
NOARG = {2, 8, 9, 10, 11, 12, 13, 33, 40, 48, 56, 57, 58, 59, 64, 65, 66, 67, 68,
         72, 73, 74, 76, 80, 81, 88, 89, 90, 91, 97}


class MakiError(Exception):
    pass


class Reader:
    def __init__(self, data: bytes):
        self.d = data
        self.p = 0

    def u8(self):
        v = self.d[self.p]
        self.p += 1
        return v

    def u16(self):
        v = struct.unpack_from("<H", self.d, self.p)[0]
        self.p += 2
        return v

    def u32(self):
        v = struct.unpack_from("<I", self.d, self.p)[0]
        self.p += 4
        return v

    def i32(self):
        v = struct.unpack_from("<i", self.d, self.p)[0]
        self.p += 4
        return v

    def peek32(self):
        if self.p + 4 > len(self.d):
            return 0
        return struct.unpack_from("<I", self.d, self.p)[0]

    def string(self):
        n = self.u16()
        s = self.d[self.p:self.p + n]
        self.p += n
        return s.decode("latin-1")


class Program:
    def __init__(self, data: bytes, script_id=""):
        self.id = script_id
        r = Reader(data)
        if data[:2] != b"FG":
            raise MakiError("not a MAKI file")
        r.p = 2
        self.version = r.u16()
        r.u32()  # extra version
        # classes
        self.classes = []
        for _ in range(r.u32()):
            raw = "".join(f"{r.u32():08x}" for _ in range(4))
            self.classes.append(format_guid(raw))
        # methods
        self.methods = []
        for _ in range(r.u32()):
            code = r.u16()
            r.u16()
            name = r.string().lower()
            self.methods.append((name, code & 0xFF))
        # variables
        self.vars: list[Var] = []
        for _ in range(r.u32()):
            type_off = r.u8()
            is_obj = r.u8()
            sub = r.u16()
            u1 = r.u16()
            u2 = r.u16()
            r.u16()
            r.u16()
            glob = r.u8()
            r.u8()
            if sub:
                base = self.vars[type_off] if type_off < len(self.vars) else None
                v = Var("OBJECT", None, base.guid if base else None, bool(glob))
                if base is not None:
                    base.is_class = True
                    base.members.append(len(self.vars))
                self.vars.append(v)
            elif is_obj:
                guid = self.classes[type_off] if type_off < len(self.classes) else None
                self.vars.append(Var("OBJECT", None, guid, bool(glob)))
            else:
                t = PRIMS.get(type_off, "INT")
                if t in ("INT", "BOOLEAN"):
                    val = u1  # unsigned, as Winamp does
                elif t in ("FLOAT", "DOUBLE"):
                    exp = (u2 & 0xFF80) >> 7
                    mant = ((0x80 | (u2 & 0x7F)) << 16) | u1
                    val = mant * 2.0 ** (exp - 0x96) if (u1 or u2) else 0.0
                else:
                    val = ""
                self.vars.append(Var(t, val, None, bool(glob)))
        # constants (string initialisers)
        for _ in range(r.u32()):
            i = r.u32()
            s = r.string()
            if i < len(self.vars):
                self.vars[i].value = s
        # bindings
        raw_bind = []
        for _ in range(r.u32()):
            raw_bind.append((r.u32(), r.u32(), r.u32()))
        # code
        length = r.u32()
        start = r.p
        cmds = []
        offset_to_index = {}
        while r.p < start + length:
            pos = r.p - start
            op = r.u8()
            arg = None
            kind = ARG_TYPES.get(op)
            if kind == "line":
                arg = r.i32() + 5 + pos
            elif kind in ("var", "count"):
                arg = r.u32()
            elif op not in NOARG:
                raise MakiError(f"unknown opcode {op} at {pos}")
            if kind is not None and length > pos + 5 + 4:
                pk = r.peek32()
                if 0xFFFF0000 <= pk <= 0xFFFF000F:
                    r.u32()
            if op == 112:
                r.u8()
            offset_to_index[pos] = len(cmds)
            cmds.append([op, arg, kind])
        for c in cmds:
            if c[2] == "line":
                c[1] = offset_to_index.get(c[1], len(cmds))
        self.commands = [(c[0], c[1]) for c in cmds]
        self.bindings = []
        for var_i, meth_i, bin_off in raw_bind:
            idx = offset_to_index.get(bin_off)
            if idx is not None and meth_i < len(self.methods):
                self.bindings.append((var_i, self.methods[meth_i][0], idx))
        # event index: method name -> [(var index, command index)]
        self.events: dict[str, list] = {}
        for var_i, name, idx in self.bindings:
            self.events.setdefault(name, []).append((var_i, idx))


NULL = Var("NULL", None)


def _num(v):
    x = v.value
    if x is None:
        return 0
    if isinstance(x, bool):
        return int(x)
    if isinstance(x, str):
        try:
            return float(x) if "." in x else int(x)
        except ValueError:
            return 0
    return x


def _coerce(t, value):
    try:
        if t == "INT":
            if isinstance(value, str):
                return int(float(value or 0))
            return int(value) if isinstance(value, (int, float, bool)) else 0
        if t == "BOOLEAN":
            return 1 if value else 0
        if t in ("FLOAT", "DOUBLE"):
            if isinstance(value, str):
                return float(value or 0)
            return float(value) if value is not None else 0.0
        if t == "STRING":
            if value is None:
                return ""
            if isinstance(value, float):
                return f"{value:g}"
            return str(value)
    except (TypeError, ValueError):
        return 0 if t != "STRING" else ""
    return value


def _rtype(result: str) -> str:
    u = (result or "").upper()
    if u in ("INT", "FLOAT", "DOUBLE", "STRING", "BOOLEAN", "ANY"):
        return u
    if u == "":
        return "NULL"
    return "OBJECT"


TRACE = os.environ.get("ZEBAMP_MAKI_TRACE", "")


class VM:
    OP_BUDGET = 400_000

    def __init__(self, engine):
        self.engine = engine
        self.programs: list[Program] = []
        self.depth = 0

    def add(self, prog: Program):
        self.programs.append(prog)

    def remove(self, prog: Program):
        if prog in self.programs:
            self.programs.remove(prog)

    def dispatch(self, obj, event: str, args: list | None = None) -> int:
        """Fire `event` on `obj` for every script that binds it."""
        if self.depth > 24:
            return 0
        n = 0
        for prog in list(self.programs):
            hooks = prog.events.get(event)
            if not hooks:
                continue
            for var_i, cmd_i in hooks:
                if var_i >= len(prog.vars):
                    continue
                v = prog.vars[var_i]
                match = False
                if v.is_class:
                    for m in v.members:
                        if prog.vars[m].value is obj:
                            v.value = obj
                            match = True
                            break
                elif v.type == "OBJECT" and v.value is obj and obj is not None:
                    match = True
                if match:
                    stack = [Var(t, val) for t, val in reversed(args or [])]
                    self.run(prog, cmd_i, stack, event)
                    n += 1
        return n

    def run(self, prog: Program, ip: int, stack: list, event=""):
        self.depth += 1
        try:
            self._run(prog, ip, stack)
        except Exception as e:
            log.info("MAKI %s/%s stopped: %s", os.path.basename(prog.id), event, e)
        finally:
            self.depth -= 1

    def _run(self, prog: Program, ip: int, stack: list):
        cmds = prog.commands
        vars_ = prog.vars
        calls: list[int] = []
        budget = self.OP_BUDGET
        n = len(cmds)
        push = stack.append
        pop = stack.pop
        while 0 <= ip < n:
            budget -= 1
            if budget <= 0:
                raise MakiError("instruction budget exceeded")
            op, arg = cmds[ip]
            if op == 1:
                push(vars_[arg])
            elif op == 2:
                if stack:
                    pop()
            elif op == 3:
                a = pop()
                dst = vars_[arg]
                dst.value = _coerce(dst.type, a.value) if dst.type != "OBJECT" else a.value
            elif 8 <= op <= 13:
                a = pop()
                b = pop()
                av, bv = a.value, b.value
                if op == 8:
                    r = (av.lower() == bv.lower()) if isinstance(av, str) and isinstance(bv, str) else _eq(bv, av)
                elif op == 9:
                    r = (av.lower() != bv.lower()) if isinstance(av, str) and isinstance(bv, str) else not _eq(bv, av)
                else:
                    x, y = _num(b), _num(a)
                    r = {10: x > y, 11: x >= y, 12: x < y, 13: x <= y}[op]
                push(Var("INT", 1 if r else 0))
            elif op == 16:
                if pop().value:
                    pass
                else:
                    ip = arg
                    continue
            elif op == 17:
                if pop().value:
                    ip = arg
                    continue
            elif op == 18:
                ip = arg
                continue
            elif op in (24, 112):
                name, cls_i = prog.methods[arg]
                guid = prog.classes[cls_i] if cls_i < len(prog.classes) else None
                md = find_method(guid, name) if guid else None
                argc, rtype = (md[0], _rtype(md[1])) if md else (0, "ANY")
                margs = [pop().value for _ in range(argc)]
                target = pop() if stack else NULL
                obj = target.value
                result = None
                if obj is None:
                    log.debug("MAKI call %s on null", name)
                else:
                    fn = getattr(obj, "maki_call", None)
                    if fn is not None:
                        result = fn(name, margs)
                    elif TRACE:
                        log.warning("MAKI %s: %s on non-object %r", prog.id, name, obj)
                if TRACE and TRACE.lower() in prog.id.lower():
                    log.warning("MAKI %s: %s.%s(%s) -> %r", os.path.basename(prog.id),
                                getattr(obj, "cls", type(obj).__name__), name,
                                ", ".join(repr(a)[:40] for a in margs), result if not hasattr(result, "maki_call") else
                                f"<{getattr(result, 'cls', '?')} {getattr(result, 'id', '')}>")
                if rtype == "BOOLEAN":
                    push(Var("BOOLEAN", 1 if result else 0))
                elif rtype == "INT":
                    push(Var("INT", _coerce("INT", result)))
                elif rtype in ("FLOAT", "DOUBLE"):
                    push(Var(rtype, _coerce("FLOAT", result)))
                elif rtype == "STRING":
                    push(Var("STRING", _coerce("STRING", result)))
                elif rtype == "NULL":
                    push(NULL)
                else:
                    push(Var("OBJECT" if rtype == "OBJECT" else "ANY", result))
            elif op == 25:
                calls.append(ip)
                ip = arg
                continue
            elif op == 33:
                if not calls:
                    return
                ip = calls.pop()
            elif op == 40:
                pass
            elif op == 48:
                a = pop()
                b = pop()
                if b is not None and b is not NULL:
                    b.value = _coerce(b.type, a.value) if b.type not in ("OBJECT", "ANY", "NULL") else a.value
                push(a)
            elif op in (56, 57):
                a = pop()
                old = a.value or 0
                a.value = old + (1 if op == 56 else -1)
                push(Var(a.type, old))
            elif op in (58, 59):
                a = pop()
                a.value = (a.value or 0) + (1 if op == 58 else -1)
                push(a)
            elif op == 64:
                a = pop()
                b = pop()
                if isinstance(a.value, str) or isinstance(b.value, str):
                    push(Var("STRING", _coerce("STRING", b.value) + _coerce("STRING", a.value)))
                else:
                    push(Var(_arith_type(a, b), _num(b) + _num(a)))
            elif op == 65:
                a = pop()
                b = pop()
                push(Var(_arith_type(a, b), _num(b) - _num(a)))
            elif op == 66:
                a = pop()
                b = pop()
                push(Var(_arith_type(a, b), _num(b) * _num(a)))
            elif op == 67:
                a = pop()
                b = pop()
                y = _num(a)
                t = _arith_type(a, b)
                if y == 0:
                    push(Var(t, 0))
                else:
                    # Winamp (like Webamp) divides as real numbers even for two
                    # ints: skins rely on it (e.g. "v / 255 * 70" volume bars).
                    q = _num(b) / y
                    if t == "INT" and q == int(q):
                        push(Var("INT", int(q)))
                    else:
                        push(Var("FLOAT", q))
            elif op == 68:
                a = pop()
                b = pop()
                y = int(_num(a))
                push(Var("INT", int(_num(b)) % y if y else 0))
            elif op == 72:
                a = pop()
                b = pop()
                push(Var("INT", int(_num(b)) & int(_num(a))))
            elif op == 73:
                a = pop()
                b = pop()
                push(Var("INT", int(_num(b)) | int(_num(a))))
            elif op == 104:
                # Winamp 5.5+ opcode with a count: discard that many values
                for _ in range(min(int(arg or 0), len(stack))):
                    pop()
            elif op == 74:
                a = pop()
                push(Var("INT", 0 if a.value else 1))
            elif op == 76:
                a = pop()
                push(Var(a.type if a.type in ("FLOAT", "DOUBLE") else "INT", -_num(a)))
            elif op == 80:
                a = pop()
                b = pop()
                push(Var("INT", 1 if (b.value and a.value) else 0))
            elif op == 81:
                a = pop()
                b = pop()
                push(Var("INT", 1 if (b.value or a.value) else 0))
            elif op in (88, 90):
                a = pop()
                b = pop()
                push(Var("INT", int(_num(b)) << int(_num(a))))
            elif op in (89, 91):
                a = pop()
                b = pop()
                push(Var("INT", int(_num(b)) >> int(_num(a))))
            elif op == 96:
                guid = prog.classes[arg] if arg < len(prog.classes) else None
                obj = self.engine.maki_new(guid)
                push(Var("OBJECT", obj))
            elif op == 97:
                a = pop()
                if a.value is not None and hasattr(a.value, "maki_delete"):
                    a.value.maki_delete()
            else:
                raise MakiError(f"opcode {op}")
            ip += 1


def _eq(a, b):
    is_obj = hasattr(a, "maki_call") or hasattr(b, "maki_call")
    if is_obj:
        return a is b                       # GUI objects compare by identity
    if a is None or b is None:
        # MAKI treats NULL and 0 as equal
        return (a is None or a == 0) and (b is None or b == 0)
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return a == b


def _arith_type(a, b):
    if a.type in ("FLOAT", "DOUBLE") or b.type in ("FLOAT", "DOUBLE"):
        return "FLOAT"
    if isinstance(a.value, float) or isinstance(b.value, float):
        return "FLOAT"
    return "INT"

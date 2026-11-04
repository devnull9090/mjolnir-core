"""Minimal Halo CE cache-file scenario script dumper.

usage: python ce_hs.py <map> [--json]   (prints decompiled scripts + device info)
"""
import json
import struct
import sys

MEM = 0x40440000
TYPES = ["unparsed", "special_form", "function_name", "passthrough", "void", "boolean", "real",
         "short", "long", "string", "script", "trigger_volume", "cutscene_flag",
         "cutscene_camera_point", "cutscene_title", "cutscene_recording", "device_group", "ai",
         "ai_command_list", "starting_profile", "conversation", "navpoint", "hud_message",
         "object_list", "sound", "effect", "damage", "looping_sound", "animation_graph",
         "actor_variant", "damage_effect", "object_definition", "game_difficulty", "team",
         "ai_default_state", "actor_type", "hud_corner", "object", "unit", "vehicle", "weapon",
         "device", "scenery", "object_name", "unit_name", "vehicle_name", "weapon_name",
         "device_name", "scenery_name"]
SCRIPT_TYPES = ["startup", "dormant", "continuous", "static", "stub"]


class CeMap:
    def __init__(self, path):
        self.b = open(path, "rb").read()
        b = self.b
        if b[:4] not in (b"daeh", b"head"):
            raise ValueError("not an uncompressed CE map")
        self.index_off = struct.unpack_from("<I", b, 0x10)[0]
        hdr = self.index_off
        self.index_ptr, self.scnr_id, _, self.tag_count = struct.unpack_from("<IIII", b, hdr)
        self.magic = self.index_ptr - (hdr + 0x28)
        self.tags = {}
        base = self.off(self.index_ptr)
        for i in range(self.tag_count):
            c1, c2, c3, tid, nptr, dptr, idx, _ = struct.unpack_from("<4s4s4sIIIII", b, base + i * 32)
            try:
                name = self.cstr(self.off(nptr))
            except Exception:
                name = "?"
            self.tags[tid] = (c1[::-1].decode("latin-1"), name, dptr, idx)

    def off(self, ptr):
        return ptr - self.magic

    def cstr(self, o):
        e = self.b.index(b"\0", o)
        return self.b[o:e].decode("latin-1")

    def reflexive(self, base, field, size):
        n, ptr = struct.unpack_from("<II", self.b, base + field)
        if n == 0 or ptr == 0:
            return []
        o = self.off(ptr)
        return [o + i * size for i in range(n)]

    def rawdata(self, base, field):
        size, _, _, ptr = struct.unpack_from("<IIII", self.b, base + field)
        if size == 0:
            return b""
        o = self.off(ptr)
        return self.b[o:o + size]

    def tag_name(self, tid):
        t = self.tags.get(tid)
        return t[1] if t else None


def name32(b, o):
    return b[o:o + 32].split(b"\0")[0].decode("latin-1")


def load(path):
    m = CeMap(path)
    cls, sname, sptr, _ = m.tags[m.scnr_id]
    s = m.off(sptr)
    b = m.b
    out = {"scenario": sname}
    syntax = m.rawdata(s, 0x474)
    strings = m.rawdata(s, 0x488)
    scripts = [(name32(b, o), struct.unpack_from("<HHI", b, o + 32)) for o in m.reflexive(s, 0x49C, 92)]
    globs = [(name32(b, o), struct.unpack_from("<H", b, o + 32)[0], struct.unpack_from("<I", b, o + 40)[0])
             for o in m.reflexive(s, 0x4A8, 92)]
    out["object_names"] = [name32(b, o) for o in m.reflexive(s, 0x204, 36)]
    out["device_groups"] = [(name32(b, o), struct.unpack_from("<f", b, o + 32)[0]) for o in m.reflexive(s, 0x288, 52)]
    return m, s, syntax, strings, scripts, globs, out


def decompiler(syntax, strings):
    hdr = 56
    nsize = struct.unpack_from("<H", syntax, 34)[0] or 20
    count = (len(syntax) - hdr) // nsize
    nodes = [struct.unpack_from("<HHHHIII", syntax, hdr + i * nsize) for i in range(count)]
    sdata = strings.decode("latin-1")

    def s_at(o):
        e = sdata.find("\0", o)
        return sdata[o:e]

    calls = {}

    def node(h):
        if h == 0xFFFFFFFF:
            return None
        return nodes[h & 0xFFFF]

    def lit(n):
        salt, idx, typ, flags, nxt, so, data = n
        tname = TYPES[typ] if typ < len(TYPES) else str(typ)
        if flags & 4:  # global
            return s_at(so)
        if tname == "boolean":
            return "true" if data & 0xFF else "false"
        if tname == "real":
            return repr(round(struct.unpack("<f", struct.pack("<I", data))[0], 4))
        if tname in ("short",):
            return str(struct.unpack("<h", struct.pack("<H", data & 0xFFFF))[0])
        if tname == "long":
            return str(struct.unpack("<i", struct.pack("<I", data))[0])
        st = s_at(so)
        if tname == "string" or " " in st or "\\" in st:
            return '"%s"' % st
        return st if st else "none"

    def expr(h, depth=0):
        n = node(h)
        if n is None:
            return "?"
        salt, idx, typ, flags, nxt, so, data = n
        if flags & 1:
            return lit(n)
        # call: data = first child (function name primitive) / script call
        first = node(data)
        if flags & 2:
            fname = s_at(first[5]) if first else "?"
            args_h = first[4] if first else 0xFFFFFFFF
        else:
            fname = s_at(first[5]) if first else "?"
            args_h = first[4] if first else 0xFFFFFFFF
        calls[fname] = calls.get(fname, 0) + 1
        args = []
        a = args_h
        while a != 0xFFFFFFFF:
            args.append(expr(a, depth + 1))
            a = node(a)[4]
        flat = "(" + " ".join([fname] + args) + ")"
        if len(flat) < 90 and "\n" not in flat:
            return flat
        pad = "\n" + "    " * (depth + 1)
        return "(" + fname + "".join(pad + x for x in args) + ")"

    return expr, calls


def main():
    path = sys.argv[1]
    m, s, syntax, strings, scripts, globs, out = load(path)
    if not syntax:
        print("; no scripts")
        return
    expr, calls = decompiler(syntax, strings)
    print("; scenario", out["scenario"])
    print("; object names:", " ".join(out["object_names"]))
    print("; device groups:", out["device_groups"])
    for name, t, init in globs:
        print("(global %s %s %s)" % (TYPES[t] if t < len(TYPES) else t, name, expr(init)))
    for name, (st, rt, root) in scripts:
        body = expr(root, 0)
        print("\n(script %s %s %s\n    %s)" % (SCRIPT_TYPES[st] if st < 5 else st,
                                              TYPES[rt] if rt < len(TYPES) else rt, name, body))
    print("\n; calls:", json.dumps(dict(sorted(calls.items(), key=lambda kv: -kv[1]))))


if __name__ == "__main__":
    main()

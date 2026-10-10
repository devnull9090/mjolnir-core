#!/usr/bin/env python3
"""Read a Halo CE map's scripts and devices out of its scenario tag.

A cache file keeps no script source. What the scenario carries is the
compiler's output: `script syntax data`, a datum array of 20-byte expression
nodes threaded into trees, and `script string data`, the text of every name
token the source had. Each script and global names its root node. That is
enough to write the source back out (`--hsc`), and to count which engine
functions and globals a map calls, which is what a conversion to this game's
script engine has to supply.

Layout (Custom Edition, cache version 609; checked on Hugeass and Coldsnap):

    scenario   0x204 object names (36 bytes), 0x288 device groups (52),
               0x294 machines (64), 0x2AC controls (64), 0x2C4 light
               fixtures (88), 0x360 trigger volumes (96), 0x378 netgame
               flags, 0x42C encounters, 0x438 command lists, 0x474 script
               syntax data and 0x488 script string data (20-byte data
               references: size, flags, file offset, address, id), 0x49C
               scripts (92), 0x4A8 globals (92), 0x4B4 references, 0x4E4
               cutscene flags, 0x4F0 cutscene camera points, 0x4FC titles
    syntax     a 0x38-byte datum array header ('script node', u16 maximum,
               u16 element size 20, 'd@t@' at 0x28), then the nodes
    node       u16 salt, u16 index (a call's function index, or a
               constant's own value type), u16 value type (what the
               context expects), u16 flags (1 primitive, 2 script call,
               4 global reference, 8 garbage collectable), u32 next node,
               u32 string offset (the token's text), u32 value (a
               constant's bits, or a call's first child)
    script     char[32] name, u16 script type, u16 return type, u32 root node
    global     char[32] name, u16 type, 6 bytes, u32 initial value node
    device     scenario object (type, name, flags, permutation, position,
               rotation, padding: 40 bytes), then u16 power group, u16
               position group (-1 for none), u32 device flags

A call is a node that is not primitive; its first child is the function's
name (value type 2) and the rest are its arguments. Special forms (begin,
if, set, and, cond, sleep_until, ...) are calls like any other.

    python tools/halomaps/cescript.py maps/hugeass.map           # survey, JSON
    python tools/halomaps/cescript.py --hsc maps/hugeass.map     # the scripts as source
    python tools/halomaps/cescript.py --names maps/hugeass.map   # the names scripts refer to

The names the scripts refer to, laid out as follows (checked on Hugeass):

    object name     char[32] name, u16 object type (0 biped, 1 vehicle,
                    2 weapon, 3 equipment, 4 garbage, 5 projectile, 6 scenery,
                    7 machine, 8 control, 9 light fixture, 10 placeholder,
                    11 sound scenery), u16 placement index in that block
    trigger volume  u32, char[32] name at 4, 3 reals parameters at 36, then
                    forward, up, position and extents (3 reals each)
    cutscene flag   u32, char[32] name at 4, position (3 reals) at 36,
                    facing (yaw, pitch) at 48
    device group    char[32] name, real initial value at 32, u32 flags at 36
"""

from __future__ import annotations

import argparse
import collections
import json
import struct
import sys

import cemap

SCNR = {
    "object names": (0x204, 36), "device groups": (0x288, 52), "machines": (0x294, 64),
    "controls": (0x2AC, 64), "light fixtures": (0x2C4, 88), "trigger volumes": (0x360, 96),
    "netgame flags": (0x378, 148), "encounters": (0x42C, 176), "command lists": (0x438, 96),
    "scripts": (0x49C, 92), "globals": (0x4A8, 92), "references": (0x4B4, 40),
    "cutscene flags": (0x4E4, 92), "cutscene camera points": (0x4F0, 104),
    "cutscene titles": (0x4FC, 96),
}
SYNTAX_DATA, STRING_DATA = 0x474, 0x488
SYNTAX_HEADER, NODE = 0x38, struct.Struct("<HHHHIII")
DEVICE_GROUPS_AT = 40  # power group, position group in a device placement
NONE = 0xFFFFFFFF

PRIMITIVE, SCRIPT_CALL, GLOBAL_REF = 1, 2, 4
SCRIPT_TYPES = ["startup", "dormant", "continuous", "static", "stub"]
# Halo CE's script value types, by number.
VALUE_TYPES = [
    "unparsed", "special_form", "function_name", "passthrough", "void", "boolean", "real",
    "short", "long", "string", "script", "trigger_volume", "cutscene_flag",
    "cutscene_camera_point", "cutscene_title", "cutscene_recording", "device_group", "ai",
    "ai_command_list", "starting_profile", "conversation", "navpoint", "hud_message",
    "object_list", "sound", "effect", "damage", "looping_sound", "animation_graph",
    "actor_variant", "damage_effect", "object_definition", "game_difficulty", "team",
    "ai_default_state", "actor_type", "hud_corner", "object", "unit", "vehicle", "weapon",
    "device", "scenery", "object_name", "unit_name", "vehicle_name", "weapon_name",
    "device_name", "scenery_name",
]
FUNCTION_NAME, BOOLEAN, REAL, SHORT, LONG = 2, 5, 6, 7, 8
VEHICLE_TYPE_AT = 0x2F4  # u16 in a vehi tag's data
VEHICLE_TYPES = ["human_tank", "human_jeep", "human_boat", "human_plane", "alien_scout",
                 "alien_fighter", "turret"]


def ident(name: str) -> str:
    """A script or global name as source can spell it. Protection tools
    rename scripts with spaces in them (Yoyorast Island V2's
    "is_server check"); the calls name them the same way, so both sides
    come out the same."""
    return "_".join(name.split()) or "_"


def value_type(n: int) -> str:
    return VALUE_TYPES[n] if n < len(VALUE_TYPES) else f"type_{n}"


class Scenario:
    """A map's scenario tag, read from the tag data cemap reads."""

    def __init__(self, data: bytes, base: int, offset: int):
        self.data, self.base, self.off = data, base, offset
        size, _f, _o, addr, _id = self._raw(SYNTAX_DATA)
        self.nodes_off = addr - base + SYNTAX_HEADER if size else None
        self.node_count = (size - SYNTAX_HEADER) // NODE.size if size > SYNTAX_HEADER else 0
        if self.nodes_off is not None:
            hdr = addr - base
            if not (0 <= hdr and hdr + size <= len(data)) or data[hdr + 0x28:hdr + 0x2C] != b"@t@d":
                self.nodes_off, self.node_count = None, 0
        size, _f, _o, addr, _id = self._raw(STRING_DATA)
        start = addr - base
        self.strings = data[start:start + size] if size and 0 <= start <= len(data) - size else b""

    def _raw(self, at: int) -> tuple[int, int, int, int, int]:
        return struct.unpack_from("<IIIII", self.data, self.off + at)

    def block(self, name: str) -> list[int]:
        """The file offsets of a block's elements ([] when it runs off the data)."""
        at, size = SCNR[name]
        count, addr, _ = struct.unpack_from("<III", self.data, self.off + at)
        start = addr - self.base
        if count == 0 or count > 65535 or start < 0 or start + count * size > len(self.data):
            return []
        return [start + i * size for i in range(count)]

    def name_at(self, off: int) -> str:
        return self.data[off:off + 32].split(b"\0")[0].decode("latin1")

    def text(self, offset: int) -> str | None:
        if offset >= len(self.strings):
            return None
        end = self.strings.find(b"\0", offset)
        return self.strings[offset:end if end >= 0 else None].decode("latin1")

    def node(self, handle: int):
        """(index, value type, flags, next, string offset, value), or None."""
        i = handle & 0xFFFF
        if handle == NONE or self.nodes_off is None or i >= self.node_count:
            return None
        salt, index, vtype, flags, nxt, so, val = NODE.unpack_from(self.data, self.nodes_off + i * NODE.size)
        if salt == 0:
            return None
        return index, vtype, flags, nxt, so, val

    def children(self, handle: int):
        n = self.node(handle)
        c = n[5] if n else NONE
        seen = 0
        while c != NONE and seen < 4096:
            yield c
            nc = self.node(c)
            c = nc[3] if nc else NONE
            seen += 1

    def scripts(self) -> list[dict]:
        out = []
        for e in self.block("scripts"):
            stype, rtype, root = struct.unpack_from("<HHI", self.data, e + 32)
            out.append({"name": self.name_at(e), "type": SCRIPT_TYPES[stype] if stype < 5 else stype,
                        "returns": value_type(rtype), "root": root})
        return out

    def globals(self) -> list[dict]:
        out = []
        for e in self.block("globals"):
            gtype = struct.unpack_from("<H", self.data, e + 32)[0]
            init = struct.unpack_from("<I", self.data, e + 40)[0]
            out.append({"name": self.name_at(e), "type": value_type(gtype), "init": init})
        return out

    def calls(self, root: int, functions: collections.Counter, engine_globals: collections.Counter,
              own_globals: set[str], depth: int = 0) -> None:
        """Count the functions a tree calls and the engine globals it reads."""
        n = self.node(root)
        if n is None or depth > 512:
            return
        _index, _vtype, flags, _nxt, so, _val = n
        if flags & PRIMITIVE:
            if flags & GLOBAL_REF:
                name = self.text(so)
                if name and name not in own_globals:
                    engine_globals[name] += 1
            return
        kids = list(self.children(root))
        if not kids:
            return
        head = self.node(kids[0])
        if head and not flags & SCRIPT_CALL:
            name = self.text(head[4])
            if name:
                functions[name] += 1
        for k in kids[1:]:
            self.calls(k, functions, engine_globals, own_globals, depth + 1)

    # --- source ----------------------------------------------------------

    def constant(self, n) -> str:
        index, vtype, flags, _nxt, so, val = n
        # A function name's index is the function's number, not a type.
        kind = index if not flags & GLOBAL_REF and vtype != FUNCTION_NAME else vtype
        if not flags & GLOBAL_REF and vtype != FUNCTION_NAME:
            if kind == BOOLEAN:
                return "true" if val & 0xFF else "false"
            if kind == REAL:
                r = struct.unpack("<f", struct.pack("<I", val))[0]
                return f"{r:.6g}" if "." in f"{r:.6g}" or "e" in f"{r:.6g}" else f"{r:.6g}.0"
            if kind == SHORT:
                return str(struct.unpack("<h", struct.pack("<H", val & 0xFFFF))[0])
            if kind == LONG:
                return str(struct.unpack("<i", struct.pack("<I", val))[0])
        t = self.text(so)
        if t is None:
            return "none"
        if kind == 9 and not flags & GLOBAL_REF:  # a string constant
            return '"' + t.replace('"', '\\"') + '"'
        if flags & GLOBAL_REF or vtype == FUNCTION_NAME:
            return ident(t)
        return t

    def source(self, handle: int, indent: int = 0, depth: int = 0) -> str:
        n = self.node(handle)
        if n is None or depth > 512:
            return "<?>"
        if n[2] & PRIMITIVE:
            return self.constant(n)
        parts = [self.source(c, indent + 1, depth + 1) for c in self.children(handle)]
        flat = "(" + " ".join(parts) + ")"
        if len(flat) + indent * 4 <= 100 or len(parts) < 2:
            return flat
        pad = "\n" + "    " * (indent + 1)
        return "(" + parts[0] + "".join(pad + p for p in parts[1:]) + ")"

    def hsc(self) -> str:
        lines = []
        for g in self.globals():
            lines.append(f"(global {g['type']} {ident(g['name'])} {self.source(g['init'], 1)})")
        if lines:
            lines.append("")
        for s in self.scripts():
            head = f"(script {s['type']}"
            if s["type"] in ("static", "stub"):
                head += f" {s['returns']}"
            body = list(self.children(s["root"]))
            # The root is a begin the compiler wraps the body in.
            first = self.node(body[0]) if body else None
            if first and self.text(first[4]) == "begin":
                body = body[1:]
            else:
                body = [s["root"]]
            lines.append(f"{head} {ident(s['name'])}")
            lines += ["    " + self.source(b, 1) for b in body]
            lines[-1] += ")"
            lines.append("")
        return "\n".join(lines)


def open_scenario(path: str) -> tuple[Scenario, list[dict], dict, bytes]:
    header, data, _size, _sha = cemap.read_tag_data(path, digest=False)
    tags, index = cemap.read_tags(data, header)
    base = index["base_address"]
    array_off = struct.unpack_from("<I", data, 0)[0] - base
    scnr = next((t for t in tags if t["id"] == index["scenario_id"]), None) \
        or next((t for t in tags if t["class"] == "scnr"), None)
    if scnr is None:
        raise cemap.NotACacheFile("no scenario tag")
    data_addr = cemap.TAG_ENTRY.unpack_from(data, array_off + scnr["index"] * cemap.TAG_ENTRY.size)[5]
    return Scenario(data, base, data_addr - base), tags, index, data


def vehicle_types(data: bytes, tags: list[dict], base: int) -> dict[str, str]:
    """Each vehicle tag's CE vehicle type (jeep, plane, ...), by path."""
    array_off = struct.unpack_from("<I", data, 0)[0] - base
    out = {}
    for t in tags:
        if t["class"] != "vehi" or t["external"]:
            continue
        addr = cemap.TAG_ENTRY.unpack_from(data, array_off + t["index"] * cemap.TAG_ENTRY.size)[5]
        off = addr - base + VEHICLE_TYPE_AT
        if 0 <= off < len(data) - 2:
            v = struct.unpack_from("<H", data, off)[0]
            out[t["path"] or f"#{t['index']}"] = VEHICLE_TYPES[v] if v < len(VEHICLE_TYPES) else f"type_{v}"
    return out


OBJECT_TYPES = ["biped", "vehicle", "weapon", "equipment", "garbage", "projectile", "scenery",
                "machine", "control", "light_fixture", "placeholder", "sound_scenery"]


def names(sc: Scenario) -> dict:
    """Every name a script can refer to, with what a bake needs to recreate
    it: the object names with the placement each names, and the trigger
    volumes, cutscene flags and device groups with their geometry or value.
    Positions are CE world units."""
    d = sc.data
    vec = lambda off: [round(v, 4) for v in struct.unpack_from("<3f", d, off)]
    out = {"object names": [], "trigger volumes": [], "cutscene flags": [], "device groups": []}
    for e in sc.block("object names"):
        otype, index = struct.unpack_from("<Hh", d, e + 32)
        out["object names"].append({"name": sc.name_at(e),
                                    "type": OBJECT_TYPES[otype] if otype < len(OBJECT_TYPES) else otype,
                                    "placement": index})
    for e in sc.block("trigger volumes"):
        out["trigger volumes"].append({"name": sc.name_at(e + 4), "forward": vec(e + 48), "up": vec(e + 60),
                                       "position": vec(e + 72), "extents": vec(e + 84)})
    for e in sc.block("cutscene flags"):
        yaw, pitch = struct.unpack_from("<2f", d, e + 48)
        out["cutscene flags"].append({"name": sc.name_at(e + 4), "position": vec(e + 36),
                                      "facing": [round(yaw, 4), round(pitch, 4)]})
    for e in sc.block("device groups"):
        value, flags = struct.unpack_from("<fI", d, e + 32)
        out["device groups"].append({"name": sc.name_at(e), "initial": round(value, 4), "flags": flags})
    return out


def survey_scenario(sc: Scenario) -> dict:
    """What a conversion has to carry: the scripts and what they call, and
    the devices, groups and volumes they work on."""
    counts = {name: len(sc.block(name)) for name in SCNR}
    scripts = sc.scripts()
    globals_ = sc.globals()
    own = {g["name"] for g in globals_}
    functions: collections.Counter = collections.Counter()
    engine_globals: collections.Counter = collections.Counter()
    for s in scripts:
        sc.calls(s["root"], functions, engine_globals, own)
    for g in globals_:
        sc.calls(g["init"], functions, engine_globals, own)
    linked = 0
    for kind in ("machines", "controls"):
        for e in sc.block(kind):
            power, position = struct.unpack_from("<hh", sc.data, e + DEVICE_GROUPS_AT)
            if power >= 0 or position >= 0:
                linked += 1
    return {
        "counts": {k: v for k, v in counts.items() if v},
        "script_types": dict(collections.Counter(str(s["type"]) for s in scripts)),
        "syntax_nodes": sc.node_count,
        "readable": sc.nodes_off is not None and bool(sc.strings),
        "functions": dict(functions.most_common()),
        "engine_globals": dict(engine_globals.most_common()),
        "devices_in_groups": linked,
    }


def read(path: str) -> dict:
    sc, tags, index, data = open_scenario(path)
    out = survey_scenario(sc)
    out["vehicle_types"] = vehicle_types(data, tags, index["base_address"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("maps", nargs="+")
    ap.add_argument("--hsc", action="store_true", help="print the scripts as source instead")
    ap.add_argument("--names", action="store_true", help="print the names scripts refer to, as JSON")
    a = ap.parse_args()
    for p in a.maps:
        if a.names:
            sc, *_ = open_scenario(p)
            json.dump(names(sc), sys.stdout, indent=1)
            print()
        elif a.hsc:
            sc, *_ = open_scenario(p)
            if len(a.maps) > 1:
                print(f"; {p}")
            print(sc.hsc())
        else:
            json.dump(read(p), sys.stdout, indent=1)
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main())

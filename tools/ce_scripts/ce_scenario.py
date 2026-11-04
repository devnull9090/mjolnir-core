"""What a Custom Edition map's scripts need from its scenario.

    python ce_scenario.py <map> [--tags <staging tags.json>] [--out scenario.json]

Reads the blocks a script names (object names, machines, controls, device
groups, trigger volumes, cutscene flags) and, per machine tag, what a machine
of the simulation's own has to copy: its transition time, its collision BSPs
and the node each hangs on. Offsets are the CE scenario's and device tags', as
docs/re/ce_map_scripts.md lists them.

Protected maps scramble tag classes and names: give `--tags` the staging's
tags.json (halo2ue's repaired table) to name tags by datum.
"""
import argparse
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ce_hs  # noqa: E402

# Element sizes of the eight arrays of a CE collision BSP, in `.bin` order
# (blam_sbsp::ce::CE_SIZES), which is also their order in the tag.
BSP_ARRAYS = [("bsp3d_nodes", 12), ("planes", 16), ("leaves", 8), ("bsp2d_references", 8),
              ("bsp2d_nodes", 20), ("surfaces", 12), ("edges", 24), ("vertices", 16)]

# The placement blocks an object name can point into: kind, field, element size.
OBJECT_BLOCKS = [("scenery", 0x210, 72), ("biped", 0x228, 120), ("vehicle", 0x240, 120), ("equipment", 0x258, 40),
                 ("weapon", 0x270, 92), ("machine", 0x294, 64), ("control", 0x2AC, 64),
                 ("light_fixture", 0x2C4, 88), ("sound_scenery", 0x2DC, 40)]


class Scenario:
    def __init__(self, path, tags=None):
        self.map = ce_hs.CeMap(path)
        self.b = self.map.b
        self.s = self.map.off(self.map.tags[self.map.scnr_id][2])
        self.by_datum = {}
        if tags:
            self.by_datum = {t["datum"]: t for t in json.load(open(tags, encoding="utf-8"))["tags"]}

    def f(self, o, n=1):
        v = struct.unpack_from(f"<{n}f", self.b, o)
        return v[0] if n == 1 else list(v)

    def i16(self, o):
        return struct.unpack_from("<h", self.b, o)[0]

    def u16(self, o):
        return struct.unpack_from("<H", self.b, o)[0]

    def u32(self, o):
        return struct.unpack_from("<I", self.b, o)[0]

    def name32(self, o):
        return self.b[o:o + 32].split(b"\0")[0].decode("latin-1")

    def block(self, base, field, size):
        return self.map.reflexive(base, field, size)

    def datum_of(self, o):
        """The tag a dependency at `o` points at, or None."""
        d = self.u32(o + 12)
        return None if d == 0xFFFFFFFF else d

    def path_of(self, datum):
        t = self.by_datum.get(datum)
        return t["path"] if t else self.map.tags[datum][1]

    def palette(self, field):
        return [self.datum_of(o) for o in self.block(self.s, field, 48)]

    def names(self):
        return [self.name32(o) for o in self.block(self.s, 0x204, 36)]

    def placements(self, field, palette_field):
        """Machines or controls: 64-byte placements."""
        names, palette, out = self.names(), self.palette(palette_field), []
        for i, o in enumerate(self.block(self.s, field, 64)):
            t, n = self.i16(o), self.i16(o + 2)
            datum = palette[t] if 0 <= t < len(palette) else None
            out.append({
                "index": i, "datum": datum, "tag": self.path_of(datum) if datum is not None else None,
                "name": names[n] if 0 <= n < len(names) else None, "not_placed": self.u16(o + 4),
                "position": self.f(o + 8, 3), "rotation": self.f(o + 0x14, 3),
                "power_group": self.i16(o + 0x28), "position_group": self.i16(o + 0x2A),
                "device_flags": self.u32(o + 0x2C), "flags": self.u32(o + 0x30),
            })
        return out

    def machines(self):
        return self.placements(0x294, 0x2A0)

    def named_objects(self):
        """Which block each object name's placement is in: name -> {kind, index,
        position, rotation}. Scripts type a name by what it was placed as."""
        names, out = self.names(), {}
        for kind, field, size in OBJECT_BLOCKS:
            for i, o in enumerate(self.block(self.s, field, size)):
                n = self.i16(o + 2)
                if 0 <= n < len(names):
                    out.setdefault(names[n], {"kind": kind, "index": i, "not_placed": self.u16(o + 4),
                                              "position": self.f(o + 8, 3), "rotation": self.f(o + 0x14, 3)})
        return out

    def controls(self):
        return self.placements(0x2AC, 0x2B8)

    def device_groups(self):
        return [{"name": self.name32(o), "initial_value": self.f(o + 32), "flags": self.u32(o + 36)}
                for o in self.block(self.s, 0x288, 52)]

    def trigger_volumes(self):
        return [{"name": self.name32(o + 4), "forward": self.f(o + 0x30, 3), "up": self.f(o + 0x3C, 3),
                 "position": self.f(o + 0x48, 3), "extents": self.f(o + 0x54, 3)}
                for o in self.block(self.s, 0x360, 96)]

    def cutscene_flags(self):
        return [{"name": self.name32(o + 4), "position": self.f(o + 0x24, 3), "facing": self.f(o + 0x30, 2)}
                for o in self.block(self.s, 0x4E4, 92)]

    def device_tag(self, datum):
        """A device tag's fields, with the collision BSPs its nodes carry."""
        o = self.map.off(self.map.tags[datum][2])
        coll = self.datum_of(o + 0x70)
        return {"bounding_radius": self.f(o + 4), "position_transition": self.f(o + 0x188),
                "power_transition": self.f(o + 0x180), "animated": self.datum_of(o + 0x38) is not None,
                "bsps": self.collision(coll) if coll is not None else []}

    def scenery_tag(self, index):
        """What `device_tag` gives, for a scenery placement."""
        at = self.block(self.s, 0x210, 72)[index]
        datum = self.palette(0x21C)[self.i16(at)]
        o = self.map.off(self.map.tags[datum][2])
        coll = self.datum_of(o + 0x70)
        return {"bounding_radius": self.f(o + 4), "bsps": self.collision(coll) if coll is not None else []}

    def collision(self, datum):
        """Each BSP of a collision model: its node's name and its raw arrays."""
        o = self.map.off(self.map.tags[datum][2])
        out = []
        for n in self.block(o, 0x28C, 64):
            for bsp in self.block(n, 52, 96):
                arrays = []
                for k, (_, size) in enumerate(BSP_ARRAYS):
                    count, ptr = struct.unpack_from("<II", self.b, bsp + 12 * k)
                    at = self.map.off(ptr) if count else 0
                    arrays.append((count, self.b[at:at + count * size]))
                out.append({"node": self.name32(n), "arrays": arrays})
        return out


def triangles(bsp):
    """A collision BSP's surfaces as triangles, walked from their edge rings."""
    (_, surfaces), (_, edges), (_, vertices) = bsp["arrays"][5], bsp["arrays"][6], bsp["arrays"][7]
    point = lambda i: struct.unpack_from("<3f", vertices, 16 * i)
    out = []
    for s in range(len(surfaces) // 12):
        first = struct.unpack_from("<i", surfaces, 12 * s + 4)[0]
        ring, e = [], first
        while True:
            start, end, forward, reverse, left, right = struct.unpack_from("<6i", edges, 24 * e)
            if left == s:
                ring.append(point(start))
                e = forward
            else:
                ring.append(point(end))
                e = reverse
            if e == first or len(ring) > 64:
                break
        for k in range(1, len(ring) - 1):
            out.append([list(ring[0]), list(ring[k]), list(ring[k + 1])])
    return out


def write_bsp(bsp, base):
    """A BSP as the staging's `<base>.bsp.json` and `.bin` (ce_pc_v7)."""
    blob = b"".join(struct.pack("<I", count) + raw for count, raw in bsp["arrays"])
    points = [struct.unpack_from("<3f", bsp["arrays"][7][1], 16 * i) for i in range(bsp["arrays"][7][0])]
    lo = [min(p[k] for p in points) for k in range(3)]
    hi = [max(p[k] for p in points) for k in range(3)]
    open(base + ".bsp.bin", "wb").write(blob)
    json.dump({"layout": "ce_pc_v7", "coordinate_space": "halo_wu_node_local", "bin": os.path.basename(base) + ".bsp.bin",
               "world_bounds": {"min": lo, "max": hi}},
              open(base + ".bsp.json", "w", encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("map")
    ap.add_argument("--tags")
    ap.add_argument("--out")
    a = ap.parse_args()
    s = Scenario(a.map, a.tags)
    out = {"object_names": s.names(), "machines": s.machines(), "controls": s.controls(),
           "device_groups": s.device_groups(), "trigger_volumes": s.trigger_volumes(),
           "cutscene_flags": s.cutscene_flags()}
    text = json.dumps(out, indent=1)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(text)
    else:
        print(text)


if __name__ == "__main__":
    main()

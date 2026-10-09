"""A classic CE map's planar fog: BSP 0's fog planes, the regions they bound
and the fog tags those regions use, written beside the staging as fog.json
for ce_material_spec.py (docs/ce_map_conversion.md, "Planar fog").

    python ce_fog.py <map.map> <staging dir>

Damnation's shaft, Gephyrophobia's chasm, Battle Creek's stream, Chill Out's
pool and Death Island's sea (a water fog) are planar fog: below a plane, a
colour that thickens with depth under the plane and with distance from the
eye, opaque at the fog tag's opaque depth and distance. halo2ue does not
stage it, so it is read from the map here.

Layouts (H1 public definitions, checked on the 19 stock maps): the
scenario's structure BSPs at 0x5A4 (32 bytes: file offset, size, address,
pad, ref; the BSP block starts with a pointer to the sbsp root, in the
block's own address space); sbsp fog planes at 376 (32 bytes: front region
i16, pad 2, plane i, j, k, d, vertices block), fog regions at 388 (40: pad
36, fog palette i16, weather palette i16), fog palette at 400 (136: name 32,
fog reference 16, ...). fog: flags u32 at 0 (bit 0 is water), maximum
density at 88, opaque distance at 96, opaque depth at 104, colour at 120.
Distances are world units.
"""
import json
import os
import struct
import sys

from ce_sounds import Map


def planar_fog(m):
    """Every fog plane with its fog: [{plane: [i, j, k, d], color, max_density,
    opaque_distance, opaque_depth, water, fog}], CE world units."""
    d = m.d
    scen = next((t for t in m.tags if t["cls"] == "scnr"), None)
    if not scen:
        return []
    n, ptr = struct.unpack_from("<II", d, m.off(scen["doff"]) + 0x5A4)
    if n < 1:
        return []
    start, _size, address = struct.unpack_from("<III", d, m.off(ptr))
    conv = lambda p: start + (p - address)
    root = conv(struct.unpack_from("<I", d, start)[0])
    planes_n, planes_p = struct.unpack_from("<II", d, root + 376)
    regions_n, regions_p = struct.unpack_from("<II", d, root + 388)
    palette_n, palette_p = struct.unpack_from("<II", d, root + 400)
    out = []
    for k in range(planes_n):
        e = conv(planes_p) + 32 * k
        region, = struct.unpack_from("<h", d, e)
        plane = list(struct.unpack_from("<4f", d, e + 4))
        if not 0 <= region < regions_n:
            continue
        fog_i, = struct.unpack_from("<h", d, conv(regions_p) + 40 * region + 36)
        if not 0 <= fog_i < palette_n:
            continue
        fog_path = m.dep(conv(palette_p) + 136 * fog_i + 32)
        t = next((t for t in m.tags if t["cls"] == "fog " and t["path"] == fog_path), None)
        if not t:
            continue
        f = m.off(t["doff"])
        flags, = struct.unpack_from("<I", d, f)
        out.append({
            "plane": plane,
            "fog": fog_path,
            "water": bool(flags & 1),
            "max_density": struct.unpack_from("<f", d, f + 88)[0],
            "opaque_distance": struct.unpack_from("<f", d, f + 96)[0],
            "opaque_depth": struct.unpack_from("<f", d, f + 104)[0],
            "color": list(struct.unpack_from("<3f", d, f + 120)),
        })
    return out


def main():
    src, staging = sys.argv[1:3]
    fogs = planar_fog(Map(src, staging))
    with open(os.path.join(staging, "fog.json"), "w", encoding="utf-8") as f:
        json.dump({"planes": fogs}, f, indent=1)
    for p in fogs:
        print(f"  fog plane z = {p['plane'][3]:.2f} wu ({p['fog']}): density {p['max_density']:.2f},"
              f" opaque at {p['opaque_distance']:.2f} wu distance / {p['opaque_depth']:.2f} wu depth"
              f"{', water' if p['water'] else ''}")
    if not fogs:
        print("  no planar fog")


if __name__ == "__main__":
    main()

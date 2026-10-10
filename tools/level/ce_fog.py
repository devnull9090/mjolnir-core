"""A classic CE map's planar fog: BSP 0's fog planes, the regions they bound
and the fog tags those regions use, written beside the staging as fog.json
for ce_material_spec.py (docs/ce_map_conversion.md, "Planar fog"); and its
weather (the weather palette's particle systems its clusters use, and the
weather polyhedra) and how many of its clusters draw a sky, for
gen_ce_level.py.

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
fog reference 16, ...), clusters at 308 (104: sky, fog, background sound,
sound environment, weather palette, all i16), weather palette at 436 (240:
name 32, particle system reference 16, ...), weather polyhedra at 448 (32:
bounding sphere centre and radius, pad 4, planes block of i, j, k, d). fog:
flags u32 at 0 (bit 0 is water), maximum
density at 88, opaque distance at 96, opaque depth at 104, colour at 120.
Distances are world units.
"""
import json
import os
import struct
import sys

from ce_sounds import Map


def bsp_root(m):
    """BSP 0's root struct in the file and the converter from the BSP block's
    addresses to file offsets, or (None, None)."""
    d = m.d
    scen = next((t for t in m.tags if t["cls"] == "scnr"), None)
    if not scen:
        return None, None
    n, ptr = struct.unpack_from("<II", d, m.off(scen["doff"]) + 0x5A4)
    if n < 1:
        return None, None
    start, _size, address = struct.unpack_from("<III", d, m.off(ptr))
    conv = lambda p: start + (p - address)
    return conv(struct.unpack_from("<I", d, start)[0]), conv


def planar_fog(m):
    """Every fog plane with its fog: [{plane: [i, j, k, d], color, max_density,
    opaque_distance, opaque_depth, water, fog}], CE world units."""
    d = m.d
    root, conv = bsp_root(m)
    if root is None:
        return []
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


def sky_clusters(m):
    """How many of BSP 0's clusters draw a sky. CE fogs only those with the
    sky's outdoor fog: Chill Out's sky has a fog, opaque at 90 wu, but none
    of its ten clusters has a sky."""
    root, conv = bsp_root(m)
    if root is None:
        return 0
    clusters_n, clusters_p = struct.unpack_from("<II", m.d, root + 308)
    return sum(struct.unpack_from("<h", m.d, conv(clusters_p) + 104 * k)[0] >= 0 for k in range(clusters_n))


def weather(m):
    """The weather BSP 0's clusters draw: {systems: [{system, clusters}], one
    per weather palette entry with a particle system that some cluster uses,
    most used first; polyhedra: [{centre, radius, planes}], the volumes CE
    draws no weather in}, CE world units. Every stock map's palette carries
    only wind; Coldsnap's snow is `levels\\b40\\snow`."""
    d = m.d
    root, conv = bsp_root(m)
    if root is None:
        return {"systems": [], "polyhedra": []}
    clusters_n, clusters_p = struct.unpack_from("<II", d, root + 308)
    palette_n, palette_p = struct.unpack_from("<II", d, root + 436)
    used = {}
    for k in range(clusters_n):
        w, = struct.unpack_from("<h", d, conv(clusters_p) + 104 * k + 8)
        if 0 <= w < palette_n:
            used[w] = used.get(w, 0) + 1
    systems = []
    for w, n in sorted(used.items(), key=lambda x: -x[1]):
        system = m.dep(conv(palette_p) + 240 * w + 32)
        if system:
            systems.append({"system": system, "clusters": n})
    polys_n, polys_p = struct.unpack_from("<II", d, root + 448)
    polyhedra = []
    for k in range(polys_n):
        e = conv(polys_p) + 32 * k
        cx, cy, cz, r = struct.unpack_from("<4f", d, e)
        planes_n, planes_p = struct.unpack_from("<II", d, e + 20)
        planes = [list(struct.unpack_from("<4f", d, conv(planes_p) + 16 * i)) for i in range(planes_n)]
        polyhedra.append({"centre": [cx, cy, cz], "radius": r, "planes": planes})
    return {"systems": systems, "polyhedra": polyhedra}


def main():
    src, staging = sys.argv[1:3]
    m = Map(src, staging)
    fogs = planar_fog(m)
    wx = weather(m)
    with open(os.path.join(staging, "fog.json"), "w", encoding="utf-8") as f:
        json.dump({"planes": fogs, "weather": wx, "sky_clusters": sky_clusters(m)}, f, indent=1)
    for p in fogs:
        print(f"  fog plane z = {p['plane'][3]:.2f} wu ({p['fog']}): density {p['max_density']:.2f},"
              f" opaque at {p['opaque_distance']:.2f} wu distance / {p['opaque_depth']:.2f} wu depth"
              f"{', water' if p['water'] else ''}")
    if not fogs:
        print("  no planar fog")
    for s in wx["systems"]:
        print(f"  weather {s['system']} in {s['clusters']} cluster(s), {len(wx['polyhedra'])} polyhedra without it")


if __name__ == "__main__":
    main()

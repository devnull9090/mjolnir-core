"""Audit a converted map's textures: where each shader is, how far its
base map is stretched, and what the remaster does with it.

    python tools/level/texture_audit.py <CODE> [--out audit.json] [--top N]

For every shader of the map's scene (ce_upgrade_maps.json's conversion):
its surface area, its base map and that map's size, how many metres one
copy of the base map covers (from the mesh's UVs), and so the size of a
texel on the surface, in cm. A texel over about 1 cm reads as blurred from
a player's eye height at arm's length; over 3 cm, from across a room.

`treatment` says what the remaster already does with the shader: the
landscape (`shaders`), the cliffs' rock (`cliff_shaders`), a PBR surface
(`structure_surfaces`), hidden (`hide_materials`), or `as converted`.
`as converted` rows sorted by area times texel size are the work list.
"""
import argparse
import collections
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from refine_water_gltf import read_accessor  # noqa: E402


def treatment(name, m):
    for tok in m.get("hide_materials") or []:
        if tok.lower() in name:
            return "hidden"
    for i, st in enumerate(m.get("structure_surfaces") or []):
        if any(x in name for x in st["shaders"]):
            return "surface: " + st["surface"]
    if any(x in name for x in m.get("cliff_shaders") or []):
        return "cliff rock"
    if any(x in name for x in m.get("shaders") or []):
        return "landscape"
    return "as converted"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("code")
    ap.add_argument("--out")
    ap.add_argument("--top", type=int, default=60)
    a = ap.parse_args()
    m = json.load(open(os.path.join(HERE, "ce_upgrade_maps.json"), encoding="utf-8"))[a.code]
    conv = m.get("scene") or m["conversion"]
    spec = json.load(open(os.path.join(conv, "materials.spec.json"), encoding="utf-8"))
    files = {t["name"]: t["file"] for t in spec["textures"]}
    by_name = {e["name"]: e for e in spec["materials"]}
    rows = collections.OrderedDict()
    for scene in sorted(f for f in os.listdir(conv) if f.startswith("scene") and f.endswith(".gltf")):
        doc = json.load(open(os.path.join(conv, scene), encoding="utf-8"))
        if not doc.get("buffers"):
            continue
        data = open(os.path.join(conv, doc["buffers"][0]["uri"]), "rb").read()
        for mesh in doc.get("meshes") or []:
            for prim in mesh["primitives"]:
                if "TEXCOORD_0" not in prim["attributes"] or "indices" not in prim:
                    continue
                full = doc["materials"][prim["material"]]["name"]
                shader = full.split("__lm")[0]
                pos = read_accessor(doc, data, prim["attributes"]["POSITION"]).astype(float)
                uv = read_accessor(doc, data, prim["attributes"]["TEXCOORD_0"]).astype(float)
                idx = read_accessor(doc, data, prim["indices"]).reshape(-1, 3)
                t, u = pos[idx], uv[idx]
                world = 0.5 * np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1).sum()
                e1, e2 = u[:, 1] - u[:, 0], u[:, 2] - u[:, 0]
                uva = 0.5 * np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]).sum()
                row = rows.setdefault(shader, {"shader": shader, "area_m2": 0.0, "uv_area": 0.0, "scenes": set(),
                                               "entry": by_name.get(full)})
                row["area_m2"] += float(world)
                row["uv_area"] += float(uva)
                row["scenes"].add(scene.replace("scene", "").replace(".gltf", "").strip("_") or "terrain")
                row["entry"] = row["entry"] or by_name.get(full)
    out = []
    for row in rows.values():
        e = row.pop("entry") or {}
        tex = e.get("textures") or {}
        base = str(tex.get("Base") or tex.get("Map0") or "").rsplit(".", 1)[-1]
        size = None
        if base in files and os.path.exists(files[base]):
            size = list(Image.open(files[base]).size)
        span = (row["area_m2"] / row["uv_area"]) ** 0.5 if row["uv_area"] > 1e-9 else None
        texel = span * 100.0 / max(size) if span and size else None
        row.update({"scenes": sorted(row["scenes"]), "parent": str(e.get("parent", "")).rsplit(".", 1)[-1],
                    "base": base, "base_size": size, "detail": str(tex.get("Primary", "")).rsplit(".", 1)[-1],
                    "bump": str(tex.get("Bump", "")).rsplit(".", 1)[-1],
                    "span_m": round(span, 2) if span else None, "texel_cm": round(texel, 2) if texel else None,
                    "area_m2": round(row["area_m2"], 1), "treatment": treatment(row["shader"], m)})
        row.pop("uv_area")
        out.append(row)
    out.sort(key=lambda r: -(r["area_m2"] * (r["texel_cm"] or 0)))
    if a.out:
        json.dump(out, open(a.out, "w", encoding="utf-8"), indent=1)
    counts = collections.Counter(r["treatment"].split(":")[0] for r in out)
    print(f"{a.code}: {len(out)} shader(s), {sum(r['area_m2'] for r in out):.0f} m2; " +
          ", ".join(f"{v} {k}" for k, v in counts.most_common()))
    todo = [r for r in out if r["treatment"] == "as converted"]
    print(f"as converted: {len(todo)} shader(s), {sum(r['area_m2'] for r in todo):.0f} m2. Worst first:")
    for r in todo[:a.top]:
        size = "x".join(str(v) for v in r["base_size"]) if r["base_size"] else "?"
        print(f"  {r['area_m2']:8.0f} m2  {str(r['texel_cm'] or '?'):>6} cm/texel  {size:>9}  {r['parent']:28s} "
              f"{r['shader'][-58:]}")


if __name__ == "__main__":
    main()

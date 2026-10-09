#!/usr/bin/env python3
"""Add a staged CE map's scenery collision to its BSP collision.

    merge_ce_collision.py <staging dir> <out collision.json>

CE scenery (rocks, trees) collides through each object's own collision model;
a converted map has no Blam scenery to carry one, so the triangles are added
to the structure BSP's collision instead. Every scenery placement with a
staged collision model (`collision/*.json`, object space, world units) has its
triangles moved to the placement and appended as standalone surfaces: one
plane, one three-edge ring and three vertices each, marked two-sided, with a
material picked from the scenery's name (shield, rock, wood, plant:
SCENERY_MATERIALS).

Ground shaders that paint grass into sand per pixel are split: their surfaces
over grass get a grass material of their own (split_blended_ground). Every
material ends up in the output's `materials`, with the CE `material_type` or a
`game_material` that `mjolnir level collision` turns into the game's own.

No BSP leaf references them here. `mjolnir level collision --own-bsp` puts
them into the BSP tree (blam_sbsp::scenery: the leaves they pass through are
split on their planes), so queries that walk the tree, projectiles among
them, meet them, and compiles the structure's Havok MOPP with one key per
collision surface, so players and vehicles stand on and run into them.

Writes `<out>.json` and the `.bin` it names, in the staging's own layout.
"""
import json
import math
import os
import struct
import sys

ORDER_DEFAULT = ["bsp3d_nodes", "planes", "leaves", "bsp2d_references", "bsp2d_nodes", "surfaces", "edges", "vertices"]
FORMATS = {
    "bsp3d_nodes": "<iii", "planes": "<ffff", "leaves": "<Hhi", "bsp2d_references": "<ii",
    "bsp2d_nodes": "<fffii", "surfaces": "<iiBbh", "edges": "<iiiiii", "vertices": "<fffi",
}
TWO_SIDED = 1


def ce_rotation(yaw, pitch, roll):
    cy, sy, cp, sp, cr, sr = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch), math.cos(roll), math.sin(roll)
    # CE object rotation, row-major: yaw about z, then pitch and roll about
    # the world's y and x axes (merge_ce_scene.py ce_rotation, which the
    # render geometry uses: the two must agree).
    rz = [[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]]
    ry = [[cp, 0, -sp], [0, 1, 0], [sp, 0, cp]]
    rx = [[1, 0, 0], [0, cr, -sr], [0, sr, cr]]

    def mul(a, b):
        return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    return mul(mul(rx, ry), rz)


# Scenery collision models carry no shader, so their material is picked by
# name: what a footstep or a bullet should sound and look like on it. The
# Covenant shield (c_field_generator) takes the Jackal shield's material: an
# energy shield made to stop small-arms fire, where energy_hologram (CE's
# "force field" type) is the hologram decoy's. Not yet confirmed in game.
SCENERY_MATERIALS = [(("field_generator",), "energy_shield_thick_cov_jackal"),
                     (("rock", "boulder", "stone", "cliff"), "hard_terrain_stone"),
                     (("tree", "log", "stump", "wood", "branch"), "tough_organic_wood"),
                     (("plant", "bush", "shrub", "grass", "fern", "leaf"), "soft_organic_plant")]


def add_material(materials, game_material, shader_path):
    for m in materials:
        if m.get("game_material") == game_material and m.get("shader_path") == shader_path:
            return m["index"]
    index = len(materials)
    materials.append({"index": index, "shader_class": "", "shader_path": shader_path,
                      "datum": 4294967295, "material_type": None, "game_material": game_material})
    return index


def scenery_material(materials, asset):
    name = asset.replace("\\", "/").lower()
    for words, game in SCENERY_MATERIALS:
        if any(w in name for w in words):
            return add_material(materials, game, "scenery " + game)
    return add_material(materials, "hard_terrain_stone", "scenery hard_terrain_stone")


def surface_points(s, surfaces, edges, vertices):
    """A surface's vertices, walked round its edge ring."""
    pts, e, first = [], surfaces[s][1], surfaces[s][1]
    for _ in range(64):
        start, end, forward, reverse, left, _right = edges[e]
        if left == s:
            pts.append(vertices[start][:3])
            e = forward
        else:
            pts.append(vertices[end][:3])
            e = reverse
        if e == first or e < 0:
            break
    return pts


def split_blended_ground(staging, materials, surfaces, edges, vertices):
    """CE's ground shaders paint grass into sand (or dirt) per pixel: a blended
    shader takes its secondary detail map where the base map's alpha is low.
    A collision surface has one material, so each surface of such a shader
    whose secondary detail is grass is moved to a grass copy of its material
    when the base alpha under it is mostly low. Sampled through the render
    geometry: the surface's points are found on the shader's own triangles and
    the base map is read at their UVs."""
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        return {}
    shaders = json.load(open(os.path.join(staging, "materials.json"), encoding="utf-8"))
    by_path = {m["shader"].get("tag_path", "").lower(): m for m in shaders.values() if isinstance(m, dict) and "shader" in m}
    targets = {}
    for m in materials:
        sh = by_path.get(m.get("shader_path", "").lower())
        if not sh or m.get("game_material"):
            continue
        s = sh["shader"]
        detail = s.get("detail") or {}
        if s.get("shader_type", 0) >= 1 and "grass" in (detail.get("secondary") or "").lower() \
                and s.get("base_map_has_alpha") and s.get("base_map"):
            targets[m["index"]] = (sh, os.path.basename(s["base_map"]))
    if not targets:
        return {}

    gl_path = os.path.join(staging, "bsp", "bsp_0.gltf")
    g = json.load(open(gl_path, encoding="utf-8"))
    bufs = [open(os.path.join(os.path.dirname(gl_path), b["uri"]), "rb").read() for b in g["buffers"]]

    def acc(i):
        a = g["accessors"][i]
        bv = g["bufferViews"][a["bufferView"]]
        n = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
        dt = {5126: "f4", 5125: "u4", 5123: "u2"}[a["componentType"]]
        arr = np.frombuffer(bufs[bv["buffer"]], dtype=dt, count=a["count"] * n,
                            offset=bv.get("byteOffset", 0) + a.get("byteOffset", 0))
        return arr.reshape(-1, n) if n > 1 else arr

    names = [m["name"] for m in g["materials"]]
    out = {}
    for ce_index, (sh, base_file) in targets.items():
        key = sh["shader"]["tag_path"].replace("\\", "_").replace(" ", "_").lower()
        tris, uvs = [], []
        for mesh in g["meshes"]:
            for p in mesh["primitives"]:
                if names[p["material"]].split("__lm")[0].lower() != key:
                    continue
                pos = acc(p["attributes"]["POSITION"]).astype(np.float64)
                # glTF (x, y up, z) metres -> CE world units (x, -z, y).
                ce = np.stack([pos[:, 0], -pos[:, 2], pos[:, 1]], axis=1) / 3.048
                idx = acc(p["indices"]).astype(np.int64).reshape(-1, 3)
                tris.append(ce[idx])
                uvs.append(acc(p["attributes"]["TEXCOORD_0"]).astype(np.float64)[idx])
        if not tris:
            continue
        T, U = np.concatenate(tris), np.concatenate(uvs)
        alpha = np.asarray(Image.open(os.path.join(staging, "textures", base_file)).convert("RGBA"))[..., 3]
        h, w = alpha.shape
        a0, e1, e2 = T[:, 0, :2], T[:, 1, :2] - T[:, 0, :2], T[:, 2, :2] - T[:, 0, :2]
        den = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
        ok = np.abs(den) > 1e-12

        def grass_at(pt):
            d = pt[:2] - a0
            with np.errstate(divide="ignore", invalid="ignore"):
                u = (d[:, 0] * e2[:, 1] - d[:, 1] * e2[:, 0]) / den
                v = (e1[:, 0] * d[:, 1] - e1[:, 1] * d[:, 0]) / den
            inside = ok & (u >= -1e-4) & (v >= -1e-4) & (u + v <= 1 + 1e-4)
            if not inside.any():
                return None
            zs = T[:, 0, 2] + u * (T[:, 1, 2] - T[:, 0, 2]) + v * (T[:, 2, 2] - T[:, 0, 2])
            cand = np.where(inside)[0]
            k = cand[np.argmin(np.abs(zs[cand] - pt[2]))]
            uv = U[k, 0] + u[k] * (U[k, 1] - U[k, 0]) + v[k] * (U[k, 2] - U[k, 0])
            x = int(np.floor((uv[0] % 1.0) * w)) % w
            y = int(np.floor((uv[1] % 1.0) * h)) % h
            return alpha[y, x] < 128

        grass_index = None
        grass, total = 0, 0
        for si, s in enumerate(surfaces):
            if s[4] != ce_index:
                continue
            pts = np.array(surface_points(si, surfaces, edges, vertices), dtype=np.float64)
            if len(pts) < 3:
                continue
            c = pts.mean(axis=0)
            votes = [grass_at(p) for p in [c] + [(c + q) / 2 for q in pts]]
            votes = [v for v in votes if v is not None]
            total += 1
            if votes and sum(votes) * 2 > len(votes):
                if grass_index is None:
                    grass_index = add_material(materials, "tough_terrain_grass", sh["shader"]["tag_path"])
                surfaces[si] = s[:4] + (grass_index,)
                grass += 1
        out[sh["shader"]["tag_path"]] = (grass, total)
    return out


def main():
    staging, out = sys.argv[1:3]
    src_json = os.path.join(staging, "bsp", "collision_0.json")
    meta = json.load(open(src_json, encoding="utf-8"))
    order = meta.get("array_order") or ORDER_DEFAULT
    if isinstance(order, int):
        order = ORDER_DEFAULT
    data = open(os.path.join(staging, meta["bin"]), "rb").read()

    arrays, at = {}, 0
    for name in order:
        (count,) = struct.unpack_from("<I", data, at)
        at += 4
        fmt = FORMATS[name]
        size = struct.calcsize(fmt)
        arrays[name] = [struct.unpack_from(fmt, data, at + i * size) for i in range(count)]
        at += count * size

    placement = json.load(open(os.path.join(staging, "placement.json"), encoding="utf-8"))
    # Placed as merge_ce_scene.py places them (ce_seat.py).
    from ce_seat import seat
    seat(placement, staging, log=lambda *_: None)
    planes, surfaces, edges, vertices = arrays["planes"], arrays["surfaces"], arrays["edges"], arrays["vertices"]
    materials = meta.setdefault("materials", [])
    split = split_blended_ground(staging, materials, surfaces, edges, vertices)
    cache, added, objects = {}, 0, 0
    for e in placement["entries"]:
        if e.get("kind") != "scenery" or not e.get("collision"):
            continue
        path = os.path.join(staging, e["collision"])
        if path not in cache:
            cache[path] = json.load(open(path, encoding="utf-8"))["triangles"]
        flat = cache[path]
        r = ce_rotation(*e.get("rot", [0, 0, 0]))
        t = e["pos"]
        for i in range(0, len(flat), 9):
            tri = []
            for j in range(3):
                x, y, z = flat[i + 3 * j: i + 3 * j + 3]
                tri.append([r[k][0] * x + r[k][1] * y + r[k][2] * z + t[k] for k in range(3)])
            a, b, c = tri
            u = [b[k] - a[k] for k in range(3)]
            v = [c[k] - a[k] for k in range(3)]
            n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
            length = math.sqrt(sum(x * x for x in n))
            if length < 1e-9:
                continue
            n = [x / length for x in n]
            plane = len(planes)
            planes.append((n[0], n[1], n[2], sum(n[k] * a[k] for k in range(3))))
            surface = len(surfaces)
            v0, e0 = len(vertices), len(edges)
            for j in range(3):
                vertices.append((tri[j][0], tri[j][1], tri[j][2], e0 + j))
            for j in range(3):
                # A ring walked from the surface's left: start vertex j, the
                # forward edge the next one; nothing on the right.
                edges.append((v0 + j, v0 + (j + 1) % 3, e0 + (j + 1) % 3, -1, surface, -1))
            surfaces.append((plane, e0, TWO_SIDED, -1, scenery_material(materials, e.get("asset", ""))))
            added += 1
        objects += 1

    blob = bytearray()
    for name in order:
        fmt = FORMATS[name]
        blob += struct.pack("<I", len(arrays[name]))
        for rec in arrays[name]:
            blob += struct.pack(fmt, *rec)
    bin_name = os.path.splitext(os.path.basename(out))[0] + ".bin"
    out_dir = os.path.dirname(os.path.abspath(out))
    os.makedirs(out_dir, exist_ok=True)
    open(os.path.join(out_dir, bin_name), "wb").write(blob)
    meta["bin"] = bin_name
    meta["counts"] = {name: len(arrays[name]) for name in order}
    meta["scenery_surfaces"] = {"objects": objects, "surfaces": added,
                                "note": "standalone surfaces after the BSP's own; mjolnir level collision links them into the tree"}
    json.dump(meta, open(out, "w", encoding="utf-8"), indent=1)
    print(f"{objects} scenery placement(s): {added} collision surface(s) added -> {out}")
    for name, (grass, total) in split.items():
        print(f"  {name}: {grass} of {total} surface(s) are grass")


if __name__ == "__main__":
    main()

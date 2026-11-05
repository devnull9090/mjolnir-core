#!/usr/bin/env python3
"""Split a staged, node-rigid CE vehicle into one static mesh per node.

    ce_vehicle_mesh.py <staging> <models/x__vehi.gltf> <CODE> <Name> <out dir> [--paks ...] [--examples ...]
                       [--instances <name>.instances.json]

`staging` is a fresh halo2ue export. Each node with geometry becomes
`/Game/MJOLNIR/Maps/<CODE>/SM_<CODE>_<Name>_<node>`, in the node's own space,
built the way tools/level/add_devices.py builds a machine's mesh: mesh_rewrite
on the shipped cube, package_add into pakchunk986-MJOLNIRMESH-<CODE>_P. A
node's transparent sections are a mesh of their own, `.._<node>_t`, since a
rewritten mesh enters the translucency pass by its slot 0.

- The model must be rigid: a blended vertex, or a triangle across two nodes,
  stops the tool.
- mesh_rewrite centres a mesh on its box and scales it into the donor's +-50 cm
  (the bounds it culls against stay the donor's). Two vertices no triangle uses
  make each box symmetric about the node, so the origin stays on the node and
  only the scale is left: the manifest's `component_scale`, which whatever
  attaches the mesh has to apply. Parts within +-50 cm come out at scale 1.
- ce_material_spec.py describes the materials, from a staging cut down to this
  model's shaders. Slots are real ones (--asset-imports). With --instances
  (ce_vehicle_materials.py's <name>.instances.json) each points at its cooked
  material instance, so a part arrives dressed, on every client, with nothing
  to run at spawn. Without it each points at its bare master. A slot names a
  package, not an object: mesh_rewrite hashes all of it as the package's name.
  Nothing here cooks.
- A vehicle moves, so it has no ground to take CE's object lighting from: it
  gets merge_ce_scene's default lighting, fixed to the vehicle.

Writes to <out dir>: the container, the .uasset files, materials.spec.json and
<name>.manifest.json. Every build is read back: each mesh's vertex buffer is
found in its package, and put through the manifest's transforms it has to land
on the staged model.
"""
import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
from types import SimpleNamespace

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from add_devices import WU_M, compact, rewrite  # noqa: E402
from merge_ce_scene import (DEFAULT_OBJECT_LIGHTING, LUMA, OBJECT_LIGHTING_PAGE, TRANSPARENT, accessor, change_colors,  # noqa: E402
                            light_vertices, load_gltf, primitives, quat_matrix, tangents_for, with_decal_offset,
                            with_passes, write_gltf)

DONOR_HALF = 0.5  # metres: mesh_rewrite's box, the cube's.
# merge_ce_scene's object lighting page: a block a placement, a column a colour.
BLOCK, PER_ROW, COLUMNS = 4, 16, 8
# glTF axes to Unreal's (a mirror) and to CE's (a rotation): manifest
# coordinate_contract, (x, z, -y) * 3.048 and (x, -y, z) * 304.8.
TO_UE = np.array([[1, 0, 0], [0, 0, 1], [0, 1, 0]], dtype=float)
TO_CE = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], dtype=float)


def node_worlds(g):
    """Each node's rest matrix in the model's space, and its parent."""
    nodes = g["nodes"]
    parent = {c: i for i, n in enumerate(nodes) for c in n.get("children", [])}

    def local(n):
        m = np.eye(4)
        m[:3, :3] = quat_matrix(n.get("rotation", [0, 0, 0, 1]))
        m[:3, 3] = n.get("translation", [0, 0, 0])
        return m

    def world(i):
        return world(parent[i]) @ local(nodes[i]) if i in parent else local(nodes[i])

    return [world(i) for i in range(len(nodes))], parent


def rigid_check(g, buf, prims):
    """Stop unless every vertex rides one node and no triangle spans two."""
    weights = [accessor(g, buf, p["attributes"]["WEIGHTS_0"]) for m in g["meshes"] for p in m["primitives"]]
    for w, p in zip(weights, prims):
        if np.any(w[:, 1:] > 0):
            sys.exit(f"{p['material']}: blended vertices; this model is not node-rigid")
        tri = p["joint"][p["idx"].reshape(-1, 3)]
        if np.any(tri != tri[:, :1]):
            sys.exit(f"{p['material']}: a triangle spans two nodes; this model is not node-rigid")




def lit(prims, shaders, textures):
    """merge_ce_scene's object treatment, for one placement under the default
    lighting: `<shader>__lmobj` sections, an incident direction per vertex
    whose dot with the normal is that vertex's share of the page's texel."""
    from PIL import Image
    lighting = DEFAULT_OBJECT_LIGHTING
    out = []
    for p in prims:
        halo = {**p["extras"].get("halo", {}), "lightmap_index": "objects", "lightmap_texture": OBJECT_LIGHTING_PAGE}
        out.append({**p, "tan": tangents_for(p["nrm"]), "material": f"{p['material']}__lmobj", "extras": {"halo": halo}})
    colours = [light_vertices(q["nrm"], lighting) for q in out]
    peak = np.clip(np.max(np.concatenate(colours), axis=0), 1e-3, 1.0)
    column = BLOCK * PER_ROW
    wid, hgt = column * COLUMNS, BLOCK
    uv = (0.5 * BLOCK / wid, 0.5)
    for q, colour in zip(out, colours):
        share = np.clip((colour @ LUMA) / float(peak @ LUMA), 0.0, 1.0)[:, None]
        q["inc"] = share * q["nrm"] + np.sqrt(1.0 - share * share) * q["tan"][:, :3]
        q["uv1"] = np.tile(uv, (len(q["pos"]), 1))
    page = np.zeros((hgt, wid, 3), dtype=np.uint8)
    for c, colour in enumerate([peak, lighting[2]] + change_colors({})):
        page[:, c * column:c * column + BLOCK] = np.round(np.clip(colour, 0.0, 1.0) * 255.0)
    Image.fromarray(page, "RGB").save(os.path.join(textures, OBJECT_LIGHTING_PAGE))
    return with_decal_offset(with_passes(out, shaders), shaders)


def strings(v):
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for x in v.values():
            yield from strings(x)
    elif isinstance(v, list):
        for x in v:
            yield from strings(x)


def small_staging(staging, dest, shaders):
    """This model's shaders and their bitmaps: the spec then lists those alone
    (a whole staging's lens flares and fog are the map's, not the vehicle's)."""
    textures = os.path.join(dest, "textures")
    os.makedirs(textures, exist_ok=True)
    json.dump(shaders, open(os.path.join(dest, "materials.json"), "w", encoding="utf-8"))
    for s in strings(shaders):
        stem, ext = os.path.splitext(s)
        if ext.lower() in (".png", ".dds"):
            for e in (".png", ".dds"):
                src = os.path.join(staging, "textures", stem + e)
                if os.path.exists(src):
                    shutil.copyfile(src, os.path.join(textures, stem + e))
    return textures


def to_local(p, world):
    """A primitive in a node's space; `world` is kept for the read-back."""
    r, t = world[:3, :3], world[:3, 3]
    tan = p["tan"].copy()
    tan[:, :3] = p["tan"][:, :3] @ r
    return {**p, "world": p["pos"], "pos": (p["pos"] - t) @ r, "nrm": p["nrm"] @ r, "tan": tan, "inc": p["inc"] @ r}


def anchored(prims):
    """Add two unused vertices to the last primitive, opposite each other about
    the origin, so mesh_rewrite's box is centred on it. Returns the primitives
    and the box's half size in metres, never under the donor's."""
    reach = np.max(np.abs(np.concatenate([p["pos"] for p in prims])), axis=0)
    half = max(DONOR_HALF, math.ceil(float(reach.max()) * 100) / 100)
    corner = reach.copy()
    corner[int(np.argmax(reach))] = half
    last = dict(prims[-1])
    two = np.array([corner, -corner])
    last["pos"] = np.vstack([last["pos"], two])
    last["nrm"] = np.vstack([last["nrm"], [[0, 1, 0]] * 2])
    last["tan"] = np.vstack([last["tan"], [[1, 0, 0, 1]] * 2])
    last["uv0"] = np.vstack([last["uv0"], np.zeros((2, 2))])
    last["uv1"] = np.vstack([last["uv1"], np.zeros((2, 2))])
    last["inc"] = np.vstack([last["inc"], np.zeros((2, 3))])
    return prims[:-1] + [last], half


def quat(r):
    """A rotation matrix's quaternion, x y z w, w >= 0."""
    t = np.trace(r)
    if t > 0:
        s = math.sqrt(t + 1.0) * 2
        q = [(r[2, 1] - r[1, 2]) / s, (r[0, 2] - r[2, 0]) / s, (r[1, 0] - r[0, 1]) / s, s / 4]
    else:
        i = int(np.argmax(np.diag(r)))
        j, k = (i + 1) % 3, (i + 2) % 3
        s = math.sqrt(1.0 + r[i, i] - r[j, j] - r[k, k]) * 2
        q = [0.0, 0.0, 0.0, (r[k, j] - r[j, k]) / s]
        q[i], q[j], q[k] = s / 4, (r[j, i] + r[i, j]) / s, (r[k, i] + r[i, k]) / s
    return [float(x) for x in (-np.array(q) if q[3] < 0 else np.array(q))]


def rest(m):
    """A transform in glTF axes as Unreal cm and CE world units."""
    return {"ue_cm": {"translation": [float(x) for x in TO_UE @ m[:3, 3] * 100],
                      "rotation_xyzw": quat(TO_UE @ m[:3, :3] @ TO_UE.T)},
            "ce_wu": {"translation": [float(x) for x in TO_CE @ m[:3, 3] / WU_M],
                      "rotation_xyzw": quat(TO_CE @ m[:3, :3] @ TO_CE.T)}}


def rotate(q, v):
    """FQuat's RotateVector, on rows."""
    u, w = np.array(q[:3]), q[3]
    t = 2 * np.cross(u, v)
    return v + w * t + np.cross(u, t)


def read_back(uasset, prims, half, item):
    """The vertex buffer as the package holds it, through the manifest's
    transforms, against the staged model. Returns the worst miss in cm."""
    pos = np.concatenate([p["pos"] for p in prims]).astype(np.float32)
    # mesh_rewrite's own arithmetic, in single precision.
    cm = (pos[:, [0, 2, 1]] * np.float32(100.0)).astype(np.float32)
    fit = np.float32(50.0) / np.float32(half * 100)
    want = (cm * fit).astype("<f4")
    blob = open(uasset, "rb").read()
    at = blob.find(want.tobytes())
    if at < 0:
        sys.exit(f"{uasset}: its vertex buffer is not in the package")
    got = np.frombuffer(blob, dtype="<f4", count=want.size, offset=at).reshape(-1, 3).astype(float)
    got = got[:-2] * item["component_scale"]  # the two anchors stay in the buffer.
    r = item["rest_vehicle"]["ue_cm"]
    placed = rotate(r["rotation_xyzw"], got) + np.array(r["translation"])
    staged = np.concatenate([p["world"] for p in prims]) @ TO_UE.T * 100
    return float(np.abs(placed - staged).max())


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for n in ("staging", "model", "code", "name", "out"):
        ap.add_argument(n)
    ap.add_argument("--paks", default=os.environ.get("HCE_PAKS"))
    repo = os.path.dirname(os.path.dirname(HERE))
    ap.add_argument("--repo", default=repo)
    ap.add_argument("--examples", default=os.path.join(repo, "target", "release", "examples"))
    ap.add_argument("--instances", help="ce_vehicle_materials.py's <name>.instances.json")
    a = ap.parse_args()
    if not a.paks:
        sys.exit("--paks or HCE_PAKS: Meteorite/Content/Paks")
    a.out = os.path.abspath(a.out)
    os.makedirs(a.out, exist_ok=True)
    code = a.code.upper()
    root = f"/Game/MJOLNIR/Maps/{code}"

    g, buf = load_gltf(os.path.join(a.staging, a.model))
    prims = primitives(g, buf)
    rigid_check(g, buf, prims)
    worlds, parent = node_worlds(g)
    joints = g["skins"][0]["joints"]
    every = json.load(open(os.path.join(a.staging, "materials.json"), encoding="utf-8"))
    shaders = {p["material"]: every[p["material"]] for p in prims}
    small = os.path.join(a.out, "staging")
    textures = small_staging(a.staging, small, shaders)
    sections = lit(prims, shaders, textures)

    # Each node's sections: opaque, then transparent.
    leaves = []
    for k, j in enumerate(joints):
        node = re.sub(r"[^A-Za-z0-9_]", "_", g["nodes"][j]["name"].removeprefix("frame "))
        for clear, suffix in ((False, ""), (True, "_t")):
            parts = []
            for p in sections:
                if (p["extras"]["halo"].get("shader_class") in TRANSPARENT) != clear:
                    continue
                tri = p["idx"].reshape(-1, 3)
                sel = tri[p["joint"][tri[:, 0]] == k]
                if len(sel):
                    parts.append(to_local(compact({**p, "joint": None, "idx": sel.reshape(-1)}), worlds[j]))
            if parts:
                leaves.append({"k": k, "j": j, "node": node, "leaf": f"SM_{code}_{a.name}_{node}{suffix}", "prims": parts,
                               "clear": clear})

    # The gltfs first: the spec reads their materials.
    for item in leaves:
        item["padded"], item["half"] = anchored(item["prims"])
        item["gltf"] = os.path.join(a.out, item["leaf"] + ".gltf")
        write_gltf(item["padded"], item["gltf"])
    spec_path = os.path.join(a.out, "materials.spec.json")
    subprocess.run([sys.executable, os.path.join(HERE, "ce_material_spec.py"), "--code", code, small, a.name.lower(), spec_path]
                   + [i["gltf"] for i in leaves], check=True)
    spec = json.load(open(spec_path, encoding="utf-8"))
    by_pattern = {s["pattern"]: s for s in spec["slots"]}
    instance = {}
    if a.instances:
        instance = {e["material"]: e["package"] for e in json.load(open(a.instances, encoding="utf-8"))["instances"]}
        missing = sorted({s["name"] for s in spec["slots"]} - set(instance))
        if missing:
            sys.exit(f"{a.instances} has no instance for {missing}: run ce_vehicle_materials.py on this spec")

    tool = SimpleNamespace(examples=a.examples, paks=a.paks, out=a.out, repo=a.repo)
    meshes, added, worst = [], [], 0.0
    for item in leaves:
        leaf = item["leaf"]
        names = []
        for p in item["prims"]:
            if p["material"] not in names:
                names.append(p["material"])
        slots = [by_pattern[n.lower() + "$"] for n in names]
        lines = [f"{root}/{leaf}"]
        for k, s in enumerate(slots):
            package = instance.get(s["name"]) or s["material"]["parent"].split(".")[0]
            lines += ["--material", f"s_{s['name']}={package}={s['pattern']}" + ("|*" if k == 0 else "")]
        lines.append("--asset-imports")
        (x, y, z, scale), uasset = rewrite(tool, item["gltf"], "basicshapes/cube", f"{root}/{leaf}", lines, leaf)
        want = item["half"] / DONOR_HALF
        if max(abs(x), abs(y), abs(z)) > 0.05 or abs(scale - want) > 1e-3:
            sys.exit(f"{leaf}: mesh_rewrite moved it: ({x}, {y}, {z}) at {scale}, wanted the origin at {want}")
        added += ["--package", f"{root}/{leaf}={uasset}"]
        passless = [p for p in item["prims"] if "pass" not in p["extras"]["halo"]]
        entry = {
            "soft_path": f"{root}/{leaf}.{leaf}", "node": item["node"], "node_index": item["k"],
            "translucent": item["clear"], "component_scale": want,
            "rest_vehicle": rest(worlds[item["j"]]),
            "triangles": sum(len(p["idx"]) // 3 for p in passless),
            "section_triangles": sum(len(p["idx"]) // 3 for p in item["prims"]),
            "vertices": sum(len(p["pos"]) for p in item["prims"]),
            "extent_cm": [float(v) for v in TO_UE @ np.max(np.abs(np.concatenate([p["pos"] for p in item["prims"]])), axis=0) * 100],
            "material_slots": [{"slot": f"s_{s['name']}", "index": k, "material": s["name"], "parent": s["material"]["parent"],
                                "instance": instance.get(s["name"])}
                               for k, s in enumerate(slots)],
        }
        miss = read_back(uasset, item["padded"], item["half"], entry)
        entry["read_back_miss_cm"] = miss
        worst = max(worst, miss)
        meshes.append(entry)
        print(f"  {leaf}: {entry['triangles']} triangle(s), scale {want:.2f}, read back within {miss:.4f} cm")

    total = sum(m["triangles"] for m in meshes)
    staged = sum(len(p["idx"]) // 3 for p in prims)
    if total != staged:
        sys.exit(f"{total} triangle(s) in the meshes, {staged} staged")

    container = f"pakchunk986-MJOLNIRMESH-{code}_P"
    po = subprocess.run([os.path.join(a.examples, "package_add.exe"), a.paks, a.out, "--name", container] + added,
                        cwd=a.repo, capture_output=True, text=True)
    print(po.stdout.strip()[-300:])
    if po.returncode != 0:
        sys.exit(f"package_add failed:\n{po.stderr[-2000:]}")
    # The game mounts a .utoc/.ucas pair only beside a .pak.
    shutil.copyfile(os.path.join(a.paks, "pakchunk115-Windows.pak"), os.path.join(a.out, container + ".pak"))

    index = {j: k for k, j in enumerate(joints)}
    nodes = []
    for k, j in enumerate(joints):
        up = parent.get(j)
        relative = worlds[j] if up is None else np.linalg.inv(worlds[up]) @ worlds[j]
        nodes.append({"index": k, "name": g["nodes"][j]["name"], "parent": index.get(up, -1), "rest_vehicle": rest(worlds[j]),
                      "rest_parent": rest(relative), "meshes": [m["soft_path"] for m in meshes if m["node_index"] == k]})
    manifest = {"model": a.model, "container": container, "code": code, "triangles": total, "read_back_miss_cm": worst,
                "units": {"ue_cm": "(x, -y, z) * 304.8 of CE", "ce_wu": "CE world units"},
                "scale_note": "mesh vertices are stored at 1/component_scale; origin is the node",
                "materials_spec": os.path.basename(spec_path), "nodes": nodes, "meshes": meshes}
    json.dump(manifest, open(os.path.join(a.out, f"{a.name.lower()}.manifest.json"), "w", encoding="utf-8"), indent=1)
    print(f"{len(meshes)} mesh(es), {total} triangle(s), read back within {worst:.4f} cm -> {a.out}")


if __name__ == "__main__":
    main()

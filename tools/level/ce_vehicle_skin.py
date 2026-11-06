#!/usr/bin/env python3
"""Turn a staged CE model into one skinned glTF, with bones named as its nodes.

    ce_vehicle_skin.py <staging> <models/x__vehi.gltf> <Name> <out dir>

`staging` is a fresh halo2ue export. Writes to <out dir>:

- <Name>.skinned.gltf: every section of the model on one skin. Bone weights
  are the model's own, so a blended vertex stays blended. Sections are lit as
  ce_vehicle_mesh.py lights them, with the incident direction packed into the
  vertex colour by the same rule mesh_rewrite follows.
- bones.json: the ordered bones, their parents and rest transforms in tag space
  and in Unreal's, with each node's tag name and its bone name.
- staging/: this model's shaders and bitmaps, for ce_material_spec.py.

Then, in the Meteorite project: ce_material_spec.py on the glTF,
ce_vehicle_materials.py --masters /Game/MJOLNIR/CESkinned, the masters
(Scripts/build_ce_skinned_masters.py), the instances, ce_vehicle_skin_editor.py,
a cook and its retarget. Extract SK_<stem> and SKEL_<stem> from their chunk, run
skin_uv on the mesh, and hand them to ce_vehicle_rig.py.

Rules, none of them per vehicle:

- The sim hands the animation Blueprint one local transform per node: the
  translation in world units as (x, -y, z) * 304.8, and the node's name read
  from its string id with spaces turned to underscores, measured: `frame hull`
  arrives as `frame_hull`. A bone takes that transform only if the names agree,
  so a bone is named by bone_name(), and its parent is its node's parent. Tags
  keep CE's name. A bone whose name is off stays at its bind pose, silently.
- A root node has to sit at the object's origin: a vehicle whose root does not
  floats by that offset. CE's root often sits off it, on the hull. When it does,
  ORIGIN_ROOT goes above it at the identity, as every shipped vehicle's first
  node sits, and each CE node keeps its own local transform and its true place.
  Node indices in skel, coll, phmo and jmad then shift up by one.
- The bind pose is CE's default node pose at true scale.
- The donor's lights hang from names like `VFX_Headlight_L`. Each name is a bone
  here, with no skin on it and no tag node, on CE's own `headlight` or `taillight`
  marker, left to right, so the Blueprint's lights and their switching stay and
  land on the model. The sim moves only bones it has a node for. A light with no
  CE marker has no bone, and ce_vehicle_rig.py leaves it out. CE's markers can sit
  behind the body, where a glow would be buried, so each moves along its own
  facing until it clears the model's surface.
- Unreal's skeletal import keeps one UV channel; `second_uv` is the constant
  skin_uv.rs restores.
"""
import argparse
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ce_vehicle_mesh import TO_CE, TO_UE, lit, node_worlds, quat, rest, small_staging  # noqa: E402
from merge_ce_scene import accessor, load_gltf, primitives  # noqa: E402

WU_CM = 304.8
ORIGIN_ROOT = "pedestal"
# The Warthog's light attach names, left to right as the driver sees them.
LIGHT_BONES = {"headlight": ("VFX_Headlight_L", "VFX_Headlight_LMid", "VFX_Headlight_RMid", "VFX_Headlight_R"),
                 "taillight": ("VFX_Taillight_L", "VFX_Taillight_R")}


def bone_name(name):
    """The bone for a tag node called `name`: what the sim calls it in Unreal."""
    return name.strip().replace(" ", "_")


def is_identity(m, tolerance=1e-6):
    return float(np.abs(m - np.eye(4)).max()) < tolerance


def bone_list(g):
    """The model's joints as bones, a root at the origin first if it needs one.
    Each bone: name, parent (a bone index, -1 for the root), its local and
    object-space matrix in glTF axes, and the joint index it stands for."""
    worlds, parent = node_worlds(g)
    joints = g["skins"][0]["joints"]
    index = {j: k for k, j in enumerate(joints)}
    roots = [k for k, j in enumerate(joints) if parent.get(j) not in index]
    if len(roots) != 1:
        sys.exit(f"{len(roots)} root nodes; a skeleton has one")
    names = [g["nodes"][j]["name"] for j in joints]
    repeats = {n for n in names if names.count(n) > 1}
    if repeats:
        sys.exit(f"nodes share a name, so a bone cannot tell them apart: {sorted(repeats)}")
    clashes = {bone_name(n) for n in names}
    if len(clashes) != len(names):
        sys.exit("two node names become one bone name")
    added = 0 if is_identity(worlds[joints[roots[0]]]) else 1
    if added and ORIGIN_ROOT in names:
        sys.exit(f"the model has a node named {ORIGIN_ROOT} off the origin")
    bones = []
    if added:
        bones.append({"name": ORIGIN_ROOT, "parent": -1, "local": np.eye(4), "object": np.eye(4), "joint": None})
    for k, j in enumerate(joints):
        up = index.get(parent.get(j))
        local = worlds[j] if up is None else np.linalg.inv(worlds[joints[up]]) @ worlds[j]
        bones.append({"name": names[k], "parent": -1 if up is None and not added else (0 if up is None else up + added),
                      "local": local, "object": worlds[j], "joint": k})
    return bones, added


def constant_uv(sections):
    """The second UV channel, which the object lighting page keeps at one texel.
    The skinned import drops the channel, and crates/ue-asset/examples/skin_uv.rs
    puts it back as this one value."""
    every = np.concatenate([np.asarray(s["uv1"], dtype=float) for s in sections])
    if np.ptp(every, axis=0).max() > 1e-6:
        sys.exit("the second UV channel varies; skin_uv.rs writes a constant")
    return [float(x) for x in every[0]]


def light_bones(markers, rows):
    """The bones for a model's light markers, each under its node's bone. `markers`
    are CE's (`name`, `node`, `t` in the node's space in wu, `q`), `rows` the
    manifest's bones. A location is in the bone's space in cm; a rotation x y z w
    in Unreal's axes. Spare markers or names stay unused, outermost first."""
    lights = []
    for kind, names in LIGHT_BONES.items():
        found = sorted((m for m in markers if m["name"] == kind), key=lambda m: -m["t"][1])
        if len(found) > len(names):  # the inner pair of a row longer than the donor's goes
            found = found[:(len(names) + 1) // 2] + found[-(len(names) // 2):]
        used = names if len(found) == len(names) else names[:1] + names[-1:] if len(found) == 2 else names[:len(found)]
        for name, m in zip(used, found):
            bone = next(r["bone"] for r in rows if r["ce_node"] == m["node"])
            x, y, z, w = m["q"]
            # A marker stores the conjugate; Unreal's axes flip x and z of that.
            lights.append({"name": name, "bone": bone,
                           "location": [m["t"][0] * WU_CM, -m["t"][1] * WU_CM, m["t"][2] * WU_CM],
                           "rotation": [x, -y, z, w]})
    return lights


def clear_of_body(lights, parents, points, reach=6.0, gap=1.0):
    """Move each light along its facing until `gap` cm past the surface within
    `reach` cm of its line. `points` are the model's vertices in Unreal's object
    space, and `parents` each bone's place there, by name."""
    for row in lights:
        facing = rotation_matrix(row["rotation"])[:, 0]
        at = np.array(row["location"]) + parents[row["bone"]]
        along = (points - at) @ facing
        beside = np.linalg.norm((points - at) - np.outer(along, facing), axis=1)
        near = along[beside < reach]
        if near.size and near.max() + gap > 0:
            row["location"] = [float(v) for v in np.array(row["location"]) + facing * (near.max() + gap)]


def rotation_matrix(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def light_joints(lights, bones):
    """`light_bones` rows as joints after `bones`, in the glTF's axes and metres."""
    joints = []
    for row in lights:
        parent = next(i for i, b in enumerate(bones) if bone_name(b["name"]) == row["bone"])
        local = np.eye(4)
        local[:3, :3] = TO_UE.T @ rotation_matrix(row["rotation"]) @ TO_UE
        local[:3, 3] = TO_UE.T @ np.array(row["location"]) / 100
        joints.append({"name": row["name"], "parent": parent, "local": local, "object": bones[parent]["object"] @ local})
    return joints


def bones_manifest(bones, added, model):
    """bones.json: what the tags and the mesh have to agree on. `name` is the
    string skel, coll, phmo and jmad carry, `bone` the mesh's name for it."""
    rows = []
    for i, b in enumerate(bones):
        here, there = rest(b["local"]), rest(b["object"])
        rows.append({"index": i, "name": b["name"], "bone": bone_name(b["name"]), "parent": b["parent"],
                     "parent_name": bones[b["parent"]]["name"] if b["parent"] >= 0 else None,
                     "ce_node": b["joint"], "tag_local": here["ce_wu"], "ue_local": here["ue_cm"],
                     "tag_object": there["ce_wu"], "ue_object": there["ue_cm"]})
    return {"model": model, "origin_root_added": bool(added), "node_index_shift": added, "wu_cm": WU_CM,
            "contract": {"node_count": len(bones), "tags_carry": "name",
                         "node_index": "a CE node index plus node_index_shift; bone 0 is a real tag node when added",
                         "bone": "the name in the mesh and skeleton; the sim turns name into this"},
            "units": {"tag": "world units, x y z and the rotation as a tag stores it",
                      "ue": "centimetres, (x, -y, z) of the tag's; rotation (-x, y, -z, w) of the tag's"},
            "bones": rows}


def skin_of(g, buf):
    """Per primitive, the JOINTS_0 and WEIGHTS_0 arrays, in primitives()'s order."""
    out = []
    for node in g["nodes"]:
        if "mesh" not in node:
            continue
        for p in g["meshes"][node["mesh"]]["primitives"]:
            out.append((accessor(g, buf, p["attributes"]["JOINTS_0"]).astype(np.uint16),
                        accessor(g, buf, p["attributes"]["WEIGHTS_0"]).astype(np.float32)))
    return out


def pack_incident(p):
    """The incident direction in each vertex's tangent frame, as mesh_rewrite
    packs it: rgb the unit vector at 0.5 + 0.5 v, alpha its length."""
    n = p["nrm"] / np.maximum(np.linalg.norm(p["nrm"], axis=1, keepdims=True), 1e-9)
    t = p["tan"][:, :3] - n * np.sum(p["tan"][:, :3] * n, axis=1, keepdims=True)
    t = t / np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-9)
    b = np.cross(n, t) * p["tan"][:, 3:4]
    length = np.linalg.norm(p["inc"], axis=1, keepdims=True)
    d = p["inc"] / np.maximum(length, 1e-6) * (length > 1e-6)
    frame = np.stack([np.sum(t * d, axis=1), np.sum(b * d, axis=1), np.sum(n * d, axis=1)], axis=1)
    rgb = np.round((np.clip(frame, -1, 1) * 0.5 + 0.5) * 255)
    alpha = np.round(np.clip(length, 0, 1) * 255)
    return np.hstack([rgb, alpha]).astype(np.uint8)


def write_skinned(path, bones, sections):
    """One glTF: bones first, then one mesh of `sections`, one primitive each."""
    blob = bytearray()
    views, accessors = [], []

    def add(data, ctype, kind, target=None, normalized=False):
        data = np.ascontiguousarray(data)
        if data.dtype.itemsize != {5126: 4, 5125: 4, 5123: 2, 5121: 1}[ctype]:
            sys.exit(f"{data.dtype} under glTF component type {ctype}")
        while len(blob) % 4:
            blob.append(0)
        view = {"buffer": 0, "byteOffset": len(blob), "byteLength": data.nbytes}
        if target:
            view["target"] = target
        blob.extend(data.tobytes())
        views.append(view)
        acc = {"bufferView": len(views) - 1, "componentType": ctype, "count": len(data), "type": kind}
        if kind == "VEC3" and ctype == 5126:
            acc["min"], acc["max"] = data.min(0).tolist(), data.max(0).tolist()
        if normalized:
            acc["normalized"] = True
        accessors.append(acc)
        return len(accessors) - 1

    # glTF to Unreal is a mirror, which the import applies to a tangent's vector
    # and not to its handedness, so the file carries the sign Unreal needs.
    f32 = lambda x: np.asarray(x, dtype=np.float32)  # noqa: E731
    materials, by_name, prims = [], {}, []
    for s in sections:
        if s["material"] not in by_name:
            by_name[s["material"]] = len(materials)
            materials.append({"name": s["material"], "extras": s.get("extras", {})})
        attributes = {"POSITION": add(f32(s["pos"]), 5126, "VEC3", 34962), "NORMAL": add(f32(s["nrm"]), 5126, "VEC3", 34962),
                      "TANGENT": add(f32(s["tan"]) * f32([1, 1, 1, -1]), 5126, "VEC4", 34962), "TEXCOORD_0": add(f32(s["uv0"]), 5126, "VEC2", 34962),
                      "TEXCOORD_1": add(f32(s["uv1"]), 5126, "VEC2", 34962),
                      "COLOR_0": add(pack_incident(s), 5121, "VEC4", 34962, normalized=True),
                      "JOINTS_0": add(s["joints"], 5123, "VEC4", 34962), "WEIGHTS_0": add(s["weights"], 5126, "VEC4", 34962)}
        indices = add(np.asarray(s["idx"], dtype=np.uint32), 5125, "SCALAR", 34963)
        prims.append({"attributes": attributes, "indices": indices, "material": by_name[s["material"]], "mode": 4})
    binds = b"".join(f32(np.linalg.inv(b["object"]).T).tobytes() for b in bones)
    ib = add(np.frombuffer(binds, dtype=np.float32).reshape(-1, 16), 5126, "MAT4")
    nodes = []
    for i, b in enumerate(bones):
        n = {"name": bone_name(b["name"]), "translation": [float(v) for v in b["local"][:3, 3]], "rotation": quat(b["local"][:3, :3])}
        kids = [k for k, c in enumerate(bones) if c["parent"] == i]
        if kids:
            n["children"] = kids
        nodes.append(n)
    nodes.append({"name": "model", "mesh": 0, "skin": 0})
    bin_name = os.path.splitext(os.path.basename(path))[0] + ".bin"
    with open(os.path.join(os.path.dirname(os.path.abspath(path)), bin_name), "wb") as f:
        f.write(blob)
    root = next(i for i, b in enumerate(bones) if b["parent"] < 0)
    doc = {"asset": {"version": "2.0", "generator": "ce_vehicle_skin"}, "scene": 0,
           "scenes": [{"nodes": [root, len(nodes) - 1]}], "nodes": nodes, "materials": materials,
           "meshes": [{"primitives": prims}], "accessors": accessors, "bufferViews": views,
           "skins": [{"joints": list(range(len(bones))), "inverseBindMatrices": ib, "skeleton": root}],
           "buffers": [{"byteLength": len(blob), "uri": bin_name}]}
    json.dump(doc, open(path, "w", encoding="utf-8"))


def check_binding(bones, sections, added):
    """Every weight names a real bone, and each vertex's weights sum to one."""
    for s in sections:
        used = s["joints"][s["weights"] > 0]
        if used.size and (used.max() >= len(bones) or (added and used.min() < added)):
            sys.exit(f"{s['material']}: a weight on a bone outside the skin")
        if np.abs(s["weights"].sum(axis=1) - 1).max() > 1e-3:
            sys.exit(f"{s['material']}: weights that do not sum to one")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for n in ("staging", "model", "name", "out"):
        ap.add_argument(n)
    ap.add_argument("--bones-only", action="store_true", help="write bones.json and stop")
    ap.add_argument("--markers", help="JSON with the model's CE `markers`, for the light bones")
    a = ap.parse_args()
    a.out = os.path.abspath(a.out)
    os.makedirs(a.out, exist_ok=True)

    g, buf = load_gltf(os.path.join(a.staging, a.model))
    bones, added = bone_list(g)
    manifest = bones_manifest(bones, added, a.model)
    if a.markers:
        markers = json.load(open(a.markers, encoding="utf-8"))["markers"]
        manifest["light_bones"] = light_bones(markers, manifest["bones"])
    bones_path = os.path.join(a.out, "bones.json")
    json.dump(manifest, open(bones_path, "w", encoding="utf-8"), indent=1)
    print(f"{len(bones)} bone(s), root {bones[0]['name']}{' (added)' if added else ''}")
    if a.bones_only:
        return

    prims = primitives(g, buf)
    for p, (joints, weights) in zip(prims, skin_of(g, buf)):
        p["joints"], p["weights"] = (joints + added * (weights > 0)).astype(np.uint16), weights
    every = json.load(open(os.path.join(a.staging, "materials.json"), encoding="utf-8"))
    shaders = {p["material"]: every[p["material"]] for p in prims}
    textures = small_staging(a.staging, os.path.join(a.out, "staging"), shaders)
    sections = lit(prims, shaders, textures)
    check_binding(bones, sections, added)
    if "light_bones" in manifest:
        points = np.concatenate([s["pos"] for s in sections]) @ TO_UE.T * 100
        parents = {r["bone"]: np.array(r["ue_object"]["translation"]) for r in manifest["bones"]}
        clear_of_body(manifest["light_bones"], parents, points)
    manifest["second_uv"] = constant_uv(sections)
    json.dump(manifest, open(bones_path, "w", encoding="utf-8"), indent=1)
    path = os.path.join(a.out, f"{a.name}.skinned.gltf")
    write_skinned(path, bones + light_joints(manifest.get("light_bones", []), bones), sections)
    blended = sum(int(np.count_nonzero(s["weights"][:, 1] > 0)) for s in sections)
    vertices = sum(len(s["pos"]) for s in sections)
    print(f"{len(sections)} section(s), {vertices} vertices, {blended} blended -> {path}")


if __name__ == "__main__":
    main()

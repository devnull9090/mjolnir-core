"""Prepare a one-instance open-crown variation from intact original native branch sprays."""

import json
import struct

import numpy as np
from heightfield import load_heightfield
from prepare_sweep_bend_pine import ART as PREVIOUS
from prepare_sweep_bend_pine import FIELD, ROOT, SCALE, SOURCE, YAW, read, save
from scipy.optimize import linear_sum_assignment
from scipy.spatial import cKDTree
from scipy.spatial.distance import cdist
from verify_conifer_attributes_v4 import digest
from verify_conifer_attributes_v4 import read as read_glb

ART = PREVIOUS.parents[1] / "round22/pine"
MESH = "/Game/MJOLNIR/GrassPilot/Playable/SM_PWR_SweepBendPine_OpenA"
ORIGINAL = SOURCE / "mature-pine-a.glb"
ARCHIVE_SHA = "68bdcb09e0af2dc2030b50b543f45d28a7284264bd7ce188484759b320cdf405"
# Each small area is surveyed on real terrain through the approved native camera.
# Selection removes entire measured needle sprays which interrupt sunlight there.
WINDOWS = {
    "left_near": (0.29, 0.961, 0.038, 0.027),
    "left_inside": (0.357, 0.904, 0.029, 0.017),
    "near_glint": (0.522, 0.824, 0.060, 0.034),
}
SUN = np.array([np.cos(np.radians(55)), np.sin(np.radians(55))]) / np.tan(
    np.radians(37)
)


def flatten(v):
    return v[..., :2] + v[..., 2, None] * SUN


def world(tris):
    c, s = np.cos(np.radians(YAW)), np.sin(np.radians(YAW))
    rot = np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]])
    return (
        np.asarray(read(PREVIOUS / "placement.json")["root_survey_m"])
        + tris @ rot * SCALE
    )


def receiver(field, u, v):
    pose = read(ROOT / "out/pwr/sweep-polish/round18/earth/roadbed.json")[
        "reference_camera_pose"
    ]
    eye = np.array(pose[:3]) * [0.01, -0.01, 0.01]
    p, y, f = np.radians(pose[3:])
    h = np.array([np.cos(y), -np.sin(y)])
    fw = np.r_[h * np.cos(p), np.sin(p)]
    rt = np.r_[-np.sin(y), -np.cos(y), 0]
    up = np.r_[-h * np.sin(p), np.cos(p)]
    rays = (
        fw
        + (u[..., None] - 0.5) * 2 * np.tan(f / 2) * rt
        + (0.5 - v[..., None]) * 2 * np.tan(f / 2) * (9 / 16) * up
    )
    low = np.zeros(u.shape)
    high = np.full(u.shape, 80.0)
    for _ in range(25):
        t = (low + high) / 2
        q = eye + t[..., None] * rays
        hit = q[..., 2] <= field.sample(q[..., 0], q[..., 1])
        high = np.where(hit, t, high)
        low = np.where(hit, low, t)
    return eye + high[..., None] * rays


def prim(d, a, j=1):
    p = d["meshes"][0]["primitives"][j]
    v = a(p["attributes"]["POSITION"])[:, [0, 2, 1]] * [1, -1, 1]
    return v[a(p["indices"]).reshape(-1, 3)], p


def whole_sprays(d, a):
    r = read(SOURCE / "source.json")
    leaf = next(x for x in r["assets"] if x["mesh"] == r["recipe"]["leaf_mesh"])
    g, k = read_glb(leaf["glb"])
    pr = g["meshes"][leaf["selected_lod"]]["primitives"][0]
    idx = k(pr["indices"]).reshape(-1, 3)
    verts = k(pr["attributes"]["POSITION"])[:, [0, 2, 1]] * [1, -1, 1]
    leaftris = verts[idx]
    original, _ = prim(d, a)
    n = len(idx)
    clusters = original.reshape(-1, n, 3, 3)
    nativefactor = 28 / 217.199
    F = np.diag([1.0, -1.0, 1.0])
    leaves = r["recipe"]["leaves"]
    src = np.stack(
        [
            leaftris @ (F @ np.array(item["m"]) @ F) * nativefactor
            + np.array(item["off"]) * [0.01, -0.01, 0.01] * nativefactor
            for item in leaves
        ]
    )
    # Verify each entire discrete group against the transformed original branch prototype,
    # including all corners, so no arbitrary authoring index group is mistaken for a bough.
    dist = cdist(clusters.mean((1, 2)), src.mean((1, 2)))
    rr, mapping = linear_sum_assignment(dist)
    dd = dist[rr, mapping]
    if len(set(mapping.tolist())) != len(leaves) or dd.max() > 0.001:
        raise ValueError(
            f"Expected 592 original spray transforms, deviation {dd.max()}"
        )
    err = max(
        cKDTree(src[j].reshape(-1, 3)).query(clusters[i].reshape(-1, 3))[0].max()
        for i, j in enumerate(mapping)
    )
    if err > 0.002:
        raise ValueError(f"Original spray geometry mismatch {err}")
    return clusters, mapping, float(err), leaf


def solar_hits(tris, points):
    p = flatten(tris.reshape(-1, 3, 3))
    lo = p.min(1)
    hi = p.max(1)
    found = set()
    for q in points:
        candidates = np.flatnonzero(((lo <= q) & (hi >= q)).all(1))
        tr = p[candidates]
        d = q - tr[:, 0]
        s = tr[:, 1] - tr[:, 0]
        t = tr[:, 2] - tr[:, 0]
        cr = lambda a, b: a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]
        den = cr(s, t)
        den = np.where(abs(den) > 1e-12, den, np.nan)
        x = cr(d, t) / den
        y = cr(s, d) / den
        ids = candidates[(x >= 0) & (y >= 0) & (x + y <= 1)] // tris.shape[1]
        found.update(ids.tolist())
    return found


def pruned_glb(d, local, indices, target):
    raw = ORIGINAL.read_bytes()
    n = struct.unpack_from("<I", raw, 12)[0]
    bin0 = raw[28 + n :]
    prev = d["accessors"][local["indices"]]
    typ = {5123: "<u2", 5125: "<u4"}[prev["componentType"]]
    blob = indices.astype(typ).tobytes()
    start = len(bin0)
    buf = bin0 + blob + b"\0" * ((-len(blob)) % 4)
    d["bufferViews"].append(
        {"buffer": 0, "byteOffset": start, "byteLength": len(blob), "target": 34963}
    )
    d["accessors"].append(
        {
            "bufferView": len(d["bufferViews"]) - 1,
            "componentType": prev["componentType"],
            "count": indices.size,
            "type": "SCALAR",
            "min": [int(indices.min())],
            "max": [int(indices.max())],
        }
    )
    local["indices"] = len(d["accessors"]) - 1
    d["buffers"][0]["byteLength"] = len(buf)
    d["meshes"][0]["name"] = "SM_PWR_SweepBendPine_OpenA"
    d["nodes"][0]["name"] = d["meshes"][0]["name"]
    j = json.dumps(d, separators=(",", ":")).encode()
    j += b" " * ((-len(j)) % 4)
    target.write_bytes(
        struct.pack("<4sII", b"glTF", 2, 28 + len(j) + len(buf))
        + struct.pack("<I4s", len(j), b"JSON")
        + j
        + struct.pack("<I4s", len(buf), b"BIN\0")
        + buf
    )


def prepare():
    if digest(ORIGINAL) != ARCHIVE_SHA:
        raise ValueError("Different mature pine source")
    ART.mkdir(exist_ok=True, parents=True)
    field = load_heightfield(FIELD)
    doc, acc = read_glb(ORIGINAL)
    clusters, recipe_index, err, leaf = whole_sprays(doc, acc)
    transformed = world(clusters)
    by_window = {}
    for name, (u, v, rx, ry) in WINDOWS.items():
        aa, bb = np.meshgrid(np.linspace(-1, 1, 15), np.linspace(-1, 1, 13))
        ms = aa * aa + bb * bb < 1.0
        q = flatten(receiver(field, u + rx * aa[ms], v + ry * bb[ms]))
        by_window[name] = sorted(solar_hits(transformed, q))
    cuts = sorted(set().union(*by_window.values()))
    keep = np.ones(len(clusters), bool)
    keep[cuts] = False
    if not 0 < len(cuts) < 0.16 * len(clusters):
        raise ValueError(f"Unexpected spray count {len(cuts)}")
    bark, _wood = prim(doc, acc, 0)
    _, needles = prim(doc, acc, 1)
    index = acc(needles["indices"]).reshape(len(keep), -1)
    target = ART / "open-canopy.glb"
    pruned_glb(doc, needles, index[keep], target)
    rd, ra = read_glb(target)
    bt, _ = prim(rd, ra, 0)
    ft, _ = prim(rd, ra, 1)
    if not np.array_equal(bt, bark) or not np.array_equal(
        ft, clusters[keep].reshape(-1, 3, 3)
    ):
        raise ValueError("Unexpected surgery outside complete native sprays")
    spec = read(PREVIOUS / "verges.json")
    spec["groups"][0]["mesh"] = MESH + "." + MESH.split("/")[-1]
    save(ART / "verges.json", spec)
    for name in ["verges.bin", "verges.bin.xf1"]:
        (ART / name).write_bytes((PREVIOUS / name).read_bytes())
    result = {
        "schema": "pwr-one-pine-open-crown-v1",
        "original_sha256": ARCHIVE_SHA,
        "glb_sha256": digest(target),
        "original_mesh": "/Game/MJOLNIR/Scenery/PWR/SM_PWR_MaturePine_A",
        "target_mesh": MESH,
        "source_prototype": leaf["mesh"],
        "source_prototype_sha256": leaf["sha256"],
        "complete_spray_maximum_distance_to_transformed_original_m": err,
        "total_sprays": len(keep),
        "removed_sprays": len(cuts),
        "retained_sprays": int(keep.sum()),
        "removed_authoring_cluster_indices": cuts,
        "removed_original_recipe_indices": recipe_index[cuts].tolist(),
        "group_source_hits": by_window,
        "survey_window_uv": WINDOWS,
        "pruned_cluster_height_range_relative_pivot_m": [
            float(transformed[cuts][..., 2].min() - world(np.zeros(3))[2]),
            float(transformed[cuts][..., 2].max() - world(np.zeros(3))[2]),
        ],
        "wood_triangles_before_and_after": len(bark),
        "original_leaf_triangles": len(clusters) * clusters.shape[1],
        "retained_leaf_triangles": len(ft),
        "retained_wood_xyz_and_topology_exact": True,
        "all_retained_leaf_xyz_and_topology_exact": True,
        "all_vertex_attributes_and_uv_unchanged": True,
        "chunk": 965,
        "sun_pitch_deg": -37,
        "sun_yaw_deg": -55,
    }
    save(ART / "canopy.json", result)
    print(
        json.dumps(
            {
                k: v
                for k, v in result.items()
                if k
                not in (
                    "removed_authoring_cluster_indices",
                    "removed_original_recipe_indices",
                    "group_source_hits",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    prepare()

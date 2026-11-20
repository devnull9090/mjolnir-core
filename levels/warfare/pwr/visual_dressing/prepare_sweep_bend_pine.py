# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2,<3", "scipy", "pillow", "trimesh", "shapely>=2"]
# ///
"""Place one native mature pine in the Southwest stand and append only its measured stem."""

import argparse
import json
import struct
from pathlib import Path

import numpy as np
from build_mature_pine_collision import BARK, TRUNK, read_mesh
from heightfield import load_heightfield
from prepare_alpine_verges import (
    DISCS,
    FIELD,
    GEO,
    ROOT,
    TREES,
    append_foliage,
    read,
    sha256,
)
from scipy.spatial import ConvexHull
from shapely.geometry import LineString, Point, Polygon, shape
from sweep_pine_trunk import compare, source

ART = ROOT / "out/pwr/sweep-polish/round21/pine"
PARENT = ROOT / "out/pwr/sweep-polish/round20"
DONOR = ROOT / "out/pwr/sweep-polish/round18/verges/physics"
SOURCE = ROOT / "out/pwr/visual-v5/outcrops-v4/trees"
MESH = "/Game/MJOLNIR/Scenery/PWR/SM_PWR_MaturePine_A.SM_PWR_MaturePine_A"
XY = np.array([-607.8, -565.4])
SCALE = 1.06
YAW = 170.0
STEM = "Southwest bend mature pine trunk"


def save(path, record):
    path.write_text(json.dumps(record, indent=2, allow_nan=False) + "\n")


def put(v, xyz):
    a = np.radians(YAW)
    c, s = np.cos(a), np.sin(a)
    # Source GLB helper returns native Unreal centimeters. Survey is metres with Y flipped.
    p = v * np.array([0.01, -0.01, 0.01]) * SCALE
    return xyz + np.c_[c * p[:, 0] - s * p[:, 1], s * p[:, 0] + c * p[:, 1], p[:, 2]]


def footprint(pts):
    xy = pts[:, :2]
    return Polygon(xy[ConvexHull(xy).vertices])


def survey(field, xyz, world):
    poly = footprint(world)
    roads = read(GEO)["roads"]
    gaps = {
        r["id"]: poly.distance(LineString(np.array(r["centreline_m"])[:, :2]))
        - r["width_m"] / 2
        - r["shoulder_m"]
        for r in roads
    }
    axes = [np.array(t["position"])[:2] for t in read(TREES)["instances"]]
    d = np.sort(np.linalg.norm(axes - xyz[:2], axis=1))
    discs = [
        (n, poly.distance(Point(q)) - r) for n, q, r in read(DISCS)["clearance_discs"]
    ]
    level = read(PARENT / "native-level.json")
    for k in ("player_starts", "vehicles"):
        discs.extend(
            (k, poly.distance(Point(np.array(o["pos"][:2]) * [0.01, -0.01])) - 12)
            for o in level["blam"][k]
        )
    discs.extend(
        (
            "map marker",
            poly.distance(Point(np.array(o["pos"][:2]) * [0.01, -0.01])) - 12,
        )
        for o in level["markers"]
    )
    discs.extend(
        ("hill", poly.distance(Point(x * 0.01, -y * 0.01)) - 0.01 * r - 5)
        for x, y, _, r, *_ in level["koth_hills"]
    )
    probes = read(
        ROOT / "out/pwr/world-v5/visual5/native-refresh/terrain-probe-plan.json"
    )
    discs.extend(
        (
            i["id"],
            poly.distance(Point(i["position_m"][:2]))
            - max(8, i.get("max_walk_metres", 0) + 4),
        )
        for i in probes["probes"]
    )
    pave = read(ROOT / "out/pwr/visual-v5/base-paving-v3/footprints.geojson")
    paving = min(poly.distance(shape(x["geometry"])) for x in pave["features"])
    from b30_collision import rotator_matrix

    rocks = []
    rockrows = read(
        ROOT / "out/pwr/visual-v6/scenery/rocks-and-outcrops.authored-decor.json"
    )["decor"]
    hulls = ROOT / "out/pwr/visual-v6/scenery/hulls"
    for o in rockrows:
        if np.linalg.norm(xyz[:2] - np.array(o["pos"][:2]) * [0.01, -0.01]) > 60:
            continue
        h = read(hulls / (o["mesh"].split(".")[-1] + ".json"))
        v = (
            np.array(h["points"]) * o["scale"] @ rotator_matrix(*o["rot"]) + o["pos"]
        ) * [0.01, -0.01, 0.01]
        rocks.append(poly.distance(footprint(v)))
    with np.load(
        ROOT / "out/pwr/sweep-polish/round18/verges/physical-surfaces.npz"
    ) as solids:
        rocks.extend(
            poly.distance(footprint(val.reshape(-1, 3))) for val in solids.values()
        )
    # Crown is fully on the far side of the camera plane and cannot occlude its near view.
    pose = read(ROOT / "out/pwr/sweep-polish/round18/earth/roadbed.json")[
        "reference_camera_pose"
    ]
    eye = np.array(pose[:3]) * [0.01, -0.01, 0.01]
    pitch, yaw = np.radians(pose[3:5])
    forward = np.array(
        [np.cos(pitch) * np.cos(yaw), -np.cos(pitch) * np.sin(yaw), np.sin(pitch)]
    )
    canopy_depth = (world - eye) @ forward
    if (
        min(gaps.values()) < 0.15
        or d[0] < 6.8
        or min(g for _, g in discs) < 0
        or min(rocks) <= 0
        or paving <= 0
        or canopy_depth.max() >= 0
    ):
        raise ValueError(
            "New pine violates a road, stand, structure or camera clearance"
        )
    levels = ["water", "road", "bases", "shore"]
    loc = np.vstack((np.array(poly.exterior.coords), xyz[None, :2]))
    masks = {
        key: float(np.max(field.sample_mask(key, loc[:, 0], loc[:, 1])))
        for key in levels
    }
    # The road raster feathers into established forest beyond the physical shoulders.
    # Use the original forest generator's full-strength raster core clearance, in addition
    # to exact full-crown distance to every surveyed road plus its full-width shoulders.
    ij = np.rint((xyz[:2] - field.origin_m) / field.spacing_m).astype(int)
    yi, xi = np.nonzero(field.masks["road"] >= 1 - 1e-7)
    core = float(
        np.min(
            np.linalg.norm((np.column_stack((xi, yi)) - ij) * field.spacing_m, axis=1)
        )
    )
    if core <= 8.9 or any(masks[k] > 0.002 for k in ("water", "bases", "shore")):
        raise ValueError("Tree enters a protected field mask")
    return {
        "root_survey_m": xyz.tolist(),
        "root_ue_cm": (xyz * [100, -100, 100]).tolist(),
        "authored_yaw_deg": YAW,
        "unreal_yaw_deg": -YAW,
        "scale": SCALE,
        "shoulder_clearance_whole_convex_crown_m": min(gaps.values()),
        "nearest_road": min(gaps, key=gaps.get),
        "nearest_trunk_axes_m": d[:4].tolist(),
        "minimum_protected_disc_buffer_m": min(g for _, g in discs),
        "minimum_rock_or_dressing_footprint_clearance_m": min(rocks),
        "minimum_paved_footprint_clearance_m": paving,
        "protected_masks": masks,
        "forest_road_core_clearance_m": core,
        "driver_view_mesh_depth_m": [
            float(canopy_depth.min()),
            float(canopy_depth.max()),
        ],
        "height_above_planting_pivot_m": float(world[:, 2].max() - xyz[2]),
    }


def prepare():
    ART.mkdir(parents=True, exist_ok=True)
    field = load_heightfield(FIELD)
    xyz = np.r_[XY, field.sample(*XY)]
    package = SOURCE / "native/package-readback.glb"
    full = np.vstack([read_mesh(package, 0, key)[0] for key in (BARK, "MI_Branch_Mat")])
    result = survey(field, xyz, put(full, xyz))
    recipe = read(SOURCE / "source.json")
    native = next(a for a in recipe["assets"] if a["mesh"] == TRUNK)
    raw = Path(native["glb"])
    if sha256(raw) != native["sha256"] or native["selected_lod"] != 1:
        raise ValueError("Different approved trunk source")
    verts, edges = source(raw)
    # The short sealed foot sits below the entire local ground surface. Buried,
    # unreachable roots underneath this foot never consume native surface keys.
    heights = [-12, 50, 170, 980, float(verts[:, 2].max())]
    p, f, report = compare(verts, edges, heights, 6, 0)
    if len(f) != 56 or report["continuous_max_enclosure_deficit_cm"] > 1e-4:
        raise ValueError("Invalid trunk closure")
    tri = p[f]
    volume = (
        np.sum(np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2]))) / 6
    )
    all_edges = np.concatenate((f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]))
    _ue, counts = np.unique(np.sort(all_edges, axis=1), return_counts=True, axis=0)
    if (
        volume <= 0
        or not np.all(counts == 2)
        or len(np.unique(all_edges, axis=0)) != len(all_edges)
    ):
        raise ValueError("Trunk shell is not closed and outward")
    proj = put(p, xyz)
    bottom = proj[:6]
    below = field.sample(bottom[:, 0], bottom[:, 1]) - bottom[:, 2]
    if below.min() < 0.025:
        raise ValueError("Ground does not seal the trunk foot")
    result.update(
        native_root_buried_m=float(xyz[2] - put(full, xyz)[:, 2].min()),
        physical_foot_soil_cover_m=below.tolist(),
        source_trunk_sha256=sha256(raw),
        packaged_tree_readback_sha256=sha256(package),
        original_trunk_points=len(verts),
        trunk_proxy_faces=len(f),
        trunk_proxy_volume_m3=volume * 1e-6 * SCALE**3,
        proxy_ring_heights_local_cm=heights,
        proxy_scope="Original wood trunk from below local soil to leader; all branches and needles are visual.",
        proxy_enclosure=report,
    )
    from trimesh import Trimesh
    from trimesh.proximity import closest_point_naive

    vv, ff, _ = read_mesh(raw, 1, BARK)
    mesh = Trimesh(vertices=vv * (28 / 217.199), faces=ff, process=False)
    side = tri[:48]
    pts = np.unique(
        np.vstack(
            (
                p,
                side.mean(1),
                (side[:, 0] + side[:, 1]) / 2,
                (side[:, 1] + side[:, 2]) / 2,
                (side[:, 2] + side[:, 0]) / 2,
            )
        ),
        axis=0,
    )
    gaps = (
        np.concatenate(
            [
                closest_point_naive(mesh, pts[i : i + 6])[1]
                for i in range(0, len(pts), 6)
            ]
        )
        * SCALE
    )
    result["placed_exact_nearest_bark_samples_cm"] = {
        k: {
            "count": int(m.sum()),
            "max": float(gaps[m].max()),
            "p95": float(np.quantile(gaps[m], 0.95)),
        }
        for k, m in [("foot_to_eye", pts[:, 2] <= 200), ("above_eye", pts[:, 2] > 200)]
    }
    if np.max(gaps) > 41:
        raise ValueError("Measured wood approximation exceeds about 0.4 m")
    # Serialize the same native transform for the actual HISM and the wood BSP.
    position = xyz * [100, -100, 100]
    half = np.radians(-YAW / 2)
    binary = ART / "verges.bin"
    binary.write_bytes(b"MJF3" + struct.pack("<II", 3, 0))
    append_foliage(binary, [[*position, -YAW, SCALE, 0, 0]])
    xf = ART / "verges.bin.xf1"
    xf.write_bytes(
        struct.pack(
            "<10f", *position, 0, 0, np.sin(half), np.cos(half), SCALE, SCALE, SCALE
        )
    )
    group = {
        "key": "Pine",
        "mesh": MESH,
        "material": None,
        "wpo": 0,
        "cull": [90000, 125000],
        "flags": 35,
        "count": 1,
        "exact": True,
        "transform_sha256": sha256(xf),
    }
    save(
        ART / "verges.json",
        {
            "actor": "PWR_SweepBendPine",
            "file": binary.name,
            "groups": [group],
            "count": 1,
            "binary_sha256": sha256(binary),
        },
    )
    save(ART / "placement.json", result)
    save(
        ART / "structural.json",
        [
            {
                "name": STEM,
                "faces": len(f),
                "mesh": MESH,
                "collision_scope": "trunk_only",
                "material": "tough_organic_wood",
                "placement_sha256": sha256(ART / "placement.json"),
            }
        ],
    )
    # Flipping from Unreal to survey reverses winding; restore the outward orientation.
    np.savez_compressed(ART / "physical-surfaces.npz", **{STEM: proj[f[:, [0, 2, 1]]]})
    print(json.dumps(result, indent=2))


def cook():
    from build_sweep_banks import collision

    old = read(PARENT / "saturday.20/receipt.json")["collision"]["sbsp"]
    collision(source=DONOR, art=ART, expected_bsp=old)


if __name__ == "__main__":
    op = argparse.ArgumentParser(description=__doc__)
    op.add_argument("--collision", action="store_true")
    args = op.parse_args()
    if args.collision:
        cook()
    else:
        prepare()

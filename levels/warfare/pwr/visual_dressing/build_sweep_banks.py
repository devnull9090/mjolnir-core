# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2,<3", "pillow", "scipy", "shapely"]
# ///
"""Build the surveyed Southwest banks, their native collision and instanced surface dressing."""

import argparse
from collections import defaultdict
from copy import deepcopy
import json
import struct
import subprocess
import sys

import numpy as np
from scipy.spatial.transform import Rotation
import sweep_bank_forms as forms

from prepare_sweep_forest_floor import Road, Site, smooth
from prepare_alpine_verges import (
    Camera,
    CLI,
    FOREST,
    PAKS,
    REVIEW,
    ROOT,
    read,
    sha256,
    append_foliage,
    lod0_points,
    witness_existing_collision,
)

BASE = ROOT / "out/pwr/alpine-target/verges"
SWEEP = ROOT / "out/pwr/sweep-polish"
OUT = SWEEP / "round16/verges"
REVISION = 16
FOLDER = "/Game/MJOLNIR/GrassPilot/Playable"
NOSNOW = "/Game/Env/Bio/Rock/Glacial/Rock_Glacial_Med_A/Materials/MI_Rock_Glacial_Med_A_NoSnow"
# Each island uses its own physical dimensions and its own portion of the texture atlas.
BANKS = [
    ("west outcrop", (-602.66, -531.8), (5.2, 2.80), -6, 0.93),
    ("west forest apron", (-601.2, -535.2), (5.10, 2.70), 24, 0.46),
    ("east road bank", (-577.53, -519.2), (16.85, 5.30), 72, 0.64),
    ("east root collar", (-570.5, -505.7), (9.55, 4.7), 55, 0.60),
]


def save(path, obj):
    path.write_text(json.dumps(obj, indent=2, allow_nan=False) + "\n")


def qpath(p):
    return p + "." + p.rsplit("/", 1)[-1]


def source_cols():
    return {r["key"]: r for r in read(BASE / "verges.json")["groups"]}


def to_xy(bank, lx, ly):
    _, center, (a, b), az, _ = bank
    v = np.radians(az)
    return np.stack(
        (
            center[0] + np.cos(v) * a * lx - np.sin(v) * b * ly,
            center[1] + np.sin(v) * a * lx + np.cos(v) * b * ly,
        ),
        axis=-1,
    )


def build_geometry():
    field = Site()
    road = Road(field)
    cam = Camera(read(REVIEW / "field-check-cameras.json")["cameras"][FOREST]["pose"])
    origin = np.array([-590.0, -524.0, 104.0])
    allv = []
    allf = []
    alluv = []
    support = []
    data = []
    proof = []
    fields = []
    for index, bank in enumerate(forms.BANKS if REVISION >= 17 else BANKS):
        rings, wedges = (4, 20) if index >= 4 else (7, 28)
        if REVISION == 18 and index in (2, 3):
            rings, wedges = 4, 18
        lx, ly = [0.0], [0.0]
        for ring in range(1, rings + 1):
            theta = 2 * np.pi * np.arange(wedges) / wedges
            radius = (ring / rings) * (
                0.95
                + 0.084 * np.sin(3 * theta + index)
                + 0.048 * np.sin(5 * theta - 1.5 * index)
            )
            if REVISION >= 17:
                radius = ring / rings * forms.footprint(theta, index)
            lx.extend(radius * np.cos(theta))
            ly.extend(radius * np.sin(theta))
        lx = np.array(lx)
        ly = np.array(ly)
        xy = to_xy(bank, lx, ly)
        x, y = xy.T
        _, side = road.surveys(xy)
        rootdist = field.trunks.query(xy)[0]
        r = np.r_[0, np.repeat(np.arange(1, rings + 1) / rings, wedges)]
        lip = 1 - smooth(0.43, 1.0, r)
        broken = (
            0.78
            + 0.16 * np.sin(x * 1.60 + y * 0.57)
            + 0.10 * np.cos(y * 1.97 - x * 0.45)
        )
        h = bank[4] * lip * broken
        # Soft, passable shoulder transitions within the nominal 24 m bed.
        h *= smooth(6.8, 13.1, np.abs(side))
        h = np.minimum(h, 0.045 + 0.83 * smooth(8.1, 13.2, np.abs(side)))
        h *= 0.28 + 0.72 * smooth(0.18, 1.75, rootdist)
        h -= 0.045 * smooth(0.81, 1, r)
        if REVISION >= 17:
            h = forms.surface(index, lx, ly, r, x, y, side, rootdist)
        if REVISION == 18 and index in (2, 3):
            # Broad bank in the side driver photograph screened the actual native trunk roots.
            # Low hummocks flank the trunk, leaving branches and flared roots as the main relief.
            h = np.minimum(h, 0.24) * 0.69 - 0.045 - 0.13 * smooth(0.60, 0.98, r)
        vert = np.column_stack((xy, field.height(xy) + h))
        faces = []
        for i in range(wedges):
            faces.append([0, i + 1, (i + 1) % wedges + 1])
        for ring in range(1, rings):
            j = 1 + (ring - 1) * wedges
            k = j + wedges
            for i in range(wedges):
                n = (i + 1) % wedges
                faces.extend([[j + i, k + i, k + n], [j + i, k + n, j + n]])
        faces = np.asarray(faces)
        tri = vert[faces]
        if not np.all(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])[:, 2] > 0):
            raise ValueError("Folded bank topology")
        screen = cam.project(vert)
        visible = screen[(h > 0.11) & (screen[:, 2] > 0)]
        proof.append(
            dict(
                name=bank[0],
                height_m=float(h.max()),
                screen_bounds=(
                    [visible[:, :2].min(0).tolist(), visible[:, :2].max(0).tolist()]
                    if len(visible)
                    else None
                ),
                minimum_lateral_distance_of_height_over_12cm=float(
                    np.abs(side[h > 0.12]).min()
                )
                if np.any(h > 0.12)
                else None,
                height_within_8m=float(h[np.abs(side) < 8].max())
                if (np.abs(side) < 8).any()
                else 0,
            )
        )
        u = (index % 2 + (0.5 + 0.445 * lx)) / 2
        v = (index // 2 + (0.5 + 0.445 * ly)) / 2
        if REVISION >= 17:
            u0, v0, w, d = forms.tile(index)
            u = u0 + (0.5 + 0.416 * lx) * w
            v = v0 + (0.5 + 0.416 * ly) * d
            fields.extend(np.column_stack((r, h, rootdist, np.full_like(r, index))))
        alluv.extend(np.column_stack((u, v)))
        allf.extend(faces + len(allv))
        allv.extend(vert)
        support.append((bank[0], tri))
        data.append((vert, faces))
    verts = np.array(allv)
    faces = np.array(allf)
    positions = (verts - origin) * [100, -100, 100]
    # MeshDescription's importer takes UE's clockwise index order viewed from above.
    # The coordinate reflection already changes the winding of these author-space faces.
    norms = np.zeros_like(verts)
    tri = verts[faces]
    normal = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    for i in range(3):
        np.add.at(norms, faces[:, i], normal)
    norms /= np.linalg.norm(norms, axis=1)[:, None]
    norms *= [1, -1, 1]
    if REVISION >= 17:
        save(
            OUT / "bank-surface-fields.json",
            dict(
                fields=np.round(fields, 6).tolist(),
                normal_z=norms[:, 2].round(6).tolist(),
            ),
        )
    save(
        OUT / "landform.json",
        dict(
            origin_cm=(origin * [100, -100, 100]).tolist(),
            positions=positions.round(4).tolist(),
            normals=norms.round(7).tolist(),
            faces=faces.tolist(),
            uv=np.round(alluv, 7).tolist(),
            islands=proof,
        ),
    )
    # Use the actual triangles for all subsequent vegetation and collision placement.
    return field, road, cam, origin, data, support


def bank_top(xy, field, data):
    top = field.height(xy).copy()
    for vert, faces in data:
        # Piecewise interpolation in the authored ring triangles, not a differently triangulated cloud.
        for tri in vert[faces]:
            bounds = (
                (xy[:, 0] >= tri[:, 0].min())
                & (xy[:, 0] <= tri[:, 0].max())
                & (xy[:, 1] >= tri[:, 1].min())
                & (xy[:, 1] <= tri[:, 1].max())
            )
            if not bounds.any():
                continue
            e = tri[1:, :2] - tri[0, :2]
            loc = (xy[bounds] - tri[0, :2]) @ np.linalg.inv(e)
            inside = np.all(loc >= -1e-8, axis=1) & (loc.sum(1) <= 1 + 1e-8)
            inds = np.flatnonzero(bounds)[inside]
            top[inds] = np.maximum(
                top[inds], tri[0, 2] + loc[inside] @ (tri[1:, 2] - tri[0, 2])
            )
    return top


def log_geometry(field, data):
    groups = source_cols()
    source = next(
        r
        for r in read(BASE / "structural.json")
        if r["camera"] == FOREST and r["kind"] == "Log"
    )
    # The scanned 5.5 m trunk points along local X. Set the sawn end toward the player.
    v = np.unique(lod0_points(ROOT / groups["Log"]["source_glb"]) * 0.01, axis=0)
    axis_a = np.array([-598.43, -534.13])
    axis_b = np.array([-597.43, -529.70])
    center = (axis_a + axis_b) / 2
    direction = axis_b - axis_a
    cross_section = [1.75, 1.83] if REVISION >= 17 else [0.62, 0.58]
    scale = np.array([np.linalg.norm(direction) / np.ptp(v[:, 0]), *cross_section])
    yaw = -np.degrees(np.arctan2(direction[1], direction[0]))
    rot = field.rotation(center, yaw)
    offsets = rot.apply(v * scale)
    z = float(field.height(center))
    footxy = center + offsets[:, :2] * [1, -1]
    # Contact the real bank under the bottom of the wood, without burying the split profile.
    burial = 0.015 if REVISION >= 17 else 0.035
    z -= (
        np.quantile(
            z + offsets[:, 2] - bank_top(footxy, field, data),
            0.035 if REVISION >= 17 else 0.08,
        )
        + burial
    )
    transform = np.r_[center * [100, -100], z * 100, rot.as_quat(), scale]
    old = read(BASE / "physics/collision-proof.json")
    scene = read(BASE / "physics/collision_scene.json")
    tri_count = old["added_surfaces"]
    with (BASE / "physics" / scene["bin"]).open("rb") as f:
        f.seek(-tri_count * 3 * scene["element_sizes"]["vertices"], 2)
        vr = np.frombuffer(f.read(), dtype=np.dtype([("p", "<f4", 3), ("edge", "<i4")]))
        added = vr["p"].reshape(-1, 3, 3).astype(float)
    offset = 0
    for obj in old["objects"]:
        if obj["kind"] == "Log" and obj["id"] == source["id"]:
            break
        offset += obj["surfaces"]
    else:
        raise ValueError("Missing native donor log hulls")
    old_tri = added[offset : offset + obj["surfaces"]] * [304.8, -304.8, 304.8]
    local = (
        Rotation.from_quat(source["rotation_xyzw"])
        .inv()
        .apply(old_tri.reshape(-1, 3) - source["position_cm"])
        / source["scale_xyz"]
    )
    new = (rot.apply(local * scale) + transform[:3]) * [0.01, -0.01, 0.01]
    return (
        transform,
        new.reshape(-1, 3, 3),
        dict(
            donor=source["id"],
            donor_faces=obj["surfaces"],
            support_burial_m=burial,
            cross_section_scale=cross_section,
            minimum_lane_distance_m=float(np.abs(Road(field).surveys(footxy)[1]).min()),
        ),
    )


def pack_groups(folder, owner, entries):
    folder.mkdir(parents=True, exist_ok=True)
    binary = folder / "verges.bin"
    binary.write_bytes(b"MJF3" + struct.pack("<II", 3, 0))
    groups = []
    for i, (definition, transforms) in enumerate(entries, 1):
        mat = np.asarray(transforms, dtype="<f4").reshape(-1, 10)
        f = folder / f"verges.bin.xf{i}"
        mat.tofile(f)
        append_foliage(
            binary,
            np.column_stack(
                (mat[:, :3], np.zeros(len(mat)), mat[:, 7], np.zeros((len(mat), 2)))
            ),
        )
        groups.append(
            dict(definition, count=len(mat), exact=True, transform_sha256=sha256(f))
        )
    save(
        folder / "verges.json",
        dict(
            actor=owner,
            file=binary.name,
            groups=groups,
            count=sum(g["count"] for g in groups),
            binary_sha256=sha256(binary),
        ),
    )


def scene_inputs():
    OUT.mkdir(parents=True, exist_ok=True)
    field, road, cam, origin, data, support = build_geometry()
    if REVISION == 18:
        import sweep_litter as litter
        import sweep_root_collars as roots

        meshes = litter.write_sources()
        log, hull, logproof = litter.wood_pose(field, data)
    else:
        log, hull, logproof = log_geometry(field, data)
    support.append(("split fallen trunk", hull))
    defs = source_cols()
    rocks = [
        r
        for r in read(BASE / "structural.json")
        if r["camera"] == FOREST and r["kind"] == "Outcrop"
    ]
    rxf = [[*r["position_cm"], *r["rotation_xyzw"], *r["scale_xyz"]] for r in rocks]
    land = dict(
        key="Landform",
        mesh=qpath(FOLDER + "/SM_PWR_SweepMossBanks"),
        material="M_PWR_SweepBank",
        wpo=0,
        cull=[12500, 17500],
        flags=35,
    )
    rock = dict(defs["Outcrop"], key="NoSnow", material_package=NOSNOW, material=None)
    wood = dict(defs["Log"], key="Deadfall", cull=[11000, 16000])
    if REVISION == 18:
        wood = dict(
            key="Deadfall",
            mesh=qpath(FOLDER + "/SM_PWR_SweepDeadPine"),
            material="M_PWR_SweepLitter",
            cull=[11000, 16000],
            wpo=0,
            flags=35,
        )
    groups = [
        (land, [np.r_[origin * [100, -100, 100], [0, 0, 0, 1, 1, 1, 1]]]),
        (rock, rxf),
        (wood, [log]),
    ]
    rng = np.random.default_rng(161097)
    grass = read(ROOT / "out/pwr/ground-life/grass/wind.json")["groups"][1]
    grass_mesh = grass["mesh"]
    placements = defaultdict(list)
    for index, (bank, (v, f)) in enumerate(zip(BANKS, data) if REVISION == 16 else []):
        n = [710, 420, 1670, 770][index]
        a = rng.uniform(-1, 1, (n, 2))
        a = a[np.linalg.norm(a, axis=1) < 0.96]
        xy = to_xy(bank, *a.T)
        top = bank_top(xy, field, data)
        _, d = road.surveys(xy)
        keep = (top - field.height(xy) > 0.06) & (abs(d) > 8.1)
        for j in np.flatnonzero(keep):
            p = xy[j]
            s = rng.uniform(0.45, 0.95)
            scale_z = s * rng.uniform(0.75, 1.3)
            k = rng.choice(["Sedge", "Ferns", "Tufts"], p=[0.49, 0.18, 0.33])
            if k == "Ferns":
                s *= 1.65
                scale_z = s * 0.94
            if k == "Tufts":
                s *= 0.95
                scale_z = s * 1.60
            yaw = rng.uniform(-180, 180)
            placements[k].append(
                [
                    p[0] * 100,
                    -p[1] * 100,
                    (top[j] - 0.012) * 100,
                    *Rotation.from_euler("z", yaw, degrees=True).as_quat(),
                    s,
                    s,
                    scale_z,
                ]
            )
    if REVISION >= 17:
        placements = forms.communities(field, road, data)
    if REVISION == 18:
        a = np.array([-598.28, -534.18])
        b = np.array([-597.41, -529.71])
        d = b - a
        for k, ps in placements.items():
            near = np.array(ps)[:, :2] * [0.01, -0.01] - a
            gap = np.linalg.norm(
                near - np.clip(near @ d / (d @ d), 0, 1)[:, None] * d, axis=1
            )
            placements[k] = [
                v for v, r in zip(ps, gap) if r > (1.11 if k == "Ferns" else 0.99)
            ]
    sedge = dict(
        key="Sedge",
        mesh=grass_mesh,
        material="MI_PWR_Wind_B30",
        cull=[6400, 10000],
        flags=32,
        wpo=3800,
    )
    groups.extend(
        [
            (sedge, placements["Sedge"]),
            (dict(defs["Fern15"], key="Ferns", cull=[5500, 8200]), placements["Ferns"]),
            (
                dict(defs["FescueA"], key="Tufts", cull=[5600, 8800]),
                placements["Tufts"],
            ),
        ]
    )
    if REVISION == 18:
        for i, poses in enumerate(litter.placements(field, road, data, cam)):
            groups.append(
                (
                    dict(
                        key="Litter" + "ABC"[i],
                        mesh=qpath(meshes[i]["package"]),
                        material="M_PWR_SweepLitter",
                        cull=[3100, 5100],
                        wpo=0,
                        flags=33,
                    ),
                    poses,
                )
            )
        rg, objects, contacts = roots.fit(field, data, OUT, cam)
        groups.extend(rg)
        support.extend(objects)
        save(OUT / "root-contacts.json", contacts)
        save(
            OUT / "litter.json",
            dict(
                meshes=meshes,
                material=FOLDER + "/M_PWR_SweepLitter",
                texture_package=FOLDER + "/T_PWR_SweepLitter_D",
                texture_file="litter-D.png",
                blend_mode="opaque",
                source_geometry_space="Unreal local centimetres",
            ),
        )
    pack_groups(OUT, "PWR_SweepBanks", groups)
    floor = SWEEP / "verges"
    prev = read(floor / "verges.json")
    effective = []
    changes = {}
    for i, g in enumerate(prev["groups"], 1):
        m = np.fromfile(floor / f"verges.bin.xf{i}", dtype="<f4").reshape(-1, 10)
        if g["key"] == "Moss":
            # Remove the original conspicuous dark fragments. Retain only modest chips close to trunks.
            xy = m[:, :2] * [0.01, -0.01]
            gap = field.trunks.query(xy)[0]
            retain = (gap < 4.0) & (np.arange(len(m)) % 3 == 0)
            changes["moss_indices"] = np.flatnonzero(retain).tolist()
            m = m[retain].copy()
            m[:, 7:9] *= 0.56
            m[:, 9] *= 0.45
        effective.append((g, m))
    pack_groups(OUT.parent / "floor", prev["actor"], effective)
    changes.update(
        baseline_moss_source_sha256=sha256(floor / "verges.json"),
        snowfree_moved_outcrops=rxf,
        snowfree_material=NOSNOW,
        donor_log=logproof,
        camera=cam.pose,
    )
    save(OUT / "legacy-edits.json", changes)
    np.savez_compressed(OUT / "physical-surfaces.npz", **dict(support))
    save(OUT / "structural.json", [dict(name=k, faces=len(t)) for k, t in support])
    print(
        json.dumps(
            {
                "geometry": read(OUT / "landform.json")["islands"],
                "log": logproof,
                "faces": sum(len(t) for k, t in support),
                "reduced_moss": len(changes["moss_indices"]),
            }
        )
    )


def collision(source=None, art=None, expected_bsp=None):
    sys.path.insert(0, str(ROOT / "levels/warfare/pwr/bases_v1"))
    from cook_polish_collision import (
        FORMATS,
        MAX_SURFACES,
        arrays,
        extend_arrays,
        verify_native_surfaces,
    )

    src = source if source is not None else BASE / "physics"
    art = art if art is not None else OUT
    dst = art / "physics"
    dst.mkdir(exist_ok=True)
    old = read(src / "collision_scene.json")
    prev = read(src / "native-collision-receipt.json")
    sealed = expected_bsp or read(SWEEP / "saturday.15/receipt.json")["collision"]["sbsp"]
    binary = old["bin"]
    if (
        sha256(src / "pwr.sbsp"),
        sha256(src / binary),
        sha256(src / "collision_scene.json"),
    ) != (sealed, prev["source_binary_sha256"], prev["source_manifest_sha256"]):
        raise ValueError(
            "Published native physics differs from the collision donor"
        )
    added = defaultdict(bytearray)
    base = arrays(src / binary, old)
    manifest = deepcopy(old)
    mats = {r.get("game_material"): r["index"] for r in old["materials"]}
    objects = []
    alltri = []
    for name, t in np.load(art / "physical-surfaces.npz").items():
        tri = t / 3.048
        material = (
            mats["tough_organic_wood"]
            if "trunk" in name
            else mats["hard_terrain_stone"]
        )
        if REVISION >= 17 and "granite" not in name and "trunk" not in name:
            material = mats["tough_terrain_dirt"]
        if (
            REVISION == 18
            and name.startswith("Root")
            and not name.startswith("RootMat")
        ):
            material = mats["tough_organic_wood"]
        counts = {
            k: n + len(added[k]) // struct.calcsize(FORMATS[k])
            for k, n in old["counts"].items()
        }
        for k, v in extend_arrays(tri, counts, material).items():
            added[k].extend(v)
        objects.append(dict(name=name, surfaces=len(tri), material=material))
        alltri.extend(tri)
    tri = np.array(alltri)
    start = old["counts"]["surfaces"]
    if start + len(tri) > MAX_SURFACES:
        raise ValueError("Physical surface budget exceeded")
    with (dst / binary).open("wb") as handle:
        for key in manifest["array_order"]:
            manifest["counts"][key] += len(added[key]) // struct.calcsize(FORMATS[key])
            handle.write(struct.pack("<I", manifest["counts"][key]))
            handle.write(base[key])
            handle.write(added[key])
    manifest["scenery_surfaces"]["surfaces"] += len(tri)
    manifest["scenery_surfaces"]["objects"] += len(objects)
    for key, op in (("min", np.minimum), ("max", np.maximum)):
        manifest["world_bounds"][key] = op(
            manifest["world_bounds"][key], getattr(tri, key)(axis=(0, 1))
        ).tolist()
    save(dst / "collision_scene.json", manifest)
    updated = arrays(dst / binary, manifest)
    for k in manifest["array_order"]:
        if updated[k][: len(base[k])] != base[k]:
            raise ValueError("Existing native surfaces moved")
    del base, updated
    command = [
        CLI,
        "level",
        "collision",
        dst / "collision_scene.json",
        "--paks",
        PAKS,
        "--own-bsp",
        "--bsp-index",
        "0",
        "--receipt",
        dst / "native-collision-receipt.json",
        "--out",
        dst / "pwr.sbsp",
    ]
    with (dst / "native.log").open("w") as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    receipt = read(dst / "native-collision-receipt.json")
    if (
        receipt["source_surfaces"] != start + len(tri)
        or receipt["source_manifest_sha256"] != sha256(dst / "collision_scene.json")
        or receipt["source_binary_sha256"] != sha256(dst / binary)
        or receipt["output_sha256"] != sha256(dst / "pwr.sbsp")
    ):
        raise RuntimeError("Native collision cook does not match the authored surfaces")
    error = verify_native_surfaces(receipt, start, tri, dst)
    save(
        dst / "collision-proof.json",
        dict(
            base_sbsp=sealed,
            sbsp=receipt["output_sha256"],
            source_arrays_prefix_exact=True,
            preserved_source_surfaces=start,
            added_surfaces=len(tri),
            total_surfaces=start + len(tri),
            source_structural_sha256=sha256(art / "structural.json"),
            source_triangles_sha256=sha256(art / "physical-surfaces.npz"),
            objects=objects,
            root_and_definition_havok_verified_per_face=True,
            cooked_surface_maximum_error_m=error,
            live_physics_tested=False,
        ),
    )
    witness_existing_collision(dst, src)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collision", action="store_true")
    parser.add_argument("--revision", type=int, choices=[16, 17, 18], default=16)
    args = parser.parse_args()
    REVISION = args.revision
    OUT = SWEEP / f"round{REVISION}/verges"
    if args.collision:
        collision()
    else:
        scene_inputs()

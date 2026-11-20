"""Split the shipped .12 sedge population by dry pine ecology without moving a plant."""

from collections import Counter
import hashlib
import json
from pathlib import Path
import struct

import numpy as np
from scipy.ndimage import distance_transform_edt
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation

import prepare_wind_grass as p
import verify_distance_colonies as native
from verify_render_only_hism_cook import package, number

OUT = p.ROOT / "out/pwr/ground-life/forest.13"
FOLDER = "/Game/MJOLNIR/GrassPilot/Playable/"
SPECIES = {
    "FescueA": (
        FOLDER + "SM_PWR_FineFescue_A",
        "MI_PWR_Wind_Fescue",
        [2100, 4400],
        3100,
    ),
    "FescueB": (
        FOLDER + "SM_PWR_FineFescue_B",
        "MI_PWR_Wind_Fescue",
        [2100, 4400],
        3100,
    ),
    "Wild12": (p.MESH["Wild12"], "MI_PWR_Wind_B30", [2750, 5500], 4600),
    "Wild16": (p.MESH["Wild16"], "MI_PWR_Wind_B30", [2750, 5500], 4600),
    "Fern14": (
        "/Game/Megascans/3D_Plants/BeechFern/SM_BeechFern_14",
        None,
        [2600, 5900],
        3700,
    ),
    "Fern15": (
        "/Game/Megascans/3D_Plants/BeechFern/SM_BeechFern_15",
        None,
        [2600, 5900],
        3700,
    ),
}
STOCK = "/Game/Env/Bio/Grass/Sedges/Grass_Sedges_A/SM_Grass_Sedges_A_Leaves_C"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    field = p.load_heightfield(p.FIELD)
    ecology = np.load(
        p.ROOT / "out/pwr/visual-v6/source-ecology/ecology/ecology.rgba.npy",
        mmap_mode="r",
    )
    water_clear = (
        distance_transform_edt(
            (field.masks["water"] == 0) & (field.masks["shore"] < 0.01)
        )
        * field.spacing_m[0]
    )
    tree_points = json.loads(
        (p.ROOT / "out/pwr/visual-v6/scenery/trees/trees.selected.json").read_text()
    )["instances"]
    tree = cKDTree([v["position"][:2] for v in tree_points])
    src = OUT.parent / "native.12/LPE.umap"
    original = src.read_bytes()
    groups = []
    replacement = {k: [] for k in SPECIES}
    rng = np.random.default_rng(131113)
    totals = Counter()
    for row in native.decode(src, native.GAME)["exports"]:
        if (
            row["class"] != "HierarchicalInstancedStaticMeshComponent"
            or package(row, "StaticMesh") != STOCK
        ):
            continue
        assert row["outer"] == "MJOLNIR_Foliage"
        n = int(number(row["properties"]["NumBuiltInstances"]))
        matrices = native.native_matrices(original, row, n)
        xyz = matrices[:, 3, :3]
        x, y = xyz[:, 0] * 0.01, -xyz[:, 1] * 0.01
        im, jm = (
            np.rint((x + 1000) / field.spacing_m[0]).astype(int),
            np.rint((y + 1000) / field.spacing_m[1]).astype(int),
        )
        env = ecology[jm, im]
        trees = tree.query(np.column_stack((x, y)))[0]
        wet = water_clear[jm, im] <= 12
        under = (
            (field.sample_mask("forest", x, y) > 0.50)
            & (trees < 11)
            & (env[:, 1] > 0.35)
        )
        select = under & ~wet & (env[:, 0] < 0.64)
        ix = np.flatnonzero(select)
        selected = xyz[ix]
        name = row["name"]
        assert len(ix) > 0
        # The source index plus original XYZ can be checked before native bulk removal.
        arr = np.zeros(len(ix), dtype=[("index", "<i4"), ("xyz", "<f4", (3,))])
        arr["index"] = ix
        arr["xyz"] = selected
        arr.tofile(OUT / (name + ".remove"))
        keep = matrices[~select]
        keep = keep[np.lexsort(tuple(keep[:, 3, j] for j in (2, 1, 0)))]
        groups.append(
            dict(
                component=name,
                original=n,
                removed=len(ix),
                survivors=len(keep),
                retained_affine_sha256=hashlib.sha256(keep.tobytes()).hexdigest(),
                wet_retained=int(wet.sum()),
            )
        )
        bases = matrices[ix, :3, :3]
        scale = np.linalg.norm(bases, axis=2)
        quat = Rotation.from_matrix(
            (bases / scale[:, :, None]).transpose(0, 2, 1)
        ).as_quat()
        draw = rng.random(len(ix))
        kinds = np.array(
            ["FescueA", "FescueB", "Wild12", "Wild16", "Fern14", "Fern15"]
        )[np.searchsorted([0.345, 0.69, 0.816, 0.991, 0.9955, 1.0], draw)]
        for key in SPECIES:
            chosen = kinds == key
            count = int(chosen.sum())
            factor = (
                rng.uniform(0.72, 1.03, count)
                if key.startswith("Fescue")
                else rng.uniform(0.93, 1.30, count)
                if key.startswith("Fern")
                else rng.uniform(0.61, 0.96, count)
            )
            xf = np.column_stack(
                (selected[chosen], quat[chosen], scale[chosen] * factor[:, None])
            ).astype("<f4")
            replacement[key].append(xf)
        totals.update(
            dict(
                original=n,
                dry_forest=len(ix),
                wet_retained=int(wet.sum()),
                nonforest_retained=int((~under).sum()),
                forest_camera_replaced=int(
                    np.sum(select & (np.hypot(x - 365, y - 205) < 12))
                ),
            )
        )
    rows = []
    with (OUT / "floor.bin").open("wb") as f:
        f.write(b"MJF3" + struct.pack("<II", 3, len(SPECIES)))
        for i, (k, (mesh, mi, cull, wpo)) in enumerate(SPECIES.items(), 1):
            xf = np.vstack(replacement[k])
            xf.tofile(OUT / f"floor.bin.xf{i}")
            f.write(struct.pack("<I", len(xf)))
            basic = np.empty(
                len(xf),
                dtype=[
                    ("pos", "<f4", (3,)),
                    ("yaw", "u1"),
                    ("scale", "u1"),
                    ("oct", "i1", (2,)),
                    ("clr", "u1", (3,)),
                ],
            )
            basic["pos"] = xf[:, :3]
            basic["yaw"] = 0
            basic["scale"] = 100
            basic["oct"] = 0
            basic["clr"] = 255
            f.write(basic.tobytes())
            rows.append(
                dict(
                    key=k,
                    mesh=p.qpath(mesh),
                    material=mi,
                    cull=cull,
                    wpo=wpo,
                    count=len(xf),
                )
            )
    assert (
        len(groups) == 2
        and sum(r["count"] for r in rows) == totals["dry_forest"]
        and totals["forest_camera_replaced"] > 30
    )
    assert sum(r["count"] for r in rows if r["key"].startswith("Fern")) < 1500
    p.write(OUT / "floor.json", dict(source=groups, groups=rows, totals=dict(totals)))
    print(dict(totals), {r["key"]: r["count"] for r in rows})


if __name__ == "__main__":
    main()

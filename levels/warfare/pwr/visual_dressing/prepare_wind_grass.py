"""Prepare .10-native grass varieties, wind atlases and PCG inputs for natural verges."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt
from scipy.spatial import cKDTree
import shapely
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools/level"))
from heightfield import load_heightfield
from foliage_bake import mesh_info

OUT = ROOT / "out/pwr/ground-life/grass"
BASE = ROOT / "out/pwr/base-approaches"
PAKS = ROOT / "out/pwr/playtest-20261121/rehearsal-game/Meteorite/Content/Paks"
CLI = ROOT / "target/release/mjolnir.exe"
FIELD = ROOT / "levels/warfare/pwr/terrain/runtime-v5/runtime-master.json"
SEED = 231109
B30 = "/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/"
CANYON = "/Game/Env/Bio/Grass/CanyonPrinceWildRye/SM_Grass_CanyonPrinceWildRye"
TUNDRA = "/Game/Env/Bio/Grass/GroundcoverClump/Grass_GroundcoverClump_A/SM_Grass_GroundcoverClump_A"
MESH = {
    "Canyon": CANYON,
    **{
        "Wild" + str(i): B30 + "S_Wild_Grass_vlkhcbxia_0_Var" + str(i) + "_lod0"
        for i in [1, 12, 16]
    },
    "Tundra": TUNDRA,
}
TEXTURES = {
    "Canyon": ("T_Grass_CanyonPrinceWildRye_D", "T_Grass_CanyonPrinceWildRye_ORT"),
    "B30": ("T_Wild_Grass_vlkhcbxia_8K_D", "T_WildGrass_vlkhcbxia_8K_ART"),
    "Tundra": (
        "T_MI_Tundra_Grass_Removed_Highlights_D",
        "T_TundraGrass_wk2oaeyqx_4K_ART",
    ),
}


def write(path, data):
    path.write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def qpath(mesh):
    return mesh + "." + mesh.rsplit("/", 1)[1]


def chart(image, x, y):
    n = image.shape[0]
    return image[
        np.clip(((1000 - y) * n / 2000).astype(int), 0, n - 1),
        np.clip(((1000 + x) * n / 2000).astype(int), 0, n - 1),
    ]


def assets():
    source = OUT / "source"
    source.mkdir(exist_ok=True, parents=True)
    meshes = {}
    atlases = {}
    for key, (diff, mask) in TEXTURES.items():
        paths = []
        # Keep full shipped resolution for the short Tundra and Canyon assets.
        for name in [diff, mask]:
            path = source / (name + "-full.png")
            if not path.is_file():
                subprocess.run(
                    [
                        CLI,
                        "texture",
                        "export",
                        "--paks",
                        PAKS,
                        "--asset",
                        name,
                        "--mip",
                        "1" if key == "B30" else "0",
                        "--out",
                        path,
                    ],
                    check=True,
                    capture_output=True,
                )
            paths.append(path)
        image = Image.open(paths[0]).convert("RGBA")
        opacity = Image.open(paths[1]).getchannel("R")
        if image.size != opacity.size:
            raise ValueError("Mismatched native grass UV atlas")
        image.putalpha(opacity)
        dest = OUT / ("T_PWR_Wind_" + key + ".png")
        image.save(dest)
        atlases[key] = dict(
            path=str(dest),
            sha256=sha(dest),
            source=[p.name for p in paths],
            size=image.size,
            red_mask_below_clip=float((np.asarray(opacity) < 85).mean()),
        )
    for name, mesh in MESH.items():
        info = mesh_info(str(CLI), PAKS, qpath(mesh))
        meshes[name] = dict(
            mesh=qpath(mesh),
            origin=info["origin"],
            extent=info["extent"],
            standin_slots=info["slots"],
        )
    return meshes, atlases


def prepare(fine=False):
    output = OUT.with_name("grass.12") if fine else OUT
    output.mkdir(parents=True, exist_ok=True)
    if fine:
        baseline = json.loads((OUT / "wind-grass.json").read_text())
        atlases = baseline["atlases"]
        meshes = {
            k: {
                "mesh": qpath(
                    "/Game/MJOLNIR/GrassPilot/Playable/SM_PWR_FineFescue_" + k
                )
            }
            for k in ("A", "B")
        }
    else:
        meshes, atlases = assets()
    field = load_heightfield(FIELD)
    rng = np.random.default_rng(SEED)
    level = json.loads((BASE / "saturday.10/map-input/pwr.level.json").read_text())
    geo = json.loads((BASE / "geometry/gate-routes.geojson").read_text())
    site = json.loads(
        (BASE / "site-finish/geometry/site-footprints.geojson").read_text()
    )
    protected = shapely.union_all(
        [
            shape(g["geometry"])
            for g in geo["features"]
            if g["properties"]["role"] in ("rear_pad", "court")
        ]
        + [
            shape(g["geometry"])
            for g in site["features"]
            if g["properties"]["role"] in ("toe", "spur_and_bay")
        ]
    )
    roads = np.array(Image.open(BASE / "roads/road-network.png"))[:, :, 0]
    road_margin = distance_transform_edt(roads < 5) * 2000 / len(roads)
    site_data = np.array(Image.open(BASE / "site-finish/terrain/site-ground.png"))
    tree_xy = np.array(
        [
            p["position"][:2]
            for p in json.loads(
                (
                    ROOT / "out/pwr/visual-v6/scenery/trees/trees.selected.json"
                ).read_text()
            )["instances"]
        ]
    )
    trees = cKDTree(tree_xy)
    geo_world = json.loads(
        (ROOT / "levels/warfare/pwr/terrain/final-v5/terrain.geometry.json").read_text()
    )
    # Seed a discontinuous ribbon tangential to each real road, with local
    # pockets across either shoulder. Road bends/merges are tested once more
    # against the .10 rendered network mask before any candidate reaches PCG.
    centers = []
    for road in geo_world["roads"]:
        raw = road.get("centreline_m", road.get("deck_centreline_m", []))
        if len(raw) < 2:
            continue
        line = shapely.LineString(np.asarray(raw)[:, :2])
        for ds in np.arange(0, line.length, 9.5):
            if rng.random() < 0.31:
                continue
            a = np.array(line.interpolate(ds).coords[0])
            b = np.array(line.interpolate(min(ds + 0.5, line.length)).coords[0])
            v = b - a
            if np.linalg.norm(v) < 0.01:
                continue
            v /= np.linalg.norm(v)
            side = np.array([-v[1], v[0]]) * rng.choice([-1, 1])
            centers.append((a + side * rng.uniform(16, 28), v, 32, "road"))
    for entry in site["features"]:
        if entry["properties"]["role"] != "toe":
            continue
        line = shape(entry["geometry"]).boundary
        x, y = shape(entry["geometry"]).centroid.coords[0]
        for ds in np.arange(0, line.length, 8.5):
            p = np.array(line.interpolate(ds).coords[0])
            n = p - [x, y]
            n /= np.linalg.norm(n)
            centers.append(
                (p + n * rng.uniform(10, 21), np.array([-n[1], n[0]]), 42, "base")
            )
    # Selected broad touchdown terraces and the near-camera road approach use
    # a connected meadow texture. A denser center fades into shorter patches.
    for x, y, n in [
        (-817.94, -497.0, 72),
        (-825, -505, 50),
        (-812, -494, 40),
        (-654, -168, 44),
        (581, 338, 40),
        (575, 336, 45),
        (583, 337, 38),
        (580, 340, 30),
    ]:
        for _ in range(5):
            centers.append(
                (
                    np.array([x, y]) + rng.normal(0, 3, 2),
                    np.array([0.74, 0.67]),
                    n,
                    "meadow",
                )
            )
    for _ in range(400):
        pos = rng.uniform(-955, 955, 2)
        if field.sample_mask("water", *pos) > 0 or trees.query(pos)[0] < 8:
            continue
        centers.append((pos, np.array([0.82, 0.57]), 23, "field"))
    positions = []
    types = []
    for center, tangent, number, kind in centers:
        normal = np.array([-tangent[1], tangent[0]])
        positions.append(
            center
            + rng.normal(0, 4.9, (number, 1)) * tangent
            + rng.normal(0, 2.25, (number, 1)) * normal
        )
        types.extend([kind] * number)
    if fine:
        from verify_distance_colonies import (
            decode,
            GAME,
            native_matrices,
            number,
            package,
        )

        world = BASE / "site-finish/native/LPE.umap"
        contents = world.read_bytes()
        for row in decode(world, GAME)["exports"]:
            if (
                row["class"] != "HierarchicalInstancedStaticMeshComponent"
                or "SM_Grass_GroundcoverClump_A" not in str(package(row, "StaticMesh"))
            ):
                continue
            matrices = native_matrices(
                contents, row, int(number(row["properties"]["NumBuiltInstances"]))
            )
            xy = matrices[::9, 3, :2] * np.array([0.01, -0.01])
            xy = xy + rng.normal(0, 1.45, size=xy.shape)
            positions.append(xy)
            types.extend(["meadow-floor"] * len(xy))
        positions = [xy + rng.normal(0, 2.3, xy.shape) for xy in positions]
    pos = np.vstack(positions)
    x, y = pos.T
    kind = np.array(types)
    road_clear = chart(road_margin, x, y)
    grade = chart(site_data, x, y)[:, 0] / 255.0
    p = shapely.points(pos)
    court_clear = shapely.distance(p, protected)
    water = field.sample_mask("water", x, y)
    sx = (field.sample(x + 1, y) - field.sample(x - 1, y)) * 0.5
    sy = (field.sample(x, y + 1) - field.sample(x, y - 1)) * 0.5
    keep = (
        (np.abs(x) < 966)
        & (np.abs(y) < 966)
        & (water == 0)
        & (sx * sx + sy * sy < 0.64)
        & (road_clear > 2.25)
        & (court_clear > 2.0)
        & (grade < 0.38)
        & (trees.query(pos)[0] > 2)
    )
    for row in level["blam"]["vehicles"] + level["blam"]["player_starts"]:
        a, b = row["pos"][:2]
        keep &= (x - a * 0.01) ** 2 + (y + b * 0.01) ** 2 > 8**2
    for a, b, _, r in level["koth_hills"]:
        keep &= (x - a * 0.01) ** 2 + (y + b * 0.01) ** 2 > (r * 0.01 + 2.3) ** 2
    # Explicitly exclude shore/crossing splines plus the service apron and native road itself.
    for entry in geo_world["crossings"]:
        a, b = entry["position_m"][:2]
        keep &= (x - a) ** 2 + (y - b) ** 2 > 19**2
    points = []
    norm = np.column_stack((-sx, -sy, np.ones(len(x))))
    norm /= np.linalg.norm(norm, axis=1)[:, None]
    families = ["Wild1", "Wild12", "Wild16", "Canyon"]
    z = field.sample(x, y)
    for i in np.flatnonzero(keep):
        family = (
            rng.choice(["A", "B"])
            if fine
            else rng.choice(families, p=[0.31, 0.30, 0.25, 0.14])
        )
        points.append(
            dict(
                id=len(points),
                kind=family,
                position=np.round([x[i], y[i], z[i]], 6).tolist(),
                normal=np.round(norm[i], 7).tolist(),
                density=float(rng.uniform(0.61, 0.89)),
                biome_mask=1,
                biome=kind[i],
            )
        )
    if fine:
        families = ["A", "B"]
    write(output / "points.json", dict(schema=1, align_to_normal=True, points=points))
    write(
        output / "palette.json",
        dict(
            kinds={
                k: dict(
                    meshes=[meshes[k]["mesh"]],
                    rule=k,
                    cull=[2100, 4400] if fine else [4800, 8800],
                    bands=1,
                    shadow=False,
                    static=False,
                )
                for k in families
            }
        ),
    )
    support = dict(
        candidates=len(points),
        min_gravel_boundary_m=float(road_clear[keep].min()),
        min_building_ground_m=float(court_clear[keep].min()),
        biome_candidates={i: int(np.sum(kind[keep] == i)) for i in set(types)},
        max_water=float(water[keep].max()),
    )
    spec = dict(
        meshes=meshes,
        atlases=atlases,
        seed=SEED + int(fine),
        budget=57000 if fine else 42000,
        support=support,
        b30_source="DA_SpawnableGrass_Wild_B30",
        baseline_sha256=sha(BASE / "saturday.10/receipt.json"),
    )
    write(output / "wind-grass.json", spec)
    print(support)


if __name__ == "__main__":
    prepare("--fine" in sys.argv)

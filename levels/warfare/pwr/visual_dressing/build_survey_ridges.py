"""Fit surveyed alpine ridgelines behind the fixed, playable PWR valley."""

from pathlib import Path
import argparse
import json
import numpy as np
import rasterio
from rasterio.windows import from_bounds
from PIL import Image
from scipy import ndimage as nd
from scipy.spatial import cKDTree

import build_apron_v7 as mesh
from heightfield import sha256

ROOT = mesh.ROOT
OLD = ROOT / "out/pwr/visual-v7/apron-cliffs/apron/apron.source.npz"
MASKS = ROOT / "out/pwr/visual-v8/surface-cooked-final"
GROUND = ROOT / "out/pwr/visual-v8/foothills/clustered-final/grounding.json"
ORIGINAL_CLIFFS = (
    ROOT / "out/pwr/visual-v7/apron-cliffs/heroes/pilot.preview-grounding.json"
)
BASE_MAP = ROOT / "out/pwr/base-approaches/saturday.10/map-input/pwr.level.json"
SURVEY = "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/13/TIFF/current/n44w111/USGS_13_n44w111.tif"
# Game coordinates in authoring metres. Orient each massif's surveyed valley
# face towards the play space. Positive Y in authoring is negative Y in Unreal.
PEAKS = (
    ("Grand Teton", 400, 2550, -110.80236, 43.74125, 2.17, 0.52, 1140, 2590),
    ("Mount Moran", 2700, -1000, -110.77653, 43.83505, 2.26, 0.55, 1100, 2530),
    ("Middle Teton", -670, -2850, -110.81125, 43.72986, 2.45, 0.52, 1070, 2330),
    ("Teewinot foothill", 45, -1575, -110.77977, 43.74708, 3.1, 0.27, 490, 1250),
    ("Southern Teton crest", -2750, -950, -110.81921, 43.68921, 2.04, 0.56, 1040, 2500),
)


def smooth(lo, hi, value):
    f = np.clip((value - lo) / (hi - lo), 0, 1)
    return f * f * (3 - 2 * f)


def save_json(file, value):
    file.write_text(json.dumps(value, indent=2) + "\n")


class Ridges:
    def __init__(self, dem, contacts):
        with rasterio.open(dem) as ds:
            window = (
                from_bounds(-110.95, 43.57, -110.63, 43.95, ds.transform)
                .round_offsets()
                .round_lengths()
            )
            self.heights = ds.read(1, window=window)
            self.transform = ds.window_transform(window)
        if self.heights.min() < 0 or self.heights.max() < 4100:
            raise ValueError("Missing source elevations")

        # Grounded native foothill assets extend past the common belt on the
        # west and east walls. Include the longest old triangle edge in the
        # protected area to keep their supporting triangle planes exact.
        protected = np.zeros((1001, 1001), bool)
        for row in contacts["cliffs"] + contacts["trees"]:
            low, high = np.asarray(row["bounds_ue_cm"])[:, :2] * [0.01, -0.01]
            xmin, ymin = np.minimum(low, high)
            xmax, ymax = np.maximum(low, high)
            protected[
                int((ymin + 4000) // 8) : int((ymax + 4000) // 8) + 2,
                int((xmin + 4000) // 8) : int((xmax + 4000) // 8) + 2,
            ] = True
        self.clearance = nd.distance_transform_edt(~protected, sampling=8).astype("f4")

    def evaluate(self, x, y, old):
        radius = np.maximum(abs(x), abs(y))
        distance = nd.map_coordinates(
            self.clearance, [(y + 4000) / 8, (x + 4000) / 8], order=1, mode="nearest"
        )
        grounded = smooth(108, 350, distance)
        top = old.copy()
        for name, cx, cy, lon, lat, scale, vertical, top_z, extent in PEAKS:
            dx, dy = x - cx, y - cy
            length = np.hypot(cx, cy)
            e = (-cx * dx - cy * dy) / length
            n = (cy * dx - cx * dy) / length
            east, north = e * scale, n * scale
            # East-west metres per degree vary with latitude.
            col, row = (~self.transform) * (
                lon + east / (111320 * np.cos(np.deg2rad(lat))),
                lat + north / 111110,
            )
            surveyed = nd.map_coordinates(
                self.heights, [row - 0.5, col - 0.5], order=1, mode="nearest"
            )
            scol, srow = (~self.transform) * (lon, lat)
            summit = nd.map_coordinates(
                self.heights, [[srow - 0.5], [scol - 0.5]], order=1
            )[0]
            target = top_z + vertical * (surveyed - summit)
            footprint = 1 - smooth(0.57 * extent, extent, np.hypot(e * 1.25, n * 0.88))
            collar = (
                smooth(1040, 1390, radius)
                if name == "Teewinot foothill"
                else smooth(1430, 2140, radius)
            )
            top = np.maximum(
                top, old + np.maximum(target - old, 0) * collar * grounded * footprint
            )
        return top


def geology(out, verts, new_z):
    n = 1024
    y, x = np.mgrid[0:n, 0:n]
    x = -4000 + (x + 0.5) * 8000 / n
    y = 4000 - (y + 0.5) * 8000 / n
    tree = cKDTree(verts[:, :2])
    d, near = tree.query(np.stack([x, y], axis=-1), k=4, workers=6)
    w = 1 / np.maximum(d, 0.01) ** 2
    old = np.sum(verts[near, 2] * w, axis=2) / np.sum(w, axis=2)
    new = np.sum(new_z[near] * w, axis=2) / np.sum(w, axis=2)
    mask = smooth(2, 65, new - old)
    grid = nd.gaussian_filter(new, 1)
    gy, gx = np.gradient(grid, 8000 / n)
    grade = np.hypot(gx, gy)
    convexity = grid - nd.gaussian_filter(grid, 5.5)
    elevation = smooth(540, 940, grid)
    face = smooth(0.25, 1.05, grade)
    ledge = smooth(-18, 6, -convexity)
    # Snow collects in concave cirques and on gentler ramps between exposed
    # rock ribs. This is evaluated on the final geometry in its actual pose.
    lee = 0.5 + 0.5 * np.clip((gx * 0.50 + gy * 0.86) / np.maximum(0.001, grade), -1, 1)
    # In a shaded high gully, hanging snow crosses a steeper face than it
    # can on an exposed buttress. The scales are measured in survey metres.
    high_shelter = smooth(450, 820, grid)
    incision = nd.gaussian_filter(grid, 13) - grid
    snow = (
        high_shelter
        * (0.07 + 0.93 * ledge)
        * (0.52 + 0.48 * lee)
        * (1 - smooth(0.55, 1.55, grade))
    )
    snow = np.maximum(
        snow,
        high_shelter
        * smooth(4, 22, incision)
        * smooth(-4, 8, -convexity)
        * (0.62 + 0.38 * lee)
        * (1 - smooth(1.0, 1.9, grade)),
    )
    rock_rib = smooth(3, 18, convexity) * smooth(245, 450, grid)
    stone = np.maximum(
        0.22 + 0.62 * face + 0.20 * rock_rib, 0.90 * smooth(560, 960, grid)
    ) * (1 - 0.10 * snow)
    field = np.asarray(
        Image.open(MASKS / "T_PWR_ApronField.png").convert("RGBA")
    ).copy()
    broad_cirque = (grid - nd.gaussian_filter(grid, 15)) / 48
    exposure = np.clip(
        0.55 + 0.30 * np.tanh(broad_cirque) + 0.20 * np.tanh(convexity / 13), 0, 1
    )
    surface = np.stack([stone, snow, 0.21 + 0.73 * elevation, exposure], axis=2)
    field = np.rint(
        field * (1 - mask[:, :, None]) + 255 * np.clip(surface, 0, 1) * mask[:, :, None]
    ).astype("uint8")
    Image.fromarray(field).save(out / "T_PWR_ApronField.png")

    base = np.asarray(Image.open(MASKS / "T_LandBase.png").convert("RGBA")).copy()
    original = base.copy()
    terrain = mesh.ROOT / "levels/warfare/pwr/terrain/runtime-v5"

    def sample(prop):
        a = np.load(terrain / ("runtime-master." + prop + ".npy"))[::-1].copy()
        return np.asarray(
            Image.fromarray(a.astype("f4")).resize((n, n), Image.Resampling.BILINEAR)
        )

    h = sample("heights")
    local = nd.gaussian_filter(h, 1.3)
    gy, gx = np.gradient(local, 2000 / n)
    slope = np.hypot(gx, gy)
    rib = local - nd.gaussian_filter(local, 9)
    gully = nd.gaussian_filter(local, 3) - nd.gaussian_filter(local, 19)
    clearance = 1 - smooth(
        0.02, 0.18, np.maximum.reduce([sample(k) for k in ("bases", "road", "water")])
    )
    iy, ix = np.indices((n, n))
    border = np.minimum.reduce([ix, iy, n - 1 - ix, n - 1 - iy]) * 2000 / n
    protect = (
        clearance
        * smooth(20, 45, border)
        * (1 - smooth(0.01, 0.12, base[:, :, 3] / 255))
    )
    hill = smooth(112, 190, h) * smooth(0.12, 0.46, slope) * protect
    # Broken headwall strata follow elevation and aspect. Colluvium is
    # restricted to convexity transitions below these exposed rock faces.
    strike = h * 0.31 + ix * 0.046 - iy * 0.024 + nd.gaussian_filter(rib, 5) * 0.25
    bedding = smooth(-0.68, 0.38, np.sin(strike) + 0.40 * np.sin(0.48 * strike + 0.61))
    bedrock = np.clip(
        0.22
        + 0.41 * bedding
        + 0.40 * smooth(-0.8, 2.1, rib)
        + 0.18 * smooth(0.25, 0.78, slope),
        0,
        1,
    )
    talus = smooth(0.25, 3.8, -gully) * (1 - smooth(0.62, 1.1, slope))
    old_rock, old_snow, old_soil = original[:, :, :3].transpose(2, 0, 1) / 255
    stone = np.clip(old_rock * (1 - 0.48 * hill) + hill * 0.85 * bedrock, 0, 1)
    snow = old_snow * (1 - hill * (0.50 * bedding + 0.32 * smooth(0.20, 0.85, slope)))
    earth = np.maximum(old_soil, 0.40 * hill * talus)
    base[:, :, :3] = np.rint(np.stack([stone, snow, earth], axis=2) * 255).astype(
        "uint8"
    )
    if not np.array_equal(base[:, :, 3], original[:, :, 3]) or np.any(
        base[protect == 0] != original[protect == 0]
    ):
        raise ValueError("Hill material changed a protected sample")
    Image.fromarray(base).save(out / "T_LandBase.png")
    return {
        "exterior_changed_texels": int((mask > 0.01).sum()),
        "playable_changed_texels": int(np.any(base != original, axis=2).sum()),
        "protected_playable_texels_exact": int((protect == 0).sum()),
        "road_alpha_exact": True,
    }


def build(args):
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    old = np.load(OLD)
    vertices = old["vertices_m"]
    original = vertices.copy()
    contacts = json.loads(GROUND.read_text())
    contacts["cliffs"].extend(json.loads(ORIGINAL_CLIFFS.read_text())["checks"])
    if len({r["id"] for r in contacts["cliffs"]}) != 96:
        raise ValueError("Missing exterior cliff footprint")
    ridges = Ridges(args.survey, contacts)
    vertices[:, 2] = ridges.evaluate(*vertices.T)
    delta = vertices[:, 2] - original[:, 2]
    if np.any(delta[:4032]) or np.any(delta < 0):
        raise ValueError("Invalid collar or crest")
    audit = geology(out, original, vertices[:, 2])
    outer, edge = mesh.write_mesh(
        out, vertices, old["triangles"], old["normals"][:4032]
    )
    level = json.loads(BASE_MAP.read_text())
    actor = next(a for a in level["decor"] if a["id"] == "pwr_distant_apron")
    material = actor["materials"][0]
    material["parent"] = (
        "/Game/MJOLNIR/GrassPilot/Playable/M_PWR_AlpineRidges.M_PWR_AlpineRidges"
    )
    material["vectors"]["RockTint"] = [0.62, 0.72, 0.82, 1]
    material["vectors"]["ApronTiles"] = [240, 220, 1050, 450]
    save_json(out / "geology.material.json", material)
    report = {
        "schema": "pwr-apron-v7",
        "runtime_master_sha256": sha256(mesh.MASTER),
        "source_url": SURVEY,
        "survey_sha256": sha256(args.survey),
        "previous_mesh_sha256": sha256(OLD),
        "footprint_sha256": [sha256(GROUND), sha256(ORIGINAL_CLIFFS)],
        "peaks": PEAKS,
        "triangles": len(old["triangles"]),
        "outer_boundary_edges": outer,
        "maximum_horizontal_edge_m": edge,
        "range_before_m": [
            float(v) for v in (original[:, 2].min(), original[:, 2].max())
        ],
        "range_after_m": [
            float(v) for v in (vertices[:, 2].min(), vertices[:, 2].max())
        ],
        "maximum_rise_m": float(delta.max()),
        "vertex_count_changed": int((delta > 0.01).sum()),
        "geology": audit,
        **{s + "_sha256": sha256(out / ("apron." + s)) for s in ("gltf", "bin")},
    }
    save_json(out / "receipt.json", report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--survey", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    build(p.parse_args())

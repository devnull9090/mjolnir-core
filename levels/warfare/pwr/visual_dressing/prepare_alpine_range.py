# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "scipy", "pillow", "rasterio"]
# ///
"""Prepare a render-only Teton skyline and snow field on the existing apron topology."""

import argparse
import json
import shutil
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from scipy import ndimage as nd
from scipy.spatial import cKDTree

import build_apron_v7 as mesh
from build_survey_ridges import GROUND, ORIGINAL_CLIFFS, save_json, smooth
from heightfield import sha256


BASE = mesh.ROOT / "out/pwr/ground-life/mountains/ridges-final"
DEM = mesh.ROOT / "out/pwr/ground-life/mountains/source/USGS_13_n44w111.tif"
OUT = mesh.ROOT / "out/pwr/alpine-target/range"
CELL = 8000 / 1024


def sample_grid(grid, x, y):
    return nd.map_coordinates(
        grid, [(4000 - y) / CELL - 0.5, (x + 4000) / CELL - 0.5],
        order=1, mode="nearest", prefilter=False,
    )


def skyline(vertices, pose):
    """Project apron vertices into the saved Halo lens; smaller screen Y is higher."""
    eye = np.asarray(pose[:3]) * [.01, -.01, .01]
    dx, dy, dz = (vertices - eye).T
    yaw, pitch, fov = np.radians([-pose[4], pose[3], pose[5]])
    ahead = dx * np.cos(yaw) + dy * np.sin(yaw)
    right = dx * np.sin(yaw) - dy * np.cos(yaw)
    depth = ahead * np.cos(pitch) + dz * np.sin(pitch)
    high = -ahead * np.sin(pitch) + dz * np.cos(pitch)
    facing = depth > 300
    x = .5 + .5 * right[facing] / (depth[facing] * np.tan(fov / 2))
    y = .5 - (16 / 9) * .5 * high[facing] / (depth[facing] * np.tan(fov / 2))
    bins = np.linspace(.62, .88, 14)
    return np.array([y[(x >= a) & (x < b)].min() for a, b in zip(bins[:-1], bins[1:])])


def survey_cirque(x, y):
    # Place the east slope of Mt. Owen beyond the opening to the east of Grand Teton.
    # All samples are taken from the same USGS tile that supplied the near range.
    lon, lat = -110.8023, 43.7477
    dx, dy = x - 2270, y - 3550
    east = (-0.54 * dx - 0.84 * dy) * 2.0
    north = (0.84 * dx - 0.54 * dy) * 1.75
    with rasterio.open(DEM) as survey:
        from rasterio.windows import from_bounds

        window = from_bounds(-110.95, 43.59, -110.66, 43.86, survey.transform)
        window = window.round_offsets().round_lengths()
        tile = survey.read(1, window=window)
        inv = ~survey.window_transform(window)
        col, row = inv * (lon + east / (111320 * np.cos(np.deg2rad(lat))), lat + north / 111110)
        def elevation(r, c):
            return nd.map_coordinates(tile.astype("float32", copy=False), [r - .5, c - .5],
                                      order=1, mode="nearest", prefilter=False)
        crest_col, crest_row = inv * (lon, lat)
        crest = elevation(np.array([crest_row]), np.array([crest_col]))[0]
        surface = 815 + 0.29 * (elevation(row, col) - crest)
    footprint = 1 - smooth(.55, 1, np.hypot((dx - .22 * dy) / 1750, (dy + .20 * dx) / 1070))
    return surface, footprint


def range_field(vertices):
    """The rear range and rib sharpening on the 8 m grid, from the parent apron's vertices.

    Returns grid x, y, the parent height, the protection weight, ribs and rear lift; the
    displacement anywhere is sample_grid((ribs + rear_lift) * weight, x, y)."""
    y, x = np.indices((1024, 1024), dtype=float)
    x = (x + 0.5) * CELL - 4000
    y = 4000 - (y + 0.5) * CELL
    xy_tree = cKDTree(vertices[:, :2])
    ds, ids = xy_tree.query(np.stack([x, y], axis=-1), k=4, workers=2)
    weight = 1 / np.maximum(ds, .01) ** 2
    height = (vertices[ids, 2] * weight).sum(axis=2) / weight.sum(axis=2)

    # Preserve every native prop support, with an extra full triangle of clearance.
    supports = json.loads(GROUND.read_text())
    rows = supports["cliffs"] + supports["trees"] + json.loads(ORIGINAL_CLIFFS.read_text())["checks"]
    protected = np.zeros(height.shape, dtype=bool)
    for row in rows:
        bounds = np.asarray(row["bounds_ue_cm"])[:, :2] * [.01, -.01]
        lo, hi = bounds.min(axis=0) - 60, bounds.max(axis=0) + 60
        left, top = np.floor([(lo[0] + 4000) / CELL, (4000 - hi[1]) / CELL]).astype(int)
        right, bottom = np.ceil([(hi[0] + 4000) / CELL, (4000 - lo[1]) / CELL]).astype(int)
        protected[max(0, top):bottom + 1, max(0, left):right + 1] = True
    distance = nd.distance_transform_edt(~protected) * CELL
    radius = np.maximum(np.abs(x), np.abs(y))
    weight = smooth(20, 160, distance) * smooth(1470, 1920, radius)
    rear, coverage = survey_cirque(x, y)
    rear_lift = np.maximum(rear - height, 0) * coverage

    # Rock ribs and incised drainage are coherent over tens of metres at this camera distance.
    # Sharpen the source relief without changing the position of the major summits.
    high = smooth(335, 760, height)
    relief = nd.gaussian_filter(height, 1) - nd.gaussian_filter(height, 4.3)
    ribs = np.clip(relief * .63, -25, 23) * high
    return x, y, height, weight, ribs, rear_lift, rows


def build(out):
    if out.resolve() == BASE.resolve():
        raise ValueError("Use a separate candidate directory")
    out.mkdir(parents=True, exist_ok=True)
    baseline = json.loads((BASE / "receipt.json").read_text())
    if sha256(DEM) != baseline["survey_sha256"]:
        raise ValueError("The candidate requires the surveyed release source")
    with np.load(BASE / "apron.source.npz") as source:
        vertices = source["vertices_m"]
        triangles = source["triangles"]
        seam_normals = source["normals"][:4032]
    x, y, height, weight, ribs, rear_lift, rows = range_field(vertices)
    vx, vy, original = vertices.T.copy()
    dz = sample_grid((ribs + rear_lift) * weight, vx, vy)
    if np.any(dz[:4032]) or not np.all(np.isfinite(dz)):
        raise ValueError("Invalid seam or ridge displacement")
    frames = mesh.ROOT / "out/pwr/ground-life/visual-review/final.13/frames/frames.json"
    pose = json.loads(frames.read_text())["frames"]["teton-road"]["requested"]
    skyline_before = skyline(vertices, pose)
    vertices[:, 2] = original + dz
    skyline_lift = skyline_before - skyline(vertices, pose)
    height = height + (ribs + rear_lift) * weight
    ridge_ref = nd.gaussian_filter(height, .8)
    gy, gx = np.gradient(ridge_ref, CELL)
    grade = np.hypot(gx, gy)
    cut = nd.gaussian_filter(ridge_ref, 7.5) - ridge_ref
    trough = nd.gaussian_filter(ridge_ref, 2.5) - ridge_ref
    shelter = np.clip(.50 + .50 * (-.68 * gx + .73 * gy) / np.maximum(.07, grade), 0, 1)
    accumulation = smooth(460, 900, height) * (
        .78 * smooth(-2, 17, cut) * smooth(-3.5, 3.5, trough)
        + .40 * smooth(0.86, .21, grade) * shelter
    ) * (1 - .57 * smooth(.73, 1.7, grade))
    snow = smooth(.10, .47, accumulation)
    exposure = np.clip(.57 - .32 * np.tanh(cut / 18) - .17 * np.tanh(trough / 5)
                       + .11 * (gx - gy) / np.maximum(1, grade), 0, 1)
    stone = .62 + .34 * smooth(.20, 1.0, grade) - .17 * smooth(4, 23, cut)
    field = np.array(Image.open(BASE / "T_PWR_ApronField.png").convert("RGBA"))
    old_field = field.copy()
    influence = smooth(320, 620, height) * weight
    for channel, values in ((0, stone), (1, snow), (3, exposure)):
        field[:, :, channel] = np.rint(field[:, :, channel] * (1 - influence) +
                                       np.clip(values, 0, 1) * 255 * influence).astype("uint8")
    if not np.array_equal(field[influence == 0], old_field[influence == 0]):
        raise ValueError("Geology crossed the protected boundary")
    Image.fromarray(field).save(out / "T_PWR_ApronField.png")
    for filename in ("T_LandBase.png", "geology.material.json"):
        shutil.copyfile(BASE / filename, out / filename)
    outer, edge = mesh.write_mesh(out, vertices, triangles, seam_normals)
    summit = (np.abs(x - 400) < 570) & (np.abs(y - 2550) < 650) & (height > 560)
    far = (rear_lift * weight > 30)
    if not np.any(far) or not np.any(field[:, :, 1][summit] >= 128):
        raise ValueError("Missing distant ridge or high-elevation snow")
    receipt = {**baseline, "previous_mesh_sha256": sha256(BASE / "apron.source.npz"),
               "parent_receipt_sha256": sha256(BASE / "receipt.json"),
               "range_before_m": [float(original.min()), float(original.max())],
               "triangles": len(triangles), "outer_boundary_edges": outer,
               "maximum_horizontal_edge_m": edge, "seam_vertices_exact": 4032,
               "protected_objects": len(rows), "range_after_m": [float(vertices[:, 2].min()),
                                                                  float(vertices[:, 2].max())],
               "rear_range_peak_rise_m": float((rear_lift * weight).max()),
               "rear_range_qualified_area_km2": float(far.sum() * CELL**2 / 1e6),
               "teton_skyline_lift_fraction_at_x_0p63_to_0p87": skyline_lift.round(4).tolist(),
               "central_peak_snow_coverage_at_half": [float(np.mean(a[:, :, 1][summit] >= 128))
                                                       for a in (old_field, field)],
               "geology": {"changed_texels": int(np.any(old_field != field, axis=2).sum()),
                           "unchanged_playable_geology": sha256(out / "T_LandBase.png")},
               "vertex_count_changed": int(np.count_nonzero(dz)),
               "maximum_rise_m": float(dz.max()),
               **{s + "_sha256": sha256(out / ("apron." + s)) for s in ("bin", "gltf")}}
    save_json(out / "receipt.json", receipt)
    print(json.dumps({k: receipt[k] for k in ("triangles", "rear_range_peak_rise_m",
                                              "central_peak_snow_coverage_at_half", "geology")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    build(parser.parse_args().out)

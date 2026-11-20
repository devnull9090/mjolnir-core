"""Root an irregular native sedge and fine-grass band along the newly cut lake margins."""

from pathlib import Path
import json
import os
import sys
import numpy as np
from scipy import ndimage
from scipy.spatial import ConvexHull

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "terrain"))
import headwater_dressing as d
import outlet_apron as apron

OUT = Path(os.environ["PWR_HEADWATER_OUTPUT"])
BASE = d.ROOT / "out/pwr/river-apron"


def main():
    field = d.load_heightfield(OUT / "terrain/runtime-master.json")
    old = d.load_heightfield(BASE / "terrain/runtime-master.json")
    geo = d.read(OUT / "terrain/terrain.geometry.json")
    lake = next(x for x in geo["lakes"] if x["id"] == "north_headwater_lake")
    level = lake["water_z_m"]
    xx, yy = np.meshgrid(
        *(
            origin + step * np.arange(n)
            for origin, step, n in zip(
                field.origin_m, field.spacing_m, field.dimensions
            )
        )
    )
    edit = np.abs(old.heights_m - field.heights_m) > 0.02
    dist_edit = ndimage.distance_transform_edt(~edit, sampling=field.spacing_m[::-1])
    wet = (field.heights_m < level - 0.035) & (field.masks["water"] > 0.3)
    drydist = ndimage.distance_transform_edt(~wet, sampling=field.spacing_m[::-1])
    forward, _ = apron.coordinates(np.stack((xx, yy), axis=-1))
    candidates = (
        (dist_edit < 10.0)
        & (drydist > 0.2)
        & (drydist < 7.0)
        & (field.heights_m > level + 0.12)
        & (field.heights_m < level + 2.15)
        & (forward > 60.0)
    )
    candidates &= (
        (field.masks["road"] < 0.01)
        & (field.masks["bases"] < 0.01)
        & (xx > -490)
        & (xx < -218)
        & (yy > 799)
        & (yy < 993)
    )
    ys, xs = np.nonzero(candidates)
    if len(xs) < 30:
        raise ValueError("Unusable shore candidates")
    # Build feather weights for the elevation-based wet strand shader only over the revised basin.
    ry = np.arange(796.0, 1000.1, 4.0)
    rows = []
    for y in ry:
        band = edit & (np.abs(yy - y) < 2.6)
        points = xx[band]
        rows.append(
            [round(float(points.min()), 3), round(float(points.max()), 3)]
            if len(points)
            else [-365.0, -365.0]
        )
    rocks = []
    cache = {}
    for r in d.read(OUT / "dressing/decor-moves.json")["decor"]:
        foot = d.world_foot(r, cache)[:, :2] * d.UE_TO_WORLD
        centre = np.array(r["new_pos_ue_cm"][:2]) * d.UE_TO_WORLD
        rocks.append(
            (
                centre,
                np.linalg.norm(foot, axis=1).max(),
                centre + foot[ConvexHull(foot).vertices],
            )
        )
    plants = {}
    rng = np.random.default_rng(38081)
    for _ in range(min(len(xs) * 2, 1100)):
        i = rng.integers(len(xs))
        x, y = xx[ys[i], xs[i]], yy[ys[i], xs[i]]
        patch = 0.5 + 0.5 * np.cos(x * 0.117 + y * 0.083 + 0.94 * np.sin(y * 0.15))
        if rng.random() > 0.14 + 0.77 * patch:
            continue
        radius = rng.uniform(0.65, 2.1)
        for k in range(rng.integers(5, 14)):
            p = np.array([x, y]) + np.clip(rng.normal(0, radius, 2), -3.0, 3.0)
            if np.min(p - field.origin_m) < 0 or p[1] > 993:
                continue
            z = float(field.sample(*p))
            dz = z - level
            fwd = float(apron.coordinates(p)[0])
            ix, iy = np.rint((p - field.origin_m) / field.spacing_m).astype(int)
            if (
                not 0.16 < dz < 2.15
                or drydist[iy, ix] > 8.1
                or dist_edit[iy, ix] > 10.5
                or fwd < 60.0
            ):
                continue
            if field.sample_mask("water", *p) > 0.12 or any(
                field.sample_mask(t, *p) > 0.01 for t in ("road", "bases")
            ):
                continue
            if any(
                np.linalg.norm(p - c) < rad and d.inside_polygon(p[:1], p[1:], poly)[0]
                for c, rad, poly in rocks
            ):
                continue
            dx = field.sample(p[0] + 0.4, p[1]) - field.sample(p[0] - 0.4, p[1])
            dy = field.sample(p[0], p[1] + 0.4) - field.sample(p[0], p[1] - 0.4)
            if np.hypot(dx, dy) > 0.8:
                continue
            if k == 0 and dz > 0.59 and rng.uniform() < 0.12:
                kind = "willow"
                height = rng.uniform(60, 109)
            elif dz < 0.50 and rng.uniform() < 0.47:
                kind = "sedge"
                height = rng.uniform(32, 59)
            else:
                kind = str(
                    rng.choice(["fine_a", "fine_b", "rush"], p=[0.50, 0.43, 0.07])
                )
                height = rng.uniform(24, 59)
            plants.setdefault(kind, []).append(
                dict(
                    position=[
                        round(100 * p[0], 3),
                        round(-100 * p[1], 3),
                        round(100 * z - 1.2, 3),
                    ],
                    height=round(height, 3),
                    breadth=round(rng.uniform(0.78, 1.43), 4),
                    yaw=round(rng.uniform(-180, 180), 4),
                )
            )
    xyz = np.array([r["position"] for group in plants.values() for r in group]) * [
        0.01,
        -0.01,
        0.01,
    ]
    if not 180 <= len(xyz) <= 10000:
        raise ValueError(len(xyz))
    proof = dict(
        total=len(xyz),
        species={k: len(v) for k, v in plants.items()},
        bounds_m=np.stack((np.min(xyz, axis=0), np.max(xyz, axis=0))).tolist(),
        forward_min_m=float(apron.coordinates(xyz[:, :2])[0].min()),
        terrain_manifest_sha256=field.manifest_sha256,
        water_level_m=level,
    )
    for name, obj in [
        ("basin-plants.json", plants),
        ("basin-strand.json", dict(rows=rows, y_limits=[ry[0], ry[-1]], level=level)),
        ("basin-plant-survey.json", proof),
    ]:
        (OUT / name).write_text(json.dumps(obj, allow_nan=False, separators=(",", ":")))
    print(proof)


if __name__ == "__main__":
    main()

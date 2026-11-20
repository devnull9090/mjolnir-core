# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2,<3", "pillow", "scipy", "shapely"]
# ///
"""Bake the Southwest Sweep duff, vegetated margins and loose aggregate along the driven bend."""

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import struct
import subprocess

import numpy as np
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation

from bake_alpine_roadbed import densify
from prepare_alpine_verges import (
    CLI,
    FIELD,
    FOREST,
    GEO,
    PAKS,
    REVIEW,
    ROOT,
    TREES,
    Camera,
    Site,
    append_foliage,
    lod0_points,
    mesh_info,
    read,
    sha256,
    verify_world,
)


OUT = ROOT / "out/pwr/sweep-polish/verges"
PREV = ROOT / "out/pwr/alpine-target/verges"
EARTH = ROOT / "out/pwr/ground-life/earth"
OWNER = "PWR_SweepForestFloor"
BARK = "/Game/Megascans/3D_Assets/Broken_Tree_Bark_wjhiecy/S_Broken_Tree_Bark_wjhiecy_lod0_Var1"


def write(name, data):
    (OUT / name).write_text(
        json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


def smooth(a, b, value):
    f = np.clip((value - a) / (b - a), 0.0, 1.0)
    return f * f * (3.0 - 2.0 * f)


def sources():
    carry = {r["key"]: r for r in read(PREV / "verges.json")["groups"]}
    keys = ("Fern14", "Fern15", "FescueA", "FescueB", "Moss", "Branch")
    rows = {
        key: {
            k: v
            for k, v in carry[key].items()
            if k not in ("count", "transform_sha256")
        }
        for key in keys
    }
    for row in rows.values():
        # Fade small wind motion first and give the 40 m trunk colonies a complete silhouette.
        if row["key"].startswith("Fescue"):
            row["cull"] = [4800, 7200]
        elif row["key"].startswith("Fern"):
            row["cull"] = [5200, 8200]
    stock = OUT / "stock"
    stock.mkdir(exist_ok=True)
    leaf = BARK.split("/")[-1]
    bark = stock / (leaf + ".glb")
    if not bark.is_file():
        subprocess.run(
            [CLI, "mesh", "export", "--paks", PAKS, "--asset", leaf, "--out", bark],
            check=True,
        )
    info = mesh_info(str(CLI), str(PAKS), BARK)
    rows["Bark"] = dict(
        mesh=BARK + "." + leaf,
        source_glb=str(bark.relative_to(ROOT)),
        sha256=sha256(bark),
        origin=info["origin"],
        extent=info["extent"],
        standin_slots=info["slots"],
    )
    for i, rock in enumerate(read(EARTH / "stock-native.json")[:3], 1):
        glb = EARTH / "stock" / rock["source_file"]
        rows[f"Gravel{i}"] = dict(
            mesh=rock["path"],
            source_glb=str(glb.relative_to(ROOT)),
            sha256=rock["sha256"],
            origin=rock["native"]["origin"],
            extent=rock["native"]["extent"],
            standin_slots=rock["native"]["slots"],
        )
    meshes = {}
    for key, row in rows.items():
        path = ROOT / row["source_glb"]
        if sha256(path) != row["sha256"]:
            raise ValueError(f"Source geometry changed for {key}")
        v = np.unique(lod0_points(path) * 0.01, axis=0)
        lo, hi = v.min(0), v.max(0)
        row.update(key=key, exact=True, visible_bounds_m=[lo.tolist(), hi.tolist()])
        if key == "Bark" or key.startswith("Gravel"):
            row.update(wpo=0, flags=34, material=None, cull=[2600, 4600])
        # Quantiles and actual bottom vertices seat the mesh on the local tangent plane.
        # Keep a representative height envelope for verifying the inclines at authoring time.
        meshes[key] = (max((hi - lo)[:2]), np.quantile(v[:, 2], 0.055), hi[2], lo[2])
    return rows, meshes


class Road:
    def __init__(self, site):
        original = next(r for r in site.roads if r["id"] == "southwest_sweep")
        self.xy = densify(np.array(original["centreline_m"])[:, :2])
        self.ds = np.r_[0, np.cumsum(np.linalg.norm(np.diff(self.xy, axis=0), axis=1))]
        self.tree = cKDTree(self.xy)

    def frame(self, station):
        i = np.clip(np.searchsorted(self.ds, station), 1, len(self.ds) - 2)
        tangent = self.xy[i + 1] - self.xy[i - 1]
        tangent /= np.linalg.norm(tangent, axis=-1, keepdims=True)
        return np.column_stack(
            (
                np.interp(station, self.ds, self.xy[:, 0]),
                np.interp(station, self.ds, self.xy[:, 1]),
            )
        ), np.stack((-tangent[..., 1], tangent[..., 0]), axis=-1)

    def surveys(self, xy):
        _, i = self.tree.query(xy)
        s = self.ds[i]
        center, normal = self.frame(s)
        return s, np.sum((xy - center) * normal, axis=-1)

    @staticmethod
    def margin(station, side):
        # Signed stations/offsets were projected from the reference bend onto the native field.
        # The narrower visual road retains all 24 metres of the collision-graded bed.
        left = np.interp(
            station,
            [0, 70, 104, 117, 124.5, 128, 130, 149, 195, 300],
            [6.3, 6, 5.4, 5.65, 5.55, 5.11, 4.38, 5.8, 5.9, 6.0],
        )
        right = np.interp(
            station,
            [0, 80, 115, 123, 140, 180, 280],
            [7.8, 7.1, 9.33, 7.9, 7.1, 8, 7.3],
        )
        scallop = 0.28 * np.sin(station * 0.54 + side) + 0.14 * np.sin(station * 1.05)
        return np.where(side < 0, left, right) + scallop


class Planting:
    def __init__(self, scene, road):
        self.scene = scene
        self.road = road
        self.rng = np.random.default_rng(153241)
        self.plants = defaultdict(list)
        self.props = read(PREV / "structural.json")
        self.trees = np.array([v["position"][:2] for v in read(TREES)["instances"]])
        self.camera = Camera(
            read(REVIEW / "field-check-cameras.json")["cameras"][FOREST]["pose"]
        )
        self.root_index = cKDTree(self.trees)

    def add(
        self,
        kind,
        xy,
        width,
        *,
        yaw=None,
        squeeze=1.0,
        role="forest verge",
        base=None,
        vector=None,
    ):
        # width is the final dominant horizontal dimension in metres, after native import.
        if yaw is None:
            yaw = self.rng.uniform(0, 360)
        self.plants[kind].append(
            (np.asarray(xy), width, yaw, squeeze, role, base, vector)
        )

    def patches(self):
        g = self.rng
        # Ribbons on both sides follow continuous road station, the same frame as the surface pass.
        for side in (-1, 1):
            for station in np.arange(52, 244, 1.1):
                edge = self.road.margin(station, side)
                fade = smooth(52, 70, station) * (1 - smooth(220, 244, station))
                if g.random() > fade:
                    continue
                for outer, number, spread in (
                    (0.30, 7, 0.48),
                    (1.45, 9, 0.75),
                    (3.65, 13, 1.35),
                    (6.5, 7, 1.7),
                ):
                    d = edge + outer + g.normal(0, 0.45)
                    p, n = self.road.frame([station])
                    p = p[0] + side * n[0] * d
                    root = self.root_index.query(p)[0]
                    # Open stretches are dominated by flat litter. Fern islands need shelter.
                    fullness = (
                        0.45
                        + 0.45
                        * (
                            1
                            + np.sin(station * 0.28 + side)
                            * np.sin(station * 0.075 - 0.8)
                        )
                        / 2
                    )
                    for _ in range(g.poisson(number * fullness)):
                        local = p + g.normal(0, [spread, spread * 0.72])
                        if outer < 0.5:
                            kind = g.choice(
                                ["FescueA", "FescueB", "Bark", "Branch", "Moss"],
                                p=[0.23, 0.31, 0.21, 0.19, 0.06],
                            )
                        elif outer < 2:
                            kind = g.choice(
                                [
                                    "FescueA",
                                    "FescueB",
                                    "Bark",
                                    "Branch",
                                    "Moss",
                                    "Fern14",
                                ],
                                p=[0.32, 0.27, 0.13, 0.09, 0.14, 0.05],
                            )
                        else:
                            kind = g.choice(
                                [
                                    "FescueA",
                                    "FescueB",
                                    "Fern14",
                                    "Fern15",
                                    "Moss",
                                    "Branch",
                                    "Bark",
                                ],
                                p=[0.30, 0.26, 0.11, 0.09, 0.12, 0.06, 0.06]
                                if root < 15
                                else [0.41, 0.35, 0.05, 0.03, 0.07, 0.05, 0.04],
                            )
                        widths = {
                            "FescueA": (0.30, 0.70),
                            "FescueB": (0.23, 0.62),
                            "Moss": (0.14, 0.43),
                            "Fern14": (0.25, 0.53),
                            "Fern15": (0.48, 0.92),
                            "Bark": (0.10, 0.38),
                            "Branch": (0.18, 0.62),
                        }
                        squeeze = (
                            (0.36 if kind == "Moss" else 0.60)
                            if outer < 0.5
                            else (0.76 if kind.startswith("Fescue") else 0.85)
                        )
                        self.add(kind, local, g.uniform(*widths[kind]), squeeze=squeeze)
        # Ferns cluster around each native root flare, with a ragged collar opening into the road.
        s, side = self.road.surveys(self.trees)
        selected = self.trees[(s > 50) & (s < 244) & (abs(side) < 32)]
        for center in selected:
            for _ in range(g.integers(3, 6)):
                phi = g.uniform(0, 2 * np.pi)
                clump = center + np.array([np.cos(phi), np.sin(phi)]) * g.uniform(
                    1.2, 4.0
                )
                for _ in range(g.integers(5, 10)):
                    p = clump + g.normal(0, 0.55, 2)
                    if np.linalg.norm(p - center) < 0.95:
                        continue
                    k = g.choice(
                        ["Fern15", "Fern14", "Moss", "Branch", "Bark", "FescueB"],
                        p=[0.25, 0.17, 0.18, 0.10, 0.11, 0.19],
                    )
                    width = (
                        g.uniform(0.56, 1.06)
                        if k == "Fern15"
                        else g.uniform(0.24, 0.56)
                    )
                    self.add(k, p, width, role="root collar")

    def gravel(self):
        # Sparse real three-dimensional aggregate anchors the fine gravel in the material.
        g = self.rng
        keys = ("Gravel1", "Gravel2", "Gravel3")
        for station in g.uniform(53, 241, 2850):
            sign = g.choice([-1, 1])
            edge = self.road.margin(station, sign)
            offset = g.choice(
                [
                    g.uniform(0.12, 1.1),
                    g.uniform(2.05, edge + 0.7),
                    g.normal(edge + 0.25, 0.72),
                ],
                p=[0.12, 0.24, 0.64],
            )
            p, n = self.road.frame([station])
            center = p[0] + n[0] * sign * offset
            for _ in range(1 + g.poisson(1.65)):
                xy = center + g.normal(0, 0.17, 2)
                width = (
                    g.uniform(0.028, 0.112)
                    if offset < edge - 0.7
                    else g.uniform(0.037, 0.135)
                )
                self.add(
                    g.choice(keys),
                    xy,
                    width,
                    squeeze=g.uniform(0.28, 0.66),
                    role="loose gravel",
                )
        # Talus delivered by the outcrops forms short fans instead of a blanket of uniform stones.
        for s0, side, length in [
            (89, 1, 7.0),
            (126, -1, 7.8),
            (128, 1, 5.3),
            (177, -1, 6.2),
        ]:
            for _ in range(190):
                s = g.normal(s0, length)
                edge = self.road.margin(s, side)
                offset = g.normal(edge - 0.52, 1.06)
                p, n = self.road.frame([s])
                center = p[0] + n[0] * side * offset
                for _ in range(g.integers(2, 7)):
                    self.add(
                        g.choice(keys),
                        center + g.normal(0, 0.20, 2),
                        g.uniform(0.035, 0.092),
                        squeeze=g.uniform(0.31, 0.55),
                        role="gravel fan",
                    )

    def mossy_boulders(self):
        g = self.rng
        outcrop = next(
            s for s in read(PREV / "verges.json")["groups"] if s["key"] == "Outcrop"
        )
        source = lod0_points(ROOT / outcrop["source_glb"]) / 100
        for row in self.props:
            if row["camera"] != FOREST or row["kind"] != "Outcrop":
                continue
            pose = Rotation.from_quat(row["rotation_xyzw"])
            xyz = pose.apply(source * row["scale_xyz"]) * [1, -1, 1] + row["position_m"]
            tree = cKDTree(xyz[:, :2])
            extent = np.ptp(xyz, axis=0)
            count = int(np.prod(extent[:2]) * 30)
            for _ in range(count):
                xy = g.uniform(xyz[:, :2].min(0), xyz[:, :2].max(0))
                distance, hits = tree.query(xy, 18)
                if distance[0] > 0.06:
                    continue
                top = xyz[hits, 2].max()
                if top < self.scene.height(xy) + 0.06:
                    continue
                # Use only the upward, weathered face. The mineral is still visible between lichens.
                if (
                    0.45 * np.cos(xy[0] * 3.3 + xy[1] * 1.25)
                    + 0.4 * np.sin(xy[1] * 3.6 - xy[0] * 1.45)
                    < -0.30
                ):
                    continue
                offsets = np.array([[0.08, 0], [-0.08, 0], [0, 0.08], [0, -0.08]])
                distances, incident = tree.query(xy + offsets, 12)
                if distances[:, 0].max() > 0.09:
                    continue
                h = xyz[incident, 2].max(axis=1)
                slope = [(h[0] - h[1]) / 0.16, (h[2] - h[3]) / 0.16]
                if np.linalg.norm(slope) > 1.25:
                    continue
                self.add(
                    "Moss",
                    xy,
                    g.uniform(0.24, 0.47),
                    squeeze=0.32,
                    role="moss on native rock",
                    base=top - 0.022,
                    vector=slope,
                )
            for _ in range(32):
                xy = g.normal(xyz[:, :2].mean(0), extent[:2] * 0.48)
                if tree.query(xy)[0] < 0.12:
                    continue
                self.add(
                    g.choice(["Fern14", "Fern15"]),
                    xy,
                    g.uniform(0.36, 0.77),
                    role="rock foot",
                )
        # Extend the base of the left outcrop along its actual strike. Tall forms stay against
        # the existing solid rock; within the graded bed only a low, driveable moss apron continues.
        for _ in range(135):
            t = g.random()
            xy = (
                np.array([-604.5, -531.35])
                + np.array([3.65, 0.38]) * t
                + g.normal(0, [0.43, 0.47], 2)
            )
            _, off = self.road.surveys(xy[None, :])
            width = g.uniform(0.43, 0.92)
            scale_z = (
                g.uniform(0.42, 0.60) if abs(off[0]) > 12.6 else g.uniform(0.11, 0.19)
            )
            self.add("Moss", xy, width, squeeze=scale_z, role="moss apron")
            if g.random() < 0.38:
                self.add(
                    "Fern15",
                    xy + g.normal(0, 0.51, 2),
                    g.uniform(0.48, 0.88),
                    role="rock foot",
                )
        # Two grounded split strips of scanned bark give the left bank a legible deadwood edge.
        for x, y, w, yaw in [
            (-598.65, -533.6, 1.62, 121),
            (-598.18, -532.3, 1.43, 109),
            (-597.83, -531.16, 1.66, 101),
            (-597.45, -529.8, 1.48, 107),
            (-596.6, -538.2, 0.86, 155),
        ]:
            self.add("Bark", [x, y], w, yaw=yaw, squeeze=0.35, role="split bank bark")

    def export(self, definitions, meshes):
        binary = OUT / "verges.bin"
        binary.write_bytes(b"MJF3" + struct.pack("<II", 3, 0))
        groups, summary, roles = [], {}, Counter()
        masks = np.zeros((4, 6), dtype=int)
        max_gravel = 0.0
        for key, rows in sorted(self.plants.items()):
            xy = np.array([r[0] for r in rows])
            station, signed = self.road.surveys(xy)
            inside = abs(signed) < 11.9
            # No tall plant reaches the wheel tracks. Only brush and flat aggregate occupy the shoulders.
            allowed = np.ones(len(xy), dtype=bool)
            if key.startswith("Fern"):
                allowed &= (
                    abs(signed) > self.road.margin(station, np.sign(signed)) + 1.65
                )
            elif key.startswith("Fescue"):
                allowed &= (
                    abs(signed) > self.road.margin(station, np.sign(signed)) - 0.18
                )
            elif not key.startswith("Gravel"):
                allowed &= abs(signed) > 3.8
            for name in ("water", "shore", "bases"):
                allowed &= self.scene.ground.sample_mask(name, *xy.T) < 0.006
            for p, r in self.scene.protected:
                allowed &= np.sum((xy - p) ** 2, axis=1) > (r + 1.5) ** 2
            rows = [r for r, keep in zip(rows, allowed) if keep]
            xy, inside = xy[allowed], inside[allowed]
            if not len(xy):
                continue
            width, burial, hi, lo = meshes[key]
            scale = np.array([r[1] / width for r in rows])
            sz = scale * np.array([r[3] for r in rows])
            if key.startswith("Gravel"):
                sz = np.minimum(sz, 0.035 / max(hi - burial, 0.001))
                max_gravel = max(max_gravel, float(np.max((hi - burial) * sz)))
            if key.startswith("Fern"):
                sz = np.where(inside, np.minimum(sz, 0.28 / max(hi - burial, 0.01)), sz)
            z = self.scene.height(xy)
            sx = (
                self.scene.height(xy + [0.20, 0]) - self.scene.height(xy - [0.20, 0])
            ) / 0.4
            sy = (
                self.scene.height(xy + [0, 0.20]) - self.scene.height(xy - [0, 0.20])
            ) / 0.4
            for i, row in enumerate(rows):
                if row[5] is not None:
                    z[i] = row[5]
                    sx[i], sy[i] = row[6]
            z -= sz * burial + (0.003 if key.startswith("Gravel") else 0.006)
            normals = np.column_stack((-sx, sy, np.ones(len(z))))
            normals /= np.linalg.norm(normals, axis=1)[:, None]
            yaw = np.radians([r[2] for r in rows])
            tang = np.column_stack((np.cos(yaw), np.sin(yaw), np.zeros(len(z))))
            tang -= normals * np.sum(tang * normals, axis=1)[:, None]
            tang /= np.linalg.norm(tang, axis=1)[:, None]
            rotation = Rotation.from_matrix(
                np.stack((tang, np.cross(normals, tang), normals), axis=-1)
            ).as_quat()
            xyz = np.column_stack((xy, z)) * [100, -100, 100]
            sidecar = OUT / ("verges.bin.xf" + str(len(groups) + 1))
            np.column_stack((xyz, rotation, scale, scale, sz)).astype("<f4").tofile(
                sidecar
            )
            append_foliage(
                binary,
                np.column_stack((xyz, np.zeros(len(z)), scale, np.zeros((len(z), 2)))),
            )
            groups.append(
                dict(
                    definitions[key], count=len(rows), transform_sha256=sha256(sidecar)
                )
            )
            uv = self.camera.project(np.column_stack((xy, z)))
            seen = (uv[:, 2] > 0) & np.all((uv[:, :2] >= 0) & (uv[:, :2] < 1), axis=1)
            np.add.at(
                masks, ((uv[seen, 1] * 4).astype(int), (uv[seen, 0] * 6).astype(int)), 1
            )
            summary[key] = {
                "count": len(rows),
                "visible_pivots_from_driver": int(seen.sum()),
                "interior_gradation": int(inside.sum()),
                "max_height_cm": round(float(np.max(sz * (hi - burial)) * 100), 2),
            }
            roles.update([r[4] for r in rows])
        count = sum(r["count"] for r in groups)
        write(
            "verges.json",
            dict(
                actor=OWNER,
                file=binary.name,
                count=count,
                groups=groups,
                binary_sha256=sha256(binary),
                source_sha256={
                    str(f.relative_to(ROOT)): sha256(f)
                    for f in (FIELD, GEO, TREES, PREV / "structural.json")
                },
            ),
        )
        write(
            "verification.json",
            dict(
                groups=summary,
                roles=roles,
                total=count,
                driver_grid_6x4=masks.tolist(),
                maximum_loose_stone_above_local_plane_cm=round(max_gravel * 100, 2),
                changes_to_structural_transforms=0,
                changes_to_collision=0,
                source_camera=self.camera.pose,
            ),
        )
        print(
            json.dumps(
                {"total": count, "groups": summary, "grid": masks.tolist()}, indent=1
            )
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-world", type=Path)
    args = parser.parse_args()
    if args.verify_world:
        verify_world(args.verify_world, folder=OUT, prefix="PWRSweep_")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    definitions, meshes = sources()
    site = Site()
    planting = Planting(site, Road(site))
    planting.patches()
    planting.gravel()
    planting.mossy_boulders()
    planting.export(definitions, meshes)


if __name__ == "__main__":
    main()

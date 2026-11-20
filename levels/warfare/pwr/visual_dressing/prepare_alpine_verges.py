# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2,<3", "scipy>=1.15", "pillow>=11", "shapely>=2", "trimesh>=4"]
# ///
"""Bake the fixed alpine road edges from the released native surface and tree pivots."""

from collections import Counter
import json
from pathlib import Path
import struct
import subprocess
import sys

import numpy as np
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation

from outcrops_v3 import lod0_points
from prepare_wind_grass import ROOT, CLI, FIELD, PAKS, qpath
from heightfield import load_heightfield, sha256
from foliage_bake import mesh_info
from upgrade_ce_map import append_foliage


OUT = ROOT / "out/pwr/alpine-target/verges"
REVIEW = ROOT / "out/pwr/ground-life/visual-review"
GEO = ROOT / "levels/warfare/pwr/terrain/final-v5/terrain.geometry.json"
TREES = ROOT / "out/pwr/visual-v6/scenery/trees/trees.selected.json"
DISCS = ROOT / "out/pwr/visual-v5/forest-v2/inputs.receipt.json"
NATIVE = ROOT / "out/pwr/ground-life/saturday.13/map-input/pwr.level.json"
ROCKS = ROOT / "out/pwr/visual-v4/assets/rock-bounds.json"
TETON, FOREST = "teton-road", "southwest-forest-road-driver"
HERO_XY = (-419.0, -77.0)


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def dump(name, data):
    (OUT / name).write_text(
        json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


def clipped(value):
    return np.asarray(value).round(5).tolist()


class Camera:
    def __init__(self, pose):
        self.pose = pose
        self.eye = np.asarray(pose[:3]) * [0.01, -0.01, 0.01]
        p, y, f = np.radians(pose[3:])
        self.heading = np.array([np.cos(y), -np.sin(y)])
        self.right = np.array([-np.sin(y), -np.cos(y), 0])
        self.forward = np.r_[self.heading * np.cos(p), np.sin(p)]
        self.up = np.r_[-self.heading * np.sin(p), np.cos(p)]
        self.tan = np.tan(f / 2)

    def project(self, xyz):
        v = np.asarray(xyz) - self.eye
        d = v @ self.forward
        return np.stack(
            (
                0.5 + (v @ self.right) / (2 * self.tan * d),
                0.5 - (v @ self.up) * 16 / (18 * self.tan * d),
                d,
            ),
            axis=-1,
        )


class Site:
    def __init__(self):
        self.ground = load_heightfield(FIELD)
        self.roads = read(GEO)["roads"]
        edges, widths = [], []
        for road in self.roads:
            line = np.array(road["centreline_m"])[:, :2]
            pair = np.stack((line[:-1], line[1:]), axis=1)
            pair = pair[np.linalg.norm(pair[:, 1] - pair[:, 0], axis=1) > 0.001]
            edges.extend(pair)
            widths.extend([road["width_m"] / 2] * len(pair))
        self.a, end = np.array(edges).transpose(1, 0, 2)
        self.delta = end - self.a
        self.length2 = (self.delta**2).sum(axis=-1)
        self.width = np.array(widths)
        self.road_index = cKDTree((end + self.a) / 2)
        self.trunks = cKDTree([p["position"][:2] for p in read(TREES)["instances"]])
        self.protected = [
            (np.array(xy), radius) for _, xy, radius in read(DISCS)["clearance_discs"]
        ]
        level = read(NATIVE)
        for r in (
            level["blam"]["player_starts"]
            + level["blam"]["vehicles"]
            + level["markers"]
        ):
            self.protected.append((np.array(r["pos"][:2]) * [0.01, -0.01], 12))
        for x, y, _, rad, *_ in level["koth_hills"]:
            self.protected.append((np.array([x, -y]) / 100, rad / 100 + 5))
        catalog = {r["path"]: r for r in read(ROCKS)}
        for r in level["decor"]:
            if r["mesh"] in catalog:
                b = catalog[r["mesh"]]
                span = np.maximum(np.abs(b["min"]), np.abs(b["max"]))
                self.protected.append(
                    (
                        np.array(r["pos"][:2]) * [0.01, -0.01],
                        np.linalg.norm(span * r.get("scale", [1, 1, 1])) / 100,
                    )
                )
        self.protected_xy = np.array([p for p, _ in self.protected])
        self.protected_radius = np.array([r for _, r in self.protected])

    def road_margin(self, xy):
        _, i = self.road_index.query(xy, k=28)
        off = xy - self.a[i]
        t = np.clip(np.sum(off * self.delta[i], axis=1) / self.length2[i], 0, 1)
        return float(
            np.min(
                np.linalg.norm(off - t[:, None] * self.delta[i], axis=1) - self.width[i]
            )
        )

    def allowed(self, xy, radius):
        if self.road_margin(xy) < radius + 0.12:
            return False
        if np.any(
            np.linalg.norm(xy - self.protected_xy, axis=1)
            < self.protected_radius + radius
        ):
            return False
        for cx, cy in [(-590, -80), (600, -80), (0, 690)]:
            if (
                abs(xy[0] - cx) < 112 + radius
                and cy - 125 - radius < xy[1] < cy + 142 + radius
            ):
                return False
        t = np.linspace(0, 2 * np.pi, 9, endpoint=False)
        pts = np.vstack(
            (xy, xy + (radius + 1.5) * np.stack((np.cos(t), np.sin(t)), axis=-1))
        )
        for mask in ("water", "shore", "bases"):
            if self.ground.sample_mask(mask, *pts.T).max() > 0.006:
                return False
        return True

    def height(self, xy):
        return self.ground.sample(*np.asarray(xy).T)

    def rotation(self, xy, degrees, vertical=False):
        x, y = xy
        slope_x = self.height([x + 0.5, y]) - self.height([x - 0.5, y])
        slope_y = self.height([x, y + 0.5]) - self.height([x, y - 0.5])
        if vertical:
            return Rotation.from_euler("z", degrees, degrees=True)
        normal = np.array([-slope_x, slope_y, 1.0])
        normal /= np.linalg.norm(normal)
        flat = np.r_[np.cos(np.radians(degrees)), np.sin(np.radians(degrees)), 0.0]
        tangent = flat - normal * np.dot(normal, flat)
        tangent /= np.linalg.norm(tangent)
        return Rotation.from_matrix(
            np.column_stack((tangent, np.cross(normal, tangent), normal))
        )


def sources():
    stock = OUT / "stock"
    stock.mkdir(parents=True, exist_ok=True)
    game = ROOT / "out/pwr/ground-life"
    pine = ROOT / "out/pwr/visual-v5/outcrops-v4/trees/native/package-readback.glb"
    stone = ROOT / "out/pwr/visual-v5/outcrops-v3/assets/SM_Rock_Glacial_Med_A.glb"
    floor = {r["key"]: r for r in read(game / "forest.13/floor.json")["groups"]}
    # Each object path below is the one referenced by a gameplay package.
    assets = {
        "Pine": (
            "/Game/MJOLNIR/Scenery/PWR/SM_PWR_MaturePine_A",
            pine,
            [90000, 180000],
        ),
        "Outcrop": (
            "/Game/Env/Bio/Rock/Glacial/Rock_Glacial_Med_A/SM_Rock_Glacial_Med_A",
            stone,
            [35000, 60000],
        ),
        "Log": (None, "S_Fallen_Tree_Log_xiclaj1r_lod0_Var1", [19000, 32000]),
        "Branch": (None, "SM_DryBranches_01", [3800, 7000]),
        "Moss": (None, "SM_Mossy_Stones_Pack_tliiadmva_Var_02", [4100, 8500]),
    }
    for key in ("FescueA", "FescueB", "Fern14", "Fern15"):
        leaf = floor[key]["mesh"].split(".")[-1]
        cache = "grass.12" if key.startswith("Fescue") else "forest.13"
        assets[key] = (
            floor[key]["mesh"].split(".")[0],
            game / cache / "cooked-proof" / (leaf + ".glb"),
            floor[key]["cull"],
        )
    metadata, verts = {}, {}
    for kind, (pkg, glb, cull) in assets.items():
        if pkg is None:
            search = glb
            receipt = stock / (search + ".json")
            if not receipt.exists():
                subprocess.run(
                    [
                        CLI,
                        "mesh",
                        "list",
                        "--paks",
                        PAKS,
                        "--filter",
                        search,
                        "--out",
                        receipt,
                    ],
                    check=True,
                )
            matches = [r for r in read(receipt) if r["path"].endswith("." + search)]
            if len(matches) != 1:
                raise ValueError(f"Ambiguous stock reference for {search}")
            pkg = matches[0]["path"].split(".")[0]
            glb = stock / (search + ".glb")
            if not glb.exists():
                subprocess.run(
                    [
                        CLI,
                        "mesh",
                        "export",
                        "--paks",
                        PAKS,
                        "--asset",
                        pkg.removeprefix("/Game/"),
                        "--out",
                        glb,
                    ],
                    check=True,
                )
        mesh = qpath(pkg)
        verts[kind] = np.unique(lod0_points(glb) * 0.01, axis=0)
        lo, hi = verts[kind].min(axis=0), verts[kind].max(axis=0)
        source = (
            ROOT
            / "out/pwr/ground-life/editor/Meteorite/Content"
            / (pkg.removeprefix("/Game/") + ".uasset")
        )
        row = dict(
            mesh=mesh,
            cull=cull,
            source_glb=str(glb.relative_to(ROOT)),
            sha256=sha256(glb),
            visible_bounds_m=clipped([lo, hi]),
            has_baseline_editor_package=source.exists(),
            material=floor.get(kind, {}).get("material"),
            wpo=floor.get(kind, {}).get("wpo", 0),
        )
        if not source.exists():
            if kind in ("Pine", "FescueA", "FescueB"):
                raise ValueError("Missing authored editor asset: " + mesh)
            info = mesh_info(str(CLI), str(PAKS), pkg)
            row.update(
                origin=info["origin"],
                extent=info["extent"],
                standin_slots=info["slots"],
            )
        metadata[kind] = row
    return metadata, verts


class Dressing:
    def __init__(self, site, metadata, verts):
        self.site, self.metadata, self.verts = site, metadata, verts
        self.points = []
        self.cameras = {
            TETON: Camera(read(REVIEW / "cameras.json")[TETON]["pose"]),
            FOREST: Camera(
                read(REVIEW / "field-check-cameras.json")["cameras"][FOREST]["pose"]
            ),
        }
        self.structural = []
        self.rng = np.random.default_rng(132411)

    def plant(self, kind, xy, scale, heading, camera, patch, required=False):
        xy, v = np.array(xy, dtype=float), self.verts[kind]
        lo, hi = np.array(self.metadata[kind]["visible_bounds_m"])
        # Obstacles are tested against a disc enclosing every rotated ground projection.
        radius = np.linalg.norm(np.maximum(abs(lo), abs(hi))[:2]) * scale
        if not self.site.allowed(xy, radius):
            if required:
                raise ValueError(
                    f"Unsafe {kind} at {xy}, radius {radius}, road margin {self.site.road_margin(xy)}"
                )
            return False
        structural = kind in ("Pine", "Outcrop", "Log")
        existing_root_gap = self.site.trunks.query(xy)[0]
        if structural:
            core = min(radius, 2.5) if kind != "Pine" else max(2, radius * 0.55)
            if existing_root_gap < core + 0.75 or any(
                np.linalg.norm(xy - pos) < core + gap for pos, gap in self.structural
            ):
                if required:
                    raise ValueError(f"Overlapping {kind} at {xy}")
                return False
        elif existing_root_gap < 0.5:
            return False
        if kind == "Log":
            # Orient the principal axis of the scanned trunk along the road bank.
            _, vectors = np.linalg.eigh(np.cov(v[:, :2].T))
            heading -= np.degrees(np.arctan2(*vectors[:, -1][::-1]))
        rot = self.site.rotation(xy, heading, vertical=kind == "Pine")
        z = float(self.site.height(xy))
        scale_xyz = np.array(
            [scale, scale, scale * (0.65 if kind == "Outcrop" else 1.0)]
        )
        offsets = rot.apply(v * scale_xyz)
        ground_pts = xy + offsets[:, :2] * [1, -1]
        diff = z + offsets[:, 2] - self.site.height(ground_pts)
        if kind != "Pine":
            # A small portion of roots, moss and bark disappears into the soil.
            # Quantiles provide several contact patches on bent logs.
            burial = {
                "Log": 0.045,
                "Outcrop": 0.09,
                "Moss": 0.012,
                "Branch": 0.008,
            }.get(kind, 0.012)
            contact = float(np.quantile(diff, 0.10 if structural else 0.035))
            z -= contact + burial
            diff -= contact + burial
        # Re-evaluate clearance with the final tilted mesh's actual horizontal support.
        final_radius = float(np.max(np.linalg.norm(ground_pts - xy, axis=1)))
        if final_radius > radius and not self.site.allowed(xy, final_radius):
            if required:
                raise ValueError("Tilted mesh exceeds allowed area")
            return False
        if diff.min() > 0.01 or diff.max() < 0.01:
            if required:
                raise ValueError("No visible ground contact")
            return False
        if structural:
            self.structural.append((xy, core))
        screen = self.cameras[camera].project(
            np.column_stack((ground_pts, z + offsets[:, 2]))
        )
        front = screen[screen[:, 2] > 0.1, :2]
        row = dict(
            id=len(self.points),
            kind=kind,
            patch=patch,
            camera=camera,
            mesh=self.metadata[kind]["mesh"],
            position_m=clipped([*xy, z]),
            position_cm=clipped([xy[0] * 100, -xy[1] * 100, z * 100]),
            rotation_xyzw=rot.as_quat().tolist(),
            scale_xyz=scale_xyz.tolist(),
            full_mesh_road_margin_m=round(self.site.road_margin(xy) - final_radius, 4),
            support_range_cm=clipped([diff.min() * 100, diff.max() * 100]),
            existing_trunk_distance_m=round(float(existing_root_gap), 3),
            screen_bbox_uv=clipped([front.min(axis=0), front.max(axis=0)])
            if len(front)
            else None,
        )
        self.points.append(row)
        return True

    def cluster(self, xy, heading, camera, role, width=2.7, count=36):
        rng = self.rng
        ang = np.radians(-heading)
        u = np.array([np.cos(ang), np.sin(ang)])
        perp = np.array([-u[1], u[0]])
        for _ in range(count):
            offset = u * rng.normal(0, width) + perp * rng.normal(0, width * 0.46)
            at = xy + offset
            tree_dist = self.site.trunks.query(at)[0]
            key = rng.choice(
                ["FescueA", "FescueB", "Moss", "Branch", "Fern14", "Fern15"],
                p=[0.33, 0.28, 0.16, 0.06, 0.09, 0.08]
                if tree_dist < 12 or role == "pine-root"
                else [0.44, 0.36, 0.13, 0.04, 0.015, 0.015],
            )
            scale = (
                rng.uniform(0.80, 1.48) if key != "Branch" else rng.uniform(0.85, 1.55)
            )
            self.plant(key, at, float(scale), rng.uniform(0, 360), camera, role)

    def design(self):
        rng = self.rng
        self.plant("Pine", HERO_XY, 0.536, 157, TETON, "foreground-pine", True)
        # Use a road's own sampled tangent and signed normal for both its verge and its bends.
        for name, route_id in [
            (TETON, "red_upper_approach"),
            (FOREST, "southwest_sweep"),
        ]:
            cam = self.cameras[name]
            line = np.asarray(
                next(r for r in self.site.roads if r["id"] == route_id)["centreline_m"]
            )[:, :2]
            ds = np.r_[0, np.cumsum(np.linalg.norm(np.diff(line, axis=0), axis=1))]
            s0 = ds[np.linalg.norm(line - cam.eye[:2], axis=1).argmin()]
            half = (
                next(r["width_m"] for r in self.site.roads if r["id"] == route_id) / 2
            )
            for s in np.arange(max(2, s0 - 92), min(ds[-1] - 2, s0 + 112), 4.9):
                i = int(np.clip(np.searchsorted(ds, s), 1, len(ds) - 2))
                u = line[i + 1] - line[i - 1]
                u /= np.linalg.norm(u)
                perp = np.array([-u[1], u[0]])
                for side in [-1, 1]:
                    if rng.random() < 0.20:
                        continue
                    bank = line[i] + side * perp * (half + rng.uniform(0.45, 3.5))
                    heading = -np.degrees(np.arctan2(u[1], u[0]))
                    self.cluster(bank, heading, name, "outer-verge", 2.5, 12)
            near = self.site.trunks.query_ball_point(cam.eye[:2], 78)
            for i in near:
                root = self.site.trunks.data[i]
                f = np.dot(root - cam.eye[:2], cam.heading)
                if f < -10 or self.site.road_margin(root) > 28:
                    continue
                t = rng.uniform(0, np.pi * 2)
                self.cluster(
                    root + 2.3 * np.array([np.cos(t), np.sin(t)]),
                    rng.uniform(0, 360),
                    name,
                    "existing-root",
                    2.0,
                    25,
                )
        for xy, kind, desired, ang, cam in [
            ((-411.8, -90.5), "Outcrop", 2.10, -22, TETON),
            ((-412.7, -86.5), "Log", 6.3, -14, TETON),
            ((-604.8, -531.7), "Outcrop", 3.45, 26, FOREST),
            ((-606.9, -525.9), "Log", 5.1, -45, FOREST),
            ((-573.3, -519.5), "Outcrop", 1.20, 20, FOREST),
        ]:
            v = self.verts[kind]
            length = np.ptp(v @ np.linalg.eigh(np.cov(v.T))[1][:, -1])
            scale = float(desired / length)
            self.plant(kind, xy, scale, ang, cam, "landmark", True)
            self.cluster(np.array(xy), ang, cam, "landmark-fringe", 2.1, 45)
        self.cluster(np.array(HERO_XY), 120, TETON, "pine-root", 3.2, 72)
        for xy, scale in [
            ((-433, -34), 0.43),
            ((-407, -28), 0.45),
            ((-392, -22), 0.37),
            ((-442, -11), 0.51),
        ]:
            self.plant("Pine", xy, scale, rng.uniform(0, 360), TETON, "meadow-edge")
            self.cluster(np.array(xy), 74, TETON, "pine-root", 2.1, 25)


def verify_world(path, folder=OUT, prefix="PWRVerge_"):
    """Check each cooked HISM transform, flags, culls and shader binding."""
    from verify_wind_grass import (
        native,
        package,
        number,
        matrices,
        identity_ancestors,
        NATIVE_PROPS,
    )

    spec = read(folder / "verges.json")
    world = native.decode(path, native.GAME)
    raw = path.read_bytes()
    by_id = {r["export"]: r for r in world["exports"]}
    rows = [
        r
        for r in world["exports"]
        if r["outer"] == spec["actor"]
        and r["class"] == "HierarchicalInstancedStaticMeshComponent"
    ]
    groups = {g["mesh"].split(".")[0]: (i, g) for i, g in enumerate(spec["groups"], 1)}
    seen = set()
    evidence = []
    for r in rows:
        mesh = package(r, "StaticMesh")
        i, g = groups[mesh]
        if mesh in seen:
            raise ValueError("Duplicated alpine HISM")
        seen.add(mesh)
        p = r["properties"]
        count = int(number(p["NumBuiltInstances"]))
        if count != g["count"] or r["name"] != prefix + g["key"]:
            raise ValueError("Cooked alpine group count changed")
        if [
            number(p.get(k))
            for k in ("InstanceStartCullDistance", "InstanceEndCullDistance")
        ] != g["cull"]:
            raise ValueError("Cooked alpine cull distance changed")
        if (p.get("bEvaluateWorldPositionOffset", "true") == "true") != bool(g["wpo"]):
            raise ValueError("Cooked vegetation movement flag changed")
        all_props = subprocess.check_output(
            [
                NATIVE_PROPS,
                native.GLOBAL / "world-paks",
                ROOT / "defs/ue" / native.GAME,
                path,
                str(r["export"]),
            ],
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        class_values = dict(
            s.strip().split(" = ", 1) for s in all_props.splitlines() if " = " in s
        )
        shadow = class_values.get("CastShadow", "true") == "true"
        if (
            shadow != bool(g["flags"] & 1)
            or number(class_values.get("WorldPositionOffsetDisableDistance"))
            != g["wpo"]
        ):
            raise ValueError(
                "Cooked alpine shadow or wind distance changed: " + g["key"]
            )
        want = g.get("material_package") or (
            "/Game/MJOLNIR/GrassPilot/Playable/" + g["material"]
            if g["material"]
            else None
        )
        if (
            package(r, "OverrideMaterials[0]") != want
            or p.get("BodyInstance.CollisionProfileName") != "NoCollision"
        ):
            raise ValueError("Alpine shader or native collision ownership changed")
        a = native.native_matrices(raw, r, count)
        b = matrices(folder / (spec["file"] + f".xf{i}"))

        def coord_order(x):
            return x[np.lexsort((x[:, 3, 2], x[:, 3, 1], x[:, 3, 0]))]

        delta = abs(coord_order(a) - coord_order(b))
        position = float(delta[:, 3, :3].max())
        basis = float(delta[:, :3, :3].max())
        if position > 0.03 or basis > 2.0e-5:
            raise ValueError(
                "Cooked alpine transforms disagree with road clearance proof"
            )
        identity_ancestors(r, by_id)
        evidence.append(
            dict(
                component=r["name"],
                mesh=mesh,
                count=count,
                max_position_error_cm=position,
                max_basis_error=basis,
            )
        )
    if seen != set(groups):
        raise ValueError("Missing alpine native instances in world")
    proof = dict(
        world_sha256=sha256(path),
        source_manifest_sha256=sha256(folder / "verges.json"),
        native_count=sum(g["count"] for g in evidence),
        groups=evidence,
    )
    (folder / "cooked-world.json").write_text(json.dumps(proof, indent=2) + "\n")


def witness_existing_collision(dest=None, source=None):
    """Compare indexed, playable Havok surfaces in both the release and this scene."""
    dest = dest or OUT / "physics"
    source = source or ROOT / "out/pwr/base-polish/rear-gate/physics"
    native = [read(p / "native-collision-receipt.json") for p in (source, dest)]
    proof = read(dest / "collision-proof.json")
    start = proof["preserved_source_surfaces"]
    groups = []
    for surface in [9, 71563, 414107, 825143, 1171710, start - 24]:
        samples = []
        for i, (directory, recipe) in enumerate(zip((source, dest), native)):
            match = [
                p
                for p in recipe["pieces"]
                if p["source_surface_range"]
                and p["source_surface_range"][0] <= surface
                and surface + 8 <= p["source_surface_range"][1]
            ]
            if len(match) != 1:
                raise ValueError("Ambiguous original surface ownership")
            piece = match[0]
            local = surface - piece["source_surface_range"][0]
            out = dest / f"prefix-{i}-{surface}.f32"
            subprocess.run(
                [
                    ROOT / "target/release/examples/readback_surfaces.exe",
                    directory / "pwr.sbsp",
                    str(piece["instance"]),
                    str(local),
                    str(local + 8),
                    out,
                ],
                check=True,
            )
            samples.append(np.fromfile(out, dtype="<f4").reshape(8, 3, 3))
        a, b = samples
        delta = (
            min(
                np.linalg.norm(a - np.roll(b, k, axis=1), axis=2).max()
                for k in range(3)
            )
            * 3.048
        )
        if delta > 0.0005:
            raise ValueError(
                f"Changed measurable original native collision near surface {surface}"
            )
        groups.append(dict(first_surface=surface, faces=8, max_error_m=float(delta)))
    proof["sampled_existing_havok_faces"] = groups
    (dest / "collision-proof.json").write_text(json.dumps(proof, indent=2) + "\n")


def cook_native_collision():
    from collections import defaultdict
    from copy import deepcopy
    from build_mature_pine_collision import bounded_band, clipped_points, audit_band
    from verify_conifer_attributes_v4 import read as read_glb
    from b30_collision import to_ce

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bases_v1"))
    from cook_polish_collision import (
        arrays,
        extend_arrays,
        verify_native_surfaces,
        FORMATS,
        MAX_SURFACES,
    )

    source = ROOT / "out/pwr/base-polish/rear-gate/physics"
    dest = OUT / "physics"
    dest.mkdir(exist_ok=True)
    released = read(ROOT / "out/pwr/ground-life/saturday.13/receipt.json")["collision"][
        "sbsp"
    ]
    base = read(source / "native-collision-receipt.json")
    baseline = read(source / "collision_scene.json")
    binary = baseline["bin"]
    if (
        sha256(source / "pwr.sbsp"),
        sha256(source / "collision_scene.json"),
        sha256(source / binary),
    ) != (released, base["source_manifest_sha256"], base["source_binary_sha256"]):
        raise ValueError("Base collision differs from the previously sealed .13 source")
    if released != base["output_sha256"]:
        raise ValueError("Wrong baseline collision receipt")

    spec = read(OUT / "verges.json")
    rows = read(OUT / "structural.json")
    shapes = {}
    hulls = ROOT / "out/pwr/visual-v5/outcrops-v4/hulls"
    for key, file in [
        ("Pine", "SM_PWR_MaturePine_A_bark_v1.json"),
        ("Outcrop", "SM_Rock_Glacial_Med_A.json"),
    ]:
        hull = read(hulls / file)
        shapes[key] = [(np.array(hull["points"]), np.array(hull["faces"]))]
    log = next(g for g in spec["groups"] if g["key"] == "Log")
    asset = ROOT / log["source_glb"]
    if sha256(asset) != log["sha256"]:
        raise ValueError(
            "Fallen log source changed after rendering transforms were generated"
        )
    doc, accessor = read_glb(asset)
    verts, faces = [], []
    n = 0
    for p in doc["meshes"][0]["primitives"]:
        v = accessor(p["attributes"]["POSITION"])[:, [0, 2, 1]].astype(float) * 100
        f = accessor(p["indices"]).reshape(-1, 3)
        faces.append(f.astype(int) + n)
        verts.append(v)
        n += len(v)
    verts, faces = np.vstack(verts), np.vstack(faces)
    # Clip actual intersecting triangles at the cuts. Five bounded convex pieces follow
    # the irregular swept trunk and taper without a collider spanning the whole bend.
    _, basis = np.linalg.eigh(np.cov(verts.T))
    if np.linalg.det(basis) < 0:
        basis[:, 0] *= -1
    local = verts @ basis
    partitions = np.linspace(local[:, 2].min(), local[:, 2].max(), 6)
    shapes["Log"] = []
    log_audit = []
    for lo, hi in zip(partitions, partitions[1:]):
        band = clipped_points(local, faces, lo, hi)
        for face_budget in (36, 32, 28, 24, 20, 16, 12):
            points, indices = bounded_band(band, face_budget)
            metric = audit_band(points, indices, band)
            if metric["minimum_triangle_area_cm2"] > 0.02:
                break
        else:
            raise ValueError("No stable enclosing log hull")
        if (
            metric["maximum_source_plane_deficit_cm"] > 0.003
            or metric["signed_volume_cm3"] <= 0
        ):
            raise ValueError(
                "A log collision segment does not enclose its measured source"
            )
        shapes["Log"].append((points @ basis.T, np.array(indices)))
        log_audit.append(metric)

    original = arrays(source / binary, baseline)
    manifest = deepcopy(baseline)
    materials = {m.get("game_material"): m["index"] for m in manifest["materials"]}
    radii = {
        g["key"]: np.linalg.norm(np.max(np.abs(g["visible_bounds_m"]), axis=0)[:2])
        for g in spec["groups"]
    }
    ordered = sorted(rows, key=lambda r: (r["kind"], r["id"]))
    added = defaultdict(bytearray)
    all_faces = []
    objects = []
    for row in ordered:
        material = materials[
            "hard_terrain_stone" if row["kind"] == "Outcrop" else "tough_organic_wood"
        ]
        rot = Rotation.from_quat(row["rotation_xyzw"])
        triangles = []
        for points, faces in shapes[row["kind"]]:
            world = rot.apply(points * row["scale_xyz"]) + row["position_cm"]
            triangles.extend(to_ce(world)[faces[:, [0, 2, 1]]])
        triangles = np.array(triangles)
        # Y reflection reverses winding; preserve the native outward face test.
        world_cm = triangles.reshape(-1, 3) * [304.8, 304.8, 304.8]
        horizontal = world_cm[:, :2] / 100
        if np.max(
            np.linalg.norm(horizontal - np.array(row["position_m"][:2]), axis=1)
        ) > (radii[row["kind"]] * max(row["scale_xyz"]) + 0.65):
            raise ValueError("Collider leaves the mesh's measured support radius")
        counts = {
            k: v + len(added[k]) // struct.calcsize(FORMATS[k])
            for k, v in baseline["counts"].items()
        }
        areas = np.linalg.norm(
            np.cross(
                triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]
            ),
            axis=1,
        )
        if areas.min() < 1.0e-9:
            raise ValueError(
                f"Degenerate {row['kind']}:{row['id']} face, min {areas.min()}, count {sum(areas < 1.0e-9)}"
            )
        append = extend_arrays(triangles, counts, material)
        for k, v in append.items():
            added[k].extend(v)
        objects.append(
            dict(
                id=row["id"],
                kind=row["kind"],
                object_index=len(objects),
                material=material,
                surfaces=len(triangles),
                position_m=row["position_m"],
                full_mesh_road_margin_m=row["full_mesh_road_margin_m"],
            )
        )
        all_faces.extend(triangles)
    triangles = np.array(all_faces)
    if len(triangles) + baseline["counts"]["surfaces"] > MAX_SURFACES:
        raise ValueError(
            "Structural collision would exceed the PWR native surface bound"
        )
    with (dest / binary).open("wb") as out:
        for k in manifest["array_order"]:
            manifest["counts"][k] += len(added[k]) // struct.calcsize(FORMATS[k])
            out.write(struct.pack("<I", manifest["counts"][k]))
            out.write(original[k])
            out.write(added[k])
    manifest["scenery_surfaces"]["objects"] += len(objects)
    manifest["scenery_surfaces"]["surfaces"] += len(triangles)
    for key, op in (("min", np.minimum), ("max", np.maximum)):
        manifest["world_bounds"][key] = op(
            manifest["world_bounds"][key], getattr(triangles, key)(axis=(0, 1))
        ).tolist()
    (dest / "collision_scene.json").write_text(json.dumps(manifest, indent=2) + "\n")
    after = arrays(dest / binary, manifest)
    for k in manifest["array_order"]:
        if after[k][: len(original[k])] != original[k]:
            raise ValueError(f"Original {k} changed")
    del after, original
    command = [
        CLI,
        "level",
        "collision",
        dest / "collision_scene.json",
        "--paks",
        PAKS,
        "--own-bsp",
        "--bsp-index",
        "0",
        "--receipt",
        dest / "native-collision-receipt.json",
        "--out",
        dest / "pwr.sbsp",
    ]
    with (dest / "native.log").open("w") as logfile:
        subprocess.run(
            [str(c) for c in command],
            check=True,
            stdout=logfile,
            stderr=subprocess.STDOUT,
        )
    result = read(dest / "native-collision-receipt.json")
    start = baseline["counts"]["surfaces"]
    if (
        result["source_surfaces"] != start + len(triangles)
        or result["delta_wu"] != [0, 0, 0]
        or result["tail_linked_in_host"]
        or result["output_sha256"] != sha256(dest / "pwr.sbsp")
        or result["source_binary_sha256"] != sha256(dest / binary)
        or result["source_manifest_sha256"] != sha256(dest / "collision_scene.json")
    ):
        raise ValueError("Native collision build does not match the checked source")
    error = verify_native_surfaces(result, start, triangles, dest)
    proof = dict(
        base_sbsp=released,
        sbsp=result["output_sha256"],
        source_arrays_prefix_exact=True,
        preserved_source_surfaces=start,
        added_surfaces=len(triangles),
        total_surfaces=result["source_surfaces"],
        source_structural_sha256=sha256(OUT / "structural.json"),
        source_placements_sha256=sha256(OUT / "placements.json"),
        root_and_definition_havok_verified_per_face=True,
        cooked_surface_maximum_error_m=error,
        objects=objects,
        log_segments=log_audit,
        cosmetic_groups=["FescueA", "FescueB", "Fern14", "Fern15", "Moss", "Branch"],
        native_scene_proof="exactly one cooked Havok surface per added triangle; prior source arrays byte-identical",
        live_physics_tested=False,
    )
    (dest / "collision-proof.json").write_text(json.dumps(proof, indent=2) + "\n")
    witness_existing_collision()
    print(
        f"Preserved {start} original surfaces; {len(triangles)} new landform surfaces; measured error {error} m"
    )


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    metadata, verts = sources()
    site = Site()
    scene = Dressing(site, metadata, verts)
    scene.design()
    ordered = sorted({r["kind"] for r in scene.points})
    binary = OUT / "verges.bin"
    binary.write_bytes(b"MJF3" + struct.pack("<II", 3, 0))
    groups = []
    for index, kind in enumerate(ordered, 1):
        records = [r for r in scene.points if r["kind"] == kind]
        append_foliage(
            binary, [[*p["position_cm"], 0, p["scale_xyz"][0], 0, 0] for p in records]
        )
        values = np.array(
            [
                [*p["position_cm"], *p["rotation_xyzw"], *p["scale_xyz"]]
                for p in records
            ],
            dtype="<f4",
        )
        sidecar = OUT / f"verges.bin.xf{index}"
        values.tofile(sidecar)
        flags = 32 if metadata[kind]["wpo"] else 34
        if kind in ("Pine", "Log", "Outcrop"):
            flags |= 1
        groups.append(
            dict(
                **metadata[kind],
                key=kind,
                count=len(records),
                exact=True,
                flags=flags,
                transform_sha256=sha256(sidecar),
            )
        )
    points = scene.points
    assert all(
        r["full_mesh_road_margin_m"] >= 0.119 and r["support_range_cm"][0] <= 1
        for r in points
    )
    assert all(
        any(r["camera"] == n and r["kind"].startswith("Fescue") for r in points)
        for n in (TETON, FOREST)
    )
    dump("placements.json", points)
    dump(
        "verges.json",
        dict(
            actor="PWR_AlpineVerges",
            file=binary.name,
            groups=groups,
            count=len(points),
            source_sha256={
                str(p.relative_to(ROOT)): sha256(p)
                for p in [FIELD, TREES, GEO, DISCS, NATIVE]
            },
            source_release="0.1.0-playtest.13",
            binary_sha256=sha256(binary),
        ),
    )
    # Structural entries are also the native collision integration inputs, in the same pose.
    dump(
        "structural.json",
        [r for r in points if r["kind"] in ("Pine", "Outcrop", "Log")],
    )
    dump(
        "verification.json",
        dict(
            status="offline placements and source mesh geometry",
            native_game_capture=False,
            instances=len(points),
            groups=len(groups),
            kinds=dict(Counter(p["kind"] for p in points)),
            minimum_full_mesh_road_margin_m=min(
                r["full_mesh_road_margin_m"] for r in points
            ),
            max_bottom_above_ground_cm=max(r["support_range_cm"][0] for r in points),
            placement_z_source="released native triangle heightfield in metres",
            cameras={k: v.pose for k, v in scene.cameras.items()},
            roots_near_existing_trees=sum(
                r["patch"] == "existing-root" and r["existing_trunk_distance_m"] < 8
                for r in points
            ),
            landmarks=[
                r for r in points if r["patch"] in ("foreground-pine", "landmark")
            ],
        ),
    )
    print(len(points), "native instance transforms", len(groups), "groups", flush=True)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--verify-world":
        verify_world(Path(sys.argv[2]))
    elif sys.argv[1:] == ["--witness"]:
        witness_existing_collision()
    elif sys.argv[1:] == ["--native-collision"]:
        cook_native_collision()
    else:
        main()

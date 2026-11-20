"""Fit stock remaster root fans and scanned ground-root mats to existing tree centres."""

import subprocess
import numpy as np
from scipy.spatial import ConvexHull, cKDTree
from scipy.spatial.transform import Rotation

from prepare_alpine_verges import mesh_info, CLI, PAKS, lod0_points, ROOT, sha256


def fit(field, data, folder, cam):
    from build_sweep_banks import bank_top

    stem = "SM_Ground_TreeRoot_Messy_A"
    paths = {"RootMat": "/Game/Env/Bio/Ground/TreeRoot/Ground_TreeRoot_Messy_A/" + stem}
    for suffix in "AB":
        base = "Tree_Metasequoia_Root_" + suffix
        paths["Root" + suffix] = (
            "/Game/Env/Bio/Tree/Metasequoia/" + base + "/SM_" + base
        )
    defs = {}
    local = {}
    hulls = {}
    placements = {k: [] for k in paths}
    for key, path in paths.items():
        f = folder / "stock" / (path.rsplit("/", 1)[-1] + ".glb")
        if not f.is_file():
            f.parent.mkdir(exist_ok=True)
            subprocess.run(
                [CLI, "mesh", "export", "--paks", PAKS, "--asset", f.stem, "--out", f],
                check=True,
            )
        v = np.unique(lod0_points(f) * 0.01, axis=0)
        local[key] = v
        info = mesh_info(str(CLI), str(PAKS), path)
        defs[key] = dict(
            key=key,
            mesh=path + "." + f.stem,
            origin=info["origin"],
            extent=info["extent"],
            standin_slots=info["slots"],
            source_glb=str(f.relative_to(ROOT)),
            sha256=sha256(f),
            material=None,
            wpo=0,
            flags=35,
            cull=[7500, 10500],
        )
        if key == "RootMat":
            axis = np.linspace(-2.96, 2.96, 6)
            x, y = np.meshgrid(axis, axis)
            xy = np.c_[x.ravel(), y.ravel()]
            tree = cKDTree(v[:, :2])
            _, near = tree.query(xy, k=30)
            top = np.percentile(v[near, 2], 75, axis=1)
            pts = np.c_[xy, top]
            faces = []
            for j in range(5):
                for i in range(5):
                    a = j * 6 + i
                    faces.extend([[a, a + 1, a + 7], [a, a + 7, a + 6]])
            hulls[key] = (pts, np.asarray(faces))
        else:
            # Close support around the scanned root in its native longitudinal direction.
            dirs = []
            for angle in np.arange(6) * np.pi / 3:
                for z in [-0.21, 0.20]:
                    dirs.append([np.cos(angle), np.sin(angle), z])
            dirs.extend([[0, 0, -1], [0, 0, 1]])
            pts = np.unique(v[np.argmax(v @ np.array(dirs).T, axis=0)], axis=0)
            hull = ConvexHull(pts)
            faces = hull.simplices.copy()
            for i, f0 in enumerate(faces):
                if (
                    np.dot(
                        np.cross(pts[f0[1]] - pts[f0[0]], pts[f0[2]] - pts[f0[0]]),
                        hull.equations[i, :3],
                    )
                    < 0
                ):
                    faces[i] = f0[[0, 2, 1]]
            hulls[key] = (pts, faces)
    targets = [
        (-571.33, -502.67),
        (-560.31, -495.76),
        (-559.36, -502.98),
        (-614.2, -509.4),
    ]
    objects = []
    contacts = []
    for j, t in enumerate(targets):
        _, it = field.trunks.query(t)
        tr = field.trunks.data[it]
        if np.linalg.norm(tr - t) > 0.4:
            raise ValueError("Tree registration drift")
        for k, key in enumerate(
            (["RootMat", "RootA", "RootB", "RootA"] if j < 2 else ["RootMat", "RootB"])
        ):
            if key == "RootMat":
                yaw = 27 + 81 * j
                sc = (
                    np.array([0.91, 0.85, 0.76])
                    if j < 2
                    else np.array([0.73, 0.77, 0.63])
                )
                rot = field.rotation(tr, yaw)
                offset = rot.apply(local[key] * sc)
                mid = tr + np.array([-0.28, 0.19])
                xy = mid + offset[:, :2] * [1, -1]
                rim = (abs(local[key][:, 0]) > 2.91) | (abs(local[key][:, 1]) > 2.91)
                ground = bank_top(xy, field, data)
                # Most of the rectangular skirt lies below the real soil; only woody scan ridges emerge.
                z = -np.percentile(offset[rim, 2] - ground[rim], 98) - 0.008
            else:
                ang = np.radians(([229, 307, 142][k - 1] if j < 2 else 239) + 17 * j)
                direct = np.array([np.cos(ang), np.sin(ang)])
                mid = tr + direct * 0.34
                # The taper goes upwards in stock model space. Rotate it to grow outward and downhill.
                reach = (2.55 if key == "RootA" else 2.2) * (1 if j < 2 else 0.84)
                dz = -0.42
                fw = np.r_[direct * [1, -1], dz / reach]
                fw /= np.linalg.norm(fw)
                across = np.array([-fw[1], fw[0], 0])
                across /= np.linalg.norm(across)
                rot = Rotation.from_matrix(
                    np.column_stack((across, np.cross(fw, across), fw))
                )
                sc = np.array([1.65, 1.31, reach / np.ptp(local[key][:, 2])])
                offset = rot.apply(local[key] * sc)
                xy = mid + offset[:, :2] * [1, -1]
                ground = bank_top(xy, field, data)
                # Root butt enters the existing trunk; its distal quarter settles into its soil.
                distal = local[key][:, 2] > np.percentile(local[key][:, 2], 79)
                z = -np.percentile(offset[distal, 2] - ground[distal], 40) - 0.026
            xf = np.r_[mid * [100, -100], z * 100, rot.as_quat(), sc]
            placements[key].append(xf)
            p, faces = hulls[key]
            w = (rot.apply(p * sc) + xf[:3] * 0.01) * [1, -1, 1]
            tri = w[faces[:, [0, 2, 1]]]
            name = f"{key} at tree {it}"
            if any(n == name for n, _ in objects):
                name = f"{key} {k} at tree {it}"
            objects.append((name, tri))
            clearance = z + offset[:, 2] - ground
            screen = cam.project(np.c_[xy, z + offset[:, 2]])
            contacts.append(
                dict(
                    tree=int(it),
                    key=key,
                    root_world_xy=tr.tolist(),
                    height_percentiles_m=np.percentile(
                        clearance, [0, 10, 50, 90, 100]
                    ).tolist(),
                    screen=[
                        screen[:, :2].min(0).tolist(),
                        screen[:, :2].max(0).tolist(),
                    ],
                    native_faces=len(tri),
                )
            )
    return [(defs[k], placements[k]) for k in paths], objects, contacts

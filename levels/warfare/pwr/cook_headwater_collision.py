"""Refit a local PWR terrain collision patch to a native UE heightfield within its original face budget."""

import hashlib
import json
import os
import struct
import sys
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree, distance
from scipy.optimize import linear_sum_assignment
from matplotlib.tri import Triangulation
import triangle

W = Path(__file__).resolve().parents[3]
OUT = Path(os.environ.get("PWR_HEADWATER_OUTPUT", W / "out/pwr/headwater-lake"))
BASE = W / "out/pwr/sweep-polish/round21/pine/physics"
PLAN = W / "out/pwr/base-runtime/native-refresh/terrain-probe-plan.json"
UNIT = 3.048


def filehash(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def raster(path):
    return np.load(path).astype(float)


def sample(a, xy):
    g = np.clip((xy + 1000.0) * 0.504, 0, 1008.0)
    ij = np.minimum(g.astype(int), 1007)
    x, y = ij.T
    u, v = (g - ij).T
    sw, se, nw, ne = a[y, x], a[y, x + 1], a[y + 1, x], a[y + 1, x + 1]
    return np.where(
        u + v <= 1,
        sw + (se - sw) * u + (nw - sw) * v,
        ne + (nw - ne) * (1 - u) + (se - ne) * (1 - v),
    )


def collision_arrays(raw, manifest):
    di = {}
    o = 0
    for k in manifest["array_order"]:
        (n,) = struct.unpack_from("<I", raw, o)
        o += 4
        sz = manifest["element_sizes"][k]
        if n != manifest["counts"][k]:
            raise ValueError(k)
        di[k] = (o, sz, n)
        o += sz * n
    if o != len(raw):
        raise ValueError("Source array length mismatch")
    return di


def bary(f, t, q, h):
    d = f[t[:, 1:]] - f[t[:, 0, None]]
    w = np.linalg.solve(d.swapaxes(1, 2), (q - f[t[:, 0]])[:, :, None])[:, :, 0]
    return h[t[:, 0]] + (w * (h[t[:, 1:]] - h[t[:, 0, None]])).sum(1)


def fit(v, faces, master):
    tri = v[faces]
    # Pick whole baseline terrain cells enclosing the delta plus an untouched buffer.
    basin = os.environ.get("PWR_RIVER_BASIN") == "1"
    west,east,south = (-490.,-218.,738.) if basin else (-465.,-223.,740.)
    sel = np.flatnonzero(
        (tri[:, :, 0].max(1) > west)
        & (tri[:, :, 0].min(1) < east)
        & (tri[:, :, 1].max(1) > south)
        & (tri[:, :, 1].min(1) < 1001)
    )
    if basin:
        domain=tri[sel,:,:2]
        forward = (domain - [-273.,785.]) @ [-.54419,.83896]
        previous_height = raster(W/"out/pwr/river-apron/terrain/runtime-master.heights.npy")
        anchors=np.concatenate([domain,.5*(domain+np.roll(domain,-1,axis=1)),domain.mean(1)[:,None,:]],axis=1)
        flat=anchors.reshape(-1,2)
        changed=np.abs(sample(master,flat)-sample(previous_height,flat)).reshape(len(sel),-1).max(1)>.005
        sel=sel[(np.min(forward,axis=1)>57.8)|changed]
    planar=tri[sel,:,:2].reshape(-1,2)
    if basin: planar=np.round(planar,5)
    uv, re = np.unique(planar, axis=0, return_inverse=True)
    tab = re.reshape(-1, 3)
    if basin:
        arms=uv[tab[:,1:]]-uv[tab[:,0,None]]
        rev=arms[:,0,0]*arms[:,1,1]-arms[:,0,1]*arms[:,1,0]<0
        tab[rev]=tab[rev][:,[0,2,1]]
    edges = np.sort(tab[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2), axis=1)
    edges, counts = np.unique(edges, axis=0, return_counts=True)
    boundary = edges[counts == 1]
    nodes, inv = np.unique(boundary, return_inverse=True)
    segments = inv.reshape(-1, 2)
    points = uv[nodes]
    if basin:
        source_z=np.zeros(len(uv));source_z[re.ravel()]=tri[sel,:,2].ravel()
        boundary_z=source_z[nodes]
    # Find newly surveyed terrain at sub-quad samples, including the engine's rendered diagonal.
    xmin, ymin = (np.floor((uv.min(0) + 1000) * 0.504) * 2).astype(int)
    xmax, ymax = (np.ceil((uv.max(0) + 1000) * 0.504) * 2).astype(int)
    xx, yy = np.meshgrid(np.arange(xmin, xmax + 1), np.arange(ymin, ymax + 1))
    q = np.column_stack([xx.ravel(), yy.ravel()]) / 0.504 / 2 - 1000
    orig = Triangulation(*uv.T, triangles=tab).get_trifinder()(q[:, 0], q[:, 1])
    q = q[orig >= 0]
    exact = sample(master, q)
    localwet = sample(raster(OUT / "terrain/runtime-master.water.npy"), q)
    localshore = sample(raster(OUT / "terrain/runtime-master.shore.npy"), q)
    tolerance = np.where((localwet > 0.05) | (localshore > 0.08), 0.24, 0.48)
    safe = np.ones(len(q), bool)
    for a, b in points[segments]:
        v2 = b - a
        along = np.clip(((q - a) @ v2) / (v2 @ v2), 0, 1)
        safe &= np.linalg.norm(q - (a + along[:, None] * v2), axis=1) > 0.0001
    for step in range(30):
        mesh = triangle.triangulate(dict(vertices=points, segments=segments), "pQ")
        coords, t = mesh["vertices"], mesh["triangles"]
        finder = Triangulation(*coords.T, triangles=t).get_trifinder()
        assn = finder(*q.T)
        if min(assn) < 0:
            raise ValueError(("Original patch coverage", int((assn < 0).sum())))
        h = sample(master, coords)
        if basin:
            if not np.array_equal(coords[:len(nodes)],uv[nodes]): raise ValueError("Native join order changed")
            h[:len(nodes)] = boundary_z
        err = np.abs(bary(coords, t[assn], q, h) - exact)
        # A wet shoreline and vehicle contact both need a tighter bound than standard walkable collision.
        ix = np.flatnonzero((err > tolerance) & safe)
        print(
            "Refinement",
            step,
            "triangles",
            len(t),
            "max residual",
            float(max(err)),
            "budget",
            len(sel),
            flush=True,
        )
        if len(t) > len(sel):
            raise ValueError("Lake clip exceeds original face budget")
        if len(ix) == 0:
            break
        ix = ix[np.lexsort((ix, -err[ix], assn[ix]))]
        best = ix[np.r_[True, np.diff(assn[ix]) != 0]]
        points = np.concatenate((coords, q[best]))
    else:
        raise ValueError("Could not meet collision tolerance")
    if (len(sel) - len(t)) % 2:
        raise ValueError("Invalid topology parity")
    # Use the remaining exact same face slots to improve resolution without changing any outside face index.
    while len(t) < len(sel):
        n = min(len(t), (len(sel) - len(t)) // 2)
        shape = coords[t]
        a = shape[:, 1] - shape[:, 0]
        b = shape[:, 2] - shape[:, 0]
        areas = np.abs(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0])
        picks = np.argsort(-areas, kind="stable")[:n]
        keep = np.ones(len(t), bool)
        keep[picks] = False
        centers = shape[picks].mean(1)
        newidx = np.arange(len(coords), len(coords) + n)
        coords = np.vstack([coords, centers])
        h = np.r_[
            h,
            bary(
                shape[picks].reshape(-1, 2),
                np.arange(3 * n).reshape(n, 3),
                centers,
                h[t[picks]].ravel(),
            ),
        ]
        extras = np.concatenate(
            [
                np.column_stack([t[picks, j], t[picks, (j + 1) % 3], newidx])
                for j in range(3)
            ]
        )
        t = np.vstack([t[keep], extras])
    finder = Triangulation(*coords.T, triangles=t).get_trifinder()
    actual = np.abs(bary(coords, t[finder(*q.T)], q, h) - exact)
    if np.any(actual[safe] > tolerance[safe] + 0.001):
        raise ValueError("Final fit validation failed")
    # Assign geographically close source slots, retaining compiled physics-instance locality.
    new = np.column_stack([coords, h])[t]
    oldcentres = tri[sel].mean(1)[:, :2]
    newcentres = new.mean(1)[:, :2]
    oldidx, newidx = linear_sum_assignment(
        distance.cdist(oldcentres, newcentres, metric="sqeuclidean")
    )
    original = Triangulation(*uv.T, triangles=tab).get_trifinder()(*newcentres.T)
    if original.min() < 0:
        raise ValueError("Revised terrain face outside original cover")
    audit={}
    if basin:
        worst=int(actual.argmax()); xy=q[worst]; tid=Triangulation(*uv.T,triangles=tab).get_trifinder()(*xy)
        oldtri=tri[sel][tid]; weight=np.linalg.solve((oldtri[1:,:2]-oldtri[0,:2]).T,xy-oldtri[0,:2]); old_z=float(oldtri[0,2]+weight@(oldtri[1:,2]-oldtri[0,2]))
        previous_field=raster(W/"out/pwr/river-apron/terrain/runtime-master.heights.npy")
        wet_pts=q[localwet>.14]
        audit=dict(worst_xy_m=xy.tolist(),worst_r16_m=float(exact[worst]),prior_r16_m=float(sample(previous_field,xy[None,:])[0]),prior_collision_m=old_z,
                   final_collision_m=float(bary(coords,t[finder(*xy)][None,:],xy[None,:],h)[0]),distance_to_nearest_wet_sample_m=float(np.linalg.norm(wet_pts-xy,axis=1).min()),
                   road_mask=float(sample(raster(OUT/"terrain/runtime-master.road.npy"),xy[None,:])[0]),water_mask=float(localwet[worst]),shore_mask=float(localshore[worst]),frozen=bool(not safe[worst]))
    return (
        sel[oldidx],
        new[newidx],
        sel[original[newidx]],
        {
            **({"boundary_audit":audit} if basin else {}),
            "faces": len(sel),
            "samples": len(q),
            "shore_max_m": float(actual[(localwet > 0.05) | (localshore > 0.08)].max()),
            "frozen_boundary_max_m": float(actual[~safe].max()),
            "max_error_m": float(actual.max()),
            "p95_m": float(np.percentile(actual, 95)),
        },
    )


def main():
    physical = OUT / "native/physics"
    physical.mkdir(parents=True, exist_ok=True)
    j = json.loads((BASE / "collision_scene.json").read_text())
    receipt = json.loads((BASE / "native-collision-receipt.json").read_text())
    if filehash(BASE / "collision_scene.bin") != receipt["source_binary_sha256"]:
        raise ValueError("Source collision checksum mismatch")
    raw = bytearray((BASE / "collision_scene.bin").read_bytes())
    a = collision_arrays(raw, j)
    view = lambda k, dtype, n: np.ndarray(
        (a[k][2], n), dtype=dtype, buffer=raw, offset=a[k][0], strides=(a[k][1], 4)
    )
    verts = view("vertices", "<f4", 3)
    planes = view("planes", "<f4", 4)
    edges = view("edges", "<i4", 6)
    surf = view("surfaces", "<i4", 2)
    vi = np.column_stack(
        (edges[surf[:, 1], 0], edges[surf[:, 1], 1], edges[edges[surf[:, 1], 2], 1])
    )
    p = json.loads(PLAN.read_text())["provenance"]
    first = p["terrain_source_first"]
    size = p["terrain_surfaces"]
    geom = np.load(p["ordered_path"])
    v = geom["vertices_m"]
    f = geom["triangles"]
    orig = verts[vi[first : first + size]].astype(float) * UNIT
    idx = np.argsort(
        orig[:, :, 0] + orig[:, :, 1] * 2397 + orig[:, :, 2] * 0.53, axis=1
    )
    expect = v[f]
    jdx = np.argsort(
        expect[:, :, 0] + expect[:, :, 1] * 2397 + expect[:, :, 2] * 0.53, axis=1
    )
    if not np.allclose(
        np.take_along_axis(orig, idx[:, :, None], axis=1),
        np.take_along_axis(expect, jdx[:, :, None], axis=1),
        rtol=0,
        atol=0.001,
    ):
        print(orig[:1], expect[:1])
        raise ValueError("Triangle provenance mismatch")
    master = raster(OUT / "terrain/runtime-master.heights.npy")
    basin = os.environ.get("PWR_RIVER_BASIN")=="1"
    materials = np.ndarray(
        (len(surf),),
        dtype="<i2",
        buffer=raw,
        offset=a["surfaces"][0] + 10,
        strides=(a["surfaces"][1],),
    )
    if basin:
        # Seed the fit from the prior compiled triangles, preserving every protected foreground face.
        parent_physics = W / "out/pwr/river-apron/native/physics"
        prev = np.load(parent_physics/"terrain-replacement.npz")
        inherited = prev["source_indices"]
        local = first+inherited
        prior = np.memmap(parent_physics/"collision_scene.bin",dtype="u1",mode="r")
        for array,indices in ((verts,vi[local]),(planes,surf[local,0]),(materials,local)):
            offset = array.ctypes.data - np.frombuffer(raw,"u1").ctypes.data
            old_array = np.ndarray(array.shape,dtype=array.dtype,buffer=prior,offset=offset,strides=array.strides)
            array[indices] = old_array[indices]
        # Offline receipt retains full-precision shared perimeter coordinates before Havok conversion.
        mesh = v[f].astype(float)
        mesh[inherited] = prev["triangles_m"]
        v = mesh.reshape(-1,3)
        f = np.arange(len(v)).reshape(-1,3)
    sel, new, oldslot, report = fit(v, f, master)
    if basin:
        report["retained_previous_terrain_faces"] = int(len(set(inherited)-set(sel)))
        report["protected_outlet_station_m"] = 57.8
    centre = new.mean(1)[:, :2]
    old_height = raster(
        W / "levels/warfare/pwr/terrain/runtime-v5/runtime-master.heights.npy"
    )
    wet = sample(raster(OUT / "terrain/runtime-master.water.npy"), centre)
    strand = sample(raster(OUT / "terrain/runtime-master.shore.npy"), centre)
    edited = np.abs(sample(master, centre) - sample(old_height, centre)) > 0.03
    native_material = materials[first + oldslot].copy()
    native_material[edited & (strand > 0.20)] = 5
    native_material[edited & (wet > 0.14)] = 2
    materials[first + sel] = native_material
    report["wet_bed_stone_faces"] = int(np.count_nonzero(edited & (wet > 0.14)))
    report["dry_strand_dirt_faces"] = int(
        np.count_nonzero(edited & (strand > 0.20) & (wet <= 0.14))
    )
    oldnorm = planes[surf[first + sel, 0], :3]
    new = new / UNIT
    sign = (
        np.cross(new[:, 1] - new[:, 0], new[:, 2] - new[:, 0])[:, 2] * oldnorm[:, 2] < 0
    )
    new[sign] = new[sign][:, [0, 2, 1]]

    def replace(indices, z):
        ids = vi[indices]
        if len(np.unique(ids)) != ids.size or len(np.unique(surf[indices, 0])) != len(
            indices
        ):
            raise ValueError("Unexpected shared surface data")
        verts[ids] = z
        z = verts[ids].astype(float)
        n = np.cross(z[:, 1] - z[:, 0], z[:, 2] - z[:, 0])
        n /= np.linalg.norm(n, axis=1)[:, None]
        planes[surf[indices, 0]] = np.column_stack((n, (n * z[:, 0]).sum(1)))

    replace(first + sel, new)
    np.savez_compressed(
        physical / "terrain-replacement.npz", source_indices=sel, triangles_m=new * UNIT
    )
    if "--fit-only" in sys.argv:
        print(report)
        return
    apply_rock_moves(raw, verts, vi, surf, replace, report, first)
    binary = physical / "collision_scene.bin"
    binary.write_bytes(raw)
    j["headwater_revision"] = {
        "baseline_binary_sha256": receipt["source_binary_sha256"],
        "terrain_samples": report,
        "r16_sha256": filehash(OUT / "terrain/runtime-master.r16"),
        "dressing_ledger_sha256": filehash(OUT / "dressing/decor-moves.json"),
    }
    (physical / "collision_scene.json").write_text(json.dumps(j, indent=2))
    (physical / "patch-report.json").write_text(json.dumps(report, indent=2))
    print(report, flush=True)


def apply_rock_moves(raw, verts, vi, surf, replace, report, first):
    sys.path.insert(0, str(W / "tools/level"))
    from b30_collision import rotator_matrix
    from scipy.spatial.transform import Rotation

    rockmoves = json.loads((OUT / "dressing/decor-moves.json").read_text())["decor"]
    tri = verts[vi[9:first]].astype(float) * UNIT
    reference = tri.mean(1)
    atlas = cKDTree(reference)

    def match(points, faces, label):
        pred = points[faces]
        dist, idx = atlas.query(pred.mean(1))
        print(
            label,
            "surfaces",
            len(faces),
            "centroid error",
            round(float(dist.max()), 3),
            flush=True,
        )
        if len(np.unique(idx)) != len(idx) or max(dist) > 0.04:
            raise ValueError(
                (
                    label,
                    "hull could not be aligned",
                    float(max(dist)),
                    pred[dist.argmax()].mean(0),
                    reference[idx[dist.argmax()]],
                )
            )
        actual = tri[idx]
        # Check all native triangle corners in either winding.
        discrepancy = np.linalg.norm(
            actual[:, :, :, None] - pred.swapaxes(1, 2)[:, None, :, :], axis=2
        ).min(2)
        if discrepancy.max() > 0.04:
            raise ValueError((label, "vertex discrepancy", discrepancy.max()))
        return idx + 9

    used = set()
    rocks = 0
    for r in rockmoves:
        delta = np.asarray(r["delta_ue_cm"]) * [0.01, -0.01, 0.01]
        if np.linalg.norm(delta) < 1e-7:
            continue
        mesh = r["mesh"].split(".")[-1]
        hull = json.loads(
            (W / "out/pwr/pcg-v3/rocks/hulls" / f"{mesh}.json").read_text()
        )
        pts = (
            np.asarray(hull["points"]) * r["scale"] @ rotator_matrix(*r["rot"])
            + r["old_pos_ue_cm"]
        )
        idx = match(pts * [0.01, -0.01, 0.01], np.array(hull["faces"]), r["id"])
        if used.intersection(idx):
            raise ValueError("Overlapping rock hulls")
        used.update(idx)
        replace(idx, (tri[idx - 9] + delta) / UNIT)
        rocks += 1
    # Removing the drowned mature pine also removes its measured bark-only Blam hull.
    # Spend those same local slots refining neighbouring ground faces; no duplicate or degenerate triangles.
    (pine,) = [
        r
        for r in json.loads(
            (W / "out/pwr/visual-v6/scenery/trees/trees.selected.json").read_text()
        )["instances"]
        if r["id"] == 1068981
    ]
    hull = json.loads(
        (
            W / "out/pwr/visual-v6/scenery/hulls/SM_PWR_MaturePine_A_bark_v1.json"
        ).read_text()
    )
    pts = (
        Rotation.from_quat(pine["rotation_xyzw"]).apply(
            np.asarray(hull["points"]) * pine["scale_xyz"]
        )
        + pine["position_cm"]
    )
    idx = match(
        pts * [0.01, -0.01, 0.01], np.array(hull["faces"]), "inundated mature pine"
    )
    report.update(rock_hulls=rocks, rock_faces=len(used), removed_pine_faces=len(idx))
    if len(idx) % 2:
        raise ValueError("Closed tree hull has an odd number of faces")
    support = OUT / 'bank/support.npz'
    basin = os.environ.get('PWR_RIVER_BASIN') == '1'
    if os.environ.get('PWR_RIVER_APRON') == '1' or basin:
        origin = W / 'out/pwr/river-apron' if basin else OUT
        support = origin / 'bank/support.npz'
        survey = json.loads((origin / 'bank/survey.json').read_text())
        if (survey['rock_ledger_sha256'] != filehash(origin / 'dressing/decor-moves.json') or
                survey['terrain_sha256'] != filehash(origin / 'terrain/runtime-master.r16')):
            raise ValueError('Bank support belongs to another terrain revision')
        if basin:
            locations = np.load(support)['triangles_m'].reshape(-1,3)[:,:2]
            prior = raster(origin/'terrain/runtime-master.heights.npy')
            current = raster(OUT/'terrain/runtime-master.heights.npy')
            if np.any(sample(prior,locations)!=sample(current,locations)):
                raise ValueError('The new basin intersects the registered native outlet support')
        with np.load(support) as survey:
            triangles = survey['triangles_m']
            mat = survey['materials']
        if len(triangles) != len(idx) or len(mat) != len(idx):
            raise ValueError('Shoreline support budget differs from the recovered tree slots')
        replace(idx, triangles / UNIT)
        ds = np.ndarray((len(surf),), dtype='<i2', buffer=raw,
                        offset=surf.ctypes.data - np.frombuffer(raw, 'u1').ctypes.data + 10, strides=(12,))
        ds[idx] = mat
        report.update(registered_bank_faces=len(idx), bank_support_sha256=filehash(support))
        return
    npz = np.load(OUT / "native/physics/terrain-replacement.npz")
    local = npz["source_indices"] + first
    ground = verts[vi[local]].astype(float)
    nearest = np.argsort(
        np.linalg.norm(
            ground.mean(1)[:, :2] * UNIT - np.array(pine["position"])[:2], axis=1
        )
    )[: len(idx) // 2]
    picked = ground[nearest]
    centre = picked.mean(1)
    for side, slots in enumerate((local[nearest], idx[::2], idx[1::2])):
        replace(
            slots,
            np.stack([picked[:, side], picked[:, (side + 1) % 3], centre], axis=1),
        )
    # Preserve source material on slots donated from the old tree to terrain.
    ds = np.ndarray(
        (len(surf),),
        dtype="<i2",
        buffer=raw,
        offset=surf.ctypes.data - np.frombuffer(raw, "u1").ctypes.data + 10,
        strides=(12,),
    )
    ds[idx[::2]] = ds[local[nearest]]
    ds[idx[1::2]] = ds[local[nearest]]


if __name__ == "__main__":
    main()

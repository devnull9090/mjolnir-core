"""Measure the sealed, material-bound GPU and fallback rear passage, and inspect native fallback tangent frames."""

import argparse
import json
from pathlib import Path
import struct
import sys

import numpy as np
from scipy.spatial import cKDTree

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from verify_runtime_visuals import read_mesh, sha


def clipped_count(positions, indices, lower, upper):
    tri = positions[indices][:, :, [0, 2, 1]].astype(np.float64)
    tri[:, :, 1] *= -1
    lo = np.asarray(lower)
    hi = np.asarray(upper)
    mask = np.all(tri.min(axis=1) <= hi, axis=1) & np.all(tri.max(axis=1) >= lo, axis=1)
    a = tri[mask] - (lo + hi) / 2
    if not len(a):
        return 0
    half = (hi - lo) / 2
    edge = np.roll(a, -1, axis=1) - a
    axes = [np.cross(edge[:, 0], edge[:, 1])]
    for i in range(3):
        for unit in np.eye(3):
            axes.append(np.cross(edge[:, i], unit))
    keep = np.ones(len(a), dtype=bool)
    for axis in axes:
        projected = np.sum(a * axis[:, None, :], axis=-1)
        support = np.sum(half * np.abs(axis), axis=1)
        keep &= (projected.min(axis=1) <= support) & (projected.max(axis=1) >= -support)
    return int(keep.sum())


def fallback_tangents(package, glb, source, limits, changed):
    with glb.open("rb") as f:
        f.seek(12)
        s, _ = struct.unpack("<II", f.read(8))
        doc = json.loads(f.read(s))
    attr = doc["meshes"][1]["primitives"][0]["attributes"]["POSITION"]
    count = doc["accessors"][attr]["count"]
    data = package.read_bytes()
    marker = struct.pack("<4I", 12, count, 12, count)
    assert data.count(marker) == 1
    start = data.index(marker) + 16
    positions = (
        np.frombuffer(data, dtype="<f4", count=count * 3, offset=start).reshape(-1, 3)[
            :, [0, 2, 1]
        ]
        * 0.01
    )
    p = start + 12 * count
    _, uv_channels, n, _, hq, elem, n2 = struct.unpack_from("<H6I", data, p)
    assert uv_channels == 1 and n == n2 == count and elem == 16 and hq == 1
    raw = np.frombuffer(data, dtype="<i2", offset=p + 26, count=count * 8).reshape(
        -1, 8
    )
    axis = raw[:, :3].astype(np.float64) / 32767
    normal = raw[:, 4:7].astype(np.float64) / 32767
    norm = np.linalg.norm(normal, axis=1)
    length = np.linalg.norm(axis, axis=1)
    orth = np.abs((axis * normal).sum(axis=1))
    source_sections = {s["slot"]: s for s in read_mesh(source)}
    changed_xyz = []
    for name in changed:
        for key, range_ in limits[name].items():
            sec = source_sections[key]
            i, t = range_["i"], range_["t"]
            changed_xyz.append(
                sec["position"][sec["triangles"][i : i + t]].reshape(-1, 3)
            )
    gate = np.unique(np.concatenate(changed_xyz), axis=0)
    gate_bounds = (gate.min(axis=0) - 1e-4, gate.max(axis=0) + 1e-4)
    roi = np.all((positions > gate_bounds[0]) & (positions < gate_bounds[1]), axis=1)
    selected = np.flatnonzero(roi)
    near = cKDTree(gate).query(positions[roi])[0] < 3e-5
    selected = selected[near]
    # Count rendered vertices that touch at least one non-degenerate fallback triangle.
    with glb.open("rb") as f:
        f.seek(20 + s)
        length_bin, _ = struct.unpack("<II", f.read(8))
        buf = f.read(length_bin)
    used = np.zeros(count, dtype=bool)
    for prim in doc["meshes"][1]["primitives"]:
        acc = doc["accessors"][prim["indices"]]
        view = doc["bufferViews"][acc["bufferView"]]
        dtype = {5125: "<u4", 5123: "<u2"}[acc["componentType"]]
        faces = np.frombuffer(
            buf,
            dtype=dtype,
            count=acc["count"],
            offset=view.get("byteOffset", 0) + acc.get("byteOffset", 0),
        ).reshape(-1, 3)
        coords = positions[faces].astype(np.float64)
        physical = (
            np.linalg.norm(
                np.cross(coords[:, 1] - coords[:, 0], coords[:, 2] - coords[:, 0]),
                axis=1,
            )
            > 1e-10
        )
        used[faces[physical].ravel()] = True

    def stats(sel):
        ix = np.asarray(sel, dtype=int)
        return {
            "vertices": len(ix),
            "zero_tangents": int(np.sum(length[ix] < 0.1)),
            "zero_normals": int(np.sum(norm[ix] < 0.1)),
            "nonunit_tangents": int(np.sum(abs(length[ix] - 1) > 0.002)),
            "nonunit_normals": int(np.sum(abs(norm[ix] - 1) > 0.002)),
            "maximum_abs_tangent_normal_dot": float(orth[ix].max(initial=0)),
            "invalid_handedness": int(
                np.sum(np.abs(raw[ix, 7].astype(np.int32)) < 32760)
            ),
        }

    return {
        "native_precision_bits": 16,
        "vertices": count,
        "edited_gate_rendered": stats(selected[used[selected]]),
        "old_and_new_assembly_rendered": stats(np.flatnonzero(used)),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--final", required=True, type=Path)
    parser.add_argument("--sealed", type=Path)
    args = parser.parse_args()
    b = args.build.resolve()
    sealed = (args.sealed or b / "955-final").resolve()
    manifest = json.loads((b / "art/manifest.json").read_text())
    old_manifest = json.loads(Path(manifest["sealed_parent_manifest"]).read_text())
    boundaries = json.loads((b / "art/original-object-boundaries.json").read_text())
    patch = json.loads((args.final / "patch.json").read_text())
    matrix = patch["clearance_box_m"]
    result = {}
    for spec in manifest["assets"]:
        name = spec["name"]
        team = spec["id"].split("_")[0]
        changed = [
            r["name"] for r in patch["objects"] if r["site"] == team and r["structural"]
        ]
        assert len(changed) == 21, changed
        orig = next(s for s in old_manifest["assets"] if s["name"] == name)
        new_glb = sealed / "readback" / (name + ".glb")
        old_glb = (
            Path(manifest["sealed_parent_manifest"]).parent.parent
            / "visual-readback"
            / (name + ".glb")
        )
        meshfile = f"{name}.uasset"
        records = {}
        for rev, glb, gltf, native in [
            ("before", old_glb, Path(orig["gltf"]), b / "original-members" / meshfile),
            (
                "after",
                new_glb,
                Path(spec["gltf"]),
                next((b / "replace-members").rglob(meshfile)),
            ),
        ]:
            info = {}
            for lod, label in enumerate(("nanite", "fallback")):
                blocks = read_mesh(glb, lod)
                hits = {
                    s["slot"]: clipped_count(
                        s["position"], s["triangles"], matrix["min"], matrix["max"]
                    )
                    for s in blocks
                }
                info[label + "_faces_crossing_driving_volume"] = sum(hits.values())
                info[label + "_by_slot"] = hits
            info["tangent_frames"] = fallback_tangents(
                native, glb, gltf, boundaries[spec["id"]], changed
            )
            records[rev] = info
        for label in ("nanite", "fallback"):
            assert records["before"][label + "_faces_crossing_driving_volume"] > 0
            assert records["after"][label + "_faces_crossing_driving_volume"] == 0
        result[team] = records
        print(team, records["after"]["tangent_frames"], flush=True)
    (sealed / "aperture-and-frame-check.json").write_text(
        json.dumps(
            {"passed_clearance": True, "bounds_m": matrix, "sites": result}, indent=2
        )
        + "\n"
    )


if __name__ == "__main__":
    main()

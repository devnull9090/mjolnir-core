"""Validate additive actor placements, archive ownership, and per-property/readback evidence before staging."""

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

import numpy as np
from scipy.spatial import cKDTree

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE))
from verify_runtime_visuals import sha, read_mesh
from stage_wide_gate import contents


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def validate_guides(b, target):
    info = read(b / "954/package.json")
    inputs = read(b / "art/portal-guides.json")["meshes"]
    result = {}
    for actor, team in zip(info["decor"], ("red", "blue", "green")):
        r = info["teams"][team]
        scale = r["scale"]
        center = np.array(r["center_cm"])[[0, 2, 1]] / 100.0
        source = Path(inputs[team]["gltf"])
        a = read_mesh(source)
        c = read_mesh(b / "954" / (source.stem + ".glb"))
        stats = []
        for dst in c:
            src = next(s for s in a if s["slot"] == dst["slot"])
            expected = np.concatenate(
                [src["position"], src["uv"], src["normal"]], axis=1
            )[src["triangles"]]
            measured = np.concatenate(
                [dst["position"] * scale + center, dst["uv"], dst["normal"]], axis=1
            )[dst["triangles"]]
            rotations = np.concatenate([np.roll(expected, i, axis=1) for i in range(3)])
            _, idx = cKDTree(rotations.reshape(-1, 24)).query(measured.reshape(-1, 24))
            diff = abs(rotations[idx] - measured)
            xyz = float(np.linalg.norm(diff[:, :, :3], axis=2).max())
            uv = float(diff[:, :, 3:5].max())
            normal = float(diff[:, :, 5:].max())
            if (
                len(np.unique(idx % len(expected))) != len(expected)
                or xyz > 0.002
                or uv > 0.001
                or normal > 0.009
            ):
                raise ValueError((team, src["slot"], xyz, uv, normal))
            stats.append(
                {
                    "slot": src["slot"],
                    "faces": len(measured),
                    "max_m": xyz,
                    "max_uv": uv,
                    "max_normal_component": normal,
                }
            )
        result[team] = stats
    save(target, {"passed": True, "sites": result})


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--build", type=Path, required=True)
    p.add_argument("--final", required=True, type=Path)
    args = p.parse_args()
    b = args.build.resolve()
    art = args.final.resolve() / "art"
    native = b / "955-frames"
    seed = ROOT / "out/pwr/base-polish/saturday.5/map-input"
    records = [
        read(b / "953-final/package.json"),
        read(b / "954/package.json"),
        read(native / "ownership.json"),
    ]
    targets = []
    changed = []
    for r in records:
        stem = Path(r["stem"])
        old = contents(seed / (stem.name + ".utoc"))
        new = contents(stem.with_suffix(".utoc"))
        assert old.keys() == new.keys()
        modified = sorted(k for k in old if old[k] != new[k])
        targets.append(
            {"stem": str(stem), "files": r["files"], "changed_files": modified}
        )
        changed.extend(r.get("decor", []))
    baseline = {a["id"]: a for a in read(seed / "pwr.level.json")["decor"]}
    changed = [a for a in changed if a != baseline[a["id"]]]
    aperture = read(native / "aperture-and-frame-check.json")
    for site, rows in aperture["sites"].items():
        assert (
            rows["after"]["nanite_faces_crossing_driving_volume"]
            == rows["after"]["fallback_faces_crossing_driving_volume"]
            == 0
        )
        f = rows["after"]["tangent_frames"]["edited_gate_rendered"]
        assert (
            f["zero_tangents"]
            == f["nonunit_tangents"]
            == f["zero_normals"]
            == f["nonunit_normals"]
            == f["invalid_handedness"]
            == 0
            and f["maximum_abs_tangent_normal_dot"] < 0.001
        ), (site, f)
    validate_guides(b, b / "954/guide-attributes.json")
    reports = {}
    for site in ("red", "blue", "green"):
        proc = subprocess.run(
            [
                str(ROOT / "target/release/examples/mesh_probe.exe"),
                str(native / "audit"),
                site + "_architecture",
                "--tangent-report",
            ],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        if proc.returncode:
            raise RuntimeError(proc.stderr[-1000:])
        m = re.search(
            r"explicit tangent frames in (\d+)/(\d+) full-detail clusters; (\d+) dropped triangles",
            proc.stdout,
        )
        assert m, proc.stdout[:300]
        explicit, total, dropped = map(int, m.groups())
        assert explicit == total and explicit and not dropped, (site, m.group(0))
        reports[site] = {
            "explicit_tangent_clusters": explicit,
            "all_full_detail_clusters": total,
            "dropped_triangles": dropped,
        }
    save(native / "nanite-tangent-pages.json", reports)
    receipt = read(native / "readback/receipt.json")
    assert receipt["passed"]
    evidence = [
        native / "ownership.json",
        native / "readback/receipt.json",
        native / "aperture-and-frame-check.json",
        native / "nanite-tangent-pages.json",
        b / "tangent-editor.json",
        b / "954/package.json",
        b / "954/guide-attributes.json",
        b / "953-final/package.json",
        b / "art/editor-import.receipt.json",
    ]
    assembly = read(art / "base-polish.json")
    scene = Path(assembly["scene"])
    assert sha(scene) == assembly["scene_sha256"]

    before_patch = read(ROOT / "out/pwr/base-polish/rear-gate/patch.json")
    final_patch = read(art.parent / "patch.json")
    assert before_patch["objects"] == final_patch["objects"]
    assert sha(art / "solid-cores.json") == sha(b / "polish-art/solid-cores.json")
    output = {
        "scene_sha256": assembly["scene_sha256"],
        "geometry_source_blend_sha256": read(b / "art/manifest.json")[
            "source_blend_sha256"
        ],
        "core_export_sha256": sha(art / "solid-cores.json"),
        "containers": targets,
        "decor": changed,
        "evidence": [str(p) for p in evidence],
        "verified_identical_gate_patch_records": len(final_patch["objects"]),
        "stable_unmodified_assets": True,
        "installed": False,
    }
    save(b / "visual-release.json", output)
    print(
        b / "visual-release.json", len(changed), "changed actor transforms", flush=True
    )


if __name__ == "__main__":
    main()

"""Pack the three base approaches as native meshes; verify each shipped section."""

import json
import re
import sys
import numpy as np
from base_approach_paths import ROOT, OUT, PLAN
from base_approach_surfaces import SLOTS
from base_approach_witnesses import PRIVATE, execute, link, sha

sys.path.insert(0, str(ROOT / "levels/warfare/pwr"))
from package_base_paving import write_gltf, read_glb
from scipy.spatial import cKDTree

STEM = "pakchunk952-MJOLNIRPWRAPPROACHES-PWR_P"
NATIVE = OUT / "native"
MAT = "/Game/MJOLNIR/World/PWR/Surfaces/M_CE_PWRPaving"
COLORS = [
    [0.266, 0.287, 0.266],
    [0.075, 0.096, 0.097],
    [0.038, 0.051, 0.049],
    [0.48, 0.265, 0.069],
]
ROUGH = [0.77, 0.56, 0.82, 0.60]
METAL = [0.12, 0.54, 0.38, 0.33]


def recipe(slot):
    return {
        "parent": MAT + ".M_CE_PWRPaving",
        "vectors": {
            "PavingTint": [*COLORS[slot], 1.0],
            "PavingParams": [340, ROUGH[slot], METAL[slot], 0.24],
            "PavingLayout": [1100, 1700, 2, 0.1 if slot == 0 else 0],
            "PavingPattern": [30, 0.012, 0.13, 0.08] if slot == 0 else [30, 0, 0, 0],
            "PavingGraphic": [1200, 0, 1, 0],
        },
    }


def package(
    source=OUT,
    stem=STEM,
    mesh_prefix="SM_PWR_GateApproach_",
    actor_prefix="pwr_approach_",
    slots=SLOTS,
    binding_keys=("floor", "dark", "shadow", "trim"),
    make_recipe=recipe,
    retired=(
        "pwr_paving_red_home",
        "pwr_paving_blue_home",
        "pwr_paving_citadel_plateau",
    ),
    schema="pwr-base-approaches-1",
):
    native_dir = source / "native"
    native_dir.mkdir(parents=True, exist_ok=True)
    priv = OUT / "witnesses/isolated-input"
    # Only the main stock content is needed for the engine Cylinder donor. The
    # .8 materials are mounted in the production map; native imports retain
    # one distinct binding per section so runtime material slots remain stable.
    for p in PRIVATE.glob("pakchunk0-Windows.u*"):
        link(p, priv / p.name)
    ex = ROOT / "target/release/examples"
    cli = ROOT / "target/release/mjolnir.exe"
    bindings = json.loads(
        (ROOT / "out/pwr/base-runtime/visuals/editor-import.receipt.json").read_text()
    )["materials"]
    native_binding = [bindings[k].split(".")[0] for k in binding_keys]
    bases = json.loads(PLAN.read_text())["bases"]
    actors = []
    members = []
    sources = {}
    for base in bases:
        team = base["id"]
        leaf = mesh_prefix + team.title()
        package = "/Game/MJOLNIR/Maps/PWR/Approaches/" + leaf
        material_mesh = np.load(source / (team + "-surfaces.npz"))
        parts = []
        for i, key in enumerate(slots):
            faces = material_mesh[key]
            v = faces.reshape(-1, 3)
            t = np.arange(len(v), dtype="<i4").reshape(-1, 3)
            name = team + "-" + key + ".npz"
            np.savez_compressed(native_dir / name, vertices_m=v, triangles=t)
            parts.append({"material_slot": i, "mesh_file": name})
        model, v, t, uv, center, scale = write_gltf(
            parts,
            native_dir,
            native_dir,
            leaf,
            {"position_m": base["terrace_center_m"]},
        )
        doc = json.loads(model.read_text())
        doc["materials"] = [{"name": k} for k in slots]
        model.write_text(json.dumps(doc) + "\n")
        native = native_dir / (leaf + ".uasset")
        args = [
            ex / "mesh_rewrite.exe",
            priv,
            "basicshapes/cylinder",
            model,
            native,
            "--rename",
            package,
            "--offset",
            "0,0,0",
            "--donor-sphere",
            "70.7",
            "--asset-imports",
            "--selftest",
        ]
        for i, key in enumerate(slots):
            args.extend(
                [
                    "--material",
                    key + "=" + native_binding[i] + "=" + ("*" if not i else key + "$"),
                ]
            )
        log = execute(args, native_dir / (team + "-native.log"))
        result = re.search(
            r"SPAWN: location \(([-\d.]+), ([-\d.]+), ([-\d.]+)\) cm, uniform scale ([\d.]+)",
            log,
        )
        if not result or "materials read back:" not in log:
            raise ValueError("No verified native placement or material binding")
        rounded = np.array([float(x) for x in result.groups()])
        if (
            np.abs(center - rounded[:3]).max() > 0.051
            or abs(scale - rounded[3]) > 0.000051
        ):
            raise ValueError("Mesh normalization did not match native writer")
        actors.append(
            {
                "id": actor_prefix + team,
                "mesh": package + "." + leaf,
                "pos": center.astype(float).tolist(),
                "rot": [0, 0, 0],
                "scale": [scale] * 3,
                "static": True,
                "cast_shadow": False,
                "materials": [make_recipe(i) for i in range(len(slots))],
            }
        )
        members.extend(["--package", package + "=" + str(native)])
        sources[team] = (leaf, center, scale, material_mesh)
    execute(
        [ex / "package_add.exe", priv, native_dir, "--name", stem, *members],
        native_dir / "package.log",
    )
    audit = native_dir / "audit"
    audit.mkdir(exist_ok=True)
    for ext in (".utoc", ".ucas"):
        link(priv / ("global" + ext), audit / ("global" + ext))
        link(native_dir / (stem + ext), audit / (stem + ext))
    checks = {}
    for team, (leaf, center, scale, groups) in sources.items():
        out = native_dir / (leaf + ".glb")
        execute(
            [cli, "mesh", "export", "--paks", audit, "--asset", leaf, "--out", out],
            native_dir / (team + "-read.log"),
        )
        pos, _, indices, doc = read_glb(out)
        world = (pos * scale + center) * np.array([0.01, -0.01, 0.01])
        if [m["name"] for m in doc["materials"]] != list(slots):
            raise ValueError("Material order differs in the native container")
        st = 0
        error = 0
        counts = {}
        for slot, prim in zip(slots, doc["meshes"][0]["primitives"]):
            n = doc["accessors"][prim["indices"]]["count"] // 3
            src = groups[slot]
            dst = world[indices[st : st + n]]
            st += n
            if len(dst) != len(src):
                raise ValueError((team, slot, len(dst), len(src)))
            rots = np.concatenate([np.roll(src, r, axis=1) for r in range(3)])
            distance, near = cKDTree(rots.reshape(-1, 9)).query(dst.reshape(-1, 9))
            error = max(error, float(np.linalg.norm(dst - rots[near], axis=2).max()))
            if error > 0.001:
                raise ValueError((team, slot, error))
            counts[slot] = n
        checks[team] = {
            "source_vertex_world_error_m": error,
            "material_triangles": counts,
            "native_glb_sha256": sha(out),
        }
    fragment = {
        "schema": "mjolnir-runtime-decor-v1",
        "render_only": True,
        "decor": actors,
    }
    (native_dir / "runtime_decor.json").write_text(
        json.dumps(fragment, indent=2) + "\n"
    )
    return {
        "schema": schema,
        "container_stem": str(native_dir / stem),
        "runtime_decor": str(native_dir / "runtime_decor.json"),
        "decor": actors,
        "remove_decor_ids": list(retired),
        "files": {
            s: {
                "path": str(native_dir / (stem + s)),
                "sha256": sha(native_dir / (stem + s)),
            }
            for s in (".utoc", ".ucas")
        },
        "readback_checks": checks,
    }


if __name__ == "__main__":
    from verify_base_approaches import validate

    result = package()
    result["validation"] = validate(result["decor"])
    (NATIVE / "package.receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["validation"], indent=2))

"""Package the Blender vehicle guides as render-only native static meshes."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

import numpy as np
from scipy.spatial import cKDTree

from verify_runtime_visuals import read_mesh, sha


ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools/level"))
from verify_pwr_surface_cook import imported_packages

STEM = "pakchunk954-MJOLNIRPORTALGUIDES-PWR_P"
PACKAGE = "/Game/MJOLNIR/Maps/PWR/PortalGuides"


def run(command, log):
    result = subprocess.run([str(arg) for arg in command], capture_output=True, text=True)
    output = result.stdout + result.stderr
    log.write_text(output, encoding="utf-8")
    if result.returncode or "MISMATCH" in output:
        raise RuntimeError(f"See {log}: {output[-1500:]}")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--art", required=True, type=Path)
    parser.add_argument("--paks", required=True, type=Path, help="Read-only game content directory")
    parser.add_argument("--out", required=True, type=Path, help="New build directory")
    parser.add_argument("--polish-level", type=Path, help="Build base polish using this staged level's anchors")
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    examples = ROOT / "target/release/examples"
    materials = json.loads((ROOT / "out/pwr/base-runtime/visuals/editor-import.receipt.json").read_text())["materials"]
    anchors = json.loads((args.polish_level or ROOT / "out/pwr/base-runtime/visuals/runtime_decor.json").read_text())["decor"]
    polish = args.polish_level is not None
    stem = "pakchunk953-MJOLNIRBASEPOLISH-PWR_P" if polish else STEM
    base_package = "/Game/MJOLNIR/Maps/PWR/BasePolish" if polish else PACKAGE
    art = json.loads((args.art / ("base-polish.json" if polish else "portal-guides.json")).read_text())
    add, decor, results = [], [], {}
    for team in ("red", "blue", "green"):
        rec = art["meshes"][team]
        model = Path(rec["gltf"])
        if sha(model) != rec["gltf_sha256"] or sha(model.with_suffix(".bin")) != rec["bin_sha256"]:
            raise ValueError(f"Changed Blender export for {team}")
        package = f"{base_package}/{model.stem}"
        native = out / (model.stem + ".uasset")
        slots = rec["material_keys"]
        if "shadow" in slots:
            slots = ["shadow"] + [k for k in slots if k != "shadow"]
        bindings = [materials[k].split(".")[0] for k in slots]
        command = [examples / "mesh_rewrite.exe", args.paks, "basicshapes/cylinder", model, native,
                   "--rename", package, "--offset", "0,0,0", "--asset-imports", "--selftest"]
        if polish:
            # The authored cylinder has 50 cm box half-extents and a 70.71 cm
            # sphere. A tall, broad citadel can fit the former and exceed the latter.
            command.extend(["--donor-sphere", "70.70"])
        for key, binding in zip(slots, bindings):
            pattern = "*" if key == slots[0] else key + "$"
            command.extend(["--material", f"{key}={binding}={pattern}"])
        log = run(command, out / f"{team}-build.log")
        if imported_packages(native) != ["/Engine/EngineMaterials/DefaultMaterial", *bindings]:
            raise ValueError("Incorrect native material references for " + team)
        match = re.search(r"SPAWN: location \(([-\d.]+), ([-\d.]+), ([-\d.]+)\) cm, uniform scale ([\d.]+)", log)
        if not match:
            raise ValueError("Missing mesh placement from native writer")
        *center, scale = map(float, match.groups())
        base, = [a for a in anchors if a["id"] == "pwr_newbase_" + team + "_architecture"]
        if base["rot"] != [0, 0, 0] or base["scale"] != [1, 1, 1]:
            raise ValueError(f"Unexpected native base transform for {team}")
        decor.append({"id": ("pwr_base_polish_" if polish else "pwr_portal_guides_") + team, "mesh": package + "." + model.stem,
                      "pos": [b + c for b, c in zip(base["pos"], center)], "rot": [0, 0, 0],
                      "scale": [scale] * 3, "static": True, "cast_shadow": polish})
        add.extend(["--package", f"{package}={native}"])
        results[team] = {"center_cm": center, "scale": scale, "triangles": rec["triangles"],
                         "material_packages": bindings}
    run([examples / "package_add.exe", args.paks, out, "--name", stem, *add], out / "package.log")
    # Read each shipped member from the sealed pair in isolation. Global data
    # supplies the class registry; no installed copy of a guide can mask it.
    audit = out / "audit"
    audit.mkdir()
    for name in ("global", stem):
        origin = args.paks if name == "global" else out
        for ext in (".utoc", ".ucas"):
            shutil.copy2(origin / (name + ext), audit / (name + ext))
    for team, row in results.items():
        model = Path(art["meshes"][team]["gltf"])
        target = out / (model.stem + ".glb")
        run([ROOT / "target/release/mjolnir.exe", "mesh", "export", "--paks", audit,
             "--asset", model.stem, "--out", target], out / f"{team}-readback.log")
        src, dst = read_mesh(model), read_mesh(target)
        if sum(len(s["triangles"]) for s in dst) != row["triangles"] or len(dst) != len(src):
            raise ValueError(f"Packaged section or triangle count changed for {team}")
        # Both project glTF tools use the same (UE X, UE Z, UE Y) metre axes.
        c = np.asarray(row["center_cm"])[[0, 2, 1]] / 100
        error = 0.
        uv_error = normal_error = 0.
        if polish:
            # SPAWN rounds its *actor* centre for level JSON. Near a narrow
            # bevel that half-millimetre error can move a valid triangle closer
            # to the next one. Identify corners using the writer's unrounded
            # float32 normalization, then audit actual world placement below.
            raw_cm = np.concatenate([s["position"] for s in src]) * np.float32(100)
            lo, hi = raw_cm.min(axis=0), raw_cm.max(axis=0)
            origin = (lo + hi) * .5
            fit = min(50/((hi-lo)*.5).max(), 70.70/np.linalg.norm(raw_cm-origin,axis=1).max())
        for section in dst:
            if polish and (np.max(np.abs(section["position"])) > .50001 or
                           np.linalg.norm(section["position"], axis=1).max() > .7071):
                raise ValueError("Native cull volume misses geometry for " + team)
            original, = [s for s in src if s["slot"] == section["slot"]]
            a = original["position"][original["triangles"]]
            b = section["position"][section["triangles"]] * row["scale"] + c
            if len(a) != len(b):
                raise ValueError(f"Native material assignment changed for {team}")
            # Match triangles independent of index order, allowing cyclic
            # permutations only. A reversed backface would disappear in play.
            rotations = np.concatenate([np.roll(a, k, axis=1) for k in range(3)])
            lookup, query = rotations, b
            if polish:
                lookup = (rotations*np.float32(100)-origin)*np.float32(fit*.01)
                query = section["position"][section["triangles"]]
            _, nearest = cKDTree(lookup.reshape(-1, 9)).query(query.reshape(-1, 9))
            if len(set(nearest % len(a))) != len(a):
                raise ValueError(f"Duplicate or missing native faces for {team}")
            error = max(error, float(np.linalg.norm(b - rotations[nearest], axis=2).max()))
            if polish:
                for attr in ("uv", "normal"):
                    corners = original[attr][original["triangles"]]
                    oriented = np.concatenate([np.roll(corners, k, axis=1) for k in range(3)])[nearest]
                    delta = float(np.abs(section[attr][section["triangles"]]-oriented).max())
                    if attr == "uv":
                        uv_error = max(uv_error,delta)
                    else:
                        normal_error = max(normal_error,delta)
        if error > .002:
            raise ValueError(f"Packaged vertex placement changed by {error:.4f} m for {team}")
        row.update(maximum_vertex_error_m=error, readback_sha256=sha(target))
        if polish:
            if uv_error > 1e-6 or normal_error > .009:
                raise ValueError(f"UVs or packed shading normals changed for {team}: {uv_error}, {normal_error}")
            row.update(maximum_uv_error=uv_error, maximum_normal_component_error=normal_error,
                       cylinder_culling_bounds_verified=True)
    receipt = {"stem": str(out / stem), "source": str(args.art.resolve()), "decor": decor,
               "teams": results, "files": {ext: sha(out / (stem + ext)) for ext in (".utoc", ".ucas")}}
    (out / "package.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()

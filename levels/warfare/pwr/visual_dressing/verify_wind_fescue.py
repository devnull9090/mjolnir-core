"""Audit the .12 native wind component identities, physical mesh and all PCG transforms."""

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile

import numpy as np
import verify_wind_grass as grass
from verify_wind_grass import (
    native,
    get_payload,
    package,
    number,
    matrices,
    load_container,
)

ROOT = grass.ROOT
F = grass.BASE / "grass.12"
OUT = F / "cooked-proof"


def check_meshes(toc):
    c = load_container(toc)
    info = json.loads((F / "meshes.json").read_text())
    with tempfile.TemporaryDirectory(dir=OUT) as tmp:
        tmp = Path(tmp)
        for pair in (toc, native.GLOBAL / "world-paks/global.utoc"):
            for path in (pair, pair.with_suffix(".ucas")):
                os.link(path, tmp / path.name)
        for row in info.values():
            name = row["mesh"].split(".")[-1]
            payload = get_payload(c, "/" + name + ".uasset")
            assert grass.FOLDER + "MI_PWR_Wind_Fescue" in grass.imports(payload)
            glb = OUT / (name + ".glb")
            subprocess.run(
                [
                    str(ROOT / "target/release/mjolnir.exe"),
                    "mesh",
                    "export",
                    "--paks",
                    str(tmp),
                    "--asset",
                    "/" + name,
                    "--out",
                    str(glb),
                ],
                check=True,
                capture_output=True,
            )
            data = glb.read_bytes()
            doc = json.loads(data[20 : 20 + struct.unpack_from("<I", data, 12)[0]])
            (prim,) = doc["meshes"][0]["primitives"]
            p = doc["accessors"][prim["attributes"]["POSITION"]]
            faces = doc["accessors"][prim["indices"]]["count"] // 3
            ext = np.asarray(p["max"]) - np.asarray(p["min"])
            assert (
                faces == row["triangles"]
                and 0.09 < ext[1] < 0.25
                and 0.55 < max(ext[0], ext[2]) < 1.45
            ), (faces, ext)
            row["cooked_extent_m"] = ext.tolist()
            row["cooked_triangle_count"] = faces
    return info


def audited_world(path, rows, sidecars, baseline):
    data = path.read_bytes()
    doc = native.decode(path, native.GAME)
    hist = {r["component"] + "@" + r["owner"]: r for r in rows}
    count = Counter()
    position_error = 0.0
    basis_error = 0.0
    native_scales = 0
    for r in doc["exports"]:
        tag = r["name"] + "@" + r["outer"]
        if not r["name"].startswith("PWRBlade_"):
            continue
        assert tag in hist
        e = hist.pop(tag)
        props = r["properties"]
        n = int(number(props["NumBuiltInstances"]))
        assert (
            n == e["count"]
            and e["mesh"].split(".")[0] == package(r, "StaticMesh")
            and e["material"].split(".")[0] == package(r, "OverrideMaterials[0]")
        )
        assert props.get("bEvaluateWorldPositionOffset", "true") == "true"
        assert [
            number(props.get(k))
            for k in ("InstanceStartCullDistance", "InstanceEndCullDistance")
        ] == e["cull"]
        assert props.get("BodyInstance.CollisionProfileName") == "NoCollision"
        count[r["outer"]] += n
        # Legacy Tundra stays at its original 12 .11 affine streams. Verify by
        # export ownership so an inadvertently reconstructed population fails.
        actual = native.native_matrices(data, r, n)
        if r["outer"] == "MJOLNIR_Foliage":
            assert (
                native.sha(actual.tobytes())
                == baseline[r["name"].removeprefix("PWRBlade_")]
            )
        else:
            orig = sidecars[e["mesh"]].copy()
            if "Canyon" in e["mesh"]:
                phase = orig[:, 3, :3] @ np.array([0.735, 0.971, 0.047])
                t = 0.5 + 0.5 * np.sin(phase)
                orig[:, 0, :3] *= (0.7 + 0.28 * t)[:, None]
                orig[:, 1, :3] *= (0.7 + 0.28 * t)[:, None]
                orig[:, 2, :3] *= (0.53 + 0.37 * t)[:, None]

            def order(m):
                return m[np.lexsort(tuple(m[:, 3, j] for j in (2, 1, 0)))]

            d = abs(order(actual) - order(orig))
            position_error = max(position_error, float(d[:, 3, :3].max()))
            basis_error = max(basis_error, float(d[:, :3, :3].max()))
        prop_log = subprocess.run(
            [
                str(grass.NATIVE_PROPS),
                str(native.GLOBAL / "world-paks"),
                str(ROOT / "defs/ue" / native.GAME),
                str(path),
                str(r["export"]),
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert "bEnableDensityScaling = true" in prop_log, (
            e["component"],
            "density scaling",
        )
        native_scales += 1
    assert not hist and position_error < 0.01 and basis_error < 0.00002
    return dict(
        world=doc["package"],
        count=dict(count),
        position_error_cm=position_error,
        basis_error=basis_error,
        density_scaled_components=native_scales,
        unchanged_tundra_components=len(baseline),
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--land", required=True, type=Path)
    p.add_argument("--world", required=True, type=Path)
    args = p.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    updated = json.loads((F / "editor-built.json").read_text())
    prev = json.loads((grass.ART / "editor-built.json").read_text())
    grass.OUT = OUT
    land = grass.land(args.land, prev)
    c = load_container(args.land)
    m = grass.properties(
        get_payload(c, "/M_PWR_WindBlade.uasset"), "M_PWR_WindBlade-grounded"
    )
    assert (
        m.get("ShadingModel", "1") == "1"
        and m.get("ShadingModels.ShadingModelField", "2") == "2"
    )
    assert grass.FOLDER + "T_PWR_Wind_Canyon" in grass.imports(
        get_payload(c, "/MI_PWR_Wind_Fescue.uasset")
    )
    mesh = check_meshes(args.land)
    source = grass.BASE / "native/LPE.umap"
    data = source.read_bytes()
    baseline = {
        r["name"]: native.sha(
            native.native_matrices(
                data, r, int(number(r["properties"]["NumBuiltInstances"]))
            ).tobytes()
        )
        for r in native.decode(source, native.GAME)["exports"]
        if r["class"] == "HierarchicalInstancedStaticMeshComponent"
        and "SM_Grass_GroundcoverClump_A" in str(package(r, "StaticMesh"))
    }
    affines = {}
    for base, stem in [(grass.ART, "wind"), (F, "fine")]:
        groups = json.loads((base / (stem + ".json")).read_text())["groups"]
        affines.update(
            {
                g["mesh"]: matrices(base / f"{stem}.bin.xf{i}")
                for i, g in enumerate(groups, 1)
            }
        )
    world = args.world
    if args.world.suffix.lower() == ".utoc":
        world = OUT / "PWR.umap"
        world.write_bytes(get_payload(load_container(args.world), "/PWR/PWR.umap"))
    receipt = dict(
        land=land,
        mesh=mesh,
        world=audited_world(world, updated["rows"], affines, baseline),
    )
    (OUT / "verification.json").write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt["world"], indent=2))


if __name__ == "__main__":
    main()

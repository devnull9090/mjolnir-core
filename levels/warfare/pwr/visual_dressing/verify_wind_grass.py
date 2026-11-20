"""Read the native PWR wind material, varieties, and all authored grass transforms."""

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import struct
import subprocess

import numpy as np

import verify_distance_colonies as native
from verify_distance_terrain import DEFAULT_OODLE, FREQ, load_name_batch, parse_library
from verify_render_only_hism_cook import package, number, matrices, identity_ancestors
from iostore import load_container, read_chunk

ROOT = native.ROOT
BASE = ROOT / "out/pwr/ground-life"
ART = BASE / "grass"
OUT = ART / "cooked-proof"
FOLDER = "/Game/MJOLNIR/GrassPilot/Playable/"
NAMES = ("B30", "Canyon", "Tundra")
NAME = "PWR_WindMeadow"
# This recorded build decodes cooked FPerQualityLevelFloat/Int serialization.
NATIVE_PROPS = ROOT / "out/pwr/toolchain-grass-v7/r2/props_dump.exe"


def get_payload(c, suffix):
    (key,) = [i for i in c.files if i.endswith(suffix)]
    return read_chunk(c, c.chunks[c.files[key]], oodle_roots=[DEFAULT_OODLE])


def imports(payload):
    return load_name_batch(payload, struct.unpack_from("<I", payload, 48)[0])[0]


def referenced_package(payload, property_text):
    """Resolve this exact object index rather than just testing the whole import table."""
    index = int(re.fullmatch(r"import (\d+)", property_text)[1])
    start, end = struct.unpack_from("<II", payload, 28)
    assert 0 <= index < (end - start) // 8
    object_id = struct.unpack_from("<Q", payload, start + 8 * index)[0]
    assert object_id >> 62 == 2
    return imports(payload)[(object_id >> 32) & 0x3FFFFFFF]


def scaled_default(text, as_float, quality):
    data = bytes.fromhex(text)
    assert len(data) == (12 if quality else 8)
    assert struct.unpack_from("<I", data)[0] == 1
    if quality:
        assert struct.unpack_from("<I", data, 8)[0] == 0
    return struct.unpack_from("<f" if as_float else "<i", data, 4)[0]


def properties(payload, stem):
    tmp = OUT / (stem + ".uasset")
    tmp.write_bytes(payload)
    raw = subprocess.run(
        [
            str(NATIVE_PROPS),
            str(native.GLOBAL / "world-paks"),
            str(ROOT / "defs/ue" / native.GAME),
            str(tmp),
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    (OUT / (stem + ".properties.txt")).write_text(raw)
    return {
        match[1]: match[2]
        for line in raw.splitlines()
        if (match := re.fullmatch(r"\s+(.+?) = (.+)", line))
    }


def land(toc, editor):
    c = load_container(toc)
    sm6 = parse_library(get_payload(c, "Chunk965-PCD3D_SM6-PCD3D_SM6.ushaderbytecode"))
    groups = {
        s.chunk_id.to_bytes(8, "little") + s.chunk_index.to_bytes(2, "big")
        for s in c.chunks
        if s.type_name == "ShaderCode" and s.length
    }
    assert sm6.group_ids and all(key[:10] in groups for key in sm6.group_ids)

    def blob(name):
        return get_payload(c, "GrassPilot/Playable/" + name + ".uasset")

    master = blob("M_PWR_WindBlade")
    pr = properties(master, "M_PWR_WindBlade")
    assert (
        pr["TwoSided"] == "true"
        and pr["bUsedWithInstancedStaticMeshes"] == "true"
        and pr["bUsedWithNanite"] == "true"
    )
    assert number(pr["MaxWorldPositionOffsetDisplacement"]) == 19.0
    stages = {}
    for i, h in enumerate(sm6.map_hashes):
        if h not in master:
            continue
        indices = sm6.map_shaders(i)
        assert indices and all(sm6.shader_size(x) > 0 for x in indices)
        stages[h.hex()] = dict(
            Counter(FREQ.get(sm6.shader_entries[j][0], "?") for j in indices)
        )
    assert stages and any(row.get("VS") and row.get("PS") for row in stages.values()), (
        stages
    )
    materials = {}
    settings = dict(
        B30=(31.0, 6.2, 3100.0, 4700.0),
        Canyon=(91.0, 12.0, 3200.0, 4750.0),
        Tundra=(17.0, 3.8, 1750.0, 2750.0),
    )
    for name in NAMES:
        mesh_mi = blob("MI_PWR_Wind_" + name)
        refs = imports(mesh_mi)
        assert (
            FOLDER + "M_PWR_WindBlade" in refs and FOLDER + "T_PWR_Wind_" + name in refs
        )
        tex = blob("T_PWR_Wind_" + name)
        assert len(tex) > 100
        p = properties(mesh_mi, "MI_PWR_Wind_" + name)
        params = {
            p[k]: number(p[k.replace(".ParameterInfo.Name", ".ParameterValue")])
            for k in p
            if k.startswith("ScalarParameterValues[")
            and k.endswith(".ParameterInfo.Name")
        }
        for k, v in zip(
            ("BladeHeight", "TipSway", "WindNear", "WindFar"), settings[name]
        ):
            assert np.isclose(params[k], v)
        materials[name] = dict(
            parameters=params,
            master=FOLDER + "M_PWR_WindBlade",
            texture=FOLDER + "T_PWR_Wind_" + name,
        )
    gt = blob("GT_PWRPilot")
    gp = properties(gt, "GT_PWRPilot")
    assert gp["GrassVarieties"] == "[5 item(s)]"
    values = []
    for i, (name, density, start, end) in enumerate(
        zip(
            editor["landscape_varieties"],
            [43, 22, 32, 22, 15],
            [4200, 3600, 4400, 4300, 4200],
            [6700, 5800, 7400, 7300, 7000],
        )
    ):
        pref = f"GrassVarieties[{i}]."
        actual = referenced_package(gt, gp[pref + "GrassMesh"])
        assert actual == name.split(".")[0], (actual, name)
        assert (gp.get(pref + "OverrideMaterials[0]") is None) == (i == 1)
        if i != 1:
            assert referenced_package(
                gt, gp[pref + "OverrideMaterials[0]"]
            ) == FOLDER + "MI_PWR_Wind_" + ("Canyon" if i == 0 else "B30")
        for p, val, numeric_float in (
            ("GrassDensity", density, True),
            ("StartCullDistance", start, False),
            ("EndCullDistance", end, False),
        ):
            for quality in (False, True):
                x = scaled_default(
                    gp[pref + p + ("Quality" if quality else "")],
                    numeric_float,
                    quality,
                )
                assert x == val, (p, val, x)
        assert number(gp[pref + "InstanceWorldPositionOffsetDisableDistance"]) == (
            3500 if i == 1 else 4800
        )
        values.append(
            dict(mesh=actual, density=density, cull_m=[start / 100, end / 100])
        )
    assert not any("/Megascans/" in p or "/Env/Bio/" in p for p in c.files)
    return dict(
        path=str(toc),
        shader_stages=stages,
        material_instances=materials,
        landscape=values,
    )


def world(path, schema, editor):
    doc = native.decode(path, schema)
    data = path.read_bytes()
    by_id = {r["export"]: r for r in doc["exports"]}
    rows = [
        r
        for r in doc["exports"]
        if r["class"] == "HierarchicalInstancedStaticMeshComponent"
    ]
    spec = json.loads((ART / "wind.json").read_text())
    selected = [r for r in rows if r["outer"] == NAME]
    expected = {k.split(".")[0]: v for k, v in editor["kind_counts"].items()}
    assert len(selected) == 4
    inspected = {}
    for r in selected:
        mesh = package(r, "StaticMesh")
        slot = "Canyon" if "Canyon" in mesh else "B30"
        assert package(r, "OverrideMaterials[0]") == FOLDER + "MI_PWR_Wind_" + slot
        p = r["properties"]
        assert (
            p.get("bEvaluateWorldPositionOffset", "true") == "true"
            and p["BodyInstance.CollisionProfileName"] == "NoCollision"
        )
        assert [
            number(p[k])
            for k in ("InstanceStartCullDistance", "InstanceEndCullDistance")
        ] == [4800, 8800]
        n = int(number(p["NumBuiltInstances"]))
        assert expected[mesh] == n
        identity_ancestors(r, by_id)
        xyz = native.native_matrices(data, r, n)
        idx = next(
            j
            for j, g in enumerate(spec["groups"], 1)
            if g["mesh"].split(".")[0] == mesh
        )
        side = matrices(ART / f"wind.bin.xf{idx}")

        def order(a):
            return a[np.lexsort(tuple(a[:, 3, j] for j in (2, 1, 0)))]

        d = abs(order(xyz) - order(side))
        assert d[:, 3, :3].max() < 0.01 and d[:, :3, :3].max() < 1.0e-5
        inspected[mesh] = dict(
            count=n,
            position_error_cm=float(d[:, 3, :3].max()),
            basis_error=float(d[:, :3, :3].max()),
        )
    original = [
        r
        for r in rows
        if "SM_Grass_GroundcoverClump_A" in str(package(r, "StaticMesh"))
    ]
    for r in original:
        assert package(r, "OverrideMaterials[0]") == FOLDER + "MI_PWR_Wind_Tundra"
        assert r["properties"].get("bEvaluateWorldPositionOffset", "true") == "true"
    assert (
        sum(int(number(r["properties"]["NumBuiltInstances"])) for r in original)
        == editor["tundra_updated"]
    )
    return dict(
        package=doc["package"],
        sha256=native.sha(data),
        direct_components=inspected,
        tundra_count=editor["tundra_updated"],
        tundra_components=len(original),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--world-toc", type=Path)
    parser.add_argument(
        "--land-toc",
        type=Path,
        default=BASE / "native/land/pakchunk965-MJOLNIRLAND-Windows.utoc",
    )
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    editor = json.loads((ART / "editor-built.json").read_text())
    results = {"land": land(args.land_toc, editor)}
    for src, schema in (("LPE.stock.umap", native.STOCK), ("LPE.umap", native.GAME)):
        results[src] = world(BASE / "native" / src, schema, editor)
    if args.world_toc:
        payload = get_payload(load_container(args.world_toc), "/PWR/PWR.umap")
        target = OUT / "PWR.umap"
        target.write_bytes(payload)
        results["release"] = world(target, native.GAME, editor)
        assert results["release"]["package"] == "/Game/Levels/Halo1/Solo/PWR/PWR"
    (OUT / "verification.json").write_text(json.dumps(results, indent=2))
    print(
        "Verified",
        editor["count"],
        "grass transforms and seven native wind material assets",
        list(results),
    )


if __name__ == "__main__":
    main()

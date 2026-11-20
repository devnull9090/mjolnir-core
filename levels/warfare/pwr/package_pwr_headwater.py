"""Package the isolated headwater cook, preserving sealed Pelican scenario, lighting and all unrelated assets."""

import json
import os
from pathlib import Path
import shutil
import sys
import numpy as np
from package_landscape_revision import run
from stage_world_playtest import (
    ROOT,
    WORLD,
    LAND,
    sha,
    world_entries,
    load_container,
    read_chunk,
)

out = Path(os.environ.get("PWR_HEADWATER_OUTPUT", ROOT / "out/pwr/headwater-lake"))
n = out / "native"
old = ROOT / "out/pwr/sweep-polish/round31/saturday.31/map-input"
examples = ROOT / "target/release/examples"
cli = ROOT / "out/pwr/toolchain-grass-v7/r2/mjolnir.exe"
paks = ROOT / "out/pwr/playtest-20261121/rehearsal-game/Meteorite/Content/Paks"
maps = n / "map-input"
apron = os.environ.get('PWR_RIVER_APRON') == '1'
basin = os.environ.get('PWR_RIVER_BASIN')=='1'
if basin:
    old = ROOT/'out/pwr/river-apron/finish37/map-input'
if apron:
    old = ROOT / 'out/pwr/river-erosion/saturday.35/map-input'
    apron_assets = {f'MJOLNIR/GrassPilot/Playable/{leaf}.{ext}'
                    for leaf in ('M_PWR_OutletAlluvium', 'SM_PWR_OutletAlluvium') for ext in ('uasset','ubulk')}



def log(p):
    raw = p.read_bytes()
    return raw.decode(
        "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig",
        errors="replace",
    )


def changes(a, b, allowed_additions=()):
    prior, after = world_entries(a), world_entries(b)
    additions=after.keys()-prior.keys()
    if prior.keys()-after.keys() or not additions<=set(allowed_additions):
        raise ValueError("Package inventory changed")
    return {k:[prior.get(k),digest] for k,digest in after.items() if prior.get(k)!=digest}


def prepare(allowed_additions=(), require_material_change=True):
    s = log(out / "cook.log")
    if "BUILD SUCCESSFUL" not in s or any(
        x.lower() in s.lower()
        for x in (
            "failed to compile material",
            "default material will be used in game",
            "shadermap pointer is null",
            "shader is using too many samplers",
        )
    ):
        raise ValueError("Cook or material failure")
    (staged,) = list(
        (out / "editor/Meteorite/Saved/StagedBuilds").rglob("pakchunk965-Windows.utoc")
    )
    source = n / "stock"
    source.mkdir(parents=True, exist_ok=True)
    for stem in ("global", "pakchunk965-Windows"):
        for ext in (".ucas", ".utoc"):
            shutil.copyfile(staged.parent / (stem + ext), source / (stem + ext))
    land = n / "land"
    land.mkdir(exist_ok=True)
    run(
        [
            cli,
            "ue",
            "retarget",
            "--paks",
            source,
            "--container",
            "pakchunk965-Windows",
            "--classes",
            "Material,MaterialInstanceConstant,LandscapeGrassType",
            "--rewrite",
            "--name",
            "pakchunk965-MJOLNIRLAND-Windows",
            "--out-dir",
            land,
        ],
        n / "land.log",
    )
    for suffix, dest in (("umap", "LPE.stock.umap"), ("ubulk", "LPE.ubulk")):
        run(
            [
                examples / "extract_file.exe",
                source,
                "Levels/Halo1/Solo/LPE/LPE." + suffix,
                n / dest,
            ],
            n / ("extract-" + suffix + ".log"),
        )
    run(
        [
            examples / "retarget_package.exe",
            source,
            ROOT / "defs/ue/UE-5.5-stock.usmap",
            ROOT / "defs/ue/Meteorite-2607-CU3.usmap",
            n / "LPE.stock.umap",
            n / "LPE.umap",
        ],
        n / "world-layout.log",
    )
    (landtoc,) = land.glob("*.utoc")
    if apron:
        allowed_additions = apron_assets
    change = changes(old / (LAND + ".utoc"), landtoc,allowed_additions)
    if apron and not {k for k in apron_assets if k.endswith('.uasset')} <= set(change):
        raise ValueError('Native outlet art not cooked in LAND')
    if (require_material_change and not any(k.endswith("M_PWRPilot.uasset") for k in change)) or not all(
        k in allowed_additions or k.endswith(("M_PWRPilot.uasset", "LPE.umap", "LPE.ubulk", ".ushaderbytecode"))
        for k in change
    ):
        raise ValueError(list(change))
    maps.mkdir(exist_ok=True)
    for ext in (".utoc", ".ucas"):
        shutil.copyfile(landtoc.with_suffix(ext), maps / (LAND + ext))
    (n / "land-diff.json").write_text(json.dumps(change, indent=2))


def finish():
    bsp = n / "physics/pwr.sbsp"
    receipt = json.loads((n / "physics/native-collision-receipt.json").read_text())
    bsp_hash = sha(bsp)
    readback = json.loads((n / "physics/native-readback.json").read_text())
    if (receipt["output_sha256"] != bsp_hash or receipt["source_surfaces"] != 1199995
            or readback["compiled_bsp_sha256"] != bsp_hash or not readback["root_and_definition_havok_queries"]):
        raise ValueError("Native BSP mismatch")
    world = n / "world-bake"
    level = json.loads(
        (ROOT / "out/pwr/sweep-polish/round31/native-level.json").read_text()
    )
    level["decor"] = json.loads((out / "dressing/level-decor.json").read_text())
    (n / "native-level.json").write_text(json.dumps(level, indent=2))
    run(
        [
            cli,
            "level",
            "bake",
            n / "native-level.json",
            "--paks",
            paks,
            "--standalone",
            "PWR",
            "--bsp",
            "8=" + str(bsp.resolve()),
            "--out-dir",
            world,
            "--world",
            n / "LPE.umap",
        ],
        n / "world-bake.log",
    )
    name = WORLD + ".utoc"
    fresh = world / name
    delta = changes(old / name, fresh)
    allowed = (
        "/PWR/PWR.umap",
        "/PWR/PWR.ubulk",
        "-scenario_structure_bsp.uasset",
        "-scenario_structure_bsp.ubulk",
    )
    restore = [k for k in delta if not k.endswith(allowed)]
    if any(
        not k.endswith(("/PWR-scenario.uasset", "/PWR-scenario.ubulk")) for k in restore
    ):
        raise ValueError(restore)
    if restore:
        base = load_container(old / name)
        for k in restore:
            f = n / "restore-scenario" / k
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(read_chunk(base, base.chunks[base.files[k]]))
        final = n / "world-final"
        run(
            [examples / "replace_members.exe", fresh, n / "restore-scenario", final],
            n / "restore.log",
        )
        fresh = final / name
    delta = changes(old / name, fresh)
    if (
        not all(k.endswith(allowed) for k in delta)
        or not any(k.endswith("-scenario_structure_bsp.ubulk") for k in delta)
        or not any(k.endswith("PWR.umap") for k in delta)
    ):
        raise ValueError(list(delta))
    for ext in (".utoc", ".ucas"):
        shutil.copyfile(fresh.with_suffix(ext), maps / (WORLD + ext))
    packaged = load_container(maps / name)
    (member,) = [k for k in delta if k.endswith("scenario_structure_bsp.ubulk")]
    body = read_chunk(packaged, packaged.chunks[packaged.files[member]])

    def shell_adjust(original, stored):
        raw = np.fromfile(original, "u1")
        got = np.frombuffer(stored, "u1")
        if raw.size != got.size:
            raise ValueError("Packaged BSP length differs")
        ix = np.flatnonzero(raw != got)
        if not 0 < len(ix) <= 16:
            raise ValueError("Unexpected duplicate-shell adjustment")
        return [(int(i - ix[0]), int(raw[i]), int(got[i])) for i in ix]

    control = load_container(old / name)
    unchanged_adjust = shell_adjust(
        (ROOT / 'out/pwr/river-apron/native/physics/pwr.sbsp' if basin else
         ROOT / 'out/pwr/river-erosion/native/physics/pwr.sbsp' if apron else
         ROOT / "out/pwr/sweep-polish/round31/pine/physics/pwr.sbsp"),
        read_chunk(control, control.chunks[control.files[member]]),
    )
    if shell_adjust(bsp, body) != unchanged_adjust:
        raise ValueError("Unexpected native shell adjustment")
    verification = dict(
        rebuild="levels/warfare/pwr/build_headwater_native.ps1",
        native_physics_receipt="native/physics/native-collision-receipt.json",
        physical_queries="native/physics/native-readback.json",
        native_members={p.name: sha(p) for p in maps.iterdir()},
        world_changed=delta,
        land_changed=json.loads((n / "land-diff.json").read_text()),
        scenario_restored=restore,
        sbsp=bsp_hash,
        geometry=json.loads((n / "physics/patch-report.json").read_text()),
        editor=json.loads((out / "editor-verified.json").read_text()),
        material=json.loads((out / "shore-material.json").read_text()),
    )
    authored = json.loads((n/"physics/collision_scene.json").read_text())["headwater_revision"]
    ledger_sha = sha(out/"dressing/decor-moves.json")
    field_sha = sha(out/"terrain/runtime-master.r16")
    if (authored["dressing_ledger_sha256"] != ledger_sha or authored["r16_sha256"] != field_sha or
            verification["editor"]["dressing_ledger_sha256"] != ledger_sha or
            verification["editor"]["terrain_r16_sha256"] != field_sha):
        raise ValueError("Native world and physical source were cooked from different placements or terrain")
    verification.update(dressing_ledger_sha256=ledger_sha,terrain_r16_sha256=field_sha,
                        terrain_manifest_sha256=sha(out/"terrain/runtime-master.json"))
    if apron:
        bank = out / 'bank'
        survey = json.loads((bank/'survey.json').read_text())
        verified = json.loads((bank/'surface-verified.json').read_text())
        plants = json.loads((bank/'editor-verified.json').read_text())
        if (verified['surface_sha256'] != sha(bank/'surface.json') or
            verified['support_sha256'] != verification['geometry']['bank_support_sha256'] or
            survey['rock_ledger_sha256'] != ledger_sha or survey['terrain_sha256'] != field_sha or
            plants['transforms_read_back'] != survey['planting'] or
            plants['source_plan_sha256'] != sha(bank/'planting.json')):
            raise ValueError('Shore art and native game support do not match')
        verification.update(rebuild='levels/warfare/pwr/build_headwater_native.ps1 -RiverApron -OutputPath out/pwr/river-apron',
                            material=json.loads((bank/'material.json').read_text()),
                            outlet_surface=verified, planting=plants, outlet_survey=survey,
                            compared_to='saturday.35', plants_by_kind=json.loads((bank/'placements.json').read_text()))
    if basin:
        parent = ROOT/'out/pwr/river-apron'
        sealed = json.loads((parent/'finish37/receipt.json').read_text())
        plants = json.loads((out/'basin-verified.json').read_text())
        if (plants['plan_sha256']!=sha(out/'basin-plants.json') or
                plants['placement']['terrain_manifest_sha256']!=verification['terrain_manifest_sha256'] or
                verification['geometry']['bank_support_sha256']!=sealed['editor_readback']['mesh']['support_sha256'] or
                verification['geometry']['retained_previous_terrain_faces']<=0 or
                plants['protected_outlet_transforms']<=0):
            raise ValueError('Protected outlet or new basin readback mismatch')
        oldland=world_entries(old/(LAND+'.utoc'))
        newland=world_entries(maps/(LAND+'.utoc'))
        joins=json.loads((n/'physics/seam-survey.json').read_text())
        if joins['worst_vertical_join_m']>.0001 or joins['max_horizontal_join_m']>.00025 or not joins['preserved_terrain_vertices_byte_identical']:
            raise ValueError('Unsealed basin collision boundary')
        immutable={k:h for k,h in oldland.items() if 'OutletAlluvium.' in k or 'T_PWR_RiverCobble' in k}
        if len(immutable)!=6 or any(newland.get(k)!=h for k,h in immutable.items()):
            raise ValueError('Outlet artwork or photographic material sources changed')
        verification.update(rebuild='levels/warfare/pwr/build_headwater_native.ps1 -RiverBasin -OutputPath out/pwr/river-basin',
                            joined_collision_perimeter=joins,compared_to='saturday.37',parent_native_members=sealed['native_members'],
                            retained_outlet_assets=immutable,retained_outlet_mesh=sealed['editor_readback']['mesh'],
                            planting=plants,initial_boundary_audit=json.loads((out/'original-boundary-audit.json').read_text()) if (out/'original-boundary-audit.json').exists() else None)
    (n / "landscape-collision.json").write_text(json.dumps(verification, indent=2))


if __name__ == "__main__":
    (prepare if "--prepare" in sys.argv else finish)()

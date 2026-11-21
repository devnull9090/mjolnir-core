"""Cooked-package and release checks for the outlet planting, cutbank and spring."""
import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace

import package_pwr_headwater as p
from bases_v1.stage_base_polish import seal_release, unpack_map
from stage_apron_finish import asset_layout
from stage_world_playtest import jsonfile, stage_name
import sys
sys.path.insert(0, str(p.ROOT / "tools/level"))
from flux_wrap_safe import make_level_safe
import forerunner_surfaces
import stage_vista
import stage_interiors

WORK = p.ROOT / "out/pwr/river-riparian"
BASIN = WORK.parent / "river-basin"
PARENT = "dc06be35b9549104baaba411eb86395651630b1011db4009918f08d1c76d8f0e"
BASELINE = BASIN / "saturday.39"
PRIOR = BASIN / "shore-contact/native/map-input"
WORLD_MAP = "Meteorite/Content/Levels/Halo1/Solo/PWR/PWR"

def prepare(version):
    checked = jsonfile(WORK/"editor-verified.json")
    stem_names = set(checked["assets"])
    additions = {"MJOLNIR/GrassPilot/Playable/" + stem + ext for stem in stem_names for ext in (".uasset",".ubulk")}
    required = {name for name in additions if name.endswith(".uasset")}
    baseline = jsonfile(BASELINE/"receipt.json")
    old = jsonfile(PRIOR.parent/"receipt.json")
    if p.sha(BASELINE/baseline["archive"]) != PARENT or baseline["sha256"] != PARENT:
        raise ValueError("Wrong lake release")
    for name, expected in old["native_members"].items():
        if p.sha(PRIOR/name) != expected or baseline["members_sha256"]["content/"+name] != expected:
            raise ValueError("Parent native package changed: "+name)
    p.out, p.n, p.maps, p.old = WORK, WORK/"packaging", WORK/"map-input", PRIOR
    p.apron = p.basin = False
    p.n.mkdir(exist_ok=True)
    # A round may also change named existing map assets, listed one by one in
    # PWR_ALLOW_LAND_CHANGES (comma-separated container paths, e.g. the meadow pass's
    # MJOLNIR/GrassPilot/Playable/GT_PWRPilot.uasset). Nothing else may change.
    edits = {k.strip() for k in os.environ.get("PWR_ALLOW_LAND_CHANGES", "").split(",") if k.strip()}
    p.prepare(allowed_additions=additions | edits, require_material_change=False)
    toc = p.LAND + ".utoc"
    changes = jsonfile(p.n/"land-diff.json")
    if not required <= {k for k,v in changes.items() if v[0] is None}:
        raise ValueError("Missing native lake packages")
    if any(k not in additions and k not in edits and not k.endswith(("/LPE/LPE.umap","/LPE/LPE.ubulk",".ushaderbytecode")) for k in changes):
        raise ValueError("Unrelated native art change: "+str(list(changes)))
    mount, container_id, before = asset_layout(p.LAND, PRIOR/toc)
    new_mount, new_id, after = asset_layout(p.LAND, p.maps/toc)
    if (mount, container_id) != (new_mount, new_id) or any(after.get(k) != address for k,address in before.items()):
        raise ValueError("Changed a prior native asset address")
    bsp = BASIN / "native/physics/pwr.sbsp"
    if p.sha(bsp) != old["retained_bsp_sha256"]:
        raise ValueError("Terrain collision mismatch")
    support=None
    if version>=41:
        physics=WORK/"native/physics"
        bsp=physics/"pwr.sbsp"
        support=jsonfile(physics/"collision_scene.json")["riparian_cutbank"]
        verified=jsonfile(physics/"native-readback.json")
        if (p.sha(bsp)!=verified["compiled_bsp_sha256"] or support["support_sha256"]!=p.sha(WORK/"cutbank/support.npz")
                or support["changed_faces"]!=verified["verified_changed_faces"] or not verified["root_and_definition_havok_queries"]):
            raise ValueError("New bank support is unverified")
    folder = p.n/"world-bake"
    p.run([p.cli,"level","bake",BASIN/"native/native-level.json","--paks",p.paks,"--standalone","PWR",
           "--bsp","8="+str(bsp.resolve()),"--out-dir",folder,"--world",p.n/"LPE.umap"],p.n/"world-bake.log")
    world_toc = p.WORLD+".utoc"
    world_changes = p.changes(PRIOR/world_toc,folder/world_toc)
    allowed={WORLD_MAP+".umap",WORLD_MAP+".ubulk"}
    if support:
        allowed.update(k for k in world_changes if k.endswith(("/BSP_01_1_Start-scenario_structure_bsp.uasset","/BSP_01_1_Start-scenario_structure_bsp.ubulk")))
        if not any(k.endswith("-scenario_structure_bsp.ubulk") for k in allowed):
            raise ValueError("World cook did not include the new shore physics")
    if WORLD_MAP+".umap" not in world_changes or world_changes.keys()-allowed:
        raise ValueError("Unexpected gameplay, collision or lighting change: "+str(list(world_changes)))
    for suffix in (".ucas",".utoc"):
        shutil.copyfile(folder/(p.WORLD+suffix),p.maps/(p.WORLD+suffix))
    return dict(native_members={name:p.sha(p.maps/name) for name in old["native_members"]},
                editor=checked,land_packages=changes,world_packages=world_changes,
                base_bsp_sha256=old["retained_bsp_sha256"],compiled_bsp_sha256=p.sha(bsp),shore_support=support)

def stage(art, version):
    output = WORK / ("saturday."+str(version))
    if output.exists():
        raise FileExistsError(output)
    args = SimpleNamespace(baseline=BASELINE,cli=p.ROOT/"target/release/mjolnir.exe",version="0.1.0-playtest."+str(version))
    with tempfile.TemporaryDirectory(dir=WORK) as tmp:
        folder=Path(tmp)/"release"
        folder.mkdir()
        inputs, parent, hashes, manifest=unpack_map(BASELINE,folder)
        original=dict(hashes)
        for name, expected in art["native_members"].items():
            shutil.copyfile(p.maps/name,inputs/name)
            if p.sha(inputs/name)!=expected:
                raise ValueError("Staged native package differs: "+name)
            hashes["content/"+name]=expected
        # Baked Flux borders: wrap-safe, so the river tile's south edge does not blend with its
        # high north edge into a curtain at the seam (tools/level/flux_wrap_safe.py).
        changed, flux_report = make_level_safe(inputs/"pwr.level.json", inputs)
        # Forerunner ground: courts, approaches and site finishes onto the Forerunner floor master and
        # natural bed ground (tools/level/forerunner_surfaces.py). Slot names come from this release's
        # own cooked meshes, read beside the game's global container.
        with tempfile.TemporaryDirectory(dir=WORK) as paks:
            for f in inputs.glob("pakchunk*.u*"):
                shutil.copyfile(f, Path(paks)/f.name)
            for g in ("global.utoc", "global.ucas"):
                shutil.copyfile(Path(p.paks)/g, Path(paks)/g)
            level = jsonfile(inputs/"pwr.level.json")
            surface_report = forerunner_surfaces.reskin(level, str(p.ROOT/"target/release/mjolnir.exe"), str(Path(paks).resolve()))
            # Distant range: atmosphere and range material values (visual_dressing/vista.json), and
            # a re-refined range mesh container when PWR_VISTA_APRON names a packaged apron folder.
            vista_report = stage_vista.apply(inputs, level, hashes, os.environ.get("PWR_VISTA_APRON") or None)
            # Base interiors (stage_interiors.py): the meshes whose coplanar faces were separated go
            # into the release's own base container when PWR_BASES_COOKED names their cook
            # (PWR_BASES_MANIFEST the import manifest); then lights at the lamps of the meshes as
            # they now ship, and the lamps' glow.
            interiors = {}
            if os.environ.get("PWR_BASES_COOKED"):
                interiors["splice"] = stage_interiors.splice(inputs, os.environ["PWR_BASES_COOKED"], hashes,
                                                             os.environ["PWR_BASES_MANIFEST"])
                for f in inputs.glob("pakchunk955-*.u*"):
                    shutil.copyfile(f, Path(paks)/f.name)
            if os.environ.get("PWR_UI_CONTAINER"):
                interiors["ui_container"] = stage_interiors.ui_container(inputs, os.environ["PWR_UI_CONTAINER"], hashes)
            fixtures = jsonfile(stage_vista.CONFIG).get("fixture_lights")
            if fixtures:
                interiors["lights"] = stage_interiors.light(level, str(p.ROOT/"target/release/mjolnir.exe"),
                                                            str(Path(paks).resolve()), fixtures)
            (inputs/"pwr.level.json").write_text(json.dumps(level, indent=2))
        for rel in changed+["level.json"]:
            member = "map/"+rel
            hashes[member] = p.sha(inputs/stage_name(member))
        seal_release(args,folder,inputs,parent,hashes,manifest,dict(
            modified_members=sorted(k for k in hashes if hashes[k]!=original[k]),
            riparian_shore=art,compiled_bsp_sha256=art["compiled_bsp_sha256"],flux_wrap_safe=flux_report,forerunner_surfaces=surface_report,vista=vista_report,interiors=interiors))
        folder.rename(output)
    print(output)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--version",type=int,default=43)
    version=parser.parse_args().version
    stage(prepare(version),version)

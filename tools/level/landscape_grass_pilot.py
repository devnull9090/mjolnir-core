"""CPU preparation and strict saved-buffer validation for the opt-in PWR grass pilot.

Preparation uses NumPy/SciPy/Shapely/Pillow; validation is stdlib-only so the
same contract runs in Unreal Python. This module never launches an app.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "mjolnir-landscape-grass-pilot-v1"
ASSETS = "/Game/MJOLNIR/GrassPilot/PWRV7"
ASSETS_V8 = "/Game/MJOLNIR/GrassPilot/PWRV8"
WORLD = "/Game/Levels/Halo1/Solo/LPG/LPG"
FIELD_WORLD = "/Game/Levels/Halo1/Solo/LPE/LPE"
FIELD_ASSETS = "/Game/MJOLNIR/GrassPilot/Playable"
CANYON_SOURCE = "/Game/Env/Bio/Grass/CanyonPrinceWildRye/MI_Grass_CanyonPrinceWildRye"
CANYON_TARGET = "/Game/MJOLNIR/GrassMaterials/PWRV8/MI_PWR_Canyon_Offset10"
CANYON_OBJECT = CANYON_TARGET + "." + CANYON_TARGET.rsplit("/", 1)[-1]
CANYON_CONTAINER = "pakchunk966-MJOLNIRGRASS-PWR_P"
MATERIAL_NEVER_COOK = "/Game/MJOLNIR/GrassMaterials"
PACKAGING_SETTINGS = ROOT / "Unreal/MJOLNIRMaterials/Config/DefaultGame.ini"
FAMILIES = [
    ("canyon", "/Game/Env/Bio/Grass/CanyonPrinceWildRye/SM_Grass_CanyonPrinceWildRye.SM_Grass_CanyonPrinceWildRye", 125., [.5, .65]),
    ("crab", "/Game/Env/Bio/PNW/Meshes/SM_Crab_Grass/SM_Crab_Grass_Clump_B.SM_Crab_Grass_Clump_B", 25., [.75, .9]),
    ("wild", "/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/S_Wild_Grass_vczndjqja_Var12_lod0.S_Wild_Grass_vczndjqja_Var12_lod0", 100/6, [.6, .8]),
]
OLD_MEADOW = [
    "/Game/Env/Bio/Grass/Sedges/Grass_Sedges_A/SM_Grass_Sedges_A_Leaves_C.SM_Grass_Sedges_A_Leaves_C",
    "/Game/Megascans/3D_Plants/Tall_Grass_rbeki/SM_Tall_Grass_rbeki_01.SM_Tall_Grass_rbeki_01",
    "/Game/Env/Bio/Grass/Rushes/Grass_Rushes_A/SM_Grass_Rushes_A.SM_Grass_Rushes_A",
]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def material_cook_inputs(config, folder):
    """Pin the optional external native MIC; the same-path editor MIC never ships."""
    material = config.get("canyon_material")
    if material is None:
        return {}
    if (material.get("schema") != "pwr-canyon-max-offset-v1"
            or material.get("source") != CANYON_SOURCE or material.get("target") != CANYON_TARGET
            or material.get("container") != CANYON_CONTAINER
            or material.get("never_cook") != MATERIAL_NEVER_COOK):
        raise ValueError("Only the owned Canyon Max Offset material is permitted")
    inputs = {}
    def pinned(key, entry):
        path = Path(entry["path"])
        if not path.is_absolute():
            path = Path(folder) / path
        path = path.resolve()
        if digest(path) != entry["sha256"]:
            raise ValueError("Stale native grass material " + key)
        inputs["native_grass_material_" + key] = path
        return path
    manifest = pinned("manifest", material["manifest"])
    expected = [{"source": CANYON_SOURCE, "target": CANYON_TARGET,
                 "scalars": {"Max Offset#-1": {"value": 10., "association": 2}}, "vectors": {}}]
    if json.loads(manifest.read_text(encoding="utf-8")) != expected:
        raise ValueError("Native grass clone must change only global Max Offset to 10")
    proof_path = pinned("proof", material["proof"])
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    wanted_scalar = {"name": "Max Offset", "association": 2, "index": -1,
                     "value": 10., "expression_guid": "00000000000000000000000000000000"}
    if (proof.get("schema") != "pwr-native-grass-material-clone-independent-audit-v1"
            or proof.get("status") != "passed"
            or proof.get("source", {}).get("identity") != CANYON_SOURCE
            or proof.get("clone", {}).get("identity") != CANYON_TARGET
            or any(proof.get("added_scalar", {}).get(key) != value for key, value in wanted_scalar.items())
            or any(proof.get(key) is not True for key in ("source_properties_preserved",
                "native_tail_identical", "native_parent_and_texture_imports_preserved", "existing_guids_preserved"))):
        raise ValueError("Native grass clone preservation proof failed")
    files = material["files"]
    if len(files) != 3:
        raise ValueError("Native grass material requires exactly one complete external container")
    expected_names = {CANYON_CONTAINER + suffix for suffix in (".pak", ".utoc", ".ucas")}
    actual_names = set()
    for entry in files:
        path = pinned(Path(entry["path"]).suffix[1:], entry)
        actual_names.add(path.name)
    if actual_names != expected_names:
        raise ValueError("Unexpected native grass material container")
    pinned("tool", material["tool"])
    proof_seals = {}
    for index, entry in enumerate(proof.get("input_seals", [])):
        proof_seals[pinned("evidence_" + str(index), entry)] = entry["sha256"]
    for key in ("manifest", "tool", "pak", "utoc", "ucas"):
        path = inputs["native_grass_material_" + key]
        if proof_seals.get(path) != digest(path):
            raise ValueError("Native grass proof does not bind current " + key)
    for index, entry in enumerate(material.get("evidence", [])):
        pinned("extra_evidence_" + str(index), entry)
    never_cook = '+DirectoriesToNeverCook=(Path="' + MATERIAL_NEVER_COOK + '")'
    if never_cook not in PACKAGING_SETTINGS.read_text(encoding="utf-8").splitlines():
        raise ValueError("Native grass editor stand-in must remain NeverCook")
    inputs["native_grass_material_packaging"] = PACKAGING_SETTINGS
    return inputs


def archive_owned_editor_assets(source, destination):
    """Copy and verify retired editor bytes before the caller deletes their assets."""
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination == source or source in destination.parents:
        raise ValueError("Editor archive must be outside its source folder")
    entries = []
    for original in sorted(source.rglob("*")):
        if not original.is_file():
            continue
        relative = original.relative_to(source)
        backup = destination / relative
        original_hash = digest(original)
        if backup.exists() and digest(backup) != original_hash:
            raise ValueError("Refusing to replace an earlier editor archive: " + str(backup))
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            shutil.copy2(original, backup)
        if digest(backup) != original_hash:
            raise ValueError("Editor archive failed byte verification: " + str(original))
        entries.append({"file": relative.as_posix(), "sha256": original_hash,
                        "bytes": original.stat().st_size})
    if not entries:
        raise ValueError("Cannot retire an empty or missing editor asset folder")
    receipt = {"source": str(source), "archive": str(destination), "files": entries}
    dump(destination / "archive.receipt.json", receipt)
    return receipt


def prepare_material_variant(base_pilot, land, material_folder, output):
    """Freeze the proven two-component geometry while adding the accepted Canyon MIC."""
    base_pilot, land, material_folder, output = (Path(p).resolve()
                                               for p in (base_pilot, land, material_folder, output))
    config = json.loads(base_pilot.read_text(encoding="utf-8"))
    validate_config(config, base_pilot.parent)
    if config.get("canyon_material"):
        raise ValueError("Material variant requires the unmodified native V7 pilot")
    new_spec = land / "landscape.json"
    spec = json.loads(new_spec.read_text(encoding="utf-8"))
    if any(spec[key] != value for key, value in config["grid"].items()):
        raise ValueError("Material-only grass variant cannot change the native terrain grid")
    if digest(land / spec["heights"]) != config["heights"]["sha256"]:
        raise ValueError("Material-only grass variant cannot change native terrain heights")
    old_specs = [entry for entry in config["sources"] if Path(entry["path"]).name == "landscape.json"]
    if len(old_specs) != 1:
        raise ValueError("Expected exactly one source landscape spec")
    old_land = Path(old_specs[0]["path"]).parent
    for entry in config["sources"]:
        original = Path(entry["path"])
        if original.parent == old_land:
            replacement = land / original.name
            entry.update(path=str(replacement), sha256=digest(replacement))
    config["sources"].append({"path": str(base_pilot), "sha256": digest(base_pilot)})
    def pinned(path):
        return {"path": str(path), "sha256": digest(path)}
    config["canyon_material"] = {
        "schema": "pwr-canyon-max-offset-v1", "source": CANYON_SOURCE, "target": CANYON_TARGET,
        "container": CANYON_CONTAINER, "never_cook": MATERIAL_NEVER_COOK,
        "manifest": pinned(material_folder / "clone.manifest.json"),
        "proof": pinned(material_folder / "qa-independent-proof.json"),
        "tool": pinned(ROOT / "out/pwr/toolchain-wind-v7/native_material_clone.exe"),
        "files": [pinned(material_folder / (CANYON_CONTAINER + suffix)) for suffix in (".pak", ".utoc", ".ucas")]}
    config["asset_folder"] = ASSETS_V8
    config["varieties"][0]["override_materials"] = [CANYON_OBJECT]
    config["notes"] = config.get("notes", []) + [
        "V8 changes only Canyon Max Offset to 10, global association 2/index -1; native WPO stays enabled.",
        "The external native MIC is required; the same-path editor stand-in is NeverCook.",
        "Two-component mask, densities, scales, cull, other varieties and baseline groundcover remain frozen."]
    if output.exists():
        raise ValueError("Material variant requires a fresh output folder")
    output.mkdir(parents=True)
    for key in ("mask", "texture", "heights"):
        shutil.copy2(base_pilot.parent / config[key]["file"], output / config[key]["file"])
    validate_config(config, output)
    dump(output / "pilot.json", config)
    print(json.dumps({"config": str(output / "pilot.json"), "container": CANYON_CONTAINER,
                      "material": CANYON_OBJECT, "section_bases": config["section_bases"]}))


def component_weights(mask, size, quads, x, y):
    return b"".join(mask[(y+j)*size+x:(y+j)*size+x+quads+1] for j in range(quads+1))


def filter_meadow_group(group, payload, sidecars, count):
    """Stable byte selection only; all positions/rotations/scales retain PCG provenance."""
    if group.get("mesh") not in OLD_MEADOW or group.get("rule") != "visual6 meadow":
        return group,payload,sidecars,count
    if not group.get("pcg") or not group.get("exact") or len(sidecars.get("xf",b"")) != count*40:
        raise ValueError("Meadow source must carry exact UE PCG transforms")
    keep=[]
    for index,pose in enumerate(struct.iter_unpack("<10f",sidecars["xf"])):
        if not all(math.isfinite(v) for v in pose): raise ValueError("Non-finite source grass pose")
        # Whole two-component area in Unreal centimetres, including its boundary.
        if not (12500 <= pose[0] <= 37500 and 37500 <= pose[1] <= 50000): keep.append(index)
    records=payload[4:]
    result=struct.pack("<I",len(keep))+b"".join(records[i*19:(i+1)*19] for i in keep)
    filtered={suffix:b"".join(data[i*stride:(i+1)*stride] for i in keep)
              for suffix,data in sidecars.items() for stride in [40 if suffix=="xf" else 16]}
    return group,result,filtered,len(keep)


def filter_existing_foliage(source, output):
    from pcg_foliage import read_mjf_groups
    source,output=Path(source).resolve(),Path(output).resolve()
    if source.parent == output: raise ValueError("Cannot overwrite source foliage")
    spec,groups=read_mjf_groups(source)
    if ([row[3] for row in groups] != [279132,359355,79829,9995]
            or [row[0]["mesh"] for row in groups[1:]] != OLD_MEADOW
            or groups[0][0].get("rule") != "short grass"):
        raise ValueError("Source is not the reviewed four-group visual6 PCG foliage")
    final=[filter_meadow_group(*row) for row in groups]
    if final[0] != groups[0]: raise ValueError("Original groundcover changed")
    output.mkdir(parents=True,exist_ok=True)
    binary=output/"foliage.bin"
    binary.write_bytes(b"MJF3"+struct.pack("<II",3,len(final))+b"".join(row[1] for row in final))
    for index,(_,_,sidecars,_) in enumerate(final,1):
        for suffix,data in sidecars.items(): Path(f"{binary}.{suffix}{index}").write_bytes(data)
    dump(output/"foliage.json",dict(spec,file=binary.name,groups=[row[0] for row in final]))
    read_mjf_groups(output/"foliage.json")
    source_binary=source.parent/spec["file"]
    sources=[source,source_binary]+[Path(f"{source_binary}.{suffix}{i}")
                                   for i,row in enumerate(groups,1) for suffix in row[2]]
    receipt={"schema":"pwr-native-grass-pilot-filter-v1","selection":"Remove only visual6 meadow roots inside the two pilot components",
             "bounds_unreal_cm":[12500,37500,37500,50000],"preserved_groundcover":279132,
             "baseline_payload_sha256":hashlib.sha256(groups[0][1]).hexdigest(),
             "baseline_exact_transforms_sha256":hashlib.sha256(groups[0][2]["xf"]).hexdigest(),
             "sources":[{"path":str(p),"sha256":digest(p)} for p in sources],
             "groups":[{"input":old[3],"retained":new[3],"removed":old[3]-new[3],
                        "retained_record_and_sidecar_bytes_exact":True} for old,new in zip(groups,final)]}
    dump(output/"filter.receipt.json",receipt)
    return {"spec":str(output/"foliage.json"),
            "files":[{"path":str(p),"sha256":digest(p)} for p in sorted(output.iterdir()) if p.is_file()]},sources,receipt


def validate_config(config, folder):
    """Fail before editor mutations if input hashes, scope, density or bounds changed."""
    folder = Path(folder)
    production = config.get("world") == FIELD_WORLD
    if config.get("schema") != SCHEMA or config.get("world") not in (WORLD, FIELD_WORLD):
        raise ValueError("Not the isolated PWR grass pilot")
    material_inputs = material_cook_inputs(config, folder)
    expected_assets = FIELD_ASSETS if production else ASSETS_V8 if material_inputs else ASSETS
    if config.get("asset_folder") != expected_assets or config.get("source_world") == WORLD:
        raise ValueError("Pilot source/destination must remain separate")
    if config.get("chunk") != 965:
        raise ValueError("Pilot belongs only to chunk 965")
    if config.get("source_world") != "/Game/Levels/Halo1/Solo/LPW/LPW":
        raise ValueError("Unexpected source world")
    if config.get("preserved_groundcover") != 279132 or config.get("serialized_instances") != 0:
        raise ValueError("Baseline preservation / streaming contract changed")
    if not config.get("sources"):
        raise ValueError("Missing pinned source inputs")
    for source in config["sources"]:
        if digest(source["path"]) != source["sha256"]:
            raise ValueError("Stale grass source: " + source["path"])
    grid = config["grid"]
    if (grid["size"], grid["components"], grid["sections"], grid["quads"]) != (1009, 16, 1, 63):
        raise ValueError("Pilot requires the frozen 16x16 native grid")
    if grid["location"] != [-100000., -100000., 22400.] or len(grid["scale"]) != 3 or any(
        abs(a-b) > 1e-8 for a, b in zip(grid["scale"], [12500/63, 12500/63, 100.])):
        raise ValueError("Landscape transform changed")
    selected = {tuple(v) for v in config["section_bases"]}
    if production and (len(selected) != len(config["section_bases"]) or not 3 <= len(selected) <= 256):
        raise ValueError("Full-field support must name distinct Landscape components")
    if not production and (selected != {(567, 693), (630, 693)} or len(config["section_bases"]) != 2):
        raise ValueError("Exactly the two reviewed components are permitted")
    for key in ("mask", "texture", "heights"):
        entry = config[key]
        path = (folder / entry["file"]).resolve()
        if path.parent != folder.resolve() or digest(path) != entry["sha256"]:
            raise ValueError("Changed or external pilot " + key)
    mask = (folder / config["mask"]["file"]).read_bytes()
    if len(mask) != grid["size"]**2:
        raise ValueError("Invalid mask byte length")
    if (folder / config["heights"]["file"]).stat().st_size != 2*len(mask):
        raise ValueError("Invalid height byte length")
    for y in range(0, grid["size"]-1, grid["quads"]):
        for x in range(0, grid["size"]-1, grid["quads"]):
            nonzero = sum(v > 0 for v in component_weights(mask, grid["size"], grid["quads"], x, y))
            if ((x, y) in selected) != (nonzero > 0):
                raise ValueError(f"Grass support escaped or emptied pilot component {(x,y)}")
    varieties = config["varieties"]
    if len(varieties) != len(FAMILIES):
        raise ValueError("Unexpected variety count")
    for row, (name, mesh, density, scales) in zip(varieties, FAMILIES):
        overrides = [CANYON_OBJECT] if material_inputs and name == "canyon" else []
        if (row["name"] != name or row["mesh"] != mesh or row["scale"] != scales
                or not math.isfinite(row["density_per_100m2"]) or abs(row["density_per_100m2"]-density) > 1e-8
                or row.get("override_materials") != overrides):
            raise ValueError("Native variety identity, scale, density or slots changed")
    if config["cull_cm"] != [4000, 6000]:
        raise ValueError("Pilot cull range changed")
    if config.get("filtered_foliage"):
        for entry in config["filtered_foliage"]["files"]:
            if digest(entry["path"]) != entry["sha256"]:
                raise ValueError("Changed filtered foliage: "+entry["path"])
    return mask


def validate_readback(config, folder, readback, *, require_saved=False):
    mask = validate_config(config, folder)
    if readback.get("error"):
        raise ValueError(readback["error"])
    if readback.get("schema") != "mjolnir-native-grass-readback-v1" or readback.get("world") != config["world"]:
        raise ValueError("Readback from wrong world/schema")
    if require_saved and readback.get("built") is not False:
        raise ValueError("Saved verification must read without generating grass data")
    expected_type = config["asset_folder"] + "/GT_PWRPilot.GT_PWRPilot"
    expected_material = config["asset_folder"] + "/M_PWRPilot.M_PWRPilot"
    if readback.get("grass_type") != expected_type:
        raise ValueError("Wrong grass type")
    expected_varieties = [{"mesh": row["mesh"], "override_materials": row["override_materials"]}
                          for row in config["varieties"]]
    if ("varieties" in readback or config.get("canyon_material")) and readback.get("varieties") != expected_varieties:
        raise ValueError("Saved native grass variety material binding changed")
    heights = (Path(folder)/config["heights"]["file"]).read_bytes()
    size, quads = config["grid"]["size"], config["grid"]["quads"]
    expected = {(x,y) for x in range(0,size-1,quads) for y in range(0,size-1,quads)}
    seen, nonempty, total, max_error = set(), set(), 0, 0
    for row in readback["components"]:
        key = (row["x"], row["y"])
        if key in seen or key not in expected or row["quads"] != quads:
            raise ValueError("Duplicate/unexpected landscape component")
        seen.add(key)
        if row.get("error") or row["material"] != expected_material or row["grass_types"] != [expected_type]:
            raise ValueError("Invalid component grass/material binding")
        wanted = component_weights(mask, size, quads, *key)
        n = row["num_elements"]
        if n == 0:
            if any(wanted) or row["weight_channels"] != 0 or row.get("weights_b64"):
                raise ValueError("Missing nonzero saved grass data")
            continue
        if n != (quads+1)**2 or row["weight_channels"] not in (0,1):
            raise ValueError("Unbuilt or malformed native grass data")
        actual_heights = base64.b64decode(row["heights_b64"], validate=True)
        x,y = key
        wanted_heights = b"".join(heights[2*((y+j)*size+x):2*((y+j)*size+x+quads+1)] for j in range(quads+1))
        if actual_heights != wanted_heights:
            raise ValueError("Grass height buffer differs from frozen native terrain")
        if row["weight_channels"] == 0:
            if any(wanted) or row.get("weights_b64"):
                raise ValueError("Missing nonzero saved grass data or unexpected stripped-channel weights")
            continue
        actual = base64.b64decode(row["weights_b64"], validate=True)
        if len(actual) != len(wanted):
            raise ValueError("Malformed grass weight buffer length")
        error = max(abs(a-b) for a,b in zip(actual,wanted))
        if error > 1 or any(a and not b for a,b in zip(actual,wanted)):
            raise ValueError("Saved grass weights differ or leak into excluded cells")
        max_error = max(max_error,error)
        count = sum(v > 0 for v in actual)
        if count: nonempty.add(key)
        total += count
    if seen != expected or nonempty != {tuple(v) for v in config["section_bases"]}:
        raise ValueError("Missing components or grass outside the two-component pilot")
    return {"components":len(seen), "nonzero_components":len(nonempty),
            "nonzero_weight_samples":total, "maximum_weight_byte_error":max_error,
            "saved_buffers_verified":require_saved}


def ground_support(land, scenery, *, include_dry_banks=False):
    """Playable ground after terrain, paving, measured scenery and gameplay clearances."""
    import numpy as np
    from scipy.ndimage import distance_transform_edt
    import shapely
    from shapely.geometry import MultiPoint, box, shape
    from shapely.ops import unary_union
    from heightfield import load_heightfield
    import b30_collision, pcg_tree_decor
    from authored_decor import expand_background_trees

    master = ROOT/"levels/warfare/pwr/terrain/runtime-v5/runtime-master.json"
    scenery = Path(scenery).resolve() if scenery else ROOT/"out/pwr/visual-v6/scenery"
    paving_path = ROOT/"out/pwr/visual-v5/base-paving-v3/footprints.geojson"
    trees_path, rocks_path = scenery/"trees/trees.selected.json", scenery/"rocks-and-outcrops.authored-decor.json"
    recipes_path = scenery/"trees/recipes.json"
    spec_path = land/"landscape.json"
    spec = json.loads(spec_path.read_text())
    field = load_heightfield(master)
    if field.dimensions != (1009,1009): raise ValueError("Native field dimensions changed")
    sources = {master, spec_path, land/spec["heights"], paving_path, trees_path, rocks_path, recipes_path}
    for item in [field.metadata["height"], *field.metadata["masks"].values()]:
        sources.add((master.parent/item["path"]).resolve())
    trees, rocks, recipes = [json.loads(p.read_text()) for p in (trees_path, rocks_path, recipes_path)]
    if len(trees["instances"]) != 4702 or len(rocks["decor"]) != 1072:
        raise ValueError("Reviewed visual6 scenery changed")
    tree_decor, leaves = expand_background_trees(pcg_tree_decor.convert(trees, recipes, max_trees=6000), recipes, {})
    if leaves or len(tree_decor) != 4702: raise ValueError("Unexpected tree expansion")
    obstacles = []
    for is_tree, rows in ((False, rocks["decor"]), (True,tree_decor)):
        for row in rows:
            leaf = row["mesh"].split(".")[-1].rsplit("/",1)[-1]
            bark = scenery/"hulls"/(leaf+"_bark_v1.json")
            path = bark if is_tree and bark.exists() else scenery/"hulls"/(leaf+".json")
            data = json.loads(path.read_text()); sources.add(path)
            points = np.asarray(data["points"],float)*row["scale"]
            points = points @ b30_collision.rotator_matrix(*row["rot"]) + row["pos"]
            # Convex hull of measured points, with the existing grass clearance.
            footprint = MultiPoint(points[:,:2]*[.01,-.01]).convex_hull
            obstacles.append(footprint.buffer(.45 if is_tree else .55))
    paving = unary_union([shape(v["geometry"]) for v in json.loads(paving_path.read_text())["features"]])
    obstacles.append(paving.buffer(1.0))
    # Retain the earlier PCG's explicitly protected gameplay/collision probe areas.
    from shapely.geometry import Point
    protected_path=ROOT/"out/pwr/visual-v5/forest-v2/inputs.receipt.json"
    probes_path=ROOT/"out/pwr/world-v5/visual5/native-refresh/terrain-probe-plan.json"
    sources.update((protected_path,probes_path))
    for _,xy,radius in json.loads(protected_path.read_text())["clearance_discs"]:
        obstacles.append(Point(xy).buffer(radius))
    for probe in json.loads(probes_path.read_text())["probes"]:
        obstacles.append(Point(probe["position_m"][:2]).buffer(max(8,probe.get("max_walk_metres",0)+4)))
    clearance = math.sqrt(2)*spec["scale"][0]/100 + 1.25
    exclusion = unary_union(obstacles).buffer(clearance)
    size, q = spec["size"], spec["quads"]
    xx = spec["location"][0]/100 + np.arange(size)*spec["scale"][0]/100
    yy = -(spec["location"][1]/100 + np.arange(size)*spec["scale"][1]/100)
    x,y = np.meshgrid(xx,yy)
    required = ("road","bases","water","shore","walkable")
    if any(k not in field.masks for k in required): raise ValueError("Missing ecology exclusion mask")
    eligible = np.ones(x.shape,dtype=bool)
    for name in ("road","bases","water"):
        eligible &= field.sample_mask(name,x,y) == 0
    if not include_dry_banks:
        eligible &= field.sample_mask("shore",x,y) < .25
    eligible &= field.sample_mask("walkable",x,y) > .5
    dy,dx = np.gradient(field.heights_m,field.spacing_m[0])
    normal_z = 1/np.sqrt(1+dx*dx+dy*dy)
    eligible &= field._sample(normal_z,x,y,True) > .8
    eligible = distance_transform_edt(eligible,sampling=spec["scale"][0]/100) > clearance
    eligible &= ~shapely.intersects_xy(exclusion,x,y)
    return field, spec, scenery, sources, x, y, eligible, clearance


def prepare(output, land, scenery=None):
    import numpy as np
    import shapely
    from PIL import Image
    from shapely.geometry import box
    output, land = Path(output).resolve(), Path(land).resolve()
    output.mkdir(parents=True, exist_ok=True)
    field,spec,scenery,sources,x,y,eligible,clearance = ground_support(land,scenery)
    filtered,foliage_sources,filter_receipt=filter_existing_foliage(scenery/"grass/foliage.json",output/"filtered-foliage")
    sources.update(foliage_sources)
    # The whole adjacent pair is one region: its internal shared edge may carry grass.
    region = box(125,-500,375,-375).buffer(-clearance)
    eligible &= shapely.contains_xy(region,x,y)
    # This first structural pilot deliberately uses full density wherever eligible.
    # Production ecology modulation is separate; no PCG/tree/rock selection is modified.
    weights = (eligible.astype(np.uint8)*255)
    raw = output/"density.r8"; raw.write_bytes(weights.tobytes())
    texture = output/"density.png"
    rgba = np.repeat(weights[:,:,None],4,axis=2); rgba[:,:,3]=255
    Image.fromarray(rgba).save(texture)
    heights = output/"heights.r16"; heights.write_bytes((land/spec["heights"]).read_bytes())
    varieties=[]
    for name,mesh,density,scale in FAMILIES:
        source = ROOT/"out/pwr/visual-v7/grass-pilot-mixed/assets"/(mesh.split(".")[-1]+".glb")
        data=source.read_bytes(); doc=json.loads(data[20:20+struct.unpack_from("<I",data,12)[0]])
        sources.add(source)
        varieties.append({"name":name,"mesh":mesh,"density_per_100m2":density,"scale":scale,
                          "override_materials":[],"standin_slots":[v["name"] for v in doc["materials"]]})
    config={"schema":SCHEMA,"source_world":"/Game/Levels/Halo1/Solo/LPW/LPW","world":WORLD,
        "asset_folder":ASSETS,"chunk":965,"grid":{k:spec[k] for k in ("size","components","sections","quads","location","scale")},
        "section_bases":[[567,693],[630,693]],"varieties":varieties,"cull_cm":[4000,6000],
        "preserved_groundcover":279132,"serialized_instances":0,"rule":"grass",
        "filtered_foliage":filtered,
        "mask":{"file":raw.name,"sha256":digest(raw)},"texture":{"file":texture.name,"sha256":digest(texture)},
        "heights":{"file":heights.name,"sha256":digest(heights)},
        "sources":[{"path":str(p.resolve()),"sha256":digest(p)} for p in sorted(sources)],
        "mask_guard_m":clearance,"nonzero_vertices":int(eligible.sum()),
        "full_density_instances_per_m2":sum(v[2] for v in FAMILIES)/100,
        "runtime_cvars_to_measure":{"grass.MaxInstancesPerComponent":1024,"grass.GrassMap.UseRuntimeGeneration":0},
        "notes":["Saved density weights only; native camera-driven instances, no Lua tick.",
                 "Readback must run in a separate fresh editor process after build.",
                 "Keep native mesh packages excluded from this cook; stand-ins are editor-only."]}
    validate_config(config,output)
    dump(output/"pilot.json",config)
    print(json.dumps({"config":str(output/"pilot.json"),"nonzero_vertices":config["nonzero_vertices"],
                      "weighted_area_m2":float(eligible.sum()*(spec["scale"][0]/100)**2),
                      "old_meadow_removed":sum(r["removed"] for r in filter_receipt["groups"])}))


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",required=True)
    parser.add_argument("--land",required=True)
    parser.add_argument("--scenery",help="Frozen final tree/rock/recipe/hull directory; inputs are hash pinned")
    parser.add_argument("--base-pilot",help="Freeze a proven pilot's mask and add only the accepted native material")
    parser.add_argument("--material-folder",help="Independently verified owned Canyon native clone directory")
    args=parser.parse_args()
    if args.base_pilot or args.material_folder:
        if not (args.base_pilot and args.material_folder): parser.error("Both --base-pilot and --material-folder are required")
        prepare_material_variant(args.base_pilot,args.land,args.material_folder,args.out)
    else:
        prepare(args.out,args.land,args.scenery)

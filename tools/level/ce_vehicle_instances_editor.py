"""Make a CE vehicle's material instances, in the Unreal editor.

    set MJ_CE_INSTANCES=<name>.instances.json
    powershell -File tools/ue/editor_cmd.ps1 -Script ..\\..\\tools\\level\\ce_vehicle_instances_editor.py

tools/level/ce_vehicle_materials.py writes the file and runs this. Each entry
becomes a MaterialInstanceConstant of one of Scripts/build_ce_materials.py's
masters, with the textures, scalars and vectors a level's loader would have
set on a dynamic instance. A scalar or vector the master does not have is left
out, as a dynamic instance ignores it (ce_material_spec.py gives every object
section ObjectPage; the glass masters have none), and listed in <file>.dropped
for the read-back. A texture the master does not have stops the run, unless the
file says `"drop_textures": true` (machine_instances.py: a moving part's lit
master has no reflection cube, which the loader's dynamic instance ignored
too); then it is dropped the same way. The file's `overrides` go on whichever
masters have them.

The file's `standins` (clad_materials.py: the game's own Megascans textures a
cladding rock's material names) are made as never-cooked stand-ins where the
project has none: a 4x4 texture at the game's path, under /Game/Megascans
(DirectoriesToNeverCook), whose import the cooked instance keeps and the game
resolves to its own texture, as the baked foliage's game meshes are named.

The file's `label` ({"name", "chunk"}: machine_instances.py, an upgraded map's
machine parts) is a label of the folder's own, made here: not recursive, so
the chunk takes the instances and not their masters. Without it the folder is
under a map's own label (build_ce_level.py's), which is made not recursive.
"""
import json
import os

import unreal

mel = unreal.MaterialEditingLibrary
eal = unreal.EditorAssetLibrary
assets = unreal.AssetToolsHelpers.get_asset_tools()

spec = json.load(open(os.environ["MJ_CE_INSTANCES"], encoding="utf-8"))

# Instances the file no longer names would still cook.
folder = spec["folder"]
wanted = {e["package"] for e in spec["instances"]}
if eal.does_directory_exist(folder):
    for path in eal.list_assets(folder, recursive=True, include_folder=False):
        # ce_vehicle_sounds.py's waves share the folder and the chunk.
        if path.startswith(f"{folder}/Sounds/"):
            continue
        if path.split(".")[0] not in wanted and path.rsplit(".", 1)[-1] != (spec.get("label") or {}).get("name"):
            eal.delete_asset(path.split(".")[0])

def png4():
    """A 4x4 mid-grey PNG, written with the standard library alone."""
    import struct
    import zlib

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    rows = b"".join(b"\x00" + b"\x80\x80\x80\xff" * 4 for _ in range(4))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 4, 4, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def standin_texture(path):
    """A never-cooked stand-in for the game's texture at `path`, sampled as
    the game's is: a normal map (_N), a linear mask (ORHG and the like), or
    colour; none of them virtual (the masters sample plain textures)."""
    package = path.split(".")[0]
    folder, leaf = package.rsplit("/", 1)
    # A map's own texture (clad_materials.py: a Halo 1 map converted
    # elsewhere): only in a folder of stand-ins, each recorded with its
    # file's hash, which the cook leaves out (-NEVERCOOKDIR).
    on_map = package.startswith("/Game/MJOLNIR/Maps/")
    disk = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir()),
                        *folder[len("/Game/"):].split("/"))
    record = os.path.join(disk, "MJOLNIR_STANDINS.json")
    if eal.does_asset_exist(package):
        if on_map and leaf not in (json.load(open(record, encoding="utf-8")) if os.path.exists(record) else {}):
            raise RuntimeError(f"{package} is a real texture of the project's, not a stand-in: plan it as one")
        return
    if on_map:
        others = [a for a in (eal.list_assets(folder, recursive=False, include_folder=False)
                              if eal.does_directory_exist(folder) else [])]
        known = json.load(open(record, encoding="utf-8")) if os.path.exists(record) else {}
        strange = [a for a in others if a.split(".")[0].rsplit("/", 1)[1] not in known]
        if strange:
            raise RuntimeError(f"stand-in {package} would share {folder} with real packages {strange}")
    elif not package.startswith("/Game/Megascans/"):
        raise RuntimeError(f"stand-in outside /Game/Megascans and the maps' stand-in folders: {package}")
    import tempfile
    src = os.path.join(tempfile.gettempdir(), f"{leaf}.png")
    open(src, "wb").write(png4())
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", src)
    task.set_editor_property("destination_path", folder)
    task.set_editor_property("destination_name", leaf)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", False)
    assets.import_asset_tasks([task])
    tex = unreal.load_asset(package)
    if tex is None:
        raise RuntimeError(f"could not make the stand-in {package}")
    tail = leaf.rsplit("_", 1)[-1].upper()
    if on_map:
        # As build_ce_materials.py's ce_texture_settings reads every CE
        # bitmap, so the master's sampler takes it as it takes the real one.
        tex.set_editor_property("srgb", False)
        tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP)
        tex.set_editor_property("never_stream", True)
    elif tail == "N":
        tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
        tex.set_editor_property("srgb", False)
    elif tail != "D":
        tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_MASKS)
        tex.set_editor_property("srgb", False)
    tex.set_editor_property("virtual_texture_streaming", False)
    if not eal.save_loaded_asset(tex):
        raise RuntimeError(f"could not save the stand-in {package}")
    if on_map:
        import hashlib
        known = json.load(open(record, encoding="utf-8")) if os.path.exists(record) else {}
        known[leaf] = hashlib.sha1(open(os.path.join(disk, leaf + ".uasset"), "rb").read()).hexdigest()
        json.dump(known, open(record, "w", encoding="utf-8"), indent=1, sort_keys=True)
    os.remove(src)
    unreal.log(f"MJOLNIR stand-in texture {package}")


if spec.get("standins"):
    unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(
        sorted({t.split(".")[0].rsplit("/", 1)[0] for t in spec["standins"]}), True)
    for path in spec["standins"]:
        standin_texture(path)

dropped = {}
for entry in spec["instances"]:
    package = entry["package"]
    leaf = package.rsplit("/", 1)[1]
    parent = unreal.load_asset(entry["parent"])
    if parent is None:
        raise RuntimeError(f"no master {entry['parent']}")
    mi = unreal.load_asset(package)
    if mi is None:
        mi = assets.create_asset(leaf, folder, unreal.MaterialInstanceConstant,
                                 unreal.MaterialInstanceConstantFactoryNew())
    if mi is None:
        raise RuntimeError(f"could not create {package}")
    mel.set_material_instance_parent(mi, parent)
    mel.clear_all_material_instance_parameters(mi)
    have = {str(n) for n in mel.get_scalar_parameter_names(parent)}
    have_vector = {str(n) for n in mel.get_vector_parameter_names(parent)}
    have_texture = {str(n) for n in mel.get_texture_parameter_names(parent)}
    dropped[package] = [n for n in list(entry["scalars"]) + list(entry["vectors"]) if n not in have | have_vector]
    if spec.get("drop_textures"):
        dropped[package] += [n for n in entry["textures"] if n not in have_texture]
    for name, value in entry["scalars"].items():
        if name in have:
            mel.set_material_instance_scalar_parameter_value(mi, name, float(value))
    for name, value in spec.get("overrides", {}).items():
        if name in have:
            mel.set_material_instance_scalar_parameter_value(mi, name, float(value))
    for name, value in entry["vectors"].items():
        if name in have_vector:
            mel.set_material_instance_vector_parameter_value(mi, name, unreal.LinearColor(*value))
    for name, path in entry["textures"].items():
        if name not in have_texture:
            if spec.get("drop_textures"):
                continue
            raise RuntimeError(f"{leaf}: {entry['parent']} has no texture {name}")
        texture = unreal.load_asset(path)
        if texture is None:
            raise RuntimeError(f"{leaf}: no texture {path}")
        mel.set_material_instance_texture_parameter_value(mi, name, texture)
    mel.update_material_instance(mi)
    if not eal.save_loaded_asset(mi):
        raise RuntimeError(f"could not save {package}")
    unreal.log(f"MJOLNIR instance {leaf}: {len(entry['scalars'])} scalar(s), {len(entry['vectors'])} vector(s), "
               f"{len(entry['textures'])} texture(s), left out {dropped[package]}")

# build_ce_level.py's label is recursive, which for textures alone costs
# nothing. An instance's references reach its master and the master's default
# textures, and the chunk took copies of them, shaders and all, to shadow the
# runtime pack's. The label's folder scan already holds everything here.
own = spec.get("label")
if own:
    label = unreal.load_asset(f"{folder}/{own['name']}")
    if label is None:
        label = assets.create_asset(own["name"], folder, unreal.PrimaryAssetLabel, unreal.DataAssetFactory())
    rules = label.get_editor_property("rules")
    rules.set_editor_property("chunk_id", int(own["chunk"]))
    rules.set_editor_property("priority", 10)
    rules.set_editor_property("cook_rule", unreal.PrimaryAssetCookRule.ALWAYS_COOK)
    label.set_editor_property("label_assets_in_my_directory", True)
else:
    root = folder.rsplit("/", 1)[0]
    label = unreal.load_asset(f"{root}/PAL_{root.rsplit('/', 1)[1]}")
    rules = label.get_editor_property("rules")
rules.set_editor_property("apply_recursively", False)
label.set_editor_property("rules", rules)
eal.save_loaded_asset(label)

json.dump(dropped, open(os.environ["MJ_CE_INSTANCES"] + ".dropped", "w", encoding="utf-8"), indent=1)
unreal.log(f"MJOLNIR vehicle instances: {len(spec['instances'])} under {folder}")

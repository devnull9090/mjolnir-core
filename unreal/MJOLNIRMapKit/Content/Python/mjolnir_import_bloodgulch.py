"""Build the empty B40 canvas world, then import the halo2ue Bloodgulch terrain
mesh beside it so the cook carries the mesh asset into the same container.

Run headless (from the MapKit project):

    UnrealEditor-Cmd.exe Meteorite.uproject -run=pythonscript \
        -script="Content/Python/mjolnir_import_bloodgulch.py" -stdout -unattended -nosplash

Environment:
    MJOLNIR_LEVEL_PACKAGE   canvas world package, default /Game/Levels/Halo1/Solo/B40/B40
    MJOLNIR_CONTENT         passed through to the world generator, default none
    MJOLNIR_BLOODGULCH_GLTF path to staging/bloodgulch/bsp/bsp_0.gltf

The mesh lands under the canvas level's folder, which the PrimaryAssetLabel
there routes into chunk 990, so `package.ps1` stages world and mesh together.
Whether the game deserialises a stock-cooked UStaticMesh is the open question
this cook exists to answer; the world itself is known to load.

The imported mesh is also **placed in the canvas level** as a StaticMeshActor.
That is the point of this step: a package nothing references is cooked into
the container and then never loaded, which is why earlier builds showed an
empty void -- the canvas world had five exports and no imported packages at
all. Placing the actor makes the world import the mesh package, so the engine
loads it with the level instead of on a runtime request. StaticMeshActor is
the one actor class a stock UE 5.5 cook is known to survive in 343's engine
build (PlayerStart and the light classes hit a serial-size mismatch; see
mjolnir_build_world.py), so lighting still comes from the runtime loader.

    MJOLNIR_BLOODGULCH_OFFSET  actor location in UE cm; default is the
                               collision transplant's offset in UE axes
"""
import os
import sys

import unreal

os.environ.setdefault("MJOLNIR_LEVEL_PACKAGE", "/Game/Levels/Halo1/Solo/B40/B40")
os.environ.setdefault("MJOLNIR_CONTENT", "none")

LEVEL_PACKAGE = os.environ["MJOLNIR_LEVEL_PACKAGE"]
LEVEL_DIR = LEVEL_PACKAGE.rsplit("/", 1)[0]
MESH_DIR = LEVEL_DIR + "/Halo/Bloodgulch"
GLTF = os.environ.get(
    "MJOLNIR_BLOODGULCH_GLTF",
    r"C:\Users\will\prj\HalcyonRing\staging\bloodgulch\bsp\bsp_0.gltf",
)


# halo2ue exports the level so an Unreal glTF import already lands the geometry
# at Halo (x, -y, z) x 304.8 cm, so the only transform left is the offset the
# collision transplant used to move Blood Gulch into B40's world box:
# (-35.4, 151.17, 44.0) world units, which is (dx, -dy, dz) x 304.8 in UE.
OFFSET = unreal.Vector(*(
    float(v) for v in os.environ.get(
        "MJOLNIR_BLOODGULCH_OFFSET", "-10789.9,-46076.6,13411.2").split(",")))


def log(msg):
    unreal.log("[MJOLNIR Bloodgulch] " + msg)


def build_world():
    # The generator lives beside this file; the editor puts Content/Python on
    # sys.path, but be explicit so a commandlet run finds it too.
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import mjolnir_build_world as bw  # noqa: E402

    bw.main()
    log("canvas world built at " + LEVEL_PACKAGE)


def import_terrain():
    if not os.path.exists(GLTF):
        raise RuntimeError("terrain glTF not found: " + GLTF)
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", GLTF)
    task.set_editor_property("destination_path", MESH_DIR)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", True)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    imported = list(task.get_editor_property("imported_object_paths") or [])
    log("imported %d object(s) from %s" % (len(imported), os.path.basename(GLTF)))
    meshes = []
    for path in imported:
        asset = unreal.EditorAssetLibrary.load_asset(path)
        kind = type(asset).__name__ if asset else "?"
        log("  %s  (%s)" % (path, kind))
        if isinstance(asset, unreal.StaticMesh):
            meshes.append(path)
    if not meshes:
        raise RuntimeError("the glTF import produced no StaticMesh")
    # Write the mesh object paths where the level file author can pick them up.
    out = os.path.join(unreal.Paths.project_saved_dir(), "mjolnir_bloodgulch_meshes.txt")
    with open(out, "w") as f:
        for m in meshes:
            f.write(m + "\n")
    log("mesh list written to " + out)
    return meshes


def place_terrain(mesh_paths):
    """Put the imported mesh into the canvas level as a StaticMeshActor.

    Without this the mesh package is cooked but unreferenced, so nothing ever
    loads it. Movable mobility keeps the actor out of the static-lighting path,
    so the level still needs no Lightmass bake and no _BuiltData package.
    """
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not les.load_level(LEVEL_PACKAGE):
        raise RuntimeError("could not load canvas level " + LEVEL_PACKAGE)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    placed = 0
    for path in mesh_paths:
        mesh = unreal.EditorAssetLibrary.load_asset(path)
        if not isinstance(mesh, unreal.StaticMesh):
            continue
        name = path.rsplit("/", 1)[-1].split(".")[-1]
        actor = eas.spawn_actor_from_class(
            unreal.StaticMeshActor, OFFSET, unreal.Rotator(0.0, 0.0, 0.0))
        actor.set_actor_label("MJOLNIR_Bloodgulch_" + name)
        comp = actor.static_mesh_component
        comp.set_editor_property("static_mesh", mesh)
        comp.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
        placed += 1
        log("placed %s at (%.1f, %.1f, %.1f)" % (name, OFFSET.x, OFFSET.y, OFFSET.z))
    if not placed:
        raise RuntimeError("no StaticMesh to place")
    if not les.save_current_level():
        raise RuntimeError("failed to save " + LEVEL_PACKAGE)
    log("saved %s with %d terrain actor(s)" % (LEVEL_PACKAGE, placed))


def label_mesh_dir():
    """The canvas label's directory rule stops at its own folder, so the mesh
    folder gets a label of its own routing it into the same chunk."""
    name = "PAL_MJOLNIRWORLD_BLOODGULCH"
    path = MESH_DIR + "/" + name
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        log("mesh chunk label already exists: " + path)
        return
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    label = tools.create_asset(name, MESH_DIR, unreal.PrimaryAssetLabel, unreal.DataAssetFactory())
    if not label:
        raise RuntimeError("could not create PrimaryAssetLabel at " + path)
    rules = unreal.PrimaryAssetRules()
    rules.set_editor_property("chunk_id", 990)
    rules.set_editor_property("cook_rule", unreal.PrimaryAssetCookRule.ALWAYS_COOK)
    label.set_editor_property("rules", rules)
    label.set_editor_property("label_assets_in_my_directory", True)
    unreal.EditorAssetLibrary.save_asset(path)
    log("created mesh chunk label " + path)


def main():
    build_world()
    meshes = import_terrain()
    label_mesh_dir()
    place_terrain(meshes)
    unreal.EditorAssetLibrary.save_directory(MESH_DIR, only_if_is_dirty=False, recursive=True)
    log("done")


if __name__ == "__main__":
    main()

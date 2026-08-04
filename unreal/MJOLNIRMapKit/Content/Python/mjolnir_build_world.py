"""Build the MJOLNIR test world: a lit plane with a player spawn and marker examples.

Run headless:
    UnrealEditor-Cmd.exe <Meteorite.uproject> -run=pythonscript
        -script="<this file>" -stdout -unattended

or in the editor: Tools > Execute Python Script.

Why this world is shaped the way it is
--------------------------------------
* The level is saved at /Game/Levels/Test/Testing_Shooting_Range/
  testing_shooting_range because that exact package path is pre-registered in
  the game's DT_Test_Scenarios table under the scenario name
  `testing_shooting_range`. The game validates that the world package exists
  before traveling, so the path has to match to the character.

* Every asset referenced here ships inside the game's own containers
  (/Engine/BasicShapes/*, engine light classes). Referencing only shipped
  assets means the game already has working shaders for everything, whatever
  happens with our own cooked copies.

* All lights are MOVABLE so the level needs no Lightmass bake and cooks
  standalone with no _BuiltData dependencies to worry about.

* Spawn conventions for modders (see README.md):
    - The player spawn is a stock PlayerStart.
    - Everything else is a TargetPoint carrying actor tags of the form
      MJOLNIR.<Kind>.<Detail> (e.g. MJOLNIR.VehicleSpawn.Warthog). The game's
      Blam classes do not exist in stock UE, so maps mark intent with tags and
      a runtime mod does the spawning.
"""

import os

import unreal

# Override with MJOLNIR_LEVEL_PACKAGE to build the world at a different path.
# Only the 13 shipped campaign scenarios have Blam scenario tags, and the
# campaign flow validates against those tags -- so overriding a campaign world
# (e.g. /Game/Levels/Halo1/Solo/A15/A15) is what actually launches today.
LEVEL_PACKAGE = os.environ.get(
    "MJOLNIR_LEVEL_PACKAGE",
    "/Game/Levels/Test/Testing_Shooting_Range/testing_shooting_range")

# Which content to place, as a comma-separated list in MJOLNIR_CONTENT.
#
# This exists because 343's engine build deserializes some cooked component
# classes incompatibly with stock UE 5.5 (CapsuleComponent and
# DirectionalLightComponent both die with "Serial size mismatch" during load;
# see docs/multiplayer_investigation_notes.md). Which classes are affected has
# to be established one at a time, so each piece of content is switchable and a
# cook can carry exactly one component class under test.
#
#   MJOLNIR_CONTENT=none                  bare level: no actors at all
#   MJOLNIR_CONTENT=floor                 StaticMeshActor only
#   MJOLNIR_CONTENT=floor,lights,markers  everything except the PlayerStart
#
ALL_PARTS = ("floor", "playerstart", "lights", "markers")
_requested = os.environ.get("MJOLNIR_CONTENT", ",".join(ALL_PARTS)).strip().lower()
if _requested in ("none", ""):
    PARTS = frozenset()
else:
    PARTS = frozenset(p.strip() for p in _requested.split(",") if p.strip())
    unknown = PARTS - frozenset(ALL_PARTS)
    if unknown:
        raise RuntimeError(
            "unknown MJOLNIR_CONTENT parts: %s (known: %s)"
            % (", ".join(sorted(unknown)), ", ".join(ALL_PARTS)))

# Where the floor sits and how big it is, in world units (1 UU = 1 cm).
#
# When this world overrides a campaign scenario, the Blam scenario data -- not
# our level -- decides where the player materialises, and that spot is wherever
# the real mission began. A floor at the origin is then simply somewhere else.
# MJOLNIR_FLOOR_ORIGIN re-centres the pad on the measured spawn point.
FLOOR_ORIGIN = unreal.Vector(*(
    float(v) for v in os.environ.get("MJOLNIR_FLOOR_ORIGIN", "0,0,0").split(",")))
FLOOR_EXTENT_M = float(os.environ.get("MJOLNIR_FLOOR_EXTENT_M", "50"))

# Everything under /Game/Levels/Test (this map and whatever it references) is
# assigned to this content chunk, so packaging can install a container holding
# only the custom world instead of the whole cooked project.
CONTENT_CHUNK = 990
LABEL_DIR = LEVEL_PACKAGE.rsplit("/", 1)[0]
LABEL_NAME = "PAL_MJOLNIRWORLD"

# The floor is a scaled /Engine/BasicShapes/Cube rather than a Plane: the cube
# carries simple box collision, so it is solid from above and cannot be fallen
# through, and it reads as a slab from the side. The base cube is 100 cm and
# pivots at its centre, so a scale of N gives an N-metre edge and the walking
# surface sits half the thickness above the actor.
FLOOR_THICKNESS_SCALE = 1.0
FLOOR_SCALE = unreal.Vector(FLOOR_EXTENT_M, FLOOR_EXTENT_M, FLOOR_THICKNESS_SCALE)
FLOOR_LOCATION = unreal.Vector(
    FLOOR_ORIGIN.x, FLOOR_ORIGIN.y, FLOOR_ORIGIN.z - 50.0 * FLOOR_THICKNESS_SCALE)

MARKERS = [
    ("MJOLNIR.VehicleSpawn.Warthog", unreal.Vector(800.0, 0.0, 20.0)),
    ("MJOLNIR.WeaponSpawn.AssaultRifle", unreal.Vector(0.0, 400.0, 20.0)),
    ("MJOLNIR.ObjectiveMarker.Example", unreal.Vector(-800.0, 0.0, 20.0)),
]


def log(msg):
    unreal.log("[MJOLNIR MapKit] " + msg)


def spawn(actor_class, location, label, rotation=None):
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actor = eas.spawn_actor_from_class(
        actor_class, location, rotation or unreal.Rotator(0.0, 0.0, 0.0))
    actor.set_actor_label(label)
    return actor


def ensure_chunk_label():
    """Create the PrimaryAssetLabel that routes this content into chunk 990."""
    label_path = LABEL_DIR + "/" + LABEL_NAME
    if unreal.EditorAssetLibrary.does_asset_exist(label_path):
        log("chunk label already exists: " + label_path)
        return
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    label = tools.create_asset(
        LABEL_NAME, LABEL_DIR, unreal.PrimaryAssetLabel, unreal.DataAssetFactory())
    if not label:
        raise RuntimeError("could not create PrimaryAssetLabel at " + label_path)
    rules = unreal.PrimaryAssetRules()
    rules.set_editor_property("chunk_id", CONTENT_CHUNK)
    rules.set_editor_property("cook_rule", unreal.PrimaryAssetCookRule.ALWAYS_COOK)
    label.set_editor_property("rules", rules)
    label.set_editor_property("label_assets_in_my_directory", True)
    unreal.EditorAssetLibrary.save_asset(label_path)
    log("created chunk label %s (chunk %d)" % (label_path, CONTENT_CHUNK))


def main():
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)

    ensure_chunk_label()

    # Regeneration is destructive on purpose: the template is the script, and
    # the .umap is build output. Park on a scratch level so the target can be
    # deleted while not loaded.
    scratch = "/Game/__MJOLNIR_Scratch"
    if unreal.EditorAssetLibrary.does_asset_exist(LEVEL_PACKAGE):
        les.new_level(scratch)
        if not unreal.EditorAssetLibrary.delete_asset(LEVEL_PACKAGE):
            raise RuntimeError("could not delete existing " + LEVEL_PACKAGE)
        log("deleted existing level for clean regeneration")

    if not les.new_level(LEVEL_PACKAGE):
        raise RuntimeError("could not create level at " + LEVEL_PACKAGE)
    log("created level " + LEVEL_PACKAGE)

    log("content: " + (", ".join(sorted(PARTS)) if PARTS else "none (bare level)"))

    # A bare level is the control experiment for the engine-fork serialization
    # wall: World, Level, Model and WorldSettings exports only. It loads
    # (verified 2026-08-02), which is what proved cooked worlds are viable at
    # all -- everything below is the question of how much content can ride
    # along inside the cook rather than being spawned at runtime.

    # --- floor -----------------------------------------------------------
    if "floor" in PARTS:
        cube = unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Cube")
        if not cube:
            raise RuntimeError("/Engine/BasicShapes/Cube not found")
        floor = spawn(unreal.StaticMeshActor, FLOOR_LOCATION, "MJOLNIR_Floor")
        mesh_comp = floor.static_mesh_component
        mesh_comp.set_editor_property("static_mesh", cube)
        # Movable keeps the slab out of any static-lighting path, so the level
        # needs no Lightmass bake and no _BuiltData package alongside it.
        mesh_comp.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
        floor.set_actor_scale3d(FLOOR_SCALE)
        log("floor: %.0f m pad, surface at z=%.0f" % (FLOOR_EXTENT_M, FLOOR_ORIGIN.z))

    # --- player spawn ----------------------------------------------------
    #
    # PlayerStart carries a UCapsuleComponent, and this game's engine build
    # serializes that class differently from stock UE 5.5: loading a
    # stock-cooked one dies with
    #   "CapsuleComponent ... Serial size mismatch: Expected read size 34,
    #    Actual read size 14"
    # (verified 2026-08-02, fatal in AsyncLoading2). Leave "playerstart" out of
    # MJOLNIR_CONTENT when overriding a campaign scenario -- there the Blam
    # scenario data places the player and a PlayerStart is dead weight anyway.
    if "playerstart" in PARTS:
        spawn(unreal.PlayerStart,
              unreal.Vector(FLOOR_ORIGIN.x, FLOOR_ORIGIN.y, FLOOR_ORIGIN.z + 150.0),
              "MJOLNIR_PlayerStart")

    # --- light and sky (all movable: no bake required) --------------------
    #
    # DirectionalLightComponent hits the same serialization wall as the capsule
    # ("Expected read size 67, Actual read size 21"), so lighting is the other
    # thing a cook may not be able to carry. Spawning lights at runtime from
    # UE4SS goes through the game's own class layouts and sidesteps it.
    if "lights" in PARTS:
        sun = spawn(unreal.DirectionalLight, unreal.Vector(0, 0, 5000), "MJOLNIR_Sun",
                    unreal.Rotator(-50.0, 30.0, 0.0))
        sun.light_component.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
        sun.light_component.set_editor_property("intensity", 8.0)

        sky_light = spawn(unreal.SkyLight, unreal.Vector(0, 0, 5000), "MJOLNIR_SkyLight")
        sky_light.light_component.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
        sky_light.light_component.set_editor_property("real_time_capture", True)

        spawn(unreal.SkyAtmosphere, unreal.Vector(0, 0, 0), "MJOLNIR_SkyAtmosphere")
        spawn(unreal.ExponentialHeightFog, unreal.Vector(0, 0, 0), "MJOLNIR_Fog")

    # --- modder convention markers ----------------------------------------
    if "markers" in PARTS:
        for tag, location in MARKERS:
            marker = spawn(unreal.TargetPoint, location, tag)
            marker.tags = [unreal.Name(tag)]

    # --- world settings ----------------------------------------------------
    try:
        world = unreal.UnrealEditorSubsystem().get_editor_world()
        settings = world.get_world_settings()
        settings.set_editor_property("kill_z", -100000.0)
    except Exception as exc:  # cosmetic; a probe map works without it
        log("could not set KillZ: " + str(exc))

    if not les.save_current_level():
        raise RuntimeError("failed to save " + LEVEL_PACKAGE)
    log("saved " + LEVEL_PACKAGE)

    if unreal.EditorAssetLibrary.does_asset_exist(scratch):
        unreal.EditorAssetLibrary.delete_asset(scratch)
    log("world built at %s with content: %s"
        % (LEVEL_PACKAGE, ", ".join(sorted(PARTS)) if PARTS else "none"))


if __name__ == "__main__":
    main()

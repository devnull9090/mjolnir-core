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

import unreal

LEVEL_PACKAGE = "/Game/Levels/Test/Testing_Shooting_Range/testing_shooting_range"

# 1 UU = 1 cm. A 50 x 50 m pad is plenty to land on and look around.
FLOOR_SCALE = unreal.Vector(50.0, 50.0, 1.0)

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


def main():
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)

    if not les.new_level(LEVEL_PACKAGE):
        raise RuntimeError("could not create level at " + LEVEL_PACKAGE)
    log("created level " + LEVEL_PACKAGE)

    # --- floor -----------------------------------------------------------
    plane = unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Plane")
    if not plane:
        raise RuntimeError("/Engine/BasicShapes/Plane not found")
    floor = spawn(unreal.StaticMeshActor, unreal.Vector(0, 0, 0), "MJOLNIR_Floor")
    mesh_comp = floor.static_mesh_component
    mesh_comp.set_editor_property("static_mesh", plane)
    floor.set_actor_scale3d(FLOOR_SCALE)

    # --- player spawn ----------------------------------------------------
    spawn(unreal.PlayerStart, unreal.Vector(0, 0, 150), "MJOLNIR_PlayerStart")

    # --- light and sky (all movable: no bake required) --------------------
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
    log("world built: floor, PlayerStart, movable lighting, %d markers" % len(MARKERS))


if __name__ == "__main__":
    main()

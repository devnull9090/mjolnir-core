# MJOLNIR MapKit

A template Unreal Engine project for building **custom worlds that Halo Campaign
Evolved can load** through its own (hidden but shipped) debug map menu.

**Status: experimental.** The launch plumbing is verified — the game's
`SetAndBeginCampaign` flow validates that a world package exists, refuses
gracefully when it doesn't, and travels when it does (see
[`docs/multiplayer_investigation_notes.md`](../../docs/multiplayer_investigation_notes.md)).
What is *not* yet verified is the first custom world actually loading; this kit
exists to run that experiment and to become the template modders start from.

## Requirements

| What | Why |
|---|---|
| **Unreal Engine 5.5.x** (Epic Games Launcher) | The game is UE 5.5. Cooked package formats are engine-version locked; 5.6+ output will not load. |
| Halo Campaign Evolved (Steam) | The target. |
| The MJOLNIRMultiplayer UE4SS mod | `mjolnir_mission <scenario>` launches the map. The game's own debug menu (`mjolnir_debug_ui`) works too. |

## Quickstart

```powershell
cd unreal\MJOLNIRMapKit\scripts
.\generate_world.ps1        # builds the template level headlessly
.\package.ps1 -Install      # cook, stage, install into the game's Paks
```

Then launch the game and run (UE4SS console, or the game console with
MJOLNIRConsoleEnabler):

```
mjolnir_mission testing_shooting_range
```

`false`/"rejected" means the game did not see the world package. "accepted"
plus a load means you are standing on the plane.

To remove: delete the three `pakchunk990-MJOLNIRWORLD-*` files from
`<game>\Meteorite\Content\Paks`. Nothing shipped is modified.

## Where a custom world can live

The game launches scenarios by name, and the name→world mapping ships in
`DT_Test_Scenarios`. These 19 paths are pre-registered and their worlds were
stripped from the retail cook — they are free slots a mod container can fill.
The world's package path (folder + asset name) must match **exactly**.

| Scenario name (`mjolnir_mission <this>`) | Required world package |
|---|---|
| `testing_shooting_range` | `/Game/Levels/Test/Testing_Shooting_Range/testing_shooting_range` |
| `testing_combat_weapons` | `/Game/Levels/Test/Testing_Combat_Weapons/Testing_Combat_Weapons` |
| `testing_faction_fight` | `/Game/Levels/Test/Testing_Faction_Fight/Testing_Faction_Fight` |
| `testing_vehicle_obstacle` | `/Game/Levels/Test/Testing_Vehicle_Obstacle/Testing_Vehicle_Obstacle` |
| `testing_grunt` | `/Game/Levels/Test/Testing_Grunt/Testing_Grunt` |
| `testing_jackal` | `/Game/Levels/Test/Testing_Jackal/Testing_Jackal` |
| `testing_elite` | `/Game/Levels/Test/Testing_Elite/Testing_Elite` |
| `testing_hunter` | `/Game/Levels/Test/Testing_Hunter/Testing_Hunter` |
| `testing_marine` | `/Game/Levels/Test/Testing_Marine/Testing_Marine` |
| `testing_sentinel` | `/Game/Levels/Test/Testing_Sentinel/Testing_Sentinel` |
| `testing_infector` | `/Game/Levels/Test/Testing_Infector/Testing_Infector` |
| `testing_carrier` | `/Game/Levels/Test/Testing_Carrier/Testing_Carrier` |
| `testing_combatform` | `/Game/Levels/Test/Testing_CombatForm/Testing_CombatForm` |
| `testing_puretank` | `/Game/Levels/Test/Testing_PureTank/Testing_PureTank` |
| `testing_remix` | `/Game/Levels/Test/Testing_Remix/Testing_Remix` |
| `testing_chatter` | `/Game/Levels/Test/Testing_Chatter/Testing_Chatter` |
| `testing_clouds` | `/Game/Levels/Test/Testing_Clouds/Testing_Clouds` |
| `testing_cinematics` | `/Game/Levels/Test/Testing_Cinematics/Testing_Cinematics` |
| `d40_warthog_testkit` | `/Game/Levels/Lookdev/E10_Kit/D40_Warthog_Testkit` |

(`testing_hlod` points into a developer folder and is skipped here.)

## The template world

[`Content/Python/mjolnir_build_world.py`](Content/Python/mjolnir_build_world.py)
builds it; open the level in the editor afterwards to extend it. It contains:

- a 50×50 m floor (engine `Plane` mesh),
- one **`PlayerStart`** — the player spawn,
- movable sun + skylight + atmosphere (no lighting build needed),
- example **marker actors** for the spawn conventions below.

### Spawn conventions for modders

The game's own actor classes (bipeds, vehicles, weapons) do not exist in stock
Unreal, so a map cannot place a Warthog directly. Instead the map declares
*intent* with plain `TargetPoint` actors carrying actor tags, and a runtime
mod (UE4SS Lua) reads the tags and spawns the real thing:

| Actor tag | Meaning |
|---|---|
| `MJOLNIR.VehicleSpawn.<Vehicle>` | vehicle spawn point, e.g. `...Warthog` |
| `MJOLNIR.WeaponSpawn.<Weapon>` | weapon pickup point |
| `MJOLNIR.ObjectiveMarker.<Name>` | game-mode objective location (flag stand, hill, ...) |

The tag reader/spawner mod is future work; the convention is established now
so maps built today keep working.

## Rules that keep a map loadable

1. **Reference only assets the game ships.** `/Engine/BasicShapes/*`,
   `/Engine/EngineMaterials/WorldGridMaterial`, and the engine light/actor
   classes are all in the game's containers — the game already has shaders
   for them. Anything else you add must cook into your container, and:
2. **Leave `bShareMaterialShaderCode=False` alone** (set in
   `Config/DefaultGame.ini`). It inlines shader bytecode into material
   packages. The game never opens a dropped-in container's shader library, so
   shared shader code renders broken or crashes.
3. **Cook with UE 5.5.x only.**
4. **No World Partition** for test maps (the generator creates a classic
   persistent level). The shipped campaign uses WP, but every stripped test
   world was a plain level and WP adds generated-cell complexity for nothing
   at this size.

## Known unknowns (the experiment this kit runs)

- The 13 shipped campaign worlds all have generated **Blam scenario/BSP tags**;
  the stripped test worlds have none in the retail build. If the simulation
  requires them, the world may load and then fail to start — that outcome
  would itself be the next lead (generate minimal scenario tags; see
  [`docs/tag_data_pipeline.md`](../../docs/tag_data_pipeline.md)).
- The game runs a **modified 5.5**. If 343's engine changes touched core class
  serialization, a stock-5.5 cook may fail to load. Fallback documented in the
  investigation notes: re-key the shipped `SeamlessTravelTEst` world into a
  free scenario slot instead.
- Player spawning: campaign missions spawn via Blam scenario data, but plain
  `PlayerStart` is the best first bet for the plain-UE test worlds.

## How the container works

`package.ps1` stages the project with IoStore and renames the result to
`pakchunk990-MJOLNIRWORLD-Windows_P`. The `_P` patch suffix makes it win chunk
lookups; the stub `.pak` beside it is what makes the game discover it (both
verified against this game — [`docs/iostore_packaging.md`](../../docs/iostore_packaging.md)).
The container carries its own `ContainerHeader`, so the new package is
registered in the game's package store when it mounts.

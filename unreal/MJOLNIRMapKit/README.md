# MJOLNIR MapKit

A template Unreal Engine project for building **custom worlds that Halo Campaign
Evolved can load** through its own (hidden but shipped) debug map menu.

**Status: it works.** A custom world loads, renders and is walkable — verified
in-game on CU3, 2026-08-03. The recipe is not the obvious one, because the game
will load our *world* but refuses to deserialize our *actors*:

> **Cook the world empty. Build the map at runtime.**

The cooked package carries the level and nothing else; the
[`MJOLNIRWorldBuilder`](../../mods/MJOLNIRWorldBuilder) UE4SS mod spawns the
floor, sun and sky in-process the moment the world loads. Runtime spawning uses
the game's own class layouts, so it sidesteps the serialization wall entirely
(see [Rules that keep a map loadable](#rules-that-keep-a-map-loadable)).

## Requirements

| What | Why |
|---|---|
| **Unreal Engine 5.5.x** (Epic Games Launcher) | The game is UE 5.5. Cooked package formats are engine-version locked; 5.6+ output will not load. |
| Halo Campaign Evolved (Steam) | The target. |
| The MJOLNIRMultiplayer UE4SS mod | `mjolnir_mission <scenario>` launches the map. The game's own debug menu (`mjolnir_debug_ui`) works too. |
| The MJOLNIRWorldBuilder UE4SS mod | Furnishes the world once it loads. Without it a custom world is an empty void. |

## Quickstart

Override a campaign scenario's world — today that is the only route that
launches, because scenario *names* are gated by Blam tags (see below).

```powershell
cd unreal\MJOLNIRMapKit\scripts
$env:MJOLNIR_CONTENT = "none"        # empty world: actors come from the runtime mod
.\generate_world.ps1 -LevelPackage "/Game/Levels/Halo1/Solo/A15/A15"
.\package.ps1 -LevelPackage "/Game/Levels/Halo1/Solo/A15/A15" -Install
```

Then launch the game, **clear the title screen**, and run:

```
mjolnir_mission A15
```

A15's opening prompt is the brightness-calibration step — press `E` to proceed,
or the screen stays black and looks like a failure that it isn't.

The world builder fires automatically on load. To drive it by hand:

```
mjolnir_world_probe          what is actually in the loaded world
mjolnir_world_build [size_m] lighting + a floor under the player
```

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

## What the runs established

**A custom cooked world loads, and the mission runs on it** (2026-08-02). An empty world
installed over A15's package produced a running A15 mission — HUD, objective prompts, a
possessed pawn — with reflection confirming the loaded world was ours. Cooking in stock UE 5.5
is viable.

**It renders, and you can walk on it** (2026-08-03). With the world builder mod supplying a
floor, a directional light, a sky atmosphere and a sky light, the pad draws, the sky draws, and
the player walks across it while A15's Blam entities go about their business on top.

### Cooked actor components are binary-incompatible — all of them, one cause

Three different component classes, three different-looking deaths during load:

```text
CapsuleComponent ...          Serial size mismatch: Expected read size 34, Actual read size 14
DirectionalLightComponent ... Serial size mismatch: Expected read size 67, Actual read size 21
StaticMeshComponent ...       Bad export index 201463809/7
```

One cause: **UE5 cooks properties *unversioned*** — no names on the wire, just a bitmask of
which properties differ from defaults, read back in class-layout order. 343's build has its own
layouts for these classes, so the reader walks off the end of the stream and either miscounts
bytes or reads a garbage object index. Nothing about the *world* is wrong; the actors inside it
are being read with the wrong ruler.

> **Ship the world empty (`MJOLNIR_CONTENT=none`); build the map at runtime.**

**The open lead:** cook with *tagged* properties instead, so each property carries its name and
type and the game's loader can skip what it does not recognise.
`package.ps1 -TaggedProperties` does this. It cannot be a project setting — with
`CanUseUnversionedPropertySerialization=False` in `DefaultEngine.ini` the editor asserts at
startup, because the same flag gates *reading* unversioned data and the editor's own caches are
full of it — so it is passed to the cook process alone. **Untested against the game.** If it
works, modders get to author real geometry in the editor instead of scripting it.

### Runtime spawning has one sharp edge

`AStaticMeshActor`'s component ships with **`Mobility = Static`**, and `SetStaticMesh` silently
refuses to do anything on a registered static component — it logs "not movable" and returns. The
result is a live actor with no geometry, which from the outside is indistinguishable from a
rendering bug. Set `Mobility = 2` (Movable) *first*:

```lua
comp.Mobility = 2
comp:SetStaticMesh(mesh)
```

Then read `comp.StaticMesh` back to confirm. (`GetStaticMesh()` is not callable through UE4SS
reflection here; the property is.) The same ordering applies to spawned lights.

### The Blam simulation brings its own collision

In an empty custom world overriding A15, the pawn does **not** fall — it settles at `z = 2` and
walks around on collision that has no Unreal geometry behind it at all. The `a15` scenario tag's
BSP collision is still live. So a world overriding a campaign scenario inherits that mission's
invisible floor plan, which is useful to know before wondering why a player will not stand where
you put your slab.

**Scenario names are gated by Blam tags.** Only the 13 shipped campaign scenarios have
`*-scenario` tags, and the campaign flow resolves the scenario *name* against those tags. A
`testing_*` name cannot launch regardless of what world package exists, so a custom world must
override a campaign scenario's world (the table of free `Testing_*` slots above is therefore
aspirational until scenario-tag generation works).

**Environment switches** on the generator: `MJOLNIR_LEVEL_PACKAGE` (target package path),
`MJOLNIR_CONTENT` (comma-separated list of `floor,playerstart,lights,markers`, or `none`),
`MJOLNIR_FLOOR_ORIGIN` / `MJOLNIR_FLOOR_EXTENT_M` (where the pad sits and how big it is).

## Known unknowns

- **Tagged-property cooking is untested** — see above. It is the difference between authoring
  maps in the editor and scripting them in Lua.
- The 13 shipped campaign worlds all have generated **Blam scenario/BSP tags**; the stripped
  test worlds have none in the retail build. Generating one is what would free a custom map
  from having to squat on a campaign scenario ([`docs/tag_data_pipeline.md`](../../docs/tag_data_pipeline.md)).
- Whether the Blam-driven pawn collides with **runtime-spawned Unreal geometry** at all. It
  walks on Blam BSP collision; our slab has not been shown to be stood on.

## How the container works

`package.ps1` stages the project with IoStore and renames the result to
`pakchunk990-MJOLNIRWORLD-Windows_P`. The `_P` patch suffix makes it win chunk
lookups; the stub `.pak` beside it is what makes the game discover it (both
verified against this game — [`docs/iostore_packaging.md`](../../docs/iostore_packaging.md)).
The container carries its own `ContainerHeader`, so the new package is
registered in the game's package store when it mounts.

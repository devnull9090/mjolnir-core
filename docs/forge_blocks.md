# Forge building blocks

**Status:** 2026-11-01. Two shipped blocks are included on newly baked maps
(a Covenant crate and the Covenant portable shield). The original 18-piece
Foundry source set and community pack catalog, packaging, dependency and layout
binding support are implemented. See [forge_packs.md](forge_packs.md) for the
current architecture, reproducible build and runtime verification status.
The [local CU4 evidence](forge_pack_validation.md) records all 18 types placed,
representative rendering and collision, restart persistence, and save/load identity guards.
**See also:** [forge.md](forge.md), [re/forge_engine.md](re/forge_engine.md)
(placing, the grab crash, markers), [level_format.md](level_format.md)
(`blam.map_variant`, `blam.forge`).

## What a block needs

A Forge block is an object tag the simulation can place from a map's palette
and players stand on. Four things, all checked in CU4:

| Need | Why | Where |
|---|---|---|
| A collision model (`coll`), ideally a physics model (`phmo`) | The simulation does all collision. Unreal geometry is visual only. | the tag's `model` |
| A multiplayer object block | The placement check (`0x3049e0`) refuses a tag without one (root `+0x124`) | the object definition |
| An Unreal actor | Each object tag's wrapper package holds an `AssetReference` to an actor Blueprint, and the game binds a pooled actor of that class to the object. Without one the object is invisible, like MJOLNIR's flag stands and spawn points. | `/Game/Tags/<path>-<group>`, `BlamCrateTagDataAsset` and the like |
| *Phased physics in forge* (multiplayer flags bit 1) | Otherwise placing looks for room at the cursor and refuses anything resting on the ground | MJOLNIRForge sets it in memory on palette tags |

## What ships

CU4 ships **no Forge blocks**. Nothing of Reach's Forge World palette
survives: a search of all 12,508 tags and 144,482 Unreal packages for
forge, block, wall, ramp, bridge, platform or column names found campaign
geometry only. What comes closest (surveyed 2026-11-01; every row has a
collision model, a physics model and a Blueprint with a mesh):

| Tag | Use | Size (m) | MP block | On B40 |
|---|---|---|---|---|
| `objects\props\covenant\crate_space_a\crate_space_a` (crate) | crate, cover | 1.4 × 1.6 × 2.25 | yes | yes |
| `objects\props\covenant\cov_portable_shield\cov_portable_shield` (scenery) | barrier (the panel can be shot down and recharges) | 2.4 × 1.2 × 2.9 | yes | yes |
| `crate_comm_a`, `crate_comm_b` (crate) | wall, column | 2.9 × 2.6 × 4.2; 1.8 × 2.5 × 4.2 | no | yes |
| `objects\levels\halo1\solo\b40\bridge_glass\bridge_glass` (scenery) | bridge (breaks at once: vitality 1) | 14.7 × 2.6 × 0.25 | no | yes |
| `light_bridge_b40` (machine) | bridge | 27 × 3.7 × 0.5 | no | yes |
| `elevator_a/b/c_b40` (machine) | platform | 6.5 × 6.6 × 0.5 | no | yes |
| Forerunner doors (`acr_big_angle_door`, `for_door_a`, `acr_control_room_door`, `chasm_door`) | walls | various | no | yes |

More is shipped but not loaded by B40: C20's light bridges (4 × 22 m and
4 × 28 m), E30 wreckage, small UNSC crates and doors. A palette entry that
names one loads it by name. Machines follow their device animation, so where
a door or a light bridge rests once placed on its own has to be seen in game.

`defs/level/palette-map.json` `blocks` lists the two with a multiplayer
block, so every map baked with `map_variant` gets a **blocks** palette. The
others need a multiplayer block grafted in, which makes new tags (see
*Making blocks* below).

VERIFIED in game (BGL, 2026-11-01): with `crate_space_a` put in a palette
entry at run time, it placed from the palette, Unreal drew it, it was saved
in the layout, and a Slayer game started with it. Not checked: standing on
it (the Monitor flies through everything).

## Run-time palette slots: `slots.txt`

A palette entry's object is the tag index in its first variant (`+0x10`).
The simulation reads it every time it places from the entry (`0x32f450` →
`0x5ee570`). MJOLNIRForge points entries at other tags when it reads the
palettes, and again at each new map before a saved layout is applied, from
`MJOLNIRForge\slots.txt`:

```
# palette:entry = tag path (an object tag the map loads)
3:1 = objects\props\covenant\crate_space_a\crate_space_a
```

- The tag must be loaded: referenced by the map, or by anything the map
  loads.
- The entry changes for the whole game. Objects the map itself placed from
  it change too: pointing BGL's health-pack entry at a crate turned every
  health pack into a crate.
- A saved layout's engine payload names entries. New community-pack layouts
  also save tag/version bindings and refuse an entry whose tag or pack line changed; see
  [saved-layout checks](forge_packs.md#saved-layouts-and-downloads).

## Community packs

The earlier proposal for 32 global slot tags and Hub-assigned slot ranges is
retired. Packs now own `objects\mjolnir\forge\<pack-id>\<block-id>` tag paths.
Each map declares its supported subset and order in `blam.forge_packs` before a
standalone bake. The scenario includes these references and their package
preloads; the map archive depends on the corresponding Hub release lines.
There is no shared global slot allocation and installing a pack does not
automatically add it to an existing map.

The Hub's Forge catalog displays validated content releases. The launcher
downloads map dependencies and missing releases required by saved layout
sidecars. Native Forge checks each saved index against its tag path and pack
line before recreating objects. The complete contract and
current limits are in [forge_packs.md](forge_packs.md).

## Making blocks

The [Foundry build](../forge-packs/foundry/README.md) uses these tools to produce
new namespaced meshes, synchronized actors, tags and exact collision hulls.
Cooked artifacts are generated locally from the supported game installation.

- **The tag:**
  - `mjolnir new-tag --group crate --from objects\props\covenant\crate_space_a\crate_space_a --to <namespaced block path>`;
  - `--graft "object.multiplayer object=crate:crate_space_a-crate:object.multiplayer object"` for a donor without the block;
  - `--asset-reference /Game/.../BP_Thing` for the actor;
  - `--payload` for a model, collision and physics of its own.
- **Collision:** `forge_collision` builds triangle collision BSPs and MOPPs;
  `tools/forge/build_collision.py` builds fixed polyhedra from the same hulls.
  Composite pieces retain separate hulls to preserve openings.
- **The Unreal mesh:**
  - rewrite a shipped mesh's LOD in place (`mesh_rewrite` + `package_add`,
    docs on UE mesh writing); or
  - cook in the MJOLNIRMaterials editor and retarget (`tools/ue/cook.ps1`,
    `ue retarget`); or
  - draw it the way the Halo 2 machines are drawn: the level loader's
    `follow` attaches a mesh to the donor's actor and hides the donor's own
    (`mods/MJOLNIRLevelLoader/Scripts/main.lua`, `follow`).
- **From Halo Reach (MCC):** `mjolnir cache info forge_halo.map` identifies
  the map, but no stager reads Reach caches yet. One would be modelled on
  `crates/blam-cache/src/h2`. The first check is whether Reach's
  collision and physics model layouts match CU4's, by comparing
  `mjolnir fields` for each group. Forge World's blocks are mostly
  scenery with a Havok physics model, which CU4's crates use too.
- **Modelled new:** a mesh plus collision hulls (boxes and ramps are their own
  hulls), through the same pipeline. Each physics hull must be convex; a
  doorway or other compound piece uses multiple hulls.

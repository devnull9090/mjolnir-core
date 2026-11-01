# Forge building blocks

**Status:** 2026-11-01. Two shipped blocks are on every map baked from now on
(a Covenant crate and the Covenant portable shield). Any object tag the map
loads can be put into a palette at run time (`slots.txt`). Block packs from
the hub, ported from other Halo games or modelled new, are designed below
but not built.
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
- A saved layout names entries, not tags. Its objects are whatever the
  entries hold when it loads.

## Block packs (designed, not built)

The user's plan is block packs on the hub: blocks ported from other Halo
games, and new ones modelled with AI tools. A pack has to work on maps
already baked, whose palettes are fixed in their scenario tags. The run-time
slots above cannot reach a pack's tags on their own, because only referenced
tags load. So:

1. **Slot tags in the CE runtime pack.** `objects\mjolnir\forge\slot_00` to
   `slot_31`, each a clone of `crate_space_a` with a multiplayer block. The
   bake's blocks palette lists all 32, so every map references them and they
   always load. A slot with no pack behind it is hidden from the palette.
2. **A pack overrides slot tags by path.** It ships its own tags at those
   paths (a mod container, the same way the CE runtime overrides shipped
   tags) and the Unreal side for them. The hub assigns each pack a slot range
   so two packs never collide; the manifest records which slot is which
   block.
3. **Layouts record their slots.** A saved layout gets a side file with the
   slot → pack block list. Loading one whose packs are missing says which,
   instead of placing the wrong blocks.

## Making blocks

All of these tools exist; none has made a Forge block yet.

- **The tag:**
  - `mjolnir new-tag --group crate --from objects\props\covenant\crate_space_a\crate_space_a --to <slot path>`;
  - `--graft "object.multiplayer object=crate:crate_space_a-crate:object.multiplayer object"` for a donor without the block;
  - `--asset-reference /Game/.../BP_Thing` for the actor;
  - `--payload` for a model, collision and physics of its own.
- **Collision:** `mjolnir level machine-collision` rebuilds a collision
  model's MOPP from triangles. That is the step the Halo 2 machines use
  (`tools/level/h2_machines.py`).
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
- **Modelled new (the user's AI-modelling plan):** a mesh plus a simple
  collision hull (boxes and ramps are their own hulls), through the same
  three steps. Keep the collision convex per piece; the simulation's
  physics models are convex shapes.

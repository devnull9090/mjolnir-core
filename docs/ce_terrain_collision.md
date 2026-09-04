# Halo CE terrain as Campaign Evolved collision (2026-09-03)

How a classic `bloodgulch.map` collision BSP becomes something the Meteorite
simulation walks on, what was proven offline, and what the single remaining
in-game test is. Tooling lives in `crates/blam-sbsp` (`unpack16`, `pack16`,
`transplant`, examples). No claim below needed the game running unless it
says so.

## Where walkable collision lives

The world shell (`raw_items.collision bsp`) is not what the pawn stands on.
Every walkable surface is an **instanced-geometry definition**, referenced by
an **instance** (transform, bounds, a `physics` block with the Havok shape) and
reached through a two-level Havok broadphase:

    cluster to instance group spheres / mopps   ->  instance group to instance spheres / mopps  ->  instance

- A definition's `collision info` carries the same eight 16-bit tables as the
  shell (nodes 8 B, planes 16, leaves 8, 2D refs 4, 2D nodes 16, surfaces 14,
  edges 12, vertices 16) plus `bsp3d supernodes`. Nine shipped definitions have
  no supernode; one ships 3,205 surfaces, so size is not a limit.
- Raising the definitions under the spawn by 3 wu (`examples/shift_defs.rs`)
  changed what the pawn stood on (it fell through), so these tables are the
  source. Confirmed in game, one launch.
- An instance without a `physics` block (the navmesh instance) is never
  collidable. An instance moved away from its group's sphere is culled before
  its shape is tested: relocating instance 105 to the origin gave no collision
  even with valid tables.
- `instance group to instance spheres[g]` has `center`, `radius`, and an
  `instance indices` block; `examples/groups.rs <payload> <instance>` finds the
  group. Instance 763 (a spawn-floor platform) sits in group 58, radius 17.87.

## The encoder is byte-exact

`examples/roundtrip16.rs` decodes a shipped block into the CE structs
(`unpack16`), re-packs it with `pack16`, and compares. Definitions 10, 159
and 178 and the world shell of `BSP_01_1_Start` all come back **identical**,
every table. Our leaf flags, 2D sign bits, plane-negated flag and edge order
match the engine's.

## The 2D projection convention, and the translation bug

Each 2D BSP lives in the projection of its parent 3D plane. Scoring every
candidate against the surfaces the shipped 2D trees actually sort:

| convention | def 10 | def 159 | def 178 | shell |
|---|---|---|---|---|
| drop the largest-normal axis; keep the other two in cyclic order when that component is positive, swapped when negative; right child = positive side | 100% | 100% | 100% | 99.5% |
| every other candidate | 0–72% | 28–72% | 39–65% | 19–81% |

`pack16::translate` used to move vertices and 3D planes and leave the 2D split
lines alone. After any sideways move every point-in-leaf lookup then chose
the wrong surface, which is why transplanted shells and definitions let the
pawn through. It now shifts each 2D line by `i·t[u] + j·t[v]` in its parent
plane's projection (`pack16::projection_axes`, `pack16::node_planes`); the
probe stays at 100% after a `(-35.4, 151.17, 50)` move of a shipped
definition. On the Halo data the probe reads 98.3% both before and after
translation, so that residual is the data or the probe, not the move.
`examples/probe_residual.rs` narrows it to 14 of 5,098 surfaces (flat floors
among them), with no 2D subtree shared between references and no dependence
on the reference's negation bit — a property of those Halo trees, worth a
look only if holes show up in play.

## Placing Bloodgulch

`examples/def_transplant.rs --keep-position` puts the CE collision into a
definition behind an instance that stays where it is (so it stays inside its
broadphase group), resets that instance to an identity frame, subtracts the
instance position from the geometry, and sets the instance bounds, bounding
sphere and Havok shape box. `examples/def_clear.rs` empties the competing
floor definitions so what the pawn lands on is unambiguous, and
`examples/widen_group.rs` grows the group sphere to the new extent.

Staged for the next launch (`pakchunk999-MJOLNIR-Windows_P`):

    def_transplant  bsp_01_1_start.bin collision_0.json out 159 763 -35.4 151.17 44.0 --keep-position
    def_clear       out out2 78 97 110 129 32 141 168 71 9
    widen_group     out2 out3 58 33.504 33.532 68.826 99.4
    mjolnir pack --group scenario_structure_bsp --tag Solo/B40/_Generated_/BSP_01_1_Start --payload out3

### The broadphase, as far as it is decoded

`examples/mopp_dump.rs <payload> 58` prints group 58's Havok mopp: 141 bytes
of bytecode, build type 0, scale/offset `v = (16.70, 24.37, 37.86; w
635595.9)`, over ten members `[165, 214, 279, 545, 550, 593, 643, 722, 763,
779]`. It is a bounding-volume tree over the members' boxes, so a query far
from instance 763's original box will not return 763 even after the group
sphere is widened; near the spawn, inside that box, it should. Regenerating
these mopps (both levels) is the price of placing terrain as instances
anywhere in the map — or the price is avoided entirely if the world shell
turns out to be walkable once its 2D splits are right, which is why two
variants are staged:

| variant | where the terrain lives | broadphase | in `Paks` now |
|---|---|---|---|
| shell | `raw_items.collision bsp[0]`, pass-through supernode, Chasm_old kd companions | none (kd supernodes) | **yes** (`scratch/bgshell`) |
| definition | definition 159 behind instance 763, group 58 sphere widened | group mopps, untouched | no (`scratch/bgsbsp`) |

Both clear the spawn-floor definitions (78 97 110 129 32 141 168 71 9; the
definition variant leaves 159) so the pawn has nothing else to stand on.
Every earlier "the shell is not walkable" verdict came from transplants with
the 2D-split bug, so it is unproven either way.

### The one-launch protocol

NEW GAME → Assault on the Control Room (row 5), no screenshots. Then:

```lua
local pawn = FindFirstOf("BP_MeteoritePawn_C")
local z0 = pawn:K2_GetActorLocation().Z / 304.8
local t = os.clock(); while os.clock() - t < 3 do end
local z1 = pawn:K2_GetActorLocation().Z / 304.8
print(string.format("z %.2f -> %.2f : %s", z0, z1,
  (z1 > 43.5 and z1 < 45.5) and "PASS: standing on Halo terrain"
  or (z1 < 30 and "FAIL: fell through" or "inconclusive")))
```

Prediction for the blank B40 map, NEW GAME: the pawn spawns at 48.16 wu with
no tower floor under it and lands on Bloodgulch's canyon floor at about
**44.1 wu** (CE z 0.12 + 44). Falling to the kill plane means the group's
Havok mopp still culls the instance, and the mopp bytecode is the next thing
to decode. Do not test through RESUME: three of three resumes with a modified
structure BSP hung the game thread, while NEW GAME loaded every time.

## The scenario half

`tools/level/gen_bloodgulch_level.py` turns the halo2ue staging export
(`staging/bloodgulch/placement.json`) into `examples/levels/bloodgulch.level.json`:
eight CTF/Slayer starts, the 28 vehicles, 15 weapons and 18 pickups the CE map
places (through `defs/level/palette-map.json`; health packs, the flamethrower
and the plasma cannon have no equivalent and are dropped), and 170 netgame
markers kept for a later game-mode layer. Everything moves by the same
`(-35.4, 151.17, 44.0)` wu offset as the collision, so a start at Halo
`(98.49, -157.64, 1.70)` lands at `(63.09, -6.47, 45.70)` wu, 1.6 wu above the
transplanted floor there.

Assembly for a test, two containers plus the loader's level file:

    mjolnir level bake examples/levels/bloodgulch.level.json --install-test     # scnr: pakchunk998-MJOLNIRLEVEL-bloodgulch_P
    (one of the two collision containers above)                               # sbsp: pakchunk999-MJOLNIR-Windows_P

Remove `pakchunk998-MJOLNIRLEVEL-blank_b40_P.*` first: two `_P` containers
over the same scenario chunk would race. Order of tests: blank map + shell
collision (landing height), then this level on whichever collision variant
held the pawn.

## The visual half

The world under the blank map is already a MapKit cook: the installed
`pakchunk990-MJOLNIRWORLD-Windows_P` holds one file, an empty `B40.umap`, so
the void with one streaming level and no lights was our own canvas, not the
shipped world. Visuals therefore ride the same container as the world:

1. `unreal/MJOLNIRMapKit/Content/Python/mjolnir_import_bloodgulch.py` builds
   the empty canvas with the existing generator, then imports halo2ue's
   `staging/bloodgulch/bsp/bsp_0.gltf` (one mesh, 42 materials, 16 textures)
   under the level's folder, which the chunk label routes into chunk 990. The
   UE 5.6 HaloUE project's 343 assets cannot be reused: cooked formats are
   engine-version locked and the game is 5.5.
2. `scripts/package.ps1 -LevelPackage /Game/Levels/Halo1/Solo/B40/B40` cooks
   world and mesh into the container. Two things had to be true for the mesh
   to come along at all: nothing in the empty world references it, so
   `DefaultGame.ini` lists the folder under `DirectoriesToAlwaysCook`; and a
   label's "assets in my directory" rule does not descend into subfolders, so
   the mesh folder carries its own chunk-990 label.
3. The level file's `decor` names the mesh
   (`/Game/Levels/Halo1/Solo/B40/Halo/Bloodgulch/bsp_0.bsp_0`) at the
   collision offset; the runtime loader spawns it.

Coordinates check out from the glTF alone: its position bounds are
`(18.0, -1.06, 137.33)..(402.04, 79.96, 579.79)` m, which is Halo
`(x, z, -y) x 3.048`, and Unreal's glTF import turns that into
`(x, -y, z) x 304.8` cm — the same mapping every other placement uses — so
the mesh at identity sits at native Halo positions and only the transplant
offset is applied.

Two unknowns the next launch answers, both in
`tools/level/checks/bloodgulch_check.lua`: whether the game deserialises a
stock-cooked `UStaticMesh` (the actor/component wall documented in the MapKit
README is about unversioned *actor* properties; assets are untested), and
whether a package absent from the shipped asset registry can be loaded by
path from Lua at all (`LoadAsset` versus `KismetSystemLibrary.LoadAsset_Blocking`).
If neither loads it, the fallback is to make the empty world import the mesh
so it arrives with the level.

## Installed right now (2026-09-03 evening)

| container | holds |
|---|---|
| `pakchunk990-MJOLNIRWORLD-Windows_P` | empty B40 canvas world + `bsp_0` terrain mesh, 42 materials, 16 textures (79 chunks) |
| `pakchunk998-MJOLNIRLEVEL-bloodgulch_P` | stripped B40 scenario with Bloodgulch starts, vehicles, pickups, startup script |
| `pakchunk999-MJOLNIR-Windows_P` | BSP_01_1_Start with the Bloodgulch collision in the **world shell**, spawn floors cleared |

Plus the loader's `levels/B40.level.json` with the terrain decor entry. One
NEW GAME launch of Assault on the Control Room, then
`tools/level/checks/bloodgulch_check.lua`, answers three questions at once:
does the shell collision hold the pawn, does the mesh asset load, does it
render where the collision is. The definition-collision variant and the
blank level wait in the session scratch (`bgsbsp`, `paks_moved`).
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

Prediction for the blank B40 map, NEW GAME: the pawn spawns at 48.16 wu with
no tower floor under it and lands on Bloodgulch's canyon floor at about
**44.1 wu** (CE z 0.12 + 44). Falling to the kill plane means the group's
Havok mopp still culls the instance, and the mopp bytecode is the next thing
to decode. Do not test through RESUME: three of three resumes with a modified
structure BSP hung the game thread, while NEW GAME loaded every time.

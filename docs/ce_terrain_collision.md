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

## Launch log, 2026-09-03 evening

| build | collision | level | result |
|---|---|---|---|
| shell, 2D fixed, floors cleared | world shell | Blood Gulch level (starts, vehicles, pickups) | vehicles and pickups placed; pawn steady 3 s at the Halo start (63.09, -6.47, 45.13); user fell after moving; LoadAsset on the mesh returned invalid; a blocking soft-path load with a 5.0-shaped struct crashed the game |
| def 159 via inst 763, 2D fixed, group sphere widened | definition | blank | game thread stalled ~4 s after the B40 world loaded |
| same, sphere untouched | definition | blank | stalled after the world loaded |
| same + fan split (73 polygons -> triangles) | definition | blank | stalled during the travel transition, before the world |
| **control: shipped def 178 copied verbatim into 159** | definition | blank | stalled during the travel transition |

So the definition-slot swap stalls the load even with shipped geometry, and
the one definition build that did load earlier (broken 2D data) had its
emptied floors still holding the pawn - which means that container's tables
were not what the pawn stood on. Whether the override was served at all in
that run is unknown. None of these stalls left a crash report.

The next launch is a control, already installed: **every definition's
collision emptied** (`bg_allclear`), with the mesh-free canvas world back in
place. Standing at 48.16 means definition tables in an override are not what
the pawn walks on (and the earlier shift result needs re-reading); falling
means overrides are served and the slot swap is the problem. The blank
level, the fan-split transplant and the Blood Gulch level all wait in the
session scratch. Do not test through Resume.

### Later the same night

Two more definition-route launches, both stalled in the travel transition:
every definition emptied (`bg_allclear`), and the Blood Gulch transplant
with the Havok shape box written correctly. `examples/shape_frame.rs`
established the box's frame first — the definition's local vertex bounds
times the instance scale, no rotation or position (instances 763, 105, 545
match to the last digit) — so the box is right and still not sufficient.
Five stalls against one load: the definition route is parked until the
per-instance load-time build is understood, most likely by finding what the
simulation does with `instanced geometry instances[i].physics` and the
instance-group mopps when a BSP is mounted.

Installed for the next launch: **world shell** collision (the build that
held the pawn), the Blood Gulch level with BSP 8's world box widened to the
terrain's extent, and the world container carrying the terrain mesh. The
check script also asks the asset registry to scan the mesh folder before
loading.

### Shell route, second launch (user-driven, 22:41)

Blood Gulch level with BSP 8's box widened, shell collision, mesh world.
Vehicles and pickups placed. With `bWaitingForBlamGameplayStart` already
false, the pawn read **(63.09, -6.47, 44.05) steady for five seconds** at
the Halo start — 1.65 wu below the start point, i.e. landed, on Blood
Gulch's floor (the transplant has nothing else there). The user reported
falling to death before that sample; whether the fall was the respawn cycle
or the terrain giving way elsewhere is the open question. The loader again
reported the terrain mesh not found at spawn time; a later `StaticFindObject`
returned an object (validity unchecked), `LoadAsset` returned invalid, and a
level reload plus registry scan was followed by a game-thread hang.

### What the minidumps say

UE4SS wrote a minidump for each stall. All four decode to the same access
violation at `HaloSimulation_tag_release.dll+0x2eb450`: the bsp3d tree walker
reading a node through the definition's runtime block reference (an arena id
in the top four bits of the word after the count, plus a word offset — the
`{count, arena-offset/4, struct id}` header from the runtime-poking notes).
Its caller, `+0x2eb130`, is a **kd supernode walk**: it takes a supernode
index, reads that supernode's 128 bytes (15 split values, an opaque word, 15
cells, a dimensions word), picks a cell and passes the cell's node to the
walker. Every Blood Gulch definition build shipped with **zero supernodes**,
so the walk read garbage cells; the all-clear build had nothing at all. The
one shipped definitions with no supernode are small and probably non-solid.
The shipped-copy control (21 supernodes) crashing the same way is not yet
explained. Next build: a pass-through supernode built on definition 159's own
(15 cells all naming node 0), which no definition build had tried through
NEW GAME. `examples/super_dump.rs` shows shipped cells are `0x40000000|node`
for tree roots and small integers for child supernodes.

### The fault address is zero

The pass-through-supernode build crashed at the same instruction, and the
exception records of the last two dumps both read address **0x0**. At that
instruction the address is `arena_base + (block_ref_offset + node*2)*4`, so
the definition's runtime block reference for `bsp3d nodes` was still zero:
the block header was never relocated at load. The rewrite leaves the layout
sections byte-identical and only grows the data section; the wrapping
`.uasset` is 769 bytes with no offset table; the block fields and `tgbl`
headers are shaped exactly like the shipped ones (`examples/block_headers.rs`,
`tag_sections.rs`, `uasset_offsets.rs`). So whatever the loader uses to
decide which nested block headers to relocate is not in the layout, not in
the package, and not in the header shape — and the world shell's silent "no
collision" is most likely the same unrelocated reference read by a walker
that tolerates null. This is where the definition route stops without
reversing the loader; `C:\tools\ghidra_12.1.2_PUBLIC` is available for that
pass, starting from the caller chain into `HaloSimulation_tag_release.dll`
`+0x2eb130` and the relocation of `raw_items` blocks at BSP mount.

### Ghidra: the relocation, found (2026-09-04)

Full write-up in `docs/re/collision_bsp/`. The sim resolves collision data
through 16 memory arenas: a reference is `(arena<<28)|(dword offset)`, resolved
as `arena_base_table[arena] + offset*4` (base table at `.data 0x1802c2ccc0`).
On-disk block fields are `{count, 0, 0}`; the two zeros are the data and
struct-def refs, filled at load into a resident structure-BSP record at
`DAT_1813d45a8 + bsp_index*0x490`. The crash (`+0x2eb450`, the kd supernode
walk) reads `arena_base[ref>>28]` and gets null: the collision block's ref was
never correctly relocated. The trigger is **changing a nested collision
block's element count** — the same-size `shift_defs` edit loads and the pawn
stands, while every count change (transplant grow, shipped-copy, all-clear
shrink) crashes, regardless of byte validity or total size. The exact writer
populates the 0x490 record through a passed pointer, so the cheapest next step
is a live memory diff of that record between a shipped and a resized load to
name the block whose relocation breaks.

## The MOPP compiler, and the supernode bug (2026-09-08)

Two real blockers were found and fixed; the pawn now lands on transplanted
Blood Gulch terrain, though it does not yet stay there.

**The broadphase is three trees deep.** Collision reaches an instance through
`cluster -> instance group -> instance` before the definition's own tree is
consulted, and each level is a Havok MOPP. A transplant that moves or grows an
instance leaves all of the upper trees describing where it used to be, and
widening the group *sphere* does not help: the sphere and the tree are
separate tests. `examples/group_mopp.rs` recompiles the instance-group and
cluster trees; `examples/def_mopp.rs` recompiles the definition's own.

Terminal conventions, read off the shipped data: an instance-group tree names
**absolute instance indices** (group 58 ships `Reindex` nodes so its terminals
come out as its member list, 165..779), and the cluster tree names **absolute
group indices** (0..91).

**The pass-through supernode was writing the wrong slots.** A `bsp3d
supernode` is thirty-two dwords: fifteen split planes at 0..14, **sixteen**
child cells at 15..30, and the packed axis word at 31. `passthrough_from` was
setting cells at 16..30 and leaving slot 15 alone — and the walk
(`FUN_1802eb130`) descends exactly four levels, so the cell it lands on is
`15..=30`, slot 15 included. Definition 159 ships `0x80000000` there, which the
walk reads as "no hit, stop", so every query whose descent went left four
times found nothing. Shipped supernode 1 carries `0x400000b9` in that same
slot, which is plainly a child, so the old comment claiming slot 15 is never a
child was simply wrong. `passthrough_supernode` had the matching error: it put
the axis word after the planes instead of last.

That is why the earlier note here said a pass-through supernode "hung the
simulation" and why `def_transplant` defaulted to emitting none. Emitting none
leaves the definition with zero supernodes, and the walk then has nothing to
traverse, which is the fall-through that survived every other fix.

### Where it stands

With the definition tree, both broadphase levels and the supernode all
correct, the pawn **lands on Blood Gulch**: measured at `45.96` wu, three
samples, zero velocity, against a predicted floor of `45.09` plus the capsule.
Offline the compiled tree answers a pawn-sized column at the spawn with all
eight surfaces that are actually there, and the floor polygons under the spawn
carry upward winding normals, so orientation is right.

It does not hold. Later samples at the same xy read `28.56` wu with zero
velocity, resting on other B40 geometry below. The pawn sinks straight down
rather than sliding, so the next suspect is the definition's own BSP rather
than the broadphase: `probe_residual` already reports 14 of 5,098 surfaces
that the 2D trees mis-sort, and a gap under the pawn would look exactly like
this.

## It stands (2026-09-09)

With the Blood Gulch scenario level installed (`pakchunk998-MJOLNIRLEVEL-bloodgulch_P`,
which puts the player start at a CTF start rather than B40's own) the pawn spawns at
`(63.09, -6.47)` and rests at `45.70` wu with zero velocity, and all 28 vehicles the
scenario places rest on the terrain at `43.9..47.1` (Ghosts hovering at 44.1, Scorpions
at 45, Banshees at 45.8) — none of the 98 vehicle actors fell to the B40 geometry at 28.
Vehicles are Havok bodies, so that is the MOPP path proven independently of the
pawn's own ground test.

The earlier fall-throughs were at B40's original start `(33.5, 33.5)`, beside the
tower platforms that had been moved to z −500; one load in four stood there and the
rest rested on B40 geometry at 28.5. That spot is not representative and is no longer
the test point.

The last fix on the way: the mopp element carries its code length **three** times —
the hkArray size at 56, its flagged capacity at 60, and the mopp code's own data size
at 80 — and `patch_element` had been writing only the first two. Every shipped
element carries all three equal.

Build recipe that stands:

    def_transplant  bsp_01_1_start.bin collision_0.json a.bin 159 763 -35.4 151.17 44.0 --keep-position --passthrough-supernode
    widen_group     a.bin b.bin 58 33.504 33.532 68.826 99.4
    def_mopp        b.bin c.bin 159
    group_mopp      c.bin d.bin 58 --cluster
    (move instances 593 779 646 545 503 314 to z -500 with `mjolnir tag-file`)
    mjolnir pack --group scenario_structure_bsp --tag Solo/B40/_Generated_/BSP_01_1_Start --payload d.bin

## One command, and what the live pawn showed (2026-09-30)

`mjolnir level collision <collision_N.json> --out <bsp>` now runs the whole
recipe ([`blam_sbsp::convert`](../crates/blam-sbsp/src/convert.rs)): it reads
the canvas BSP and `BSP_03_1_Chasm_old` from the shipped containers, centres
the terrain on the canvas anchor (or `--anchor` / `--delta`), transplants it
into definition 159 behind instance 763, recompiles the definition, group and
cluster MOPPs, parks every canvas instance under the footprint and every other
instance of definition 159 (764 shares it), and writes `<bsp>.transform.json`
for `tools/level/gen_ce_level.py`. With the old hand-typed numbers it
reproduces the September Blood Gulch payload exactly, apart from the rounding
of those numbers. 21 of the 23 halo2ue exports convert offline; Coldsnap's two
BSPs exceed 32,767 surfaces after the fan split and need two definitions.
MOPPs past 64 KB (Infinity, 135 KB) now reach their far subtree through a
24-bit jump (`07`).

`examples/ray_probe.rs` ([`raytest`](../crates/blam-sbsp/src/raytest.rs))
traces rays from every walkable floor point down and sideways through a tree
and compares with brute-force polygon hits. The staged CE tables, the packed
16-bit tables, the definition and the shell all give **zero misses**, with
identical counts: the transcoder is faithful and the tables have no holes.

Hang 'Em High on B40 (codename HEH), six launches, read with
`mjolnir live objects` and Blam `object_get_bsp`:

- **A point outside the canvas shell's inside test freezes everything.**
  `object_get_bsp (player_get 0)` returned -1; no object was simulated (the
  player could not be killed or pushed, pickups sat at their exact placement
  heights). B40's shell calls roughly x 1.6..89.6, y 23.4..115.4 inside
  (`examples/shell_inside.rs`); HEH's first spawn (y 21.4) and **the
  2026-09-09 Blood Gulch spawn (y -6.5) are both outside**. So "it stands"
  in September was a frozen pawn, and the definition route has never held a
  simulated one.
- Putting the CE tree into the shell as well (`transplant_shell`, pass-through
  supernode + Chasm_old kd companions) makes the pawn simulated: it falls,
  dies below the terrain's lowest point and respawns.
- **An instance's Havok shape keeps copies** of its definition's mopp header —
  `mopp data size`, `code info copy`, `havok w code info copy` — and of its
  scale (`mopp scale`, 0.328084 on definition 159's instances). The converter
  now writes all four (`sync_instance_mopp_copies`, `mopp scale`).
- Player starts in CE sit exactly on the floor (50.110 over 50.109); the
  generator now lifts them 1 wu.
- **Still falling**, with the header copies and scale synced, the start
  lifted, and — the discriminating run — B40's own shell kept and the terrain
  placed inside it (`--anchor 45.6 69.4 43.65 --keep-canvas-shell`): the pawn
  is simulated and drops straight through the terrain. Parking B40's instances
  under the footprint removes the floor the body used to stop on at z 5, so
  instance Havok shapes *are* the collision path; the transplanted instance
  just is not in it.

Offline, the whole broadphase answers at the spawn
(`examples/havok_path.rs`: cluster → group 58 → instance 763 → 147
surfaces). Next: bisect with a **no-op control** — definition 159's own
tables round-tripped through the same pipeline, pawn dropped on it — then add
one change at a time (MOPP recompile, frame reset, bounds, group and cluster
trees) until the floor disappears.

### The bisect, with a live Megalo pawn (2026-09-30, later)

With the Megalo spawn working on B40's floor (`re/megalo_engine.md`), a
control build — definition 159's MOPP recompiled from its own shipped
surfaces with `examples/control_mopp.rs`, instance 763's shape header synced,
the other floors under the spawn (545, 593, 779) parked, nothing else changed —
**holds the pawn** at (33.50, 33.53, 47.85). So the MOPP compiler, the header
sync and host 763 are all fine.

What the converted build changes on top is the frame, bounds and broadphase —
and it misses the **`instance kd hierarchy`**: a collision kd-tree (15,293
nodes, a 19,116-entry spatial hash, and `in use masks` with one entry per shell
supernode — 2,009, exactly B40's count) whose nodes list the collidable
instances (`collidable headers`: instance index, `1 << (index % 32)` dword
mask, bsp mask). Instance 763 is listed only in the nodes around its old box,
so terrain moved away from it is never tested; and a shell replaced by one
pass-through supernode no longer matches the hierarchy at all. The converter
has to rebuild it to match the shell it ships.

### What the pawn actually stands on (2026-09-30, last)

Two more controls overturn the model this document has been working under:

- Definition 159's own geometry, through the whole converter at its shipped
  place (`examples/control_world.rs`): the pawn stands. Moved +20 wu: it
  falls. Blam's own queries were then traced live at the new spot (point →
  BSP 8 cluster 0 → kd root node 15, which lists 763 → 763's record, box and
  sphere): all correct.
- The passing control again **with 763 itself parked at z -500**: the pawn
  **still stands**, at (31.53, 33.46, 48.18).

So no pawn has ever stood on a definition's collision, the 2026-09-09 result
included. Havok movement stands on the BSP's cooked **`structure_physics`**
static shape: a 561,889-byte MOPP over 34,890 keys (contiguous from
`0x34000000`, not the 19 shell surfaces, and not the instances' 239,840 /
89,491 definition surfaces), next to the resource's `meshes` block (183
`global_mesh` elements: the 182 definitions plus one). Parking instances does
move what the pawn rests on elsewhere, so instance data feeds that shape
somehow, but not through the definitions' collision BSPs.

Next: identify the `structure_physics` shape (the Havok shape type, how a key
resolves to a triangle, where the triangles live — `meshes`, the resource's
per-mesh parts, the instance transforms) and compile the CE terrain into it;
`blam_sbsp::mopp` already compiles valid trees.

## It stands, for real (2026-09-30, night)

`convert::rebuild_structure_mopp` recompiles the BSP's static Havok body,
`structure_physics.mopp code block`. Its terminals are keys resolved by
`getChildShape` (`0x3cf720`): `key >> 29` = 1 one world-shell surface
(`0x20000000 | k << 26 | surface`), 2 a whole instance under its frame
(`0x40000000 | instance`), 3 one definition surface under an instance's frame
(`0x60000000 | surface << 16 | instance`, surface < 8192). B40's start BSP
ships 19 / 776 / 34,095 of them, and nothing rebuilds the tree at load. The
converter keeps every shell key and every key of an instance it neither parks
nor replaces (boxed from the geometry as it now is), drops the rest, and adds
one type-3 key per host surface (one type-2 key past 8,191).

- Control: definition 159 moved +20 wu with the rebuilt tree — **the pawn
  stands** at (32.02, 55.27, 47.85).
- **Hang 'Em High**, converted with `mjolnir level collision --anchor 45.6 69.4
  43.65 --keep-canvas-shell`, generated with `tools/level/gen_ce_level.py`
  (spawn-point scenery, map variant palette), launched under Megalo: the
  player spawns at a CE start and **stands on the terrain** at (52.88, 62.90,
  44.95); all 17 map weapons rest on it at their CE heights (44.95 placed →
  44.98). 19 shell + 20,603 kept + 2,050 new keys, 14,268 dropped, 205,578 B.

Still open: the canvas shell's inside region limits where a terrain can sit
(B40: about x 1.6..89.6, y 23.4..115.4) — Blood Gulch is bigger, so the shell
has to be replaced (the CE tree plus a matching kd hierarchy, case A); terrain
visuals; collision materials.

## A BSP of our own: Blood Gulch without B40's geometry (2026-09-30, late)

`mjolnir level collision <collision_N.json> --out <bsp> --own-bsp [--delta dx dy dz]`
builds the structure BSP from `BSP_03_1_Chasm_old` — a small shipped BSP with
one kd supernode, one cluster and one instance — instead of B40's start BSP
(`convert::convert_own`): the CE tree goes into its world shell (the inside
test, with its own kd companion tables widened) and into definition 0 behind
instance 0 (seeded with a MOPP element cloned from the static body's, since it
ships none), and `structure_physics` is rebuilt with one surface key per CE
surface. Only the package wrapper is still a shipped tag's (a rebuilt BSP
wrapper does not start); none of the canvas mission's geometry remains, and
there is no region or size limit.

Two things learned on the way:

- A static body of **shell keys alone** (type 1, one per CE shell surface) did
  not hold anything. The instance-surface keys (type 3) are what work.
- The map must stay inside the level's overall extent. Lifted 800 wu above
  B40, objects fell and vehicles were flung hundreds of wu (Havok's world
  extent, presumably). What also matters is that no **active** canvas BSP's
  world box covers the map (B40's start zone set activates BSPs 4, 8, 11, 12,
  15, 16); Blood Gulch was moved by (334.1, -509.8, 0) into a corner only
  inactive BSPs cover.

Result, under Megalo on the canvas's Unreal world: the player spawns at a CE
start and stands at (377.15, -600.41, 0.17); **all 28 vehicles rest on Blood
Gulch** at the CE bases' heights (z 0..4). 1.18 MB payload, 5,305 surfaces.

Next: trim the standalone scenario to this one BSP and zone set (then the
coordinates can stay CE's own), the terrain mesh, and the bare world.

## Scenery behind instances of its own (2026-10-01)

A definition's tables are 16-bit (surfaces 32,767, planes 65,535, edges and
vertices 65,534), and `merge_ce_collision.py` adds every scenery triangle as
a standalone surface with its own plane, three edges and three vertices. The
forested maps overflow one definition on scenery alone: Timberland 31,950
scenery surfaces, Danger Canyon 43,646, Infinity 58,464 (planes first).

When the merged collision does not fit, `mjolnir level collision --own-bsp`
splits the scenery tail off (`split::split_standalone`, using the manifest's
`scenery_surfaces` count) into pieces of 8,192 surfaces, so every surface keeps
a type-3 key of its own. Each piece gets a copy of definition 0 and instance 0
(`convert::add_scenery_instances`): its tables behind an identity frame at the
host's position, a one-node tree with the same empty leaf on both sides
(every point open space; Blam queries never reached scenery surfaces anyway),
its MOPP and the instance's copies of
it, the instance's own index in its collision shape, a place in group 0, and a
collidable header at every kd root. The group, cluster and structure trees are
then rebuilt over all of the instances. The BSP itself stays in the shell and
definition 0. Maps that fit are built exactly as before.

Timberland (4 scenery instances), Danger Canyon (6), Death Island (3) and
Infinity (8) build this way.

A child of "none" in a bsp3d node is **solid**, not empty. The first version
gave each piece a node with "none" on both sides, so every point of the map
was inside solid scenery: a player was killed by the guardians
(`guardian_kill`) the moment they moved, and teleporters refused to exit into
it (`teleporter_blocked`). Danger Canyon, 2026-10-01; one empty leaf fixed
both. Coldsnap does not: its BSP alone has 35,173
surfaces, which would need the tree itself split.

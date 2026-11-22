# AI pathfinding: sectors, links and how the simulation finds them

Part of the [engine reference](engine_reference.md). This page covers the
ground an AI can walk: the tag data that describes it, the simulation code that
reads it, and the generator that writes it for maps that ship without any.

| | |
|---|---|
| Subsystem | AI navigation over level geometry |
| Tag data | `scenario` > `ai pathfinding data[bsp]`; `scenario_structure_bsp` > `instanced geometry instances[i].pathfinding policy` |
| Simulation code | `HaloSimulation_tag_release.dll`, CU4 (build pin below) |
| Our code | `crates/blam-sbsp/src/pathfinding.rs`, `crates/blam-sbsp/src/navmesh.rs` |
| Tools | `pf_stats`, `pf_objects`, `pf_roundtrip`, `pf_generate`, `pf_dump`, `pf_where` (`crates/blam-sbsp/examples/`) |
| Status | Lookup traced and matched to shipped data. Generator built, wired into `level bake`, and **run in the game** (2026-11-22, one PC, solo): on B40's BSP 8 an Elite hunted the player across instances, and on Pelican Warfare four AI walked up to 1.1 km across terrain tiles on 15,197 generated sectors. Structures that stand on the terrain (bases, capture platforms) are joined to it, and an Elite walked from open ground onto a base floor. Not yet run with a second player, or in a real match. |

Every claim carries one of four labels, defined in
[how to research and verify](engine_research_method.md):
**[traced]** read from the simulation's code, **[data]** measured on shipped
tags, **[live]** seen in the running game, **[inferred]** a reading that fits
the rest and has not been tested on its own.

## The idea in one paragraph

The walkable ground of a BSP is cut into **sectors**: flat-ish polygons, each
walkable everywhere inside. Sectors meet along **links**, which are shared
edges. A path is a chain of sectors, crossed link by link. To know which sector
an AI is in, the simulation does not search the polygons. It takes the
collision surface the AI is standing on and looks that surface up in a table of
**refs**, one per collision surface, which names the sector directly. So the
pathfinding data is tied to the collision geometry surface by surface, and any
tool that changes collision must rebuild it.

## The tag data

All of it sits in one element of the scenario's `ai pathfinding data` block per
structure BSP (148 bytes; `scenario_structure_bsp` has a block of the same
layout, `pathfinding data`, which shipped maps leave to the scenario). Indices
are 16-bit and **unsigned**, with `0xFFFF` for none **[data]**: A30's largest
BSP has 59,826 links and link indices up to 59,356.

### Blocks

| Block | Element | What it holds |
|---|---|---|
| `sectors` | 8 bytes | `flags` (u16), `hint index` (i16), `first link` (i32) |
| `links` | 16 bytes | `vertex 1`, `vertex 2`, `link flags`, `hint index`, `forward link`, `reverse link`, `left sector`, `right sector` (all 16-bit) |
| `vertices` | 12 bytes | a point, **world space** [data] |
| `bsp2d refs` | 4 bytes | one ref per collision surface of the BSP's own shell |
| `bsp2d nodes` | 20 bytes | a 2D plane `(nx, ny, d)` and `left child`, `right child` refs |
| `object refs` | 24 bytes | `flags` (bit 0 `mobile`), a `bsps` block, an `object id` |
| `object refs[].bsps` | 24 bytes | `bsp reference` (u32), `node_index` (i16), a `bsp2d refs` block, `vertex offset` (i32) |
| `instanced geometry refs` | 4 bytes | one per instance of the BSP: the index of its `object refs` element (i16) |
| `pathfinding hints` | 20 bytes | `hint type`, `next hint index`, four data longs |
| `seams`, `jump seams`, `doors`, `giant pathfinding data`, `structure checksum` | | not studied; empty or unused in what we generate |

### Sectors and links are winged edges

A link is an edge that runs `vertex 1 -> vertex 2` with its `left sector` on
the left. `forward link` is the next edge around the left sector, `reverse
link` the next around the right one. To walk a sector's ring, start at its
`first link` and take `forward` wherever the sector is the link's left, else
`reverse`, until the first link comes round again. Corners are `vertex 1` when
the sector is on the left, `vertex 2` when it is on the right.

Measured with `pf_stats` on three shipped BSPs **[data]**:

| | B40 BSP 8 | A30 BSP 3 | B30 BSP 3 |
|---|---|---|---|
| Sectors / links / vertices | 632 / 2,377 / 1,807 | 17,301 / 59,826 / 42,028 | 2,928 / 11,903 / 8,806 |
| Rings that fail to close | 0 | 0 | 0 |
| Winding seen from above | 632 counter-clockwise | 17,299 ccw, 2 cw | 2,925 ccw, 3 cw |
| Corners per sector | 3 to 13, most often 4 | 3 to 59, most often 3-4 | 3 to 25 |
| Distance from one plane: median / 99% / max (wu) | 0.000 / 0.262 / 0.446 | 0.013 / 0.226 / 1.427 | 0.011 / 0.189 / 0.347 |
| Area: median / 99% / max (wu²) | 0.57 / 62.7 / 142 | 0.19 / 18.7 / 199 | 0.43 / 33.5 / 139 |
| Longest edge (wu) | 17.3 | 23.3 | 22.5 |
| Sectors that dent inward by more than 0.002 wu | 16 | 1,377 (8%) | 316 (11%) |
| Connected pieces | 125 | 2,027 (one holds 8,878 sectors) | not measured |

Three things follow for anyone writing this data:

- Rings wind **counter-clockwise seen from above**.
- Sectors are **not exactly flat and not exactly convex**. A tolerance of about
  0.2 wu from a plane covers 99% of shipped sectors.
- Shipped ground is in many disconnected pieces. One connected component is not
  a rule the engine enforces.

### Sector flags

Bit names from the tag definition: `sector walkable` (0x1), `sector breakable`
(0x2), `sector mobile` (0x4), `sector bsp source` (0x8), `floor` (0x10),
`ceiling` (0x20), `wall north/south/east/west` (0x40 to 0x200), `crouchable`
(0x400), `aligned` (0x800), `sector step` (0x1000), `sector interior`
(0x2000), `sector rail` (0x4000), `sector user` (0x8000).

In shipped data **[data]** a plain floor is `0x11` (walkable, floor). `0x15`
adds `mobile`: B40 BSP 8 has 149 of those plus 17 step sectors (`0x1045`,
`0x1085`, `0x1105`, `0x1205`: walkable, mobile, one wall bit, step), and all of
them carry `mobile`. They are the sectors on machines and scenery (the object
refs whose `object id` names an object) **[inferred]**.

### Link flags

`sector link from collision edge` (0x1), `sector intersection link` (0x2),
`bsp2d creation error` (0x4), `topology error` (0x8), `chain error` (0x10),
`threshold` (0x20), `wall base` (0x40), `ledge` (0x80), `leanable` (0x100),
`leanable low` (0x200), `leanable high` (0x400), `start corner` (0x800),
`end corner` (0x1000), `seam` (0x2000).

How shipped links use them, counted by whether the link has a sector on both
sides **[data]** (A30 BSP 3; B40 BSP 8 has the same pattern):

| Flag | One-sided | Two-sided |
|---|---|---|
| none | 28,491 | 6,498 |
| `threshold` | 0 | 12,668 |
| `intersection link` | 955 | 3 |
| `wall base` (always with `leanable`) | 7,696 | 0 |
| `ledge` | 3,111 | 0 |
| `topology error` | 729 | 0 |

So `threshold` marks only links between two sectors, and `wall base` and
`ledge` only outer edges. What `threshold` means to the planner, and why most
outer edges carry no flag at all, is **not known**. Our generator writes `0`
between sectors and `wall base` or `ledge` on every outer edge; that has run
live on converted maps (the bots lane, [bots.md](bots.md)) **[live]**.

### Hints and intersection links

Sectors on separate pieces of geometry share no edge, so the data joins them
with an **intersection link** **[data, live]**:

- each sector keeps its own outer link along the seam, flagged
  `intersection link`, with a hint;
- the hint (type `intersection link`, data `(joining link, 0, 0, 0)`) names one
  two-sided link appended after all the others. It runs along the first
  sector's link (same vertices, same `forward link`) and carries the second
  sector's `forward link` as its `reverse link`;
- a sector's `hint index` heads a chain (`next hint index`) of exactly the
  hints of its own links.

In shipped data the two flagged links of a seam lie on the same line
**[data]**: over every intersection hint of B40's 14 BSPs and A30's 8 (about
4,500 seams), the second sector's link is never more than 0.005 wu from the
joining link, across or in height (`pf_stats` prints this per BSP). Bungie's
tool cut the pieces where they meet; it did not bridge a gap.

Other hint types exist in the tag definition (`jump`, `climb`, `vault`,
`mount`, `hoist`, `wall jump`, `breakable floor`, `rail`, `seam`, `door`,
`anticipation`, `takeoff`). B40 BSP 8 uses only `intersection link`; A30 BSP 3
has two `jump link` hints. None of the others has been studied.

### Refs: from a collision surface to a sector

A ref is a 32-bit value:

| Value | Meaning |
|---|---|
| `0` and up | a sector index |
| `-1` | no sector: an AI on this surface is nowhere |
| `0x80000000 \| n` | go to `bsp2d nodes[n]`: this surface is split between sectors |

A node holds a 2D plane and two children, each a ref again. The walk goes
**left when `n . p - d > 0`, else right**, until it reaches a value that is
not a node **[traced]**.

There are three ref tables, one per kind of thing an AI can stand on
**[traced]**:

1. **The BSP's shell**: the top-level `bsp2d refs`, indexed by the shell's
   collision surface. No shipped campaign BSP uses it (the count is 0 in all 13
   scenarios) **[data]**; converted maps do **[live]**. The scenario's
   `structure bsps[i].flags` bit `0x8`, `no default structure pathfinding`,
   must be clear for it to count.
2. **Instanced geometry**: `instanced geometry refs[instance]` names an
   `object refs` element, and that element's `bsps[0].bsp2d refs` is indexed by
   the collision surface **of the instance's definition**.
3. **Scenario objects** (machines, scenery): the `object refs` element whose
   `object id` matches the object, then the `bsps` entry whose `bsp reference`
   matches the collision BSP that was hit.

### The instance policy gate

Each `instanced geometry instances` element of the structure BSP (148 bytes)
has a `pathfinding policy` byte at `+0x7c`: `cut-out` (0), `static` (1),
`none` (2). **The simulation reads an instance's refs only when the policy is
not `none`** **[traced]**. With `none` it ignores the ref and casts a ray 4 wu
straight down from the point to find something else to stand on.

B40 BSP 8 agrees **[data]**: of 841 instances, 825 are `none` and 16 are
`static`. Each static one has its own object ref (flags 0, one `bsps` entry,
`bsp reference` 0, `object id` all -1) whose ref count equals its definition's
surface count. The 825 `none` instances all carry ref index 0, which is never
read. The other 14 object refs are machines and scenery.

This is the trap for converted maps: a map can ship perfect sectors and still
have every AI standing on nothing, because its instances say `none`. Pelican
Warfare's 151 instances all do.

### Firing positions name their sector

A zone's `firing positions` element (40 bytes) carries `structure bsp`, `bsp
index` and **`sector index`**: the sector the position stands on. An AI plans
its way to a position through that sector **[live]**. So whoever replaces a
BSP's sectors must look every firing position on that BSP up again.

This was found the hard way. With generated sectors and the old indices, an
Elite walked 5 wu and stopped for good, while every biped's ground record
already named a generated sector. On the same map with Bungie's data it walked
15 wu. With the indices re-resolved it crossed three instances to the player
and killed them.

## How the simulation finds a sector

### Build pin

| | |
|---|---|
| File | `Meteorite/Binaries/Win64/HaloSimulation_tag_release.dll` |
| Game build | CU4 (`config/hce-build.lock.json`) |
| Size | 14,668,560 bytes |
| SHA-256 | `C8C144404ADF61A9DE821C996682A7E66ABADD7E530397D3BBDE31C123203BF7` |
| PE timestamp | `0x6a7a740a` |
| Image base | `0x180000000` (addresses below are RVAs: add the base for Ghidra) |

### Code map

| RVA | Role | Label |
|---|---|---|
| `0x139e00` | Ground contact to sector. Takes the BSP, collision surface, instance and object of a contact and returns `sector << 16 \| bsp`. | traced |
| `0x13a080` | Picks the ref table by the kind of contact (shell, instance, object), applies the instance policy gate, and falls back to the ray. | traced |
| `0x179250`, `0x179510` | Evaluate one ref: fetch the surface's plane, project the point, walk the node tree. | traced |
| `0x13a4d0` | The fallback: a ray 4 wu down from the point. | traced |
| `0x16d960` | Returns a BSP's pathfinding data. Every reader goes through it. | traced |
| `0x13d4618` (data) | The per-BSP runtime table the accessor reads. | traced |
| `0x7e2660` (data) | The projection table (below). | traced, bytes read from the file |
| HS function 464 | `generate_pathfinding`. Points at the shared return-false handler, like the other script functions the release build stubs out ([re/restored_cheats.md](re/restored_cheats.md)): **the game has no generator**. | traced |

### The lookup, step by step

```text
sector_of(contact):
    if contact has no instance and no object:
        refs = pathfinding.bsp2d_refs                      # shell
        frame = world
    else if contact is on an instance:
        if instance.pathfinding_policy == none:
            return whatever a ray 4 wu down finds
        object = pathfinding.instanced_geometry_refs[instance]
        refs = pathfinding.object_refs[object].bsps[0].bsp2d_refs
        frame = the instance's definition (local)
    else:                                                  # a scenario object
        entry = the object_refs element whose object id matches
        refs = the entry's bsps element whose bsp reference matches the hit BSP
        frame = the object's node that owns that BSP (local)

    ref = refs[contact.surface]
    if ref is a node:
        p = point taken into `frame`, then projected to 2D by the
            dominant axis of the surface's plane
        while ref is a node:
            node = pathfinding.bsp2d_nodes[ref & 0x7fffffff]
            ref = node.left if dot(node.n, p) - node.d > 0 else node.right
    return ref                                             # a sector, or -1
```

For an instance the local frame is `(p - position) / scale`, then dotted with
the instance's forward, left and up vectors.

**The projection** is Halo's usual one: drop the axis the surface's plane
normal is largest on, and order the other two by the sign of that component.

| Dominant normal axis | Positive | Negative |
|---|---|---|
| x | (y, z) | (z, y) |
| y | (z, x) | (x, z) |
| z | (x, y) | (y, x) |

The table in the DLL is three rows of six 16-bit numbers, negative case first:
`2 1 0 | 1 2 0`, `0 2 1 | 2 0 1`, `1 0 2 | 0 1 2`.

So **node planes live in the definition's local 2D frame, while vertices (what
links name and paths are planned on) are world space.** A generator that only
ever gives a whole surface to one sector never needs a node, and never needs
the local frame.

### What is never read

Only the two ref evaluators touch `object refs`, checked across every caller
of the accessor and every user of the per-BSP table **[traced]**. They never
read `vertex offset` or `node_index`. B40's `vertex offset` is not even its
object's first vertex (object 0 uses vertices 0 to 103 and says 64)
**[data]**. A generator can write the object's first vertex and 0.

### Finding these functions again after a game update

Addresses move with every build. Two anchors survive:

- **The projection table.** Search the DLL's read-only data for the 36 bytes
  `02 00 01 00 00 00 01 00 02 00 00 00 00 00 02 00 01 00 02 00 00 00 01 00 01
  00 00 00 02 00 00 00 01 00 02 00`. The functions that reference it include
  the ref evaluators.
- **The instance element.** The policy gate compares a byte at `+0x7c` of a
  148-byte (`0x94`) element with 2, right after indexing a table by
  `instance * 0x94`. The function doing that is the table picker; its one
  caller chain leads up to the contact-to-sector function.

Then confirm with data, not by eye: run `pf_objects` on B40 BSP 8 and check
that the 16 static instances still own one object ref each.

## What a writer must get right

Proved by `pf_roundtrip`, which empties B40 BSP 8's `object refs` and rebuilds
all 30 of them (3,192 refs) to a file **byte-identical** to the original
**[data]**:

1. An `object refs` element owns a `bsps` block, which owns `bsp2d refs`. A new
   element needs its tag-block wrapper **with those children**. Writing the
   elements alone leaves a scenario that no longer parses: the element says one
   `bsps` entry and the block is not there.
2. The order that works: write all elements with a donor element's wrapper
   (`blam_tag::blockedit::element_with_wrapper`), then per object replace the
   `bsp2d refs` leaf, then the `bsps` element.
3. Per static instance: one object ref (flags 0, `object id` -1), one `bsps`
   entry (`bsp reference` 0), and exactly as many refs as the instance's
   definition has collision surfaces.
4. Objects are per **instance**, not per definition: vertices are world space,
   so two instances of one definition need different sectors.
5. Set the instance's policy byte to `static` in the structure BSP, or nothing
   is read.
6. Keep existing object refs at their indices: scenario objects name a
   pathfinding object by index (`pathfinding references`).
7. Re-resolve the `sector index` of every firing position on the BSP (above).
8. Clear `seams`, `jump seams`, `doors` and `giant pathfinding data`: they name
   links and sectors that are gone.

An earlier attempt at object refs crashed Blood Gulch 2 to 5 seconds after
bots moved, even with every ref `-1`. The lookup above would have handled
those values, and the writer of that attempt wrote elements without wrappers,
so the missing child blocks are the likely cause **[inferred]**.

## The generator

`blam_sbsp::pathfinding::Pathfinding::build` turns a welded collision into
sectors, one per walkable surface, with steps and crack seams
([bots.md](bots.md) has its rules). That is enough for a converted map whose
ground is a few thousand polygons in the shell.

`blam_sbsp::navmesh` is the front end for ground that is instanced geometry: a
triangle soup, unwelded and far too fine to be one sector each.

0. **Cut covered floor** (`cut_covered`, when `headroom` is set). Where a
   floor has a floor of another piece of ground less than `headroom` above
   it, the upper one is the ground and the lower one is cut away, along the
   upper one's outline or the line the two cross on. Both then end on the
   same line, which is what a seam needs (above). See "Structures on the
   terrain" below.
1. **Weld** each instance's triangles by position. Instances stay separate
   objects, as in shipped data.
2. **Choose floors**: not breakable, normal z at least 0.65 (about 49 degrees),
   accepted by the caller's filter.
3. **Merge** floors that share an edge while the union stays near-convex in
   plan (`dent`), within `plane_tolerance` of one plane and walkable.
4. **Straighten** the borders between merged floors: drop a corner that only
   two polygons touch when the border moves by no more than `border` in plan.
   Borders against walls and open edges only lose corners that are exactly in
   line.
5. **Build** sectors from the result. Crack seams become intersection links
   between instances.
6. **Drop ground too small to matter** (`min_ground`, in plan area, seams
   counted as connections) and build again. A rock's top costs links and
   serves nobody.

Every sector is a union of whole source triangles or of pieces of them, so
every surface gets one plain ref and no nodes are written. A surface that was
cut names the sector of its largest remaining piece.

### Structures on the terrain

A base slab or a capture platform lies on the terrain without sharing an edge
with it. The terrain runs on underneath, so it has no edge where the slab
ends, and an intersection link needs an outer link on both sides. Left alone,
each structure is a separate piece of ground: small ones are dropped by
`min_ground`, and an AI standing on one has no sector.

`cut_covered` gives the terrain that edge. The rule is geometry only, with no
notion of "terrain" or "structure":

- For two floor polygons of **different pieces of ground**
  (`ground_pieces`: what the generator would connect with nothing cut), the
  lower one loses the part of it where the upper one is less than `headroom`
  above. Per pair the gap is linear, so the part is a convex clip: the upper
  polygon's outline and one half-plane.
- Of two floors in the same place (within 0.002 wu), the one of the smaller
  piece goes.
- What is left of a cut polygon comes back as convex pieces with the same
  object and surface. New corners are snapped to one point per place, and
  put into the neighbours' rings where they fall on an edge, so the pieces
  still share whole edges.
- The seam builder then joins the two outlines. `seam_step` says how far
  apart in height they may be: a slab 0.15 wu thick needs more than the
  default 0.1.

Three things this took to get right, all measured on Pelican Warfare:

- **The upper floor must always win.** A first version let a floor less than
  0.2 wu above another "ride" on it (the lower one stayed). With three
  layers (terrain, a slab 0.15 above, a second slab 0.15 above that) each
  rule removed a different one and nothing was left: a hole where a player
  stands. "The top of any stack stays" cannot go round in a circle.
- **Only different pieces cut each other.** PWR's terrain is several sheets
  that cross each other all over. Cutting every crossing made 80,000 sectors.
  Sheets that are already one piece of ground gain nothing from a cut.
- **Leave rock facets out first** (`min_island`). PWR has about 24,000
  pieces of floor under 50 wu² (123,000 triangles), nearly all rock facets
  near the ground. Each one cut the terrain round it. With `min_island: 50`
  they are not floor at all, and 3,400 floors are cut instead of 43,000.

A surface that is no ground itself (a facet left out, a trim strip) in an
instance the bake makes `static` would have no sector, where the engine's own
fallback for a `none` instance is a ray 4 wu down. In `ground` mode the bake
gives such a surface the sector under its middle within those 4 wu.

### Checked against Bungie's data

B40 BSP 8, the 16 static instances, default options (`pf_generate --static
--compare`):

| | Ours | Shipped |
|---|---|---|
| Surfaces with a sector | 1,036 | 1,039 |
| Surfaces where both agree | 2,075 of 2,078 (the 3 misses are 0.4 wu² of step faces) | |
| Sectors on static geometry | 531 | 466 (632 less the 166 flagged `mobile`) |
| Walkable area (wu²) | 2,346 | 2,349 |
| Rings and hint chains | all valid | all valid |
| Intersection hints | 814 | 194 (whole BSP) |

Ours joins more seams than Bungie's, because the crack rule (edges within
0.1 wu, less than a step apart in height) pairs floors Bungie leaves to door
and machine sectors. That has not caused trouble on converted maps, and has
not been tried on B40 itself.

### Sized on Pelican Warfare

1,199,986 triangles in 150 instances (the shell copy left out),
`--ground 1000 --tolerance 0.5 --ring 24`, 8 seconds:

| `dent` = `border` | Sectors | Links (limit 65,535) | Vertices | Hints |
|---|---|---|---|---|
| 0 (exactly convex) | over the limit: about 35,000 sectors and 98,000 links | | | |
| 0.6 wu | 19,290 | 62,109 | 40,024 | 6,330 |
| 1.0 wu | 15,197 | 51,844 | 33,890 | 6,252 |

All 18 terrain tiles come out as **one connected ground** of about 452,000
wu², joined tile to tile by intersection links. Three structures stay separate
pieces of about 3,100 wu² each: the two bases (centred near (-590, -80) m and
(600, -80) m, by the home flags) and a third of the same size at (0, 690) m.
They sit on the terrain without sharing its edges, so no seam joins them to it.

Two limits on that result. It was run with **every floor accepted, river and
lake beds included** (the simulation has no water, so they are ordinary
collision); with deep water cut out, as the feasibility note recommends,
connectivity has not been measured. And the output was checked only for closed
rings and consistent hints: nothing yet verifies that each source triangle lies
inside its sector's straightened polygon to within `border`.

Why exactly convex sectors do not fit: the terrain is an irregular triangle
mesh, and a convex polygon made of whole triangles can only have a handful of
corners before the mesh's edges zigzag out of it. Loosening the flatness
tolerance changes almost nothing (the merge is blocked by shape about 200 times
as often as by flatness). Two ways out:

- **Accept borders that move** by up to a metre or three between two walkable
  sectors (the `dent` and `border` settings above). An AI near a border may be
  told it is in the neighbouring sector. Shipped data is loose in the same way
  (one sector in twelve dents), but by how much the planner minds is untested.
- **Cut triangles with `bsp2d nodes`**, as Bungie does, so sector borders are
  free of the triangle mesh. The lookup side is traced (above); a node writer
  is not built.

### In the bake, and in the game

`level bake` takes a `blam.pathfinding` setting and regenerates the level's
BSP's pathfinding from its instances (`Baker::instance_pathfinding` in
`crates/blam-cli/src/level.rs`):

```json
"blam": {
  "active_bsps": [8],
  "pathfinding": { "instances": "static", "plane_tolerance": 0.2, "dent": 0, "border": 0, "min_ground": 0 }
}
```

`instances` says which instances get sectors:

- `"static"`: those whose policy is already `static`. The BSP is not changed,
  so its payload may come from `--pathfinding-bsp <payload>` for a level that
  plays on a canvas BSP as shipped.
- `"ground"`: every instance that carries walkable ground once `min_ground`
  has dropped what is too small to matter. The bake sets those instances'
  policy byte to `static` in the BSP's payload before packing it, so this
  needs `--bsp <index>=<payload>`. No instance is ever named: the choice
  follows from the collision.

An instance reuses the object ref it already has when that object is its alone
and the right size; otherwise a new one is cloned from an existing instance
object. When the BSP is the map's own, the canvas BSP's `instanced geometry
refs` are replaced by one entry per instance of the new BSP. Refs of the shell
and of objects that are not instances become none.

With `blam.bots` in the same level, the bots lane does not build sectors from
the shell: its spawns, firing positions and areas go on the generated ground
([bots.md](bots.md)).

**The live gate** is `examples/levels/bot_b40_pathfinding.level.json`: Slayer
on Silent Cartographer's stock BSP 8 with B40's own squads, and the BSP's
pathfinding replaced by ours. The same level without the setting is the
control, since Bungie's data is known to run there.

```bash
mjolnir level bake examples/levels/bot_b40_pathfinding.level.json --standalone BPF \
  --pathfinding-bsp <B40 BSP 8 payload> --world <B40.umap> --install-test
```

Result, PC 1, solo, 2026-11-22 **[live]**:

| | Generated | Bungie's (control) |
|---|---|---|
| Bake | 16 instances, 2,078 polygons, 531 sectors, 2,671 links, 407 seams; 16 object refs reused, 14 emptied; 338 firing positions re-resolved, 0 lost | unchanged |
| Ground records (unit `+0x9e8`) | name generated sectors, on five different instances | name Bungie's sectors |
| An AI on a `none` instance | keeps a sector found by the ray down | same |
| Elite, after `ai_place` | walked 17 wu across three instances to the player, killed them, followed the respawn and killed again | walked 15 wu to a firing position |
| Crash | none in about four minutes | none |

Read with `mjolnir live objects --group bipd` for positions and the object
address, then the ground record at the address `+0x9e4` (surface), `+0x9e8`
(`sector << 16 | bsp`) and `+0x9ec` (instance).

That run reused all 16 object refs and changed no policy byte. The Grunts of
the other two squads stood still in both runs.

**Pelican Warfare**, the same day **[live]**. The level's own bake plus
`blam.bots` (spawns at six capture sites) and

```json
"pathfinding": { "instances": "ground", "plane_tolerance": 0.5, "dent": 1.0, "border": 1.0, "max_corners": 24, "min_ground": 1000 }
```

| | |
|---|---|
| Instances chosen | 24 of 151 carry ground; all 24 set from `none` to `static` |
| Object refs | 0 reused, **24 added** (cloned from B40's), 30 of the canvas BSP's emptied |
| Tables | 15,197 sectors, 51,844 links, 3,126 seams, 33,890 vertices |
| Read back | rings all close; 24 static instances, each with its own object and one ref per surface (8,192 on a terrain tile) |
| Bots lane | 6 of 6 spawns on the main ground; 1,854 firing positions in 16 areas |
| Ground records | AI on three different terrain tiles each named a generated sector |
| Movement | four AI ordered to distant areas all arrived: an Elite went 365 wu (1.1 km) in about three and a half minutes, others 285, 220 and 155 wu |
| Crash | none in about six minutes |

So new object refs, a policy byte we changed, and borders loosened to 1 wu all
run. What it does not show: a second player (AI far from a joiner are known to
lag), AI fighting on this ground, a route into a base, or a match under the
Warfare rules (the test sat in warm-up with one player).

One AI was placed on a pad at a capture site, which is a small structure of
its own and got no sectors (`min_ground` dropped it). It had no sector while
it stood there, and still walked off onto the terrain when ordered.

**Pelican Warfare with structures joined**, the same day **[live]**. The same
level with

```json
"pathfinding": { "instances": "ground", "plane_tolerance": 0.5, "dent": 1.0, "border": 1.0, "max_corners": 24, "min_ground": 1000, "min_island": 50, "headroom": 0.5, "seam_step": 0.25 }
```

| | Before | With the cut |
|---|---|---|
| Floors cut | none | 3,471 |
| Pieces of ground over 100 wu² apart from the main one | 3 bases of about 3,100 wu², 4 pads of 200 to 370, about 30 ledges | the ledges only (all 0.6 wu or more above the ground at every edge) |
| Main ground | 452,243 wu² | 455,129 wu² |
| Instances with a pathfinding object | 24 | 35 |
| Tables | 15,197 sectors, 51,844 links, 3,126 seams | 15,928 sectors, 55,361 links, 2,827 seams |
| Surfaces naming the sector beneath | none | 13,955 |
| AI on the north pad (instance 149) | no sector | sector 15904, then walked 110 wu off the pad when ordered |
| AI ordered to the area of the west base | not tried | walked 100 wu from open terrain onto the base floor (instance 148) and stopped on a firing position there, in that floor's own sector |
| Crash | none | none in about six minutes |

What this does not show: an AI walking onto the centre platform (none was
ordered there: tasks name areas of 490 m, not spots, and AI did not chase a
player 40 wu away in warm-up), a second player, or a fight. The base floors
are single level slabs; nothing here has a ramp or a second storey.

A level baked `--standalone` on a canvas world ships no world of its own, and
the lobby refuses to host such a map (it checks that a world named after the
codename is mounted). For a test, ship the canvas world under the codename
with `--world`.

### Run it

```bash
# what shipped sectors look like
cargo run --release -p blam-sbsp --example pf_stats -- <scenario> [bsp index]
# generate for a BSP's static instances and compare with the scenario's own data
cargo run --release -p blam-sbsp --example pf_generate -- <sbsp> --static --compare <scenario> <bsp index>
# size a converted map
cargo run --release -p blam-sbsp --example pf_generate -- <sbsp> --ground 1000 --tolerance 0.5 --dent 0.6 --border 0.6
# how a scenario's object refs sit on its instances
cargo run --release -p blam-sbsp --example pf_objects -- <scenario> <sbsp> <bsp index>
# prove the nested-block writer on shipped data
cargo run --release -p blam-sbsp --example pf_roundtrip -- <scenario> <bsp index>
```

## Open questions

| Question | Why it matters | How to settle it |
|---|---|---|
| How does the planner use a sector's shape? | Decides how loose `dent` and `border` may be. | Trace the callers that read `links` and `vertices` through the accessor at `0x16d960`. |
| What do `threshold` and the unflagged outer links mean? | We write neither as Bungie does. | Same trace; then compare AI behaviour on a link with and without the flag. |
| How loose may borders be before the AI misbehaves? | PWR ran at 1 wu with AI walking in straight lines over open ground. Nothing was watched near obstacles or in a fight. | Watch AI around rocks and at tile seams at 0.6 and 1.0 wu; the tighter setting fits too (62,109 links). |
| Does an AI use a seam with a step in it as readily as a flat one? | Shipped seams are flat to 0.005 wu; ours at a base's edge step up to 0.25 wu. One Elite crossed one. | Watch several AI cross a base's edge both ways, and try `seam_step` at 0.15. |
| Should a rock stop an AI? | Facets under `min_island` are not floor, and the terrain runs on under the rock, so the planner sees open ground there. | Cut the terrain where any collision stands on it (the `cut-out` policy's job in shipped data), and watch AI walk a boulder field before and after. |
| What else stores a sector index? | Firing positions did, and stale ones stopped the AI. | Search the scenario's AI blocks (zones' areas, squads' starting locations, user hints) for sector fields, and watch an AI that uses each. |
| Does generated output look like shipped output? | Only rings and hints are checked today. | Run `pf_stats`' measures (winding, flatness, dent depth) on generated tables, and add a check that every source triangle's centre lies within `border` of its sector's polygon. |
| Is the ground still connected with deep water cut out? | The PWR run accepted river and lake beds. | Pass a water mask as the generator's floor filter and count the pieces again. |
| What are `seams`, `jump seams`, `doors` and `giant pathfinding data`? | Unknown blocks in the same element. | Census them across the shipped scenarios first. |

## History

- 2026-10-25: Bungie's own object-ref pathfinding ran in a Megalo Slayer match
  on B40's stock BSP 8 ([re/ai_in_multiplayer.md](re/ai_in_multiplayer.md)).
- 2026-10-30: shell pathfinding for converted maps shipped with the bots lane
  ([bots.md](bots.md)).
- 2026-11-22: the lookup traced in Ghidra, the writer proved by round trip, the
  instance generator built and sized on Pelican Warfare
  ([pwr_ai_feasibility.md](pwr_ai_feasibility.md)).
- 2026-11-22: the generator wired into `level bake` and run live on B40 BSP 8.
  Stale firing-position sector indices found and fixed.
- 2026-11-22: `instances: "ground"` and the bots lane on generated ground; run
  live on Pelican Warfare.
- 2026-11-22: shipped seams measured; `cut_covered` joins structures to the
  terrain they stand on; run live on Pelican Warfare.

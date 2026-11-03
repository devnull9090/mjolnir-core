# Crossline 0.3

Crossline / **FRB** is a **96 × 160 m** Red versus Blue arena and construction
showcase for two to sixteen players. It has four times the area of version
0.2. Raised bases and galleries remain **4.5 m** above the ground, inside a
continuous **9 m** perimeter with open sky. Two stock Warthogs use the ground
route beneath the raised platforms; the player and vehicles retain their
original scale.

**This is a local development build.** The layout has passed offline
collision and clearance checks. Private Forge tests verified walking from
ground level up the lift ramps and rising through the column, a controlled
gallery landing from an earlier drop-in setup, transparent
glass with collision on both sides, animated green fields and teleporting
in both directions. Local tests also verified door collision, saved modes and
visible opening/closing, and a nearby Warthog holding the gate open until
removed. Full vehicle traversal, including driving beneath the gate, still
needs testing with compatible development mods.
The [validation record](../../docs/forge_pack_validation.md) separates these
Crossline 0.3 checks from earlier versions' results.

## Routes and showcase

The bases have four team-owned spawn positions each, weapons and cover.
Four neutral starts in the lower midfield support free-for-all Slayer.
Two broad
approaches per base connect the lower landings to the 48 × 24 m upper decks.
Each approach is 8 m wide and rises 4 m over 32 m. Side galleries and a central
crossbridge connect the bases above an open, 8 m-wide ground vehicle corridor.
Conventional ramps remain available around the utility demonstrations.

| Area | What to try |
| --- | --- |
| Red and blue bases | Large 16 m platforms, long walls, full-size coloured lights and green teleporter housings |
| West lane, south | An automatic vehicle gate with an 8 × 5.5 m opening, then a pedestrian door with a 4 × 3.5 m opening |
| West lane, middle | Solid glass, a glazed window and a glass corner; walk around the panes, not through them |
| West lane, north | Connected T, cross and wide L-shaped bridge footprints, with their actual open cutouts |
| East lane, south | An 8 m-wide high ramp, a short wide ramp and a guarded landing |
| East lane, middle | A gravity lift beside the upper gallery; steer west onto the adjacent landing, or use the main ramps |
| East lane, north | A narrower high ramp and landing connected to the gallery |

Door panels sit in front of their frames and have unobstructed upward travel.
Both doors have ground-level bypasses. The lift's launch column has open sky;
its tuning is a separate live-game check. Green teleporter housings and pads
surround two linked gameplay markers on channel **alpha**. Their exits face
back into the arena, with room to leave the trigger before returning.

All **twenty new Foundry Wide pieces** appear in the authored layout. The
palette contains all **38 Wide pieces**, alongside all **24 original Foundry
pieces**. There are **293 simulation objects**, two Warthogs, three weapon
pickups and two equipment pickups: **300 authored objects**, leaving **351**
of the native 651 object slots for editing. Decorative ground markings do
not consume those slots. This map does not provide bot navigation.

## Play and edit

After a fresh launch, press **Enter** at the title screen and finish sign-in.
From the main menu, choose **Crossline → Team Slayer**, **Slayer**, or **Forge**. In Forge, **B**
switches between Spartan and Monitor. **Left/Right** changes categories and
**Up/Down** selects pieces; **Insert** places, **V** grabs/drops, **Page Up/Down**
changes held distance, and **comma/period** turns. **F5** saves, **F6** reloads,
and **F2** restores the authored layout. Development controls **F3**, **F4**
and **F10** select physics, position grid and rotation snap. Use Phased for
precise construction and check the final pose; native motion and collision
can affect the final angle. See [Forge controls](../../docs/forge.md).

The map pins **Foundry 0.2.0** and **Foundry Wide 0.2.0**, plus its tested CE
runtime. Compatible launcher support resolves those releases before play.
The original 24 Foundry and 18 Wide palette entries retain their order; new
Wide entries append to that prefix. Original Wide geometry is unchanged.

**Preserve older private layouts before updating.** Crossline 0.2 saves belong
to its smaller canvas and Wide 0.1.0 dependency. Keep the old `.mvar` and
`.mvar.packs` together with their matching map/pack versions; do not reinterpret
them as a 0.3 authored layout. This update changes neither Forge Canvas nor
Roadworks, their pack dependencies, or their saved layouts.

## Rebuild

Regenerate only Crossline, then run the independent map checks:

```powershell
python forge-maps/generate.py --only crossline
python -m unittest discover -s tools/forge -p test_build_maps.py
```

The source is `crossline.level.json`. The accompanying `crossline.layout.json`
records route samples, door travel, lift/teleporter clearances and showcase
object indices for validation; it is authoring data, not a private Forge save.
Tests probe transformed collision triangles, floor/ramp/gallery joins, stock
Spartan capsules, Warthog footprints and headroom, closed-door bypasses,
open-door passages, upward panel travel, glass solidity and teleporter exits.

Build Foundry and Foundry Wide, then create the 96 × 160 m canvas. Create the
output directory first if needed:

```powershell
cargo run -p blam-sbsp --example forge_canvas -- `
  forge-packs/foundry/build/donors/Levels/Halo1/Solo/B40/_Generated_/BSP_03_1_Chasm_old.scenario_structure_bsp `
  forge-packs/foundry-wide/build/canvas/crossline.sbsp `
  --width-m 96 --depth-m 160 --extent-m 96
```

Use a fresh Paks view containing the game, tested CE runtime, Foundry 0.2.0
and Foundry Wide 0.2.0. The builder selects **FRB / Crossline 0.3.0** and this
README:

```powershell
python tools/forge/build_maps.py --only crossline `
  --paks C:/path/to/combined-paks --runtime '^1.17.0'
```

Use the runtime range actually tested. The builder checks exact palettes,
container bytes, the enlarged canvas receipt and dependency pins, then writes
a fresh retained build directory without installing anything. Each archive
contains its authored level and map-owned containers; it excludes private
saves and a shared registry override. Current candidates remain unsigned and
unpublished until the normal Hub submission workflow is completed.

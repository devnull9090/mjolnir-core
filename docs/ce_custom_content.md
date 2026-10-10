# Custom Content in Community CE Maps

Community maps bring their own weapons, vehicles, scenery, devices and
scripts. [ce_map_conversion.md](ce_map_conversion.md) converts what the
stock maps have. This page records what the community maps add on top,
measured across the whole halomaps.org archive, and the order to support it
in.

The numbers come from the archive mirror ([tools/halomaps](../tools/halomaps/README.md)):
`python tools/halomaps/halomaps.py scripts` reads every map's scenario with
`tools/halomaps/cescript.py`, and `report` writes them up in `report.md`.
Figures are for the 4,264 multiplayer cache files, as of 2026-10-10.

## Where conversion stands

- **Weapons, vehicles and pickups** map by tag path to a type this game has
  (`defs/level/ce-tag-map.json` → `defs/level/palette-map.json`). An
  unlisted custom vehicle falls back to its CE vehicle type. Anything else
  is dropped and logged.
- **Scenery** is drawn and collides, as static geometry.
- **Machines and controls** are drawn in their rest pose. A gear's moving
  part is animated in the material; nothing else moves. They are not
  simulation objects, so doors, lifts and switches do nothing.
- **Scripts** are never read. Every converted map runs the generated
  startup script, and the bake clears the blocks scripts name (object
  names, device groups, trigger volumes, cutscene flags).

## What the archive carries

| | Maps |
|---|---|
| Custom weapons | 2,667 |
| Custom vehicles | 1,925 (595 with a custom aircraft, CE's `human_plane`) |
| Machines or controls | 1,087 (119 link them through device groups, 75 script them) |
| Scripts | 759 (median 3 scripts each) |
| Trigger volumes | 455 |
| AI encounters | 877 (83 script `ai_*`) |
| `switch_bsp` | 57 (Hugeass's day/night: a trigger volume switches to its second BSP) |

Many "custom" tags are the same few tags passed between maps. The energy
sword is in 456 maps, the SMG in 325, the battle rifle in 324, the LAAG
turret in 223, the Gauss Warthog in 198.

## This game has more than the canvas places

The canvas level (B40) places only part of the game's armoury, but the
game ships much more. The bake gives a type the canvas palette lacks an
entry of its own (the shotgun was played that way on 2026-10-03). Tags in
the containers with a full Unreal side (an animation Blueprint and a
`BlamWeaponComponent`, found with `mjolnir ue roundtrip --filter <Name>`):

- **Weapons:** battle rifle, SMG, shotgun, fuel rod (`flak_cannon`), energy
  sword, beam rifle. The campaign places the SMG (A15, A30, A50) and the
  beam rifle (A30, A50).
- **Vehicles:** Pelican, Seraph, Wraith, space Banshee, plus the Gauss
  Warthog turret.
- **Ammo:** battle rifle, shotgun and needler ammo, besides the four the
  canvas has.

The weapon group also lists Reach's DMR, needle rifle, concussion rifle,
grenade launcher, gravity hammer, Spartan laser, plasma launcher and focus
rifle. Most have no Unreal packages under their names, and none is known
to draw.

So the archive's most shared custom weapons now map to the game's own
(`ce-tag-map.json`): every energy sword, battle rifle and SMG variant
listed there, the Hunter fuel rod, the brute plasma rifle (as the plasma
rifle), the H2/H3 rifles, pistols, rockets and shotgun, and the H2/H3
grenades, power-ups and ammo. The battle rifle and SMG fall back to the
assault rifle. CE's own ammo pickups (assault rifle, pistol, rocket,
shotgun, needler) were not mapped at all and are now. Custom aircraft
(Coldsnap's jets and fighter-bombers, CE type `human_plane`) spawn as
Banshees, the one aircraft players fly here; the shared Pelicans and
Wraiths as the game's own. Whether players can drive this game's Pelican
and Wraith is the open question for those two.

**Checked in game (2026-10-10, Night-Lockout, a 9.0-rated halomaps map with
the battle rifle, SMG, energy sword, beam rifle and brute plasma rifle):**
every placed weapon spawns in the simulation (`mjolnir live objects`), and
each has its own Unreal actor at its spot, drawn with the game's art
(`BP_BattleRifle_WeaponActor_C` with its scope and ammo display,
`BP_SMG_WeaponActor_C`, `BP_Shotgun_WeaponActor_C`,
`BP_EnergySword_WeaponActor_C`). Picking them up and firing them is still
to be played.

A vehicle with spawn flags 0 is in no game type's set: only a script
creates it. Coldsnap's and Hugeass's fighter-bomber wreck pieces are
vehicle tags of that kind (CE type `human_jeep`), and used to be placed as
14 extra Warthogs; they are dropped now, until scripts are converted.

## Scripts

### Reading them

A cache file keeps no script source, only the compiled trees: `script
syntax data` (20-byte nodes) and `script string data` (every name token's
text). A call's first child is its function's name, so the source comes
back without CE's function table:

    python tools/halomaps/cescript.py --hsc maps/hugeass.map

Protected maps decompile too (Yoyorast Island V2: 51 scripts).

### What they call

759 maps have scripts. Matched by name against this game's function table
(`defs/hce/console.json`, 1,695 functions), 352 (46%) call nothing this
game lacks. The gaps are concentrated, and most are cheap:

| Step | Maps covered |
|---|---|
| By name, today | 352 (46%) |
| Drop server, console, debug and save calls (`sv_say` alone is 154 maps) | 427 (56%) |
| Drop the engine globals with no use here (`rider_ejection` 109 maps, network rates, cheats) | 509 (67%) |
| Expand `object_create_anew_containing` and friends to the names they match, at compile time | 523 (69%) |
| HUD show/hide and help text | 548 (72%) |
| `vehicle_test_seat_list`, `unit_set_seat`, the flashlight (maps use it as a button) | 582 (77%) |
| `switch_bsp`, `structure_bsp_index` (needs a second BSP) | 618 (81%) |

What's left is mostly CE's encounter AI (`ai_dialogue_triggers`,
`ai_attach`, `ai_magically_see_players`), nav points and cinematic screen
effects.

A name in the table is not a working call. Arguments, value types and
behaviour need checking, and the reference for that is in hand: the MCC
editing kit has CE's original campaign `.hsc` sources
(`HCEEK/data/levels/*/scripts`), and this game's scenarios carry the
developers' ported campaign scripts (`mjolnir script --tag <CODE>
--decompile`), so the two show how each function was translated.

### Compiling them

`mjolnir compile` builds a tree from `.hsc` for this game, with full type
checking. Its vocabulary is the corpus the campaign's scripts call
(`defs/hce/scripting.json`, 483 functions) plus the engine's own table
(`--console`, by default `defs/hce/console.json`): the 782 live functions
the campaign never calls compile with the signatures the engine declares.
Stubs stay unknown on purpose, so a script calling one fails until the
translation pass decides what to do with it.

Decompiled and compiled that way, the pilot maps fail only on the gaps in
the table above:

| Map | Scripts | Errors |
|---|---|---|
| Hugeass | 11 | `vehicle_test_seat_list` 52, `switch_bsp` 2 |
| Coldsnap | 24 | `vehicle_test_seat_list` 198, `*_containing` 16, flashlight 6, nav points 8, `switch_bsp` 2, `structure_bsp_index` 1 |
| Yoyorast Island V2 | 51 | `*_containing` 2, `rasterizer_decals_flush` 2 |

`vehicle_test_seat_list` (vehicle, seat label, units) has a counterpart
here, `vehicle_test_seat` (vehicle, `unit_seat_mapping`), but the seat
mapping names this game's seats, so the shim maps CE's seat labels onto the
chassis vehicle's.

One thing the compile doesn't see yet is the scenario's names. A script
names objects, trigger volumes, cutscene flags and device groups, and the
compiler types those names from the scenario; until the bake carries those
blocks across from the CE scenario instead of clearing them, a name the
compiler can't type compiles as a `string_id`, with a warning.

### Plan

1. ~~Widen the compiler's vocabulary to the engine's table.~~ Done.
2. Carry object names, trigger volumes, cutscene flags and device groups
   into the baked scenario.
3. A translation pass between decompile and compile: drop, rename, shim and
   expand per the table above, with a per-map report of what was dropped.
4. Pilot on Yoyorast Island V2 (51 scripts: the shield doors, teleports,
   permutation swaps) and Hugeass (vehicle teleports, the fighter-bombers
   breaking apart, tank spawns off a switch). Scripts run in the
   simulation, as the campaign's do in co-op; test with two PCs.

## Devices

Most device placements need no script: CE doors open for whoever walks up,
and platforms and lifts run on their own. So the device work is making
machines and controls real simulation objects: a Blam machine tag (cloned
from a shipped one) with the CE model's collision, and an Unreal visual
that follows the object. The visual is the hard half; see below.

## Vehicles and weapons of their own

New objects need two halves. The simulation's half is a tag, and the tools
already clone and edit tags (the health pack from battle rifle ammo, the
two-way teleporter, the Spartan fix). The visual half is the bottleneck:
assets cooked with stock Unreal don't load in this game, so geometry ships
only by rewriting a mesh the game already ships
([ue_mesh_write.md](ue_mesh_write.md)). That covers rigid parts,
not new skeletons or animations.

So a custom vehicle or weapon is a **chassis**: a clone of the closest
stock one, with CE's numbers copied onto it (speeds and turn rates;
magazine, fire rate, damage, zoom) and the custom mesh swapped in where it
is rigid. A jet: the Banshee's seats and flight, the jet's hull and
collision. A weapon keeps a stock weapon's first-person arms and
animations. Custom first-person models and walkers (Coldsnap's Mythos and
Nirvash) are out of reach.

## Not converted yet

- Sounds a custom map keeps inside its `.map`.
- A map's second BSP (Hugeass's night).
- AI encounters (CE encounters; this engine has squads).
- The flamethrower: none ships.

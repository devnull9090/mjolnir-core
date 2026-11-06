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
  unlisted custom vehicle falls back to its CE vehicle type. Anything else,
  and a tag listed with no type, is dropped and logged.
- **Custom vehicles** can run as themselves: clones of a shipped vehicle
  with CE's model and numbers ([custom_vehicles.md](custom_vehicles.md),
  Yoyorast's Mongoose).
- **Scenery** is drawn and collides, as static geometry.
- **Machines and controls** are drawn in their rest pose by default. A gear's
  moving part is animated in the material. A map that goes through the device
  lanes gets real machines and controls
  ([ce_map_scripts.md](re/ce_map_scripts.md), Yoyorast and Sanctuary Final).
- **Scripts** of a map that isn't translated are not read: it runs the
  generated startup script, and the bake clears the blocks scripts name.
  `tools/ce_scripts/ce_translate.py` turns a map's own scripts into HSC the
  engine loads.

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
Banshees, the one aircraft players fly here, until a clone of their own
replaces them ([custom_vehicles.md](custom_vehicles.md)); the shared
Pelicans and Wraiths as the game's own. Whether players can drive this
game's Pelican and Wraith is the open question for those two.

**Checked in game (2026-10-10, Night-Lockout, a 9.0-rated halomaps map with
the battle rifle, SMG, energy sword, beam rifle and brute plasma rifle):**
every placed weapon spawns in the simulation (`mjolnir live objects`), and
each has its own Unreal actor at its spot, drawn with the game's art
(`BP_BattleRifle_WeaponActor_C` with its scope and ammo display,
`BP_SMG_WeaponActor_C`, `BP_Shotgun_WeaponActor_C`,
`BP_EnergySword_WeaponActor_C`). Picking them up and firing them is still
to be played.

A vehicle with spawn flags 0 is in no game type's set: only a script
creates it. That covers wreckage and real vehicles alike, so the flags alone
don't decide. Coldsnap's and Hugeass's fighter-bomber wreck pieces and the
Mythos hull are vehicle tags of that kind (CE type `human_jeep` or
`human_tank`). They used to be placed as Warthogs and a Scorpion, and
`ce-tag-map.json` lists them with no type now. Yoyorast's Mongooses and
Hugeass's Scorpions have the same flags and are real vehicles, so they stay
placed, in every game type's set.

## Scripts

### Reading them

A cache file keeps no script source, only the compiled trees: `script
syntax data` (20-byte nodes) and `script string data` (every name token's
text). A call's first child is its function's name, so the source comes
back without CE's function table:

    python tools/halomaps/cescript.py --hsc maps/hugeass.map

Protected maps decompile too (Yoyorast Island V2: 51 scripts).
`tools/ce_scripts/ce_hs.py` does the same for the script work in
[ce_map_scripts.md](re/ce_map_scripts.md); `cescript.py` also reads a map's
devices and vehicle types for the archive's survey, and `--names` exports
what its scripts refer to.

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
(`defs/hce/scripting.json`, 483 functions) plus every function of the engine's
own table (`console.json` beside the corpus) that the campaign never calls,
with the signatures the engine declares. The engine compiles a scenario's
source at load, so that source is what a converted map ships
([ce_map_scripts.md](re/ce_map_scripts.md)).

Decompiled and compiled with nothing translated (2026-10-10), the pilot maps
failed only on the gaps in the table above:

| Map | Scripts | Errors |
|---|---|---|
| Hugeass | 11 | `vehicle_test_seat_list` 52, `switch_bsp` 2 |
| Coldsnap | 24 | `vehicle_test_seat_list` 198, `*_containing` 16, flashlight 6, nav points 8, `switch_bsp` 2, `structure_bsp_index` 1 |
| Yoyorast Island V2 | 51 | `*_containing` 2, `rasterizer_decals_flush` 2 |

`ce_translate.py` closes those gaps: drops, renames, seat labels and
`*_containing` expansion, with a report of what it left out. Where that stands,
map by map, is in [ce_map_scripts.md](re/ce_map_scripts.md).

## Devices

Most device placements need no script: CE doors open for whoever walks up,
and platforms and lifts run on their own. So the device work is making
machines and controls real simulation objects: a Blam machine tag (cloned
from a shipped one) with the CE model's collision, and an Unreal visual
that follows the object. Yoyorast and Sanctuary Final work this way on a
host ([ce_map_scripts.md](re/ce_map_scripts.md)).

## Vehicles and weapons of their own

New objects need two halves. The simulation's half is a tag, and the tools
already clone and edit tags (the health pack from battle rifle ammo, the
two-way teleporter, the Spartan fix). The visual half is a cloned Blueprint
with CE's model in it. [custom_vehicles.md](custom_vehicles.md) has the recipe
and [ce_native_support.md](ce_native_support.md) the direction: a CE object's
own tags decide what it does and how it looks. Weapons are still to come, and
walkers (Coldsnap's Mythos and Nirvash) stay out of reach: their legs are
animation only.

## Not converted yet

- Sounds a custom map keeps inside its `.map`.
- A map's second BSP (Hugeass's night).
- AI encounters (CE encounters; this engine has squads).
- The flamethrower: none ships.

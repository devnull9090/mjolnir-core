# Forge

**Status:** 2026-11-01. On any converted multiplayer map, host only (the
fireteam side is built but waits on a two-PC test). Layouts
(save, load, start a game with one), object properties, markers, turning
and budgets are in mods 0.42.0 (MJOLNIRForge 0.3.0).
First released in mods 0.34.0 with CE runtime 1.14.0; placing from the
palette needs MJOLNIRForge 0.2.0 and CE runtime 1.15.0 (the panel).
**How it works:** [re/forge_engine.md](re/forge_engine.md).

Halo Reach's Forge is still inside Halo: Campaign Evolved's simulation.
MJOLNIR switches it on: you turn into the Monitor, fly around the map, and
pick up, move, drop and delete its objects. The game's own Forge engine does
the work; MJOLNIR gives it keys and a HUD. As the Monitor you can also
place new objects from the map's palette: weapons, vehicles, equipment and
scenery.

Community model sets use [Forge packs](forge_packs.md). Maps declare their
supported pack pieces when baked; the Hub catalog and launcher handle their
releases and dependencies. That guide includes the original Foundry set,
authoring commands and saved-layout compatibility checks.
The [Foundry validation record](forge_pack_validation.md) separates observed
game behavior from the remaining collision, visual and multiplayer checks.

## Starting a Forge game

1. MULTIPLAYER → HOST GAME, pick a map.
2. Pick **FORGE** as the game type. It is listed once MJOLNIRForge is
   installed and the CE runtime pack has the monitor fix.
3. Start. A panel at the top left says `FORGE`.

For scripts and tests: `mjolnir_auto host <CODE> forge private` at the
console.

## The HUD

![Holding an assault rifle as the Monitor: the target card with the weapon's silhouette, the distance bar and the control bar](images/forge-hud-holding.jpg)

- **Top left:** FORGE, whether you are the Monitor or your Spartan, and the
  map.
- **Centre:** the Monitor's cursor. Blue when it rests on nothing, white
  on an object, green while you hold one.
- **Beside the cursor:** what you aim at or hold. It shows the kind of object,
  its name, the game's own picture for a weapon, and what the keys do to it.
  While you hold something, a bar shows how far out it is (1 to 60 m).
- **Bottom:** every key, dimmed when it does nothing right now, and a short
  note of what the last key did ("DELETED Shotgun").

![Aiming at a shotgun: WEAPON, Shotgun, and the keys that act on it](images/forge-hud-aiming.jpg)

![A Ghost just placed from the palette: the VEHICLES category on the right, the Ghost held at the cursor](images/forge-palette.jpg)

- **Right, as the Monitor:** the palette. The category (WEAPONS, VEHICLES,
  EQUIPMENT, SCENERY) between its keys, the object Insert places with its
  picture, and the category's list around it. A dimmed entry is one the map
  cannot place right now.

The HUD ships in the CE runtime pack (`pakchunk980-MJOLNIRFORGEUI-Windows`).
Without it, a plain text panel shows the same things. The HUD from CE runtime
1.14.0 has no palette panel; with it a note names each object you select.

## Keys

| Key | What it does |
|---|---|
| **B** | Turn into the Monitor, or back into your Spartan |
| **V** | Pick up what the cursor is on; press again to drop it |
| **Page Up / Page Down** | Push a held object away, or pull it in |
| **Delete** | Delete what you hold (or, holding nothing, what you aim at) |
| **N** | Duplicate the target at the cursor |
| **Insert** | Place the palette's selected object at the cursor; you hold it, ready to move |
| **Left / Right** | Previous / next palette category |
| **Up / Down** | Previous / next object in the category |
| **F5** | Save this map's layout |
| **F6** | Load the saved layout, replacing the objects on the map now |
| **F2** | Go back to the map's own layout (the saved one is kept in `layouts\history`) |
| **K** | Team of the target: neutral, red, blue |
| **L** | Megalo label of the target (the map's labels in turn, then none) |
| **J** | Respawn time of the target: 0, 5, 10, 15, 30, 45, 60, 90, 120, 180 s |
| **O** | Spawn order of the target: 0 to 9 |
| **P** | Teleporter channel of the target: alpha through zulu, then 26–31 |
| **, / .** | Turn what you hold or carry, or the next marker you place, 22.5° left / right |

As the Monitor you move with your usual movement keys and the mouse; jump
flies up.

To use other keys, create `keys.txt` in the MJOLNIRForge mod folder with
lines like `grab=F7` (actions `toggle`, `grab`, `duplicate`, `delete`,
`nearer`, `farther`, `place`, `prev_category`, `next_category`, `prev_item`,
`next_item`, `save`, `load`, `revert`, `team`, `label`, `respawn`, `order`, `channel`,
`rotate_left`, `rotate_right`; key names as UE4SS spells them, such as `PAGE_UP` or
`LEFT_ARROW`).
The defaults are keys the game does not use. G, C, Z and X are taken.

## The palette

A map's palette is its scenario's own Forge palette. Converted maps baked
since 2026-10-24 list the whole CE arsenal: 13 weapons, 6 vehicles (not the
campaign's flyers), grenades, power-ups and ammo, and the map's scenery
(spawn points, teleporters, flag stands, health packs). Maps baked before
list only the kinds they already place, so you can place and duplicate
those but not, say, a Wraith on Blood Gulch, until the map is republished.
There is no limit on how many of each, unless the map sets one (*Budgets
and quotas*).

Maps baked from 2026-11-01 also have a **blocks** palette: a Covenant crate
and the Covenant portable shield, the only shipped pieces that are already
Forge-ready. Maps can also include original namespaced model sets such as
Foundry through [Forge packs](forge_packs.md).

## Object properties

Every object Forge places carries properties the game types read. K, L, J
and O change the target's (what you hold, else what you aim at); the target
card shows its team and label.

- **Team**: a red flag stand is where the red flag starts in CTF; spawn
  points with a team are that team's.
- **Label**: what a game type looks objects up by. CTF finds flag stands by
  `ctf_flag_return` and team spawns by `ctf_spawn_red` / `ctf_spawn_blue`.
  The list is the map's own labels.
- **Respawn time** and **spawn order** for weapons, vehicles and equipment.

## Markers: flag stands, spawn points, health packs, teleporters

These have no physics, so the Monitor cannot drag them the way it drags a
weapon. Forge handles them its own way:

- **Insert** puts one where the cursor is, facing the way , and . set.
- **V** on one picks it up: it leaves the map and the HUD shows you carrying
  it, properties and all. Turn it with , and . and press **V** again to put
  it down at the cursor. **Delete** while carrying throws it away.
- **N** copies one, properties included.
- They are invisible in game (the bases' stands are separate scenery), and
  the cursor cannot land on them, so Forge aims at the nearest one within
  about a metre of your crosshair.

A flag stand made this way works in CTF: on Blood Gulch, a red stand placed,
labelled `ctf_flag_return`, saved, and the map then hosted as CTF got the red
flag.

### Teleporters

The scenery palette can include **Teleporter Sender**, **Teleporter Receiver**
and **Teleporter 2-Way**. Place an entrance and exit with the same channel;
**P** changes the targeted marker's channel, shown on its target card. The
game's simulation handles travel, including the receiver's facing. Use different
channels for separate routes. A two-way pair uses the same channel at both ends.

New Insert placements start on alpha with a player-only cylinder about 1.07 m
in radius, 1.83 m above and 0.30 m below the marker. Moving, duplicating and
saving preserves the marker's channel and trigger dimensions. Keep the receiver
clear of walls and leave room for the Spartan. The engine supports 32 endpoints
in total, including both ends of each route. Foundry's portal frames and pads
are visible architecture; place functional teleporter markers separately.

### Pack lights

Foundry's light strip and warm/red/blue pylons have optional catalog light data.
MJOLNIRForge attaches a movable point light to each active piece's actor, so
light follows placement and rotation and is removed when the piece disappears.
This also runs in ordinary game modes and when a saved layout starts a match.
The first 64 active lights receive illumination; additional fixtures still
render. Lights currently cast no shadows. Colors and brightness are properties
of the piece's catalog, so use the red or blue variant for team bases.

These utility additions have automated coverage; the
[validation record](forge_pack_validation.md) distinguishes live game evidence
from checks still awaiting a playtest.

## With your fireteam

**For now FORGE is host only:** the lobby refuses to start it with fireteam
members, as before. Everything below is built (FORGE has its own insertion
slot, 5, and the Forge DLL's client guards are in), but the first two-PC
test (2026-11-01) lost the second PC to a GPU crash while it loaded, so the
lobby's refusal stays until one passes. Lifting it is the members check in
MJOLNIRLobby's `startGame`.

Fireteam members who are in the lobby, or who join a FORGE game under way,
would start Forge too, and need MJOLNIRForge and the CE runtime pack the host has.
Each of them can be the Monitor, pick up, drop, delete, duplicate and place
weapons, vehicles and equipment: those go to the host's game as the engine's
own Forge requests, as in Reach. The rest stays with the host for now: saving
and loading layouts that start games, object properties, turning, and
markers (flag stands, spawn points). A FORGE game is never listed in FIND
GAMES.

On 2026-11-01 PC 2 joined PC 1's fireteam, PC 1 started FORGE on Blood Gulch
(with the refusal lifted), and PC 2 travelled and started the sandbox engine
as a client ("BGL starts under the sandbox engine, FORGE (client travel)").
PC 2 then dropped out during the load and went off the network. It had had
a GPU crash at its title screen ten minutes before, with no Forge code
running, so the hardware is the likely cause, but nothing proves it yet.

## Budgets and quotas

A map can limit what Forge places: a budget, a price per object, and a most
of each kind. The simulation enforces them, as Reach's Forge did: an object
over its quota or over the budget is refused ("THIS MAP CAN'T PLACE ANOTHER").
The palette shows `placed/most` and the price beside an object that has them,
and the budget spent in its title. The text panel shows the same.

Maps set them when they are built (`blam.forge` in the level file,
[level_format.md](level_format.md)). The maps released so far set none, so
there is no limit.

## Layouts

F5 saves what is on the map now, everything Forge can move, as a layout:
`layouts\<MAP>.mvar` in the MJOLNIRForge mod folder (Blood Gulch is
`BGL.mvar`). It works as the Monitor or as your Spartan, in a FORGE game.

**A map with a saved layout starts every game with it**: FORGE, Slayer, CTF
or any other game type on that map. Saving again replaces it; the one before
moves to `layouts\history` with the time in its name. To play the map as it
shipped, press F2 in a FORGE game (or move the file out of `layouts`).

F6 puts the saved layout back on the spot, undoing everything since the last
save. Objects you are holding are dropped first.

A layout file is a Halo Reach map variant (`.mvar`), the same format MCC
uses, so `cargo run -p blam-megalo --example mvar_summary -- BGL.mvar`
lists what is in it. Layouts belong to one map: the file name says which.

## Not there yet

- **Several layouts per map, and picking one in the lobby.** One saved layout
  per map for now; `layouts\history` keeps the older ones.
- **Layouts for your fireteam.** A saved layout is used when you host;
  players who join see the host's objects.
- **A Forge menu** (object lists, properties).
- **Tilting.** , and . turn about the vertical only.
- **Markers are invisible**: aim near where you put them.
- The cursor only reaches things in plain view: it stops at walls and the
  ground.

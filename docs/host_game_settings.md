# Host game settings

Plan for a host-only GAME SETTINGS screen in the multiplayer lobby: what
classic Halo CE let a host change, what our runtime can change, and how a
choice gets from the lobby to every machine's simulation. Researched
2026-10-04; nothing here is built yet.

Sources, marked on each fact:
- **V**: read from CE's own tags. Custom Edition `ui.map` (814 widgets, 168
  string lists) and `bloodgulch.map` (globals weapon list).
- **D**: behaviour read in the Halo CEA (Xbox 360) and Xbox Halo 1 decomps,
  under the facts-only rule (see the h1 decomp note: never copied, never
  built; every fact restated in our words).
- **OS**: OpenSauce's game variant header.
- **Ours**: our code (`crates/blam-megalo`, `mods/`), with file references.

## What classic CE offered

### Menus (V)

MULTIPLAYER → CREATE GAME → map → game type (a STANDARD / CLASSIC / CUSTOM
bank above a list, with a side panel showing the description and current
rules) → server settings (name, password, connection type, MAX PLAYERS 2-16)
→ START GAME.

EDIT GAMETYPES → a variant → CHANGE NAME (24 characters), GAME OPTIONS (pick
the mode, then its own page), PLAYER OPTIONS, ITEM OPTIONS, VEHICLE OPTIONS,
INDICATOR OPTIONS, TEAMPLAY OPTIONS, OK. Every page is the same shape: a
column of label + spinner rows, OK, and a help box that describes the
highlighted value.

### Universal settings (V labels and values; D effects)

| Page | Setting | Values | Classic Slayer |
|---|---|---|---|
| Player | Number of lives | infinite, 1, 3, 5 | infinite |
| Player | Maximum health | 50, 100, 150, 200, 300, 400 % | 100 % |
| Player | Shields | yes, no (no also removes overshields) | yes |
| Player | Respawn time | instant, 5, 10, 15 s | instant |
| Player | Respawn time growth | none, 5, 10, 15 s per death; enemy kills refund a step | none |
| Player | Odd man out | the last player killed waits for the next death | no |
| Player | Invisible players | permanent camo; camo pickups removed | no |
| Player | Suicide penalty | none, 5, 10, 15 s added on a death that is not an enemy kill | 10 s |
| Item | Infinite grenades | spawn with the maximum; grenade pickups removed | no |
| Item | Weapon set | 13 sets, below | Classic |
| Item | Starting equipment | custom (the map's per-mode profile) or generic | custom |
| Vehicle | Vehicle respawn time | never, 30 s, 1, 1.5, 2, 3, 5 min | never |
| Vehicle | Vehicle set, per team | default, none, warthogs, ghosts, scorpions, rocket warthogs, banshees, turrets, custom (0-4 of each) | warthogs |
| Indicator | Objectives indicator | motion tracker, nav points, none | motion tracker |
| Indicator | Other players on radar | all, friends, none | all |
| Indicator | Friend indicators on screen | yes, no | yes |
| Teamplay | Friendly fire | off, on, shields only, explosives only | on |
| Teamplay | Friendly fire penalty | none, 5, 10, 15 s | none |
| Teamplay | Auto team balance | yes, no | no |
| Mode page | Time limit | none, 10, 15, 20, 25, 30, 45 min | none |
| Mode page | Team play | yes, no (CTF always teams) | no |

Vehicle counts only cap how many of the map's own placements spawn.

### Mode settings (V labels; D effects)

| Mode | Setting | Values |
|---|---|---|
| Slayer | Kills to win | 5, 10, 15, 25, 50 |
| Slayer | Death bonus / kill penalty | run faster after each death / slower after each kill |
| Slayer | Kill in order | you score only on your assigned target |
| CTF | Captures to win | 1, 3, 5, 10, 15 |
| CTF | Assault | carry your own flag into the enemy base |
| CTF | Single flag | off, or teams swap attack and defence every 1, 2, 3, 5, 10 min |
| CTF | Flag must reset | touching your flag does not return it |
| CTF | Flag at home to score | |
| King | Score to win | 1, 2, 5, 10, 15 min |
| King | Moving hill | moves every minute |
| Oddball | To win | 1, 2, 5, 10, 15 min (kills for juggernaut) |
| Oddball | Ball type | normal, reverse tag, juggernaut |
| Oddball | Ball count, random start | 1-16 balls |
| Oddball | Speed / trait with ball, trait without | slow, normal, fast; none, invisible, extra damage, damage resistant |
| Race | Laps, race type, team scoring | normal, any order, rally |

### Weapon sets (V names; D behaviour)

A set swaps every placed weapon (and starting weapon) for another; the flag
and ball never change, and weapons outside CE's stock list pass through.

| Set | Result |
|---|---|
| Normal | as placed |
| Pistols | pistols, with plasma pistols for the Covenant side |
| Rifles | assault rifles and plasma rifles |
| Plasma | plasma pistols and rifles, plasma grenades |
| Sniper | sniper rifles (pistols stay) |
| No sniping | sniper rifles become shotguns, pistols assault rifles |
| Rockets | rocket launchers only |
| Shotguns | shotguns only |
| Short range | close-range weapons |
| Human / Covenant | one side's arsenal, with that side's grenades |
| Classic | no flamethrower or fuel rod |
| Heavy | rockets, flamethrowers, fuel rods |

### Presets (V names; D settings)

Classic bank (the Xbox originals): Slayer, Slayer Pro, Elimination, Phantoms,
Endurance, Rockets, Snipers, Oddball, Reverse Tag, Accumulate, Juggernaut,
Stalker, King, King Pro, Crazy King, Race, Rally, CTF, Invasion, Iron CTF,
CTF Pro, Team Race, Team Rally, Team Ball, Team King, Team Slayer. Standard
bank (PC): Slayer, Oddball, Juggernaut, King, Crazy King, Race, CTF, Assault,
Team Slayer, Team Oddball, Team King, Team Race.

## What our runtime can change

Our game types are Megalo variants (`.mglo`), built once in CI
(`.github/workflows/release-mods.yml:96-97`, Slayer and CTF only) by
`mjolnir megalo write`. Everything except the mode, score to win, rounds,
CTF flag reset and health packs is a fixed value in `write_base`
(`crates/blam-megalo/src/variant.rs:633`). The base options sit at the same
bit offsets in every file we write, so a host's choice can be patched into a
copy of the file before it is staged.

Routes: **patch** = overwrite a fixed field before staging; **script** = new
Megalo script or user options; **data** = new tag data in the runtime pack;
**none** = no counterpart.

| CE setting | Route | Status |
|---|---|---|
| Kills / captures to win | patch (the score field) | verified |
| Time limit | patch (misc time limit) | untested: does the round end, and the HUD has no clock |
| Number of lives | patch (respawn lives) | untested: does the round end when all are out |
| Respawn time | patch | 5 s verified, other values untested |
| Suicide penalty | patch | untested |
| Friendly fire on/off, betrayal penalty | patch (social flags) | untested; currently written 0, so FF may be off today |
| Shields, maximum health | patch (base player traits) | untested; Reach trait value tables unverified on this build |
| Invisible players | patch (camo trait) | untested |
| Radar, friend indicators | patch (sensor traits) | untested; the UE HUD may not follow them |
| Infinite grenades, starting grenades | patch (traits) | untested |
| Grenades / powerups on the map | patch (map options) | verified (0 removes, 0x1f places all) |
| Team play (Slayer) | script: Team Slayer | small |
| Respawn growth | patch exists; CE's kill refund needs script | untested |
| Odd man out, death bonus, kill penalty, kill in order | script | |
| CTF assault, single flag, flag must reset, flag at home | script (CTF script options) | |
| Oddball, King and their options | script + data (ball object, hill boundaries) | |
| Weapon sets (snipers only etc.) | data: remap tables in the object type list we ship, selected by the variant's weapon set | needs RE of where the sim applies the remap |
| Vehicle set, vehicle respawn | data: vehicle remap tables, or script deleting vehicles; respawn is baked at conversion | |
| Starting equipment | patch (spawn weapon traits) | encoding unverified |
| FF shields-only / explosives-only, per-team vehicle sets, Race | none without major work | |

## Design

### The screen

One cooked screen, `WBP_MJOLNIRGameSettings`, generic so new settings never
need a re-cook:
- left: page buttons (GAME, PLAYERS, ITEMS, INDICATORS, TEAMS; more slots
  hidden until used) and a PRESET spinner over them;
- middle: up to 12 rows of `label   < value >`; Lua names each row, fills
  its values and hides the rest;
- right: CE's help box, describing the highlighted row's current value;
- footer: RESET (back to the preset) and DONE.

GAME SETTINGS sits in the lobby menu under GAME TYPE (host only). The lobby
card lists the settings that differ from the preset under the mode's
description, so clients see the rules too. Only settings that work are
shown; nothing is greyed out "coming soon".

### Getting a choice into every simulation

1. The host's choices are one `key=value` string, saved beside
   `last_game.txt` and sent to clients in the existing `lobby` broadcast
   (`MJOLNIRLobby/Scripts/main.lua`, broadcastLobby), and once more just
   before StartCountdown.
2. On every machine, the level loader copies `variants/<mode>.mglo`,
   patches the fields, and stages the result as it does today.
3. Field offsets come from `mjolnir megalo write --layout`, a JSON emitted by
   CI beside each `.mglo`, so the Rust writer stays the only definition; a
   Rust test round-trips patched files.
4. MJOLNIRHud reads the staged `native\variant.mglo`, not the installed one.
5. Joins into a match under way get the string from the hub listing (one new
   field) and patch before their held world is released.

Risk: the Ice Fields note says map options can lag one match behind when the
variant changes mid-session. Per-round settings (score, time, respawn,
traits) are read at the round reset and should not lag; map options and
weapon sets might. Verify first.

## Phases

1. **Patch-only settings.** Score, time limit, lives, respawn time, suicide
   and betrayal penalties, friendly fire, shields, maximum health,
   invisibility, radar, friend indicators, grenades and powerups on the map.
   Each is verified in game before it is shown. Presets that fit: Classic
   Slayer, Slayer Pro, Elimination, Phantoms, CTF, Iron CTF (without its
   Scorpion rule), CTF Pro (without generic equipment).
2. **Script.** Team Slayer, respawn growth with refunds, odd man out, CTF
   rules (assault, single flag, flag must reset, flag at home), then Oddball
   and King with their options and presets (Juggernaut, Crazy King ...).
3. **Data.** Weapon sets (Snipers, Rockets ...) and vehicle sets, after the
   remap is understood.

## Open questions

1. When does the sim decode the staged variant relative to creating placed
   objects (the one-match lag)?
2. Does the time limit end a round by itself, and does elimination (lives)?
3. Is friendly fire off in team games today?
4. Do Unreal's radar, waypoints and camo follow the sim's traits?
5. Does a client's variant affect play, or only the host's?
6. How does the sim apply the variant's weapon set through the object type
   list remap?

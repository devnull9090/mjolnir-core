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
| Time limit | patch (misc time limit) + script (`with_time_limit`) | verified 2026-10-04: the engine counts the clock but never ends the round; the trigger does |
| Number of lives | patch (respawn lives) | untested: a GPU driver reset hit the one test (cause unknown) |
| Respawn time | patch | verified: 0 (instant) and 15 s |
| Suicide penalty | patch | verified: 10 s added to a suicide |
| Friendly fire on/off, betrayal penalty | patch (social flags) | untested; currently written 0, so FF may be off today |
| Shields | patch (shield trait 1) | verified: shield vitality 0 of 70 |
| Maximum health | patch (health trait) | untested: trait 4 leaves maximum body vitality at 45; damage scaling unmeasured |
| Invisible players | patch (camo trait 4) | verified: first-person active camo |
| Radar, friend indicators | patch (sensor traits) | radar trait 1 left the motion tracker drawn: the UE HUD does not follow it |
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
- left: five page buttons (GAME, PLAYERS, ITEMS used so far), RESET (every
  setting back to its default) and DONE;
- middle: twelve rows of `<   LABEL   value   >`; clicking the row steps it
  forward, `<` and `>` step either way; Lua names each row, fills it and
  hides the rest; a value away from its default is drawn in the accent;
- right: CE's help box for the highlighted row: its label, value and what
  it does.

GAME SETTINGS sits in the lobby menu under GAME TYPE (host only). The lobby
card lists the settings away from their defaults under the game type, for
the host and every client. Only settings that work are shown; nothing is
greyed out "coming soon". Presets (Snipers, Rockets, Elimination ...) wait
for the settings they need.

### Getting a choice into every simulation (built)

1. The host's choices (`MJOLNIRLobby/Scripts/settings.lua`, saved in
   `MJOLNIRLobby\game_settings.txt`) become one line of variant fields,
   `key=value;...`, with a score to win per game type (`score.slayer`,
   `score.ctf`) so the line stays right when a post-game vote changes the
   game type.
2. The host writes it to `MJOLNIRLevelLoader\variant_settings.txt` as it
   starts a game; fireteam clients get it as the third field of the `lobby`
   message and write the same file. A host from before settings sends no
   third field, which clears it. A join from FIND GAMES clears it too (or
   takes the listing's `settings`, once the hub carries one).
3. On every machine the level loader patches the line into its copy of
   `variants/<mode>.mglo` (`variant_settings.lua`, keeping only that game
   type's score) and stages the result.
4. MJOLNIRHud reads the staged `native\variant.mglo`: the score to win and
   the time limit for its round clock.
5. `tools/tests/test_variant_settings.lua` patches the Rust writer's default
   variants with a settings line and must get, byte for byte, what the
   writer makes with the same settings (`settings_fixtures_are_current`
   keeps the fixtures current); `test_game_settings.lua` patches every
   choice of every option.

A player who joins from FIND GAMES, including into a match under way, gets
the line from the hub: a public host sends it with its listing and every
heartbeat (`settings`, migration 0015), and `/join` returns it, which
games.lua writes for the loader before the join goes out. A listing from a
host without settings returns null, and the joiner runs the variant's own
rules.

A changed variant applies at the next match: test C0 ran straight after C1
from the post-game vote with the new file.

### The round clock

The engine counts the round clock down and raises `30_seconds_remaining`
and `10_seconds_remaining`, but shows nothing. MJOLNIRHud shows `M:SS` under
TO WIN when a time limit is set: counted from the first spawn (the clock
starts about 0.8 s after it), set right by those two incidents, and on a
fireteam client by the host, which sends its count every 30 s.

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

# Pelican Warfare: waves, reinforcements and moving zones

Design for the second round of Pelican Warfare (PWR) features, agreed
2026-11-22. It extends [the prototype](pelican_warfare.md); read that first
for the slot layout, the native adapter and the HUD bridge.

Four features, in build order (1-3 are built; 4 is a design, see [AI feasibility](pwr_ai_feasibility.md)):

1. **Warmup countdown**: a large centred countdown before insertion.
2. **Reinforcement waves**: the dead wait, spectate their team, and fly back
   in together on a shared clock.
3. **Moving zones**: each match picks where A, B and C are.
4. **Covenant waves**: AI arrive on Spirit dropships, fight both teams and
   contest the zones.

Decisions taken with the owner (2026-11-22): Covenant are hostile to both
teams; Covenant inside a zone block capture and payout the way an enemy player
does; reinforcements use one shared 60-second clock for both teams.

## What the spikes found

- **Global numbers are full.** Megalo holds 12 global numbers and the variant
  uses all 12 (`variant.rs` refuses a 13th). New published values must be packed
  into existing slots or derived from them. Object numbers have room (5 of 8).
- **Randomness exists.** CU4 keeps Megalo action 25 *Random Number* and action 96
  *Get Random Object With Label*, plus *Delete Object* (3).
- **No engine respawn hold is needed.** Instead of holding dead players in the
  engine's respawn queue (the `respawn_sync_with_team` bit is only inferred), the
  dead respawn after the normal short delay straight into a reinforcement Pelican
  parked at their team's flight start, which already exists for insertion.
- **A spectator camera is available.** `SetViewTargetWithBlend` already drives
  the view in MJOLNIRFlyCam and the HUD bench. A camera actor attached to a
  teammate's biped actor follows it with no Lua loop.
- **The Spirit dropship exists as a vehicle.** It is
  `objects/Vehicles/covenant/tuning_fork/tuning_fork` (its sounds are
  `spirit_anim_door_*`; Unreal has `Vehicles/covenant/SpiritDropShip`). It has 31
  AI passenger seats (`fork_p_*`). It can be cloned the way
  `tools/level/build_warfare_pelican.ps1` clones the Pelican.
- **PWR has no AI data yet.** No pathfinding, squads, zones or objectives. The
  `blam.bots` bake lane has never run on a 2 km heightfield shell. That, and the
  16 Havok proxies the AI memory notes, are the open risks for feature 4.

## Protocol

The map's metadata keeps `protocol 20569` and layout 3, so the published map
does not change. The Megalo rules get their own magic in slot 2, **20570**.
The native DLL, HUD and variant ship together; each refuses the other's old
revision.

Slot 3 (the clock) changes meaning by phase:

| Phase | Slot 3 |
|---|---|
| 0 warmup | `-1` while waiting for the minimum players, else whole seconds left |
| 1 insertion | the insertion duration in seconds (was also published in phase 0) |
| 2 combat | combat seconds elapsed (unchanged) |

Native reads the insertion duration only in phase 1. Slot 6 (scratch, never
replicated) counts ticks inside the second in phases 0 and 2.

## 1. Warmup countdown (built)

Megalo counts the warmup down in whole seconds in slot 3. The status line says
"DEPLOYMENT IN 0:23" (or "WAITING FOR PLAYERS" while slot 3 is `-1`), and the
last ten seconds count down large in the middle of the screen
(`MJOLNIRHud/Scripts/warfare_countdown.lua`), gold for the last three, then
"DEPLOY" for two seconds as insertion begins.

The number is a Lua-made TextBlock in the game's own countdown face
(`Font_Oxanium` Medium, from `WBP_MatchStartCountdown`) at 420 pt. A TextBlock's
font can be set from Lua only before the widget first reaches the screen;
SetFont afterwards changes nothing, and a hand-built font struct passed to
SetFont crashed the game. Render scale works but blurs.

Verified 2026-11-22 in a solo match at 4K, and the clock reached both joiners
on three game copies.

## 2. Reinforcement waves (built)

- **Schedule.** Wave k (k >= 1) leaves at combat second k x 60 and flies 30
  seconds of its team's insertion route (`reinforcement` in `layout.json`,
  generated into `warfare_layout.h` and written to the state file for the HUD).
  It is derived from the replicated combat clock, so every machine agrees with
  no extra slot. The 30-second flight at the 30 m/s cap reaches the middle of
  the map; the forced exit is at 27 s (the insertion's 54/60).
- **Sortie.** The per-player state machine (`warfare_core.h`) takes a
  `warfare_sortie` instead of "phase 1": the insertion is sortie 0, the wave
  that parks before departure k is sortie k. A rider stays aboard only the
  sortie they boarded, so an insertion rider still seated at combat start
  leaves even though a reinforcement Pelican is parked.
- **Boarding.** After death the player respawns at home (Megalo's five
  seconds) and is boarded while their team's Pelican is parked at
  `pwr_<team>_flight_start`. Only a player still waiting where they spawned is
  taken: on foot within 40 m of the home flag. Someone who walked off or took a
  vehicle is never pulled out. Every machine checks "parked" itself (the
  transport near its flight start), so a client never tries to board a Pelican
  that is not there. Late joiners and players not admitted at roster lock take
  the next wave. A seat is allocated at boarding (late joiners have no roster
  seat). A boarding the host never completes fails quietly and retries on the
  next wave; a client that loses the race with its host's boarding adopts the
  seat it finds itself in.
- **Transport.** The host holds the parked Pelican at its flight start with a
  bounded correction (about 2 m of sag in 55 s), flies it on schedule, and once
  it is empty after a flight makes it anew at its flight start. The first one
  replaces the insertion Pelican after the usual cleanup delay. Empty Pelicans
  fly their waves too, which keeps the schedule identical everywhere.
- **Jumping while parked** leaves at once by the normal exit (host detach,
  cabin clearance, canopy). The parked Pelican hovers over the team's base, so
  this is how to stay home. A first version that detached and teleported the
  rider home left a remote rider hanging at 550 m on three copies: the client's
  HS teleport never took. A body detached from a stationary Pelican also
  sleeps, so the fall starts with `object_wake_physics` (`WF_WAKE`).
- **Spectating** (`warfare_spectate.lua`). While seated in a parked wave with
  more than three seconds to go, the view follows a teammate on foot through a
  CameraActor attached behind their biped (`SetViewTargetWithBlend`), and the
  line adds "WATCHING <name>". Restoring the cabin view is the default on any
  other tick. The game hides actors outside its own player's view, so the
  watched body is un-hidden while watched and given back its own state after.
  There is no key to change teammates yet; with nobody to watch the cabin view
  stays.

Verified 2026-11-22: solo (board on respawn, parked countdown, departure on the
minute, forced exit mid-map, re-park, parked jump with an immediate fall) and on
three copies (host and client boarding, the host spectating its red teammate
with the body drawn, a client's flying jump and parked jump through the host
relay). Not yet seen: the wake on a client's parked jump (that branch is covered
by `test_warfare.c` only), a full match on two PCs, and more than one teammate
to watch. On three copies on one PC the simulation ran at about a third of real
speed and no descent ever registered a landing (all timed out at stage 6); the
solo run landed normally, so that looks like the rig, not the mode.

## 3. Moving zones (built)

- **Markers.** Each site may have up to six candidate `koth_hill` markers. A
  marker's spawn order is `site + 3 * candidate`, so the classic 0, 1 and 2 are
  candidate 0 and a map with one marker per site plays exactly as before
  (including today's published PWR).
- **The pick** (`warfare.rs`). Every warmup tick draws a *Random Number*
  (action 25) to stir the host's LCG, whose seed may repeat between launches.
  At launch each candidate draws a number and the highest wins per site. The
  last site then takes the first site's candidate index when it has one: on
  PWR, C's candidates mirror A's across the line between the homes, so every
  draw is equally fair to both teams. From insertion on the unchosen markers
  are deleted; only the chosen ones capture and score.
- **Publishing.** Each site's slot adds `1024 * candidate` to its packed state
  (`SiteState.candidate`), from insertion on, so riders can steer toward where
  the zones went.
- **Positions.** `layout.json` `capture_candidates_m` holds each site's extra
  spots (metres). `prepare_runtime.py` turns them into the extra markers and
  `warfare.capture_candidates` (Unreal cm) in the level file, which the HUD
  reads for the holo fields, waypoints and zone tiles. The native layout
  header carries them for the tactical map.
- **Choosing spots** (`plan_capture_candidates.py`). It searches the accepted
  runtime terrain's masks for 20 m discs that are flat (under 3 m of rise over
  26 m), walkable, dry, off the shore and nearly tree-free, at least 150 m from
  other sites, 100 m from the site's own candidates and 160 m from both homes.
  A is searched on red's half and mirrored for C; B runs along the centre line.
  It writes `capture_candidates_m` with `--write` and a preview map.
- **The map.** The candidates are scenario markers, so the map needs one
  rebake. Only the scenario tag changes: a standalone bake of
  `river-basin/native/native-level.json` (patched by `prepare_runtime.py`) with
  the release's own `pwr.sbsp` and `LPE.umap`, against the rehearsal Paks,
  differed from the sealed chunk 997 in `PWR-scenario.uasset/.ubulk` only. The
  map registry DLL must be rebuilt too: it validates variants with its own copy
  of the Megalo crate, and an old one refuses a variant that uses *Random Number*.

Verified 2026-11-22 in a solo match on the rebaked scenario: A took candidate
3, B candidate 2 and C candidate 3 (following A), announced at launch; the
tactical map and all three holo fields stood at the new spots and nothing
remained at the classic ones. Not yet played: a full match across several draws,
two machines, and the zone tiles' "you are here" rim at a moved zone.

## 4. Covenant waves

- A cloned Spirit (`pwr_spirit`, from `tuning_fork`) per wave, flown by the
  native host like the Pelicans, from a map edge to a hover point near a zone.
- AI are placed with `ai_place` (the lobby DLL's Megalo gate is already shipped),
  loaded into the Spirit's `fork_p_*` seats, and unloaded over the zone.
- Both teams are enemies: the player-team table gives red and blue campaign teams
  that Covenant fight (for example human and player) instead of the team-bot
  mapping of red covenant and blue flood.
- Contest: the capture scan counts AI as a third presence. Megalo cannot see AI
  bipeds through `EachPlayer`; the candidate routes are a Megalo object loop over
  the biped or a labelled marker the host keeps on each AI. A spike decides.
- Prerequisites, in order: bake pathfinding and an objective for PWR (and measure
  it), check the Havok proxy budget with 16 players, the fleets and a wave, clone
  and cook the Spirit.

## Testing

Each rule gets a `warfare_behavior.rs` case and each native change a
`test_warfare.c` case. Live proof needs two game copies
(`tools/remote/instances.mjs up 2`), then PC 2. Nothing is released until the
owner has played it.

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

**The director is built** (2026-11-22, not released). The parts:

- **The map** gets wave squads from the bake: `blam.bots.objectives:
  ["koth_hill"]` makes each capture spot a place to hold with its own task,
  and `blam.bots.waves` four squads per spot (an Elite, two Grunts and a
  Jackal) whose first task is that spot ([bots.md](bots.md#waves)). Pelican
  Warfare gets 44.
- **The host's lobby DLL** (`warfare_waves`, run from the Warfare tick) does
  the rest, with no map data of its own:
  - once a world, in combat, it reads each site's chosen spot from its slot
    (`SiteState.candidate`), names the place `koth_hill_<site + 3 x
    candidate>` and counts that place's squads with `ai_living_count`. A map
    without wave squads answers "no such squad", and the director stands
    down for the match;
  - on each wave time of the combat clock (the first at 45 s, then every 90
    s; a crossing, so a late tick still fires it once) it counts the live
    Covenant per site and picks the site with the fewest. On a tie an owned
    site comes before a neutral one, and equal sites take turns;
  - it places that site's free squads, `ai_force_active` and wakes each, up
    to 12 live Covenant in all (the Havok proxy budget is unmeasured);
  - it stands down for the rest of the match if the bots' team table is in
    force, since that table puts red on the Covenant's side (not yet run
    with bots on).
- The pure rules (`warfare_wave_due`, `warfare_wave_target`,
  `warfare_wave_size`) are in `warfare_core.h` with `test_warfare.c` cases.

**Solo run, PC 1** (a test game type with one minimum player and a 10 s
warm-up; the branch's DLL, HUD, map registry and game type installed for the
run): the director found four squads at each site's chosen spot (A on
`koth_hill_9`, B on `koth_hill_1`, C on `koth_hill_11`, following A). Wave 1
at 45 s went to A, wave 2 at 135 s to B (onto the north pad's structure), wave
3 at 225 s to C; all 12 walked into their spot's boundary and stayed. Wave 4
at 315 s was skipped at the cap. Two of A's squads killed by script, wave 5 at
405 s went to A and placed exactly those two. No crash in about eight minutes.

**The contest is built** (2026-11-22, not released). Megalo cannot see AI,
so the host counts them: in combat, ten times a second, the lobby DLL counts
living bipeds that no player owns and nothing carries inside each chosen
site's boundary (20 m, from 1 m below to 4 m above the marker). It writes the
count to that site marker's Megalo object number 6
(`warfare_contest` in `native/lobby/warfare_runtime.h`), every pass, zeros
included, and zeros on any stand-down. It finds the marker as global object 2
+ site and its Megalo object entry by handle (`[TLS+0x3a0]`, 0x94 bytes, the
object at `+0x38`, numbers at `+0x50`), and writes only when that entry's
number 4 equals the site's published slot. The rules (`COVENANT` in
`blam-megalo` `warfare.rs`) read it: while it is above zero neither team's
capture advances and the owner gets no payout. A game type with no writer
reads 0 and plays as before (a `warfare_behavior.rs` case).

Live, solo on PC 1: the player, made invulnerable, took site B and it paid a
point a second. Wave 1 went to B; as its four squads walked in the count went
from 1 to 4, and red's score stopped at 27 for the next two minutes with the
player still on the site. Wave 2 contested C the same way. With B's squads
erased the count went back to 0 and the payout resumed at once. Not yet shown:
two PCs.

**The Covenant take zones** (2026-11-22, not released). The same count now
captures as well as contests. Owner 3 (`OWNER_COVENANT`) is a site the
Covenant hold, and a marker's object number 7 (`COVENANT_PROGRESS`) is their
capture progress, so variants declare 8 object numbers. Per tick, on each
chosen site:

- **Covenant alone** (count above 0, no player): a team's progress drains
  toward 0 at one a tick, the teams' own rate, and the site goes neutral as
  usual. Only on a neutral site does number 7 then fill, one a tick; at the
  Covenant capture time (`covenant_capture_seconds`, default 30 s, CLI
  `--covenant-capture-seconds`) the owner becomes 3. So an undefended team
  site falls in the team capture time (15 s) plus 30 s. (The live runs below
  used the first defaults, 8 s and 20 s.)
- **A Covenant site pays nobody**, and stays theirs when they are all killed.
- **Players alone** on it drain number 7 back to 0 first (owner back to 0 as
  soon as it drops below full), then capture as on any neutral site.
- **Covenant and players together**: nothing moves, nobody is paid.
- Numbers 1 and 7 are never both non-zero (a `warfare_behavior.rs` case),
  and with no writer every published value is the old packing, tick for tick
  (another).

The published slot carries it for every machine. Owner 3 sits in the low two
bits. While number 7 is above 0, the progress field holds
`COVENANT_STEP_BASE` (34) plus its steps, past the teams' 1 to 33. `COVENANT_PRESENT`
(8192) is added while Covenant stand in the zone. That is above the candidate
bits, so the candidate is `(value % 8192) / 1024`: `warfare_site_candidate`
in `warfare_core.h`, `SiteState` in Rust and `Warfare.site` in the HUD decode
the same vectors in their tests. The director's tie-break presses a team's
site, then a neutral one, then a Covenant one. The tactical map draws a
Covenant site as unowned.

On the HUD a Covenant site is purple, and its tile reads COVENANT. Covenant
alone on a team site read UNDER ATTACK, and on a neutral one OVERRUN, with
their progress in purple. Players alone on a Covenant site read CLEARING;
Covenant with players read CONTESTED. The capture feed says "The Covenant
took zone B", "Zone A was neutralized by the Covenant", and "Red team cleared
zone B".

Live, solo on PC 1 (test bake 6), the variant with 8 object numbers:

- Wave 1 unloaded on neutral A. The published state counted the Covenant's
  progress up and A went to owner 3 about 20 s after they arrived. The tile
  turned purple and read COVENANT, the world markers went purple, and the
  feed logged it. Waves 2 and 3 took B and C the same way.
- With A's squads erased and the player on A's marker, the Covenant's
  progress ran back down. A went neutral at the first step below full, red
  captured it, and it paid a point a second.
- Wave 6 landed four Covenant on red's A. A went neutral 21 s later and
  Covenant 20 s after that, which is the drain then capture (the player had
  been killed off the zone).

Not yet shown: two PCs (the joiner reads the same replicated slots, and its
parser now takes owner 3).

**Spirits bring them** (2026-11-22, not released). The game's own Spirit
(`objects\vehicles\covenant\tuning_fork\tuning_fork`, the one B40 flies)
is placed once per capture spot, named `pwr_spirit_<place>`, not placed
automatically.

- **Routes** come from `levels/warfare/pwr/plan_transport_routes.py`. For each
  spot it walks outward to the box's edge and takes the first point where a
  transport 25 m over the ground is hidden from both homes and all 11 spots by
  the ground between, else the point at the edge. The route in climbs to clear
  the highest ground ahead by 60 m and comes down the upper hull of the ground
  (so along the mountainside, not in a dive at the end), to a hover 8 m over
  the spot. Written to `layout.json` `transport_routes_m`, into the native
  layout header (`warfare_spirit_paths`, `warfare_pelican_paths`), and by
  `prepare_runtime.py` into the map's placements.
- **A wave** with a Spirit for its spot: the host creates it (hidden),
  `ai_place`s the squads and `vehicle_load_magic`s them into `fork_p` seats,
  shows the Spirit once it has climbed, flies the route by velocity ten times
  a second (40 m/s, slowing into the hover), `unit_open`s and
  `vehicle_unload`s over the spot, holds 8 s, and flies the route back,
  hidden again from its climb point, and is destroyed. A map with no Spirit
  for the spot still walks them in.
- **Why not from behind the mountains:** the mountains are a render-only mesh
  outside the 2 km box. An object can sit out there asleep (a Banshee moved
  2.5 km out stayed and drew), but the simulation removes any awake object
  beyond the BSP, whatever the scenario's world bounds say: a Spirit given a
  velocity out there, or loaded with troops, vanished at once, also with
  world bounds widened to 4 km. So transports start inside the box, low at
  its edge, with `object_hide` until they have climbed. Measured on PWR: 10
  of the 11 spots and both Pelicans have no point at the edge hidden by the
  ground. `object_hide` does hide what Unreal draws: from the ground 120 m
  from the red staging point, looking at it, the parked Pelican was not
  drawn, appeared at once on `(object_hide pwr_pelican_red false)` and went
  again on `true` (PC 1, solo). Reading actor `bHidden` cannot show this,
  because the game culls Pelican actors itself. A Spirit is shown at its
  first route point, 30 to 70 m above its start, so it is hidden for under
  two seconds and then appears in the air at the box's edge.
- **Found on the way:** an unpiloted Spirit falls through PWR's terrain once
  awake, so it is never left without a velocity; unloading from 18 m up
  killed the passengers, hence the 8 m hover.

**Pelicans wait out of sight.** A reinforcement Pelican is made where the map
places it, at its staging point low at the box's edge behind its base, and
hidden. In the last seconds before its wave (as long as its route takes at 40
m/s, plus 3 s) it climbs and flies to its flight start, is shown there, and
leaves on the minute as before. The insertion's Pelicans are unchanged.
Boarding counts a Pelican anywhere on that way in as parked, on every
machine. A rider who jumps while it waits leaves through the usual verified
exit and, being outside the play area, is sent home by their own machine.
A map whose Pelicans are placed at their flight starts plays as before.

Live, solo on PC 1, on a test bake with the routes:

- Wave 1's Spirit started at the west edge 979 m out, climbed, crossed to
  site A nose-first (facing and travel both -48 degrees on a later wave),
  hovered, unloaded four squads (the contest counted 4 on A at once), flew back
  tail-first and was removed; wave 2's did the same at B.
- Both Pelicans parked at their staging points, climbed to 550 m in the 15 s
  before each wave, reached their flight starts and flew the route on time.
- A rider respawned into the Pelican while it was on its way in, rode the
  whole flight, left over the middle, opened the canopy and landed. A rider
  who jumped while it waited at the edge was refused cabin clearance there
  (outside the play area) and the existing failure path put them at their
  home within about 2 s.
- With the published map (Pelicans placed at their flight starts) and the new
  DLL, the Pelicans park at their flight starts as before: a Pelican made at
  its flight start skips the route.

Not yet shown: two PCs (whether a joiner hides the same objects), and the
Spirit's flight seen from the ground.

**Every place, PC 1, warm-up**: each of the 11 places' four squads placed by
script, counted after 60 s, then erased. First pass: 10 places 4 of 4, and
`koth_hill_0` 2 of 4 twice: two squads had spawned under a rock lying on the
terrain. With spawn points kept clear of overhead collision, all 44 squads
reached their spot, including the two places beside the centre platform.

**Two PCs** (PC 1 hosting, PC 3 joining, the branch's files and the bake on
both, hashes checked; the real two-player game type): waves 1 to 3 at 45, 135
and 225 s went to A, B and C, and all 12 Covenant held their spots on both
PCs. PC 3's player, moved 12 wu from site A's wave, lost its shield and half
its body within 4 s and died; so did the host's player, on the other team.
Both came back on the reinforcement Pelican. No wave AI showed in either HUD;
the scoreboard was not opened. The joiner again read different maxima for the
AI (Grunts 120 against 40 and 65), with the same files on both PCs.

Not yet done or shown:

- **No off switch.** Once a map with wave squads is published, every Warfare
  match on it has waves, at fixed times and the fixed cap.
- **No re-tasking.** A squad holds its spot for good; when a site falls
  nothing sends its squads on.
- The wave times and the cap are constants, not host settings yet.

The plan this started from:

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

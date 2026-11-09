# Lua or native: where compiled code would pay

**Status:** 2026-11-08. A read-only audit of the 15 Lua mods (about 35,000
lines) and the five shipped native DLLs, checked against PC 1's hitch history:
73 sessions, 57 per-map summaries and 6,356 logged hitches from 2026-11-06 to
2026-11-08 (RTX 5090, mostly 3840x2160 Epic). Nothing was changed. A cost
marked *estimate* was read off the code, not measured in game. Updated
2026-11-09: [the Lua-to-native channel](#the-lua-to-native-channel) and the
[roster's](#3-player-roster-from-the-simulation-for-the-hud) open questions,
measured with two test copies on PC 1.

## Short answer

- **Interpreting Lua is not where the time goes. UE4SS reflection is.** Each
  call from Lua into an engine object costs something. The lookups cost the
  most:
  - `FindAllOf` and `FindFirstOf` walk the whole object array, 15–23 ms per
    class on a converted map ([playtest_2026-10-03.md](playtest_2026-10-03.md)).
  - `StaticFindObject` takes about 2 ms for a `/Script` function path and about
    21 ms for an asset path ([performance.md](performance.md)).

  A C port that makes the same reflection calls saves only UE4SS's dispatch.
  Native code pays only when it can skip reflection, by reading or hooking the
  simulation directly.
- **Steady-state Lua is small.** Our timed loops averaged about 8 ms of game
  thread a second, under 1%. The exception is CTF and Assault: flag cloth alone
  reaches 30–35 ms a second there (3.5%).
- **Hitches hurt players more than the average does, and the biggest one was a
  Lua bug.** Every host hitched 50–70 ms every 5.1 seconds: 531 of them in three
  days, every one logged as "none of our timed loops". MJOLNIRLobby 0.24.1 fixes
  it in Lua: a 4-minute host test went from 82 hitches to 1
  ([below](#the-51-second-host-hitch-fix-first)).
- **Three jobs are worth moving into native code**, all into the lobby DLL's
  existing simulation-tick hook:
  - the Halo 2 lifts;
  - a player roster read from the simulation for the HUD;
  - the bots' bookkeeping.

  A fourth, flag cloth, should leave the CPU altogether as a cloth material.
- **Native code can take arguments and return values without files**
  (2026-11-09). A call through UE4SS's exported `LuaMadeSimple` wrapper costs
  about 0.3 µs; a file round trip costs about 1.3 ms in game. The roster is a
  go: a fireteam client's simulation holds every player's unit.
- **Everything else should stay Lua.** That covers the menus, lobby, chat,
  scoreboard, feed, match log, hub calls, map dressing and JSON. It is
  event-driven or runs at most once a second. It works on UMG and actor handles
  that only UE4SS's Lua side can hold. A C bug there is an access violation in a
  16-player match, not a log line.

## What the measurements say

Final per-map summaries in `MJOLNIRHud/hitches.log` and `hitches.old.log` on PC 1.
ms/s is game-thread time per second of play:

| Loop | Sessions | Mean ms/s | Highest ms/s | Worst single run |
|---|---|---|---|---|
| Hud tick | 57 | 3.3 | 11.9 (BGL) | 129 ms (BCK) |
| LevelLoader flag cloth | 50 | 2.4 | 35.2 (CHL) | 26 ms (YOY) |
| LevelLoader devices | 8 | 1.1 | 2.3 (YOY) | 30 ms (YOY) |
| LevelLoader lifts | 57 | 1.0 | 2.2 (IVT) | 61 ms (TMB) |
| Forge HUD | 1 | 1.3 | 1.3 (FRB) | 51 ms (FRB) |
| LevelLoader vehicle sounds | 11 | 0.5 | 1.7 (YOY) | 13 ms |
| LevelLoader pulses | 8 | 0.4 | 2.8 (CSN) | 1 ms |
| LevelLoader CTF flags | 5 | 0.3 | 0.5 | 23 ms (BGL) |
| LevelLoader footprints | 26 | 0.1 | 0.3 | 47 ms (TMB) |
| Everything else | | ≤ 0.3 | | ≤ 5 ms |

- **Hitches.** In 1,065 of the 6,356 logged hitches (17%), one of our timed
  loops ran for 1 ms or more. A single loop ran 20 ms or more in 83 hitches for
  the Hud tick, 37 for devices, 5 for lifts and 1 or 2 for the rest. The other
  83% name none of our timed loops.
- **What the logger cannot see.** It only counts loops that report through
  `MJOLNIR.work`. These are invisible to it:
  - the HUD's per-frame hook;
  - the Lobby's games, presence and identity loops;
  - every `RegisterHook` and `NotifyOnNewObject` callback;
  - `ExecuteInGameThread` closures;
  - the lifts' 50 ms step.
- **Load frames.** The LevelLoader tick held the game thread for 1,457 ms and
  1,582 ms on two TMB loads today. The HUD's first match tick took 182 ms (68–77
  ms in October).
- **Today's TMB sessions are not representative.** They were windowed at a
  55–68 ms median. The 2026-11-07 runs at 4K are.

## The 5.1-second host hitch (fix first)

**What the log shows.** The gaps between unattributed hitches cap at about 5.1 s:

- 429 came exactly 5.1 s after the one before.
- Almost none (about 40 of 5,232) came more than 5.2 s after.
- 63 of 73 sessions have them, on every map, and nearly all are unattributed.
- They average 50–70 ms against 9–17 ms median frames.
- Every one of those sessions was hosted on PC 1. A joiner's log has not been
  checked for a period.

So a job that runs every 5 seconds costs 40–55 ms whenever nothing else hitches
first.

**Cause, from the code.**
- The Lobby's games loop runs every 1,000 ms plus its own work
  ([games.lua:741-754](../mods/MJOLNIRLobby/Scripts/games.lua)). On a host, every
  fifth pass
  ([games.lua:682-688](../mods/MJOLNIRLobby/Scripts/games.lua)) sends
  `publicsession` with `Net.toClients`.
- `publicsession` is not in `Net.REPEATED`
  ([net.lua:157-164](../mods/MJOLNIRLobby/Scripts/net.lua)), so every send runs
  a fresh `FindAllOf("PlayerController")`. The code's own comment prices that at
  about 20 ms. It runs even for a solo private host with no clients.
- The same pass calls `connectionString()` every 5 s, which goes into the lobby
  DLL and back through a temporary file.
- On every pass it also builds `Host.info`. `MapLive.release` re-reads and
  decodes the launcher's `hub_state.json` once it is more than 5 s old
  ([maplive.lua:319-336](../mods/MJOLNIRLobby/Scripts/maplive.lua)), so every
  6 s. That explains the few 6.2 s gaps. Each decode of the 259 KB file costs
  about 19 ms and 4.6 MB of garbage (measured in Lua 5.4.6 outside the game).
- The Lobby runs Lua's default incremental collector, not the generational one
  the HUD and loader moved to in PR #206.
- None of this reports to `MJOLNIR.work`, which is why the hitch log names "none
  of our timed loops".

**Measured and fixed (MJOLNIRLobby 0.24.1).** The A/B ran on PC 1: a private
Blood Gulch Slayer host, 1280x720, standing still, `mjolnir_hitches reset`, then
about 4 minutes.

- **The old code has two chains.** `FindAllOf("PlayerController")` timed at
  25–26 ms in game, to find one controller. It made a 33–37 ms frame every 5 s.
  The `hub_state.json` decode made another every 6 s. Every 30 s the two land on
  the same frame, which is the 63–65 ms hitch. That is the other half of the
  excess.
- **The fix:**
  - `Net.clients` keeps one controller walk until the set of player states in
    `GameState.PlayerArray` changes, and walks nothing while the host is alone.
  - `MapLive.release` decodes only when the file's text changed.
  - `Host.info` is built only for a public game.
  - The games, presence and identity loops now report to the hitch log.

| | Before (0.24.0) | After (0.24.1) |
|---|---|---|
| Window | 4 min 08 s | 4 min 12 s |
| Median frame | 6 ms | 7 ms |
| Hitches | 82: 74 under 50 ms, 8 of 50–100 ms | 1: 20 ms, during a 15 ms lifts run |
| Worst frame | 65 ms | 20 ms |
| Lobby games / presence | not timed | 0.5 / 0.6 ms/s, worst 4 / 2 ms |

Timing the games loop also shows a one-off 109 ms run at the main menu, on its
first pass after the game starts. It is probably the lobby DLL's one-time
pattern scans; that has not been checked.

**Related, on the host.** The LevelLoader's incident relay also runs
`FindAllOf("PlayerController")` at most every 5 s
([main.lua:2193](../mods/MJOLNIRLevelLoader/Scripts/main.lua)). That is about
19 ms on a frame where something died.

## The HUD's scans and lookups (measured and fixed)

**Measured on PC 1, 2026-11-08.** Blood Gulch, 1280x720 windowed, hosting
private with 8 legendary Spartan bots and standing still. `mjolnir_hitches
reset` came once the bots were in, then `mjolnir_bots 0` and `mjolnir_bots 8`,
so a bot start fell inside the window. Each run lasted 4 to 4.5 minutes.

| | Before (MJOLNIRHud 0.19.0) | After (0.19.1) |
|---|---|---|
| BGL Slayer: Hud tick | 16.6 ms/s, worst 308 ms | 13.9 ms/s, worst 10 ms |
| BGL Slayer: the frame the bots restarted in | 313 ms | no hitch |
| BGL King: Hud tick | 14.4 ms/s, worst 58 ms | 13.7 ms/s, worst 8 ms |
| YOY Slayer: Hud tick | (not run) | 13.6 ms/s, worst 12 ms |

The two BGL after-runs had per-section timing added to the tick (a few
`os.clock` calls, logged only for a tick over 20 ms). The YOY run is the build
as shipped. An earlier after-run on BGL without that timing is under "What is
left".

**What the scans cost.** The map pools 271 bipeds, and their numbers grow over
the first seconds of a match (78 known at 3 s, 271 at 40 s):

- 46 `BP_SpartansBipedActor_C`;
- 75 each of the Elite, Grunt and Jackal classes;
- no Brutes or Marines.

One `FindAllOf` took 31–39 ms a class in that match, so a 7-class `fillPool`
took about 250 ms. The 308 ms run was a rescan 7 s after the bots started:
`blind()` counted a class as unwatched until an actor of it had been seen, and
Brutes and Marines never are.

**The fix.**
- **One watch.** Every bot class derives from the Blueprint
  `BP_BaseBipedActor_C`, which derives from the native class
  `/Script/BlamSynchronization.BlamObjectActor`. One `NotifyOnNewObject` on that
  native class, armed when the HUD loads, sees each biped as it is made
  (`Scripts/bipeds.lua`). It saw all 271.
- **The watch's own cost.** It also fires for other Blam objects: 1,516
  callbacks while a map's pools filled, 30 ms in total, spread over the frames.
- **Why not a Blueprint class.** A watch on a Blueprint class needs the class
  loaded, and a Blueprint class can be unloaded and loaded again between maps.
- **`StaticFindObject` by path,** measured in the same match:
  - `Default__KismetSystemLibrary` about 1 ms;
  - `BlamDeviceComponent` and `BlamMeshSynchronizationComponentBase` about
    0.1 ms;
  - `StaticMeshActor` under 0.02 ms.
- **The hill.** A hill move asked for two library lookups a panel. Both hill.lua
  versions were timed in the same match: 55–62 ms before, 2–5 ms after.

**What is left.**
- **The steady cost with bots: fixed in Lua too.** `liveActors` called
  `IsValid` and `K2_GetActorLocation` on all 271 pooled bipeds every 0.25 s,
  about 2,200 calls a second. It now reads only the actors off the origin,
  plus a placing bot's class while it is placed and every class every 5 s.
  The A/B ran back to back on a quiet PC 1 (the earlier runs' 13–14 ms/s were
  inflated by other work on the machine): Hud tick 11.6 ms/s, worst 20 ms,
  before; 5.0 ms/s, worst 9 ms, after (BGL, 8 bots, 4 min each).
- **The first bot start of a session: about 43 ms,** timed around the whole
  poll; later matches' starts stayed under 20 ms. Most of it is probably
  `mjolnir_bots_enable`, which scans the simulation DLL's code for the
  `ai_place` gate once per launch (read from the source, not timed on its own).
- **The relay's `FindAllOf("PlayerController")`: 32–37 ms,** once a hosted
  match, now on its own poll.
- **An unexplained cluster.** One un-instrumented after-run on BGL had a burst
  of six Hud tick runs of 19–888 ms, 186–198 s into the window, with nothing in
  UE4SS.log. The median frame had doubled at the same time (13 to 26 ms). It
  did not come back in 13 minutes of runs with per-section timing in the tick,
  nor in the YOY run. Lua's `os.clock` is wall time on Windows, so a stall in
  the tick's file writes would read as Hud tick time.

## The load frame (measured and fixed)

**Measured on PC 1, 2026-11-09.** Private Slayer hosts, 1920x1080 borderless,
the game window not in front (it then runs at about 20 frames a second, so
every frame is 50 ms or more whatever the loader does). Each step of a load
was timed with `os.clock` and logged as one `load timing` line (kept in
MJOLNIRLevelLoader 0.13.3). A test copy of MJOLNIRHud's hitch log logged
every frame of 50 ms or more, with the Lua that ran in it. Before is main
at 0.13.2 plus that timing. After is 0.13.3: TMB, BGL and ZAN ran on its
dressing code exactly. Its last commit, which only starts devices and
turning machines once the world is dressed, was run on YOY and ASC.

| | Before: the one frame | After: frames | After: our Lua in all | After: most of it in one frame |
|---|---|---|---|---|
| TMB | 1,716 ms (loader 1,658 ms) | 75 | 1,275 ms | 56 ms (the `StaticMeshActor` walk) |
| BGL | loader 1,020 ms | 51 | 843 ms | 47 ms (foliage) |
| ZAN | 1,429 ms (loader 1,386 ms) | 117 | 1,553 ms | 36 ms |
| YOY | (not run) | 87 | 1,370 ms | 54 ms (terrain shadow proxy) |
| ASC | (not run) | 44 | 519 ms | 18 ms |

An earlier TMB run, of the build before the brush registration was
sliced, took 1,033 ms of Lua over 65 frames, with the same walk at 40 ms:
the later run was slower in every step, with other sessions building on
the machine. BGL's 1,020 ms frame is the loader's own timing: the hitch
log had not yet picked up the new world.

**Where TMB's 1,658 ms went** (before):

- **The decor loop, 704 ms, but not the baked pieces.** Its 4,242 baked
  pieces took 133 ms. Its 26 spawned pieces took 569 ms: the CE terrain
  (106 runtime materials on one mesh) and the flares. Zanzibar's 51 spawned
  pieces took 1,178 ms.
- **The level file, 210 ms,** decoded again 1–2 s after the travel's switch
  had decoded it (232 ms).
- **Whole-array scans, about 310 ms with the name reads after them:**
  - five `FindFirstOf` for the deformation brushes' classes, 138 ms;
  - `StaticMeshActor` twice, 52 ms each with a name read per actor;
  - `Landscape` twice, 23 ms each (a third in the flux step);
  - the scenario tag, 24 ms.
- **The rest:**
  - the baked foliage meshes, 85 ms, their
    `HierarchicalInstancedStaticMeshComponent` walk included;
  - the landscape's ground, cliffs and rocks, 136 ms;
  - `foliage.bin` read whole, 15 MB, 41 ms.

**The fix (MJOLNIRLevelLoader 0.13.3):**

- **Redundant work dropped.**
  - Baked pieces without `scalars` keep their mesh's materials: the bake
    sets none on them (`BakeDecor`), so setting each slot to its own
    material changed nothing. A reload still restores pieces that had
    instances (`Current.bakedMids`). The baked foliage meshes' reset is
    skipped the same way.
  - One `StaticMeshActor` walk feeds the decor and the cladding rocks.
  - One `Landscape` lookup a world, through `GetActorOfClass`.
  - The deformation brushes' five `FindFirstOf` became one
    `GetAllActorsOfClass` on `BlamObjectActor`. In the same TMB match both
    routes listed the same 145 vehicles and bipeds.
  - The travel's decode is handed to the load (`level_files.lua`) when the
    file's text is unchanged.
  - `foliage.bin` is read past its header only when a group needs its
    clumps.
- **The rest spread over frames** (`dress.lua`). The steps run in order,
  about 12 ms of Lua a frame. Long lists are worked a slice a frame through
  a queue:
  - a spawned piece's material slots, one job each;
  - the baked foliage meshes;
  - the landscape's four parts;
  - the cladding rocks (7,086 on BGL);
  - the brush actors (1,364 on TMB).

  The world counts as furnished, and fades in, after the last step.
  Devices and turning machines start then too: a device binds only once its
  decor exists. Gaps between load frames read 1–13 ms, and no logged frame
  carried two slices: the deferred calls run once an engine tick
  (`DefaultExecuteInGameThreadMethod = EngineTick`).
- **Two full collections end the load,** a frame each, 6–23 ms. Item 11's
  two collections were the `mjolnir_level_status` command's, not a load's.

**Dressed the same.** Every dressing line in UE4SS.log matched before and
after on TMB, BGL and ZAN: decor counts, materials, foliage clumps and
meshes, rocks, effects, landscape slots, cliffs, lights and decals. Only a
Lua line number in an error message and the brush count differed: brushes
went 90 → 286, because the step now runs while the game is still filling
its biped pools; later ones are caught by the existing watch either way.
Screenshots from a fixed camera on TMB, BGL and ZAN differ by 1–6/255 on
average, which is wind, clouds, water and Zanzibar's turning wheel. YOY's
10 devices all bound, and ASC's three turning machines rode their
simulation actors. On BGL, `mjolnir_foliage off`, `on` and
`mjolnir_level_reload` each re-dressed the map as it was: the grass in its
own colours (not the 2026-10-18 dark grey), and the cladding rocks hidden,
then shown again.

**What is left.**

- **Single calls the loader cannot cut, 30–56 ms each.** These set a load
  frame's ceiling:
  - the `StaticMeshActor` walk;
  - the foliage step's `HierarchicalInstancedStaticMeshComponent` walk
    with its names;
  - one terrain shadow proxy spawn;
  - the landscape's cliff materials (19–25 slots in one function).
- **The travel's own decode, 92–239 ms on the frame the map starts.** The
  switch needs the level's variant and vehicle sets before the map loads.
- **`mjolnir_foliage off` and `on`:** a frame of 71–78 ms on BGL, hiding or
  showing its 7,086 rocks at once. Only that console command does it.
- **More Lua in all on Zanzibar,** 1,553 ms against 1,386: the queue and its
  closures cost a little per material slot.
- **Engine frames of 100–330 ms** before the player is in, with none of our
  Lua in them, on both builds: streaming, pipeline states and the Fluid
  Flux capture.
- **Untested:** whether the end-of-load collections end the 47–61 ms lifts
  and footprints runs minutes into a TMB match (item 11); and a joiner's
  load.

## Where native (or GPU) code pays

Ranked by expected gain.

### 1. Flag cloth: a material, not C

**Status, 2026-11-08:** both halves built.
- **Throttle** (MJOLNIRLevelLoader 0.13.1, PR #368): measured on CHL.
  - Facing a flag: 12 → 5.5 ms/s.
  - Flags near but out of view: 10.5–16 → 1.4–2.3 ms/s.
- **GPU material** (0.13.2, PR #371): `M_CE_FlagCloth` in
  the runtime pack's chunk 966 (`build_flag_cloth.py`).
  - At rest: 0.5 ms/s.
  - Carrying a flag: about 3 ms/s.
  - It waits for a CE runtime pack release; until then the throttle runs.

The text below is the audit as written.

- **Today:** `Teams.clothTick` runs every 33 ms on every map and returns at once
  outside CTF and Assault ([teams.lua:490](../mods/MJOLNIRLevelLoader/Scripts/teams.lua),
  scheduled at [main.lua:5238](../mods/MJOLNIRLevelLoader/Scripts/main.lua)).
  With two flags in range it makes about 32 UE4SS calls a run: the pawn and
  flag reads, then one `K2_SetRelativeLocationAndRotation` per strip, 8 strips
  per flag ([teams.lua:421-431](../mods/MJOLNIRLevelLoader/Scripts/teams.lua)).
  Measured at 30–35 ms/s on CHL and 13 ms/s on BGL.
- **Why not native:** a C loop still makes the same 16–24 transform calls every
  frame and saves only the dispatch. It would also hold raw pointers to strip
  components on flag actors that are destroyed at every pickup and drop.
- **Design:** a world-position-offset cloth material in a cooked master,
  waving from engine time. Lua sets 2–3 parameters only while the flag is
  carried.
- **Gain:** about 30 ms/s in CTF, the largest steady cost we have.
- **Cost:** a new cooked master, through a cook pipeline that has been fragile
  ([ue_mesh_write.md](ue_mesh_write.md)), and a larger bounds scale.
- **Meanwhile, in Lua:** 15–20 Hz at rest, skip flags not rendered recently, 6
  strips, and back off to 1 s on maps without flags.

### 2. Halo 2 lifts: into the lobby DLL's simulation tick

- **Today:**
  - A 500 ms timed loop ([lifts.lua:270](../mods/MJOLNIRLevelLoader/Scripts/lifts.lua)):
    0.3–2.2 ms/s, worst 61 ms.
  - A 50 ms step that runs while a player is within 9 m of a lift
    ([lifts.lua:248-266](../mods/MJOLNIRLevelLoader/Scripts/lifts.lua)). It is
    untimed and repeats the 500 ms work; *estimate* 1,200–2,000 UE4SS calls a
    second near a lift.
  - Each push writes Blam script to a file for the DLL to run on the simulation
    thread ([sim_script.lua:23-37](../mods/MJOLNIRLevelLoader/Scripts/sim_script.lua)).
- **Design:**
  - Lua ships the map's lift volumes once.
  - The DLL's per-tick hook ([mjolnir_lobby.c:2896](../native/lobby/mjolnir_lobby.c))
    reads each local player's unit from the players table, through the TLS slot
    it already uses.
  - It tests the volumes and pushes through `hs_evaluate` directly.
- **Gain:** the lift Lua and the file write per push go away, and the push lands
  on the simulation tick instead of up to 50 ms late.
- **Cost:** the unit datum's offset in the 0x4b0-byte player record and the
  velocity offset need reverse-engineering. Position, at object+0x44, is
  already known from the teleport tooling. Like the team bytes, these offsets
  break with game updates. Guard the reads with `__try`.

This is the smallest of the three native jobs, and it builds the plumbing the
next two need: per-map data in, simulation reads out.

### 3. Player roster from the simulation, for the HUD

**Status, 2026-11-09: go.** Both open questions are answered, with two test
copies on PC 1 in a private Blood Gulch Slayer game (copy 1 hosting, copy 2
joined):
- A native function can return the whole roster without files, in 4–6 µs
  ([below](#the-lua-to-native-channel)).
- A fireteam client's simulation holds every remote player's unit, at the
  host's position.

- **Today, as audited:**
  - `playersOn`: about 12–14 reflection calls per player, 5 times a second, in
    King and Juggernaut ([markers.lua:56-85](../mods/MJOLNIRHud/Scripts/markers.lua)).
  - `refreshNames`: about 15–19 per player, every second and on every spawn,
    join and board redraw ([main.lua:409-452](../mods/MJOLNIRHud/Scripts/main.lua)).
  - The biped pool: two `FindAllOf` scans, about 30–46 ms, repeated every 2 s
    while no Spartan has been seen
    ([main.lua:333-387](../mods/MJOLNIRHud/Scripts/main.lua)). Since replaced
    by one `NotifyOnNewObject` (MJOLNIRHud 0.19.1, above).
- **Today, measured.** Both functions' reads were timed in game, run over
  `GameState.PlayerArray` 500 times in each copy:
  - `playersOn`: 26 µs a player a pass, the array walk included;
  - `refreshNames`: 23–25 µs a player a pass;
  - the walk alone: 3 µs a player.

  Two players took part, one of them the reader's own, which is the cheaper
  path. At 16 players that is about 0.4 ms a pass for each function: about
  2 ms/s for `playersOn` at 5 Hz, plus 0.4 ms/s or more for `refreshNames`. So
  about 2.5 ms/s in a 16-player King or Juggernaut game and under 1 ms/s in
  other modes, the low end of the 2–6 ms/s estimate.
- **The file channel would have cost more than it saved.** A reply file that
  Lua reads and parses costs 1.05–1.10 ms (median) in game. At 5 Hz that is
  about 5.5 ms/s, more than the reads it would replace. Through
  `lua_channel.h` the same 16 players cost:
  - 3.8–5.6 µs as one packed string read with `string.unpack`;
  - 8–9 µs as 16 tables of 8 fields;
  - about 0.03 ms/s at 5 Hz.
- **What a client's simulation holds.** Read from outside the game with
  `tools/remote/blam-players.py`:
  - **Both players and both units.** The client's players table lists the host
    with local user -1 and its own player with 0. Each player's unit handle
    names a live biped (type 0) in the client's object table.
  - **The host's positions.** The host's unit read `(38.903, -81.087, 1.702)`
    on the host and `(38.900, -81.090, 1.702)` on the client. After the host
    walked 14 m (in-game input on copy 1) it read `(35.970, -84.614)` and
    `(35.974, -84.611)`, within 2 cm.
  - **Handles are per peer.** The host's `0xe2fa008b` is the client's
    `0xe2c30054`. Each peer reads its own roster; handles are never compared
    across machines.
  - **Entry `+0x0C` is the host's index, not the entry's own.** On the client,
    entries 84 and 88 read 139 and 140, the host's indices for the same units.
    A check that it equals the entry's index rejects every unit on a client,
    including the client's own. The lift push had that check until #375
    ([below](#correctness-issues-found-along-the-way)).
- **Correctness, not only cost.** In the same test the client's
  `BP_SpartansBipedActor_C` for the host did not follow the host:
  - It stayed where the host spawned, 3 m up, after the host walked 14 m, while
    the client's simulation followed within 2 cm.
  - The host's actor for the joiner sat 2.5 m above the joiner's unit too.
  - Copy 2's window was in the background and its camera was not on the host.
    So this may be engine relevance rather than a bug.

  Either way, these are the actors the HUD's markers read for remote players.
  The simulation is the better source.
- **Design** (refined from the audit):
  - **The export.** A `mjolnir_roster` export in the lobby DLL, called at 5 Hz
    through `lua_channel.h`.
  - **The read.** On the simulation tick, under an SRW lock, it copies each
    seat:
    - salt and team (player `+0x4a4`);
    - unit handle and local user;
    - alive (a live unit);
    - position (`+0x44`), velocity (`+0x68`) and vehicle parent (`+0x14`).
  - **Validation.** An object is checked by its salt and type, never by
    `+0x0C`.
  - **Return.** One packed string per call, read in Lua with `string.unpack`:
    one push for 16 players instead of about 150 for a table of tables.
  - **Errors.** It never raises. When the tables don't check out it returns
    nil and a reason.
  - **Names stay in Lua.**
- **Gain:**
  - about 2–2.5 ms/s in 16-player King and Juggernaut, less elsewhere;
  - a client's markers drawn from its own simulation rather than from actors
    that can sit where a player spawned;
  - no stored biped handles in Lua, so no stored-handle crashes.
- **Cost:**
  - Positions are in simulation units: world units, Y flipped, ×304.8 for
    Unreal centimetres. On the client this matched the actors to 0.1 mm in x
    and y: its own biped, and the host's before the host moved.
  - It needs a layout size check like the one the team code already does.
  - The `LuaMadeSimple` exports become a dependency pinned to the UE4SS build.

### 4. Bots' bookkeeping (host only)

- **Today** (as audited; both bullets are fixed in Lua in MJOLNIRHud 0.19.1,
  [above](#the-huds-scans-and-lookups-measured-and-fixed)):
  - `liveActors` runs `IsValid` and `K2_GetActorLocation` on every pooled actor
    of 7 classes, every 0.25 s
    ([bots.lua:238-252](../mods/MJOLNIRHud/Scripts/bots.lua)). Measured since:
    271 pooled bipeds on BGL, about 2,200 calls a second.
  - `fillPool` scans all 7 classes with `FindAllOf`. The file's own comment
    prices that at "about 160 ms each", allowed up to 3 rescans a match
    ([bots.lua:207-234](../mods/MJOLNIRHud/Scripts/bots.lua)). It runs 3 s into
    a hosted match, on the same poll as `Relay.arm`'s scan. That is the
    likeliest source of the Hud tick's 108–129 ms worst runs.
- **Design:** the DLL already patches `ai_place`, gives bots their teams and
  runs their script. Have it also report each squad's unit, alive flag,
  position and last damage owner from the simulation's AI and object tables
  ([re/ai_in_multiplayer.md](re/ai_in_multiplayer.md)).
- **Gain:** the steady pool polling and the jump and teleport guesswork go away.
- **Cost:** more reverse-engineering than any other item. The 160 ms scans have a
  Lua fix that doesn't wait for this (below).

### Not worth native, and why

- **The 1.5 s load frame.**
  - Its time is thousands of reflection calls on world actors: 611–692 ms in the
    decor loop over 4,242 baked pieces, and 11 whole-array scans, about 210 ms.
    (Measured since: the decor loop's time was mostly the 26 spawned pieces'
    runtime materials, not the baked pieces. See
    [above](#the-load-frame-measured-and-fixed).)
  - Native code cannot hand those objects back to Lua.
  - Most of it is redundant work that Lua can drop, and the rest can be spread
    over frames: done in MJOLNIRLevelLoader 0.13.3.
- **The HUD's per-frame hook**
  ([main.lua:1644-1663](../mods/MJOLNIRHud/Scripts/main.lua)).
  - About 20 reflection calls a frame on a Slayer client and 45 in CTF.
  - On a host, about 4 more per remote controller, because `ReceiveTick` fires
    for every controller.
  - *Estimate:* 0.05–0.6 ms a frame.
  - Untimed, so measure it first (see "Measure first"). The Lua fixes below
    reach most of it. Animating widgets from C would make the same calls.
- **The Lobby, all of it.** Its costs are object scans, `StaticFindObject` and a
  JSON decode, each removed by a cache or an existing Blueprint hook. Its file
  channel to the DLL measured 0.04–0.54 ms per operation outside the game. In
  game a round trip costs about 1.3 ms
  ([below](#the-lua-to-native-channel)), still under 1 ms/s at the Lobby's
  rates.
- **Forge, FlyCam, BlamConsole, Bridge, CTF, WorldBuilder and the rest.** No
  loop costs more than 1.5 ms/s, and each cost is waste that Lua can remove. Most
  are opt-in or dev tools; Core, LevelLoader, Lobby and Hud are the four the
  launcher installs with every map.
- **JSON and level parsing.** As audited: without the Lua C API, a native
  parser cannot build the Lua table. Since 2026-11-09 it could, through
  `lua_channel.h` ([below](#the-lua-to-native-channel)). It is still not
  needed: the one costly decode, `hub_state.json`, now runs only when the file
  changes (MJOLNIRLobby 0.24.1).

## Lua fixes, ranked by what players feel

| # | Fix | Where | Effect |
|---|---|---|---|
| 1 | **Done in MJOLNIRLobby 0.24.1:** the 5.1 s host hitch (above), plus generational GC in the Lobby | `net.lua` `Net.clients`, `maplive.lua` `MapLive.release`, `games.lua` `presenceTick` | 82 hitches to 1 in a 4-minute host test |
| 2 | **Done in MJOLNIRHud 0.19.1** ([below](#the-huds-scans-and-lookups-measured-and-fixed)): one `NotifyOnNewObject` on the bipeds' native ancestor at mod load, so no match runs a whole-array scan; no 2 s biped rescan; a backstop rescan only of the slot's own class; `Relay.arm` and the bots start on different polls | `bipeds.lua`, `bots.lua`, `main.lua` `findBipeds` | Hud tick worst 308 ms to 10 ms with 8 bots on BGL |
| 3 | **Done in MJOLNIRLevelLoader 0.13.3** ([above](#the-load-frame-measured-and-fixed)): the load frame. No `SetMaterial(i, the same material)` on baked pieces without `scalars`; one `StaticMeshActor` scan; five `FindFirstOf` became one `GetAllActorsOfClass`; `level.json` decoded once per map; `foliage.bin` read past its header only when needed; the steps spread over frames, then two full collections | `main.lua` `spawnDecor`, `dress.lua`, `level_files.lua` | TMB 1,716 ms in one frame to 75 frames, at most 56 ms of Lua in any; BGL 1,020 ms to at most 47 ms; ZAN 1,429 ms to at most 36 ms |
| 4 | **Done in MJOLNIRLevelLoader 0.13.1 and 0.13.2:** flag cloth throttle, then the GPU cloth material ([above](#1-flag-cloth-a-material-not-c)) | `teams.lua` `Teams.clothTick` | CHL facing a flag 12 → 5.5 ms/s (throttle) → 0.5 ms/s (material) |
| 5 | **Libraries cached in MJOLNIRHud 0.19.1.** Hill and race redraw: 16–64 panels with 2 `StaticFindObject` each, per hill move. Spreading the panels over polls is not needed now | `hill.lua` | a 26-panel move: 55–62 ms to 2–5 ms (measured) |
| 6 | **Done in MJOLNIRHud 0.19.1:** cache `syncClass` (one `StaticFindObject` per flag or ball every 0.2 s) | `flagmark.lua` | about 0.1 ms a lookup measured, so about 1 ms/s with two flags |
| 7 | **Done in MJOLNIRLevelLoader 0.13.2:** cache the shields' class, and back off the rescan for unbound devices (it stops after 8 scans that bind nothing). The 37 hitches were the rescan, not the class lookup: a FindAllOf every 2 s, 24–27 ms each, for a whole match on YOY (2026-11-06), while one device stayed unbound | `devices.lua` | devices 0.4 ms/s, worst 1 ms on YOY (was 0.8–1.6, worst 27–30) |
| 8 | Post-game vote covers: keep the texture handle, redraw only on change | Lobby `main.lua:3485` | *estimate* about 32 ms/s while the vote is up |
| 9 | Forge: leave `aim` out of the state comparison (it re-renders the HUD 10 times a second); scan pack lights and surfaces only in Forge or on a world change; generational GC | Forge `main.lua:527-541` | the 1.3 ms/s and 51 ms runs of Forge HUD |
| 10 | Avatars: keep imported textures across maps, import at most one per poll | `hubnames.lua:72-94`, `main.lua:1249` | the first Tab press and final standings |
| 11 | A full collection twice at the end of a load. **Corrected in MJOLNIRLevelLoader 0.13.3:** those two were the `mjolnir_level_status` command's; a load ran none. A load now ends with two, a frame each, 6–23 ms | LevelLoader `main.lua` `status`, `spawnDecor` | may explain the 47–61 ms lifts and footprints runs minutes after a TMB load (still to test) |

## Correctness issues found along the way

- **The native lift push skipped a fireteam client's own player** (found
  2026-11-09; fixed in #375, before MJOLNIRLobby 0.25.0 ships).
  - **Cause.** `lift_biped` required the object entry's `+0x0C` to equal the
    entry's index. On a client that field is the host's index (above), so every
    unit failed the check, the client's own included, and no joiner was ever
    pushed.
  - **Fix.** #375 checks the salt, type and datum size instead.
  - **Proof.** On Lockout with two copies, a joiner in the lower tube got no
    push with the old DLL and rode to the upper floor with the fix
    ([re/lift_push.md](re/lift_push.md#a-fireteam-clients-own-player)).
  - **The doors.** The Forge doors' `fd_object` has the same check, but they
    return before it on a client.
- **`LoopAsync` handing work to the game thread every second.** CTF
  (`main.lua:404-410`), WorldBuilder (`main.lua:352-358`) and Bridge
  (`main.lua:375-396`) do it, and BlamConsole does it per answer. LevelLoader
  (`main.lua:5144-5150`) and Lobby (`main.lua:4189-4191`) both record this
  pattern freezing the game. These are dev mods, but they ship in the signed
  set.
- **The host may queue its own incident relays once per client.**
  [main.lua:1017-1037](../mods/MJOLNIRHud/Scripts/main.lua) skips the host's own
  hook for team relays but not for incident batches. With 15 clients, a burst
  of 5 incidents would fill the 64-entry queue and drop real ones. Untested
  past two PCs.
- **A failed pattern rescans every second.** If `inject_prepare`'s byte patterns
  stop matching after a game update, it re-runs three scans of the simulation
  DLL every second on a host. It logs the failure only once
  ([mjolnir_lobby.c:4259-4265, 5103-5110](../native/lobby/mjolnir_lobby.c)).
  Latch the failure.
- **Fresh `{}` out-parameters, which UE4SS keeps forever:**
  - FlyCam, every frame while it is on (`main.lua:315-321, 392-394`);
  - the waypoint's `GetViewportSize` (fixed in MJOLNIRHud 0.19.1);
  - the hill's line traces (fixed in MJOLNIRHud 0.19.1);
  - the vehicle sounds' hit result (`vehicle_sounds.lua:275`).

## The Lua-to-native channel

**Today.**
- UE4SS exports no `lua_*` C API. So the lobby DLL's exports, called through
  `package.loadlib`, take no arguments; they exchange request and reply files
  in `native\`.
- **In game that costs more than first measured.** Two test copies on PC 1 ran
  500 round trips each (2026-11-09): Lua writes the request, the export reads
  it and writes its reply through a temporary file and a rename, then Lua reads
  the reply.
  - Median 1.30 ms, mean 1.35–1.41 ms, worst 3.6–34 ms.
  - A reply alone, read and parsed (16 lines): median 1.05–1.10 ms.
  - Outside the game the same operations had measured 0.04–0.54 ms each.
  - The copies keep their `native\` under `%LOCALAPPDATA%` rather than the
    Steam install's folder; the install's own was not timed.

  Fine once a second, wrong at 5 Hz.
- A native function also cannot hand a UObject back to Lua. So native work must
  be self-contained: read simulation memory and act on it, as the lift, roster
  and bots designs do. Otherwise it returns plain numbers and strings.

**Measured 2026-11-09: arguments and return values without files.** UE4SS
3.0.1 (`d0107f63`) exports its `RC::LuaMadeSimple::Lua` wrapper, and its
members work as a small Lua C API.
[`native/lobby/lua_channel.h`](../native/lobby/lua_channel.h) calls them from
C. No shipped code uses it yet. `native/lobby/test-lua-channel.ps1` runs in CI
against a stand-in built from the same C++ declarations, so a wrong export
name or calling convention fails the build.

**How it was checked.** By disassembly, then with a throwaway probe DLL loaded
from the bridge in both copies (host and client). The three open questions:

- **Size.** The `Lua` object is 0xa8 bytes, with no vtable:
  - the `lua_State*` at `+0`;
  - a vector at `+8`;
  - an optional at `+0x38`, engaged flag `+0x98`;
  - a pointer to itself at `+0xa0`.

  The header builds it in 0x100 bytes on the stack, once per call. Its
  constructor and destructor do no more than that.
- **Pops: yes, the value at the index, not the top.** Every `get_*` reads with
  `lua_to*` and then removes that value. None checks the type.
  - `get_integer` at index 1 on `(2.5, "7", 9, 2.0)` took the stack from 4 to
    3, 2, 1, 0 and returned 0, 7, 9, 2: a non-integral float reads as 0.
  - `get_string` on anything but a string or number dereferences NULL.
  - Any `get_*`, or `discard_value`, on an index past the top removes a value
    that is there: `lua_rotate` does not check in this build.
  - The header checks the index and the type before each read and removes
    exactly one value, so arguments read in order from index 1. Extra
    arguments stay on the stack, unread.
- **Errors: a longjmp back to the caller's `pcall`.** UE4SS builds Lua as C:
  `luaD_throw` longjmps to the protected call. A probe export raised through
  `throw_error`, inside a `__try`/`__finally` inside a `__try`/`__except`:
  - Lua's `pcall` got `false` and the message, with UE4SS's traceback appended;
  - the code after the raise never ran;
  - the `__finally` ran;
  - the `__except` filter was never asked;
  - the next calls worked normally, and so did a second raise.

  So a native function must never raise, and must never hold a lock or own
  memory across a call that could. It reports a bad argument as nil and a
  reason. None of the header's calls raise: they check first, and only running
  out of memory would.

Two more things the disassembly shows: `lua_lock` is a global critical section
in this build, so every API call enters it; and `get_string`'s view points into
a string its own removal just unanchored, so the header copies it at once.

**Cost, in µs per call** (copy 1 hosting, copy 2 joined, both in the match;
timed with a QPC clock read through the channel itself):

| Call | Host | Client |
|---|---|---|
| A Lua function, 4 arguments and 4 results | 0.05 | 0.05 |
| An export, no arguments or results | 0.014 | 0.020 |
| An export, 4 arguments in, 5 results out | 0.29 | 0.36 |
| A roster: 16 tables of 8 fields | 8.1 | 9.4 |
| A roster: one 512-byte string, read with 16 `string.unpack` | 3.8 | 5.6 |
| UE4SS reflection: `pc:IsValid()` | 0.15 | 0.23 |
| UE4SS reflection: `pc.Pawn` | 0.82 | 1.07 |
| File round trip: request, export, reply (median) | 1,302 | 1,309 |
| File reply alone, read and parsed (median) | 1,102 | 1,054 |

A first client run during the map load measured about twice as slow on every
line, with a 51 ms worst file round trip.

**What it means.**
- **No more file round trips.** The roster and lift designs can drop theirs. A
  call costs less than one UE4SS property read; a file round trip costs about
  4,000 times as much.
- **The exports are pinned to the UE4SS build,** like the AOB signatures. Once
  shipped code uses the header, a UE4SS bump must check that `lc_resolve`
  still finds every name (`lc_missing` names the first gone) and re-read the
  getters' behaviour. Add that step to the bump notes in
  `runtime/ue4ss.lock.json` then.
- **Tables are cheap now.** The 16-table roster set 128 fields in 8–9 µs,
  about 0.06 µs a field. So a native parser could build Lua tables, which the
  audit had ruled out ("JSON and level parsing", above).

**Possible, not needed yet: UE4SS's C++ hooks.** UE4SS also exports
`Hook::RegisterEngineTickPreCallback` and `RegisterProcessEventPreCallback`,
`UObjectGlobals::RegisterHook`, `FindAllOf` and `ProcessEvent`.

- They take `std::function` and `std::vector`, so a DLL using them must be C++
  built against UE4SS's MSVC and STL ABI.
- The pinned build in `runtime/ue4ss.lock.json` makes that feasible, but every
  UE4SS bump becomes a native rebuild and retest.
- None of the ranked items needs it: all three native jobs fit the lobby DLL's
  existing simulation-tick hook.

## Measure first

- **The HUD frame hook.** Sum `os.clock()` around its body. Report it once a
  second as `Hud frame`, with the calls per frame.
- **Labels inside the Hud tick.** Bots, markers, names, board, chat and drain.
- **The Lobby's games, presence and identity loops, and the lifts' 50 ms step.**
  Route them through `UI.reportSlow` and `every`.
- **Each `FindAllOf`, by class.** One hosted bot match tells the 7-class bot
  scan from the rest.
- **A two-PC check: done 2026-11-09, with two copies on PC 1.** A client's
  simulation holds every remote player's unit, at the host's position
  ([section 3](#3-player-roster-from-the-simulation-for-the-hud)).

## Suggested order

1. The Lobby's 5.1 s hitch, generational GC and timing for its untimed loops:
   done in MJOLNIRLobby 0.24.1. Forge's generational GC is still to do.
2. The HUD's scans moved to `NotifyOnNewObject`, plus `StaticFindObject` caching
   in hill, flagmark and devices: done in MJOLNIRHud 0.19.1 and
   MJOLNIRLevelLoader 0.13.2.
3. The load-frame trims, then spreading the load over frames: done in
   MJOLNIRLevelLoader 0.13.3.
4. The flag cloth throttle, then the cloth material: done in
   MJOLNIRLevelLoader 0.13.1 and 0.13.2.
5. Native lifts in the lobby DLL's simulation tick: done (#370, MJOLNIRLobby
   0.25.0, through a file). Fireteam clients needed the `+0x0C` fix, #375
   ([above](#correctness-issues-found-along-the-way)).
6. The native roster, then the bots. The roster is a go: build it on
   `lua_channel.h`.
7. The `LuaMadeSimple` spike: done 2026-11-09. It works (`lua_channel.h`).

Steps 1–3 remove most of the hitches our mods cause. Step 4 removes the largest
steady cost. Steps 5–6 are each worth about 1–6 ms/s, and also bring the lift
timing and the end of stored-biped crashes. None of it needs a new DLL.

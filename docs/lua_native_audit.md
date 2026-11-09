# Lua or native: where compiled code would pay

**Status:** 2026-11-08. A read-only audit of the 15 Lua mods (about 35,000
lines) and the five shipped native DLLs, checked against PC 1's hitch history:
73 sessions, 57 per-map summaries and 6,356 logged hitches from 2026-11-06 to
2026-11-08 (RTX 5090, mostly 3840x2160 Epic). Nothing was changed. A cost
marked *estimate* was read off the code, not measured in game.

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

## Where native (or GPU) code pays

Ranked by expected gain.

### 1. Flag cloth: a material, not C

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

- **Today:**
  - `playersOn`: about 12–14 reflection calls per player, 5 times a second, in
    King and Juggernaut ([markers.lua:56-85](../mods/MJOLNIRHud/Scripts/markers.lua)).
  - `refreshNames`: about 15–19 per player, every second and on every spawn,
    join and board redraw ([main.lua:409-452](../mods/MJOLNIRHud/Scripts/main.lua)).
  - The biped pool: two `FindAllOf` scans, about 30–46 ms, repeated every 2 s
    while no Spartan has been seen
    ([main.lua:333-387](../mods/MJOLNIRHud/Scripts/main.lua)).
  - *Estimate:* 2–6 ms/s in 16-player objective and team games.
- **Design:** a `mjolnir_roster` export.
  - On the simulation tick, under a lock, it copies each seat's team, unit,
    alive flag and position (plus vehicle parent).
  - Lua reads it at 5 Hz.
  - Names stay in Lua.
- **Gain:** the per-player reflection and the biped scans go away. So do the
  stored-biped-handle crashes, because Lua stops holding biped handles at all.
- **Cost:**
  - Positions are in simulation units (world units, Y flipped).
  - It is unverified whether a client's simulation holds remote players' units.
    That needs a two-PC check before building.
  - It needs a layout size check like the one the team code already does.

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
  - Native code cannot hand those objects back to Lua.
  - Most of it is redundant work that Lua can drop, and the rest can be spread
    over frames (below).
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
  channel to the DLL measured 0.04–0.54 ms per operation outside the game,
  under 1 ms/s in a match.
- **Forge, FlyCam, BlamConsole, Bridge, CTF, WorldBuilder and the rest.** No
  loop costs more than 1.5 ms/s, and each cost is waste that Lua can remove. Most
  are opt-in or dev tools; Core, LevelLoader, Lobby and Hud are the four the
  launcher installs with every map.
- **JSON and level parsing.** Without the Lua C API, a native parser cannot
  build the Lua table.

## Lua fixes, ranked by what players feel

| # | Fix | Where | Effect |
|---|---|---|---|
| 1 | **Done in MJOLNIRLobby 0.24.1:** the 5.1 s host hitch (above), plus generational GC in the Lobby | `net.lua` `Net.clients`, `maplive.lua` `MapLive.release`, `games.lua` `presenceTick` | 82 hitches to 1 in a 4-minute host test |
| 2 | **Done in MJOLNIRHud 0.19.1** ([below](#the-huds-scans-and-lookups-measured-and-fixed)): one `NotifyOnNewObject` on the bipeds' native ancestor at mod load, so no match runs a whole-array scan; no 2 s biped rescan; a backstop rescan only of the slot's own class; `Relay.arm` and the bots start on different polls | `bipeds.lua`, `bots.lua`, `main.lua` `findBipeds` | Hud tick worst 308 ms to 10 ms with 8 bots on BGL |
| 3 | Load frame: don't `SetMaterial(i, the same material)` on every slot of every baked piece unless it has `scalars`; share the `StaticMeshActor` scan; five `FindFirstOf` become `GetAllActorsOfClass`; decode `level.json` once per map (the travel hooks decode it again, about 124 ms each); read only `foliage.bin`'s header when foliage is baked; spread the steps over frames, then run two full collections | `main.lua:4945-4971`, `3669`, `4702-4710`, `5849-5855`, `3695` | *estimate* 0.5–0.8 s off TMB's 1.5 s frame, no frame over about 50 ms |
| 4 | Flag cloth throttle until the material exists | `teams.lua:490` | most of the 30–35 ms/s in CTF |
| 5 | **Libraries cached in MJOLNIRHud 0.19.1.** Hill and race redraw: 16–64 panels with 2 `StaticFindObject` each, per hill move. Spreading the panels over polls is not needed now | `hill.lua` | a 26-panel move: 55–62 ms to 2–5 ms (measured) |
| 6 | **Done in MJOLNIRHud 0.19.1:** cache `syncClass` (one `StaticFindObject` per flag or ball every 0.2 s) | `flagmark.lua` | about 0.1 ms a lookup measured, so about 1 ms/s with two flags |
| 7 | **Done in MJOLNIRLevelLoader 0.13.0:** cache the shields' class, and back off the rescan for unbound devices (it stops after 8 scans that bind nothing). The 37 hitches were the rescan, not the class lookup: a FindAllOf every 2 s, 24–27 ms each, for a whole match on YOY (2026-11-06), while one device stayed unbound | `devices.lua` | devices 0.4 ms/s, worst 1 ms on YOY (was 0.8–1.6, worst 27–30) |
| 8 | Post-game vote covers: keep the texture handle, redraw only on change | Lobby `main.lua:3485` | *estimate* about 32 ms/s while the vote is up |
| 9 | Forge: leave `aim` out of the state comparison (it re-renders the HUD 10 times a second); scan pack lights and surfaces only in Forge or on a world change; generational GC | Forge `main.lua:527-541` | the 1.3 ms/s and 51 ms runs of Forge HUD |
| 10 | Avatars: keep imported textures across maps, import at most one per poll | `hubnames.lua:72-94`, `main.lua:1249` | the first Tab press and final standings |
| 11 | A full collection twice at the end of a load | LevelLoader `main.lua:5497-5501` | may explain the 47–61 ms lifts and footprints runs minutes after a TMB load (to test) |

## Correctness issues found along the way

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
- UE4SS exports no `lua_*` C API, so a native function called through
  `package.loadlib` takes no arguments. It exchanges request and reply files in
  `native\`.
- That costs 0.04–0.54 ms per file operation: fine at 1–5 calls a second, wrong
  for per-frame work.
- A native function also cannot hand a UObject back to Lua. So native work must
  be self-contained: read simulation memory and act on it, as the lift, roster
  and bots designs do. Otherwise it returns plain numbers and strings.

**Possible, unverified: real arguments and return values.** UE4SS 3.0.1
(`d0107f63`) exports its `RC::LuaMadeSimple::Lua` wrapper:

- the constructor `Lua(lua_State*)`;
- `get_integer`, `get_number`, `get_bool` and `get_string`, each taking a stack
  index;
- `set_integer`, `set_number`, `set_bool` and `set_string`;
- `get_stack_size`, `prepare_new_table` and the `Table` field setters.

`package.loadlib` already hands the DLL the `lua_State*`, and every one of these
is callable from C:

- They are MSVC x64 member functions, so `this` goes in `rcx`.
- `get_string` returns a `std::string_view` through a hidden pointer.

So a native function could take arguments and return values with no files. A
spike has to settle three things before anything relies on it:

- the size of the `Lua` object (allocate generously);
- whether `get_*` pops the value;
- how a Lua error unwinds through a C frame.

If it works, the roster and lift designs lose their file round trips.

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
- **A two-PC check.** Does a client's simulation hold remote players' units?
  The roster design depends on it.

## Suggested order

1. The Lobby's 5.1 s hitch, generational GC and timing for its untimed loops:
   done in MJOLNIRLobby 0.24.1. Forge's generational GC is still to do.
2. The HUD's scans moved to `NotifyOnNewObject`, plus `StaticFindObject` caching
   in hill, flagmark and devices: done in MJOLNIRHud 0.19.1 and
   MJOLNIRLevelLoader 0.13.0.
3. The load-frame trims, then spreading the load over frames.
4. The flag cloth throttle now, the cloth material later.
5. Native lifts in the lobby DLL's simulation tick.
6. The native roster, then the bots.
7. Optionally, the `LuaMadeSimple` spike, before item 5 if it works.

Steps 1–3 remove most of the hitches our mods cause. Step 4 removes the largest
steady cost. Steps 5–6 are each worth about 1–6 ms/s, and also bring the lift
timing and the end of stored-biped crashes. None of it needs a new DLL.

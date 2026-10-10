# Installing a map while the game runs

A player who joins a server on a map they don't have, or whose host or
post-game vote picks one, gets a prompt with the map's hub screenshot and
details. DOWNLOAD installs the map and loads it into the running game, and the
join (or the lobby) carries on. There is no restart. The same screenshots now
appear on the map select, the lobby card, FIND GAMES and the post-game vote.

Verified on CU4, 2026-10-09:

- Wizard was uninstalled (launcher state, cache, Paks, `MJOLNIRMaps`, and the
  registration container rebuilt without it). From the running game's
  download screen it then downloaded, verified, installed, mounted and
  registered in under six seconds, and hosted and played.
- Reactor, a halomaps.org conversion that was never in the registration
  container or in Paks at boot, was registered and mounted by hand while the
  game ran, then hosted and played. The game exited cleanly afterwards.

Then on two PCs (PC 2 without Wizard: launcher uninstall, so its
registration container lacked it too):

- **FIND GAMES:** PC 2 used DOWNLOAD AND JOIN on PC 1's Wizard game. It
  downloaded, mounted and registered the map, joined the lobby, and both
  played it.
- **The host's pick:** PC 1 changed the lobby to Hang 'em High. PC 2 got the
  prompt, PC 1's lobby showed "WAITING FOR 1 PLAYER TO DOWNLOAD", PC 2
  downloaded it, and both played.
- **The vote:** the post-game vote chose The Longest. PC 2's option read
  `/ DOWNLOAD`, it got the prompt, PC 1 held its countdown until PC 2 was
  ready, and both played.

Two things only a second PC could show, both fixed:

1. **The map's index in the campaign list must match on every machine**
   (next section).
2. **The live row's MapGuid has to match the cooked one.** The C copy of
   `map_guid` upper-cased all of "MJOLNIR map CODE", not just the code. A
   host alone never notices: it only has to agree with itself. A client
   whose row disagrees with the host's loads the world, and the game never
   starts.

## Every machine needs the same index for the map

`SetAndBeginCampaign` (0x7B446E0) finds the map by a linear scan of
`DA_FirstPlayableCampaign.ScenarioList` and keeps its index
(BlamCampaignFlowGameSubsystem+0x38). A fireteam only starts when every
machine's index agrees:

- PC 1 has two local maps (CSN, YOY) that PC 2 lacks. Danger Canyon is index
  15 on PC 1 and 14 on PC 2, and both loaded the world and stayed "not in a
  game".
- Blood Gulch sits before both local maps, at 12 on each, and started.

Installed map sets differ from player to player, and a live install appends
at the end, so this has to be handled:

- The host sends its index with the map: field 4 of the lobby message,
  field 6 of the vote message.
- A guest joining a match under way asks for it (`where` / `mapindex`).
- Clients call `MapLive.follow`, which uses `mjolnir_scenario_place`
  (native/map_registry) to swap the handle to that index. When the list is
  shorter, it pads with copies of B40's handle; the scan finds the real B40
  first, so a filler never answers for anything.

The map registry logs the move, e.g. `place DCN: index 14 -> 15`.

## What a converted map needs, and when each step happens

| Step | At boot (the launcher's install) | While the game runs |
| --- | --- | --- |
| Containers in Paks | `hub::materialize` copies them; the engine mounts them at startup | the launcher's live install copies them under the same names; `mjolnir_mount_paks` mounts them |
| Short world name resolves | `mjolnir_map_registry` indexes `Paks/*.utoc` at load | the mount re-reads the indexes |
| `DT_Scenarios` row and campaign `ScenarioList` handle | cooked into `pakchunk996-MJOLNIRREG_P` | `mjolnir_scenario_add` clones the B40 row in memory |
| Frontend levels cache entry | built at boot from every `DT_Scenarios` row | the same insert, called by `mjolnir_scenario_add` |
| Level data and the menu list | `maps::sync` writes `MJOLNIRMaps/<CODE>/` and `maps.json` | `maps::add_live` writes the same; the lobby re-reads it every time |

The frontend levels cache was the missing piece. The 2026-09 notes put the
boot-time gate in the simulation's own levels registry. That registry is the
data arrays `campaign levels` (64) and `multiplayer levels` (50) in
`HaloSimulation_tag_release.dll` at 0xbd5738 and 0xbd5748, and on CU4 they are
**empty**. Nothing reads them, and their caps limit nothing.

The real boot-time step is in the exe:
`UBlamFrontendLevelsEngineGlueSubsystem::BuildRuntimeCachesFromBuiltInMapInfoDataAsset`
(0x7B7D180). It passes every row of the tables `BuiltInMapInfoData` names to
a per-row insert (0x7BAC140). That insert builds the subsystem's per-map
entries: 0x14c bytes each, keyed by MapGuid, in a sparse array at
subsystem+0x138. It then stamps each campaign map's entry with its
campaign's id (+0x120).

A row added without that entry loads the world, but the simulation stays "not
in a game" (`mjolnir live arrays`). With the entry, the map plays. So there is
no limit on how many hub maps a player can install. Only maps registered at
boot or added this session can start, and every start path adds the map
first.

## The pieces

**Launcher, `--install-map <CODE> --progress <file>`** (`hub::run_live_install`).
This is the ordinary install (`install_one`), run with no window:

- It checks the hub's sha256, the platform signature when there is one, and
  the author signature.
- It writes the same cache, `hub_state.json` and active profile, and uses the
  same Paks file names. The next launch therefore copies nothing and rebuilds
  the registration container, because its record lacks the new code.

What it leaves out, because the game is running:

- It never rewrites a container already in Paks: the game holds them open,
  and a mounted map's update waits for a restart.
- It doesn't install or update code mods: their DLLs are loaded.
- It treats a missing dependency (the CE runtime pack) as an error.
- It doesn't rebuild the registration container: it is mounted.

Progress goes to `<file>` as one JSON object, replaced as it changes:

- `{"stage":"download","received":n,"total":n}`, where the total comes from
  the hub listing, since the archive is streamed without a length.
- Then `{"stage":"done","mount":[...],...}` or `{"stage":"error","message":...}`.

The launcher records its own path in `launcher_exe.txt` in its config folder
each time it starts. A launcher from before live installs records nothing, so
the game says to update it instead of opening it.

**MJOLNIRLobby's native half** (`native/lobby`):

- `mjolnir_map_install` starts the launcher for a code (`[A-Z0-9]{3}` only).
- `mjolnir_map_install_status` says whether the launcher is still running.
- `mjolnir_hub_call` gained a `FILE` method that saves a hub response to
  `MJOLNIRMaps\_covers\<name>`; the name is a plain file name.

**MJOLNIRLevelLoader's native half** (`native/map_registry`):

- `mjolnir_mount_paks` calls `FCoreDelegates::MountPak`. The storage is at
  exe 0xD349040; the bound instance holds the `FPakPlatformFile` at +0x18 and
  `HandleMountPakDelegate` (0x4694C00) at +0x20, and the method is checked
  before the call. It mounts each `.pak`, then its IoStore sibling with the
  IoDispatcher and the package store, and fires `OnPakFileMounted`. Then it
  re-reads the world index.
- `mjolnir_scenario_add` does the following:
  - clones a template row (B40, as the cooked rows do) with the codename's
    world, `ScenarioName` and MapGuid (`blam_pack::scenario::map_guid`);
  - adds it to `DT_Scenarios`' `RowMap`;
  - appends the `ScenarioList` handle;
  - calls the frontend levels insert and copies the campaign id from the
    template's entry.

  Every allocation goes through `GMalloc` (exe 0xD4B7428: Malloc at vtable
  +0x28, Free at +0x48), so the engine frees them at shutdown like its own.
  An FText copied by value takes a reference (`+8` of its text data).

Both are CU4-only by RVA, guarded by the exe's timestamp.

**MJOLNIRLobby** (`Scripts/maplive.lua`, wired into `main.lua`):

- `MapLive.refresh` / `info` read the hub listings (`GET /maps`,
  `/maps/{code}`).
- `MapLive.cover` / `texture` keep each map's cover on disk and read it with
  `KismetRenderingLibrary.ImportFileAsTexture2D`. Textures are kept by name
  and found again with `StaticFindObject`, never kept by reference: a
  transient texture no brush holds any more is collected.
- `MapLive.install` starts the launcher, polls its progress, mounts, then
  registers.
- `MapLive.register` adds a map's scenario records unless they are there
  already. It runs before every start (`startGame`), before a join from
  FIND GAMES, and when a client hears the host's map.

## The flows

- **FIND GAMES:**
  - A game on a map you lack offers **DOWNLOAD AND JOIN**. The download
    screen explains why, and once the map is in, the join runs as usual.
  - The details panel shows the map's screenshot and download size.
  - QUICK JOIN still only picks maps you have.
- **The host picks a map a client lacks:**
  - The client's lobby offers the download once; after that, the lobby's
    START button reads **DOWNLOAD MAP**.
  - The client reports `mapstate <code> prompt|download <pct>|ready|declined|error`
    to the host.
  - While someone is deciding or downloading, the host's lobby footer says
    so. A first START warns; a second START within ten seconds starts
    without them.
- **The post-game vote picks a map a client lacks:**
  - Vote options on maps you lack read `/ DOWNLOAD`.
  - When the vote ends on one, the client gets the download screen.
  - The host's countdown waits while anyone is deciding (up to 25 s
    without word) or downloading (`Live.DOWNLOAD_WAIT`, 180 s), and the
    post-game footer says who it is waiting for.
- **Test verbs:**
  - `mjolnir_auto download <CODE>` opens the screen.
  - `mjolnir_auto install <CODE>` installs with no screen.
  - `mjolnir_auto join` downloads the listed game's map first.

## What is not done yet

- **A map with the same code but a different version.** Lobbies carry only
  the map code. A client with an older version joins with it; one without
  the map downloads the newest release, which may be newer than the host's.
  The listing should carry the host's release id.
- **A client that declines and is still in the fireteam when the host
  starts.** It follows the host into a map it doesn't have. Not tested.
- **Updating a map that is already mounted** needs a restart, as it always
  has.
- **Joining a match under way on a map this PC lacks.** FIND GAMES downloads
  the map first. The index request for a held join (`where`) is in place,
  but has not been tried on two PCs.

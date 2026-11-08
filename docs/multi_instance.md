# Several copies of the game on one PC

Multiplayer tests used to need PC 2. `tools/remote/instances.mjs` runs two to
four copies of Halo: Campaign Evolved on PC 1, all signed in to the one
account, all in one fireteam lobby, and takes them into one match that every
copy plays in the same Blam simulation.

What this covers, and what it does not (2026-11-07, CU4 Steam build):

| Layer | Same-account copies on one PC |
|---|---|
| Sign-in, main menu, own fireteam lobby | works, 2 to 4 copies |
| PlayFab lobby and Party network (joining by connection string) | works |
| UE session (listen server, connections, `GameState.PlayerArray`) | works: every copy lists every player |
| Host starts a match; every copy travels to the map with HUD and weapon | works |
| Blam simulation | **shared**: 4 copies, 4 players on 4 machines in every copy, positions agree, a kill counts on both sides |
| Back to the lobby and a second match | works (4 copies) |
| Team games (CTF) | work: 4 copies split 2 against 2, the same in every copy, armour colours match |
| `Net` messages between host and clients (ClientMessage, lobby messages, kicks) | go over the UE session; not tested one by one |

Proof, 2026-11-07: with 2 copies, the host shot the joiner (in-game input on
the host) and both copies logged the kill (`Kill`, `death`; the joiner also
`first_blood`), with the score at 1. With 4 copies, the three joiners were
teleported (each in its own copy) to stand in front of the host's camera, and
the host's screen showed all three; every copy listed the same four biped
positions. In CTF with 4 copies, the host (red) saw blue, red and blue
Spartans in front of it, and every copy's simulation had the same teams.

## The recipe

```
node tools/remote/instances.mjs up 2                                    two copies, 1280x720
node tools/remote/instances.mjs up 4 -windowed -ResX=960 -ResY=540      four copies
node tools/remote/instances.mjs console 1 "mjolnir_auto host BGL slayer private"
node tools/remote/instances.mjs players     each copy: world, UE players, Blam players and machines
node tools/remote/instances.mjs down        stop every copy (never the Steam game)
```

`up N --separate` leaves the simulations apart: every copy still follows the
host into its match, each playing alone (the state before the identity work
below).

Driving a copy's player: in-game input through that copy's bridge,
`MJOLNIR_GAME_DIR="<copy's install>" node tools/mcp/game/cli.mjs input '[{"mouse":"left","hold":3000}]'`
(no mouse or focus taken). Teleports are written in the copy that owns the
player (object `+0x44`, see [teleport notes](game_state_reader.md)).

`up N` builds any missing mirror, puts this checkout's built
`mods/MJOLNIRLobby/native/mjolnir_lobby.dll` into each copy, starts the
copies one after another, signs each in through the title menu's own click
event (no keys, no mouse), waits for every fireteam lobby, makes copy 1's menu
world a listen server, and joins copies 2..N to copy 1 by its lobby
connection string. The hub is not involved: nothing is listed publicly.
Measured: 2 copies in 70 s, 4 copies in 2 min 41 s.

Other verbs: `mirror`, `deploy`, `launch`, `menu`, `lua`, `console`,
`connection`, `join <n> <host>`, `log <n>`. Each copy has its own bridge, so
`lua 3 ...` runs in copy 3. Screenshots of one copy:
`tools/mcp/game/capture.ps1 -ProcessId <pid> -OutFile shot.png`. The Blam
players of one copy: `python tools/remote/blam-players.py --pid <pid>`.

Rebuild the lobby DLL before `up` when it changes (`native/lobby/build.ps1`).
The test-only behaviour below runs only in copies the tool starts, because
the tool sets `MJOLNIR_INSTANCE`. The Steam game, and every player's game,
never sees it.

### Cost

About 5 to 20 GB of RAM per copy (the host copy is the largest), and about
4 GB of video memory per copy at the low settings the tool gives them. Four
copies left 60 GB of RAM free on PC 1 (128 GB) and used 17 GB on its RTX 5090.

## How each copy is kept apart

- **Install.** Copy n lives in `%LOCALAPPDATA%\MJOLNIR\instances\<n>\Halo
  Campaign Evolved`: every game file is a hard link to the Steam install (no
  extra disk, made in a second), and `Meteorite\Binaries\Win64\ue4ss` is a
  real copy, so each copy has its own mods' state files (`native\*.txt`),
  bridge channel and `UE4SS.log`. A hard-linked state file would be shared,
  because mods rewrite those files in place. Crash dumps, logs and the
  function dump are left out. Maps installed in the Steam game later reach a
  copy on its next `mirror`.
- **Saved folder.** `-saveddirsuffix=_mj<n>` gives each copy
  `%LOCALAPPDATA%\Meteorite\Saved__mj<n>` (config, logs, crashes, saves).
- **Steam.** The copies start the exe directly with `SteamAppId` and
  `SteamGameId` set. Steam does not relaunch them, and all share the running
  Steam client and account.
- **Display.** Each copy gets its own `GameUserSettings.ini`: windowed at the
  asked size, every scalability group at its lowest. With the Steam game's
  settings, a fourth copy died at startup in D3D12 (`D3D12Util.cpp` line
  1012). The tool also waits for one copy's bridge before starting the next.

## What stopped a second copy, and the fix for each

1. **The account's cloud settings.** The game keeps the account's settings in
   the cloud with a concurrency token, which it saves in
   `Saved\Config\<account>\HaloGlobalGameUserSettings.ini` and
   `HaloLocalGameUserSettings.ini` (`HaloUserSettingsToken`). A game whose
   token differs from the cloud's signs in and shows the menu, but never
   creates its fireteam lobby: no hosting, no joining, no error. A game with
   no such files uploads its settings, which moves the cloud's token on and
   strands every other install. This happened to the Steam game on
   2026-11-07, after test copies had started fresh. Setting the token to 0
   does not help. **Fix:** before each launch the tool copies the Steam
   install's two files, content and token, into the copy. No copy starts
   fresh, so no copy uploads. If the Steam game itself ever shows the menu
   with no fireteam lobby (`lobby: created` missing from
   `MJOLNIRLobby\native\fireteam.log`), give its two files the cloud's
   current token (the newest `HaloUserSettingsToken` among the copies' files).
   That fixed it on 2026-11-07; the originals are beside them as
   `*.mjolnir-backup-20261107-1200`.

2. **Party allows one device per user.** The fireteam's Party network ships
   with `MaxDevicesPerUserCount` 1. A second copy authenticated into the
   host's network and was removed at once. **Fix:** in test copies the lobby
   DLL's existing `PartyCreateNewNetwork` hook raises devices per user to the
   fireteam size. Users per device and endpoints per device stay as shipped.

3. **The host never starts listening.** A host opens its UE net driver when
   the PlayFab lobby reports a new member. A copy on the same account is no
   new member, because PlayFab lobbies are keyed by entity: the joiner's
   `PFMultiplayerJoinLobby` succeeds (`JoinLobbyCompleted 0x0`, and the
   joiner sees itself as `MemberAdded`), but the host gets no event. The
   joiner's travel to the Party address (`0.0.0.0:5000`) then times out after
   20 s. The event pump is exe `0x6f44150`; its `MemberAdded` case
   broadcasts to a listener bound to exe `0x6f1cc60`, which reads the
   member's `PlatformId`. **Fix:** `up` makes copy 1's menu world a listen
   server (`open /Game/Levels/UI/Frontend/Frontend?listen`) once its lobby
   exists. After that, joins connect and every copy's `GameState` lists every
   player. Doing it before the lobby exists stalls the fireteam flow.

4. **A match started by a lone member goes offline.**
   `UBlamOnlineSessionSubsystem::SetSessionRunning` (exe `0x7abb940`) leaves
   the session when it counts one member. That is always the case on one
   account, so the host dropped its lobby and every copy at the start. **Fix:**
   in test copies the DLL keeps the existing "stay online alone" branch
   patch on permanently (public games already use it).

With 1 to 4 fixed, a match starts and every copy follows the host into the
map by seamless travel.

## How the simulations are joined

The Blam simulation names each machine with an 8-byte identity. On one
account every copy had the same one, so at a match's start each copy saw "the
host is me", hosted its own one-machine session (`life 6`, peer mask 1) and
played alone. Three things in the lobby DLL fix that, all in test copies only,
and on unless `up` is given `--separate` (`MJOLNIR_SIM_JOIN=1`):

1. **The joiner's own identity.** The simulation asks the exe's online
   object for its identity (sim `0x4d1230` reads `[[sim+0x2c40028]+0x10]`,
   vtable `+0x148`, then the object's `+0x18`) and caches it at
   `sim+0x2c0c7d2`, with a flag byte before it. In the exe, `+0x18` (own
   identity) and `+0x20` (id of a new session) come from exe `0x7acc640`;
   `+0x10` and `+0x30` (the host's identity and session) come from exe
   `0x7ab94c0`. Both derive the value from the account. A copy that joins
   another mixes its copy number into the first byte of `+0x18`'s answer and
   of the simulation's new session ids (`+0x20`), then clears the cache flag
   so the simulation asks again. The host keeps the account's identity.
   Without the session-id change the joiner failed at once with "FAILED TO
   JOIN THE HOST'S SQUAD": its own squad session had the host's id, so the
   join found itself.
2. **The host's view of each joiner.** The same 8 bytes are the simulation's
   transport address. The exe's Blam transport (vtable `exe+c11b418`)
   sends and receives through Party endpoints (receive `0x7add6a0` is a
   socket `RecvFrom`; the sender's endpoint id is looked up in a map at
   `transport+0x120`). It registers each peer with exe `0x7ade590`
   (transport, &identity, two endpoint ids). The caller (`0x7adf740`) takes
   the endpoints from a component of each player and the identity from the
   player's UniqueId string, which is the account's for every copy. So the
   host filed every joiner as itself, and refused each join with reason 13.
   Now each joining copy writes its own Party endpoint ids to
   `%LOCALAPPDATA%\MJOLNIR\instances\endpoints\<n>.txt` (from
   `CreateEndpointCompleted` and `PartyEndpointGetUniqueIdentifier`). An
   inline hook on `0x7ade590` gives endpoints a joiner wrote that joiner's
   identity (the account's XOR its copy number), the value its simulation
   uses for itself. The host then accepts the join: its session is
   `life 6` with peer mask 3 (two copies), and the joiner's is `life 4` (a
   peer) in the host's session.
3. **A lone member stays online** (fix 4 above).

The joiners' simulations join just after the host's game has started, so each
joiner arrives as a player joined in progress (player flags `0x8001`), added by
the simulation itself.

Tried and dropped: returning a different lobby owner from `PFLobbyGetOwner`
(no effect, and it emptied the target session).

## The game type each copy plays

The map registry (MJOLNIRLevelLoader's native DLL) stages each match's
variant as `mjolnir.mglo` in the folder the simulation reads it from. It asks
the simulation for that folder, which is still empty when a match is staged,
and fell back to `%LOCALAPPDATA%\Meteorite\Saved\BlamData\HotReload`. A copy
started with `-saveddirsuffix=_mjN` reads `Saved__mjN` instead. So every copy
wrote the Steam game's file and played whatever variant its own folder last
had: CTF on Chill Out ran with no flags and no CTF spawns (2026-11-07). The
registry from that day falls back to `Saved_<suffix>` when the command line
has one, and `deploy` puts this checkout's built registry DLL into each copy
(`native/map_registry/build.ps1`). The Steam game, started with no suffix, is
unchanged. Check a copy's game type from its `map_registry.log`: the
`megalo: ... installed` line should name `Saved__mjN`. Copy tests of game
types before that day ran the wrong variant.

## Teams for joining copies

The joiners' simulations join just after the host's game has started, so
the simulation adds each one as a player joined in progress (player flags
`0x8001`, player-new at sim `0x182000` called from sim `0x4feac0`). Such a
player's team comes from the simulation's balancer (sim `0x2b3f50`), not from
its options. The balancer counts the players who asked for the same team
(player record `+0xad`) by the team they're on (`+0x4a4`) and takes the first
team none of them is on, which put every joiner on team 0 (red). And past the
second player, the team asked for is the slot number (2, 3), which a
two-team game type doesn't have.

So in test copies a hook on player-new, on the host only (its Lua writes
`team_game.txt`), puts a player joined in progress in a team game on red or
blue, whichever the other players are on fewer of (red on a tie: host red,
then blue, red, blue). It flags the change the way the balancer does (sim
`0x4d1d40`: 7, player, `0x1000`), so every copy gets it. On the joiners the
asked-for field keeps the slot number; only the team itself is sent.

## Known gaps

- **HUD "YOU".** The HUD finds "your" row by player key, and every copy is
  `devnull9090`, so every copy's HUD calls the host's team and score "YOU"
  (CTF: "RED / YOU" on a blue joiner). The armour colour and the simulation
  are right. Every player state also reads index 0 in every copy, so the
  host's HUD knows only seat 0 and its team roster to clients names only
  seat 0 (`MJOLNIR|teams|0R`). Board and team checks per seat need PC 2.
- **One account.** Names, kill-feed names, scoreboard rows and match-history
  claims all carry one name. Anything keyed by account (hub match history,
  bans, reports) sees one player.
- Copies use this checkout's MJOLNIRLobby (`deploy`: the DLL, every script
  and `mod.json`) and MJOLNIRHud (scripts and `mod.json`), but the Steam
  install's other mods.
- **A host's leave strands the joiners.** After the host's SAVE AND EXIT or
  `LeaveGame` mid-match, a joining copy lands in a frontend with no host's
  game state and waits out the 120 s connection timeout. Two PCs don't do
  this: the joiner is in the host's lobby within about 2 s. In copies only,
  MJOLNIRLobby cuts the timeout to 1 s after 10 s
  ([multiplayer_postgame.md](multiplayer_postgame.md));
  `MJOLNIR_STRANDED_AFTER=100000` in `up`'s environment keeps the game's
  own two minutes.
- **No rejoin tests.** After a copy leaves (or crashes out of) the host's
  PlayFab lobby, that lobby refuses every join (`JoinLobbyCompleted
  0x89236226`) until both restart, likely because the one account's leave
  takes the host's membership with it. Rejoining needs PC 2.
- `up` re-mirrors each copy, which resets its `fireteam.log` to the Steam
  install's, and `menu` can answer "at the main menu" from a copy's previous
  run: wait for the copy's lobby (`connection <n>`) before joining. `down`
  waits for the copies to exit and 5 s more: a copy launched at once quit
  with no log.
- The endpoint files in `%LOCALAPPDATA%\MJOLNIR\instances\endpoints` carry
  their writer's process id, and `up` and `down` clear them. A copy that had
  gone once left ids the next network reused, and the host filed itself as
  that copy.

## Diagnosis kept in the DLL (test copies only)

- `fireteam.log` gets the result codes of every Party "...Completed" change
  (with `PartyGetErrorMessage` text), the reason of `LocalUserRemoved`, every
  PlayFab lobby event (`lobby event: MemberAdded <entity>`, ...), the lobby
  pump object's vtable, and a hex dump of the first join-request each run.
- Reading a copy from outside: the simulation's sessions (`life`, peer mask,
  ids) are at `[sim+0x2c3cea0]` (two, `0x5b9e8` apart), and the session ids
  at `sim+0x12546c0 + index*0x488`. `blam-players.py --pid` prints players,
  their machines and bipeds.
- `transport: peer <identity> on endpoints <a>/<b> (copy joiner|itself)`: each
  peer the exe's transport files, and `transport: local endpoint <id>` each
  Party endpoint a copy makes.

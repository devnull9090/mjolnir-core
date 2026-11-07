# Several copies of the game on one PC

Multiplayer tests used to need PC 2. `tools/remote/instances.mjs` runs two to
four copies of Halo: Campaign Evolved on PC 1, all signed in to the one
account, all in one fireteam lobby, and takes them into a match together.

What this covers, and what it does not (2026-11-07, CU4 Steam build):

| Layer | Same-account copies on one PC |
|---|---|
| Sign-in, main menu, own fireteam lobby | works, 2 to 4 copies |
| PlayFab lobby and Party network (joining by connection string) | works |
| UE session (listen server, connections, `GameState.PlayerArray`) | works: every copy lists every player |
| Host starts a match; every copy travels to the map with HUD and weapon | works |
| `Net` messages between host and clients (ClientMessage, lobby messages, kicks) | goes over the UE session, so expected to work; not tested one by one |
| Blam simulation (bipeds, kills, objectives, Megalo state) | **not shared**: each copy runs its own one-machine game |

So the copies can test the lobby, the menus, the host flow, travel, the
post-game return and anything carried by UE messages. They can't test
gameplay sync, the scoreboard from the simulation, or game types, because
each copy plays its own match. That still needs PC 2 or a second account; see
"What still blocks the simulation" below.

## The recipe

```
node tools/remote/instances.mjs up 2                                    two copies, 1280x720
node tools/remote/instances.mjs up 4 -windowed -ResX=960 -ResY=540      four copies
node tools/remote/instances.mjs console 1 "mjolnir_auto host BGL slayer private"
node tools/remote/instances.mjs players     each copy: world, UE players, Blam players
node tools/remote/instances.mjs down        stop every copy (never the Steam game)
```

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

## What still blocks the simulation

The Blam simulation names each machine with an 8-byte identity, and on one
account every copy has the same one. The simulation asks the exe's online
object for it (sim `0x4d1230` reads `[[sim+0x2c40028]+0x10]`, vtable
`+0x148`, then the object's `+0x18`) and caches it at `sim+0x2c0c7d2`, with a
flag byte before it. In the exe, `+0x18` (own identity) and `+0x20` (id of a
new session) come from exe `0x7acc640`; `+0x10` and `+0x30` (the host's
identity and session) come from exe `0x7ab94c0`. Both derive the value from
the account through an Online Services interface. The same 8 bytes are the
simulation's transport address too (sim `0x4d14c0` returns the address as
the identity when online). On this account it is `11b8d544b36256b4`, which
the lobby also carries as `OWNERNICKNAME`.

So at a match's start (shell command 0/0, sim `0xf4b0` pulls the target
session), each copy sees "the host is me", hosts its own one-machine session
(`life 6`, peer mask 1) and plays alone.

Tried (in the lobby DLL, test copies only, off unless `MJOLNIR_SIM_JOIN=1`,
which `up N --sim-join` sets):

- Returning a different lobby owner from `PFLobbyGetOwner`: no effect (and
  it emptied the target session). Removed.
- Mixing the copy number into the first byte of the joiner's identity
  (`+0x18`) and of its new session ids (`+0x20`, simulation callers only).
  The joiner's simulation then sends real join-requests (912 bytes,
  carrying its new identity) to the host's session, and they reach the host
  over the copies' own connection. That is the first time a same-account
  copy's simulation asked to join. Before the session-id change it failed
  locally with "FAILED TO JOIN THE HOST'S SQUAD", because the joiner's own
  session had the host's id.
- The host refuses each join with reason 13. Its join handler (sim
  `0x4be8a0`) maps the packet's sender address back to a peer. The host's
  exe files every packet from the joiner under the account identity, which
  is its own (its refusal goes to `11b8d544b36256b4`). That peer has no
  transport channel, so the join fails, and the joiner shows "Lost
  connection to squad leader". Hooking the joiner's exe-side identity too
  did not change what the host sees, so the host takes the address from its
  own view of the connection's account, not from the packet.

Next steps, in order of cost:

1. **Two copies only:** remap at the host's exe-to-simulation transport
   boundary. Packets from the one remote connection become the joiner's
   identity, and sends to that identity go to the connection. It needs the
   exe's packet delivery into the simulation found, and it can't tell three
   or more same-account copies apart.
2. **Any number of copies:** make the host's exe derive a remote copy's
   identity from something per copy (each copy would announce its number,
   and exe `0x7ab94c0` / `0x7acc640` and the address mapping would use it).
   This means more identity work in the online layer.
3. **A second account.** A second Steam account (a second Steam client in a
   sandbox) and a second Microsoft account give a genuinely different
   identity everywhere. This needs accounts only the user can create.

## Diagnosis kept in the DLL (test copies only)

- `fireteam.log` gets the result codes of every Party "...Completed" change
  (with `PartyGetErrorMessage` text), the reason of `LocalUserRemoved`, every
  PlayFab lobby event (`lobby event: MemberAdded <entity>`, ...), the lobby
  pump object's vtable, and a hex dump of the first join-request each run.
- Reading a copy from outside: the simulation's sessions (`life`, peer mask,
  ids) are at `[sim+0x2c3cea0]` (two, `0x5b9e8` apart), and the session ids
  at `sim+0x12546c0 + index*0x488`. `blam-players.py --pid` prints players and
  the machine mask.

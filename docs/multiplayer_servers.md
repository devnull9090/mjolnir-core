# Server list and hosting

**Question:** how do players find games and host them, and can a game run on
a dedicated server that players connect to?

**Short answer:**
- Every game is already hosted by a player: the host's game is a listen
  server, and PlayFab Party carries the traffic. The server list needs only
  client glue on top of the hub API, which is already live.
- A true dedicated server is not possible: there is no server binary, and no
  way to run the Blam sim outside the game client.
- A **headless host** is possible: the real game, with no window, run on a
  machine with a GPU. It signed in, hosted Blood Gulch Slayer and spawned a
  Spartan on 2026-10-02.

Status as of 2026-10-02 (CU4).

## What exists

| Piece | Where | Status |
|---|---|---|
| Lobby API: register, heartbeat, remove, list, join | `hub/src/lib/api/lobby.ts`, migration `0012_maps_and_lobbies.sql` | Live in prod (`GET /api/v1/lobbies` answers `{"lobbies":[]}`) |
| Games page on the website | `hub/src/app/games/page.tsx` | Live, empty |
| `lobbies:write` on launcher device keys | `hub/src/lib/api/device.ts` `DEVICE_SCOPES` | Live |
| Host flow: MULTIPLAYER, HOST GAME, map, game type, START | `mods/MJOLNIRLobby` | Shipped |
| Lobby and Party caps raised to 16 | `native/lobby` | Shipped (mods 0.10.0) |
| FIND GAMES, JOIN PRIVATE | `mods/MJOLNIRLobby/Scripts/main.lua` | Stubs ("not yet") |
| Anything that registers a game or joins one by connection string | — | Not built |

The listing hides the connection string. A client gets it from `/join`, which
requires sign-in. See the header comment in `lobby.ts`.

## How a game is hosted today

- The host's game creates a PlayFab lobby (membership) and a PlayFab Party
  network (traffic), then opens a `PlayFabNetDriver` when the first remote
  player arrives ([fireteam_join_and_cap.md](fireteam_join_and_cap.md)).
- Party traffic goes through Microsoft's relays, so hosts need no port
  forwarding. The game opens only UDP 57716+.
  - The exe carries `DirectPeerConnectivity` strings. The game's setting for
    it is unread.
- The lobby is Private, with no owner migration. **When the host leaves, the
  game ends.** That is the main argument for always-on hosts.
- Joining needs only the lobby's connection string, which reaches
  `PFMultiplayerJoinLobby` through `JoinSession` or the Steam
  invite-accepted path. The exe imports `PFLobbyGetConnectionString`.

## The server list (player-hosted)

Three pieces of glue, all on the client side.

1. **Host registers its game.**
   - `native/lobby` already hooks `PFMultiplayerCreateAndJoinLobby`. It
     should also keep the lobby handle and call `PFLobbyGetConnectionString`
     once the create completes.
   - It should `POST /lobbies` with map, game type, players and the
     connection string, then heartbeat every 30 s with player count and
     state (`open`, `in_game`, `full`), and `DELETE` on leave.
   - UE4SS Lua has no HTTP, so the requests go out from the native DLL
     (WinHTTP). Lua tells it the map, game type and player count.
2. **FIND GAMES lists games.**
   - A cooked widget beside the lobby (chunk 984), filled from
     `GET /lobbies`, sorted by the estimated ping.
   - Grey out games whose map pack isn't installed, or let the launcher
     fetch the map first.
3. **Join by connection string.**
   - `/join` returns the string. The native DLL hands it to the game's own
     invite-accepted flow, as a Steam invite does.
   - **Unverified:** no join by connection string has been tried yet. Every
     two-PC join so far went through a Steam invite. Test this first,
     because the rest depends on it.

**Auth.** `POST /lobbies` and `/join` need a key with `lobbies:write`. The
launcher's device key already has it. The launcher can write the key where
the native DLL reads it, so players never paste a key. Players without the
launcher can't host listed games or join through the list. Invites still
work for them.

**JOIN PRIVATE** can be the same path with a short code: the host registers
the game as unlisted and the hub maps the code to the lobby.

## Dedicated servers

### A. An Unreal dedicated server: not possible

- The shipping exe is a game target, not a server target.
  `IsRunningDedicatedServer` is not in it.
- PlayFab's own server product (`JoinLobbyAsServer`,
  `RequestMultiplayerServer`) needs the title's server credentials. Those
  belong to the publisher.

### B. The Blam sim on its own: not practical

`HaloSimulation_tag_release.dll` could in principle be loaded by our own
process. But clients are Unreal clients:
- they expect an Unreal server speaking UE replication (GameState,
  PlayerState, the BlamExperience readiness flags, pawns), with the Blam
  network endpoints carried inside it;
- all of it runs over PlayFab Party, under a PlayFab identity of the title.

That means reimplementing an Unreal server around the sim. Not worth it.

### C. A headless host: works, with a GPU

The real game with no window, hosting through the normal menu path, driven
by script. Tested 2026-10-02 on PC 1, as a second process launched directly
(`SteamAppId=2806050`):

| Launch flags | Signs in | Starts a map |
|---|---|---|
| `-nullrhi -nosound -unattended` | Yes. No GPU driver loads; reaches the frontend in about 2 min | **No.** `StartCountdown` never returned. The game thread hung (190 s and counting), with about 9 cores busy. |
| `-RenderOffScreen -nosound -unattended` | Yes | **Yes.** BGL, Slayer under Megalo, HUD hooks armed, one Spartan spawned |

Sign-in without input: call the title screen's own click event,
`WBP_TitleMenu_C:BndEvt__WBP_TitleMenu_WBP_MeteoriteStandaloneButtonDefault_K2Node_ComponentBoundEvent_1_CommonButtonBaseClicked__DelegateSignature(nil)`.
Then wait for `MULTIPLAYER is on the main menu`. The account is whatever
Steam is signed in as.

Cost at BGL with no players: about 6–7 CPU cores, 55–60% of the GPU's 3D
engine, and 8 GB of working set. `t.MaxFPS 30` and the low `sg.*` settings
barely changed it. Whether those console variables applied was not checked.
`-ResX/-ResY` may be ignored offscreen.

What a headless host still needs:
- **One Steam account and one game licence per server.** PlayFab membership
  is per account (two instances on one account rejoin as the same member).
- **A Windows machine with a GPU.** `-nullrhi` can't start a map. WARP
  (software D3D12) is untested.
- **Its own player out of the game.** The host is a real player and takes
  one of the 16 slots. Options: a Megalo variant that parks it (invisible,
  invulnerable, off the map), plus filtering it out of the scoreboard and
  kill feed. The sim may also allow it never to spawn. Untested.
- **A host loop.** Host on start, register with the hub, rotate maps (the
  post-game vote already exists), watchdog and restart on a hang, and
  re-host after a game update.
- Two hosts can share one PC if each has its own account.

## Recommended order

1. **Join by connection string**, two PCs, no UI: the host logs its
   connection string, PC 2's native DLL joins with it. Everything below
   depends on this.
2. **Register and heartbeat** from `native/lobby`, with the key handed over
   by the launcher. The game appears on the website's Games page.
3. **FIND GAMES** in game, plus missing-map handling.
4. **JOIN PRIVATE** by short code.
5. **Headless host**, once players can find games:
   - the host player hidden;
   - the loop and watchdog;
   - a `mjolnir host` command or launcher mode that runs it.

   Its value is games that outlive their host and an always-full list. It
   costs a GPU machine and a game copy per server.

## Open questions

- Does a Private lobby accept a join by connection string from a stranger?
  Expected yes, per PlayFab's model; not tested.
- Can the host's player be kept from spawning, or must it be parked?
- WARP for a GPU-less host, and why `-nullrhi` hangs at map start (PSO and
  loading-screen waits are the likely suspects).
- Game Pass: the same PlayFab path, untested.

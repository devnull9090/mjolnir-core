# Server list and hosting

**Question:** how do players find games and host them, and can a game run on
a dedicated server that players connect to?

**Short answer:**
- Every game is hosted by a player: the host's game is a listen server, and
  PlayFab Party carries the traffic.
- Public games are built: a host switches its lobby to PUBLIC GAME, the game
  is listed on the hub, and FIND GAMES joins it through the game's own
  invite flow (below).
- A true dedicated server is not possible: there is no server binary, and no
  way to run the Blam sim outside the game client. A headless host (the real
  game, windowless) works on a GPU machine, but the idea was dropped on
  2026-10-02. The findings are kept below.

Status as of 2026-10-02 (CU4).

## What exists

| Piece | Where | Status |
|---|---|---|
| Lobby API: register, heartbeat, remove, list, join | `hub/src/lib/api/lobby.ts`, migration `0012_maps_and_lobbies.sql` | Live in prod |
| Games page on the website | `hub/src/app/games/page.tsx` | Live |
| `lobbies:write` on launcher device keys | `hub/src/lib/api/device.ts` `DEVICE_SCOPES` | Live; keys paired before it lack the scope (403 `insufficient_scope`) |
| The lobby's connection string | `native/lobby` `mjolnir_lobby_connection` | Verified: `cv2:...`, 106 characters, membership unlocked, max 16 |
| Join by connection string | `native/lobby` `mjolnir_join` (OnlineTick hook) | Verified on one PC: the game left its lobby and called `PFMultiplayerJoinLobby` with our string, then showed its own FAILED TO JOIN for a fake one |
| Hub calls from the game | `native/lobby` `mjolnir_hub_call` (WinHTTP) | Verified: `GET /lobbies` 200 |
| PRIVATE / PUBLIC GAME, FIND GAMES | `mods/MJOLNIRLobby/Scripts/games.lua`, `main.lua`, `WBP_MJOLNIRFindGames` | Built, solo-verified; two-PC test pending ([two_pc_test.md](two_pc_test.md), Phase 5) |

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

## Public games

**Hosting.** The lobby's PRIVATE GAME button switches to PUBLIC GAME (host
only; every session starts private). While public, `games.lua`:
- reads the PlayFab lobby's connection string from the native half;
- `POST /lobbies` with the map, game type, players and the string;
- heartbeats every 30 s, and at once after a map, game type or start
  changes, with players, state (`open`, `in_game`, `full`) and the current
  string (the game makes a new lobby after leaving one);
- `DELETE`s the listing when the host goes private or joins another game. A
  game that quits drops out when its heartbeat goes stale (90 s).

The lobby's footer says why a game isn't listed (no launcher sign-in, an old
key, the hub unreachable).

**FIND GAMES** (`WBP_MJOLNIRFindGames`, chunk 984) lists up to 12 public
games, nearest first. A row is map / game type / players. The details show
the host, state, ping estimate, a missing map, and a different MJOLNIR Lobby
version. JOIN refuses a map that isn't installed.

**Joining.** JOIN gets the string from `/lobbies/{id}/join` and writes it to
`native\join_request.txt`. `mjolnir_join` queues it, and the next
`FOnlineAsyncTaskManagerSteam::OnlineTick` (online thread) calls the task
manager's own `GameRichPresenceJoinRequested_t` handler with it. That handler
is what a Steam "Join Game" runs:
- it builds `FOnlineAsyncEventSteamInviteAccepted`;
- a connect string without `SteamConnectIP=` is stored whole as
  `CONNECTIONSTRING`;
- the game leaves its fireteam and joins the host's.

How the native half finds it, by pattern rather than address:
- `OnlineTick` by its body bytes; exe RVA `0x6a7b580` on CU4, the only
  pointer to it is vtable slot 6 at `0xbc86b00`;
- the handler by scanning the task manager for the `CCallback` whose
  `m_iCallback` is 337 and whose `m_pObj` is the manager (+0x380 on CU4,
  `m_Func` `0x6a7b5d0`).

The handler converts the connect string as a C string, so Steam's 256-byte
limit doesn't apply. Today's strings are 106 characters anyway.

**Auth.** Listing needs `lobbies:write`; `/join` needs any signed-in key. The
native half reads the launcher's key from
`%APPDATA%\com.devnull9090.mjolnir-launcher\hub_auth.json` and sends it to
the hub only. Players without the launcher can still host for, and be
invited by, friends.

**Not built:** JOIN PRIVATE by short code (an unlisted registration the hub
maps to the lobby); the launcher fetching a missing map before a join.

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

### C. A headless host: works with a GPU (dropped 2026-10-02)

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

## Open questions

- **Can a player join a match in progress?** The host's lobby membership is
  unlocked at the menu; whether the game locks it in a match, and whether a
  late client gets a seat in the sim, is untested. The local-guest research
  found the sim roster fixed at launch,
  but that was a local `CreatePlayer`, not a network join.
- Does a Private lobby accept a join by connection string from a stranger?
  Expected yes, per PlayFab's model; not tested with a real host.
- Game Pass: the same PlayFab path, untested. Its online subsystem may not
  be Steam, so the join hook would need another route there.
- Headless host (dropped): keeping its player from spawning; WARP for a
  GPU-less machine; why `-nullrhi` hangs at map start.

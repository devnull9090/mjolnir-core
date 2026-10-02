# Fireteam join path and player cap (CU4)

**Question:** can players join a host's converted-map game from our own lobby
service, on Steam and Game Pass alike, and can a game hold more than four?

**Short answer:** yes on joining. The PlayFab join needs only the lobby's
connection string, not an invite. Toward 16 players there are four separate
caps to raise, none of them known to be impossible.

- Measured 2026-10-01 on CU4, statically (the exe disassembled with capstone)
  and by live reflection. Nothing was patched or tested with a second player.
- Exe RVAs are relative to `0x140000000`, the simulation DLL's to
  `0x180000000`. They move with each update.
- The CU3 study before it is on the `mjolnir/coop-lobby-8-players-de2bcd`
  branch (`docs/coop_player_cap.md`, `tools/pe/lobby_size_hook.py`).

## The stack

The session layer is Microsoft's OnlineSubsystemPlayFab:
`DefaultPlatformService=PlayFab`, `NativePlatformService=Steam`. Two PlayFab
libraries sit under it:
- **PlayFab Multiplayer lobbies** carry membership and the connection string.
- **PlayFab Party** carries the network traffic.

The Friends roster (`WBP_Roster_C`) lists Xbox, PlayStation, Steam and WinGDK
friends, each `Joinable` or `NotJoinable` (`ERosterJoinability`). The game
can join a friend's fireteam from the roster, without an invite. Invites are
platform-native: `PFMultiplayerSendInvite` is not imported.

## Joining

| What | Where | Status |
|---|---|---|
| The one `PFMultiplayerJoinLobby` call | `0x6f41e7c` in `0x6f417c0`; the string is the session setting `CONNECTIONSTRING` | Verified |
| Reached from IOnlineSession::JoinSession | `0x6f1fcd0`, `0x6f1fa10` (vtable `0xbde6c10`) via `0x6f1f210` | Verified |
| Steam invite accepted | `0x6aa6960` (`FOnlineAsyncEventSteamInviteAccepted` vtable `0xbc83420`). A URL without `SteamConnectIP=` is stored whole as `CONNECTIONSTRING`, then "invite accepted" is raised | Verified |
| Steam rich presence `connect` = the host's connection string | `0x6aaa4cd`, from `0x6aabf20` | Inferred |
| `+connect X` on the command line | becomes `-SteamConnectIP=X` (`0x6aaba07`): the IP path, not a lobby | Observed |
| Reflected entry points | stock `JoinSessionCallbackProxy`/`FindSessionsCallbackProxy` (the result struct is opaque to Blueprint); `MeteoriteLobbyNotifier.AcceptInvite(ToastInitData)` (no connection string in reflected fields); `UBlamOnlineSessionSubsystem` (`0x7abee20`–`0x7ada000`) has `PendingInvite`, `DeferredInvite`, `JoinRemoteSession` natively, with only `IsReadyToPlay` reflected | Observed |

**Route for our lobby service.**
1. The host publishes its lobby connection string. It can come from
   `PFLobbyGetConnectionString`, or from its Steam rich presence `connect`.
2. A joiner's native mod hands the string to the game's own invite-accepted
   flow, the way a Steam invite does. `UBlamOnlineSessionSubsystem` then
   leaves and joins as it would for a real invite.
3. The fallback is calling JoinSession with a search result whose settings
   hold `CONNECTIONSTRING`.

The PlayFab half is the same on Game Pass. That binary isn't on this box, so
Game Pass is unverified.

## Finding lobbies

- `PFMultiplayerFindLobbies` is called at `0x6f1a347`, from FindSessions
  (`0x6f19210`). It builds OData filters (`lobby/memberCount`,
  `lobby/amMember`, search keys).
- Lobbies are created at `0x6f40aaf`–`0x6f40ade`:
  - owner migration: none;
  - access: **Private**, unless the session is advertised, then Public (or
    Friends with presence-join friends only);
  - search properties `string_key1`, `string_key2`, plus `PlatformId`,
    `PlatformModel=WIN64`, `OWNERNICKNAME`, `_flags`.
- Co-op lobbies are Private, so a search never finds them. A Private lobby
  can still be joined by its connection string, which is why our own service
  is the place to list games.

## The caps

| Layer | Where | Value | Status |
|---|---|---|---|
| PlayFab lobby `maxMemberCount` | `CreateAndJoinLobby` at `0x6f4156e` in CreateSession `0x6f40880`: from `FOnlineSessionSettings.NumPublicConnections` (settings+8) | 4 today; the game code supplying it not traced | Verified |
| Native (Steam) presence session after a PlayFab join | `0x6f2007b` | `NumPublicConnections = NumPrivateConnections = 4`, a literal | Verified |
| PlayFab Party network | `PartyCreateNewNetwork` `0x6f375dc`; fields loaded at `0x6f2eecb` from `[OnlineSubsystemPlayFab]` MaxDeviceCount, MaxUserCount, MaxUsersPerDeviceCount, MaxDevicesPerUserCount, MaxEndpointsPerDeviceCount | ini values unread (in the Oodle-compressed paks) | Verified as ini-driven |
| Unreal `GameSession.MaxPlayers` | `HaloOnlineGameSession` | 4; MJOLNIRCoop8 raises it, rebuilt every level | Verified (CU3) |
| Simulation players array | `0x181010` (sim DLL) | **16** of `0x4B0` bytes. CU3 notes read 32: `0x20` there is the name buffer, not the count | Verified |
| `k_maximum_campaign_players` | block definition `0x9bb460` | 4 | Verified |
| `net_maximum_player_count` | registered at `0x9a3dd8` | value unread | Verified present |
| Network co-op refusal | `error_too_many_players_for_network_coop` = `0x50000a` (table `0x8384e8`) | where it is raised not found | Verified present |

**Route toward 16:**
1. Raise `NumPublicConnections` before CreateSession (or the CU3 IAT stub on
   `PFMultiplayerCreateAndJoinLobby`, CU4 IAT slot `0xa8bb630`).
2. Patch the presence session's literal 4 at `0x6f2007b`.
3. Make Party's MaxUserCount and MaxDeviceCount at least 16.
4. Keep raising `GameSession.MaxPlayers`.
5. Find the simulation's network co-op check.

## Unknowns

- PlayFab may reject a larger `maxMemberCount`, depending on the title's
  configuration.
- The Party ini values.
- Where the sim raises `0x50000a`, and `net_maximum_player_count`'s value.
- Whether Steam presence lobbies cap at 4 elsewhere.

None of this can be settled without a second machine or account in the
lobby.

## Other CU4 RVAs

IAT: `PFMultiplayerJoinLobby` `0xa8bb5f8`, `PFMultiplayerCreateAndJoinLobby`
`0xa8bb630`, `PFMultiplayerFindLobbies` `0xa8bb608`. Party connect `0x6f37900`.
Steam command-line parser `0x6aab2a0`.

## Raising the caps in game (2026-10-02, two PCs)

MJOLNIRLobby's native half (`native/lobby`, `mjolnir_fireteam_open`) now does
three things at startup, all found at runtime by import name or byte pattern:
- hooks `PFMultiplayerCreateAndJoinLobby` (IAT) and raises `maxMemberCount`;
- hooks `PartyCreateNewNetwork` (IAT) and raises the Party limits;
- patches the presence session's two literal 4s (the unique 24-byte pattern
  at exe RVA `0x6f2007b`).

MJOLNIRLobby holds `GameSession.MaxPlayers` at 16. `native\fireteam.log`
records each call:

```text
party: users 4 devices 4 users/device 2 devices/user 1 endpoints/device 3 (options 15)
party: users 16 devices 16
lobby: maxMemberCount 4 -> 16
```

The incoming Party values match the shipped `[OnlineSubsystemPlayFab]`
section (MaxUserCount 4, MaxDeviceCount 4, MaxUsersPerDeviceCount 2,
MaxDevicesPerUserCount 1, MaxEndpointsPerDeviceCount 3), which confirms
`PartyNetworkConfiguration`'s field order. Both calls happen at sign-in.
A user `Saved/Config/Windows/Engine.ini` is deleted by the game at startup,
so the ini route is closed.

**Results:**
- **More than four players join.** PC 2 joined a host that already had three
  `CreatePlayer` guests: five players in `GameState.PlayerArray`, five
  player states, one `PlayFabNetConnection`.
- **Keep Party's per-device limits as shipped.** Raising users/device to 4
  and endpoints/device to 5 made every remote join time out, with or without
  guests: `ClientTravel` to the Party address (`0.0.0.0:5000`) gives up after
  exactly 20 s with "CONNECTION LOST / Disconnected from host", although the
  lobby join, the Party connect, authentication and endpoint creation all
  return 0 on the client and the host's lobby sees the member arrive.
- The host has no net driver at the frontend. It creates a
  `PlayFabNetDriver` when the first remote player arrives.
- **Local guests added before the first remote player block that join**
  (the same 20 s timeout). Guests added after a remote player has joined do
  not block later joins, up to four local players. `CreatePlayer` guests
  never pass through `UBlamOnlineSessionSubsystem::AddSplitscreenPlayerToSession`;
  the game's own `HaloOnlineGameInstance:LoginSplitScreenPlayer` does nothing
  without a second input device.
- **More than two local players on one PC freeze a match at its start**:
  black screen on every machine, nothing responds, `player_spawn` still
  fires. This happens offline too (host plus two guests, no remote player),
  so it is a splitscreen limit, not the fireteam's. Host, one guest and one
  remote player play Slayer normally.
- CTF with three players raised `game_over` (cause -1) about 15 s in; Slayer
  did not.

So a five-player match needs five machines, or a fix for three local players
on one; two PCs reach four players at most (two per machine).

### The FIRETEAM panel

`MeteoriteSquadLobbyViewModel.SquadMembers` always holds four slots: the
players, then blank INVITE + rows. A fifth player gets no row and the header
reads "n/4". MJOLNIRLobby's `squadpanel.lua` rebuilds the difference after
the panel's own `BackingDataChanged` and `UpdateHeader`: a row for every
player in the game state, one INVITE + row while there is room, and
"Fireteam n/16".
- A row's widget class travels with its item in a native field. The list's
  `EntryWidgetClass` is only the fallback, read whenever the list builds the
  row, so a fresh item gets whichever class happens to be set by then.
  Player rows are therefore constructed with one of the view model's own
  player items as the template, which carries the class.
- An added row's `MeteoritePlayerViewModel` holds the name, platform and
  player state. `CanKickFromFireteam` returns true on it, so its menu offers
  Kick.

Removing a `CreatePlayer` guest with `GameplayStatics:RemovePlayer` crashed
the game.

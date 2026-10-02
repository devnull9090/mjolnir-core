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

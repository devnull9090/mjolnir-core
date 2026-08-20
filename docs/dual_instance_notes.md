# Running Two Game Instances at Once

**Date**: 2026-08-08
**Status**: Two concurrent instances verified working. Same-lobby co-op requires a second
account — the identity constraint, not the process constraint, is the real wall.

> **Build label:** installed build is CU3 per [`build_lock.md`](build_lock.md). Everything
> below was exercised against the current Steam install on this machine.

---

## The question

Can two windowed copies of Halo: Campaign Evolved run on one machine, and can they join
the same co-op lobby — possibly by faking the second player's identity?

## Verified: two instances run concurrently

Experiment performed 2026-08-08:

1. Instance 1 launched normally (`steam://rungameid/2806050` via `game_launch`), reached
   the frontend, bridge answering.
2. Instance 2 launched by **starting the exe directly** with the environment Steam would
   have set:

   ```powershell
   $env:SteamAppId = "2806050"; $env:SteamGameId = "2806050"
   Start-Process "...\Meteorite\Binaries\Win64\HaloCampaignEvolved.exe"
   ```

3. Both processes coexisted (pids 13392 / 28692, ~4–6 GB working set each). The second
   instance reached the title screen, **signed in with the cached account**, and landed on
   the full main menu (`RESUME SOLO GAME / CAMPAIGN / PLAY CO-OP / CUSTOMIZATION`).
4. Both instances were **signed in simultaneously on the same account**. Neither was
   kicked, errored, or bounced back to Steam.

Supporting static facts:

- No game-specific single-instance mutex string was found in the exe.
- The exe's Steamworks import surface (`SteamAPI_Init`, `SteamInternal_ContextInit`, …)
  does **not** include `SteamAPI_RestartAppIfNecessary`, consistent with the direct exe
  launch not bouncing through Steam. `steam_api64.dll` ships at
  `Engine\Binaries\ThirdParty\Steamworks\Steamv157\Win64`.
- Steam itself does not block the second process because Steam never sees it — only the
  first launch went through the Steam client.

## Verified: the co-op flow is invite-only, through friends

`PLAY CO-OP` opens a **FRIENDS** screen with two tabs:

- **PLATFORM** — the Steam friends list, each row an `+ Invite` button.
- **CROSS-PLATFORM** — with the hint text: *"Cross-platform friends must be in the Main
  Menu to receive in-game invites."*

No lobby browser, no join code, no direct connect, no LAN entry. A string sweep of the
exe found no LAN/offline-session vocabulary either. This matches the known online stack
(`OnlineSubsystemPlayFab` + PlayFab Lobby + Party relay; see
[`multiplayer_investigation_notes.md`](multiplayer_investigation_notes.md)).

**Consequence:** two instances on the *same* account have no UI path into one lobby — an
account cannot friend or invite itself.

## Identity analysis — how to get a second player

The lobby stack is PlayFab. On Steam the client authenticates to PlayFab with a Steam
session ticket (`/Client/LoginWithSteam` is in the binary along with the whole PlayFab
SDK login surface); the XSAPI/XAL plugin is compiled in for the Xbox/cross-platform
identity side.

| Route | Verdict |
|---|---|
| **Second Steam account** (own copy or Steam Family), second Steam client isolated in a second Windows session or sandbox | Should work — real identity end to end. Friend the two accounts, invite via the PLATFORM tab. **Unverified** on this machine. |
| **Steam copy + Game Pass copy**, two different Microsoft accounts | Should work via the CROSS-PLATFORM tab (second instance sits at its main menu to receive the invite). The launcher already knows how to detect/launch the Game Pass SKU. **Unverified.** |
| **Steam emulator (Goldberg etc.) faking a second SteamID** | Almost certainly a dead end for co-op: PlayFab validates the Steam session ticket **server-side**, so a fabricated ticket fails login, and there is no LAN/offline session mode to fall back to. The game would likely run but be unable to reach the lobby service. **Unverified but low-probability.** |
| **Same account, self-join via reflection** — drive `BlamOnlineSessionSubsystem` / PlayFab `CreateLobby`/`JoinLobby` with a connection string, bypassing the friends UI | Worth one experiment. PlayFab lobby members are keyed by entity, so the same account joining twice is probably treated as a *reconnect* of the same member rather than a second player. **Unverified.** |

## Hazards for tooling and for actually playing this way

- **Both instances load UE4SS and share `mjolnir-bridge/`.** Both bridge mods poll the
  same `request.txt`, so which instance serves a request is a race. The MCP game tools
  are single-instance by assumption; do not trust `game_lua`/`game_status` while two
  copies run.
- **`capture.ps1` and `input.ps1` select the first process by name.** Per-PID scratch
  variants were used for this experiment; a `-TargetPid` parameter would make the shipped
  tools dual-instance safe.
- **`GameUserSettings.ini` and the save directory are shared.** Last writer wins on
  settings; window size/mode changes in one instance can affect the next launch of the
  other. Windowed 1280x720 was forced for the test, but a focused instance was observed
  restoring itself to 2560x1440.
- Memory: ~5–6 GB RAM per instance at the frontend. Two in-mission instances will double
  GPU load; untested.

## 2026-08-08 follow-up: the reflection self-join experiment

**Status: blocked at the native boundary.** Run the same day with both instances driven
independently — the bridge now supports an instance channel (below) — signed in on the
same account, both at the main menu with the co-op roster open.

What the reflected surface actually offers, and where each path ends:

- `BlamOnlineSessionSubsystem` reflects exactly one function: `IsReadyToPlay`. The
  create/find/join session proxies the earlier notes mentioned are the *generic PlayFab
  REST SDK* (`/Script/PlayFab.PlayFabMultiplayerAPI:CreateLobby/JoinLobby/...`), which
  the game's own flow does not use — and which has no auth: the native client's entity
  token lives in `PlayFabMultiplayerWin.dll`, not in the BP SDK's auth context.
- The join UI path is `MeteoriteProfilePuckBase:JoinOtherPlayer()` /
  `MeteoriteProfileTrayWidgetBase:JoinFriend()` — both parameterless; they act on the
  row's bound `RosterFriendItemData`. That object carries **display-only** fields
  (DisplayName, Presence, Status, PlatformType, Joinability); `IdentifierName` reads
  `None` on every live row. The friend's real identity is held in native maps the
  reflection layer never sees.
- `MeteoriteLobbyNotifier:AcceptInvite(MeteoriteInviteToastInitData)` is the invite-accept
  entry, but the init data holds only cosmetics plus a `FPlatformUserId` — a *local user
  slot handle*, not a network identity. It selects which pending **native** invite to
  accept; with no native invite queued (same account cannot invite itself on any tab),
  there is nothing to accept.

**Verified by forging:** constructing a `RosterFriendItemData`, binding it with
`SetProfileLink`, and calling `JoinOtherPlayer()` dispatches a real join attempt that
reaches the online service and fails with the game's generic **"Failed to Join —
Something went wrong. Try again later."** alert. This happens for an offline friend's
real row and for forged rows carrying an arbitrary name or the account's exact display
name (`devnull9090`). Display name is not the resolution key; a row without a native
friend record behind it cannot join anything. The host instance never noticed any of it
(squad count 1, no alerts). Side effect observed on the joining instance:
`bOfferJoinSlots` flipped to false after the failed attempts.

**Why deeper effort is unlikely to pay off same-account:** PlayFab Lobby membership is
entity-keyed — one entity occupies one member slot, and a second join by the same entity
is treated as a reconnect, not a second player. Even a native-level self-join (hooking
`PFMultiplayerJoinLobby` in `PlayFabMultiplayerWin.dll` and injecting the host's
connection string) would most likely displace the host's membership rather than add a
player. The identity wall is structural: **two players in one lobby requires two
accounts.**

### Bridge instance channels (shipped alongside this experiment)

`mods/MJOLNIRBridge/Scripts/main.lua` now reads `MJOLNIR_INSTANCE` from the process
environment. Unset (any Steam launch) keeps the plain `request.txt`/`response.txt`/
`status.txt`; a process launched with `MJOLNIR_INSTANCE=2` answers on
`request-2.txt`/`response-2.txt`/`status-2.txt`. This removes the both-instances-execute-
every-request hazard for the second instance; the MCP client tooling still only speaks
the default channel (a scratchpad PowerShell client was used for channel 2).

## Next experiments

1. The real second-account test, whichever SKU pair is available (Steam+Game Pass with
   two Microsoft accounts is the least infrastructure).
2. Plumb the instance channel through `tools/mcp/game` (client-side pid/channel
   selection for lua/console/capture/input).

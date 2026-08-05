# MJOLNIR Multiplayer Investigation — Session Notes
**Date**: 2026-07-25 ~11:50 PM PST
**Conversation ID**: `f74b07be-cdb9-4b3f-ac8b-b193380aa670`

> **Build label:** this note is stamped CU2; the installed build is CU3. The 13 root
> world package paths below have been re-verified against CU3; nothing else here has.
> See [`build_lock.md`](build_lock.md).

---

## 🗂️ Key Paths

| What | Path |
|:-----|:-----|
| Project repo | `C:\haloce` |
| Game install | `C:\Program Files (x86)\Steam\steamapps\common\Halo Campaign Evolved` |
| Game EXE | `...\Meteorite\Binaries\Win64\HaloCampaignEvolved.exe` (230 MB) |
| Simulation DLL | `...\Meteorite\Binaries\Win64\HaloSimulation_tag_release.dll` (14.6 MB) |
| PlayFab DLL | `...\Meteorite\Binaries\Win64\PlayFabMultiplayerWin.dll` (1.8 MB) |
| Party DLL | `...\Meteorite\Binaries\Win64\PartyWin.dll` (4.0 MB) |
| UE4SS install | `...\Meteorite\Binaries\Win64\ue4ss\` |
| UE4SS log | `...\ue4ss\UE4SS.log` (255 KB, 3502 lines) |
| Pak files | `...\Meteorite\Content\Paks\` (40+ GB main chunk) |
| LogicMods | `...\Meteorite\Content\Paks\LogicMods\` (EMPTY — ready for BP mods) |
| Ghidra | `C:\tools\ghidra_12.1.2_PUBLIC` |
| Installed mods | `...\ue4ss\Mods\mods.txt` |

> **NOTE**: Historical `PenguinHotel` references came from MECCHA Chameleon (a different game), NOT from Halo CE. The real game module name is `Meteorite`.

---

## 🔥🔥🔥 LATEST FINDING: Main EXE Reveals Full Architecture

String search on `HaloCampaignEvolved.exe` (completed as background task) revealed:

### UE5 Plugin Structure (i343 = 343 Industries)
```
Plugins/i343/BlamEngine/Source/BlamEngine/Public/Objects/GameEngineTraits/BlamGameEngineVariant.h
Plugins/i343/BlamEngine/Source/BlamGlue/Public/UnrealGlue/Subsystems/BlamEngineGlueOuterSubsystem.h
Plugins/i343/BlamEngine/Source/BlamSynchronization/Private/Components/ObjectTypes/VehicleTypes/BlamVehicleFighterComponent.cpp
Plugins/i343/BlamEngine/Source/BlamSynchronization/Private/Components/ObjectTypes/VehicleTypes/BlamVehicleWithEngineComponent.cpp
Plugins/i343/BlamEngine/Source/BlamSynchronization/Private/DebugMenuWidgets/SBlamDebugMenuItemWidget.cpp
Plugins/i343/BlamEngine/Source/BlamSynchronization/Private/DebugMenuWidgets/SBlamDebugMenuWidget.cpp
Plugins/i343/BlamEngine/Source/BlamSynchronization/Public/BlamAnimNotify.h
```

### Key UE5 Script Modules
```
/Script/BlamEngine              ← THE BLAM ENGINE UE5 PLUGIN MODULE
/Script/Meteorite               ← THE GAME'S OWN MODULE
/Script/MeteoriteOnlineServices ← ONLINE SERVICES MODULE!
/Script/DataflowSimulation
```

### FBlamEngineLauncher Class
```
FBlamEngineLauncher::RegisterShellOutputHandlerCallbacks()
  - Has 4+ lambda callbacks for handling simulation output
```

### Critical CVars / Config Variables
```
bDesireClangHaloSimulationDll   ← LOADS THE SIMULATION DLL!
bDisableBlamEngine              ← CAN DISABLE THE BLAM ENGINE
bEnableSimulation / bDisable... / bSuspendSimulation
bResetSimulation
bLockToSimulationFrameRate
bLiveSimulation / bLocalSimulation / bClientSimulation
bIsSimulationDirty
AdvanceSimulation / AdvanceSimulationByTime
CanTriggerResimulation
bEnablePhysicsResimulation
bEnableResimulationError*Threshold (Position, Rotation, AngularVelocity, LinearVelocity)
BlamAlertFatalSimulationError
BlamEngineTelemetry
```

### Material Assets
```
/BlamEngine/Materials/M_BlamDebug.M_BlamDebug
```

### KEY INSIGHT: Module Architecture
The game has THREE main script modules:
1. **`/Script/BlamEngine`** — The Blam engine UE5 plugin (bridges UE5 ↔ HaloSimulation DLL)
2. **`/Script/Meteorite`** — The game-specific module (campaign logic, UI, etc.)
3. **`/Script/MeteoriteOnlineServices`** — Online services (likely PlayFab/Party integration)

The `BlamGameEngineVariant` header file confirms: **game engine variants (Slayer, CTF, etc.) are a first-class concept in the UE5 plugin layer**, not just in the simulation DLL.

---

## 🔥 BIGGEST FINDING: Complete Halo Multiplayer Engine

### HaloSimulation_tag_release.dll

**Single export**: `CreateBlamEngineShell` — factory function that creates the entire Halo "Blam" engine simulation shell.

**Imports**: KERNEL32, USER32, WS2_32 (Winsock networking!), DINPUT8, xinput1_4, ADVAPI32, bcrypt, dbghelp, ole32, WINMM, MSVCP140, VCRUNTIME140

**Contains ALL classic Halo multiplayer game modes** (verified via string extraction):

#### Game Modes Found
- **Slayer** — top level options, primary options, advanced options, scoring options, leader traits (appearance/movement/sensors/shields/weapons)
- **CTF** — top level, primary, advanced options, carrier traits (full set)
- **Oddball** — top level, primary, advanced, carrier traits
- **King of the Hill** — top level, primary, advanced, hill traits
- **Infection** — top level, primary, scoring, advanced options
- **Juggernaut** — top level, primary, advanced, juggernaut traits
- **Assault** — top level, primary, advanced, assault bomb
- **Territories** — top level, primary, advanced

#### Engine Systems Found
```
game_engine_respawn_options_block / flags
game_engine_team_options_block / team_block / team_flags
game_engine_team_options_designator_switch_type
game_engine_team_options_model_override_type
game_engine_team_options_player_model_choice
game_engine_player_traits_block / list_block
game_engine_loadout_options_block
game_engine_loadout_palette_entry_block
game_engine_map_override_options_block / flags
game_engine_miscellaneous_options_block / flags
game_engine_social_options_block / flags
game_engine_sandbox_variant_block
game_engine_survival_variant_block / flags / additional_flags
game_engine_survival_round_properties_block
game_engine_survival_wave_properties_struct
game_engine_survival_bonus_wave_properties_struct
game_engine_survival_custom_skull_block
game_engine_campaign_variant_block
game_engine_ai_traits_struct / list_block
game_engine_settings / settings_definition / flags
game_engine_event_block (audience, input, response_context, flags)
game_engine_simulation_dependency_flags
game_engine_status_response_block
game_engine_request_boot_player
game_engine_globals / globals_block
```

#### Megalo Scripting Engine
```
megalo_chud_message
<megalo omni widget> (augmentation icon, available, label, meter, value string)
chud_megalo_datasource_omni_widget_label / value
chud_megalo_progress_bar_label
CS:Megalo Globals
```

#### Respawn System
```
game_engine_respawn_options_block / flags
debug_player_respawn
debug_respawn_point_objects
debug_spawning_respawn_zones
debug_initial_spawn_point_objects
coop respawn effect / sound
fireteam 1-4 respawn zone
spartan_respawn_* (30+ traits)
elite_respawn_* (same full trait set)
disable spartan/elite respawn on backfield/player
```

#### Loadout System
```
spartan_loadouts_tier[1-3]_loadout[0-4]: enabled, name, primary, secondary, equipment, grenades
elite_loadouts_tier[1-3]_loadout[0-4]: same structure
```

#### Forge System
```
forge_object_properties (physics, shape, team, symmetry, spawn_at_start, spawn_time, etc.)
forge_object_edit_coords (x, y, z, pitch, yaw, roll)
default_map_variant_save_description_format / name_format
debug_multiplayer_object_properties
```

---

### PlayFabMultiplayerWin.dll — Full Matchmaking API

```
/Lobby/CreateLobby, /Lobby/JoinLobby, /Lobby/JoinLobbyAsServer
/Lobby/JoinArrangedLobby, /Lobby/FindLobbies, /Lobby/FindFriendLobbies
/Lobby/InviteToLobby, /Lobby/UpdateLobby, /Lobby/LeaveLobby
/Lobby/RemoveMember, /Lobby/DeleteLobby, /Lobby/GetLobby
/Match/CreateMatchmakingTicket, /Match/CancelMatchmakingTicket
/Match/CancelAllMatchmakingTicketsForPlayer, /Match/CancelServerBackfillTicket

Classes: LobbyImpl, LobbyManager, MatchmakingManager, MatchmakingTicketImpl
State changes: PFLobbyStateChange, PFMatchmakingStateChange
API domain: .playfabapi.com
```

### PartyWin.dll — P2P Networking + Voice Chat

```
BumblelionNetwork, Endpoint/EndpointModel, ChatControl/ChatManager
QoS: ListPartyQosServersRequest/Response
Party: RequestPartyRequest/Response
Voice: IXAudio2VoiceCallback, SourceVoice
Transport: WebSocket (MessageWebSocket)
```

---

## 🖥️ UE4SS Log Analysis (key findings from 3502 lines)

### Blueprint Classes at Frontend
- **BP_FrontendPlayerController**: `PushPlayerTraitsToServer`, `ServerSetDesiredPlayerTraits`, `ClientRequestForPlayerTraitsFromServer`
- **BP_FrontendGameMode**: `OnXsapiStart` (Xbox Services API)
- **BP_FrontendGameState**: `ResetClientLobbyData`, `StartCountdown`, `CancelCountdown`
- **BP_FrontendHUD**: `IsSplitscreenPlayer`, `InitializeSplitscreenLayoutAndInput`, `FireteamWidgetAddref/Removeref`, `OpenWidgetByName/CloseWidgetByName`
- **SpectatorPawn** was also found loaded

### UE4SS Config (what's enabled)
- Engine version: 5.5
- HookManagerEnabled = 0 (custom hooks disabled in config)
- All major hooks enabled (ProcessInternal, LoadMap, BeginPlay, EndPlay, EngineTick, etc.)
- BPModLoaderMod enabled, LogicMods dir is empty and ready

---

## 📁 Game File Structure

```
Meteorite/Binaries/Win64/
├── HaloCampaignEvolved.exe (230 MB)
├── HaloSimulation_tag_release.dll (14.6 MB) ← BLAM ENGINE
├── PlayFabMultiplayerWin.dll (1.8 MB)        ← MATCHMAKING
├── PartyWin.dll (4.0 MB)                     ← P2P + VOICE
├── libHttpClient.Win32.dll (258 KB)           ← HTTP
├── dwmapi.dll (71 KB)                         ← UE4SS PROXY
├── boost_*.dll, tbb*.dll, amd_*, OpenColorIO  ← Dependencies
├── D3D12/, DML/                               ← DirectX 12
└── ue4ss/                                     ← UE4SS
    ├── Mods/ (MJOLNIRFlyCam, DumpCommandsMod, CheatManager, Console, BPModLoader, Keybinds)
    └── UE4SS_Signatures/

Meteorite/Content/Paks/
├── LogicMods/ (EMPTY — ready for BP mods!)
├── pakchunk0 (40+ GB main content)
├── pakchunk1-10 (~330 MB each, likely campaign levels)
└── pakchunk115-530 (additional content chunks)
```

---

## 🔧 Commands Run (for reproduction)

### String Extraction from HaloSimulation DLL
```powershell
$bytes = [IO.File]::ReadAllBytes("...\HaloSimulation_tag_release.dll")
$text = [System.Text.Encoding]::ASCII.GetString($bytes)
$matches = [regex]::Matches($text, '[\x20-\x7E]{8,}')
$strings = $matches | ForEach-Object { $_.Value }

# Game modes
$strings | Where-Object { $_ -match '^(slayer|ctf|oddball|king|assault|infection|territories|juggernaut)' } | Sort-Object -Unique

# Engine systems
$strings | Where-Object { $_ -match '^game_engine_' } | Sort-Object -Unique

# Teams/respawn/damage/kill
$strings | Where-Object { $_ -match 'team|respawn|slayer|ctf|game_engine|game_variant|round|score|multiplayer|kill|death|damage' } | Sort-Object -Unique | Select-Object -First 100
```

### String Extraction from Main EXE
```powershell
$bytes = [IO.File]::ReadAllBytes("...\HaloCampaignEvolved.exe")
$text = [System.Text.Encoding]::ASCII.GetString($bytes)
$matches = [regex]::Matches($text, '[\x20-\x7E]{8,}')
$strings = $matches | ForEach-Object { $_.Value }
$strings | Where-Object { $_ -match 'BlamEngine|HaloSimulation|Simulation|GameVariant|MapVariant|game_engine|Meteorite' } | Sort-Object -Unique
```

### PE Export Analysis
```powershell
# Result: Single export "CreateBlamEngineShell"
# Imports: KERNEL32, WS2_32, DINPUT8, xinput1_4, etc.
```

---

## 🎯 WHAT TO DO NEXT (Priority Order)

### 1. 🔴 Deep EXE String Search (HIGH PRIORITY)
Run more targeted string searches on the main EXE:
```powershell
# Search for BlamEngine UE5 class names
$strings | Where-Object { $_ -match 'Blam[A-Z]' } | Sort-Object -Unique

# Search for /Script/ module paths
$strings | Where-Object { $_ -match '^/Script/' } | Sort-Object -Unique

# Search for /Game/ asset paths (maps, blueprints)
$strings | Where-Object { $_ -match '^/Game/' } | Sort-Object -Unique

# Search for game variant related
$strings | Where-Object { $_ -match 'Variant|GameMode|GameType' } | Sort-Object -Unique

# Search for multiplayer/online
$strings | Where-Object { $_ -match 'Multiplayer|OnlineService|Matchmak|Lobby|PlayFab' } | Sort-Object -Unique
```

### 2. 🔴 Ghidra Analysis of HaloSimulation DLL (HIGH PRIORITY)
Use `C:\tools\ghidra_12.1.2_PUBLIC` to:
- Analyze `CreateBlamEngineShell` — what vtable/interface does it return?
- Find multiplayer game engine initialization paths
- Check if `game_engine_slayer` etc. are function tables or just data
- Trace the respawn system entry points

### 3. 🔴 UE4SS Discovery: Find BlamEngine Classes (HIGH PRIORITY)
Create a Lua mod that:
```lua
-- Find ALL /Script/BlamEngine objects
local objects = FindAllOf("Object")
-- Search for: BlamGameEngineVariant, BlamEngineGlueOuterSubsystem
-- Search for: anything in /Script/Meteorite, /Script/MeteoriteOnlineServices
-- Try: StaticFindObject("/Script/BlamEngine.Default__BlamGameEngineVariant")
```

### 4. 🟡 Console Commands to Try In-Game
```
stat BlamEngine
stat Simulation
BlamEngine.DisableBlamEngine 0
BlamEngine.ResetSimulation
BlamEngine.AdvanceSimulation
```

### 5. 🟡 Extract Pak File Contents
Need UnrealPak or Python pak reader to list asset paths

### 6. 🟢 Enable SplitScreenMod
Test if Ctrl+Y spawns a second player with independent control

---

## 💡 Architecture Theory (UPDATED with EXE findings)

```
HaloCampaignEvolved.exe (UE5)
├── /Script/Meteorite                    ← Game module (campaign, UI)
├── /Script/BlamEngine                   ← UE5↔Blam bridge plugin
│   ├── FBlamEngineLauncher              ← Loads simulation DLL
│   │   └── RegisterShellOutputHandlerCallbacks()
│   ├── BlamGameEngineVariant            ← GAME MODE VARIANT CONFIG
│   ├── BlamEngineGlueOuterSubsystem     ← Glue layer
│   ├── BlamSynchronization              ← UE5↔Blam state sync
│   │   ├── BlamVehicleFighterComponent
│   │   ├── BlamVehicleWithEngineComponent
│   │   ├── BlamAnimNotify
│   │   └── SBlamDebugMenu*
│   └── M_BlamDebug (debug material)
├── /Script/MeteoriteOnlineServices      ← PlayFab/Party wrapper
└── /Script/DataflowSimulation           ← Physics

HaloSimulation_tag_release.dll (Blam Engine)
├── CreateBlamEngineShell()              ← Single export entry point
├── Game Modes: Slayer, CTF, Oddball, KOTH, Infection, Juggernaut, Assault, Territories
├── Megalo scripting engine
├── Forge/Sandbox system
├── Respawn system
├── Team system
├── Loadout system (Spartan/Elite, 3 tiers, 5 loadouts each)
└── WS2_32 networking (own net layer)
```

> **Superseded 2026-07-26:** `BlamGameEngineVariant` is present as a source/header identifier, but it
> is not an exposed runtime class in this build. UE4SS and binary-name scans instead expose
> `BlamGameEngineBaseVariant` and `BlamGameEngineCampaignVariant`.

---

## 2026-07-26 Follow-Up: CU2 Static Analysis

This section records checks performed after the original session. It supersedes the placeholder map
and travel assumptions above where they conflict.

### Build Lock

| Artifact | Verified value |
|---|---|
| Host version | `2026.06.26.1097863.1-Rel-i343-Meteorite-2606-CU2` |
| Host SHA-256 | `0670FAA751E2553940B90DF6BE43D3B0FF59EA87F22155CF3C3FE9D439367F1D` |
| Simulation SHA-256 | `8EE1A37F6F0BC89241F47946546EDCA798962F81E2D06B386196BC75DE991705` |

### Packed Map Inventory

**Verified:** all 28 IoStore indexes and all 27 companion pak indexes were listed without extracting
game content.

- IoStore format: UE5.5 `ReplaceIoChunkHashWithIoHash`, indexed, Oodle-compressed, not encrypted.
- `132,091` unique IoStore paths.
- `14,240` `.umap` chunks, mostly World Partition generated cells.
- `77` named `.umap` paths after excluding generated/external-actor maps.
- `13` root Halo world packages, all under `Levels/Halo1/Solo`.
- No `Levels/Halo1/Multi` branch and no named multiplayer world package.
- No Blood Gulch, Beaver Creek, Sidewinder, or other classic Halo CE multiplayer map name.
- Eleven apparent CTF/KOTH `.umap` hits were random generated cell IDs containing those letters.
- The pak indexes contain `200,029` entries, predominantly Wwise audio/resources, and no Unreal map
  or asset package entries.

The currently indexed root world paths include:

```text
/Game/Levels/Halo1/Solo/A15/A15
/Game/Levels/Halo1/Solo/A30/A30
/Game/Levels/Halo1/Solo/A50/A50
/Game/Levels/Halo1/Solo/B30/B30
/Game/Levels/Halo1/Solo/B40/B40
/Game/Levels/Halo1/Solo/C10/C10
/Game/Levels/Halo1/Solo/C20/C20
/Game/Levels/Halo1/Solo/C45/C45
/Game/Levels/Halo1/Solo/D20/D20
/Game/Levels/Halo1/Solo/D40/D40
/Game/Levels/Halo1/Solo/Extra/E10/E10
/Game/Levels/Halo1/Solo/Extra/E20/E20
/Game/Levels/Halo1/Solo/Extra/E30/E30
```

**Conclusion:** no hidden competitive map package was found in this build. This does not rule out
dormant competitive gameplay code or assets.

### Retained Multiplayer Content

**Verified:** the path index contains `713` files under explicit multiplayer directories and `616`
paths under `Tags/multiplayer/game_variant_settings`.

Examples include multiplayer globals, object type lists, team names, messages, respawn sounds, map
overrides, social options, custom Spartan/Elite loadouts, Megalo, Sandbox, the Oddball weapon, and
assault-bomb content. These are stronger evidence than raw strings, but they still do not prove that
the shipping UI or UE5 bridge exposes a competitive launch path.

> **Refined 2026-07-26:** those counts mixed `.uasset` headers with their `.ubulk` payloads. Counting
> tags rather than index entries, the build ships `319` multiplayer tags, of which `308` are under
> `Tags/multiplayer/game_variant_settings`. The content is real Blam tag data, not strings. See
> [`tag_data_pipeline.md`](tag_data_pipeline.md).

### CreateBlamEngineShell Result

**Verified by Ghidra decompilation:** the export behaves as:

```cpp
bool CreateBlamEngineShell(void* context, void** outShell);
```

It allocates a `0x5A0`-byte, `0x20`-aligned shell object, installs two nine-entry interface tables,
initializes lock-free event queues, replaces the process-global shell, writes `outShell`, and returns
`1`. The second interface is embedded at `this + 0x140` and implements queued shell-output dispatch.

The matching UE5 executable constructs the basename `HaloSimulation`, loads the module into launcher
offset `0x1A0`, resolves `CreateBlamEngineShell`, writes the result to launcher offset `0x1C8`, and
immediately invokes shell interface slot 1.

See [`halosimulation_tag_release.md`](halosimulation_tag_release.md) for the dedicated analysis.

### Live UE4SS Discovery

**Verified at runtime:** `MJOLNIRDiscovery` loaded and registered its commands on the CU2 build. A
frontend scan at `2026-07-26T08:08:33Z` produced 300 unique matching entries:

- 279 reflected `/Script/BlamEngine` functions.
- 20 reflected `/Script/MeteoriteOnlineServices` functions.
- One live `BlamEngineGlueOuterSubsystemImpl` under the transient `GameEngine` object.

The generic paths `/Script/BlamEngine.BlamGameEngineVariant` and
`Default__BlamGameEngineVariant` were not found. The reflected variant surface is:

```text
BlamGameEngineBaseVariant:GetSocialOptions
BlamGameEngineBaseVariant:SetSocialOptions
BlamGameEngineCampaignVariant:GetFlags
BlamGameEngineCampaignVariant:SetFlags
BlamGameEngineCampaignVariant:GetPerPlayerTraits
BlamGameEngineCampaignVariant:SetPerPlayerTraits
```

**Verified reflected multiplayer helpers:**

```text
BlamSynchronizationHelperLibrary:ActorTeamIsAlly
BlamSynchronizationHelperLibrary:ActorTeamIsEnemy
BlamSynchronizationHelperLibrary:ActorTeamIsFriendly
BlamSynchronizationHelperLibrary:ActorTeamIsTraitor
BlamSynchronizationHelperLibrary:FindPlayerStateUsingBlamAbsolutePlayerIndex
BlamSynchronizationHelperLibrary:ResolvePlayerStateUsingBlamAbsolutePlayerIndex
BlamSynchronizationHelperLibrary:ResolvePlayerStateUsingBlamInputUserIndex
BlamEngineAudioGameSubsystem:IsNetworkCoop
```

The broader reflected function dump also exposes `/Script/BlamNetworkSession`, including
`BlamOnlineSessionSubsystem:IsReadyToPlay`, replicated session-running state, endpoint IDs, and
primary-player IDs. Standard create/find/join session proxies and PlayFab create/join/leave lobby
functions are reflected as well.

The first world scan reported zero because its case-sensitive UI path filter used `levels` while the
live package path uses `Levels`. This is a scanner defect, not evidence that no frontend world was
loaded; the filter now normalizes case and records every live `World` object.

**Second runtime pass (A30 loaded):**

- `725` matching reflected functions and targeted objects were recorded.
- Static lookup verified the classes and CDOs for `BlamGameEngineBaseVariant`,
  `BlamGameEngineCampaignVariant`, and `BlamOnlineSessionSubsystem`.
- Four live `BlamGameEngineCampaignVariant` objects existed. One was owned by
  `MeteoriteGameInstance.BlamCampaignFlowGameSubsystem`; three were transient copies.
- The world scan found `91` worlds: `/Game/Levels/Halo1/Solo/A30/A30` plus 90 generated World
  Partition cell worlds.
- All 14 initial session/lobby/travel hooks registered at runtime, but zero hook callbacks fired before
  the A30 state snapshot. **Observed:** those reflected wrappers were not invoked during the traced
  interval. **Unverified:** tracing may have started after an earlier session transition, or the
  official flow may use native paths beneath these wrappers.

The next probe adds pre/post hooks for Blam endpoint assignment and campaign-flow transitions and a
reflected state snapshot for the active variants and network components.

**Third runtime pass: controlled frontend-to-A30 solo baseline**

The tester confirmed that no second human player was connected. This pass must not be cited as a
co-op capture.

At the frontend (`2026-07-26T08:32:56Z`):

- No live `BlamGameEngineBaseVariant` or `BlamGameEngineCampaignVariant` instances.
- `BlamNetworkGameStateComponent.bSessionRunning = false`.
- One frontend `BlamNetworkPlayerStateComponent` with endpoint generation `0` and both endpoint IDs
  equal to `0`.
- `MeteoriteSquadLobbyViewModel.TotalPlayerCount = 1` and `bCrossPlayEnabled = false`.

At `01:33:45`, the only captured lifecycle callback fired:

```text
BlamCampaignFlowGameSubsystem:SetActiveCampaign
```

After A30 loaded (`2026-07-26T08:33:58Z`):

- `CurrentCampaign` resolved to
  `/Game/Blueprints/Campaign/DA_FirstPlayableCampaign.DA_FirstPlayableCampaign`.
- Four `BlamGameEngineCampaignVariant` instances appeared; the campaign-flow subsystem owned one.
- The root world was `/Game/Levels/Halo1/Solo/A30/A30`, accompanied by 85 generated World Partition
  cell worlds in this run.
- The mission GameState component still reported `bSessionRunning = false`.
- Two PlayerState network components existed. This is object/component count, **not evidence of two
  connected players**.
- Both components had endpoint generation `1`, but in-channel and out-of-band endpoint IDs remained
  `0`.
- Lobby player count remained `1`; `bCrossPlayEnabled` changed to `true`.

**Verified interpretation:** endpoint generation advancing from `0` to `1` occurs during ordinary
solo campaign activation and does not prove a peer endpoint exists. Likewise, cross-play enablement
is configuration state, not proof of a remote player. A real co-op baseline requires another human
present and should show which of readiness, session-running, endpoint IDs, squad count, or player
components diverge from this solo capture.

**Current boundary:** a second human tester is not presently available. Competitive-mode activation,
session preservation across custom travel, and the solo-versus-co-op state differential remain
`Unverified`; do not infer them from the solo baseline. Static analysis and single-process runtime
work can continue independently.

### Native Reflection Follow-Up

`AnalyzeMultiplayerRuntime.java` was run against the matching CU2 host executable. It recovered 112
identifier/reference records and 15 owning functions.

**Verified:**

- `BlamNetworkPlayerStateComponent` is registered as a `0xF8`-byte reflected class.
- In-channel endpoint ID, out-of-band endpoint ID, and endpoint generation are separately registered
  reflected properties.
- `bSessionRunning` has concrete reflected registration paths on the network GameState component.
- `ServerSetBlamEndpointIds` and `ServerSetPrimaryPlayerId` have distinct native name/registration
  initializers.

**Observed limitation:** direct name xrefs primarily reach Unreal reflection registration code, not
the underlying method implementations. `IsReadyToPlay`, `IsNetworkCoop`, `SetActiveCampaign`, and
`CampaignVariantStorage` names did not expose direct implementation xrefs. The deployed runtime probe
therefore calls readiness, network-coop, squad-count, and campaign-variant getters directly on the
live objects and attempts to enumerate the variant storage struct.

### Correction: MJOLNIRMultiplayer Is an Experiment

The Lua mod does not create or advertise a session. The placeholder URLs and `PenguinHotel` fallback
were replaced on 2026-07-26 with verified CU2 world paths and player-controller console dispatch.
`mjolnir_travel <map>` and `mjolnir_listen <map>` remain unverified until exercised in HCE.

> **Exercised 2026-07-27.** `mjolnir_travel` dispatched from the **frontend menu** crashes the
> game: `EXCEPTION_ACCESS_VIOLATION` reading `0x1c`, a couple of minutes into the load. `open`
> skips the setup the campaign flow performs, which is what step 3 below anticipated. Start
> missions through the menus; travel between levels once already in game is untested.
> See [`game_automation.md`](game_automation.md).

Runtime discovery commands added in the same pass:

```text
mjolnir_scan_blam
mjolnir_scan_worlds
mjolnir_trace_network
mjolnir_dump_state
```

### Revised Experiment Order

1. Run `mjolnir_trace_network` before creating or joining an official campaign co-op session.
2. Run `mjolnir_dump_state` in the frontend and again after the mission loads; compare the active
  campaign variant and Blam network component properties.
3. Reuse the official campaign co-op flow, then test travel to a verified campaign package.
4. Trace shell primary slots 2 and 3 to identify the startup/game-variant structure.
5. Activate a competitive variant before attempting custom-map cooking.
6. Add team spawns, flag stands, boundaries, and objectives to an existing campaign world at runtime.
7. Only then cook a tiny UE5.5 test world and package it as pak/utoc/ucas.

## 2026-08-02 Follow-Up: CU3 — the game ships a working debug map-select menu

**Game build:** `2026.07.25.1112544.4-Rel-i343-Meteorite-2607-CU3` (read off the live Test
options panel). Host SHA-256
`4D20DC56611B29CD710D591C86CF5DE55B914EB986838C42E719B82CCD367753`, written to disk 2026-07-31.
All findings below were made against CU3, both the on-disk IoStore index and the live process.

### UE4SS injection broke on the CU3 update — and the AOB was not the problem

**Observed:** after the update, UE4SS died with `Fatal Error: AOB scans could not be completed`
for `FName_Constructor.lua`, while the other three signatures resolved. The installed pattern
was found **exactly once** in the CU3 exe on disk (file offset `0x36FC730`, `.text`), and a
`ReadProcessMemory` probe at the matching RVA (`0x36FD130`) returned the identical bytes in the
live process. The bytes were right; the scanner missed them.

**Recovery sequence (Observed, not fully bisected):** setting `SigScannerNumThreads = 1` alone
did not fix it; deleting `ue4ss/cache` and relaunching with 1 thread did. The scan cache is a
known trap — `InvalidateCacheIfDLLDiffers` watches UE4SS's own DLL, not the game exe — so
**always clear `ue4ss/cache` after a game update** before diagnosing signatures. Whether the
thread count mattered is unproven; both changes are currently in place and injection is
verified working on CU3. See `signatures/README.md` for the triage procedure.

Also observed: `GUObjectHashTables.lua` resolved to different addresses on different launches
with the same image base, so its wildcarded pattern matches more than one site. It works, but
the ambiguity is worth tightening.

### UI widget inventory: the co-op layer ships, the competitive layer does not

**Verified** from the complete CU3 IoStore directory index (132,093 entries, all 28 containers)
by enumerating every `WBP_*` widget blueprint (~240 unique):

Ships: `WBP_ClientLobby` (host, mission, difficulty, skulls, crossplay, squad list),
`WBP_MatchStartCountdown` ("Game is starting" / "Cancel Countdown"), the Squad suite
(`WBP_SquadWidget`, voice, splitscreen entries), the Roster suite (add friends, invite,
report player, profile), `WBP_Meteorite_Chat`, `WBP_MeteoriteSessionInProgress`,
`WBP_LoadingWaitStatus` with per-player entries, `WBP_MeteoriteSplitscreenSignIn`, and the
input action `IA_BlamShowScoreboard`.

Absent: any matchmaking browser, playlist or game-variant picker, Slayer/CTF mode-select
widget, scoreboard widget, or postgame screen. The eight competitive modes exist only in the
simulation DLL and the 308 `game_variant_settings` tags. **There is no hidden competitive menu
to unhide in this build.**

### The debug menu chain — verified live, in a Shipping build

**Verified at runtime on CU3**, driven entirely by UE4SS reflection with no keyboard input:

1. `WBP_MainMenu` carries a hidden `DebugButtonContainer` with a `DebugMenuButton`, plus
   handlers `OnToggleDebugMenu` and `DebugRefreshMenu`. Calling `OnToggleDebugMenu()` on the
   live instance flips the container visible and reveals a **"Test options"** panel showing the
   build string, **DEBUG LEVEL SELECT**, and **MISSIONS - UNLOCK**.
2. Invoking the debug button's click delegate opens `WBP_DebugMenuSelect` — an on-screen
   **MAP SELECT** page with **CAMPAIGN MISSIONS** and **TEST MAPS**.
3. The TEST MAPS page (`WBP_TestMapDebugMenu`) lists 20 items from `DA_TestMapsCampaign`;
   the CAMPAIGN MISSIONS page (`WBP_CampaignDebugMenu`) lists Launch A15–E30 from
   `DA_FirstPlayableCampaign` and `DA_AdditionalCampaign` (E10/E20/E30).
4. Item clicks call `BlamCampaignFlowGameSubsystem:SetAndBeginCampaign`.

### SetAndBeginCampaign — the crash-free replacement for `open`

**Verified** reflected signature:

```text
BlamCampaignFlowGameSubsystem:SetAndBeginCampaign(
    Campaign              BlamCampaignDataAsset,
    StartingScenarioName  Name,
    Options               BlamScenarioGameOptions) -> bool

BlamScenarioGameOptions: bLoadFromCoreSave, SaveSlot, SavedFilmName,
    CampaignDifficultyLevel, InsertionPoint, ActiveSkulls, bFriendlyFireEnabled,
    bIsLASO, GameVariant (ObjectProperty)
```

**Verified behaviors:**

- `("testing_shooting_range", DA_TestMapsCampaign)` → returns `false` in under 1 ms,
  synchronously, game stays at the frontend. **Missing worlds fail gracefully** — no crash,
  unlike frontend `open` travel.
- `("A15", DA_FirstPlayableCampaign)` from the frontend debug menu → `true`, full mission
  load, live `BP_MeteoritePawn_C`.
- Direct Lua call from **inside A15** with a Lua-table Options struct reusing a live
  `BlamGameEngineCampaignVariant` → `true`, traveled to A30, pawn possessed at a live world
  position. **Mission-to-mission travel through the campaign flow works from reflection.**
  This closes the gap flagged in `game_automation.md` — mission start no longer needs
  `game_input`.
- Direct call from the **frontend** with `GameVariant = nil` (no live variant exists there)
  → `true`, A15 loaded to a possessed pawn. The flow spawns its own default variant.
  Verified end to end through the new `mjolnir_mission` console command after a cold launch.

`Options.GameVariant` being a plain object property is the significant seam: the campaign flow
accepts a variant *object*. Whether it accepts a non-campaign variant subclass is the next
question that matters for competitive-mode activation.

### Test worlds were stripped from the cook — which is the opportunity

**Verified:** `DT_Test_Scenarios` maps all 20 scenario names to worlds under
`/Game/Levels/Test/...` (plus `/Game/Levels/Lookdev/E10_Kit/D40_Warthog_Testkit`), but none of
those `.umap` packages ship — only stray dependencies survive (materials for `Testing_Arena`,
`Testing_Shooting_Range`, `Testing_Combat_Simple`, `Testing_GravLifts`, `Testing_Ally_AI`, and
the lone `Levels/Test/SeamlessTravelTEst.umap`; also `C20/Archived/C20_GreyboxNoArt.umap`).

The launch plumbing for those worlds ships and validates asset existence before traveling.
Therefore: **mount a custom cooked world at one of the pre-registered paths** (e.g.
`/Game/Levels/Test/Testing_Shooting_Range/testing_shooting_range`) in an IoStore mod container
and the shipped debug menu should launch it through the legitimate campaign flow. Open
question from the tag pipeline: the 13 shipped scenarios all have generated Blam scenario/BSP
tags, and the test scenarios have none — the `false` return today is consistent with a
world-existence check, but a mounted world may still need scenario tags to survive simulation
start. That is the discriminating experiment.

### 2026-08-02, later: the first custom world — what the gate actually is

**Verified.** A UE 5.5.0 world was built, cooked, and installed as
`pakchunk990-MJOLNIRWORLD-Windows_P` (see [`unreal/MJOLNIRMapKit`](../unreal/MJOLNIRMapKit/README.md)),
targeting the pre-registered `testing_shooting_range` slot. Results, in order:

1. **The container mounts.** With the game running, its `.ucas` could not be renamed
   (*used by another process*) while the `.utoc` moved freely — the read-index-once /
   hold-data-open signature of an IoStore mount, the same test used for tag overrides.
2. **The cooked package is structurally sound.** Our own zen parser reads the header:
   correct package name, `package_flags = 0x80022200` (identical to the shipped
   `SeamlessTravelTEst.umap`), 42 imports, 5 exports.
3. **Every import resolves against the game's own script-object table.** All 40 distinct
   script imports our world needs are present in the game's `global.utoc` with **identical
   64-bit hashes**. A stock UE 5.5.0 cook is therefore *not* incompatible with 343's
   modified engine at the class-reference level — the earlier worry is disproven for a
   world this simple.
4. **`mjolnir_mission testing_shooting_range` still returned `false`**, synchronously, exactly
   as it did before the world existed.

**The discriminating evidence:** the build ships **exactly 13 `*-scenario` tags** — one per
launchable campaign mission (`a15`, `a30`, `a50`, `B30`, `B40`, `c10`, `c20`, `C45`, `d20`,
`d40`, `E10`, `E20`, `e30`), each under `Tags/Levels/Halo1/Solo/<M>/_Generated_/` — and **zero
for any `testing_*` scenario**. The campaign flow's scenario-name argument is resolved against
the **Blam scenario tag**, not against the Unreal world package. Supplying the world changes
nothing because the world was never what was missing.

**Superseded:** the earlier reading that `false` was "a world-existence check" was wrong. It is
a scenario-tag lookup. The `DT_Test_Scenarios` world paths are real but unreachable without a
matching scenario tag.

**Consequence for custom maps.** Two routes, and the cheap one is now testable:

- **Override a shipped scenario's world.** Cook the custom world at, e.g.,
  `/Game/Levels/Halo1/Solo/A15/A15` and launch `mjolnir_mission A15`. The `a15` scenario tag
  exists and is untouched; only the Unreal world is replaced. This isolates "can the game render
  and play a custom UE world" from "can we author Blam scenario data", which is the question
  worth answering first.
- **Generate a scenario tag** for a new name — the real prize, and much larger: the `_Generated_`
  sets pair each scenario with BSP, seam, lighting and soft-ceiling tags
  ([`tag_data_pipeline.md`](tag_data_pipeline.md)).

**Also observed:** calling `LoadAsset` on a world package from UE4SS Lua crashed the game
(`EXCEPTION_ACCESS_VIOLATION` reading `0x10`, all frames inside UE4SS). Loading a world outside
the engine's travel path is not a safe probe; use `SetAndBeginCampaign` and read the result.

**Unverified, noted for later:** the shipped `SeamlessTravelTEst.umap` uses
`/Script/BlamEngine/BlamWorldSettings` where a stock cook emits `/Script/Engine/WorldSettings`.
Whether the Blam subclass is *required* for a world to run is untested — if the A15 override
loads geometry but the simulation never starts, this is the first thing to suspect.

### 2026-08-02, third pass: a custom world loads and the mission runs on it

**Verified — this is the breakthrough.** A world cooked in stock UE 5.5, installed as an
override of A15's world package, **loaded, and A15's mission logic ran on top of it**: HUD
reticle, and the opening objective text ("Begin Calibration? Press E to Proceed").

Proof it was our world and not the shipped one, read by reflection while in game:

| Check | Our world | Shipped A15 |
|---|---|---|
| WorldSettings class | `WorldSettings` (stock) | `BlamWorldSettings` |
| `StaticMeshActor` count | `0` | thousands |
| `BlamWorldSettings` instances | `0` | 1 |

A pawn spawned (`BP_MeteoritePawn_C`), the player controller possessed it, and the campaign
flow behaved normally. **Cooked custom worlds are viable in this game.** The stock-5.5-versus-
343-fork worry is disproven at the package, import and world level.

The screen is black because the world is *empty on purpose* — this run used
`MJOLNIR_EMPTY_WORLD=1`, which saves the bare level (World, Level, Model, WorldSettings) with
no actors. Black is the correct result for a world with no geometry and no lights.

#### The actual wall: cooked actor components

Building the same world *with* content fails during load, fatally, in `AsyncLoading2`:

```text
ObjectSerializationError: /Game/Levels/Halo1/Solo/A15/A15
  CapsuleComponent ...PlayerStart_0.CollisionCapsule:
  Serial size mismatch: Expected read size 34, Actual read size 14

ObjectSerializationError: /Game/Levels/Halo1/Solo/A15/A15
  DirectionalLightComponent ...DirectionalLight_0.LightComponent0:
  Serial size mismatch: Expected read size 67, Actual read size 21
```

Two different component classes, same failure shape, expected consistently larger than actual:
**343's engine build serializes these component classes differently from stock UE 5.5**. The
world, level and model exports are fine; it is component payloads that are binary-incompatible.

**Verified workaround: spawn content at runtime instead of cooking it.** In the loaded custom
world, `LoadAsset("/Engine/BasicShapes/Cube.Cube")` succeeded, `World:SpawnActor` produced a
live `StaticMeshActor`, `SetStaticMesh` and `SetActorScale3D` applied, and a runtime-spawned
`DirectionalLight` configured cleanly. Runtime spawning goes through the game's own class
layouts, so it sidesteps the serialization wall entirely.

**The emerging recipe for a custom map:** ship an *empty* cooked world at a scenario slot whose
Blam scenario tag exists, then build the map at runtime from a UE4SS mod. That splits cleanly
along the boundary the evidence draws: the engine will load our *world*, but only its own
process may construct our *actors*.

**Unverified:** whether a runtime-spawned mesh actually renders. Screenshots stayed black after
spawning a cube and a light. Candidates: no sky/ambient contribution, the Blam renderer owning
the view, or the spawned actor needing registration the Lua path skipped. This is the next
thing to chase.

**Also verified (and it matters for automation):** `SetAndBeginCampaign` called straight from
the frontend, *before* clearing the title/login screen, loads the mission in a degraded state —
pawn present but HUD hidden and nothing drawn. Pressing through the title screen first and then
launching produces a normal, running mission. Automated runs must clear the title screen first.

#### Debug menu: custom entries

`mods/MJOLNIRMapMenu` reveals the shipped Test options panel automatically at the frontend and
adds custom rows to the TEST MAPS page. **Verified:** a `BP_DebugMapItemData_C` constructed at
runtime with `CampaignData` + `StartingScenarioName` is accepted by the shipped list view
(`AddItem` reported success; the item pool grew from 20 to 21).

Presentation lives on the `HaloUIViewItemData` base, not the Blueprint: `EntryName` (the label),
`EntryWidgetClass` and `EntryWidgetButtonStyle` (without which a row renders as nothing). The
mod now copies those from a shipped item. **Unverified:** the added row has not been *seen* on
screen — keyboard navigation did not reach past the shipped entries, and a reflection probe
calling `GetNumItems` on the list view crashed the game (access violation reading `0x18`), so
that call is not a valid method here. Confirming the row visually is unfinished work.

### 2026-08-03: the world renders, and the player walks on it

**Verified.** An empty world cooked at A15's package path, plus
[`mods/MJOLNIRWorldBuilder`](../mods/MJOLNIRWorldBuilder) spawning the contents at runtime,
produced a custom map that draws and can be walked across: a 100 m grid pad, a sky, and A15's
Blam entities (marines, crates, the training-diagnostic objective) carrying on over the top of
it. `WorldSettings` read back as stock `WorldSettings`, so the loaded world was ours. Walking
`W` for 2.5 s moved the pawn from `(-16972, -1432, 2)` to `(-16716, 381, 2)`.

Four things had to be untangled to get there, and three of them were measurement problems rather
than engine problems.

#### 1. "Runtime-spawned geometry does not render" was never true

The default screenshot path (`PrintWindow`) captures the Slate/UI layer and returns the 3D scene
as black. Confirmed against an *unmodified* A30 mission: HUD perfect, world black; the same
instant via `foreground: true` (`CopyFromScreen`) showed forest, cliffs and weapon. The previous
pass's black screenshots were photographs of a capture bug. Written up in
[`game_automation.md`](game_automation.md).

#### 2. A15's opening prompt is the brightness calibration

"Begin Calibration? Press E to Proceed" is the gamma-adjustment step, and it holds the screen
near-black until dismissed. Automated runs must press `E` through it or every capture looks like
a failed load.

#### 3. `SetStaticMesh` silently refuses on a Static component

`AStaticMeshActor` spawns with `Mobility = Static` (read back as `0`). `SetStaticMesh` on a
registered static component logs "not movable" and returns without doing anything, leaving a
live, valid, empty actor. Setting `comp.Mobility = 2` *before* the call makes it take —
`comp.StaticMesh` then reads back `StaticMesh /Engine/BasicShapes/Cube.Cube`. The earlier pass
reported `SetStaticMesh` as succeeding; it returned without erroring, which is not the same
thing. Read the property back.

Note `GetStaticMesh()` is not callable through UE4SS reflection here (it comes back as a
`TrivialObject`); the `StaticMesh` property is.

#### 4. Cooked components fail for one reason, not three

Adding a `StaticMeshActor` to the cook produced a third distinct death:

```text
StaticMeshComponent /Game/Levels/Halo1/Solo/A15/A15.A15:PersistentLevel.StaticMeshActor_0
  .StaticMeshComponent0: Bad export index 201463809/7
```

Together with the two "Serial size mismatch" failures, that is three symptoms of **unversioned
property serialization**: UE5 cooks properties as a bitmask plus values in class-layout order,
with no names on the wire. Where 343's class layout differs from stock 5.5, the reader
miscounts — sometimes landing on a wrong byte count, sometimes on a garbage object index. The
world, level and model exports are never implicated because those are not property-serialized
the same way.

**Open lead: cook tagged properties instead.** `[Core.System]
CanUseUnversionedPropertySerialization=False` makes the cooker emit names and types per property,
which the game's loader could match and skip past. It cannot go in `DefaultEngine.ini` — the same
flag gates *reading* unversioned data, and the editor asserts on startup
(`UnversionedPropertySerialization.cpp:936`) because its own caches are full of it. It has to be
a cook-process override, which is now `package.ps1 -TaggedProperties`. **Not yet tested against
the game.** If it works, maps get authored in the editor rather than scripted in Lua.

#### Also learned: the Blam simulation brings its own collision

In the empty custom world the pawn does not fall. It settles at `z = 2` and walks around on
collision with no Unreal geometry behind it — the `a15` scenario tag's BSP collision is still
live even though the Unreal world is ours. A world overriding a campaign scenario inherits that
mission's invisible floor plan. Whether the Blam-driven pawn collides with runtime-spawned
*Unreal* geometry is still unknown: our slab was laid 1.2 m below the surface the pawn was
already standing on, so it was never tested as a floor.

### Revised next steps

1. ~~Cook a minimal UE 5.5 world and launch it.~~ **Done 2026-08-02 — it loads.**
   ~~Remaining thread: make runtime-spawned geometry actually render.~~ **Done 2026-08-03 — it
   renders and is walkable.** See the 2026-08-03 pass above.
1b. Test `package.ps1 -TaggedProperties` against the game. This is now the highest-value
   experiment: it decides whether custom maps are authored or scripted.
2. If the sim rejects it, generate minimal scenario/BSP tags for the world
   ([`tag_data_pipeline.md`](tag_data_pipeline.md)) and retry.
3. Probe `Options.GameVariant`: enumerate what variant classes
   `StaticConstructObject` will produce, try passing a non-campaign variant, and watch
   `BlamGameEngineBaseVariant`/`SetSocialOptions` behavior.
4. Decode the 308 `game_variant_settings` tags to learn what a competitive variant payload
   looks like before trying to activate one.

## 2026-07-26 Follow-Up: Tag Data Pipeline

The game runs on real Blam tag data. `12,328` tag files across `101` classic tag groups ship inside
the IoStore containers, each as an Unreal package whose bulk-data segment is a raw Blam tag file
carrying the `BLAM` signature. Rendering is fully Unreal: zero `render_model` and zero `bitmap` tags
ship, and object definitions bind to Blueprint actors such as `BP_EliteBipedActor`.

This matters for multiplayer work in three ways:

1. `game_engine_settings-game_engine_settings_definition`,
  `globals-multiplayer_object_type_list`, `multiplayer_globals-multiplayer_globals`, and `308`
  `game_variant_settings` tags are dumpable and readable. They should be decoded before further
  runtime probing, because they define what the simulation believes is available.
2. There is still no multiplayer `scenario` tag. All `13` scenarios are generated from the solo
  Unreal worlds under `_Generated_`, alongside their BSP, seam, lighting, and soft-ceiling tags.
3. A competitive map likely requires both an Unreal world and a generated Blam scenario/BSP set.
  Cooking a world alone is probably insufficient.

Full analysis and reproduction: [`tag_data_pipeline.md`](tag_data_pipeline.md).

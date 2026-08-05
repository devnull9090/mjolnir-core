# MJOLNIR Multiplayer Investigation — Session Notes
**Date**: 2026-07-25 ~11:50 PM PST
**Conversation ID**: `f74b07be-cdb9-4b3f-ac8b-b193380aa670`

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

> **Superseded 2026-08-04.** The mode list below is read from the DLL's *tag definition* strings. It
> describes what the definitions can express, not what ships. Reading the actual tags shows no
> per-mode settings tags, no flag object, an empty announcer sound table, and a host executable whose
> `EBlamGameEngineType` enum contains only `Campaign`. See
> [`multiplayer_ctf_plan.md`](multiplayer_ctf_plan.md).

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

# Getting Two Players Into a Match

**Status:** Plan. Research section verified 2026-08-04.
**Goal:** two or more human players in a shared lobby, playing an objective game mode.

### Build Lock

Every finding in Part 1 was read from **CU3**, which the installed game had already updated to when
this was written. The earlier multiplayer notes in this repository are CU2 and are not
interchangeable with it.

| Artifact | Value |
|---|---|
| Build | `2026.07.25.1112544.4-Rel-i343-Meteorite-2607-CU3` |
| Binaries dated | 2026-07-31 |
| Host SHA-256 | `4D20DC56611B29CD710D591C86CF5DE55B914EB986838C42E719B82CCD367753` |
| Simulation SHA-256 | `82B8A3A006BA3F981D6857DC7F4E4E929AE5282587F31F92F77A3FA78F4B2DAC` |
| `CreateBlamEngineShell` | RVA `0x6980` — unchanged from CU2 |

**Verified: CU3 did not restore competitive content.** Still 13 scenario tags, all solo campaign
(`a15`…`e30`). Still no per-mode directory under `Tags/multiplayer/game_variant_settings/`. The
inventory below is CU3's, not inherited.

**Unverified:** the shell interface table RVAs recorded in
[`halosimulation_tag_release.md`](halosimulation_tag_release.md) (`0x7B1560`, `0x7B1610`) are CU2
figures. The export entry point did not move, but the tables may have; re-verify before relying on
them.

This supersedes the CTF-related speculation in
[`multiplayer_investigation_notes.md`](multiplayer_investigation_notes.md), which was written from
string extraction alone. Strings told us the definitions exist. Reading the shipped tags tells us
which of those definitions have anything behind them, and the answer changes the plan.

## Evidence Labels

- **Verified:** reproduced by dumping shipped data or decompiling the matching binary.
- **Observed:** present in an artifact, runtime reachability not proven.
- **Unverified:** a testable claim with no discriminating check run yet.

---

## Part 1 — What Actually Ships

### The short version

| Question | Answer |
|---|---|
| Are there CTF sounds? | **No audio, but the wiring is complete.** 510 events name their announcer sounds and display strings correctly; all 205 announcer sound tags are absent. |
| Are there CTF strings? | **Yes.** Fully localized, 12 languages, including "You captured a flag!" |
| Is there a flag object? | **No.** Oddball and the assault bomb ship; the flag does not. |
| Can the UE5 layer start a competitive match? | **No.** Its game-mode enum contains `Campaign` and nothing else. |
| Is there a network stack? | **Yes, two of them.** Neither is currently wired to a competitive mode. |
| Is there any way in? | **Yes.** A Lyra-style Experience framework ships with one asset in it and a `-BlamExperience=` selector. |

### CTF audio: the wiring survives, the voice does not

> **Revised 2026-08-04, after the `values` fix in PR #46.** The first pass read this section through
> a value tree capped at 64 elements and concluded the event table was as empty as the megalo sound
> table. It is not. `game_engine_globals` has **510 events, not 64**, and they are fully wired. The
> conclusion below is unchanged — there is no CTF announcer audio — but the reason matters, because
> it makes authoring that audio far cheaper than first estimated.

**Verified.** Two tables map game-engine events to announcer sounds, and they are in opposite states.

`multiplayer\megalo\english (mgls)` ships with **94 of its 95 slots empty**:

```text
flag_captured  =     [tag reference]
flag_taken     =     [tag reference]
flag_dropped   =     [tag reference]
flag_stolen    =     [tag reference]
flag_recovered =     [tag reference]
flag_reset     =     [tag reference]
...
invasion_beginning = sound\music\invasion_temp_cues\invasion_beginning (snd!)
```

The one populated slot is a leftover Halo Reach Invasion cue, and **its target does not ship either** —
there is no `invasion_beginning` anywhere in the containers. The reference dangles.

`game_engine_globals` is the opposite: **completely wired**. Its event-response list holds 510 events
naming 256 distinct sounds, 205 of them under `sound\dialog\multiplayer\`. The CTF events are there,
pointing at the right strings and the right audio:

```text
name = "flag_scored"
  display string = "ctf_flag_captured"
  sound = sound\dialog\multiplayer\capture_the_flag\flag_captured (snd!)
```

Alongside `flag_grabbed`, `flag_dropped`, `flag_dropped_neutral`, `flag_grabbed_neutral`,
`flag_reset`, `flag_reset_neutral`, `flag_recovered`, `neutral_flag_grabbed`, `flagcarrier_kill` —
and the equivalents for Oddball, KOTH, Assault, Territories, Infection, Juggernaut, plus the full
medal and spree set. The CTF announcer slots are exactly nine:

```text
sound\dialog\multiplayer\capture_the_flag\{capture_the_flag, offense, defense,
  flag_taken, flag_stolen, flag_dropped, flag_captured, flag_recovered, flag_reset}
```

**Verified: not one of those 205 sound tags ships.** `Tags/sound/dialog/` contains a single
subdirectory, `combat`, with 4,754 campaign battle-chatter entries. Nothing else.

**Verified in the `.pak` containers too**, which is where this build keeps its Wwise audio rather
than in IoStore. All 200,029 pak entries were listed: 194,559 are `WwiseAudio/Media` files named by
numeric hash, and the named Wwise *event* assets in IoStore are 14,339 `Systemic` entries plus
campaign categories — every VO event is battle chatter (`VO_SYS_Johnson`, `VO_SYS_Mendoza`, and so
on). There is no announcer event, in either container, under any name.

**What this changes.** The event table is not a ruin to be rebuilt; it is a finished harness with the
speaker unplugged. Supplying CTF announcer audio means authoring nine sound tags at nine known paths
and letting the existing wiring fire them — not implementing an event system. That is a content
task, and a small one.

What *does* ship under `Audio/game_sfx/multiplayer` is twelve non-vocal effects:

```text
comm_fail  comm_loop_mp (+3 stems)  countdown_for_respawn  flag_failure
player_respawn  player_timer_beep  shield_hit  teleporter_activate
```

Plus `sound/Weapons/flag/flag_drop-sound`. So there is a flag-drop stinger and a flag-failure
stinger, and nothing that says the word "flag" out loud.

### CTF text: complete and localized

**Verified.** `multiplayer\in_game_multiplayer_messages` carries **318 string ids** with translations
into English, Japanese, German, French, Spanish, Mexican Spanish, Italian, Korean, Traditional and
Simplified Chinese, and Portuguese. The CTF set is whole:

```text
ctf_flag_captured        ctf_flag_captured_cp     ctf_flag_grabbed_ct
ctf_flag_dropped         ctf_flag_dropped_et      ctf_flag_grabbed_cp
ctf_flag_recovered       ctf_flag_recovered_et    ctf_flag_grabbed_et
ctf_flag_reset           ctf_flag_reset_et        ctf_failed_capture_cp
ctf_game_start           ctf_new_defensive_team   ctf_new_defensive_team_ct
ctf_kill_carrier_cp/ct/ep/et
state_you_have_flag      state_enemy_has_your_flag
state_flag_away_from_home  state_flag_contested
medal_flag_grab          medal_flag_carrier_kill
```

With real text behind them: `You captured a flag!`, `#cause_team captured a flag!`,
`Enemy has your flag!`, `Your flag is missing!`, `Flag is contested`, `Flag Taken`, `Flag Save`,
`#effect_team flag reset`, and `Capture the Flag` as the mode name. The full medal set is there too —
`medal_killtacular`, `medal_running_riot`, `medal_sniper_kill`, and the rest.

`global_multiplayer_messages` (152 ids) adds the mode roster (`variant_ctf`, `variant_slayer`,
`variant_oddball`, `variant_king`, `variant_juggernaut`, `variant_territories`, `variant_infection`,
`variant_assault`, `variant_vip`), scoreboard headers, placings, and the Reach default variant names
(`variant_name_team_slayer`, `variant_name_rockets`, `variant_name_elimination`, `variant_name_duel`).
`globals/game_engine_text` carries another 553, and `UI/Hud/hud_messages` 695.

**So the entire text layer of a CTF match is already shipping in twelve languages.** This is the
single largest piece of work we do not have to do.

> **Tooling defect — fixed.** `mjolnir values` used to report these blocks as having exactly 64
> elements when the raw payload has 318. The `unic` reader was never at fault: it read the true
> count all along, and the CLI printed how many elements the value tree had *materialised* instead.
> The tree is capped at 64 elements per block so a `scenario_structure_bsp` cannot exhaust memory,
> and `--elements` only ever trimmed the printout, so it could not raise that cap. `values` now
> prints the block's real count and `--elements n` builds enough of the tree to show `n`. Any
> string-count figure in the older notes that came from `values` and reads exactly 64 is wrong low
> and should be re-read.

### The flag object does not exist

**Verified.** `multiplayer_object_type_list` ships with 18 entries. All eighteen are weapons —
assault rifle through sentinel gun. There are no objective objects in it.

`multiplayer_globals` names exactly two objective objects, and carries a shipped warning about them:

```text
ball         = objects\weapons\multiplayer\skull\oddball (weap)
assault bomb = objects\weapons\multiplayer\assault_bomb\assault_bomb (weap)
```

> "the ball and bomb references are not directly touched by game code, but the references are load
> baring \[sic]. Removing these fields or emptying the reference will cause their
> multiplayer_object_type_list entries to fail to resolve and result in oddball/assault megalo
> variants to fail to load"

Both ship complete — model, collision, physics, skeleton, animation graph, effects. **There is no
equivalent for the flag.** No `weap`, no model, no animation graph. The `mulg` structure has no flag
field at all.

This is why **CTF is the most expensive objective mode to target, not the cheapest.** Oddball needs
no new art. CTF needs a carryable flag object built from scratch.

### The variant settings tags were cut

**Verified.** The DLL's definition strings promise a settings UI for every mode — `ctf top level
options`, `ctf primary options`, `ctf advanced options`, `ctf carrier traits` and its
appearance/movement/sensors/shields/weapons children, and the same for Slayer, Oddball, KOTH,
Infection, Juggernaut, Assault, Territories.

The shipped tag tree under `Tags/multiplayer/game_variant_settings/` contains nine directories:

```text
custom_loadouts (440)  player_traits_template (88)  map_overrides (22)  Sandbox (22)
respawn_options (18)   global_options (12)          social_options (6)  megalo (6)
multiplayer_editable_settings
```

**No `ctf`. No `slayer`. No per-mode directory of any kind.** The shared machinery survived the cut;
every mode-specific settings tag was removed. `game_engine_settings` itself ships, but contains only
the player-traits schema — damage resistance, shield multipliers, weapon modifiers — with no mode
definitions.

Likewise `megalo_string_id_table` ships, but its 57 entries are Reach map and character leftovers
(`mp_boneyard_a_fly_in`, `carter`, `emile`, `mp_spire_fp`), not gameplay hooks.

### The hard blocker: the UE5 layer only knows Campaign

**Verified in the matching host executable.** `EBlamGameEngineType` is registered with exactly three
members:

```text
EBlamGameEngineType::None
EBlamGameEngineType::Campaign
EBlamGameEngineType::Num
```

The reflected variant classes are `UBlamGameEngineBaseVariant` and `UBlamGameEngineCampaignVariant`.
There is no CTF variant class, no Slayer variant class, nothing else deriving from the base.

And a whole-binary check, both ASCII and UTF-16:

| Term | Occurrences in `HaloCampaignEvolved.exe` |
|---|---:|
| `Slayer` | 0 |
| `CaptureTheFlag` | 0 |
| `Oddball` | 0 |
| `Juggernaut` / `Territories` / `Infection` | 0 |
| `Firefight` | 0 |
| `Multiplayer` | 531 |
| `Matchmaking` | 101 |

**The host has no notion that competitive modes exist.** The Blam DLL carries their definitions; the
UE5 process that drives the Blam DLL cannot name one. This is the reason no console command, tag
edit, or Blueprint mod is going to "turn CTF back on" — there is nothing on the UE5 side to turn on.

**Unverified, and the one check that could still change this:** whether the Blam DLL retains
*executable* game-engine code for the competitive modes, reachable through the shell interface
without the UE5 enum. String evidence is ambiguous — the megalo material in the DLL is definitions,
traits, and HUD widgets rather than an interpreter. See Phase 1.

### Two network stacks, both real

**Verified — Blam side.** The simulation DLL carries the complete Halo Reach network layer. 131
`net_*` / `network_*` console command names, including:

```text
network_session_class_system_link / xbox_live / offline
network_session_privacy_open / friends_only / invitation_only
net_build_game_variant       net_load_and_use_game_variant   net_verify_game_variant
net_build_map_variant        net_load_and_use_map_variant
net_force_host  net_force_host_squad  net_host_delegation_disable
net_speculative_host_migration_disable
net_status_sessions / connections / channels / link
net_maximum_machine_count  net_maximum_player_count  net_skip_countdown
```

Plus host-selection quality metrics, host migration, a full `join_failed_*` reason set (NAT
strictness, version mismatch, game not open, not enough space), and the Reach lobby data model as
`prop_*` UI bindings — `prop_game_start_countdown_timer_total_seconds`, `prop_game_start_status_ready`,
`prop_game_variant_name`, `prop_game_variant_max_team_count`, `prop_hopper_id`.

The Blam HSC command table also carries `game_multiplayer`, `game_set_variant`, `game_start`,
`game_start_when_ready`, `game_start_when_joined`, `game_start_with_squad_session`, `game_player_count`,
`game_splitscreen`, `map_name`, `switch_map_and_zone_set`.

**Verified — UE5 side.** The host links the standard Unreal networking stack: `IpNetDriver`,
`GameNetDriver`, `?listen`, `UWorld::ServerTravel`, `IsDedicatedServer`, Iris replication configs,
and `OnlineSubsystemNull` with `bIsLanMatch` and LAN session support. It also links the PlayFab
lobby and multiplayer-server client APIs (`CreateLobby`, `JoinLobby`, `JoinLobbyAsServer`,
`RequestMultiplayerServer`, `ListMultiplayerServers`) and `PartyWin` for P2P and voice.

`EBlamMultiplayerTeam` ships complete: `Red, Blue, Green, Orange, Purple, Yellow, Brown, Grey`,
matching the eleven team colors in `multiplayer_globals`. Teams are a live concept in the host.

**So:** a UE5 listen server is architecturally available, and `EBlamOnlineSessionTransitionState`
(`CreatingSession`, `JoiningSession`, `LeavingForJoin`, …) shows the game already drives session
create/join for campaign co-op. What is missing is not transport. It is a mode to play.

### There is a supported way to add a game mode

Everything above says what was taken out. This says what was left in, and it is the most useful
finding in this document.

**Verified.** The host ships a Lyra-style *Experience* system as its own reflected module,
`/Script/BlamExperience`:

```text
UBlamExperienceDefinition          UBlamExperienceManager
UBlamExperienceManagerComponent    UBlamExperiencePlayerStateComponent
UAsyncAction_BlamExperienceReady   DefaultBlamExperience
BlamEngine.ExperienceDelayLoad.MinSecs / .RandomSecs
```

In Unreal terms an Experience *is* a game mode: a data asset naming the pawn data, components,
abilities, and GameFeature plugins to compose for a session. The full GameFeatures subsystem is
linked too — `GameFeaturesSubsystem`, `GameFeaturePluginStateMachine`, `GameFeaturesToEnable`,
`EGameFeatureTargetState`.

**Verified: exactly one Experience ships, and it is empty.**
`/Game/Blueprints/Experiences/BP_BlamExperienceDefault` — one asset in a system built to hold many,
and its `GameFeaturesToEnable`, `Actions`, and `ActionSets` are all zero-length. The framework runs;
nothing currently uses it. No shipped example shows how to compose a Halo mode from one.

**Verified: `BlamExperienceDefinition` is a registered primary asset type** in the engine's
`AssetManagerSettings`, alongside `Map`, `GameFeatureData`, `Frontend`, and five others. An
experience delivered in a mod pak under a scanned path is discoverable without a code change.

And there is a selector. The string `-BlamExperience=` sits directly alongside `OptionsString`,
`ABlamGameMode`, `ABlamGameModePlayerStart`, and `UBlamGameInstance` — the exact neighbourhood of
Lyra's experience-resolution chain, where the game mode picks an experience from a command-line
override, then a URL option, then world settings, then developer settings.

**Verified at runtime on CU3:** all five of those classes resolve, a `BlamExperienceManager` is live
on the engine at the frontend, and `UBlamExperienceDefinition`'s CDO carries exactly
`GameFeaturesToEnable`, `Actions`, and `ActionSets` — Lyra's definition, field for field. The
framework is not vestigial; it is running.

**Still unverified:** whether `-BlamExperience=<asset path>` is honoured, and what
`BP_BlamExperienceDefault` contains. See Phase 1 step 5 for how far that got and what took the game
down.

Note also `ABlamGameModePlayerStart` — a player-start class already exists, which is what team spawns
need.

**Why this matters.** Architecture B does not have to mean bolting gameplay onto the campaign with
Blueprint hooks and hoping. It can mean authoring a second Experience — the extension point the
engine was built around, shipped, reflected, and selectable — and delivering it in a LogicMods pak.
That is a supported path rather than a hack, which changes both the odds and the maintenance cost.

### Where that leaves us

```
Blam DLL          ██████████████████░░  definitions, network layer, lobby model — no launch path
Shipped tags      ████░░░░░░░░░░░░░░░░  strings + oddball + bomb + traits; no modes, no flag
UE5 host          ██░░░░░░░░░░░░░░░░░░  Campaign only; teams and sessions exist
Experience system ████████████████░░░░  full framework, one asset in it, selector present
Transport         ████████████████████  UE net driver, LAN, Steam, PlayFab lobbies, Party P2P
```

The gap is a **game mode**, not a network layer and not content — and the engine ships the socket a
game mode plugs into. That reframes the whole project.

---

## Part 2 — The Plan

### The decision this plan turns on

Three architectures could put two players in a CTF match. They are not equally likely to work.

**A. Revive the Blam competitive engine.** Find the shell's startup structure, set the game-engine
type to CTF, feed it a game variant, let the Blam DLL run the match. *If* the code is still in the
DLL, this is the highest-fidelity outcome — real Blam CTF. If the code was stripped along with the
UE5 enum, it is a dead end. **Unverified. Phase 1 decides it.**

**B. Author a second Experience.** Use the shipped `/Script/BlamExperience` framework as intended:
a new `UBlamExperienceDefinition` describing an objective mode, selected through the same chain
`BP_BlamExperienceDefault` is, delivered in a LogicMods pak. Flag carry, scoring, and team spawns
become components and actors composed by the experience, with the shipped string tags for text, the
team enum for sides, `ABlamGameModePlayerStart` for spawns, and the oddball skull as the carryable.
*Always available, and it is the engine's own extension point rather than a hook into campaign code.*

**C. External dedicated server.** Not a real option for the first milestone. Both PlayFab's server
product and a UE dedicated build need a server-side executable we do not have — the shipping binary
is a client. Worth noting that `SteamGameServer` symbols are linked, which is the usual route to a
public server browser, but that is a Phase 5 question at the earliest. Revisit only after B works.

**Recommendation: run Phase 1 to settle A, and build B's foundation in parallel** — the transport
and lobby work in Phases 2–3 is needed under either architecture, so it is not wasted either way.

**Recommendation on the mode: target Oddball first, CTF second.** Oddball needs no new art (the
skull ships complete with model, physics, and animation), has the same carry/drop/score shape as
CTF, and its strings ship too. Prove the loop with the skull, then swap in a flag once we are
building objects. The user goal — *two or more players in a lobby playing an objective mode* — is met
sooner, and CTF becomes a content problem instead of a content-plus-systems problem.

### Phase 1 — Settle whether the Blam engine can still run a match

Decides between A and B. Do not build anything until this returns.

> **Result, 2026-08-04: step 2 was attempted and did not answer the question. Recorded here rather
> than quietly retried, because the failure is informative and the next person should not repeat it.**
>
> `AnalyzeGameEngineCode.java` walks from a probe string up to whatever code consumes it, with two
> calibration groups: known tag-definition names and known console-command names. Version one asked
> the naive question — is the string referenced from an instruction? — and got zero for every group
> *including both controls*. Blam is table-driven: strings are referenced only by pointer-table
> entries, and code holds the table base.
>
> Version two follows the chain, scanning backwards in pointer steps when a hop dead-ends on a table
> interior. Its summary looks like a result and is not one:
>
> ```text
> CONTROL_DEFINITION found=5  code=3  stranded=2  avgHops=8.0
> CONTROL_CODE       found=5  code=2  stranded=1  unref=2  avgHops=4.0
> CTF                found=7  code=0  stranded=7
> OTHER_MODES        found=6  code=0  stranded=6
> ```
>
> The mode groups strand completely while the controls reach code, which is the shape a real finding
> would have. But the trails say otherwise:
>
> - Every CTF probe converges on an **identical** tail — `180a45c00 → 180a43260 → 180a43230 →
>   180a43060 → 180a42f40 → 180a42db8 → 180a42d98` — no matter which string it started from. The
>   backward scan is wandering through a data region, not climbing a real hierarchy.
> - The three `CONTROL_DEFINITION` successes all landed at *exactly* the 8-hop limit, two of them in
>   the same function through a shared tail. That is the scan eventually bumping into something
>   referenced, not a traced chain.
> - `game_set_variant` and `game_multiplayer` came back **unreferenced**. They are console command
>   names; they are certainly reachable. A control that reports the impossible invalidates the run.
>
> So the 100% strand rate on the mode groups is at least as likely to mean "the walk ran out of hops
> on a wandering path" as "there is no code". **No conclusion may be drawn from it.** The independent
> string-level check is weakly consistent with definitions-only — the DLL has no megalo interpreter
> strings and no game-variant-file parsing structures — but absence of strings is not absence of code.
>
> **The gate is being closed on different grounds.** Architecture A needs two things: game-engine
> code in the DLL, *and* a reachable path to invoke it. The second is already **Verified absent** —
> the host's `EBlamGameEngineType` has only `Campaign` and the executable cannot name a competitive
> mode. Even if the DLL code were fully intact, reaching it would mean hand-synthesising calls into
> the shell, which is its own research project rather than a route to two players in a lobby.
> Resolving step 2 properly would need a sounder method (typing the pointer tables and following real
> structure, rather than a proximity heuristic) and would not change what we build next.
>
> **Proceed on architecture B.** Steps 1 and 3 are deferred, not done. Step 5 is now the priority.

1. **Ghidra: shell primary slot 2.** The 14.6 MB DLL's slot 2 is the large startup path
   ([`halosimulation_tag_release.md`](halosimulation_tag_release.md)). Recover the structure it takes
   and look for a game-engine-type field. Extend `AnalyzeBlamShell.java`.
2. **Ghidra: is there code behind the definitions?** Cross-reference the `game_engine_*` and CTF
   strings to their owning functions. Distinguish *definition tables* (data describing a tag layout)
   from *game-engine update functions* (code that would run a match). This is the discriminating
   check. If every CTF string resolves only into definition tables, A is dead.
3. **Ghidra: the console command table.** The 131 `net_*` names imply a Blam command registry. Find
   its dispatch entry point. If we can call it, `net_status_sessions`, `game_multiplayer`, and
   `game_set_variant` become directly testable.
4. **Runtime: probe the variant surface.** Using the existing bridge, call
   `UBlamGameEngineBaseVariant::GetGameEngineType` and `GetVariantStorage` on the live campaign
   variant, and try to construct a base variant with a non-Campaign type. Confirms or refutes the
   enum finding from the inside.
5. **Runtime: does `-BlamExperience=` work?** Launch with the switch pointing at
   `/Game/Blueprints/Experiences/BP_BlamExperienceDefault` — the one experience that ships — and see
   whether `UBlamExperienceManagerComponent` reports it as the selection. Selecting the *default*
   proves the switch is honoured without needing a mod to exist yet. Then read
   `BP_BlamExperienceDefault` to learn what a definition has to fill in.

   This is cheap, it needs no second player, and it is the single check that most determines how
   much work architecture B is. Do it first.

   > **Partial result, 2026-08-04, CU3, at the frontend.** The framework is real and live.
   >
   > **Verified** — each of these printed a genuine object path, not just a non-null pointer:
   >
   > ```text
   > Class /Script/BlamExperience.BlamExperienceDefinition
   > Class /Script/BlamExperience.BlamExperienceManager
   > Class /Script/BlamExperience.BlamExperienceManagerComponent
   > Class /Script/BlamExperience.BlamExperiencePlayerStateComponent
   > Class /Script/BlamExperience.AsyncAction_BlamExperienceReady
   > ```
   >
   > **Verified:** `UBlamExperienceDefinition`'s CDO carries exactly three properties —
   > `GameFeaturesToEnable`, `Actions`, `ActionSets`. That is Lyra's `ULyraExperienceDefinition`
   > field for field, which tells us precisely what a new experience has to fill in.
   >
   > **Verified:** a `BlamExperienceManager` instance is live on the engine at the frontend,
   > `/Engine/Transient.GameEngine_*:BlamExperienceManager_*`, before any gameplay world exists. The
   > system is running in the shipping build, not merely compiled in.
   >
   > **Verified:** no `BlamExperienceManagerComponent` and no definition instance exist at the
   > frontend, which matches Lyra — the component lives on the GameState of a gameplay world.
   >
   > **Not established, and the probe that tried it crashed the game:** where the default experience
   > is configured, and whether `-BlamExperience=` is honoured. `StaticFindObject` returns a garbage
   > non-null pointer for paths that do not exist, and reading properties off one exits the process;
   > see the hazard note in [`game_automation.md`](game_automation.md). An earlier loop in the same
   > session reported `BlamExperienceSettings` and `BlamDeveloperSettings` as present in five
   > different modules, which is exactly that failure mode. **Disregard those; they were never
   > verified.**
   >
   > **Second pass, same day, CU3.** The switch test was run and **did not produce a verdict**, for a
   > reason worth recording: it passed the wrong kind of value.
   >
   > **Verified — the shipped experience is empty.** `BP_BlamExperienceDefault` loads via `LoadAsset`,
   > and its class chain is
   >
   > ```text
   > BP_BlamExperienceDefault_C
   >   -> /Script/BlamExperience.BlamExperienceDefinition
   >   -> /Script/Engine.PrimaryDataAsset
   >   -> /Script/Engine.DataAsset -> Object
   > ```
   >
   > Its CDO carries `GameFeaturesToEnable = 0`, `Actions = 0`, `ActionSets = 0`. **All three are
   > empty.** The framework is live but *unused*: the campaign does not get its gameplay from it.
   > That cuts both ways — nothing to conflict with, but also no worked example of how to compose a
   > Halo mode out of one.
   >
   > **Verified — experiences are a registered primary asset type.** The engine's
   > `AssetManagerSettings` scans eight types, and `BlamExperienceDefinition` is one of them:
   >
   > ```text
   > Map  PrimaryAssetLabel  InputMappingContext  Frontend
   > GameFeatureData  BlamBuiltInMapInfoDataAsset  BlamExperienceDefinition  Audio Globals
   > ```
   >
   > This matters twice over. An experience shipped in a mod pak under a scanned path will be
   > *discovered* by the AssetManager without any code change. And it means `-BlamExperience=`
   > almost certainly takes an `FPrimaryAssetId` — `BlamExperienceDefinition:BP_BlamExperienceDefault`
   > — the way Lyra's `-Experience=` does, **not** the `/Game/…` object path the test passed.
   >
   > **So the switch remains unverified**, and the next attempt should pass the primary-asset-id form.
   >
   > **Also verified, and it clears the switch of suspicion:** the direct-exe run hung after the title
   > screen, but a control launch with **no switch at all** hung identically — same place, 2124s vs
   > 2139s CPU, 6496 MB vs 6505 MB resident. The hang is the launch route, not the switch. A
   > Steam-launched run stayed responsive throughout. **Launch through Steam; direct-exe launches hang
   > leaving the title screen even though the bridge answers and the frontend renders.**
   >
   > **Blocked on the environment, not the game.** Menu input could not be delivered: the foreground
   > window was held by an *invisible* `GameInputSvc` window, so `SetForegroundWindow` failed, a
   > synthetic click at the window centre failed to claim it, and `game_input` correctly reported the
   > focus warning. Reaching a gameplay world — needed to see `BlamExperienceManagerComponent` and
   > `CurrentExperience` — needs that cleared or a human at the keyboard.
   >
   > **Next:** relaunch through Steam with
   > `-BlamExperience=BlamExperienceDefinition:BP_BlamExperienceDefault`, get into any mission, and
   > read `CurrentExperience` off the manager component. Passing a deliberately bogus id in a second
   > run is the cheap discriminator: if the game behaves identically either way, the switch is dead.

**Gate:** ~~if (2) finds live game-engine code and (1) finds a type field, pursue A. Otherwise B.~~
**Closed 2026-08-04 on B**, for the reason recorded above: the invocation path for A is verified
absent, so the DLL-code question no longer changes the decision.

### Phase 2 — Get two humans into one session, unmodified

This is the milestone everything else stands on, and it is the one thing in this whole plan that the
shipping game already does. It also needs a second person; the existing notes flag that as the
standing blocker, and every "co-op" capture so far has been a solo baseline mislabelled.

1. Bring in a second tester. Nothing below is meaningful without one.
2. Capture a real two-player campaign co-op session with `mjolnir_trace_network` and
   `mjolnir_dump_state`, at the frontend and again in-mission.
3. Diff against the solo baseline already recorded on 2026-07-26. The known solo values are
   `bSessionRunning = false`, both endpoint IDs `0`, `TotalPlayerCount = 1`. Establish which of
   those actually change when a peer connects — endpoint generation advancing to `1` is *not* a peer
   signal, that happens solo.
4. Record which layer carries gameplay state: UE replication, or the Blam DLL's own WS2_32 sockets.
   This determines where a custom mode's state has to live, and it is currently a guess.

**Deliverable:** a verified two-player state fingerprint. **Gate:** we can reliably get two players
into one session and read that fact programmatically.

### Phase 3 — A lobby we control

1. Stand up a session outside the campaign flow. Try, in order of decreasing preference:
   `OnlineSubsystemNull` LAN (no accounts, no PlayFab, easiest to iterate); `OnlineSubsystemSteam`,
   which is also linked and would give internet play without standing up our own service; the
   reflected `BlamOnlineSessionSubsystem` create/join path; raw `?listen` server travel.
   Note that `open` from the frontend crashes this build — `EXCEPTION_ACCESS_VIOLATION` reading
   `0x1c`, see [`game_automation.md`](game_automation.md) — so travel has to happen from in-game or
   through the session subsystem, not from the menu.
2. Build a minimal join UI. The `Meteorite` squad-lobby view models (`UMeteoriteSquadLobbyViewModel`,
   `UMeteoriteSquadWidgetBase`) already exist and already show player count and crossplay state;
   extend rather than replace.
3. Only once a LAN join works end to end, consider a master server list. It is a thin directory over
   a working join, and worthless before one.

**Deliverable:** two players in a lobby we built, on a map we chose. **This meets the stated goal,
before any game mode exists.**

### Phase 4 — The mode

Under architecture B. Under A, this collapses to configuring a variant instead.

0. **The Experience asset.** Author a second `UBlamExperienceDefinition` and get the game to select
   it, before writing any gameplay. Everything below then hangs off that asset instead of being
   patched into the campaign. If Phase 1 step 5 showed the selector does not work, this step becomes
   "find how `BP_BlamExperienceDefault` is chosen and hook that instead" — and the rest is unchanged.
1. **Scoring and state.** Team scores, round timer, win condition. Server-authoritative on the
   listen host.
2. **The carryable.** Start with the shipped oddball skull. Pick up, drop on death, return on timer.
3. **Objective volumes.** Capture points and return points as actors placed in a custom map — we
   have already proven custom maps work.
4. **Feedback.** Wire the shipped strings: `state_you_have_flag`, `ctf_flag_captured`,
   `medal_flag_grab`. The text and its twelve translations are free.
   Announcer audio is a separate, smaller task than it first looked: `game_engine_globals` already
   binds each event to a display string *and* a sound path, so filling the nine
   `sound\dialog\multiplayer\capture_the_flag\` tags is all that stands between the existing harness
   and a talking announcer. Under architecture B this only pays off if our mode raises the same Blam
   events; under A it is close to free. Either way, `flag_drop` and `flag_failure` ship and should be
   used regardless.
5. **Then CTF.** Build the flag object — model, collision, physics, skeleton, animation graph,
   following `objects/Weapons/multiplayer/Skull/` as the template, since that is the shipped example
   of exactly this kind of object. Swap it for the skull.

### What would change this plan

- **Phase 1 finds live Blam game-engine code.** Then architecture A, and Phase 4 becomes variant
  authoring instead of gameplay programming. Best outcome; treat as unlikely given the UE5 enum, but
  it is the cheapest thing to check and the payoff is large.
- **A later game update restores competitive content.** The build is version-locked above; re-run
  the Part 1 checks against any new build before trusting this document. This already happened once
  — the install moved CU2 → CU3 between the previous investigation and this one, and CU3 changed
  none of the conclusions. Check the hashes first every time; do not assume.
- **Gameplay state turns out to live entirely in the Blam DLL.** Then a UE5-side mode cannot own
  authoritative state, and Phase 4 needs a different design. Phase 2 step 4 is what tells us.
- **The Experience selector turns out to be dead or editor-only.** Then architecture B loses its
  clean extension point and falls back to hooking campaign flow, which is more work and more
  fragile. Phase 1 step 5 is what tells us, and it is cheap enough to run before anything else.

---

## Reproduction

Dumps in Part 1 came from the repository CLI against an untouched install. Nothing is written to
disk; extracted tag data is copyrighted game content and stays in memory.

```bash
export HCE_PAKS="/c/Program Files (x86)/Steam/steamapps/common/Halo Campaign Evolved/Meteorite/Content/Paks"
cargo build --release -p blam-cli
```

```bash
./target/release/mjolnir.exe values --group megalogamengine_sounds --all --elements 200
```

```bash
./target/release/mjolnir.exe values --group multiplayer_globals --depth 5
```

```bash
./target/release/mjolnir.exe values --group multiplayer_object_type_list --depth 5 --elements 100
```

String-id and localized-text counts were read from the raw chunk, because `values` truncated `unic`
blocks at 64 elements when this document was written:

```bash
./target/release/mjolnir.exe chunk --path "in_game_multiplayer_messages-multilingual_unicode_string_list.ubulk" --hexdump 200000
```

That defect is fixed, so `values` now reports the block's real count and lists every element when
asked. The two agree at 318 for `in_game_multiplayer_messages`:

```bash
./target/release/mjolnir.exe values --group multilingual_unicode_string_list --tag in_game_multiplayer_messages --depth 5 --elements 4000
```

The 510-event announcer table:

```bash
./target/release/mjolnir.exe values --group game_engine_globals --depth 5 --elements 2000
```

Wwise audio lives in the `.pak` containers, not IoStore, so the absence of announcer audio has to be
checked there too. `ue_iostore::pak::load_all` over `Meteorite/Content/Paks` lists all 200,029
entries; the named Wwise *event* assets are in IoStore under
`Meteorite/Content/WwiseAudio/Events/`, and every VO category there is campaign battle chatter.

Host-executable enum checks were done by extracting both ASCII and UTF-16 strings from
`HaloCampaignEvolved.exe` and searching for `EBlamGameEngineType::`, `EBlamMultiplayerTeam::`, and
the mode names in the table above. The Experience framework was found the same way — search the
UTF-16 set for `Experience` and for `-BlamExperience=`, whose neighbours in the string table are
`OptionsString`, `ABlamGameMode`, and `ABlamGameModePlayerStart`. The reflected module list comes
from the ASCII set, matching `^/Script/[A-Za-z]+$`.

The one shipped Experience asset is in the IoStore path index:

```bash
grep -i experience out/iostore_paths.tsv
```

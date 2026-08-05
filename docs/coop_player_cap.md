# Where the Four-Player Co-op Cap Lives

**Question:** campaign co-op seats four. What has to change for it to seat eight?

**Short answer:** four is not one number. It is a policy constant sitting on top of an engine
that is already built wider than four, wrapped in a session layer and a hosted lobby service that
each keep their own count. The simulation's player table holds `32`. Nothing found so far requires
the cap to be four; several things assume it.

This note records what was measured, on which build, and by what method. Claims are marked
**Verified** (measured directly), **Observed** (seen, with a stated limit on what it proves), or
**Unverified** (not yet tested).

---

## Build

Measured on **CU3**, `2026.07.25.1112544.4-Rel-i343-Meteorite-2607-CU3`. The hashes live in
[`build_lock.md`](build_lock.md) rather than being restated here; confirm an install matches with:

```bash
python tools/build_lock.py "<install root>" --verify config/hce-build.lock.json
```

Every offset below is a file offset into the CU3 `HaloSimulation_tag_release.dll`
(image base `0x180000000`). They will move on the next content update.

---

## The Four Layers

A fifth player has to get past all four of these. They fail differently, which is the whole reason
to separate them.

| Layer | Owns | Reachable from a Lua mod? |
|:--|:--|:--|
| Unreal session | `MaxPlayers`, splitscreen counts, net driver | **Yes** — properties and a stock cvar |
| Meteorite squad UI | Lobby rows, join slots, invite flow | Partly — reflected, but Blueprint-driven |
| PlayFab lobby | `maxMemberCount`, membership validation | **No** — enforced by the service |
| Blam simulation | Player datum array, campaign policy, replication | **No** — native, and every peer must match |

---

## Layer 4: the simulation is not the wall people assume

### The player table holds 32, not 4

**Verified by disassembly.** The players datum array is constructed at `0x180181010`:

```asm
180181010  push rbx …                       ; allocator prologue
18018102b  mov  edx, 0x4b74                 ; total allocation
180181053  lea  rbp, [rax + 0x70]           ; array base
180181057  mov  edi, 0x20                   ; ← element count = 32
180181061  lea  r14, [rbp + 0x4b00]         ; array end  (0x4b00 = 32 * 0x258)
18018106a  lea  rcx, [rip + 0x65e987]       ; "players"
180181074  call qword ptr [rip + 0x60e80e]  ; data_new(name, count)
```

`0x4b00 / 0x20 = 0x258`, so the array is `32` player data of `600` bytes each. **The simulation
allocates room for 32 players regardless of game mode.** Whatever caps campaign co-op at four, it
is not the size of this table.

### The campaign constant that *is* four

**Verified.** The string `k_maximum_campaign_players` at `0x84d740` is referenced once, from a tag
block definition at `0x9b9e60`. Tag block definitions in this build lay out as
`[name_ptr][max_count][max_count_name_ptr]`, giving:

```
scenario_player_appearance_customization_array   max = 4   (k_maximum_campaign_players)
```

So `k_maximum_campaign_players == 4` in CU3, and the only tag data it bounds is **appearance
customization** — cosmetic per-player slots. It is a real compiled constant, and code elsewhere
almost certainly sizes fixed arrays with it, but the one use that is visible in tag data is
not gameplay-critical.

### Scenario content does not cap at four

**Verified**, same method:

```
scenario_players_block     max = 256   (MAXIMUM_SCENARIO_PLAYERS_PER_BLOCK)
scenario_profiles_block    max = 256   (MAXIMUM_SCENARIO_PLAYERS_PER_BLOCK)
```

Spawn points and starting profiles are not the constraint. The campaign maps can describe far more
than four players' worth of starting state.

### The AI difficulty tables already scale past four

**Verified** by string extraction from `coop_difficulty_block` (`0x889c60` onward). The block
carries scalars for two-, three-, four-, and **six-or-more**-player co-op, across enemy shield
recharge delay and timer, armor lock chance, grenade dive chance, evasion chance/delay/danger
threshold, burst duration and separation, damage modifier, projectile speed, and major upgrade
chance:

```
six-player shield recharge delay#multiplier on enemy shield recharge delay with six coop players or more
six-player grenade dive chance#multiplier on enemy grenade dive chance with six coop players or more
six-player major upgrade#multiplier on the major upgrade chance … with six coop players or more
```

**Observed:** the engine's encounter-balancing model was authored for co-op parties larger than
four. This is evidence about the data model's intent, not proof that a six-player campaign session
was ever run. But it does mean an eight-player party would land in a defined bucket rather than
falling off the end of a table.

### Named refusals

**Verified.** The simulation carries distinct error identifiers, mapped to codes in a table at
`0x8376e8`:

```
0x500009  error_too_many_local_players_for_coop
0x50000a  error_too_many_players_for_network_coop
0x50000b  error_players_incompatible_for_network_coop
```

Local and network overflow are *separate* refusals. That matters: it means splitscreen count and
connected-peer count are checked independently, so raising one without the other will produce a
diagnosable failure rather than a silent one. No direct code reference to `0x50000a` was found by
immediate scan, so the constant is likely loaded indirectly; the emitting call site is
**Unverified**.

### Blam-side config variables

**Verified** present in the simulation's registered variable tables:

```
0x9a27d8   net_maximum_player_count          (adjacent: net_maximum_machine_count)
0x9a1500   net_config_maximum_multiplayer_split_screen_override
```

These are registered names, not values — the neighbouring qwords are type tags, not defaults.
**Unverified:** whether HCE exposes any route to set them. The Blam variable system is internal to
the simulation shell; the UE5 developer console does not reach it. If a route exists it runs through
`CreateBlamEngineShell`'s interface tables — see
[`halosimulation_tag_release.md`](halosimulation_tag_release.md).

---

## Layer 1: the Unreal session limits are reachable

**Verified** present in the CU3 host by string extraction:

```
net.MaxPlayersOverride          MaxPlayers            GetMaxPlayers
MaxSplitscreensPerConnection    MaxSplitscreenPlayers
```

`net.MaxPlayersOverride` is stock Unreal: `AGameSession::InitOptions` prefers it over the configured
`MaxPlayers` whenever it is greater than zero. It is a normal console variable and survives the
session object being rebuilt, which the raw property write does not.

`MJOLNIRCoop8` sets the cvar and raises `MaxPlayers`, `MaxSpectators`,
`MaxSplitscreensPerConnection` and `MaxSplitscreenPlayers` on every live instance it can find.

**Verified in the running game** (CU3 frontend, 2026-08-05), read back after each write:

```
[cvar] net.MaxPlayersOverride 8              dispatched (KismetSystemLibrary)
[prop] GameSession.MaxPlayers                raised 4 -> 8
[prop] GameSession.MaxSpectators             raised 0 -> 8
[prop] GameSession.MaxSplitscreensPerConnection  raised 2 -> 8
[prop] GameViewportClient.MaxSplitscreenPlayers  raised 4 -> 8
```

So the Unreal layer's stock 4 is real, and it moves. Whether anything downstream honours the new
value is a separate question that needs a second player.

`UGameMapsSettings` is **not** reachable this way. Its CDO resolves, but every property on it reads
back as UE4SS's `TrivialObject` placeholder, including ones that certainly exist — missing
reflection data rather than a missing property. Anything needing it has to go through an ini.

One thing did **not** move: `MeteoriteSquadLobbyViewModel:CanAddSplitscreenPlayer` still returned
`false` after every cap above was raised. Whatever gates a second local player, it is not these
properties.

---

## Layer 3: PlayFab is the layer a mod cannot argue with

**Verified** present in the host: `PFLobbyGetMaxMemberCount`, `LobbyCurrentPlayersMoreThanMaxPlayers`,
`LobbyPlayerMaxLobbyLimitExceeded`, `MaxMembers`, `MaxPartySize`.

Lobby membership is validated by the PlayFab service, not by the client. If `CreateLobby` is issued
with `maxMemberCount = 4`, the fifth join is refused server-side no matter what the client believes.
Whether the client picks that number — in which case it is patchable — or the title configuration
pins it — in which case it is not — is **Unverified** and is the single highest-value thing to
measure next. `MJOLNIRCoop8` hooks `CreateLobby`, `JoinLobby`, and `JoinArrangedLobby` to capture it.

---

## Layer 2: the squad UI counts its own rows

**Verified** reflected surface on `UMeteoriteSquadLobbyViewModel`:

```
TotalPlayerCount        GetNumSquadMembers      CanAddSplitscreenPlayer
bOfferJoinSlots         EMeteoriteSquadLobbyRowType::{Player, SplitscreenPrompt, Blank, Num}
```

The lobby is a row list with explicit blank rows, so the visible four slots come from a count the
widget is given.

### The FIRETEAM 1/4 panel can be extended at runtime

**Verified on the CU3 main menu**, on screen, not inferred. The live widget is
`WBP_SquadWidget_C` under `WBP_MeteoriteUILayout_C`, and the two members that matter are:

| Member | Type | Effect |
|:--|:--|:--|
| `FireteamHeader` | `HaloUITextBlock` | `SetText(FText("FIRETEAM 1/8"))` — the header re-rendered as `1/8` |
| `SquadListView` | `HaloUIListView` | `AddItem(<new MeteoriteSquadLobbyViewItemData>)` — the panel grew from four rows to eight |

Both calls succeeded and both changes were visible in a screenshot. **The four-slot panel is not a
fixed layout — it is a list, and the list takes more items.**

**Two caveats, and they matter:**

1. The four added rows rendered with the *player* row template — crown and controller icons, no
   name — rather than as `INVITE +`. Setting `FireteamRowType = 2` on the new item data was not
   enough, even though the three live `INVITE +` rows read `FireteamRowType = 2` and the player row
   reads `0`. So the entry widget is chosen by something other than that field alone; the likely
   candidate is a `GetDesiredEntryClassForItem` override on the Blueprint. **Unverified.**
2. This is presentation only. Adding a row does not create a player slot anywhere below the UI, and
   the view model's `TotalPlayerCount` was untouched by it. A panel that shows eight slots while the
   session seats four is a worse bug than a panel that shows four.

**A warning for whoever picks this up.** Three game crashes came out of probing this widget live,
all `EXCEPTION_ACCESS_VIOLATION`:

- `FindFirstOf("WBP_SquadWidget_C")` returns the **class-default archetype**, whose sub-widget
  pointers are null. Calling any method on `archetype.FireteamHeader` reads address `0x10` and takes
  the process down. Filter `FindAllOf` results to full names containing `/Engine/Transient` to get
  the live instance, and guard every member with `:IsValid()` before calling into it.
- `UEnum` reflection (`NumEnums`, `GetNameStringByIndex`) crashes outright. Read enum values off
  live objects instead.

---

## What this adds up to

Raising the cap to eight is a real project, not a config edit, but it is **not** blocked by the
thing that would have killed it outright — the simulation's player table is 32 wide and the AI
scaling tables already describe six-plus parties.

The plausible order of work:

1. **Measure the refusal.** Run `MJOLNIRCoop8` with a second player and find which of the four
   layers says no first. Everything below is guesswork until this exists.
2. **If PlayFab refuses at four**, find whether `maxMemberCount` is client-supplied. If the title
   pins it, peer-to-peer/LAN co-op becomes the only viable target and matchmade co-op is out.
3. **If Unreal refuses**, the cvar and property raises in this mod are probably already enough.
4. **If the simulation refuses**, locate the campaign policy comparison against 4 and confirm which
   fixed-size arrays are sized by `k_maximum_campaign_players`. Appearance customization is
   cosmetic; replication and respawn-zone tables are not.
5. **Every peer must run the identical patch.** The simulation is lockstep — `network_coop_oos_alert`
   exists — so a mismatched player count between peers desynchronises rather than degrading.

**Honest position:** steps 1–3 are ordinary modding. Step 4 is native reverse engineering against a
14.6 MB stripped DLL that reshuffles every content update, and step 5 means the result only works
between consenting modded clients. Nobody should expect this to work with matchmade strangers.

**The UI is deliberately not on that list.** The fireteam panel extends to eight slots today, and it
would be easy to ship that and call it progress. It would be the wrong thing to ship: showing eight
slots changes nothing about how many players the session seats, and a lobby that displays a
capacity it does not have is worse than one that displays the truth. Extend the panel when the
layers underneath it can fill it.

---

## Reproduction

Static analysis is read-only; no game content is copied into the repository. The runtime figures
came from `MJOLNIRCoop8` and the `tools/mcp/game` bridge against a live CU3 frontend.

Strings, including the error identifiers and the `coop_difficulty_block` field names:

```bash
python tools/pe/pe_strings.py "<Win64>/HaloSimulation_tag_release.dll" --match "coop|fireteam|max.{0,6}player"
```

Tag-block maxima, including the two headline numbers:

```bash
python tools/pe/pe_blocks.py "<Win64>/HaloSimulation_tag_release.dll" --pattern k_maximum --filter "player|coop"
```

`pe_blocks.py --xref <string>` dumps the qwords surrounding a data reference, which is how the
error-code table at `0x8376e8` and the config-variable tables were read.

The players array count came from disassembling the allocation site that passes the `"players"`
string literal — locate it with `--xref players`, then disassemble the enclosing function.

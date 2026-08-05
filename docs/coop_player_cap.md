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
`false` after every cap above was raised. It is gated on hardware, not on a limit — see below.

---

## Layer 3: PlayFab is the layer a mod cannot argue with

**Verified** present in the host: `PFLobbyGetMaxMemberCount`, `LobbyCurrentPlayersMoreThanMaxPlayers`,
`LobbyPlayerMaxLobbyLimitExceeded`, `MaxMembers`, `MaxPartySize`.

Lobby membership is validated by the PlayFab service, not by the client. If the lobby is created
with `maxMemberCount = 4`, the fifth join is refused server-side no matter what the client believes.

### The client supplies `maxMemberCount`

**Verified by disassembly**, and it is the answer to the question this section used to leave open.

The Blueprint hooks do not help: `MJOLNIRCoop8` registers
`/Script/PlayFab.PlayFabMultiplayerAPI:CreateLobby` and it never fires, through the co-op menu and
into campaign selection. Those reflected wrappers exist but this flow does not use them — the host
calls the native SDK directly.

The exe imports `PFMultiplayerCreateAndJoinLobby` from `PlayFabMultiplayerWin.dll` (IAT
`0x14a8b3630`) and calls it from exactly **one** site, `0x146f3f74e`. The third argument is the
`PFLobbyCreateConfiguration`, whose first field is `maxMemberCount`. That struct is built at
`0x146f3ec8f`:

```asm
146f3ec84  call  0x14691b9a0              ; keyed lookup, 0x38-byte elements
146f3ec89  mov   eax, [rbp + 0x238]       ; field +0x8 of the result
146f3ec8f  mov   [rbp + 0x110], eax       ; -> maxMemberCount
146f3ec95  mov   [rbp + 0x114], 2         ; ownerMigrationPolicy, a literal
146f3ec9f  mov   [rbp + 0x118], 2         ; accessPolicy, a literal
```

**The size is not a literal.** The two policy fields beside it are, which makes the contrast
concrete: `maxMemberCount` alone is fetched, from a struct field behind a hash lookup. So the client
decides the lobby size and tells the service — it is not handed down by the title configuration at
this point in the flow.

**What that does and does not mean.** It means the number is client-side data, so a mod that finds
that data can change what gets requested. It does **not** mean PlayFab will honour it: the service
validates the request against title limits, and whether an eight-member lobby is accepted is still
**Unverified**. It also does not help unless every peer agrees.

**Not yet found:** where the looked-up table lives. It is keyed data with `0x38`-byte entries, likely
a settings asset rather than a hardcoded array. Locating it is the next concrete step on this layer,
and it is static-analysis work — no second machine required.

---

## Layer 2: the squad UI counts its own rows

**Verified** reflected surface on `UMeteoriteSquadLobbyViewModel`:

```
TotalPlayerCount        GetNumSquadMembers      CanAddSplitscreenPlayer
bOfferJoinSlots         EMeteoriteSquadLobbyRowType::{Player, SplitscreenPrompt, Blank, Num}
```

The lobby is a row list with explicit blank rows, so the visible four slots come from a count the
widget is given.

### `CanAddSplitscreenPlayer` counts input devices, not slots

This is the one that returned `false` no matter which cap was raised, so it looked like a second
hidden limit. It is not a limit at all.

**Verified by disassembly.** The exec thunk is registered in the class's native function table at
`0xc1a86e0`, next to `CheckIsOffline`, `GetNumSquadMembers` and — the useful neighbour —
`HandleInputDeviceConnectionChange`. The thunk at `0x147c4f480` tail-calls the implementation at
`0x147c8ac90`, which runs in two phases:

1. Reaches an object through `GameInstance + 0x1d8 -> +0x30 -> +0x200`, returning **false** if
   either pointer is null, then compares two small containers by count and, when the counts match
   and exceed one, by first element.
2. Calls a lazy singleton (`0x1439d2f10`, a 0x78-byte object built on first use), invokes
   `[vtbl+0x18]` to fill an array of 4-byte IDs, then per entry calls `[vtbl+0x58]` to map that ID
   to another 4-byte value, appending to a result array **only when a linear scan finds no match**.

That last step is a distinct-value count, and the binary exposes exactly the API it fits:
`GetAllInputDevices`, `GetAllConnectedInputDevices`, `GetAllInputDevicesForUser`,
`GetInputDeviceConnectionState`, `EInputDeviceConnectionState`, `FInputDeviceId` and
`FPlatformUserId` — the last two being int32 wrappers, which is why the arrays step by four.

**Observed:** the function counts how many distinct platform users the connected input devices imply,
and refuses when there is no spare device to hand to a guest. The host machine had **no gamepad
attached** when this was measured — `Get-PnpDevice` showed only generic HID system controllers — so
one device meant one user meant `false`.

### …and it does not gate local players at all

**Verified in the running game**, and it makes the controller question moot. `CanAddSplitscreenPlayer`
governs the UI's *offer* to add a guest. It does not govern whether a second local player can exist:

```
UGameplayStatics::CreatePlayer(world, 1, true)  ->  ok, LocalPlayers 1 -> 2
```

No controller was attached. The squad panel updated itself to **FIRETEAM 2/4** with a real second
member row, and the view model's `TotalPlayerCount` went to `2` on its own. `CanAddSplitscreenPlayer`
stayed `false` throughout — so it is advisory, and the engine will seat the player regardless.

That also retires the idea of hand-building rows: the panel is data-driven and populates itself the
moment a real local player exists. Faking list entries was solving the wrong problem.

### Local players stop at four, and it is Unreal's enum

**Verified.** With every cap already raised (`MaxSplitscreenPlayers` 4 → 8,
`MaxSplitscreensPerConnection` 2 → 8, logged earlier in the same session), repeated `CreatePlayer`
calls gave:

```
CreatePlayer(id=2): ok  LocalPlayers 2 -> 3
CreatePlayer(id=3): ok  LocalPlayers 3 -> 4
CreatePlayer(id=4): process died
```

Four local players work. The fifth is an `EXCEPTION_ACCESS_VIOLATION`.

**Observed** cause: the shipping binary's `ESplitScreenType` enumerates
`None`, `TwoPlayer_Horizontal`, `TwoPlayer_Vertical`, `ThreePlayer_{FavorTop,FavorBottom,Horizontal,Vertical}`
and `FourPlayer_{Grid,Horizontal,Vertical}` — and stops. There is no five-player layout, so a fifth
viewport has no entry to index. This is stock Unreal, not a Meteorite choice, which is why raising
`MaxSplitscreenPlayers` to 8 changed nothing: the property is a bound, and the layout table behind
it only describes four.

### What that means for eight

Better than it first sounds. The route was never "eight players on one screen" — it is **four
connections carrying two local players each**, and two-per-machine sits comfortably inside a limit
that demonstrably reaches four. PlayFab's connection cap does not have to be beaten for that;
it already allows the four connections the plan needs.

So the open questions narrow to two, and neither is the splitscreen layout:

- Does the game let a host bring splitscreen guests into a *network* co-op session?
- Does the simulation seat eight players across four connections?

Both need a second machine. Neither needs a controller, and neither needs new splitscreen layouts.

### The FIRETEAM 1/4 panel can be extended at runtime

**Verified on the CU3 main menu**, on screen, not inferred. The live widget is
`WBP_SquadWidget_C` under `WBP_MeteoriteUILayout_C`, and the two members that matter are:

| Member | Type | Result |
|:--|:--|:--|
| `FireteamHeader` | `HaloUITextBlock` | `SetText` works, but **does not hold** on its own |
| `SquadListView` | `HaloUIListView` | `AddItem` adds rows, which also **do not hold** on their own |

### The header: works, with a catch worth knowing

A single `SetText(FText("FIRETEAM 1/8"))` succeeds, renders, and reverts within about a second when
the widget re-applies its own binding. That window is long enough to screenshot and believe it
worked, which is exactly what happened the first time this was tried.

Re-applying on a 500 ms interval makes it stick. `mjolnir_coop8_ui <n>` does that and holds through
menu animation and idle; `mjolnir_coop8_ui 0` releases it, after which the label reverts at the
widget's next refresh rather than immediately.

### The rows: they work, and they need re-asserting too

Constructing `MeteoriteSquadLobbyViewItemData` objects and calling `AddItem` renders the extra
slots. `mjolnir_coop8_ui 8` does this, and the panel holds at eight rows across repeated menu
transitions and idle.

**A correction, because the first write-up of this was wrong.** Early attempts crashed, and that was
attributed to garbage collection — the theory being that nothing rooted an object built by
`StaticConstructObject`. That theory does not hold: `UListView::ListItems` is a `UPROPERTY`, so items
handed to `AddItem` *are* traced. The crashes are better explained by the two hazards below, both of
which were being tripped in the same sessions. Adding rows on its own has since run clean across
many rebuilds.

Two things that are easy to get wrong:

1. **Count with `GetNumItems`, not by counting row widgets.** Discarded row widgets stay alive and
   findable after the panel rebuilds, so a `FindAllOf` tally read `8` while the list actually held
   `4`. A top-up loop using that tally concludes it has nothing to do, and the rows silently stay
   gone after the first menu transition. `GetNumItems` reported `4` correctly.
2. **Neither the label nor the rows survive a rebuild.** Leaving the menu and coming back is enough
   to reset both. The loop re-asserts them every 500 ms, only ever appending the shortfall, so the
   panel settles at the target instead of growing.

Known cost: each rebuild leaves the previous batch of item objects behind for the collector — 44
were alive after a handful of transitions. They are small and unreferenced, but it is a real
churn rather than a free effect.

### Making the rows read `INVITE +`

The added rows first came out wearing the player template — crown and controller icons, no name.
`FireteamRowType` was the obvious suspect and it was the wrong one, twice: setting it to `2` did
nothing, and appending one row of *each* value produced four identical player-chrome rows.

**Verified.** The row's look comes from the list's `EntryWidgetClass`, which defaults to the player
template:

```
ListView.EntryWidgetClass  = WBP_SquadPlayerListViewItem_C
vm.PlayerWidgetClass       = WBP_SquadPlayerListViewItem_C
vm.BlankWidgetClass        = WBP_SquadBlankListViewItem_C
vm.SplitscreenWidgetClass  = WBP_SquadBlankListViewItem_C
```

The view model carries three widget classes precisely so the panel can swap `EntryWidgetClass` as it
populates. Doing the same — pointing it at `BlankWidgetClass` before appending — makes the rows
render as `INVITE +`, matching the game's own. Leaving it pointed there is safe: the panel sets the
class itself as it repopulates, so the real player row still comes back correctly after a rebuild,
confirmed across menu transitions.

Still open: each rebuild leaves the previous batch of item objects for the collector. Routing through
the view model's `SquadMembers` array rather than the ListView would likely remove that churn.

And the reason this stays cosmetic: adding a row does not create a player slot anywhere below the
UI. `TotalPlayerCount` stays at `1`. A real second local player — see below — makes the panel
populate a genuine row on its own, with none of this.

**A warning for whoever picks this up.** Three game crashes came out of probing this widget live,
all `EXCEPTION_ACCESS_VIOLATION`:

- `FindFirstOf("WBP_SquadWidget_C")` returns the **class-default archetype**, whose sub-widget
  pointers are null. Calling any method on `archetype.FireteamHeader` reads address `0x10` and takes
  the process down. Filter `FindAllOf` results to full names containing `/Engine/Transient` to get
  the live instance, and guard every member with `:IsValid()` before calling into it.
- `UEnum` reflection (`NumEnums`, `GetNameStringByIndex`) crashes outright. Read enum values off
  live objects instead.
- **TArray-returning reflected functions crash**, consistently: `GetListItems`,
  `GetDisplayedEntryWidgets` and `UInputDeviceLibrary::GetAllInputDevices` all took the process
  down or failed outright. Scalar-returning ones such as `GetNumItems` are fine, which is usually
  enough — prefer them, and derive the rest from live object scans.

---

## What this adds up to

Raising the cap to eight is a real project, not a config edit, but it is **not** blocked by the
thing that would have killed it outright — the simulation's player table is 32 wide and the AI
scaling tables already describe six-plus parties.

The plausible order of work:

1. **Take two local players into a network co-op session.** `CreatePlayer` already seats a second
   local player with no controller attached, and four work locally, so the four-connections-times-two
   route needs only that the host may bring a guest into a session. No hardware required.
2. **Measure the network refusal.** Run `MJOLNIRCoop8` with a second player and find which of the
   four layers says no first. Everything below is guesswork until this exists.
3. **Find the table behind `maxMemberCount`.** It is already established that the client supplies
   the number rather than the title pinning it, so the remaining work is locating the keyed data it
   reads (0x38-byte entries, fetched at `0x14691b9a0`) and changing what gets requested. Static
   analysis; no second machine needed.
4. **If Unreal refuses**, the cvar and property raises in this mod are probably already enough.
5. **If the simulation refuses**, locate the campaign policy comparison against 4 and confirm which
   fixed-size arrays are sized by `k_maximum_campaign_players`. Appearance customization is
   cosmetic; replication and respawn-zone tables are not.
6. **Every peer must run the identical patch.** The simulation is lockstep — `network_coop_oos_alert`
   exists — so a mismatched player count between peers desynchronises rather than degrading.

**Honest position:** steps 1–4 are ordinary modding. Step 5 is native reverse engineering against a
14.6 MB stripped DLL that reshuffles every content update, and step 6 means the result only works
between consenting modded clients. Nobody should expect this to work with matchmade strangers.

**The UI is not on that list.** `mjolnir_coop8_ui 8` shows eight slots and holds them, and it is
opt-in for a reason: the slots are cosmetic. They add no player capacity anywhere below the UI, and
the module says so every time it runs. Treat the panel as a display, not as evidence — a lobby
showing a capacity the session does not have is worse than one showing the truth.

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

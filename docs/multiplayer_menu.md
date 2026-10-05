# The multiplayer menu (MJOLNIRLobby)

**Status:** 2026-10-01. MULTIPLAYER on the main menu opens MJOLNIR's own lobby
and map select screens ("Our own screens" below). Verified in game on CU4:
- CHANGE MAP, picking Danger Canyon and Capture the Flag, SELECT, GAME TYPE
  and Back all worked.
- START GAME started Danger Canyon under the Megalo engine, with the
  multiplayer HUD up.

Earlier, the campaign-menu screens (now the fallback) started Gephyrophobia
the same way, and the campaign save stayed byte for byte the same. Finding
and joining other players' games is not built yet.

Code: `mods/MJOLNIRLobby` (Lua) and `native/lobby` (its native half,
`mjolnir_lobby.dll`).

## How a map has to start

Only the campaign menu's own Start Game starts the simulation. A bare
`BlamCampaignFlowGameSubsystem:SetAndBeginCampaign` from script returns true
and loads the Unreal world, but the simulation never starts a game:
`(list_count (players))` stays 0 and the pawn waits at the world origin,
under the map. That is true for shipped missions as well
([new_scenario_loading.md](new_scenario_loading.md)).

The difference is the `BlamScenarioGameOptions` struct:

| field | scripted start | Start Game |
|---|---|---|
| `GameVariant` | none | a `BlamGameEngineCampaignVariant` built by `BP_FrontendGameState` |
| `bFriendlyFireEnabled` | false | true |
| `SaveSlot`, `bLoadFromCoreSave` | 0, false | 0, false |

The simulation's load-map event needs a campaign variant.

The skulls screen's Start Game goes through `BPFL_CampaignMenuHelpers`:
`SetClientLobbySkulls`, then `StartCountdown(CampaignSetup)`. The countdown
is the co-op lobby's countdown, which every fireteam member sees. When it
ends, `LaunchCampaign` builds the options and calls `SetAndBeginCampaign`.

The setup is a `BP_CampaignSetupParameters` held by the frontend player
controller:

- `Mode`
- `CampaignDataAsset`
- `ScenarioRow`
- `Difficulty`
- `InsertionPoint`
- `Skulls`
- `GameVariant`
- `FriendlyFireEnabled`

`SetCampaignMode(pc, 0)` gives a fresh setup for the campaign. The `Selected*`
helpers fill it in; `SelectedMission` copies the `DT_Scenarios` row. None of
them pushes a screen.

START GAME does the same:

1. `SetCampaignMode`
2. `GetCampaignSetup`
3. `SelectedMission`, `SelectedDifficulty`, `SelectedInsertionPoint`
4. `SetClientLobbyMission` and `SetClientLobbyDifficulty`
5. `StartCountdown`

The countdown brings the campaign's Mission Select up behind it.

The game type travels to MJOLNIRLevelLoader as `pending_variant.txt` beside
it. The loader reads it once, when the map starts, and stages
`variants/<mode>.mglo` in place of the level's default `variant`.

**The campaign save.** The campaign menu warns that a New Game overwrites the
save. A multiplayer map never writes it, because it makes no campaign
checkpoints. `CoreSave_0/1.sav` and `Progress.sav` were compared against a
backup after a launch, after spawning and play, and after quitting: all
three unchanged. The menu therefore skips that popup.

## Our own screens

`WBP_MJOLNIRLobby` and `WBP_MJOLNIRMapSelect` are MJOLNIR's own Widget
Blueprints, cooked into `pakchunk984-MJOLNIRUI`
(`unreal/MJOLNIRMaterials/Scripts/build_mjolnir_ui.py`,
[custom_ui.md](custom_ui.md)). They derive from `CommonActivatableWidget`, so
`ContentStack:BP_AddWidget` pushes them like any shipped screen: the stack
hides the main menu beneath, and Back (Escape, B) pops them
(`bIsBackHandler`).

- **The lobby:** the map and game type, a description of each, the players
  (the frontend's player states), and START GAME, INVITE FRIENDS, CHANGE
  MAP, GAME TYPE (cycles the map's modes), PRIVATE / PUBLIC GAME, MAX
  PLAYERS (2 to 16, host only;
  [fireteam_join_and_cap.md](fireteam_join_and_cap.md)), FIND GAMES and BACK.
  - Team modes (CTF and Team Slayer) show separate Red/Blue roster sections.
    These reflect the game's team assignments, with an Awaiting assignment
    section when the frontend has no simulation team yet. No local team
    choices or fabricated alternating assignments are written to the game.
    Free-for-all uses one list. The roster supports up to 16 players and
    scrolls without moving the surrounding controls.
  - INVITE FRIENDS opens the game's own Friends screen (`WBP_Roster_C`:
    Platform and Cross-Platform friends, each with + Invite). It does this by
    calling `BP_OnClicked` on one of the fireteam panel's INVITE + rows
    (`WBP_SquadBlankListViewItem_C`). Those rows belong to the UI layout's
    squad widget, alive under every screen. Back returns to the lobby.
  - That screen also shows START CAMPAIGN, which starts the campaign, not
    the lobby's map. The last game hosted is remembered in
  `MJOLNIRLobby\last_game.txt`.
- **The map select:** every installed map in a scrolling list. Hovering a
  map previews its details and game types; clicking picks it. A game type
  button picks the mode, and SELECT returns to the lobby with both.

Each button's own graph calls the widget's `MJ_Event(<event>)`: `start`,
`changemap`, `gametype`, `back`, `select`, `map:<i>`, `hover:<i>`,
`mode:<i>`. Lua hooks it and handles the event off the click, in
`ExecuteInGameThread`. No native delegate binding is involved. Only the
injected fallback MULTIPLAYER button still needs it (next section).

Without the UI container, MULTIPLAYER falls back to the campaign-menu
screens described next.

The custom screens use a 2560×1440 design canvas fitted as a whole to the
viewport, keeping columns together at lower resolutions and ultrawide
aspect ratios. Flat translucent navy panels, fine cyan rules, regular
weight type and gold primary actions share the scoreboard's visual style.
The game's animated background and CommonUI menu stack remain in use.

## The main menu's own MULTIPLAYER button

Verified on CU4, 2026-10-02. MULTIPLAYER is a real button of `WBP_MainMenu`,
cooked into the menu's package:
- It sits after the hidden Remix button, between CAMPAIGN and PLAY CO-OP.
- It is there the first time the menu shows.
- It has the menu's own styling, focus, keyboard and gamepad navigation, and
  Back.
- Its click pushes `WBP_MJOLNIRLobby` itself, through the call the menu uses
  for Customization (`HaloUIManagerSubsystem.PushStreamableContentToLayerFullscreen`).
- Remix keeps its slot, its click and its unlock rule.

Lua only fills the lobby once it exists (`NotifyOnNewObject` on the lobby
class) and handles its events, as above.

```bash
mjolnir ue menu-button --out-dir <dir>      # writes pakchunk985-MJOLNIRMENU_P
```

`tools/level/build_ce_runtime.sh` builds it into the CE runtime pack, beside
the lobby's own container (chunk 984). The defaults are the main menu,
`MultiplayerButton`, "MULTIPLAYER", after `RemixButton`, opening
`/Game/MJOLNIR/UI/WBP_MJOLNIRLobby.WBP_MJOLNIRLobby_C`.
`ue_asset::menu_button` does the work, and finds everything by name.

**What a new button takes** (all in the one package):

| | added | copied from |
|---|---|---|
| the button | a new export in the widget tree, its label changed from the string table entry `Menus/main_item_remixmenu` to the text "MULTIPLAYER" | `RemixButton` |
| its slot | a new `HaloUIButtonContainerSlot` export, listed in `MainButtonContainer.Slots` right after Remix's | Remix's slot |
| the click function | a new `BndEvt__…MultiplayerButton…` export, added to the class's Children and FuncMap; it enters the ubergraph at the new block | Remix's click stub |
| the binding | a `ComponentDelegateBindings` row: `MultiplayerButton.OnButtonBaseClicked` → that function | Remix's row |
| the variable | an `ObjectProperty` named `MultiplayerButton`, last among the class's own properties | `RemixButton`'s |
| the push | a block before the ubergraph's `EX_EndOfScript`: player controller, push, pop | the Customization push |

New exports go at the end of the export map, and the block at the end of
the ubergraph, so no package index, jump or entry point moves. Each new
export gets a dependency bundle like its template's. Its create and
serialize commands sit beside the template's in the export bundle.

**The class default object has to move too.** An unversioned property
header numbers a class's own properties first and its supers' after them.
The new variable is own slot 35, so every inherited value of
`Default__WBP_MainMenu_C` moves up one slot: its header's skip before slot 87
goes from 53 to 54. Without that the CDO reads garbage, and the game
crashed as the frontend built the menu.

**Rebuild after every game update.** The container replaces the whole
`WBP_MainMenu` package. A stale copy would hide the updated menu, so the
runtime pack has to be rebuilt from the new build. The command refuses when
something it looks for is gone, rather than guessing.

**Without the container** (an older runtime pack), the main menu has no
`MultiplayerButton`, and MJOLNIRLobby falls back to injecting its own button
into Remix's slot (next section). The log says which one is in use:
`MULTIPLAYER is on the main menu (its own button)`, or `... (injected: ...)`.

`mjolnir ue disasm --package <pkg> --export <name|index>` prints a
Blueprint function's bytecode (`ue_asset::kismet`). That's how the Remix
gate (`UpdateButtonsEnabled`: `IsRemixMenuUnlocked`) and the pushes were
found.

## Screens from the game's widgets (fallback)

A screen is a `WBP_CampaignMenu_C` (header, sub-header, a
`HaloUIButtonContainer`, a description and the fireteam panel) pushed with
`WBP_MeteoriteUILayout_C.ContentStack:BP_AddWidget`. Its own buttons are
swapped for ours. Buttons are `WBP_MeteoriteStandaloneButtonDefault_C`, the
main menu's kind.

- **Use the container's own slots.** Put a button into one with
  `ReplaceButtonContainerChildAt`. That keeps the button group consistent.
  Appending after hidden native buttons left the group's selection on a
  hidden button, and CommonUI routes Enter through the selected button.
- **Labels.** Set a label after the button is in the tree. A label set before
  construction is lost.
- **Repeat clicks.** `bInteractableWhenSelected = true`. Otherwise a clicked
  button is selected and ignores the next press.
- **Re-activation.** The campaign menu's activation resets its own buttons
  and texts, so `BP_OnActivated` re-applies the screen.
- **Main menu entry.** Without pakchunk985-MJOLNIRMENU, the injected
  MULTIPLAYER takes the slot of the hidden Remix button. A light poll puts
  it back on each new main menu.
- **Loading classes.** UE4SS's `LoadAsset` needs the asset's object path
  (`/Game/.../WBP_CampaignMenu.WBP_CampaignMenu`). Neither the bare package
  nor the `_C` class path works. The frontend loads most screen classes only
  when they are first opened.

### Clicks

A CommonUI button reports a click only through its `OnButtonBaseClicked`
dynamic delegate, and the path to it is native-to-native. Hooks on the
button's `BP_OnClicked`, `HandleButtonClicked` or `BP_OnPressed` never fire
for a Blueprint that does not implement them. UE4SS's Lua cannot bind a
delegate either: the property comes back as an opaque object.

UE4SS.dll exports what binding needs:

- `UObject::GetPropertyByNameInChain`. The plain `GetPropertyByName` sees
  only the Blueprint class's own properties.
- The `FWeakObjectPtr` and `FName` constructors.
- `FMulticastDelegateProperty::AddDelegate`, the engine's own add.

So `mjolnir_lobby_bind` binds each button's delegate to a clicker. The
clicker is a hidden `WBP_MeteoriteHyperlink_C` whose Blueprint function
`SetHyperlinkText` takes no parameters and only sets its own text. The
Lua hook on that function is the click.

The clicker is parked, collapsed, in the button's `LeafNamedSlot`, so it
lives exactly as long as the button. It is armed 300 ms after creation,
because construction calls `SetHyperlinkText` too. Lua has no C API here
(UE4SS does not export it), so requests and replies travel as
`native/lobby_request.txt` and `lobby_reply.txt`.

**Hook only Blueprint-scripted functions.** A hook on
`HaloUIButtonContainer:HandleButtonGroupSelectionChanged` (native, with
parameters) crashed the game inside UE4SS's argument marshalling.

## Maps and modes

`mjolnir level bake --install-test` writes `MJOLNIRLevelLoader/maps.json`
(Lua cannot list a directory). Each entry has:

- `code`
- `title`
- `description`
- `modes`: the level file's `modes`, else its `variant`

`tools/level/gen_ce_level.py` names the stock maps (`STOCK_TITLES`) and lists
`"modes": ["slayer"]`. A mode is offered when the map lists it and
`variants/<mode>.mglo` is installed.

## Next

- **A lobby service of our own** (Cloudflare, beside the hub), since Game Pass
  and Store players have no Steam. Planned shape: a game list, join codes, the
  member list and chat, as a D1-backed polled API first. Live chat may move to
  a Durable Object. The open question is the hand-off: how a client joins the
  host's PlayFab session.
- **Steam lobbies**, for Steam players only. Steam is live in the process
  (`steam_api64` v1.57), and its flat API can be called from the native half.
  Pieces:
  - FIND GAMES: a lobby list.
  - JOIN PRIVATE: friends-only and invite lobbies.
  - The friends list's Join Game: `GameLobbyJoinRequested`, `+connect_lobby`.
  - Bringing lobby members into the host's fireteam session.
- **Discord** rich presence over its local IPC pipe.
- Two-player verification of the session join and of Megalo kill scoring.

# The multiplayer menu (MJOLNIRLobby)

**Status:** 2026-10-01; updated 2026-10-24. MULTIPLAYER on the main menu
opens MJOLNIR's own lobby, map select and game type screens ("Our own
screens" below). The lobby and map selection were verified in game on CU4:
- CHANGE MAP, picking Danger Canyon and Capture the Flag, SELECT, GAME TYPE
  and Back all worked.
- START GAME started Danger Canyon under the Megalo engine, with the
  multiplayer HUD up.

Earlier, the campaign-menu screens (now the fallback) started Gephyrophobia
the same way, and the campaign save stayed byte for byte the same. Finding
and joining other players' games was not built then. It shipped later:
PUBLIC GAME, FIND GAMES and joins by connection string in mods-v0.11.0
(PR #127), joins into a public match under way in mods-v0.12.0 (PR #130),
and FIND GAMES as a server browser in mods-v0.13.0 (PR #132)
([multiplayer_servers.md](multiplayer_servers.md)).

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

`WBP_MJOLNIRLobby`, `WBP_MJOLNIRMapSelect` and
`WBP_MJOLNIRGameTypeSelect` are MJOLNIR's own Widget Blueprints, cooked
into `pakchunk984-MJOLNIRUI`
(`unreal/MJOLNIRMaterials/Scripts/build_mjolnir_ui.py`,
[custom_ui.md](custom_ui.md)). They derive from `CommonActivatableWidget`, so
`ContentStack:BP_AddWidget` pushes them like any shipped screen: the stack
hides the main menu beneath, and Back (Escape, B) pops them
(`bIsBackHandler`).

- **The lobby:** the players (the frontend's player states), START GAME,
  INVITE FRIENDS, CHANGE MAP, GAME TYPE (opens the current map's mode
  picker), GAME SETTINGS (host only, since mods-v0.16.0;
  [host_game_settings.md](host_game_settings.md)), PRIVATE / PUBLIC GAME,
  MAX PLAYERS (2 to 16, host only;
  [fireteam_join_and_cap.md](fireteam_join_and_cap.md)), FIND GAMES and BACK,
  and a card with what the game will be. Since mods-v0.39.0 (with CE
  runtime 1.16.0's UI container) the card is two tiles, the map (its
  screenshot, name, game and players) and the game type (its icon, name and
  format), over the game settings away from the defaults in two columns of
  at most five lines, the last saying how many more. The tiles and the
  settings are buttons for the host, with the events of CHANGE MAP, GAME
  TYPE and GAME SETTINGS; a fireteam client's are HitTestInvisible. An older
  UI container keeps the one-column card with each part's description.
  A fireteam client without the host's map, or with another release of it,
  sees START GAME as DOWNLOAD MAP or UPDATE MAP (since mods-v0.20.0;
  [live_map_install.md](live_map_install.md)).
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
- **The map select:** up to 80 maps in a scrolling list: every installed
  map, then the hub's maps this PC does not have, marked DOWNLOAD
  (`MapLive.listings`, the cached `GET /maps`). Chips above it narrow the
  list by game (the hub's `game`: Halo CE or Halo 2), by source (official
  or community) and to installed maps; a map the hub does not list passes
  only the ALL choices. Hovering a map previews its details and game types,
  and leaving it shows the chosen map again; clicking picks it. A game type
  picks the mode, and SELECT returns to the lobby with both, or, for a map
  not installed, opens the download screen and picks the map once it is in.
  Since mods-v0.39.0 (CE runtime 1.16.0's UI container):
  - A search box over the list has the focus when the screen opens. Every
    word typed must be in a map's title, code or game's names ("ce", "halo
    2"); the best matches come first (a word starting the title, then one
    starting a word of it) and the best is picked as you type, so ENTER
    selects it (`Pick.score`). Only ENTER leaves the box focused when it
    commits, which tells it from the focus moving away. CLEAR empties it.
  - Rows are sorted by title and show the map's game (CE or H2) and DOWNLOAD
    or CURRENT (the map the lobby has). A second click on the same row within
    half a second selects it.
  - The details panel has a fixed size, with SELECT and BACK at its foot:
    the screenshot, the title, the hub listing's facts (game, size, players,
    vehicles) and summary, the author line, and the game types as a row of
    icon tiles. Hovering a tile describes its mode beside the row.
- **The game type select:** the host's current map and its available modes,
  with an icon, description and match format for each. The current mode is
  marked CURRENT and focused when the screen opens. Hover previews a mode;
  clicking chooses a pending mode. SELECT saves that choice and updates the
  lobby; BACK, Escape or controller B leaves the hosted game unchanged.
  Availability uses the same map support, installed variant and required
  runtime checks as map selection. Team Slayer is supported wherever Slayer
  is, and Forge appears when its editor and runtime are installed. Six rows
  accommodate all five multiplayer modes plus Forge. Before confirming,
  `Scripts/gametype.lua` rechecks host authority, the map and mode availability.
  An older UI container without this screen opens the existing map picker
  on the current map instead.

The game type icons are original geometric glyphs generated by
`tools/ue/draw_gametype_icons.py`, using Pillow. They contain no extracted
Halo or MCC artwork. Run `python tools/ue/draw_gametype_icons.py` to rebuild
the six transparent 256-pixel PNGs in
`unreal/MJOLNIRMaterials/Art/GameTypeIcons`; add `--sheet out/gametype-icons.png`
for a preview sheet. The UI builder imports them as `T_MJMode_<Name>` under
`/Game/MJOLNIR/UI/ModeIcons` and cooks them with the screen in chunk 984.
The lobby shows the selected mode's same icon beside its game type title,
including when following the host's choice as a fireteam client. Missing
icon textures hide the lobby emblem and do not prevent mode selection.

Each button's own graph calls the widget's `MJ_Event(<event>)`: `start`,
`invite`, `changemap`, `gametype`, `gamesettings`, `listing`, `maxdown`,
`maxup`, `maxplayers`, `findgames`, `back`, `select`, `map:<i>`,
`hover:<i>`, `unhover:<i>`, `mode:<i>`, `filter:game`, `filter:source`, `filter:installed` (FIND GAMES and GAME SETTINGS send their own, such
as `game:<i>`, `sort:<column>` and `reset`). Lua hooks it and handles the
event off the click, in `ExecuteInGameThread`. No native delegate binding is involved. Only the
injected fallback MULTIPLAYER button still needs it (next section).
Game type events compare the sender's native UObject address with the
active screen, so delayed events from a previous picker cannot change the
new choice. `tools/tests/test_gametype_picker.lua` covers this and the
selection, cancellation, availability and older-container behavior.

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

The lobby reads the launcher's `MJOLNIRMaps\maps.json`, rebuilt from every
installed map (`crates/blam-pack/src/maps.rs`). For codes that list lacks, it
reads `MJOLNIRLevelLoader/maps.json`, which `mjolnir level bake
--install-test` writes (Lua cannot list a directory). Each entry has:

- `code`
- `title`
- `description`
- `modes`: the level file's `modes`, else its `variant`

`tools/level/gen_ce_level.py` names the stock maps (`STOCK_TITLES`) and lists
`"modes": ["slayer"]`, plus `"ctf"` when the map has a flag for each team.
A mode is offered when the map lists it and `variants/<mode>.mglo` is
installed.

## Next

**Update 2026-10-21:** the lobby service is built on the hub, as a D1-backed
polled API (`hub/src/lib/api/lobby.ts`, PR #106). The hand-off is the PlayFab
lobby's connection string, given to the game's own Steam join handler
(mods-v0.11.0, PR #127; [multiplayer_servers.md](multiplayer_servers.md)),
and on the Xbox app to the GDK session's invite handler (mods-v0.23.0 and
v0.23.1, PR #179 and #181). FIND GAMES lists the hub's games, not Steam
lobbies. The session join was verified on two PCs on 2026-10-01 (03fae037).
Match chat shipped in the match HUD, not the lobby service (mods-v0.27.0,
PR #200). Discord Rich Presence and public-session Join Game are implemented
through local IPC ([discord_presence.md](discord_presence.md)). Still not
built: join codes (JOIN PRIVATE) and Steam lobbies.

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
- **Discord** rich presence over its local IPC pipe is implemented; see
  [setup and verification](discord_presence.md).
- Two-player verification of the session join and of Megalo kill scoring.

# The multiplayer menu (MJOLNIRLobby)

**Status:** 2026-10-01. MULTIPLAYER on the main menu, HOST GAME → map → game
type → lobby → START GAME, verified in game on CU4: Gephyrophobia started
under the Megalo engine with the Slayer variant, the player spawned, all 16
teleporter pads were present, and the campaign save stayed byte for byte the
same. FIND GAMES and JOIN PRIVATE (Steam lobbies) are not built yet.

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

## Screens from the game's widgets

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
- **Main menu entry.** MULTIPLAYER takes the slot of the hidden Remix button
  on the main menu.
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

- **Steam lobbies.** Steam is live in the process (`steam_api64` v1.57), and
  its flat API can be called from the native half. Pieces:
  - FIND GAMES: a lobby list.
  - JOIN PRIVATE: friends-only and invite lobbies.
  - The friends list's Join Game: `GameLobbyJoinRequested`, `+connect_lobby`.
  - Bringing lobby members into the host's fireteam session.
- **Discord** rich presence over its local IPC pipe.
- Two-player verification of the session join and of Megalo kill scoring.

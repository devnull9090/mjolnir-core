# Custom UI: our own Widget Blueprints in the game

MJOLNIR's screens (lobby, map select, chat, kill feed, scoreboard) can be real
Widget Blueprints, cooked in our Unreal project and loaded by the game from a
container of ours. They don't have to be buttons injected into the shipped
screens (`mods/MJOLNIRLobby`).

Proven 2026-10-01 with `WBP_MJOLNIRHello`:

1. The game loaded the cooked class from `pakchunk984-MJOLNIRUI-Windows`.
2. Lua created it, added it to the viewport and called its Blueprint function
   `SetMessage`.
3. A real mouse click on its button ran the widget's own `OnClicked` graph,
   which called `MJ_Event("hello_clicked")`.
4. A Lua `RegisterHook` on `MJ_Event` received the call.

No native delegate binding was needed for any of it.

## Why widgets cook when meshes and components don't

The game runs 343's fork of UE 5.5.4. Our project (`unreal/MJOLNIRMaterials`)
is stock UE 5.5. Cooked packages store properties unversioned, by position,
so a class whose property layout differs in the fork reads garbage. That is
why cooked scene components, static meshes and material instances fail
([ue_mesh_write.md](ue_mesh_write.md), [re/fork_renderer.md](re/fork_renderer.md)).

Comparing the fork's layouts (`defs/ue/Meteorite-2607-CU3.usmap`) with stock
headers, 2026-10-01:

- **Identical to stock:**
  - `Widget`, `UserWidget`, `WidgetTree`, `WidgetAnimation`, `WidgetBlueprintGeneratedClass`
  - `TextBlock`, `Button`, `EditableText`, `EditableTextBox`, `Image`, `Border`
  - `ScrollBox`, `ListView`, the box slots, `CanvasPanelSlot`
  - `CommonActivatableWidget`, `CommonUserWidget`
- **Different, so never cook them:**
  - `CommonButtonBase` (adds `bSetIsSelectedWhenClicked`)
  - `CommonTextBlock` (adds `TextScalingCategory`)
  - `SceneComponent` and `PrimitiveComponent`, so no components in a widget

Re-check after a game update: re-dump the `.usmap` with UE4SS and compare
again.

## Building a widget

The UI Builder plugin (`Plugins/MjolnirUIBuilder`, editor only) does what
Python can't:

- `create_widget_blueprint`
- `add_widget`: a tree widget made a variable, returned so Python can set its
  properties and slot.
- `add_string_function`: a function taking one String. It is empty (an event
  for Lua to hook) or sets a text block.
- `bind_event_to_function`: a widget's delegate, such as a Button's
  `OnClicked`, calls a function with a fixed argument.
- `compile_widget`

The graphs it places use only engine functions (`Conv_StringToText`,
`TextBlock.SetText`), so the cooked widget never references the plugin.

```powershell
# once, and after changing the plugin (a short -Package path: the default
# scratch path is past MAX_PATH)
& "C:\Program Files\Epic Games\UE_5.5\Engine\Build\BatchFiles\RunUAT.bat" BuildPlugin `
    -Plugin="$PWD\unreal\MJOLNIRMaterials\Plugins\MjolnirUIBuilder\MjolnirUIBuilder.uplugin" `
    -Package="C:\mjb\MjolnirUIBuilderBuild" -TargetPlatforms=Win64 -Rocket
Copy-Item C:\mjb\MjolnirUIBuilderBuild\Binaries unreal\MJOLNIRMaterials\Plugins\MjolnirUIBuilder -Recurse -Force

powershell -File tools/ue/editor_cmd.ps1 -Script Scripts/build_mjolnir_ui.py
powershell -File tools/ue/cook.ps1     # also writes pakchunk984-Windows
```

`PAL_MJOLNIR_UI` puts `/Game/MJOLNIR/UI` in chunk 984. Install the staged
`pakchunk984-Windows.{utoc,ucas,pak}` as `pakchunk984-MJOLNIRUI-Windows.*`.

Before installing, list the container:
`find_files <StagedBuilds Paks dir> MJOLNIR/UI EngineFonts`. It must hold our
widgets only. The engine assets a widget imports (Roboto) cook into chunk 0,
which we don't ship, so the import resolves to the game's own copy.

## Driving it from Lua

UE4SS's `LoadAsset` only finds what the game's asset registry lists. Load
through a soft class path instead:

```lua
local ksl = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
local cls = ksl:LoadClassAsset_Blocking(ksl:Conv_SoftClassPathToSoftClassRef(
    ksl:MakeSoftClassPath("/Game/MJOLNIR/UI/WBP_MJOLNIRHello.WBP_MJOLNIRHello_C")))
local wbl = StaticFindObject("/Script/UMG.Default__WidgetBlueprintLibrary")
local w = wbl:Create(pc, cls, pc)
w:AddToViewport(50)
w:SetMessage("hello")                       -- a Blueprint function, called with a Lua string
RegisterHook("/Game/MJOLNIR/UI/WBP_MJOLNIRHello.WBP_MJOLNIRHello_C:MJ_Event",
    function(self, name) print(name:get():ToString()) end)
w:SetVisibility(1)                          -- Collapsed; never RemoveFromParent (it hung the game once)
```

- Widgets are variables, so Lua reaches them by name (`w.Ok`, `w.Message`).
- `PlayerController:SetMouseLocation` places the cursor in viewport pixels
  (3840×2160 here), which is how the click was tested.

## Screens on the game's menu stack

A widget whose parent is `CommonActivatableWidget` (the project enables
CommonUI for it) can be pushed onto the game's own menu stack with
`WBP_MeteoriteUILayout_C.ContentStack:BP_AddWidget(cls)`. That gives it
everything a shipped screen has:
- the screen beneath is hidden;
- Back (Escape, the gamepad's B) pops it, with `bIsBackHandler` set on the
  class defaults (`finish_screen`);
- `DeactivateWidget()` pops it from Lua.

`WBP_MJOLNIRLobby` and `WBP_MJOLNIRMapSelect` work this way
([multiplayer_menu.md](multiplayer_menu.md)). Their buttons use stock
`Button` styling (tinted brushes): the game's own CommonUI buttons can't be
cooked.

## Next

- Text input for chat. `EditableTextBox.OnTextCommitted` goes through
  `bind_event_to_function`, extended to pass the text on. Keys come from UE4SS
  `RegisterKeyBind`. The sim reads input through GameInput, so typing may
  still move the player.
- `CommonActivatableWidget` as the parent, so a screen joins the game's menu
  stack and gets gamepad back handling.
- The game's fonts and styles, set on our widgets at runtime.

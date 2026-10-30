# Custom UI: our own Widget Blueprints in the game

MJOLNIR's screens (the lobby, map select, FIND GAMES, game settings,
post-game and map download screens, and the HUD's chat, kill feed and
scoreboard) are real Widget Blueprints, cooked in our Unreal project and
loaded by the game from a container of ours
(`unreal/MJOLNIRMaterials/Scripts/build_mjolnir_ui.py`). They don't have to
be buttons injected into the shipped screens; `mods/MJOLNIRLobby` falls back
to those only when our UI container is missing.

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
why a stock cook of scene components, static meshes or materials is misread
([ue_mesh_write.md](ue_mesh_write.md), [re/fork_renderer.md](re/fork_renderer.md)).
`tools/ue/cook.ps1` now re-encodes each staged container's materials (and,
with `-Classes`, other classes such as `StaticMesh`) in the game's layout by
property name (`mjolnir ue retarget --rewrite`, `crates/ue-asset/src/retarget.rs`).
The widget classes listed as identical below need none of it.

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

Re-checked 2026-10-17 against `defs/ue/UE-5.5-stock.usmap`, also identical:
`Overlay`/`OverlaySlot`, `SizeBox`/`SizeBoxSlot`, `ScaleBox`, `Spacer`,
`SlateBrush` with `SlateBrushOutlineSettings` (so rounded-box brushes cook),
`SlateFontInfo`, `WidgetTransform`, `Texture`/`Texture2D` (so our own UI
textures cook; the kill feed's glyphs are in chunk 984).

Re-check after a game update: re-dump the `.usmap` with UE4SS and compare
again.

## The game's assets from Lua

Our widgets can use the game's own pictures and fonts at runtime, without
copying them:

- A texture or material: `KismetSystemLibrary:LoadAsset_Blocking` on
  `Conv_SoftObjPathToSoftObjRef(MakeSoftObjectPath(path))`, then
  `Image:SetBrushFromTexture` or `SetBrushFromMaterial`. The HUD's weapon
  silhouettes are channel-packed masks, drawn through the game's own icon
  material: `SetBrushFromMaterial(MI_HUDCradleIcon_FragGrenade)`,
  `GetDynamicMaterial()`, `SetTextureParameterValue("InputTexture", tex)`.
  The image's colour multiplies the material's cyan; it cannot recolour it.
- A font: `/Game/Fonts/Font_Oxanium` (the menus' face) and
  `Font_NormativePro`, through `TextBlock:SetFont({ FontObject = font,
  TypefaceFontName = FName("Bold"), Size = block.Font.Size, ... })`.
  Oxanium has Light ... ExtraBold; Normative Pro Light, Regular, Medium,
  Bold and their italics.
- Keep what you find. `StaticFindObject` by path costs ~2 ms in UE4SS (19 ms
  the first call), so a lookup per use adds up: the kill feed's first build
  did half a dozen per line and held the game thread 50-80 ms on every kill
  (two PCs, 2026-10-17). Keep the handle, check it with `IsValid()` before
  each use (an object no engine object holds may be collected), and find it
  again only when that fails.

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

The MJOLNIR CORE emblem at the top right of every menu screen
(`screen_header`) is `Art/Brand/Logo.png`, made from the hub's own logo by
`python tools/ue/brand_logo.py` (cropped, centred, 256 pixels). It is
imported with mips, since 720p draws it at about a third of that. It sits
in `LogoButton`, whose click `finish_screen` binds to `MJ_Event("logo")` on
every menu screen.

The Forge HUD (`WBP_MJOLNIRForge`, [forge.md](forge.md)) is built by the same
script but lives in `/Game/MJOLNIR/ForgeUI` with its own glyphs
(`Art/ForgeIcons`, `T_MJForge_*`) and its own label, `PAL_MJOLNIR_ForgeUI`,
which puts it in chunk 980. It ships as `pakchunk980-MJOLNIRFORGEUI-Windows`
beside the CE runtime's monitor fix, without touching chunk 984.

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
- Text input: chat's `ChatInput` is an `EditableTextBox` that Lua focuses
  (`SetKeyboardFocus`); a UE4SS `RegisterKeyBind` on ENTER reads it with
  `GetText()`, so no delegate binding is needed. Keys the box does not use
  bubble up to the game viewport, which feeds the simulation, so while the
  box is open the game is in UI-only input (`SetInputMode_UIOnlyEx`;
  `mods/MJOLNIRHud/Scripts/chat.lua`).
- A delegate with parameters binds like `OnClicked`: the map select's
  search box sends `MJ_Event("search")` from `OnTextChanged` and
  `MJ_Event("searched")` from `OnTextCommitted` (`bind_event_to_function`
  drops the parameters), and Lua reads `GetText()`. On a menu screen the
  frontend has no simulation to feed, so the box needs no input mode of its
  own; Escape still pops the screen while it has focus.

## Screens on the game's menu stack

A widget whose parent is `CommonActivatableWidget` (the project enables
CommonUI for it) can be pushed onto the game's own menu stack with
`WBP_MeteoriteUILayout_C.ContentStack:BP_AddWidget(cls)`. That gives it
everything a shipped screen has:
- the screen beneath is hidden;
- Back (Escape, the gamepad's B) pops it, with `bIsBackHandler` set on the
  class defaults (`finish_screen`);
- `DeactivateWidget()` pops it from Lua.

`WBP_MJOLNIRLobby`, `WBP_MJOLNIRMapSelect`, `WBP_MJOLNIRFindGames`,
`WBP_MJOLNIRGameSettings`, `WBP_MJOLNIRPostGame` and
`WBP_MJOLNIRMapDownload` work this way
([multiplayer_menu.md](multiplayer_menu.md)). Their buttons use stock
`Button` styling (tinted brushes): the game's own CommonUI buttons can't be
cooked.

The main menu's MULTIPLAYER button is not one of ours: it is the shipped
`WBP_MainMenu` with a button added, rewritten into chunk 985
(`pakchunk985-MJOLNIRMENU_P`, `mjolnir ue menu-button`). MJOLNIRLobby injects
a button only when that container is missing.

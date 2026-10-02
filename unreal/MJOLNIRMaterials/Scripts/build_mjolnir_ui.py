"""Build MJOLNIR's own widgets: real Widget Blueprints the game loads from our
container, instead of buttons slipped into its shipped screens.

    powershell -File tools/ue/editor_cmd.ps1 -Script Scripts/build_mjolnir_ui.py

Writes, under /Game/MJOLNIR/UI:
  WBP_MJOLNIRHello   the first test: a message and an OK button.
                     SetMessage(Text) sets the message; clicking OK calls
                     MJ_Event("hello_clicked"), an empty function Lua hooks.
  PAL_MJOLNIR_UI     the label that puts the folder in chunk 984
                     (pakchunk984-MJOLNIRUI).

The widget tree and graph nodes come from the MjolnirUIBuilder editor plugin
(Python can create a Widget Blueprint but not edit either). Only stock UMG
classes are used: their property layouts match the game's fork, while
CommonUI's button and text classes, and every scene component, do not
(docs/custom_ui.md).
"""
import unreal

ROOT = "/Game/MJOLNIR/UI"
CHUNK = 984

ui = unreal.MjolnirUIBuilderLibrary
eal = unreal.EditorAssetLibrary
assets = unreal.AssetToolsHelpers.get_asset_tools()


def fail(why):
    unreal.log_error(f"MJOLNIR UI: {why}")
    raise RuntimeError(why)


def widget(bp, cls, name, parent=""):
    w = ui.add_widget(bp, cls, name, parent)
    if w is None:
        fail(f"could not add {name}")
    return w


def text_style(block, text, size, color=(1.0, 1.0, 1.0, 1.0)):
    block.set_editor_property("text", unreal.Text(text))
    font = block.get_editor_property("font")
    font.set_editor_property("size", size)
    block.set_editor_property("font", font)
    block.set_editor_property("color_and_opacity", unreal.SlateColor(unreal.LinearColor(*color)))


def build_hello():
    name = "WBP_MJOLNIRHello"
    if eal.does_asset_exist(f"{ROOT}/{name}"):
        eal.delete_asset(f"{ROOT}/{name}")
    bp = ui.create_widget_blueprint(ROOT, name)
    if bp is None:
        fail(f"could not create {name}")

    widget(bp, unreal.CanvasPanel, "Root")
    panel = widget(bp, unreal.Border, "Panel", "Root")
    panel.set_editor_property("brush_color", unreal.LinearColor(0.0, 0.02, 0.05, 0.75))
    panel.set_editor_property("padding", unreal.Margin(24, 16, 24, 16))
    slot = panel.get_editor_property("slot")
    slot.set_anchors(unreal.Anchors(minimum=unreal.Vector2D(0.5, 0.15), maximum=unreal.Vector2D(0.5, 0.15)))
    slot.set_alignment(unreal.Vector2D(0.5, 0.0))
    slot.set_auto_size(True)

    widget(bp, unreal.VerticalBox, "Stack", "Panel")
    text_style(widget(bp, unreal.TextBlock, "Message", "Stack"), "MJOLNIR UI", 28, (0.55, 0.85, 1.0, 1.0))
    ok = widget(bp, unreal.Button, "Ok", "Stack")
    ok.get_editor_property("slot").set_horizontal_alignment(unreal.HorizontalAlignment.H_ALIGN_CENTER)
    text_style(widget(bp, unreal.TextBlock, "OkLabel", "Ok"), "OK", 20, (0.05, 0.05, 0.05, 1.0))

    if not ui.compile_widget(bp):
        fail(f"{name} does not compile (widget tree)")
    if not ui.add_string_function(bp, "MJ_Event", "Name", ""):
        fail("MJ_Event")
    if not ui.add_string_function(bp, "SetMessage", "Text", "Message"):
        fail("SetMessage")
    if not ui.bind_event_to_function(bp, "Ok", "OnClicked", "MJ_Event", "hello_clicked"):
        fail("Ok.OnClicked")
    if not ui.compile_widget(bp):
        fail(f"{name} does not compile")
    eal.save_loaded_asset(bp)
    unreal.log(f"MJOLNIR UI: {ROOT}/{name} built")


def build_label():
    full = f"{ROOT}/PAL_MJOLNIR_UI"
    if eal.does_asset_exist(full):
        eal.delete_asset(full)
    label = assets.create_asset("PAL_MJOLNIR_UI", ROOT, unreal.PrimaryAssetLabel, unreal.DataAssetFactory())
    rules = label.get_editor_property("rules")
    rules.set_editor_property("chunk_id", CHUNK)
    rules.set_editor_property("apply_recursively", True)
    rules.set_editor_property("cook_rule", unreal.PrimaryAssetCookRule.ALWAYS_COOK)
    label.set_editor_property("rules", rules)
    label.set_editor_property("label_assets_in_my_directory", True)
    eal.save_loaded_asset(label)


build_hello()
build_label()
unreal.log("MJOLNIR UI built")

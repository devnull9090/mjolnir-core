"""Build MJOLNIR's own widgets: real Widget Blueprints the game loads from our
container, instead of buttons slipped into its shipped screens.

    powershell -File tools/ue/editor_cmd.ps1 -Script Scripts/build_mjolnir_ui.py

Writes, under /Game/MJOLNIR/UI:
  WBP_MJOLNIRHello   the first test: a message and an OK button.
                     SetMessage(Text) sets the message; clicking OK calls
                     MJ_Event("hello_clicked"), an empty function Lua hooks.
  WBP_MJOLNIRKillFeed    the multiplayer kill feed and respawn countdown
  WBP_MJOLNIRScoreboard  the multiplayer scoreboard
                     Both are layout only: MJOLNIRHud fills their text blocks
                     from Lua (`w.Line0:SetText(FText(...))`).
  PAL_MJOLNIR_UI    the label that puts the folder in chunk 984
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


def fresh_widget(name):
    if eal.does_asset_exist(f"{ROOT}/{name}"):
        eal.delete_asset(f"{ROOT}/{name}")
    bp = ui.create_widget_blueprint(ROOT, name)
    if bp is None:
        fail(f"could not create {name}")
    return bp


def hud_root(bp):
    """A full-screen canvas the mouse passes through: HUD widgets never take
    clicks or focus from the game."""
    root = widget(bp, unreal.CanvasPanel, "Root")
    root.set_visibility(unreal.SlateVisibility.HIT_TEST_INVISIBLE)
    return root


def place(w, anchor, alignment, offset=(0.0, 0.0)):
    slot = w.get_editor_property("slot")
    slot.set_anchors(unreal.Anchors(minimum=unreal.Vector2D(*anchor), maximum=unreal.Vector2D(*anchor)))
    slot.set_alignment(unreal.Vector2D(*alignment))
    slot.set_position(unreal.Vector2D(*offset))
    slot.set_auto_size(True)


def shadowed(block):
    block.set_shadow_offset(unreal.Vector2D(2.5, 2.5))
    block.set_shadow_color_and_opacity(unreal.LinearColor(0.0, 0.0, 0.0, 0.85))


def finish(bp, name):
    if not ui.compile_widget(bp):
        fail(f"{name} does not compile")
    eal.save_loaded_asset(bp)
    unreal.log(f"MJOLNIR UI: {ROOT}/{name} built")


# The kill feed: FEED_LINES lines, newest at the bottom, at the left of the
# screen above the motion tracker; and the respawn countdown in the middle.
# MJOLNIRHud fills the lines (Line0 oldest) and fades them out.
FEED_LINES = 6


def build_kill_feed():
    name = "WBP_MJOLNIRKillFeed"
    bp = fresh_widget(name)
    hud_root(bp)
    feed = widget(bp, unreal.VerticalBox, "Feed", "Root")
    place(feed, (0.02, 0.68), (0.0, 1.0))
    for i in range(FEED_LINES):
        line = widget(bp, unreal.TextBlock, f"Line{i}", "Feed")
        text_style(line, "", 32)
        shadowed(line)
    respawn = widget(bp, unreal.TextBlock, "Respawn", "Root")
    place(respawn, (0.5, 0.36), (0.5, 0.5))
    text_style(respawn, "", 52, (0.55, 0.85, 1.0, 1.0))
    respawn.set_editor_property("justification", unreal.TextJustify.CENTER)
    shadowed(respawn)
    finish(bp, name)


# The scoreboard: a title, a subtitle (the score to win, or the team scores),
# a header and SCORE_ROWS player rows of name, score, kills and deaths.
# MJOLNIRHud fills it, sorted, and hides the rows it does not use.
SCORE_ROWS = 16
COLUMNS = (("Name", "PLAYER", 5.0, unreal.TextJustify.LEFT),
           ("Score", "SCORE", 1.5, unreal.TextJustify.CENTER),
           ("Kills", "KILLS", 1.5, unreal.TextJustify.CENTER),
           ("Deaths", "DEATHS", 1.5, unreal.TextJustify.CENTER))


def columns(bp, parent, suffix, size, header):
    for key, title, fill, justify in COLUMNS:
        cell = widget(bp, unreal.TextBlock, f"{key}{suffix}", parent)
        text_style(cell, title if header else "", size,
                   (0.55, 0.85, 1.0, 1.0) if header else (1.0, 1.0, 1.0, 1.0))
        cell.set_editor_property("justification", justify)
        cell.get_editor_property("slot").set_size(unreal.SlateChildSize(fill, unreal.SlateSizeRule.FILL))


def build_scoreboard():
    name = "WBP_MJOLNIRScoreboard"
    bp = fresh_widget(name)
    hud_root(bp)
    panel = widget(bp, unreal.Border, "Panel", "Root")
    panel.set_editor_property("brush_color", unreal.LinearColor(0.0, 0.02, 0.05, 0.82))
    panel.set_editor_property("padding", unreal.Margin(44, 32, 44, 40))
    place(panel, (0.5, 0.45), (0.5, 0.5))
    size = widget(bp, unreal.SizeBox, "Size", "Panel")
    size.set_width_override(1500.0)
    widget(bp, unreal.VerticalBox, "Stack", "Size")
    text_style(widget(bp, unreal.TextBlock, "Title", "Stack"), "SLAYER", 52, (0.55, 0.85, 1.0, 1.0))
    subtitle = widget(bp, unreal.TextBlock, "Subtitle", "Stack")
    text_style(subtitle, "", 30, (0.75, 0.75, 0.75, 1.0))
    subtitle.get_editor_property("slot").set_padding(unreal.Margin(0, 4, 0, 24))
    header = widget(bp, unreal.HorizontalBox, "Header", "Stack")
    header.get_editor_property("slot").set_padding(unreal.Margin(16, 0, 16, 10))
    columns(bp, "Header", "H", 26, True)
    for i in range(SCORE_ROWS):
        row = widget(bp, unreal.Border, f"Row{i}", "Stack")
        row.set_editor_property("brush_color", unreal.LinearColor(1.0, 1.0, 1.0, 0.06 if i % 2 == 0 else 0.02))
        row.set_editor_property("padding", unreal.Margin(16, 6, 16, 6))
        widget(bp, unreal.HorizontalBox, f"Cols{i}", f"Row{i}")
        columns(bp, f"Cols{i}", str(i), 34, False)
    finish(bp, name)


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
build_kill_feed()
build_scoreboard()
build_label()
unreal.log("MJOLNIR UI built")

"""Build MJOLNIR's own widgets: real Widget Blueprints the game loads from our
container, instead of buttons slipped into its shipped screens.

    powershell -File tools/ue/editor_cmd.ps1 -Script Scripts/build_mjolnir_ui.py

Writes, under /Game/MJOLNIR/UI:
  WBP_MJOLNIRHello   the first test: a message and an OK button.
                     SetMessage(Text) sets the message; clicking OK calls
                     MJ_Event("hello_clicked"), an empty function Lua hooks.
  WBP_MJOLNIRKillFeed    the multiplayer kill feed and respawn countdown
  WBP_MJOLNIRScoreboard  the multiplayer scoreboard
  WBP_MJOLNIRLobby       the host's lobby (MJOLNIRLobby): map, game type,
                         players, START GAME
  WBP_MJOLNIRMapSelect   the map list, a map's details and its game types
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
    bp = ui.create_widget_blueprint(ROOT, name, None)
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


def fresh_widget(name, parent=None):
    if eal.does_asset_exist(f"{ROOT}/{name}"):
        eal.delete_asset(f"{ROOT}/{name}")
    bp = ui.create_widget_blueprint(ROOT, name, parent)
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


# --- Menu screens ------------------------------------------------------------
#
# Screens are CommonActivatableWidgets, pushed by MJOLNIRLobby onto the game's
# own menu stack (the UI layout's ContentStack): the stack hides the screen
# beneath, and Back (Escape, the gamepad's B) pops ours, as on any shipped
# screen. Every button's click calls MJ_Event(<event>), which Lua hooks;
# map buttons also call MJ_Event("hover:<i>") when hovered.

ACCENT = (0.55, 0.85, 1.0, 1.0)
GREY = (0.72, 0.76, 0.8, 1.0)
MAP_BUTTONS = 32
MODE_BUTTONS = 5
ROSTER_ROWS = 8


def stretch(w):
    slot = w.get_editor_property("slot")
    slot.set_anchors(unreal.Anchors(minimum=unreal.Vector2D(0, 0), maximum=unreal.Vector2D(1, 1)))
    slot.set_offsets(unreal.Margin(0, 0, 0, 0))


def sized(bp, name, parent, width=None, height=None):
    box = widget(bp, unreal.SizeBox, name, parent)
    if width:
        box.set_width_override(width)
    if height:
        box.set_height_override(height)
    return box


def panel(bp, name, parent, alpha=0.78, padding=(32, 28, 32, 28)):
    border = widget(bp, unreal.Border, name, parent)
    border.set_editor_property("brush_color", unreal.LinearColor(0.0, 0.02, 0.05, alpha))
    border.set_editor_property("padding", unreal.Margin(*padding))
    return border


def wrapped(block):
    block.set_editor_property("auto_wrap_text", True)


def gap(w, top=0, bottom=0):
    w.get_editor_property("slot").set_padding(unreal.Margin(0, top, 0, bottom))


def button_style(button):
    style = button.get_editor_property("widget_style")
    for state, rgba in (("normal", (0.06, 0.14, 0.2, 0.85)), ("hovered", (0.16, 0.42, 0.56, 0.95)),
                        ("pressed", (0.32, 0.68, 0.86, 1.0)), ("disabled", (0.05, 0.06, 0.07, 0.6))):
        brush = style.get_editor_property(state)
        brush.set_editor_property("tint_color", unreal.SlateColor(unreal.LinearColor(*rgba)))
        style.set_editor_property(state, brush)
    style.set_editor_property("normal_padding", unreal.Margin(24, 12, 24, 12))
    style.set_editor_property("pressed_padding", unreal.Margin(24, 13, 24, 11))
    button.set_editor_property("widget_style", style)


def menu_button(bp, name, label, parent, size=30):
    """A button with a text label (`<name>Label`), returned with its events
    still to bind (bind_events, after the tree is compiled)."""
    button = widget(bp, unreal.Button, name, parent)
    button_style(button)
    text_style(widget(bp, unreal.TextBlock, f"{name}Label", name), label, size)
    return button


def bind_events(bp, events):
    """events: (widget name, delegate, MJ_Event argument)."""
    for name, delegate, argument in events:
        if not ui.bind_event_to_function(bp, name, delegate, "MJ_Event", argument):
            fail(f"{name}.{delegate}")


def screen_header(bp, title, subtitle):
    shade = widget(bp, unreal.Border, "Shade", "Root")
    shade.set_editor_property("brush_color", unreal.LinearColor(0.0, 0.01, 0.03, 0.55))
    stretch(shade)
    head = widget(bp, unreal.VerticalBox, "Header", "Root")
    place(head, (0.06, 0.07), (0.0, 0.0))
    text_style(widget(bp, unreal.TextBlock, "Title", "Header"), title, 64, ACCENT)
    text_style(widget(bp, unreal.TextBlock, "Subtitle", "Header"), subtitle, 28, GREY)


def finish_screen(bp, name):
    if not ui.compile_widget(bp):
        fail(f"{name} does not compile")
    # Back pops the screen off the stack (CommonActivatableWidget's default
    # back action deactivates it).
    cdo = unreal.get_default_object(bp.generated_class())
    cdo.set_editor_property("is_back_handler", True)
    eal.save_loaded_asset(bp)
    unreal.log(f"MJOLNIR UI: {ROOT}/{name} built")


def build_lobby():
    """The host's lobby: the map and game type, the players, START and
    INVITE FRIENDS (the game's own Friends screen, cross-platform)."""
    name = "WBP_MJOLNIRLobby"
    bp = fresh_widget(name, unreal.CommonActivatableWidget)
    widget(bp, unreal.CanvasPanel, "Root")
    screen_header(bp, "MULTIPLAYER", "CUSTOM GAME")

    menu = sized(bp, "MenuSize", "Root", width=560)
    place(menu, (0.06, 0.30), (0.0, 0.0))
    widget(bp, unreal.VerticalBox, "Menu", "MenuSize")
    events = []
    for key, label in (("Start", "START GAME"), ("Invite", "INVITE FRIENDS"), ("ChangeMap", "CHANGE MAP"),
                       ("GameType", "GAME TYPE"), ("Back", "BACK")):
        gap(menu_button(bp, key, label, "Menu"), bottom=14)
        events.append((key, "OnClicked", key.lower()))

    card = panel(bp, "Card", "Root")
    place(card, (0.30, 0.30), (0.0, 0.0))
    sized(bp, "CardSize", "Card", width=1080)
    widget(bp, unreal.VerticalBox, "CardStack", "CardSize")
    text_style(widget(bp, unreal.TextBlock, "MapTitle", "CardStack"), "BLOOD GULCH", 56)
    mode = widget(bp, unreal.TextBlock, "ModeTitle", "CardStack")
    text_style(mode, "SLAYER", 34, ACCENT)
    gap(mode, bottom=18)
    description = widget(bp, unreal.TextBlock, "MapDescription", "CardStack")
    text_style(description, "", 26)
    wrapped(description)
    gap(description, bottom=18)
    mode_description = widget(bp, unreal.TextBlock, "ModeDescription", "CardStack")
    text_style(mode_description, "", 24, GREY)
    wrapped(mode_description)

    roster = panel(bp, "Roster", "Root")
    place(roster, (0.94, 0.30), (1.0, 0.0))
    sized(bp, "RosterSize", "Roster", width=520)
    widget(bp, unreal.VerticalBox, "RosterStack", "RosterSize")
    heading = widget(bp, unreal.TextBlock, "PlayersHeading", "RosterStack")
    text_style(heading, "PLAYERS", 28, ACCENT)
    gap(heading, bottom=12)
    for i in range(ROSTER_ROWS):
        row = widget(bp, unreal.TextBlock, f"Player{i}", "RosterStack")
        text_style(row, "", 28)
        gap(row, bottom=6)

    status = widget(bp, unreal.TextBlock, "Status", "Root")
    place(status, (0.06, 0.88), (0.0, 0.0))
    text_style(status, "", 26, GREY)

    if not ui.compile_widget(bp):
        fail(f"{name} does not compile (widget tree)")
    if not ui.add_string_function(bp, "MJ_Event", "Name", ""):
        fail("MJ_Event")
    bind_events(bp, events)
    finish_screen(bp, name)


def build_map_select():
    """Every installed map, its details and game types, and SELECT."""
    name = "WBP_MJOLNIRMapSelect"
    bp = fresh_widget(name, unreal.CommonActivatableWidget)
    widget(bp, unreal.CanvasPanel, "Root")
    screen_header(bp, "SELECT MAP", "CUSTOM GAME")

    list_panel = panel(bp, "ListPanel", "Root", padding=(16, 16, 16, 16))
    place(list_panel, (0.06, 0.22), (0.0, 0.0))
    sized(bp, "ListSize", "ListPanel", width=620, height=1340)
    widget(bp, unreal.ScrollBox, "MapList", "ListSize")
    events = []
    for i in range(MAP_BUTTONS):
        gap(menu_button(bp, f"Map{i}", "", "MapList", size=28), bottom=8)
        events += [(f"Map{i}", "OnClicked", f"map:{i}"), (f"Map{i}", "OnHovered", f"hover:{i}")]

    details = panel(bp, "Details", "Root")
    place(details, (0.30, 0.22), (0.0, 0.0))
    sized(bp, "DetailsSize", "Details", width=1500)
    widget(bp, unreal.VerticalBox, "DetailsStack", "DetailsSize")
    text_style(widget(bp, unreal.TextBlock, "MapTitle", "DetailsStack"), "", 60)
    description = widget(bp, unreal.TextBlock, "MapDescription", "DetailsStack")
    text_style(description, "", 28)
    wrapped(description)
    gap(description, top=8, bottom=30)
    heading = widget(bp, unreal.TextBlock, "ModesHeading", "DetailsStack")
    text_style(heading, "GAME TYPE", 28, ACCENT)
    gap(heading, bottom=12)
    widget(bp, unreal.HorizontalBox, "Modes", "DetailsStack")
    for i in range(MODE_BUTTONS):
        button = menu_button(bp, f"Mode{i}", "", "Modes", size=26)
        button.get_editor_property("slot").set_padding(unreal.Margin(0, 0, 14, 0))
        events.append((f"Mode{i}", "OnClicked", f"mode:{i}"))
    mode_description = widget(bp, unreal.TextBlock, "ModeDescription", "DetailsStack")
    text_style(mode_description, "", 26, GREY)
    wrapped(mode_description)
    gap(mode_description, top=16)

    actions = widget(bp, unreal.HorizontalBox, "Actions", "Root")
    place(actions, (0.30, 0.86), (0.0, 0.0))
    for key, label in (("Select", "SELECT"), ("Back", "BACK")):
        button = menu_button(bp, key, label, "Actions")
        button.get_editor_property("slot").set_padding(unreal.Margin(0, 0, 20, 0))
        events.append((key, "OnClicked", key.lower()))

    if not ui.compile_widget(bp):
        fail(f"{name} does not compile (widget tree)")
    if not ui.add_string_function(bp, "MJ_Event", "Name", ""):
        fail("MJ_Event")
    bind_events(bp, events)
    finish_screen(bp, name)


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
build_lobby()
build_map_select()
build_label()
unreal.log("MJOLNIR UI built")

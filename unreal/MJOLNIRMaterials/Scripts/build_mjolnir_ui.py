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
  WBP_MJOLNIRPostGame    after a match: the final standings and the vote on
                         the next game (MJOLNIRLobby)
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
    font.set_editor_property("typeface_font_name", "Regular")
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
    return screen_canvas(bp, interactive=False)


def screen_canvas(bp, interactive=True):
    """One design space, fitted to any viewport (including 4:3 and ultrawide).
    Pixel widths and anchored columns must scale together, not overlap at 720p.
    The game's animated frontend remains visible behind the composition."""
    viewport = widget(bp, unreal.CanvasPanel, "Viewport")
    viewport.set_visibility(unreal.SlateVisibility.SELF_HIT_TEST_INVISIBLE if interactive
                            else unreal.SlateVisibility.HIT_TEST_INVISIBLE)
    fit = widget(bp, unreal.ScaleBox, "Fit", "Viewport")
    stretch(fit)
    fit.set_stretch(unreal.Stretch.SCALE_TO_FIT)
    sized(bp, "Design", "Fit", width=2560, height=1440)
    return widget(bp, unreal.CanvasPanel, "Root", "Design")


def place(w, anchor, alignment, offset=(0.0, 0.0)):
    slot = w.get_editor_property("slot")
    slot.set_anchors(unreal.Anchors(minimum=unreal.Vector2D(*anchor), maximum=unreal.Vector2D(*anchor)))
    slot.set_alignment(unreal.Vector2D(*alignment))
    slot.set_position(unreal.Vector2D(*offset))
    slot.set_auto_size(True)


def shadowed(block):
    block.set_shadow_offset(unreal.Vector2D(2.5, 2.5))
    block.set_shadow_color_and_opacity(unreal.LinearColor(0.0, 0.0, 0.0, 0.85))


def watermark(bp):
    """`Watermark`, the build line at the bottom centre of every MJOLNIR
    screen and of the HUD (mod versions and the game build, filled from
    Lua), so a screenshot or a stream shows what was running."""
    line = widget(bp, unreal.TextBlock, "Watermark", "Root")
    place(line, (0.5, 1.0), (0.5, 1.0), (0.0, -10.0))
    text_style(line, "MJOLNIR MULTIPLAYER", 14, (0.62, 0.74, 0.82, 0.55))
    line.set_editor_property("justification", unreal.TextJustify.CENTER)
    shadowed(line)
    line.set_visibility(unreal.SlateVisibility.HIT_TEST_INVISIBLE)


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

    # Persistent match score, pinned to the top edge above the native shield
    # bar. Lua uses Red / Blue for teams, YOU / LEADER for free-for-all.
    strip = panel(bp, "MatchScore", "Root", alpha=0.55, padding=(16, 8, 16, 10))
    place(strip, (0.5, 0.0), (0.5, 0.0))
    widget(bp, unreal.HorizontalBox, "ScoreSides", "MatchScore")
    for side, label, color in (("Left", "RED", RED), ("Target", "TO WIN", GREY), ("Right", "BLUE", BLUE)):
        sized(bp, "Score" + side + "Size", "ScoreSides", width=80 if side == "Target" else 170)
        widget(bp, unreal.VerticalBox, "Score" + side + "Stack", "Score" + side + "Size")
        if side != "Target":
            line = sized(bp, "Score" + side + "Rule", "Score" + side + "Stack", height=2)
            ink = widget(bp, unreal.Border, "Score" + side + "Accent", line.get_name())
            ink.set_editor_property("brush_color", unreal.LinearColor(*color))
            ink.set_editor_property("padding", unreal.Margin(0))
            gap(line, bottom=5)
        caption = widget(bp, unreal.TextBlock, "Score" + side + "Label", "Score" + side + "Stack")
        text_style(caption, label, 11 if side == "Target" else 14, color)
        caption.set_editor_property("justification", unreal.TextJustify.CENTER)
        if side == "Target":
            gap(caption, top=10, bottom=2)
        value = widget(bp, unreal.TextBlock, "ScoreTarget" if side == "Target" else "Score" + side + "Value",
                       "Score" + side + "Stack")
        text_style(value, "0", 18 if side == "Target" else 30, GREY if side == "Target" else WHITE)
        value.set_editor_property("justification", unreal.TextJustify.CENTER)
    watermark(bp)
    finish(bp, name)


# The scoreboard: a title, a subtitle (the score to win, or the team scores),
# a header and SCORE_ROWS player rows of name, score, kills and deaths.
# MJOLNIRHud fills it, sorted, and hides the rows it does not use.
SCORE_ROWS = 19  # sixteen players and up to three team headings
COLUMNS = (("Name", "PLAYER", 5.0, unreal.TextJustify.LEFT),
           ("Score", "SCORE", 1.5, unreal.TextJustify.CENTER),
           ("Kills", "KILLS", 1.5, unreal.TextJustify.CENTER),
           ("Deaths", "DEATHS", 1.5, unreal.TextJustify.CENTER))


def columns(bp, parent, suffix, size, header):
    # A separate marker preserves the player's name and makes the local row
    # identifiable even without colour vision.
    marker_size = sized(bp, f"MarkerSize{suffix}", parent, width=66)
    marker = widget(bp, unreal.TextBlock, f"Marker{suffix}", marker_size.get_name())
    text_style(marker, "", 16, GOLD)
    marker.get_editor_property("slot").set_vertical_alignment(unreal.VerticalAlignment.V_ALIGN_CENTER)
    for key, title, fill, justify in COLUMNS:
        cell = widget(bp, unreal.TextBlock, f"{key}{suffix}", parent)
        text_style(cell, title if header else "", size,
                   (0.55, 0.85, 1.0, 1.0) if header else (1.0, 1.0, 1.0, 1.0))
        cell.set_editor_property("justification", justify)
        cell.set_editor_property("text_overflow_policy", unreal.TextOverflowPolicy.ELLIPSIS)
        cell.get_editor_property("slot").set_size(unreal.SlateChildSize(fill, unreal.SlateSizeRule.FILL))


def build_scoreboard():
    name = "WBP_MJOLNIRScoreboard"
    bp = fresh_widget(name)
    hud_root(bp)
    frame = panel(bp, "Panel", "Root", alpha=0.94, padding=(36, 28, 36, 28))
    place(frame, (0.5, 0.49), (0.5, 0.5))
    sized(bp, "Size", "Panel", width=1540)
    widget(bp, unreal.VerticalBox, "Stack", "Size")
    rule(bp, "BoardTopRule", "Stack", ACCENT, 2)
    kicker = widget(bp, unreal.TextBlock, "BoardLabel", "Stack")
    text_style(kicker, "MULTIPLAYER  /  MATCH STANDINGS", 18, ACCENT)
    gap(kicker, top=18, bottom=12)
    text_style(widget(bp, unreal.TextBlock, "Title", "Stack"), "SLAYER", 44, WHITE)
    subtitle = widget(bp, unreal.TextBlock, "Subtitle", "Stack")
    text_style(subtitle, "", 21, GREY)
    gap(subtitle, top=6, bottom=24)
    header = widget(bp, unreal.HorizontalBox, "Header", "Stack")
    header.get_editor_property("slot").set_padding(unreal.Margin(16, 0, 16, 10))
    columns(bp, "Header", "H", 18, True)
    for i in range(SCORE_ROWS):
        row = widget(bp, unreal.Border, f"Row{i}", "Stack")
        row.set_editor_property("padding", unreal.Margin(0))
        row.set_visibility(unreal.SlateVisibility.COLLAPSED)
        widget(bp, unreal.HorizontalBox, f"RowLayout{i}", f"Row{i}")
        sized(bp, f"StripeSize{i}", f"RowLayout{i}", width=3)
        widget(bp, unreal.Border, f"Stripe{i}", f"StripeSize{i}")
        content = widget(bp, unreal.HorizontalBox, f"Cols{i}", f"RowLayout{i}")
        content.get_editor_property("slot").set_size(unreal.SlateChildSize(1, unreal.SlateSizeRule.FILL))
        content.get_editor_property("slot").set_padding(unreal.Margin(13, 5, 16, 5))
        columns(bp, f"Cols{i}", str(i), 26, False)
    gap(rule(bp, "BoardBottomRule", "Stack", LINE), top=20, bottom=14)
    foot = widget(bp, unreal.HorizontalBox, "BoardFooter", "Stack")
    count = widget(bp, unreal.TextBlock, "PlayerCount", foot.get_name())
    text_style(count, "", 17, GREY)
    count.get_editor_property("slot").set_size(unreal.SlateChildSize(1, unreal.SlateSizeRule.FILL))
    text_style(widget(bp, unreal.TextBlock, "BoardHint", "BoardFooter"), "RELEASE TAB / VIEW TO RETURN", 17, GREY)
    finish(bp, name)


# --- Menu screens ------------------------------------------------------------
#
# Screens are CommonActivatableWidgets, pushed by MJOLNIRLobby onto the game's
# own menu stack (the UI layout's ContentStack): the stack hides the screen
# beneath, and Back (Escape, the gamepad's B) pops ours, as on any shipped
# screen. Every button's click calls MJ_Event(<event>), which Lua hooks;
# map buttons also call MJ_Event("hover:<i>") when hovered.

ACCENT = (0.46, 0.79, 0.94, 1.0)
WHITE = (0.88, 0.95, 1.0, 1.0)
GREY = (0.46, 0.61, 0.70, 1.0)
GOLD = (1.0, 0.80, 0.35, 1.0)
LINE = (0.24, 0.49, 0.63, 0.45)
RED = (1.0, 0.32, 0.28, 1.0)
BLUE = (0.3, 0.65, 1.0, 1.0)
MAP_BUTTONS = 32
MODE_BUTTONS = 5
ROSTER_ROWS = 16


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
    border.set_editor_property("brush_color", unreal.LinearColor(0.005, 0.018, 0.03, alpha))
    border.set_editor_property("padding", unreal.Margin(*padding))
    return border


def wrapped(block):
    block.set_editor_property("auto_wrap_text", True)


def gap(w, top=0, bottom=0):
    w.get_editor_property("slot").set_padding(unreal.Margin(0, top, 0, bottom))


def rule(bp, name, parent, color=LINE, height=1):
    box = sized(bp, name, parent, height=height)
    line = widget(bp, unreal.Border, name + "Ink", name)
    line.set_editor_property("brush_color", unreal.LinearColor(*color))
    line.set_editor_property("padding", unreal.Margin(0))
    return box


def button_style(button):
    style = button.get_editor_property("widget_style")
    for state, rgba in (("normal", (0.025, 0.06, 0.09, 0.28)), ("hovered", (0.12, 0.32, 0.43, 0.8)),
                        ("pressed", (0.20, 0.48, 0.60, 0.95)), ("disabled", (0.03, 0.04, 0.05, 0.35))):
        brush = style.get_editor_property(state)
        # Remove the stock rounded/bevelled button image entirely.
        brush.set_editor_property("resource_object", None)
        brush.set_editor_property("draw_as", unreal.SlateBrushDrawType.IMAGE)
        brush.set_editor_property("tint_color", unreal.SlateColor(unreal.LinearColor(*rgba)))
        style.set_editor_property(state, brush)
    style.set_editor_property("normal_padding", unreal.Margin(24, 18, 24, 18))
    style.set_editor_property("pressed_padding", unreal.Margin(24, 19, 24, 17))
    button.set_editor_property("widget_style", style)


def menu_button(bp, name, label, parent, size=30):
    """A button with a text label (`<name>Label`), returned with its events
    still to bind (bind_events, after the tree is compiled)."""
    button = widget(bp, unreal.Button, name, parent)
    button_style(button)
    block = widget(bp, unreal.TextBlock, f"{name}Label", name)
    text_style(block, label, size, GOLD if name in ("Start", "Select") else WHITE)
    block.get_editor_property("slot").set_horizontal_alignment(unreal.HorizontalAlignment.H_ALIGN_LEFT)
    return button


def bind_events(bp, events):
    """events: (widget name, delegate, MJ_Event argument)."""
    for name, delegate, argument in events:
        if not ui.bind_event_to_function(bp, name, delegate, "MJ_Event", argument):
            fail(f"{name}.{delegate}")


def screen_header(bp, title, subtitle):
    shade = widget(bp, unreal.Border, "Shade", "Root")
    shade.set_editor_property("brush_color", unreal.LinearColor(0.0, 0.008, 0.02, 0.40))
    stretch(shade)
    head = widget(bp, unreal.VerticalBox, "Header", "Root")
    place(head, (0.06, 0.07), (0.0, 0.0))
    text_style(widget(bp, unreal.TextBlock, "Subtitle", "Header"), subtitle + "  /  MJOLNIR", 20, ACCENT)
    heading = widget(bp, unreal.TextBlock, "Title", "Header")
    text_style(heading, title, 72, WHITE)
    gap(heading, top=10, bottom=18)
    sized(bp, "HeaderRuleWidth", "Header", width=225)
    rule(bp, "HeaderRule", "HeaderRuleWidth", ACCENT, 3)


def footer(bp):
    watermark(bp)
    foot = sized(bp, "FooterSize", "Root", width=2250)
    place(foot, (0.06, 0.88), (0, 0))
    widget(bp, unreal.VerticalBox, "Footer", "FooterSize")
    gap(rule(bp, "FooterRule", "Footer"), bottom=18)
    status = widget(bp, unreal.TextBlock, "Status", "Footer")
    text_style(status, "", 22, GREY)
    wrapped(status)
    return status


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
    screen_canvas(bp)
    screen_header(bp, "MULTIPLAYER", "CUSTOM GAME")

    menu = sized(bp, "MenuSize", "Root", width=470)
    place(menu, (0.06, 0.28), (0.0, 0.0))
    widget(bp, unreal.VerticalBox, "Menu", "MenuSize")
    gap(rule(bp, "MenuRule", "Menu", ACCENT, 2), bottom=12)
    events = []
    for key, label in (("Start", "START GAME"), ("Invite", "INVITE FRIENDS"), ("ChangeMap", "CHANGE MAP"),
                       ("GameType", "GAME TYPE"), ("Back", "BACK")):
        gap(menu_button(bp, key, label, "Menu", size=30), bottom=10)
        events.append((key, "OnClicked", key.lower()))

    card = panel(bp, "Card", "Root")
    place(card, (0.28, 0.28), (0.0, 0.0))
    sized(bp, "CardSize", "Card", width=840)
    widget(bp, unreal.VerticalBox, "CardStack", "CardSize")
    gap(rule(bp, "MapRule", "CardStack", ACCENT, 2), bottom=24)
    label = widget(bp, unreal.TextBlock, "MapKicker", "CardStack")
    text_style(label, "MISSION AREA", 18, ACCENT)
    gap(label, bottom=12)
    map_title = widget(bp, unreal.TextBlock, "MapTitle", "CardStack")
    text_style(map_title, "BLOOD GULCH", 46, WHITE)
    wrapped(map_title)
    description = widget(bp, unreal.TextBlock, "MapDescription", "CardStack")
    text_style(description, "", 24, GREY)
    wrapped(description)
    gap(description, top=20, bottom=32)
    gap(rule(bp, "ModeRule", "CardStack"), bottom=26)
    text_style(widget(bp, unreal.TextBlock, "ModeKicker", "CardStack"), "GAME TYPE", 18, ACCENT)
    mode = widget(bp, unreal.TextBlock, "ModeTitle", "CardStack")
    text_style(mode, "SLAYER", 34, WHITE)
    gap(mode, top=12, bottom=16)
    wrapped(mode)
    mode_description = widget(bp, unreal.TextBlock, "ModeDescription", "CardStack")
    text_style(mode_description, "", 24, GREY)
    wrapped(mode_description)
    gap(rule(bp, "FormatRule", "CardStack"), top=32, bottom=20)
    text_style(widget(bp, unreal.TextBlock, "MatchFormat", "CardStack"), "FREE FOR ALL", 20, ACCENT)

    roster = panel(bp, "Roster", "Root")
    place(roster, (0.94, 0.28), (1.0, 0.0))
    sized(bp, "RosterSize", "Roster", width=640)
    widget(bp, unreal.VerticalBox, "RosterStack", "RosterSize")
    gap(rule(bp, "RosterRule", "RosterStack", ACCENT, 2), bottom=24)
    heading = widget(bp, unreal.TextBlock, "PlayersHeading", "RosterStack")
    text_style(heading, "PLAYERS", 22, ACCENT)
    gap(heading, bottom=18)
    sized(bp, "RosterScrollSize", "RosterStack", height=590)
    widget(bp, unreal.ScrollBox, "RosterScroll", "RosterScrollSize")
    for group, title, color in (("FFA", "FIRETEAM", ACCENT), ("Red", "RED TEAM", RED),
                                 ("Blue", "BLUE TEAM", BLUE), ("Unassigned", "AWAITING ASSIGNMENT", GREY)):
        section = widget(bp, unreal.VerticalBox, group + "Roster", "RosterScroll")
        gap(section, bottom=16)
        strip = panel(bp, group + "Strip", group + "Roster", padding=(14, 10, 14, 10))
        strip.set_editor_property("brush_color", unreal.LinearColor(*color[:3], 0.18))
        text_style(widget(bp, unreal.TextBlock, group + "Heading", group + "Strip"), title, 20, color)
        for i in range(ROSTER_ROWS):
            row = widget(bp, unreal.TextBlock, f"{group}Player{i}", group + "Roster")
            text_style(row, "", 24, WHITE)
            row.set_editor_property("text_overflow_policy", unreal.TextOverflowPolicy.ELLIPSIS)
            row.get_editor_property("slot").set_padding(unreal.Margin(14, 8, 14, 4))
            row.set_visibility(unreal.SlateVisibility.COLLAPSED)
    hint = widget(bp, unreal.TextBlock, "TeamHint", "RosterStack")
    text_style(hint, "", 19, GREY)
    wrapped(hint)
    gap(hint, top=12)
    footer(bp)

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
    screen_canvas(bp)
    screen_header(bp, "SELECT MAP", "CUSTOM GAME")

    list_panel = panel(bp, "ListPanel", "Root", padding=(16, 16, 16, 16))
    place(list_panel, (0.06, 0.22), (0.0, 0.0))
    sized(bp, "ListSize", "ListPanel", width=520, height=790)
    widget(bp, unreal.ScrollBox, "MapList", "ListSize")
    events = []
    for i in range(MAP_BUTTONS):
        gap(menu_button(bp, f"Map{i}", "", "MapList", size=25), bottom=5)
        events += [(f"Map{i}", "OnClicked", f"map:{i}"), (f"Map{i}", "OnHovered", f"hover:{i}")]

    details = panel(bp, "Details", "Root")
    place(details, (0.32, 0.22), (0.0, 0.0))
    sized(bp, "DetailsSize", "Details", width=1430)
    widget(bp, unreal.VerticalBox, "DetailsStack", "DetailsSize")
    gap(rule(bp, "DetailsRule", "DetailsStack", ACCENT, 2), bottom=24)
    title = widget(bp, unreal.TextBlock, "MapTitle", "DetailsStack")
    text_style(title, "", 48, WHITE)
    wrapped(title)
    description = widget(bp, unreal.TextBlock, "MapDescription", "DetailsStack")
    text_style(description, "", 28)
    wrapped(description)
    gap(description, top=8, bottom=30)
    heading = widget(bp, unreal.TextBlock, "ModesHeading", "DetailsStack")
    text_style(heading, "GAME TYPE", 28, ACCENT)
    gap(heading, bottom=12)
    # Vertical options never run beyond the card when all five modes exist.
    widget(bp, unreal.VerticalBox, "Modes", "DetailsStack")
    for i in range(MODE_BUTTONS):
        button = menu_button(bp, f"Mode{i}", "", "Modes", size=24)
        gap(button, bottom=6)
        events.append((f"Mode{i}", "OnClicked", f"mode:{i}"))
    mode_description = widget(bp, unreal.TextBlock, "ModeDescription", "DetailsStack")
    text_style(mode_description, "", 26, GREY)
    wrapped(mode_description)
    gap(mode_description, top=16)

    actions = widget(bp, unreal.HorizontalBox, "Actions", "Root")
    place(actions, (0.32, 0.79), (0.0, 0.0))
    for key, label in (("Select", "SELECT"), ("Back", "BACK")):
        button = menu_button(bp, key, label, "Actions")
        button.get_editor_property("slot").set_padding(unreal.Margin(0, 0, 20, 0))
        events.append((key, "OnClicked", key.lower()))
    text_style(footer(bp), "CHOOSE A MAP AND GAME TYPE   /   SELECT TO CONFIRM", 22, GREY)

    if not ui.compile_widget(bp):
        fail(f"{name} does not compile (widget tree)")
    if not ui.add_string_function(bp, "MJ_Event", "Name", ""):
        fail("MJ_Event")
    bind_events(bp, events)
    finish_screen(bp, name)


VOTE_OPTIONS = 4
RESULT_ROWS = 18  # sixteen players and the two team headings


def build_post_game():
    """After a match, on the menu: the final standings, and the vote on the
    next game. Every fireteam member votes; the host can start the leader
    at once or go back to the lobby (docs/multiplayer_postgame.md)."""
    name = "WBP_MJOLNIRPostGame"
    bp = fresh_widget(name, unreal.CommonActivatableWidget)
    screen_canvas(bp)
    screen_header(bp, "POST-GAME", "CUSTOM GAME")

    results = panel(bp, "Results", "Root")
    place(results, (0.06, 0.28), (0.0, 0.0))
    sized(bp, "ResultsSize", "Results", width=1280)
    widget(bp, unreal.VerticalBox, "ResultsStack", "ResultsSize")
    gap(rule(bp, "ResultsRule", "ResultsStack", ACCENT, 2), bottom=24)
    kicker = widget(bp, unreal.TextBlock, "ResultsKicker", "ResultsStack")
    text_style(kicker, "FINAL STANDINGS", 18, ACCENT)
    gap(kicker, bottom=12)
    winner = widget(bp, unreal.TextBlock, "Winner", "ResultsStack")
    text_style(winner, "", 46, WHITE)
    wrapped(winner)
    summary = widget(bp, unreal.TextBlock, "Summary", "ResultsStack")
    text_style(summary, "", 24, GREY)
    wrapped(summary)
    gap(summary, top=10, bottom=26)
    gap(rule(bp, "TableRule", "ResultsStack"), bottom=14)
    header = widget(bp, unreal.HorizontalBox, "TableHeader", "ResultsStack")
    header.get_editor_property("slot").set_padding(unreal.Margin(16, 0, 16, 10))
    columns(bp, "TableHeader", "H", 18, True)
    sized(bp, "RowsSize", "ResultsStack", height=470)
    widget(bp, unreal.ScrollBox, "Rows", "RowsSize")
    for i in range(RESULT_ROWS):
        row = widget(bp, unreal.Border, f"Row{i}", "Rows")
        row.set_editor_property("padding", unreal.Margin(0))
        row.set_visibility(unreal.SlateVisibility.COLLAPSED)
        widget(bp, unreal.HorizontalBox, f"RowLayout{i}", f"Row{i}")
        sized(bp, f"StripeSize{i}", f"RowLayout{i}", width=3)
        widget(bp, unreal.Border, f"Stripe{i}", f"StripeSize{i}")
        content = widget(bp, unreal.HorizontalBox, f"Cols{i}", f"RowLayout{i}")
        content.get_editor_property("slot").set_size(unreal.SlateChildSize(1, unreal.SlateSizeRule.FILL))
        content.get_editor_property("slot").set_padding(unreal.Margin(13, 5, 16, 5))
        columns(bp, f"Cols{i}", str(i), 24, False)

    vote = panel(bp, "Vote", "Root")
    place(vote, (0.94, 0.28), (1.0, 0.0))
    sized(bp, "VoteSize", "Vote", width=780)
    widget(bp, unreal.VerticalBox, "VoteStack", "VoteSize")
    gap(rule(bp, "VoteRule", "VoteStack", ACCENT, 2), bottom=24)
    heading = widget(bp, unreal.TextBlock, "VoteKicker", "VoteStack")
    text_style(heading, "NEXT GAME", 18, ACCENT)
    gap(heading, bottom=12)
    timer = widget(bp, unreal.TextBlock, "VoteTimer", "VoteStack")
    text_style(timer, "VOTE", 34, WHITE)
    wrapped(timer)
    gap(timer, bottom=22)
    events = []
    for i in range(VOTE_OPTIONS):
        line = widget(bp, unreal.HorizontalBox, f"VoteRow{i}", "VoteStack")
        gap(line, bottom=8)
        button = menu_button(bp, f"Vote{i}", "", line.get_name(), size=26)
        button.get_editor_property("slot").set_size(unreal.SlateChildSize(1, unreal.SlateSizeRule.FILL))
        count_size = sized(bp, f"VoteCountSize{i}", line.get_name(), width=110)
        count_size.get_editor_property("slot").set_vertical_alignment(unreal.VerticalAlignment.V_ALIGN_CENTER)
        count = widget(bp, unreal.TextBlock, f"VoteCount{i}", count_size.get_name())
        text_style(count, "", 26, GOLD)
        count.set_editor_property("justification", unreal.TextJustify.RIGHT)
        events.append((f"Vote{i}", "OnClicked", f"vote:{i}"))
    hint = widget(bp, unreal.TextBlock, "VoteHint", "VoteStack")
    text_style(hint, "", 21, GREY)
    wrapped(hint)
    gap(hint, top=14, bottom=26)
    gap(rule(bp, "ActionsRule", "VoteStack"), bottom=18)
    actions = widget(bp, unreal.HorizontalBox, "Actions", "VoteStack")
    for key, label, event in (("Start", "START NOW", "start"), ("Lobby", "LOBBY", "lobby")):
        button = menu_button(bp, key, label, actions.get_name(), size=28)
        button.get_editor_property("slot").set_padding(unreal.Margin(0, 0, 16, 0))
        events.append((key, "OnClicked", event))
    footer(bp)

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
build_post_game()
build_label()
unreal.log("MJOLNIR UI built")

"""Build MJOLNIR's own widgets: real Widget Blueprints the game loads from our
container, instead of buttons slipped into its shipped screens.

    powershell -File tools/ue/editor_cmd.ps1 -Script Scripts/build_mjolnir_ui.py

Writes, under /Game/MJOLNIR/UI:
  WBP_MJOLNIRHello   the first test: a message and an OK button.
                     SetMessage(Text) sets the message; clicking OK calls
                     MJ_Event("hello_clicked"), an empty function Lua hooks.
  WBP_MJOLNIRKillFeed    the multiplayer kill feed (rows with the game's weapon
                         silhouettes and our glyphs), medal callouts, the
                         respawn countdown and the match score bars
  Icons/T_MJHud_*        the HUD's glyphs (tools/ue/draw_hud_icons.py)
  WBP_MJOLNIRScoreboard  the multiplayer scoreboard
  WBP_MJOLNIRLobby       the host's lobby (MJOLNIRLobby): map, game type,
                         players, START GAME
  WBP_MJOLNIRMapSelect   the map list, a map's details and its game types
  WBP_MJOLNIRFindGames   public games from the hub: filter chips, a sortable
                         server table, a game's details, JOIN, QUICK JOIN
  WBP_MJOLNIRPostGame    after a match: the final standings and the vote on
                         the next game (MJOLNIRLobby), and the panel that
                         reports a player (docs/player_identity.md)
  WBP_MJOLNIRMapDownload a map this PC does not have: its hub screenshot and
                         details, DOWNLOAD, and the download's progress
                         (docs/live_map_install.md)
  WBP_MJOLNIRChat        match chat: the lines above the kill feed and the
                         box you type in (MJOLNIRHud Scripts/chat.lua)
                     Both are layout only: MJOLNIRHud fills their text blocks
                     from Lua (`w.Line0:SetText(FText(...))`).
  PAL_MJOLNIR_UI    the label that puts the folder in chunk 984
                     (pakchunk984-MJOLNIRUI).
  WBP_MJOLNIRForge  the Forge HUD (mods/MJOLNIRForge), in /Game/MJOLNIR/ForgeUI
                     with its glyphs; PAL_MJOLNIR_ForgeUI puts that folder in
                     chunk 980 (pakchunk980-MJOLNIRFORGEUI).

The widget tree and graph nodes come from the MjolnirUIBuilder editor plugin
(Python can create a Widget Blueprint but not edit either). Only stock UMG
classes are used: their property layouts match the game's fork, while
CommonUI's button and text classes, and every scene component, do not
(docs/custom_ui.md).
"""
import os

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


def text_style(block, text, size, color=(1.0, 1.0, 1.0, 1.0), face="Regular"):
    block.set_editor_property("text", unreal.Text(text))
    font = block.get_editor_property("font")
    font.set_editor_property("size", size)
    font.set_editor_property("typeface_font_name", face)
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


def fresh_widget(name, parent=None, root=None):
    root = root or ROOT
    if eal.does_asset_exist(f"{root}/{name}"):
        eal.delete_asset(f"{root}/{name}")
    bp = ui.create_widget_blueprint(root, name, parent)
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


def finish(bp, name, root=None):
    if not ui.compile_widget(bp):
        fail(f"{name} does not compile")
    eal.save_loaded_asset(bp)
    unreal.log(f"MJOLNIR UI: {root or ROOT}/{name} built")


# The HUD's own glyphs (tools/ue/draw_hud_icons.py): white silhouettes the
# kill feed tints, imported as T_MJHud_<Name> under ICON_ROOT. The game's
# weapon silhouettes are not copied: MJOLNIRHud draws the game's own, through
# the game's icon material, at runtime.
ICON_ROOT = f"{ROOT}/Icons"


def import_hud_icons(art="HudIcons", root=ICON_ROOT, prefix="T_MJHud_"):
    src = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()), "Art", art)
    names = sorted(os.path.splitext(f)[0] for f in os.listdir(src) if f.lower().endswith(".png"))
    tasks = []
    for n in names:
        task = unreal.AssetImportTask()
        task.set_editor_property("filename", os.path.join(src, n + ".png"))
        task.set_editor_property("destination_path", root)
        task.set_editor_property("destination_name", prefix + n)
        task.set_editor_property("replace_existing", True)
        task.set_editor_property("automated", True)
        task.set_editor_property("save", False)
        tasks.append(task)
    assets.import_asset_tasks(tasks)
    icons = {}
    for n in names:
        tex = eal.load_asset(f"{root}/{prefix}{n}.{prefix}{n}")
        if not tex:
            fail(f"icon {n} did not import")
        tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_EDITOR_ICON)
        tex.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_UI)
        tex.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
        tex.set_editor_property("never_stream", True)
        tex.set_editor_property("srgb", True)
        eal.save_loaded_asset(tex)
        icons[n] = tex
    unreal.log(f"MJOLNIR UI: {len(icons)} icons under {root}")
    return icons


def rounded(border, radius, color, padding=0):
    """A Border drawn as a rounded box of `color`."""
    brush = border.get_editor_property("background")
    brush.set_editor_property("draw_as", unreal.SlateBrushDrawType.ROUNDED_BOX)
    brush.set_editor_property("resource_object", None)
    outline = brush.get_editor_property("outline_settings")
    outline.set_editor_property("corner_radii", unreal.Vector4(radius, radius, radius, radius))
    outline.set_editor_property("rounding_type", unreal.SlateBrushRoundingType.FIXED_RADIUS)
    outline.set_editor_property("width", 0.0)
    brush.set_editor_property("outline_settings", outline)
    border.set_editor_property("background", brush)
    border.set_editor_property("brush_color", unreal.LinearColor(*color))
    border.set_editor_property("padding", unreal.Margin(padding, padding, padding, padding))
    return border


def icon_box(bp, name, parent, width, height, collapsed=True):
    """An Image `<name>` in a SizeBox `<name>Box` of width x height. MJOLNIRHud
    sets the box's width to the picture's aspect for weapons."""
    box = sized(bp, name + "Box", parent, width=width, height=height)
    middle(box)
    widget(bp, unreal.Image, name, box.get_name())
    if collapsed:
        box.set_visibility(unreal.SlateVisibility.COLLAPSED)
    return box


def hidden_text(block):
    block.set_visibility(unreal.SlateVisibility.COLLAPSED)
    return block


# The kill feed: a pool of FEED_ROWS rows, newest at the bottom, at the left
# of the screen above the motion tracker. Every row sits at the same anchor;
# MJOLNIRHud stacks them with render translations and animates them in, up
# and out (Scripts/feed.lua), so a row never snaps when another leaves.
#
#   FeedEdge<i>        rounded Border: a gold rim when the line names you
#    FeedRow<i>        rounded Border: the row's dark fill
#     FeedAccent<i>    the coloured bar at the row's left edge
#     FeedGlyph<i>     an event's glyph (joined, left, a medal ...)
#     FeedLeadAvatar<i> the killer's hub avatar, round (hidden without one)
#     FeedLead<i>      the killer, or the player the line is about
#     FeedWeapon<i>    the weapon, the game's own silhouette, facing the victim
#     FeedMod<i>       headshot, splatter, stuck ...
#     FeedTailAvatar<i> the victim's hub avatar
#     FeedTail<i>      the victim, or what happened
#     FeedNote<i>      a quiet extra: a weapon with no picture, "x2" ...
#
# Also: Callout, the local player's medals in the middle of the screen
# (DOUBLE KILL); RespawnBox, the respawn countdown; MatchScore, the match's
# score as two bars filling toward the score to win, with the clock between.
FEED_ROWS = 7
FEED_ROW_HEIGHT = 40
SCORE_TRACK = (320, 32)
FEED_FILL = (0.012, 0.03, 0.045, 0.70)
FEED_AVATAR = 28


def round_image(image, size):
    """An Image drawn as a circle with a faint rim: a player's hub avatar,
    which Lua sets with SetBrushFromTexture (the draw type stays)."""
    brush = image.get_editor_property("brush")
    brush.set_editor_property("draw_as", unreal.SlateBrushDrawType.ROUNDED_BOX)
    outline = brush.get_editor_property("outline_settings")
    outline.set_editor_property("corner_radii", unreal.Vector4(size / 2, size / 2, size / 2, size / 2))
    outline.set_editor_property("rounding_type", unreal.SlateBrushRoundingType.HALF_HEIGHT_RADIUS)
    outline.set_editor_property("width", 1.5)
    outline.set_editor_property("color", unreal.SlateColor(unreal.LinearColor(1.0, 1.0, 1.0, 0.45)))
    brush.set_editor_property("outline_settings", outline)
    image.set_editor_property("brush", brush)


def feed_row(bp, i):
    edge = widget(bp, unreal.Border, f"FeedEdge{i}", "Root")
    rounded(edge, 8, (1.0, 0.80, 0.35, 0.0), padding=2)
    place(edge, (0.018, 0.79), (0.0, 1.0))
    edge.set_visibility(unreal.SlateVisibility.COLLAPSED)
    row = widget(bp, unreal.Border, f"FeedRow{i}", edge.get_name())
    rounded(row, 6, FEED_FILL)
    sized(bp, f"FeedRowSize{i}", row.get_name(), height=FEED_ROW_HEIGHT)
    widget(bp, unreal.HorizontalBox, f"FeedRowBox{i}", f"FeedRowSize{i}")
    accent = sized(bp, f"FeedAccentSize{i}", f"FeedRowBox{i}", width=4)
    accent.get_editor_property("slot").set_vertical_alignment(unreal.VerticalAlignment.V_ALIGN_FILL)
    rounded(widget(bp, unreal.Border, f"FeedAccent{i}", accent.get_name()), 2, (0.46, 0.79, 0.94, 1.0))
    cols = widget(bp, unreal.HorizontalBox, f"FeedCols{i}", f"FeedRowBox{i}")
    cols.get_editor_property("slot").set_padding(unreal.Margin(12, 0, 16, 0))
    cols.get_editor_property("slot").set_vertical_alignment(unreal.VerticalAlignment.V_ALIGN_CENTER)
    glyph = icon_box(bp, f"FeedGlyph{i}", cols.get_name(), 26, 26)
    glyph.get_editor_property("slot").set_padding(unreal.Margin(0, 0, 10, 0))
    face = icon_box(bp, f"FeedLeadAvatar{i}", cols.get_name(), FEED_AVATAR, FEED_AVATAR)
    face.get_editor_property("slot").set_padding(unreal.Margin(0, 0, 8, 0))
    round_image(face.get_content(), FEED_AVATAR)
    lead = widget(bp, unreal.TextBlock, f"FeedLead{i}", cols.get_name())
    text_style(lead, "", 22, WHITE, "Bold")
    middle(lead)
    weapon = icon_box(bp, f"FeedWeapon{i}", cols.get_name(), 80, 28)
    weapon.get_editor_property("slot").set_padding(unreal.Margin(14, 0, 6, 0))
    mod = icon_box(bp, f"FeedMod{i}", cols.get_name(), 24, 24)
    mod.get_editor_property("slot").set_padding(unreal.Margin(2, 0, 4, 0))
    face = icon_box(bp, f"FeedTailAvatar{i}", cols.get_name(), FEED_AVATAR, FEED_AVATAR)
    face.get_editor_property("slot").set_padding(unreal.Margin(8, 0, 0, 0))
    round_image(face.get_content(), FEED_AVATAR)
    tail = widget(bp, unreal.TextBlock, f"FeedTail{i}", cols.get_name())
    text_style(tail, "", 22, WHITE, "Bold")
    middle(tail)
    tail.get_editor_property("slot").set_padding(unreal.Margin(8, 0, 0, 0))
    note = hidden_text(widget(bp, unreal.TextBlock, f"FeedNote{i}", cols.get_name()))
    text_style(note, "", 17, GREY)
    note.get_editor_property("slot").set_padding(unreal.Margin(10, 0, 0, 0))
    middle(note)


def score_side(bp, side, color, label):
    """One team's (or player's) bar: `Score<side>Label` beside the track,
    `Score<side>Fill` the SizeBox whose width Lua sets to the share of the
    score to win, `Score<side>Accent` its ink, `Score<side>Value` the score at
    the bar's inner end. The left bar fills from the middle outward to the
    left, the right one to the right."""
    left = side == "Left"

    def tag():
        box = sized(bp, f"Score{side}LabelSize", "ScoreRow", width=170)
        middle(box)
        box.get_editor_property("slot").set_padding(unreal.Margin(0, 0, 14, 0) if left else unreal.Margin(14, 0, 0, 0))
        caption = widget(bp, unreal.TextBlock, f"Score{side}Label", box.get_name())
        text_style(caption, label, 17, color, "Bold")
        caption.set_editor_property("justification", unreal.TextJustify.RIGHT if left else unreal.TextJustify.LEFT)
        caption.set_editor_property("text_overflow_policy", unreal.TextOverflowPolicy.ELLIPSIS)
        shadowed(caption)

    # The label outside the bar: before it on the left, after it on the right.
    if left:
        tag()
    track = sized(bp, f"Score{side}Track", "ScoreRow", width=SCORE_TRACK[0], height=SCORE_TRACK[1])
    middle(track)
    frame = widget(bp, unreal.Overlay, f"Score{side}Frame", track.get_name())
    back = rounded(widget(bp, unreal.Border, f"Score{side}Back", frame.get_name()), 5, (0.01, 0.025, 0.04, 0.62))
    lane = widget(bp, unreal.HorizontalBox, f"Score{side}Lane", frame.get_name())
    for w in (back, lane):
        slot = w.get_editor_property("slot")
        slot.set_horizontal_alignment(unreal.HorizontalAlignment.H_ALIGN_FILL)
        slot.set_vertical_alignment(unreal.VerticalAlignment.V_ALIGN_FILL)
    if left:
        fill(widget(bp, unreal.Spacer, f"Score{side}Space", lane.get_name()), 1)
    bar = widget(bp, unreal.SizeBox, f"Score{side}Fill", lane.get_name())
    bar.set_width_override(0)
    bar.set_clipping(unreal.WidgetClipping.CLIP_TO_BOUNDS)
    bar.get_editor_property("slot").set_vertical_alignment(unreal.VerticalAlignment.V_ALIGN_FILL)
    rounded(widget(bp, unreal.Border, f"Score{side}Accent", bar.get_name()), 5, color)
    if not left:
        fill(widget(bp, unreal.Spacer, f"Score{side}Space", lane.get_name()), 1)
    value = widget(bp, unreal.TextBlock, f"Score{side}Value", frame.get_name())
    text_style(value, "0", 26, WHITE, "Bold")
    shadowed(value)
    slot = value.get_editor_property("slot")
    slot.set_horizontal_alignment(unreal.HorizontalAlignment.H_ALIGN_RIGHT if left else unreal.HorizontalAlignment.H_ALIGN_LEFT)
    slot.set_vertical_alignment(unreal.VerticalAlignment.V_ALIGN_CENTER)
    slot.set_padding(unreal.Margin(0, 0, 12, 0) if left else unreal.Margin(12, 0, 0, 0))
    if not left:
        tag()


def build_kill_feed(icons):
    name = "WBP_MJOLNIRKillFeed"
    bp = fresh_widget(name)
    hud_root(bp)

    # The glyphs, so they cook with the widget and are loaded with it; Lua
    # finds them by path (T_MJHud_<Name>) and never shows the palette.
    palette = widget(bp, unreal.HorizontalBox, "IconPalette", "Root")
    place(palette, (0.0, 0.0), (0.0, 0.0))
    palette.set_visibility(unreal.SlateVisibility.COLLAPSED)
    for n, tex in icons.items():
        image = widget(bp, unreal.Image, f"Icon{n}", palette.get_name())
        image.set_brush_from_texture(tex, False)

    for i in range(FEED_ROWS):
        feed_row(bp, i)

    callout = widget(bp, unreal.VerticalBox, "Callout", "Root")
    place(callout, (0.5, 0.25), (0.5, 0.5))
    callout.set_visibility(unreal.SlateVisibility.COLLAPSED)
    mark = icon_box(bp, "CalloutIcon", callout.get_name(), 64, 64, collapsed=False)
    mark.get_editor_property("slot").set_horizontal_alignment(unreal.HorizontalAlignment.H_ALIGN_CENTER)
    title = widget(bp, unreal.TextBlock, "CalloutTitle", callout.get_name())
    text_style(title, "", 50, WHITE, "Bold")
    title.set_editor_property("justification", unreal.TextJustify.CENTER)
    shadowed(title)
    gap(title, top=6)
    sub = widget(bp, unreal.TextBlock, "CalloutSub", callout.get_name())
    text_style(sub, "", 21, (0.80, 0.90, 1.0, 1.0))
    sub.set_editor_property("justification", unreal.TextJustify.CENTER)
    shadowed(sub)

    respawn = widget(bp, unreal.VerticalBox, "RespawnBox", "Root")
    place(respawn, (0.5, 0.36), (0.5, 0.5))
    respawn.set_visibility(unreal.SlateVisibility.COLLAPSED)
    caption = widget(bp, unreal.TextBlock, "RespawnLabel", respawn.get_name())
    text_style(caption, "RESPAWN IN", 22, ACCENT, "Bold")
    caption.set_editor_property("justification", unreal.TextJustify.CENTER)
    shadowed(caption)
    count = widget(bp, unreal.TextBlock, "Respawn", respawn.get_name())
    text_style(count, "", 84, WHITE, "Bold")
    count.set_editor_property("justification", unreal.TextJustify.CENTER)
    shadowed(count)

    # The match score, pinned to the top edge above the native shield bar:
    # Red / Blue for teams, YOU / LEADER in free for all.
    strip = widget(bp, unreal.VerticalBox, "MatchScore", "Root")
    place(strip, (0.5, 0.0), (0.5, 0.0), (0.0, 22.0))
    widget(bp, unreal.HorizontalBox, "ScoreRow", strip.get_name())
    score_side(bp, "Left", RED, "RED")
    mid = sized(bp, "ScoreMidSize", "ScoreRow", width=140)
    middle(mid)
    widget(bp, unreal.VerticalBox, "ScoreMid", mid.get_name())
    # The round clock (a time limit from the host's game settings); MJOLNIRHud
    # fills it and hides it when there is no limit.
    clock = widget(bp, unreal.TextBlock, "MatchClock", "ScoreMid")
    text_style(clock, "", 30, WHITE, "Bold")
    clock.set_editor_property("justification", unreal.TextJustify.CENTER)
    clock.set_visibility(unreal.SlateVisibility.COLLAPSED)
    shadowed(clock)
    target = widget(bp, unreal.HorizontalBox, "ScoreTargetLine", "ScoreMid")
    target.get_editor_property("slot").set_horizontal_alignment(unreal.HorizontalAlignment.H_ALIGN_CENTER)
    caption = widget(bp, unreal.TextBlock, "ScoreTargetLabel", target.get_name())
    text_style(caption, "TO WIN  ", 14, GREY, "Bold")
    value = widget(bp, unreal.TextBlock, "ScoreTarget", target.get_name())
    text_style(value, "0", 14, WHITE, "Bold")
    for block in (caption, value):
        shadowed(block)
    score_side(bp, "Right", BLUE, "BLUE")
    watermark(bp)
    finish(bp, name)


# The scoreboard: a title, a subtitle (the score to win, or the team scores),
# a header and SCORE_ROWS player rows of name, score, kills and deaths.
# MJOLNIRHud fills it, sorted, and hides the rows it does not use.
SCORE_ROWS = 19  # sixteen players and up to three team headings
SCORE_AVATAR = 36
COLUMNS = (("Name", "PLAYER", 5.0, unreal.TextJustify.LEFT),
           ("Score", "SCORE", 1.5, unreal.TextJustify.CENTER),
           ("Kills", "KILLS", 1.5, unreal.TextJustify.CENTER),
           ("Deaths", "DEATHS", 1.5, unreal.TextJustify.CENTER))


def columns(bp, parent, suffix, size, header, avatar=0):
    # A separate marker preserves the player's name and makes the local row
    # identifiable even without colour vision.
    marker_size = sized(bp, f"MarkerSize{suffix}", parent, width=66)
    marker = widget(bp, unreal.TextBlock, f"Marker{suffix}", marker_size.get_name())
    text_style(marker, "", 16, GOLD)
    marker.get_editor_property("slot").set_vertical_alignment(unreal.VerticalAlignment.V_ALIGN_CENTER)
    if avatar:
        # The player's hub (Discord) avatar, `Avatar<i>`, which Lua gives the
        # cached picture (docs/player_identity.md). Hidden, not collapsed, so
        # a row without one keeps its name in line with the rest; the header
        # keeps the same space empty.
        box = sized(bp, f"AvatarSize{suffix}", parent, width=avatar, height=avatar)
        box.get_editor_property("slot").set_padding(unreal.Margin(0, 0, 14, 0))
        box.get_editor_property("slot").set_vertical_alignment(unreal.VerticalAlignment.V_ALIGN_CENTER)
        if not header:
            image = widget(bp, unreal.Image, f"Avatar{suffix}", box.get_name())
            image.set_visibility(unreal.SlateVisibility.HIDDEN)
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
    columns(bp, "Header", "H", 18, True, avatar=SCORE_AVATAR)
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
        columns(bp, f"Cols{i}", str(i), 26, False, avatar=SCORE_AVATAR)
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
MAP_BUTTONS = 80
MODE_BUTTONS = 5
ROSTER_ROWS = 16
ROSTER_AVATAR = 32
GAME_ROWS = 40


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
    text_style(block, label, size, GOLD if name in ("Start", "Select", "Join", "Download") else WHITE)
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


def max_players_row(bp, parent):
    """The host's MAX PLAYERS: - and + either side of the number, which also
    steps up when clicked (MJOLNIRLobby wraps it from 16 to the fewest). Lua
    sets MaxPlayersValue, enables the steps and shows the row to the host
    only. Returns the row's events."""
    row = widget(bp, unreal.HorizontalBox, "MaxPlayersRow", parent)
    gap(row, bottom=5)
    for key, text in (("MaxPlayersDown", "-"), ("MaxPlayers", None), ("MaxPlayersUp", "+")):
        button = widget(bp, unreal.Button, key, "MaxPlayersRow")
        button_style(button)
        if text is None:
            fill(button, 1)
            button.get_editor_property("slot").set_padding(unreal.Margin(8, 0, 8, 0))
            inner = widget(bp, unreal.HorizontalBox, "MaxPlayersInner", key)
            caption = widget(bp, unreal.TextBlock, "MaxPlayersCaption", "MaxPlayersInner")
            text_style(caption, "MAX PLAYERS", 20, ACCENT)
            middle(caption)
            value = widget(bp, unreal.TextBlock, "MaxPlayersValue", "MaxPlayersInner")
            text_style(value, "16", 26, WHITE)
            value.get_editor_property("slot").set_padding(unreal.Margin(14, 0, 0, 0))
            middle(value)
        else:
            text_style(widget(bp, unreal.TextBlock, key + "Label", key), text, 26, WHITE)
    return [("MaxPlayersDown", "OnClicked", "maxdown"), ("MaxPlayers", "OnClicked", "maxplayers"),
            ("MaxPlayersUp", "OnClicked", "maxup")]


def build_lobby():
    """The host's lobby: the map and game type, the players, START,
    INVITE FRIENDS (the game's own Friends screen, cross-platform), PRIVATE /
    PUBLIC GAME and MAX PLAYERS."""
    name = "WBP_MJOLNIRLobby"
    bp = fresh_widget(name, unreal.CommonActivatableWidget)
    screen_canvas(bp)
    screen_header(bp, "MULTIPLAYER", "CUSTOM GAME")

    menu = sized(bp, "MenuSize", "Root", width=470)
    place(menu, (0.06, 0.28), (0.0, 0.0))
    widget(bp, unreal.VerticalBox, "Menu", "MenuSize")
    gap(rule(bp, "MenuRule", "Menu", ACCENT, 2), bottom=12)
    events = []
    # Listing: the host's game private (fireteam and invites only) or
    # public (listed on the hub for FIND GAMES); Lua sets its label.
    # GameSettings: the host's game settings (WBP_MJOLNIRGameSettings).
    for key, label in (("Start", "START GAME"), ("Invite", "INVITE FRIENDS"), ("ChangeMap", "CHANGE MAP"),
                       ("GameType", "GAME TYPE"), ("GameSettings", "GAME SETTINGS"), ("Listing", "PRIVATE GAME"),
                       ("FindGames", "FIND GAMES"), ("Back", "BACK")):
        gap(menu_button(bp, key, label, "Menu", size=26), bottom=5)
        events.append((key, "OnClicked", key.lower()))
        if key == "Listing":
            events += max_players_row(bp, "Menu")

    card = panel(bp, "Card", "Root")
    place(card, (0.28, 0.28), (0.0, 0.0))
    sized(bp, "CardSize", "Card", width=840)
    widget(bp, unreal.VerticalBox, "CardStack", "CardSize")
    gap(rule(bp, "MapRule", "CardStack", ACCENT, 2), bottom=24)
    # The map's hub screenshot beside its kicker and title.
    head = widget(bp, unreal.HorizontalBox, "MapHead", "CardStack")
    head_text = widget(bp, unreal.VerticalBox, "MapHeadText", "MapHead")
    fill(head_text, 1)
    label = widget(bp, unreal.TextBlock, "MapKicker", "MapHeadText")
    text_style(label, "MISSION AREA", 18, ACCENT)
    gap(label, bottom=12)
    map_title = widget(bp, unreal.TextBlock, "MapTitle", "MapHeadText")
    text_style(map_title, "BLOOD GULCH", 46, WHITE)
    wrapped(map_title)
    shot = map_image(bp, "MapImage", "MapHead", 320, 180)
    shot.get_editor_property("slot").set_padding(unreal.Margin(24, 0, 0, 0))
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
    # The game settings away from the defaults, one per line; Lua hides the
    # box when there are none.
    rules_box = widget(bp, unreal.VerticalBox, "RulesBox", "CardStack")
    gap(rules_box, top=24)
    rules_box.set_visibility(unreal.SlateVisibility.COLLAPSED)
    gap(rule(bp, "RulesRule", "RulesBox"), bottom=18)
    text_style(widget(bp, unreal.TextBlock, "RulesKicker", "RulesBox"), "GAME SETTINGS", 18, ACCENT)
    rules = widget(bp, unreal.TextBlock, "Rules", "RulesBox")
    text_style(rules, "", 22, WHITE)
    wrapped(rules)
    gap(rules, top=10)

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
            # A player: their hub avatar (`<group>PlayerAvatar<i>`, hidden
            # until Lua has the picture) and name. Lua shows and hides the
            # whole row (`<group>PlayerRow<i>`).
            line = widget(bp, unreal.HorizontalBox, f"{group}PlayerRow{i}", group + "Roster")
            line.get_editor_property("slot").set_padding(unreal.Margin(14, 8, 14, 4))
            line.set_visibility(unreal.SlateVisibility.COLLAPSED)
            face = sized(bp, f"{group}PlayerAvatarSize{i}", line.get_name(), width=ROSTER_AVATAR, height=ROSTER_AVATAR)
            face.get_editor_property("slot").set_padding(unreal.Margin(0, 0, 12, 0))
            middle(face)
            image = widget(bp, unreal.Image, f"{group}PlayerAvatar{i}", face.get_name())
            image.set_visibility(unreal.SlateVisibility.HIDDEN)
            row = widget(bp, unreal.TextBlock, f"{group}Player{i}", line.get_name())
            text_style(row, "", 24, WHITE)
            row.set_editor_property("text_overflow_policy", unreal.TextOverflowPolicy.ELLIPSIS)
            middle(row)
            fill(row, 1)
    hint = widget(bp, unreal.TextBlock, "TeamHint", "RosterStack")
    text_style(hint, "", 19, GREY)
    wrapped(hint)
    gap(hint, top=12)
    # The main menu pushes this screen without Lua, but only MJOLNIRLobby
    # answers its buttons. Its first fill replaces this line (and its
    # colour), so the warning stays only when the mods are not running.
    # The usual cause is UE4SS giving up at startup (UE4SS.log ends in
    # "Fatal Error: AOB scans could not be completed"), which a restart
    # often gets past.
    text_style(footer(bp), "MJOLNIR MODS DID NOT START, SO THESE BUTTONS DO NOTHING   /   RESTART THE GAME. "
               "IF IT KEEPS HAPPENING, CHECK MJOLNIRLOBBY IS ON IN THE LAUNCHER AND SEND US ue4ss\\UE4SS.log",
               22, GOLD)

    if not ui.compile_widget(bp):
        fail(f"{name} does not compile (widget tree)")
    if not ui.add_string_function(bp, "MJ_Event", "Name", ""):
        fail("MJ_Event")
    bind_events(bp, events)
    finish_screen(bp, name)


def build_map_select():
    """Every installed map and the hub's maps not installed (MJOLNIRLobby
    marks those DOWNLOAD), filter chips for the game, the source and
    installed maps, a map's details and game types, and SELECT."""
    name = "WBP_MJOLNIRMapSelect"
    bp = fresh_widget(name, unreal.CommonActivatableWidget)
    screen_canvas(bp)
    screen_header(bp, "SELECT MAP", "CUSTOM GAME")
    events = []

    # Cycling chips (a caption and a value), as FIND GAMES' are; the count of
    # rows beside them. Lua fills the values and colours the chips.
    bar = widget(bp, unreal.HorizontalBox, "Filters", "Root")
    place(bar, (0.06, 0.205), (0.0, 0.0))
    for key, label in (("Game", "GAME"), ("Source", "SOURCE"), ("Installed", "SHOW")):
        chip = widget(bp, unreal.Button, f"Filter{key}", "Filters")
        flat_style(chip, (0.02, 0.05, 0.075, 0.55), (0.12, 0.32, 0.43, 0.8), (0.20, 0.48, 0.60, 0.95),
                   padding=(18, 11, 20, 11))
        chip.get_editor_property("slot").set_padding(unreal.Margin(0, 0, 10, 0))
        inner = widget(bp, unreal.HorizontalBox, f"Filter{key}Row", chip.get_name())
        unpadded(inner)
        caption = widget(bp, unreal.TextBlock, f"Filter{key}Caption", inner.get_name())
        text_style(caption, label, 17, ACCENT)
        middle(caption)
        value = widget(bp, unreal.TextBlock, f"Filter{key}Value", inner.get_name())
        text_style(value, "ALL", 21, WHITE)
        value.get_editor_property("slot").set_padding(unreal.Margin(12, 0, 0, 0))
        middle(value)
        events.append((chip.get_name(), "OnClicked", f"filter:{key.lower()}"))
    count = widget(bp, unreal.TextBlock, "ListCount", "Filters")
    text_style(count, "MAPS", 18, GREY)
    count.get_editor_property("slot").set_padding(unreal.Margin(20, 0, 0, 0))
    middle(count)

    list_panel = panel(bp, "ListPanel", "Root", padding=(16, 16, 16, 16))
    place(list_panel, (0.06, 0.265), (0.0, 0.0))
    sized(bp, "ListSize", "ListPanel", width=520, height=740)
    widget(bp, unreal.ScrollBox, "MapList", "ListSize")
    for i in range(MAP_BUTTONS):
        gap(menu_button(bp, f"Map{i}", "", "MapList", size=25), bottom=5)
        events += [(f"Map{i}", "OnClicked", f"map:{i}"), (f"Map{i}", "OnHovered", f"hover:{i}")]

    details = panel(bp, "Details", "Root")
    place(details, (0.32, 0.265), (0.0, 0.0))
    sized(bp, "DetailsSize", "Details", width=1430)
    widget(bp, unreal.HorizontalBox, "DetailsColumns", "DetailsSize")
    sized(bp, "DetailsLeftSize", "DetailsColumns", width=780)
    widget(bp, unreal.VerticalBox, "DetailsStack", "DetailsLeftSize")
    side = widget(bp, unreal.VerticalBox, "DetailsSide", "DetailsColumns")
    side.get_editor_property("slot").set_padding(unreal.Margin(40, 0, 0, 0))
    gap(rule(bp, "SideRule", "DetailsSide", ACCENT, 2), bottom=24)
    map_image(bp, "MapImage", "DetailsSide", 600, 338)
    meta_size = sized(bp, "MapMetaSize", "DetailsSide", width=600)
    gap(meta_size, top=14)
    meta = widget(bp, unreal.TextBlock, "MapMeta", "MapMetaSize")
    text_style(meta, "", 21, GREY)
    wrapped(meta)
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


def flat_style(button, normal, hovered, pressed, padding=(0, 0, 0, 0)):
    """A tinted, imageless button style (rows, column headers, filter chips)."""
    style = button.get_editor_property("widget_style")
    for state, rgba in (("normal", normal), ("hovered", hovered), ("pressed", pressed),
                        ("disabled", (0.03, 0.04, 0.05, 0.25))):
        brush = style.get_editor_property(state)
        brush.set_editor_property("resource_object", None)
        brush.set_editor_property("draw_as", unreal.SlateBrushDrawType.IMAGE)
        brush.set_editor_property("tint_color", unreal.SlateColor(unreal.LinearColor(*rgba)))
        style.set_editor_property(state, brush)
    style.set_editor_property("normal_padding", unreal.Margin(*padding))
    style.set_editor_property("pressed_padding", unreal.Margin(*padding))
    button.set_editor_property("widget_style", style)


def fill(w, value):
    w.get_editor_property("slot").set_size(unreal.SlateChildSize(value, unreal.SlateSizeRule.FILL))


def middle(w):
    w.get_editor_property("slot").set_vertical_alignment(unreal.VerticalAlignment.V_ALIGN_CENTER)


def swatch(bp, name, parent, width, height, color):
    """A solid block of colour: `<name>` is the Border Lua recolours."""
    box = sized(bp, name + "Size", parent, width=width, height=height)
    ink = widget(bp, unreal.Border, name, box.get_name())
    ink.set_editor_property("brush_color", unreal.LinearColor(*color))
    ink.set_editor_property("padding", unreal.Margin(0))
    return box


def map_image(bp, name, parent, width, height):
    """A map's hub screenshot, `width` by `height`: `<name>` is the Image Lua
    gives the cached cover (KismetRenderingLibrary.ImportFileAsTexture2D) and
    shows; `<name>Note` the line shown in its place until then. The image is
    hidden, not collapsed, so the box keeps its size and nothing moves when
    the picture arrives."""
    box = sized(bp, name + "Size", parent, width=width, height=height)
    frame = widget(bp, unreal.Overlay, name + "Frame", box.get_name())
    back = widget(bp, unreal.Border, name + "Back", frame.get_name())
    back.set_editor_property("brush_color", unreal.LinearColor(0.0, 0.0, 0.0, 0.45))
    image = widget(bp, unreal.Image, name, frame.get_name())
    image.set_visibility(unreal.SlateVisibility.HIDDEN)
    for w in (back, image):
        slot = w.get_editor_property("slot")
        slot.set_horizontal_alignment(unreal.HorizontalAlignment.H_ALIGN_FILL)
        slot.set_vertical_alignment(unreal.VerticalAlignment.V_ALIGN_FILL)
    note = widget(bp, unreal.TextBlock, name + "Note", frame.get_name())
    text_style(note, "", 18, GREY)
    note.set_editor_property("justification", unreal.TextJustify.CENTER)
    slot = note.get_editor_property("slot")
    slot.set_horizontal_alignment(unreal.HorizontalAlignment.H_ALIGN_CENTER)
    slot.set_vertical_alignment(unreal.VerticalAlignment.V_ALIGN_CENTER)
    return box


# The server table's columns: key, heading, width (None: the rest), centred.
# Header and row cells are fixed-width boxes with the same inner padding, and
# every button's content slot is unpadded, so the columns line up exactly
# whatever the text in them; the last column takes what is left (the rows
# give some of it to the scroll bar).
GAME_COLUMNS = (("Name", "SERVER", 380, False), ("Map", "MAP", 290, False),
                ("Type", "GAME TYPE", 300, False), ("Players", "PLAYERS", 150, True),
                ("Ping", "PING", 170, False), ("State", "STATUS", None, False))
CELL_PAD = 14
SCROLLBAR = (6, 8)   # the list's scroll bar, when it shows: thickness, gap before it
FILTERS = (("Type", "GAME TYPE", True), ("Map", "MAP", True), ("Full", "HIDE FULL", False),
           ("Match", "HIDE IN MATCH", False), ("Have", "MAPS I HAVE", False))
DIM = (0.20, 0.30, 0.36, 1.0)
GREEN = (0.45, 0.88, 0.55, 1.0)
CAPACITY_PIPS = 16


def column(bp, name, parent, width):
    """A table cell: `width` wide (or the rest of the row), clipped, so a long
    value never runs into the next column."""
    if width:
        box = sized(bp, name, parent, width=width)
    else:
        box = widget(bp, unreal.SizeBox, name, parent)
        fill(box, 1)
    box.set_clipping(unreal.WidgetClipping.CLIP_TO_BOUNDS)
    return box


def unpadded(w):
    """No padding from the slot a button (or size box) gives its content."""
    w.get_editor_property("slot").set_padding(unreal.Margin(0, 0, 0, 0))


def build_find_games():
    """Public games from the hub as a server table: filter chips, sortable
    columns, rows that line up, and the chosen game's details with JOIN and
    QUICK JOIN (docs/multiplayer_servers.md). MJOLNIRLobby fills every text
    and colour.

    Names an older MJOLNIRLobby relies on are kept (Game<i>, Game<i>Label,
    GameKicker, GameTitle, GameDetails, Join, Refresh, Back, Empty, Status),
    so a newer runtime pack still works with it."""
    name = "WBP_MJOLNIRFindGames"
    bp = fresh_widget(name, unreal.CommonActivatableWidget)
    screen_canvas(bp)
    screen_header(bp, "FIND GAMES", "MULTIPLAYER")
    events = []

    # Filters: two cycling chips (a caption and a value) and three toggles
    # (a check square and a label). Lua colours the squares and values.
    bar = widget(bp, unreal.HorizontalBox, "Filters", "Root")
    place(bar, (0.06, 0.205), (0.0, 0.0))
    for key, label, cycles in FILTERS:
        chip = widget(bp, unreal.Button, f"Filter{key}", "Filters")
        flat_style(chip, (0.02, 0.05, 0.075, 0.55), (0.12, 0.32, 0.43, 0.8), (0.20, 0.48, 0.60, 0.95),
                   padding=(18, 11, 20, 11))
        chip.get_editor_property("slot").set_padding(unreal.Margin(0, 0, 10, 0))
        inner = widget(bp, unreal.HorizontalBox, f"Filter{key}Row", chip.get_name())
        unpadded(inner)
        if cycles:
            caption = widget(bp, unreal.TextBlock, f"Filter{key}Caption", inner.get_name())
            text_style(caption, label, 17, ACCENT)
            middle(caption)
            value = widget(bp, unreal.TextBlock, f"Filter{key}Value", inner.get_name())
            text_style(value, "ALL", 21, WHITE)
            value.get_editor_property("slot").set_padding(unreal.Margin(12, 0, 0, 0))
            middle(value)
        else:
            check = swatch(bp, f"Filter{key}Check", inner.get_name(), 16, 16, DIM)
            middle(check)
            text = widget(bp, unreal.TextBlock, f"Filter{key}Label", inner.get_name())
            text_style(text, label, 20, WHITE)
            text.get_editor_property("slot").set_padding(unreal.Margin(12, 0, 0, 0))
            middle(text)
        events.append((chip.get_name(), "OnClicked", f"filter:{key.lower()}"))

    # The table.
    table = panel(bp, "ListPanel", "Root", padding=(0, 0, 0, 0))
    place(table, (0.06, 0.265), (0.0, 0.0))
    sized(bp, "ListSize", "ListPanel", width=1520)
    widget(bp, unreal.VerticalBox, "ListStack", "ListSize")
    rule(bp, "ListRule", "ListStack", ACCENT, 2)
    caption = widget(bp, unreal.HorizontalBox, "ListCaption", "ListStack")
    caption.get_editor_property("slot").set_padding(unreal.Margin(24, 18, 24, 6))
    count = widget(bp, unreal.TextBlock, "ListCount", "ListCaption")
    text_style(count, "PUBLIC GAMES", 18, ACCENT)
    fill(count, 1)
    order = widget(bp, unreal.TextBlock, "ListOrder", "ListCaption")
    text_style(order, "", 18, GREY)

    header = widget(bp, unreal.HorizontalBox, "TableHeader", "ListStack")
    header.get_editor_property("slot").set_padding(unreal.Margin(10, 6, 10, 6))
    sized(bp, "TableHeaderStripe", "TableHeader", width=4)
    for key, title, width, centred in GAME_COLUMNS:
        box = column(bp, f"Head{key}Size", "TableHeader", width)
        cell = widget(bp, unreal.Button, f"Head{key}", box.get_name())
        unpadded(cell)
        flat_style(cell, (0, 0, 0, 0), (0.12, 0.32, 0.43, 0.45), (0.20, 0.48, 0.60, 0.7),
                   padding=(CELL_PAD, 8, CELL_PAD, 8))
        inner = widget(bp, unreal.HorizontalBox, f"Head{key}Row", cell.get_name())
        unpadded(inner)
        if centred:
            inner.get_editor_property("slot").set_horizontal_alignment(unreal.HorizontalAlignment.H_ALIGN_CENTER)
        else:
            inner.get_editor_property("slot").set_horizontal_alignment(unreal.HorizontalAlignment.H_ALIGN_LEFT)
        label = widget(bp, unreal.TextBlock, f"Head{key}Label", inner.get_name())
        text_style(label, title, 17, GREY)
        middle(label)
        arrow = widget(bp, unreal.TextBlock, f"Head{key}Sort", inner.get_name())
        text_style(arrow, "", 14, GOLD)
        arrow.get_editor_property("slot").set_padding(unreal.Margin(8, 0, 0, 0))
        middle(arrow)
        events.append((cell.get_name(), "OnClicked", f"sort:{key.lower()}"))
    sized(bp, "TableHeaderScrollGap", "TableHeader", width=sum(SCROLLBAR))
    rule(bp, "TableHeaderRule", "ListStack")

    rows = sized(bp, "RowsSize", "ListStack", height=700)
    rows.get_editor_property("slot").set_padding(unreal.Margin(10, 8, 10, 10))
    scroll = widget(bp, unreal.ScrollBox, "GameList", "RowsSize")
    for prop, value in (("scrollbar_thickness", unreal.Vector2D(SCROLLBAR[0], SCROLLBAR[0])),
                        ("scrollbar_padding", unreal.Margin(SCROLLBAR[1], 0, 0, 0)),
                        ("scroll_when_focus_changes", unreal.ScrollWhenFocusChanges.ANIMATED_SCROLL)):
        try:
            scroll.set_editor_property(prop, value)
        except Exception as e:  # an engine without the property: default look
            unreal.log_warning(f"MJOLNIR UI: GameList.{prop}: {e}")
    # A flat accent thumb on a faint track, instead of the stock white bar.
    try:
        bar = scroll.get_editor_property("widget_bar_style")
        for prop, rgba in (("normal_thumb_image", (0.46, 0.79, 0.94, 0.45)),
                           ("hovered_thumb_image", (0.46, 0.79, 0.94, 0.8)),
                           ("dragged_thumb_image", (0.46, 0.79, 0.94, 1.0)),
                           ("vertical_background_image", (0.0, 0.0, 0.0, 0.3)),
                           ("vertical_top_slot_image", (0.0, 0.0, 0.0, 0.3)),
                           ("vertical_bottom_slot_image", (0.0, 0.0, 0.0, 0.3))):
            brush = bar.get_editor_property(prop)
            brush.set_editor_property("resource_object", None)
            brush.set_editor_property("draw_as", unreal.SlateBrushDrawType.IMAGE)
            brush.set_editor_property("tint_color", unreal.SlateColor(unreal.LinearColor(*rgba)))
            bar.set_editor_property(prop, brush)
        scroll.set_editor_property("widget_bar_style", bar)
    except Exception as e:
        unreal.log_warning(f"MJOLNIR UI: GameList scroll bar style: {e}")
    empty = widget(bp, unreal.TextBlock, "Empty", "GameList")
    text_style(empty, "", 26, GREY)
    wrapped(empty)
    empty.get_editor_property("slot").set_padding(unreal.Margin(24, 24, 24, 24))

    for i in range(GAME_ROWS):
        row = widget(bp, unreal.Button, f"Game{i}", "GameList")
        flat_style(row, (0.02, 0.05, 0.075, 0.42), (0.08, 0.22, 0.30, 0.6), (0.14, 0.34, 0.44, 0.85))
        row.set_visibility(unreal.SlateVisibility.COLLAPSED)
        gap(row, bottom=3)
        cols = widget(bp, unreal.HorizontalBox, f"GameCols{i}", row.get_name())
        unpadded(cols)
        cols.get_editor_property("slot").set_horizontal_alignment(unreal.HorizontalAlignment.H_ALIGN_FILL)
        cols.get_editor_property("slot").set_vertical_alignment(unreal.VerticalAlignment.V_ALIGN_FILL)
        stripe = sized(bp, f"GameStripeSize{i}", cols.get_name(), width=4)
        ink = widget(bp, unreal.Border, f"GameStripe{i}", stripe.get_name())
        ink.set_editor_property("brush_color", unreal.LinearColor(*ACCENT))
        for key, _, width, centred in GAME_COLUMNS:
            box = column(bp, f"Game{key}Size{i}", cols.get_name(), width)
            middle(box)
            cell = widget(bp, unreal.VerticalBox, f"Game{key}Cell{i}", box.get_name())
            cell.get_editor_property("slot").set_padding(unreal.Margin(CELL_PAD, 9, CELL_PAD, 9))
            justify = unreal.TextJustify.CENTER if centred else unreal.TextJustify.LEFT
            if key == "Ping":
                line = widget(bp, unreal.HorizontalBox, f"GamePingLine{i}", cell.get_name())
                for b, height in enumerate((8, 13, 18, 23)):
                    bar = swatch(bp, f"GamePing{i}Bar{b}", line.get_name(), 5, height, DIM)
                    bar.get_editor_property("slot").set_vertical_alignment(unreal.VerticalAlignment.V_ALIGN_BOTTOM)
                    bar.get_editor_property("slot").set_padding(unreal.Margin(0, 0, 3, 0))
                value = widget(bp, unreal.TextBlock, f"GamePing{i}", line.get_name())
                text_style(value, "", 21, WHITE)
                value.get_editor_property("slot").set_padding(unreal.Margin(10, 0, 0, 0))
                value.get_editor_property("slot").set_vertical_alignment(unreal.VerticalAlignment.V_ALIGN_BOTTOM)
                continue
            # The server name's block keeps the old row label's name.
            main = widget(bp, unreal.TextBlock, f"Game{i}Label" if key == "Name" else f"Game{key}{i}",
                          cell.get_name())
            text_style(main, "", {"Name": 24, "Players": 24, "State": 20}.get(key, 22), WHITE)
            main.set_editor_property("justification", justify)
            main.set_editor_property("text_overflow_policy", unreal.TextOverflowPolicy.ELLIPSIS)
            note = widget(bp, unreal.TextBlock, f"Game{key}Note{i}", cell.get_name())
            text_style(note, "", 16, GREY)
            note.set_editor_property("justification", justify)
            note.set_editor_property("text_overflow_policy", unreal.TextOverflowPolicy.ELLIPSIS)
            note.get_editor_property("slot").set_padding(unreal.Margin(0, 3, 0, 0))
        events += [(f"Game{i}", "OnClicked", f"game:{i}"), (f"Game{i}", "OnHovered", f"hover:{i}"),
                   (f"Game{i}", "OnUnhovered", f"unhover:{i}")]

    # The chosen game.
    details = panel(bp, "Details", "Root")
    place(details, (0.94, 0.265), (1.0, 0.0))
    sized(bp, "DetailsSize", "Details", width=640)
    widget(bp, unreal.VerticalBox, "DetailsStack", "DetailsSize")
    gap(rule(bp, "DetailsRule", "DetailsStack", ACCENT, 2), bottom=24)
    # The kicker, title and host beside the map's screenshot, which adds no
    # height: the panel already reaches the footer with a long game.
    head = widget(bp, unreal.HorizontalBox, "GameHead", "DetailsStack")
    gap(head, bottom=22)
    head_text = widget(bp, unreal.VerticalBox, "GameHeadText", "GameHead")
    fill(head_text, 1)
    kicker = widget(bp, unreal.TextBlock, "GameKicker", "GameHeadText")
    text_style(kicker, "", 18, ACCENT)
    gap(kicker, bottom=10)
    title = widget(bp, unreal.TextBlock, "GameTitle", "GameHeadText")
    text_style(title, "", 42, WHITE)
    wrapped(title)
    host = widget(bp, unreal.TextBlock, "GameHost", "GameHeadText")
    text_style(host, "", 21, GREY)
    gap(host, top=6)
    shot = map_image(bp, "MapImage", "GameHead", 192, 108)
    shot.get_editor_property("slot").set_padding(unreal.Margin(16, 0, 0, 0))
    gap(rule(bp, "InfoRule", "DetailsStack"), bottom=14)
    for key, label in (("Map", "MAP"), ("Type", "GAME TYPE"), ("Players", "PLAYERS"), ("Ping", "PING"),
                       ("Region", "REGION"), ("Version", "VERSION")):
        line = widget(bp, unreal.HorizontalBox, f"Info{key}", "DetailsStack")
        gap(line, top=7, bottom=7)
        size = sized(bp, f"Info{key}LabelSize", line.get_name(), width=190)
        middle(size)
        text_style(widget(bp, unreal.TextBlock, f"Info{key}Label", size.get_name()), label, 17, GREY)
        value = widget(bp, unreal.TextBlock, f"Info{key}Value", line.get_name())
        text_style(value, "", 24, WHITE)
        value.set_editor_property("text_overflow_policy", unreal.TextOverflowPolicy.ELLIPSIS)
        fill(value, 1)
        middle(value)
        if key == "Players":
            # One pip per slot: filled for each player, hidden past the cap.
            pips = widget(bp, unreal.HorizontalBox, "Pips", "DetailsStack")
            pips.get_editor_property("slot").set_padding(unreal.Margin(190, 2, 0, 8))
            for p in range(CAPACITY_PIPS):
                pip = swatch(bp, f"Pip{p}", "Pips", 20, 8, DIM)
                pip.get_editor_property("slot").set_padding(unreal.Margin(0, 0, 5, 0))
    info = widget(bp, unreal.TextBlock, "GameDetails", "DetailsStack")
    text_style(info, "", 21, GOLD)
    wrapped(info)
    gap(info, top=14, bottom=22)
    gap(rule(bp, "ActionsRule", "DetailsStack"), bottom=18)
    join = menu_button(bp, "Join", "JOIN", "DetailsStack", size=30)
    events.append(("Join", "OnClicked", "join"))
    gap(join, bottom=12)
    actions = widget(bp, unreal.HorizontalBox, "Actions", "DetailsStack")
    for key, label, event in (("QuickJoin", "QUICK JOIN", "quickjoin"), ("Refresh", "REFRESH", "refresh"),
                              ("Back", "BACK", "back")):
        button = menu_button(bp, key, label, actions.get_name(), size=22)
        button.get_editor_property("slot").set_padding(unreal.Margin(0, 0, 12, 0))
        events.append((key, "OnClicked", event))
    footer(bp)

    if not ui.compile_widget(bp):
        fail(f"{name} does not compile (widget tree)")
    if not ui.add_string_function(bp, "MJ_Event", "Name", ""):
        fail("MJ_Event")
    bind_events(bp, events)
    finish_screen(bp, name)


VOTE_OPTIONS = 4
RESULT_ROWS = 18  # sixteen players and the two team headings
RESULT_AVATAR = 34


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
    columns(bp, "TableHeader", "H", 18, True, avatar=RESULT_AVATAR)
    sized(bp, "RowsSize", "ResultsStack", height=470)
    widget(bp, unreal.ScrollBox, "Rows", "RowsSize")
    events = []
    for i in range(RESULT_ROWS):
        row = widget(bp, unreal.Border, f"Row{i}", "Rows")
        row.set_editor_property("padding", unreal.Margin(0))
        row.set_visibility(unreal.SlateVisibility.COLLAPSED)
        # The whole row is a button: clicking another player opens the
        # report panel on them (MJ_Event "row:<i>"). Lua disables a row
        # with no one to report (a heading, yourself, no hub account).
        button = widget(bp, unreal.Button, f"RowButton{i}", f"Row{i}")
        flat_style(button, (0, 0, 0, 0), (0.46, 0.79, 0.94, 0.16), (0.46, 0.79, 0.94, 0.28))
        button.get_editor_property("slot").set_padding(unreal.Margin(0))
        button.get_editor_property("slot").set_horizontal_alignment(unreal.HorizontalAlignment.H_ALIGN_FILL)
        events.append((f"RowButton{i}", "OnClicked", f"row:{i}"))
        layout = widget(bp, unreal.HorizontalBox, f"RowLayout{i}", f"RowButton{i}")
        layout.get_editor_property("slot").set_padding(unreal.Margin(0))
        layout.get_editor_property("slot").set_horizontal_alignment(unreal.HorizontalAlignment.H_ALIGN_FILL)
        sized(bp, f"StripeSize{i}", f"RowLayout{i}", width=3)
        widget(bp, unreal.Border, f"Stripe{i}", f"StripeSize{i}")
        content = widget(bp, unreal.HorizontalBox, f"Cols{i}", f"RowLayout{i}")
        content.get_editor_property("slot").set_size(unreal.SlateChildSize(1, unreal.SlateSizeRule.FILL))
        content.get_editor_property("slot").set_padding(unreal.Margin(13, 5, 16, 5))
        columns(bp, f"Cols{i}", str(i), 24, False, avatar=RESULT_AVATAR)
    hint = widget(bp, unreal.TextBlock, "ResultsHint", "ResultsStack")
    text_style(hint, "SELECT A PLAYER TO REPORT THEM", 17, GREY)
    gap(hint, top=12)

    vote = panel(bp, "Vote", "Root")
    place(vote, (0.94, 0.28), (1.0, 0.0))
    sized(bp, "VoteSize", "Vote", width=780)
    widget(bp, unreal.VerticalBox, "VoteStack", "VoteSize")
    gap(rule(bp, "VoteRule", "VoteStack", ACCENT, 2), bottom=24)
    vote_head = widget(bp, unreal.HorizontalBox, "VoteHead", "VoteStack")
    gap(vote_head, bottom=22)
    vote_text = widget(bp, unreal.VerticalBox, "VoteHeadText", "VoteHead")
    fill(vote_text, 1)
    heading = widget(bp, unreal.TextBlock, "VoteKicker", "VoteHeadText")
    text_style(heading, "NEXT GAME", 18, ACCENT)
    gap(heading, bottom=12)
    timer = widget(bp, unreal.TextBlock, "VoteTimer", "VoteHeadText")
    text_style(timer, "VOTE", 34, WHITE)
    wrapped(timer)
    shot = map_image(bp, "MapImage", "VoteHead", 288, 162)
    shot.get_editor_property("slot").set_padding(unreal.Margin(20, 0, 0, 0))
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
    events += report_panel(bp)

    if not ui.compile_widget(bp):
        fail(f"{name} does not compile (widget tree)")
    if not ui.add_string_function(bp, "MJ_Event", "Name", ""):
        fail("MJ_Event")
    bind_events(bp, events)
    finish_screen(bp, name)


# Why a player is reported, in the order of the panel's buttons; the keys are
# the hub's (POST /players/reports).
REPORT_REASONS = (("cheating", "CHEATING"), ("betraying", "BETRAYING"), ("harassment", "HARASSMENT"),
                  ("griefing", "GRIEFING / AFK"), ("quitting", "QUITTING"), ("name", "NAME OR AVATAR"),
                  ("other", "OTHER"))


def report_panel(bp):
    """The post-game screen's report panel, over the middle of the screen and
    collapsed until a player row is clicked (docs/player_identity.md): who,
    a reason (`Reason<k>`, MJ_Event "reason:<k>"), what happened
    (`ReportText`, a multi-line text box Lua reads), `ReportStatus`, and SEND
    REPORT / CANCEL. Returns its events."""
    report = panel(bp, "Report", "Root", alpha=0.97, padding=(44, 34, 44, 34))
    place(report, (0.5, 0.5), (0.5, 0.5))
    report.get_editor_property("slot").set_z_order(20)
    report.set_visibility(unreal.SlateVisibility.COLLAPSED)
    sized(bp, "ReportSize", "Report", width=1180)
    widget(bp, unreal.VerticalBox, "ReportStack", "ReportSize")
    gap(rule(bp, "ReportRule", "ReportStack", RED, 2), bottom=22)
    kicker = widget(bp, unreal.TextBlock, "ReportKicker", "ReportStack")
    text_style(kicker, "REPORT A PLAYER", 18, RED)
    gap(kicker, bottom=16)
    who = widget(bp, unreal.HorizontalBox, "ReportWho", "ReportStack")
    gap(who, bottom=24)
    face = sized(bp, "ReportAvatarSize", "ReportWho", width=84, height=84)
    face.get_editor_property("slot").set_padding(unreal.Margin(0, 0, 22, 0))
    image = widget(bp, unreal.Image, "ReportAvatar", face.get_name())
    image.set_visibility(unreal.SlateVisibility.HIDDEN)
    names = widget(bp, unreal.VerticalBox, "ReportNames", "ReportWho")
    middle(names)
    fill(names, 1)
    text_style(widget(bp, unreal.TextBlock, "ReportName", "ReportNames"), "", 40, WHITE)
    count = widget(bp, unreal.TextBlock, "ReportCount", "ReportNames")
    text_style(count, "", 20, GREY)
    gap(count, top=6)
    text_style(widget(bp, unreal.TextBlock, "ReasonKicker", "ReportStack"), "WHY", 18, ACCENT)
    events = []
    keys = [key for key, _ in REPORT_REASONS]
    for r, reasons in enumerate((REPORT_REASONS[:4], REPORT_REASONS[4:])):
        line = widget(bp, unreal.HorizontalBox, f"ReasonRow{r}", "ReportStack")
        gap(line, top=10 if r == 0 else 8)
        for key, label in reasons:
            k = keys.index(key)
            button = menu_button(bp, f"Reason{k}", label, line.get_name(), size=22)
            fill(button, 1)
            button.get_editor_property("slot").set_padding(unreal.Margin(0, 0, 10, 0))
            events.append((f"Reason{k}", "OnClicked", f"reason:{k}"))
        if len(reasons) < 4:
            spacer = widget(bp, unreal.Spacer, f"ReasonFill{r}", line.get_name())
            fill(spacer, 4 - len(reasons))
    detail = widget(bp, unreal.TextBlock, "DetailKicker", "ReportStack")
    text_style(detail, "WHAT HAPPENED", 18, ACCENT)
    gap(detail, top=24, bottom=10)
    box = sized(bp, "ReportTextSize", "ReportStack", height=190)
    text = widget(bp, unreal.MultiLineEditableTextBox, "ReportText", box.get_name())
    text.set_editor_property("hint_text",
                             unreal.Text("Tell the moderators what happened (optional, up to 1000 characters)"))
    try:
        style = text.get_editor_property("widget_style")
        for state in ("background_image_normal", "background_image_hovered", "background_image_focused",
                      "background_image_read_only"):
            brush = style.get_editor_property(state)
            brush.set_editor_property("resource_object", None)
            brush.set_editor_property("draw_as", unreal.SlateBrushDrawType.IMAGE)
            brush.set_editor_property("tint_color", unreal.SlateColor(unreal.LinearColor(
                0.0, 0.03, 0.05, 0.95 if state == "background_image_focused" else 0.8)))
            style.set_editor_property(state, brush)
        style.set_editor_property("foreground_color", unreal.SlateColor(unreal.LinearColor(*WHITE)))
        style.set_editor_property("padding", unreal.Margin(16, 12, 16, 12))
        inner = style.get_editor_property("text_style")
        font = inner.get_editor_property("font")
        font.set_editor_property("size", 22)
        inner.set_editor_property("font", font)
        style.set_editor_property("text_style", inner)
        text.set_editor_property("widget_style", style)
    except Exception as e:  # a style field this engine lacks: the stock look
        unreal.log_warning(f"MJOLNIR UI: report text style: {e}")
    status = widget(bp, unreal.TextBlock, "ReportStatus", "ReportStack")
    text_style(status, "", 20, GREY)
    wrapped(status)
    gap(status, top=16, bottom=18)
    actions = widget(bp, unreal.HorizontalBox, "ReportActions", "ReportStack")
    for key, label, event in (("ReportSend", "SEND REPORT", "report_send"),
                              ("ReportCancel", "CANCEL", "report_cancel")):
        button = menu_button(bp, key, label, actions.get_name(), size=26)
        button.get_editor_property("slot").set_padding(unreal.Margin(0, 0, 16, 0))
        events.append((key, "OnClicked", event))
    return events


DOWNLOAD_TRACK = 1000
DOWNLOAD_INFO = (("Author", "BY"), ("Rating", "RATING"), ("Downloads", "DOWNLOADS"), ("Size", "DOWNLOAD"),
                 ("Version", "VERSION"), ("Modes", "GAME TYPES"))


def build_map_download():
    """A map this PC does not have (docs/live_map_install.md): its hub
    screenshot and details, DOWNLOAD and CANCEL, and the download's progress
    bar. MJOLNIRLobby pushes it when joining a game on such a map, or when
    the host or a vote picks one, and fills every text; the bar's fill is a
    size box whose width Lua sets (ProgressFillSize, 0 to DOWNLOAD_TRACK)."""
    name = "WBP_MJOLNIRMapDownload"
    bp = fresh_widget(name, unreal.CommonActivatableWidget)
    screen_canvas(bp)
    screen_header(bp, "DOWNLOAD MAP", "MULTIPLAYER")
    events = []

    card = panel(bp, "Card", "Root")
    place(card, (0.06, 0.25), (0.0, 0.0))
    sized(bp, "CardSize", "Card", width=2200)
    widget(bp, unreal.HorizontalBox, "CardRow", "CardSize")
    map_image(bp, "MapImage", "CardRow", 1120, 630)
    side_size = sized(bp, "SideSize", "CardRow", width=1000)
    side_size.get_editor_property("slot").set_padding(unreal.Margin(48, 0, 0, 0))
    widget(bp, unreal.VerticalBox, "Side", "SideSize")
    gap(rule(bp, "SideRule", "Side", ACCENT, 2), bottom=22)
    kicker = widget(bp, unreal.TextBlock, "Kicker", "Side")
    text_style(kicker, "MAP NOT INSTALLED", 18, GOLD)
    gap(kicker, bottom=10)
    title = widget(bp, unreal.TextBlock, "MapTitle", "Side")
    text_style(title, "", 56, WHITE)
    wrapped(title)
    reason = widget(bp, unreal.TextBlock, "Reason", "Side")
    text_style(reason, "", 22, GREY)
    wrapped(reason)
    gap(reason, top=8, bottom=20)
    gap(rule(bp, "InfoRule", "Side"), bottom=10)
    for key, label in DOWNLOAD_INFO:
        line = widget(bp, unreal.HorizontalBox, f"Info{key}", "Side")
        gap(line, top=6, bottom=6)
        size = sized(bp, f"Info{key}LabelSize", line.get_name(), width=220)
        middle(size)
        text_style(widget(bp, unreal.TextBlock, f"Info{key}Label", size.get_name()), label, 17, GREY)
        value = widget(bp, unreal.TextBlock, f"Info{key}Value", line.get_name())
        text_style(value, "", 24, WHITE)
        value.set_editor_property("text_overflow_policy", unreal.TextOverflowPolicy.ELLIPSIS)
        fill(value, 1)
        middle(value)
    description = widget(bp, unreal.TextBlock, "MapDescription", "Side")
    text_style(description, "", 22, GREY)
    wrapped(description)
    gap(description, top=16, bottom=22)

    # The download: a track, its fill, and a line under it.
    progress = widget(bp, unreal.VerticalBox, "Progress", "Side")
    gap(progress, bottom=18)
    track_size = sized(bp, "ProgressTrackSize", "Progress", width=DOWNLOAD_TRACK, height=14)
    track = widget(bp, unreal.Border, "ProgressTrack", track_size.get_name())
    track.set_editor_property("brush_color", unreal.LinearColor(*DIM[:3], 0.6))
    track.set_editor_property("padding", unreal.Margin(0))
    track.set_editor_property("horizontal_alignment", unreal.HorizontalAlignment.H_ALIGN_LEFT)
    fill_size = sized(bp, "ProgressFillSize", "ProgressTrack", width=1, height=14)
    ink = widget(bp, unreal.Border, "ProgressFill", fill_size.get_name())
    ink.set_editor_property("brush_color", unreal.LinearColor(*ACCENT))
    ink.set_editor_property("padding", unreal.Margin(0))
    line = widget(bp, unreal.TextBlock, "ProgressText", "Progress")
    text_style(line, "", 21, WHITE)
    wrapped(line)
    gap(line, top=10)

    gap(rule(bp, "ActionsRule", "Side"), bottom=18)
    actions = widget(bp, unreal.HorizontalBox, "Actions", "Side")
    for key, label in (("Download", "DOWNLOAD"), ("Cancel", "CANCEL")):
        button = menu_button(bp, key, label, actions.get_name(), size=28)
        button.get_editor_property("slot").set_padding(unreal.Margin(0, 0, 16, 0))
        events.append((key, "OnClicked", key.lower()))
    text_style(footer(bp), "MAPS COME FROM MJOLNIRCORE.COM, SIGNED BY THEIR AUTHORS AND CHECKED BEFORE THEY INSTALL",
               22, GREY)

    if not ui.compile_widget(bp):
        fail(f"{name} does not compile (widget tree)")
    if not ui.add_string_function(bp, "MJ_Event", "Name", ""):
        fail("MJ_Event")
    bind_events(bp, events)
    finish_screen(bp, name)


SETTINGS_PAGES = 5
SETTINGS_ROWS = 12


def build_game_settings():
    """The host's game settings (docs/host_game_settings.md): page buttons,
    then up to SETTINGS_ROWS rows of `<  LABEL  value  >`, and a help panel
    for the highlighted row, as CE's EDIT GAMETYPES pages had. Generic:
    MJOLNIRLobby's settings.lua names, fills and hides everything, so a new
    setting needs no new cook."""
    name = "WBP_MJOLNIRGameSettings"
    bp = fresh_widget(name, unreal.CommonActivatableWidget)
    screen_canvas(bp)
    screen_header(bp, "GAME SETTINGS", "CUSTOM GAME")
    mode_line = widget(bp, unreal.TextBlock, "ModeLine", "Root")
    place(mode_line, (0.06, 0.205), (0.0, 0.0))
    text_style(mode_line, "", 20, ACCENT)
    events = []

    pages = sized(bp, "PagesSize", "Root", width=360)
    place(pages, (0.06, 0.26), (0.0, 0.0))
    widget(bp, unreal.VerticalBox, "Pages", "PagesSize")
    gap(rule(bp, "PagesRule", "Pages", ACCENT, 2), bottom=12)
    for i in range(SETTINGS_PAGES):
        gap(menu_button(bp, f"Page{i}", "", "Pages", size=28), bottom=8)
        events.append((f"Page{i}", "OnClicked", f"page:{i}"))
    gap(rule(bp, "ActionsRule", "Pages"), top=20, bottom=12)
    for key, label in (("Reset", "RESET"), ("Back", "DONE")):
        gap(menu_button(bp, key, label, "Pages", size=28), bottom=8)
        events.append((key, "OnClicked", key.lower()))

    # Widths are UI units (the screen is 2560 wide at any resolution), not
    # pixels: pages end near 0.21, the rows run to 0.61, the help to 0.94.
    options = panel(bp, "Options", "Root", padding=(24, 20, 24, 20))
    place(options, (0.225, 0.26), (0.0, 0.0))
    sized(bp, "OptionsSize", "Options", width=960)
    widget(bp, unreal.VerticalBox, "Rows", "OptionsSize")
    for i in range(SETTINGS_ROWS):
        row = widget(bp, unreal.HorizontalBox, f"Row{i}", "Rows")
        gap(row, bottom=8)
        for key, text in ((f"Row{i}Prev", "<"), (f"Row{i}Pick", None), (f"Row{i}Next", ">")):
            button = widget(bp, unreal.Button, key, f"Row{i}")
            button_style(button)
            if text is None:
                fill(button, 1)
                button.get_editor_property("slot").set_padding(unreal.Margin(8, 0, 8, 0))
                inner = widget(bp, unreal.HorizontalBox, f"Row{i}Inner", key)
                # The label on the left, the value on the right, across the
                # whole button (a button centres its content otherwise).
                inner.get_editor_property("slot").set_horizontal_alignment(unreal.HorizontalAlignment.H_ALIGN_FILL)
                label = widget(bp, unreal.TextBlock, f"Row{i}Label", inner.get_name())
                text_style(label, "", 26, WHITE)
                fill(label, 1)
                middle(label)
                value = widget(bp, unreal.TextBlock, f"Row{i}Value", inner.get_name())
                text_style(value, "", 26, WHITE)
                value.set_editor_property("justification", unreal.TextJustify.RIGHT)
                value.get_editor_property("slot").set_padding(unreal.Margin(24, 0, 0, 0))
                middle(value)
            else:
                text_style(widget(bp, unreal.TextBlock, key + "Label", key), text, 26, WHITE)
        events += [(f"Row{i}Prev", "OnClicked", f"prev:{i}"), (f"Row{i}Pick", "OnClicked", f"row:{i}"),
                   (f"Row{i}Pick", "OnHovered", f"hover:{i}"), (f"Row{i}Next", "OnClicked", f"next:{i}")]

    help_panel = panel(bp, "Help", "Root")
    place(help_panel, (0.64, 0.26), (0.0, 0.0))
    sized(bp, "HelpSize", "Help", width=700)
    widget(bp, unreal.VerticalBox, "HelpStack", "HelpSize")
    gap(rule(bp, "HelpRule", "HelpStack", ACCENT, 2), bottom=24)
    title = widget(bp, unreal.TextBlock, "HelpTitle", "HelpStack")
    text_style(title, "", 20, ACCENT)
    value = widget(bp, unreal.TextBlock, "HelpValue", "HelpStack")
    text_style(value, "", 44, WHITE)
    gap(value, top=10, bottom=18)
    help_text = widget(bp, unreal.TextBlock, "HelpText", "HelpStack")
    text_style(help_text, "", 26, GREY)
    wrapped(help_text)
    text_style(footer(bp), "", 22, GREY)

    if not ui.compile_widget(bp):
        fail(f"{name} does not compile (widget tree)")
    if not ui.add_string_function(bp, "MJ_Event", "Name", ""):
        fail("MJ_Event")
    bind_events(bp, events)
    finish_screen(bp, name)


# Match chat (MJOLNIRHud, Scripts/chat.lua): CHAT_ROWS lines, oldest at the
# top, at the left of the screen above the kill feed, and the box you type
# in. Lua fills the lines from the bottom, collapses the rest, and fades
# them out a few seconds after they arrive; while the box is open every
# line shows on a dark panel.
#
#   Chat               VerticalBox at the left edge, growing up
#    ChatPanel         rounded Border: clear, dark while typing
#     ChatLines        the lines
#      ChatLine<i>     rounded Border: one line's own dark fill
#       ChatTag<i>     [TEAM], collapsed for all chat
#       ChatAvatar<i>  the sender's hub avatar, round (collapsed without one)
#       ChatName<i>    the sender, in their colour
#       ChatText<i>    what they said, wrapped
#    ChatInputBar      rounded Border, collapsed until T (all) or Y (team)
#     ChatChannel      ALL or TEAM
#     ChatInput        the EditableTextBox; Lua focuses it
#    ChatHint          ENTER to send, ESC to cancel
#
# Every container passes the mouse through (SelfHitTestInvisible) and the
# lines take nothing; only the input box is hit-testable, because Slate
# gives keyboard focus only along a path of visible widgets.
CHAT_ROWS = 10
CHAT_WIDTH = 920
CHAT_FILL = (0.012, 0.03, 0.045, 0.62)
CHAT_AVATAR = 28
CHAT_SUGGEST_ROWS = 6  # Scripts/commands.lua ROWS


def chat_line(bp, i):
    line = widget(bp, unreal.Border, f"ChatLine{i}", "ChatLines")
    rounded(line, 6, CHAT_FILL)
    line.set_editor_property("padding", unreal.Margin(12, 7, 16, 7))
    line.set_visibility(unreal.SlateVisibility.COLLAPSED)
    line.get_editor_property("slot").set_padding(unreal.Margin(0, 3, 0, 0))
    line.get_editor_property("slot").set_horizontal_alignment(unreal.HorizontalAlignment.H_ALIGN_LEFT)
    row = widget(bp, unreal.HorizontalBox, f"ChatLineBox{i}", line.get_name())
    tag = hidden_text(widget(bp, unreal.TextBlock, f"ChatTag{i}", row.get_name()))
    text_style(tag, "[TEAM]", 17, ACCENT, "Bold")
    tag.get_editor_property("slot").set_padding(unreal.Margin(0, 6, 8, 0))
    face = icon_box(bp, f"ChatAvatar{i}", row.get_name(), CHAT_AVATAR, CHAT_AVATAR)
    # Centred on the first line of text: Normative Pro's 22 px line is about
    # 42 px tall, so a 28 px picture at the top of the row sat high (and,
    # beside the text's drop shadow, a little left). A message that wraps
    # keeps its name and picture on its first line.
    face.get_editor_property("slot").set_padding(unreal.Margin(2, 7, 8, 0))
    face.get_editor_property("slot").set_vertical_alignment(unreal.VerticalAlignment.V_ALIGN_TOP)
    round_image(face.get_content(), CHAT_AVATAR)
    name = widget(bp, unreal.TextBlock, f"ChatName{i}", row.get_name())
    text_style(name, "", 22, WHITE, "Bold")
    shadowed(name)
    text = widget(bp, unreal.TextBlock, f"ChatText{i}", row.get_name())
    text_style(text, "", 22, WHITE)
    # A fixed wrap width: auto-wrap in a row sized to its content wraps at
    # almost nothing ("Press T to / chat"). A short line keeps a short row.
    text.set_editor_property("wrap_text_at", CHAT_WIDTH - 260)
    shadowed(text)
    text.get_editor_property("slot").set_padding(unreal.Margin(8, 0, 0, 0))
    for w in (row, name, text):
        w.set_visibility(unreal.SlateVisibility.HIT_TEST_INVISIBLE)


def chat_input_style(box):
    try:
        style = box.get_editor_property("widget_style")
        for state in ("background_image_normal", "background_image_hovered", "background_image_focused",
                      "background_image_read_only"):
            brush = style.get_editor_property(state)
            brush.set_editor_property("resource_object", None)
            brush.set_editor_property("draw_as", unreal.SlateBrushDrawType.IMAGE)
            brush.set_editor_property("tint_color", unreal.SlateColor(unreal.LinearColor(0.0, 0.0, 0.0, 0.0)))
            style.set_editor_property(state, brush)
        style.set_editor_property("foreground_color", unreal.SlateColor(unreal.LinearColor(*WHITE)))
        style.set_editor_property("padding", unreal.Margin(4, 6, 4, 6))
        inner = style.get_editor_property("text_style")
        font = inner.get_editor_property("font")
        font.set_editor_property("size", 24)
        inner.set_editor_property("font", font)
        style.set_editor_property("text_style", inner)
        box.set_editor_property("widget_style", style)
    except Exception as e:  # a style field this engine lacks: the stock look
        unreal.log_warning(f"MJOLNIR UI: chat input style: {e}")


def build_chat():
    name = "WBP_MJOLNIRChat"
    bp = fresh_widget(name)
    passes = unreal.SlateVisibility.SELF_HIT_TEST_INVISIBLE
    viewport = widget(bp, unreal.CanvasPanel, "Viewport")
    fit = widget(bp, unreal.ScaleBox, "Fit", "Viewport")
    stretch(fit)
    fit.set_stretch(unreal.Stretch.SCALE_TO_FIT)
    design = sized(bp, "Design", "Fit", width=2560, height=1440)
    root = widget(bp, unreal.CanvasPanel, "Root", "Design")
    for w in (viewport, fit, design, root):
        w.set_visibility(passes)

    chat = widget(bp, unreal.VerticalBox, "Chat", "Root")
    place(chat, (0.018, 0.55), (0.0, 1.0))
    chat.set_visibility(passes)
    size = sized(bp, "ChatSize", "Chat", width=CHAT_WIDTH)
    size.set_visibility(passes)
    stack = widget(bp, unreal.VerticalBox, "ChatStack", size.get_name())
    stack.set_visibility(passes)

    chat_panel = widget(bp, unreal.Border, "ChatPanel", stack.get_name())
    rounded(chat_panel, 8, (0.005, 0.018, 0.03, 0.0), padding=8)
    chat_panel.set_visibility(passes)
    lines = widget(bp, unreal.VerticalBox, "ChatLines", chat_panel.get_name())
    lines.set_visibility(passes)
    for i in range(CHAT_ROWS):
        chat_line(bp, i)

    # Slash commands (Scripts/commands.lua): what "/" can do, under the
    # lines and over the box, the one Tab completes highlighted.
    suggest = widget(bp, unreal.Border, "ChatSuggest", stack.get_name())
    rounded(suggest, 8, (0.0, 0.03, 0.05, 0.92), padding=6)
    gap(suggest, top=8)
    suggest.set_visibility(unreal.SlateVisibility.COLLAPSED)
    rows = widget(bp, unreal.VerticalBox, "ChatSugRows", suggest.get_name())
    rows.set_visibility(passes)
    for i in range(CHAT_SUGGEST_ROWS):
        row = widget(bp, unreal.Border, f"ChatSugRow{i}", rows.get_name())
        rounded(row, 5, (0.0, 0.0, 0.0, 0.0))
        row.set_editor_property("padding", unreal.Margin(10, 4, 10, 4))
        row.set_visibility(unreal.SlateVisibility.COLLAPSED)
        line = widget(bp, unreal.HorizontalBox, f"ChatSugLine{i}", row.get_name())
        line.set_visibility(passes)
        label = widget(bp, unreal.TextBlock, f"ChatSugName{i}", line.get_name())
        text_style(label, "", 20, ACCENT, "Bold")
        hint_text = widget(bp, unreal.TextBlock, f"ChatSugHelp{i}", line.get_name())
        text_style(hint_text, "", 18, GREY)
        hint_text.get_editor_property("slot").set_padding(unreal.Margin(14, 1, 0, 0))
        for w in (label, hint_text):
            w.set_visibility(unreal.SlateVisibility.HIT_TEST_INVISIBLE)

    bar = widget(bp, unreal.Border, "ChatInputBar", stack.get_name())
    rounded(bar, 8, (0.0, 0.03, 0.05, 0.92), padding=0)
    bar.set_editor_property("padding", unreal.Margin(16, 6, 16, 6))
    gap(bar, top=8)
    bar.set_visibility(unreal.SlateVisibility.COLLAPSED)
    row = widget(bp, unreal.HorizontalBox, "ChatInputRow", bar.get_name())
    row.set_visibility(passes)
    channel = widget(bp, unreal.TextBlock, "ChatChannel", row.get_name())
    text_style(channel, "ALL", 22, ACCENT, "Bold")
    middle(channel)
    channel.get_editor_property("slot").set_padding(unreal.Margin(0, 0, 14, 0))
    channel.set_visibility(unreal.SlateVisibility.HIT_TEST_INVISIBLE)
    box = widget(bp, unreal.EditableTextBox, "ChatInput", row.get_name())
    box.set_editor_property("hint_text", unreal.Text("Say something"))
    box.set_editor_property("clear_keyboard_focus_on_commit", False)
    chat_input_style(box)
    fill(box, 1)
    middle(box)

    hint = widget(bp, unreal.TextBlock, "ChatHint", stack.get_name())
    text_style(hint, "ENTER  SEND      ESC  CANCEL      /  COMMANDS      TAB  COMPLETE", 15, GREY, "Bold")
    gap(hint, top=6)
    hint.set_visibility(unreal.SlateVisibility.COLLAPSED)
    shadowed(hint)

    # The chat rules, shown the first time a player opens chat; chat opens
    # only once they agree. Lua fills the text (Scripts/chat.lua RULES), so
    # the wording can change without a new container.
    rules = panel(bp, "ChatRules", "Root", alpha=0.94, padding=(48, 40, 48, 36))
    rounded(rules, 12, (0.005, 0.018, 0.03, 0.94), padding=0)
    rules.set_editor_property("padding", unreal.Margin(48, 40, 48, 36))
    place(rules, (0.5, 0.5), (0.5, 0.5))
    rules.set_visibility(unreal.SlateVisibility.COLLAPSED)
    size = sized(bp, "ChatRulesSize", rules.get_name(), width=1080)
    stack = widget(bp, unreal.VerticalBox, "ChatRulesStack", size.get_name())
    title = widget(bp, unreal.TextBlock, "ChatRulesTitle", stack.get_name())
    text_style(title, "MATCH CHAT IS MODERATED", 34, ACCENT, "Bold")
    body = widget(bp, unreal.TextBlock, "ChatRulesBody", stack.get_name())
    text_style(body, "", 22, WHITE)
    wrapped(body)
    gap(body, top=18)
    listed = widget(bp, unreal.TextBlock, "ChatRulesList", stack.get_name())
    text_style(listed, "", 21, WHITE)
    wrapped(listed)
    gap(listed, top=18)
    note = widget(bp, unreal.TextBlock, "ChatRulesNote", stack.get_name())
    text_style(note, "", 19, GREY)
    wrapped(note)
    gap(note, top=18)
    actions = widget(bp, unreal.HorizontalBox, "ChatRulesActions", stack.get_name())
    gap(actions, top=28)
    events = []
    for key, label, event in (("ChatRulesAccept", "I AGREE", "chat_accept"),
                              ("ChatRulesDecline", "NOT NOW", "chat_decline")):
        button = menu_button(bp, key, label, actions.get_name(), size=26)
        button.get_editor_property("slot").set_padding(unreal.Margin(0, 0, 16, 0))
        events.append((key, "OnClicked", event))
    keys = widget(bp, unreal.TextBlock, "ChatRulesKeys", stack.get_name())
    text_style(keys, "ENTER  AGREE      ESC  NOT NOW", 15, GREY, "Bold")
    gap(keys, top=14)

    if not ui.compile_widget(bp):
        fail(f"{name} does not compile (widget tree)")
    if not ui.add_string_function(bp, "MJ_Event", "Name", ""):
        fail("MJ_Event")
    bind_events(bp, events)
    finish(bp, name)


# --- Forge -------------------------------------------------------------------
#
# WBP_MJOLNIRForge, the HUD of a FORGE game (mods/MJOLNIRForge; docs/forge.md),
# in a folder and chunk of its own (/Game/MJOLNIR/ForgeUI, chunk 980,
# pakchunk980-MJOLNIRFORGEUI) so it ships beside the CE runtime's monitor fix
# without rebuilding chunk 984. A HUD: nothing takes the mouse or focus; the
# keys are MJOLNIRForge's own binds. Lua fills every text and colour.
#
#   ForgeBadge     top left: ForgeMark (the Monitor glyph), ForgeTitle
#                  ("FORGE"), ForgeRule, ForgeMode (MONITOR / SPARTAN),
#                  ForgeMap (the map's name)
#   ReticleBox     the Monitor's cursor, Reticle, tinted per state
#   TargetCard     right of the cursor: TargetIconBox / TargetIcon (the game's
#                  weapon silhouette, hidden without one), TargetCategory
#                  (WEAPON ...), TargetName, TargetCap<i> / TargetKey<i> /
#                  TargetAct<i> (what the keys do to it), and while holding,
#                  DistanceRow: DistanceFill (a SizeBox Lua widens over
#                  DistanceTrack) and DistanceValue
#   ControlBar     bottom centre: Control<i> = ControlCap<i> / ControlKey<i> /
#                  ControlAct<i>, every action's key; Lua dims what does not
#                  apply and hides the slots it does not use
#   Toast          above the bar: ToastAccent and ToastText, the last action,
#                  faded out by Lua
FORGE_ROOT = "/Game/MJOLNIR/ForgeUI"
FORGE_CHUNK = 980
FORGE_ICON_ROOT = f"{FORGE_ROOT}/Icons"
FORGE_CARD_HINTS = 3
FORGE_CONTROLS = 6
FORGE_DISTANCE_TRACK = (280, 6)
FORGE_FILL = (0.008, 0.024, 0.038, 0.78)
KEYCAP_FILL = (0.85, 0.95, 1.0, 0.14)


def keycap(bp, name, parent, key, action, key_size=18, action_size=17):
    """A key cap (`<name>Cap`, rounded, `<name>Key` inside) and the action
    beside it (`<name>Act`), in a HorizontalBox `<name>`."""
    row = widget(bp, unreal.HorizontalBox, name, parent)
    cap = rounded(widget(bp, unreal.Border, f"{name}Cap", row.get_name()), 6, KEYCAP_FILL)
    cap.set_editor_property("padding", unreal.Margin(10, 3, 10, 4))
    middle(cap)
    block = widget(bp, unreal.TextBlock, f"{name}Key", cap.get_name())
    text_style(block, key, key_size, WHITE, "Bold")
    act = widget(bp, unreal.TextBlock, f"{name}Act", row.get_name())
    text_style(act, action, action_size, GREY, "Bold")
    act.get_editor_property("slot").set_padding(unreal.Margin(8, 0, 0, 0))
    middle(act)
    shadowed(act)
    return row


def build_forge_hud(icons):
    name = "WBP_MJOLNIRForge"
    bp = fresh_widget(name, root=FORGE_ROOT)
    hud_root(bp)

    # The badge.
    badge = widget(bp, unreal.VerticalBox, "ForgeBadge", "Root")
    place(badge, (0.018, 0.035), (0.0, 0.0))
    title_row = widget(bp, unreal.HorizontalBox, "ForgeTitleRow", badge.get_name())
    mark = icon_box(bp, "ForgeMark", title_row.get_name(), 44, 44, collapsed=False)
    middle(mark)
    mark.get_content().set_brush_from_texture(icons["Mark"], False)
    mark.get_content().set_color_and_opacity(unreal.LinearColor(*ACCENT))
    title = widget(bp, unreal.TextBlock, "ForgeTitle", title_row.get_name())
    text_style(title, "FORGE", 40, ACCENT, "Bold")
    title.get_editor_property("slot").set_padding(unreal.Margin(12, 0, 0, 0))
    middle(title)
    shadowed(title)
    line = rule(bp, "ForgeRule", badge.get_name(), color=LINE, height=2)
    line.set_width_override(300)
    gap(line, top=8)
    mode = widget(bp, unreal.TextBlock, "ForgeMode", badge.get_name())
    text_style(mode, "MONITOR", 21, WHITE, "Bold")
    gap(mode, top=8)
    shadowed(mode)
    where = widget(bp, unreal.TextBlock, "ForgeMap", badge.get_name())
    text_style(where, "", 17, GREY)
    shadowed(where)

    # The cursor.
    # (A SizeBox on the canvas, not icon_box: a canvas slot has no alignment.)
    reticle = sized(bp, "ReticleBox", "Root", width=76, height=76)
    place(reticle, (0.5, 0.5), (0.5, 0.5))
    cursor = widget(bp, unreal.Image, "Reticle", reticle.get_name())
    cursor.set_brush_from_texture(icons["Reticle"], False)
    cursor.set_color_and_opacity(unreal.LinearColor(*ACCENT))
    reticle.set_visibility(unreal.SlateVisibility.COLLAPSED)

    # The target card.
    card = rounded(widget(bp, unreal.Border, "TargetCard", "Root"), 10, FORGE_FILL)
    card.set_editor_property("padding", unreal.Margin(20, 14, 22, 16))
    place(card, (0.5, 0.5), (0.0, 0.5), (74.0, 0.0))
    card.set_visibility(unreal.SlateVisibility.COLLAPSED)
    stack = widget(bp, unreal.VerticalBox, "TargetStack", card.get_name())
    top = widget(bp, unreal.HorizontalBox, "TargetTop", stack.get_name())
    picture = icon_box(bp, "TargetIcon", top.get_name(), 120, 40)
    picture.get_editor_property("slot").set_padding(unreal.Margin(0, 0, 14, 0))
    middle(picture)
    words = widget(bp, unreal.VerticalBox, "TargetWords", top.get_name())
    middle(words)
    category = widget(bp, unreal.TextBlock, "TargetCategory", words.get_name())
    text_style(category, "OBJECT", 15, ACCENT, "Bold")
    named = widget(bp, unreal.TextBlock, "TargetName", words.get_name())
    text_style(named, "", 30, WHITE, "Bold")
    shadowed(named)
    hints = widget(bp, unreal.HorizontalBox, "TargetHints", stack.get_name())
    gap(hints, top=12)
    for i in range(FORGE_CARD_HINTS):
        hint = keycap(bp, f"Target{i}", hints.get_name(), "V", "PICK UP", key_size=16, action_size=15)
        hint.get_editor_property("slot").set_padding(unreal.Margin(0, 0, 18, 0))
    # Holding: how far out it is, as a bar over 1..60 m and the metres.
    distance = widget(bp, unreal.VerticalBox, "DistanceRow", stack.get_name())
    gap(distance, top=12)
    distance.set_visibility(unreal.SlateVisibility.COLLAPSED)
    caption_row = widget(bp, unreal.HorizontalBox, "DistanceCaptionRow", distance.get_name())
    caption = widget(bp, unreal.TextBlock, "DistanceLabel", caption_row.get_name())
    text_style(caption, "DISTANCE", 14, GREY, "Bold")
    fill(widget(bp, unreal.Spacer, "DistanceSpace", caption_row.get_name()), 1)
    metres = widget(bp, unreal.TextBlock, "DistanceValue", caption_row.get_name())
    text_style(metres, "", 14, WHITE, "Bold")
    track = sized(bp, "DistanceTrack", distance.get_name(), width=FORGE_DISTANCE_TRACK[0],
                  height=FORGE_DISTANCE_TRACK[1])
    gap(track, top=6)
    frame = widget(bp, unreal.Overlay, "DistanceFrame", track.get_name())
    back = rounded(widget(bp, unreal.Border, "DistanceBack", frame.get_name()), 3, (0.85, 0.95, 1.0, 0.12))
    lane = widget(bp, unreal.HorizontalBox, "DistanceLane", frame.get_name())
    for w in (back, lane):
        slot = w.get_editor_property("slot")
        slot.set_horizontal_alignment(unreal.HorizontalAlignment.H_ALIGN_FILL)
        slot.set_vertical_alignment(unreal.VerticalAlignment.V_ALIGN_FILL)
    bar = widget(bp, unreal.SizeBox, "DistanceFill", lane.get_name())
    bar.set_width_override(0)
    bar.set_clipping(unreal.WidgetClipping.CLIP_TO_BOUNDS)
    bar.get_editor_property("slot").set_vertical_alignment(unreal.VerticalAlignment.V_ALIGN_FILL)
    rounded(widget(bp, unreal.Border, "DistanceInk", bar.get_name()), 3, ACCENT)
    fill(widget(bp, unreal.Spacer, "DistanceRest", lane.get_name()), 1)

    # The toast: what the last key did.
    toast = rounded(widget(bp, unreal.Border, "Toast", "Root"), 8, FORGE_FILL)
    toast.set_editor_property("padding", unreal.Margin(0, 0, 20, 0))
    place(toast, (0.5, 0.875), (0.5, 1.0))
    toast.set_visibility(unreal.SlateVisibility.COLLAPSED)
    toast_row = widget(bp, unreal.HorizontalBox, "ToastRow", toast.get_name())
    accent = sized(bp, "ToastAccentSize", toast_row.get_name(), width=4, height=46)
    rounded(widget(bp, unreal.Border, "ToastAccent", accent.get_name()), 2, ACCENT)
    said = widget(bp, unreal.TextBlock, "ToastText", toast_row.get_name())
    text_style(said, "", 22, WHITE, "Bold")
    said.get_editor_property("slot").set_padding(unreal.Margin(16, 0, 0, 0))
    middle(said)

    # The control bar.
    strip = rounded(widget(bp, unreal.Border, "ControlBar", "Root"), 10, FORGE_FILL)
    strip.set_editor_property("padding", unreal.Margin(22, 12, 4, 12))
    place(strip, (0.5, 0.955), (0.5, 1.0))
    row = widget(bp, unreal.HorizontalBox, "ControlRow", strip.get_name())
    for i in range(FORGE_CONTROLS):
        control = keycap(bp, f"Control{i}", row.get_name(), "B", "MONITOR")
        control.get_editor_property("slot").set_padding(unreal.Margin(0, 0, 22, 0))

    finish(bp, name, root=FORGE_ROOT)


def build_forge_label():
    full = f"{FORGE_ROOT}/PAL_MJOLNIR_ForgeUI"
    if eal.does_asset_exist(full):
        eal.delete_asset(full)
    label = assets.create_asset("PAL_MJOLNIR_ForgeUI", FORGE_ROOT, unreal.PrimaryAssetLabel, unreal.DataAssetFactory())
    rules = label.get_editor_property("rules")
    rules.set_editor_property("chunk_id", FORGE_CHUNK)
    rules.set_editor_property("apply_recursively", True)
    rules.set_editor_property("cook_rule", unreal.PrimaryAssetCookRule.ALWAYS_COOK)
    label.set_editor_property("rules", rules)
    label.set_editor_property("label_assets_in_my_directory", True)
    eal.save_loaded_asset(label)


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
build_kill_feed(import_hud_icons())
build_scoreboard()
build_lobby()
build_map_select()
build_find_games()
build_post_game()
build_map_download()
build_game_settings()
build_chat()
build_label()
build_forge_hud(import_hud_icons("ForgeIcons", FORGE_ICON_ROOT, "T_MJForge_"))
build_forge_label()
unreal.log("MJOLNIR UI built")

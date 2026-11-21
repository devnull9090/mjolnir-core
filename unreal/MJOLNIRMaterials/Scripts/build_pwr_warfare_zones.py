"""Cook-only UMG zone strip for Pelican Warfare: one tile per capture site under the match score.

Run through tools/ue/editor_cmd.ps1. Chunk 958 (beside the tactical map) owns
/Game/MJOLNIR/UI/WBP_MJOLNIRWarfareZones. MJOLNIRHud (Scripts/warfare_zones.lua)
fills it from the native warfare snapshot; the widget is layout only.

Per site i (0..2): Zone<i>Rim (owner / you-are-here rim), Zone<i>Tint (owner wash),
Zone<i>Letter, Zone<i>State, Zone<i>Fill (SizeBox whose width Lua sets to the capture
progress, TRACK px at full) with its ink Zone<i>Ink, and the presence pips Zone<i>RedPip,
Zone<i>BluePip. Same 2560 x 1440 design space and palette as the kill feed's score strip.
"""
import unreal

ROOT = "/Game/MJOLNIR/UI"
NAME = "WBP_MJOLNIRWarfareZones"
LABEL_ROOT = "/Game/MJOLNIR/TacticalMap"
CHUNK = 958
ui = unreal.MjolnirUIBuilderLibrary
eal = unreal.EditorAssetLibrary
assets = unreal.AssetToolsHelpers.get_asset_tools()

WHITE = (0.88, 0.95, 1.0, 1.0)
GREY = (0.46, 0.61, 0.70, 1.0)
LINE = (0.24, 0.49, 0.63, 0.55)
RED = (1.0, 0.32, 0.28, 1.0)
BLUE = (0.3, 0.65, 1.0, 1.0)
GLASS = (0.01, 0.025, 0.04, 0.80)
TILE = (168, 100)  # tall enough for 10 px between the state word and the capture bar
TRACK = 144        # TILE width less the 2 px rim and 10 px of padding each side


def add(cls, name, parent=""):
    w = ui.add_widget(bp, cls, name, parent)
    if w is None:
        raise RuntimeError(f"Cannot create {name}")
    return w


def rounded(border, radius, color, padding=0):
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


def fill(w):
    slot = w.get_editor_property("slot")
    slot.set_horizontal_alignment(unreal.HorizontalAlignment.H_ALIGN_FILL)
    slot.set_vertical_alignment(unreal.VerticalAlignment.V_ALIGN_FILL)
    return w


def text(block, value, size, color, face="Bold"):
    block.set_editor_property("text", unreal.Text(value))
    font = block.get_editor_property("font")
    font.set_editor_property("size", size)
    font.set_editor_property("typeface_font_name", face)
    block.set_editor_property("font", font)
    block.set_editor_property("color_and_opacity", unreal.SlateColor(unreal.LinearColor(*color)))
    block.set_editor_property("justification", unreal.TextJustify.CENTER)
    block.set_shadow_offset(unreal.Vector2D(2.0, 2.0))
    block.set_shadow_color_and_opacity(unreal.LinearColor(0.0, 0.0, 0.0, 0.85))
    return block


def sized(name, parent, width=None, height=None):
    box = add(unreal.SizeBox, name, parent)
    if width is not None:
        box.set_width_override(width)
    if height is not None:
        box.set_height_override(height)
    return box


def tile(i, letter):
    size = sized(f"Zone{i}Size", "Zones", *TILE)
    size.get_editor_property("slot").set_padding(unreal.Margin(8, 0, 8, 0))
    frame = add(unreal.Overlay, f"Zone{i}", size.get_name())
    rim = fill(rounded(add(unreal.Border, f"Zone{i}Rim", frame.get_name()), 11, LINE, 2))
    body = add(unreal.Overlay, f"Zone{i}Body", rim.get_name())
    fill(rounded(add(unreal.Border, f"Zone{i}Back", body.get_name()), 9, GLASS))
    fill(rounded(add(unreal.Border, f"Zone{i}Tint", body.get_name()), 9, (0, 0, 0, 0)))
    words = add(unreal.VerticalBox, f"Zone{i}Text", body.get_name())
    slot = words.get_editor_property("slot")
    slot.set_horizontal_alignment(unreal.HorizontalAlignment.H_ALIGN_CENTER)
    slot.set_vertical_alignment(unreal.VerticalAlignment.V_ALIGN_TOP)
    slot.set_padding(unreal.Margin(0, 4, 0, 0))
    text(add(unreal.TextBlock, f"Zone{i}Letter", words.get_name()), letter, 30, WHITE)
    state = text(add(unreal.TextBlock, f"Zone{i}State", words.get_name()), "NEUTRAL", 13, GREY)
    # The capture bar along the foot of the tile.
    foot = fill(add(unreal.VerticalBox, f"Zone{i}Foot", body.get_name()))
    spacer = add(unreal.Spacer, f"Zone{i}Lift", foot.get_name())
    spacer.get_editor_property("slot").set_size(unreal.SlateChildSize(1.0, unreal.SlateSizeRule.FILL))
    track = sized(f"Zone{i}Track", foot.get_name(), TRACK, 6)
    slot = track.get_editor_property("slot")
    slot.set_horizontal_alignment(unreal.HorizontalAlignment.H_ALIGN_CENTER)
    slot.set_padding(unreal.Margin(0, 0, 0, 10))
    lanes = add(unreal.Overlay, f"Zone{i}Lanes", track.get_name())
    fill(rounded(add(unreal.Border, f"Zone{i}TrackBack", lanes.get_name()), 3, (0.0, 0.0, 0.0, 0.55)))
    lane = fill(add(unreal.HorizontalBox, f"Zone{i}Lane", lanes.get_name()))
    bar = add(unreal.SizeBox, f"Zone{i}Fill", lane.get_name())
    bar.set_width_override(0)
    bar.set_clipping(unreal.WidgetClipping.CLIP_TO_BOUNDS)
    bar.get_editor_property("slot").set_vertical_alignment(unreal.VerticalAlignment.V_ALIGN_FILL)
    rounded(add(unreal.Border, f"Zone{i}Ink", bar.get_name()), 3, WHITE)
    rest = add(unreal.Spacer, f"Zone{i}Rest", lane.get_name())
    rest.get_editor_property("slot").set_size(unreal.SlateChildSize(1.0, unreal.SlateSizeRule.FILL))
    # Who is standing in the zone: a red and a blue pip at the top right.
    pips = add(unreal.HorizontalBox, f"Zone{i}Pips", body.get_name())
    slot = pips.get_editor_property("slot")
    slot.set_horizontal_alignment(unreal.HorizontalAlignment.H_ALIGN_RIGHT)
    slot.set_vertical_alignment(unreal.VerticalAlignment.V_ALIGN_TOP)
    slot.set_padding(unreal.Margin(0, 9, 10, 0))
    for side, color in (("Red", RED), ("Blue", BLUE)):
        pip = sized(f"Zone{i}{side}PipSize", pips.get_name(), 9, 9)
        pip.get_editor_property("slot").set_padding(unreal.Margin(3, 0, 0, 0))
        rounded(add(unreal.Border, f"Zone{i}{side}Pip", pip.get_name()), 4.5, color)
        pip.set_visibility(unreal.SlateVisibility.COLLAPSED)


if eal.does_asset_exist(f"{ROOT}/{NAME}"):
    eal.delete_asset(f"{ROOT}/{NAME}")
bp = ui.create_widget_blueprint(ROOT, NAME, None)
viewport = add(unreal.CanvasPanel, "Viewport")
viewport.set_visibility(unreal.SlateVisibility.HIT_TEST_INVISIBLE)
fit = add(unreal.ScaleBox, "Fit", "Viewport")
slot = fit.get_editor_property("slot")
slot.set_anchors(unreal.Anchors(minimum=unreal.Vector2D(0, 0), maximum=unreal.Vector2D(1, 1)))
slot.set_offsets(unreal.Margin(0, 0, 0, 0))
fit.set_stretch(unreal.Stretch.SCALE_TO_FIT)
design = sized("Design", "Fit", 2560, 1440)
add(unreal.CanvasPanel, "Root", "Design")
row = add(unreal.HorizontalBox, "Zones", "Root")
slot = row.get_editor_property("slot")
slot.set_anchors(unreal.Anchors(minimum=unreal.Vector2D(0.5, 0), maximum=unreal.Vector2D(0.5, 0)))
slot.set_alignment(unreal.Vector2D(0.5, 0))
# Under the score strip (kill feed MatchScore: top edge + 22, 32 px bars, TO WIN line).
slot.set_position(unreal.Vector2D(0, 92))
slot.set_auto_size(True)
for i, letter in enumerate("ABC"):
    tile(i, letter)

if not ui.compile_widget(bp):
    raise RuntimeError("Warfare zone widget compile failed")
eal.save_loaded_asset(bp)
label_path = f"{LABEL_ROOT}/PAL_PWR_WarfareZones"
label = eal.load_asset(label_path) if eal.does_asset_exist(label_path) else assets.create_asset(
    "PAL_PWR_WarfareZones", LABEL_ROOT, unreal.PrimaryAssetLabel, unreal.DataAssetFactory())
rules = label.get_editor_property("rules")
rules.set_editor_property("chunk_id", CHUNK)
rules.set_editor_property("apply_recursively", True)
rules.set_editor_property("cook_rule", unreal.PrimaryAssetCookRule.ALWAYS_COOK)
label.set_editor_property("rules", rules)
label.set_editor_property("label_assets_in_my_directory", False)
label.set_editor_property("explicit_assets", [bp])
eal.save_loaded_asset(label)
unreal.log("MJOLNIR warfare zones built: three site tiles, chunk958")

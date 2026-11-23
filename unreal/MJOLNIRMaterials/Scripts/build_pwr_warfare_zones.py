"""Cook-only UMG zone bars for Pelican Warfare: one slim row per capture site, stacked in the top left.

Run through tools/ue/editor_cmd.ps1. Chunk 958 (beside the tactical map) owns
/Game/MJOLNIR/UI/WBP_MJOLNIRWarfareZones and its two badge textures
(T_PWR_ZoneHexRim, T_PWR_ZoneHexFill from Art/WarfareZones, drawn by
tools/ue/draw_zone_badges.py). MJOLNIRHud (Scripts/warfare_zones.lua) fills it
from the native warfare snapshot; the widget is layout only.

Per site i (0..2), one row: a hexagon badge (Zone<i>Tint, the owner's wash, under
Zone<i>Rim, the owner / you-are-here outline, both Borders drawing a white hexagon
that Lua tints by brush colour) with Zone<i>Letter inside; beside it Zone<i>State
over the capture bar Zone<i>Fill (SizeBox whose width Lua sets to the progress,
TRACK px at full) and its ink Zone<i>Ink; the presence pips Zone<i>RedPip and
Zone<i>BluePip after the state word. Same 2560 x 1440 design space and palette
as the kill feed's score strip.
"""
from pathlib import Path

import unreal

ROOT = "/Game/MJOLNIR/UI"
NAME = "WBP_MJOLNIRWarfareZones"
LABEL_ROOT = "/Game/MJOLNIR/TacticalMap"
ART = Path(__file__).resolve().parents[1] / "Art" / "WarfareZones"
CHUNK = 958
ui = unreal.MjolnirUIBuilderLibrary
eal = unreal.EditorAssetLibrary
assets = unreal.AssetToolsHelpers.get_asset_tools()

WHITE = (0.88, 0.95, 1.0, 1.0)
GREY = (0.46, 0.61, 0.70, 1.0)
LINE = (0.24, 0.49, 0.63, 0.55)
RED = (1.0, 0.32, 0.28, 1.0)
BLUE = (0.3, 0.65, 1.0, 1.0)
BADGE = 62          # the hexagon's box
TRACK = 340         # the capture bar at full (warfare_zones.lua TRACK)
ROW_GAP = 14
CORNER = (48, 40)   # from the top left of the design space


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


def pictured(border, texture, color):
    """A Border drawing `texture` whole; its brush colour tints it."""
    brush = border.get_editor_property("background")
    brush.set_editor_property("draw_as", unreal.SlateBrushDrawType.IMAGE)
    brush.set_editor_property("resource_object", texture)
    border.set_editor_property("background", brush)
    border.set_editor_property("brush_color", unreal.LinearColor(*color))
    border.set_editor_property("padding", unreal.Margin(0, 0, 0, 0))
    return border


def fill(w):
    slot = w.get_editor_property("slot")
    slot.set_horizontal_alignment(unreal.HorizontalAlignment.H_ALIGN_FILL)
    slot.set_vertical_alignment(unreal.VerticalAlignment.V_ALIGN_FILL)
    return w


def text(block, value, size, color, face="Bold", justify=unreal.TextJustify.CENTER):
    block.set_editor_property("text", unreal.Text(value))
    font = block.get_editor_property("font")
    font.set_editor_property("size", size)
    font.set_editor_property("typeface_font_name", face)
    block.set_editor_property("font", font)
    block.set_editor_property("color_and_opacity", unreal.SlateColor(unreal.LinearColor(*color)))
    block.set_editor_property("justification", justify)
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


def texture(name):
    source = ART / f"{name}.png"
    if not source.is_file():
        raise RuntimeError(f"Missing zone badge art (python tools/ue/draw_zone_badges.py): {source}")
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", str(source))
    task.set_editor_property("destination_path", LABEL_ROOT)
    task.set_editor_property("destination_name", "T_PWR_Zone" + name)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    assets.import_asset_tasks([task])
    tex = eal.load_asset(f"{LABEL_ROOT}/T_PWR_Zone{name}")
    tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_EDITOR_ICON)
    tex.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_UI)
    tex.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_SIMPLE_AVERAGE)
    tex.set_editor_property("never_stream", True)
    tex.set_editor_property("srgb", True)
    eal.save_loaded_asset(tex)
    return tex


def row(i, letter, rim_texture, fill_texture):
    line = add(unreal.HorizontalBox, f"Zone{i}", "Zones")
    line.get_editor_property("slot").set_padding(unreal.Margin(0, 0 if i == 0 else ROW_GAP, 0, 0))
    # The badge: the owner's wash under the outline, the letter on top.
    badge = sized(f"Zone{i}Badge", line.get_name(), BADGE, BADGE)
    badge.get_editor_property("slot").set_vertical_alignment(unreal.VerticalAlignment.V_ALIGN_CENTER)
    stack = add(unreal.Overlay, f"Zone{i}Body", badge.get_name())
    fill(pictured(add(unreal.Border, f"Zone{i}Tint", stack.get_name()), fill_texture, (0, 0, 0, 0)))
    fill(pictured(add(unreal.Border, f"Zone{i}Rim", stack.get_name()), rim_texture, LINE))
    mark = text(add(unreal.TextBlock, f"Zone{i}Letter", stack.get_name()), letter, 27, WHITE)
    slot = mark.get_editor_property("slot")
    slot.set_horizontal_alignment(unreal.HorizontalAlignment.H_ALIGN_CENTER)
    slot.set_vertical_alignment(unreal.VerticalAlignment.V_ALIGN_CENTER)
    # Beside it: the state word and presence pips over the capture bar.
    side = add(unreal.VerticalBox, f"Zone{i}Text", line.get_name())
    slot = side.get_editor_property("slot")
    slot.set_vertical_alignment(unreal.VerticalAlignment.V_ALIGN_CENTER)
    slot.set_padding(unreal.Margin(16, 0, 0, 0))
    head = add(unreal.HorizontalBox, f"Zone{i}Head", side.get_name())
    state = text(add(unreal.TextBlock, f"Zone{i}State", head.get_name()), "NEUTRAL", 17, GREY,
                 justify=unreal.TextJustify.LEFT)
    state.get_editor_property("slot").set_vertical_alignment(unreal.VerticalAlignment.V_ALIGN_CENTER)
    for side_name, color in (("Red", RED), ("Blue", BLUE)):
        pip = sized(f"Zone{i}{side_name}PipSize", head.get_name(), 10, 10)
        slot = pip.get_editor_property("slot")
        slot.set_padding(unreal.Margin(6, 0, 0, 0))
        slot.set_vertical_alignment(unreal.VerticalAlignment.V_ALIGN_CENTER)
        rounded(add(unreal.Border, f"Zone{i}{side_name}Pip", pip.get_name()), 5, color)
        pip.set_visibility(unreal.SlateVisibility.COLLAPSED)
    track = sized(f"Zone{i}Track", side.get_name(), TRACK, 7)
    track.get_editor_property("slot").set_padding(unreal.Margin(0, 6, 0, 0))
    lanes = add(unreal.Overlay, f"Zone{i}Lanes", track.get_name())
    fill(rounded(add(unreal.Border, f"Zone{i}TrackBack", lanes.get_name()), 2.5, (0.0, 0.0, 0.0, 0.5)))
    lane = fill(add(unreal.HorizontalBox, f"Zone{i}Lane", lanes.get_name()))
    bar = add(unreal.SizeBox, f"Zone{i}Fill", lane.get_name())
    bar.set_width_override(0)
    bar.set_clipping(unreal.WidgetClipping.CLIP_TO_BOUNDS)
    bar.get_editor_property("slot").set_vertical_alignment(unreal.VerticalAlignment.V_ALIGN_FILL)
    rounded(add(unreal.Border, f"Zone{i}Ink", bar.get_name()), 2.5, WHITE)
    rest = add(unreal.Spacer, f"Zone{i}Rest", lane.get_name())
    rest.get_editor_property("slot").set_size(unreal.SlateChildSize(1.0, unreal.SlateSizeRule.FILL))


rim_texture, fill_texture = texture("HexRim"), texture("HexFill")
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
stack = add(unreal.VerticalBox, "Zones", "Root")
slot = stack.get_editor_property("slot")
slot.set_anchors(unreal.Anchors(minimum=unreal.Vector2D(0, 0), maximum=unreal.Vector2D(0, 0)))
slot.set_alignment(unreal.Vector2D(0, 0))
slot.set_position(unreal.Vector2D(*CORNER))
slot.set_auto_size(True)
for i, letter in enumerate("ABC"):
    row(i, letter, rim_texture, fill_texture)

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
label.set_editor_property("explicit_assets", [bp, rim_texture, fill_texture])
eal.save_loaded_asset(label)
unreal.log("MJOLNIR warfare zones built: three stacked zone bars, top left, chunk958")

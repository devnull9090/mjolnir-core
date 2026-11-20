"""Cook-only UMG tactical overview; all live tracking comes from native code.

Run through tools/ue/editor_cmd.ps1. Chunk 958 owns the tactical widget under
/Game/MJOLNIR/UI and its map-specific textures in /Game/MJOLNIR/TacticalMap.
"""
from pathlib import Path
import unreal

ROOT = "/Game/MJOLNIR/TacticalMap"
WIDGET_ROOT = "/Game/MJOLNIR/UI"
NAME = "WBP_MJOLNIRTacticalMap"
REPO = Path(__file__).resolve().parents[3]
ART = REPO / "levels/warfare/pwr/tactical-map"
ui = unreal.MjolnirUIBuilderLibrary
eal = unreal.EditorAssetLibrary
assets = unreal.AssetToolsHelpers.get_asset_tools()
CYAN = (0.35, 0.86, 0.93, 1)
WHITE = (0.9, 0.95, 0.96, 1)
MUTED = (0.44, 0.6, 0.65, 1)


def add(cls, name, parent=""):
    w = ui.add_widget(bp, cls, name, parent)
    if w is None:
        raise RuntimeError(f"Cannot create {name}")
    return w


def position(w, x, y, width, height):
    slot = w.get_editor_property("slot")
    slot.set_position(unreal.Vector2D(x, y))
    slot.set_size(unreal.Vector2D(width, height))
    return w


def block(name, value, x, y, width, size=24, color=WHITE, parent="Root"):
    w = position(add(unreal.TextBlock, name, parent), x, y, width, size * 1.8)
    w.set_text(unreal.Text(value))
    font = w.get_editor_property("font")
    font.set_editor_property("size", size)
    w.set_editor_property("font", font)
    w.set_color_and_opacity(unreal.SlateColor(unreal.LinearColor(*color)))
    return w


def rect(name, x, y, width, height, color, parent="Root"):
    w = position(add(unreal.Image, name, parent), x, y, width, height)
    w.set_color_and_opacity(unreal.LinearColor(*color))
    return w


textures = {}
for name in ("overview", "player", "hog", "tank", "banshee", "pelican", "base", "capture"):
    source = ART / f"{name}.png"
    if not source.is_file():
        raise RuntimeError(f"Missing authored tactical map art: {source}")
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", str(source))
    task.set_editor_property("destination_path", ROOT)
    task.set_editor_property("destination_name", "T_PWR_" + name)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    assets.import_asset_tasks([task])
    tex = eal.load_asset(f"{ROOT}/T_PWR_{name}")
    tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_EDITOR_ICON)
    tex.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_UI)
    tex.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_SIMPLE_AVERAGE)
    tex.set_editor_property("never_stream", True)
    tex.set_editor_property("srgb", True)
    eal.save_loaded_asset(tex)
    textures[name] = tex

if eal.does_asset_exist(f"{WIDGET_ROOT}/{NAME}"):
    eal.delete_asset(f"{WIDGET_ROOT}/{NAME}")
bp = ui.create_widget_blueprint(WIDGET_ROOT, NAME, None)
viewport = add(unreal.CanvasPanel, "Viewport")
viewport.set_visibility(unreal.SlateVisibility.HIT_TEST_INVISIBLE)
fit = add(unreal.ScaleBox, "Fit", "Viewport")
slot = fit.get_editor_property("slot")
slot.set_anchors(unreal.Anchors(minimum=unreal.Vector2D(0, 0), maximum=unreal.Vector2D(1, 1)))
slot.set_offsets(unreal.Margin(0, 0, 0, 0))
fit.set_stretch(unreal.Stretch.SCALE_TO_FIT)
design = add(unreal.SizeBox, "Design", "Fit")
design.set_width_override(2560)
design.set_height_override(1440)
add(unreal.CanvasPanel, "Root", "Design")
rect("Veil", 0, 0, 2560, 1440, (0.002, 0.008, 0.013, 0.64))
rect("Panel", 420, 62, 1720, 1316, (0.006, 0.02, 0.028, 0.97))
rect("Accent", 420, 62, 1720, 3, CYAN)
block("Eyebrow", "UNSC  /  FIELD OPERATIONS", 480, 87, 1000, 21, CYAN)
block("Title", "TACTICAL OVERVIEW", 480, 120, 1120, 38)
block("Mode", "PELICAN WARFARE", 1680, 103, 420, 22, MUTED)
block("LiveStatus", "ACQUIRING FIELD TELEMETRY", 1680, 142, 420, 18, CYAN)

rect("MapRim", 477, 207, 1106, 1106, (0.24, 0.44, 0.49, 1))
clip = position(add(unreal.CanvasPanel, "MapClip", "Root"), 480, 210, 1100, 1100)
clip.set_clipping(unreal.WidgetClipping.CLIP_TO_BOUNDS_ALWAYS)
background = rect("Overview", 0, 0, 1100, 1100, (1, 1, 1, 1), "MapClip")
background.set_brush_from_texture(textures["overview"])
# All map items share this exact 1100px coordinate space, north up.
for i in range(1, 5):
    at = 1100 * i / 5
    rect(f"GridX{i}", 480 + at, 210, 1, 1100, (0.55, 0.8, 0.85, 0.12))
    rect(f"GridY{i}", 480, 210 + at, 1100, 1, (0.55, 0.8, 0.85, 0.12))
for i in range(5):
    block(f"GridCol{i}", chr(65 + i), 480 + 220 * i + 102, 216, 40, 16, MUTED)
    block(f"GridRow{i}", str(i + 1), 487, 210 + 220 * i + 100, 40, 16, MUTED)
block("North", "N", 1529, 230, 42, 26, WHITE)
rect("NorthLine", 1543, 269, 2, 23, CYAN)
marks = position(add(unreal.CanvasPanel, "MapMarks", "Root"), 480, 210, 1100, 1100)
marks.set_clipping(unreal.WidgetClipping.CLIP_TO_BOUNDS_ALWAYS)

for i in range(64):
    marker = rect(f"Mark{i}", 0, 0, 34, 34, WHITE, "MapMarks")
    marker.set_brush_from_texture(textures["player"])
    marker.set_visibility(unreal.SlateVisibility.COLLAPSED)
    label = block(f"Label{i}", "", 0, 0, 240, 18, parent="MapMarks")
    label.set_visibility(unreal.SlateVisibility.COLLAPSED)

block("ScoreTitle", "CONTROL SCORE", 1640, 230, 430, 20, MUTED)
block("RedScore", "RED   000", 1640, 278, 430, 32, (1, 0.36, 0.3, 1))
block("BlueScore", "BLUE  000", 1640, 327, 430, 32, (0.3, 0.65, 1, 1))
rect("Rule1", 1640, 399, 430, 1, (0.24, 0.44, 0.49, 0.7))
block("ObjectivesTitle", "CAPTURE SITES", 1640, 428, 430, 20, MUTED)
for i, letter in enumerate("ABC"):
    block(f"Site{i}", f"{letter}   /   WAITING", 1640, 478 + i * 48, 430, 25)
rect("Rule2", 1640, 652, 430, 1, (0.24, 0.44, 0.49, 0.7))
block("LegendTitle", "FIELD SYMBOLS", 1640, 680, 430, 20, MUTED)
legend = [("player", "YOU / TEAMMATES"), ("hog", "WARTHOG"), ("tank", "SCORPION"),
          ("banshee", "BANSHEE"), ("pelican", "PELICAN"), ("base", "TEAM BASE")]
for i, (kind, title) in enumerate(legend):
    icon = rect(f"LegendIcon{i}", 1640, 735 + i * 56, 32, 32, CYAN)
    icon.set_brush_from_texture(textures[kind])
    block(f"LegendText{i}", title, 1692, 735 + i * 56, 380, 21)
block("IntelNote", "FRIENDLY + AVAILABLE VEHICLES", 1640, 1103, 445, 17, MUTED)
block("Position", "", 1640, 1157, 440, 20, CYAN)
block("TeamStatus", "", 1640, 1201, 440, 20, WHITE)
block("CloseHint", "[ M ]  CLOSE MAP     [ N ]  ZOOM", 480, 1331, 720, 21, CYAN)
block("Scale", "NORTH UP  /  2 KM x 2 KM", 1200, 1331, 660, 19, MUTED)

if not ui.compile_widget(bp):
    raise RuntimeError("Tactical map widget compile failed")
eal.save_loaded_asset(bp)
label_path = f"{ROOT}/PAL_PWR_TacticalMap"
label = eal.load_asset(label_path) if eal.does_asset_exist(label_path) else assets.create_asset(
    "PAL_PWR_TacticalMap", ROOT, unreal.PrimaryAssetLabel, unreal.DataAssetFactory())
rules = label.get_editor_property("rules")
rules.set_editor_property("chunk_id", 958)
rules.set_editor_property("apply_recursively", True)
rules.set_editor_property("cook_rule", unreal.PrimaryAssetCookRule.ALWAYS_COOK)
label.set_editor_property("rules", rules)
label.set_editor_property("label_assets_in_my_directory", False)
label.set_editor_property("explicit_assets", [bp, *textures.values()])
eal.save_loaded_asset(label)
unreal.log("MJOLNIR tactical map built: 64 pooled markers, north-up 2km bounds, chunk958")

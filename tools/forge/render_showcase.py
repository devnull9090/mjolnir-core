"""Reproduce the blog's real-mesh illustration without regenerating pack sources.

Render (Blender 5.2 LTS):
  blender --background --factory-startup --python tools/forge/render_showcase.py
Encode all four WebPs (normal Python with Pillow):
  python tools/forge/render_showcase.py --web

The assembly is a studio illustration, not a baked or play-tested map. All
construction uses unchanged Foundry Wide meshes at scale 1. Materials/lighting
are Blender previews; the green field is not the game's animated CE shader.
Only the studio floor and two-metre scale ruler are presentation geometry.
PNG, blend and provenance reports go into the pack's ignored build directory;
the four WebPs go into hub/public/blog-images/forge-building.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "forge-packs/foundry-wide"
BUILD = PACK / "build/blog-showcase"
WEB = ROOT / "hub/public/blog-images/forge-building"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def placements():
    """Metres/Z-up, bottom-centre origins; never stretch a construction piece."""
    rows = []

    def add(ident, x, y, z=0, yaw=0):
        rows.append({"id": ident, "position_m": [x, y, z], "yaw_deg": yaw})

    for x in (-8, 8):
        for y in (-8, 8):
            add("floor_4x4", x, y, -.5)  # Finished courtyard floor Z=0.
    for x in (-8, 0, 8):
        add("floor_2x2", x, 12, 3.5)  # Finished gallery floor Z=4.
        add("wall", x, 15.5)
    for x in (-10, 10):
        for y in (10, 14):
            add("column", x, y, -.5)
    add("ramp_wide_high", 8, 0)  # Nose Y=-8/Z=0; crest Y=8/Z=4.
    add("doorway_tall", -8, 7.5)
    add("door_panel", -8, 6.75)  # Separate matching panel, closed for this still.
    add("window_glazed", 0, 7.5)
    for x in (-8, 8):
        add("glass_wall", x, 15.5, 4)
    add("glass_wall", 11.5, 12, 4, 90)
    add("teleporter_housing", 0, 15.5, 4)
    # Leave the left gallery mouth open where the bridge joins it.
    add("railing", 0, 8.25, 4)
    add("bridge_straight", -8, 4, 3.5)
    add("floor_1x1", -8, -2, 3.5)
    add("column", -8, 0, -.5)
    add("railing", -10.25, 4, 4, 90)
    add("railing", -5.75, 4, 4, 90)
    add("lift_station", -8, -8)
    add("cover", -.5, -6)
    add("cover", -.5, 0)
    return rows


def render(args):
    import bpy
    from mathutils import Vector

    module_spec = importlib.util.spec_from_file_location("showcase_wide_helpers", PACK / "build_blender.py")
    helpers = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(helpers)
    source_path = PACK / "source/geometry.json"
    source_hash = digest(source_path)
    source = json.loads(source_path.read_bytes())
    pieces = {p["id"]: p for p in source["pieces"]}
    rows = placements()
    args.build.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    scene.unit_settings.system, scene.unit_settings.scale_length = "METRIC", 1
    library = bpy.data.collections.new("Source mesh prototypes")
    assembly = bpy.data.collections.new("Unscaled Foundry Wide assembly")
    stage = bpy.data.collections.new("Studio presentation only")
    for collection in (library, assembly, stage):
        scene.collection.children.link(collection)
    materials = {name: helpers.material(name, spec) for name, spec in source["materials"].items()}
    prototypes = {}
    for row in rows:
        ident = row["id"]
        if ident not in prototypes:
            parts = []
            for index, component in enumerate(pieces[ident]["visual"]):
                obj = helpers.mesh_object(f"{ident}_{index:02}", component, library)
                obj.data.materials.append(materials[component["material"]])
                if component["bevel_m"]:
                    helpers.select_only([obj])
                    bevel = obj.modifiers.new("Authored cosmetic bevel", "BEVEL")
                    bevel.width, bevel.segments = component["bevel_m"], 2
                    bevel.limit_method, bevel.angle_limit = "ANGLE", math.radians(20)
                    bpy.ops.object.modifier_apply(modifier=bevel.name)
                parts.append(obj)
            helpers.select_only(parts)
            bpy.ops.object.join()
            prototypes[ident] = bpy.context.view_layer.objects.active
        obj = prototypes[ident].copy()
        obj.name = f"{len(assembly.objects):02} / {ident}"
        obj.location = row["position_m"]
        obj.rotation_euler.z = math.radians(row["yaw_deg"])
        obj.scale = (1, 1, 1)
        obj["pack_id"], obj["block_id"] = "foundry-wide", ident
        assembly.objects.link(obj)
    library.hide_render, library.hide_viewport = True, True

    studio = helpers.material("Studio slate", {"base_color": [.032, .048, .064, 1], "metallic": .05, "roughness": .86})
    ground = helpers.mesh_object("Studio floor (not a pack item)", helpers.original.box(200, 200, .1, z=-.7), stage)
    ground.data.materials.append(studio)
    # A two-metre ruler supplies scale without implying a new character asset.
    ruler = helpers.mesh_object("Two-metre scale ruler", helpers.original.box(.09, 2, .025, 13.7, -10.5), stage)
    ruler.data.materials.append(materials["amber"])
    for y in (-11.5, -10.5, -9.5):
        tick = helpers.mesh_object("Ruler tick", helpers.original.box(.45, .07, .025, 13.7, y), stage)
        tick.data.materials.append(materials["amber"])
    helpers.label("2 m", 14.2, -10.8, .48, materials["amber"], stage)

    camera_data = bpy.data.cameras.new("Orthographic assembly camera")
    camera = bpy.data.objects.new(camera_data.name, camera_data)
    stage.objects.link(camera)
    camera.location = (39, -49, 37)
    target = Vector((0, 1.2, 2))
    camera.rotation_euler = (target-camera.location).to_track_quat("-Z", "Y").to_euler()
    camera_data.type, camera_data.ortho_scale = "ORTHO", 47
    scene.camera = camera
    for name, position, power, size, color in (
        ("Soft key", (2, -12, 32), 23000, 20, (1, .91, .8)),
        ("Cool fill", (-20, -3, 20), 16000, 18, (.72, .85, 1)),
        ("Gallery rim", (7, 24, 26), 23000, 15, (.91, .96, 1)),
    ):
        data = bpy.data.lights.new(name, "AREA")
        data.energy, data.shape, data.size, data.color = power, "DISK", size, color
        light = bpy.data.objects.new(name, data)
        stage.objects.link(light)
        light.location = position
        light.rotation_euler = (target-light.location).to_track_quat("-Z", "Y").to_euler()
    scene.world.use_nodes = True
    world = scene.world.node_tree.nodes["Background"]
    world.inputs["Color"].default_value = (.12, .17, .22, 1)
    world.inputs["Strength"].default_value = .45
    scene.render.engine = "CYCLES"
    scene.cycles.samples, scene.cycles.use_denoising = args.samples, True
    scene.render.resolution_x, scene.render.resolution_y = 1920, 1280
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(args.build / "assembly.png")
    scene.view_settings.view_transform = "AgX"
    bpy.ops.wm.save_as_mainfile(filepath=str(args.build / "assembly.blend"))
    bpy.ops.render.render(write_still=True)
    assert source_hash == digest(source_path), "Source geometry changed during render"
    report = {
        "kind": "Blender studio illustration, not a play-tested map",
        "blender": bpy.app.version_string, "samples": args.samples,
        "source": str(source_path.relative_to(ROOT)),
        "source_sha256": source_hash, "piece_count": len(rows), "placements": rows,
        "all_piece_scales": [1, 1, 1], "materials": "Authored Blender preview materials",
        "presentation_only": ["studio floor", "two-metre ruler"],
        "output_sha256": digest(args.build / "assembly.png"),
    }
    (args.build / "assembly-report.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print(f"SHOWCASE_RENDER_OK: {len(rows)} unchanged pack placements", flush=True)


def web(args):
    from PIL import Image

    args.output.mkdir(parents=True, exist_ok=True)
    sources = {
        "foundry": ROOT / "forge-packs/foundry/art/foundry-contact-sheet.png",
        "foundry-wide": PACK / "art/foundry-wide-contact-sheet.png",
        "roadworks": ROOT / "forge-packs/roadworks/art/roadworks-contact-sheet.png",
        "assembly": args.build / "assembly.png",
    }
    report = []
    for name, path in sources.items():
        before = digest(path)
        with Image.open(path) as source:
            image = source.convert("RGB")
            image.thumbnail((2400, 4000), Image.Resampling.LANCZOS)
            dest = args.output / f"{name}.webp"
            image.save(dest, "WEBP", quality=86, method=6)
            report.append({"name": name, "dimensions": list(image.size), "bytes": dest.stat().st_size,
                           "source": str(path.relative_to(ROOT)), "source_sha256": before,
                           "sha256": digest(dest)})
        assert before == digest(path), "Encoding modified its source PNG"
    args.build.mkdir(parents=True, exist_ok=True)
    (args.build / "web-report.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--web", action="store_true", help="Encode existing PNGs with Pillow; no Blender required.")
    parser.add_argument("--build", type=Path, default=BUILD)
    parser.add_argument("--output", type=Path, default=WEB)
    parser.add_argument("--samples", type=int, default=48)
    argv = (sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv
            else [] if "--python" in sys.argv else sys.argv[1:])
    args = parser.parse_args(argv)
    if not 1 <= args.samples <= 256:
        parser.error("--samples must be between 1 and 256")
    args.build, args.output = args.build.resolve(), args.output.resolve()
    (web if args.web else render)(args)


if __name__ == "__main__":
    main()

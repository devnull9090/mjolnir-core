"""Build a separate playtest art scene from the version-four vehicle guide master."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy
from mathutils import Matrix

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import polish_citadel
import polish_home
import polish_gate_lights
import validate_bases


def digest(path):
    with path.open("rb") as data:
        return hashlib.file_digest(data, "sha256").hexdigest()


def refine_edges(destination):
    """Rebuild the front roof edge and stair cheeks on an isolated copy of playtest seven."""
    import polish_roof_edge
    import polish_ramp_ridges
    import polish_rear_gate

    source = Path(bpy.data.filepath).resolve()
    destination = Path(destination).resolve()
    if not source.name.endswith("playtest7.blend") or destination == source:
        raise ValueError("Open the playtest-seven base scene and choose a new output")
    originals = {obj.name for obj in bpy.context.scene.objects if obj.type == "MESH"}
    polish_roof_edge.build()
    polish_ramp_ridges.build()
    bpy.context.view_layer.update()
    revised = {obj.name for obj in bpy.context.scene.objects if obj.type == "MESH"}
    destination.parent.mkdir(parents=True, exist_ok=True)
    validate_bases.OUT = destination.parent / "clearance.json"
    clearance = validate_bases.main()
    if not clearance["passed"]:
        raise ValueError(f"Base geometry checks failed: {clearance['failed_checks']}")
    rear_gate = polish_rear_gate.verify()
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(destination), relative_remap=True)
    clearance["blend"] = str(destination)
    validate_bases.OUT.write_text(json.dumps(clearance, indent=2) + "\n", encoding="utf-8")
    receipt = {"source":str(source), "source_sha256":digest(source), "scene":str(destination),
               "scene_sha256":digest(destination), "added_meshes":sorted(revised-originals),
               "removed_meshes":sorted(originals-revised), "rear_gate":rear_gate,
               "mirror_pairs":clearance["checks"]["red_blue_mirror"]["paired_objects"]}
    (destination.parent / "assembly.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def finish_paving(destination):
    """Apply the shared cosmetic finishing kit while keeping all physical surfaces."""
    import polish_paving_faces
    import polish_flank_faces
    import polish_rear_gate
    source = Path(bpy.data.filepath).resolve()
    destination = Path(destination).resolve()
    if not source.name.endswith("playtest6.blend") or source == destination:
        raise ValueError("Open the wide-gate playtest-six scene and choose a new output")
    pieces, paving = polish_paving_faces.build()
    pieces += polish_flank_faces.build()
    if any(ob.get("pwr_polish_solid") for ob in pieces):
        raise ValueError("The paving finish must preserve the accepted collision")
    destination.parent.mkdir(parents=True, exist_ok=True)
    validate_bases.OUT = destination.parent / "clearance.json"
    checked = validate_bases.main()
    gate = polish_rear_gate.verify()
    if not checked["passed"]:
        raise ValueError(f"Playtest-seven geometry validation failed: {checked['failed_checks']}")
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(destination), relative_remap=True)
    checked["blend"] = str(destination)
    validate_bases.OUT.write_text(json.dumps(checked,indent=2)+"\n",encoding="utf-8")
    receipt = {"source":str(source), "source_sha256":digest(source), "scene":str(destination),
               "scene_sha256":digest(destination), "pieces":[o.name for o in pieces],
               "paving":paving, "rear_gate":gate}
    (destination.parent / "assembly.json").write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
    return receipt


def build_wide_gates(destination, collision_contract):
    """Build the widened playtest-six gates from the sealed playtest-five authoring scene."""
    import polish_pewter
    import polish_rear_gate
    destination = Path(destination).resolve()
    source = Path(bpy.data.filepath).resolve()
    contract = Path(collision_contract).resolve()
    if source.name != "forerunner-bases-playtest5-final.blend" or source == destination:
        raise ValueError("Open the sealed playtest-five scene and choose a separate output file")
    original = json.loads(contract.read_text(encoding="utf-8"))
    spans = {(r["team"],r["name"]):r for r in original["replacement_objects"]}
    pieces, profiles = polish_pewter.build()
    patch = polish_rear_gate.build()
    for entry in patch["objects"]:
        if entry["structural"]:
            record = spans[entry["site"],entry["name"]]
            entry["previous_native_span"] = {k:record[k] for k in
                ("first_extra_surface","surfaces","triangle_f64_le_sha256")}
    patch["validation"] = polish_rear_gate.verify()
    destination.parent.mkdir(parents=True, exist_ok=True)
    validate_bases.OUT = destination.parent / "clearance.json"
    clearance = validate_bases.main()
    if not clearance["passed"]:
        raise ValueError(f"Geometry checks failed: {clearance['failed_checks']}")
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(destination), relative_remap=True)
    patch.update(source_scene=str(source), source_sha256=digest(source),
                 native_structure_manifest=str(contract), scene=str(destination),
                 scene_sha256=digest(destination))
    clearance["blend"] = str(destination)
    receipts = {"clearance":clearance, "patch":patch,
                "pewter":{"pieces":[o.name for o in pieces], "profiles":profiles}}
    for name, data in receipts.items():
        (destination.parent / (name + ".json")).write_text(
            json.dumps(data,indent=2) + "\n", encoding="utf-8")
    return patch


def build(destination):
    destination = Path(destination).resolve()
    source = Path(bpy.data.filepath).resolve()
    if source.name != "forerunner-portal-guides.blend" or destination == source:
        raise ValueError("Open the version-four portal guides scene and choose a new output file")
    red, blue, green = (next(c for c in bpy.data.collections if c.name.startswith(prefix))
                        for prefix in ("01_RED", "02_BLUE", "03_GREEN"))
    guides = [o for o in blue.objects if o.get("purpose") == "Visual vehicle route marking"]
    if len(guides) != 4:
        raise ValueError("The blue base must contain the four original approach guides")
    for ob in guides:
        original = red.objects[ob.name.replace("blue | ", "red | ", 1)]
        if original.data != ob.data:
            raise ValueError(f"Unlinked version-four guide {ob.name}")
        ob["mirror_source_object"] = original.name

    homes = polish_home.build() + polish_gate_lights.build()
    green_front = []
    for original in (o for o in homes if o["pwr_polish_site"] == "red"):
        ob = original.copy()
        ob.name = "03_GREEN/" + original.name
        green.objects.link(ob)
        ob.matrix_world = Matrix.Translation((0, 150, 0)) @ original.matrix_world
        ob["pwr_polish_site"] = "green"
        ob["source_object_name"] = original.name
        for slot in ob.material_slots:
            if slot.material == bpy.data.materials["TEAM • red recessed energy"]:
                slot.link = "OBJECT"
                slot.material = bpy.data.materials["TEAM • green recessed energy"]
        green_front.append(ob)
    citadel = polish_citadel.build()
    bpy.context.view_layer.update()
    destination.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(destination), relative_remap=True)
    validate_bases.OUT = destination.parent / "clearance.json"
    report = validate_bases.main()
    if not report["passed"]:
        raise ValueError(f"Base clearance or mirror validation failed: {report['failed_checks']}")
    additions = homes + green_front + citadel
    receipt = {"source": str(source), "source_sha256": digest(source),
               "scene": str(destination), "scene_sha256": digest(destination),
               "clearance": str(validate_bases.OUT), "sites": {}}
    for team in ("red", "blue", "green"):
        site = [o for o in additions if o["pwr_polish_site"] == team]
        receipt["sites"][team] = {"added": [o.name for o in site],
            "collision_cores": [o.name for o in site if o.get("pwr_polish_solid")]}
    (destination.parent / "assembly.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--gate-contract", type=Path,
                        help="Build the widened playtest-six gates from playtest five using the original base collision contract")
    mode.add_argument("--finish-paving", action="store_true",
                      help="Apply the final machined finishes to the verified wide-gate scene")
    mode.add_argument("--refine-edges", action="store_true",
                      help="Rebuild the roof bevel and ramp sidewalls from playtest seven")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    if args.refine_edges:
        refine_edges(args.out)
    elif args.finish_paving:
        finish_paving(args.out)
    elif args.gate_contract:
        build_wide_gates(args.out, args.gate_contract)
    else:
        build(args.out)

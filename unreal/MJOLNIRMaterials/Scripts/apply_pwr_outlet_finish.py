"""Reopen and finish the registered.36 outlet only."""

from hashlib import sha256
import json
import math
import os
from pathlib import Path
import sys
import traceback
import unreal as ue

ROOT = Path(os.environ["PWR_HEADWATER_ROOT"])
BASE = ROOT / "out/pwr/river-apron"
W = BASE / "finish37"
sys.path.insert(0, str(ROOT / "unreal/MJOLNIRMaterials/Scripts"))
import apply_pwr_outlet_bank as strip

VERIFY = os.environ.get("PWR_HEADWATER_VERIFY") == "1"
PLANTS = {
    "rye": ("PWR_WindMeadow", "PWRBlade_MJFol_1_1_0"),
    "wild_a": ("PWR_WindMeadow", "PWRBlade_MJFol_2_1_0"),
    "wild_b": ("PWR_WindMeadow", "PWRBlade_MJFol_3_1_0"),
    "sedge": ("MJOLNIR_Foliage", "MJFol_2_1_0"),
    "rush": ("PWR_FieldUnderstory", "MJFol_13_1_0"),
    "fine_a": ("PWR_FineMeadow", "PWRBlade_MJFol_1_1_0"),
    "fine_b": ("PWR_FineMeadow", "PWRBlade_MJFol_2_1_0"),
}


def data(p):
    return json.loads(p.read_text())


def save(p, x):
    p.write_text(json.dumps(x, separators=(",", ":")))


def digest_unchanged(path, src, expr, shader):
    return (
        sha256(src.encode()).hexdigest() == data(path)["terrain"]
        and expr.get_editor_property("code") == shader
    )


def materials():
    lib = ue.MaterialEditingLibrary
    prop = ue.MaterialProperty
    sha = lambda text: sha256(text.encode()).hexdigest()
    land = ue.load_asset(strip.FOLDER + "M_PWRPilot")
    node = lib.get_material_property_input_node(land, prop.MP_BASE_COLOR)
    current = node.get_editor_property("code").replace("\r\n", "\n").strip()
    root = data(BASE / "bank/material.json")["shader_sha256"]
    bank = ue.load_asset(strip.FOLDER + strip.MATERIAL)
    expr = lib.get_material_property_input_node(bank, prop.MP_BASE_COLOR)
    shader = """float l=dot(scan,float3(.24,.59,.17));
    float3 grain=clamp(scan/max(l,.012),.72,1.31);
    return tint*(.50+.88*smoothstep(.025,.31,l))*lerp(1.,grain,.65);"""
    saved = W / "materials.json"
    if VERIFY or (saved.exists() and digest_unchanged(saved, src, expr, shader)):
        if (
            expr.get_editor_property("code") != shader
            or sha(current) != data(W / "materials.json")["terrain"]
        ):
            raise ValueError("Reopened outlet graph differs")
        return
    if sha(current) == root:
        token = "rock=lerp(rock,rock*1.18+float3(.019,.017,.012),regionAP);"
        if current.count(token) != 1:
            raise ValueError("Registered .36 sediment graph missing")
        new = current.replace(
            token,
            """float submergedAP=1.-smoothstep(-.26,.065,level);
            float3 slate=lerp(float3(.88,.94,.98),float3(1.05,.97,.77),stain);
            float3 mineralAP=rock*slate*lerp(.63,1.40,submergedAP)+submergedAP*float3(.023,.025,.024);
            rock=lerp(rock,mineralAP,regionAP);""",
        )
        new = new.replace(
            "2.16*lerp(.88,1.13,h.w)",
            "lerp(2.16,3.86,regionAP*(1.-smoothstep(-.3,.12,level)))*lerp(.88,1.13,h.w)",
        )
        node.set_editor_property("code", new)
        lib.recompile_material(land)
        assert ue.EditorAssetLibrary.save_loaded_asset(land, False)
    else:
        if (
            not (W / "materials.json").exists()
            or sha(current) != data(W / "materials.json")["terrain"]
        ):
            raise ValueError("Expected .36 terrain")
        new = current
    expr.set_editor_property("code", shader)
    color = lib.get_inputs_for_material_expression(bank, expr)
    # The scan's packed alpha is its measured roughness. Keep a matte floor for exposed grit.
    rough = lib.get_material_property_input_node(bank, prop.MP_ROUGHNESS)
    rough.set_editor_properties(dict(const_a=0.94, const_b=0.78))
    spec = lib.create_material_expression(
        bank, ue.MaterialExpressionConstant, -190, 585
    )
    spec.set_editor_property("r", 0.13)
    assert lib.connect_material_property(spec, "", prop.MP_SPECULAR)
    # Small diffuse skylight approximation restricted to shaded soil, never the wet mineral.
    vc = next(o for o in color if isinstance(o, ue.MaterialExpressionVertexColor))
    sky = lib.create_material_expression(bank, ue.MaterialExpressionCustom, -310, 690)
    inp = ue.CustomInput()
    inp.set_editor_property("input_name", "stone")
    sky.set_editor_properties(
        dict(
            code="return (1.-stone)*float3(.0061,.0060,.0055);",
            inputs=[inp],
            output_type=ue.CustomMaterialOutputType.CMOT_FLOAT3,
        )
    )
    assert lib.connect_material_expressions(vc, "A", sky, "stone")
    assert lib.connect_material_property(sky, "", prop.MP_EMISSIVE_COLOR)
    base_normal = lib.get_material_property_input_node(bank, prop.MP_NORMAL)
    base_normal.set_editor_property("const_alpha", 0.51)
    # Per-texel photographed roughness remains between 0.60 and 0.91 on all stone.
    scan = next(o for o in color if isinstance(o, ue.MaterialExpressionTextureSample))
    roughnode = lib.create_material_expression(
        bank, ue.MaterialExpressionCustom, -350, -320
    )
    ip = []
    for pn in ("gloss", "stone"):
        pin = ue.CustomInput()
        pin.set_editor_property("input_name", pn)
        ip.append(pin)
    roughnode.set_editor_properties(
        dict(
            inputs=ip,
            code="return lerp(.93,clamp(.43+.49*gloss,.60,.91),stone);",
            output_type=ue.CustomMaterialOutputType.CMOT_FLOAT1,
        )
    )
    assert lib.connect_material_expressions(scan, "A", roughnode, "gloss")
    assert lib.connect_material_expressions(vc, "A", roughnode, "stone")
    assert lib.connect_material_property(roughnode, "", prop.MP_ROUGHNESS)
    lib.recompile_material(bank)
    assert ue.EditorAssetLibrary.save_loaded_asset(bank, False)
    save(W / "materials.json", dict(terrain=sha(new), parent=root, bank=sha(shader)))


def plants():
    levels = ue.get_editor_subsystem(ue.LevelEditorSubsystem)
    assert levels.load_level(strip.WORLD)
    actors = ue.get_editor_subsystem(ue.EditorActorSubsystem).get_all_level_actors()
    comps = {
        (a.get_actor_label(), c.get_name()): (a, c)
        for a in actors
        for c in a.get_components_by_class(ue.InstancedStaticMeshComponent)
    }
    updates = data(W / "vegetation.json")
    parent = data(BASE / "bank/placements.json")
    parentplants = data(BASE / "bank/planting.json")
    proof = data(W / "vegetation-applied.json") if VERIFY else {}
    for key, rows in updates.items():
        a, c = comps[PLANTS[key]]
        if VERIFY:
            record = proof[key]
            if c.get_instance_count() != record["after"]:
                raise ValueError((key, c.get_instance_count(), record["after"]))
            valid = {}
            box = ue.Box(
                min=ue.Vector(-33000, -86000, 13000),
                max=ue.Vector(-25800, -77800, 16500),
            )
            for i in c.get_instances_overlapping_box(box, True):
                t = c.get_instance_transform(i, True)
                valid[tuple(round(v, 1) for v in t.translation.to_tuple())] = (
                    t.scale3d.to_tuple()
                )
            for p, t in record["live"]:
                if tuple(p) not in valid or math.dist(t, valid[tuple(p)]) > 0.001:
                    raise ValueError((key, p, t))
            if any(tuple(p) in valid for p in record["gone"]):
                raise ValueError("Removed tuft remained in " + key)
            continue
        c.modify()
        a.modify()
        start = c.get_instance_count()
        live = []
        gone = []
        if key.startswith("fine_"):
            mesh = c.get_editor_property("static_mesh")
            box = mesh.get_bounding_box()
            height = box.max.z - box.min.z
            transforms = []
            for r in rows:
                t = ue.Transform()
                t.translation = ue.Vector(*r["position"])
                z = r["height"] / height
                t.scale3d = ue.Vector(z * r["breadth"], z * r["breadth"], z)
                x = math.radians(r["yaw"]) / 2
                t.rotation = ue.Quat(0, 0, math.sin(x), math.cos(x))
                transforms.append(t)
                live.append(
                    (
                        [round(v, 1) for v in t.translation.to_tuple()],
                        t.scale3d.to_tuple(),
                    )
                )
            c.add_instances(transforms, False, True, False)
        else:
            base = parent[key]["before"]
            originals = [r for r in parentplants if r["kind"] == key]
            if start != base + len(originals):
                raise ValueError((key, start))
            for r in rows:
                i = base + r["index"]
                t = c.get_instance_transform(i, True)
                p = t.translation.to_tuple()
                if math.dist(p, originals[r["index"]]["position"]) > 0.15:
                    raise ValueError("Unrecognized .36 planting")
                pos = [round(v, 1) for v in p]
                if r.get("remove"):
                    gone.append(pos)
                    continue
                t.scale3d = ue.Vector(
                    *[u * v for u, v in zip(t.scale3d.to_tuple(), r["scale"])]
                )
                assert c.update_instance_transform(i, t, True, False, True)
                live.append((pos, t.scale3d.to_tuple()))
            for i in sorted(
                (r["index"] + base for r in rows if r.get("remove")), reverse=True
            ):
                assert c.remove_instance(i)
        proof[key] = dict(
            before=start, after=c.get_instance_count(), live=live, gone=gone
        )
    if VERIFY:
        save(
            W / "editor-verified.json",
            dict(
                placements=sum(len(r["live"]) for r in proof.values()),
                removed=sum(len(r["gone"]) for r in proof.values()),
                vegetation=sha256((W / "vegetation.json").read_bytes()).hexdigest(),
                mesh=data(W / "surface-verified.json"),
                materials=data(W / "materials.json"),
            ),
        )
    else:
        assert levels.save_current_level()
        save(W / "vegetation-applied.json", proof)


try:
    if VERIFY or not (W / "surface-built.json").exists():
        strip.place_surface(W, VERIFY)
    materials()
    if VERIFY or not (W / "vegetation-applied.json").exists():
        plants()
except:
    (W / ("verify.err" if VERIFY else "apply.err")).write_text(traceback.format_exc())
    raise

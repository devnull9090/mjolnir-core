"""Author or verify the local lake vegetation in the already loaded LPE level."""
import json
import hashlib
import math
import os
from pathlib import Path
import struct

import unreal as ue


FOLDER = "/Game/MJOLNIR/GrassPilot/Playable/"
SUN = """float Y=dot(Atlas,float3(.2126,.7152,.0722));
float leaf=saturate((Atlas.g-Atlas.b)*2.1/(.09+Y));
float t=smoothstep(.13,.90,Tip);
float3 olive=Y*lerp(float3(.99,1.06,.50),float3(1.12,1.05,.43),Seed);
float3 pigment=lerp(Atlas,olive,(.31+.34*leaf)*(.66+.34*t));
float fleck=smoothstep(.71,.98,t)*smoothstep(.12,.38,Y)*lerp(.16,1.,smoothstep(.47,.92,Seed));
float3 tips=float3(.078,.068,.012)*fleck*(.34+.66*leaf);
return saturate(pigment*Lift*lerp(.72,1.19,t)+tips);"""


def shoreline_materials(out, verify):
    assets = ue.EditorAssetLibrary
    lib = ue.MaterialEditingLibrary
    prop = ue.MaterialProperty
    name = "M_PWR_RiparianSun"
    master = ue.load_asset(FOLDER + name)
    if not master and not verify:
        master = assets.duplicate_asset(FOLDER + "M_PWR_WindBlade", FOLDER + name)
    if not master:
        raise ValueError("Missing lake blade material")
    output = lib.get_material_property_input_node(master, prop.MP_BASE_COLOR)
    if not output or set(str(i.get_editor_property("input_name")) for i in output.get_editor_property("inputs")) != {"Atlas","Seed","Tip","Lift"}:
        raise ValueError("The native wind blade no longer exposes its root-to-tip pigment inputs")
    graph = output.get_editor_property("code").replace("\r\n", "\n").strip()
    bounce = lib.get_material_property_input_node(master, prop.MP_EMISSIVE_COLOR)
    if graph != SUN or (bounce and bounce.get_editor_property("const_b") != 0.):
        if verify:
            raise ValueError("Missing lake crown palette")
        output.modify()
        output.set_editor_property("code", SUN)
        # The previous lake material added an all-over fill to the pigment. Let
        # actual directional and indirect light illuminate the scanned leaf now.
        if bounce:
            bounce.modify()
            bounce.set_editor_property("const_b", 0.)
        lib.recompile_material(master)
        assert assets.save_loaded_asset(master,False)
    willow = ue.load_asset(FOLDER + "T_PWR_RiparianWillow")
    if not willow and not verify:
        task = ue.AssetImportTask()
        task.set_editor_properties(dict(filename=str(out/"T_PWR_RiparianWillow.png"),
                    destination_path=FOLDER.rstrip("/"),destination_name="T_PWR_RiparianWillow",
                    automated=True,replace_existing=False,save=True))
        ue.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        willow = ue.load_asset(FOLDER + "T_PWR_RiparianWillow")
        willow.set_editor_properties(dict(srgb=True,virtual_texture_streaming=False,do_scale_mips_for_alpha_coverage=True,
                                           alpha_coverage_thresholds=ue.Vector4(0,0,0,.31)))
        assert assets.save_loaded_asset(willow,False)
    if not willow:
        raise ValueError("No native willow opacity and pigment atlas")
    palette = {}
    for short, atlas, values in (
        ("Canyon", ue.load_asset(FOLDER+"T_PWR_Wind_Canyon"), (101.,7.5,3500.,5350.,1.20)),
        ("Wild", ue.load_asset(FOLDER+"T_PWR_Wind_B30"), (37.,4.5,3500.,5350.,1.17)),
        ("Willow", willow,(125.,4.9,4200.,7100.,1.29))
    ):
        key = "MI_PWR_Riparian" + short
        inst = ue.load_asset(FOLDER+key)
        if not verify:
            inst = inst or ue.AssetToolsHelpers.get_asset_tools().create_asset(
                key,FOLDER.rstrip("/"),ue.MaterialInstanceConstant,ue.MaterialInstanceConstantFactoryNew())
            lib.set_material_instance_parent(inst,master)
            lib.set_material_instance_texture_parameter_value(inst,"BladeAtlas",atlas)
            for par, val in zip(("BladeHeight","TipSway","WindNear","WindFar","PigmentLift"),values):
                lib.set_material_instance_scalar_parameter_value(inst,par,val)
            lib.update_material_instance(inst)
            assert assets.save_loaded_asset(inst,False)
        if (not atlas or not inst or inst.get_editor_property("parent") != master
                or lib.get_material_instance_texture_parameter_value(inst,"BladeAtlas") != atlas
                or abs(lib.get_material_instance_scalar_parameter_value(inst,"PigmentLift")-values[-1])>.0002):
            raise ValueError("Wrong atlas or pigment on " + key)
        palette[key] = inst
    return palette


def run(verify=False):
    root = Path(os.environ["PWR_HEADWATER_ROOT"])
    out = root / "out/pwr/river-riparian/planting"
    plan = json.loads((out / "planting.json").read_text())
    specs = plan["groups"]
    owner = plan["owner"]
    world = ue.get_editor_subsystem(ue.UnrealEditorSubsystem).get_editor_world()
    if not world.get_path_name().startswith("/Game/Levels/Halo1/Solo/LPE/LPE."):
        raise ValueError("Expected loaded authoring LPE, got " + world.get_path_name())
    actors = ue.get_editor_subsystem(ue.EditorActorSubsystem)

    def find_owner():
        found = [a for a in actors.get_all_level_actors() if a.get_actor_label() == owner]
        if len(found) > 1:
            raise ValueError("Duplicate riparian vegetation owner")
        return found[0] if found else None

    binary = out / "riparian.bin"
    palette = shoreline_materials(out, verify)
    seal = hashlib.sha256((out/"planting.json").read_bytes())
    for g in range(1,len(specs)+1):
        seal.update(Path(str(binary)+".xf"+str(g)).read_bytes())
    revision = "RiparianLayout_" + seal.hexdigest()[:16]
    actor = find_owner()
    if actor and revision not in [str(tag) for tag in actor.get_editor_property("tags")]:
        if verify:
            raise ValueError("Saved native bank still has a prior planting layout")
        # Only replace the known render-only canopy from the previous revision.
        # Renaming before destruction frees the exact stable native object name.
        existing = actor.get_components_by_class(ue.HierarchicalInstancedStaticMeshComponent)
        if not existing or any(not c.get_name().startswith("PWRRiparian_") for c in existing):
            raise ValueError("Unexpected contents on prior vegetation owner")
        actor.modify()
        actor.rename("PWR_RiparianPrevious_"+seal.hexdigest()[:8])
        actor.set_actor_label(actor.get_name())
        if not actors.destroy_actor(actor):
            raise ValueError("Could not replace prior shoreline vegetation")
        actor = None
    if not actor and verify:
        raise ValueError("Missing saved " + owner)
    if not actor:
        count = ue.MjolnirUIBuilderLibrary.bake_foliage(
            world, str(binary), owner, [s["mesh"] for s in specs], [s["bands"] for s in specs],
            [ue.Vector2D(*s["cull"]) for s in specs], [32 + int(s["casts_shadow"]) for s in specs])
        if count != sum(s["count"] for s in specs):
            raise ValueError(("Incomplete riparian planting", count))
        actor = find_owner()
        actor.modify()
        actor.set_editor_property("tags",list(actor.get_editor_property("tags"))+[ue.Name(revision)])
    if not actor or actor.get_name() != owner:
        raise ValueError("Riparian scene owner not retained")
    components = {c.get_name(): c for c in actor.get_components_by_class(ue.HierarchicalInstancedStaticMeshComponent)}
    if len(components) != sum(s["bands"] for s in specs):
        raise ValueError("Unexpected riparian component count")
    results = []
    for group, spec in enumerate(specs, 1):
        exact = list(struct.iter_unpack("<10f", Path(str(binary) + ".xf" + str(group)).read_bytes()))
        if len(exact) != spec["count"]:
            raise ValueError("Stale riparian instance data")
        first, last = spec["cull"]
        for band in range(spec["bands"]):
            label = f"PWRRiparian_{spec['name']}_{band + 1}"
            comp = components.get(label)
            if comp is None and not verify:
                comp = components[f"MJFol_{group}_{band + 1}_0"]
                comp.modify()
                comp.rename(label)
            if comp is None or comp.get_name() != label:
                raise ValueError("Missing protected component " + label)
            end = int(first + (last - first) * (band + 1) / spec["bands"])
            start = end - 5600
            if not verify:
                comp.modify()
                comp.set_cull_distances(start, end)
                comp.set_evaluate_world_position_offset(True)
                comp.set_world_position_offset_disable_distance(spec["wind_until_cm"])
                if spec["material"]:
                    comp.set_material(0, palette[spec["material"]])
            mesh = comp.get_editor_property("static_mesh")
            bounds = mesh.get_bounding_box()
            actual_height = bounds.max.z - bounds.min.z
            if abs(actual_height - 2 * spec["source_extent_cm"][2]) > max(6., .12 * actual_height):
                raise ValueError((label, "stock reference height", actual_height, spec["source_extent_cm"]))
            props = [comp.get_editor_property(k) for k in ("instance_start_cull_distance", "instance_end_cull_distance")]
            if (props != [start, end] or mesh.get_path_name() != spec["mesh"]
                    or (spec["material"] and comp.get_material(0) != palette[spec["material"]])
                    or comp.get_editor_property("cast_shadow") != spec["casts_shadow"]
                    or not comp.get_editor_property("evaluate_world_position_offset")
                    or comp.get_editor_property("world_position_offset_disable_distance") != spec["wind_until_cm"]
                    or comp.get_collision_enabled() != ue.CollisionEnabled.NO_COLLISION):
                raise ValueError(("Riparian visuals or collision changed", label, props))
            rows = exact[band::spec["bands"]]
            if comp.get_instance_count() != len(rows):
                raise ValueError(("Unexpected count", label))
            for i, row in enumerate(rows):
                t = comp.get_instance_transform(i, True)
                quat = t.rotation.to_tuple()
                if (math.dist(t.translation.to_tuple(), row[:3]) > .04
                        or math.dist(t.scale3d.to_tuple(), row[7:]) > .0001
                        or min(math.dist(quat, row[3:7]), math.dist([-v for v in quat], row[3:7])) > .0001):
                    raise ValueError(("Riparian pose drift", label, i))
            results.append(dict(name=label, count=len(rows), mesh=mesh.get_path_name(), material=spec["material"],
                                start_cm=start, end_cm=end, source_height_cm=actual_height,
                                wind_until_cm=spec["wind_until_cm"], casts_shadow=spec["casts_shadow"]))
    report = dict(owner=owner, count=sum(v["count"] for v in results), components=results)
    name = "editor-verified.json" if verify else "editor-applied.json"
    (out / name).write_text(json.dumps(report, indent=2) + "\n")
    return report


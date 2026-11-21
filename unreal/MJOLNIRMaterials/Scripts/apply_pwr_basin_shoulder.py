"""Add the graded distant lake strand, retaining the verified foreground art."""

from hashlib import sha256
import math
import json
import os
from pathlib import Path
import traceback
import unreal as ue

ROOT = Path(os.environ["PWR_HEADWATER_ROOT"])
OUT = Path(os.environ["PWR_HEADWATER_OUTPUT"])
PARENT = ROOT / "out/pwr/river-apron/finish37"
VERIFY = os.environ.get("PWR_HEADWATER_VERIFY") == "1"
PLANTS = dict(
    fine_a=("PWR_FineMeadow", "PWRBlade_MJFol_1_1_0"),
    fine_b=("PWR_FineMeadow", "PWRBlade_MJFol_2_1_0"),
    sedge=("MJOLNIR_Foliage", "MJFol_2_1_0"),
    rush=("PWR_FieldUnderstory", "MJFol_13_1_0"),
    willow=("PWR_FieldUnderstory", "MJFol_17_1_0"),
)
PREVIOUS = dict(
    PLANTS,
    rye=("PWR_WindMeadow", "PWRBlade_MJFol_1_1_0"),
    wild_a=("PWR_WindMeadow", "PWRBlade_MJFol_2_1_0"),
    wild_b=("PWR_WindMeadow", "PWRBlade_MJFol_3_1_0"),
)


def read(path):
    return json.loads(path.read_text())


def save(path, obj):
    path.write_text(json.dumps(obj, indent=2))


def material():
    target = ue.load_asset("/Game/MJOLNIR/GrassPilot/Playable/M_PWRPilot")
    lib = ue.MaterialEditingLibrary
    node = lib.get_material_property_input_node(
        target, ue.MaterialProperty.MP_BASE_COLOR
    )
    src = node.get_editor_property("code").replace("\r\n", "\n").strip()
    digest = lambda x: sha256(x.encode()).hexdigest()
    prior = read(PARENT / "materials.json")["terrain"]
    receipt = OUT / "shore-material.json"
    if receipt.exists() and read(receipt)["shader_sha256"] == digest(src):
        return
    if VERIFY or digest(src) != prior:
        raise ValueError("Wrong source material for basin")
    plan = read(OUT / "basin-strand.json")
    rows = plan["rows"]
    begin, end = plan["y_limits"]
    code = (
        """
    // Only the newly graded far lake: actual quantized shore elevation controls wetness.
    float farAP=dot(hwXY-float2(-273.,785.),float2(-.54419,.83896));
    [branch] if(farAP>58.0 && hwXY.x> -491. && hwXY.x< -218. && hwXY.y>796. && hwXY.y<1000.) {
      const float2 basinRows[COUNT]={ROWVALS};
      float j=clamp((hwXY.y-796.)*.25,0.,LAST);
      float2 sides=lerp(basinRows[(int)j],basinRows[(int)j+1],frac(j));
      float reach=smoothstep(58.,71.,farAP)*smoothstep(-4.,7.,min(hwXY.x-sides.x,sides.y-hwXY.x));
      float level=WorldCM.z*.01-LAKEZ;
      float wav=.34*sin(hwXY.x*.74+hwXY.y*.21)+.25*cos(hwXY.y*.53+hwXY.x*.32);
      float strand=reach*(1.-smoothstep(.24,1.31,level+.38*wav))*smoothstep(-1.95,-.85,level);
      [branch] if (strand>.001) {
        float2 uv=hwXY/2.75+float2(.47,.20);
        float4 sed=Texture2DSampleGrad(RiverCobble,SiteEarthSampler,uv,hwDx/2.75,hwDy/2.75);
        float3 dirt=Texture2DSampleGrad(SiteEarth,SiteEarthSampler,hwXY/3.2,hwDx/3.2,hwDy/3.2).rgb;
        float sat=1.-smoothstep(-.08,.70,level+.15*wav);
        float3 land=lerp(dirt*float3(.75,.72,.57),sed.rgb*float3(.69,.70,.68),.25+.56*sat);
        originalGround=lerp(originalGround,land,strand*.79);
        WetRough=lerp(WetRough,lerp(.84,.59,sat),strand);
        WetSpec=lerp(WetSpec,.19+.05*sat,strand);
      }
    }
    """.replace("COUNT", str(len(rows)))
        .replace("LAST", str(len(rows) - 1.00001))
        .replace("LAKEZ", str(plan["level"]))
    )
    code = code.replace(
        "ROWVALS", ",".join("float2(%.3f,%.3f)" % tuple(row) for row in rows)
    )
    endline = "return originalGround;"
    if src.count(endline) != 1:
        raise ValueError("Terrain graph has no recognized output")
    built = src.replace(endline, code + "\n" + endline)
    node.set_editor_property("code", built)
    lib.recompile_material(target)
    assert ue.EditorAssetLibrary.save_loaded_asset(target, False)
    save(
        receipt,
        dict(
            shader_sha256=digest(built),
            parent_shader_sha256=prior,
            protected_forward_m=58,
            source_shorebands_sha256=sha256(
                (OUT / "basin-strand.json").read_bytes()
            ).hexdigest(),
        ),
    )


def run():
    material()
    levels = ue.get_editor_subsystem(ue.LevelEditorSubsystem)
    assert levels.load_level("/Game/Levels/Halo1/Solo/LPE/LPE")
    actors = ue.get_editor_subsystem(ue.EditorActorSubsystem).get_all_level_actors()
    comps = {
        (a.get_actor_label(), c.get_name()): (a, c)
        for a in actors
        for c in a.get_components_by_class(ue.InstancedStaticMeshComponent)
    }
    plan = read(OUT / "basin-plants.json")
    receipt = OUT / "basin-plant-counts.json"
    proof = read(receipt) if VERIFY else {}
    for key, rows in plan.items():
        actor, c = comps[PLANTS[key]]
        mesh = c.get_editor_property("static_mesh")
        bounds = mesh.get_bounding_box()
        height = bounds.max.z - bounds.min.z
        if not VERIFY:
            start = c.get_instance_count()
            transforms = []
            actor.modify()
            c.modify()
            for r in rows:
                z = r["height"] / height
                t = ue.Transform()
                t.translation = ue.Vector(*r["position"])
                t.scale3d = ue.Vector(z * r["breadth"], z * r["breadth"], z)
                yaw = math.radians(r["yaw"]) * 0.5
                t.rotation = ue.Quat(0, 0, math.sin(yaw), math.cos(yaw))
                transforms.append(t)
            c.add_instances(transforms, False, True, False)
            proof[key] = dict(before=start, added=len(rows), mesh=mesh.get_path_name())
        start = proof[key]["before"]
        if c.get_instance_count() != start + len(rows):
            raise ValueError((key, start, c.get_instance_count()))
        for i, r in enumerate(rows):
            t = c.get_instance_transform(start + i, True)
            if (
                math.dist(t.translation.to_tuple(), r["position"]) > 0.09
                or abs(t.scale3d.z * height - r["height"]) > 0.03
            ):
                raise ValueError((key, i))
    if VERIFY:
        retained = 0
        for key, record in read(PARENT / "vegetation-applied.json").items():
            _, c = comps[PREVIOUS[key]]
            box = ue.Box(
                min=ue.Vector(-33100, -86200, 12500),
                max=ue.Vector(-25200, -76800, 16500),
            )
            ids = c.get_instances_overlapping_box(box, True)
            live = {}
            for i in ids:
                t = c.get_instance_transform(i, True)
                live[tuple(round(v, 1) for v in t.translation.to_tuple())] = (
                    t.scale3d.to_tuple()
                )
            for p, scale in record["live"]:
                s = (0.01 * p[0] + 273.0) * (-0.54419) + (
                    -0.01 * p[1] - 785.0
                ) * 0.83896
                if s >= 58.0:
                    continue
                if tuple(p) not in live or math.dist(live[tuple(p)], scale) > 0.001:
                    raise ValueError(("Protected outlet", key, p))
                retained += 1
        (bank,) = [a for a in actors if a.get_actor_label() == "PWR_OutletAlluvium"]
        mesh = bank.get_editor_property("static_mesh_component").get_editor_property(
            "static_mesh"
        )
        if not mesh.get_name() == "SM_PWR_OutletAlluvium":
            raise ValueError("Outlet art missing")
        save(
            OUT / "basin-verified.json",
            dict(
                protected_outlet_transforms=retained,
                mesh=mesh.get_path_name(),
                added=sum(len(v) for v in plan.values()),
                plan_sha256=sha256(
                    (OUT / "basin-plants.json").read_bytes()
                ).hexdigest(),
                placement=read(OUT / "basin-plant-survey.json"),
                material=read(OUT / "shore-material.json"),
            ),
        )
    else:
        assert levels.save_current_level()
        save(receipt, proof)


try:
    run()
except:
    (OUT / ("basin-verify.err" if VERIFY else "basin-apply.err")).write_text(
        traceback.format_exc()
    )
    raise

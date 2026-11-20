"""Native riverbank relief and registered alluvium for the headwater outlet."""

from hashlib import sha256
import json
import unreal as ue

FOLDER = "/Game/MJOLNIR/GrassPilot/Playable/"
MESH = "SM_PWR_OutletAlluvium"
MATERIAL = "M_PWR_OutletAlluvium"
WORLD = "/Game/Levels/Halo1/Solo/LPE/LPE"


def register_shader(raw, spec):
    rows = spec["banks"]
    table = ", ".join("float2(%.5f,%.5f)" % tuple(r) for r in rows)
    registration = """
    float2 deltaAP=hwXY-float2(-273.,785.);
    float dsAP=dot(deltaAP,float2(-.54419,.83896));
    float crossAP=dot(deltaAP,float2(.83896,.54419));
    const float2 bankAP[59]={TABLE};
    float ixAP=clamp(dsAP-10.,0.,57.999);
    float2 edgesAP=lerp(bankAP[(int)ixAP],bankAP[(int)ixAP+1],frac(ixAP));
    edgesAP+=float2(.32*sin(dsAP*.61)+.2*sin(dsAP*1.13),.28*sin(dsAP*.43+1.)+.17*sin(dsAP*.83));
    float leftAP=crossAP-edgesAP.x, rightAP=edgesAP.y-crossAP;
    float regionAP=smoothstep(4.,14.,dsAP)*(1.-smoothstep(54.,71.,dsAP));
    regionAP*=smoothstep(-10.,-5.,min(leftAP,rightAP));
    float barAP=smoothstep(.22,.62,leftAP/max(1.,edgesAP.y-edgesAP.x));
    bar=lerp(bar,barAP,regionAP);
    scope=max(scope,regionAP);
    float focus=max(terraces,scope);
    originalGround=lerp(originalGround,preShoreColor,regionAP);
    WetNormal=normalize(lerp(WetNormal,preShoreNormal,regionAP));
    WetRough=lerp(WetRough,preShoreRough,regionAP);
    WetSpec=lerp(WetSpec,preShoreSpec,regionAP);
    """.replace("TABLE", table)
    raw = raw.replace("float focus=max(terraces,scope);", registration)
    raw = raw.replace(
        "float3 sandy=",
        """float leftSod=1.-smoothstep(-.86,-.21,leftAP+.20*broad);
        float rightSod=1.-smoothstep(-5.5,-2.25,rightAP+1.45*broad+.64*sin(dsAP*.63));
        sod=lerp(sod,max(leftSod,rightSod),regionAP);
        cut=lerp(cut,(1.-smoothstep(-.45,.75,leftAP+.15*broad))*smoothstep(-.08,.42,level),regionAP);
        float3 sandy=""",
    )
    raw = raw.replace(
        "[branch] if(deposit>.002)",
        """float wetBar=smoothstep(-4.5,-.6,rightAP+1.55*broad+.67*sin(dsAP*.39));
        wetBar*=smoothstep(-.95,.92,leftAP)*(.85+.15*stain);
        deposit=lerp(deposit,wetBar,regionAP);
        [branch] if(deposit>.002)""",
    )
    raw = raw.replace(
        "sorted=lerp(sandy,rock,deposit);",
        "rock=lerp(rock,rock*1.18+float3(.019,.017,.012),regionAP);\n            sorted=lerp(sandy,rock,deposit);",
    )
    return raw


def place_surface(work, verify):
    lib = ue.MaterialEditingLibrary
    assets = ue.EditorAssetLibrary
    art = json.loads((work / "surface.json").read_text())
    name = FOLDER + MESH
    path = FOLDER + MATERIAL
    mat = ue.load_asset(path)
    mesh = ue.load_asset(name)
    if not verify:
        mat = mat or ue.AssetToolsHelpers.get_asset_tools().create_asset(
            MATERIAL, FOLDER.rstrip("/"), ue.Material, ue.MaterialFactoryNew()
        )
        mat.set_editor_properties(dict(two_sided=True))
        lib.delete_all_material_expressions(mat)
        vc = lib.create_material_expression(
            mat, ue.MaterialExpressionVertexColor, -800, -170
        )
        color = lib.create_material_expression(
            mat, ue.MaterialExpressionTextureSample, -800, 80
        )
        norm = lib.create_material_expression(
            mat, ue.MaterialExpressionTextureSample, -800, 330
        )
        color.set_editor_properties(
            dict(
                texture=ue.load_asset(FOLDER + "T_PWR_RiverCobble_BC"),
                sampler_type=ue.MaterialSamplerType.SAMPLERTYPE_COLOR,
            )
        )
        norm.set_editor_properties(
            dict(
                texture=ue.load_asset(FOLDER + "T_PWR_RiverCobble_N"),
                sampler_type=ue.MaterialSamplerType.SAMPLERTYPE_NORMAL,
            )
        )
        expr = lib.create_material_expression(mat, ue.MaterialExpressionCustom, -270, 0)
        code = "float l=dot(scan,float3(.24,.59,.17)); return tint*(.78+.70*saturate(l*2.5));"
        expr.set_editor_properties(
            dict(code=code, output_type=ue.CustomMaterialOutputType.CMOT_FLOAT3)
        )
        pins = []
        for n in ("scan", "tint"):
            pin = ue.CustomInput()
            pin.set_editor_property("input_name", n)
            pins.append(pin)
        expr.set_editor_property("inputs", pins)
        assert lib.connect_material_expressions(color, "RGB", expr, "scan")
        assert lib.connect_material_expressions(vc, "", expr, "tint")
        assert lib.connect_material_property(
            expr, "", ue.MaterialProperty.MP_BASE_COLOR
        )
        n = lib.create_material_expression(
            mat, ue.MaterialExpressionLinearInterpolate, -290, 340
        )
        n.set_editor_properties(dict(const_alpha=0.31))
        up = lib.create_material_expression(
            mat, ue.MaterialExpressionConstant3Vector, -780, 510
        )
        up.set_editor_property("constant", ue.LinearColor(0.0, 0.0, 1.0, 1.0))
        assert lib.connect_material_expressions(up, "", n, "A")
        assert lib.connect_material_expressions(norm, "RGB", n, "B")
        assert lib.connect_material_property(n, "", ue.MaterialProperty.MP_NORMAL)
        r = lib.create_material_expression(
            mat, ue.MaterialExpressionLinearInterpolate, -280, -340
        )
        r.set_editor_properties(dict(const_a=0.91, const_b=0.64))
        assert lib.connect_material_expressions(vc, "A", r, "Alpha")
        assert lib.connect_material_property(r, "", ue.MaterialProperty.MP_ROUGHNESS)
        lib.recompile_material(mat)
        assert assets.save_loaded_asset(mat, False)
        mesh = mesh or ue.MjolnirUIBuilderLibrary.create_stand_in_mesh(
            name + "." + MESH
        )
        indices = [i for t in art["faces"] for i in t]
        uv = [ue.Vector2D(*art["uv"][i]) for i in indices]
        if not ue.MjolnirUIBuilderLibrary.build_static_mesh(
            mesh,
            [ue.Vector(*v) for v in art["positions"]],
            [ue.Vector(*n) for n in art["normals"]],
            indices,
            uv,
            uv,
            [0] * len(art["faces"]),
            [ue.Name("RiparianAlluvium")],
            [ue.LinearColor(*c) for c in art["colors"]],
            [],
        ):
            raise RuntimeError("Failed to create surveyed bank landform")
        mesh.set_material(0, mat)
        assert assets.save_loaded_asset(mesh, False)
    if not mesh or mesh.get_material(0) != mat:
        raise RuntimeError("Incomplete native outlet bank asset")
    levels = ue.get_editor_subsystem(ue.LevelEditorSubsystem)
    assert levels.load_level(WORLD)
    actors = ue.get_editor_subsystem(ue.EditorActorSubsystem)
    matches = [
        a
        for a in actors.get_all_level_actors()
        if a.get_actor_label() == "PWR_OutletAlluvium"
    ]
    if not verify and not matches:
        a = actors.spawn_actor_from_class(
            ue.StaticMeshActor, ue.Vector(*art["origin_cm"])
        )
        a.set_actor_label("PWR_OutletAlluvium")
        comp = a.get_editor_property("static_mesh_component")
        comp.set_mobility(ue.ComponentMobility.STATIC)
        assert comp.set_static_mesh(mesh)
        # All player/vehicle support lives in the matching Blam triangle shell.
        comp.set_collision_enabled(ue.CollisionEnabled.NO_COLLISION)
        comp.set_editor_property("cast_shadow", True)
        assert levels.save_current_level()
        matches = [a]
    if (
        len(matches) != 1
        or matches[0]
        .get_editor_property("static_mesh_component")
        .get_editor_property("static_mesh")
        != mesh
    ):
        raise ValueError("Surveyed bank not present in reopened map")
    proof = dict(
        mesh=mesh.get_path_name(),
        triangles=len(art["faces"]),
        vertices=len(art["positions"]),
        surface_sha256=sha256((work / "surface.json").read_bytes()).hexdigest(),
        support_sha256=sha256((work / "support.npz").read_bytes()).hexdigest(),
    )
    (work / ("surface-verified.json" if verify else "surface-built.json")).write_text(
        json.dumps(proof, indent=2)
    )

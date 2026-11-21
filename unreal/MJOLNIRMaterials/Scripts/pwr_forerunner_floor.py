"""The Forerunner floor master: 343's exterior floor layering, in a material of our own.

343's MI_FR_Metal_Diagonal_01_B_Mid_Rough1_Low (HaloMaterialLibrary) reads as Forerunner because
its circuit pattern lives in ROUGHNESS on reflective metal (T_FR_Diagonal_01_ORHG green, a subtle
T_FR_Diagonal_01_N), broken up by grime and grunge masks (T_Misc_Grime_01_ORH, T_Misc_Grunge_01/02_ORHG,
T_Misc_WearGrime_Packed_01_Control). Those maps are exported from the game (mjolnir texture export,
mip 0) and imported here, the route the paving material already ships. The master is world-projected
along each surface's dominant axis (one sample a map), so any generated mesh takes it without UVs.

Vector parameters (all a runtime MID or a MIC may set; level.json decor bindings use them):
  FloorTint    rgb base colour (linear), a unused
  FloorScale   cm: x circuit tile, y grime tile, z grunge tile, w macro grunge tile
  FloorFinish  x roughness on the pattern's smooth plates, y on its rough channels, z metallic, w grime strength
  FloorLayout  plate seams: x, y plate size cm, z seam width cm, w seam strength (0 off)
  FloorAxis    x 1 = plates follow the vertex-colour axis (r, g = axis * .5 + .5), else world axes; y yaw degrees
"""
import os

import unreal as ue

FOLDER = "/Game/MJOLNIR/GrassPilot/Playable/"
MASTER = "M_PWR_FRFloor"
TEXTURES = {   # our asset name: (exported file, kind)
    "T_PWR_FRDiagonal_N": ("T_FR_Diagonal_01_N.png", "normal"),
    "T_PWR_FRDiagonal_ORHG": ("T_FR_Diagonal_01_ORHG.png", "mask"),
    "T_PWR_FRGrime": ("T_Misc_Grime_01_ORH.png", "mask1k"),
    "T_PWR_FRGrunge1": ("T_Misc_Grunge_01_ORHG.png", "mask1k"),
    "T_PWR_FRGrunge2": ("T_Misc_Grunge_02_ORHG.png", "mask1k"),
    "T_PWR_FRWear": ("T_Misc_WearGrime_Packed_01_Control.png", "mask1k"),
}
PINS = {"Diag": "T_PWR_FRDiagonal_ORHG", "DiagN": "T_PWR_FRDiagonal_N", "Grime": "T_PWR_FRGrime",
        "Grunge1": "T_PWR_FRGrunge1", "Grunge2": "T_PWR_FRGrunge2", "Wear": "T_PWR_FRWear"}
DEFAULTS = dict(FloorTint=(0.30, 0.32, 0.34, 1), FloorScale=(400, 2600, 900, 7000),
                FloorFinish=(0.22, 0.62, 0.85, 0.7), FloorLayout=(1600, 800, 5, 0.6), FloorAxis=(0, 0, 0, 0))

CODE = r"""
struct Floor {
    float4 plates(float2 p, float2 size, float joint) {
        float row = floor(p.y / size.y);
        float2 q = p - float2(fmod(abs(row), 2.0) * size.x * .5, 0);
        float2 id = floor(q / size);
        float2 local = (frac(q / size) - .5) * size;
        float2 h = size * .5;
        float bevel = min(size.x, size.y) * .05;
        float edge = min(min(h.x - abs(local.x), h.y - abs(local.y)), (h.x + h.y - bevel - abs(local.x) - abs(local.y)) * .70710678);
        float aa = max(max(length(ddx(p)), length(ddy(p))), 1.0);
        float seam = 1.0 - smoothstep(joint * .5 - aa, joint * .5 + aa, edge);
        float hash = frac(sin(dot(id, float2(127.1, 311.7))) * 43758.5453);
        return float4(seam, hash, edge, 0);
    }
};
Floor F;
// Plate frame: the deck's vertex-colour axis, or world axes turned by Axis.y degrees.
float2 ax = Axis.x > .5 ? normalize(Col.rg * 2.0 - 1.0) : float2(cos(radians(Axis.y)), sin(radians(Axis.y)));
float2 px = float2(-ax.y, ax.x);
float3 w = float3(dot(W.xy, ax), dot(W.xy, px), W.z);
float3 n = normalize(Nw);
float3 nf = float3(dot(n.xy, ax), dot(n.xy, px), n.z);
// Dominant-axis projection: one sample per map.
float3 an = abs(nf);
float2 p = an.z >= max(an.x, an.y) ? w.xy : (an.x >= an.y ? w.yz : w.xz);
float2 uv = p / Scale.x;
float diag = Texture2DSample(Diag, DiagSampler, uv).g;
float2 dn = Texture2DSample(DiagN, DiagNSampler, uv).rg * 2.0 - 1.0;
float grime = Texture2DSample(Grime, GrimeSampler, p / Scale.y).r;
float4 g1 = Texture2DSample(Grunge1, Grunge1Sampler, p / Scale.z);
float4 g2 = Texture2DSample(Grunge2, Grunge2Sampler, p / Scale.w + .37);
float wear = Texture2DSample(Wear, WearSampler, p / (Scale.z * .55) + .19).b;
float4 k = Layout.w > 0 ? F.plates(p, max(Layout.xy, 100.0.xx), Layout.z) : float4(0, .5, 1e4, 0);
float seam = k.x * Layout.w;
// Dirt gathers in broad grime clouds, along grunge stains and in the seams; worn scratches stay bright.
float dirt = saturate((smoothstep(.42, .78, 1.0 - grime) * .8 + g1.a * .6 + g2.a * .4) * Finish.w + seam * .5);
float scratch = smoothstep(.62, .9, wear) * (1.0 - dirt);
float plateTone = lerp(.93, 1.07, k.y);
Rough = saturate(lerp(Finish.x, Finish.y, diag) * lerp(1.0, 1.35, dirt) + scratch * -.08 + seam * .25);
Metal = saturate(Finish.z * (1.0 - dirt * .45) * (1.0 - seam * .7));
// Normal in the projection's frame, back to world (top faces carry the pattern; sides keep a whisper of it).
float3 t = an.z >= max(an.x, an.y) ? float3(dn.x, dn.y, 0) : (an.x >= an.y ? float3(0, dn.x, dn.y) : float3(dn.x, 0, dn.y));
float3 tw = t.x * float3(ax, 0) + t.y * float3(px, 0) + float3(0, 0, t.z);
tw -= n * dot(tw, n);
Normal = normalize(n + tw * 1.4);
float3 base = Tint.rgb * plateTone * lerp(1.0, .58, dirt) * (1.0 - seam * .45) + scratch * .04;
return base;
"""


def import_textures(src_dir):
    tools = ue.AssetToolsHelpers.get_asset_tools()
    out = {}
    for name, (file, kind) in TEXTURES.items():
        path = FOLDER + name
        tex = ue.load_asset(path)
        if not tex:
            task = ue.AssetImportTask()
            task.set_editor_property("filename", os.path.join(src_dir, file))
            task.set_editor_property("destination_path", FOLDER.rstrip("/"))
            task.set_editor_property("destination_name", name)
            task.set_editor_property("automated", True)
            task.set_editor_property("replace_existing", True)
            task.set_editor_property("save", False)
            tools.import_asset_tasks([task])
            tex = ue.load_asset(path)
        if not tex:
            raise RuntimeError("Could not import " + file)
        tex.set_editor_property("srgb", False)
        tex.set_editor_property("virtual_texture_streaming", False)
        tex.set_editor_property("compression_settings", ue.TextureCompressionSettings.TC_NORMALMAP if kind == "normal"
                                else ue.TextureCompressionSettings.TC_MASKS)
        tex.set_editor_property("flip_green_channel", False)
        tex.set_editor_property("max_texture_size", 1024 if kind == "mask1k" else 2048)
        ue.EditorAssetLibrary.save_loaded_asset(tex, False)
        out[name] = tex
    return out


def ensure_master(src_dir):
    textures = import_textures(src_dir)
    m = ue.load_asset(FOLDER + MASTER) or ue.AssetToolsHelpers.get_asset_tools().create_asset(
        MASTER, FOLDER.rstrip("/"), ue.Material, ue.MaterialFactoryNew())
    lib = ue.MaterialEditingLibrary
    lib.delete_all_material_expressions(m)
    m.set_editor_property("shading_model", ue.MaterialShadingModel.MSM_DEFAULT_LIT)
    m.set_editor_property("tangent_space_normal", False)
    m.set_editor_property("used_with_static_lighting", False)
    node = lib.create_material_expression(m, ue.MaterialExpressionCustom, -300, 0)
    ty = ue.CustomMaterialOutputType
    node.set_editor_properties(dict(code=CODE, output_type=ty.CMOT_FLOAT3))
    names = ["W", "Nw", "Col", "Tint", "Scale", "Finish", "Layout", "Axis"] + list(PINS)
    pins = []
    for pin_name in names:
        pin = ue.CustomInput(); pin.set_editor_property("input_name", pin_name); pins.append(pin)
    node.set_editor_property("inputs", pins)
    outs = []
    for out_name, kind in (("Rough", ty.CMOT_FLOAT1), ("Metal", ty.CMOT_FLOAT1), ("Normal", ty.CMOT_FLOAT3)):
        o = ue.CustomOutput(); o.set_editor_properties(dict(output_name=out_name, output_type=kind)); outs.append(o)
    node.set_editor_property("additional_outputs", outs)
    y = -400
    for pin_name, cls in (("W", ue.MaterialExpressionWorldPosition), ("Nw", ue.MaterialExpressionVertexNormalWS),
                          ("Col", ue.MaterialExpressionVertexColor)):
        e = lib.create_material_expression(m, cls, -900, y); y += 110
        assert lib.connect_material_expressions(e, "", node, pin_name)
    for pin_name, param in (("Tint", "FloorTint"), ("Scale", "FloorScale"), ("Finish", "FloorFinish"),
                            ("Layout", "FloorLayout"), ("Axis", "FloorAxis")):
        e = lib.create_material_expression(m, ue.MaterialExpressionVectorParameter, -900, y); y += 110
        e.set_editor_properties(dict(parameter_name=param, default_value=ue.LinearColor(*DEFAULTS[param])))
        # The default output is RGB only and the shader reads .w of each: append A back on.
        app = lib.create_material_expression(m, ue.MaterialExpressionAppendVector, -600, y - 110)
        assert lib.connect_material_expressions(e, "", app, "A")
        assert lib.connect_material_expressions(e, "A", app, "B")
        assert lib.connect_material_expressions(app, "", node, pin_name)
    for pin_name, tex_name in PINS.items():
        e = lib.create_material_expression(m, ue.MaterialExpressionTextureObjectParameter, -900, y); y += 110
        e.set_editor_properties(dict(parameter_name=pin_name, texture=textures[tex_name],
                                     sampler_type=ue.MaterialSamplerType.SAMPLERTYPE_NORMAL if pin_name == "DiagN"
                                     else ue.MaterialSamplerType.SAMPLERTYPE_MASKS))
        assert lib.connect_material_expressions(e, "", node, pin_name)
    prop = ue.MaterialProperty
    for out_name, dest in (("", prop.MP_BASE_COLOR), ("Rough", prop.MP_ROUGHNESS), ("Metal", prop.MP_METALLIC),
                           ("Normal", prop.MP_NORMAL)):
        assert lib.connect_material_property(node, out_name, dest)
    lib.recompile_material(m)
    assert ue.EditorAssetLibrary.save_loaded_asset(m, False)
    return m, textures


if os.environ.get("MJ_FR_COMPILE_CHECK"):   # compile check: build the master, report its shader errors
    mat, _ = ensure_master(os.environ["MJ_FR_TEXTURES"])
    errors = ue.MaterialEditingLibrary.get_material_compile_errors(mat) if hasattr(ue.MaterialEditingLibrary, "get_material_compile_errors") else []
    ue.log("FRFLOOR compiled: %s" % (list(errors) if errors else "no errors reported"))


def instance(name, master, values):
    """A MIC of the floor master (UE 5.5's setter returns False even on success: read back)."""
    lib = ue.MaterialEditingLibrary
    mi = ue.load_asset(FOLDER + name) or ue.AssetToolsHelpers.get_asset_tools().create_asset(
        name, FOLDER.rstrip("/"), ue.MaterialInstanceConstant, ue.MaterialInstanceConstantFactoryNew())
    lib.set_material_instance_parent(mi, master)
    for k, v in values.items():
        lib.set_material_instance_vector_parameter_value(mi, k, ue.LinearColor(*v))
        got = lib.get_material_instance_vector_parameter_value(mi, k)
        if max(abs(got.r - v[0]), abs(got.g - v[1]), abs(got.b - v[2]), abs(got.a - v[3])) > 1e-4:
            raise RuntimeError("%s did not take %s" % (name, k))
    lib.update_material_instance(mi)
    assert ue.EditorAssetLibrary.save_loaded_asset(mi, False)
    return mi

"""Cookable, namespaced Forge glass and the original CE animated green portal.

MJ_FORGE_SPEC points at tools/forge/build_materials.py's bounded build spec.
No world or material instance is cooked; Forge assigns runtime instances.
"""
import importlib.util
import json
import os
from pathlib import Path
import re

import unreal

spec = json.loads(Path(os.environ["MJ_FORGE_SPEC"]).read_text(encoding="utf-8"))
root = spec["root"]
if not re.fullmatch(r"/Game/MJOLNIR/Forge/[a-z0-9][a-z0-9-]{1,63}", root):
    raise ValueError("Forge material root must be derived from a valid pack slug")
if not isinstance(spec["chunk"], int) or not 900 <= spec["chunk"] <= 999:
    raise ValueError("Use an explicitly reserved 9NN shader chunk")

# Reuse the exact CE stage graph, not a simplified green emissive substitute.
# Library mode creates no shared CE assets or chunk labels.
os.environ["MJ_CE_LIBRARY"] = "1"
module_spec = importlib.util.spec_from_file_location("forge_ce_graphs", Path(__file__).with_name("build_ce_materials.py"))
ce = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(ce)
ce.ROOT = root + "/Materials"
ce.TRIAL_ROOT = ce.ROOT
defaults = ce.build_defaults()

# Bake the same defaults used by runtime MIDs, so a newly mounted/pooled
# actor already has its intended appearance before the first surface poll.
textures = {}
for texture in spec["textures"]:
    if texture["name"] not in ("T_PortalDust", "T_PortalMask"):
        raise ValueError("Unexpected Forge texture")
    tex = ce.import_texture(texture["file"], root + "/Textures", texture["name"])
    if tex is None:
        raise RuntimeError("CE portal texture import failed")
    ce.ce_texture_settings(tex)
    tex.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_LEAVE_EXISTING_MIPS)
    ce.eal.save_loaded_asset(tex)
    textures[texture["name"]] = tex
portal = dict(spec["profiles"]["teleporter_green"])
portal["textures"] = {parameter: textures[name] for parameter, name in portal["textures"].items()}
ce.build_transparent("M_ForgePortalGreen", unreal.BlendMode.BLEND_ADDITIVE, defaults,
                     two_sided=True, parameter_defaults=portal)

# A lit cyan pane: finite opacity and smooth specular response from either side.
glass = ce.fresh(ce.ROOT, "M_ForgeGlassCyan", unreal.Material, unreal.MaterialFactoryNew())
glass.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
glass.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
glass.set_editor_property("two_sided", True)
glass.set_editor_property("used_with_static_lighting", False)
glass.set_editor_property("translucency_lighting_mode", unreal.TranslucencyLightingMode.TLM_SURFACE)
g = ce.Graph(glass)
for node, prop in ((g.vector4("GlassColor", (.12,.55,.65,1)), unreal.MaterialProperty.MP_BASE_COLOR),
                   (g.scalar("Opacity", .24), unreal.MaterialProperty.MP_OPACITY),
                   (g.scalar("Roughness", .12), unreal.MaterialProperty.MP_ROUGHNESS),
                   (g.scalar("Specular", .7), unreal.MaterialProperty.MP_SPECULAR)):
    ce.mel.connect_material_property(node, "", prop)
ce.mel.recompile_material(glass)
ce.eal.save_loaded_asset(glass)

label = ce.fresh(root, "PAL_ForgeMaterials", unreal.PrimaryAssetLabel, unreal.DataAssetFactory())
rules = label.get_editor_property("rules")
rules.set_editor_property("chunk_id", spec["chunk"])
rules.set_editor_property("priority", 20)
rules.set_editor_property("apply_recursively", True)
rules.set_editor_property("cook_rule", unreal.PrimaryAssetCookRule.ALWAYS_COOK)
label.set_editor_property("rules", rules)
label.set_editor_property("label_assets_in_my_directory", True)
ce.eal.save_loaded_asset(label)
unreal.log("MJOLNIR Forge materials ready: " + root + " chunk " + str(spec["chunk"]))

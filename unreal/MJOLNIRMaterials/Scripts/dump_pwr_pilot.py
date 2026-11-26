"""Read-only: write M_PWRPilot's landscape graph (custom HLSL nodes, their inputs, texture
parameters and the textures behind them) to PWR_PILOT_DUMP (a folder), for planning edits.

Run with UnrealEditor-Cmd -run=pythonscript on the PWR editor project. Changes nothing."""
import json
import os
from pathlib import Path

import unreal

OUT = Path(os.environ["PWR_PILOT_DUMP"])
OUT.mkdir(parents=True, exist_ok=True)
lib = unreal.MaterialEditingLibrary
mat = unreal.load_asset("/Game/MJOLNIR/GrassPilot/Playable/M_PWRPilot")


def describe(node):
    row = {"class": node.get_class().get_name(), "name": node.get_name()}
    for prop in ("parameter_name", "description", "sampler_type", "sampler_source", "texture", "default_value", "r"):
        try:
            v = node.get_editor_property(prop)
        except Exception:
            continue
        if isinstance(v, unreal.Texture):
            row[prop] = v.get_path_name()
            for t in ("virtual_texture_streaming", "srgb", "compression_settings", "lod_group"):
                try:
                    row["texture_" + t] = str(v.get_editor_property(t))
                except Exception:
                    pass
        else:
            row[prop] = str(v)
    return row


props = {}
for name in ("MP_BASE_COLOR", "MP_NORMAL", "MP_ROUGHNESS", "MP_AMBIENT_OCCLUSION", "MP_SPECULAR", "MP_METALLIC",
             "MP_WORLD_POSITION_OFFSET", "MP_EMISSIVE_COLOR", "MP_OPACITY_MASK", "MP_DISPLACEMENT"):
    prop = getattr(unreal.MaterialProperty, name, None)
    if prop is None:
        continue
    node = lib.get_material_property_input_node(mat, prop)
    if node is None:
        continue
    entry = describe(node)
    if isinstance(node, unreal.MaterialExpressionCustom):
        code = node.get_editor_property("code")
        (OUT / f"{name}.hlsl").write_text(code, encoding="utf-8")
        entry["code_chars"] = len(code)
        pins = [str(p.get_editor_property("input_name")) for p in node.get_editor_property("inputs")]
        srcs = lib.get_inputs_for_material_expression(mat, node)
        entry["inputs"] = [dict(pin=p, source=describe(s) if s else None) for p, s in zip(pins, srcs)]
        entry["outputs"] = [str(o.get_editor_property("output_name")) for o in node.get_editor_property("additional_outputs")]
    else:
        entry["inputs"] = [describe(s) if s else None for s in lib.get_inputs_for_material_expression(mat, node)]
    props[name] = entry

customs = []
for node in unreal.MaterialEditingLibrary.get_material_selected_nodes(mat) or []:
    pass
(OUT / "graph.json").write_text(json.dumps({"material": mat.get_path_name(), "properties": props,
                                            "num_expressions": unreal.MaterialEditingLibrary.get_num_material_expressions(mat)},
                                           indent=1), encoding="utf-8")
unreal.log("PWR pilot dump written to " + str(OUT))

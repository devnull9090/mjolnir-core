"""What lights a converted CE level, per shader, for radiosity_bake
(crates/ue-texture/examples/radiosity_bake.rs).

    python ce_light_inputs.py <staging> <out.json>

Per shader (the glTF materials' names without their `__lmN` / `__lmobj`
suffix):

- `albedo`: the base map's mean colour, linear (the share of light a surface
  sends on; the bounce's colour);
- `emit`: the radiosity light the shader gives off, its `power` times its
  `color_of_emitted_light` (the shader header, H1's
  shader_radiosity_properties), 0 for most.

And the sky's outdoor ambient (colour times power), for reference: the bake
fits the levels against CE's own lightmap, so these set the light's shape and
colour, not its strength.
"""
import json
import os
import sys

import numpy as np
from PIL import Image


def main():
    staging, out = sys.argv[1:3]
    shaders = json.load(open(os.path.join(staging, "materials.json"), encoding="utf-8"))
    table = {}
    for name, info in shaders.items():
        shader = info.get("shader") or {}
        tag = shader.get("tag") or {}
        png = info.get("base_map") or shader.get("base_map")
        albedo = [0.5, 0.5, 0.5]
        try:
            px = np.asarray(Image.open(os.path.join(staging, "textures", png)).convert("RGB"), dtype=np.float64) / 255.0
            albedo = (px.reshape(-1, 3) ** 2.2).mean(axis=0).tolist()
        except (OSError, TypeError):
            pass
        power = float(tag.get("power") or 0.0)
        colour = tag.get("color_of_emitted_light") or [0.0, 0.0, 0.0]
        table[name] = {"albedo": albedo, "emit": [power * c for c in colour]}
    sky = {}
    placement = json.load(open(os.path.join(staging, "placement.json"), encoding="utf-8"))
    for e in placement["entries"]:
        if e.get("kind") == "sky":
            a = e.get("outdoor_ambient") or {}
            sky = {"outdoor_ambient": [a.get("power", 0.0) * c for c in a.get("color", [0, 0, 0])]}
            break
    json.dump({"shaders": table, "sky": sky}, open(out, "w"), indent=1)
    emitters = {k: v["emit"] for k, v in table.items() if any(v["emit"])}
    print(f"{len(table)} shader(s), {len(emitters)} emitting -> {out}")


if __name__ == "__main__":
    main()

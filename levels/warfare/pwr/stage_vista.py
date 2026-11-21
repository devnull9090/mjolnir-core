"""The distant range in a staged release: atmosphere, the range's material values and its mesh container.

visual_dressing/vista.json holds what no tag can say about this map's backdrop: the environment keys
the loader reads (aerial_perspective, haze), and value overrides for the decor that draws the range
(found by its mesh, not its id). An optional packaged apron folder (visual_dressing/package_apron.py
output) replaces the range's mesh container, chunk 963.

    from stage_vista import apply
    report = apply(inputs_dir, level_dict, hashes, apron_dir=None)
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "tools/level"))
CONFIG = HERE / "visual_dressing/vista.json"
CHUNK = 963


def sha(path):
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def apply(inputs, level, hashes, apron_dir=None, config=CONFIG):
    spec = json.loads(Path(config).read_text())
    env = level.setdefault("environment", {})
    for key, value in spec.get("environment", {}).items():
        if isinstance(value, dict) and isinstance(env.get(key), dict):
            env[key] = dict(env[key], **value)
        else:
            env[key] = value
    # The map's live haze is the landscape's (the loader prefers landscape.pbr.haze over
    # environment.haze): its second layer is the low valley mist.
    haze = spec.get("landscape_haze")
    if haze:
        pbr = level.setdefault("landscape", {}).setdefault("pbr", {})
        pbr["haze"] = dict(pbr.get("haze") or {}, **haze)
    # Ambient sound from the map's own water (tools/level/flux_ambience.py) and the palette.
    ambience = None
    if spec.get("ambience"):
        import flux_ambience
        palette = json.loads((Path(config).parent / spec["ambience"]).read_text())
        env["sounds"], ambience = flux_ambience.sounds(level, inputs, palette)
    # A polish piece laid a hair above the floor it finishes flickers against it: lift the whole
    # (render-only) decor piece clear. Keyed by mesh name; collision is the BSP's and does not move.
    lifted = []
    for d in level.get("decor", []):
        for name, dz in (spec.get("decor_lift_cm") or {}).items():
            if name in (d.get("mesh") or "") and not d.get("vista_lift"):
                d["pos"] = [d["pos"][0], d["pos"][1], d["pos"][2] + dz]
                d["vista_lift"] = dz
                lifted.append(d["id"])
    touched = []
    mesh = spec["range"]["mesh"]
    for d in level.get("decor", []):
        if d.get("mesh") != mesh:
            continue
        for m in d.get("materials", []):
            if not isinstance(m, dict):
                continue
            for group in ("vectors", "textures", "scalars"):
                if spec["range"].get(group):
                    m[group] = dict(m.get(group) or {}, **spec["range"][group])
        touched.append(d["id"])
    if not touched:
        raise ValueError("No decor draws the range mesh " + mesh)
    replaced = {}
    if apron_dir:
        apron_dir = Path(apron_dir)
        source = next(apron_dir.glob(f"pakchunk{CHUNK}-*.utoc")).with_suffix("")
        target = next(Path(inputs).glob(f"pakchunk{CHUNK}-*.utoc")).with_suffix("")
        for ext in (".utoc", ".ucas"):
            shutil.copyfile(source.with_suffix(ext), target.with_suffix(ext))
            member = "content/" + target.name + ext
            hashes[member] = sha(target.with_suffix(ext))
            replaced[member] = hashes[member]
        decor = json.loads((apron_dir / "runtime_decor.json").read_text())["decor"][0]
        for d in level["decor"]:
            if d.get("mesh") == mesh:
                d["pos"], d["scale"] = decor["pos"], decor["scale"]
    return {"config_sha256": sha(config), "environment": spec.get("environment", {}),
            "landscape_haze": haze, "ambience": ambience, "lifted_decor": lifted,
            "range_decor": touched, "range_container": replaced}

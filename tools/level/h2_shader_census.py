"""Halo 2 shader census: what each template draws in Halo 2 against what
the converter makes of it, weighted by the triangles that use it.

    cargo run --release -p blam-cache --example h2_shader_census -- <h2 maps dir> <dir>/shader_census.json
    mjolnir cache stage <map>.map --out <dir>/staged/<map>     (every map)
    python tools/level/h2_shader_census.py <dir>

Reads <dir>/shader_census.json (every `shad` tag by template, with the
passes the template draws) and each <dir>/staged/<map> (materials.json:
what staging made of each shader; bsp/ and models/ glTFs: the triangles
using it). Writes <dir>/census_joined.json and prints one line a template,
heaviest first. A gap is a feature Halo 2's passes draw that no staged
material of the template carries: specular (the specular_sphere pass with
lightmap passes that write the base alpha mask),
reflection (an env pass, opaque shaders) or glow (an illum pass, opaque
shaders; an additive shader's map is its glow). docs/h2_shader_census.md
has the results of 2026-11-10."""
import glob
import json
import os
import sys
from collections import defaultdict

import numpy as np

S = sys.argv[1]
census = {r["template"]: r for r in json.load(open(os.path.join(S, "shader_census.json")))}
root = os.path.join(S, "staged")


def tri_counts(gltf):
    try:
        doc = json.load(open(gltf, encoding="utf-8"))
    except Exception:
        return {}
    out = defaultdict(int)
    for m in doc.get("meshes", []):
        for p in m["primitives"]:
            if "material" not in p or "indices" not in p:
                continue
            name = doc["materials"][p["material"]].get("name", "")
            out[name] += doc["accessors"][p["indices"]]["count"] // 3
    return out


def arm(t):
    """Which branch of render.rs template()/shader_summary a template takes."""
    if t.startswith("tex_bump_alpha_test") and "single_pass" in t:
        return "tex_bump_alpha_test single pass"
    if t.startswith("tex_bump_alpha_test"):
        return "tex_bump_alpha_test"
    if t.startswith("tex_bump_env") and t.endswith("alpha_test_combined"):
        return "env alpha test combined"
    named = {"tex_bump_detail_blend", "tex_bump_plasma_one_channel_illum", "tex_bump_illum_3_channel", "waves",
             "tex_env", "tex_illum", "tex_illum_bloom", "tex_detail_blend", "decal_simple", "plasma_alpha",
             "two_alpha_env_illum", "two_alpha_env_detail", "one_add_illum", "two_add_detail_masked",
             "two_add_env_illum", "overlay", "sky_one_add_illum_detail", "one_add_illum_detail", "add_illum_detail"}
    if t in named:
        return t
    for pre in ["tex_bump_detail_blend_detail", "water_pool", "tex_bump_illum", "tex_bump_env_illum_3_channel",
                "tex_bump_env_illum", "tex_bump_env_no_detail", "tex_bump_one_change_color"]:
        if t.startswith(pre):
            return pre + "*"
    if t.startswith("tex_bump_detail") or t in ("tex_bump_two_detail", "tex_bump_three_detail_blend"):
        return "tex_bump_detail*"
    if t.startswith("tex_bump_env") or t.startswith("tex_bump_dprs_env"):
        return "tex_bump_env*"
    if t.startswith("tex_bump"):
        return "tex_bump* (generic)"
    if t.startswith("tex_alpha_test"):
        return "tex_alpha_test*"
    if t.startswith("illum"):
        return "illum*"
    if t.endswith("one_alpha_env") or t.endswith("one_alpha_env_clamped") or t.endswith("one_alpha_env_illum"):
        return "one_alpha_env (glass)"
    if "two_plus_two" in t:
        return "two_plus_two"
    if t.endswith("two_alpha_clouds"):
        return "two_alpha_clouds"
    if t.endswith("two_add_clouds") or t.endswith("two_add_clouds_clamped"):
        return "two_add_clouds"
    if "add" in t:
        return "'add' catch-all"
    if "alpha" in t and "alpha_test" not in t:
        return "'alpha' catch-all"
    return "default (diffuse map, opaque)"


rows = defaultdict(lambda: {"maps": set(), "materials": 0, "tris": 0, "spec": 0, "refl": 0, "glow": 0,
                            "detail": 0, "bump": 0, "classes": defaultdict(int), "examples": []})
for mdir in sorted(glob.glob(os.path.join(root, "*"))):
    mat_path = os.path.join(mdir, "materials.json")
    if not os.path.isfile(mat_path):
        continue
    name = os.path.basename(mdir)
    mats = json.load(open(mat_path, encoding="utf-8"))
    tris = defaultdict(int)
    for g in glob.glob(os.path.join(mdir, "bsp", "*.gltf")) + glob.glob(os.path.join(mdir, "models", "**", "*.gltf"), recursive=True):
        for k, v in tri_counts(g).items():
            tris[k] += v
    for key, m in mats.items():
        s = m.get("shader") or {}
        t = s.get("h2_template") or "(none)"
        r = rows[t]
        r["maps"].add(name)
        r["materials"] += 1
        n = sum(v for k, v in tris.items() if k == key or k.startswith(key + "__"))
        r["tris"] += n
        r["classes"][m.get("shader_class") or s.get("shader_class")] += 1
        if (s.get("specular") or {}).get("flags", 0) & 4:
            r["spec"] += 1
        if s.get("reflection") or m.get("shader_class") == "sgla":
            r["refl"] += 1
        if (s.get("self_illum") or {}).get("map"):
            r["glow"] += 1
        d = s.get("detail") or {}
        if d.get("primary") or d.get("secondary"):
            r["detail"] += 1
        if (s.get("bump") or {}).get("map"):
            r["bump"] += 1
        if len(r["examples"]) < 3:
            r["examples"].append(f"{name}:{(s.get('tag_path') or key).split(chr(92))[-1]}")

out = []
for t, r in rows.items():
    passes = census.get(t, {}).get("passes", [])
    names = [p.split(" [")[0] for p in passes]
    lightmaps = [n for n in names if n.startswith("lightmap")]
    # As render.rs specular_mask: the lightmap passes must write the base
    # alpha mask (not the env, overlay, no-specular or alpha-tested ones).
    mask = bool(lightmaps) and all(
        "env" not in n and not n.endswith("detail_overlay") and not n.endswith("no_specular")
        and ("alpha_test" not in n or n.endswith("alpha_test_no_bump")) for n in lightmaps)
    halo = {
        "specular": any("specular_sphere" in p and "[vc" in p for p in passes) and mask,
        "reflection": any("env" in p for p in passes) or "env" in t,
        "glow": any("illum" in p for p in passes) or "illum" in t,
    }
    cls = set(r["classes"])
    gaps = []
    if halo["specular"] and r["spec"] == 0:
        gaps.append("specular")
    if halo["reflection"] and r["refl"] == 0 and "shad" in cls and not t.startswith("sky_"):
        gaps.append("reflection")
    if halo["glow"] and r["glow"] == 0 and "shad" in cls:
        gaps.append("glow")
    out.append({"template": t, "branch": arm(t), "maps": sorted(r["maps"]), "materials": r["materials"],
                "triangles": r["tris"], "classes": dict(r["classes"]), "with_spec": r["spec"],
                "with_reflection": r["refl"], "with_glow": r["glow"], "with_detail": r["detail"],
                "with_bump": r["bump"], "halo_passes": passes, "gaps": gaps, "examples": r["examples"]})
out.sort(key=lambda x: -x["triangles"])
json.dump(out, open(os.path.join(S, "census_joined.json"), "w"), indent=1)
total = sum(x["triangles"] for x in out)
print(f"{len(out)} templates drawn, {total} triangles")
for x in out:
    print(f"{x['template']:42s} {x['triangles']:8d} tris {100*x['triangles']/max(total,1):5.1f}% {len(x['maps']):2d} maps "
          f"{x['materials']:4d} mats | {x['branch']:28s} | gaps {','.join(x['gaps']) or '-'}")

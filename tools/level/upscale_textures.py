"""Upscale a converted map's one-off textures for its remaster.

    python tools/level/upscale_textures.py <CODE> <out dir> [--model M] [--max 1024]

A tiling wall takes a PBR surface (`structure_surfaces`); a texture with an
identity of its own (hazard stripes, a sign, the wheel's plating, a prop)
has nothing to stand in for it, and Halo 2's are 64 to 512 pixels over
metres. This runs each through Upscayl's Real-ESRGAN build
(`upscayl-bin`, 4x) and writes `<out>/<asset name>.png` plus
`<out>/manifest.json`, which the editor stage imports beside the
landscape's bakes and assemble points the level's materials at.

Which: the base maps (`Base`, `Map0`) of every material the remaster
leaves as converted: not the landscape's or the cliffs' (the loader finds
those by their texture paths), not a `structure_surfaces` set's (drawn in
a surface), nothing whose name holds a `skip` token of the map's `upscale`
config (sky, glass, plasma, lightmaps), and no bump map.

Each image is wrap-padded before and cropped after, so a tiling texture
still tiles; alpha is kept; a result over `--max` pixels a side is scaled
down to it. Skipped when the output is newer than its source.
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
UPSCAYL = os.environ.get("UPSCAYL", "C:/Program Files/Upscayl/resources")
PAD = 16
SKIP = ("skies", "glass", "energy_", "lightmap", "plasma", "_bump", "reflection", "fusion_coil_bloom")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("code")
    ap.add_argument("out")
    ap.add_argument("--model", default="upscayl-standard-4x")
    ap.add_argument("--max", type=int, default=1024)
    a = ap.parse_args()
    m = json.load(open(os.path.join(HERE, "ce_upgrade_maps.json"), encoding="utf-8"))[a.code]
    cfg = m.get("upscale") if isinstance(m.get("upscale"), dict) else {}
    skip = SKIP + tuple(cfg.get("skip") or ())
    conv = m.get("scene") or m["conversion"]
    spec = json.load(open(os.path.join(conv, "materials.spec.json"), encoding="utf-8"))
    files = {t["name"]: t["file"] for t in spec["textures"]}
    owned = list(m.get("shaders") or []) + list(m.get("cliff_shaders") or []) \
        + [x for st in m.get("structure_surfaces") or [] for x in st["shaders"]]
    names = set()
    for mat in spec["materials"]:
        if any(x in mat["name"].lower() for x in owned):
            continue
        for key in ("Base", "Map0"):
            leaf = str((mat.get("textures") or {}).get(key, "")).rsplit(".", 1)[-1]
            if leaf and leaf in files and not any(s in leaf.lower() for s in skip):
                names.add(leaf)
    # The wall decals' textures: quads in the level, not materials of the scene.
    names.update(n for n in files if "_decals_" in n.lower() and not any(s in n.lower() for s in skip))
    exe = os.path.join(UPSCAYL, "bin", "upscayl-bin.exe")
    if not os.path.exists(exe):
        sys.exit(f"{exe} is missing: install Upscayl, or set UPSCAYL to its resources folder")
    os.makedirs(a.out, exist_ok=True)
    manifest, made = [], 0
    for name in sorted(names):
        src, dst = files[name], os.path.join(a.out, name + ".png")
        if not os.path.exists(src):
            continue
        if not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(src):
            img = np.asarray(Image.open(src).convert("RGBA"))
            tmp = os.path.join(a.out, "_in.png")
            Image.fromarray(np.pad(img, ((PAD, PAD), (PAD, PAD), (0, 0)), mode="wrap")).save(tmp)
            raw = os.path.join(a.out, "_out.png")
            subprocess.run([exe, "-i", tmp, "-o", raw, "-m", os.path.join(UPSCAYL, "models"), "-n", a.model,
                            "-s", "4", "-f", "png"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if not os.path.exists(raw):
                sys.exit(f"{name}: the upscaler wrote nothing")
            big = Image.open(raw).convert("RGBA")
            big = big.crop((PAD * 4, PAD * 4, big.size[0] - PAD * 4, big.size[1] - PAD * 4))
            if max(big.size) > a.max:
                k = a.max / max(big.size)
                big = big.resize((max(1, round(big.size[0] * k)), max(1, round(big.size[1] * k))), Image.LANCZOS)
            big.save(dst)
            os.remove(raw)
            os.remove(tmp)
            made += 1
        manifest.append({"name": name, "file": dst.replace("\\", "/"), "size": list(Image.open(dst).size),
                         "source_size": list(Image.open(src).size)})
    json.dump({"model": a.model, "textures": manifest}, open(os.path.join(a.out, "manifest.json"), "w",
                                                             encoding="utf-8"), indent=1)
    texels = sum(t["size"][0] * t["size"][1] for t in manifest)
    print(f"{a.code}: {len(manifest)} texture(s) upscaled with {a.model} ({made} new), "
          f"about {texels * 4 * 1.33 / 1e6:.0f} MB uncompressed with mips -> {a.out}")


if __name__ == "__main__":
    main()

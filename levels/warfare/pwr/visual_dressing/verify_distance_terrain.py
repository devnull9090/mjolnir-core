"""Read the actual 965 IoStore field, its mip chain and the referenced landscape SM6 shader maps."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT/"tools/iostore"),str(ROOT/"tools/ue/shader_archive")]
from iostore import load_container, read_chunk
from shaderlib import FREQ, parse_library
from zen_class import load_name_batch


LEAF = "T_PWR_BiomeColor"
FOLDER = "/Game/MJOLNIR/GrassPilot/Playable"
DEFAULT_OODLE = Path("C:/Program Files/Epic Games/UE_5.5/Engine/Binaries/DotNET/UnrealBuildTool/oo2core_9_win64.dll")
BASELINE = ROOT/"out/pwr/base-polish/saturday.7/map-input/pakchunk965-MJOLNIRLAND-PWR_P.utoc"


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()


def shader_receipt(toc,oodle,extra_materials=()):
    container = load_container(toc)
    def data(suffix):
        names = [k for k in container.files if k.endswith(suffix)]
        if len(names)!=1:
            raise ValueError(f"{suffix}: expected one package, found {names}")
        index = container.files[names[0]]
        return read_chunk(container,container.chunks[index],oodle_roots=[oodle])
    master = data("GrassPilot/Playable/M_PWRPilot.uasset")
    world = data("/LPE/LPE.umap")
    library = parse_library(data("Chunk965-PCD3D_SM6-PCD3D_SM6.ushaderbytecode"))
    names = load_name_batch(master,struct.unpack_from("<i",master,48)[0])[0]
    for dependency in (FOLDER+"/"+LEAF,FOLDER+"/GT_PWRPilot"):
        if dependency not in names:
            raise ValueError(f"The landscape lost {dependency}")
    if b"PWRBiomeStrength" not in master:
        raise ValueError("Missing compiled PWR biome strength")
    groups = {c.chunk_id.to_bytes(8,"little")+c.chunk_index.to_bytes(2,"big") for c in container.chunks
              if c.type_name=="ShaderCode" and c.length}
    if not library.group_ids or not all(h[:10] in groups for h in library.group_ids):
        raise ValueError("Incomplete SM6 shader groups")
    def stages(payload):
        result = {}
        for i,h in enumerate(library.map_hashes):
            if h not in payload:
                continue
            indices = library.map_shaders(i)
            if not indices or not all(library.shader_size(j)>0 for j in indices):
                raise ValueError("Empty shader stage")
            result[h.hex()] = dict(Counter(FREQ.get(library.shader_entries[j][0],"?") for j in indices))
        if not result or not any(row.get("PS") for row in result.values()):
            raise ValueError("No linked pixel shader in the cooked payload")
        return result
    result = {"master":stages(master),"landscape_world":stages(world),"owned_code_groups":len(groups),
              "grass_type_referenced":True,"biome_field_referenced":True}
    for material in extra_materials:
        result[material] = stages(data("GrassPilot/Playable/"+material+".uasset"))
    return result


def texture_data(toc,global_toc,folder):
    cli = ROOT/"target/release/mjolnir.exe"
    for pair in (toc,global_toc):
        for ext in (".utoc",".ucas"):
            src = pair.with_suffix(ext)
            dest = folder/src.name
            try: os.link(src,dest)
            except OSError: shutil.copyfile(src,dest)
    base = ["--paks",str(folder),"--asset",LEAF]
    info = subprocess.run([str(cli),"texture","info",*base],capture_output=True,text=True,check=True).stdout
    if not (re.search(r"size\s+1024x1024",info) and re.search(r"mips\s+11\b",info)
            and "PF_B8G8R8A8" in info):
        raise ValueError(info)
    levels = {}
    for lod in (0,2,4,5,10):
        dest = folder/f"mip-{lod}.png"
        subprocess.run([str(cli),"texture","export",*base,"--mip",str(lod),"--out",str(dest)],
                       capture_output=True,check=True)
        with Image.open(dest) as im:
            levels[lod] = np.array(im.convert("RGBA"))
    return levels


def verify(toc,baseline_toc,global_toc,art,oodle):
    sources = art/"biome-color.png", ROOT/"out/pwr/world-art/foliage-r2/biome-color.png"
    cooked = {}
    shader_maps = {}
    for key,path,source in zip(("current","before"),(toc,baseline_toc),sources):
        with tempfile.TemporaryDirectory(dir=art) as tmp:
            levels = texture_data(path,global_toc,Path(tmp))
        wanted = np.asarray(Image.open(source).convert("RGBA"))
        if not np.array_equal(levels[0], wanted):
            raise ValueError(f"{key}: native RGBA mip 0 differs from authored field in "
                             f"{np.any(levels[0]!=wanted,axis=-1).sum()} texels")
        cooked[key] = levels
        shader_maps[key] = shader_receipt(path,oodle)
    # The same filenames with stale cached component maps will not draw the new wet response.
    for target in ("master","landscape_world"):
        if set(shader_maps["current"][target]) == set(shader_maps["before"][target]):
            raise ValueError(f"The {target} uses the .7 shader map after the wet-graph revision")
    now = cooked["current"]
    author = json.loads((art/"terrain-field.json").read_text())
    meadow = art/author["measured_meadow"]["file"]
    if sha(meadow)!=author["measured_meadow"]["sha256"]:
        raise ValueError("Authored meadow evaluation mask drifted")
    coverage = Image.open(meadow).convert("L")
    mip_stats = {}
    for lod,pixels in now.items():
        side = 1024 >> lod
        if pixels.shape != (side,side,4):
            raise ValueError(f"Mip {lod} has the wrong dimensions")
        # PIL premultiplies RGBA when resizing, whereas the texture has four *data*
        # channels; filter them separately to reconstruct the native mip target.
        reference = np.stack([np.asarray(Image.fromarray(now[0][:,:,k]).resize((side,side),Image.Resampling.BOX))
                              for k in range(4)],axis=-1)
        delta = np.abs(pixels.astype(np.int16)-reference.astype(np.int16))
        if np.max(delta) > 3:
            raise ValueError(f"Mip {lod} fails independent coverage/reflectance filter: {np.max(delta)}")
        mip_stats[str(lod)] = {"metres_per_texel":2000/side,"mean_rgba":pixels.mean(axis=(0,1)).round(2).tolist(),
                              "max_byte_error_vs_linear_average":int(delta.max()),
                              "direct_sha256":hashlib.sha256(pixels.tobytes()).hexdigest()}
        if side >= 32:
            meadow_pixels = np.asarray(coverage.resize((side,side),Image.Resampling.BOX))>200
            for key,levels in cooked.items():
                luma = (levels[lod][:,:,:3] @ np.array([.2126,.7152,.0722]))/128
                lo,hi = np.percentile(luma[meadow_pixels],[10,90])
                mip_stats[str(lod)]["meadow_p90_p10_"+key] = round(float(hi-lo),3)
            if mip_stats[str(lod)]["meadow_p90_p10_current"] <= mip_stats[str(lod)]["meadow_p90_p10_before"]:
                raise ValueError(f"Native open-meadow contrast did not survive at mip {lod}")
    old_rgb, alpha = cooked["before"][0], now[0][:,:,3]
    if alpha.max()!=255 or alpha.min()!=0 or np.array_equal(alpha,old_rgb[:,:,3]):
        raise ValueError("The new wet-coverage channel is absent or constant")
    wanted_spots = json.loads((art/"wet-spot-views.json").read_text()) if (art/"wet-spot-views.json").exists() else []
    wet_spots = []
    for spot in wanted_spots:
        x,y = spot["pixel"]
        if int(alpha[y,x]) != spot["peak_wet"]:
            raise ValueError(f"Water coverage missing at {x}/{y}")
        wet_spots.append({"pixel":[x,y],"baked_wet":int(alpha[y,x]),"ue_cm":spot["target_ue_cm"]})
    wet_area = int(np.count_nonzero(alpha>=174))
    record = {"container_sha256":{ext:sha(toc.with_suffix(ext)) for ext in (".utoc",".ucas")},
              "before_container_sha256":{ext:sha(baseline_toc.with_suffix(ext)) for ext in (".utoc",".ucas")},
              "exact_rgba_texels":1024**2,"mip_count":11,"mip_proofs":mip_stats,
              "baked_pool_coverage_texels_at_068":wet_area,"baked_mapped_wet_spots":wet_spots,"sm6":shader_maps}
    (art/"cooked-terrain-readback.json").write_text(json.dumps(record,indent=2)+"\n")
    Image.fromarray(now[0]).save(art/"cooked-valley-rgba.png")
    Image.fromarray(old_rgb).save(art/"cooked-previous-valley-rgba.png")
    print(json.dumps(record,indent=2))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("toc",type=Path)
    p.add_argument("--global-toc",required=True,type=Path)
    p.add_argument("--baseline-toc",default=BASELINE,type=Path)
    p.add_argument("--art",default=ROOT/"out/pwr/landscape-distance/terrain",type=Path)
    p.add_argument("--oodle",default=DEFAULT_OODLE,type=Path)
    a=p.parse_args()
    verify(a.toc.resolve(),a.baseline_toc.resolve(),a.global_toc.resolve(),a.art.resolve(),a.oodle.resolve())

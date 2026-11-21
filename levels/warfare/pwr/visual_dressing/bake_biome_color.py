"""Bake low-frequency valley reflectance from the PWR soil, canopy, water and erosion fields."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt, gaussian_filter


ROOT = Path(__file__).resolve().parents[4]
MASTER = ROOT / "levels/warfare/pwr/terrain/runtime-v5"
AUDIT = ROOT / "out/pwr/visual-v8/surface-cooked-final"
SIZE, METRES = 1024, 2000 / 1024


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def smooth(lo, hi, x):
    t = np.clip((x-lo)/(hi-lo), 0, 1)
    return t*t*(3-2*t)


def bake(out):
    out.mkdir(parents=True, exist_ok=True)
    source = {}
    def field(kind):
        path = MASTER / f"runtime-master.{kind}.npy"
        source[str(path.relative_to(ROOT))] = sha(path)
        # Source vertices run from south to north. Unreal texture rows run north to south.
        return np.asarray(Image.fromarray(np.load(path)[::-1].copy()).resize((SIZE,SIZE),Image.Resampling.BILINEAR))
    def rgba(path):
        source[str(path.relative_to(ROOT))] = sha(path)
        return np.asarray(Image.open(path).convert("RGBA").resize((SIZE,SIZE),Image.Resampling.BILINEAR),
                          dtype=np.float32)/255
    z, forest, water = field("heights"), field("forest"), field("water")
    base, eco = rgba(AUDIT/"T_LandBase.png"), rgba(AUDIT/"T_LandEcology.png")
    painted = base[:,:,3]
    # The native Base alpha also covers lake beds and bare terrain. Restrict the
    # visual road weathering to the frozen traffic corridors where these coincide.
    traffic = field("road")
    ecotones = out / "ecotone-weights.png"
    edge, reed, pine = rgba(ecotones)[:,:,:3].transpose(2,0,1) if ecotones.is_file() else (0,0,0)
    def blur(a, metres): return gaussian_filter(a, metres / METRES)
    # Seeded mesoscale deviations break uniform terrain shelves. Different wavelengths
    # supply dozens of broad, connected meadow patches rather than high-frequency speckle.
    rng = np.random.default_rng(41221)
    def patch(metres):
        a = blur(rng.standard_normal(z.shape, dtype=np.float32), metres)
        return np.tanh((a-np.mean(a))/(1.45*np.std(a)))
    broad, mid, fine = patch(52), patch(17), patch(5)
    z7 = blur(z,7)
    convex = np.tanh((z7-blur(z,69))/8)
    wet, litter, debris = eco[:,:,0],eco[:,:,1],eco[:,:,2]
    bank_dist = distance_transform_edt(water < .45)*METRES
    road_core = (painted>.48) & (distance_transform_edt(traffic < .35)*METRES<4)
    road_dist = distance_transform_edt(~road_core)*METRES
    crossfall = road_dist-distance_transform_edt(road_core)*METRES
    road = 1-smooth(-4.5,4.5,crossfall+2.3*fine)
    shoulder = (1-smooth(2,13+4*mid,road_dist))*(1-road)
    bank = (1-smooth(1.5,24+8*mid,bank_dist))*(.68+.32*wet)
    dry = np.clip(.51+.35*broad+.18*mid+.13*convex-.28*wet,0,1)
    woodland = np.clip(.52*blur(litter,10)+.25*forest+.19*edge+.25*pine,0,1)
    # Values are ratios of diffuse reflectance in LINEAR light. The native PBR scans
    # supply their real base colour, roughness and normals beneath this broad modulation.
    def mix(a,b,t): return a+(np.asarray(b,dtype=np.float32)-a)*np.asarray(t)[:,:,None]
    color = mix(np.array([.70,.82,.68],dtype=np.float32), [1.37,1.03,.75], dry)
    color *= (1+.17*broad+.06*mid+.035*fine)[:,:,None]
    color = mix(color,[.55,.54,.48],woodland)
    color = mix(color,[.46,.56,.53],np.clip(.84*bank+.18*reed,0,1))
    color = mix(color,[1.12,.78,.48],shoulder*(.52+.14*fine))
    dirt = np.array([.69,.68,.62],dtype=np.float32)*(1+.20*broad+.12*mid+.04*fine-.20*wet)[:,:,None]
    color = mix(color,dirt,road)
    # Taper the grading on exposed rock and snow and across the seam to the existing 8 km apron.
    rock = smooth(.20,.78,base[:,:,0]+.3*debris)
    snow = smooth(.07,.75,base[:,:,1])
    py,px=np.mgrid[:SIZE,:SIZE]
    boundary = np.minimum.reduce([px,py,SIZE-1-px,SIZE-1-py])*METRES
    weight = smooth(0,67,boundary)*(1-.82*rock)*(1-.96*snow)
    color = 1+(color-1)*weight[:,:,None]
    if not np.isfinite(color).all() or color.min()<=0 or color.max()>=2:
        raise ValueError("Reflectance multiplier is out of encoding range")
    # Exact neutral = 128. Shader reconstructs the ratio using 255/128.
    encoded=np.uint8(np.rint(128*color))
    png=out/"biome-color.png"
    Image.fromarray(encoded).save(png)
    luminance=color@np.array([.2126,.7152,.0722])
    regions={"meadow":(road<.01)&(water<.05)&(litter<.15)&(forest<.55)&(base[:,:,0]<.2)&(boundary>82),
             "woods":(woodland>.63)&(boundary>82),"bank":(bank>.66)&(road<.15)&(water<.42)&(boundary>82),
             "roads":(road>.9)&(boundary>82)}
    stats={key:dict(pixels=int(mask.sum()),p10_p50_p90=np.percentile(luminance[mask],[10,50,90]).round(3).tolist())
           for key,mask in regions.items() if mask.any()}
    if stats["meadow"]["p10_p50_p90"][2]-stats["meadow"]["p10_p50_p90"][0]<.17:
        raise ValueError("Insufficient broad meadow variation")
    record=dict(file=png.name,sha256=sha(png),sources_sha256=source,regions=stats,width=SIZE,height=SIZE,
                bounds_ue_cm=[-100000,-100000,200000,200000],encoding="RGB linear reflectance x128",
                road_alpha_sha256=hashlib.sha256(np.rint(255*painted).astype("uint8").tobytes()).hexdigest())
    (out/"biome-color.receipt.json").write_text(json.dumps(record,indent=2)+"\n")
    return record


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out",type=Path)
    parser.add_argument("--bind-pilot",action="store_true")
    args=parser.parse_args()
    record=bake(args.out.resolve())
    if args.bind_pilot:
        p=args.out/"pilot.json"
        config=json.loads(p.read_text())
        config["biome_color"]={k:record[k] for k in ("file","sha256","bounds_ue_cm")}
        tmp=p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(config,indent=2)+"\n")
        tmp.replace(p)
    print(json.dumps(record["regions"]))

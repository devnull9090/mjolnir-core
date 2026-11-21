"""Author PWR's meadow weight field and editor PCG woodland understory on the collision heightfield."""
import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools/level"))
import landscape_grass_pilot as grass
import pcg_foliage
from foliage_bake import PAKS, mesh_info

BASE = ROOT / "out/pwr/base-runtime/landscape-grass-pilot/pilot.json"
PALETTE = Path(__file__).with_name("playable-ecology-palette.json")
SEED = 24117


def bands(x, y):
    # Two different wavelengths create contiguous colonies with irregular edges.
    broad = np.sin(x/47 + 1.3*np.cos(y/81)) * np.cos(y/33 - .7*np.sin(x/64))
    fine = np.sin(x/9.5 + y/14) * np.cos(y/16.2 - x/27)
    return np.clip(.5 + .35*broad + .15*fine, 0., 1.)


def prepare(out):
    base = pcg_foliage.load(BASE)
    grass.validate_config(base, BASE.parent)
    land = next(Path(r["path"]).parent for r in base["sources"] if Path(r["path"]).name == "landscape.json")
    field, spec, scenery, sources, x, y, allowed, clearance = grass.ground_support(land, None)
    trees = pcg_foliage.load(scenery/"trees/trees.selected.json")
    xy = np.asarray([r["position"][:2] for r in trees["instances"]])
    tree_gap = cKDTree(xy).query(np.column_stack((x.ravel(),y.ravel())), workers=4)[0].reshape(x.shape)
    shade = np.exp(-(tree_gap/17)**2)
    patches = bands(x, y)
    # Keep open meadow broad and legible. Woodland shifts from grasses to low herbs.
    density = (.43 + .57*patches) * (1 - .43*shade)
    weights = np.rint(255*density*allowed).astype(np.uint8)
    size, q = spec["size"], spec["quads"]
    components = [[cx,cy] for cy in range(0,size-1,q) for cx in range(0,size-1,q)
                  if weights[cy:cy+q+1,cx:cx+q+1].any()]
    raw, png = out/"density.r8", out/"density.png"
    raw.write_bytes(weights.tobytes())
    Image.fromarray(weights).convert("RGBA").save(png)
    shutil.copy2(BASE.parent / base["heights"]["file"], out/base["heights"]["file"])
    # Retain the exact independent vegetation obstacle audit and existing field heights.
    config = dict(base, world=grass.FIELD_WORLD, asset_folder=grass.FIELD_ASSETS, section_bases=components,
                  mask={"file":raw.name,"sha256":grass.digest(raw)}, texture={"file":png.name,"sha256":grass.digest(png)},
                  nonzero_vertices=int(allowed.sum()), notes=["Distance-culled native ground cover across playable habitat."])
    config["sources"] = [{"path":str(p),"sha256":grass.digest(p)} for p in sorted(
        {Path(r["path"]) for r in base["sources"]} | sources | {PALETTE, Path(__file__).resolve()})]
    grass.validate_config(config, out)
    grass.dump(out/"pilot.json",config)

    # Candidates lie on distinct native height samples. Independent offsets break rows;
    # the engine graph then thins them and chooses orientation, scale and asset draw.
    rng = np.random.default_rng(SEED)
    rr, cc = np.mgrid[1:size-4:3,1:size-4:3]
    rr += rng.integers(0,3,rr.shape)
    cc += rng.integers(0,3,cc.shape)
    rr, cc = rr[allowed[rr,cc]], cc[allowed[rr,cc]]
    px, py = x[rr,cc], y[rr,cc]
    pz = field.sample(px,py)
    d = tree_gap[rr,cc]
    colony = bands(px+51,py-36)
    wet = field.sample_mask("shore",px,py)
    # Small stones follow rock aprons. Birch marks woodland fringes; ferns gather
    # in shade; balsam fills the dappled gaps. Open vehicle meadows stay low.
    rocks = pcg_foliage.load(scenery/"rocks-and-outcrops.authored-decor.json")["decor"]
    rxy = np.array([[r["pos"][0]*.01,-r["pos"][1]*.01] for r in rocks])
    rock_gap = cKDTree(rxy).query(np.c_[px,py])[0]
    kinds = np.select([rock_gap<12, d<13, (d<28)&(colony>.42)],
                      ["stone","fern","birch"], default="balsam")
    probability = np.select([kinds=="stone",kinds=="fern",kinds=="birch"],
                            [.30,.45,.27], default=.06 + .13*(wet>.05))
    probability *= .22+.78*colony
    dx = (field.sample(px+1,py)-field.sample(px-1,py))*.5
    dy = (field.sample(px,py+1)-field.sample(px,py-1))*.5
    normal = np.c_[-dx,-dy,np.ones_like(px)]
    normal /= np.linalg.norm(normal,axis=1)[:,None]
    points=[dict(id=i,position=[float(px[i]),float(py[i]),round(float(pz[i]),7)],
                 normal=normal[i].round(8).tolist(), density=round(float(probability[i]),6),
                 biome_mask=1, kind=str(kinds[i]), biome="woodland understory") for i in range(len(px))]
    src=out/"understory.candidates.json"
    src.write_text(json.dumps({"schema":1,"align_to_normal":True,"points":points},separators=(",",":")))
    jobs=[dict(input=str(src),output=str(out/f"understory{s}.pcg.json"),seed=SEED,scale_min=.76,scale_max=1.19,
               graph=f"/Game/MJOLNIR/PCGAuthoring/PWRField/PCG_Understory{s}") for s in ("","_repeat")]
    grass.dump(out/"request.json",{"jobs":jobs})
    area = float(weights.sum()/255 * (spec["scale"][0]/100)**2)
    grass.dump(out/"field.receipt.json",dict(active_components=len(components),field_area_km2=4.,
            habitat_area_m2=float(allowed.sum()*(spec["scale"][0]/100)**2),weighted_area_m2=area,
            expected_logical_grass=int(area*config["full_density_instances_per_m2"]),
            grass_cull_m=[40,60],root_clearance_m=clearance,baseline_groundcover=base["preserved_groundcover"],
            recommended_test_pose_m=[-818,-486],pcg_candidate_count=len(points),pcg_request=str(out/"request.json")))
    print((out/"field.receipt.json").read_text(),flush=True)


def finalize(out):
    source, first, repeat = [out/s for s in ("understory.candidates.json","understory.pcg.json","understory_repeat.pcg.json")]
    proof = pcg_foliage.compare(source,first,repeat)
    result = pcg_foliage.adapt(source,first,PALETTE,out,"understory")
    field=pcg_foliage.load(out/"pilot.json")
    data=pcg_foliage.load(out/"understory.json")
    instances=result["instances"]
    if not 500 <= len(instances) <= 14000:
        raise ValueError("Understory outside the playable instance budget")
    counts = {row["mesh"]:0 for row in data["groups"]}
    weights = np.fromfile(out/field["mask"]["file"],np.uint8).reshape(1009,1009)
    for r in instances:
        x,y,z=r["position"]
        ix,iy=round((x+1000)*1008/2000),round((1000-y)*1008/2000)
        if not weights[iy,ix]: raise ValueError("PCG output leaked outside eligible ground")
        counts[r["mesh"]]+=1
    for row in data["groups"]:
        row.update(mesh_info(str(ROOT/"target/release/mjolnir.exe"),PAKS,row["mesh"]))
        row["standin_slots"]=row.pop("slots")
        row["count"]=counts[row["mesh"]]
    data.update(count=len(instances), binary_sha256=grass.digest(out/data["file"]),
                exact_sidecars=[grass.digest(out/(data["file"]+f".xf{i}")) for i in range(1,len(data["groups"])+1)])
    grass.dump(out/"understory-bake.json",data)
    field["understory"]={"file":"understory-bake.json","sha256":grass.digest(out/"understory-bake.json")}
    grass.dump(out/"pilot.json",field)
    grass.dump(out/"understory.receipt.json",dict(proof=proof,selected=len(instances),by_mesh=counts,excluded_hits=0))
    print(json.dumps({"count":len(instances),"groups":len(counts)}))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=["prepare","finalize"])
    parser.add_argument("--out",type=Path,default=ROOT/"out/pwr/world-art/foliage")
    args=parser.parse_args()
    out=args.out.resolve()
    out.mkdir(parents=True,exist_ok=True)
    (prepare if args.action=="prepare" else finalize)(out)

"""Build an isolated map-owned render-only apron; never installs to the game."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import build_candidate as v4

OUT=v4.OUT/"apron"
PAKS=Path("C:/Program Files (x86)/Steam/steamapps/common/Halo Campaign Evolved/Meteorite/Content/Paks")
PACKAGE="/Game/MJOLNIR/Maps/PWR/SM_PWR_DistantApron"
MATERIAL="/Game/Env/Bio/Rock/Glacial/Rock_Glacial_Med_A/Materials/MI_Rock_Glacial_Med_A_NoSnow"
STEM="pakchunk963-MJOLNIRPWRVISTA_P"


def run(name,args,out=None):
    result=subprocess.run([str(a) for a in args],cwd=v4.REPO,capture_output=True,text=True)
    log=result.stdout+result.stderr
    ((out or v4.OUT/"apron")/(name+".log")).write_text(log,encoding="utf-8")
    if result.returncode or "MISMATCH" in log:
        raise RuntimeError(name+" failed: "+log[-2000:])
    return log


def package(apron_dir=None, material_spec=None):
    OUT=Path(apron_dir).resolve() if apron_dir else v4.OUT/"apron"
    binding=v4.pcg_foliage.load(material_spec) if material_spec else None
    material=(binding["parent"].split(".")[0] if binding else
              MATERIAL.removesuffix("_NoSnow") if v4.APRON_SNOW else MATERIAL)
    field=v4.field()
    receipt=v4.pcg_foliage.load(OUT/"receipt.json")
    if receipt["runtime_master_sha256"]!=field.manifest_sha256:raise ValueError("Apron belongs to another runtime master")
    for suffix in ("gltf","bin"):
        if v4.digest(OUT/("apron."+suffix))!=receipt[suffix+"_sha256"]:raise ValueError("Apron geometry changed after validation")
    uasset=OUT/"SM_PWR_DistantApron.uasset"
    log=run("mesh",[v4.REPO/"target/release/examples/mesh_rewrite.exe",PAKS,"basicshapes/cylinder",
                     OUT/"apron.gltf",uasset,"--offset","0,0,0","--rename",PACKAGE,
                     "--material",f"DistantGranite={material}=*","--asset-imports","--selftest"],OUT)
    match=re.search(r"SPAWN: location \(([-\d.]+), ([-\d.]+), ([-\d.]+)\) cm, uniform scale ([\d.]+)",log)
    if not match: raise RuntimeError("Native writer omitted normalization transform")
    x,y,z,scale=map(float,match.groups())
    run("package",[v4.REPO/"target/release/examples/package_add.exe",PAKS,OUT,"--name",STEM,
                    "--package",f"{PACKAGE}={uasset}"],OUT)
    shutil.copy2(PAKS/"pakchunk115-Windows.pak",OUT/(STEM+".pak"))
    actor={"id":"pwr_distant_apron","mesh":PACKAGE+".SM_PWR_DistantApron",
           "pos":[x,y,z],"rot":[0,0,0],"scale":[scale]*3,"static":True,"cast_shadow":False,
           "materials":[binding or {"parent":material+"."+material.rsplit("/",1)[-1]}]}
    v4.dump(OUT/"runtime_decor.json",{"schema":"mjolnir-runtime-decor-v1","render_only":True,"decor":[actor]})
    v4.dump(OUT/"package.receipt.json",{"container_stem":str(OUT/STEM),"runtime_decor":str(OUT/"runtime_decor.json"),
        "mesh":actor["mesh"],"material":material,"native_snowblend":v4.APRON_SNOW and not binding,
        "material_binding_sha256":v4.digest(material_spec) if material_spec else None,
        "snow_appearance_status":"explicit world-space material; requires live review" if binding else
                                "native height/slope mask; requires live review" if v4.APRON_SNOW else "NoSnow",
        "geometry_receipt_sha256":v4.digest(OUT/"receipt.json"),
        "native_mesh_selftest":True,"render_only":True,"collision_required":"Disabled by existing decor loader",
        "files":{suffix:{"path":str(OUT/(STEM+suffix)),"sha256":v4.digest(OUT/(STEM+suffix))}
                 for suffix in (".utoc",".ucas",".pak")}})
    print(json.dumps({"actor":actor,"container":str(OUT/STEM)},indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    v4.add_source_arguments(parser)
    parser.add_argument("--apron-dir",type=Path,help="Isolated geometry directory (default <out>/apron)")
    parser.add_argument("--material-spec",type=Path,help="Exact loader material object with parent/textures/vectors")
    args=parser.parse_args();v4.configure(args);package(args.apron_dir,args.material_spec)

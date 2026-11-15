"""Read the installed stock assets needed to reproduce PWR visual-v4.

Exports stay local under out/; this script writes no game files and starts no apps.
"""
from pathlib import Path
import subprocess
import build_candidate as v4

PAKS="C:/Program Files (x86)/Steam/steamapps/common/Halo Campaign Evolved/Meteorite/Content/Paks"
OUT=v4.OUT/"assets"
OUT.mkdir(parents=True,exist_ok=True)
CLI=v4.REPO/"target/release/mjolnir.exe"


def run(name,*args):
    result=subprocess.run([str(CLI),*map(str,args)],cwd=v4.REPO,capture_output=True,text=True)
    log=result.stdout+result.stderr
    (OUT/name).write_text(log,encoding="utf-8")
    if result.returncode: raise RuntimeError(name+": "+log[-1500:])
    print(name,"verified",flush=True)


run("mesh-list.log","mesh","list","--paks",PAKS,"--filter","Rock_","--out",OUT/"rock-bounds.json")
for spec in v4.ASSETS.values():
    leaf=spec["leaf"]
    run(leaf+".export.log","mesh","export","--paks",PAKS,"--asset",leaf,"--out",OUT/(leaf+".glb"))
materials={
    "pnw-macro-material":"/Game/Env/Bio/Rock/PNW/PNWGL_Rock_Macro_B/MI_PNWGL_Rock_Macro_B",
    "tundra-material":"/Game/Env/Bio/Rock/Massive_Tundra_Rock_Formation/MI_Massive_Tundra_Rock_Formation_01",
    "ulu-material":"/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Cliff_B/Materials/MIP_Rock_Uluwatu_Cliff_B",
    "pnw-large-material":"/Game/Env/Bio/Rock/PNW/Rock_PNW_Lrg_A/Materials/MI_Rock_PNW_Lrg_A",
}
for variant in ("Lrg_B","Lrg_C","Med_A","Med_B"):
    materials["nosnow-"+variant]="/Game/Env/Bio/Rock/Glacial/"+f"Rock_Glacial_{variant}/Materials/MI_Rock_Glacial_{variant}_NoSnow"
for name,path in materials.items():
    run(name+".properties.txt","ue","get","--paks",PAKS,"--package",path)
v4.dump(OUT/"audit.receipt.json",{"source":"installed cooked Halo Campaign Evolved CU4",
    "nanite_assets":list(v4.ASSETS),"materials":materials,
    "files":{p.name:v4.digest(p) for p in OUT.glob("*.glb")}})

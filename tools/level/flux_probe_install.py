"""Reversible, game-closed install of the isolated PWR Flux proof only.

Does not replace DLLs or the map's main containers. Records exact old/new hashes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

REPO=Path(__file__).resolve().parents[2]
GAME=Path("C:/Program Files (x86)/Steam/steamapps/common/Halo Campaign Evolved/Meteorite")


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def closed():
    result=subprocess.run(["powershell","-NoProfile","-Command",
        "@(Get-Process HaloCampaignEvolved -ErrorAction SilentlyContinue).Count"],capture_output=True,text=True,check=True)
    if result.stdout.strip()!="0":raise RuntimeError("Close the game before proof container changes")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("action",choices=["install","restore"]);p.add_argument("--proof",type=Path,required=True)
    a=p.parse_args();closed();proof=a.proof.resolve();backup=proof/"installed-backup"
    receipt_path=backup/"receipt.json"
    if a.action=="restore":
        receipt=json.loads(receipt_path.read_text())
        for item in receipt["files"]:
            target=Path(item["target"])
            if not target.is_relative_to(GAME):raise RuntimeError("Invalid restoration target")
            if target.exists() and digest(target)!=item["installed_sha256"]:raise RuntimeError(f"Proof target changed: {target}")
        for item in receipt["files"]:
            target=Path(item["target"])
            if item["previous"]:shutil.copy2(backup/item["previous"],target)
            elif target.exists():target.unlink()
        (backup/"restored.json").write_text(json.dumps({"restored":True,"files":len(receipt["files"])},indent=2))
        print("Restored exact original helper/metadata and removed temporary container");return
    if receipt_path.exists():raise RuntimeError("Proof snapshot exists; restore before creating a new proof directory")
    backup.mkdir(parents=True,exist_ok=True)
    scripts=GAME/"Binaries/Win64/ue4ss/Mods/MJOLNIRLevelLoader/Scripts"
    level=GAME/"Binaries/Win64/ue4ss/MJOLNIRMaps/PWR/level.json"
    original=(scripts/"main.lua").read_text(encoding="utf-8")
    source=(REPO/"mods/MJOLNIRLevelLoader/Scripts/main.lua").read_text(encoding="utf-8")
    def replace(old,new):
        nonlocal original
        if original.count(old)!=1:raise RuntimeError("Installed helper hook is ambiguous: "+old[:60])
        original=original.replace(old,new)
    replace("    Current.fluxPending = nil","    Current.fluxPending = nil\n    Current.fluxRuntime = nil")
    replace("local function clearActors()","local function clearActors()\n    Current.fluxRuntime = nil")
    replace("local Effects = { on = true }",'local Effects = { on = true }\nEffects.Flux = dofile(MOD_DIR .. "\\\\Scripts\\\\flux_runtime.lua")')
    api=source[source.index("function Effects.fluxAPI()"):source.index("    local dom = Current.actors[\"__flux_domain\"]",source.index("function Effects.fluxBake(id)"))]
    replace("function Effects.fluxBake()\n",api)
    old="function Effects.flux(world)\n    local spec = Current.level and Current.level.flux"
    new=source[source.index("function Effects.flux(world)"):source.index('    if type(spec) ~= "table"',source.index("function Effects.flux(world)"))].rstrip()
    replace(old,new)
    start=source.index('    RegisterConsoleCommandHandler("mjolnir_flux_bake"')
    end=source.index('    RegisterConsoleCommandHandler("mjolnir_flux_recapture"',start)
    installed_start=original.index('    RegisterConsoleCommandHandler("mjolnir_flux_bake"')
    installed_end=original.index('    RegisterConsoleCommandHandler("mjolnir_flux_recapture"',installed_start)
    original=original[:installed_start]+source[start:end]+original[installed_end:]
    main=proof/"proof.main.lua";main.write_text(original,encoding="utf-8")
    check=subprocess.run(["lua","-e",f"assert(loadfile([[{main.as_posix()}]]))"],capture_output=True,text=True)
    if check.returncode:raise RuntimeError(check.stderr)
    document=json.loads(level.read_text(encoding="utf-8"))
    if document.get("flux"):raise RuntimeError("Existing PWR Flux must be preserved; use a separate proof map")
    document["flux"]=json.loads((proof/"flux.spec.json").read_text())
    document["decor"].append(json.loads((proof/"bed.actor.json").read_text()))
    prepared=proof/"proof.level.json";prepared.write_text(json.dumps(document,indent=1)+"\n",encoding="utf-8")
    files=[(main,scripts/"main.lua"),(REPO/"mods/MJOLNIRLevelLoader/Scripts/flux_runtime.lua",scripts/"flux_runtime.lua"),(prepared,level)]
    stem="pakchunk962-MJOLNIRPWRFLUXPROOF_P"
    for suffix in (".utoc",".ucas",".pak"):
        target=GAME/"Content/Paks"/(stem+suffix)
        if target.exists():raise RuntimeError("Proof container already exists")
        files.append((proof/(stem+suffix),target))
    records=[]
    for i,(src,target) in enumerate(files):
        previous=f"{i}-{target.name}" if target.exists() else None
        if previous:shutil.copy2(target,backup/previous)
        records.append({"target":str(target),"previous":previous,"previous_sha256":digest(target) if previous else None,"installed_sha256":digest(src)})
    receipt_path.write_text(json.dumps({"files":records},indent=2))
    for src,target in files:shutil.copy2(src,target)
    print("Installed isolated Flux proof; snapshot: "+str(receipt_path))


if __name__=="__main__":main()

"""Prepare then supervise a reversible, camera-only rehearsal using the existing verified switcher."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import zipfile

QA=Path(__file__).resolve().parent
ART=QA.parent
PWR=ART.parent
OLD=PWR/"playtest-20261121"
BASE=OLD/"flight-candidate"
PREVIOUS_RUN=OLD/"steam-rehearsal-1795051153335"
GAME=Path("C:/Program Files (x86)/Steam/steamapps/common/Halo Campaign Evolved")
PAKS=GAME/"Meteorite/Content/Paks"
sys.path.insert(0,str(PWR/"flight-review"))
from bridge import call


def digest(path):
    with path.open("rb") as f: return hashlib.file_digest(f,"sha256").hexdigest()


def link(source,dest):
    dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists(): raise FileExistsError(dest)
    os.link(source,dest)


def prep(build,review):
    review.mkdir(parents=True,exist_ok=False)
    bundle=review/"rehearsal-bundle"
    sat=review/"saturday"
    run=review/"steam"
    sat.mkdir(); run.mkdir()
    mapmeta=json.loads((build/"receipt.json").read_text())
    rt=json.loads((build/"solo/developer-runtime-receipt.json").read_text())
    assert mapmeta["sha256"]==rt["paired_map"]["sha256"]
    assert digest(build/mapmeta["archive"])==mapmeta["sha256"] and digest(build/"solo"/rt["archive"])==rt["sha256"]
    link(build/mapmeta["archive"],sat/mapmeta["archive"])
    link(build/"solo"/rt["archive"],sat/rt["archive"])
    plan=json.loads((BASE/"rehearsal-receipt.json").read_text())
    oldfiles=plan["files"]
    members=mapmeta["members_sha256"]
    # Use the same local prologue as the flight rehearsal. The installed developer
    # mount calls chunk 965 "LAND-Windows". The shareable archive names it by map.
    changes={}
    for canonical,local in [("pakchunk965-MJOLNIRLAND-PWR_P","pakchunk965-MJOLNIRLAND-Windows"),
            ("pakchunk997-MJOLNIRMAP-PWR_P","pakchunk997-MJOLNIRMAP-PWR_P"),
            ("pakchunk956-MJOLNIRPWRSURFACES-PWR_P","pakchunk956-MJOLNIRPWRSURFACES-PWR_P")]:
        if "965" in local:
            for ext in (".utoc",".ucas"):
                assert digest(PAKS/(local+ext))==digest(BASE/"map-input"/(canonical+ext))
        for ext in (".utoc",".ucas"):
            name=canonical+ext
            source=build/"map-input"/name
            assert digest(source)==members["content/"+name]
            changes["Paks/"+local+ext]=source
    cooked=PWR/"world-surfaces/cooked"
    stub=cooked/"pakchunk956-MJOLNIRPWRSURFACES_P.pak"
    assert digest(stub)==json.loads((cooked/"receipt.json").read_text())["files_sha256"][stub.name]
    changes["Paks/pakchunk956-MJOLNIRPWRSURFACES-PWR_P.pak"]=stub
    new_surface_names=[Path(k).stem for k in changes if "pakchunk956-" in k]
    assert len(new_surface_names)==3 and len(set(new_surface_names))==1
    changes["Win64/ue4ss/MJOLNIRMaps/PWR/level.json"]=build/"map-input/pwr.level.json"
    assert digest(changes["Win64/ue4ss/MJOLNIRMaps/PWR/level.json"])==members["map/level.json"]
    for key,expected in oldfiles.items():
        if key in changes: continue
        src=BASE/"rehearsal-bundle"/key
        assert digest(src)==expected
        link(src,bundle/key)
    for key,src in changes.items(): link(src,bundle/key)
    files={p.relative_to(bundle).as_posix():digest(p) for p in bundle.rglob("*") if p.is_file()}
    with zipfile.ZipFile(sat/rt["archive"]) as runtime:
        for k,h in json.loads(runtime.read("manifest.json"))["payload_sha256"].items():
            local=("Win64/ue4ss/Mods/"+k[5:]) if k.startswith("mods/") else ("Paks/"+Path(k).name)
            assert files[local]==h
    plan.update(map_sha256=mapmeta["sha256"], runtime_sha256=rt["sha256"],files=files,
                profile="solo-world-visual-inspection",launched=False)
    (review/"rehearsal-receipt.json").write_text(json.dumps(plan,indent=2))
    for ext in (".utoc",".ucas"):
        name="pakchunk997-MJOLNIRMAP-PWR_P"+ext
        link(OLD/"saturday/map-input"/name,sat/"map-input"/name)
    shutil.copy2(PREVIOUS_RUN/"switch.py",run/"switch.py")
    print("Verified",len(files),"temporary world files",flush=True)


def status():
    return call("game_status",{})[0]["text"]


def supervise(review):
    run=review/"steam"
    assert "process      running" not in status()
    def switch(action):
        subprocess.run([sys.executable,"switch.py",action],cwd=run,check=True)
    switch("prepare"); switch("apply")
    pid=None
    try:
        reply=call("game_launch",{"via":"steam","save_suffix":"PWRWorldArtNov18","width":1600,"height":900,"wait_seconds":100})[0]["text"]
        found=re.search(r"pid (\d+)",reply)
        if found: pid=found[1]
        assert pid and "bridge answering" in reply,reply
        (review/"ready.json").write_text(json.dumps({"pid":int(pid)}))
        print("Camera rehearsal ready",pid,flush=True)
        for _ in range(1200):
            if (review/"finish").exists(): break
            if _%15==0 and ("pid "+pid) not in status(): break
            time.sleep(1)
    finally:
        live=status()
        if "process      running" in live:
            if pid is None: raise RuntimeError("Launch returned no PID; verify the owner before restoring")
            assert ("pid "+pid) in live, "A different Halo process is running"
            call("game_quit",{})
            for _ in range(25):
                if "process      running" not in status(): break
                time.sleep(1)
            else: raise RuntimeError("Owned Halo process is still open")
        # A private run that crashes can leave its crash reporter holding the temporary
        # mod directory open. Close only a reporter belonging to this rehearsal.
        if pid:
            query = ("$owned = Get-CimInstance Win32_Process -Filter \"Name = 'CrashReportClient.exe'\" | "
                     "Where-Object { $_.ParentProcessId -eq " + str(int(pid)) +
                     " -and $_.CommandLine -like '*Saved_PWRWorldArtNov18*' }; "
                     "foreach ($r in $owned) { Stop-Process -Id $r.ProcessId -ErrorAction Stop }")
            subprocess.run(["powershell","-NoProfile","-Command",query],check=True)
        for attempt in range(4):
            try:
                switch("restore")
                break
            except subprocess.CalledProcessError:
                if attempt==3: raise
                time.sleep(2)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("build",type=Path)
    p.add_argument("name")
    args=p.parse_args()
    assert re.fullmatch(r"pass-\d+",args.name)
    review=QA/args.name
    prep(args.build.resolve(),review)
    supervise(review)

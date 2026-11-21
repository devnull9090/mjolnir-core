import hashlib
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path

run = Path(__file__).resolve().parent
review = run.parent
if os.environ.get("PWR_FLIGHT_REHEARSAL") == "1":
    review = review / "flight-candidate"
elif os.environ.get("PWR_SOLO_DIAGNOSTIC") == "1":
    review = review / "solo-diagnostic"
game = Path("C:/Program Files (x86)/Steam/steamapps/common/Halo Campaign Evolved").resolve(strict=True)
active = (game / "Meteorite/Binaries/Win64/ue4ss").resolve(strict=True)
paks = (game / "Meteorite/Content/Paks").resolve(strict=True)
assert active.parent == game/"Meteorite/Binaries/Win64" and paks.parent == game/"Meteorite/Content"
plan = json.loads((review / "rehearsal-receipt.json").read_text())
bundle = review / "rehearsal-bundle"
state = run / "backup.json"
original = run / "original-ue4ss"
shadow = run / "test-ue4ss"
flag = ".pwr-rehearsal-owner"

def sha(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()

def inventory(folder):
    return {p.relative_to(folder).as_posix():sha(p) for p in folder.rglob("*") if p.is_file()}

def write(dest,data):
    temp = dest.with_name(dest.name+".pwr-tmp")
    assert not temp.exists()
    temp.write_text(json.dumps(data,indent=2))
    os.replace(temp,dest)

def replace(src,dest):
    tmp=dest.with_name(dest.name+".pwr-tmp")
    assert not tmp.exists()
    shutil.copy2(src,tmp)
    os.replace(tmp,dest)

def prepare():
    assert not state.exists() and not original.exists() and not shadow.exists() and not (active/flag).exists()
    assert not any(p.is_symlink() or (p.stat().st_file_attributes & 1024) for p in active.rglob("*"))
    sat=review/"saturday"
    archive=next(sat.glob("*.mjolnir"))
    runtime=next(sat.glob("*.zip"))
    assert sha(archive)==plan["map_sha256"] and sha(runtime)==plan["runtime_sha256"]
    with zipfile.ZipFile(runtime) as z:
        baseline=json.loads(z.read("manifest.json"))["baseline_sha256"]
    for name,expected in baseline.items():
        file=game/name
        assert (sha(file) if file.is_file() else None)==expected,name
    before=inventory(active)
    shutil.copytree(active,shadow)
    assert inventory(shadow)==before
    (shadow/flag).write_text(run.name)
    prefix="Win64/ue4ss/"
    changes={}
    backups=run/"original-paks"
    backups.mkdir()
    for name,digest in plan["files"].items():
        src=(bundle/name).resolve(strict=True)
        assert src.is_relative_to(bundle) and sha(src)==digest
        if name.startswith(prefix):
            dest=(shadow/name.removeprefix(prefix)).resolve()
            assert dest.is_relative_to(shadow)
            dest.parent.mkdir(parents=True,exist_ok=True)
            replace(src,dest)
        else:
            assert name=="Paks/"+src.name and src.suffix in (".pak",".utoc",".ucas")
            dest=paks/src.name
            old=sha(dest) if dest.is_file() else None
            if old != digest:
                if old:
                    shutil.copy2(dest,backups/src.name)
                    assert sha(backups/src.name)==old
                changes[src.name]={"old":old,"new":digest}
    for rel in plan["queued_files_quarantined"]:
        # Exclude old native request/reply files from the temporary copy.
        path=(game/rel).relative_to(active)
        target=(shadow/path).resolve()
        assert target.is_relative_to(shadow)
        target.unlink(missing_ok=True)
    for name in ("pending_join.txt","pending_join.discord.tmp"):
        (shadow/"Mods/MJOLNIRLobby"/name).unlink(missing_ok=True)
    (shadow/"Mods/MJOLNIRLobby/last_game.txt").write_bytes(b"PWR\twarfare")
    write(state,{"original_files":before,"paks":changes})
    print("Verified baseline, packages and backup:",len(before),"protected mod-tree files;",len(changes),"changed cooked files.",flush=True)

def apply():
    s=json.loads(state.read_text())
    assert inventory(active)==s["original_files"] and not original.exists()
    assert (shadow/flag).read_text()==run.name
    ledger=run/"active-switch.json"
    assert not ledger.exists()
    scenario = "pakchunk997-MJOLNIRMAP-PWR_P"
    scenario_files={scenario+suffix for suffix in (".utoc",".ucas")}
    if any("Paks/"+name in plan["files"] for name in scenario_files):
        assert all("Paks/"+name in plan["files"] for name in scenario_files)
        for name in scenario_files:
            known=run.parent/"saturday/map-input"/name
            current=paks/name
            digest=sha(known)
            assert sha(current)==digest,name
            saved=run/"original-paks"/name
            if not saved.exists():
                shutil.copy2(current,saved)
            assert sha(saved)==digest
            s["paks"][name]={"old":digest,"new":plan["files"]["Paks/"+name]}
    expected={}
    for key,h in plan["files"].items():
        if key.startswith("Paks/"):
            name=Path(key).name
            assert key=="Paks/"+name and sha(bundle/key)==h
            if name not in s["paks"]:
                assert (paks/name).is_file() and sha(paks/name)==h,name
            else:
                expected[name]=h
    assert set(expected)==set(s["paks"])
    for name,v in s["paks"].items():
        dest=paks/name
        assert (sha(dest) if dest.exists() else None)==v["old"]
    write(ledger,{name:{"old":s["paks"][name]["old"],"new":h} for name,h in expected.items()})
    # Both resolved tree names are fixed inside the checked game and run directories.
    active.rename(original)
    try:
        shadow.rename(active)
        for name in s["paks"]:
            replace(bundle/"Paks"/name,paks/name)
        for key,h in plan["files"].items():
            p=paks/Path(key).name if key.startswith("Paks/") else active/key.removeprefix("Win64/ue4ss/")
            assert sha(p)==h,key
    except BaseException:
        restore()
        raise
    print("Verified all",len(plan["files"]),"solo overlay entries on registered game",flush=True)

def restore():
    s=json.loads(state.read_text())
    ledger=run/"active-switch.json"
    if ledger.exists():
        live=json.loads(ledger.read_text())
        extra=set(live)-set(s["paks"])
        assert extra.issubset({"pakchunk997-MJOLNIRMAP-PWR_P.utoc","pakchunk997-MJOLNIRMAP-PWR_P.ucas"})
        assert all(name in live and live[name]["old"]==v["old"] for name,v in s["paks"].items())
        for name in extra:
            assert sha(run/"original-paks"/name)==live[name]["old"]
        s["paks"]=live
    if original.exists():
        if active.exists():
            assert (active/flag).read_text()==run.name and not shadow.exists()
            active.rename(shadow)
        original.rename(active)
    for name,v in s["paks"].items():
        p=paks/name
        current=sha(p) if p.exists() else None
        if current==v["old"]:
            continue
        assert current==v["new"],"Conflicting external write to "+name
        if v["old"] is None:
            p.unlink()
        else:
            replace(run/"original-paks"/name,p)
    assert inventory(active)==s["original_files"]
    for name,v in s["paks"].items():
        p=paks/name
        assert (sha(p) if p.exists() else None)==v["old"]
    write(run/"restored.json",{"mod_files_byte_verified":len(s["original_files"]),"paks_verified":len(s["paks"]),"restored":True})
    ledger.unlink(missing_ok=True)
    print("Steam installation byte-verified after restoration")

{"prepare":prepare,"apply":apply,"restore":restore}[sys.argv[1]]()

"""One reversible private Halo run: locked .13 benchmark, moving camera, then matched photographs."""
from __future__ import annotations
import argparse
import base64
from contextlib import contextmanager
from io import BytesIO
import json
import math
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import time
from unittest.mock import patch

from PIL import Image
import benchmark as b

HERE=b.HERE
REFERENCE=b.VIS/"final.13"
BASE=HERE/"baseline-13/benchmark.json"
RAIL=HERE/"southwest-rail.json"
EXTENT=[1600,900]
RAIL_STOP="""local s=PWRAlpineRail;if s then s.active=false;UnregisterHook(s.func,s.pre,s.post);PWRAlpineRail=nil end"""
RAIL_DUMP="""local s=assert(PWRAlpineRail); assert(s.done);print('TICKS '..s.ticks); for _,m in ipairs(s.marks) do print(m) end"""
RES_READ="""local ok,v=pcall(function()
    local k=StaticFindObject('/Script/Engine.Default__KismetSystemLibrary')
    local value=k:GetConsoleVariableStringValue('r.SetRes')
    if type(value)=='string' then return value end
    return value:ToString()
end)
print('RES '..(ok and v or ''))"""

def reference_frames():
    baseline=b.read(BASE)
    b.check(baseline["completed"] and baseline["restoration"]["restored"],"Missing verified .13 timing baseline")
    b.check(baseline["plan"]==b.plan(),"The fixed .13 telemetry protocol changed")
    receipt=b.read(REFERENCE/"rehearsal-receipt.json")
    b.check(receipt["map_sha256"]==baseline["release"]["map_sha256"],"Art and timing source releases differ")
    main=b.read(REFERENCE/"frames/frames.json")
    field=b.read(REFERENCE/"field-check/receipt.json")
    photos={}
    for name,pose in b.cameras().items():
        if name in main["frames"]:
            site=main["frames"][name]
            directory=REFERENCE/"frames"
            wanted,frame=site["requested"],site["frames"][0]
        else:
            site=field["cameras"][name]
            directory=REFERENCE/"field-check"
            wanted,frame=site["pose"],site["captures"][0]
        b.check(pose==wanted,"Reference camera differs from timing camera at "+name)
        for side in ("camera_before","camera_after"):
            p=frame[side]
            b.check(math.dist(p[:3],pose[:3])<.1 and all(abs((x-y+180)%360-180)<.01 for x,y in zip(p[3:6],pose[3:])),
                    "Recorded .13 photo position differs at "+name)
            b.check(list(p[6:8])==EXTENT,"Unexpected .13 source viewport")
        path=directory/frame["file"]
        with Image.open(path) as im:
            b.check(list(im.size)==EXTENT and im.format=="PNG","Invalid .13 source image")
        photos[name]={"file":str(path),"sha256":b.sha(path),"pose":pose,"capture":frame}
    return photos

def rail_code():
    rail=b.read(RAIL)
    points=rail["poses_ue_cm_pitch_yaw_hfov"]
    b.check(len(points)==91 and rail["duration_s"]==15 and rail["length_m"]==180,"Reference rail changed")
    b.check(all(len(v)==6 and v[5]==82 and all(math.isfinite(x) for x in v) for v in points),"Invalid rail poses")
    table="{"+",".join("{"+",".join(map(str,p))+"}" for p in points)+"}"
    code=(HERE/"traversal.lua").read_text(encoding="utf-8-sig")
    return rail,code.replace("__POINTS__",table).replace("__DURATION__",str(rail["duration_s"]))

def traversal(folder,photo,native_dir,expected):
    rail,motion=rail_code()
    poses=rail["poses_ue_cm_pitch_yaw_hfov"]
    timings=(HERE/"window.lua").read_text(encoding="utf-8-sig")
    timings=timings.replace("__DLL__",json.dumps((native_dir/"mjolnir_frame_times.dll").as_posix()))
    timings=timings.replace("__TIMES__",json.dumps((native_dir/"frame_times.txt").as_posix()))
    lua=lambda code:b.run_lua(photo,code)
    lua("assert(not PhotoQA and not PWRAlpineBench and not PWRAlpineRail)")
    try:
        lua(photo.PREP)
        photo.setpose(poses[0],True)
        time.sleep(b.SETTLE_SECONDS)
        start=b.prove_pose(photo,poses[0])
        b.check(b.checked_settings(photo)==expected,"Moving run differs from stationary settings")
        b.check("BENCH_READY" in lua(timings),"Moving timing unavailable")
        b.check("RAIL_READY" in lua(motion),"Moving rail unavailable")
        duration=rail["duration_s"]
        lua(f"PWRAlpineBench.begin({duration});PWRAlpineRail.active=true")
        time.sleep(duration+1.5)
        window=b.parse_window(lua(b.DUMP))
        trace=lua(RAIL_DUMP)
        ticks=int(next(x[6:] for x in trace.splitlines() if x.startswith("TICKS ")))
        marks=[list(map(float,x.split()[1:])) for x in trace.splitlines() if x.startswith("MARK ")]
        b.check([q[0] for q in marks]==list(range(5)) and all(q[2]<.1 and q[3]<.01 for q in marks),"Missing or displaced rail samples")
        b.check(max(abs(q[1]-q[0]/4) for q in marks)<.03 and abs(ticks-window["frames"])<=3,"Timed camera samples disagree")
        end=b.prove_pose(photo,poses[-1])
        b.check(b.checked_settings(photo)==expected,"Moving run settings changed")
        b.write(folder/"traversal.json",{"rail_sha256":b.sha(RAIL),"route":rail["road"],"length_m":rail["length_m"],
                "duration_s":duration,"camera_before":start,"camera_after":end,"marks":marks,
                "mark_fields":["quarter","elapsed_fraction","position_error_cm","angle_error_deg","x_cm","y_cm","z_cm"],
                "camera_ticks":ticks,"window":window,"pawn_moved":False,"frame_captures":0,
                "baseline":"No moving .13 reference was recorded."})
        print("Moving window complete, five camera checkpoints verified.",flush=True)
    finally:
        try:lua(RAIL_STOP)
        finally:
            try:lua(b.STOP)
            finally:lua(photo.RESTORE)

def wait_size(photo,desired,timeout=6):
    end=time.monotonic()+timeout
    while True:
        size=[round(x) for x in photo.probe()[6:8]]
        if size==desired or time.monotonic()>=end:return size
        time.sleep(.3)

def resolution(photo):
    return b.run_lua(photo,RES_READ).strip().partition("RES ")[2].strip()

@contextmanager
def visual_viewport(photo,receipt):
    original=[round(v) for v in photo.probe()[6:8]]
    receipt.update(original_viewport=original,reference_viewport=EXTENT)
    if original==EXTENT:
        receipt.update(status="Native viewport already matched.")
        yield
        return
    raw=resolution(photo)
    # Change only a transient engine CVar when the exact original value can be replayed.
    match=re.fullmatch(r"(\d+)[xX](\d+)(wf|w|f)?",raw,re.I)
    if not match or [int(match[1]),int(match[2])]!=original:
        receipt.update(status="Original output CVar unavailable or different from active viewport; preserving current display.")
        yield
        return
    def send(value):
        return b.run_lua(photo,"assert(mj.console("+json.dumps("r.SetRes "+value)+"))")
    receipt["original_cvar"]=raw
    try:
        send("1600x900w")
        actual=wait_size(photo,EXTENT)
        receipt["status"]="Matched 1600x900 source viewport." if actual==EXTENT else "Engine kept a different source viewport."
        if actual!=EXTENT and actual!=original:
            send(raw)
            b.check(wait_size(photo,original)==original,"Could not return unsupported display to original extent")
        yield
    finally:
        send(raw)
        actual=wait_size(photo,original,10)
        receipt["restored_viewport"]=actual
        b.check(actual==original and resolution(photo).lower()==raw.lower(),"Display CVar or viewport did not return to its original value")

def take_image(photo,folder,name,pose):
    photo.setpose(pose,True)
    time.sleep(b.SETTLE_SECONDS)
    before=b.prove_pose(photo,pose)
    blocks=photo.call("game_screenshot",{"background_only":True,"max_width":EXTENT[0]})
    info=next(v["text"] for v in blocks if v["type"]=="text")
    b.check("PrintWindow" in info and "blank" not in info.lower(),"Background Halo capture unsuitable: "+info)
    raw=base64.b64decode(next(v["data"] for v in blocks if v["type"]=="image"),validate=True)
    after=b.prove_pose(photo,pose)
    b.check(before[6:8]==after[6:8] and after[8]>before[8],"Capture viewport changed or game clock stalled")
    with Image.open(BytesIO(raw)) as img:
        b.check(img.format=="PNG" and list(img.size)==EXTENT,"Capture did not have the .13 photo's aspect and size")
        b.check(statistics.pstdev(img.convert("L").resize((32,18)).getdata())>3,"Uniform capture")
    path=folder/(name+".png")
    path.write_bytes(raw)
    return {"file":str(path),"sha256":b.sha(path),"metadata":info,"camera_before":before,"camera_after":after,
            "native_viewport":before[6:8],"native_viewport_matches_reference":list(before[6:8])==EXTENT}

def photograph(folder,photo,baseline):
    refs=reference_frames()
    output=folder/"photos"
    output.mkdir()
    report={"art_reference_release_sha256":b.read(BASE)["release"]["map_sha256"],"release":baseline["release"],
            "settings_before_visual_phase":baseline["settings"],"viewport":{},"captures":{},"completed":False}
    def save():b.write(output/"comparison.json",report)
    lua=lambda code:b.run_lua(photo,code)
    lua("assert(not PhotoQA and not PWRAlpineBench and not PWRAlpineRail)")
    save()
    try:
        lua(photo.PREP+photo.HIDE)
        with visual_viewport(photo,report["viewport"]):
            report["visual_settings"]=b.checked_settings(photo)
            expected=baseline["settings"]
            effective=report["visual_settings"]
            permitted={"hud","viewport_w","viewport_h","display_mode"}
            unexpected=[k for k in expected if k not in permitted and expected[k]!=effective.get(k)]
            b.check(not unexpected,"Render quality changed in visual phase: "+str(unexpected))
            for name,data in refs.items():
                frame=take_image(photo,output,name,data["pose"])
                report["captures"][name]={"reference":data,"candidate":frame}
                save()
                print("Photographed",name,"at",frame["native_viewport"],flush=True)
    finally:
        try:
            lua(photo.RESTORE)
            report["camera_and_hud_restored"]=b.checked_settings(photo)==baseline["settings"]
        finally:save()
    b.check(report["camera_and_hud_restored"],"Visual state not restored")
    report["completed"]=True
    save()

def run(args):
    refs=reference_frames()
    b.check(len(refs)==4,"Matched reference photos incomplete")
    folder=HERE/args.label
    b.check(re.fullmatch(r"[A-Za-z0-9_-]{1,64}",args.label) and not folder.exists(),"Run label must be new")
    # Only the private save profile used by this owned rehearsal is in scope.
    profile=Path(os.environ["LOCALAPPDATA"])/"Meteorite"/("Saved_"+b.PROFILE)/"Config/Windows/GameUserSettings.ini"
    original=profile.read_bytes() if profile.exists() else None
    errors={}
    stationary=b.measure
    def session(folder,identity,pid,photo,native_dir):
        benchmark=stationary(folder,identity,pid,photo,native_dir)
        print("All eight fixed windows closed.",flush=True)
        if not args.skip_traversal:
            try:traversal(folder,photo,native_dir,benchmark["settings"])
            except Exception as exc:
                errors["traversal"]=str(exc)
                print("Moving camera verification did not complete:",exc,flush=True)
        print("All timed windows closed. Starting HUD-free photographs.",flush=True)
        try:photograph(folder,photo,benchmark)
        except Exception as exc:
            errors["photographs"]=str(exc)
            print("Photograph verification did not complete:",exc,flush=True)
        return benchmark
    # Inject the post-measure phase into the original private-launch driver's sole callback.
    # Its file and stationary measurement protocol stay byte-identical to the .13 baseline.
    try:
        with patch.object(b,"measure",session):
            b.run_release(args.release,args.label)
    finally:
        restored=folder/"steam/restored.json"
        if (folder/"ready.json").is_file() and restored.is_file() and b.read(restored)["restored"]:
            current=profile.read_bytes() if profile.exists() else None
            if current!=original:
                if original is None:profile.unlink()
                else:
                    import tempfile
                    with tempfile.NamedTemporaryFile(dir=profile.parent,delete=False) as f:
                        temp=Path(f.name)
                        f.write(original)
                    temp.replace(profile)
            b.check((profile.read_bytes() if profile.exists() else None)==original,"Private display preferences differ after exit")
            import hashlib
            b.write(folder/"visual-profile-restored.json",{"path":str(profile),"file_present":original is not None,
                    "original_sha256":hashlib.sha256(original).hexdigest() if original else None,
                    "game_changed_file":current!=original,"byte_verified":True})
    delta=b.compare(BASE,folder/"benchmark.json")
    b.write(folder/"stationary-comparison.json",delta)
    if errors:
        b.write(folder/"additional-phase-errors.json",errors)
        raise RuntimeError("Game restored; see additional-phase-errors.json for incomplete evidence.")
    print("Restored game; photos and matched stationary comparison:",folder,flush=True)

def self_test():
    refs=reference_frames()
    rail,code=rail_code()
    lua=shutil.which("lua")
    b.check(lua is not None,"Lua not installed")
    fake="""local now,pos,rot,hook=0,nil,nil,nil
    os.clock=function() return now end
    local pc={GetAddress=function() return 22 end};local ctx={get=function() return pc end}
    local cam={K2_SetActorLocationAndRotation=function(_,p,r) pos=p;rot=r end,
      K2_GetActorLocation=function() return pos end,K2_GetActorRotation=function() return rot end}
    PhotoQA={pc=pc,camera=cam}
    RegisterHook=function(_,cb) hook=cb;return 3,4 end
    UnregisterHook=function(_,a,b) assert(a==3 and b==4);hook=nil end"""
    test=fake+"\n"+code+"\nPWRAlpineRail.active=true;for i=0,934 do now=i/60;hook(ctx) end\n"+RAIL_DUMP+"\n"+RAIL_STOP+"\nassert(not hook and not PWRAlpineRail)"
    result=subprocess.run([lua,"-"],input=test,text=True,capture_output=True,check=True).stdout
    marks=[list(map(float,x.split()[1:])) for x in result.splitlines() if x.startswith("MARK ")]
    b.check(len(marks)==5 and marks[-1][1]==1 and all(r[2]==r[3]==0 for r in marks),"Offline rail verification failed")
    b.check(math.dist(marks[-1][4:],rail["poses_ue_cm_pitch_yaw_hfov"][-1][:3])<.1,"Endpoint differs")
    print("Verified immutable .13 benchmark, four matching source photos, 180m control rail, five camera checkpoints and hook cleanup.")

if __name__=="__main__":
    ap=argparse.ArgumentParser(description=__doc__)
    modes=ap.add_subparsers(dest="command",required=True)
    modes.add_parser("self-test")
    cmd=modes.add_parser("run")
    cmd.add_argument("--release",type=Path,required=True)
    cmd.add_argument("--label",required=True)
    cmd.add_argument("--skip-traversal",action="store_true")
    ns=ap.parse_args()
    self_test() if ns.command=="self-test" else run(ns)


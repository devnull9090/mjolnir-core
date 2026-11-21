"""Measure one sealed PWR release using the Halo bridge. plan and self-test never launch Halo."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
PWR = HERE.parents[1]
ROOT = PWR.parents[1]
VIS = PWR / "ground-life/visual-review"
STUDY = PWR / "landscape-distance/campaign-study"
BASE_QA = PWR / "base-approaches/visual-review"
PROFILE = "PWRWorldArtNov18"
SITES = ("teton-road", "southwest-forest-road-driver", "red-shoulder", "valley-ridge")
WARM_SECONDS = 180
SETTLE_SECONDS = 5
WINDOW_SECONDS = 15
NATIVE_FIELDS = ("game_ms", "game_critical_ms", "draw_ms", "draw_critical_ms", "rhit_ms", "gpu_ms")

def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))

def write(path, data):
    path = Path(path)
    temporary = path.with_suffix(path.suffix+".pending")
    temporary.write_text(json.dumps(data, indent=2)+"\n", encoding="utf-8")
    temporary.replace(path)

def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def check(condition, message):
    if not condition:
        raise RuntimeError(message)

def cameras():
    original = read(VIS/"cameras.json")
    field = read(VIS/"field-check-cameras.json")["cameras"]
    return {site: (original if site in original else field)[site]["pose"] for site in SITES}

def plan():
    poses = cameras()
    return {"protocol": "pwr-alpine-fixed-v1", "warmup_seconds": WARM_SECONDS,
            "settle_seconds": SETTLE_SECONDS, "window_seconds": WINDOW_SECONDS,
            "order": [*SITES, *SITES[2:], *SITES[:2]], "poses_cm_deg": poses,
            "hud": "normal game HUD", "captures_in_timed_windows": 0,
            "native_sampler_sha256": sha(HERE/"window.lua"), "settings_reader_sha256": sha(HERE/"settings.lua"),
            "driver_sha256": sha(Path(__file__)),
            "presentation": "Engine controller frames and average native GPU timings; generated/presented frames excluded."}

def quantile(hist, q):
    threshold = math.ceil(sum(hist.values()) * q)
    total = 0
    for key in sorted(hist):
        total += hist[key]
        if total >= threshold:
            return key / 10
    raise ValueError("Empty frame histogram")

def parse_window(output):
    lines = dict(line.split(" ", 1) for line in output.splitlines() if line.startswith(("CLOCK ", "HIST ", "NATIVE ")))
    n, seconds, engine_seconds, worst = map(float, lines["CLOCK"].split())
    hist = Counter({int(b): int(v) for b, v in (entry.split(":") for entry in lines["HIST"].split(","))})
    native = lines["NATIVE"].split()
    check(native[0] == "ok" and len(native) == 8, f"Native telemetry rejected: {native}")
    check(n == int(n) and int(n) == sum(hist.values()) == int(native[1]) and n > 0, "Frame counters disagree")
    check(seconds > 0 and abs(engine_seconds - seconds) < max(.18, .03*seconds), "Controller and native real-time clocks disagree")
    split = dict(zip(NATIVE_FIELDS, map(float,native[2:])))
    check(all(math.isfinite(v) and v>=0 for v in split.values()) and split["gpu_ms"]>0, "Incomplete native GPU timing")
    return {"frames": int(n), "seconds": seconds, "engine_clock_seconds": engine_seconds, "fps":n/seconds,
            "mean_frame_ms": 1000*seconds/n, "p50_frame_ms":quantile(hist,.5),
            "p95_frame_ms":quantile(hist,.95), "p99_frame_ms":quantile(hist,.99), "worst_frame_ms":worst,
            "native_mean":split, "frame_histogram_tenths_ms":dict(sorted(hist.items()))}

def aggregate(windows):
    hist = Counter()
    for w in windows:
        hist.update({int(k):v for k,v in w["frame_histogram_tenths_ms"].items()})
    n=sum(w["frames"] for w in windows)
    seconds=sum(w["seconds"] for w in windows)
    check(n == sum(hist.values()),"Window histogram frame count changed")
    return {"frames":n, "measured_seconds":seconds, "fps":n/seconds, "mean_frame_ms":1000*seconds/n,
            "p50_frame_ms":quantile(hist,.50),"p95_frame_ms":quantile(hist,.95),
            "p99_frame_ms":quantile(hist,.99), "worst_frame_ms":max(w["worst_frame_ms"] for w in windows),
            "native_mean":{field:sum(w["native_mean"][field]*w["frames"] for w in windows)/n for field in NATIVE_FIELDS},
            "pass_means_ms":[w["mean_frame_ms"] for w in windows],
            "hitches_over_33ms":sum(v for k,v in hist.items() if k>330),
            "hitches_over_50ms":sum(v for k,v in hist.items() if k>500)}

def release_identity(release):
    doc=read(release/"receipt.json")
    solo=read(release/"solo/developer-runtime-receipt.json")
    check(doc["sha256"]==sha(release/doc["archive"])==solo["paired_map"]["sha256"], "Sealed map SHA mismatched")
    check(solo["sha256"]==sha(release/"solo"/solo["archive"]),"Sealed matched solo runtime SHA mismatched")
    return {"archive":doc["archive"],"map_sha256":doc["sha256"],"solo_runtime_sha256":solo["sha256"]}

def run_lua(photo, code):
    blocks=photo.call("game_lua",{"code":code,"timeout_ms":45000})
    return "\n".join(x["text"] for x in blocks if x["type"]=="text")

def operating_system_view(pid):
    query = f"$p=Get-Process -Id {int(pid)} -ErrorAction Stop; [pscustomobject]@{{affinity=$p.ProcessorAffinity.ToInt64().ToString('X'); priority=$p.PriorityClass.ToString(); cpu=(Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name); gpu=@(Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion)}} | ConvertTo-Json -Depth 4 -Compress"
    return json.loads(subprocess.check_output(["powershell","-NoProfile","-Command",query], encoding="utf-8-sig").strip())

def checked_settings(photo):
    raw=run_lua(photo,(HERE/"settings.lua").read_text(encoding="utf-8-sig"))
    parsed={line.split(" ",2)[1]:line.split(" ",2)[2] for line in raw.splitlines() if line.startswith("READ ")}
    check(parsed.get("world")=="World /Game/Levels/Halo1/Solo/PWR/PWR.PWR","Unexpected measured world")
    for name in ("viewport_w","viewport_h","r.ScreenPercentage","display_mode","t.MaxFPS","r.VSync","saved_fps_limit"):
        check(name in parsed and math.isfinite(float(parsed[name])), "Missing settings readback: "+name)
    check(float(parsed["viewport_w"])>0 and float(parsed["viewport_h"])>0 and float(parsed["r.ScreenPercentage"])>0,"Invalid rendered viewport or resolution setting")
    return parsed

def prove_pose(photo, desired):
    pose=photo.probe()
    check(math.dist(desired[:3],pose[:3])<.1 and all(abs((left-right+180)%360-180)<.01 for left,right in zip(desired[3:6],pose[3:6])),
          "Benchmark camera moved: "+str(pose))
    return pose

DUMP = """
local s=assert(PWRAlpineBench)
local w=assert(s.window)
if not w.done then print("WAIT"); return end
print(string.format("CLOCK %d %.8f %.8f %.4f",w.n,w.elapsed,w.engineElapsed,w.max))
print("NATIVE "..w.native)
local bins={};for k,v in pairs(w.hist) do bins[#bins+1]=tostring(k)..":"..tostring(v) end
print("HIST "..table.concat(bins,","))
"""
STOP = """
local s=PWRAlpineBench
if s then s.active=false;UnregisterHook(s.func,s.pre,s.post);PWRAlpineBench=nil end
"""

def take_window(photo):
    run_lua(photo, f"assert(PWRAlpineBench).begin({WINDOW_SECONDS})")
    # Nothing else touches the game, the screen, or the bridge while timing.
    time.sleep(WINDOW_SECONDS+1.25)
    raw=run_lua(photo,DUMP)
    if raw.strip()=="WAIT":
        time.sleep(2)
        raw=run_lua(photo,DUMP)
    result=parse_window(raw)
    check(WINDOW_SECONDS<=result["seconds"]<=WINDOW_SECONDS+2,"Window did not cover the requested interval")
    return result

def measure(folder, identity, pid, photo, native_dir):
    photo.runlua=lambda code:run_lua(photo,code)
    privately=photo.private_world()
    dressing=photo.dressing()
    report={"release":identity,"plan":plan(),"private_match":privately,"world_ready":dressing,
            "machine":operating_system_view(pid),"windows":[],"completed":False}
    native_dll=native_dir/"mjolnir_frame_times.dll"
    report["native_dll_sha256"]=sha(native_dll)
    exe=native_dir.parents[3]/"HaloCampaignEvolved.exe"
    report["game_exe_sha256"]=sha(exe)
    report["settings"]=checked_settings(photo)
    write(folder/"benchmark.json",report)
    code=(HERE/"window.lua").read_text(encoding="utf-8-sig")
    code=code.replace("__DLL__",json.dumps(native_dll.as_posix())).replace("__TIMES__",json.dumps((native_dir/"frame_times.txt").as_posix()))
    run_lua(photo,"assert(not PhotoQA and not PWRAlpineBench, 'An existing review camera or benchmark is active')")
    try:
        run_lua(photo,photo.PREP)
        check("BENCH_READY" in run_lua(photo,code),"Native observer did not initialize")
        # Visit all survey views before the timed part; then allow the private map to settle.
        for site,pose in report["plan"]["poses_cm_deg"].items():
            photo.setpose(pose,True)
            time.sleep(SETTLE_SECONDS)
            prove_pose(photo,pose)
        world_age=photo.probe()[8]
        if world_age<WARM_SECONDS:
            print(f"Private world warming for {WARM_SECONDS-world_age:.1f} more seconds",flush=True)
            time.sleep(WARM_SECONDS-world_age+.4)
        for site in report["plan"]["order"]:
            pose=report["plan"]["poses_cm_deg"][site]
            photo.setpose(pose,True)
            time.sleep(SETTLE_SECONDS)
            before=prove_pose(photo,pose)
            check(before[8]>=WARM_SECONDS,"Native world is still warming")
            settings=checked_settings(photo)
            check(settings==report["settings"],"Effective settings changed before "+site)
            window=take_window(photo)
            after=prove_pose(photo,pose)
            check(checked_settings(photo)==settings and before[6:8]==after[6:8],"Settings changed during "+site)
            window.update(site=site,camera_before=before,camera_after=after)
            report["windows"].append(window)
            write(folder/"benchmark.json",report)
            print(f"{site}: {window['mean_frame_ms']:.2f} ms frame, {window['native_mean']['gpu_ms']:.2f} ms GPU, p95 {window['p95_frame_ms']:.1f} ms",flush=True)
    finally:
        try:
            run_lua(photo,STOP)
        finally:
            run_lua(photo,photo.RESTORE)
    check(operating_system_view(pid)==report["machine"],"Machine affinity, priority, CPU or GPU metadata changed")
    report["sites"]={site:aggregate([w for w in report["windows"] if w["site"]==site]) for site in SITES}
    report["completed"]=True
    write(folder/"benchmark.json",report)
    return report


def run_switch(folder, action):
    env=os.environ.copy()
    # The general switch also services two older rehearsals. Select the release at this
    # working directory explicitly, independently of any inherited launcher variables.
    for key in ("PWR_FLIGHT_REHEARSAL","PWR_SOLO_DIAGNOSTIC"):
        env.pop(key,None)
    subprocess.run([sys.executable,"switch.py",action],cwd=folder/"steam",env=env,check=True)

def owns_session(game, pid=None):
    command = """@(Get-CimInstance Win32_Process -Filter "Name = 'HaloCampaignEvolved.exe'" | Select-Object ProcessId,ExecutablePath,CommandLine) | ConvertTo-Json -Compress"""
    for _ in range(8):
        val=subprocess.check_output(["powershell","-NoProfile","-Command",command],encoding="utf-8-sig").strip()
        result=json.loads(val) if val else []
        rows=result if isinstance(result,list) else [result]
        if not rows:
            return None
        check(len(rows)==1,"Multiple Halo processes found; keeping the original backup")
        row=rows[0]
        if row.get("ExecutablePath") and row.get("CommandLine"):
            exe=Path(row["ExecutablePath"]).resolve()
            check(exe.is_relative_to(game.resolve()) and
                  re.search(r"(?i)(?:^|\s)[\"']?-saveddirsuffix="+PROFILE+r"[\"']?(?:\s|$)",row["CommandLine"]),
                  "Another game session owns the process; keeping the original backup")
            found=int(row["ProcessId"])
            check(pid is None or found==pid,"Different game process has appeared; keeping the original backup")
            return found
        time.sleep(.2)
    raise RuntimeError("Could not verify the owner of the active Halo process")

def restore_after_run(folder, game, photo, pid):
    active=owns_session(game,pid)
    if active:
        photo.call("game_quit",{})
        deadline=time.monotonic()+30
        while owns_session(game,active) and time.monotonic()<deadline:
            time.sleep(.5)
        check(owns_session(game,active) is None,"Private game is still open; keeping original backup")
    for attempt in range(4):
        try:
            run_switch(folder,"restore")
            break
        except subprocess.CalledProcessError:
            if attempt==3:raise
            time.sleep(2)
    restored=read(folder/"steam/restored.json")
    check(restored["restored"],"Steam restoration did not verify")
    return restored

def run_release(release,label):
    check(re.fullmatch(r"[A-Za-z0-9_-]{1,64}",label),"Label must be a short file name")
    release=release.resolve()
    folder=HERE/label
    check(not folder.exists(),f"Run already exists: {folder}")
    identity=release_identity(release)
    sys.path[:0]=[str(STUDY),str(BASE_QA)]
    import compare_release, retire_961
    from quiet_supervisor import process_status
    default_override=os.environ.get("MJOLNIR_GAME_DIR")
    game=compare_release.GAME
    os.environ["MJOLNIR_GAME_DIR"]=str(game)
    photo=compare_release.photo
    pid=None
    try:
        check(process_status()=="process      stopped","Another Halo process owns the game")
        compare_release.stage(release,folder)
        retire_961.prepare(folder)
        run_switch(folder,"prepare")
        try:
            check(process_status()=="process      stopped","Another Halo process started during preparation")
            run_switch(folder,"apply")
            reply=photo.call("game_launch",{"via":"steam","save_suffix":PROFILE,"windowed":False,"wait_seconds":110})
            message=" ".join(block.get("text","") for block in reply)
            m=re.search(r"launched via steam, pid (\d+), bridge answering",message)
            check(m is not None,"Private launch did not reach the Halo bridge: "+message)
            pid=int(m.group(1))
            check(owns_session(game,pid)==pid,"Launch ownership changed")
            write(folder/"ready.json",{"pid":pid,"started":datetime.now(timezone.utc).isoformat(),"launch":"isolated profile; no display flags"})
            measure(folder,identity,pid,photo,compare_release.UE/"Mods/MJOLNIRHud/native")
        finally:
            if (folder/"steam/active-switch.json").exists():
                restore_after_run(folder,game,photo,pid)
    finally:
        if default_override is None:os.environ.pop("MJOLNIR_GAME_DIR",None)
        else:os.environ["MJOLNIR_GAME_DIR"]=default_override
    final=read(folder/"benchmark.json")
    final["restoration"]=read(folder/"steam/restored.json")
    write(folder/"benchmark.json",final)
    print("Verified completed benchmark:",folder/"benchmark.json",flush=True)

def compare(before,after):
    a,b=read(before),read(after)
    check(a["completed"] and b["completed"] and a["restoration"]["restored"] and b["restoration"]["restored"],"Incomplete rehearsal")
    for key in ("plan","settings","machine","native_dll_sha256","game_exe_sha256"):
        check(a[key]==b[key],"Unmatched comparison: "+key)
    out={"baseline":a["release"],"candidate":b["release"],"sites":{}}
    for site in SITES:
        old,new=a["sites"][site],b["sites"][site]
        out["sites"][site]={"frame_ms_delta":new["mean_frame_ms"]-old["mean_frame_ms"],
            "frame_time_percent_change":100*(new["mean_frame_ms"]/old["mean_frame_ms"]-1),
            "gpu_ms_delta":new["native_mean"]["gpu_ms"]-old["native_mean"]["gpu_ms"],
            "p95_frame_ms_delta":new["p95_frame_ms"]-old["p95_frame_ms"]}
    return out

def self_test():
    import shutil
    lua=shutil.which("lua")
    check(lua is not None,"Offline simulated-controller test needs the installed Lua interpreter")
    fake = """
    local now,n,line,observed=0,0,"",nil
    local world={GetFullName=function() return 'World /Game/Levels/Halo1/Solo/PWR/PWR.PWR' end}
    local pc={GetWorld=function() return world end, GetAddress=function() return 55 end}
    local ctx={get=function() return pc end}
    mj={pc=function() return pc end}
    StaticFindObject=function() return {GetRealTimeSeconds=function() return now end} end
    os.clock=function() return now end
    package.loadlib=function(_,name)
        if name:find('sample',1,true) then return function() n=n+1 end end
        return function() line=string.format('ok %d 8 4 3 2 1 6',n);n=0 end
    end
    io.open=function() return {read=function() return line end,close=function() end} end
    RegisterHook=function(_,cb) observed=cb;return 1,2 end
    UnregisterHook=function(_,a,b) assert(a==1 and b==2);observed=nil end
    """
    body=(HERE/"window.lua").read_text(encoding="utf-8-sig").replace("__DLL__","'mock'").replace("__TIMES__","'mocktime'")
    exercise="""
    PWRAlpineBench.begin(3)
    for f=1,240 do now=now+1/60;observed(ctx) end
    """
    code=fake+body+exercise+"\ndo\n"+DUMP+"\nend\n"+STOP+"\nassert(not observed and not PWRAlpineBench)"
    out=subprocess.run([lua,"-"],input=code,text=True,capture_output=True,check=True).stdout
    window=parse_window(out);both=aggregate([window,window])
    check(abs(both["fps"]-60)<.001 and both["native_mean"]["gpu_ms"]==6 and 16.6<=both["p99_frame_ms"]<=16.7,"Instrumentation fixture failed")
    check(len(plan()["order"])==8 and len(plan()["poses_cm_deg"])==4,"Camera fixture missing")
    print("Offline Lua hook, native accumulator, histogram, percentiles, pooled samples, cameras and cleanup verified.")

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="mode",required=True)
    sub.add_parser("self-test")
    sub.add_parser("plan")
    live=sub.add_parser("run",help="Explicitly stage, launch the private solo session, measure and restore Steam")
    live.add_argument("--release",type=Path,required=True)
    live.add_argument("--label",required=True)
    paired=sub.add_parser("compare")
    paired.add_argument("baseline",type=Path)
    paired.add_argument("candidate",type=Path)
    paired.add_argument("--output",type=Path)
    args=parser.parse_args()
    if args.mode=="self-test":self_test()
    elif args.mode=="plan":print(json.dumps(plan(),indent=2))
    elif args.mode=="run":run_release(args.release,args.label)
    else:
        result=compare(args.baseline,args.candidate)
        if args.output:write(args.output,result)
        else:print(json.dumps(result,indent=2))
if __name__=="__main__":main()


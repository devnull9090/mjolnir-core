"""One private Steam drop. Every game action uses the local MCP bridge."""
import json
import math
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from bridge import ROOT, call, runlua, shot

OUT = Path(__file__).resolve().parent
RUN = ROOT / "out/pwr/playtest-20261121/steam-rehearsal-1795051153335"
GAME = Path("C:/Program Files (x86)/Steam/steamapps/common/Halo Campaign Evolved")
NATIVE = GAME / "Meteorite/Binaries/Win64/ue4ss/Mods/MJOLNIRLobby/native"
STATE = NATIVE / "warfare_state.txt"
events, samples = [], []
stop = threading.Event()


def event(label, **data):
    entry = {"at":time.time(),"event":label,**data}
    events.append(entry)
    print(label, data, flush=True)


def state():
    try:
        lines = STATE.read_text(errors="replace").splitlines()
    except OSError:
        return {}
    head = dict(line.split(" ",1) for line in lines if " " in line)
    if head.get("ready")!="1" or head.get("status")!="2": return {}
    for row in lines:
        cols = row.split()
        if row.startswith("player ") and len(cols)==9 and cols[4]=="0":
            index, team, stage, local, x, y, z, unit = cols[1:]
            result = dict(instance=head["instance"],tick=int(head["tick"]),stage=int(stage),
                          unit=int(unit), position=list(map(float,[x,y,z])))
            for line in lines:
                if line.startswith("flight "+index+" "):
                    vx,vy,vz,b,s=map(float,line.split()[2:])
                    result.update(velocity=[vx,vy,vz],brake=int(b),steer=s)
                if line.startswith("clearance "+index+" "): result["clearance"]=float(line.split()[-1])
            return result
    return {}


def sample():
    last = None
    while not stop.wait(.07):
        try: s=state()
        except (ValueError,KeyError): continue
        if s and s["tick"]!=last:
            samples.append({"at":time.time(),**s})
            last = s["tick"]


def until(test, seconds, message):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        value=test()
        if value: return value
        time.sleep(.12)
    raise RuntimeError(message)


def gameplay(steps):
    return call("game_input",{"method":"game","steps":steps})


def auto(command):
    dest=NATIVE/"auto_state.txt"
    old=dest.stat().st_mtime_ns if dest.exists() else 0
    try:
        call("game_console",{"command":"mjolnir_auto "+command})
    except RuntimeError:
        if command=="state" or not dest.exists() or dest.stat().st_mtime_ns==old: raise
    def ack():
        if not dest.exists() or dest.stat().st_mtime_ns==old: return
        fields=dict(line.split("=",1) for line in dest.read_text(errors="replace").splitlines() if "=" in line)
        return fields if "signed_in" in fields else None
    return until(ack,5,"No lobby acknowledgement for "+command)


def scoped_jump(s):
    dll=(NATIVE/"mjolnir_lobby.dll").as_posix()
    code=f"""local control=assert(package.loadlib([[{dll}]], 'mjolnir_warfare_controls'))
    control(0,{s["unit"]},0,0,false,0,true)"""
    runlua(code)


def scoped_brake(s, seconds):
    """Hold the public flight action when the BLAM bridge does not feed UE key polling."""
    dll=(NATIVE/"mjolnir_lobby.dll").as_posix()
    code=f"""local c=assert(package.loadlib([[{dll}]], 'mjolnir_warfare_controls'))
    local yaw=mj.pc():GetControlRotation().Yaw
    local remaining={int(seconds*1000/18)}
    LoopAsync(18,function()
        remaining=remaining-1
        local held=remaining>0
        ExecuteInGameThread(function() c(0,{s["unit"]},0,held and 1 or 0,held,yaw,false) end)
        return not held
    end)"""
    runlua(code)


def edge(before, duration):
    gameplay([{"key":"space","hold":130}])
    time.sleep(.22)
    s=state()
    if s and s["stage"]==before:
        scoped_jump(s)
        event("scoped native action",stage=before)
    return until(lambda: state().get("stage",before)!=before, duration, "No stage change after jump/deploy")


def capture(name):
    shot(OUT/(name+".png"))
    event("frame",name=name,stage=state().get("stage"))


def match():
    # Normal title menu click handler, as used by tools/remote/remote.mjs.
    title='''local t=FindFirstOf("WBP_TitleMenu_C")
    if t and t:IsValid() then t:BndEvt__WBP_TitleMenu_WBP_MeteoriteStandaloneButtonDefault_K2Node_ComponentBoundEvent_1_CommonButtonBaseClicked__DelegateSignature(nil); print("started") end'''
    deadline=time.monotonic()+75
    while time.monotonic()<deadline:
        try:
            ready=auto("state")
            if ready.get("frontend")=="1" and ready.get("signed_in")=="1": break
        except RuntimeError: pass
        try: runlua(title)
        except RuntimeError: pass
        time.sleep(2)
    else: raise RuntimeError("Title menu sign-in did not complete")
    ready=auto("host PWR warfare private")
    assert ready.get("result")=="hosting PWR warfare private",ready.get("result")
    event("private host")
    s=until(lambda: (v if (v:=state()).get("stage")==2 else None),150,"No seated Spartan")
    event("seated", unit=s["unit"])
    capture("seated")
    edge(2,12)
    until(lambda: state().get("stage")==3,12,"No freefall")
    capture("freefall")
    time.sleep(.7)
    edge(3,10)
    until(lambda: state().get("stage")==4,10,"No canopy")
    time.sleep(.6)
    capture("glide")
    event("hold brake and turn")
    gameplay([{"key":"shift","down":True},{"key":"d","down":True}])
    try:
        time.sleep(.5)
        s=state()
        if s.get("stage")==4 and not s.get("brake"):
            scoped_brake(s,4)
            event("held native brake and steer via bridge")
        try: until(lambda:any(x.get("brake") for x in samples[-20:]), 3,"No native brake sample")
        except RuntimeError as exc: event("brake verification",result=str(exc))
        capture("brake")
        gameplay([{"mouse":"left","hold":110}])
        time.sleep(1.4)
    finally: gameplay([{"release":True}])
    event("released brake")
    capture("release")
    s=state()
    if s.get("stage")==4 and s.get("clearance",0)>165:
        gameplay([{"move":[0,-810]}])
        try: capture("canopy-overhead")
        finally: gameplay([{"move":[0,810]}])
    until(lambda: state().get("stage")==5,140,"No supported landing")
    time.sleep(.4)
    capture("touchdown")
    gameplay([{"mouse":"left","hold":90}])
    capture("ground-fire")
    event("confirmed grounded end",snapshot=state())


def main():
    env=dict(os.environ,PWR_FLIGHT_REHEARSAL="1")
    status=call("game_status",{})[0]["text"]
    assert "pid 63492" in status and "/Solo/PWR/PWR.PWR" in status and (RUN/"active-switch.json").exists(), "Previous session has changed"
    event("closing prior approved session")
    call("game_quit",{})
    until(lambda:not (RUN/"original-ue4ss").exists() and not (RUN/"active-switch.json").exists(),40,
          "Prior session restoration still pending")
    for action in (["refresh_shadow.py"],["switch.py","apply"]):
        subprocess.run([sys.executable,*action],cwd=RUN,env=env,check=True)
    try:
        event("launching through mjolnir-game")
        reply=call("game_launch",{"via":"steam","save_suffix":"PWRSteam1795051153335","width":1280,
            "height":720,"wait_seconds":100})
        assert "bridge answering" in reply[0]["text"],reply
        event("bridge answering")
        monitor=threading.Thread(target=sample,daemon=True)
        monitor.start()
        match()
    finally:
        stop.set()
        (OUT/"flight-telemetry.json").write_text(json.dumps({"events":events,"samples":samples},indent=2))
        call("game_quit",{})
        until(lambda:"process      not running" in call("game_status",{})[0]["text"] or
              not any("process      running," in x["text"] for x in call("game_status",{})),25,"Game still running")
        subprocess.run([sys.executable,"switch.py","restore"],cwd=RUN,env=env,check=True)


if __name__=="__main__": main()

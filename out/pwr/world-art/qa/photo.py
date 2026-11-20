"""Photograph the already-running private PWR session through the game's MCP bridge."""
import argparse
import base64
import json
import math
from pathlib import Path
import re
import statistics
import sys
import time

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "flight-review"))
from bridge import call, runlua
from rehearse import auto, STATE

LOG = STATE.parents[3] / "UE4SS.log"
POSES = {
    # UE centimetres, pitch, yaw and horizontal FOV. Fixed for repeatable comparisons.
    "touchdown": (-81794, 48613, 9250, 0, 90, 90),
    "aerial": (75000, -65000, 69000, -25, 132, 91),
    "valley": (-19000, 96000, 46500, -15, -80, 86),
    "ring": (-60700, 14400, 12600, 15, 126, 75),
    "b30-horizon": (-55000,30000,19800,10,172,92),
    "b30-beach-sky": (50000,7500,21500,12,-17,86),
    "shore": (22000, 65500, 10300, -13, 34, 74),
}

TITLE = '''local t=FindFirstOf("WBP_TitleMenu_C")
if t and t:IsValid() then
 t:BndEvt__WBP_TitleMenu_WBP_MeteoriteStandaloneButtonDefault_K2Node_ComponentBoundEvent_1_CommonButtonBaseClicked__DelegateSignature(nil)
end'''
PREP = '''
local p=mj.pc()
assert(p and p:IsValid() and p:GetWorld():GetFName():ToString()=="PWR","PWR world required")
if not PhotoQA or not PhotoQA.camera or not PhotoQA.camera:IsValid() then
  local v=p.Pawn
  pcall(function() local t=p:GetViewTarget(); if t and t:IsValid() then v=t end end)
  local cam=p:GetWorld():SpawnActor(StaticFindObject("/Script/Engine.CameraActor"),
       p.PlayerCameraManager:GetCameraLocation(),p.PlayerCameraManager:GetCameraRotation())
  assert(cam and cam:IsValid(),"Unable to spawn review camera")
  PhotoQA={camera=cam,pc=p,original=v,hidden={}}
  pcall(function() PhotoQA.hud=p.MyHUD; PhotoQA.showhud=PhotoQA.hud.bShowHUD end)
end
'''
HIDE = '''
pcall(function() if PhotoQA.hud:IsValid() then PhotoQA.hud.bShowHUD=false end end)
-- Only top-level HUD widgets in this private world; restore their exact initial visibility.
for _,w in ipairs(FindAllOf("UserWidget") or {}) do
 pcall(function()
  if w:IsValid() and w:IsInViewport() and w:GetWorld():GetAddress()==PhotoQA.pc:GetWorld():GetAddress() then
   local key=w:GetClass():GetFName():ToString()
   if key:find("WBP_HUD",1,true) or key=="UserWidget" then
    local id=w:GetAddress()
    if not PhotoQA.hidden[id] then PhotoQA.hidden[id]={w,w:GetVisibility()} end
    w:SetVisibility(1)
   end
  end
 end)
end
'''
RESTORE = '''
if PhotoQA then
 for _,entry in pairs(PhotoQA.hidden or {}) do
  pcall(function() if entry[1]:IsValid() then entry[1]:SetVisibility(entry[2]) end end)
 end
 pcall(function() if PhotoQA.showhud~=nil and PhotoQA.hud:IsValid() then PhotoQA.hud.bShowHUD=PhotoQA.showhud end end)
 local pc=PhotoQA.pc
 if pc and pc:IsValid() then
  local target=PhotoQA.original
  if not target or not target:IsValid() then target=pc.Pawn end
  if target and target:IsValid() then pc:SetViewTargetWithBlend(target,0,0,0,false) end
 end
 if PhotoQA.camera and PhotoQA.camera:IsValid() then PhotoQA.camera:K2_DestroyActor() end
 PhotoQA=nil
end
'''
PROBE = '''
local pc=mj.pc()
local mgr=pc.PlayerCameraManager
local at=mgr:GetCameraLocation()
local r=mgr:GetCameraRotation()
local u=StaticFindObject("/Script/UMG.Default__WidgetLayoutLibrary"):GetViewportSize(pc)
local gs=StaticFindObject("/Script/Engine.Default__GameplayStatics")
print(string.format("POSE %.2f %.2f %.2f %.4f %.4f %.4f %d %d %.5f %.5f",
 at.X,at.Y,at.Z,r.Pitch,r.Yaw,mgr:GetFOVAngle(),u.X,u.Y,
 gs:GetRealTimeSeconds(pc),gs:GetWorldDeltaSeconds(pc)))
'''

def get_lobby():
    try:
        return auto("state")
    except (OSError, RuntimeError):
        return {}

def private_world():
    deadline=time.monotonic()+120
    while time.monotonic()<deadline:
        info=get_lobby()
        if info.get("world")=="PWR" and info.get("frontend")=="0":
            if info.get("public")!="0":
                raise RuntimeError("An existing PWR session is public")
            return "existing"
        if info.get("frontend")=="1" or not info:
            if info.get("signed_in")=="1":
                ack=auto("host PWR warfare private")
                if ack.get("result")!="hosting PWR warfare private":
                    raise RuntimeError(str(ack.get("result")))
                break
            try: runlua(TITLE)
            except RuntimeError: pass
        elif info.get("frontend")=="0":
            raise RuntimeError("A different level is running: "+str(info.get("world")))
        time.sleep(1.5)
    else:
        raise RuntimeError("The main menu did not become ready")
    deadline=time.monotonic()+140
    while time.monotonic()<deadline:
        d=get_lobby()
        if d.get("world")=="PWR" and d.get("frontend")=="0" and d.get("public")=="0": return "hosted"
        time.sleep(2)
    raise RuntimeError("Private PWR world did not open")

def dressing():
    deadline=time.monotonic()+135
    while time.monotonic()<deadline:
        try:
            s=LOG.read_bytes()[-4_000_000:].decode(errors="replace")
            load=list(re.finditer(r"load timing on PWR: [^\r\n]*?from the world to dressed", s))
            flux=list(re.finditer(r"flux: 2 terrain-backed domain\(s\) ready", s))
            st=STATE.read_text(errors="replace")
            if load and flux and "ready 1\n" in st and "status 2\n" in st:
                return [load[-1].group(), flux[-1].group()]
        except OSError: pass
        time.sleep(1)
    raise RuntimeError("Missing PWR dressing completion, two ready Flux domains, or active native match")

def setpose(p,keep_hud):
    x,y,z,pitch,yaw,fov=p
    code=f'''local cam=PhotoQA.camera
    local loc={{X={x},Y={y},Z={z}}}
    local rot={{Pitch={pitch},Yaw={yaw},Roll=0}}
    cam.CameraComponent.bConstrainAspectRatio=false
    cam.CameraComponent.FieldOfView={fov}
    cam:K2_SetActorLocationAndRotation(loc,rot,false,{{}},true)
    PhotoQA.pc:SetViewTargetWithBlend(cam,0,0,0,false)
    pcall(function() PhotoQA.pc.PlayerCameraManager:SetGameCameraCutThisFrame() end)'''
    runlua(code if keep_hud else code+HIDE)

def probe():
    value=runlua(PROBE)
    line=next((l for l in value.splitlines() if l.startswith("POSE ")),None)
    if not line: raise RuntimeError("Camera measurement missing: "+value[:180])
    return list(map(float,line.split()[1:]))

def matches(actual,wanted):
    def angle(a,b): return abs((a-b+180)%360-180)
    return math.dist(actual[:3],wanted[:3])<5 and angle(actual[3],wanted[3])<.5 and angle(actual[4],wanted[4])<.5 and abs(actual[5]-wanted[5])<1

def capture(out,name,p,keep_hud):
    for attempt in range(3):
        setpose(p,keep_hud)
        time.sleep(2.2+attempt)
        before=probe()
        if not matches(before,p): continue
        blocks=call("game_screenshot",{"background_only":True,"max_width":2400})
        meta=next(b["text"] for b in blocks if b["type"]=="text")
        if "PrintWindow" not in meta or "blank" in meta.lower():
            raise RuntimeError("Game returned unsuitable background frame: "+meta)
        payload=base64.b64decode(next(b["data"] for b in blocks if b["type"]=="image"))
        after=probe()
        if not matches(after,p) or after[8]<=before[8]: continue
        dest=out/(name+".png")
        dest.write_bytes(payload)
        with Image.open(dest) as im:
            pixels=list(im.convert("L").resize((30,17)).getdata())
            extent=im.size
        if statistics.pstdev(pixels)<2:
            raise RuntimeError("Nearly uniform screenshot: "+name)
        return {"requested":p,"camera_before":before,"camera_after":after,
                "viewport":list(map(int,before[6:8])),"image_size":extent,"capture":meta,"file":dest.name}
    raise RuntimeError(f"Camera {name} did not hold; last measurement {before}")

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,help="New or empty directory for the frames")
    parser.add_argument("--only",nargs="+",choices=POSES,default=list(POSES))
    parser.add_argument("--keep-hud",action="store_true")
    parser.add_argument("--restore-camera",action="store_true",help="Restore any camera left by an interrupted review and exit")
    args=parser.parse_args()
    if args.restore_camera:
        runlua(RESTORE);return
    out=(args.out or HERE/time.strftime("frames-%Y%m%d-%H%M%S")).resolve()
    out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()): raise RuntimeError("Output directory must be empty")
    def save(): (out/"frames.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    result={"mcp":"mjolnir-game","world":"PWR","foreground":False,"pose_fields":
        ["x_cm","y_cm","z_cm","pitch_deg","yaw_deg","horizontal_fov_deg","viewport_x","viewport_y","real_seconds","world_frame_seconds"],"frames":{}}
    result["private_match"]=private_world()
    result["level_ready"]=dressing()
    print("PWR is dressed and both Fluid Flux domains are ready.",flush=True)
    save()
    try:
        runlua(PREP)
        for name in args.only:
            result["frames"][name]=capture(out,name,POSES[name],args.keep_hud)
            save();print(name,out/(name+".png"),flush=True)
            if name=="touchdown":
                from cover_timing import observe
                try: observe(out,name,HERE.parent/"foliage-r2")
                except Exception as error:
                    result["cover_observation_error"]=str(error)
                    save()
    finally:
        runlua(RESTORE)
        result["camera_restored"]=True;save()

if __name__=="__main__":
    main()

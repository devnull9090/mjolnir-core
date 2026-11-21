from pathlib import Path
import json, os, sys, time, argparse, tempfile, hashlib
from contextlib import contextmanager
from unittest.mock import patch
from PIL import Image
import numpy as np
QA=Path(__file__).resolve().parent
BENCH=QA.parents[1]/"alpine-target/bench"
sys.path.insert(0,str(BENCH))
import benchmark as b
import validate_candidate as v
SITE="southwest-forest-road-driver"
BASE=BENCH/"candidate-14"
BASEMAP=BENCH.parent/"saturday.14"

@contextmanager
def preferences(folder):
    path=Path(os.environ["LOCALAPPDATA"])/"Meteorite"/("Saved_"+b.PROFILE)/"Config/Windows/GameUserSettings.ini"
    original=path.read_bytes() if path.exists() else None
    try: yield
    finally:
        if (folder/"steam/restored.json").is_file():
            b.check(b.read(folder/"steam/restored.json")["restored"],"Steam restore incomplete")
            current=path.read_bytes() if path.exists() else None
            if current!=original:
                if original is None: path.unlink()
                else:
                    with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as f:
                        f.write(original)
                        temp=Path(f.name)
                    temp.replace(path)
            b.check((path.read_bytes() if path.exists() else None)==original,"Display preferences restoration failed")
            b.write(folder/"visual-profile-restored.json",dict(path=str(path),original_sha256=hashlib.sha256(original).hexdigest() if original else None,byte_verified=True))

INIT="""
assert(not PWRSweepLights)
local world=mj.pc():GetWorld()
local id=world:GetAddress()
local function find(cls, match)
 local list={}
 for _,a in ipairs(FindAllOf(cls) or {}) do
  if a:IsValid() and a:GetWorld():IsValid() and a:GetWorld():GetAddress()==id then
   local c=a.LightComponent
   print("ACTOR "..a:GetFullName().." "..c:GetFullName().." "..tostring(c.Intensity))
   if math.abs(c.Intensity-match)<.15 then list[#list+1]=a end
  end
 end
 assert(#list==1,"Expected exactly one deployed "..cls.." at "..tostring(match)..", got "..#list)
 return list[1]
end
local sky=find("SkyLight",3)
local sun=find("DirectionalLight",32768)
local r=sun:K2_GetActorRotation()
PWRSweepLights={sky=sky,sun=sun,skyvalue=sky.LightComponent.Intensity,angle=sun.LightComponent.LightSourceAngle,cast=sun.LightComponent.CastShadows,rot={Pitch=r.Pitch,Yaw=r.Yaw,Roll=r.Roll}}
print("LIGHTS_READY "..r.Pitch.." "..r.Yaw)
"""
CLEAR_POINT="""local s=assert(PWRSweepLights)
if s.points then for _,a in ipairs(s.points) do if a:IsValid() then a:K2_DestroyActor() end end;s.points=nil end
"""
RESTORE=CLEAR_POINT+"""
s.sky.LightComponent:SetIntensity(s.skyvalue)
s.sun.LightComponent:SetLightSourceAngle(s.angle)
s.sun.LightComponent:SetCastShadows(s.cast)
s.sun:K2_SetActorRotation(s.rot,false)
if s.baked then s.baked:SetIntensity(s.savedintensity);s.baked:SetLightColor(s.savedcolour,true) end
s.sky.LightComponent:RecaptureSky()
PWRSweepLights=nil; print("RESTORED")
"""
def variant(photo, part):
    sky, pitch, yaw=map(float,part['sky_sun'])
    code=CLEAR_POINT+f"""
s.sky.LightComponent:SetIntensity({sky});s.sun:K2_SetActorRotation({{Pitch={pitch},Yaw={yaw},Roll=0}},false)
s.sky.LightComponent:RecaptureSky()
local r=s.sun:K2_GetActorRotation()
print("LIGHT "..s.sky.LightComponent.Intensity.." "..r.Pitch.." "..r.Yaw)
"""
    if "source_angle" in part:
        angle=float(part["source_angle"])
        code+=f"""
s.sun.LightComponent:SetLightSourceAngle({angle})
print("SUN_ANGLE "..s.sun.LightComponent.LightSourceAngle.." "..s.sun.LightComponent:GetFullName())
"""
    if "sun_shadows" in part:
        cast = str(bool(part["sun_shadows"])).lower()
        code += f"""
s.sun.LightComponent:SetCastShadows({cast})
print("SUN_CAST "..tostring(s.sun.LightComponent.CastShadows))
"""
    if "baked_fill" in part:
        intensity, red, green, blue=map(float,part["baked_fill"])
        code+=f"""
if not s.baked then
 local id=mj.pc():GetWorld():GetAddress()
 for _,a in ipairs(FindAllOf("PointLight") or {{}}) do
  if a:IsValid() and a:GetWorld():IsValid() and a:GetWorld():GetAddress()==id and a:GetFName():ToString()=="PWR_SweepCanopyFill1" then
   local c=a.LightComponent;local col=c:GetLightColor()
   s.baked=c;s.savedintensity=c.Intensity;s.savedcolour={{R=col.R,G=col.G,B=col.B,A=1}}
  end
 end
end
local c=assert(s.baked,"Unable to find baked local fill")
c:SetIntensity({intensity});c:SetLightColor({{R={red},G={green},B={blue},A=1}},true)
local col=c.LightColor
print("BAKED_FILL "..c.Intensity.." "..col.R.." "..col.G.." "..col.B.." "..c:GetFullName())
"""
    for point in part.get('points',[]):
        x,y,z,rad,intensity,*colour=point
        code+=f"""
do
local a=mj.pc():GetWorld():SpawnActor(StaticFindObject("/Script/Engine.PointLight"),{{X={x},Y={y},Z={z}}},{{Pitch=0,Yaw=0,Roll=0}})
assert(a and a:IsValid(),"point light could not be spawned")
s.points=s.points or {{}};s.points[#s.points+1]=a
local c=a.LightComponent;c.Mobility=2;c.bUseInverseSquaredFalloff=false;c.LightFalloffExponent=1.1;c.IntensityUnits=0;c.SpecularScale=0
c:SetIntensity({intensity});c:SetAttenuationRadius({rad});c:SetLightColor({{R={colour[0]},G={colour[1]},B={colour[2]},A=1}},true)
c:SetLightingChannels(true,true,false);c:SetCastShadows(false)
local p=a:K2_GetActorLocation()
print("POINT "..c.Intensity.." "..c.AttenuationRadius.." "..tostring(c.CastShadows).." "..p.X.." "..p.Y.." "..p.Z)
end
"""
    output=b.run_lua(photo,code)
    if "sun_shadows" in part:
        b.check("SUN_CAST "+cast in output, "Native directional shadow diagnostic did not apply")
    if "baked_fill" in part:
        fields=next(line.split() for line in output.splitlines() if line.startswith("BAKED_FILL "))
        b.check(abs(float(fields[1])-intensity)<.01 and fields[4]=='255', "Baked fill did not apply")
    measured=next(l for l in output.splitlines() if l.startswith('LIGHT ')).split()[1:]
    b.check(all(abs(float(a)-wanted)<.02 for a,wanted in zip(measured,(sky,pitch,yaw))),"Light settings did not apply")
    b.check(sum(x.startswith('POINT ') for x in output.splitlines())==len(part.get('points',[])),output)
    if 'source_angle' in part:
        measured_angle=next(l for l in output.splitlines() if l.startswith('SUN_ANGLE ')).split()[1]
        b.check(abs(float(measured_angle)-float(part['source_angle']))<.001,'Native light source angle did not apply')
    return output

def light_trial(args):
    folder=BENCH/args.label
    base=b.read(BASE/"benchmark.json")
    def shoot(folder,identity,pid,photo,native_dir):
        photo.runlua=lambda code:b.run_lua(photo,code)
        photo.private_world()
        photo.dressing()
        settings=b.checked_settings(photo)
        b.check(settings==base["settings"],"Mismatch to .14 graphics settings")
        pose=b.cameras()[SITE]
        out=folder/"photos"
        out.mkdir()
        report={"release":identity,"pose":pose,"settings":settings,"captures":{}}
        b.write(folder/"benchmark.json",{"kind":"art trial, no timing","release":identity})
        try:
            b.run_lua(photo,photo.PREP+photo.HIDE)
            photo.setpose(pose,True)
            time.sleep(4)
            report["initial_lights"]=b.run_lua(photo,INIT)
            b.check("LIGHTS_READY" in report["initial_lights"], report["initial_lights"])
            while True:
                plan=b.read(args.plan)
                pending=[(name,spec) for name,spec in plan['variants'].items() if name not in report['captures']]
                for name,spec in pending:
                    import re
                    b.check(re.fullmatch(r'[a-z0-9_-]+',name),"Unsafe variant name")
                    effective=variant(photo,spec)
                    frame=v.take_image(photo,out,name,pose)
                    b.check(frame['native_viewport']==[3840,2160],"Reference viewport differs")
                    image=np.asarray(Image.open(frame['file']).convert('L'))
                    roi=image[565:854,100:1510]
                    report['captures'][name]=dict(frame=frame,settings_readback=effective,parameters=spec,road_luma_quantiles=list(map(float,np.percentile(roi,[10,25,50,75,90]))))
                    b.write(folder/"lights.json",report)
                    print(f"LIGHT_CAPTURE {name} {effective}",flush=True)
                if plan.get('close'):break
                time.sleep(1)
        finally:
            if "LIGHTS_READY" in report.get("initial_lights",""): report["scene_restored"]=b.run_lua(photo,RESTORE)
            b.run_lua(photo,photo.RESTORE)
        b.write(folder/"lights.json",report)
    with preferences(folder),patch.object(b,"measure",shoot):
        b.run_release(args.release,args.label)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--label",required=True)
    parser.add_argument("--release",type=Path,default=BASEMAP)
    parser.add_argument("--plan",type=Path,default=QA/"light-plan.json")
    light_trial(parser.parse_args())



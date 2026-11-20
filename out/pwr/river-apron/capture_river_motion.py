"""Record a real-time, game-rendered second view at the registered outlet camera."""
import json
import base64
import io
import re
import subprocess
import time

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw


START = """
assert(not PWRWaterCapture, 'Existing water capture')
local p=mj.pc()
local world=p:GetWorld()
assert(world:GetFName():ToString()=='PWR')
local render=StaticFindObject('/Script/Engine.Default__KismetRenderingLibrary')
local gs=StaticFindObject('/Script/Engine.Default__GameplayStatics')
local pcm=p.PlayerCameraManager
local s={render=render,world=world,times={},address=p:GetAddress(),path=__PATH__,
         start=gs:GetRealTimeSeconds(world),func='/Game/Blueprints/BP_MeteoritePlayerController.BP_MeteoritePlayerController_C:ReceiveTick'}
PWRWaterCapture=s
local ok,err=pcall(function()
    s.actor=world:SpawnActor(StaticFindObject('/Script/Engine.SceneCapture2D'),pcm:GetCameraLocation(),pcm:GetCameraRotation())
    assert(s.actor and s.actor:IsValid(),'Cannot create secondary view')
    local c=s.actor.CaptureComponent2D
    assert(c and c:IsValid(),'Missing scene capture component')
    s.component=c
    c.bCaptureEveryFrame=false
    c.bCaptureOnMovement=false
    c.bAlwaysPersistRenderingState=true
    c.FOVAngle=pcm:GetFOVAngle()
    c.CaptureSource=2 -- ESceneCaptureSource::SCS_FinalColorLDR
    s.rt=render:CreateRenderTarget2D(world,960,540,3,{R=0,G=0,B=0,A=1},false,false)
    assert(s.rt and s.rt:IsValid(),'Cannot allocate LDR target')
    c.TextureTarget=s.rt
    c:CaptureScene()
    s.pre,s.post=RegisterHook(s.func,function(context)
        if context:get():GetAddress()~=s.address or s.error or #s.times>=32 then return end
        local t=gs:GetRealTimeSeconds(world)
        if t-s.start<1.2 then
            if not s.lastWarm or t-s.lastWarm>=.095 then
                local warmed,msg=pcall(function() c:CaptureScene() end)
                if not warmed then s.error=tostring(msg) end
                s.lastWarm=t
            end
            return
        end
        if #s.times>0 and t-s.times[#s.times]<.095 then return end
        local drawn,msg=pcall(function()
            c:CaptureScene()
            render:ExportRenderTarget(world,s.rt,s.path,string.format('capture-%03d.png',#s.times+1))
            s.times[#s.times+1]=t
        end)
        if not drawn then s.error=tostring(msg) end
    end)
end)
assert(ok,tostring(err))
print('RIVER_CAMERA_LIVE')
"""

STOP = """
local s=PWRWaterCapture
if s then
    local errors={}
    local function clear(fn)
        local ok,err=pcall(fn)
        if not ok then errors[#errors+1]=tostring(err) end
    end
    clear(function() if s.pre then UnregisterHook(s.func,s.pre,s.post) end end)
    clear(function() if s.actor and s.actor:IsValid() then s.actor:K2_DestroyActor() end end)
    clear(function() if s.rt and s.rt:IsValid() then s.render:ReleaseRenderTarget2D(s.rt) end end)
    PWRWaterCapture=nil
    assert(#errors==0,table.concat(errors,' / '))
end
print('RIVER_CAMERA_REMOVED')
"""


def inspect_frames(paths, reference, motion_check=None):
    thumbs = []
    for path in paths:
        with Image.open(path) as frame:
            if frame.format != "PNG" or frame.size != (960,540):
                raise ValueError("Secondary capture did not return a native 960x540 PNG")
            thumbs.append(np.asarray(frame.convert("L").resize((160,90)),dtype=float))
    with Image.open(reference) as image:
        registered = np.asarray(image.convert("L").resize((160,90)),dtype=float)
    first = thumbs[0]
    correlation = np.corrcoef(registered.ravel(), first.ravel())[0,1]
    # Dependent shading may differ between the player's view and a scene capture.
    # Use geometry across the mountains, boulders and shoreline for registration.
    stats = np.mean([np.mean(np.abs(a[64:88]-b[64:88])) for a,b in zip(thumbs,thumbs[1:])])
    if not np.isfinite(correlation) or correlation < .62 or first.std() < 7 or (motion_check is None and stats < .20):
        raise ValueError(f"Camera match or detectable water movement failed: correlation={correlation:.3f}, difference={stats:.3f}")
    if motion_check:
        actual=motion_check()
        if actual["median_cascade_delta"] < max(1., 1.3*actual["median_surround_delta"]):
            raise ValueError("No localized motion detected against the spring rocks: "+str(actual))
        return dict(registered_image_correlation=float(correlation),cascade_motion=actual)
    return dict(registered_image_correlation=float(correlation), mean_water_band_frame_difference=float(stats))


def capture(photo, b, pose, output):
    folder=output/"motion"
    folder.mkdir()
    try:
        capture_secondary(photo,b,pose,output,folder)
    except (RuntimeError,ValueError,OSError) as err:
        (folder/"secondary-capture.log").write_text(str(err),encoding="utf8")
        cleanup=folder/"cleanup.log"
        if not cleanup.is_file() or "RIVER_CAMERA_REMOVED" not in cleanup.read_text():
            raise
        sample_game_frames(photo,b,pose,output,folder)


def sample_game_frames(photo,b,pose,output,folder):
    """Preserve sparse real game-window samples as a labelled strip if the renderer declines."""
    photo.setpose(pose,True)
    time.sleep(1)
    b.prove_pose(photo,pose)
    strip=Image.new("RGB",(960,592),(18,22,21))
    draw=ImageDraw.Draw(strip)
    samples=[]
    start=time.monotonic()
    for i in range(4):
        opened=time.monotonic()-start
        rows=photo.call("game_screenshot",{"background_only":True,"max_width":960})
        closed=time.monotonic()-start
        metadata=" ".join(block["text"] for block in rows if block["type"]=="text")
        b.check("PrintWindow" in metadata and "blank" not in metadata.lower(),"Missing actual background-only game frame")
        encoded=next(block["data"] for block in rows if block["type"]=="image")
        data=base64.b64decode(encoded)
        with Image.open(io.BytesIO(data)) as image:
            b.check(image.size==(960,540),"Background game frame has unexpected dimensions")
            frame=image.convert("RGB").resize((480,270),Image.Resampling.LANCZOS)
        target=folder/f"background-{i+1:02d}.png"
        target.write_bytes(data)
        x,y=480*(i%2),296*(i//2)
        strip.paste(frame,(x,y))
        draw.text((x+6,y+276),f"Game sample {i+1}   |   capture window {opened:.1f} to {closed:.1f} s",fill="white")
        samples.append(dict(capture_started=opened,capture_finished=closed,file=target.name,sha256=b.sha(target)))
    b.prove_pose(photo,pose)
    b.check(len({s["sha256"] for s in samples})>1, "No distinct background frames")
    strip.save(output/"water-sampled-sequence.jpg",quality=92,subsampling=0)
    b.write(folder/"sparse-samples.json",dict(method="Four timestamped background-only game window captures",
            time_basis="Host monotonic time bracketing each MCP request",camera=pose,samples=samples))


def capture_secondary(photo, b, pose, output, folder, reference="riffle", video_name="outlet-in-motion.mp4", motion_check=None):
    photo.setpose(pose,True)
    time.sleep(2)
    b.prove_pose(photo,pose)
    code=START.replace("__PATH__",json.dumps(folder.resolve().as_posix()))
    times=[]
    try:
        response=b.run_lua(photo,code)
        b.check("RIVER_CAMERA_LIVE" in response,"Secondary camera failed: "+response[-380:])
        deadline=time.monotonic()+15
        while time.monotonic()<deadline and not (folder/"capture-032.png").is_file():
            time.sleep(.30)
        status=b.run_lua(photo,"local s=assert(PWRWaterCapture); print('RIVER_CAPTURE_ERROR '..tostring(s.error)); for i,t in ipairs(s.times) do print(string.format('RIVER_FRAME %d %.6f',i,t)) end")
        (folder/"frames.log").write_text(status,encoding="utf8")
        rows=re.findall(r"RIVER_FRAME (\d+) ([\d.]+)",status)
        times=[float(t) for _,t in rows]
        b.check("RIVER_CAPTURE_ERROR nil" in status and [int(i) for i,_ in rows]==list(range(1,33)),
                "Missing scene-capture frames or timestamps")
    finally:
        removed=b.run_lua(photo,STOP)
        (folder/"cleanup.log").write_text(removed,encoding="utf8")
        b.check("RIVER_CAMERA_REMOVED" in removed, "Secondary camera cleanup failed: "+removed[-400:])
    b.prove_pose(photo,pose)
    paths=[folder/f"capture-{i:03d}.png" for i in range(1,33)]
    b.check(all(p.is_file() and p.stat().st_size>15000 for p in paths), "Incomplete scene-capture PNG sequence")
    steps=np.diff(times)
    b.check(np.min(steps)>0 and np.max(steps)<1 and 2.9<times[-1]-times[0]<10, "Invalid real capture intervals")
    checks=inspect_frames(paths,output/(reference+".png"),motion_check)
    concat=["ffconcat version 1.0"]
    for i,path in enumerate(paths):
        concat.extend([f"file '{path.name}'","option framerate 1000"])
        if i<len(steps):
            concat.append(f"duration {steps[i]:.6f}")
    (folder/"frames.ffconcat").write_text("\n".join(concat)+"\n",encoding="ascii")
    video=output/video_name
    cmd=[imageio_ffmpeg.get_ffmpeg_exe(),"-hide_banner","-loglevel","error","-f","concat","-safe","0",
         "-i","frames.ffconcat","-an","-c:v","libx264","-pix_fmt","yuv420p","-crf","18",
         "-fps_mode","vfr","-enc_time_base","1:1000","-video_track_timescale","1000","-movflags","+faststart",
         "-n",str(video.resolve())]
    proc=subprocess.run(cmd,cwd=folder,capture_output=True,text=True)
    b.check(proc.returncode==0 and video.is_file(),"Encoding scene-capture video failed: "+proc.stderr[-380:])
    b.write(folder/"motion.json",dict(method="Temporary Unreal SceneCapture2D from registered "+reference+" lens",
            colour_source="FinalColorLDR, 960x540 sRGB",camera=pose,frames=len(paths),
            world_seconds=times,source_fps=len(steps)/(times[-1]-times[0]),duration_seconds=times[-1]-times[0],
            cleanup_verified=True,encoding="Variable frame rate using the game clock; one real image per frame",
            source_sha256=[b.sha(p) for p in paths],video_sha256=b.sha(video),**checks))

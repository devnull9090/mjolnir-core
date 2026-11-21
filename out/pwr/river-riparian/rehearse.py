"""Capture both banks and the spring from registered Halo bridge viewpoints."""
import argparse
import importlib.util
from pathlib import Path
import time
import sys
from unittest.mock import patch

WORK = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("apron_rehearsal", WORK.parent/"river-apron/rehearse.py")
apron = importlib.util.module_from_spec(spec)
spec.loader.exec_module(apron)
previous, b, v = apron.previous, apron.b, apron.v
reference = previous.BENCH/"river-shore-39/water/photos.json"

def run(folder, identity, pid, photo, native):
    photo.runlua = lambda code: b.run_lua(photo, code)
    photo.private_world()
    lobby = photo.get_lobby()
    b.check(lobby.get("world")=="PWR" and lobby.get("players")=="1" and lobby.get("public")=="0", "Private lake rehearsal required")
    photo.dressing()
    baseline = b.read(reference)
    settings = b.checked_settings(photo)
    b.check(settings == baseline["settings"], "Different graphics profile")
    cameras = {k:baseline["views"][k] for k in ("outlet","riffle","waterline","basin","spring-bank")}
    cameras["cutbank"] = previous.pose((-296.5,815.6,144.6), (-310.2,810.15,143.3), 71)
    cameras["inlet"] = previous.pose((-375,951,144.9),(-394.6,970.2,145.4),65)
    output = folder/"water"
    output.mkdir()
    frames = {}
    failures = {}
    def photograph(name, camera):
        photo.setpose(camera, True)
        time.sleep(3.2)
        frames[name] = v.take_image(photo, output, name, camera)
    try:
        b.run_lua(photo, photo.PREP+photo.HIDE)
        for name, camera in cameras.items():
            photograph(name, camera)
        b.write(output/"photos.json",dict(release=identity,settings=settings,views=cameras,frames=frames))
        if not identity["archive"].endswith(".39.mjolnir"):
            for path in sorted(WORK.glob("*/*readback.lua")):
                raw = b.run_lua(photo, path.read_text(encoding="utf-8-sig"))
                (output/(path.parent.name+"-"+path.stem+".log")).write_text(raw)
                if "PASS" not in raw or "stack traceback:" in raw:
                    failures[path.name]=raw[-1200:]
            photograph("inlet-motion", cameras["inlet"])
        if not args.no_timing:
            apron.sample_outlet(photo,cameras["outlet"],native,output)
        if not identity["archive"].endswith(".39.mjolnir"):
            sys.path.insert(0,str(WORK.parent/"river-apron"))
            from capture_river_motion import capture_secondary
            from measure_cascade_motion import measure
            motion = output/"motion"
            motion.mkdir()
            photo.setpose(cameras["inlet"], True)
            time.sleep(2)
            try:
                capture_secondary(photo,b,cameras["inlet"],output,motion,reference="inlet",video_name="inlet.mp4",
                                  motion_check=lambda: measure(WORK,output))
            except (ValueError,RuntimeError,OSError) as err:
                failures["cascade film"]=str(err)
    finally:
        b.run_lua(photo,photo.RESTORE)
    b.write(output/"photos.json",dict(release=identity,settings=settings,views=cameras,frames=frames))
    b.write(output/"verification.json",dict(failures=failures))
    b.write(folder/"benchmark.json",dict(completed=True,release=identity,settings=settings,frames=frames))

if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("release",type=Path)
    parser.add_argument("label")
    parser.add_argument("--no-timing",action="store_true")
    args=parser.parse_args()
    with previous.preferences(previous.BENCH/args.label), patch.object(b,"measure",run):
        b.run_release(args.release,args.label)

"""Verify two bridge runs and assemble full-frame review images."""
import argparse
import importlib.util
import json
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import numpy as np

WORK=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("apron_review",WORK.parent/"river-apron/review.py")
review=importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)
b=review.b

def read_view(folder):
    for marker,key in (("steam/restored.json","restored"),("visual-profile-restored.json","byte_verified")):
        b.check(b.read(folder/marker)[key], "Rehearsal restore missing "+marker)
    data=b.read(folder/"water/photos.json")
    for name,frame in data["frames"].items():
        b.check(b.sha(frame["file"])==frame["sha256"],"Frame changed: "+name)
    return data

def details(output,before,after):
    panel=Image.new("RGB",(1630,825),(22,26,26))
    draw=ImageDraw.Draw(panel)
    title=ImageFont.truetype("C:/Windows/Fonts/seguisb.ttf",28)
    minor=ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf",20)
    for col,(record,label) in enumerate(((before,"Before"),(after,"After"))):
        x=10+815*col
        version=record["release"]["archive"].removesuffix(".mjolnir").split(".")[-1]
        draw.text((x,6),label+"   ."+version,font=title,fill=(233,237,228))
        for i,(name,description,box) in enumerate((
            ("cutbank","Left bank at water height",(45,415,875,745)),
            ("inlet","Spring feeding the lake",(270,258,1326,678)))):
            y=56+383*i
            draw.text((x,y),description,font=minor,fill=(193,204,195))
            with Image.open(record["frames"][name]["file"]) as capture:
                panel.paste(capture.convert("RGB").crop(box).resize((800,318),Image.Resampling.LANCZOS),(x,y+32))
    panel.save(output,quality=94,subsampling=0)

def compare(release,label):
    destination=WORK/("review-"+label)
    destination.mkdir(exist_ok=True)
    control=review.BENCH/"riparian-control-39"
    live=review.BENCH/label
    before,after=read_view(control),read_view(live)
    sealed=b.read(release/"receipt.json")
    b.check(b.sha(release/sealed["archive"])==after["release"]["map_sha256"]==sealed["sha256"] and
            before["release"]["map_sha256"]==sealed["baseline_sha256"], "Game photos do not match releases")
    b.check(before["settings"]==after["settings"],"Graphics settings differ")
    original=b.read(review.BENCH/"river-shore-39/water/photos.json")
    b.check(original["release"]==before["release"] and original["settings"]==before["settings"] and
            original["frames"]["outlet"]["camera_before"][:8]==before["frames"]["outlet"]["camera_before"][:8]
            and b.sha(original["frames"]["outlet"]["file"])==original["frames"]["outlet"]["sha256"],
            "Original .39 outlet capture does not match the rehearsal")
    for name,title in (("outlet","Lake outlet"),("cutbank","Left cutbank"),("inlet","Spring cascade"),("riffle","Waterline"),("basin","Lake and headwater")):
        b.check(before["views"][name]==after["views"][name],"Camera moved")
        for row in (before,after):
            frame=row["frames"][name]
            b.check(frame["camera_before"][:8]==frame["camera_after"][:8],"Camera moved in screenshot")
        b.check(before["frames"][name]["camera_before"][:8]==after["frames"][name]["camera_before"][:8],"Camera or viewport mismatch")
        review.sheet(destination/(name+".jpg"),original if name=="outlet" else before,after,name,title)
    perf=[b.read(path/"water/native-performance.json") for path in (control,live)]
    b.check(perf[0]["camera"]==perf[1]["camera"] and perf[0]["module_sha256"]==perf[1]["module_sha256"] and
            perf[0]["settings"]==perf[1]["settings"],"Benchmark camera, settings or instrumentation differ")
    b.write(destination/"results.json",dict(before=before["release"],after=after["release"],
           camera=after["views"]["outlet"],graphics=after["settings"],performance=[x["aggregate"] for x in perf],
           restoration=[b.read(f/"steam/restored.json") for f in (control,live)]))
    details(destination/"bank-and-spring.jpg",before,after)
    print(destination)
if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("release",type=Path)
    parser.add_argument("label")
    a=parser.parse_args()
    compare(a.release,a.label)

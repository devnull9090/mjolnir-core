"""Read the shipped chute geometry and print pixels back from the cooked chunk."""
import hashlib
import json
import math
import struct
import subprocess
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

SOURCE = Path(__file__).resolve().parent
ROOT = SOURCE.parents[4]
COOK = ROOT / "out/pwr/canopy-v2"
AUDIT = COOK / "readback"


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def textile_vertices(path):
    data = path.read_bytes()
    size = struct.unpack_from("<I", data, 12)[0]
    document = json.loads(data[20:20+size])
    binary = memoryview(data)[28+size:]
    def read(index):
        a = document["accessors"][index]
        view = document["bufferViews"][a["bufferView"]]
        fmt = {5123:"H",5125:"I",5126:"f"}[a["componentType"]]
        width = {"SCALAR":1,"VEC2":2,"VEC3":3}[a["type"]]
        record = struct.Struct("<" + fmt*width)
        start = a.get("byteOffset",0) + view.get("byteOffset",0)
        stride = view.get("byteStride",record.size)
        return [record.unpack_from(binary,start+i*stride) for i in range(a["count"])]
    textile, = [p for p in document["meshes"][0]["primitives"]
                if document["materials"][p["material"]]["name"] == "GripTextile"]
    points = read(textile["attributes"]["POSITION"])
    uvs = read(textile["attributes"]["TEXCOORD_0"])
    return [(points[i],uvs[i]) for i in {row[0] for row in read(textile["indices"])}]


def check_geometry(is_pack, sockets):
    name = "SM_PWR_ParachutePackV2" if is_pack else "SM_PWR_ParachuteV2"
    vertices = textile_vertices(AUDIT / (name+".glb"))
    printed = [(p,uv) for p,uv in vertices if uv[0] >= .5]
    assert printed
    errors = []
    for (forward,up,right), uv in printed:
        if is_pack:
            assert -.18<forward<-.14 and .1619<=up<=.2151 and abs(right)<.0531
            u=(.053-right)/.106
            v=(.5+255*(.215-up)/.053)/512
        else:
            assert up>4.6 and abs(right)<=.401
            u=(right+.8)/1.6
            t=abs(right)/2.8
            chord=2.08-.38*t*t-.26*t**9
            depth=(((-forward-.28*t*t)/chord+.48)-.105)/.895
            v=1-(.5+255*(21-32*depth)/14)/512
        errors.append(math.dist(uv,((512.5+511*u)/1024,v)))
    assert max(errors)<.001,(name,max(errors))
    result={"print_vertices":len(printed),"max_uv_error":max(errors)}
    if not is_pack:
        centers={}
        for key,(f,r,h) in sockets.items():
            expected=(f/100,h/100,r/100)
            ring={p for p,_ in vertices if abs(p[2]-expected[2])<.00001
                  and abs(p[0]-expected[0])<.018 and abs(p[1]-expected[1])<.014}
            assert len(ring)==16,(key,len(ring))
            center=[sum(p[k] for p in ring)/16 for k in range(3)]
            distance=100*math.dist(expected,center)
            assert distance<.001,(key,distance)
            centers[key]={"bar_ue_cm":[100*center[0],100*center[2],100*center[1]],"error_cm":distance}
        result["cooked_grips"]=centers
    return result


def main():
    receipt=COOK/"cooked/receipt.json"
    cooked=json.loads(receipt.read_text())
    for name,sha in cooked["files_sha256"].items():
        assert digest(AUDIT/name)==digest(receipt.parent/name)==sha
    atlas_path=AUDIT/"cooked-grip-atlas.png"
    cli=ROOT/"out/pwr/toolchain-mesh-attrs-v2/mjolnir.exe"
    subprocess.run([str(cli),"texture","export","--paks",str(AUDIT),"--asset","T_PWR_GripTextile",
                    "--out",str(atlas_path)],check=True)
    with Image.open(atlas_path) as image:
        atlas=image.convert("RGBA")
    assert atlas.size==(1024,512)
    pixels={}
    for name,y in (("pack-label",0),("canopy-mark",256)):
        actual=atlas.crop((512,y,1024,y+256))
        source=Image.open(SOURCE/"print"/(name+".tga")).convert("RGB")
        mask=None
        if name=="canopy-mark":
            mask=Image.open(SOURCE/"print/canopy-ink-mask.tga").convert("L")
            expected=mask.point(lambda a: round(.86*a))
            alpha_error=ImageStat.Stat(ImageChops.difference(actual.getchannel("A"),expected)).mean[0]
            assert alpha_error<2 and actual.getpixel((0,0))[3]==0,alpha_error
        means=ImageStat.Stat(ImageChops.difference(actual.convert("RGB"),source),mask).mean
        assert max(means)<6,(name,means)
        pixels[name]={"mean_rgb_error_8bit":means}
        if mask is not None:
            pixels[name]["mean_ink_mask_error_8bit"]=alpha_error
    points=cooked["meshes"][0]["grip_sockets_ue_cm"]
    result={"cook_receipt_sha256":digest(receipt),"printed_pixels":pixels,
            "canopy":check_geometry(False,points),"pack":check_geometry(True,points)}
    (AUDIT/"grip-and-brand-readback.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()

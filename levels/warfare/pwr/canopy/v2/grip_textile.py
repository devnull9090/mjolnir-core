"""Close-view PWR textile swatches. U selects a swatch, V wraps in 32 mm."""
import math
import struct
from pathlib import Path

SIZE = 512
TILE_NAMES = ("T_PWR_GripTextile", "T_PWR_GripNormal")

def write_textures(folder):
    width = SIZE // 4
    color, normal = bytearray(), bytearray()
    prints = []
    for name in ("canopy-mark","pack-label"):
        data=(Path(folder)/"print"/(name+".tga")).read_bytes()
        fields=struct.unpack_from("<BBBHHBHHHHBB",data)
        if fields!=(0,0,2,0,0,0,0,0,512,256,24,0):
            raise ValueError(f"Expected 512x256 bottom-up true-color TGA for {name}")
        prints.append(memoryview(data)[18:18+512*256*3])
    data=(Path(folder)/"print"/"canopy-ink-mask.tga").read_bytes()
    if struct.unpack_from("<BBBHHBHHHHBB",data)!=(0,0,3,0,0,0,0,0,512,256,8,0):
        raise ValueError("Expected an uncompressed, bottom-up 8-bit crest coverage mask")
    ink=memoryview(data)[18:18+512*256]
    # Amber face, graphite binding, olive/tan braid, and folded amber throat.
    tints = [(189,128,43), (47,45,40), (146,139,108), (171,115,44)]
    tau = math.tau
    for y in range(SIZE):
        v = y / SIZE
        for x in range(SIZE):
            band, column = divmod(x, width)
            u = column / width
            if band == 2:
                # Interlaced cords alternate which diagonal passes on top.
                a, b = 5*u+8*v, 5*u-8*v
                first = (math.floor(a)+math.floor(b)) % 2 == 0
                phase = a if first else b
                h = .5+.5*math.cos(tau*phase)
                hx = -math.sin(tau*phase)*.38
                hy = (-1 if first else 1)*math.sin(tau*phase)*.34
                value = .76+.24*h
                if (math.floor((b if first else a) + .5) % 5) == 0:
                    value *= .72
            else:
                # Broken twill, with sub-yarns and a woven selvedge on either side.
                warp, weft = 23*u, 27*v
                over = (math.floor(warp)-math.floor(weft)) % 4 in (0,1)
                primary = warp if over else weft
                h = .5+.5*math.cos(tau*primary)
                sub = math.cos(2*tau*primary + .40*math.sin(tau*(weft if over else warp)))
                hx = -math.sin(tau*warp)*(.34 if over else .08)
                hy = -math.sin(tau*weft)*(.08 if over else .32)
                value = .72+.24*h+.035*sub
                margin=min(u,1-u)
                if margin < .075:
                    value *= .72
                if band in (0,3) and .084 < margin < .106 and v*11%1<.68:
                    value += .18
            rough = round(255*(.79 + .10*(1-h)))
            rgb = [round(min(255,channel*value)) for channel in tints[band]]
            color.extend((*rgb[::-1],rough))
            scale = 127.5/math.sqrt(hx*hx+hy*hy+1)
            normal.extend((round(127.5+scale),round(127.5+hy*scale),round(127.5+hx*scale)))
        # The right half holds two rectangular prints with their own UVs.
        sheet=prints[y//256]
        for px in range(512):
            pos=3*((y%256)*512+px)
            color.extend(sheet[pos:pos+3])
            color.append(round(.86*ink[(y%256)*512+px]) if y<256 else 220)
            yarn=4 if (px//2+y//2)%2 else -4
            normal.extend((255,128-yarn,128+yarn))
    for name, data, depth in zip(TILE_NAMES,(color,normal),(32,24)):
        header=struct.pack("<BBBHHBHHHHBB",0,0,2,0,0,0,0,0,SIZE*2,SIZE,depth,8 if depth==32 else 0)
        (Path(folder)/(name+".tga")).write_bytes(header+data)

def preview(material, folder, bpy):
    tree=material.node_tree
    bsdf=tree.nodes.get("Principled BSDF")
    def map_node(name,space):
        img=bpy.data.images.load(str(Path(folder)/(name+".tga")),check_existing=False)
        img.colorspace_settings.name=space
        img.alpha_mode="CHANNEL_PACKED"
        img.pack()
        node=tree.nodes.new("ShaderNodeTexImage")
        node.image=img
        return node
    color=map_node(TILE_NAMES[0],"sRGB")
    normal=map_node(TILE_NAMES[1],"Non-Color")
    direction=tree.nodes.new("ShaderNodeNormalMap")
    tree.links.new(color.outputs["Color"],bsdf.inputs["Base Color"])
    tree.links.new(color.outputs["Alpha"],bsdf.inputs["Roughness"])
    mask=tree.nodes.new("ShaderNodeMath")
    mask.operation="GREATER_THAN"
    mask.inputs[1].default_value=.25
    tree.links.new(color.outputs["Alpha"],mask.inputs[0])
    tree.links.new(mask.outputs[0],bsdf.inputs["Alpha"])
    tree.links.new(normal.outputs["Color"],direction.inputs["Color"])
    tree.links.new(direction.outputs["Normal"],bsdf.inputs["Normal"])
    bsdf.inputs["Sheen Weight"].default_value=.14

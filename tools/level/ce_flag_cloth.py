#!/usr/bin/env python3
"""Write the CE flag's cloth textures for MJOLNIRLevelLoader.

    ce_flag_cloth.py <Halo CE maps folder> <out dir>

CE draws a CTF flag's cloth from the flag tag (`weapons\\flag\\flag`), not
from the weapon's model, which is only the pole and its finial; so the
converted flag mesh has no cloth. The cloth's two bitmaps,
`weapons\\flag\\bitmaps\\flag_red` and `weapons\\flag\\bitmaps\\flags_blue`,
are read from bloodgulch.map's tag index and their pixels from bitmaps.map
(MCC's Halo CE folder, `halo1\\maps`), and written as `flag_cloth_red.png` and
`flag_cloth_blue.png`. build_ce_runtime.sh cooks them into the CE runtime
pack (chunk 981); for a local test, copy them to `MJOLNIRLevelLoader\\ctf\\`
instead. Either way the loader hangs the cloth on each flag (teams.lua,
CLOTH). They are Bungie's art, read from the user's own game: the repository
never holds them.
"""
import io
import os
import struct
import sys

from PIL import Image

# MCC Halo CE maps: tag data addresses start here.
BASE = 0x50000000
DXT = {14: b"DXT1", 15: b"DXT3", 16: b"DXT5"}
CLOTHS = {"red": "weapons\\flag\\bitmaps\\flag_red", "blue": "weapons\\flag\\bitmaps\\flags_blue"}


def tags(b):
    """`(group, name) -> file offset of the tag's data`."""
    toff = struct.unpack_from("<I", b, 0x10)[0]
    at = lambda a: toff + (a - BASE)
    array, _, _, count = struct.unpack_from("<IIII", b, toff)
    out = {}
    for i in range(count):
        group, _, _, _, name, data = struct.unpack_from("<4s4s4sIII", b, at(array) + i * 0x20)
        n = b[at(name):b.index(b"\0", at(name))].decode("latin1")
        out[(group[::-1].decode("latin1"), n)] = at(data)
    return out, at


def dds(fourcc, w, h, data):
    return struct.pack("<4sIIIIIII44sII4sIIIIIIIIII", b"DDS ", 124, 0x81007, h, w, len(data), 0, 1, b"\0" * 44,
                       32, 4, fourcc, 0, 0, 0, 0, 0, 0x1000, 0, 0, 0, 0) + data


def bitmap(b, shared, index, at, name):
    """The first bitmap of tag `name`, top mip, as an RGBA image."""
    o = index[("bitm", name)]
    _, ptr = struct.unpack_from("<II", b, o + 0x60)
    e = at(ptr)
    w, h, _, _, fmt, flags = struct.unpack_from("<HHHHHH", b, e + 4)
    off, size = struct.unpack_from("<II", b, e + 0x18)
    pixels = (shared if flags & 0x100 else b)[off:off + size]
    if fmt in DXT:
        top = max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * (8 if fmt == 14 else 16)
        return Image.open(io.BytesIO(dds(DXT[fmt], w, h, pixels[:top]))).convert("RGBA")
    if fmt in (10, 11):
        return Image.frombuffer("RGBA", (w, h), pixels[:w * h * 4], "raw", "BGRA", 0, 1).convert("RGBA")
    raise SystemExit(f"{name}: bitmap format {fmt} is not handled")


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    maps, out = sys.argv[1:3]
    b = open(os.path.join(maps, "bloodgulch.map"), "rb").read()
    shared = open(os.path.join(maps, "bitmaps.map"), "rb").read()
    index, at = tags(b)
    os.makedirs(out, exist_ok=True)
    for team, name in CLOTHS.items():
        path = os.path.join(out, f"flag_cloth_{team}.png")
        bitmap(b, shared, index, at, name).save(path)
        print(f"{name} -> {path}")


if __name__ == "__main__":
    main()

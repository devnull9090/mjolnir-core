#!/usr/bin/env python3
"""Dump named shader parameter structs (pass and root parameter structs, which
are not in the global uniform buffer list ub_dump.py walks) from a running
Unreal process.

    struct_dump.py <process image> <module> <out.json> <StructTypeName>...
    struct_dump.py HaloCampaignEvolved.exe HaloCampaignEvolved.exe fork_structs.json FRasterizePassParameters

Each FShaderParametersMetadata is a static object whose +0x10 points at its
struct type name (a TCHAR string in read-only data). This finds the name,
then every pointer to it in the module's writable sections, and keeps those
whose object reads as a struct with members (ub_dump.definition). The
MjolnirForkLayouts editor plugin applies the result (Config/
ForkShaderStructs.json) to the shader types that use these structs, so a
material's Nanite raster shaders bind their parameters at the fork's offsets.
Nanite's programmable raster (a material with world position offset, pixel
depth offset, masking or tessellation) crashed the game reading
FRasterizePassParameters at stock offsets (2026-10-12).
"""
import json
import struct
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from layout_dump import Mem, module, open_process, sections  # noqa: E402
from ub_dump import definition  # noqa: E402


def find_all(mem, base, needle):
    hits = []
    for _name, rva, vsize, _chars in sections(mem, base):
        data = mem.read(base + rva, vsize)
        if data is None:
            continue
        i = data.find(needle)
        while i >= 0:
            hits.append(base + rva + i)
            i = data.find(needle, i + 2)
    return hits


def pointers_to(mem, base, targets):
    targets = set(targets)
    found = []
    for _name, rva, vsize, chars in sections(mem, base):
        if not chars & 0x80000000:  # writable
            continue
        data = mem.read(base + rva, vsize)
        if data is None:
            continue
        for i in range(0, vsize - 8, 8):
            if struct.unpack_from("<Q", data, i)[0] in targets:
                found.append(base + rva + i)
    return found


def main():
    image, mod, dest = sys.argv[1:4]
    names = sys.argv[4:]
    header = image.lower() != "unrealeditor-cmd.exe"
    h = open_process(image)
    mem = Mem(h)
    base, _ = module(h, mod)
    out = {}
    for name in names:
        needle = name.encode("utf-16-le") + b"\0\0"
        strings = [s for s in find_all(mem, base, needle) if mem.read(s - 2, 2) in (b"\0\0", None) or True]
        objs = [p - 0x10 for p in pointers_to(mem, base, strings)]
        defs = []
        for obj in objs:
            d = definition(mem, obj, 0x100, header, {})
            if d.get("type") == name and d.get("members"):
                d["address"] = f"{obj:#x}"
                defs.append(d)
        print(f"{name}: {len(strings)} string(s), {len(objs)} reference(s), {len(defs)} struct(s)")
        if defs:
            out[name] = defs[0] if len(defs) == 1 else defs
    json.dump(out, open(dest, "w"), indent=1, sort_keys=True)
    print(f"-> {dest}")


if __name__ == "__main__":
    main()

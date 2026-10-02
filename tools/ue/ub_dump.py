#!/usr/bin/env python3
"""Dump every shader parameter struct (uniform buffers included) a running
Unreal process registered, with its full definition.

    ub_dump.py <process image name> <module name> <out.json>
    ub_dump.py HaloCampaignEvolved.exe HaloCampaignEvolved.exe fork_uniform_buffers.json

Shaders find the uniform buffers they were compiled against by layout hash
(RHICore InitStaticUniformBufferSlots -> FindUniformBufferStructByLayoutHash),
so a struct whose layout a fork changed has a different hash, and a shader
compiled against the stock layout binds nothing in its place. The dump of the
game is what the MjolnirForkLayouts editor plugin (unreal/MJOLNIRMaterials/Plugins)
re-creates in the stock editor before our materials compile.

FShaderParametersMetadata (RenderCore/Public/ShaderParameterMetadata.h) links
itself into a global list (GUniformStructList) through a TLinkedList member,
{NextLink, PrevLink, Element} (the base class's links come first), immediately
followed by its u32 LayoutHash. Field offsets in front of the link differ
between editor and game builds; those read here are the game's (a shipping
build without editor-only data):
  +0x08 LayoutName, +0x10 StructTypeName, +0x18 ShaderVariableName,
  +0x20 StaticSlotName (TCHAR*), +0x30 FileName (ANSI), +0x38 FileLine,
  +0x3c Size, +0x40 UseCase u8, +0x41 BindingFlags u8, +0x42 UsageFlags u8.
The Members TArray is found by shape. An FMember is 0x30 bytes: Name,
ShaderType, FileLine, Offset, BaseType u8, Precision u8, NumRows, NumColumns,
NumElements, Struct. Nested structs (EUseCase::ShaderParameterStruct, not in
the global list) are written inline under the member that holds them.
"""
import json
import struct
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from layout_dump import Mem, module, open_process, sections  # noqa: E402


def plausible_name(mem, p):
    s = mem.wstr(p, 96) if p and 0x10000 < p < 0x7FFFFFFFFFFF else None
    return s if s and s[:1] == "F" and s.isprintable() and len(s) > 3 else None


def find_list_head(mem, base):
    """A static pointer to a list node whose Element points at an object
    0x40..0x400 bytes before the node, with a struct type name at +0x10."""
    for name, rva, vsize, chars in sections(mem, base):
        if not chars & 0x80000000:
            continue
        data = mem.read(base + rva, vsize)
        if data is None:
            continue
        for i in range(0, vsize - 8, 8):
            node = struct.unpack_from("<Q", data, i)[0]
            if not 0x10000 < node < 0x7FFFFFFFFFFF:
                continue
            elem = mem.q(node + 0x10)
            if not elem or not 0x40 <= node - elem <= 0x400:
                continue
            if not plausible_name(mem, mem.q(elem + 0x10)):
                continue
            n, p = 0, node
            while p and n < 64:
                e = mem.q(p + 0x10)
                if not e or p - e != node - elem:
                    break
                n += 1
                p = mem.q(p)
            if n >= 64:
                return base + rva + i, node - elem
    sys.exit("struct list not found")


def astr(mem, p, cap=260):
    if not p or not 0x10000 < p < 0x7FFFFFFFFFFF:
        return None
    b = mem.read(p, cap)
    return None if b is None else b.split(b"\0", 1)[0].decode("latin-1")


def members_raw(mem, obj, span):
    """(data, num) of the struct's Members TArray, found by shape."""
    raw = mem.read(obj, span)
    if raw is None:
        return None
    for o in range(0x20, span - 8, 8):
        data, num, cap = struct.unpack_from("<Qii", raw, o)
        if not (0 < num <= cap <= 8192 and 0x10000 < data < 0x7FFFFFFFFFFF):
            continue
        rec = mem.read(data, 0x30)
        if rec is None:
            continue
        name_p, type_p = struct.unpack_from("<QQ", rec, 0)
        name = mem.wstr(name_p, 128)
        if name and name.isprintable() and mem.wstr(type_p, 64) is not None:
            return data, num
    return None


def definition(mem, obj, span, header, memo):
    if obj in memo:
        return memo[obj]
    d = {
        "type": mem.wstr(mem.q(obj + 0x10), 128),
        "layout_name": mem.wstr(mem.q(obj + 0x08), 128),
        "variable": mem.wstr(mem.q(obj + 0x18), 128),
        "static_slot": mem.wstr(mem.q(obj + 0x20), 128),
    }
    if header:
        file_line, size = struct.unpack("<iI", mem.read(obj + 0x38, 8))
        use_case, binding, usage = struct.unpack("<BBB", mem.read(obj + 0x40, 3))
        d.update({"size": size, "use_case": use_case, "binding_flags": binding, "usage_flags": usage,
                  "file": astr(mem, mem.q(obj + 0x30)), "line": file_line})
    memo[obj] = d
    found = members_raw(mem, obj, span)
    out = []
    if found:
        data, num = found
        rec = mem.read(data, 0x30 * num)
        for i in range(num):
            name_p, type_p, line, offset, base_type, precision = struct.unpack_from("<QQiIBB", rec, i * 0x30)
            rows, cols, elems = struct.unpack_from("<III", rec, i * 0x30 + 0x1C)
            struct_p = struct.unpack_from("<Q", rec, i * 0x30 + 0x28)[0]
            out.append({
                "name": mem.wstr(name_p, 128),
                "shader_type": mem.wstr(type_p, 256),
                "offset": offset,
                "base": base_type,
                "precision": precision,
                "rows": rows,
                "cols": cols,
                "elements": elems,
                "struct": definition(mem, struct_p, span, header, memo) if struct_p else None,
            })
    d["members"] = out
    return d


def main():
    image, mod, dest = sys.argv[1:4]
    # Struct headers (size, flags) are read at the game build's offsets only.
    header = image.lower() != "unrealeditor-cmd.exe"
    h = open_process(image)
    mem = Mem(h)
    base, _ = module(h, mod)
    head, link_off = find_list_head(mem, base)
    out = {}
    memo = {}
    p = mem.q(head)
    seen = set()
    while p and p not in seen:
        seen.add(p)
        obj = p - link_off
        layout_hash = struct.unpack("<I", mem.read(p + 0x18, 4))[0]
        d = definition(mem, obj, link_off, header, memo)
        d["hash"] = f"{layout_hash:08x}"
        out[d["type"] or f"@{obj:x}"] = d
        p = mem.q(p)
    json.dump(out, open(dest, "w"), indent=1, sort_keys=True)
    print(f"list head at {head:#x}, link at +{link_off:#x}; {len(out)} uniform buffer struct(s) -> {dest}")


if __name__ == "__main__":
    main()

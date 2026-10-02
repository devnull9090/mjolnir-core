#!/usr/bin/env python3
"""Dump every frozen-memory type layout a running Unreal process registered.

    layout_dump.py <process image name> <module name> <out.json>
    layout_dump.py HaloCampaignEvolved.exe HaloCampaignEvolved.exe game_layouts.json
    layout_dump.py UnrealEditor-Cmd.exe UnrealEditor-Core.dll stock_layouts.json

Unreal describes each type that can be frozen into a memory image (shaders,
their parameter bindings, shader maps) with a static FTypeLayoutDesc: name,
size, alignment, bases and a linked list of FFieldLayoutDesc (name, type,
offset, array count, flags). FTypeLayoutDesc::Register files them in
GTypeLayoutHashBuckets[4357] by NameHash % 4357 (Core/Private/Serialization/
MemoryImage.cpp). This finds that table in the given module's writable data,
walks every bucket chain and writes the layouts out, so a fork's layouts can be
compared with stock ones field by field.

Struct layouts (UE 5.5, Core/Public/Serialization/MemoryLayout.h):
  FTypeLayoutDesc  0x00 HashNext, 0x08 Name, 0x10 Fields, 0x18..0x48 functions,
                   0x50 NameHash u64, 0x58 Size, 0x5c SizeFromFields,
                   0x60 Alignment, 0x64 Interface u8, 0x65 NumBases,
                   0x66 NumVirtualBases, 0x67 IsIntrinsic:1 IsInitialized:1
  FFieldLayoutDesc 0x00 Name, 0x08 Type, 0x10 Next, 0x18 WriteFunc,
                   0x20 Offset u32, 0x24 NumArray u32, 0x28 Flags u8,
                   0x29 BitFieldSize u8, 0x2a UFieldNameLength u8
"""
import ctypes
import ctypes.wintypes as W
import json
import struct
import subprocess
import sys

BUCKETS = 4357

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi")


class MODULEINFO(ctypes.Structure):
    _fields_ = [("lpBaseOfDll", ctypes.c_void_p), ("SizeOfImage", W.DWORD), ("EntryPoint", ctypes.c_void_p)]


def open_process(image):
    out = subprocess.check_output(["tasklist", "/FI", f"IMAGENAME eq {image}", "/FO", "CSV", "/NH"]).decode()
    if image.lower() not in out.lower():
        sys.exit(f"{image} is not running")
    pid = int(out.split('","')[1])
    return k32.OpenProcess(0x0410, False, pid)


def module(h, name):
    mods = (ctypes.c_void_p * 4096)()
    need = W.DWORD()
    psapi.EnumProcessModulesEx(h, mods, ctypes.sizeof(mods), ctypes.byref(need), 3)
    for m in mods[: need.value // 8]:
        buf = ctypes.create_unicode_buffer(260)
        psapi.GetModuleBaseNameW(h, ctypes.c_void_p(m), buf, 260)
        if buf.value.lower() == name.lower():
            info = MODULEINFO()
            psapi.GetModuleInformation(h, ctypes.c_void_p(m), ctypes.byref(info), ctypes.sizeof(info))
            return m, info.SizeOfImage
    sys.exit(f"module {name} not loaded")


class Mem:
    def __init__(self, h):
        self.h = h
        self.cache = {}

    def read(self, addr, n):
        buf = ctypes.create_string_buffer(n)
        got = ctypes.c_size_t()
        if not k32.ReadProcessMemory(self.h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)) or got.value != n:
            return None
        return buf.raw

    def q(self, addr):
        b = self.read(addr, 8)
        return None if b is None else struct.unpack("<Q", b)[0]

    def wstr(self, addr, cap=256):
        if not addr:
            return None
        b = self.read(addr, cap * 2)
        if b is None:
            return None
        s = b.decode("utf-16le", errors="replace")
        return s.split("\0", 1)[0]


def sections(mem, base):
    """(rva, size, characteristics) of each PE section, read from the image."""
    hdr = mem.read(base, 0x1000)
    pe = struct.unpack_from("<I", hdr, 0x3C)[0]
    count = struct.unpack_from("<H", hdr, pe + 6)[0]
    opt = struct.unpack_from("<H", hdr, pe + 20)[0]
    out = []
    for i in range(count):
        o = pe + 24 + opt + i * 40
        name = hdr[o : o + 8].rstrip(b"\0").decode(errors="replace")
        vsize, rva = struct.unpack_from("<II", hdr, o + 8)
        chars = struct.unpack_from("<I", hdr, o + 36)[0]
        out.append((name, rva, vsize, chars))
    return out


def find_buckets(mem, base, size):
    """The bucket table in the module's writable data: a run of 4357 qwords,
    each null or a pointer to a record whose NameHash falls in that bucket. In
    a monolithic game the records sit in the same image; in the editor they
    are spread across every module, so any readable pointer is a candidate."""
    for name, rva, vsize, chars in sections(mem, base):
        if not chars & 0x80000000:  # IMAGE_SCN_MEM_WRITE
            continue
        data = mem.read(base + rva, vsize)
        if data is None:
            continue
        qs = struct.unpack_from(f"<{vsize // 8}Q", data)
        n = len(qs)
        hashes = {}

        def hash_of(v):
            if v not in hashes:
                hashes[v] = mem.q(v + 0x50) if 0x10000 < v < 0x7FFFFFFFFFFF else None
            return hashes[v]

        best = None
        tried = set()
        for j, v in enumerate(qs):
            if not v or not 0x10000 < v < 0x7FFFFFFFFFFF:
                continue
            h = hash_of(v)
            if h is None:
                continue
            origin = j - (h % BUCKETS)
            if origin < 0 or origin + BUCKETS > n or origin in tried:
                continue
            tried.add(origin)
            hits = 0
            for k in range(origin, origin + BUCKETS, 7):
                w = qs[k]
                if w and 0x10000 < w < 0x7FFFFFFFFFFF:
                    hh = hash_of(w)
                    if hh is not None and hh % BUCKETS == k - origin:
                        hits += 1
            if hits > 20 and (best is None or hits > best[1]):
                best = (base + rva + origin * 8, hits)
        if best:
            return best[0]
    sys.exit("bucket table not found")


def walk(mem, table):
    descs = {}
    for b in range(BUCKETS):
        p = mem.q(table + b * 8)
        while p and p not in descs:
            d = mem.read(p, 0x68)
            if d is None:
                break
            next_, name_p, fields_p = struct.unpack_from("<QQQ", d, 0)
            name_hash, size, size_from_fields, align = struct.unpack_from("<QIII", d, 0x50)
            iface, nbases, nvbases, bits = struct.unpack_from("<BBBB", d, 0x64)
            descs[p] = {
                "name": mem.wstr(name_p),
                "hash": f"{name_hash:016x}",
                "size": size,
                "size_from_fields": size_from_fields,
                "align": align,
                "interface": iface,
                "bases": nbases,
                "virtual_bases": nvbases,
                "intrinsic": bool(bits & 1),
                "_fields": fields_p,
            }
            p = next_
    by_addr = {a: d["name"] for a, d in descs.items()}
    out = {}
    for a, d in descs.items():
        fields = []
        f = d.pop("_fields")
        seen = set()
        while f and f not in seen:
            seen.add(f)
            r = mem.read(f, 0x30)
            if r is None:
                break
            name_p, type_p, next_p, _write = struct.unpack_from("<QQQQ", r, 0)
            offset, num_array = struct.unpack_from("<II", r, 0x20)
            flags, bitsize, namelen = struct.unpack_from("<BBB", r, 0x28)
            fields.append({
                "name": mem.wstr(name_p),
                "type": by_addr.get(type_p, f"@{type_p:x}"),
                "offset": offset,
                "array": num_array,
                "flags": flags,
                "bits": bitsize,
            })
            f = next_p
        d["fields"] = fields
        out[d["name"] or f"@{a:x}"] = d
    return out


def main():
    image, mod, dest = sys.argv[1:4]
    h = open_process(image)
    mem = Mem(h)
    base, size = module(h, mod)
    table = find_buckets(mem, base, size)
    layouts = walk(mem, table)
    json.dump(layouts, open(dest, "w"), indent=1, sort_keys=True)
    print(f"bucket table at {table:#x} (+{table - base:#x}); {len(layouts)} type layout(s) -> {dest}")


if __name__ == "__main__":
    main()

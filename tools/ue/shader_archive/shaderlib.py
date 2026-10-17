"""UE 5.5 IoStore shader library reader (FIoStoreShaderCodeArchive) + D3D12 shader blob / DXIL container parser.

Inputs come from the Rust helper in ./extract (it owns IoStore + Oodle):
    shaderlib-extract libs   <utoc> <outdir>          -> <key>.lib  (archive header chunk)
    shaderlib-extract groups <utoc> <list> <outdir>   -> <key>.bin  (decompressed shader groups)

Layout (RenderCore/Private/ShaderCodeArchive.cpp, SaveIoStoreShaderCodeArchive):
    u32 Version (=1)
    TArray<FSHAHash[20]>        ShaderMapHashes
    TArray<FSHAHash[20]>        ShaderHashes
    TArray<FIoChunkId[12]>      ShaderGroupIoHashes
    TArray<{u32 off,u32 num}>   ShaderMapEntries
    TArray<u64 packed>          ShaderEntries   (Frequency:4 | GroupIndex:30 | OffsetInGroup:30)
    TArray<{u32 off,u32 num,u32 usize,u32 csize}> ShaderGroupEntries
    TArray<u32>                 ShaderIndices

A shader blob (D3D12 RHI, InitStandardShader): [serialized FShaderResourceTable][DXBC container]
[optional data: (u8 key, u32 size, bytes)*][i32 optional data size incl. this int].
"""
from __future__ import annotations

import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

# EShaderFrequency, UE 5.5 RHIDefinitions.h
FREQ = {0: "VS", 1: "MS", 2: "AS", 3: "PS", 4: "GS", 5: "CS", 6: "RayGen", 7: "RayMiss",
        8: "RayHitGroup", 9: "RayCallable", 10: "WGRoot", 11: "WGNode"}


class R:
    def __init__(self, b: bytes, pos: int = 0):
        self.b, self.p = b, pos

    def u8(self):
        v = self.b[self.p]; self.p += 1; return v

    def u16(self):
        v = struct.unpack_from("<H", self.b, self.p)[0]; self.p += 2; return v

    def u32(self):
        v = struct.unpack_from("<I", self.b, self.p)[0]; self.p += 4; return v

    def i32(self):
        v = struct.unpack_from("<i", self.b, self.p)[0]; self.p += 4; return v

    def u64(self):
        v = struct.unpack_from("<Q", self.b, self.p)[0]; self.p += 8; return v

    def raw(self, n):
        v = self.b[self.p:self.p + n]; self.p += n; return v


@dataclass
class Library:
    version: int
    map_hashes: list[bytes]
    shader_hashes: list[bytes]
    group_ids: list[bytes]
    map_entries: list[tuple[int, int]]
    shader_entries: list[tuple[int, int, int]]  # freq, group, offset
    group_entries: list[tuple[int, int, int, int]]
    indices: list[int]

    def map_shaders(self, mi: int) -> list[int]:
        off, num = self.map_entries[mi]
        return self.indices[off:off + num]

    def shader_size(self, si: int) -> int:
        f, g, o = self.shader_entries[si]
        goff, gnum, usz, csz = self.group_entries[g]
        members = self.indices[goff:goff + gnum]
        k = members.index(si)
        if k + 1 < len(members):
            return self.shader_entries[members[k + 1]][2] - o
        return usz - o

    def group_key(self, g: int) -> str:
        return self.group_ids[g][:10].hex()


def parse_library(b: bytes) -> Library:
    r = R(b)
    ver = r.u32()

    def arr(fn):
        n = r.i32()
        return [fn() for _ in range(n)]

    mh = arr(lambda: r.raw(20))
    sh = arr(lambda: r.raw(20))
    gi = arr(lambda: r.raw(12))
    me = arr(lambda: (r.u32(), r.u32()))

    def se():
        p = r.u64()
        return (p & 0xF, (p >> 4) & ((1 << 30) - 1), (p >> 34) & ((1 << 30) - 1))
    sen = arr(se)
    ge = arr(lambda: (r.u32(), r.u32(), r.u32(), r.u32()))
    ix = arr(r.u32)
    assert r.p == len(b), (r.p, len(b))
    return Library(ver, mh, sh, gi, me, sen, ge, ix)


# ----------------------------------------------------------------- shader blob

@dataclass
class Blob:
    code: bytes
    dxbc_off: int
    dxbc: bytes
    optional: dict[str, bytes]


def split_blob(code: bytes) -> Blob:
    opt_size = struct.unpack_from("<i", code, len(code) - 4)[0]
    start = len(code) - opt_size
    end = len(code) - 4
    opt: dict[str, bytes] = {}
    p = start
    while p < end:
        k = chr(code[p]); sz = struct.unpack_from("<I", code, p + 1)[0]
        opt[k] = code[p + 5:p + 5 + sz]
        p += 5 + sz
    d = code.find(b"DXBC", 0, start)
    dx = b""
    if d >= 0:
        total = struct.unpack_from("<I", code, d + 24)[0]
        dx = code[d:d + total]
    return Blob(code, d, dx, opt)


# ----------------------------------------------------------------- DXBC / DXIL container

def dxbc_parts(dx: bytes) -> dict[str, bytes]:
    n = struct.unpack_from("<I", dx, 28)[0]
    parts = {}
    for i in range(n):
        off = struct.unpack_from("<I", dx, 32 + 4 * i)[0]
        fourcc = dx[off:off + 4].decode("latin1")
        sz = struct.unpack_from("<I", dx, off + 4)[0]
        parts[fourcc] = dx[off + 8:off + 8 + sz]
    return parts


SIG_COMP = {0: "unk", 1: "u32", 2: "i32", 3: "f32", 4: "u16", 5: "i16", 6: "f16", 7: "u64", 8: "i64", 9: "f64"}
SV = {0: "", 1: "SV_Position", 2: "SV_ClipDistance", 3: "SV_CullDistance", 4: "SV_RenderTargetArrayIndex",
      5: "SV_ViewportArrayIndex", 6: "SV_VertexID", 7: "SV_PrimitiveID", 8: "SV_InstanceID", 9: "SV_IsFrontFace",
      10: "SV_SampleIndex", 64: "SV_Target", 65: "SV_Depth", 66: "SV_Coverage", 67: "SV_DepthGE", 68: "SV_DepthLE",
      69: "SV_StencilRef", 70: "SV_InnerCoverage", 71: "SV_Barycentrics", 72: "SV_ShadingRate", 73: "SV_CullPrimitive"}


def parse_sig(part: bytes) -> list[dict]:
    """ISG1 / OSG1 / PSG1 (DxilProgramSignature + DxilProgramSignatureElement, 32 bytes each)."""
    n, off = struct.unpack_from("<II", part, 0)
    out = []
    for i in range(n):
        (stream, name_off, sem_idx, sys_val, comp_type, reg, mask, rw_mask,
         _pad, min_prec) = struct.unpack_from("<IIIIIIBBHI", part, off + 32 * i)
        e = part.find(b"\0", name_off)
        name = part[name_off:e].decode("latin1")
        out.append(dict(name=name, idx=sem_idx, sv=SV.get(sys_val, str(sys_val)), comp=SIG_COMP.get(comp_type, comp_type),
                        reg=reg, mask=mask, rw=rw_mask, stream=stream, minprec=min_prec))
    return out


def fmt_sig(sig: list[dict]) -> str:
    m = lambda x: "".join(c for c, bit in zip("xyzw", (1, 2, 4, 8)) if x & bit)
    return "; ".join(f"{e['name']}{e['idx']}{'(' + e['sv'] + ')' if e['sv'] else ''} r{e['reg']}.{m(e['mask'])} {e['comp']}"
                     for e in sig)


STAGES = {0: "PS", 1: "VS", 2: "GS", 3: "HS", 4: "DS", 5: "CS", 6: "Library", 13: "MS", 14: "AS"}


def parse_psv0(p: bytes) -> dict:
    r = R(p)
    info_size = r.u32()
    base = r.p
    d = {"psv_info_size": info_size}
    stage_union = p[base:base + 16]
    d["min_wave"], d["max_wave"] = struct.unpack_from("<II", p, base + 16)
    if info_size >= 36:
        st, viewid = p[base + 24], p[base + 25]
        d["stage"] = STAGES.get(st, st)
        d["sig_in"], d["sig_out"], d["sig_pc"] = p[base + 28], p[base + 29], p[base + 30]
        if d["stage"] == "MS":
            gs, gsv, pay, mv, mp = struct.unpack_from("<IIIHH", stage_union)
            d.update(ms_groupshared=gs, ms_payload=pay, ms_max_verts=mv, ms_max_prims=mp)
            d["ms_out_topology"] = p[base + 27]  # union { u8 SigPrimVectors; u8 MeshOutputTopology }
    if info_size >= 48:
        d["numthreads"] = struct.unpack_from("<III", p, base + 36)
    if info_size >= 52:
        d["entry_name_off"] = struct.unpack_from("<I", p, base + 48)[0]
    r.p = base + info_size
    nres = r.u32()
    if nres:
        bsz = r.u32()
        r.p += bsz * nres
    d["resources"] = nres
    if info_size >= 36:
        st_size = r.u32()
        strtab = r.raw(st_size)
        if "entry_name_off" in d:
            e = strtab.find(b"\0", d["entry_name_off"])
            d["entry"] = strtab[d["entry_name_off"]:e].decode("latin1")
    return d


def wave_info(parts: dict[str, bytes]) -> str:
    """WaveSize from PSV0 (DXC writes the [WaveSize] range into Min/MaxExpectedWaveLaneCount)."""
    if "PSV0" not in parts:
        return "?"
    d = parse_psv0(parts["PSV0"])
    lo, hi = d["min_wave"], d["max_wave"]
    if lo == 0 and hi in (0, 0xFFFFFFFF):
        return "any"
    return f"{lo}-{hi}" if lo != hi else str(lo)


def sfi0(parts: dict[str, bytes]) -> int:
    return struct.unpack_from("<Q", parts["SFI0"], 0)[0] if "SFI0" in parts else 0


# ----------------------------------------------------------------- CLI

def load_group(groupdir: Path, lib: Library, g: int) -> bytes | None:
    f = groupdir / f"{lib.group_key(g)}.bin"
    return f.read_bytes() if f.exists() else None


def shader_code(groupdir: Path, lib: Library, si: int) -> bytes | None:
    f, g, o = lib.shader_entries[si]
    data = load_group(groupdir, lib, g)
    if data is None:
        return None
    return data[o:o + lib.shader_size(si)]


def describe(code: bytes) -> dict:
    b = split_blob(code)
    out = {"size": len(code), "opt_keys": "".join(sorted(b.optional))}
    if "n" in b.optional:
        out["name"] = b.optional["n"].rstrip(b"\0").decode("latin1", "replace")
    if "x" in b.optional:
        out["features"] = int.from_bytes(b.optional["x"], "little")
    if "p" in b.optional:
        out["usage_flags"] = b.optional["p"][0]
    if not b.dxbc:
        return out
    parts = dxbc_parts(b.dxbc)
    out["parts"] = ",".join(parts)
    out["wave"] = wave_info(parts)
    out["sfi0"] = sfi0(parts)
    if "PSV0" in parts:
        out["psv"] = parse_psv0(parts["PSV0"])
    for k in ("ISG1", "OSG1", "PSG1"):
        if k in parts:
            out[k] = parse_sig(parts[k])
    return out


def main(argv):
    cmd = argv[1]
    if cmd == "summary":
        lib = parse_library(Path(argv[2]).read_bytes())
        print(f"version {lib.version} maps {len(lib.map_hashes)} shaders {len(lib.shader_hashes)} groups {len(lib.group_entries)}")
        for mi, h in enumerate(lib.map_hashes):
            ss = lib.map_shaders(mi)
            fr = {}
            for s in ss:
                k = FREQ[lib.shader_entries[s][0]]
                fr[k] = fr.get(k, 0) + 1
            print(f"map {mi} {h.hex()} n={len(ss)} {fr}")
    elif cmd == "grouplist":
        # grouplist <lib> [map indices comma | 'all' | hash prefixes]
        lib = parse_library(Path(argv[2]).read_bytes())
        sel = argv[3] if len(argv) > 3 else "all"
        maps = select_maps(lib, sel)
        gs = sorted({lib.shader_entries[s][1] for m in maps for s in lib.map_shaders(m)})
        for g in gs:
            _, _, usz, csz = lib.group_entries[g]
            print(lib.group_key(g), usz, csz)
    elif cmd == "maps":
        # maps <lib> <groupdir> <sel> : dump every shader of the selected maps
        lib = parse_library(Path(argv[2]).read_bytes())
        gd = Path(argv[3])
        for m in select_maps(lib, argv[4] if len(argv) > 4 else "all"):
            print(f"== map {m} {lib.map_hashes[m].hex()}")
            for k, s in enumerate(lib.map_shaders(m)):
                code = shader_code(gd, lib, s)
                if code is None:
                    print(f"  [{k}] shader {s} (group missing)"); continue
                d = describe(code)
                psv = d.get("psv", {})
                print(f"  [{k}] s{s} {lib.shader_hashes[s].hex()[:16]} {FREQ[lib.shader_entries[s][0]]} "
                      f"entry={psv.get('entry')} wave={d.get('wave')} nt={psv.get('numthreads')} size={d['size']} "
                      f"opt={d['opt_keys']} feat={d.get('features')} sfi0={d.get('sfi0', 0):#x}")
    elif cmd == "dxil":
        # dxil <lib> <groupdir> <outdir> <shaderhashprefix>... : write the DXBC container(s) for dxc -dumpbin
        lib = parse_library(Path(argv[2]).read_bytes())
        gd, out = Path(argv[3]), Path(argv[4])
        out.mkdir(parents=True, exist_ok=True)
        for pref in argv[5:]:
            for si, h in enumerate(lib.shader_hashes):
                if h.hex().startswith(pref):
                    code = shader_code(gd, lib, si)
                    b = split_blob(code)
                    f = out / f"{h.hex()[:16]}.dxbc"
                    f.write_bytes(b.dxbc)
                    print(f, len(b.dxbc))
    elif cmd == "link":
        # link <libMS> <groupdirMS> <ms-hash-prefix> <libPS> <groupdirPS> <ps-hash-prefix>
        # Approximates D3D12's mesh->pixel linkage checks (#666 semantic missing, #662 register/mask).
        def sigs(libp, gd, pref):
            lib = parse_library(Path(libp).read_bytes())
            si = next(i for i, h in enumerate(lib.shader_hashes) if h.hex().startswith(pref))
            return describe(shader_code(Path(gd), lib, si))
        ms, ps = sigs(argv[2], argv[3], argv[4]), sigs(argv[5], argv[6], argv[7])
        outs = {(e["name"], e["idx"]): ("vertex", e) for e in ms.get("OSG1", [])}
        outs.update({(e["name"], e["idx"]): ("primitive", e) for e in ms.get("PSG1", [])})
        ok = True
        for e in ps.get("ISG1", []):
            if e["sv"] in ("SV_Barycentrics", "SV_IsFrontFace", "SV_PrimitiveID", "SV_SampleIndex", "SV_Coverage"):
                continue
            k = (e["name"], e["idx"])
            if k not in outs:
                print(f"  #666 {e['name']}{e['idx']}: required by the PS, not output by the MS"); ok = False; continue
            kind, o = outs[k]
            if kind == "vertex" and (o["reg"] != e["reg"] or o["mask"] != e["mask"]):
                print(f"  #662 {e['name']}{e['idx']}: MS r{o['reg']} mask {o['mask']:#x} vs PS r{e['reg']} mask {e['mask']:#x}"); ok = False
            if kind == "primitive" and o["mask"] != e["mask"]:
                print(f"  #662 {e['name']}{e['idx']} (per-primitive): MS mask {o['mask']:#x} vs PS mask {e['mask']:#x}"); ok = False
        print("  links" if ok else "  LINK FAILS")
    elif cmd == "raster":
        # raster <lib> <groupdir> : every Nanite raster shader (by PSV0 entry name) with wave + signatures
        lib = parse_library(Path(argv[2]).read_bytes())
        gd = Path(argv[3])
        want = ("MicropolyRasterize", "HWRasterizeVS", "HWRasterizeMS", "HWRasterizePS")
        for m in range(len(lib.map_hashes)):
            rows = []
            for k, s in enumerate(lib.map_shaders(m)):
                code = shader_code(gd, lib, s)
                if code is None:
                    continue
                d = describe(code)
                psv = d.get("psv", {})
                if psv.get("entry") not in want:
                    continue
                rows.append((k, s, d, psv))
            if not rows:
                continue
            print(f"== map {m} {lib.map_hashes[m].hex()}")
            for k, s, d, psv in rows:
                print(f"  [{k}] s{s} {lib.shader_hashes[s].hex()[:16]} {psv['entry']} wave={d['wave']} nt={psv.get('numthreads')} "
                      f"res={psv.get('resources')} feat={d.get('features')} sfi0={d.get('sfi0', 0):#x} size={d['size']}")
                for sk in ("ISG1", "OSG1", "PSG1"):
                    if d.get(sk) and psv["entry"] != "MicropolyRasterize":
                        print(f"      {sk}: {fmt_sig(d[sk])}")
    else:
        raise SystemExit(f"unknown {cmd}")


def select_maps(lib: Library, sel: str) -> list[int]:
    if sel == "all":
        return list(range(len(lib.map_hashes)))
    out = []
    for t in sel.split(","):
        if len(t) >= 8 and all(c in "0123456789abcdef" for c in t):
            out += [i for i, h in enumerate(lib.map_hashes) if h.hex().startswith(t)]
        else:
            out.append(int(t))
    return out


if __name__ == "__main__":
    main(sys.argv)

"""Decode a cooked material's inline FMaterialShaderMap (frozen memory image) far enough to list
(shader type, permutation id, frequency, resource index -> shader hash in the library).

    python shadermap.py <export.bin> [<library.lib>]

<export.bin> is the material's ExportBundleData chunk (shaderlib-extract chunk <utoc> <path> <out>).
With the library, ResourceIndex is resolved to the shader hash through the shader map entry whose
hash follows the frozen image (bShareCode=1, FName platform, FSHAHash ResourceHash).

Layout facts used (UE 5.5 Core/Serialization/MemoryImage.*, RenderCore/Shader.h), verified on
our cook and on 343's shipped materials:
  FMemoryImageResult: u32 MaxFieldAlignment, u32 Flags, u32 FrozenSize, frozen bytes, pointer table...
  TMemoryImageArray frozen: {u64 FFrozenMemoryImagePtr, i32 Num, i32 Max}
  FFrozenMemoryImagePtr: bit0 frozen, bits 1..23 type index+1, bits 24..63 signed offset from the field
  FShaderMapContent: ShaderHash table, then ShaderTypes (FHashedName u64), ShaderPermutations (i32),
  Shaders (TMemoryImagePtr<FShader>), ShaderPipelines, ShaderPlatformName
  FShader: ... TIndexedPtr<FShaderType> Type, TIndexedPtr<FVertexFactoryType> VFType,
           FShaderTarget Target (u32: Frequency:SF_NumBits(4)... Platform), int32 ResourceIndex, ...
Type names are FHashedName: CityHash64WithSeed(upper(name), 0).
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import shaderlib  # noqa: E402

NAMES = {
    0x147603aa216d0403: "FMicropolyRasterizeCS",
    0x2e3357276e3f9c5e: "FHWRasterizeVS",
    0x895fa1bd762c3ccb: "FHWRasterizeMS",
    0x4e02077390866fd4: "FHWRasterizePS",
}

# Stock UE 5.5 permutation domains, first dimension = least significant (ToDimensionValueId).
DOMAINS = {
    "FMicropolyRasterizeCS": ["DEPTH_ONLY", "TWO_SIDED", "VISUALIZE", "VT_TARGET", "VERT_PROG", "PIX_PROG",
                              "TESSELLATION", "PATCHES", "SPLINE", "SKINNING", "FIXED_DISP_FALLBACK"],
    "FHWRasterizeVS": ["DEPTH_ONLY", "PRIM_SHADER", "VT_TARGET", "VERT_PROG", "PIX_PROG", "SPLINE", "SKINNING",
                       "FIXED_DISP_FALLBACK"],
    "FHWRasterizeMS": ["DEPTH_ONLY", "VT_TARGET", "VERT_PROG", "PIX_PROG", "SPLINE", "SKINNING",
                       "ALLOW_SV_BARY", "FIXED_DISP_FALLBACK"],
    "FHWRasterizePS": ["DEPTH_ONLY", "MESH_SHADER", "PRIM_SHADER", "VISUALIZE", "VT_TARGET", "VERT_PROG",
                       "PIX_PROG", "ALLOW_SV_BARY"],
}


def decode_perm(tname: str, pid: int) -> str:
    dims = DOMAINS.get(tname)
    if not dims:
        return ""
    return "|".join(d for i, d in enumerate(dims) if pid >> i & 1) or "-"


def frozen_ptr(b: bytes, at: int) -> int | None:
    p = struct.unpack_from("<Q", b, at)[0]
    if not p & 1:
        return None
    off = struct.unpack_from("<q", b, at)[0] >> 24
    return at + off


def find_image(b: bytes):
    """Return (frozen_start, frozen_size) of the shader map's memory image."""
    known = [struct.pack("<Q", h) for h in NAMES]
    hit = min((b.find(k) for k in known if b.find(k) >= 0), default=-1)
    if hit < 0:
        raise SystemExit("no Nanite raster shader types in this export")
    for o in range(8, hit):
        sz = struct.unpack_from("<I", b, o)[0]
        a, f = struct.unpack_from("<II", b, o - 8)
        if a in (4, 8, 16) and f < 64 and 64 < sz and o + 4 + sz <= len(b) and o + 4 <= hit < o + 4 + sz:
            return o + 4, sz
    raise SystemExit("frozen image header not found")


def main():
    b = Path(sys.argv[1]).read_bytes()
    lib = shaderlib.parse_library(Path(sys.argv[2]).read_bytes()) if len(sys.argv) > 2 else None
    start, size = find_image(b)
    end = start + size
    # Find the three consecutive TMemoryImageArray headers: ShaderTypes(u64), ShaderPermutations(i32), Shaders(ptr)
    for at in range(start, start + 256, 8):
        t = frozen_ptr(b, at)
        if t is None:
            continue
        n = struct.unpack_from("<i", b, at + 8)[0]
        if not (0 < n < 5000):
            continue
        p = frozen_ptr(b, at + 16)
        s = frozen_ptr(b, at + 32)
        if p is None or s is None:
            continue
        if struct.unpack_from("<i", b, at + 24)[0] != n or struct.unpack_from("<i", b, at + 40)[0] != n:
            continue
        types = struct.unpack_from(f"<{n}Q", b, t)
        if not any(x in NAMES for x in types):
            continue
        perms = struct.unpack_from(f"<{n}i", b, p)
        shaders = [frozen_ptr(b, s + 8 * i) for i in range(n)]
        break
    else:
        raise SystemExit("ShaderTypes/ShaderPermutations/Shaders arrays not found")

    # Resource hash: after the frozen image + pointer table etc.; locate via the library.
    map_index = None
    if lib:
        for mi, h in enumerate(lib.map_hashes):
            if b.find(h, end) >= 0:
                map_index = mi
                break
        print(f"library shader map index {map_index} {lib.map_hashes[map_index].hex() if map_index is not None else '?'}")
    for i in range(n):
        tname = NAMES.get(types[i])
        if not tname:
            continue
        sh = shaders[i]
        # FShader tail: Type (odd u64 index ptr), VFType (u64), Target (u32), ResourceIndex (i32)
        res, freq = None, None
        for q in range(sh, min(sh + 512, end) - 24, 4):
            tp = struct.unpack_from("<Q", b, q)[0]
            vf = struct.unpack_from("<Q", b, q + 8)[0]
            tgt, ri = struct.unpack_from("<Ii", b, q + 16)
            want = {"FMicropolyRasterizeCS": 5, "FHWRasterizeVS": 0, "FHWRasterizeMS": 1, "FHWRasterizePS": 3}[tname]
            if tp & 1 and tp < (1 << 20) and vf == 0 and 0 <= ri < 4096 and (tgt & 0xF) == want and 0 < tgt >> 4 < 4096:
                res, freq = ri, shaderlib.FREQ.get(tgt & 0xF)
                break
        hs = ""
        if lib is not None and map_index is not None and res is not None:
            sidx = lib.map_shaders(map_index)[res]
            hs = lib.shader_hashes[sidx].hex()[:16]
        print(f"{tname:22s} perm {perms[i]:5d} {decode_perm(tname, perms[i]):45s} freq={freq} res={res} {hs}")


if __name__ == "__main__":
    main()

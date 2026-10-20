"""Find stat unit's DrawStat in a game build and print the frame-times pattern.

native/frame_times/mjolnir_frame_times.c finds FStatUnitData::DrawStat by a
byte pattern and decodes the engine's frame-time globals from its RIP-relative
loads (docs/performance.md, "Where a frame goes"). After a game update, run
this against the new exe (`--find` rebuilds the pattern even when it matches):

    python tools/pe/statunit_pattern.py "<Win64>/HaloCampaignEvolved.exe"

It checks the pattern now in the C file first. If that still matches exactly
once, nothing needs doing. If not, it finds DrawStat again by its "%3.2f ms"
format string, which sits just before "UnitGraph" in .rdata, prints the
function's opening, and when the instruction shapes the C file expects are
there, the new `pattern[]` body and offsets to paste in.

Needs pefile and capstone (pip install pefile capstone).
"""

from __future__ import annotations

import re
import struct
import sys
from pathlib import Path

import capstone
import pefile
from capstone import x86

C_FILE = Path(__file__).resolve().parents[2] / "native" / "frame_times" / "mjolnir_frame_times.c"


def c_pattern() -> list[int]:
    src = C_FILE.read_text(encoding="utf-8")
    body = src[src.index("pattern[] = {") + len("pattern[] = {"):]
    body = body[: body.index("};")]
    return [int(t, 16) if t.startswith("0x") else int(t) for t in re.findall(r"-1|0x[0-9A-Fa-f]{2}", body)]


def regex(pat: list[int]) -> re.Pattern[bytes]:
    return re.compile(b"".join(b"." if v < 0 else re.escape(bytes([v])) for v in pat), re.S)


def main() -> int:
    exe = sys.argv[1]
    data = Path(exe).read_bytes()
    pe = pefile.PE(exe, fast_load=True)
    text = next(s for s in pe.sections if s.Name.startswith(b".text"))
    t0, tr = text.PointerToRawData, text.VirtualAddress
    tb = data[t0 : t0 + text.SizeOfRawData]

    hits = [m.start() for m in regex(c_pattern()).finditer(tb)]
    print(f"current pattern: {len(hits)} match(es)" + (f" at RVA {tr + hits[0]:#x}" if len(hits) == 1 else ""))
    if len(hits) == 1 and "--find" not in sys.argv:
        return 0

    # The "%3.2f ms" wide string just before "UnitGraph".
    fmt = "%3.2f ms\0".encode("utf-16le")
    anchor = "UnitGraph".encode("utf-16le")
    strings = [m.start() for m in re.finditer(re.escape(fmt), data) if anchor in data[m.start() : m.start() + 64]]
    if not strings:
        print("no '%3.2f ms' string beside UnitGraph: find DrawStat by hand")
        return 1
    target = pe.get_rva_from_offset(strings[0])
    xrefs = []
    for m in re.finditer(rb"[\x48\x4c]\x8d[\x05\x0d\x15\x1d\x25\x2d\x35\x3d]", tb):
        i = m.start()
        if tr + i + 7 + struct.unpack_from("<i", tb, i + 3)[0] == target:
            xrefs.append(tr + i)
    if not xrefs:
        print("no code reads the string")
        return 1
    # The function holding the first reference, from .pdata.
    pdata = next(s for s in pe.sections if s.Name.startswith(b".pdata"))
    pb = data[pdata.PointerToRawData : pdata.PointerToRawData + pdata.SizeOfRawData]
    start = None
    for i in range(0, len(pb), 12):
        b, e, _ = struct.unpack_from("<III", pb, i)
        if b <= xrefs[0] < e:
            start = b
            break
    print(f"DrawStat: RVA {start:#x}")

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    off = pe.get_offset_from_rva(start)
    ins = list(md.disasm(data[off : off + 0x600], start))
    # The pattern opens at the last `vmovsd xmm3, [rip+d]` (SecondsPerCycle)
    # before the first `mov eax, [rip+d]` (GGameThreadTime), and runs through
    # the GPU loop's `call [rax+slot]`.
    game = next((k for k, x in enumerate(ins) if x.bytes[:2] == b"\x8b\x05"), None)
    spc = [k for k, x in enumerate(ins[: game or 0]) if x.bytes[:4] == b"\xc5\xfb\x10\x1d"]
    first = spc[-1] if spc else None
    last = next((k for k, x in enumerate(ins) if x.bytes[:2] == b"\xff\x90"), None)
    if first is None or last is None:
        print("DrawStat no longer has the shape the C file expects; read it and update the offsets")
        return 1
    a = ins[first].address
    code = data[off + a - start : off + ins[last].address + ins[last].size - start]
    mask = [True] * len(code)
    loads, rhi, slot = [], None, None
    for x in ins[first : last + 1]:
        i = x.address - a
        mem = [op.mem.base for op in x.operands if op.type == x86.X86_OP_MEM]
        if x86.X86_REG_RIP in mem:
            for k in range(4):
                mask[i + x.disp_offset + k] = False
        if x.bytes[0] in (0xE8, 0xE9):
            for k in range(1, 5):
                mask[i + k] = False
        if x.mnemonic.startswith("j") and x.size > 2:
            for k in range(x.size - 4, x.size):
                mask[i + k] = False
        if x.bytes[:2] == b"\xff\x90":
            for k in range(2, 6):
                mask[i + k] = False
            slot = i
        if x.bytes[:2] == b"\x8b\x05":
            loads.append(i)
        if x.bytes[:3] == b"\x48\x8b\x0d":
            rhi = i
    vals = ["-1" if not m else f"0x{c:02X}" for c, m in zip(code, mask)]
    print(f"pattern ({len(vals)} bytes) from RVA {a:#x}:")
    for i in range(0, len(vals), 16):
        print("    " + ", ".join(vals[i : i + 16]) + ",")
    print("mov eax, [rip] loads (the first five: game, game_cp, draw, draw_cp, rhit): " + ", ".join(f"{x:#05x}" for x in loads))
    print(f"last mov rcx, [rip] (GDynamicRHI): {rhi:#05x}" if rhi is not None else "no GDynamicRHI load")
    print(f"call [rax+slot]: {slot:#05x}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

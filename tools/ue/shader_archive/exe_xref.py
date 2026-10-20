"""Read-only: find code that references a UTF-16 (or ANSI) string in the game exe, and disassemble around it.

    python exe_xref.py <exe> "<string>" [--ansi] [--before N] [--after N]

Used to tell which PipelineStateCache.cpp fatal (graphics or compute) carries line 551 in 343's build.
"""
import argparse
import struct

import capstone
import pefile


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("exe")
    ap.add_argument("text")
    ap.add_argument("--ansi", action="store_true")
    ap.add_argument("--before", type=int, default=160)
    ap.add_argument("--after", type=int, default=96)
    a = ap.parse_args()

    pe = pefile.PE(a.exe, fast_load=True)
    data = open(a.exe, "rb").read()
    base = pe.OPTIONAL_HEADER.ImageBase
    needle = a.text.encode("latin1") if a.ansi else a.text.encode("utf-16-le")
    targets = []
    p = data.find(needle)
    while p >= 0:
        rva = pe.get_rva_from_offset(p)
        if rva is not None:
            targets.append(rva)
        p = data.find(needle, p + 1)
    print("string RVAs:", [hex(t) for t in targets])
    tset = set(targets)

    text = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".text")
    tdata = text.get_data()
    tva = text.VirtualAddress
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    # lea r64, [rip+disp32]: REX.W(48|4C) 8D modrm(mod=00, rm=101)
    for i in range(len(tdata) - 7):
        if tdata[i] in (0x48, 0x4C) and tdata[i + 1] == 0x8D and (tdata[i + 2] & 0xC7) == 0x05:
            disp = struct.unpack_from("<i", tdata, i + 3)[0]
            tgt = tva + i + 7 + disp
            if tgt in tset:
                site = tva + i
                print(f"\n=== xref at RVA {site:#x} (VA {base + site:#x}) -> {tgt:#x}")
                s = max(0, i - a.before)
                for ins in md.disasm(tdata[s:i + a.after], base + tva + s):
                    mark = "  <==" if ins.address == base + site else ""
                    print(f"  {ins.address:#x}: {ins.mnemonic} {ins.op_str}{mark}")


if __name__ == "__main__":
    main()

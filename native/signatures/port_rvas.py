"""Find the Steam exe's functions and globals in another build of the game.

The native mods call into HaloCampaignEvolved.exe at fixed RVAs, measured on
the Steam build. The Xbox app ships its own exe of the same version (other
RVAs, same engine code), and every game update moves them all. This finds
each one again by its code:

- a function: its bytes, with every rel32 branch target and RIP-relative
  displacement wildcarded, are searched for in the other build's .text, and
  the hit is checked instruction by instruction over the whole function;
- a global (`g<rva>`): every function that references it is found the same
  way, and the global's new address read back from the matching instruction.

    python -P port_rvas.py <steam exe> <other image> [--dump] <rva> | g<rva> ...

`<other image>` is a file on disk, or with --dump a memory image of the
running game (the Xbox app's exe cannot be read on disk; docs/game_pass.md
has the dump recipe). Needs capstone and numpy.
"""
import re
import struct
import sys

import numpy as np
from capstone import CS_ARCH_X86, CS_MODE_64, Cs
from capstone import x86_const as X

md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True


def load(path, dumped):
    """(image laid out by RVA, sections, .pdata function table)"""
    raw = open(path, "rb").read()
    e = struct.unpack_from("<I", raw, 0x3C)[0]
    nsec = struct.unpack_from("<H", raw, e + 6)[0]
    optsz = struct.unpack_from("<H", raw, e + 20)[0]
    size = struct.unpack_from("<I", raw, e + 24 + 56)[0]
    secs = []
    for i in range(nsec):
        name, vsz, va, rsz, rptr = struct.unpack_from("<8sIIII", raw, e + 24 + optsz + 40 * i)
        secs.append((name.rstrip(b"\0").decode(), va, vsz, rsz, rptr))
    if dumped:
        img = bytearray(raw)
    else:
        img = bytearray(size)
        img[:0x1000] = raw[:0x1000]
        for _, va, vsz, rsz, rptr in secs:
            img[va:va + min(vsz, rsz)] = raw[rptr:rptr + min(vsz, rsz)]
    pd = next(s for s in secs if s[0] == ".pdata")
    fns = np.frombuffer(bytes(img[pd[1]:pd[1] + pd[2] // 12 * 12]), dtype="<u4").reshape(-1, 3)
    return img, secs, fns[fns[:, 0] != 0]


def text(image):
    img, secs, _ = image
    t = next(s for s in secs if s[0] == ".text")
    return t[1], bytes(img[t[1]:t[1] + t[2]])


def func_bounds(fns, rva):
    i = np.searchsorted(fns[:, 0], rva, side="right") - 1
    return int(fns[i, 0]), int(fns[i, 1])


def masked(img, start, end):
    """The code, a keep-mask (1 = compare), and the instructions."""
    code = bytes(img[start:end])
    mask = bytearray(b"\1" * len(code))
    insns = []
    for ins in md.disasm(code, start):
        off = ins.address - start
        insns.append(ins)
        if ins.disp_offset and any(op.type == X.X86_OP_MEM and op.mem.base == X.X86_REG_RIP for op in ins.operands):
            mask[off + ins.disp_offset:off + ins.disp_offset + ins.disp_size] = b"\0" * ins.disp_size
        if (ins.group(X.X86_GRP_JUMP) or ins.group(X.X86_GRP_CALL)) and ins.imm_offset and ins.imm_size == 4:
            mask[off + ins.imm_offset:off + ins.imm_offset + 4] = b"\0" * 4
    return code, mask, insns


def find(steam, other, rva):
    """The other build's RVAs for the Steam RVA, by its function's code."""
    start, end = func_bounds(steam[2], rva)
    code, mask, _ = masked(steam[0], start, end)
    base, hay = text(other)
    starts = set(int(x) for x in other[2][:, 0])
    hits = []
    for n in (32, 64, 128, 256, len(code)):
        n = min(n, len(code))
        rx = re.compile(b"".join(re.escape(code[i:i + 1]) if mask[i] else b"." for i in range(n)), re.S)
        hits = [m.start() + base for m in rx.finditer(hay)]
        hits = [h for h in hits if h in starts] or hits
        if len(hits) <= 1 or n == len(code):
            break
    return [h + rva - start for h in hits]


def same_code(steam, other, rva, port):
    """Whether the two functions agree mnemonic for mnemonic, whole."""
    fs, fe = func_bounds(steam[2], rva)
    gs, ge = func_bounds(other[2], port)
    a = masked(steam[0], fs, fe)[2]
    b = masked(other[0], gs, ge)[2]
    return len(a) == len(b) and all(x.mnemonic == y.mnemonic for x, y in zip(a, b))


def refs_to(image, target):
    """RVAs of RIP-relative displacements in .text that resolve to target."""
    base, hay = text(image)
    a = np.frombuffer(hay, dtype=np.uint8)
    disp = (a[:-8].astype(np.int64) | a[1:-7].astype(np.int64) << 8 |
            a[2:-6].astype(np.int64) << 16 | a[3:-5].astype(np.int64) << 24)
    disp = np.where(disp >= 1 << 31, disp - (1 << 32), disp)
    pos = np.arange(len(disp), dtype=np.int64) + base
    out = set()
    for tail in (0, 1, 4):  # bytes of immediate after the displacement
        out.update(int(pos[h]) for h in np.nonzero(pos + 4 + tail + disp == target)[0])
    return sorted(out)


def port_global(steam, other, target):
    """{other build's RVA: functions that agree on it}"""
    results = {}
    for dpos in refs_to(steam, target)[:40]:
        fs, fe = func_bounds(steam[2], dpos)
        insns = masked(steam[0], fs, fe)[2]
        idx = next((i for i, ins in enumerate(insns) if ins.address <= dpos < ins.address + ins.size), None)
        hits = find(steam, other, fs)
        if idx is None or len(hits) != 1:
            continue
        oins = masked(other[0], hits[0], hits[0] + (fe - fs) + 64)[2]
        if idx >= len(oins) or insns[idx].mnemonic != oins[idx].mnemonic:
            continue
        mem = [op for op in oins[idx].operands if op.type == X.X86_OP_MEM and op.mem.base == X.X86_REG_RIP]
        if mem:
            value = oins[idx].address + oins[idx].size + mem[0].mem.disp
            results.setdefault(value, []).append(fs)
    return results


def main(argv):
    dumped = "--dump" in argv
    argv = [a for a in argv if a != "--dump"]
    if len(argv) < 3:
        sys.exit(__doc__)
    steam, other = load(argv[0], False), load(argv[1], dumped)
    for arg in argv[2:]:
        if arg.startswith("g"):
            target = int(arg[1:], 16)
            found = port_global(steam, other, target)
            print("global %08x -> %s" % (target, ", ".join("%08x (%d functions agree)" % (k, len(v))
                                                          for k, v in found.items()) or "not found"))
        else:
            rva = int(arg, 16)
            hits = find(steam, other, rva)
            if len(hits) == 1:
                check = "whole function matches" if same_code(steam, other, rva, hits[0]) else "BODY DIFFERS"
                print("function %08x -> %08x (%s)" % (rva, hits[0], check))
            else:
                print("function %08x -> %d hits: %s" % (rva, len(hits), " ".join("%08x" % h for h in hits[:8])))


if __name__ == "__main__":
    main(sys.argv[1:])

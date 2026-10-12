"""Summarise what a DXIL shader reads and writes, per resource binding, from `dxc -dumpbin` text.

    python dxil_reads.py <dump.txt> [<dump2.txt>]

Per binding (class/space/register): the resource kind and stride from annotateHandle, the constant
byte offsets read from structured/raw buffers (rawBufferLoad / bufferLoad; an offset that is a
computed value prints as '?'), the cbuffer rows read (cbufferLoadLegacy), and the store/atomic ops
on UAVs. With two dumps, prints both side by side so a fork shader and ours can be compared.
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

CLS = {0: "SRV", 1: "UAV", 2: "CBV", 3: "Sampler"}

RE_BIND = re.compile(r"%(\w+) = call %dx\.types\.Handle @dx\.op\.createHandleFromBinding\(i32 217, %dx\.types\.ResBind "
                     r"(?:\{ i32 (\d+), i32 (\d+), i32 (\d+), i8 (\d+) \}|zeroinitializer)")
RE_ANN = re.compile(r"%(\w+) = call %dx\.types\.Handle @dx\.op\.annotateHandle\(i32 216, %dx\.types\.Handle %(\w+), "
                    r"%dx\.types\.ResourceProperties \{ i32 (-?\d+), i32 (-?\d+) \}\).*resource: (.*)$")
RE_CALL = re.compile(r"@dx\.op\.(\w+)\.?[\w.]*\(i32 \d+, %dx\.types\.Handle %(\w+)(.*)\)")


def parse(path: Path):
    text = path.read_text(errors="replace").splitlines()
    binding: dict[str, tuple] = {}
    ann: dict[str, tuple] = {}
    kinds: dict[tuple, str] = {}
    reads: dict[tuple, set] = defaultdict(set)
    ops: dict[tuple, dict] = defaultdict(lambda: defaultdict(int))
    for line in text:
        m = RE_BIND.search(line)
        if m:
            if m.group(2) is None:
                binding[m.group(1)] = (0, 0, 0)  # SRV t0 space0
            else:
                lo, _hi, space, cls = map(int, m.group(2, 3, 4, 5))
                binding[m.group(1)] = (cls, space, lo)
            continue
        m = RE_ANN.search(line)
        if m:
            src = m.group(2)
            key = binding.get(src) or ann.get(src, (None,))[0]
            ann[m.group(1)] = (key,)
            kinds[key] = m.group(5).strip()
            continue
        m = RE_CALL.search(line.split(";")[0])
        if not m:
            continue
        op, h, rest = m.groups()
        key = ann.get(h, (binding.get(h),))[0]
        if key is None:
            continue
        args = [a.strip() for a in rest.lstrip(",").split(",")]
        if op in ("rawBufferLoad", "bufferLoad"):
            # (handle, index, offset, mask, align) for raw/structured
            idx = args[0] if args else "?"
            off = args[1] if len(args) > 1 else "?"
            offc = off.split()[-1] if off.startswith("i32 ") and off.split()[-1].lstrip("-").isdigit() else "?"
            reads[key].add(offc if not offc == "?" else f"?[{idx.split()[-1]}+{off.split()[-1]}]")
            ops[key][op] += 1
        elif op == "cbufferLoadLegacy":
            row = args[0].split()[-1] if args else "?"
            reads[key].add(f"row{row}" if row.isdigit() else f"row?{row}")
            ops[key][op] += 1
        else:
            ops[key][op] += 1
    return kinds, reads, ops


def key_str(k):
    if k is None:
        return "?"
    cls, space, reg = k
    letter = {0: "t", 1: "u", 2: "b", 3: "s"}[cls]
    return f"{CLS[cls]} {letter}{reg} space{space}"


def sort_reads(s):
    def k(x):
        if x.isdigit():
            return (0, int(x), "")
        if x.startswith("row") and x[3:].isdigit():
            return (1, int(x[3:]), "")
        return (2, 0, x)
    return sorted(s, key=k)


def main():
    paths = [Path(p) for p in sys.argv[1:]]
    parsed = [parse(p) for p in paths]
    keys = sorted({k for kinds, _, _ in parsed for k in kinds if k is not None})
    for k in keys:
        print(f"== {key_str(k)}")
        for p, (kinds, reads, ops) in zip(paths, parsed):
            consts = [x for x in sort_reads(reads.get(k, set())) if not x.startswith("?")]
            dyn = len([x for x in reads.get(k, set()) if x.startswith("?")])
            print(f"   {p.stem[:16]:16s} {kinds.get(k, '-'):40s} ops={dict(ops.get(k, {}))}")
            if consts or dyn:
                print(f"      const offsets/rows: {' '.join(consts)}  (+{dyn} computed)")


if __name__ == "__main__":
    main()

"""Resolve Blam tag-block maximum counts out of a PE image.

Read-only helper for evidence gathering. The simulation DLL ships its tag block
definitions as data, laid out as:

    [ block_name_ptr ][ max_element_count ][ max_count_name_ptr ]

so a compiled limit like ``k_maximum_campaign_players`` can be turned back into a
number: find the string, find the single 8-byte pointer that references it, and
read the two qwords immediately before it.

That is how ``docs/coop_player_cap.md`` established that
``k_maximum_campaign_players == 4`` while the players datum array holds 32. Offsets
move on every content update, which is why this resolves by name rather than by
hardcoded address.

Usage:
    python pe_blocks.py <image.dll> --name "k_maximum_campaign_players"
    python pe_blocks.py <image.dll> --pattern "k_maximum|MAXIMUM" --filter player
    python pe_blocks.py <image.dll> --xref "some_string"
"""

from __future__ import annotations

import argparse
import re
import struct
from pathlib import Path


class PEImage:
    """Minimal PE32+ section table — enough to map file offsets to virtual addresses."""

    def __init__(self, path: Path) -> None:
        self.data = path.read_bytes()
        d = self.data
        e_lfanew = struct.unpack_from("<I", d, 0x3C)[0]
        if d[e_lfanew : e_lfanew + 4] != b"PE\0\0":
            raise ValueError("not a PE image")

        coff = e_lfanew + 4
        n_sections = struct.unpack_from("<H", d, coff + 2)[0]
        opt_size = struct.unpack_from("<H", d, coff + 16)[0]
        opt = coff + 20
        if struct.unpack_from("<H", d, opt)[0] != 0x20B:
            raise ValueError("PE32+ (64-bit) images only")

        self.image_base = struct.unpack_from("<Q", d, opt + 24)[0]
        table = opt + opt_size
        self.sections = []
        for i in range(n_sections):
            o = table + i * 40
            name = d[o : o + 8].rstrip(b"\0").decode("ascii", "replace")
            vsize, vaddr, rsize, raddr = struct.unpack_from("<IIII", d, o + 8)
            self.sections.append((name, vaddr, vsize, raddr, rsize))

    def off_to_va(self, off: int) -> int | None:
        for _, vaddr, _, raddr, rsize in self.sections:
            if raddr <= off < raddr + rsize:
                return self.image_base + vaddr + (off - raddr)
        return None

    def va_to_off(self, va: int) -> int | None:
        rva = va - self.image_base
        for _, vaddr, vsize, raddr, rsize in self.sections:
            if vaddr <= rva < vaddr + max(vsize, rsize):
                off = raddr + (rva - vaddr)
                if off < raddr + rsize:
                    return off
        return None

    def cstring(self, va: int, limit: int = 200) -> str | None:
        off = self.va_to_off(va)
        if off is None:
            return None
        end = self.data.find(b"\0", off, off + limit)
        if end == -1:
            return None
        try:
            return self.data[off:end].decode("ascii")
        except UnicodeDecodeError:
            return None

    def find_all(self, needle: bytes):
        i = self.data.find(needle)
        while i != -1:
            yield i
            i = self.data.find(needle, i + 1)

    def xrefs(self, va: int) -> list[int]:
        """File offsets of every 8-byte pointer holding `va`."""
        return list(self.find_all(struct.pack("<Q", va)))


def resolve_block(pe: PEImage, name: str) -> list[tuple[str, int, int]]:
    """Every (block_name, max_count, xref_off) for a max-count identifier."""
    results = []
    for off in pe.find_all(name.encode("ascii") + b"\0"):
        va = pe.off_to_va(off)
        if va is None:
            continue
        for x in pe.xrefs(va):
            if x < 16:
                continue
            max_count = struct.unpack_from("<Q", pe.data, x - 8)[0]
            block_ptr = struct.unpack_from("<Q", pe.data, x - 16)[0]
            block = pe.cstring(block_ptr)
            # A real definition has a plausible count and a readable sibling name;
            # anything else is a coincidental pointer and is dropped.
            if block and block.isprintable() and 0 < max_count < 0x100000:
                results.append((block, max_count, x))
    return results


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("image", type=Path)
    ap.add_argument("--name", action="append", default=[], help="exact max-count identifier")
    ap.add_argument("--pattern", help="regex matching max-count identifiers to resolve")
    ap.add_argument("--filter", help="only report rows whose block or identifier matches this regex")
    ap.add_argument("--xref", help="report data xrefs to an exact string, with surrounding qwords")
    args = ap.parse_args()

    pe = PEImage(args.image)
    print(f"# image base {pe.image_base:#x}, {len(pe.sections)} sections")

    if args.xref:
        for off in pe.find_all(args.xref.encode("ascii") + b"\0"):
            va = pe.off_to_va(off)
            if va is None:
                continue
            for x in pe.xrefs(va):
                print(f"\n# xref at {x:#x} -> {args.xref!r} ({va:#x})")
                for i in range(x - 32, x + 32, 8):
                    if not 0 <= i < len(pe.data) - 8:
                        continue
                    q = struct.unpack_from("<Q", pe.data, i)[0]
                    s = pe.cstring(q) if pe.image_base < q < pe.image_base + (1 << 32) else None
                    mark = " <<<" if i == x else ""
                    print(f"  {i - x:+5d}  {q:#018x}  {s or ''}{mark}")
        return 0

    names = list(args.name)
    if args.pattern:
        rx = re.compile(args.pattern.encode("ascii"))
        for m in re.finditer(rb"[A-Za-z_][A-Za-z0-9_:+\-]{3,90}\x00", pe.data):
            ident = m.group()[:-1]
            if rx.search(ident):
                names.append(ident.decode("ascii"))

    row_filter = re.compile(args.filter, re.IGNORECASE) if args.filter else None
    seen: set[tuple[str, str]] = set()
    rows = 0
    for name in names:
        for block, max_count, _ in resolve_block(pe, name):
            key = (name, block)
            if key in seen:
                continue
            seen.add(key)
            if row_filter and not (row_filter.search(name) or row_filter.search(block)):
                continue
            print(f"{max_count:>8}  {name:<58} {block}")
            rows += 1
    print(f"# {rows} block definitions resolved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

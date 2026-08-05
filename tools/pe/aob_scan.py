"""Check the UE4SS signature overrides in `signatures/` against a game build.

UE4SS finds engine internals by array-of-bytes scan. When the game updates, a
signature either still matches exactly once, matches nothing (UE4SS fails loudly),
or matches several places (UE4SS picks one, and the failure is a mystery crash
later). Only the first is safe, and nothing in the normal workflow checks for it
until someone launches the game.

This reads each `signatures/*.lua`, extracts the pattern from its `Register()`,
and reports the match count against a build's executable code. Run it after every
game update, before trusting the signatures.

Exit status is nonzero if any signature does not match exactly once.

Usage:
    python tools/pe/aob_scan.py "<Win64>/HaloCampaignEvolved.exe"
    python tools/pe/aob_scan.py "<exe>" --signatures signatures --verbose
"""

from __future__ import annotations

import argparse
import re
import struct
import sys
from pathlib import Path

REGISTER_RE = re.compile(r"return\s+\"([0-9A-Fa-f?\s]+)\"")


def parse_sections(data: bytes):
    """(name, virtual_address, raw_offset, raw_size) for each PE section."""
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    if data[e_lfanew : e_lfanew + 4] != b"PE\0\0":
        raise ValueError("not a PE image")
    coff = e_lfanew + 4
    n_sections = struct.unpack_from("<H", data, coff + 2)[0]
    opt_size = struct.unpack_from("<H", data, coff + 16)[0]
    opt = coff + 20
    image_base = struct.unpack_from("<Q", data, opt + 24)[0]
    table = opt + opt_size

    sections = []
    for i in range(n_sections):
        o = table + i * 40
        name = data[o : o + 8].rstrip(b"\0").decode("ascii", "replace")
        _vsize, vaddr, rsize, raddr = struct.unpack_from("<IIII", data, o + 8)
        sections.append((name, vaddr, raddr, rsize))
    return image_base, sections


def pattern_to_regex(pattern: str) -> bytes:
    """AOB text ('48 8B ? ?? C3') to a byte regex. '?' and '??' are one wildcard byte."""
    out = []
    for token in pattern.split():
        if set(token) <= {"?"}:
            out.append(b".")
        else:
            out.append(re.escape(bytes([int(token, 16)])))
    return b"".join(out)


def read_signature(path: Path) -> str | None:
    match = REGISTER_RE.search(path.read_text(encoding="utf-8"))
    return match.group(1).strip() if match else None


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("image", type=Path)
    ap.add_argument("--signatures", type=Path, default=Path("signatures"))
    ap.add_argument("--verbose", action="store_true", help="print every match address")
    args = ap.parse_args()

    data = args.image.read_bytes()
    image_base, sections = parse_sections(data)
    text = next((s for s in sections if s[0] == ".text"), None)
    if text is None:
        print("error: no .text section", file=sys.stderr)
        return 2
    _, text_vaddr, text_raddr, text_rsize = text
    code = data[text_raddr : text_raddr + text_rsize]

    files = sorted(args.signatures.glob("*.lua"))
    if not files:
        print(f"error: no signatures found in {args.signatures}", file=sys.stderr)
        return 2

    print(f"# {args.image.name}  image base {image_base:#x}  .text {len(code):,} bytes")
    failures = 0
    for path in files:
        pattern = read_signature(path)
        if pattern is None:
            print(f"SKIP     {path.name}: no Register() pattern found")
            continue

        matches = [m.start() for m in re.finditer(pattern_to_regex(pattern), code, re.DOTALL)]
        count = len(matches)
        # Exactly one match is the only outcome UE4SS resolves deterministically.
        status = "OK" if count == 1 else ("NO MATCH" if count == 0 else f"AMBIGUOUS x{count}")
        if count != 1:
            failures += 1

        detail = ""
        if matches and (args.verbose or count == 1):
            shown = matches[:4]
            addrs = " ".join(f"{image_base + text_vaddr + m:#x}" for m in shown)
            detail = f"  va {addrs}" + (" ..." if len(matches) > len(shown) else "")
            if count == 1:
                detail += f"  rva {text_vaddr + matches[0]:#x}"
        print(f"{status:<14} {path.stem}{detail}")

    print(f"# {len(files) - failures}/{len(files)} signatures resolve uniquely")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Extract and filter printable strings from a PE image.

Read-only helper for evidence gathering. Prints matches only; the caller decides
what to record. Nothing proprietary is written to the repository.

Usage:
    python pe_strings.py <image.exe> --match "regex" [--min 6] [--limit 200]
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", type=Path)
    ap.add_argument("--match", action="append", default=[], help="regex the string must match (case-insensitive)")
    ap.add_argument("--min", type=int, default=6)
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--count-only", action="store_true")
    args = ap.parse_args()

    blob = args.image.read_bytes()
    pattern = re.compile(rb"[\x20-\x7E]{%d,}" % args.min)
    matchers = [re.compile(m, re.IGNORECASE) for m in args.match]

    seen: set[str] = set()
    for m in pattern.finditer(blob):
        s = m.group().decode("ascii")
        if s in seen:
            continue
        if matchers and not any(r.search(s) for r in matchers):
            continue
        seen.add(s)

    print(f"# {len(seen)} unique matches")
    if args.count_only:
        return 0
    for s in sorted(seen)[: args.limit]:
        print(s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

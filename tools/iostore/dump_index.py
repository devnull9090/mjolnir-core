"""Enumerate IoStore container indexes for evidence-based analysis.

Examples
--------
List container headers only:
    python dump_index.py --paks "<game>\\Meteorite\\Content\\Paks" --summary

Write every indexed path with its chunk type and size:
    python dump_index.py --paks "<paks>" --out out\\iostore_paths.tsv

Filter to a subtree:
    python dump_index.py --paks "<paks>" --filter "tags/" --out out\\tags.tsv

Inspect the first bytes of one entry (no bulk extraction):
    python dump_index.py --paks "<paks>" --peek "Meteorite/Content/Tags/foo.bar" --peek-bytes 64
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from iostore import Container, TocError, load_container, read_chunk  # noqa: E402


def iter_containers(paks: Path):
    for utoc in sorted(paks.glob("*.utoc")):
        try:
            yield load_container(utoc)
        except TocError as exc:
            print(f"[skip] {utoc.name}: {exc}", file=sys.stderr)


def summarize(container: Container) -> str:
    return (
        f"{container.utoc_path.name}\t"
        f"ver={container.version}\t"
        f"flags={'|'.join(container.flag_names())}\t"
        f"methods={','.join(container.compression_methods)}\t"
        f"chunks={len(container.chunks)}\t"
        f"indexed_files={len(container.files)}\t"
        f"mount={container.mount_point}"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--paks", required=True, type=Path, help="directory containing *.utoc")
    ap.add_argument("--out", type=Path, help="TSV output path for the file listing")
    ap.add_argument("--filter", default="", help="case-insensitive substring the path must contain")
    ap.add_argument("--summary", action="store_true", help="print container headers only")
    ap.add_argument("--ext-stats", action="store_true", help="print a per-extension count")
    ap.add_argument("--peek", help="exact indexed path to read the leading bytes of")
    ap.add_argument("--peek-bytes", type=int, default=64)
    ap.add_argument("--oodle", type=Path, action="append", default=[], help="oo2core dll or a dir to search")
    args = ap.parse_args()

    containers = list(iter_containers(args.paks))
    if not containers:
        print("no readable containers", file=sys.stderr)
        return 1

    for c in containers:
        print(summarize(c))
    if args.summary:
        return 0

    needle = args.filter.lower()
    rows: list[tuple[str, str, str, int, int]] = []
    ext_counter: Counter[str] = Counter()

    for c in containers:
        for path, chunk_index in sorted(c.files.items()):
            full = f"{c.mount_point}{path}" if c.mount_point else path
            if needle and needle not in full.lower():
                continue
            chunk = c.chunks[chunk_index]
            rows.append((full, c.utoc_path.name, chunk.type_name, chunk.length, chunk_index))
            ext_counter[Path(full).suffix.lower() or "<none>"] += 1

    print(f"\nmatched {len(rows)} indexed entries (filter={args.filter!r})")

    if args.ext_stats:
        print("\nextension\tcount")
        for ext, count in ext_counter.most_common():
            print(f"{ext}\t{count}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write("path\tcontainer\tchunk_type\tsize\tchunk_index\n")
            for row in rows:
                fh.write("\t".join(str(v) for v in row) + "\n")
        print(f"wrote {args.out}")

    if args.peek:
        target = args.peek.lower()
        found = False
        for c in containers:
            for path, chunk_index in c.files.items():
                full = f"{c.mount_point}{path}" if c.mount_point else path
                if full.lower() != target:
                    continue
                found = True
                chunk = c.chunks[chunk_index]
                data = read_chunk(c, chunk, args.peek_bytes, args.oodle)
                print(f"\n{full}")
                print(f"  container={c.utoc_path.name} type={chunk.type_name} size={chunk.length}")
                print(f"  hex={data.hex(' ')}")
                printable = "".join(chr(b) if 32 <= b < 127 else "." for b in data)
                print(f"  ascii={printable}")
                break
            if found:
                break
        if not found:
            print(f"peek target not found: {args.peek}", file=sys.stderr)
            return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

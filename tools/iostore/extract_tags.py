"""Dump packaged Blam tag payloads from a local Halo Campaign Evolved install.

Each `Content/Tags/**/<name>-<group>.ubulk` chunk is a standalone Blam tag file.
This writes them back out as `<name>.<group>`, which is the layout Blam tooling
expects.

Legal / scope note: this operates on the caller's own installed copy for research
purposes. The extracted data is copyrighted game content. Do not redistribute the
output, and keep it out of source control.

Usage:
    python extract_tags.py --paks "<...>\\Content\\Paks" \
        --oodle "<...>\\oo2core_9_win64.dll" --out D:\\tagdump \
        [--filter objects/characters] [--group weapon --group vehicle] [--limit 50] [--dry-run]
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from iostore import load_container, read_chunk  # noqa: E402

BLAM_SIGNATURE_OFFSET = 0x3C
BLAM_SIGNATURE = b"MALB"  # 'BLAM' stored as a little-endian uint32
TAG_HEADER_SIZE = 0x4C
PAYLOAD_SIZE_OFFSET = 0x48


def split_group(stem: str) -> tuple[str, str]:
    if "-" not in stem:
        return stem, ""
    name, group = stem.rsplit("-", 1)
    return name, group


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--paks", required=True, type=Path)
    ap.add_argument("--oodle", required=True, type=Path)
    ap.add_argument("--out", type=Path, help="output root (required unless --dry-run)")
    ap.add_argument("--filter", default="", help="case-insensitive substring of the tag path")
    ap.add_argument("--group", action="append", default=[], help="restrict to these tag groups")
    ap.add_argument("--limit", type=int, default=0, help="stop after N tags (0 = no limit)")
    ap.add_argument("--dry-run", action="store_true", help="list what would be written")
    ap.add_argument("--verify", action="store_true", help="reject payloads without the BLAM signature")
    args = ap.parse_args()

    if not args.dry_run and not args.out:
        ap.error("--out is required unless --dry-run is set")

    needle = args.filter.lower()
    groups = {g.lower() for g in args.group}

    targets = []
    for utoc in sorted(args.paks.glob("*.utoc")):
        try:
            container = load_container(utoc)
        except Exception:
            continue
        for path, chunk_index in container.files.items():
            full = f"{container.mount_point}{path}" if container.mount_point else path
            if "/Tags/" not in full or not full.endswith(".ubulk"):
                continue
            if needle and needle not in full.lower():
                continue
            rel = full.split("/Tags/", 1)[1]
            name, group = split_group(Path(rel).stem)
            if not group or (groups and group.lower() not in groups):
                continue
            out_rel = Path(rel).parent / f"{name}.{group}"
            targets.append((container, container.chunks[chunk_index], out_rel))

    targets.sort(key=lambda t: str(t[2]))
    if args.limit:
        targets = targets[: args.limit]

    total_bytes = sum(chunk.length for _, chunk, _ in targets)
    print(f"tags matched: {len(targets)}  ({total_bytes / 1024 / 1024:.1f} MiB)")

    if args.dry_run:
        for _, chunk, out_rel in targets[:50]:
            print(f"  {out_rel}\t{chunk.length}")
        if len(targets) > 50:
            print(f"  ... {len(targets) - 50} more")
        return 0

    written = 0
    rejected = 0
    for container, chunk, out_rel in targets:
        data = read_chunk(container, chunk, None, [args.oodle])
        if args.verify:
            ok = (
                len(data) >= TAG_HEADER_SIZE
                and data[BLAM_SIGNATURE_OFFSET : BLAM_SIGNATURE_OFFSET + 4] == BLAM_SIGNATURE
                and struct.unpack_from("<I", data, PAYLOAD_SIZE_OFFSET)[0] + TAG_HEADER_SIZE == len(data)
            )
            if not ok:
                rejected += 1
                print(f"  [reject] {out_rel}", file=sys.stderr)
                continue
        dest = args.out / out_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        written += 1
        if written % 500 == 0:
            print(f"  ... {written}/{len(targets)}")

    print(f"wrote {written} tags to {args.out}")
    if rejected:
        print(f"rejected {rejected} payloads that failed the BLAM header check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

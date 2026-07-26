"""Sample packaged Blam tag payloads and report their container header fields.

This reads only the leading bytes of a small sample of `Tags/**.ubulk` entries in
order to test one specific claim: that the shipped payload is a Blam tag file
rather than an Unreal asset. Nothing is written to disk.

Usage:
    python inspect_tags.py --paks "<...>\\Content\\Paks" \
        --oodle "<...>\\oo2core_9_win64.dll" [--per-group 2] [--header 96]
"""

from __future__ import annotations

import argparse
import struct
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from iostore import load_container  # noqa: E402
from iostore import read_chunk  # noqa: E402

# Field offsets recovered from the Elite biped payload and re-tested per group.
OFF_GROUP = 0x30
OFF_GROUP_COUNT = 0x34
OFF_CHECKSUM = 0x38
OFF_BLAM = 0x3C
OFF_TAG_BANG = 0x40
OFF_PAYLOAD_SIZE = 0x48
HEADER_SIZE = 0x4C


def fourcc(buf: bytes, offset: int) -> str:
    raw = buf[offset : offset + 4][::-1]
    return "".join(chr(b) if 32 <= b < 127 else "?" for b in raw)


def group_from_name(name: str) -> str:
    stem = Path(name).stem
    return stem.rsplit("-", 1)[-1] if "-" in stem else ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--paks", required=True, type=Path)
    ap.add_argument("--oodle", required=True, type=Path)
    ap.add_argument("--per-group", type=int, default=2)
    ap.add_argument("--header", type=int, default=HEADER_SIZE + 16)
    ap.add_argument("--hexdump", help="print raw hex for this group name only")
    args = ap.parse_args()

    by_group: dict[str, list[tuple[object, object, str]]] = defaultdict(list)
    containers = []
    for utoc in sorted(args.paks.glob("*.utoc")):
        try:
            c = load_container(utoc)
        except Exception:
            continue
        containers.append(c)
        for path, chunk_index in c.files.items():
            full = f"{c.mount_point}{path}" if c.mount_point else path
            if "/Tags/" not in full or not full.endswith(".ubulk"):
                continue
            group = group_from_name(full)
            if group:
                by_group[group].append((c, c.chunks[chunk_index], full))

    if not by_group:
        print("no Tags/**.ubulk entries found", file=sys.stderr)
        return 1

    print(f"tag groups discovered: {len(by_group)}")
    print(f"tag payloads discovered: {sum(len(v) for v in by_group.values())}")
    print()
    print("group_name\tfourcc\tgroup_count\tsig_3c\tsig_40\thdr+size==chunk\tsample")

    matches = 0
    total = 0
    for group in sorted(by_group):
        for container, chunk, path in sorted(by_group[group], key=lambda x: x[2])[: args.per_group]:
            data = read_chunk(container, chunk, args.header, [args.oodle])
            if len(data) < HEADER_SIZE:
                print(f"{group}\t<short payload {len(data)}>")
                continue
            cc = fourcc(data, OFF_GROUP)
            count = struct.unpack_from("<I", data, OFF_GROUP_COUNT)[0]
            sig1 = fourcc(data, OFF_BLAM)
            sig2 = fourcc(data, OFF_TAG_BANG)
            payload = struct.unpack_from("<I", data, OFF_PAYLOAD_SIZE)[0]
            consistent = (payload + HEADER_SIZE) == chunk.length
            total += 1
            if sig1 == "BLAM":
                matches += 1
            short = path.rsplit("/", 1)[-1]
            print(f"{group}\t{cc}\t{count}\t{sig1}\t{sig2}\t{consistent}\t{short}")

            if args.hexdump and group == args.hexdump:
                print(f"  raw[0:{args.header}] = {data.hex(' ')}")

    print()
    print(f"BLAM signature present in {matches}/{total} sampled payloads")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

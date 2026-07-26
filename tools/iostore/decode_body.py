"""Decode the Blam tag body that follows the 0x4C-byte container header.

`docs/tag_data_pipeline.md` maps the 0x4C container header exactly but records the
body as undecoded, noting group-invariant markers (`blay`, then `4444`, `CCCC`,
`wwww` in a weapon sample). This tool tests the leading hypothesis that `blay` is a
self-describing *blam layout* section, i.e. that the shipped tag files carry their
own struct table and can be parsed without recovering definitions from the engine.

Nothing is written to disk. Payloads are read into memory only.

Usage:
    python decode_body.py --paks "<...>\\Content\\Paks" \
        --oodle "<...>\\oo2core_9_win64.dll" --group weapon --hexdump 256
    python decode_body.py --paks ... --oodle ... --survey
"""

from __future__ import annotations

import argparse
import struct
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from iostore import Container, load_container, read_chunk  # noqa: E402

HEADER_SIZE = 0x4C
OFF_GROUP = 0x30
OFF_GROUP_VERSION = 0x34
OFF_PAYLOAD_SIZE = 0x48


def fourcc(buf: bytes, offset: int) -> str:
    raw = buf[offset : offset + 4][::-1]
    return "".join(chr(b) if 32 <= b < 127 else "." for b in raw)


def group_from_name(name: str) -> str:
    stem = Path(name).stem
    return stem.rsplit("-", 1)[-1] if "-" in stem else ""


def hexdump(data: bytes, base: int = 0, width: int = 16) -> str:
    lines = []
    for off in range(0, len(data), width):
        row = data[off : off + width]
        hexpart = " ".join(f"{b:02x}" for b in row).ljust(width * 3 - 1)
        asciipart = "".join(chr(b) if 32 <= b < 127 else "." for b in row)
        lines.append(f"  {base + off:08x}  {hexpart}  |{asciipart}|")
    return "\n".join(lines)


def walk_sections(body: bytes, base: int, start: int, end: int, depth: int, out: list) -> None:
    """Walk a chain of {magic:4CC, version:u32, size:u32} sections."""
    off = start
    while off + 12 <= end:
        magic = fourcc(body, off)
        if not all(c.isalnum() or c in "!*#_" for c in magic):
            break
        version, size = struct.unpack_from("<II", body, off + 4)
        if size < 12 or off + size > end:
            out.append((depth, off + base, magic, version, size, "SIZE OUT OF RANGE"))
            break
        out.append((depth, off + base, magic, version, size, ""))
        off += size


def scan_magics(body: bytes, base: int) -> list[tuple[int, str]]:
    """Brute-force scan for dword-aligned printable four-CCs that look like section tags."""
    hits = []
    for off in range(0, len(body) - 4, 4):
        raw = body[off : off + 4]
        if all(48 <= b <= 122 for b in raw):
            cc = fourcc(body, off)
            if cc.isalnum() and cc.islower() or cc in ("str*", "tgly", "blay"):
                hits.append((base + off, cc))
    return hits


def string_blob(body: bytes) -> tuple[int, bytes, dict[int, str]]:
    """Return (blob_start, blob, {offset: string}) for the str* section."""
    blob_size = struct.unpack_from("<I", body, 0x6C)[0]
    start = 0x70
    blob = body[start : start + blob_size]
    table: dict[int, str] = {}
    off = 0
    for part in blob.split(b"\0"):
        table[off] = part.decode("utf-8", "replace")
        off += len(part) + 1
    return start, blob, table


def annotate(body: bytes, start: int, count: int, table: dict[int, str], base: int) -> str:
    """Print a u32 stream, resolving values that are valid string offsets."""
    lines = []
    for i in range(count):
        off = start + i * 4
        if off + 4 > len(body):
            break
        val = struct.unpack_from("<I", body, off)[0]
        cc = fourcc(body, off)
        note = ""
        if val in table and table[val]:
            note = f"  -> {table[val]!r}"
        elif all(32 <= b < 127 for b in body[off : off + 4]):
            note = f"  cc={cc!r}"
        lines.append(f"  0x{base + off:08x}  [{i:>4}]  {val:>10}  0x{val:08x}{note}")
    return "\n".join(lines)


def collect_tags(paks: Path) -> tuple[list[Container], dict[str, list]]:
    by_group: dict[str, list] = defaultdict(list)
    containers = []
    for utoc in sorted(paks.glob("*.utoc")):
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
    return containers, by_group


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--paks", required=True, type=Path)
    ap.add_argument("--oodle", required=True, type=Path)
    ap.add_argument("--group", help="restrict to one group directory name, e.g. weapon")
    ap.add_argument("--per-group", type=int, default=1)
    ap.add_argument("--hexdump", type=int, default=0, help="hexdump this many body bytes")
    ap.add_argument("--at", type=lambda s: int(s, 0), default=None,
                    help="hexdump starting at this absolute payload offset")
    ap.add_argument("--sections", action="store_true", help="walk the blay/tgly section chain")
    ap.add_argument("--strings", type=int, default=0, help="print the first N string-table entries")
    ap.add_argument("--decode", type=int, default=0,
                    help="annotate N u32 words, resolving string-table offsets")
    ap.add_argument("--survey", action="store_true", help="tabulate the first body dwords per group")
    args = ap.parse_args()

    _, by_group = collect_tags(args.paks)
    if not by_group:
        print("no Tags/**.ubulk entries found", file=sys.stderr)
        return 1

    groups = [args.group] if args.group else sorted(by_group)
    full_read = (args.sections or args.strings or args.decode or args.survey
                 or args.at is not None)
    read_len = None if full_read else HEADER_SIZE + max(args.hexdump, 128)

    if args.survey:
        print("group\tfourcc\tver\tblay_ver\tblay_size\tstr_size\tnstr\tblob_end_sig\tw1\tw2")

    for group in groups:
        entries = by_group.get(group)
        if not entries:
            print(f"unknown group: {group}", file=sys.stderr)
            continue
        for container, chunk, path in sorted(entries, key=lambda x: x[2])[: args.per_group]:
            data = read_chunk(container, chunk, read_len, [args.oodle])
            if len(data) < HEADER_SIZE + 16:
                continue
            cc = fourcc(data, OFF_GROUP)
            ver = struct.unpack_from("<I", data, OFF_GROUP_VERSION)[0]
            body = data[HEADER_SIZE:]
            short = path.rsplit("/", 1)[-1]

            if args.survey:
                blay_ver, blay_size = struct.unpack_from("<II", body, 4)
                try:
                    blob_start, blob, table = string_blob(body)
                except Exception:
                    print(f"{group}\t{cc}\t{ver}\t<blob parse failed>")
                    continue
                end = blob_start + len(blob)
                sig = "".join(
                    chr(b) if 32 <= b < 127 else "." for b in body[end : end + 4]
                )
                w1, w2 = struct.unpack_from("<II", body, end + 4)
                print(f"{group}\t{cc}\t{ver}\t{blay_ver}\t0x{blay_size:x}\t"
                      f"0x{len(blob):x}\t{len(table)}\t{sig!r}\t{w1}\t{w2}")
                continue

            print(f"=== {group} ({cc}) v{ver} :: {short}")
            print(f"    chunk length {chunk.length}, payload size "
                  f"{struct.unpack_from('<I', data, OFF_PAYLOAD_SIZE)[0]}")

            if args.sections:
                blay_ver, blay_size = struct.unpack_from("<II", body, 4)
                print(f"    blay v{blay_ver} size 0x{blay_size:x} "
                      f"(ends 0x{HEADER_SIZE + blay_size:x})")
                print("    blay header dwords:")
                for i in range(0x0C, 0x58, 4):
                    val = struct.unpack_from("<I", body, i)[0]
                    print(f"      +0x{i:02x}  {val:>10}  0x{val:08x}  {fourcc(body, i)}")
                found: list = []
                walk_sections(body, HEADER_SIZE, 0x58, min(blay_size, len(body)), 0, found)
                print("    section chain:")
                for depth, addr, magic, version, size, note in found:
                    pad = "  " * depth
                    line = f"      {pad}0x{addr:08x}  {magic}  v{version:<4} size 0x{size:x}"
                    print(line + ("  " + note if note else ""))

            if args.strings:
                blob_size = struct.unpack_from("<I", body, 0x6C)[0]
                blob = body[0x70 : 0x70 + blob_size]
                parts = blob.split(b"\0")
                print(f"    str* blob 0x{blob_size:x} bytes, {len(parts)} entries")
                for i, s in enumerate(parts[: args.strings]):
                    print(f"      [{i:>4}] {s.decode('utf-8', 'replace')!r}")

            if args.decode:
                blob_start, blob, table = string_blob(body)
                blob_end = blob_start + len(blob)
                origin = args.at if args.at is not None else HEADER_SIZE + blob_end
                rel = origin - HEADER_SIZE
                print(f"    str* blob body[0x{blob_start:x}:0x{blob_end:x}] "
                      f"(file 0x{HEADER_SIZE + blob_start:x}-0x{HEADER_SIZE + blob_end:x}), "
                      f"{len(table)} strings")
                print(annotate(body, rel, args.decode, table, HEADER_SIZE))

            if args.hexdump:
                origin = args.at if args.at is not None else HEADER_SIZE
                rel = origin - HEADER_SIZE
                print(hexdump(body[rel : rel + args.hexdump], base=origin))
            print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

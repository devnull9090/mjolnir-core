"""Resolve the UClass of cooked IoStore (zen) packages.

Reads the global container's ScriptObjects chunk to build a
`FPackageObjectIndex -> /Script/... path` table, then parses a package header and
reports each export's name and resolved class. This answers "what Unreal type owns
this data" without extracting any asset payload.

Usage:
    python zen_class.py --paks "<...>\\Content\\Paks" --oodle "<...>\\oo2core_9_win64.dll" \
        --package "../../../Meteorite/Content/Tags/objects/Characters/Elite/elite-biped.uasset"
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from iostore import CHUNK_TYPES, load_container, read_chunk  # noqa: E402

TYPE_EXPORT = 0
TYPE_SCRIPT_IMPORT = 1
TYPE_PACKAGE_IMPORT = 2
TYPE_NULL = 3

INDEX_TYPE_SHIFT = 62
INDEX_MASK = (1 << 62) - 1
NULL_INDEX = 0xFFFFFFFFFFFFFFFF

EXPORT_MAP_ENTRY_SIZE = 72

# FMappedName packs a 2-bit namespace type above a 30-bit index.
NAME_INDEX_MASK = (1 << 30) - 1


def mapped_name(names: list[str], packed_index: int, number: int) -> str:
    index = packed_index & NAME_INDEX_MASK
    name = names[index] if index < len(names) else f"<name:{index}>"
    return f"{name}_{number - 1}" if number else name


def load_name_batch(buf: bytes, pos: int) -> tuple[list[str], int]:
    count, string_bytes = struct.unpack_from("<ii", buf, pos)
    pos += 8
    if count == 0:
        return [], pos
    pos += 8  # hash version
    pos += 8 * count  # hashes
    headers = []
    for _ in range(count):
        b0, b1 = buf[pos], buf[pos + 1]
        headers.append((bool(b0 & 0x80), ((b0 & 0x7F) << 8) | b1))
        pos += 2
    names = []
    for is_utf16, length in headers:
        if is_utf16:
            raw = buf[pos : pos + length * 2]
            names.append(raw.decode("utf-16-le"))
            pos += length * 2
        else:
            names.append(buf[pos : pos + length].decode("utf-8", errors="replace"))
            pos += length
    return names, pos


def load_script_objects(paks: Path, oodle: Path) -> dict[int, str]:
    container = load_container(paks / "global.utoc")
    chunk = next(c for c in container.chunks if CHUNK_TYPES.get(c.chunk_type) == "ScriptObjects")
    buf = read_chunk(container, chunk, None, [oodle])

    names, pos = load_name_batch(buf, 0)
    (count,) = struct.unpack_from("<i", buf, pos)
    pos += 4

    raw: dict[int, tuple[str, int]] = {}
    for _ in range(count):
        name_index, name_number, global_index, outer_index, _cdo = struct.unpack_from(
            "<IIQQQ", buf, pos
        )
        pos += 32
        raw[global_index] = (mapped_name(names, name_index, name_number), outer_index)

    resolved: dict[int, str] = {}

    def resolve(index: int, depth: int = 0) -> str:
        if index in resolved:
            return resolved[index]
        if index == NULL_INDEX or index not in raw or depth > 16:
            return ""
        name, outer = raw[index]
        parent = resolve(outer, depth + 1)
        path = f"{parent}/{name}" if parent else name
        resolved[index] = path
        return path

    for index in raw:
        resolve(index)
    return resolved


def describe_index(value: int, scripts: dict[int, str], names: list[str]) -> str:
    if value == NULL_INDEX:
        return "<null>"
    kind = value >> INDEX_TYPE_SHIFT
    if kind == TYPE_SCRIPT_IMPORT:
        return scripts.get(value, f"<script:{value:#x}>")
    if kind == TYPE_PACKAGE_IMPORT:
        return f"<package-import:{value & INDEX_MASK:#x}>"
    if kind == TYPE_EXPORT:
        return f"<export:{value & INDEX_MASK}>"
    return f"<unknown:{value:#x}>"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--paks", required=True, type=Path)
    ap.add_argument("--oodle", required=True, type=Path)
    ap.add_argument("--package", action="append", default=[], help="exact indexed .uasset path")
    ap.add_argument("--grep-scripts", help="regex to list matching script object paths")
    args = ap.parse_args()

    scripts = load_script_objects(args.paks, args.oodle)
    print(f"script objects resolved: {len(scripts)}")

    if args.grep_scripts:
        import re

        pattern = re.compile(args.grep_scripts, re.IGNORECASE)
        hits = sorted({p for p in scripts.values() if pattern.search(p)})
        print(f"matching script objects: {len(hits)}")
        for hit in hits:
            print(f"  {hit}")

    containers = []
    for utoc in sorted(args.paks.glob("*.utoc")):
        try:
            containers.append(load_container(utoc))
        except Exception:
            continue

    for wanted in args.package:
        target = wanted.lower()
        hit = None
        for c in containers:
            for path, chunk_index in c.files.items():
                full = f"{c.mount_point}{path}" if c.mount_point else path
                if full.lower() == target:
                    hit = (c, c.chunks[chunk_index], full)
                    break
            if hit:
                break
        if not hit:
            print(f"\nnot found: {wanted}", file=sys.stderr)
            continue

        container, chunk, full = hit
        buf = read_chunk(container, chunk, None, [args.oodle])

        (
            _has_versioning,
            header_size,
            name_index,
            name_number,
            package_flags,
            _cooked_header_size,
            _hashes_off,
            import_map_off,
            export_map_off,
            export_bundle_off,
            _dep_headers_off,
            _dep_entries_off,
            imported_pkg_names_off,
        ) = struct.unpack_from("<IIIIIIiiiiiii", buf, 0)

        names, _ = load_name_batch(buf, 52)
        package_name = mapped_name(names, name_index, name_number)

        print(f"\n{full}")
        print(f"  package        = {package_name}")
        print(f"  package_flags  = {package_flags:#010x}")
        print(f"  header_size    = {header_size}  chunk_size = {chunk.length}")

        import_count = (export_map_off - import_map_off) // 8
        imports = struct.unpack_from(f"<{import_count}Q", buf, import_map_off)
        print(f"  imports        = {import_count}")
        for value in imports:
            print(f"    - {describe_index(value, scripts, names)}")

        if 0 < imported_pkg_names_off < header_size:
            imported_names, _ = load_name_batch(buf, imported_pkg_names_off)
            print(f"  imported pkgs  = {len(imported_names)}")
            for n in imported_names:
                print(f"    - {n}")

        export_count = (export_bundle_off - export_map_off) // EXPORT_MAP_ENTRY_SIZE
        print(f"  exports        = {export_count}")
        for i in range(export_count):
            base = export_map_off + i * EXPORT_MAP_ENTRY_SIZE
            serial_size = struct.unpack_from("<Q", buf, base + 8)[0]
            e_name_index, e_name_number = struct.unpack_from("<II", buf, base + 16)
            outer_index, class_index, super_index, template_index = struct.unpack_from(
                "<QQQQ", buf, base + 24
            )
            e_name = mapped_name(names, e_name_index, e_name_number)
            print(f"    [{i}] {e_name}")
            print(f"        class    = {describe_index(class_index, scripts, names)}")
            print(f"        super    = {describe_index(super_index, scripts, names)}")
            print(f"        template = {describe_index(template_index, scripts, names)}")
            print(f"        outer    = {describe_index(outer_index, scripts, names)}")
            print(f"        serial   = {serial_size} bytes")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

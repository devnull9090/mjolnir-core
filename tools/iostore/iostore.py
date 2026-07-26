"""Read-only UE5 IoStore (.utoc/.ucas) reader.

Scope: enumerate the container directory index and, when explicitly asked, read a
single chunk back into memory for header inspection. This exists to support
evidence-based reverse engineering of the shipped data layout. It is not a bulk
asset ripper and it deliberately does not write game content to disk unless the
caller passes an explicit output path for a single named entry.

Format reference: UE 5.5 `IoStore.cpp` / `IoDirectoryIndex.h`.
"""

from __future__ import annotations

import ctypes
import io
import os
import struct
from dataclasses import dataclass, field
from pathlib import Path

TOC_MAGIC = b"-==--==--==--==-"

# EIoStoreTocVersion
VER_DIRECTORY_INDEX = 2
VER_PERFECT_HASH = 4
VER_PERFECT_HASH_WITH_OVERFLOW = 5
VER_ON_DEMAND_META_DATA = 6
VER_REMOVED_ON_DEMAND_META_DATA = 7
VER_REPLACE_CHUNK_HASH_WITH_IO_HASH = 8

# EIoContainerFlags
FLAG_COMPRESSED = 1 << 0
FLAG_ENCRYPTED = 1 << 1
FLAG_SIGNED = 1 << 2
FLAG_INDEXED = 1 << 3
FLAG_ON_DEMAND = 1 << 4

CHUNK_TYPES = {
    0: "Invalid",
    1: "ExportBundleData",
    2: "BulkData",
    3: "OptionalBulkData",
    4: "MemoryMappedBulkData",
    5: "ScriptObjects",
    6: "ContainerHeader",
    7: "ExternalFile",
    8: "ShaderCodeLibrary",
    9: "ShaderCode",
    10: "PackageStoreEntry",
    11: "DerivedData",
    12: "EditorDerivedData",
    13: "PackageResource",
}


class TocError(RuntimeError):
    pass


@dataclass
class ChunkEntry:
    index: int
    chunk_id: int
    chunk_index: int
    chunk_type: int
    offset: int
    length: int

    @property
    def type_name(self) -> str:
        return CHUNK_TYPES.get(self.chunk_type, f"Unknown({self.chunk_type})")


@dataclass
class CompressedBlock:
    offset: int
    compressed_size: int
    uncompressed_size: int
    method_index: int


@dataclass
class Container:
    utoc_path: Path
    version: int
    container_id: int
    flags: int
    compression_block_size: int
    partition_size: int
    partition_count: int
    compression_methods: list[str]
    chunks: list[ChunkEntry]
    blocks: list[CompressedBlock]
    mount_point: str
    files: dict[str, int] = field(default_factory=dict)

    @property
    def indexed(self) -> bool:
        return bool(self.flags & FLAG_INDEXED)

    @property
    def encrypted(self) -> bool:
        return bool(self.flags & FLAG_ENCRYPTED)

    def flag_names(self) -> list[str]:
        names = []
        for bit, name in (
            (FLAG_COMPRESSED, "Compressed"),
            (FLAG_ENCRYPTED, "Encrypted"),
            (FLAG_SIGNED, "Signed"),
            (FLAG_INDEXED, "Indexed"),
            (FLAG_ON_DEMAND, "OnDemand"),
        ):
            if self.flags & bit:
                names.append(name)
        return names or ["None"]


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.stream = io.BytesIO(data)

    def read(self, count: int) -> bytes:
        buf = self.stream.read(count)
        if len(buf) != count:
            raise TocError(f"unexpected end of buffer (wanted {count}, got {len(buf)})")
        return buf

    def u32(self) -> int:
        return struct.unpack("<I", self.read(4))[0]

    def i32(self) -> int:
        return struct.unpack("<i", self.read(4))[0]

    def fstring(self) -> str:
        length = self.i32()
        if length == 0:
            return ""
        if length < 0:
            raw = self.read(-length * 2)
            return raw.decode("utf-16-le").rstrip("\x00")
        raw = self.read(length)
        return raw.decode("utf-8", errors="replace").rstrip("\x00")


def _read_header(blob: bytes) -> dict:
    if blob[:16] != TOC_MAGIC:
        raise TocError("not an IoStore TOC (bad magic)")
    (
        version,
        _res0,
        _res1,
        header_size,
        entry_count,
        block_count,
        block_entry_size,
        method_count,
        method_length,
        block_size,
        dir_index_size,
        partition_count,
        container_id,
    ) = struct.unpack_from("<BBHIIIIIIIIIQ", blob, 16)
    encryption_guid = blob[64:80]
    (flags, _res3, _res4, perfect_hash_seed_count) = struct.unpack_from("<BBHI", blob, 80)
    (partition_size, chunks_without_perfect_hash) = struct.unpack_from("<QI", blob, 88)
    return {
        "version": version,
        "header_size": header_size,
        "entry_count": entry_count,
        "block_count": block_count,
        "block_entry_size": block_entry_size,
        "method_count": method_count,
        "method_length": method_length,
        "block_size": block_size,
        "dir_index_size": dir_index_size,
        "partition_count": partition_count,
        "container_id": container_id,
        "encryption_guid": encryption_guid,
        "flags": flags,
        "perfect_hash_seed_count": perfect_hash_seed_count,
        "partition_size": partition_size,
        "chunks_without_perfect_hash": chunks_without_perfect_hash,
    }


def _parse_directory_index(blob: bytes) -> tuple[str, dict[str, int]]:
    r = _Reader(blob)
    mount_point = r.fstring()

    dir_count = r.i32()
    dirs = [struct.unpack("<IIII", r.read(16)) for _ in range(dir_count)]

    file_count = r.i32()
    files = [struct.unpack("<III", r.read(12)) for _ in range(file_count)]

    string_count = r.i32()
    strings = [r.fstring() for _ in range(string_count)]

    NONE = 0xFFFFFFFF
    result: dict[str, int] = {}
    if not dirs:
        return mount_point, result

    stack: list[tuple[int, str]] = [(0, "")]
    while stack:
        dir_index, prefix = stack.pop()
        name_idx, first_child, next_sibling, first_file = dirs[dir_index]
        path = prefix
        if name_idx != NONE:
            path = f"{prefix}{strings[name_idx]}/"

        file_index = first_file
        while file_index != NONE:
            f_name, f_next, f_user = files[file_index]
            if f_name != NONE:
                result[f"{path}{strings[f_name]}"] = f_user
            file_index = f_next

        if next_sibling != NONE:
            stack.append((next_sibling, prefix))
        if first_child != NONE:
            stack.append((first_child, path))

    return mount_point, result


def load_container(utoc_path: os.PathLike[str] | str) -> Container:
    utoc_path = Path(utoc_path)
    blob = utoc_path.read_bytes()
    h = _read_header(blob)

    if h["version"] < VER_DIRECTORY_INDEX:
        raise TocError(f"TOC version {h['version']} predates the directory index")

    pos = h["header_size"]

    chunk_ids = blob[pos : pos + 12 * h["entry_count"]]
    pos += 12 * h["entry_count"]

    offsets = blob[pos : pos + 10 * h["entry_count"]]
    pos += 10 * h["entry_count"]

    if h["version"] >= VER_PERFECT_HASH:
        pos += 4 * h["perfect_hash_seed_count"]
    if h["version"] >= VER_PERFECT_HASH_WITH_OVERFLOW:
        pos += 4 * h["chunks_without_perfect_hash"]

    blocks: list[CompressedBlock] = []
    size = h["block_entry_size"]
    for i in range(h["block_count"]):
        raw = blob[pos + i * size : pos + i * size + 12]
        offset = int.from_bytes(raw[0:5], "little")
        compressed = int.from_bytes(raw[5:8], "little")
        uncompressed = int.from_bytes(raw[8:11], "little")
        blocks.append(CompressedBlock(offset, compressed, uncompressed, raw[11]))
    pos += size * h["block_count"]

    methods = ["None"]
    for i in range(h["method_count"]):
        raw = blob[pos + i * h["method_length"] : pos + (i + 1) * h["method_length"]]
        methods.append(raw.split(b"\x00", 1)[0].decode("ascii", errors="replace"))
    pos += h["method_length"] * h["method_count"]

    if h["flags"] & FLAG_SIGNED:
        hash_size = struct.unpack_from("<i", blob, pos)[0]
        pos += 4
        pos += hash_size * 2
        pos += hash_size * h["block_count"]

    mount_point = ""
    files: dict[str, int] = {}
    if h["dir_index_size"] and (h["flags"] & FLAG_INDEXED):
        dir_blob = blob[pos : pos + h["dir_index_size"]]
        if h["flags"] & FLAG_ENCRYPTED:
            raise TocError("directory index is encrypted; no key supplied")
        mount_point, files = _parse_directory_index(dir_blob)

    chunks: list[ChunkEntry] = []
    for i in range(h["entry_count"]):
        cid = chunk_ids[i * 12 : (i + 1) * 12]
        raw = offsets[i * 10 : (i + 1) * 10]
        chunks.append(
            ChunkEntry(
                index=i,
                chunk_id=int.from_bytes(cid[0:8], "little"),
                chunk_index=int.from_bytes(cid[8:10], "big"),
                chunk_type=cid[11],
                offset=int.from_bytes(raw[0:5], "big"),
                length=int.from_bytes(raw[5:10], "big"),
            )
        )

    return Container(
        utoc_path=utoc_path,
        version=h["version"],
        container_id=h["container_id"],
        flags=h["flags"],
        compression_block_size=h["block_size"],
        partition_size=h["partition_size"],
        partition_count=h["partition_count"],
        compression_methods=methods,
        chunks=chunks,
        blocks=blocks,
        mount_point=mount_point,
        files=files,
    )


_OODLE = None


def _load_oodle(search_roots: list[Path]) -> ctypes.CDLL:
    global _OODLE
    if _OODLE is not None:
        return _OODLE
    candidates: list[Path] = []
    for root in search_roots:
        if root.is_file() and root.suffix.lower() == ".dll":
            candidates.append(root)
            continue
        if root.is_dir():
            candidates.extend(sorted(root.rglob("oo2core*win64.dll")))
    if not candidates:
        raise TocError("no oo2core_*_win64.dll found; pass --oodle <path>")
    dll = ctypes.CDLL(str(candidates[0]))
    dll.OodleLZ_Decompress.restype = ctypes.c_int64
    dll.OodleLZ_Decompress.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int64,
        ctypes.c_void_p,
        ctypes.c_int64,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_int64,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_int64,
        ctypes.c_int,
    ]
    _OODLE = dll
    return dll


def _decompress(method: str, src: bytes, out_size: int, oodle_roots: list[Path]) -> bytes:
    lowered = method.lower()
    if lowered in ("none", ""):
        return src[:out_size]
    if lowered == "zlib":
        import zlib

        return zlib.decompress(src)
    if lowered == "oodle":
        dll = _load_oodle(oodle_roots)
        out = ctypes.create_string_buffer(out_size)
        written = dll.OodleLZ_Decompress(
            src, len(src), out, out_size, 1, 0, 0, None, 0, None, None, None, 0, 3
        )
        if written != out_size:
            raise TocError(f"Oodle decompress returned {written}, expected {out_size}")
        return out.raw[:out_size]
    raise TocError(f"unsupported compression method {method!r}")


def read_chunk(
    container: Container,
    chunk: ChunkEntry,
    max_bytes: int | None = None,
    oodle_roots: list[Path] | None = None,
) -> bytes:
    """Read one chunk back into memory, decompressing only the blocks needed."""
    oodle_roots = oodle_roots or []
    block_size = container.compression_block_size
    first = chunk.offset // block_size
    wanted = chunk.length if max_bytes is None else min(chunk.length, max_bytes)
    last = (chunk.offset + wanted - 1) // block_size

    out = bytearray()
    base = container.utoc_path.with_suffix("")
    handles: dict[int, io.BufferedReader] = {}
    try:
        for i in range(first, last + 1):
            block = container.blocks[i]
            partition = block.offset // container.partition_size if container.partition_size else 0
            local_offset = (
                block.offset % container.partition_size if container.partition_size else block.offset
            )
            if partition not in handles:
                name = f"{base}.ucas" if partition == 0 else f"{base}_s{partition}.ucas"
                handles[partition] = open(name, "rb")
            fh = handles[partition]
            fh.seek(local_offset)
            aligned = (block.compressed_size + 15) & ~15
            raw = fh.read(aligned)[: block.compressed_size]
            method = container.compression_methods[block.method_index]
            out += _decompress(method, raw, block.uncompressed_size, oodle_roots)
    finally:
        for fh in handles.values():
            fh.close()

    start = chunk.offset - first * block_size
    return bytes(out[start : start + wanted])

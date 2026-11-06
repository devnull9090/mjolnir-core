#!/usr/bin/env python3
"""Read a Halo CE cache file's header and tag index, without the exporter.

A `.map` is a 2 KB header, the tag data (index header, tag array, paths and
every tag's body, all addressed as if loaded at the engine's base address) and
the raw model and BSP data. This reads just enough of it to catalogue a map
before anyone converts it: its name, build, type and size, how many tags it
carries and of which classes, how many structure BSPs it has, whether a
protection tool scrambled its index, and which of its object and shader tags
are not in the stock maps (the custom weapons, vehicles, scenery and bipeds a
conversion has to deal with).

Layout (Custom Edition, cache version 609; the PC retail 7 is the same):

    header   0x000 'head', u32 version, u32 file size, +0x10 u32 tag index
             offset, +0x20 char[32] name, +0x40 char[32] build, +0x60 u16
             type (0 solo, 1 multiplayer, 2 ui), 0x7FC 'foot'
    index    at the tag index offset: u32 tag array address, u32 scenario tag
             id, u32 checksum, u32 tag count, ..., 'tags' at +0x24 (40 bytes)
    tags     32 bytes each: three class fourccs (stored reversed), the tag id,
             the path address, the data address, u32 external (1 when the
             body lives in bitmaps.map, sounds.map or loc.map), padding

Addresses are engine addresses: file offset = address - base + index offset,
base 0x40440000 on PC and Custom Edition.

    python tools/halomaps/cemap.py maps/bloodgulch.map                 # one map, JSON
    python tools/halomaps/cemap.py --write-stock stock.json maps/*.map  # the stock tag set
    python tools/halomaps/cemap.py --stock stock.json custom.map        # with its custom tags
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import struct
import sys

HEADER_SIZE = 0x800
HEAD, FOOT = b"daeh", b"toof"  # the fourccs, stored little-endian
# Engine base address of the tag data, by cache version.
BASE = {7: 0x40440000, 609: 0x40440000, 5: 0x803A6000}
VERSIONS = {5: "xbox", 7: "pc", 609: "custom edition"}
MAP_TYPES = {0: "singleplayer", 1: "multiplayer", 2: "ui"}
TAG_ENTRY = struct.Struct("<4s4s4sIIIII")

# Every tag class Halo CE's engine knows. Anything else in a map's index is a
# protection tool's doing (Yoyorast's "ztpt").
KNOWN_CLASSES = {
    "actr", "actv", "ant!", "antr", "bipd", "bitm", "boom", "cdmg", "coll", "colo", "cont",
    "ctrl", "deca", "DeLa", "devc", "devi", "dobc", "effe", "elec", "eqip", "flag", "fog ",
    "font", "foot", "garb", "glw!", "grhi", "hmt ", "hud#", "hudg", "item", "itmc", "jpt!",
    "lens", "lifi", "ligh", "lsnd", "mach", "matg", "metr", "mgs2", "mod2", "mode", "mply",
    "ngpr", "obje", "part", "pctl", "phys", "plac", "pphy", "proj", "rain", "sbsp", "scen",
    "scex", "schi", "scnr", "senv", "sgla", "shdr", "sky ", "smet", "snd!", "snde", "soso",
    "Soul", "spla", "ssce", "str#", "swat", "tagc", "trak", "udlg", "unhi", "unit", "ustr",
    "vcky", "vehi", "weap", "wind", "wphi",
}
CLASS_NAMES = {
    "weap": "weapons", "vehi": "vehicles", "scen": "scenery", "bipd": "bipeds", "eqip": "equipment",
    "mach": "machines", "ctrl": "controls", "lifi": "light fixtures", "proj": "projectiles",
    "ssce": "sound scenery", "garb": "garbage", "plac": "placeholders", "sky ": "skies",
    "sbsp": "structure bsps", "scnr": "scenarios", "senv": "environment shaders",
    "soso": "model shaders", "schi": "chicago shaders", "scex": "extended chicago shaders",
    "swat": "water shaders", "sgla": "glass shaders", "smet": "meter shaders",
    "spla": "plasma shaders", "mod2": "models", "bitm": "bitmaps", "snd!": "sounds",
    "effe": "effects", "jpt!": "damage effects", "actv": "actor variants", "itmc": "item collections",
    "matg": "globals", "antr": "animations", "coll": "collision models", "DeLa": "ui widgets",
}
# The classes whose custom tags are listed by path, not just counted: what a
# conversion places or shades. Everything else only counts.
LISTED_CLASSES = [
    "weap", "vehi", "scen", "bipd", "eqip", "mach", "ctrl", "lifi", "proj", "ssce", "garb",
    "plac", "sky ", "senv", "soso", "schi", "scex", "swat", "sgla", "smet", "spla", "actv",
    "itmc", "matg",
]
# Every map's scenario and structure BSPs are its own; they say nothing
# about what is custom in it.
OWN_CLASSES = {"scnr", "sbsp"}


class NotACacheFile(ValueError):
    pass


def _cstr(data: bytes, off: int, limit: int = 256) -> str | None:
    """A NUL-terminated string at `off`, or None when it runs off the data or
    holds bytes no tag path has."""
    if off < 0 or off >= len(data):
        return None
    end = data.find(b"\0", off, off + limit)
    if end < 0:
        return None
    raw = data[off:end]
    if any(b < 0x20 or b > 0x7E for b in raw):
        return None
    return raw.decode("ascii")


def fourcc(raw: bytes) -> str | None:
    """A class fourcc as the file stores it (reversed), or None for the
    0xFFFFFFFF a tag without a secondary class carries."""
    if raw == b"\xff\xff\xff\xff":
        return None
    return raw[::-1].decode("latin1")


def read_header(data: bytes) -> dict:
    if len(data) < HEADER_SIZE or data[:4] != HEAD or data[0x7FC:0x800] != FOOT:
        raise NotACacheFile("not a Halo cache file (no head/foot)")
    version, file_size = struct.unpack_from("<II", data, 4)
    index_offset, tag_data_size = struct.unpack_from("<II", data, 0x10)
    name = data[0x20:0x40].split(b"\0")[0].decode("latin1")
    build = data[0x40:0x60].split(b"\0")[0].decode("latin1")
    map_type = struct.unpack_from("<H", data, 0x60)[0]
    crc = struct.unpack_from("<I", data, 0x64)[0]
    return {
        "name": name,
        "build": build,
        "version": version,
        "engine": VERSIONS.get(version, f"unknown ({version})"),
        "type": MAP_TYPES.get(map_type, f"unknown ({map_type})"),
        "declared_size": file_size,
        "index_offset": index_offset,
        "tag_data_size": tag_data_size,
        "crc32": f"{crc:08x}",
    }


def read_tag_data(path: str, digest: bool = True) -> tuple[dict, bytes, int, str | None]:
    """The header, the tag data (the file from the tag index on: every
    address in it is relative to the engine base), the file size and, when
    asked, the sha256 of the whole file. The tag data is a few MB of a map's
    tens, so a survey of thousands of maps reads a fraction of them."""
    with open(path, "rb") as f:
        header = read_header(f.read(HEADER_SIZE))
        size = os.fstat(f.fileno()).st_size
        idx, n = header["index_offset"], header["tag_data_size"]
        if idx <= 0 or idx >= size:
            raise NotACacheFile("tag index past the end of the file")
        f.seek(idx)
        data = f.read(n if 0 < n <= size - idx else size - idx)
        sha = None
        if digest:
            f.seek(0)
            h = hashlib.sha256()
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
            sha = h.hexdigest()
    return header, data, size, sha


def read_tags(data: bytes, header: dict) -> tuple[list[dict], dict]:
    """Every tag index entry: class fourccs, id, path, external flag. `data`
    is the tag data alone (read_tag_data), so an address's offset in it is
    the address less the engine base."""
    if len(data) < 0x28:
        raise NotACacheFile("tag index past the end of the file")
    array_addr, scenario_id, _checksum, count = struct.unpack_from("<IIII", data, 0)
    base = BASE.get(header["version"])
    if base is None:
        # Unknown engine: the array normally follows the 40-byte index header.
        base = array_addr - 0x28
    array_off = array_addr - base
    tags = []
    for i in range(count):
        off = array_off + i * TAG_ENTRY.size
        if off < 0 or off + TAG_ENTRY.size > len(data):
            break
        c0, c1, c2, tag_id, path_addr, data_addr, external, _pad = TAG_ENTRY.unpack_from(data, off)
        path = _cstr(data, path_addr - base)
        tags.append({
            "index": i,
            "class": fourcc(c0),
            "parents": [c for c in (fourcc(c1), fourcc(c2)) if c],
            "id": tag_id,
            "path": path,
            "external": bool(external),
        })
    index = {
        "tag_count": count,
        "tags_read": len(tags),
        "scenario_id": scenario_id,
        "base_address": base,
    }
    return tags, index


def survey(tags: list[dict], index: dict) -> dict:
    """Class histogram, the scenario, BSP count and the protection check."""
    classes = collections.Counter()
    unknown = 0
    bad_paths = 0
    placeholders = 0
    seen_paths = set()
    for t in tags:
        cls = t["class"]
        if cls is None or cls not in KNOWN_CLASSES:
            unknown += 1
            classes["?" if cls is None else cls] += 1
        else:
            classes[cls] += 1
        if is_placeholder(t["path"]):
            placeholders += 1
        key = (cls, t["path"])
        if t["path"] is None or key in seen_paths:
            bad_paths += 1
        seen_paths.add(key)
    n = max(len(tags), 1)
    scenario = next((t["path"] for t in tags if t["id"] == index["scenario_id"]), None)
    if scenario is None:
        scenario = next((t["path"] for t in tags if t["class"] == "scnr"), None)
    # A protection tool replaces every class with its own and every path with
    # one placeholder; half the index broken either way is the sign. A
    # lighter protection keeps the classes and blanks some paths
    # ("<protected>"): partial, and the exporter still reads the map.
    protected = unknown > n * 0.5 or bad_paths > n * 0.5
    return {
        "scenario": scenario,
        "bsps": classes.get("sbsp", 0),
        "classes": dict(sorted(classes.items(), key=lambda kv: (-kv[1], kv[0]))),
        "external_tags": sum(1 for t in tags if t["external"]),
        "unknown_classes": unknown,
        "bad_paths": bad_paths,
        "placeholder_paths": placeholders,
        "protected": protected,
        "partially_protected": placeholders > 0 and not protected,
    }


def is_placeholder(path: str | None) -> bool:
    """A path a protection tool left: "<protected>", "<zteam>"."""
    return path is not None and path.startswith("<")


def custom_tags(tags: list[dict], stock: dict[str, set[str]]) -> dict:
    """The map's tags that no stock map carries, by class: listed by path for
    the object and shader classes, counted for the rest."""
    listed = {}
    counts = collections.Counter()
    placeholders = collections.Counter()
    for t in tags:
        cls = t["class"]
        if cls not in KNOWN_CLASSES or cls in OWN_CLASSES or t["path"] is None:
            continue
        if is_placeholder(t["path"]):
            placeholders[cls] += 1  # custom or not, nobody can tell from the name
            continue
        if t["path"] in stock.get(cls, ()):
            continue
        counts[cls] += 1
        if cls in LISTED_CLASSES:
            listed.setdefault(cls, []).append(t["path"])
    for paths in listed.values():
        paths.sort()
    return {
        "total": sum(counts.values()),
        "counts": dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "tags": {cls: listed[cls] for cls in LISTED_CLASSES if cls in listed},
        "placeholders": dict(sorted(placeholders.items(), key=lambda kv: (-kv[1], kv[0]))),
    }


def read_map(path: str, stock: dict[str, set[str]] | None = None, with_tags: bool = False,
             digest: bool = True) -> dict:
    """Everything the catalogue keeps about one cache file."""
    header, data, size, sha = read_tag_data(path, digest)
    tags, index = read_tags(data, header)
    info = {
        "file": os.path.basename(path),
        "size": size,
        **header,
        **index,
        **survey(tags, index),
    }
    if sha:
        info["sha256"] = sha
    if stock is not None:
        # A protected map's paths are placeholders: every tag would count as
        # custom, so the survey waits for the exporter's repair.
        info["custom"] = None if info["protected"] else custom_tags(tags, stock)
    if with_tags:
        info["tags"] = tags
    return info


def stock_set(paths: list[str]) -> dict[str, set[str]]:
    """The union of the given maps' tag paths, by class."""
    stock: dict[str, set[str]] = {}
    for p in paths:
        try:
            header, data, _size, _sha = read_tag_data(p, digest=False)
        except NotACacheFile:
            continue  # bitmaps.map, sounds.map and loc.map are resource maps
        tags, _ = read_tags(data, header)
        for t in tags:
            if t["class"] in KNOWN_CLASSES and t["path"] and not is_placeholder(t["path"]):
                stock.setdefault(t["class"], set()).add(t["path"])
    return stock


def load_stock(path: str) -> dict[str, set[str]]:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {cls: set(paths) for cls, paths in raw["tags"].items()}


def save_stock(path: str, stock: dict[str, set[str]], sources: list[str]) -> None:
    out = {
        "comment": "Tag paths of the stock Halo CE maps, by class; a custom map's tags outside it are its own.",
        "sources": [os.path.basename(s) for s in sources],
        "tags": {cls: sorted(paths) for cls, paths in sorted(stock.items())},
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
        f.write("\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("maps", nargs="+", help="cache files to read")
    ap.add_argument("--stock", help="a stock tag set (JSON from --write-stock): report each map's custom tags")
    ap.add_argument("--write-stock", help="write the union of the given maps' tag paths as the stock set")
    ap.add_argument("--tags", action="store_true", help="include every tag index entry")
    ap.add_argument("--no-digest", action="store_true", help="skip the sha256")
    a = ap.parse_args()

    if a.write_stock:
        stock = stock_set(a.maps)
        save_stock(a.write_stock, stock, a.maps)
        print(f"wrote {a.write_stock}: {sum(len(v) for v in stock.values())} tag paths in "
              f"{len(stock)} classes from {len(a.maps)} files")
        return 0

    stock = load_stock(a.stock) if a.stock else None
    results = []
    for p in a.maps:
        try:
            results.append(read_map(p, stock=stock, with_tags=a.tags, digest=not a.no_digest))
        except NotACacheFile as e:
            results.append({"file": os.path.basename(p), "error": str(e)})
    json.dump(results[0] if len(results) == 1 else results, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())

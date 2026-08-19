"""Produce a reproducible build lock for a Halo Campaign Evolved install.

Every finding in `docs/` is only true of the build it was measured on, and the
game updates without asking. This walks an install, hashes the shipped files, and
writes a lock the docs can cite by name instead of each restating a hash.

Excluded on purpose:

* `Binaries/Win64/ue4ss/` and `Content/Paks/LogicMods/` - these are what *we*
  installed, not what shipped. Including them makes the lock differ per machine.
* `*.dmp`, `*.log` - crash dumps and logs are local residue.

Paths are recorded relative to the install root so two machines with the same
build produce byte-identical locks.

Usage:
    python tools/build_lock.py "<install root>" -o config/hce-build.lock.json
    python tools/build_lock.py "<install root>" --verify config/hce-build.lock.json
    python tools/build_lock.py "<install root>" --binaries-only     # fast pass
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

# ".DepotDownloader" is the state directory tools/steam_depot_fetch.py's
# downloads carry; excluding it is what lets a build recovered from Steam's
# depot history hash identically to the same build caught live.
SKIP_DIRS = {"ue4ss", "LogicMods", ".DepotDownloader"}
SKIP_SUFFIXES = {".dmp", ".log"}
BINARY_SUFFIXES = {".exe", ".dll"}

# UE4SS ships as a `dwmapi.dll` proxy dropped next to the executable, so it sits
# outside the `ue4ss/` directory and would otherwise be locked as if the game had
# shipped it. A lock that differs between a modded and a vanilla install cannot
# answer "is this the same build as the docs describe", which is its whole job.
SKIP_NAMES = {"dwmapi.dll"}

# The host stamps its own version; recovering it keeps the lock self-describing
# even if whoever reads it has no install to compare against. The stamp is UTF-16LE
# in the shipping image, so the pattern is applied to a decoded copy rather than to
# raw bytes - matching it bytewise silently finds nothing, which reads as "no
# version" rather than as a bug.
VERSION_RE = re.compile(r"(?:(\d+\.\d+\.\d+)-)?(\d[\d.]{6,24}-Rel-i343-Meteorite-\d{4}-CU\d+)")
HOST_RELATIVE = "Meteorite/Binaries/Win64/HaloCampaignEvolved.exe"
SIMULATION_RELATIVE = "Meteorite/Binaries/Win64/HaloSimulation_tag_release.dll"


def iter_files(root: Path, binaries_only: bool):
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        if path.name.lower() in SKIP_NAMES:
            continue
        if binaries_only and path.suffix.lower() not in BINARY_SUFFIXES:
            continue
        yield path


def sha256(path: Path, chunk: int = 1 << 22) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest().upper()


def find_version(root: Path) -> tuple[str | None, str | None]:
    """(build version, engine version) as stamped into the host image."""
    host = root / HOST_RELATIVE
    if not host.is_file():
        return None, None
    # The stamp lives in the middle of a 230 MB image; scanning it whole costs a
    # few seconds and beats guessing an offset that moves every update.
    blob = host.read_bytes()
    text = blob.decode("utf-16-le", "ignore") + "\n" + blob.decode("latin-1", "ignore")

    build, engine = None, None
    for engine_match, build_match in VERSION_RE.findall(text):
        build = build or build_match
        engine = engine or (engine_match or None)
        if build and engine:
            break
    return build, engine


def build_lock(root: Path, binaries_only: bool, generated: str | None) -> dict:
    entries = []
    total = 0
    for path in iter_files(root, binaries_only):
        rel = path.relative_to(root).as_posix()
        size = path.stat().st_size
        total += size
        entries.append({"path": rel, "size": size, "sha256": sha256(path)})
        print(f"  {rel}", file=sys.stderr)

    by_path = {e["path"]: e["sha256"] for e in entries}
    version, engine = find_version(root)
    lock = {
        "generator": "tools/build_lock.py",
        "version": version,
        "engine": engine,
        "host_sha256": by_path.get(HOST_RELATIVE),
        "simulation_sha256": by_path.get(SIMULATION_RELATIVE),
        "file_count": len(entries),
        "total_bytes": total,
        "scope": "binaries" if binaries_only else "full",
        "files": entries,
    }
    if generated:
        lock["generated"] = generated
    return lock


def verify(root: Path, lock_path: Path) -> int:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    expected_version = lock.get("version")
    actual_version, _ = find_version(root)
    if expected_version and actual_version and expected_version != actual_version:
        print(f"VERSION MISMATCH: lock {expected_version}, install {actual_version}")

    missing, changed, ok = [], [], 0
    for entry in lock["files"]:
        path = root / entry["path"]
        if not path.is_file():
            missing.append(entry["path"])
            continue
        if sha256(path) != entry["sha256"]:
            changed.append(entry["path"])
            continue
        ok += 1

    for path in missing:
        print(f"MISSING  {path}")
    for path in changed:
        print(f"CHANGED  {path}")
    print(f"# {ok} matched, {len(changed)} changed, {len(missing)} missing")
    return 1 if (changed or missing) else 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("root", type=Path, help="install root (the folder containing Meteorite/)")
    ap.add_argument("-o", "--out", type=Path, help="write the lock here instead of stdout")
    ap.add_argument("--verify", type=Path, help="check the install against an existing lock")
    ap.add_argument("--binaries-only", action="store_true", help="skip content containers")
    ap.add_argument("--generated", help="date stamp to record in the lock")
    args = ap.parse_args()

    if not (args.root / "Meteorite").is_dir():
        print(f"error: {args.root} does not look like an install root", file=sys.stderr)
        return 2

    if args.verify:
        return verify(args.root, args.verify)

    lock = build_lock(args.root, args.binaries_only, args.generated)
    text = json.dumps(lock, indent=2) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"# wrote {args.out} ({lock['file_count']} files)", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

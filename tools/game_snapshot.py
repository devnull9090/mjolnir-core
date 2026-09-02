"""Point-in-time snapshots of a Halo Campaign Evolved install.

The game updates in place and keeps no history: the moment Steam patches it, the
previous build is gone, and with it any chance of asking "what did this update
change". A snapshot taken after each update preserves that point in time, so the
next update can be diffed against it — at the file level here, and at the tag
level with `mjolnir tagdiff` against two materialized snapshots.

The store is content-addressed: file bodies live under `objects/` named by their
SHA-256, and each snapshot is a manifest of paths pointing into that pool. Files
unchanged between builds are stored once, so the first snapshot costs the full
install (~74 GiB) and each later one only what the update actually touched.

The store holds copyrighted game content. It is a private, local backup of an
install the user owns — keep it out of the repository and do not publish it.

The manifest is a superset of the `tools/build_lock.py` lock format, so a
snapshot can also stamp out the repo's build lock in the same pass.

Usage:
    python tools/game_snapshot.py snapshot "<install root>" --store D:/hce-snapshots
    python tools/game_snapshot.py list --store D:/hce-snapshots
    python tools/game_snapshot.py diff <ver-a> <ver-b> --store D:/hce-snapshots
    python tools/game_snapshot.py materialize <ver> <dest> --store D:/hce-snapshots --only Meteorite/Content/Paks
    python tools/game_snapshot.py verify <ver> --store D:/hce-snapshots

The store may also be set once via the HCE_SNAPSHOTS environment variable.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import date
from pathlib import Path

# Same-directory import: hashing, skip rules and version recovery live in
# build_lock.py and must not drift from it, or a snapshot and a lock taken from
# the same install would disagree about what "the install" is.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_lock import HOST_RELATIVE, SIMULATION_RELATIVE, find_version, iter_files, sha256


def store_root(args) -> Path:
    given = args.store or os.environ.get("HCE_SNAPSHOTS")
    if not given:
        sys.exit("error: no store given — pass --store or set HCE_SNAPSHOTS")
    return Path(given)


def object_path(store: Path, digest: str) -> Path:
    return store / "objects" / digest[:2] / digest


def manifest_dir(store: Path) -> Path:
    return store / "snapshots"


def load_manifest(store: Path, version: str) -> dict:
    path = manifest_dir(store) / f"{version}.json"
    if not path.is_file():
        names = sorted(p.stem for p in manifest_dir(store).glob("*.json"))
        matches = [n for n in names if version in n]
        if len(matches) == 1:
            path = manifest_dir(store) / f"{matches[0]}.json"
        else:
            hint = "\n  ".join(names) or "(store has no snapshots)"
            sys.exit(f"error: no snapshot {version!r}. Known:\n  {hint}")
    return json.loads(path.read_text(encoding="utf-8"))


def ingest(store: Path, source: Path, digest: str) -> bool:
    """Copy `source` into the object pool unless already present. True if copied."""
    dest = object_path(store, digest)
    if dest.is_file():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    shutil.copyfile(source, tmp)
    os.replace(tmp, dest)  # atomic: a crash never leaves a half-written object
    return True


def cmd_snapshot(args) -> int:
    store = store_root(args)
    root: Path = args.root
    if not (root / "Meteorite").is_dir():
        sys.exit(f"error: {root} does not look like an install root")

    version, engine = find_version(root)
    if not version:
        sys.exit("error: could not recover the build version from the host executable")
    out = manifest_dir(store) / f"{version}.json"
    if out.is_file() and not args.force:
        sys.exit(f"error: snapshot {version} already exists ({out}); --force to retake")
    manifest_dir(store).mkdir(parents=True, exist_ok=True)

    entries, total, new_bytes, new_files = [], 0, 0, 0
    for path in iter_files(root, binaries_only=False):
        rel = path.relative_to(root).as_posix()
        size = path.stat().st_size
        digest = sha256(path)
        if ingest(store, path, digest):
            new_files += 1
            new_bytes += size
        total += size
        entries.append({"path": rel, "size": size, "sha256": digest})
        print(f"  {rel}", file=sys.stderr)

    by_path = {e["path"]: e["sha256"] for e in entries}
    manifest = {
        "generator": "tools/game_snapshot.py",
        "version": version,
        "engine": engine,
        "host_sha256": by_path.get(HOST_RELATIVE),
        "simulation_sha256": by_path.get(SIMULATION_RELATIVE),
        "file_count": len(entries),
        "total_bytes": total,
        "scope": "full",
        "generated": args.generated or date.today().isoformat(),
        "files": entries,
    }
    out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"# snapshot {version}: {len(entries)} files, {total:,} bytes")
    print(f"# new to store: {new_files} files, {new_bytes:,} bytes")

    if args.lock_out:
        # The repo lock is the same data minus nothing — the schema is a
        # superset on purpose. Re-stamp the generator so the lock stays
        # self-describing about which tool wrote it.
        lock = dict(manifest)
        lock["generator"] = "tools/build_lock.py"
        args.lock_out.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
        print(f"# wrote lock {args.lock_out}")
    return 0


def cmd_list(args) -> int:
    store = store_root(args)
    rows = []
    for path in sorted(manifest_dir(store).glob("*.json")):
        m = json.loads(path.read_text(encoding="utf-8"))
        rows.append((m.get("generated", "?"), m["version"], m["file_count"], m["total_bytes"]))
    if not rows:
        print("(store has no snapshots)")
        return 0
    for generated, version, count, total in sorted(rows):
        print(f"{generated}  {version}  {count} files  {total / 2**30:.1f} GiB")
    return 0


def cmd_diff(args) -> int:
    store = store_root(args)
    a = load_manifest(store, args.a)
    b = load_manifest(store, args.b)
    fa = {e["path"]: e for e in a["files"]}
    fb = {e["path"]: e for e in b["files"]}

    added = sorted(set(fb) - set(fa))
    removed = sorted(set(fa) - set(fb))
    changed = sorted(p for p in set(fa) & set(fb) if fa[p]["sha256"] != fb[p]["sha256"])

    print(f"# {a['version']} -> {b['version']}")
    for p in added:
        print(f"ADDED    {p}  ({fb[p]['size']:,} bytes)")
    for p in removed:
        print(f"REMOVED  {p}")
    for p in changed:
        delta = fb[p]["size"] - fa[p]["size"]
        print(f"CHANGED  {p}  ({fa[p]['size']:,} -> {fb[p]['size']:,}, {delta:+,})")
    print(f"# {len(added)} added, {len(removed)} removed, {len(changed)} changed")
    if args.json:
        report = {
            "from": a["version"],
            "to": b["version"],
            "added": [fb[p] for p in added],
            "removed": [fa[p] for p in removed],
            "changed": [
                {"path": p, "before": fa[p], "after": fb[p]} for p in changed
            ],
        }
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"# wrote {args.json}", file=sys.stderr)
    return 0


def cmd_materialize(args) -> int:
    store = store_root(args)
    m = load_manifest(store, args.version)
    dest: Path = args.dest
    only = args.only.replace("\\", "/").rstrip("/") if args.only else None

    linked = copied = 0
    for entry in m["files"]:
        rel = entry["path"]
        if only and not rel.startswith(only + "/") and rel != only:
            continue
        src = object_path(store, entry["sha256"])
        if not src.is_file():
            sys.exit(f"error: store is missing object for {rel} ({entry['sha256']})")
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target.unlink()
        try:
            os.link(src, target)  # free on the same volume; the pool stays canonical
            linked += 1
        except OSError:
            shutil.copyfile(src, target)
            copied += 1
    if linked + copied == 0:
        sys.exit(f"error: no files matched --only {args.only!r}")
    print(f"# materialized {m['version']} -> {dest}: {linked} hardlinked, {copied} copied")
    return 0


def cmd_verify(args) -> int:
    store = store_root(args)
    m = load_manifest(store, args.version)
    missing = bad = 0
    for entry in m["files"]:
        obj = object_path(store, entry["sha256"])
        if not obj.is_file():
            print(f"MISSING  {entry['path']}")
            missing += 1
        elif obj.stat().st_size != entry["size"]:
            print(f"BAD SIZE {entry['path']}")
            bad += 1
        elif args.rehash and sha256(obj) != entry["sha256"]:
            print(f"BAD HASH {entry['path']}")
            bad += 1
    print(f"# {m['file_count'] - missing - bad} ok, {bad} bad, {missing} missing")
    return 1 if (missing or bad) else 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--store", type=Path, help="snapshot store root (or HCE_SNAPSHOTS)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("snapshot", help="capture the install as it is right now")
    s.add_argument("root", type=Path, help="install root (the folder containing Meteorite/)")
    s.add_argument("--force", action="store_true", help="retake an existing version")
    s.add_argument("--generated", help="date stamp; defaults to today")
    s.add_argument("--lock-out", type=Path, help="also write a build_lock.py-format lock here")
    s.set_defaults(fn=cmd_snapshot)

    s = sub.add_parser("list", help="list captured versions")
    s.set_defaults(fn=cmd_list)

    s = sub.add_parser("diff", help="file-level diff of two snapshots")
    s.add_argument("a", help="older version (substring is enough if unambiguous)")
    s.add_argument("b", help="newer version")
    s.add_argument("--json", type=Path, help="also write the diff as JSON")
    s.set_defaults(fn=cmd_diff)

    s = sub.add_parser("materialize", help="rebuild a version's file tree from the store")
    s.add_argument("version", help="version (substring is enough if unambiguous)")
    s.add_argument("dest", type=Path, help="directory to build the tree under")
    s.add_argument("--only", help="restrict to one subtree, e.g. Meteorite/Content/Paks")
    s.set_defaults(fn=cmd_materialize)

    s = sub.add_parser("verify", help="check a snapshot's objects are all present")
    s.add_argument("version", help="version (substring is enough if unambiguous)")
    s.add_argument("--rehash", action="store_true", help="rehash object bodies too")
    s.set_defaults(fn=cmd_verify)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())

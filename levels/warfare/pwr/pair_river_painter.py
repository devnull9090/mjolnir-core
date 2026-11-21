"""Pair the opt-in river painter with both staged Pelican Warfare runtimes."""
import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path


MEMBER = "mods/MJOLNIRLevelLoader/Scripts/flux_runtime.lua"
BASE_SHA = "1c7f49e83922699ae6fc09d084336a3502a5c4f60fd7f5142ffd6fcc1b1fb59e"
LOADER = Path(__file__).resolve().parents[3] / MEMBER


def sha(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(obj):
    return (json.dumps(obj, indent=2) + "\n").encode()


def install_painter_runtime(release_dir):
    """Modify a private staging directory. Both profiles must pass readback before publication."""
    release = Path(release_dir).resolve()
    loader = LOADER.read_bytes()
    loader_hash = sha(loader)
    if loader_hash == BASE_SHA or b"spatialPainter" not in loader:
        raise ValueError("Painter source missing")
    map_receipt = json.loads((release / "receipt.json").read_bytes())
    work = []
    summary = {"previous_loader_sha256": BASE_SHA, "loader_sha256": loader_hash, "profiles": {}}
    with tempfile.TemporaryDirectory(dir=release) as tmp:
        for label, folder in (("standard", release), ("solo", release / "solo")):
            receipt_path = folder / "developer-runtime-receipt.json"
            receipt = json.loads(receipt_path.read_bytes())
            if Path(receipt["archive"]).name != receipt["archive"] or receipt.get("installed"):
                raise ValueError("Runtime receipt must describe an uninstalled local archive")
            path = folder / receipt["archive"]
            name = path.name
            if sha(path.read_bytes()) != receipt["sha256"] or path.stat().st_size != receipt["bytes"]:
                raise ValueError(f"Changed runtime input: {path}")
            staged = Path(tmp) / (label + "-" + name)
            with zipfile.ZipFile(path) as source, zipfile.ZipFile(staged, "w") as dest:
                manifest = json.loads(source.read("manifest.json"))
                payload = manifest["payload_sha256"]
                if (len(source.namelist()) != len(set(source.namelist())) or
                        set(source.namelist()) != set(payload) | {"README.md", "manifest.json"} or
                        set(payload) != set(receipt["file_list"]) or receipt["verified_files"] != len(payload)):
                    raise ValueError(f"Unexpected archive inventory: {path}")
                paired = manifest["paired_map"]
                if (paired != receipt["paired_map"] or paired["sha256"] != map_receipt["sha256"] or
                        paired["name"] != map_receipt["archive"] or manifest["version"] != receipt["version"]):
                    raise ValueError(f"Mismatched map or version: {path}")
                if payload[MEMBER] not in {BASE_SHA, loader_hash}:
                    raise ValueError(f"Unexpected loader revision: {payload[MEMBER]}")
                expected = dict(payload)
                payload[MEMBER] = loader_hash
                for info in source.infolist():
                    data = source.read(info)
                    if info.filename in expected and sha(data) != expected[info.filename]:
                        raise ValueError(f"Changed source: {info.filename}")
                    if info.filename == MEMBER:
                        data = loader
                    elif info.filename == "manifest.json":
                        data = json_bytes(manifest)
                    dest.writestr(info, data)
            with zipfile.ZipFile(staged) as new, zipfile.ZipFile(path) as old:
                if (new.namelist() != old.namelist() or json.loads(new.read("manifest.json")) != manifest or
                        new.read("README.md") != old.read("README.md") or
                        any(sha(new.read(key)) != value for key, value in payload.items())):
                    raise ValueError(f"Runtime readback failed: {path}")
            receipt.update(sha256=sha(staged.read_bytes()), bytes=staged.stat().st_size)
            staged_receipt = Path(tmp) / (label + "-receipt.json")
            staged_receipt.write_bytes(json_bytes(receipt))
            work.extend(((staged, path), (staged_receipt, receipt_path)))
            summary["profiles"][label] = {"archive": name, "sha256": receipt["sha256"],
                                          "paired_map": paired, "payloads_verified": len(payload)}
        for src, dst in work:
            os.replace(src, dst)
    return summary

"""Seal widened Nanite assemblies and authored material changes in the original IoStore owner."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "tools/iostore"))
sys.path.insert(0, str(ROOT / "tools/level"))
from iostore import load_container, read_chunk
from verify_pwr_surface_cook import imported_packages


def sha(path):
    return hashlib.file_digest(Path(path).open("rb"), "sha256").hexdigest()


def doc(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def run(cmd):
    proc = subprocess.run(list(map(str, cmd)), cwd=ROOT, capture_output=True, text=True)
    if proc.returncode:
        raise RuntimeError(proc.stdout[-1400:] + proc.stderr[-1400:])
    return proc.stdout


def scalar_properties(path, global_paks):
    dump = run(
        [
            ROOT / "target/release/examples/props_dump.exe",
            global_paks,
            ROOT / "defs/ue/Meteorite-2607-CU3.usmap",
            path,
        ]
    )
    props = dict(re.findall(r"^  (\S+) = (.+)$", dump, re.M))
    if "Parent" not in props:
        raise RuntimeError(dump)
    indices = {
        name: k.removesuffix(".ParameterInfo.Name")
        for k, name in props.items()
        if k.endswith(".ParameterInfo.Name")
    }
    return props, indices


def patch_material(old_path, new_path, profile, audit):
    original, index = scalar_properties(old_path, audit)
    requests = {
        "Tint": [*profile["color"], 1.0],
        "RoughMin": [profile["rough"][0]],
        "RoughMax": [profile["rough"][1]],
        "Variation": [profile["variance"]],
        "Metallic": [profile["metal"]],
    }
    data = bytearray(old_path.read_bytes())
    changes = {}
    for key, new in requests.items():
        row = index[key]
        assert (
            original[row + ".ParameterInfo.Index"] == "-1"
            and original[row + ".ParameterInfo.Association"] == "2"
        )
        old = [float(x) for x in original[row + ".ParameterValue"].split(",")]
        guid = bytes.fromhex(original[row + ".ExpressionGUID"])
        # Each serialized value precedes its parameter's exact GUID. Checking both
        # prevents a repeated roughness value from altering a different field.
        token = struct.pack("<" + "f" * len(old), *old) + guid
        if data.count(token) != 1:
            raise ValueError((old_path.name, key, "ambiguous property suffix"))
        i = data.index(token)
        data[i : i + len(old) * 4] = struct.pack("<" + "f" * len(new), *new)
        changes[key] = {"old": old, "expected": new}
    new_path.write_bytes(data)
    actual, new_index = scalar_properties(new_path, audit)
    assert index == new_index
    allowed = {index[k] + ".ParameterValue" for k in requests}
    assert {k for k in actual if original[k] != actual[k]} <= allowed
    assert set(actual) == set(original)
    for key, values in requests.items():
        read = [float(x) for x in actual[index[key] + ".ParameterValue"].split(",")]
        assert max(abs(x - y) for x, y in zip(read, values)) < 1e-6, (key, read, values)
        changes[key]["parsed"] = read
    return {
        "file": new_path.name,
        "replacements": changes,
        "preserved_other_parsed_properties": len(actual) - len(allowed),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", type=Path, required=True)
    ap.add_argument("--before", type=Path, required=True)
    ap.add_argument("--final-art", type=Path, required=True)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--recook", type=Path)
    args = ap.parse_args()
    b = args.build.resolve()
    old = load_container(next(args.before.glob("*955*.utoc")))
    new = load_container(next((args.recook or b / "retarget").glob("*955*.utoc")))
    sealed, before, replacements = (
        (args.out or b / "955").resolve(),
        b / "original-members",
        b / "replace-members",
    )
    before.mkdir(exist_ok=True)
    replacements.mkdir(exist_ok=True)
    sealed.mkdir(exist_ok=True)
    profiles = doc(args.final_art.parent / "pewter.json")["profiles"]
    materials = []
    changed = []
    for path, i in old.files.items():
        filename = Path(path).name
        key = Path(path).stem.removeprefix("MI_PWR_")
        is_arch = bool(
            re.fullmatch(
                r"SM_PWR_(red|blue|green)_architecture\.(uasset|ubulk)", filename
            )
        )
        is_material = filename.startswith("MI_PWR_") and key in profiles
        if not is_arch and not is_material:
            continue
        target = replacements / path
        target.parent.mkdir(exist_ok=True, parents=True)
        old_path = before / filename
        old_path.write_bytes(read_chunk(old, old.chunks[i]))
        if is_arch:
            native = next((k for k in new.files if k == path), None)
            if native is None:
                raise ValueError(("Cooked mesh absent", path, list(new.files)[:2]))
            member = new.chunks[new.files[native]]
            assert (old.chunks[i].chunk_id, old.chunks[i].chunk_type) == (
                member.chunk_id,
                member.chunk_type,
            )
            target.write_bytes(read_chunk(new, member))
            if target.suffix == ".uasset":
                assert imported_packages(old_path) == imported_packages(target), (
                    filename
                )
        else:
            materials.append(
                patch_material(old_path, target, profiles[key], b / "954/audit")
            )
        changed.append(path)
    assert len(changed) == 11 and len(materials) == 5, (changed, materials)
    log = run(
        [
            ROOT / "target/release/examples/replace_members.exe",
            old.utoc_path.resolve(),
            replacements,
            sealed,
        ]
    )
    (sealed / "splice.log").write_text(log)
    shipped = load_container(sealed / old.utoc_path.name)
    assert set(old.files) == set(shipped.files)
    for path in changed:
        i = shipped.files[path]
        assert (
            read_chunk(shipped, shipped.chunks[i]) == (replacements / path).read_bytes()
        )
    audit = sealed / "audit"
    audit.mkdir(exist_ok=True)
    for ext in (".utoc", ".ucas"):
        shutil.copy2(b / "954/audit" / ("global" + ext), audit / ("global" + ext))
        shutil.copy2(
            sealed / (old.utoc_path.stem + ext), audit / (old.utoc_path.stem + ext)
        )
    entries = run(
        [ROOT / "target/release/examples/store_entries.exe", audit, old.utoc_path.stem]
    )
    (sealed / "package-store.log").write_text(entries)
    if not re.search(r"\b0 different\b", entries):
        raise ValueError(entries)
    write(
        sealed / "ownership.json",
        {
            "passed": True,
            "stem": str((sealed / old.utoc_path.stem).resolve()),
            "files": {
                ext: sha(sealed / (old.utoc_path.stem + ext))
                for ext in (".utoc", ".ucas")
            },
            "changed_files": changed,
            "preserved_members": len(old.chunks) - len(changed),
            "source": str(old.utoc_path),
            "source_sha256": sha(old.utoc_path),
            "direct_cooked_material_readback": materials,
            "store_entries": entries.strip().splitlines()[-1],
        },
    )


if __name__ == "__main__":
    main()

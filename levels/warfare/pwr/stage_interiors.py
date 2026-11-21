"""Base interiors in a staged release: separated meshes, fixture lights and lamp glow.

Three things, all from data:

- `splice(inputs, cooked, hashes)`: the base meshes whose coplanar faces were separated
  (tools/level/separate_coplanar.py, re-imported and cooked in the base project) replace their
  members in the release's own base container, chunk 955, with replace_members, exactly as the
  widened gates were sealed (bases_v1/package_widened_gates.py). Every other member is untouched.
- `light(level, cli, paks, spec)`: level.lights for every fixture of the configured emissive slots
  (tools/level/emissive_lights.py), read from the release's own cooked meshes, and the same slots'
  glow raised to the level's physical exposure (a material binding on the slot).

    from stage_interiors import splice, light
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "tools/level"))
sys.path.insert(0, str(ROOT / "tools/iostore"))
CHUNK = 955
# The cook compresses with Oodle; the engine ships the decoder (OODLE overrides).
OODLE = [Path(os.environ.get("OODLE") or
              "C:/Program Files/Epic Games/UE_5.5/Engine/Binaries/DotNET/AutomationTool/AutomationScripts/BuildGraph/oo2core_9_win64.dll")]


def sha(path):
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def splice(inputs, cooked, hashes, manifest):
    """Replace the meshes `manifest` names (a separate_coplanar import manifest) in the release's
    chunk 955 with their freshly cooked members from the staged build folder `cooked`."""
    from iostore import load_container, read_chunk
    names = {a["asset"].removeprefix("/Game/") for a in json.loads(Path(manifest).read_text())["assets"]}
    old_toc = next(Path(inputs).glob(f"pakchunk{CHUNK}-*.utoc"))
    old = load_container(old_toc)
    new = load_container(next(Path(cooked).glob(f"pakchunk{CHUNK}-*.utoc")))

    def member(container, path):
        """A member by its content path, whatever the container's mount point."""
        key = next((k for k in container.files if k.split("Content/", 1)[-1] == path.split("Content/", 1)[-1]), None)
        return key
    changed = []
    with tempfile.TemporaryDirectory(dir=Path(inputs).parent) as tmp:
        replacements, sealed = Path(tmp) / "replace", Path(tmp) / "sealed"
        replacements.mkdir(); sealed.mkdir()
        for path, i in old.files.items():
            stem = path.split("Content/", 1)[-1].rsplit(".", 1)[0]
            if stem not in names:
                continue
            source = member(new, path)
            if source is None:
                raise ValueError("Cooked mesh absent: " + path)
            chunk = new.chunks[new.files[source]]
            if (old.chunks[i].chunk_id, old.chunks[i].chunk_type) != (chunk.chunk_id, chunk.chunk_type):
                raise ValueError("Cooked member has another identity: " + path)
            target = replacements / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(read_chunk(new, chunk, oodle_roots=OODLE))
            changed.append(path)
        if len({c.rsplit(".", 1)[0] for c in changed}) != len(names):
            raise ValueError("Some separated meshes are not in the release's base container")
        subprocess.run([str(ROOT / "target/release/examples/replace_members.exe"), str(old_toc.resolve()),
                        str(replacements), str(sealed)], check=True, capture_output=True, text=True, cwd=ROOT)
        shipped = load_container(sealed / old_toc.name)
        if set(old.files) != set(shipped.files):
            raise ValueError("The splice changed the container's members")
        for path in changed:
            if read_chunk(shipped, shipped.chunks[shipped.files[path]], oodle_roots=OODLE) != (replacements / path).read_bytes():
                raise ValueError("Spliced member differs: " + path)
        for ext in (".utoc", ".ucas"):
            shutil.copyfile(sealed / (old_toc.stem + ext), old_toc.with_suffix(ext))
            hashes["content/" + old_toc.stem + ext] = sha(old_toc.with_suffix(ext))
    return {"changed_members": sorted(changed), "preserved_members": len(old.files) - len(changed),
            "manifest_sha256": sha(manifest)}


def light(level, cli, paks, spec):
    """Fixture lights and lamp glow for the configured emissive slots."""
    import emissive_lights
    from forerunner_surfaces import slot_names
    cache, slots_of = {}, {}
    env = dict(os.environ, MSYS2_ARG_CONV_EXCL="*")
    with tempfile.TemporaryDirectory() as tmp:
        exported = {}
        for d in level.get("decor", []):
            mesh = d.get("mesh")
            if not mesh:
                continue
            names = slot_names(cli, paks, mesh, cache)
            slots_of[mesh] = names
            asset = mesh.rsplit(".", 1)[-1]
            if asset not in exported and any(n in spec["slots"] for n in names):
                out = Path(tmp) / f"{asset}.glb"
                subprocess.run([cli, "mesh", "export", "--paks", paks, "--asset", asset, "--out", str(out)],
                               check=True, capture_output=True, text=True, env=env)
                exported[asset] = out
        lights, report = emissive_lights.lights(level, exported.get, spec)
    level["lights"] = [l for l in level.get("lights") or [] if not str(l.get("source", "")).startswith("fixtures/")] + lights
    # The lamps themselves: the slot's own material, its emission raised to the level's exposure.
    glowing = 0
    for d in level.get("decor", []):
        names = slots_of.get(d.get("mesh")) or []
        if not any(spec["slots"].get(n, {}).get("glow") for n in names):
            continue
        mats = list(d.get("materials") or [])
        mats += [""] * (len(names) - len(mats))
        for i, n in enumerate(names):
            glow = spec["slots"].get(n, {}).get("glow")
            if glow and (mats[i] == "" or (isinstance(mats[i], dict) and mats[i].get("fixture_glow"))):
                mats[i] = dict(glow, fixture_glow=True)
                glowing += 1
        d["materials"] = mats
    return {"lights": len(lights), "by_slot": report, "glowing_slots": glowing}

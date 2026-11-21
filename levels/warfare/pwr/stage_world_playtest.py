"""Build the landscape playtest from the last verified flight release and map-owned cooks."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "tools/iostore"))
from iostore import load_container, read_chunk

from visual_dressing import sky_wildlife
from world_surfaces import bind

PWR = "pelican-warfare"
CODE = "PWR"
WORLD = "pakchunk997-MJOLNIRMAP-PWR_P"
LAND = "pakchunk965-MJOLNIRLAND-PWR_P"
SURFACES = "pakchunk956-MJOLNIRPWRSURFACES-PWR_P"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def jsonfile(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def verified(folder, receipt_name):
    info = jsonfile(folder / receipt_name)
    archive = folder / info["archive"]
    if sha(archive) != info["sha256"]:
        raise ValueError(f"Baseline receipt does not match {archive}")
    return archive, info


def member_hash(archive, name):
    with archive.open(name) as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def stage_name(member):
    path = PurePosixPath(member)
    if path.is_absolute() or ".." in path.parts or ":" in member or "\\" in member:
        raise ValueError(f"Unexpected archive path {member}")
    if path.parts[:1] == ("content",) and len(path.parts) == 2:
        return Path(path.name)
    if member == "map/registration.json":
        return Path("PWR.registration.json")
    if member == "map/level.json":
        return Path("pwr.level.json")
    if path.parts[:1] == ("map",):
        return Path(*path.parts[1:])
    raise ValueError(f"Unexpected map member {member}")


def world_entries(utoc):
    container = load_container(utoc)
    return {p: hashlib.sha256(read_chunk(container, container.chunks[i])).hexdigest()
            for p, i in container.files.items()}


def verify_world(prior, replacement):
    old, new = world_entries(prior), world_entries(replacement)
    if set(old) != set(new):
        raise ValueError("Landscape bake changed the world container inventory")
    changed = sorted(p for p in old if old[p] != new[p])
    level = "levels/halo1/solo/pwr/pwr"
    if not changed or not any(p.lower().endswith(level+".umap") for p in changed) or any(
            not p.lower().endswith((level+".umap", level+".ubulk")) for p in changed):
        raise ValueError(f"Expected only the Unreal world and its bulk data to change: {changed}")
    return {"changed": changed, "preserved": {p: h for p, h in old.items() if p not in changed}}


def verify_flux_look(previous, current):
    # A material change must preserve the six EXRs, their playback bindings,
    # domain order, wave actor, sources, and all upstream river settings.
    expected = json.loads(json.dumps(previous))
    allowed = {
        "surface_vectors": {"SurfaceScattering0", "SurfaceScattering1", "SurfaceAbsorption0",
                            "SurfaceAbsorption1", "SurfaceScatteringShoreline"},
        "surface_scalars": {"DetailWaveHeight", "DetailWaveLength", "WaterRoughnessMin"},
    }
    previous_lake, = (d for d in expected["domains"] if d["id"] == "lower_lake")
    current_lake, = (d for d in current["domains"] if d["id"] == "lower_lake")
    for group, names in allowed.items():
        for name in names:
            if name in current_lake[group]:
                previous_lake[group][name] = current_lake[group][name]
    if expected != current:
        raise ValueError("The lake finish may change only reviewed Coastline material settings")


def update_level(path):
    level = jsonfile(path)
    original = json.loads(json.dumps(level))
    bind(level)
    sky_wildlife.apply(level)
    touched = {k for k in level.keys() | original.keys() if original.get(k) != level.get(k)}
    if not touched <= {"decor", "environment", "effects", "landscape", "flux"}:
        raise ValueError(f"Dressing changed gameplay data: {touched}")
    verify_flux_look(original["flux"], level["flux"])
    write_json(path, level)
    return sorted(touched)


def pair_runtime(source, dest, paired, version):
    archive, info = verified(source, "developer-runtime-receipt.json")
    name = f"{PWR}-runtime-{version}.zip"
    dest.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as prior, zipfile.ZipFile(dest / name, "w") as new:
        manifest = json.loads(prior.read("manifest.json"))
        if manifest["paired_map"] != info["paired_map"]:
            raise ValueError("Runtime baseline map reference disagrees with its receipt")
        previous = manifest["paired_map"]["name"]
        manifest.update(version=version, paired_map=paired)
        for item in prior.infolist():
            data = prior.read(item)
            if item.filename == "manifest.json":
                data = (json.dumps(manifest, indent=2)+"\n").encode()
            elif item.filename == "README.md":
                data = data.replace(previous.encode(), paired["name"].encode())
            elif hashlib.sha256(data).hexdigest() != manifest["payload_sha256"][item.filename]:
                raise ValueError(f"Runtime payload differs from receipt: {item.filename}")
            new.writestr(item, data)
    with zipfile.ZipFile(dest / name) as new:
        if json.loads(new.read("manifest.json")) != manifest or any(
                member_hash(new, key) != value for key, value in manifest["payload_sha256"].items()):
            raise ValueError("Paired runtime failed archive readback")
    info.update(archive=name, version=version, sha256=sha(dest/name),
                bytes=(dest/name).stat().st_size, paired_map=paired, installed=False)
    write_json(dest/"developer-runtime-receipt.json", info)


def build(args, out):
    previous, prior_info = verified(args.baseline, "receipt.json")
    inputs = out/"map-input"
    inputs.mkdir()
    with zipfile.ZipFile(previous) as prior:
        expected = {}
        for name in prior.namelist():
            if name == "mjolnir.json":
                continue
            target = inputs / stage_name(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            with prior.open(name) as src, target.open("xb") as dst:
                shutil.copyfileobj(src, dst)
            expected[name] = sha(target)
        old_manifest = json.loads(prior.read("mjolnir.json"))

    native = verify_world(inputs/(WORLD+".utoc"), args.world)
    verified_surfaces = jsonfile(args.surfaces.parent/"receipt.json")
    if verified_surfaces["container"] != args.surfaces.stem or any(
            sha(args.surfaces.parent/name) != h for name,h in verified_surfaces["files_sha256"].items()):
        raise ValueError("Surface cook has changed since its shader and texture readback")
    for stem, source in ((WORLD,args.world),(LAND,args.land),(SURFACES,args.surfaces)):
        if source.suffix != ".utoc" or not source.name.startswith(stem.split("-")[0]+"-"):
            raise ValueError(f"Unexpected container for {stem}: {source}")
        for suffix in (".utoc",".ucas"):
            target = inputs/(stem+suffix)
            shutil.copyfile(source.with_suffix(suffix), target)
            expected["content/"+target.name] = sha(target)
    level_path = inputs/"pwr.level.json"
    sections = update_level(level_path)
    expected["map/level.json"] = sha(level_path)
    filename = f"{PWR}-{args.version}.mjolnir"
    result = out/filename
    runtime = prior_info["ce_content_runtime"]
    subprocess.run([str(args.cli), "map","pack",str(inputs),"--code",CODE,"--runtime",runtime,
                    "--slug",PWR,"--version",args.version,"--name","Pelican Warfare","--size","large",
                    "--vehicles","true","--out",str(result)],cwd=ROOT,check=True)
    with zipfile.ZipFile(result) as packed:
        if set(packed.namelist()) != set(expected) | {"mjolnir.json"}:
            raise ValueError("Incomplete packed world")
        if any(member_hash(packed, name) != h for name,h in expected.items()):
            raise ValueError("Packed map differs from the verified inputs")
        if json.loads(packed.read("mjolnir.json")) != dict(old_manifest, version=args.version):
            raise ValueError("Unexpected manifest changes")
    paired = {"name":filename,"sha256":sha(result),"content_runtime":runtime}
    for folder, dest in ((args.baseline,out),(args.solo,out/"solo")):
        if jsonfile(folder/"developer-runtime-receipt.json")["paired_map"]["sha256"] != prior_info["sha256"]:
            raise ValueError(f"Flight runtime in {folder} belongs to a different map")
        pair_runtime(folder,dest,paired,args.version)
    shutil.copytree(args.baseline/"variants", out/"variants")
    for profile, files in prior_info["variants"].items():
        for name, h in files.items():
            if sha(out/"variants"/profile/name) != h:
                raise ValueError(f"Baseline variant changed: {name}")
    write_json(out/"receipt.json", {"archive":filename,"sha256":paired["sha256"],"bytes":result.stat().st_size,
               "ce_content_runtime":runtime,"variants":prior_info["variants"],"baseline_sha256":prior_info["sha256"],
               "level_sections":sections,"world_packages":native,"members_sha256":expected})
    return filename


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("baseline","solo","surfaces","land","world","out"):
        parser.add_argument("--"+option,type=Path,required=True)
    parser.add_argument("--version",default="0.1.0-playtest.4")
    parser.add_argument("--cli",type=Path,default=ROOT/"target/release/mjolnir.exe")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+-playtest\.[0-9]+",args.version):
        parser.error("Expected a numbered playtest version")
    if args.out.exists():
        parser.error("Choose a fresh output folder")
    args.out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.out.parent) as temp:
        staging=Path(temp)/"release"
        staging.mkdir()
        name=build(args,staging)
        os.rename(staging,args.out)
    print(f"Verified {args.out/name}")

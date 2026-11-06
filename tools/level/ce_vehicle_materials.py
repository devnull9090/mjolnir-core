#!/usr/bin/env python3
"""Cook a CE vehicle's materials as real material instances.

    ce_vehicle_materials.py <materials.spec.json> <Name> <out dir> [--set Param=value ...] [--plan]

`materials.spec.json` is ce_vehicle_mesh.py's. A vehicle has no level to replay
it: it spawns late, on every client, and a part's material has to arrive with
the part. So each slot's material is cooked as a MaterialInstanceConstant of its
CE master, under /Game/MJOLNIR/Maps/<CODE>/Vehicles (not Materials, which
build_ce_level.py clears), and ce_vehicle_mesh.py --instances points the mesh's
slot at it. Nothing runs per spawn.

Steps: build_ce_level.py imports the bitmaps, ce_vehicle_instances_editor.py
makes the instances, cook.ps1 cooks and re-encodes them in the game's layout
(once: never retarget the copy). The chunk is copied to <out dir> as
pakchunk985-MJOLNIRCOOK-<CODE>_P. Only the instances and textures ship: a
master stays the runtime pack's, and a chunk holding anything else stops here.

Every cooked instance is read back: no static permutation (an instance of a
master with no static switches has no shaders of its own, so its package must
carry none), and every parameter of the spec present with its value.

Writes <Name>.instances.json: `{"folder", "overrides", "instances": [{"material",
"slot", "package", "object", "parent", "textures", "scalars", "vectors"}]}`.

--set puts a scalar on every instance whose master has it (`overrides`). A
converted map's own world wants the masters' defaults. Inside B40's world (a test map's canvas) the game's colour
correction scales the shown colour by about 0.6: --set DisplayGain=0.6 undoes it.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
PROJECT = os.path.join(REPO, "unreal", "MJOLNIRMaterials")
STAGED = os.path.join(PROJECT, "Saved", "StagedBuilds", "Windows", "Meteorite", "Content", "Paks")
sys.path.insert(0, HERE)
from ce_material_spec import asset_name  # noqa: E402


def parent_of(material, masters):
    """The master, moved to `masters` when a skinned mesh needs its copies."""
    parent = material["parent"]
    return f"{masters.rstrip('/')}/{parent.rsplit('/', 1)[1]}" if masters else parent


def instances(spec, name, code, overrides, masters=None):
    folder = f"{spec['root']}/Vehicles"
    out = []
    for slot in spec["slots"]:
        m = slot["material"]
        leaf = asset_name(f"MI_{code}_{name}_", slot["name"])
        package = f"{folder}/{leaf}"
        out.append({"material": slot["name"], "slot": f"s_{slot['name']}", "package": package,
                    "object": f"{package}.{leaf}", "parent": parent_of(m, masters), "textures": m.get("textures", {}),
                    "scalars": m.get("scalars", {}), "vectors": m.get("vectors", {})})
    return {"folder": folder, "overrides": overrides, "instances": out}


def powershell(script, *args, env=None):
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script, *args],
                       env={**os.environ, **(env or {})}, capture_output=True, text=True, errors="replace")
    print(r.stdout.strip()[-1500:])
    if r.returncode:
        sys.exit(f"{script} failed:\n{r.stderr[-2000:]}")
    return r.stdout


def rows(mjolnir, package):
    env = {**os.environ, "MSYS_NO_PATHCONV": "1", "HCE_PAKS": STAGED}
    r = subprocess.run([mjolnir, "ue", "get", "--package", package], env=env, capture_output=True, text=True,
                       errors="replace")
    if r.returncode:
        sys.exit(f"ue get {package}: {r.stderr[-1000:]}")
    return r.stdout


def values(text, field):
    """{parameter name: value text} of a `ue get` listing's array."""
    names = dict(re.findall(rf"{field}\[(\d+)\]\.ParameterInfo\.Name = (.+?)   \(", text))
    got = dict(re.findall(rf"{field}\[(\d+)\]\.ParameterValue = (.+?)   \(", text))
    return {name: got.get(i, "0") for i, name in names.items()}


def read_back(mjolnir, entry, dropped, overrides):
    """Stop unless the cooked package says what the entry does, less what its
    master has no parameter for, and carries `overrides` where it has them."""
    text = rows(mjolnir, entry["package"])
    if "bHasStaticPermutationResource = true" in text:
        sys.exit(f"{entry['package']}: a static permutation, so shaders of its own: stop")
    scalars = values(text, "ScalarParameterValues")
    wanted = {**entry["scalars"], **{k: v for k, v in overrides.items() if k in scalars}}
    for name, want in wanted.items():
        if name in dropped:
            continue
        got = scalars.get(name, "0").replace(" (zeroed)", "")
        if abs(float(got) - float(want)) > 1e-4 * max(1.0, abs(float(want))):
            sys.exit(f"{entry['package']}: scalar {name} is {got}, wanted {want}")
    textures = values(text, "TextureParameterValues")
    missing = set(entry["textures"]) - set(textures)
    if missing:
        sys.exit(f"{entry['package']}: no texture {sorted(missing)}")
    vectors = values(text, "VectorParameterValues")
    for name, want in entry["vectors"].items():
        if name in dropped:
            continue
        got = vectors.get(name)
        if got is None:
            if any(abs(x) > 1e-6 for x in want):
                sys.exit(f"{entry['package']}: no vector {name}")
            continue
        got = [float(x) for x in got.replace(" (zeroed)", "").split(",")]
        if any(abs(a - b) > 1e-4 * max(1.0, abs(b)) for a, b in zip(got, want)):
            sys.exit(f"{entry['package']}: vector {name} is {got}, wanted {want}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("spec")
    ap.add_argument("name")
    ap.add_argument("out")
    ap.add_argument("--set", action="append", default=[], metavar="Param=value")
    ap.add_argument("--plan", action="store_true", help="write the instances file, run nothing")
    ap.add_argument("--masters", help="the folder of masters that carry skeletal usage, for a skinned mesh's instances")
    ap.add_argument("--mjolnir", default=os.path.join(REPO, "target", "release", "mjolnir.exe"))
    ap.add_argument("--paks", default=os.environ.get("HCE_PAKS"), help="read only: the stub .pak comes from here")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    spec = json.load(open(a.spec, encoding="utf-8"))
    code = spec["root"].rsplit("/", 1)[1]
    overrides = {k: float(v) for k, v in (s.split("=", 1) for s in a.set)}
    plan = instances(spec, a.name, code, overrides, a.masters)
    path = os.path.abspath(os.path.join(a.out, f"{a.name.lower()}.instances.json"))
    json.dump(plan, open(path, "w", encoding="utf-8"), indent=1)
    print(f"{len(plan['instances'])} instance(s) -> {path}")
    if a.plan:
        return
    if not a.paks:
        sys.exit("--paks or HCE_PAKS: Meteorite/Content/Paks")

    ue = os.path.join(REPO, "tools", "ue")
    editor = os.path.join(ue, "editor_cmd.ps1")
    powershell(editor, "-Script", "Scripts/build_ce_level.py", env={"MJ_CE_SPEC": os.path.abspath(a.spec)})
    powershell(editor, "-Script", "..\\..\\tools\\level\\ce_vehicle_instances_editor.py", env={"MJ_CE_INSTANCES": path})
    log = os.path.join(PROJECT, "Saved_ce_vehicle_instances_editor.log")
    if f"MJOLNIR vehicle instances: {len(plan['instances'])}" not in open(log, encoding="utf-8", errors="replace").read():
        sys.exit(f"the instances did not build: see {log}")
    out = powershell(os.path.join(ue, "cook.ps1"), env={"MJOLNIR": a.mjolnir})
    if "cook exit 0" not in out or "BUILD SUCCESSFUL" not in out:
        sys.exit("the cook failed: see unreal/MJOLNIRMaterials/Saved_cook.log; no chunk copied")

    listing = subprocess.run([os.path.join(REPO, "target", "release", "examples", "container_ls.exe"), STAGED,
                              f"pakchunk{spec['chunk']}-"], capture_output=True, text=True).stdout
    # container_ls prints paths from the container's mount point, the longest
    # prefix they share: the map's folder, unless something else got in.
    foreign = [l.strip() for l in listing.splitlines()[1:] if not l.strip().startswith(("Textures/", "Vehicles/"))]
    if foreign:
        sys.exit(f"the chunk holds more than this map's packages: {foreign}")
    dropped = json.load(open(path + ".dropped", encoding="utf-8"))
    for entry in plan["instances"]:
        read_back(a.mjolnir, entry, dropped[entry["package"]], plan["overrides"])
    stem = f"pakchunk985-MJOLNIRCOOK-{code}_P"
    for e in ("utoc", "ucas"):
        shutil.copyfile(os.path.join(STAGED, f"pakchunk{spec['chunk']}-Windows.{e}"), os.path.join(a.out, f"{stem}.{e}"))
    # The game mounts a .utoc/.ucas pair only beside a .pak.
    shutil.copyfile(os.path.join(a.paks, "pakchunk115-Windows.pak"), os.path.join(a.out, f"{stem}.pak"))
    print(f"read back {len(plan['instances'])} instance(s); pakchunk{spec['chunk']} -> {os.path.join(a.out, stem)}")


if __name__ == "__main__":
    main()

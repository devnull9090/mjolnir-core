"""Give published hub maps bots: rebake each map pack's scenario with the
bots lane (defs/level/bots.json, docs/bots.md) and pack it as the next
release of the same listing.

    python tools/level/add_bots.py <pack.mjolnir>... --version-bump minor --runtime ^1.15.0 [--sign]

Bots live in the scenario (squads, a zone, an objective and the generated
`ai pathfinding data`) and in one BSP flag, which the simulation reads when
the map loads, so they cannot be added at run time. Nothing else needs
rebuilding: the bake runs from the pack alone, the way the map was baked
(`level bake --standalone <CODE> --bsp <i>=<the pack's BSP> --world <the
pack's world>`), with the level file the pack ships less the keys only the
loader reads, plus `blam.bots`. Every other container, and every package of
the map container but the scenario, must come out byte-identical; the script
checks that and stops otherwise. The shipped level file is packed unchanged.

Work goes to <work>/<CODE>/; packs to <out>/<slug>-<version>.mjolnir.
Set HCE_PAKS to the game's Meteorite/Content/Paks (the canvas scenario).
"""
import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
CLI = os.environ.get("MJOLNIR", os.path.join(REPO, "target", "release", "mjolnir.exe"))
EXTRACT = os.environ.get("EXTRACT_FILE", os.path.join(REPO, "target", "debug", "examples", "extract_file.exe"))
BOTS = os.path.join(REPO, "defs", "level", "bots.json")
# The level file's keys `level bake` takes; the rest are the loader's own
# (landscape, effects, shadow_shell, flux ...).
BAKE_KEYS = {"schema_version", "name", "title", "author", "description", "canvas", "multiplayer", "variant",
             "game", "modes", "environment", "blam", "decor", "markers", "ctf", "health_pack", "vehicle_sets",
             "foliage"}
MACHINE = re.compile(r"-MJOLNIRMACH-[A-Z0-9]{3}-")


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode:
        sys.exit(f"failed: {' '.join(map(str, cmd))}\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}")
    return r.stdout


def bump(version, part):
    core = version.split("-")[0].split("+")[0]
    major, minor, patch = (int(x) for x in core.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def packages(utoc_dir, stem, paks):
    """The package paths a container holds (`mjolnir container`)."""
    out = run([CLI, "container", "--paks", paks, os.path.join(utoc_dir, f"{stem}.utoc")])
    return sorted({m.group(1) for m in re.finditer(r"\.\./\.\./\.\./Meteorite/Content/(\S+)", out)})


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def container_dir(parent, name, src_stem, stub):
    """A folder holding one container and a stub .pak, as the readers want."""
    d = os.path.join(parent, name)
    os.makedirs(d, exist_ok=True)
    for e in ("utoc", "ucas"):
        shutil.copyfile(f"{src_stem}.{e}", os.path.join(d, f"{os.path.basename(src_stem)}.{e}"))
    shutil.copyfile(stub, os.path.join(d, f"{os.path.basename(src_stem)}.pak"))
    return d


def one(pack, a, defaults):
    z = zipfile.ZipFile(pack)
    manifest = json.loads(z.read("mjolnir.json"))
    m = manifest["map"]
    code = m["code"]
    slug = re.sub(r"-\d+\.\d+\.\d+(-[0-9A-Za-z.]+)?$", "", os.path.basename(pack)[: -len(".mjolnir")])
    version = a.version or bump(manifest["version"], a.version_bump)
    w = os.path.join(a.work, code)
    if os.path.isdir(w):
        shutil.rmtree(w)
    unpacked = os.path.join(w, "pack")
    z.extractall(unpacked)
    names = z.namelist()
    known = {"mjolnir.json", "signature.json", "docs/README.md", "map/level.json", "map/registration.json"}
    level = json.load(open(os.path.join(unpacked, "map", "level.json"), encoding="utf-8"))
    foliage = (level.get("foliage") or {}).get("file")
    for n in names:
        if n in known or n.startswith("content/") or n.startswith("map/decals/") or n == f"map/{foliage}":
            continue
        sys.exit(f"{code}: {n} in the pack is not one this script repacks")
    print(f"== {code} ({slug}) {manifest['version']} -> {version}", flush=True)

    # The bake input.
    bake_level = {k: v for k, v in level.items() if k in BAKE_KEYS}
    if "bots" in bake_level.get("blam", {}):
        sys.exit(f"{code}: the shipped level already has blam.bots")
    bake_level["blam"]["bots"] = {k: v for k, v in defaults.items() if not k.startswith("_")}
    blam = bake_level["blam"]
    index = blam.get("single_bsp")
    if index is None:
        index = (blam.get("active_bsps") or [None])[0]
    if index is None:
        sys.exit(f"{code}: the level names no BSP (single_bsp / active_bsps)")
    bake_file = os.path.join(w, f"{code.lower()}.level.json")
    json.dump(bake_level, open(bake_file, "w", encoding="utf-8"), indent=1)

    # The map container's BSP and world, out of the pack.
    content = os.path.join(unpacked, "content")
    stem = f"pakchunk997-MJOLNIRMAP-{code}_P"
    if not os.path.exists(os.path.join(content, f"{stem}.utoc")):
        sys.exit(f"{code}: no {stem} in the pack")
    stub = os.path.join(a.paks, "pakchunk115-Windows.pak")
    src = container_dir(w, "src", os.path.join(content, stem), stub)
    tags = os.path.join(w, "tags")
    run([CLI, "extract", "--paks", src, "--out", tags, "--group", "scenario_structure_bsp"])
    bsps = glob.glob(os.path.join(tags, "**", "*.scenario_structure_bsp"), recursive=True)
    if len(bsps) != 1:
        sys.exit(f"{code}: {len(bsps)} BSPs in the map container, expected one: {bsps}")
    shipped = packages(src, stem, a.paks)
    worlds = [p for p in shipped if p.startswith("Levels/") and p.endswith(".umap")]
    bake = [CLI, "level", "bake", bake_file, "--paks", a.paks, "--standalone", code,
            "--bsp", f"{index}={bsps[0]}", "--out-dir", os.path.join(w, "bake")]
    if len(worlds) == 1:
        world = os.path.join(w, os.path.basename(worlds[0]))
        run([EXTRACT, src, worlds[0], world])
        bulk = worlds[0][: -len(".umap")] + ".ubulk"
        if bulk in shipped:
            run([EXTRACT, src, bulk, world[: -len(".umap")] + ".ubulk"])
        bake += ["--world", world]
    elif worlds:
        sys.exit(f"{code}: {len(worlds)} worlds in the map container")
    else:
        reg = json.load(open(os.path.join(unpacked, "map", "registration.json"), encoding="utf-8"))
        bake += ["--world-object", reg["world"]]
    log = run(bake)
    open(os.path.join(w, "bake.log"), "w", encoding="utf-8").write(log)
    for line in log.splitlines():
        if line.lstrip().startswith(("bots", "note")):
            print("  " + line.strip())

    # Only the scenario may differ.
    built = container_dir(w, "built", os.path.join(w, "bake", stem), stub)
    new = packages(built, stem, a.paks)
    if new != shipped:
        sys.exit(f"{code}: the rebaked container holds {new}, the shipped one {shipped}")
    for p in shipped:
        if p.endswith(("-scenario.uasset", "-scenario.ubulk")):
            continue
        x, y = os.path.join(w, "x.bin"), os.path.join(w, "y.bin")
        run([EXTRACT, src, p, x])
        run([EXTRACT, built, p, y])
        if sha(x) != sha(y):
            sys.exit(f"{code}: {p} changed in the rebake")
        os.remove(x)
        os.remove(y)
    print(f"  {len(shipped) - 2} other package(s) of the map container unchanged", flush=True)
    if a.bake_only:
        return None

    # Stage the pack as `map pack` reads a conversion folder.
    stage = os.path.join(w, "stage")
    os.makedirs(os.path.join(stage, "machines"), exist_ok=True)
    for f in glob.glob(os.path.join(content, "*.utoc")):
        s = os.path.basename(f)[: -len(".utoc")]
        if s == stem:
            for e in ("utoc", "ucas"):
                shutil.copyfile(os.path.join(w, "bake", f"{stem}.{e}"), os.path.join(stage, f"{stem}.{e}"))
            continue
        to = os.path.join(stage, "machines") if MACHINE.search(s) else stage
        for e in ("utoc", "ucas"):
            shutil.copyfile(os.path.join(content, f"{s}.{e}"), os.path.join(to, f"{s}.{e}"))
    shutil.copyfile(os.path.join(unpacked, "map", "level.json"), os.path.join(stage, f"{code.lower()}.level.json"))
    shutil.copyfile(os.path.join(unpacked, "map", "registration.json"), os.path.join(stage, f"{code}.registration.json"))
    if foliage:
        shutil.copyfile(os.path.join(unpacked, "map", foliage), os.path.join(stage, foliage))
    if os.path.isdir(os.path.join(unpacked, "map", "decals")):
        shutil.copytree(os.path.join(unpacked, "map", "decals"), os.path.join(stage, "decals"))

    os.makedirs(a.out, exist_ok=True)
    archive = os.path.join(a.out, f"{slug}-{version}.mjolnir")
    cmd = [CLI, "map", "pack", stage, "--code", code, "--version", version, "--slug", slug,
           "--name", manifest["name"], "--summary", manifest.get("summary", ""), "--runtime", a.runtime,
           "--game", m.get("game", "halo1"), "--out", archive]
    if m.get("size"):
        cmd += ["--size", m["size"]]
    if m.get("players"):
        cmd += ["--players", f"{m['players']['min']}-{m['players']['max']}"]
    if "vehicles" in m:
        cmd += ["--vehicles", "true" if m["vehicles"] else "false"]
    if "docs/README.md" in names:
        cmd += ["--readme", os.path.join(unpacked, "docs", "README.md")]
    if a.sign:
        cmd.append("--sign")
    run(cmd)

    # The new pack holds what the old one did, the map container and
    # manifest aside.
    nz = zipfile.ZipFile(archive)
    old = {n: z.getinfo(n).CRC for n in names if n not in ("mjolnir.json", "signature.json")}
    got = {n: nz.getinfo(n).CRC for n in nz.namelist() if n not in ("mjolnir.json", "signature.json")}
    changed = {n for n in set(old) | set(got) if old.get(n) != got.get(n)}
    if f"content/{stem}.ucas" not in changed or changed - {f"content/{stem}.ucas", f"content/{stem}.utoc"}:
        sys.exit(f"{code}: the new pack differs from the old in {changed}")
    print(f"  {archive}: {os.path.getsize(archive) / 2 ** 20:.1f} MiB", flush=True)
    return archive


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("packs", nargs="+")
    ap.add_argument("--version", help="the new version (one map); else --version-bump of each pack's")
    ap.add_argument("--version-bump", choices=("major", "minor", "patch"), default="minor")
    ap.add_argument("--runtime", required=True, help="the runtime pack range with the bot characters")
    ap.add_argument("--work", default="C:/haloce/ce_conversions/bots/work")
    ap.add_argument("--out", default="C:/haloce/ce_conversions/bots/packs")
    ap.add_argument("--paks", default=os.environ.get("HCE_PAKS"))
    ap.add_argument("--sign", action="store_true", help="sign with this machine's device key")
    ap.add_argument("--bake-only", action="store_true", help="rebake and check, pack nothing")
    a = ap.parse_args()
    if not a.paks:
        sys.exit("set HCE_PAKS or pass --paks")
    if a.version and len(a.packs) > 1:
        sys.exit("--version takes one pack")
    defaults = json.load(open(BOTS, encoding="utf-8"))
    failed = []
    for pack in a.packs:
        try:
            one(pack, a, defaults)
        except SystemExit as e:
            print(f"  FAILED: {e}", flush=True)
            failed.append(os.path.basename(pack))
    if failed:
        sys.exit(f"{len(failed)} failed: {failed}")


if __name__ == "__main__":
    main()

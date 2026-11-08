"""Give published hub maps their objectives: run ce_objectives.py on each map
pack's level file, rebake the scenario and pack the next release of the same
listing. Publishes nothing: the packs stay in <out> until someone uploads them.

    python tools/level/add_objectives.py <pack.mjolnir>... --paks <Paks> [--version-bump minor] [--sign]

King's hills, Oddball's ball spawns and Race's flags are placements in the
scenario, so a map cannot gain them at run time. Health pack spots move to the
eighth team in the same pass, out of the spawn search. The bake runs from the
pack alone, as add_bots.py's does, with `blam.bots` put back when the pack has
bots: the shipped level file does not carry them, and a bake without them would
drop the map's squads. Then only these may differ from the old pack:

- the map container's scenario (every other package in it is compared);
- `map/level.json`: `modes`, `koth_hills`, `race_flags` and `blam.objects`,
  where the old objects stay as they were but for the health spots' team;
- `map/bots.json`, if the bake moved a squad, which is reported.

The script stops otherwise. The runtime range stays the pack's own unless
--runtime names another. Set MJOLNIR and EXTRACT_FILE if the tools are not in
this tree's target folder.

Work goes to <work>/<CODE>/; packs to <out>/<slug>-<version>.mjolnir.
"""
import argparse
import copy
import glob
import json
import os
import re
import shutil
import sys
import zipfile

import ce_objectives
import ce_place_vehicles
from add_bots import BAKE_KEYS, BOTS, CLI, EXTRACT, MACHINE, REPO, bump, container_dir, flux_members, packages, run, sha
from ce_place_vehicles import ce_scenario

RUNTIME = "mjolnir-ce-runtime"
# What ce_objectives.apply writes at the top of a level file.
LEVEL_KEYS = {"modes", "koth_hills", "race_flags"}
OBJECTIVE_LABELS = {ce_objectives.HILL_LABEL, ce_objectives.BALL_LABEL, ce_objectives.RACE_LABEL}
SCENARIO = ("-scenario.uasset", "-scenario.ubulk")


def without(level, keys):
    """A level less some top-level keys and `blam.objects`."""
    rest = {k: v for k, v in level.items() if k not in keys}
    rest["blam"] = {k: v for k, v in level["blam"].items() if k != "objects"}
    return rest


def _plain(item):
    """An object as a level holds it, its owner team aside."""
    return {**item, "set": {k: v for k, v in item.get("set", {}).items() if k != "multiplayer data.owner team"}}


def unlabelled(level):
    """A copy of a level with its vehicles' set labels taken out."""
    level = copy.deepcopy(level)
    for vehicle in level["blam"].get("vehicles", []):
        vehicle.get("set", {}).pop(ce_objectives.LABEL, None)
    for row in level.get("vehicle_sets") or []:
        row.pop("label", None)
    return level


def level_changes(old, new, labels=False):
    """What differs between two level files, as messages; empty if only what
    ce_objectives.py may write does, and with `labels` the vehicle labels."""
    if labels:
        old, new = unlabelled(old), unlabelled(new)
    problems = []
    if without(old, LEVEL_KEYS) != without(new, LEVEL_KEYS):
        problems.append("keys ce_objectives.py does not write changed")
    kept = [o for o in new["blam"]["objects"] if o.get("set", {}).get(ce_objectives.LABEL) not in OBJECTIVE_LABELS]
    was = [o for o in old["blam"]["objects"] if o.get("set", {}).get(ce_objectives.LABEL) not in OBJECTIVE_LABELS]
    if [_plain(o) for o in kept] != [_plain(o) for o in was]:
        problems.append("objects other than the objectives changed")
    for before, after in zip(was, kept):
        team = "multiplayer data.owner team"
        if (before.get("set", {}).get(team) != after.get("set", {}).get(team)
                and after["set"].get(ce_objectives.LABEL) != ce_objectives.HEALTH_LABEL):
            problems.append(f"{after.get('tag')} changed team")
    return problems


def manifest_changes(old, new):
    """What differs between two pack manifests, but for the release's own
    fields."""
    def rest(m):
        out = {k: v for k, v in m.items() if k not in ("version", "deps")}
        out["map"] = {k: v for k, v in m["map"].items() if k != "modes"}
        return out
    return [] if rest(old) == rest(new) else [f"{rest(old)} became {rest(new)}"]


def runtime_range(manifest):
    """The runtime range a pack asks for, and any other dependency, which
    `map pack` could not carry over."""
    deps = manifest.get("deps", [])
    others = [d for d in deps if d["slug"] != RUNTIME]
    return next((d["range"] for d in deps if d["slug"] == RUNTIME), None), others


class Pack:
    """A published pack, unpacked to <work>/<CODE>/pack, and what its next
    release keeps of it: slug, runtime range, the shipped level file."""

    def __init__(self, path, a):
        self.z = zipfile.ZipFile(path)
        self.manifest = json.loads(self.z.read("mjolnir.json"))
        self.code = code = self.manifest["map"]["code"]
        self.slug = re.sub(r"-\d+\.\d+\.\d+(-[0-9A-Za-z.]+)?$", "", os.path.basename(path)[: -len(".mjolnir")])
        self.version = a.version or bump(self.manifest["version"], a.version_bump)
        self.w = os.path.join(a.work, code)
        if os.path.isdir(self.w):
            shutil.rmtree(self.w)
        self.unpacked = os.path.join(self.w, "pack")
        self.z.extractall(self.unpacked)
        self.names = self.z.namelist()
        known = {"mjolnir.json", "signature.json", "docs/README.md", "map/level.json", "map/registration.json",
                 "map/bots.json", "map/vehicle_sounds.json"}
        with open(os.path.join(self.unpacked, "map", "level.json"), encoding="utf-8") as stream:
            self.level = json.load(stream)
        runtime, others = runtime_range(self.manifest)
        self.runtime = a.runtime or runtime
        # `map pack` gives a map one dependency per Forge pack its level
        # names, as these.
        forge = [{"slug": f["slug"], "range": f"^{f['version']}"}
                 for f in self.level["blam"].get("forge_packs", [])]
        if sorted(others, key=str) != sorted(forge, key=str) or not self.runtime:
            sys.exit(f"{code}: deps {self.manifest.get('deps')} are not one runtime range and the level's "
                     "Forge packs; pass --runtime or pack by hand")
        self.water = flux_members(self.z, self.level)
        known.update(self.water)
        self.foliage = (self.level.get("foliage") or {}).get("file")
        for n in self.names:
            if (n in known or n.startswith("content/") or n.startswith("map/decals/")
                    or n == f"map/{self.foliage}"):
                continue
            sys.exit(f"{code}: {n} in the pack is not one this script repacks")


def one(pack, a, bots):
    p = Pack(pack, a)
    shipped_level = p.level
    level = ce_objectives.apply(copy.deepcopy(shipped_level), race=not a.no_race)
    if a.vehicle_plan:
        scenario = ce_scenario.Scenario(a.map, a.tags)
        with open(a.vehicle_plan, encoding="utf-8") as stream:
            level = ce_place_vehicles.relabel(level, ce_place_vehicles.scenario_rows(scenario), json.load(stream))
    if level == shipped_level:
        print(f"== {p.code}: already has its objectives", flush=True)
        return None
    problems = level_changes(shipped_level, level, labels=bool(a.vehicle_plan))
    if problems:
        sys.exit(f"{p.code}: {problems}")
    labels = [o.get("set", {}).get(ce_objectives.LABEL) for o in level["blam"]["objects"]]
    print(f"== {p.code} ({p.slug}) {p.manifest['version']} -> {p.version}: modes {level['modes']}, "
          f"{labels.count(ce_objectives.HILL_LABEL)} hills, {labels.count(ce_objectives.BALL_LABEL)} ball spawns, "
          f"{labels.count(ce_objectives.RACE_LABEL)} race flags"
          + (f" of radius {level['race_flags'][0][3] / 100:.2f} m" if level.get("race_flags") else ""), flush=True)
    return repack(p, level, a, bots)


def repack(p, level, a, bots):
    """Rebake a pack's scenario from `level` and pack the next release: the
    map container's other packages must come out byte for byte, and the new
    pack may differ from the old only in that container, the level file and
    the bots' starts. Returns the new archive (None with --bake-only)."""
    z, manifest, m, code = p.z, p.manifest, p.manifest["map"], p.code
    slug, version, runtime, w, unpacked, names = p.slug, p.version, p.runtime, p.w, p.unpacked, p.names
    water, foliage = p.water, p.foliage

    # The bake input. Keys only the loader reads stay out, koth_hills and
    # race_flags with them.
    has_bots = "map/bots.json" in names
    bake_level = {k: copy.deepcopy(v) for k, v in level.items() if k in BAKE_KEYS}
    # A level that names its own bots keeps them; the bake must then give the
    # starts the map already ships.
    own_bots = "bots" in bake_level["blam"]
    if has_bots and not own_bots:
        bake_level["blam"]["bots"] = bots
    blam = bake_level["blam"]
    index = blam.get("single_bsp")
    if index is None:
        index = (blam.get("active_bsps") or [None])[0]
    if index is None:
        sys.exit(f"{code}: the level names no BSP (single_bsp / active_bsps)")
    # A level's own script compiles beside its level; the pack carries only the
    # compiled result, so the source comes from this repository.
    script = blam.get("script")
    if script:
        source = os.path.join(REPO, "tools", "level", "data", script)
        if not os.path.exists(source):
            sys.exit(f"{code}: blam.script {script} is not in tools/level/data")
        shutil.copyfile(source, os.path.join(w, script))
    bake_file = os.path.join(w, f"{code.lower()}.level.json")
    with open(bake_file, "w", encoding="utf-8") as stream:
        json.dump(bake_level, stream, indent=1)

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
        with open(os.path.join(unpacked, "map", "registration.json"), encoding="utf-8") as stream:
            reg = json.load(stream)
        bake += ["--world-object", reg["world"]]
    log = run(bake)
    with open(os.path.join(w, "bake.log"), "w", encoding="utf-8") as stream:
        stream.write(log)

    bots_file = os.path.join(w, "bake", f"{code}.bots.json")
    if has_bots:
        if not os.path.exists(bots_file):
            sys.exit(f"{code}: the bake wrote no {code}.bots.json")
        if sha(bots_file) != sha(os.path.join(unpacked, "map", "bots.json")):
            if own_bots:
                sys.exit(f"{code}: the level's own bots gave other starts than the shipped bots.json")
            print(f"  note: the bots' starts changed; the new {code}.bots.json goes in the pack", flush=True)

    # Only the scenario may differ.
    built = container_dir(w, "built", os.path.join(w, "bake", stem), stub)
    new = packages(built, stem, a.paks)
    if new != shipped:
        sys.exit(f"{code}: the rebaked container holds {new}, the shipped one {shipped}")
    compared = 0
    for p in shipped:
        if p.endswith(SCENARIO):
            continue
        x, y = os.path.join(w, "x.bin"), os.path.join(w, "y.bin")
        run([EXTRACT, src, p, x])
        run([EXTRACT, built, p, y])
        if sha(x) != sha(y):
            sys.exit(f"{code}: {p} changed in the rebake")
        os.remove(x)
        os.remove(y)
        compared += 1
    print(f"  {compared} other package(s) of the map container unchanged", flush=True)
    return release(p, level, a, os.path.join(w, "bake"), bots_file if has_bots else None)


def release(p, level, a, container, bots_file, bots_may_change=True, added=frozenset()):
    """Pack the next release of a pack: its map container from the folder
    `container`, `level` as its level file and `bots_file` as its bots'
    starts, everything else as the old pack has it. The new pack may differ
    from the old only in the map container, the level file, (with
    `bots_may_change`) the bots' starts and the `added` members, which the
    new pack must have and the old must not. Returns the new archive (None
    with --bake-only)."""
    z, manifest, m, code = p.z, p.manifest, p.manifest["map"], p.code
    slug, version, runtime, w, unpacked, names = p.slug, p.version, p.runtime, p.w, p.unpacked, p.names
    water, foliage = p.water, p.foliage
    has_bots = "map/bots.json" in names
    content = os.path.join(unpacked, "content")
    stem = f"pakchunk997-MJOLNIRMAP-{code}_P"

    # The level file the map ships from now on.
    out_level = os.path.join(w, "level.json")
    with open(out_level, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(level, indent=2) + "\n")
    if a.bake_only:
        return None

    # Stage the pack as `map pack` reads a conversion folder.
    stage = os.path.join(w, "stage")
    os.makedirs(os.path.join(stage, "machines"), exist_ok=True)
    for f in glob.glob(os.path.join(content, "*.utoc")):
        s = os.path.basename(f)[: -len(".utoc")]
        if s == stem:
            for e in ("utoc", "ucas"):
                shutil.copyfile(os.path.join(container, f"{stem}.{e}"), os.path.join(stage, f"{stem}.{e}"))
            continue
        to = os.path.join(stage, "machines") if MACHINE.search(s) else stage
        for e in ("utoc", "ucas"):
            shutil.copyfile(os.path.join(content, f"{s}.{e}"), os.path.join(to, f"{s}.{e}"))
    shutil.copyfile(out_level, os.path.join(stage, f"{code.lower()}.level.json"))
    shutil.copyfile(os.path.join(unpacked, "map", "registration.json"), os.path.join(stage, f"{code}.registration.json"))
    if has_bots:
        shutil.copyfile(bots_file, os.path.join(stage, f"{code}.bots.json"))
    if "map/vehicle_sounds.json" in names:
        shutil.copyfile(os.path.join(unpacked, "map", "vehicle_sounds.json"), os.path.join(stage, "vehicle_sounds.json"))
    if foliage:
        shutil.copyfile(os.path.join(unpacked, "map", foliage), os.path.join(stage, foliage))
    if os.path.isdir(os.path.join(unpacked, "map", "decals")):
        shutil.copytree(os.path.join(unpacked, "map", "decals"), os.path.join(stage, "decals"))
    if water:
        os.makedirs(os.path.join(stage, "flux_state"))
        for member in water:
            shutil.copyfile(os.path.join(unpacked, *member.split("/")),
                            os.path.join(stage, "flux_state", member.rsplit("/", 1)[1]))

    os.makedirs(a.out, exist_ok=True)
    archive = os.path.join(a.out, f"{slug}-{version}.mjolnir")
    cmd = [CLI, "map", "pack", stage, "--code", code, "--version", version, "--slug", slug,
           "--name", manifest["name"], "--summary", manifest.get("summary", ""), "--runtime", runtime,
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

    # The new pack holds what the old one did, the map container, the level
    # file, the bots' starts and the manifest aside.
    nz = zipfile.ZipFile(archive)
    new_manifest = json.loads(nz.read("mjolnir.json"))
    problems = manifest_changes(manifest, new_manifest)
    if not a.runtime and new_manifest.get("deps") != manifest.get("deps"):
        problems.append(f"deps {manifest.get('deps')} became {new_manifest.get('deps')}")
    if problems:
        sys.exit(f"{code}: the manifest differs: {problems}")
    old = {n: z.getinfo(n).CRC for n in names if n not in ("mjolnir.json", "signature.json")}
    got = {n: nz.getinfo(n).CRC for n in nz.namelist() if n not in ("mjolnir.json", "signature.json")}
    changed = {n for n in set(old) | set(got) if old.get(n) != got.get(n)}
    allowed = {f"content/{stem}.ucas", f"content/{stem}.utoc", "map/level.json"} | set(added)
    if bots_may_change:
        allowed.add("map/bots.json")
    if (set(old) & set(added) or set(old) | set(added) != set(got) or "map/level.json" not in changed
            or changed - allowed):
        sys.exit(f"{code}: the new pack differs from the old in {changed}")
    print(f"  {archive}: {os.path.getsize(archive) / 2 ** 20:.1f} MiB", flush=True)
    return archive


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("packs", nargs="+")
    ap.add_argument("--version", help="the new version (one map); else --version-bump of each pack's")
    ap.add_argument("--version-bump", choices=("major", "minor", "patch"), default="minor")
    ap.add_argument("--runtime", help="the runtime pack range; else the pack's own")
    ap.add_argument("--work", default="C:/haloce/ce_conversions/ce_modes_test/work")
    ap.add_argument("--out", default="C:/haloce/ce_conversions/ce_modes_test/packs")
    ap.add_argument("--paks", default=os.environ.get("HCE_PAKS"))
    ap.add_argument("--sign", action="store_true", help="sign with this machine's device key")
    ap.add_argument("--bake-only", action="store_true", help="rebake and check, pack nothing")
    ap.add_argument("--no-race", action="store_true", help="leave the map's race track out")
    ap.add_argument("--vehicle-plan", help="ce_place_vehicles.py's plan: take its vehicle labels (one map)")
    ap.add_argument("--map", help="with --vehicle-plan: the CE .map, whose scenario names the vehicles")
    ap.add_argument("--tags", help="with --vehicle-plan: the map's staging tags.json")
    a = ap.parse_args()
    if a.vehicle_plan and not (a.map and a.tags and len(a.packs) == 1):
        sys.exit("--vehicle-plan takes one pack, with --map and --tags")
    a.packs = [os.path.abspath(p) for p in a.packs]
    a.work, a.out = os.path.abspath(a.work), os.path.abspath(a.out)
    if not a.paks:
        sys.exit("set HCE_PAKS or pass --paks")
    a.paks = os.path.abspath(a.paks)
    # The bake reads defs/ from the working folder.
    os.chdir(REPO)
    if a.version and len(a.packs) > 1:
        sys.exit("--version takes one pack")
    for tool in (CLI, EXTRACT):
        if not os.path.exists(tool):
            sys.exit(f"no {tool}: set MJOLNIR or EXTRACT_FILE")
    with open(BOTS, encoding="utf-8") as stream:
        bots = {k: v for k, v in json.load(stream).items() if not k.startswith("_")}
    failed = []
    for pack in a.packs:
        try:
            one(pack, a, bots)
        except SystemExit as e:
            print(f"  FAILED: {e}", flush=True)
            failed.append(os.path.basename(pack))
    if failed:
        sys.exit(f"{len(failed)} failed: {failed}")


if __name__ == "__main__":
    main()

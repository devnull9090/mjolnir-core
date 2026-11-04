"""Give published Halo 2 map packs their lifts, jump pads and vents: put the
`lifts` block in each pack's level file and pack it as the next release of
the same listing.

    python tools/level/add_lifts.py <pack.mjolnir>... --version-bump minor [--sign]

`lifts` is a key only MJOLNIRLevelLoader's lifts.lua reads, at run time: the
bake never sees it (add_bots.py's BAKE_KEYS), so nothing cooked or baked has
to change and a pack's scenario, with the bots in it, is kept as it shipped.
Each map is staged from its MCC .map (`mjolnir cache stage`, for placement.json
`lifts`) and gen_ce_level.py's h2_lifts puts them in Unreal space with the
transform the map was converted with. The new pack must differ from the old
in map/level.json alone, and that file only by `lifts`; the script checks both
and stops otherwise. A map with no phantom that pushes players gets no pack.

Work goes to <work>/<CODE>/; packs to <out>/<slug>-<version>.mjolnir; a list of
what each map gained to <out>/lifts.json.
"""
import argparse
import glob
import json
import os
import re
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from add_bots import CLI, MACHINE, bump, run  # noqa: E402
from gen_ce_level import h2_lifts  # noqa: E402

MAPS = "C:/Program Files (x86)/Steam/steamapps/common/Halo The Master Chief Collection/halo2/h2_maps_win64_dx11"


def to_ue_from(transform):
    """gen_ce_level.py's to_ue for a map's .sbsp.transform.json."""
    delta = transform["delta"]

    def to_ue(p):
        x, y, z = p[0] + delta[0], p[1] + delta[1], p[2] + delta[2]
        return [round(x * 304.8, 1), round(-y * 304.8, 1), round(z * 304.8, 1)]
    return to_ue


def with_lifts(shipped, placement, transform):
    """The shipped level file's bytes with `lifts` added, and the block; None
    for a map that has none. The block goes in as text before the closing
    brace, so every byte of the file as shipped stays (the files differ in
    indent and line ends)."""
    level = json.loads(shipped)
    if "lifts" in level:
        raise ValueError("the shipped level already has lifts")
    origin = (level.get("canvas") or {}).get("origin") or [0, 0, 0]
    if any(origin):
        raise ValueError(f"canvas origin {origin}: lifts are relative to it, and no Halo 2 map has one")
    lifts = h2_lifts(placement, to_ue_from(transform))
    if not lifts:
        return None, []
    body = shipped.rstrip()[:-1].rstrip()
    return body + b',\n "lifts": ' + json.dumps(lifts, indent=1).encode() + b"\n}\n", lifts


def check_only_lifts(old, new):
    """`new` is the level file `old` plus `lifts` and nothing else."""
    a, b = json.loads(old), json.loads(new)
    b.pop("lifts")
    if a != b:
        raise ValueError("the level file changed beyond lifts")


def conversion(root, code, shipped):
    """The transform of the conversion the pack came from. Its level file must
    be the one the pack ships, or the transform may not be this map's."""
    folder = os.path.join(root, code)
    levels = glob.glob(os.path.join(folder, "*.level.json"))
    transforms = glob.glob(os.path.join(folder, "*.sbsp.transform.json"))
    if len(levels) != 1 or len(transforms) != 1:
        sys.exit(f"{code}: {folder} needs one level file and one transform")
    with open(levels[0], "rb") as stream:
        if stream.read() != shipped:
            sys.exit(f"{code}: {levels[0]} is not the level file the pack ships")
    with open(transforms[0], encoding="utf-8") as stream:
        return json.load(stream)


def stage_pack(unpacked, stage, code, level, names):
    """A folder `map pack` reads, holding what the old pack held."""
    known = {"mjolnir.json", "signature.json", "docs/README.md", "map/level.json", "map/registration.json",
             "map/bots.json"}
    for n in names:
        if n not in known and not n.startswith(("content/", "map/decals/")):
            sys.exit(f"{code}: {n} in the pack is not one this script repacks")
    os.makedirs(os.path.join(stage, "machines"), exist_ok=True)
    content = os.path.join(unpacked, "content")
    for f in glob.glob(os.path.join(content, "*.utoc")):
        s = os.path.basename(f)[: -len(".utoc")]
        to = os.path.join(stage, "machines") if MACHINE.search(s) else stage
        for e in ("utoc", "ucas"):
            shutil.copyfile(os.path.join(content, f"{s}.{e}"), os.path.join(to, f"{s}.{e}"))
    with open(os.path.join(stage, f"{code.lower()}.level.json"), "wb") as stream:
        stream.write(level)
    shutil.copyfile(os.path.join(unpacked, "map", "registration.json"),
                    os.path.join(stage, f"{code}.registration.json"))
    shutil.copyfile(os.path.join(unpacked, "map", "bots.json"), os.path.join(stage, f"{code}.bots.json"))
    if os.path.isdir(os.path.join(unpacked, "map", "decals")):
        shutil.copytree(os.path.join(unpacked, "map", "decals"), os.path.join(stage, "decals"))


def one(pack, a):
    z = zipfile.ZipFile(pack)
    manifest = json.loads(z.read("mjolnir.json"))
    m = manifest["map"]
    code = m["code"]
    if m.get("game") != "halo2":
        sys.exit(f"{code}: not a Halo 2 map")
    slug = re.sub(r"-\d+\.\d+\.\d+(-[0-9A-Za-z.]+)?$", "", os.path.basename(pack)[: -len(".mjolnir")])
    version = a.version or bump(manifest["version"], a.version_bump)
    shipped = z.read("map/level.json")
    transform = conversion(a.conversions, code, shipped)
    source = os.path.join(a.maps, f"{json.loads(shipped)['name']}.map")
    if not os.path.exists(source):
        sys.exit(f"{code}: no {source}")

    w = os.path.join(a.work, code)
    if os.path.isdir(w):
        shutil.rmtree(w)
    os.makedirs(w)
    staging = os.path.join(w, "staging")
    run([CLI, "cache", "stage", source, "--out", staging, "--replace"])
    with open(os.path.join(staging, "placement.json"), encoding="utf-8") as stream:
        placement = json.load(stream)
    new_level, lifts = with_lifts(shipped, placement, transform)
    if new_level is None:
        print(f"== {code} ({slug}): no lifts, no pack", flush=True)
        return {"code": code, "slug": slug, "phantoms": 0}
    check_only_lifts(shipped, new_level)
    assets = sorted({x["asset"].rsplit("\\", 1)[-1] for x in lifts})
    print(f"== {code} ({slug}) {manifest['version']} -> {version}: {len(lifts)} phantom(s), {assets}", flush=True)
    with open(os.path.join(w, "level.json"), "wb") as stream:
        stream.write(new_level)
    summary = {"code": code, "slug": slug, "version": version, "phantoms": len(lifts), "assets": assets}
    if a.level_only:
        return summary

    unpacked = os.path.join(w, "pack")
    z.extractall(unpacked)
    stage = os.path.join(w, "stage")
    stage_pack(unpacked, stage, code, new_level, z.namelist())
    os.makedirs(a.out, exist_ok=True)
    archive = os.path.join(a.out, f"{slug}-{version}.mjolnir")
    runtime = next(d["range"] for d in manifest["deps"] if d["slug"] == "mjolnir-ce-runtime")
    cmd = [CLI, "map", "pack", stage, "--code", code, "--version", version, "--slug", slug,
           "--name", manifest["name"], "--summary", manifest.get("summary", ""), "--runtime", runtime,
           "--game", m["game"], "--out", archive]
    if m.get("size"):
        cmd += ["--size", m["size"]]
    if m.get("players"):
        cmd += ["--players", f"{m['players']['min']}-{m['players']['max']}"]
    if "vehicles" in m:
        cmd += ["--vehicles", "true" if m["vehicles"] else "false"]
    if "docs/README.md" in z.namelist():
        cmd += ["--readme", os.path.join(unpacked, "docs", "README.md")]
    if a.sign:
        cmd.append("--sign")
    run(cmd)

    # The new pack holds what the old one did, the level file and the
    # manifest's version aside: the bots are in the scenario and map/bots.json.
    nz = zipfile.ZipFile(archive)
    skip = ("mjolnir.json", "signature.json")
    old = {n: z.getinfo(n).CRC for n in z.namelist() if n not in skip}
    got = {n: nz.getinfo(n).CRC for n in nz.namelist() if n not in skip}
    changed = {n for n in set(old) | set(got) if old.get(n) != got.get(n)}
    if changed != {"map/level.json"}:
        sys.exit(f"{code}: the new pack differs from the old in {sorted(changed)}")
    check_only_lifts(shipped, nz.read("map/level.json"))
    if {**json.loads(nz.read("mjolnir.json")), "version": manifest["version"]} != manifest:
        sys.exit(f"{code}: the manifest changed beyond the version")
    print(f"  {archive}: {os.path.getsize(archive) / 2 ** 20:.1f} MiB", flush=True)
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("packs", nargs="+")
    ap.add_argument("--version", help="the new version (one map); else --version-bump of each pack's")
    ap.add_argument("--version-bump", choices=("major", "minor", "patch"), default="minor")
    ap.add_argument("--maps", default=MAPS, help="MCC's Halo 2 map folder")
    ap.add_argument("--conversions", default="C:/haloce/ce_conversions/h2/batch2",
                    help="the conversion folders, <CODE>/ each")
    ap.add_argument("--work", default="C:/haloce/ce_conversions/h2/lifts_work")
    ap.add_argument("--out", default="C:/haloce/ce_conversions/h2/lifts_packs")
    ap.add_argument("--sign", action="store_true", help="sign with this machine's device key")
    ap.add_argument("--level-only", action="store_true", help="write <work>/<CODE>/level.json, pack nothing")
    a = ap.parse_args()
    if a.version and len(a.packs) > 1:
        sys.exit("--version takes one pack")
    done, failed = [], []
    for pack in a.packs:
        try:
            done.append(one(pack, a))
        except (SystemExit, ValueError) as e:
            print(f"  FAILED {os.path.basename(pack)}: {e}", flush=True)
            failed.append(os.path.basename(pack))
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "lifts.json"), "w", encoding="utf-8") as stream:
        json.dump(done, stream, indent=1)
    if failed:
        sys.exit(f"{len(failed)} failed: {failed}")


if __name__ == "__main__":
    main()

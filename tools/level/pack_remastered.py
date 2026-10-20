"""Pack the upgraded (remastered) maps as hub map releases, the next version
of each map's existing hub listing.

    python tools/level/pack_remastered.py BGL DTI ... --version 2.0.0 --runtime ^1.8.0 [--sign]

For each map in tools/level/ce_upgrade_maps.json, a staging folder
<out>/<CODE>/ is filled and handed to `mjolnir map pack`:

  - from the installed hub release (the launcher's cache, by hub_state.json):
    the cooked textures (pakchunk985-MJOLNIRCOOK-<CODE>_P), the scenery
    meshes (986) unless the upgrade built its own, registration.json, and
    for an indoor map (no landscape) its map container (997);
  - from the upgrade's work folder (upgrade_ce_map.py): the map container
    (pakchunk997-MJOLNIRMAP), the landscape world's container renamed
    pakchunk<N>-MJOLNIRLAND-<CODE>_P (`map pack` takes the map's own
    containers by that suffix; the launcher keeps the chunk number of a
    container with a shader library, which this one has), the level file,
    foliage.bin and decals/.

That is exactly what the install stage puts in the game, so the pack plays
as the tested install does. The shared parts (the trial masters, chunk 983,
and the water masters, 982) are not a map's: they go in the runtime pack,
which --runtime makes the maps need. Writes <out>/packs/<slug>-<version>.mjolnir.
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
CONFIG = os.path.join(HERE, "ce_upgrade_maps.json")
LAUNCHER = os.path.join(os.environ.get("APPDATA", ""), "com.devnull9090.mjolnir-launcher")
CLI = os.path.join(REPO, "target", "release", "mjolnir.exe")


def installed(slug):
    state = json.load(open(os.path.join(LAUNCHER, "hub_state.json"), encoding="utf-8"))
    inst = next((m for m in state.get("installed", []) if m["slug"] == slug), None)
    if not inst:
        sys.exit(f"{slug} is not installed from the hub: its cooked textures come from the hub release")
    return inst, os.path.join(LAUNCHER, "hub-cache", inst["release_id"])


def copy_pair(src_stem, dst_dir, dst_stem=None):
    for ext in ("utoc", "ucas"):
        src = f"{src_stem}.{ext}"
        if not os.path.exists(src):
            sys.exit(f"missing {src}")
        shutil.copyfile(src, os.path.join(dst_dir, f"{dst_stem or os.path.basename(src_stem)}.{ext}"))


def stage(code, m, work, out):
    inst, cache = installed(m["hub"])
    dst = os.path.join(out, code)
    # A fresh folder each run: a stale container would be packed too. The
    # path is built from the map code, checked against the config above.
    if os.path.isdir(dst):
        for f in os.listdir(dst):
            p = os.path.join(dst, f)
            shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    os.makedirs(dst, exist_ok=True)
    w = os.path.join(work, code)

    copy_pair(os.path.join(cache, f"pakchunk985-MJOLNIRCOOK-{code}_P"), dst)
    if m.get("mesh_container"):
        copy_pair(m["mesh_container"], dst)
    else:
        copy_pair(os.path.join(cache, f"pakchunk986-MJOLNIRMESH-{code}_P"), dst)
    if m.get("indoor"):
        # An indoor map (upgrade_ce_map.py `indoor`: Rat Race) keeps the hub
        # release's map container and has no landscape; only its level file
        # changes.
        copy_pair(os.path.join(cache, f"pakchunk997-MJOLNIRMAP-{code}_P"), dst)
    else:
        copy_pair(os.path.join(w, "bake", f"pakchunk997-MJOLNIRMAP-{code}_P"), dst)
        copy_pair(os.path.join(w, "bake", f"pakchunk{m['chunk']}-MJOLNIRLAND-Windows"), dst,
                  f"pakchunk{m['chunk']}-MJOLNIRLAND-{code}_P")
    shutil.copyfile(os.path.join(cache, "map", "registration.json"), os.path.join(dst, f"{code}.registration.json"))

    level = json.load(open(os.path.join(w, "level.json"), encoding="utf-8"))
    shutil.copyfile(os.path.join(w, "level.json"), os.path.join(dst, f"{code.lower()}.level.json"))
    foliage = (level.get("foliage") or {}).get("file")
    if foliage:
        shutil.copyfile(os.path.join(w, foliage), os.path.join(dst, foliage))
    decals = os.path.join(w, "decals")
    if os.path.isdir(decals) and os.listdir(decals):
        shutil.copytree(decals, os.path.join(dst, "decals"))
    # A river's baked water (level.flux.state), beside the level file.
    if (level.get("flux") or {}).get("state"):
        shutil.copytree(os.path.join(w, "flux_state"), os.path.join(dst, "flux_state"))
    return inst, dst


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("maps", nargs="+")
    ap.add_argument("--version", required=True, help="the release version, above the hub's current one")
    ap.add_argument("--runtime", required=True, help="the runtime pack range these need (the one with 982/983)")
    ap.add_argument("--work", default="C:/haloce/ce_conversions/upgrade")
    ap.add_argument("--out", default="C:/haloce/ce_conversions/remastered")
    ap.add_argument("--sign", action="store_true", help="sign with this machine's device key")
    ap.add_argument("--summary", default="", help="the hub card line, for every map")
    a = ap.parse_args()
    config = json.load(open(CONFIG, encoding="utf-8"))
    bad = [c for c in a.maps if c not in config]
    if bad:
        sys.exit(f"unknown: {bad}")
    if not os.path.exists(CLI):
        sys.exit(f"build the CLI first: cargo build --release -p blam-cli ({CLI})")
    os.makedirs(os.path.join(a.out, "packs"), exist_ok=True)
    for code in a.maps:
        m = config[code]
        inst, dst = stage(code, m, a.work, a.out)
        archive = os.path.join(a.out, "packs", f"{m['hub']}-{a.version}.mjolnir")
        cmd = [CLI, "map", "pack", dst, "--code", code, "--version", a.version, "--slug", m["hub"],
               "--name", inst.get("name") or m["hub"], "--runtime", a.runtime, "--out", archive]
        if a.summary:
            cmd += ["--summary", a.summary]
        if a.sign:
            cmd.append("--sign")
        print(f"== {code}: {inst['version']} -> {a.version}", flush=True)
        r = subprocess.run(cmd, capture_output=True, text=True)
        print(r.stdout.strip())
        if r.returncode:
            sys.exit(f"{code}: map pack failed\n{r.stderr}")
        print(f"  {archive}: {os.path.getsize(archive) / 2 ** 20:.1f} MiB")


if __name__ == "__main__":
    main()

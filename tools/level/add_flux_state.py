"""Give published hub maps their baked river water: put a map's
`mjolnir_flux_bake` output (flux_state/ beside its conversion) into its pack
with `level.flux.state` naming it, and pack the next release of the same
listing. Publishes nothing: the packs stay in <out> until someone uploads them.

    python tools/level/add_flux_state.py <pack.mjolnir>... [--states <dir>] [--sign]

Without a baked state the loader fills a river from scratch: it spawns the
level's `prime` sources for `prime_ms` (60 s), and every Flux source costs the
render thread about 0.4 ms a frame. Timberland's 42 primers held the median
frame at 34 ms for the first minute of a match (13-25 ms after), Proving
Ground's 92 at 54 ms (15 ms after), and the river visibly filled in over that
minute, with CE's water hidden only at the end. With the state the domain
starts full (LoadInitialState) and the loader spawns no primers.

Timberland and Battle Creek were baked on 2026-10-19, but their packs never
carried flux_state/ (the hub scan and the launcher kept only foliage and
decals then), and since the scan learned to check baked water their level
files have had `flux.state` taken out to pass it.

Nothing is rebaked. The state must fit the pack's own domain (centre within
1 cm, resolution, cell, height), as the loader checks, or it would load
nothing and fill instead. Then only these may differ from the old pack:

- `map/level.json`: `flux.state` added, nothing else;
- `map/flux_state/state.json`, `height.exr`, `velocity.exr` added;
- the manifest's version.

The version gets a patch bump unless --version or --version-bump says
otherwise. States are read from <states>/<CODE>/flux_state/. Work goes to
<work>/<CODE>/; packs to <out>/<slug>-<version>.mjolnir.
"""
import argparse
import copy
import json
import os
import shutil
import sys

STATE_FILES = ("state.json", "height.exr", "velocity.exr")
# OpenEXR's magic number.
EXR_MAGIC = b"\x76\x2f\x31\x01"
# What the hub scan (hub/src/lib/api/scan.ts FluxStateSchema) accepts.
STATE_KEYS = {"height", "velocity", "centre", "res", "cell", "height_cm", "capture"}


def fits(state, domain):
    """Whether a baked state is for this domain, by the loader's own test
    (MJOLNIRLevelLoader Effects.fluxState): a state for another domain loads
    nothing and the river fills from scratch."""
    try:
        return (all(abs(state["centre"][i] - domain["centre"][i]) < 1 for i in range(3))
                and list(state["res"]) == list(domain["res"])
                and state["cell"] == domain["cell"] and state["height_cm"] == domain["height"])
    except (KeyError, IndexError, TypeError):
        return False


def read_state(folder):
    """A bake folder's state metadata, checked: the three files present and
    nonempty, both textures EXR, the metadata naming them as the loader and
    the hub scan expect. Other files in the folder are ignored."""
    for name in STATE_FILES:
        path = os.path.join(folder, name)
        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            raise ValueError(f"{path} is missing or empty")
    for name in STATE_FILES[1:]:
        with open(os.path.join(folder, name), "rb") as stream:
            if stream.read(4) != EXR_MAGIC:
                raise ValueError(f"{os.path.join(folder, name)} is not an EXR file")
    with open(os.path.join(folder, "state.json"), encoding="utf-8") as stream:
        state = json.load(stream)
    if state.get("height") != "flux_state/height.exr" or state.get("velocity") != "flux_state/velocity.exr":
        raise ValueError(f"{folder}: state.json must name flux_state/height.exr and flux_state/velocity.exr")
    if set(state) - STATE_KEYS:
        raise ValueError(f"{folder}: state.json has keys the hub does not read: {sorted(set(state) - STATE_KEYS)}")
    return state


def with_state(level, state):
    """A copy of a level with `flux.state` set; refuses a level with no river
    domain, or a state for another domain."""
    flux = level.get("flux")
    if not isinstance(flux, dict) or not isinstance(flux.get("domain"), dict):
        raise ValueError("the level has no Flux river (flux.domain)")
    if not fits(state, flux["domain"]):
        raise ValueError(f"the baked state is for another domain: state {state}, domain {flux['domain']}")
    level = copy.deepcopy(level)
    level["flux"]["state"] = copy.deepcopy(state)
    return level


def level_changes(old, new):
    """What differs between two level files but `flux.state`, as messages."""
    def rest(level):
        level = copy.deepcopy(level)
        (level.get("flux") or {}).pop("state", None)
        return level
    return [] if rest(old) == rest(new) else ["something other than flux.state changed"]


def one(pack, a):
    import add_objectives

    p = add_objectives.Pack(pack, a)
    if p.water:
        print(f"== {p.code}: the pack already carries baked water", flush=True)
        return None
    if isinstance((p.level.get("flux") or {}).get("state"), dict):
        sys.exit(f"{p.code}: the level names baked water the pack does not carry")
    folder = os.path.join(a.states, p.code, "flux_state")
    try:
        state = read_state(folder)
        level = with_state(p.level, state)
    except ValueError as e:
        sys.exit(f"{p.code}: {e}")
    problems = level_changes(p.level, level)
    if problems:
        sys.exit(f"{p.code}: {problems}")
    sources = (level["flux"].get("sources") or [])
    primers = sum(1 for s in sources if isinstance(s, dict) and s.get("prime"))
    print(f"== {p.code} ({p.slug}) {p.manifest['version']} -> {p.version}: baked water from {folder} "
          f"({primers} of {len(sources)} sources were primers)", flush=True)
    # release() stages the pack's water from its unpacked folder.
    water = os.path.join(p.unpacked, "map", "flux_state")
    os.makedirs(water)
    for name in STATE_FILES:
        shutil.copyfile(os.path.join(folder, name), os.path.join(water, name))
    p.water = [f"map/flux_state/{name}" for name in STATE_FILES]
    bots = os.path.join(p.unpacked, "map", "bots.json")
    return add_objectives.release(p, level, a, os.path.join(p.unpacked, "content"),
                                  bots if os.path.exists(bots) else None, bots_may_change=False,
                                  added=set(p.water))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("packs", nargs="+")
    ap.add_argument("--states", default="C:/haloce/ce_conversions/upgrade",
                    help="the folder holding <CODE>/flux_state/ for each map")
    ap.add_argument("--version", help="the new version (one map); else --version-bump of each pack's")
    ap.add_argument("--version-bump", choices=("major", "minor", "patch"), default="patch")
    ap.add_argument("--work", default="C:/haloce/ce_conversions/flux_state_packs/work")
    ap.add_argument("--out", default="C:/haloce/ce_conversions/flux_state_packs/release")
    ap.add_argument("--sign", action="store_true", help="sign with this machine's device key")
    ap.add_argument("--bake-only", action="store_true", help="check and write the level file, pack nothing")
    a = ap.parse_args()
    # The pack keeps its own runtime range.
    a.runtime = None
    a.packs = [os.path.abspath(p) for p in a.packs]
    a.states, a.work, a.out = os.path.abspath(a.states), os.path.abspath(a.work), os.path.abspath(a.out)
    if a.version and len(a.packs) > 1:
        sys.exit("--version takes one pack")
    from add_bots import CLI, REPO
    os.chdir(REPO)
    if not os.path.exists(CLI):
        sys.exit(f"no {CLI}: set MJOLNIR or build it")
    failed = []
    for pack in a.packs:
        try:
            one(pack, a)
        except SystemExit as e:
            print(f"  FAILED: {e}", flush=True)
            failed.append(os.path.basename(pack))
    if failed:
        sys.exit(f"{len(failed)} failed: {failed}")


if __name__ == "__main__":
    main()

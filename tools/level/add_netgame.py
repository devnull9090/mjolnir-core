#!/usr/bin/env python3
"""Give published hub maps the source map's netgame equipment as its tags
have it: the starting equipment, each pickup under its own type and in the
game types that place it, and Halo 2's vehicle respawn times. Rebakes the
scenario and packs the next release of the same listing. Publishes nothing:
the packs stay in <out> until someone uploads them.

    python tools/level/add_netgame.py <pack.mjolnir>... --levels <dir> --paks <Paks> [--version-bump minor] [--sign]

<dir> holds `<CODE>.level.json` for each pack: the level tools/level/
gen_ce_level.py writes today from a fresh staging of the source map and the
conversion's own transform (Halo 2: `mjolnir cache stage`; CE: the
conversion's staging with ce_starting_equipment.py's sidecar). Only its
netgame lanes are taken; everything a later tool gave the published pack
(objectives, lifts, teleporter teams, bots, devices) stays as shipped:

- `blam.weapons` and `blam.equipment` are replaced;
- `blam.vehicles` keeps the shipped rows and takes only the fresh spawn and
  abandonment times, and only when the rows are the same kinds one for one;
- `spawn_sets` is replaced, and must still begin with the shipped sets, whose
  labels the shipped spawn points carry;
- `starting_equipment` and `generic_equipment` are added.

The script stops if anything else would change, or if the shipped level
already equals the result. The rebake and the pack go through
add_objectives.repack: the map container's other packages must come out byte
for byte, and the new pack may differ from the old only in that container,
the level file and the bots' starts.
"""
import argparse
import collections
import copy
import json
import os
import sys

import add_objectives
from add_bots import BOTS, CLI, EXTRACT, REPO

SPAWN = "multiplayer data.spawn time"
ABANDON = "multiplayer data.abandonment time"
# What this script may write at the top of a level file and in `blam`.
LEVEL_KEYS = {"spawn_sets", "starting_equipment", "generic_equipment"}
BLAM_KEYS = {"weapons", "equipment", "vehicles"}


def splice(shipped, fresh):
    """`shipped` with `fresh`'s netgame lanes, or (None, why)."""
    level = copy.deepcopy(shipped)
    blam, new = level["blam"], fresh["blam"]
    blam["weapons"] = copy.deepcopy(new.get("weapons", []))
    blam["equipment"] = copy.deepcopy(new.get("equipment", []))
    # The vehicles are the conversion's rows in its order when they are the
    # same kinds one for one; a published pack may have moved one by hand
    # (Zanzibar's turret), which keeps its place and takes the times.
    kind = lambda v: (v.get("type"), v.get("tag"))
    old_vehicles, new_vehicles = blam.get("vehicles", []), new.get("vehicles", [])
    if [kind(v) for v in old_vehicles] == [kind(v) for v in new_vehicles]:
        for mine, theirs in zip(old_vehicles, new_vehicles):
            for key in (SPAWN, ABANDON):
                if key in theirs.get("set", {}):
                    mine.setdefault("set", {})[key] = theirs["set"][key]
    elif old_vehicles or new_vehicles:
        print("  note: the shipped vehicles are not the conversion's, so their respawn times stay as shipped", flush=True)
    # The fresh level must be this pack's own conversion: every pickup the
    # pack ships is still where the fresh level puts one (a level made with
    # another transform would move them all).
    spot = lambda r: tuple(round(v) for v in r.get("pos", ()))
    fresh_spots = {spot(r) for lane in ("weapons", "equipment") for r in new.get(lane, [])}
    moved = [r for lane in ("weapons", "equipment") for r in shipped["blam"].get(lane, []) if spot(r) not in fresh_spots]
    if moved:
        return None, (f"{len(moved)} shipped pickup(s) are nowhere in the fresh level (first: {moved[0]}): "
                      "it is not this pack's conversion")
    old_sets, new_sets = shipped.get("spawn_sets", []), fresh.get("spawn_sets", [])
    if new_sets[: len(old_sets)] != old_sets:
        return None, f"the shipped spawn sets {old_sets} are not the first of the fresh ones {new_sets}"
    if new_sets:
        level["spawn_sets"] = copy.deepcopy(new_sets)
    for key in ("starting_equipment", "generic_equipment"):
        if fresh.get(key):
            level[key] = copy.deepcopy(fresh[key])
    return level, None


def rest(level):
    """A level less what splice may write."""
    out = {k: v for k, v in level.items() if k not in LEVEL_KEYS}
    out["blam"] = {k: v for k, v in level["blam"].items() if k not in BLAM_KEYS}
    out["blam"]["vehicles"] = [{**v, "set": {k: x for k, x in v.get("set", {}).items() if k not in (SPAWN, ABANDON)}}
                               for v in level["blam"].get("vehicles", [])]
    return out


def counts(rows):
    return dict(sorted(collections.Counter(r.get("type") or r.get("tag") for r in rows).items()))


def one(pack, a, bots):
    p = add_objectives.Pack(pack, a)
    path = os.path.join(a.levels, f"{p.code}.level.json")
    if not os.path.exists(path):
        sys.exit(f"{p.code}: no {path}")
    with open(path, encoding="utf-8") as stream:
        fresh = json.load(stream)
    level, why = splice(p.level, fresh)
    if level is None:
        sys.exit(f"{p.code}: {why}")
    if level == p.level:
        print(f"== {p.code}: already has its netgame equipment", flush=True)
        return None
    if rest(level) != rest(p.level):
        sys.exit(f"{p.code}: more than the netgame lanes would change")
    print(f"== {p.code} ({p.slug}) {p.manifest['version']} -> {p.version}", flush=True)
    for lane in ("weapons", "equipment"):
        was, now = counts(p.level["blam"].get(lane, [])), counts(level["blam"][lane])
        if was != now:
            print(f"  {lane}: {was}\n  {' ' * len(lane)}  -> {now}", flush=True)
    hidden = sum(1 for lane in ("weapons", "equipment") for r in level["blam"][lane]
                 if "multiplayer data.megalo label" in r.get("set", {}))
    if hidden:
        print(f"  {hidden} pickup(s) in some game types only; sets {level.get('spawn_sets')}", flush=True)
    for kit in level.get("starting_equipment", []):
        print(f"  kit for {', '.join(kit['families'])}: {' + '.join(kit['weapons']) or 'no weapon'}, "
              f"{kit['frag_grenades']} frag, {kit['plasma_grenades']} plasma"
              f"{' (the scenario profile)' if kit.get('profile') else ''}", flush=True)
    return add_objectives.repack(p, level, a, bots)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("packs", nargs="+")
    ap.add_argument("--levels", required=True, help="the folder of fresh <CODE>.level.json files")
    ap.add_argument("--version", help="the new version (one map); else --version-bump of each pack's")
    ap.add_argument("--version-bump", choices=("major", "minor", "patch"), default="minor")
    ap.add_argument("--runtime", help="the runtime pack range; else the pack's own")
    ap.add_argument("--work", default="C:/haloce/ce_conversions/netgame/work")
    ap.add_argument("--out", default="C:/haloce/ce_conversions/netgame/packs")
    ap.add_argument("--paks", default=os.environ.get("HCE_PAKS"))
    ap.add_argument("--sign", action="store_true", help="sign with this machine's device key")
    ap.add_argument("--bake-only", action="store_true", help="rebake and check, pack nothing")
    a = ap.parse_args()
    a.packs = [os.path.abspath(p) for p in a.packs]
    a.levels, a.work, a.out = os.path.abspath(a.levels), os.path.abspath(a.work), os.path.abspath(a.out)
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

#!/usr/bin/env python3
"""Build a vehicle's actor around its own skinned mesh.

    ce_vehicle_rig.py <out dir> --bones bones.json [--mesh SK.uasset --skeleton SKEL.uasset]
                      [--code VHT] [--name mongoose] [--label Mongoose] [--donor warthog]
                      [--orphans drop|hide]

Clones the donor's Blueprint and makes the leader the drawn mesh: SK_<stem> on
SKEL_<stem>, animated by a clone of a graph that is the sim's pose and nothing
else, so bones move wherever their names match the sim's nodes. Writes
pakchunk987-MJOLNIR<code>-actor_P into <out dir> with the actor, the animation
Blueprint and the named HUD asset, and the mesh and skeleton if given; without
them they must reach the game in a container of their own.

Rules, none of them per vehicle:

- No region draws a part: every permutation's meshes go. The regions stay, since
  the sim's model names them.
- The leader is left as the donor has it, unscaled and drawn.
- A component that hung from a bone the new skeleton lacks is dropped from the
  construction script (crates/ue-asset/src/rig.rs says which), or hidden where it
  can be with `--orphans hide`, which also leaves Niagara components in, as the
  property codec cannot write them. Sound stays, on the root.
- The vehicle's sound stays with vehicle_mute and the Lua sound module.

Copy the three files to the Paks folder with the game closed, and give the
vehicle tag `--asset-reference` the path this prints.
"""
import argparse
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ce_vehicle  # noqa: E402
import ce_vehicle_name  # noqa: E402

EXAMPLES = ce_vehicle.EXAMPLES


def empty_regions(rows):
    """vehicle_actor edits that leave every region drawing nothing."""
    edits = []
    for region, perms in rows.items():
        for perm, (statics, skeletals) in perms.items():
            base = f"0|RuntimeRegions{{{region}}}.Permutations{{{perm}}}"
            if statics:
                edits.append(f"{base}.StaticMeshes|@len=0")
            if skeletals:
                edits.append(f"{base}.SkeletalMeshes|@len=0")
    return edits


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out")
    ap.add_argument("--bones", required=True, help="ce_vehicle_skin.py's bones.json")
    ap.add_argument("--mesh", help="the cooked SK_<stem>.uasset")
    ap.add_argument("--skeleton", help="the cooked SKEL_<stem>.uasset")
    ap.add_argument("--code", default="VHT")
    ap.add_argument("--name", default="mongoose")
    ap.add_argument("--label", help="the name players read; defaults to --name capitalized")
    ap.add_argument("--donor", default="warthog")
    ap.add_argument("--orphans", choices=["drop", "hide"], default="drop")
    a = ap.parse_args()
    paks = os.environ.get("HCE_PAKS") or sys.exit("set HCE_PAKS")
    with open(os.path.join(ce_vehicle.DONORS, a.donor + ".json"), encoding="utf-8") as f:
        donor = json.load(f)
    os.makedirs(a.out, exist_ok=True)

    stem = a.code + a.name.capitalize()
    folder = f"/Game/MJOLNIR/Vehicles/{a.code}"
    actor = f"{folder}/BP_{stem}"
    uasset = os.path.join(a.out, f"BP_{stem}.uasset")
    edits = os.path.join(a.out, f"BP_{stem}.edits.txt")
    with open(edits, "w", encoding="utf-8") as f:
        f.write("\n".join(empty_regions(ce_vehicle.region_rows(donor))) + "\n")
    print(ce_vehicle.run(os.path.join(EXAMPLES, "vehicle_actor.exe"), paks, donor["actor"], actor, uasset,
                         "@" + edits, capture=True).strip())
    report = ce_vehicle.run(os.path.join(EXAMPLES, "vehicle_rig.exe"), paks, uasset, donor["leader"], folder,
                            stem, a.bones, a.out, "--orphans", a.orphans, capture=True)
    print(report.strip())
    if donor["mute"]:
        print(ce_vehicle.run(os.path.join(EXAMPLES, "vehicle_mute.exe"), uasset, uasset, capture=True).strip())

    packages = []
    if a.mesh and a.skeleton:
        packages = ["--package", f"{folder}/SKEL_{stem}={a.skeleton}", "--package", f"{folder}/SK_{stem}={a.mesh}"]
    for line in report.splitlines():
        if line.startswith("package "):
            packages += ["--package", line[len("package "):]]
    packages += ce_vehicle_name.named(paks, a.out, uasset, a.label or a.name.capitalize())
    container = f"pakchunk987-MJOLNIR{a.code}-actor_P"
    ce_vehicle.run(os.path.join(EXAMPLES, "package_add.exe"), paks, a.out, "--name", container, *packages)
    # The game mounts a .utoc/.ucas pair only beside a .pak.
    shutil.copyfile(os.path.join(paks, "pakchunk115-Windows.pak"), os.path.join(a.out, container + ".pak"))
    print(f"actor {actor}")


if __name__ == "__main__":
    main()

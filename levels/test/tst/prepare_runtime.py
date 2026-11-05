"""Apply TST's authored multiplayer objectives to the converted level before upgrade.

Run after convert_ce_map.sh, before upgrade_ce_map.py. Does not install or publish.
"""
import argparse
import json
import copy
import math
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
METRES_PER_WORLD_UNIT = 3.048


def apply(level, placements, *, release_beta=False):
    markers = placements["objective_markers"]
    objects = level["blam"]["objects"]
    objects[:] = [item for item in objects if not str(item.get("set", {}).get(
        "multiplayer data.megalo label", "")).startswith(("oddball_", "koth_"))]

    # Narrow indoor alcoves can override the stock sender radius without
    # catching players walking down the vestibule. Placement dimensions are
    # metres, while multiplayer boundary fields use Halo world units.
    # The broad balcony return shields still use overlapping stock senders.
    # Reapplying this stage replaces its own side senders instead of duplicating.
    for portal in placements["teleporters"]:
        if not portal.get("shield_return") and "radius_m" not in portal:
            continue
        x,y,z=portal["from_m"]
        origin=[x*100,-y*100,z*100]
        sender_tag=r"objects\multi\teleporters\teleporter_sender"
        def near(item, dx):
            return item.get("tag")==sender_tag and all(abs(a-b)<1 for a,b in
                zip(item["pos"],[origin[0]+dx,origin[1],origin[2]]))
        center=next(item for item in objects if near(item,0))
        if "radius_m" in portal:
            radius=float(portal["radius_m"])
            if not math.isfinite(radius) or radius <= 0:
                raise ValueError(f"Teleporter {portal['channel']} radius_m must be finite and positive")
            center["set"]["multiplayer data.boundary width or radius"]=format(
                radius/METRES_PER_WORLD_UNIT,".9g")
        if not portal.get("shield_return"):
            continue
        objects[:]=[item for item in objects if not any(near(item,dx) for dx in (-140,140))]
        center["set"]["multiplayer data.boundary positive height"]="1.1"
        for dx in (-140,140):
            edge=copy.deepcopy(center)
            edge["pos"][0]+=dx
            objects.append(edge)

    def marker(position, label, radius=1, order=0):
        x, y, z = position
        objects.append({"tag": r"objects\multi\ctf\flag_stand", "group": "scenery",
            "pos": [round(x * 100, 3), round(-y * 100, 3), round(z * 100, 3)], "rot": [0, 0, 0],
            "set": {"multiplayer data.megalo label": label, "multiplayer data.owner team": "eighth party",
                    "multiplayer data.spawn order": str(order),
                    "multiplayer data.boundary shape": "cylinder",
                    "multiplayer data.boundary width or radius": str(radius),
                    "multiplayer data.boundary positive height": "1.5",
                    "multiplayer data.boundary negative height": "0.5"}})

    if not release_beta:
        marker(markers["oddball"]["position_m"], "oddball_spawn")
        for index, position in enumerate(markers["king"]["positions_m"]):
            marker(position, "koth_hill", 2, index)
    # Engines only: the lobby derives Team Slayer, Team King and the rest.
    level["modes"] = ["slayer", "ctf"]
    if not release_beta:
        level["modes"] += ["oddball", "koth"]
    level["title"] = "TST Proving Ground"
    level["description"] = "An original coastal Forerunner arena and editable community source example."
    return level


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--level", type=Path, default=Path("C:/haloce/ce_conversions/community/TST/tst.level.json"))
    parser.add_argument("--placements", type=Path, default=ROOT / "placements.json")
    parser.add_argument("--cli", type=Path, default=REPO / "target/release/mjolnir.exe")
    parser.add_argument("--rules-out", type=Path, default=REPO / ".dream-loop/variants")
    parser.add_argument("--release-beta", action="store_true",
                        help="Ship only published Slayer, Team Slayer and CTF rules; omit candidate objectives")
    args = parser.parse_args()
    placements = json.loads(args.placements.read_text())
    level = apply(json.loads(args.level.read_text()), placements, release_beta=args.release_beta)
    if not args.release_beta:
        args.rules_out.mkdir(parents=True, exist_ok=True)
    variants = ("oddball", "team_oddball", "juggernaut", "stalker", "reverse_tag",
                "koth", "crazy_king", "team_koth")
    for mode in (() if args.release_beta else variants):
        subprocess.run([str(args.cli), "megalo", "write", "--mode", mode.replace("_", "-"),
            "--vehicle-label-pool", "--tick-rate", "60",
            "--out", str(args.rules_out / f"{mode}.mglo")], check=True)
    args.level.write_text(json.dumps(level, indent=2) + "\n")
    print(f"TST prepared: {args.level}; modes: {level['modes']}")


if __name__ == "__main__":
    main()

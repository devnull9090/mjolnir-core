"""Generate examples/levels/bloodgulch.level.json from the halo2ue staging export.

    python tools/level/gen_bloodgulch_level.py [staging/bloodgulch/placement.json]

Player starts, vehicles, pickups and netgame markers come from the classic
scenario; positions move by the same Halo-wu offset the collision transplant
uses, then into UE cm with the Y flip the level file expects.
"""
import collections
import json
import math
import sys

PLACEMENT = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\will\prj\HalcyonRing\staging\bloodgulch\placement.json"
BLANK = "examples/levels/blank_b40.level.json"
OUT = "examples/levels/bloodgulch.level.json"
# The terrain mesh: a shipped package nothing places, whose LOD array carries
# Blood Gulch (crates/ue-asset/examples/mesh_rewrite.rs, docs/ue_mesh_write.md).
# A brand-new Unreal asset package does not resolve by name in this build, so
# the geometry rides a donor. Override with MJOLNIR_TERRAIN_MESH.
TERRAIN_MESH = __import__("os").environ.get(
    "MJOLNIR_TERRAIN_MESH", "/Engine/BasicShapes/Cylinder.Cylinder"
)
# Where mesh_rewrite says to put it: the geometry is normalised into the
# donor's bounding box, so the spawn carries the centre and the scale back.
TERRAIN_POS = (10212.1, -10220.6, 17356.0)
TERRAIN_SCALE = 442.4551
# Slot order matches the `--material` flags mesh_rewrite was run with; slot 0
# is the donor's own and no primitive is assigned to it. The hosts are simple
# diffuse+normal materials from the never-placed prototype content, whose
# textures carry the classic Blood Gulch bitmaps via `mjolnir texture swap`
# (docs/ue_mesh_write.md, "Original textures"). Applied to the component at spawn.
TERRAIN_MATERIALS = [
    "",
    # cliff
    "/Game/_Prototypes/SynchronizationTestContent/Assets/Vehicles/pelican/M_pelican_hull_reach_diffuse.M_pelican_hull_reach_diffuse",
    # ground, moss
    "/Game/_Prototypes/SynchronizationTestContent/Assets/Vehicles/pelican/M_pelican_instances_reach_diffuse.M_pelican_instances_reach_diffuse",
    # boulder
    "/Game/_Prototypes/SynchronizationTestContent/Assets/Vehicles/ghost/M_dghost_diffuse_D.M_dghost_diffuse_D",
    # cap metal, lights, teleporter
    "/Game/_Prototypes/SynchronizationTestContent/Assets/Vehicles/pelican/M_pelican_general_plating_diffuse.M_pelican_general_plating_diffuse",
    # metal flat
    "/Game/_Prototypes/SynchronizationTestContent/Assets/Vehicles/pelican/M_pelican_tech_panels_diffuse.M_pelican_tech_panels_diffuse",
    # panels clean
    "/Game/_Prototypes/SynchronizationTestContent/Assets/weapons/concussion_rifle/M_assault_rifle_Inst.M_assault_rifle_Inst",
    # panels
    "/Game/_Prototypes/SynchronizationTestContent/Assets/weapons/dmr/M_dmr_Inst.M_dmr_Inst",
    # panels unearthed
    "/Game/_Prototypes/SynchronizationTestContent/Assets/gear/ammo_box/M_crate_h_gun_rack_diffuse.M_crate_h_gun_rack_diffuse",
    # ramps
    "/Game/_Prototypes/SynchronizationTestContent/Assets/gear/ammo_box/M_marine_packs_diffuse.M_marine_packs_diffuse",
]

# Halo wu -> blank-B40 world wu: the offset the collision transplant used.
DELTA = (-35.4, 151.17, 44.0)

VEHICLES = {
    "vehicles/ghost/ghost_mp": "ghost",
    "vehicles/warthog/mp_warthog": "warthog",
    "vehicles/rwarthog/rwarthog": "warthog",  # no rocket hog ships; plain hog
    "vehicles/scorpion/scorpion_mp": "scorpion",
    "vehicles/banshee/banshee_mp": "banshee",
}
WEAPONS = {
    "weapons/shotgun/shotgun": "assault_rifle",  # no shotgun in B40's palette
    "weapons/pistol/pistol": "magnum",
    "weapons/assault rifle/assault rifle": "assault_rifle",
    "weapons/plasma rifle/plasma rifle": "plasma_rifle",
    "weapons/sniper rifle/sniper rifle": "sniper_rifle",
    "weapons/rocket launcher/rocket launcher": "rocket_launcher",
    "weapons/flamethrower/flamethrower": None,
    "weapons/plasma_cannon/plasma_cannon": None,
}
EQUIPMENT = {
    "weapons/frag grenade/frag grenade": "frag_grenade",
    "weapons/plasma grenade/plasma grenade": "plasma_grenade",
    "powerups/active camouflage": "active_camouflage",
    "powerups/over shield": "overshield",
    "powerups/health pack": None,
}
MARKERS = {
    "CtfFlag": "ctf_flag",
    "OddballSpawn": "oddball",
    "HillFlag": "hill",
    "TeleportFrom": "teleport_from",
    "TeleportTo": "teleport_to",
}


def to_ue(p):
    x, y, z = p[0] + DELTA[0], p[1] + DELTA[1], p[2] + DELTA[2]
    return [round(x * 304.8, 1), round(-y * 304.8, 1), round(z * 304.8, 1)]


def yaw_ue(rot):
    yaw = rot[0] if isinstance(rot, list) else rot
    return round(-math.degrees(yaw), 1)


def norm(asset):
    return asset.replace("\\", "/")


def main():
    src = json.load(open(PLACEMENT))
    blank = json.load(open(BLANK))

    starts = [
        s for s in src["player_starts"]
        if any(g in s["game_types"] for g in ("Ctf", "Slayer", "AllGames"))
    ] or src["player_starts"]
    by_team = collections.defaultdict(list)
    for s in starts:
        by_team[s["team"]].append(s)
    chosen = []
    for team in sorted(by_team):
        chosen += by_team[team][:4]
    chosen = chosen[:8]

    vehicles, weapons, equipment = [], [], []
    dropped = collections.Counter()
    for e in src["entries"]:
        asset = norm(e.get("asset", ""))
        if e["kind"] == "vehicle":
            kind = VEHICLES.get(asset)
            if kind:
                vehicles.append({"type": kind, "pos": to_ue(e["pos"]), "yaw": yaw_ue(e["rot"])})
            else:
                dropped[asset] += 1
        elif e["kind"] == "netgame_equipment":
            if asset in WEAPONS:
                if WEAPONS[asset]:
                    weapons.append({"type": WEAPONS[asset], "pos": to_ue(e["pos"]), "yaw": yaw_ue(e.get("rot", [0, 0, 0]))})
                else:
                    dropped[asset] += 1
            elif asset in EQUIPMENT:
                if EQUIPMENT[asset]:
                    equipment.append({"type": EQUIPMENT[asset], "pos": to_ue(e["pos"])})
                else:
                    dropped[asset] += 1
            else:
                dropped[asset] += 1

    level = {
        "schema_version": 1,
        "name": "bloodgulch",
        "title": "Blood Gulch (classic CE)",
        "description": (
            "Bloodgulch collision transplanted into B40 at Halo-wu offset (-35.4, 151.17, 44.0); "
            "starts, vehicles and pickups from the CE scenario through defs/level/palette-map.json; "
            "mission content stripped. Needs the BSP_01_1_Start collision override from "
            "docs/ce_terrain_collision.md. Generated by tools/level/gen_bloodgulch_level.py."
        ),
        "canvas": {"scenario": "B40", "origin": [0, 0, 0]},
        "environment": blank["environment"],
        "blam": {
            "clear": blank["blam"]["clear"],
            "player_starts": [{"pos": to_ue(s["pos"]), "yaw": yaw_ue(s["facing"])} for s in chosen],
            "vehicles": vehicles,
            "weapons": weapons,
            "equipment": equipment,
            # The host BSP's world box tiles the scenario; Blood Gulch is wider
            # than BSP_01_1_Start's, and a point outside every box is "outside
            # the world". Union of the shipped box and the terrain, plus 5 wu.
            "world_bounds": [
                {"bsp": 8, "min": [-34.5, -44.05, -270.2], "max": [101.5, 120.9, 116.35]}
            ],
        },
        "markers": [
            {"type": MARKERS[f["type"]], "team": f["team"], "pos": to_ue(f["pos"]), "yaw": yaw_ue(f["facing"])}
            for f in src["netgame_flags"]
            if f["type"] in MARKERS
        ],
        # The terrain mesh, spawned by the runtime loader. The geometry was
        # written into the donor already offset into B40's world box, so the
        # position here is the box centre mesh_rewrite reported rather than the
        # transplant's own offset, and the scale undoes the normalisation.
        "decor": [
            {
                "id": "bloodgulch_terrain",
                "mesh": TERRAIN_MESH,
                "pos": list(TERRAIN_POS),
                "scale": [TERRAIN_SCALE, TERRAIN_SCALE, TERRAIN_SCALE],
                "materials": TERRAIN_MATERIALS,
            }
        ],
    }
    json.dump(level, open(OUT, "w"), indent=2)
    print(
        f"{len(chosen)} starts, {len(vehicles)} vehicles, {len(weapons)} weapons, "
        f"{len(equipment)} equipment, {len(level['markers'])} markers; dropped {dict(dropped)}"
    )


if __name__ == "__main__":
    main()

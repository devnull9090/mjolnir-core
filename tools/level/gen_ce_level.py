"""Generate a level file for any classic CE map from its halo2ue export.

    python tools/level/gen_ce_level.py <staging dir> <transform.json> <out.level.json>
        [--name NAME] [--title TITLE] [--terrain terrain.json]

`transform.json` is what `mjolnir level collision` writes beside the converted
BSP: the CE-to-canvas offset, the canvas and its BSP index, and the terrain's
box in canvas space. Everything placed here moves by that same offset, so the
starts, vehicles and pickups land on the converted collision.

Player starts, vehicles, pickups and netgame markers come from the staging
export's placement.json. CE tags map to level-file types through
defs/level/ce-tag-map.json (a vehicle it does not list, through its CE
vehicle type); the first candidate the game has a type for
(defs/level/palette-map.json; the bake adds what the canvas palette lacks)
wins, and what cannot be placed is reported.

`--terrain` names a JSON object for the terrain mesh decor entry (`mesh`,
`pos`, `scale`, `materials`), as mesh_rewrite reports it
(docs/ue_mesh_write.md). Without it the map has collision but no terrain
visuals, which is enough to test a conversion by standing on it.
"""
import argparse
import collections
import glob
import json
import math
import os
import re
import struct
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
TAG_MAP = os.path.join(ROOT, "defs", "level", "ce-tag-map.json")
# Halo 2 stagings (mjolnir cache stage) name Halo 2 tag paths.
H2_TAG_MAP = os.path.join(ROOT, "defs", "level", "h2-tag-map.json")
PALETTE_MAP = os.path.join(ROOT, "defs", "level", "palette-map.json")

# Per canvas: the blank level whose environment and clear list strip the
# mission to bare geometry, and the host BSP's shipped world box, which the
# widened box keeps covering (Halo wu).
CANVASES = {
    "B40": {
        "blank": os.path.join(ROOT, "examples", "levels", "blank_b40.level.json"),
        "shipped_z": (-265.2, 111.35),
    },
}

# Player starts usable by a free-for-all or team game, in preference order.
START_TYPES = ("Slayer", "Ctf", "AllGames", "AllGamesExceptCtf", "AllGamesExceptCtfAndRace")

# scenario_vehicle "multiplayer spawn flags": bits 0-3 make a vehicle part
# of Slayer's, CTF's, King's and Oddball's default set; bits 8-11 only allow
# it in a custom set. Most of a CE map's Ghosts, Banshees, Scorpions and
# rocket Warthogs are custom-set only (0xf00), so a default set leaves big
# maps nearly empty. "all" places every vehicle, as CE's "all vehicles"
# custom sets do; no stock map stacks two on one spot (the closest pair,
# Infinity's, is 1.4 wu apart).
VEHICLE_SETS = {"slayer": 1 << 0, "ctf": 1 << 1, "king": 1 << 2, "oddball": 1 << 3, "all": 0xfff}

# CE's vehicle sets per game type, decided when the match starts (docs/
# ce_map_conversion.md, "Vehicle sets"). Every vehicle is placed with the
# spawn flag "hide unless megalo required" and a Megalo label,
# `ce_<type>_<rank>`, which its counterpart on the other team shares: the
# simulation places it only if the game variant has an object filter on the
# label, with a team constraint when the two teams' sets differ (the owner
# team is CE's team index). The variant holds at most 16 filters, so a label
# per vehicle did not fit (Death Island's Slayer set alone is 16). Within a
# team, a type's vehicles rank by how many game types they are default in,
# so CE's (symmetric) default sets take few labels. The level's
# `vehicle_sets` lists every vehicle with its label, team and CE's default
# and allowed game types, and MJOLNIRLevelLoader adds the filters for the
# host's vehicle settings (default: the game type's CE default set). The
# type is CE's vehicle set category: a rocket Warthog stays "rwarthog"
# though it spawns as the chaingun Warthog (VEHICLE_VARIANTS).
VEHICLE_SET_TYPES = (("rwarthog", "rwarthog"), ("rocket", "rwarthog"), ("warthog", "warthog"),
                     ("scorpion", "scorpion"), ("ghost", "ghost"), ("banshee", "banshee"),
                     ("turret", "turret"))
CE_VEHICLE_TYPE_SETS = {"human_jeep": "warthog", "human_tank": "scorpion", "alien_scout": "ghost",
                        "alien_fighter": "banshee", "alien_turret": "turret", "human_turret": "turret"}
CE_TEAMS = {0: "red", 1: "blue"}
CE_OWNER_TEAMS = {"red": "defender", "blue": "attacker"}   # scenario owner team 0 and 1
VEHICLE_SET_RANKS = 10   # crates/blam-cli megalo.rs: labels in the variants' pool
HIDE_UNLESS_REQUIRED = "0x4"   # scenario multiplayer data spawn flags bit 2
# Staging from before halo2ue read the spawn flags: every game type, both ways.
ALL_GAME_TYPES = 0x0F0F

# Respawn times are spread over RESPAWN_SPREAD seconds, deterministic per
# object: a flat 30 s brought every vehicle and weapon the simulation had
# not placed back in the same tick, a stall long enough on Death Island
# that the simulation reset the round every ~34 s (2026-10-08).
RESPAWN_SPREAD = 11


def vehicle_set_type(asset, ce_type):
    """CE's vehicle set category for a vehicle: by tag name, else by the
    tag's vehicle type."""
    name = asset.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()
    for key, kind in VEHICLE_SET_TYPES:
        if key in name:
            return kind
    return CE_VEHICLE_TYPE_SETS.get(ce_type or "", "other")


def spread(seconds, k):
    """A respawn time spread by placement: `seconds` plus 0..RESPAWN_SPREAD-1."""
    return seconds + (k * 7) % RESPAWN_SPREAD

# CE vehicles that are a model variant of a Campaign Evolved one, by CE tag:
# the rocket Warthog would be the Warthog with its "rocket" turret
# (warthog-model variants: default, gauss, troop, rocket, ...). Empty for now,
# so rocket hogs spawn as chaingun hogs, as gen_bloodgulch_level.py does: the
# rocket turret (warthog_rocket) has no Unreal actor Blueprint, so its gun was
# invisible and its gunner vanished (playtest, 2026-10-03). The real fix points
# its tag wrapper at the chaingun turret's Blueprint (crates/ue-asset
# tagwrap); the mapping code below stays so the variant can come back:
#   "vehicles/rwarthog/rwarthog": "rocket"
VEHICLE_VARIANTS = {}

# The bake creates every placed object "at rest" (placement flag 0x20). This
# override clears it, so an object placed above the floor falls into place
# instead of hanging where it was put.
NOT_AT_REST = {"object data.placement flags": "0x0"}

# Vehicles that start inside the floor at CE's height: Blood Gulch's
# Banshees on the base roofs and its Scorpions were thrown on their sides
# (2026-10-01). They start this many wu higher and fall into place (not
# "create at rest", which would leave them hanging there). Every other
# vehicle starts VEHICLE_LIFT_DEFAULT higher: CE places vehicles and items
# 0.001 wu over the floor, which leaves the part below their origin in it.
VEHICLE_LIFT = {"banshee": 0.3, "scorpion": 0.3}
VEHICLE_LIFT_DEFAULT = 0.05

# Weapons and equipment start this many wu over their CE height and fall into
# place: created at rest at CE's height, the part of a weapon below its origin
# stayed in the floor (playtest, 2026-10-03). Levitating powerups (CE's
# `levitate` flag) stay at rest where CE put them.
ITEM_LIFT = 0.05

# The canvas's structure designs (B40's three soft-ceiling exports) carry
# Reach's soft ceilings and soft-kill volumes for the mission's own space. A
# map on a BSP of its own keeps CE's coordinates, and Danger Canyon's spawns
# sat inside one: every player was killed by the guardians a second after
# spawning (2026-10-01). The starting zone set loads none of them. (The
# runtime field's name is misspelt in the tag definitions.)
NO_CANVAS_DESIGNS = {"zone sets[0].structure design zone flags": "0x0",
                     "zone sets[0].sruntime tructure design zone flags": "0x0"}

# A scenario trimmed to the map's own BSP (blam.single_bsp) drops the rest of
# the canvas mission too: placed beside BSP 0, its crates would spawn in the
# map, and its AI, cinematics and objectives name squads, zones and objects
# the bake has already cleared; its AI hints and script point sets name its
# other BSPs by index.
CANVAS_MISSION_BLOCKS = ["crates", "device groups", "object names", "cutscene flags",
                         "cinematics", "ai objectives", "reference frames",
                         "user interface objectives block", "ai user hint data",
                         "scripting data"]

# Respawn times, in seconds, of what CE left at its default (0 on the
# placement and on its item collection), and of every vehicle. A map variant
# object with spawn time 0 never came back: Blood Gulch's Banshees, once gone,
# stayed gone. A vehicle left away from its spawn is given back after its
# abandonment time, as CE did.
DEFAULT_RESPAWN = 30
VEHICLE_ABANDONMENT = 30

WORLD_MARGIN = 5.0

# CE player starts sit exactly on the floor (Hang 'Em High's first start is
# 50.110 over a floor at 50.109). This engine's biped origin rides well above
# its feet, so a pawn spawned at floor height starts with its capsule inside a
# one-sided floor and falls out of the bottom of the map. Starts go in this far
# above their CE height and the pawn drops onto the floor.
START_LIFT = 1.0

# The menu names of the stock CE multiplayer maps, by scenario name.
STOCK_TITLES = {
    "beavercreek": "Battle Creek", "bloodgulch": "Blood Gulch", "boardingaction": "Boarding Action",
    "carousel": "Derelict", "chillout": "Chill Out", "damnation": "Damnation",
    "dangercanyon": "Danger Canyon", "deathisland": "Death Island", "gephyrophobia": "Gephyrophobia",
    "hangemhigh": "Hang 'Em High", "icefields": "Ice Fields", "infinity": "Infinity",
    "longest": "Longest", "prisoner": "Prisoner", "putput": "Chiron TL-34", "ratrace": "Rat Race",
    "sidewinder": "Sidewinder", "timberland": "Timberland", "wizard": "Wizard",
}

# The menu names of Halo 2's multiplayer maps, by scenario name: several
# differ from the file (deltatap is Sanctuary), and beavercreek is Beaver
# Creek here, not CE's Battle Creek.
H2_TITLES = {
    "ascension": "Ascension", "backwash": "Backwash", "beavercreek": "Beaver Creek",
    "burial_mounds": "Burial Mounds", "coagulation": "Coagulation", "colossus": "Colossus",
    "containment": "Containment", "cyclotron": "Ivory Tower", "deltatap": "Sanctuary",
    "derelict": "Desolation", "dune": "Relic", "elongation": "Elongation", "foundation": "Foundation",
    "gemini": "Gemini", "headlong": "Headlong", "highplains": "Tombstone", "lockout": "Lockout",
    "midship": "Midship", "needle": "Uplift", "street_sweeper": "District", "triplicate": "Terminal",
    "turf": "Turf", "warlock": "Warlock", "waterworks": "Waterworks", "zanzibar": "Zanzibar",
}

# The game a staging came from (its manifest's `source`): which tag map and
# menu names apply, and what the description says.
SOURCE_GAMES = {"halo_ce": "Halo: Combat Evolved", "halo2_mcc": "Halo 2"}


# Halo 2's planar fog over what no surface covers (docs/h2_map_conversion.md,
# "Planar fog"), as the loader's height fog (`environment.haze`) at the fog
# plane: density and falloff (Unreal's units) and where it starts (cm), past
# Ascension's cloud plane (1 km out), which Halo 2 draws unfogged. Tuned
# against MCC on Ascension (2026-10-22).
H2_FOG_FILL = {"density": 0.2, "falloff": 2.0, "start": 150000.0, "cutoff": 0, "max_opacity": 1.0}


def h2_fog_fill(staging, to_ue):
    """The background under a Halo 2 map's planar fog as `environment.haze`,
    or None. The masters fog each surface below the plane, as Halo 2's
    `fog_planar` pass does; Halo 2 also lays a depth copy there for its
    full-screen fog shaders, and under Ascension's island MCC draws the fog's
    colour wherever the view passes below the plane and finds no surface:
    the rocks' fogged lower ends vanish into it. Ours showed the sky's dark
    lower edge there and the rocks' ends stood out. A height fog at the plane
    in the fog's colour fills it, past the level's own surfaces. A plane that
    is not level gets none."""
    try:
        planes = json.load(open(os.path.join(staging, "fog.json"), encoding="utf-8")).get("planes") or []
    except (OSError, ValueError):
        return None
    if not planes or planes[0]["plane"][2] < 0.99:
        return None
    p = planes[0]
    i, j, k, d = p["plane"]
    return {**H2_FOG_FILL, "height": to_ue([0.0, 0.0, d / k])[2],
            "color": [round(srgb_to_linear(c), 6) for c in p["color"]]}


def staging_source(staging):
    """The staging's `source` (halo2ue writes `halo_ce`; a staging from
    before the field existed is a CE one too)."""
    path = os.path.join(staging, "manifest.json")
    if not os.path.exists(path):
        return "halo_ce"
    return json.load(open(path, encoding="utf-8")).get("source", "halo_ce")


# Maps whose CE water the loader draws as rolling, see-through water
# (M_CE_Ocean, MJOLNIRLevelLoader `environment.water`) by default, by scenario
# name: open seas, tuned on 2026-10-11. Other maps keep CE's water until
# theirs is looked at (rivers, lakes, Damnation's falls). Each with M_CE_Ocean
# parameters of its own (`params`), over CE's: Death Island's sun on its
# water at full CE glancing brightness (ParaBrightness 1) and shore foam 0.7
# washed the shallows milky white; at half, with a little more roughness and
# less chop near the shore, they are clear down to the pebbles. No crest
# foam: from the beach it drew a still, pale stripe across the sea.
OCEAN_MAPS = {
    "deathisland": {"ParaBrightness": 0.55, "ParaTint": [0.8, 0.9, 0.95, 1.0], "Roughness": 0.22,
                    "FoamAmount": 0.0, "Specular": 0.35, "NearShoreDetail": 1.5,
                    # The original's dark green sea, not a blue one.
                    "WaterColor": [0.03, 0.1, 0.07, 1.0], "PerpTint": [0.25, 0.45, 0.38, 1.0]},
    # No crest foam: from above it drew still white rings around the islands.
    "yoyorast_island_v2": {"FoamAmount": 0.0},
}

# Under a multiplayer (Megalo) engine the simulation never reads the scenario's
# player starting locations: it spawns players only at scenery whose
# multiplayer object type is "player spawn location" (15), and a first spawn
# needs the "valid initial player spawn" flag (docs/re/megalo_engine.md). No
# such scenery ships, so this one is built by `mjolnir new-tag` from the
# invisible cinematic anchor (see tools/level/README or the doc) and placed
# at every CE start, owned by the neutral team, which any player may use.
SPAWN_SCENERY = r"objects\multi\spawning\player_spawn"

# CE pairs a "teleport from" flag with the "teleport to" flags on its channel;
# the simulation keeps Reach's multiplayer teleporters, which move what enters
# a sender's boundary to a receiver on the same teleporter channel. Both ends
# are built by tools/level/build_spawn_point.sh. The sender's boundary is a
# short cylinder over the CE flag (CE teleporters fire as a player steps onto
# the pad); a receiver's facing is the exit direction.
TELEPORTER_SCENERY = {"TeleportFrom": r"objects\multi\teleporters\teleporter_sender",
                      "TeleportTo": r"objects\multi\teleporters\teleporter_receiver"}
# The scenario's `teleporter channel` enum. CE numbers a map's channels freely
# (Gephyrophobia's start at 2), so each map's channels are renumbered densely
# from alpha in CE order: Blood Gulch's alpha/bravo pads worked while every
# Gephyrophobia pad, on charlie to foxtrot, did nothing (2026-10-01).
TELEPORTER_CHANNELS = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel",
                       "india", "juliet", "kilo", "lima", "mike", "november", "oscar", "papa",
                       "quebec", "romeo", "sierra", "tango", "uniform", "victor", "whiskey",
                       "xray", "yankee", "zulu"]
TELEPORTER_RADIUS = 0.35   # world units
TELEPORTER_HEIGHT = 0.6
# The simulation keeps a table of at most 32 teleporters, filled once per
# tick from the map's sender, receiver and 2-way scenery
# (HaloSimulation_tag_release.dll 0x1803e7670, CU4). Ends past the 32nd are
# never in it: they send nothing and nothing lands on them. Chiron TL-34
# placed 60 ends, so half its pads did nothing (2026-10-04).
TELEPORTER_MAX = 32
# CE has no two-way pad: a two-way teleporter is two channels whose "teleport
# from" and "teleport to" flags sit on top of each other at both pads (all of
# Chiron TL-34's, Gephyrophobia's and Sidewinder's). Each such pair of channels
# becomes one channel with a "teleporter 2way" at each pad, which both sends
# and receives: half the ends, so Chiron's 30 pads fit the 32. Built by
# tools/level/build_spawn_point.sh.
TELEPORTER_2WAY = r"objects\multi\teleporters\teleporter_2way"
# A "teleport from" flag and a "teleport to" flag make one pad when the
# landing spot is inside the sender's boundary (Chiron's are under 0.06 apart)
# and the exit faces the way players walk in, turned round, within this.
TELEPORTER_2WAY_YAW = 45.0   # degrees
# The simulation lands a player at the receiver's (or 2-way's) origin only if
# a Spartan fits there: it tests the biped's shape against the collision
# (0x1803e6ab0 -> 0x1802f7290) and otherwise skips that receiver, and a
# sender with none left raises teleporter_blocked. CE has no such test and
# puts its "teleport to" flags at the back of their alcoves: on Chiron TL-34
# every landing spot had 0.17-0.25 to the wall behind it against the
# Spartan's 0.175 radius (spartans-biped "radius"), and pads landing at 0.166
# and 0.182 never sent (2026-10-05). Each landing end moves forward along its
# exit facing, up to TELEPORTER_NUDGE_MAX, until the Spartan clears the CE
# collision by TELEPORTER_CLEARANCE over its standing height.
SPARTAN_RADIUS = 0.175          # world units
SPARTAN_HEIGHT = 0.65
SPARTAN_LIFT = 0.2              # 0x1802f7290 tests the shape this far up
TELEPORTER_CLEARANCE = 0.25     # radius plus margin
TELEPORTER_NUDGE_MAX = 0.15
TELEPORTER_NUDGE_STEP = 0.01

# Capture the Flag: a flag stand at each CE CTF flag, owned by the flag's team
# (CE team 0 is red, the scenario's "defender"; 1 blue, "attacker") and
# labelled for the CTF variant (blam-megalo ctf.rs), which makes the flag on
# it. Its boundary is the capture zone: a carrier scores by reaching it.
# Built by tools/level/build_ctf_flag.sh.
FLAG_STAND_SCENERY = r"objects\multi\ctf\flag_stand"
FLAG_STAND_LABEL = "ctf_flag_return"
CTF_TEAMS = {0: "defender", 1: "attacker"}
CTF_TEAMS_UE = {0: "red", 1: "blue"}
# Starts a CTF game uses.
CTF_START_TYPES = ("Ctf", "AllGames")
CAPTURE_RADIUS = 1.0   # world units
CAPTURE_HEIGHT = 1.5

# What the flags and stands look like: CE's own flag and flag base models
# (halo2ue), rewritten into meshes of our own by build_ce_flag_mesh.sh, which
# also prints these transforms (mesh_rewrite's SPAWN line: where the
# normalised mesh goes back to its own size and origin). Their textures come
# from tools/level/ce_flag_textures.py, cooked into the CE runtime pack by
# tools/level/build_ce_runtime.sh. The loader puts the flag on each flag's
# actor.
CTF_TEXTURES = "/Game/MJOLNIR/CE/CTF"
FLAG_MESH = {"mesh": "/Game/MJOLNIR/CTF/SM_CE_Flag.SM_CE_Flag", "pos": [2.3, 0.0, 119.6], "scale": 3.0743}
FLAG_BASE_MESH = {"mesh": "/Game/MJOLNIR/CTF/SM_CE_FlagBase.SM_CE_FlagBase", "pos": [0.0, 0.0, 7.6],
                  "scale": 1.3411}
CE_MODEL_MATERIAL = "/Game/MJOLNIR/CE/M_CE_EnvironmentMaskedTwoSided.M_CE_EnvironmentMaskedTwoSided"

# Health packs: nothing in the game heals on contact, so the Megalo variants
# do it (blam_megalo::powerups). Each CE health pack becomes a spot, invisible
# scenery labelled for the script, which makes the pack and gives it back
# after a pickup; the pack is equipment the loader dresses in CE's health
# pack mesh (build_ce_runtime.sh prints its transform). Built by
# tools/level/build_ctf_flag.sh.
HEALTH_PACK = "powerups/health pack"
HEALTH_SPOT_SCENERY = r"objects\multi\powerups\health_pack_spot"
HEALTH_SPOT_LABEL = "ce_health_pack"
HEALTH_PACK_MESH = {"mesh": "/Game/MJOLNIR/CE/Powerups/SM_CE_HealthPack.SM_CE_HealthPack",
                    "pos": [0.0, 0.0, 12.2], "scale": 0.6096}


# Lens flares: the glow of a light a placed object carries (Danger Canyon's
# and Blood Gulch's base beacons). Each flare is a sphere at the light's
# marker drawn with M_CE_Flare, the flare bitmap facing the camera and added
# into the frame (build_ce_materials.py); the sphere's radius is the flare's.
# CE's other light terms are already in the lightmaps.
FLARE_MESH = "/Engine/BasicShapes/Sphere.Sphere"
FLARE_MATERIAL = "/Game/MJOLNIR/CE/M_CE_Flare.M_CE_Flare"
SPHERE_RADIUS_CM = 50.0
FLARE_GAIN = 0.6   # the CE transparent masters' display gain


def ce_rotation(yaw, pitch, roll):
    """CE object rotation, row-major (as merge_ce_collision.py has it): yaw
    about z, then pitch and roll about the world's y and x axes."""
    cy, sy, cp, sp, cr, sr = (math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch),
                              math.cos(roll), math.sin(roll))
    rz = [[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]]
    ry = [[cp, 0, -sp], [0, 1, 0], [sp, 0, cp]]
    rx = [[1, 0, 0], [0, cr, -sr], [0, sr, cr]]

    def mul(a, b):
        return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    return mul(mul(rx, ry), rz)


def h2_lifts(placement, to_ue):
    """Halo 2's lifts, jump pads and vents (placement.json `lifts`, from
    crate::h2::phantom) in Unreal space for MJOLNIRLevelLoader's lifts.lua:
    each phantom's shape (planes `n.p + d <= 0` inside, or a pill), the
    marker it pushes from and along, and its accelerations and top speeds
    in centimetres (per second, and per second squared), and a bounding
    sphere (x, y, z, radius) for the loader's nearness test."""
    out = []
    for lift in placement.get("lifts") or []:
        r = ce_rotation(*lift["rot"])
        s = lift.get("scale") or 1.0
        t = lift["pos"]

        def point(p):
            return to_ue([sum(r[k][j] * p[j] * s for j in range(3)) + t[k] for k in range(3)])

        def vector(v):
            w = [sum(r[k][j] * v[j] for j in range(3)) for k in range(3)]
            n = math.sqrt(sum(c * c for c in w)) or 1.0
            return [round(w[0] / n, 4), round(-w[1] / n, 4), round(w[2] / n, 4)]

        for ph in lift["phantoms"]:
            shape = ph["shape"]
            if "planes" in shape:
                planes = []
                for nx, ny, nz, d in shape["planes"]:
                    n = vector([nx, ny, nz])
                    on = point([-d * nx, -d * ny, -d * nz])   # the plane's point nearest the origin
                    planes.append(n + [round(-sum(n[k] * on[k] for k in range(3)), 1)])
                ue_shape = {"planes": planes}
            else:
                a, b = shape["pill"]
                ue_shape = {"pill": [point(a), point(b)], "radius": round(shape["radius"] * s * WU_CM, 1)}
            centre, radius = shape["bounds"]
            out.append({
                "asset": lift["asset"],
                **ue_shape,
                "bounds": point(centre) + [round(radius * s * WU_CM, 1)],
                "origin": point(ph["origin"]),
                "forward": vector(ph["forward"]),
                "center": [round(x * WU_CM, 1) for x in ph["center"]],
                "axis": [round(x * WU_CM, 1) for x in ph["axis"]],
                "direction": [round(x * WU_CM, 1) for x in ph["direction"]],
                "negates_gravity": ph["negates_gravity"],
            })
    return out


def flare_decor(placement, texture_root, to_ue):
    """Decor entries for every lens flare on the lights placed objects carry."""
    from ce_material_spec import asset_name

    out = []
    for e in placement["entries"]:
        lights = e.get("lights") or []
        if not lights:
            continue
        r = ce_rotation(*(e.get("rot") or [0, 0, 0]))
        for light in lights:
            flare = light.get("lens_flare") or {}
            o = light.get("offset") or [0, 0, 0]
            pos = [e["pos"][k] + sum(r[k][j] * o[j] for j in range(3)) for k in range(3)]
            # The light's colour: CE's flares here carry no tint of their own.
            argb = light.get("color_lower_argb") or [0, 0, 0, 0]
            color = argb[1:4] if any(argb[1:4]) else (light.get("color_rgb") or [1, 1, 1])
            for refl in flare.get("reflections", []):
                if not refl.get("bitmap"):
                    continue
                tint = refl.get("tint_argb") or [0, 0, 0, 0]
                rgb = tint[1:4] if tint[0] > 0 and any(tint[1:4]) else color
                radius_cm = max(refl["radius"]) * flare.get("horizontal_scale", 1.0) * WU_CM
                if radius_cm <= 0:
                    continue
                s = round(radius_cm / SPHERE_RADIUS_CM, 4)
                t = asset_name("T_", os.path.splitext(refl["bitmap"])[0])
                entry = {
                    "id": f"flare_{len(out)}",
                    "mesh": FLARE_MESH,
                    "pos": to_ue(pos),
                    "scale": [s, s, s],
                    "cast_shadow": False,
                    "materials": [{
                        "parent": FLARE_MATERIAL,
                        "textures": {"Flare": f"{texture_root}/{t}.{t}"},
                        "vectors": {"Tint": [round(c, 4) for c in rgb] + [1.0]},
                        "scalars": {"Brightness": round(FLARE_GAIN * max(refl.get("brightness") or [1.0]), 4)},
                    }],
                }
                # The light scaled by an object function (the beacons' 1 s
                # cosine): MJOLNIRLevelLoader scales the flare's brightness by
                # the same periodic function every frame.
                pulse = light.get("pulse")
                if pulse and pulse.get("function", 0) >= 2 and pulse.get("period", 0) > 0:
                    entry["pulse"] = {"param": "Brightness", "function": pulse["function"],
                                      "period": pulse["period"]}
                out.append(entry)
    return out


DECAL_QUAD = "/Engine/BasicShapes/Plane.Plane"  # 100 cm square, facing +Z
DECAL_MATERIAL = "/Game/MJOLNIR/CE/M_CE_TransparentAlphaTwoSided.M_CE_TransparentAlphaTwoSided"
DECAL_ADD_MATERIAL = "/Game/MJOLNIR/CE/M_CE_TransparentAddTwoSided.M_CE_TransparentAddTwoSided"
DECAL_LIFT = 1.0  # cm off the surface


def closest_on_triangles(p, a, b, c):
    """The closest point to p on each triangle (a, b, c: (n, 3)), as (n, 3)
    (Ericson, Real-Time Collision Detection 5.1.5, vectorised)."""
    import numpy as np
    ab, ac, ap = b - a, c - a, p - a
    d1, d2 = (ab * ap).sum(1), (ac * ap).sum(1)
    bp, cp = p - b, p - c
    d3, d4 = (ab * bp).sum(1), (ac * bp).sum(1)
    d5, d6 = (ab * cp).sum(1), (ac * cp).sum(1)
    va, vb, vc = d3 * d6 - d5 * d4, d5 * d2 - d1 * d6, d1 * d4 - d3 * d2
    den = va + vb + vc
    den = np.where(np.abs(den) > 1e-12, den, 1e-12)
    out = a + ab * (vb / den)[:, None] + ac * (vc / den)[:, None]
    safe = lambda x, y: x / np.where(np.abs(y) > 1e-12, y, 1e-12)
    cases = [
        ((d4 - d3 >= 0) & (d5 - d6 >= 0) & (va <= 0), b + (c - b) * safe(d4 - d3, (d4 - d3) + (d5 - d6))[:, None]),
        ((vb <= 0) & (d2 >= 0) & (d6 <= 0), a + ac * safe(d2, d2 - d6)[:, None]),
        ((d6 >= 0) & (d5 <= d6), c),
        ((vc <= 0) & (d1 >= 0) & (d3 <= 0), a + ab * safe(d1, d1 - d3)[:, None]),
        ((d3 >= 0) & (d4 <= d3), b),
        ((d1 <= 0) & (d2 <= 0), a),
    ]
    for mask, point in cases:
        out = np.where(mask[:, None], point, out)
    return out


def decal_decor(placement, scene_gltf, texture_root, delta):
    """Halo 2's decals (placement `decals`, every one lit alpha blend) as
    decor: a quad each on the surface nearest the decal within 3 m, facing
    its open side, its texture upright on walls, its longer side twice the
    decal's radius and its other side by the bitmap's aspect, drawn with
    the transparent alpha master over the cooked bitmap. Candidates are the
    triangles whose bounds come within 3 m and the nearest is by true
    distance: a wall's big triangles have their centres far off (taken by
    centre and by plane distance, Zanzibar's flywheel sign went onto a
    slanted face nearby, tilted and half buried)."""
    decals = placement.get("decals") or []
    if not decals or not scene_gltf or not os.path.exists(scene_gltf):
        return []
    import numpy as np
    from ce_material_spec import asset_name
    from upgrade_ce_map import ray_room, scene_triangles
    tris = scene_triangles({"scene": os.path.dirname(scene_gltf)})
    lo, hi = tris.min(axis=1), tris.max(axis=1)
    nrm = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-12
    unit = 3.048
    out = []
    for i, d in enumerate(decals):
        if not d.get("texture"):
            continue
        p = [d["pos"][k] + delta[k] for k in range(3)]
        g = np.array([p[0], p[2], -p[1]]) * unit
        gap = np.maximum(np.maximum(lo - g, g - hi), 0.0)
        near = np.where(np.linalg.norm(gap, axis=1) < 3.0)[0]
        if not len(near):
            continue
        q = closest_on_triangles(g, tris[near, 0], tris[near, 1], tris[near, 2])
        j = int(np.argmin(np.linalg.norm(q - g, axis=1)))
        ng = nrm[near[j]]
        v0, e1, e2 = tris[near, 0], tris[near, 1] - tris[near, 0], tris[near, 2] - tris[near, 0]
        if ray_room(v0, e1, e2, g, -ng, 0.02) > ray_room(v0, e1, e2, g, ng, 0.02):
            ng = -ng
        g = q[j]
        n = np.array([ng[0], ng[2], ng[1]])  # Unreal axes = glTF (x, z, y)
        pos = np.array([g[0], g[2], g[1]]) * 100.0 + n * DECAL_LIFT
        if abs(n[2]) < 0.9:
            x = np.cross(n, [0.0, 0.0, 1.0])
            x /= np.linalg.norm(x)
        else:
            x = np.array([1.0, 0.0, 0.0]) - n * n[0]
            x /= np.linalg.norm(x)
        y = np.cross(n, x)
        pitch = math.degrees(math.asin(max(-1.0, min(1.0, x[2]))))
        yaw = math.degrees(math.atan2(x[1], x[0]))
        roll = math.degrees(math.atan2(-y[2], n[2]))
        size = float(d.get("radius") or 0.5) * 2 * unit
        aspect = float(d.get("aspect") or 1.0)
        sx, sy = (size, size * aspect) if aspect <= 1.0 else (size / aspect, size)
        t = asset_name("T_", os.path.splitext(d["texture"])[0])
        # Max and add layers add; multiplies come baked for alpha blending.
        blend = 3 if int(d.get("blend_function") or 0) == 3 else 0
        out.append({"id": f"h2_decal_{i}", "mesh": DECAL_QUAD,
                    "pos": [round(float(v), 1) for v in pos], "rot": [round(pitch, 2), round(yaw, 2), round(roll, 2)],
                    "scale": [round(sx, 3), round(sy, 3), 1.0], "cast_shadow": False,
                    "materials": [{"parent": DECAL_ADD_MATERIAL if blend == 3 else DECAL_MATERIAL,
                                   "textures": {"Map0": f"{texture_root}/{t}.{t}"},
                                   "scalars": {"StageCount": 1, "ChicagoFlags": 0.0, "BlendFunction": float(blend),
                                               "FadeMode": 0.0},
                                   "vectors": {"Stage0Xform": [1.0, 1.0, 0.0, 0.0],
                                               "StageColorFunctions": [0, 0.0, 0.0, 0.0],
                                               "StageAlphaFunctions": [0, 0.0, 0.0, 0.0]}}]})
    return out


def spawn_seconds(e):
    """A CE pickup's respawn time: the placement's own, else its item
    collection's (halo2ue's `collection_spawn_time`), else None for the
    game's default."""
    for key in ("spawn_time", "collection_spawn_time"):
        if (e.get(key) or 0) > 0:
            return int(e[key])
    return None


def ce_model_material(texture):
    """A CE model texture on the environment master, unlit by any lightmap."""
    stem = "T_" + os.path.splitext(texture)[0]
    return {"parent": CE_MODEL_MATERIAL, "textures": {"Base": f"{CTF_TEXTURES}/{stem}.{stem}"},
            "scalars": {"HasLightmap": 0.0, "HasPrimary": 0.0, "HasSecondary": 0.0, "HasMicro": 0.0,
                        "HasBump": 0.0, "HasSelfIllum": 0.0}}


def ctf_section(stands):
    """The level's `ctf` (the loader's flag look) and the stands' flag base
    decor, from `[(team, pos, yaw)]` in Unreal centimetres and degrees. A flag
    at home is drawn exactly on its stand, facing the stand's way (the flag
    object itself settles a little off it)."""
    flag = dict(FLAG_MESH)
    flag["materials"] = {team: [ce_model_material(f"flag_{team}.png"), ce_model_material("flag.png"),
                                ce_model_material("flag.png")]
                         for team in ("red", "blue")}
    decor = []
    for team, pos, _ in stands:
        p = FLAG_BASE_MESH["pos"]
        s = FLAG_BASE_MESH["scale"]
        decor.append({"id": f"flag_base_{team}", "mesh": FLAG_BASE_MESH["mesh"],
                      "pos": [round(pos[0] + p[0], 1), round(pos[1] + p[1], 1), round(pos[2] + p[2], 1)],
                      "scale": [s, s, s],
                      "materials": [ce_model_material("flag_base_strips.png"), ce_model_material("flag_base.png"),
                                    ce_model_material("flag_base_metal.png")]})
    section = {"flag": flag, "stands": [{"team": team, "pos": pos, "yaw": yaw} for team, pos, yaw in stands]}
    return section, decor


# The Unreal sun and sky light only light what Unreal draws lit: players,
# vehicles, weapons (the CE terrain carries its own baked light). Their level
# follows the CE sky's outdoor ambient light (colour x power): the template's
# sun 8 and sky light 3 are what Blood Gulch's ambient (0.87, 0.84, 0.75) x
# 0.2 looks right with, and other maps scale from there. Their colour is the
# lightmaps' (lightmap_tint): CE lit an object by the lightmap under it, and
# the sky's ambient colour can be anything (Infinity's test sky is pure
# yellow, (0.5, 0.5, 0), and its weapons and players came out yellow).
REFERENCE_AMBIENT = 0.2 * (0.2126 * 0.871 + 0.7152 * 0.843 + 0.0722 * 0.753)


def sky_sun(placement):
    """CE's sun from the sky tag (halo2ue's placement.json, the sky entry's
    `lights`): the exterior light with the narrowest diameter (the sky's
    fill lights are tens of degrees wide and straight up). Returns
    `{"gltf": [x, y, z] towards the sun in glTF space, "rotation": (pitch,
    yaw) for the Unreal light, "color", "power"}`, or None without one.

    CE gives a light's direction as yaw and pitch, z up: towards the sun is
    (cos p cos y, cos p sin y, sin p); glTF is (x, z, -y) of that. Checked
    against CE's own lightmaps on Danger Canyon (2026-10-07): traced sun
    shadows cover 99% of CE's dark texels with this reading, 82-91% with the
    mirrored ones, and 93% with the lightmap's incident average, which blends
    the sun with the sky's fill and sits far too steep (87 against 35
    degrees there)."""
    sky = next((e for e in placement.get("entries", []) if e.get("kind") == "sky"), None)
    lights = [l for l in (sky or {}).get("lights", []) if l.get("affects_exteriors") and l.get("power", 0) > 0]
    if not lights:
        return None
    l = min(lights, key=lambda l: (l.get("diameter", 0.0), -l.get("power", 0.0)))
    yaw, pitch = l["yaw"], l["pitch"]
    cx, cy, cz = math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch)
    # Unreal: (x, -y, z) of CE; the light shines along its forward vector,
    # away from the sun (sun_rotation's convention).
    ue_pitch = -math.degrees(pitch)
    ue_yaw = math.degrees(math.atan2(cy, -cx))
    return {"gltf": [cx, cz, -cy], "rotation": (round(ue_pitch, 1), round(ue_yaw, 1)),
            "color": l.get("color"), "power": l.get("power")}


def sun_rotation(scene_gltf):
    """The directional light's (pitch, yaw) from CE's own lighting.

    Object shadows have to fall the way the lightmaps' shadows do. CE stores
    each lightmap vertex's incident direction (the dominant light, towards it,
    exported as _INCIDENT for the bump term); over flat, brightly lit ground
    that is the sun. A night map with no strong sun comes out overhead.
    Returns None without the data."""
    try:
        import numpy as np
    except ImportError:
        return None
    try:
        g = json.load(open(scene_gltf, encoding="utf-8"))
    except OSError:
        return None
    base = os.path.dirname(scene_gltf)
    bufs = [open(os.path.join(base, b["uri"]), "rb").read() for b in g["buffers"]]

    def accessor(i):
        a = g["accessors"][i]
        bv = g["bufferViews"][a["bufferView"]]
        off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        return np.frombuffer(bufs[bv["buffer"]], dtype="f4", count=a["count"] * 3, offset=off).reshape(-1, 3)

    total = np.zeros(3)
    for mesh in g["meshes"]:
        for prim in mesh["primitives"]:
            at = prim["attributes"]
            if "_INCIDENT" not in at or "NORMAL" not in at:
                continue
            inc = accessor(at["_INCIDENT"]).astype(np.float64)
            length = np.linalg.norm(inc, axis=1)
            flat = (accessor(at["NORMAL"])[:, 1] > 0.95) & (length > 0.5)   # glTF is y-up
            # Summed raw, so a vertex weighs by how directional its light is.
            total += inc[flat].sum(axis=0)
    if not total.any():
        return None
    gx, gy, gz = total / np.linalg.norm(total)
    towards = (gx, gz, gy)   # glTF (x, y, z) is Unreal (x, z, y), as mesh_rewrite places it
    # The light shines along its forward vector, away from the sun.
    pitch = math.degrees(math.asin(max(-1.0, min(1.0, -towards[2]))))
    yaw = math.degrees(math.atan2(-towards[1], -towards[0]))
    return round(pitch, 1), round(yaw, 1)


def lightmap_tint(staging):
    """The colour of a map's light: its lightmap pages' mean over the texels
    that are lit (luminance over 0.05) and not clipped (no channel at 1),
    scaled to a maximum of 1. None without the pages or Pillow."""
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        return None
    try:
        manifest = json.load(open(os.path.join(staging, "manifest.json"), encoding="utf-8"))
    except OSError:
        return None
    total, count = np.zeros(3), 0
    for bsp in manifest.get("bsps", []):
        for page in bsp.get("lightmap_pages", []):
            path = os.path.join(staging, "textures", page)
            if not os.path.exists(path):
                continue
            a = np.asarray(Image.open(path).convert("RGB"), dtype=np.float64).reshape(-1, 3) / 255.0
            lit = (a @ [0.2126, 0.7152, 0.0722] > 0.05) & (a.max(axis=1) < 0.99)
            total += a[lit].sum(axis=0)
            count += int(lit.sum())
    if not count or total.max() <= 0:
        return None
    return [round(float(c), 3) for c in total / total.max()]


def lightmap_sun(scene_gltf, staging, bake_dir, sun=None):
    """The level's lightmap in CE's shadow and in its sun, from lightmapped
    vertices facing the sun, split by the bake's traced sun visibility
    (lightmap_bake, green: under 0.1 shadow, over 0.9 sun): `levels`, the
    luminance in each (MJOLNIRMaterials SUN_WEIGHT_CODE's LightmapSun), and
    `colour`, the sunlit lightmap's colour scaled to a maximum of 1.

    The shadow level is the lower quartile, not the median: the bake has
    lamp-lit interiors in shadow too (Blood Gulch's median 0.42, its quartile
    0.19, the level picked by eye). A texel near it gives up none of its
    colour to the Unreal sun, so an object's shadow there does not darken a
    baked one a second time. None without the scene, the bake or enough of
    either."""
    try:
        import numpy as np
        from PIL import Image
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from ce_material_spec import asset_name
    except ImportError:
        return None
    try:
        g = json.load(open(scene_gltf, encoding="utf-8"))
        pages = json.load(open(os.path.join(staging, "manifest.json"), encoding="utf-8"))["bsps"][0]["lightmap_pages"]
    except (OSError, KeyError, IndexError):
        return None
    if not pages or not os.path.isdir(bake_dir or ""):
        return None
    base = os.path.dirname(scene_gltf)
    bufs = [open(os.path.join(base, b["uri"]), "rb").read() for b in g["buffers"]]

    def accessor(i, n):
        a = g["accessors"][i]
        bv = g["bufferViews"][a["bufferView"]]
        off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        return np.frombuffer(bufs[bv["buffer"]], dtype="f4", count=a["count"] * n, offset=off).reshape(-1, n)

    images = {}

    def image(path):
        if path not in images:
            try:
                images[path] = np.asarray(Image.open(path).convert("RGB"), dtype=np.float64) / 255.0
            except OSError:
                images[path] = None
        return images[path]

    def sample(img, uv):
        h, w = img.shape[:2]
        x = np.clip((uv[:, 0] % 1.0 * w).astype(int), 0, w - 1)
        y = np.clip((uv[:, 1] % 1.0 * h).astype(int), 0, h - 1)
        return img[y, x]

    # CE's sun, as sun_rotation finds it (glTF space, towards the sun).
    total, data = np.zeros(3), []
    for mesh in g["meshes"]:
        for prim in mesh["primitives"]:
            at = prim["attributes"]
            name = g["materials"][prim["material"]]["name"] if "material" in prim else ""
            tail = name.rsplit("__lm", 1)
            if len(tail) != 2 or not tail[1].isdigit() or "TEXCOORD_1" not in at or "NORMAL" not in at:
                continue
            n = accessor(at["NORMAL"], 3).astype(np.float64)
            if "_INCIDENT" in at:
                inc = accessor(at["_INCIDENT"], 3).astype(np.float64)
                flat = (n[:, 1] > 0.95) & (np.linalg.norm(inc, axis=1) > 0.5)
                total += inc[flat].sum(axis=0)
            data.append((int(tail[1]), n, accessor(at["TEXCOORD_1"], 2).astype(np.float64)))
    if not data or (sun is None and not total.any()):
        return None
    # The sky tag's sun when known (sky_sun), else the incident average.
    sun = np.asarray(sun, dtype=np.float64) if sun is not None else total / np.linalg.norm(total)
    shadow, sunlit, colours = [], [], []
    for page, n, uv in data:
        if page >= len(pages):
            continue
        stem = os.path.splitext(pages[page])[0]
        lm = image(os.path.join(staging, "textures", pages[page]))
        bake = image(os.path.join(bake_dir, asset_name("T_", stem) + ".png"))
        if lm is None or bake is None:
            continue
        facing = n @ sun > 0.5
        rgb = sample(lm, uv)
        lum = rgb @ [0.2126, 0.7152, 0.0722]
        vis = sample(bake, uv)[:, 1]
        shadow.append(lum[facing & (vis < 0.1)])
        sunlit.append(lum[facing & (vis > 0.9)])
        colours.append(rgb[facing & (vis > 0.9)])
    shadow = np.concatenate(shadow) if shadow else np.zeros(0)
    sunlit = np.concatenate(sunlit) if sunlit else np.zeros(0)
    if len(shadow) < 50 or len(sunlit) < 50:
        return None
    levels = [round(float(np.percentile(shadow, 25)), 3), round(float(np.median(sunlit)), 3)]
    colour = np.median(np.concatenate(colours), axis=0)
    return {"levels": levels if levels[1] > levels[0] else None,
            "colour": [round(float(c), 3) for c in colour / colour.max()] if colour.max() > 0 else None}


def sun_mask(bake, root):
    """lightmap_bake's sun mask as the level's environment.sun_mask: the
    cooked texture (ce_material_spec.py cooks it under <root>/Textures) and
    its placement relative to the terrain actor; None without one."""
    for f in sorted(glob.glob(os.path.join(bake or "", "*_sunmask.json"))):
        spec = json.load(open(f, encoding="utf-8"))
        name = os.path.splitext(os.path.basename(f))[0]
        return {"texture": f"{root}/Textures/{name}.{name}", **spec}
    return None


# `--no-sun-mask`: a level whose lightmaps the solver drew (its materials
# carry the sun's shares) leaves the sun mask out: the terrain copy's shadows
# are the sun's shadows there, and the mask's metre-wide transition would
# soften every one of them.
NO_SUN_MASK = False


def environment(template, placement, scene=None, staging=None, bake=None, root=None):
    env = json.loads(json.dumps(template))
    mask = sun_mask(bake, root) if root and not NO_SUN_MASK else None
    if mask:
        env["sun_mask"] = mask
    elif NO_SUN_MASK:
        # Explicit: the loader must not fall back to a trial's mask beside it.
        env["sun_mask"] = False
    sky_light = sky_sun(placement)
    rotation = sky_light["rotation"] if sky_light else (sun_rotation(scene) if scene else None)
    if rotation:
        env.setdefault("sun", {})
        env["sun"]["pitch"], env["sun"]["yaw"] = rotation
    light = (lightmap_sun(scene, staging, bake, sun=sky_light and sky_light["gltf"])
             if scene and staging and bake else None) or {}
    if light.get("levels"):
        env.setdefault("sun", {})["lightmap_sun"] = light["levels"]
    sky = next((e for e in placement.get("entries", []) if e.get("kind") == "sky"), None)
    amb = (sky or {}).get("outdoor_ambient") or {}
    color, power = amb.get("color"), amb.get("power")
    if not color or not power:
        return env
    lum = 0.2126 * color[0] + 0.7152 * color[1] + 0.0722 * color[2]
    k = power * lum / REFERENCE_AMBIENT
    # Where the level has a real sun, the sunlit lightmap's colour: CE lit an
    # object by the lightmap under it. Otherwise the sky's ambient colour,
    # unless that is no colour of light at all (Infinity's test sky is
    # (0.5, 0.5, 0)): then the lightmaps' average. A dim "sunlit" level is sky
    # light (Danger Canyon's 0.42 came out blue), and an indoor map's average
    # is its lamps (Longest's purple).
    sunny = (light.get("levels") or [0, 0])[1] >= 0.8
    tint = light.get("colour") if sunny else None
    if not tint:
        tint = [round(c / max(color), 3) for c in color] if max(color) > 0 else [1, 1, 1]
        if min(tint) < 0.25:
            tint = (lightmap_tint(staging) if staging else None) or tint
    env.setdefault("sun", {})
    env["sun"]["intensity"] = round(env["sun"].get("intensity", 8.0) * k, 3)
    env["sun"]["color"] = tint
    # CE's own sun (colour x power, CE lightmap units): with the solver's
    # ambient page the masters rebuild each texel's sunlit lightmap from it.
    if sky_light and sky_light.get("color") and sky_light.get("power"):
        env["sun"]["ce_light"] = [round(c * sky_light["power"], 4) for c in sky_light["color"]]
    env.setdefault("skylight", {})
    env["skylight"]["intensity"] = round(env["skylight"].get("intensity", 3.0) * k, 3)
    env["skylight"]["color"] = tint
    return env


# CE world units to centimetres.
WU_CM = 304.8

# CE weather particle systems drawn with the game's own Niagara systems
# (MJOLNIRLevelLoader updateWeather), by a word in the tag path. The PNW snow
# fills a box around its component, which the loader keeps at the camera:
# one copy at its own flake size and brightness is a steady snowfall there.
# Six copies at size 6 and brightness 50 (tuned against a static copy seen
# from afar) buried the camera in glowing flakes (Coldsnap, 2026-10-10).
WEATHER_SYSTEMS = {
    "snow": {"system": "/Game/FX/Library/Environment/PNW/Atmospherics/Snow/"
                       "NS_PNW_AmbientFallingSnow_System.NS_PNW_AmbientFallingSnow_System",
             "copies": 1, "params": {"User.Mote Brightness": 1.0, "User.Snow Size": 1.0}},
}


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


# The roof map's cell (cm, half a wu) and how far above the camera a
# ceiling keeps the weather out (cm): a room's or a tunnel's, not an
# overhang's far up a cliff. Each cell is sampled at its centre: at 2 wu a
# cell whose centre fell just outside Sidewinder's facility snowed over the
# room's edge (2026-10-13).
ROOF_CELL = 152.4
ROOF_REACH = 2500.0


def weather_roofs(staging, to_ue):
    """Where the level has a roof: {cell (cm), reach (cm), cells: {"ix,iy":
    [ceiling z, cm]}}, from the CE collision BSPs' downward-facing surfaces
    with a floor below them within the reach, sampled at each cell's centre,
    in Unreal centimetres (cell ix spans [ix, ix + 1) * cell). The loader
    hides the weather while a ceiling is above the camera within the reach.
    CE stops its particles at the weather polys over a room's openings (the
    BSP's weather polyhedra, mostly single planes, not volumes); the game's
    snow fills a box about the camera and fell through Coldsnap's roofs
    (2026-10-13). None without collision."""
    tris = collision_triangles(staging)
    if not tris:
        return None
    up, down = {}, {}
    for tri in tris:
        a, b, c = (to_ue(v) for v in tri)
        u = [b[i] - a[i] for i in range(3)]
        v = [c[i] - a[i] for i in range(3)]
        nz = u[0] * v[1] - u[1] * v[0]
        n = math.sqrt((u[1] * v[2] - u[2] * v[1]) ** 2 + (u[2] * v[0] - u[0] * v[2]) ** 2 + nz * nz)
        det = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        # Unreal's y is CE's flipped, which turns the winding: up is -z here.
        if n == 0 or abs(nz / n) < 0.3 or abs(det) < 1e-6:
            continue
        target = up if nz < 0 else down
        xs, ys = (a[0], b[0], c[0]), (a[1], b[1], c[1])
        for ix in range(math.floor(min(xs) / ROOF_CELL), math.floor(max(xs) / ROOF_CELL) + 1):
            px = (ix + 0.5) * ROOF_CELL
            for iy in range(math.floor(min(ys) / ROOF_CELL), math.floor(max(ys) / ROOF_CELL) + 1):
                py = (iy + 0.5) * ROOF_CELL
                w1 = ((b[1] - c[1]) * (px - c[0]) + (c[0] - b[0]) * (py - c[1])) / det
                w2 = ((c[1] - a[1]) * (px - c[0]) + (a[0] - c[0]) * (py - c[1])) / det
                if min(w1, w2, 1 - w1 - w2) < 0:
                    continue
                target.setdefault((ix, iy), []).append(w1 * a[2] + w2 * b[2] + (1 - w1 - w2) * c[2])
    cells = {}
    for key, zs in down.items():
        floors = up.get(key, [])
        keep = sorted({round(z) for z in zs if any(0 < z - f <= ROOF_REACH for f in floors)})
        if keep:
            cells[f"{key[0]},{key[1]}"] = keep
    return {"cell": ROOF_CELL, "reach": ROOF_REACH, "cells": cells}


def sky_and_weather(placement, staging, to_ue=None):
    """The level's `sky_fog` and `weather` (environment keys), as far as it has
    them. A sky with no model (Coldsnap's) is its outdoor fog's colour: the
    masters fog the level towards it in CE's display colours and reach it at
    the opaque distance, so the loader's height fog starts there, in the same
    colour made linear (the masters' SRGB_TO_LINEAR). The weather is the
    particle system most of the BSP's clusters use, with the level's roofs
    (weather_roofs, given `to_ue`). Both come from ce_fog.py's
    fog.json, and the sky fog only where a cluster draws the sky: no cluster
    of Chill Out's does, so CE never shows its sky or the sky's outdoor fog
    (its rooms take the sky's indoor fog, ce_material_spec.sky_fog)."""
    out = {}
    try:
        cefog = json.load(open(os.path.join(staging, "fog.json"), encoding="utf-8"))
    except (OSError, ValueError):
        cefog = {}
    sky = next((e for e in placement.get("entries", []) if e.get("kind") == "sky"), None)
    fog = (sky or {}).get("outdoor_fog") or {}
    # Halo 2's atmospheric fog covers its sky too: at full density
    # (Backwash's swamp, opaque at 20 world units) everything past the
    # opaque distance is the fog's colour, the black sky dome included.
    halo2_opaque = staging_source(staging) == "halo2_mcc" and fog.get("max_density", 0) >= 0.99
    if (sky and fog.get("color") and fog.get("max_density", 0) > 0
            and (halo2_opaque or (not sky.get("model") and cefog.get("sky_clusters", 0) > 0))):
        out["sky_fog"] = {"color": [round(srgb_to_linear(c), 6) for c in fog["color"]],
                          "start": round(fog.get("opaque_distance", 0.0) * WU_CM, 1)}
    try:
        systems = cefog["weather"]["systems"]
    except (KeyError, TypeError):
        systems = []
    for s in systems:
        kind = next((k for k in WEATHER_SYSTEMS if k in s["system"].lower()), None)
        if kind:
            out["weather"] = {**WEATHER_SYSTEMS[kind], "source": s["system"]}
            roofs = to_ue and weather_roofs(staging, to_ue)
            if roofs:
                out["weather"]["roofs"] = roofs
            break
        print(f"  weather {s['system']}: no Unreal system for it, left out", file=sys.stderr)
    return out


def collision_triangles(staging):
    """The CE collision BSPs' surfaces as triangles in world units, from the
    staging export's bsp/collision_N.json and .bin; [] without them."""
    tris = []
    bsp = os.path.join(staging, "bsp")
    for name in sorted(os.listdir(bsp)) if os.path.isdir(bsp) else []:
        if not re.fullmatch(r"collision_\d+\.json", name):
            continue
        meta = json.load(open(os.path.join(bsp, name), encoding="utf-8"))
        data = open(os.path.join(bsp, name[:-5] + ".bin"), "rb").read()
        arrays, off = {}, 0
        for key in meta["array_order"]:
            count = struct.unpack_from("<I", data, off)[0]
            size = meta["element_sizes"][key]
            arrays[key] = (data[off + 4:off + 4 + count * size], size, count)
            off += 4 + count * size
        vb, vs, vn = arrays["vertices"]
        verts = [struct.unpack_from("<3f", vb, i * vs) for i in range(vn)]
        eb, es, en = arrays["edges"]
        edges = [struct.unpack_from("<6i", eb, i * es) for i in range(en)]
        sb, ss, sn = arrays["surfaces"]
        for si in range(sn):
            first = struct.unpack_from("<i", sb, si * ss + 4)[0]
            ring, e = [], first
            for _ in range(64):
                start, end, forward, reverse, left, _right = edges[e]
                ring.append(start if left == si else end)
                e = forward if left == si else reverse
                if e == first:
                    break
            for k in range(1, len(ring) - 1):
                tris.append((verts[ring[0]], verts[ring[k]], verts[ring[k + 1]]))
    return tris


def point_triangle_distance(p, tri):
    """Distance from p to the closest point of a triangle (Ericson, Real-Time
    Collision Detection 5.1.5)."""
    a, b, c = tri
    sub = lambda u, v: (u[0] - v[0], u[1] - v[1], u[2] - v[2])
    dot = lambda u, v: u[0] * v[0] + u[1] * v[1] + u[2] * v[2]
    at = lambda o, u, t: (o[0] + u[0] * t, o[1] + u[1] * t, o[2] + u[2] * t)
    ab, ac, ap = sub(b, a), sub(c, a), sub(p, a)
    d1, d2 = dot(ab, ap), dot(ac, ap)
    if d1 <= 0 and d2 <= 0:
        q = a
    else:
        bp = sub(p, b)
        d3, d4 = dot(ab, bp), dot(ac, bp)
        cp = sub(p, c)
        d5, d6 = dot(ab, cp), dot(ac, cp)
        vc, vb, va = d1 * d4 - d3 * d2, d5 * d2 - d1 * d6, d3 * d6 - d5 * d4
        if d3 >= 0 and d4 <= d3:
            q = b
        elif d6 >= 0 and d5 <= d6:
            q = c
        elif vc <= 0 and d1 >= 0 and d3 <= 0:
            q = at(a, ab, d1 / (d1 - d3))
        elif vb <= 0 and d2 >= 0 and d6 <= 0:
            q = at(a, ac, d2 / (d2 - d6))
        elif va <= 0 and d4 - d3 >= 0 and d5 - d6 >= 0:
            q = at(b, sub(c, b), (d4 - d3) / ((d4 - d3) + (d5 - d6)))
        else:
            denom = va + vb + vc
            q = at(at(a, ab, vb / denom), ac, vc / denom)
    return math.dist(p, q)


def landing_nudge(tris, pos, facing):
    """How far along `facing` (CE radians) a teleporter's landing spot at
    `pos` (world units, on the floor) moves so a standing Spartan clears the
    collision by TELEPORTER_CLEARANCE: forward first, then back (negative);
    the clearest spot within reach when none does, 0.0 when it already does.
    Gephyrophobia's "teleport to" flags face the narrow mouth of their pads,
    0.19-0.21 from its sides, so forward only lost room and every pad raised
    teleporter_blocked (2026-10-07); back towards the pad's middle clears."""
    reach = TELEPORTER_CLEARANCE + TELEPORTER_NUDGE_MAX + SPARTAN_LIFT + SPARTAN_HEIGHT
    near = [t for t in tris
            if all(min(v[i] for v in t) - reach <= pos[i] <= max(v[i] for v in t) + reach for i in range(3))]
    # The sim places the shape SPARTAN_LIFT above the landing spot: sample its
    # axis from there, so the floor itself is never in the way.
    heights = [SPARTAN_LIFT + SPARTAN_RADIUS + k * (SPARTAN_HEIGHT - 2 * SPARTAN_RADIUS) / 4
               for k in range(5)]
    dx, dy = math.cos(facing), math.sin(facing)
    best = (-1.0, 0.0)
    steps = round(TELEPORTER_NUDGE_MAX / TELEPORTER_NUDGE_STEP)
    for k in [*range(steps + 1), *range(-1, -steps - 1, -1)]:
        d = k * TELEPORTER_NUDGE_STEP
        axis = [(pos[0] + dx * d, pos[1] + dy * d, pos[2] + h) for h in heights]
        clear = min((point_triangle_distance(p, t) for p in axis for t in near), default=math.inf)
        if clear >= TELEPORTER_CLEARANCE:
            return d
        if clear > best[0] + 1e-6:
            best = (clear, d)
    return best[1]


# CE sound classes (sound tag +0x04): music, cinematic_music.
CE_MUSIC_CLASSES = (32, 38)


def ambient_sounds(sounds_dir, root, to_ue):
    """The level's ambient sound, for MJOLNIRLevelLoader: the BSP's background
    loops (2D, map-wide) and the sound scenery (3D loops at their CE
    positions, falling off over CE's distance bounds), as the SoundWaves
    unreal/MJOLNIRMaterials/Scripts/build_ce_sounds.py imports."""
    manifest = json.load(open(os.path.join(sounds_dir, "sounds.json"), encoding="utf-8"))

    def wave(file):
        stem = os.path.splitext(file)[0]
        return f"{root}/{stem}.{stem}"

    def loops(lsnd):
        out = []
        for track in manifest["loops"].get(lsnd, {}).get("tracks", []):
            snd = manifest["sounds"].get(track.get("loop") or "")
            if snd and snd.get("loop"):
                out.append((track, snd))
        return out

    halo2 = manifest.get("source") == "halo2_mcc"

    def category(snd):
        """The loader scales a sound by the game's Master slider and one more:
        ambient unless the CE sound is music (classes music and
        cinematic_music), which follows the music slider."""
        return {"category": "music"} if not halo2 and snd.get("class") in CE_MUSIC_CLASSES else {}

    def tuned(track, snd):
        """The track's gain times the sound's own (Halo 2's playback gain;
        CE's sounds carry none), and its pitch when it is not 1 (Halo 2's
        random pitch bounds, as a multiplier)."""
        out = {"gain": round(track["gain"] * snd.get("gain", 1.0), 3)}
        if abs(snd.get("pitch", 1.0) - 1.0) > 1e-3:
            out["pitch"] = round(snd["pitch"], 3)
        return out

    background, emitters = [], []
    for lsnd in manifest["background"]:
        for track, snd in loops(lsnd):
            background.append({"wave": wave(snd["loop"]), **tuned(track, snd),
                               "fade_in": round(track["fade_in"], 2), "source": lsnd,
                               **category(snd)})
    origin = to_ue([0.0, 0.0, 0.0])

    def vector(v):
        """A CE offset in Unreal's axes and centimetres (no translation)."""
        u = to_ue(v)
        return [round(u[k] - origin[k], 1) for k in range(3)]

    for e in manifest["emitters"]:
        # Distance bounds: the placement's override (Halo 2's sound
        # scenery), else the looping sound's own (Halo 2's lsnd; its loops'
        # samples mostly carry none), else the sample's (CE).
        lsnd = manifest["loops"].get(e["sound"], {})
        lo, hi = e.get("distance") or ((lsnd["min_distance"], lsnd["max_distance"]) if "min_distance" in lsnd else
                                       (None, None))
        for track, snd in loops(e["sound"]):
            near = snd["min_distance"] if lo is None else lo
            far = snd["max_distance"] if hi is None else hi
            emitter = {"pos": to_ue(e["pos"]), "wave": wave(snd["loop"]),
                       **tuned(track, snd), "fade_in": round(track["fade_in"], 2),
                       "inner": round(near * WU_CM, 1),
                       "falloff": round(max(far - near, 0.1) * WU_CM, 1),
                       "source": e["sound"], **category(snd)}
            m = e.get("motion")
            if m:
                # On a machine's moving part (ce_sounds.py marker_motion): the
                # loader moves the sound as the part's material moves it,
                # (pos - pivot) * (s - 1) + lerp(t0, t1, p) from its rest.
                emitter["motion"] = {"pivot": to_ue(m["pivot"]), "t0": vector(m["t0"]), "t1": vector(m["t1"]),
                                     "s0": m["s0"], "s1": m["s1"], "period": m["period"],
                                     "position": m["position"]}
            emitters.append(emitter)
    return {"background": background, "emitters": emitters}


def machine_sounds(decor, sounds_dir, root):
    """The one-shots a turning machine's animation raises (stage's
    `h2_motion.events`, [seconds, sound] through merge_ce_scene.py and
    build_terrain_meshes.py), as the waves build_ce_sounds.py imports, each
    falling off over its sound's distance bounds: the loader plays one as
    the machine's turn passes its time. A sound not staged is dropped."""
    manifest = json.load(open(os.path.join(sounds_dir, "sounds.json"), encoding="utf-8"))
    for item in decor:
        events = (item.get("motion") or {}).get("events")
        if not events:
            continue
        out = []
        for t, path in events:
            snd = manifest["sounds"].get(path)
            if not snd or not snd.get("files"):
                continue
            stem = os.path.splitext(snd["files"][0])[0]
            near, far = snd["min_distance"], snd["max_distance"]
            out.append({"t": t, "wave": f"{root}/{stem}.{stem}", "gain": round(snd.get("gain", 1.0), 3),
                        "inner": round(near * WU_CM, 1), "falloff": round(max(far - near, 0.1) * WU_CM, 1)})
        item["motion"]["events"] = out


def norm(asset):
    # A protected map's second copy of a stock tag comes back from halo2ue
    # as `<stock path>__p<index>` (map-core deprotect.rs): place it as the
    # stock tag.
    return re.sub(r"__p\d+$", "", asset.replace("\\", "/"))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("staging")
    ap.add_argument("transform")
    ap.add_argument("out")
    ap.add_argument("--name")
    ap.add_argument("--code", help="the map's codename: its packages live under /Game/MJOLNIR/Maps/<CODE> "
                    "(docs/map_distribution.md); without it, the older /Game/MJOLNIR/Levels/<name>")
    ap.add_argument("--title")
    ap.add_argument("--tag-map", help="the tag map (default: defs/level/ce-tag-map.json, or h2-tag-map.json "
                    "for a Halo 2 staging)")
    ap.add_argument("--terrain", help="terrain decor entry (JSON object)")
    ap.add_argument("--foliage", help="scatter_foliage.py's out.json: the level's `foliage` (its file beside "
                                      "the level file)")
    ap.add_argument("--sounds", help="tools/level/ce_sounds.py's output directory (its sounds.json): "
                                     "the map's ambient sound, imported under <root>/Sounds")
    ap.add_argument("--machines", help="tools/level/h2_machines.py's machines.json: Halo 2's turning parts as "
                                       "machines of the simulation's own, placed where the parts are, each "
                                       "part's mesh riding its machine (motion.follow)")
    ap.add_argument("--scene", help="the merged scene glTF, for the sun's direction "
                                    "(default: scene.gltf beside --terrain)")
    ap.add_argument("--bake", help="lightmap_bake's output, for the lightmap levels in CE's shadow and sun "
                                   "(default: bake beside --terrain)")
    ap.add_argument("--no-sun-mask", action="store_true",
                    help="leave the sun mask out of the level (the solver's lightmaps: the terrain copy's shadows "
                         "are the sun's shadows, and the mask would soften them)")
    ap.add_argument("--no-spawn-points", action="store_true",
                    help="do not place multiplayer spawn-point scenery at the starts")
    ap.add_argument("--game-type", choices=sorted(VEHICLE_SETS), default="all",
                    help="whose default vehicle set to place (default all: every vehicle)")
    ap.add_argument("--start-lift", type=float, default=START_LIFT,
                    help=f"Halo wu to raise player starts by (default {START_LIFT})")
    ap.add_argument("--sky-sun", action="store_true",
                    help="print the sky tag's sun as 'x,y,z' towards it in glTF space (lightmap_bake --sun) "
                         "and exit; nothing when the sky has no sun")
    a = ap.parse_args()
    global NO_SUN_MASK
    NO_SUN_MASK = bool(a.no_sun_mask)
    if a.sky_sun:
        s = sky_sun(json.load(open(os.path.join(a.staging, "placement.json"))))
        if s:
            print(",".join(f"{c:.6f}" for c in s["gltf"]))
        return
    scene = a.scene or (os.path.join(os.path.dirname(a.terrain), "scene.gltf") if a.terrain else None)
    bake = a.bake or (os.path.join(os.path.dirname(a.terrain), "bake") if a.terrain else None)

    placement = json.load(open(os.path.join(a.staging, "placement.json")))
    # A seated beacon's flares go where merge_ce_scene.py put its model (ce_seat.py).
    from ce_seat import seat
    seat(placement, a.staging, log=lambda *_: None)
    t = json.load(open(a.transform))
    source = staging_source(a.staging)
    tag_map = json.load(open(a.tag_map or (H2_TAG_MAP if source == "halo2_mcc" else TAG_MAP)))
    # Every type the bake knows: it adds what the canvas palette lacks.
    palette = json.load(open(PALETTE_MAP))
    canvas = t["canvas"].upper()
    if canvas not in CANVASES:
        raise SystemExit(f"no blank level known for canvas {canvas}")
    blank = json.load(open(CANVASES[canvas]["blank"]))
    delta = t["delta"]
    name = a.name or os.path.basename(os.path.normpath(a.staging))

    def to_ue(p):
        x, y, z = p[0] + delta[0], p[1] + delta[1], p[2] + delta[2]
        return [round(x * 304.8, 1), round(-y * 304.8, 1), round(z * 304.8, 1)]

    def yaw_ue(rot):
        yaw = rot[0] if isinstance(rot, list) else rot
        return round(-math.degrees(yaw), 1)

    dropped = collections.Counter()

    def resolve(section, asset, vehicle_type=None):
        candidates = tag_map[section].get(asset)
        if candidates is None and vehicle_type:
            # A custom map's own vehicle, or a protected map's whose name did
            # not come back: placed by the CE vehicle type it declares.
            candidates = tag_map["vehicle_types"].get(vehicle_type)
        if candidates is None:
            dropped[f"{asset} (unmapped)"] += 1
            return None
        for c in candidates:
            if c in palette[section]:
                return c
        dropped[f"{asset} (no equivalent in this game)"] += 1
        return None

    # Starts: every one a slayer or CTF game would use, de-duplicated by
    # position, in team order.
    usable = [s for s in placement["player_starts"] if any(g in START_TYPES for g in s["game_types"])]
    usable = usable or placement["player_starts"]
    pos_key = lambda s: tuple(round(v, 2) for v in s["pos"])
    # CTF gives each start a team; Slayer ignores it. A spot a CTF start uses
    # is labelled with its team, the rest "none", and the CTF variant sets
    # the spawn points' teams by label (blam-megalo ctf.rs); they stay neutral
    # for every other game type.
    ctf_team = {}
    for s in placement["player_starts"]:
        if any(g in CTF_START_TYPES for g in s["game_types"]) and s["team"] in CTF_TEAMS_UE:
            ctf_team.setdefault(pos_key(s), CTF_TEAMS_UE[s["team"]])
    seen, starts, spawns = set(), [], []
    for s in sorted(usable, key=lambda s: s["team"]):
        key = pos_key(s)
        if key not in seen:
            seen.add(key)
            lifted = [s["pos"][0], s["pos"][1], s["pos"][2] + a.start_lift]
            starts.append({"pos": to_ue(lifted), "yaw": yaw_ue(s["facing"])})
            spawns.append({
                "tag": SPAWN_SCENERY,
                "group": "scenery",
                "pos": to_ue(lifted),
                "rot": [0, yaw_ue(s["facing"]), 0],
                "set": {"multiplayer data.owner team": "neutral",
                        "multiplayer data.megalo label": f"ctf_spawn_{ctf_team.get(key, 'none')}"},
            })

    vehicles, weapons, equipment, health_spots = [], [], [], []
    vehicle_sets = []
    for e in placement["entries"]:
        asset = norm(e.get("asset", ""))
        if e["kind"] == "vehicle":
            # A CE scenario stacks every game type's vehicles on the same
            # spots and spawns only the set its game type selects. Staging
            # that predates the spawn-flag fix reads 0 for every vehicle.
            flags = e.get("spawn_flags", 0) or ALL_GAME_TYPES
            if not flags & VEHICLE_SETS[a.game_type]:
                dropped[f"{asset} (not in {a.game_type}'s vehicle set)"] += 1
                continue
            kind = resolve("vehicles", asset, e.get("vehicle_type"))
            if kind:
                lift = VEHICLE_LIFT.get(kind, VEHICLE_LIFT_DEFAULT)
                pos = [e["pos"][0], e["pos"][1], e["pos"][2] + lift]
                set_type = vehicle_set_type(asset, e.get("vehicle_type"))
                team = CE_TEAMS.get(e.get("team"), "neutral")
                v = {"type": kind, "pos": to_ue(pos), "yaw": yaw_ue(e["rot"]),
                     "set": {"multiplayer data.spawn time": str(spread(DEFAULT_RESPAWN, len(vehicles))),
                             "multiplayer data.abandonment time": str(VEHICLE_ABANDONMENT),
                             "multiplayer data.owner team": CE_OWNER_TEAMS.get(team, "neutral"),
                             "multiplayer data.spawn flags": HIDE_UNLESS_REQUIRED}}
                if lift:
                    v["set"].update(NOT_AT_REST)
                if asset in VEHICLE_VARIANTS:
                    v["set"]["permutation data.variant name"] = VEHICLE_VARIANTS[asset]
                vehicles.append(v)
                vehicle_sets.append({"type": set_type, "team": team,
                                     "default": flags & 0xF, "allowed": (flags >> 8) & 0xF})
        elif e["kind"] == "netgame_equipment":
            if asset == HEALTH_PACK:
                health_spots.append({
                    "tag": HEALTH_SPOT_SCENERY,
                    "group": "scenery",
                    "pos": to_ue(e["pos"]),
                    "rot": [0, yaw_ue(e.get("rot", [0, 0, 0])), 0],
                    "set": {"multiplayer data.owner team": "neutral",
                            "multiplayer data.megalo label": HEALTH_SPOT_LABEL},
                })
                continue
            section = "weapons" if asset in tag_map["weapons"] else "equipment"
            kind = resolve(section, asset)
            if not kind:
                continue
            lift = 0.0 if e.get("levitate") else ITEM_LIFT
            pos = [e["pos"][0], e["pos"][1], e["pos"][2] + lift]
            item = {"type": kind, "pos": to_ue(pos)}
            if section == "weapons":
                item["yaw"] = yaw_ue(e.get("rot", [0, 0, 0]))
            item["set"] = {"multiplayer data.spawn time":
                           str(spread(spawn_seconds(e) or DEFAULT_RESPAWN, len(weapons) + len(equipment)))}
            if lift:
                item["set"].update(NOT_AT_REST)
            (weapons if section == "weapons" else equipment).append(item)

    # The vehicle set labels: by type and team, the vehicles default in the
    # most game types first, then CE's order; the k-th of each team share
    # `ce_<type>_<k>`.
    ranked = collections.defaultdict(list)
    for i, vs in enumerate(vehicle_sets):
        ranked[(vs["type"], vs["team"])].append(i)
    for members in ranked.values():
        members.sort(key=lambda i: (-bin(vehicle_sets[i]["default"]).count("1"), -vehicle_sets[i]["default"],
                                    -vehicle_sets[i]["allowed"], i))
        for rank, i in enumerate(members, 1):
            label = f"ce_{vehicle_sets[i]['type']}_{min(rank, VEHICLE_SET_RANKS)}"
            vehicle_sets[i]["label"] = label
            vehicles[i]["set"]["multiplayer data.megalo label"] = label

    single_bsp = bool(t.get("own_bsp")) and t.get("scenario_bsp_index") == 0
    wb = t["world_bounds"]
    lo_z, hi_z = CANVASES[canvas]["shipped_z"]
    if t.get("own_bsp"):
        # The BSP is the CE map alone: its box is the terrain's, and must not
        # reach down into the canvas's other BSPs' space.
        lo_z, hi_z = wb["min"][2], wb["max"][2]
    world_bounds = {
        "bsp": t["bsp_index"],
        "min": [
            round(wb["min"][0] - WORLD_MARGIN, 2),
            round(wb["min"][1] - WORLD_MARGIN, 2),
            round(min(wb["min"][2] - WORLD_MARGIN, lo_z - WORLD_MARGIN), 2),
        ],
        "max": [
            round(wb["max"][0] + WORLD_MARGIN, 2),
            round(wb["max"][1] + WORLD_MARGIN, 2),
            round(max(wb["max"][2] + WORLD_MARGIN, hi_z + WORLD_MARGIN), 2),
        ],
    }

    def sender_yaw(f):
        yaw = yaw_ue(f["facing"])
        if f["type"] == "TeleportFrom":
            yaw = round((yaw + 360.0) % 360.0 - 180.0, 1)
        return yaw

    teleporters = []
    pads = [f for f in placement["netgame_flags"] if f["type"] in TELEPORTER_SCENERY]
    ce_channel = lambda f: f.get("channel", f.get("team", 0))
    by_channel = {}
    for f in pads:
        by_channel.setdefault(ce_channel(f), set()).add(f["type"])
    for ch, ends in sorted(by_channel.items()):
        if ends != set(TELEPORTER_SCENERY):
            print(f"warning: CE teleporter channel {ch} has only {', '.join(sorted(ends))}; it cannot teleport",
                  file=sys.stderr)

    # Two-way pads (TELEPORTER_2WAY): channels a and b, each with one flag
    # of each kind, where a's "from" sits on b's "to" and b's "from" on a's.
    def one_each(ch):
        ends = [f for f in pads if ce_channel(f) == ch]
        return len(ends) == 2 and {f["type"] for f in ends} == set(TELEPORTER_SCENERY)

    def end(ch, kind):
        return next(f for f in pads if ce_channel(f) == ch and f["type"] == kind)

    def same_pad(src, dst):
        turned = abs((sender_yaw(src) - yaw_ue(dst["facing"]) + 180.0) % 360.0 - 180.0)
        return math.dist(src["pos"], dst["pos"]) < TELEPORTER_RADIUS and turned < TELEPORTER_2WAY_YAW

    links = {}   # CE channel -> the channel key its pads end up on
    for ch_a in sorted(by_channel):
        if ch_a in links or not one_each(ch_a):
            continue
        for ch_b in sorted(by_channel):
            if ch_b <= ch_a or ch_b in links or not one_each(ch_b):
                continue
            if (same_pad(end(ch_a, "TeleportFrom"), end(ch_b, "TeleportTo"))
                    and same_pad(end(ch_b, "TeleportFrom"), end(ch_a, "TeleportTo"))):
                links[ch_a] = links[ch_b] = (ch_a, ch_b)
                break
    for ch in by_channel:
        links.setdefault(ch, (ch,))

    # The channel is a char enum naming 26 channels, alpha to zulu. A map
    # with more numbers the rest: the field takes a raw value, and the engine
    # pairs ends by value alone (0x1803e6600 compares the byte).
    dense = {key: i for i, key in enumerate(sorted(set(links.values())))}
    if len(dense) > 127:
        sys.exit(f"{len(dense)} teleporter channels; a char enum holds 127")
    channel_value = lambda i: TELEPORTER_CHANNELS[i] if i < len(TELEPORTER_CHANNELS) else str(i)
    collision = collision_triangles(a.staging) if pads else []
    nudged = []
    for f in pads:
        two_way = len(links[ce_channel(f)]) == 2
        if two_way and f["type"] == "TeleportFrom":
            continue   # the pad's 2-way end stands at its "teleport to" flag
        channel = dense[links[ce_channel(f)]]
        pos = f["pos"]
        if f["type"] == "TeleportTo" and collision:
            d = landing_nudge(collision, pos, f["facing"])
            if d:
                pos = [pos[0] + math.cos(f["facing"]) * d, pos[1] + math.sin(f["facing"]) * d, pos[2]]
                nudged.append(abs(d))
        teleporters.append({
            "tag": TELEPORTER_2WAY if two_way else TELEPORTER_SCENERY[f["type"]],
            "group": "scenery",
            "pos": to_ue(pos),
            # Reach's teleporter keeps a player's facing relative to the
            # sender: exit = receiver + (player - sender) + 180, the sender's
            # front facing the player who walks in. CE turns the player to the
            # receiver flag's facing and its "teleport from" flags point the
            # way players walk in, so a sender turned round makes walking in
            # head-on exit as CE does. As placed, players had to walk in
            # backwards to exit the right way (2026-10-01, Gephyrophobia).
            # A 2-way end takes its "teleport to" flag's facing, which
            # same_pad checked is its "teleport from" flag's turned round.
            "rot": [0, sender_yaw(f), 0],
            "set": {
                "multiplayer data.teleporter channel": channel_value(channel),
                "multiplayer data.boundary shape": "cylinder",
                "multiplayer data.boundary width or radius": f"{TELEPORTER_RADIUS}",
                "multiplayer data.boundary positive height": f"{TELEPORTER_HEIGHT}",
                "multiplayer data.boundary negative height": "0.1",
            },
        })
    if nudged:
        print(f"{len(nudged)} teleporter landing spot(s) moved to fit a Spartan "
              f"(up to {max(nudged):.2f} wu)", file=sys.stderr)
    if len(teleporters) > TELEPORTER_MAX:
        print(f"warning: {len(teleporters)} teleporter ends; the simulation keeps {TELEPORTER_MAX}, "
              "and the rest do nothing", file=sys.stderr)

    flag_stands = []
    for f in placement["netgame_flags"]:
        if f["type"] != "CtfFlag" or f["team"] not in CTF_TEAMS:
            continue
        flag_stands.append({
            "tag": FLAG_STAND_SCENERY,
            "group": "scenery",
            "pos": to_ue(f["pos"]),
            "rot": [0, yaw_ue(f["facing"]), 0],
            "set": {
                "multiplayer data.megalo label": FLAG_STAND_LABEL,
                "multiplayer data.owner team": CTF_TEAMS[f["team"]],
                "multiplayer data.boundary shape": "cylinder",
                "multiplayer data.boundary width or radius": f"{CAPTURE_RADIUS}",
                "multiplayer data.boundary positive height": f"{CAPTURE_HEIGHT}",
                "multiplayer data.boundary negative height": "0.5",
            },
        })
    ctf = {f["team"] for f in placement["netgame_flags"] if f["type"] == "CtfFlag"} >= set(CTF_TEAMS)
    if not ctf:
        flag_stands = []

    markers = []
    for f in placement["netgame_flags"]:
        kind = tag_map["markers"].get(f["type"])
        if kind:
            markers.append({"type": kind, "team": f["team"], "pos": to_ue(f["pos"]), "yaw": yaw_ue(f["facing"])})
        else:
            dropped[f"netgame flag {f['type']}"] += 1

    # Halo 2's turning parts as the simulation's own machines (h2_machines.py),
    # at the parts' places and full rotation (Zanzibar's flywheels are
    # tilted). The mesh merge_ce_scene.py wrote for each part names its
    # staging entry; it rides that machine's Unreal actor.
    machines = json.load(open(a.machines, encoding="utf-8")) if a.machines else {}
    sim_machines, follow = [], {}
    for n, e in enumerate(placement["entries"]):
        m = machines.get(e.get("asset")) if e.get("h2_motion") else None
        if not m:
            continue
        rot = e.get("rot") or [0.0, 0.0, 0.0]
        sim_machines.append({"tag": m["tag"], "group": "machines", "pos": to_ue(e["pos"]),
                             "rot": [0, yaw_ue(rot), 0],
                             "set": {"object data.rotation": "({}, {}, {})".format(*rot)}})
        follow[n] = {"class": m["class"], "pos": to_ue(e["pos"])}

    decor = []
    if a.terrain:
        terrain = json.load(open(a.terrain))
        # One entry, or several (the opaque terrain and its transparent
        # sections, which are a mesh of their own).
        for i, item in enumerate(terrain if isinstance(terrain, list) else [terrain]):
            item.setdefault("id", f"{name}_terrain" + (f"_{i}" if i else ""))
            motion = item.get("motion")
            if motion and motion.get("entry") in follow:
                motion["follow"] = follow[motion["entry"]]
            decor.append(item)
    texture_root = (f"/Game/MJOLNIR/Maps/{a.code.upper()}" if a.code else f"/Game/MJOLNIR/Levels/{name}") + "/Textures"
    flares = flare_decor(placement, texture_root, to_ue)
    decor.extend(flares)
    decals = decal_decor(placement, scene, texture_root, delta) if source == "halo2_mcc" else []
    decor.extend(decals)

    title = a.title or (H2_TITLES if source == "halo2_mcc" else STOCK_TITLES).get(name, name)
    level = {
        "schema_version": 1,
        "name": name,
        "title": title,
        "description": (
            f"{title}, from {SOURCE_GAMES.get(source, 'Halo')}: its own collision, spawns, vehicles, "
            "weapons and teleporters."
            if t.get("own_bsp")
            else f"Classic CE {name}, Slayer: collision inside {canvas} BSP {t['bsp_index']} "
            f"({t['bsp_tag']}) at Halo-wu offset ({delta[0]:.2f}, {delta[1]:.2f}, {delta[2]:.2f}); "
            "spawns, vehicles and weapons from the CE scenario."
        ),
        # The game the map comes from (the menus' and the hub's game filter).
        "game": "halo2" if source == "halo2_mcc" else "halo1",
        "canvas": {"scenario": canvas, "origin": [0, 0, 0]},
        # Started under the Megalo engine by MJOLNIRLevelLoader's native half.
        "multiplayer": True,
        # Rules: MJOLNIRLevelLoader's variants/slayer.mglo (convert_ce_map.sh
        # writes it with `mjolnir megalo write --mode slayer`).
        "variant": "slayer",
        # The game types the multiplayer menu (MJOLNIRLobby) offers for the
        # map; each needs its variants/<mode>.mglo installed. CTF needs a
        # flag for each team.
        "modes": ["slayer"] + (["ctf"] if ctf else []),
        # The terrain's materials output CE's own colours; the level's
        # post-process volume keeps everything between them and the screen
        # neutral: fixed exposure, no local exposure, no filmic curve
        # (MJOLNIRLevelLoader "post").
        "environment": {**environment(blank["environment"], placement, scene, a.staging, bake,
                                      f"/Game/MJOLNIR/Maps/{a.code.upper()}" if a.code else None),
                        **sky_and_weather(placement, a.staging, to_ue),
                        **({"haze": fill} if (fill := h2_fog_fill(a.staging, to_ue) if source == "halo2_mcc" else None)
                           else {}),
                        **({"water": {"style": "ocean", **({"params": OCEAN_MAPS[name]} if OCEAN_MAPS[name] else {})}}
                           if name in OCEAN_MAPS else {}),
                        "post": {"tone_curve": 0.0, "expand_gamut": 0.0, "blue_correction": 0.0,
                                 "manual_exposure": True, "exposure_bias": 0.0, "local_exposure": 1.0}},
        "blam": {
            "clear": ({**blank["blam"]["clear"],
                       "blocks": blank["blam"]["clear"].get("blocks", []) + CANVAS_MISSION_BLOCKS}
                      if single_bsp else blank["blam"]["clear"]),
            "player_starts": starts,
            "vehicles": vehicles,
            "weapons": weapons,
            "equipment": equipment,
            "objects": ([] if a.no_spawn_points else spawns) + teleporters + flag_stands + health_spots
                       + sim_machines,
            "world_bounds": [world_bounds],
            # A CE multiplayer map is a multiplayer scenario. The type does not
            # gate a launch (a multiplayer-typed map still starts under the
            # campaign engine), but it is what the scenario is.
            "set": {"type": "multiplayer", **(NO_CANVAS_DESIGNS if t.get("own_bsp") else {})},
            # The multiplayer engine creates objects that carry multiplayer
            # data (weapons, vehicles, the spawn points) only through the map
            # variant, which it builds from the placements whose tags a map
            # variant palette lists.
            "map_variant": True,
            # A map on its own BSP loads that BSP alone: every other canvas
            # BSP the starting zone set keeps active claims its own space.
            "active_bsps": [t["bsp_index"]] if t.get("own_bsp") else [],
            # A BSP built for index 0 (`level collision --bsp-index 0`) is
            # the scenario's only one: the bake drops the canvas mission's
            # other BSPs, zone sets, designs and seams.
            **({"single_bsp": t["bsp_index"]} if single_bsp else {}),
        },
        "markers": markers,
        "decor": decor,
    }
    if ctf:
        # The stands need no mesh of their own: CE's own flag base scenery
        # sits at each flag and comes in with the map's scenery.
        level["ctf"], _ = ctf_section([(CTF_TEAMS_UE[f["team"]], to_ue(f["pos"]), yaw_ue(f["facing"]))
                                       for f in placement["netgame_flags"]
                                       if f["type"] == "CtfFlag" and f["team"] in CTF_TEAMS])
    if health_spots:
        level["health_pack"] = dict(HEALTH_PACK_MESH, materials=[ce_model_material("healthpack.png")])
    if vehicle_sets:
        level["vehicle_sets"] = vehicle_sets
    foliage = json.load(open(a.foliage, encoding="utf-8")) if a.foliage else {}
    if foliage.get("groups"):
        # The game's grass, tufts and shore stones (scatter_foliage.py), with
        # a steady breeze for the grass (MJOLNIRLevelLoader Foliage.wind).
        level["foliage"] = {**foliage, "wind": {"dir": [0.9, 0.4], "strength": 0.4}}
    lifts = h2_lifts(placement, to_ue)
    if lifts:
        level["lifts"] = lifts
    if a.sounds:
        sound_root =f"/Game/MJOLNIR/Maps/{a.code.upper()}/Sounds" if a.code else f"/Game/MJOLNIR/Levels/{name}/Sounds"
        level["environment"]["sounds"] = ambient_sounds(a.sounds, sound_root, to_ue)
        machine_sounds(decor, a.sounds, sound_root)
    with open(a.out, "w") as f:
        json.dump(level, f, indent=2)
        f.write("\n")
    print(
        f"{name}: {len(starts)} starts, {len(vehicles)} vehicles, {len(weapons)} weapons, "
        f"{len(equipment)} equipment, {len(teleporters)} teleporter ends, {len(flag_stands)} flag stands, "
        f"{len(markers)} markers, {len(decor)} decor ({len(flares)} lens flares), {len(health_spots)} health packs"
    )
    for what, n in sorted(dropped.items()):
        print(f"  dropped {n:3} x {what}")


if __name__ == "__main__":
    main()

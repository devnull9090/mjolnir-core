"""Generate a level file for any classic CE map from its halo2ue export.

    python tools/level/gen_ce_level.py <staging dir> <transform.json> <out.level.json>
        [--name NAME] [--title TITLE] [--terrain terrain.json]

`transform.json` is what `mjolnir level collision` writes beside the converted
BSP: the CE-to-canvas offset, the canvas and its BSP index, and the terrain's
box in canvas space. Everything placed here moves by that same offset, so the
starts, vehicles and pickups land on the converted collision.

Player starts, vehicles, pickups and netgame markers come from the staging
export's placement.json. CE tags map to level-file types through
defs/level/ce-tag-map.json; the first candidate the game has a type for
(defs/level/palette-map.json; the bake adds what the canvas palette lacks)
wins, and what cannot be placed is reported.

`--terrain` names a JSON object for the terrain mesh decor entry (`mesh`,
`pos`, `scale`, `materials`), as mesh_rewrite reports it
(docs/ue_mesh_write.md). Without it the map has collision but no terrain
visuals, which is enough to test a conversion by standing on it.
"""
import argparse
import collections
import json
import math
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
TAG_MAP = os.path.join(ROOT, "defs", "level", "ce-tag-map.json")
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

# CE vehicles that are a model variant of a Campaign Evolved one: the rocket
# Warthog is the Warthog with its "rocket" turret (warthog-model variants:
# default, gauss, troop, rocket, ...).
VEHICLE_VARIANTS = {"vehicles/rwarthog/rwarthog": "rocket"}

# Vehicles that start inside the floor at CE's height: Blood Gulch's
# Banshees on the base roofs and its Scorpions were thrown on their sides
# (2026-10-01). They start this many wu higher and fall into place (not
# "create at rest", which would leave them hanging there).
VEHICLE_LIFT = {"banshee": 0.3, "scorpion": 0.3}

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
    """CE object rotation, row-major (as merge_ce_collision.py has it)."""
    cy, sy, cp, sp, cr, sr = (math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch),
                              math.cos(roll), math.sin(roll))
    rz = [[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]]
    ry = [[cp, 0, -sp], [0, 1, 0], [sp, 0, cp]]
    rx = [[1, 0, 0], [0, cr, -sr], [0, sr, cr]]

    def mul(a, b):
        return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    return mul(mul(rz, ry), rx)


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


def lightmap_sun(scene_gltf, staging, bake_dir):
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
    if not total.any() or not data:
        return None
    sun = total / np.linalg.norm(total)
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


def environment(template, placement, scene=None, staging=None, bake=None):
    env = json.loads(json.dumps(template))
    rotation = sun_rotation(scene) if scene else None
    if rotation:
        env.setdefault("sun", {})
        env["sun"]["pitch"], env["sun"]["yaw"] = rotation
    light = (lightmap_sun(scene, staging, bake) if scene and staging and bake else None) or {}
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
    env.setdefault("skylight", {})
    env["skylight"]["intensity"] = round(env["skylight"].get("intensity", 3.0) * k, 3)
    env["skylight"]["color"] = tint
    return env


# CE world units to centimetres.
WU_CM = 304.8


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

    background, emitters = [], []
    for lsnd in manifest["background"]:
        for track, snd in loops(lsnd):
            background.append({"wave": wave(snd["loop"]), "gain": round(track["gain"], 3),
                               "fade_in": round(track["fade_in"], 2), "source": lsnd})
    for e in manifest["emitters"]:
        for track, snd in loops(e["sound"]):
            emitters.append({"pos": to_ue(e["pos"]), "wave": wave(snd["loop"]),
                             "gain": round(track["gain"], 3), "fade_in": round(track["fade_in"], 2),
                             "inner": round(snd["min_distance"] * WU_CM, 1),
                             "falloff": round(max(snd["max_distance"] - snd["min_distance"], 0.1) * WU_CM, 1),
                             "source": e["sound"]})
    return {"background": background, "emitters": emitters}


def norm(asset):
    return asset.replace("\\", "/")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("staging")
    ap.add_argument("transform")
    ap.add_argument("out")
    ap.add_argument("--name")
    ap.add_argument("--code", help="the map's codename: its packages live under /Game/MJOLNIR/Maps/<CODE> "
                    "(docs/map_distribution.md); without it, the older /Game/MJOLNIR/Levels/<name>")
    ap.add_argument("--title")
    ap.add_argument("--terrain", help="terrain decor entry (JSON object)")
    ap.add_argument("--sounds", help="tools/level/ce_sounds.py's output directory (its sounds.json): "
                                     "the map's ambient sound, imported under <root>/Sounds")
    ap.add_argument("--scene", help="the merged scene glTF, for the sun's direction "
                                    "(default: scene.gltf beside --terrain)")
    ap.add_argument("--bake", help="lightmap_bake's output, for the lightmap levels in CE's shadow and sun "
                                   "(default: bake beside --terrain)")
    ap.add_argument("--no-spawn-points", action="store_true",
                    help="do not place multiplayer spawn-point scenery at the starts")
    ap.add_argument("--game-type", choices=sorted(VEHICLE_SETS), default="all",
                    help="whose default vehicle set to place (default all: every vehicle)")
    ap.add_argument("--start-lift", type=float, default=START_LIFT,
                    help=f"Halo wu to raise player starts by (default {START_LIFT})")
    a = ap.parse_args()
    scene = a.scene or (os.path.join(os.path.dirname(a.terrain), "scene.gltf") if a.terrain else None)
    bake = a.bake or (os.path.join(os.path.dirname(a.terrain), "bake") if a.terrain else None)

    placement = json.load(open(os.path.join(a.staging, "placement.json")))
    t = json.load(open(a.transform))
    tag_map = json.load(open(TAG_MAP))
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

    def resolve(section, asset):
        candidates = tag_map[section].get(asset)
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
    for e in placement["entries"]:
        asset = norm(e.get("asset", ""))
        if e["kind"] == "vehicle":
            # A CE scenario stacks every game type's vehicles on the same
            # spots and spawns only the set its game type selects; placing
            # them all piles them up. Staging that predates the spawn-flag
            # fix reads 0 for every vehicle, so 0 keeps them all.
            flags = e.get("spawn_flags", 0)
            if flags and not flags & VEHICLE_SETS[a.game_type]:
                dropped[f"{asset} (not in {a.game_type}'s vehicle set)"] += 1
                continue
            kind = resolve("vehicles", asset)
            if kind:
                lift = VEHICLE_LIFT.get(kind, 0.0)
                pos = [e["pos"][0], e["pos"][1], e["pos"][2] + lift]
                v = {"type": kind, "pos": to_ue(pos), "yaw": yaw_ue(e["rot"]),
                     "set": {"multiplayer data.spawn time": str(DEFAULT_RESPAWN),
                             "multiplayer data.abandonment time": str(VEHICLE_ABANDONMENT)}}
                if lift:
                    v["set"]["object data.placement flags"] = "0x0"
                if asset in VEHICLE_VARIANTS:
                    v["set"]["permutation data.variant name"] = VEHICLE_VARIANTS[asset]
                vehicles.append(v)
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
            item = {"type": kind, "pos": to_ue(e["pos"])}
            if section == "weapons":
                item["yaw"] = yaw_ue(e.get("rot", [0, 0, 0]))
            item["set"] = {"multiplayer data.spawn time": str(spawn_seconds(e) or DEFAULT_RESPAWN)}
            (weapons if section == "weapons" else equipment).append(item)

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
    # The channel is a char enum naming 26 channels, alpha to zulu. A map
    # with more (Chiron TL-34 has 30) numbers the rest: the field takes a raw
    # value, and the engine pairs a sender with receivers by value alone.
    dense = {ch: i for i, ch in enumerate(sorted(by_channel))}
    if len(dense) > 127:
        sys.exit(f"{len(dense)} teleporter channels; a char enum holds 127")
    channel_value = lambda i: TELEPORTER_CHANNELS[i] if i < len(TELEPORTER_CHANNELS) else str(i)
    for f in pads:
        tag = TELEPORTER_SCENERY[f["type"]]
        channel = dense[ce_channel(f)]
        teleporters.append({
            "tag": tag,
            "group": "scenery",
            "pos": to_ue(f["pos"]),
            # Reach's teleporter keeps a player's facing relative to the
            # sender: exit = receiver + (player - sender) + 180, the sender's
            # front facing the player who walks in. CE turns the player to the
            # receiver flag's facing and its "teleport from" flags point the
            # way players walk in, so a sender turned round makes walking in
            # head-on exit as CE does. As placed, players had to walk in
            # backwards to exit the right way (2026-10-01, Gephyrophobia).
            "rot": [0, sender_yaw(f), 0],
            "set": {
                "multiplayer data.teleporter channel": channel_value(channel),
                "multiplayer data.boundary shape": "cylinder",
                "multiplayer data.boundary width or radius": f"{TELEPORTER_RADIUS}",
                "multiplayer data.boundary positive height": f"{TELEPORTER_HEIGHT}",
                "multiplayer data.boundary negative height": "0.1",
            },
        })

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

    decor = []
    if a.terrain:
        terrain = json.load(open(a.terrain))
        # One entry, or several (the opaque terrain and its transparent
        # sections, which are a mesh of their own).
        for i, item in enumerate(terrain if isinstance(terrain, list) else [terrain]):
            item.setdefault("id", f"{name}_terrain" + (f"_{i}" if i else ""))
            decor.append(item)
    texture_root = (f"/Game/MJOLNIR/Maps/{a.code.upper()}" if a.code else f"/Game/MJOLNIR/Levels/{name}") + "/Textures"
    flares = flare_decor(placement, texture_root, to_ue)
    decor.extend(flares)

    title =a.title or STOCK_TITLES.get(name, name)
    level = {
        "schema_version": 1,
        "name": name,
        "title": title,
        "description": (
            f"{title}, from Halo: Combat Evolved: its own collision, spawns, vehicles, "
            "weapons and teleporters."
            if t.get("own_bsp")
            else f"Classic CE {name}, Slayer: collision inside {canvas} BSP {t['bsp_index']} "
            f"({t['bsp_tag']}) at Halo-wu offset ({delta[0]:.2f}, {delta[1]:.2f}, {delta[2]:.2f}); "
            "spawns, vehicles and weapons from the CE scenario."
        ),
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
        "environment": {**environment(blank["environment"], placement, scene, a.staging, bake),
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
            "objects": ([] if a.no_spawn_points else spawns) + teleporters + flag_stands + health_spots,
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
    if a.sounds:
        sound_root =f"/Game/MJOLNIR/Maps/{a.code.upper()}/Sounds" if a.code else f"/Game/MJOLNIR/Levels/{name}/Sounds"
        level["environment"]["sounds"] = ambient_sounds(a.sounds, sound_root, to_ue)
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

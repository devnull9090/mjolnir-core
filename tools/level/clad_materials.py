"""Cooked materials for a landscape world's cladding rocks.

The rocks are mesh actors baked into the world (MjolnirUIBuilder BakeFoliage,
flag 8: our cliff materials drew black on instanced meshes in this game). The
loader used to give each light group a dynamic instance of the cliffs' master
at load and set it on every rock, one Lua call a rock: 1.36 s for Ascension's
120,427 rocks, 0.5 s for its 40,390 within reach (2026-11-16). Everything that
material is made of is known when the map is built, so it is made here
instead: one MaterialInstanceConstant a group, set on the group's rocks in
the editor when the world bakes them, cooked into the landscape's chunk.

`entries` mirrors MJOLNIRLevelLoader Land.cliffs' cladding branch: the same
master, textures and vectors, from the same level fields. The editor stage
computes them from the parts of the level it has; assemble computes them
again from the finished level and stops the build when the two differ.

The loader still makes the dynamic instances when the world's rocks wear no
such material (an older world), when the light scale differs from the one
baked (`mjolnir_light_scale`) or the lightmap levels do (terrain shadows'
override): `light_scale` and `levels` go in the level file for that check.

The game's own textures (the Megascans rock, grass, sand and soil sets) are
named through never-cooked stand-ins at their paths (/Game/Megascans is in
DirectoriesToNeverCook), as the baked foliage names the game's meshes.
"""
import hashlib
import json

MEGASCANS = "/Game/Megascans/Surfaces/"
TRIAL = "/Game/MJOLNIR/CETrial/"
DEFAULT_LIGHT_SCALE = 256

# MJOLNIRLevelLoader's Land.ROCK_A, Land.ROCK_B, Land.SOIL and the three
# Land.SURFACES the cliffs take.
ROCK = {"d": "Rock_Jagged_udemcebew/T_Rock_Jagged_udemcebew_NSVT_D",
        "n": "Rock_Jagged_udemcebew/T_Rock_Jagged_udemcebew_NSVT_N",
        "o": "Rock_Jagged_udemcebew/T_Rock_Jagged_udemcebew_NSVT_ORHG"}
SOIL = {"d": "Trampled_Forest_Path_ub4jdihkw/T_Trampled_Forest_Path_ub4jdihkw_NSVT_D",
        "n": "Trampled_Forest_Path_ub4jdihkw/T_Trampled_Forest_Path_ub4jdihkw_NSVT_N",
        "o": "Trampled_Forest_Path_ub4jdihkw/T_Trampled_Forest_Path_ub4jdihkw_NSVT_ORHG"}
SURFACES = {"GrassD": "Ground_Grass_tb3nce2k/T_Ground_Grass_tb3nce_Desat_4K_NSVT_D",
            "GrassN": "Ground_Grass_tb3nce2k/T_Ground_Grass_NSVT_4K_N",
            "SandD": "Thai_Beach_Sand_tefgafrk/T_Thai_Beach_Sand_tefgafrk_2K_NSVT_D"}


def megascans(path):
    """Land.megascans: a set-relative path under MEGASCANS, or a full one."""
    if not isinstance(path, str):
        return None
    if path.startswith("/"):
        return path
    leaf = path.rsplit("/", 1)[-1]
    return f"{MEGASCANS}{path}.{leaf}"


def vec(v):
    """Land.cliffs' vec(): a table's first four, missing ones 0 (alpha 1)."""
    if not isinstance(v, list):
        return None
    v = list(v) + [None] * 4
    return [float(v[0] or 0), float(v[1] or 0), float(v[2] or 0), float(1 if v[3] is None else v[3])]


def light_scale(env):
    """lightScale() with no `mjolnir_light_scale` set."""
    post = (env or {}).get("post")
    if not isinstance(post, dict) or not post.get("manual_exposure"):
        return 1.0
    k = (env or {}).get("light_scale") or DEFAULT_LIGHT_SCALE
    return float(k) if isinstance(k, (int, float)) and k > 0 else 1.0


def lightmap_levels(env):
    """lightmapSun() with no terrain shadows' override."""
    v = ((env or {}).get("sun") or {}).get("lightmap_sun")
    if isinstance(v, list) and len(v) >= 2 and all(isinstance(x, (int, float)) for x in v[:2]):
        return [float(v[0]), float(v[1])]
    return None


def sea(level):
    """Land.seaHeight: the water decor's height, none for `sea = false`."""
    if (level.get("landscape") or {}).get("sea") is False:
        return None
    origin = (level.get("canvas") or {}).get("origin") or [0, 0, 0]
    for item in level.get("decor") or []:
        if isinstance(item, dict) and "_Water." in str(item.get("mesh", "")) and isinstance(item.get("pos"), list):
            return float(item["pos"][2] + origin[2])
    return None


def entries(level, groups, landscape_code):
    """One entry a cladding group (`groups`: the level's foliage groups,
    1-based `group`), or none when the cliffs take a shipped material (the
    snow maps: their rocks keep their meshes' own)."""
    spec = level.get("landscape") or {}
    cliff = spec.get("cliff")
    if not isinstance(cliff, dict) or isinstance(cliff.get("material"), str):
        return []
    pbr = spec.get("pbr") if isinstance(spec.get("pbr"), dict) else {}
    env = level.get("environment") or {}
    k, levels, sea_z = light_scale(env), lightmap_levels(env), sea(level)
    tess = cliff.get("tess") if isinstance(cliff.get("tess"), dict) else None
    clad_tess = bool(tess and tess.get("cladding"))
    parent = TRIAL + ("M_CE_CladTess.M_CE_CladTess" if clad_tess else "M_CE_CliffPBR.M_CE_CliffPBR")
    textures = {}
    for prefix, key in (("RockA", "rock_a"), ("RockB", "rock_b")):
        rock = cliff.get(key) if isinstance(cliff.get(key), dict) else ROCK
        for suffix in ("d", "n", "o"):
            textures[prefix + suffix.upper()] = megascans(rock.get(suffix))
    own = pbr.get("surfaces") if isinstance(pbr.get("surfaces"), dict) else {}
    for name, default in SURFACES.items():
        textures[name] = megascans(own.get(name) or default)
    soil = cliff.get("soil") if isinstance(cliff.get("soil"), dict) else SOIL
    for suffix in ("d", "n", "o"):
        textures["Soil" + suffix.upper()] = megascans(soil.get(suffix))
    edge = pbr.get("edge") if isinstance(pbr.get("edge"), dict) else None
    if edge and isinstance(edge.get("texture"), str):
        textures["Edge"] = edge["texture"]
    textures = {n: t for n, t in textures.items() if t}
    shared = {}

    def put(name, v):
        v = vec(v)
        if v is not None:
            shared[name] = v
    put("GrassTint", pbr.get("grass_tint"))
    for name, key in (("CliffTiles", "tiles"), ("CliffMix", "mix"), ("CliffLook", "look"), ("RockTint", "tint"),
                      ("CliffRough", "rough"), ("CliffFar", "far"), ("CliffCETint", "ce_tint")):
        put(name, cliff.get(key))
    f = cliff.get("fill")
    if isinstance(f, list):
        put("CliffFill", [f[0], f[1], f[2], (f[3] if len(f) > 3 and f[3] is not None else 0) * k])
    put("CliffFillDir", cliff.get("fill_dir"))
    if clad_tess:
        put("CliffDisp", [tess.get("clad_disp") if tess.get("clad_disp") is not None else (tess.get("disp") or 0.6),
                          tess.get("mip") or 400, 0, 0])
    if "Edge" in textures:
        put("EdgeRect", edge.get("rect"))
        put("EdgeRange", [edge["range"][0], edge["range"][1], 0, 0])
    d = cliff.get("drape") if isinstance(cliff.get("drape"), list) else [35, 35, 700]
    put("CliffDrape", [d[0], d[1], d[2], 0])
    put("CliffFoot", [35, 150, 0.45, 0])
    if sea_z is not None:
        put("LandSea", [sea_z, 0, cliff.get("wet") or 60, 1])
    out = []
    folder = f"/Game/MJOLNIR/CladMaterials/{landscape_code}"
    for g, group in enumerate(groups, 1):
        if not (isinstance(group, dict) and group.get("cliff") is True):
            continue
        tex = dict(textures)
        if isinstance(group.get("base"), str):
            tex["Base"] = group["base"]
        vectors = dict(shared)
        light = group.get("light") if isinstance(group.get("light"), list) else None
        if group.get("lm") and levels:
            gl = light or [-1, -1, -1]
            vectors["CladLight"] = vec([gl[0], gl[1], gl[2], 2])
            vectors["LandLMLevels"] = vec([levels[0], levels[1], 0, 0])
        elif light is not None:
            vectors["CladLight"] = vec(light)
        body = {"parent": parent, "textures": tex, "vectors": vectors}
        digest = hashlib.sha1(json.dumps(body, sort_keys=True).encode()).hexdigest()[:8]
        name = f"MI_{landscape_code}_Clad_{g}_{digest}"
        out.append(dict(body, group=g, package=f"{folder}/{name}", object=f"{folder}/{name}.{name}",
                        scalars={}, light_scale=k, levels=levels))
    return out


def standins(plan_entries):
    """The game's own textures the entries name (stand-ins in the editor)."""
    return sorted({t for e in plan_entries for t in e["textures"].values() if t.startswith(MEGASCANS)})


def loader_spec(plan_entries):
    """What the level file carries for the loader's check: by group, the
    material the baked rocks wear and what it was made with."""
    return {str(e["group"]): {"object": e["object"], "light_scale": e["light_scale"], "levels": e["levels"]}
            for e in plan_entries}

#!/usr/bin/env python3
"""Scatter the game's own plants and rocks over a converted CE map's ground.

    scatter_foliage.py <scene.gltf> <materials.spec.json> <out.json> --bin foliage.bin
        [--sea cm] [--offset x,y,z] [--lift cm] [--center x,y --radius r] [--seed 1] [--only rule,...]
        [--detail name=class ...] [--edge landscape.json] [--no-cladding]

CE draws its ground as detail maps: a blended shader_environment (Death
Island's beach) picks between two by its base map's alpha (TEXTURE_PASS_CODE
in build_ce_materials.py), so each point of the terrain is some share sand,
grass or other ground. RULES says what grows or lies on each: the game's
own Megascans meshes, at the densities, scales and heights above the sea
Campaign Evolved's B30 beach uses (its World Partition placements, read
with ue-asset's placements_csv example, 2026-10-11):

- grass: wild grass clumps where CE drew grass (B30 tints them grey for a
  dry beach; CE's grass is green).
- tufts: sea wheatgrass, ribbon grass and dune sedge along the edge of the
  grass, where it gives way to sand.
- rocky ground: Nordic beach rocky-ground slabs (3.5 m across, 24 cm high)
  in clusters on sand from just under the sea to 1.5 m above it.
- stones: B30's Uluwatu rocks, scaled small and set into the sand, among
  the rocky ground.
- lip grass: tall grass along every lip (with --edge, a landscape's edge
  map), breaking the cliff top's line.
- shells, pebbles, driftwood: B30's beach decorators (its landscape grass
  types): coral pieces in the band above the sea, small beach rocks in
  patches over all the sand, and the odd dry branch.

Nothing taller than knee height goes anywhere a player can walk: the
simulation knows only CE's collision, so a scattered rock is something to
walk and shoot through. B30's own big rocks stay out until they can be
given collision.

Each kept point is turned at random and scaled within its rule's range;
points are random but seeded, so every machine places the same. Clusters
come from a smooth noise over the ground. Points on slopes steeper than a
rule's limit are dropped, and so is anything below `--sea` that a rule
keeps above it; without `--sea`, the rules tied to the shore are left out.

Writes the instances to `--bin` (FOLIAGE_MAGIC: per group a count, then
x, y, z as float32 cm, yaw in 256ths of a turn and scale in hundredths, a
byte each, then the ground's normal x and y in 127ths, a signed byte each:
a rule with `align` lies along the slope, the rest stand upright at 0, 0) and out.json, the level file's `foliage` entry for
MJOLNIRLevelLoader: the file, and per group its mesh and optional tint,
material, cull distances, shadow and cull bands (the game's foliage
materials do not fade: the loader spreads a group's clumps over `bands`
meshes culled across its cull range, so the grass thins out with distance
rather than ending at one ring). Unreal cm: the glTF is CE in metres,
y up (Unreal x = x, y = z, z = y), plus the terrain mesh's `--offset`.
"""
import argparse
import json
import math
import os
import random
import struct
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from refine_water_gltf import read_accessor  # noqa: E402

# MJF2: the records carry the ground's normal (MJFG, without it, stood every
# rock level, and a 3.5 m slab on a slope floated on its downhill side).
# MJF3: and a colour, three bytes in 100ths (255 255 255: none), the CE light
# a cladding rock takes from the wall it sits on.
FOLIAGE_MAGIC = b"MJF3"
NO_COLOUR = (2.55, 2.55, 2.55)
MEGA = "/Game/Megascans/3D_Plants/"
MEGA3D = "/Game/Megascans/3D_Assets/"
ROCKS = "/Game/Env/Bio/Rock/Uluwatu/"
# CE detail maps by what they are (substrings of the bitmap names).
DETAIL_CLASSES = (("grass", ("detail_grass",)), ("sand", ("detail_sand",)))
# A natural surface without a grass detail can paint its grass into the base
# map: there, flat ground whose base colour is green (green over red and
# blue by GREEN_MARGIN, gamma) counts as grass. Only shaders whose detail
# maps are one of NATURAL_DETAILS, so green metal stays bare.
NATURAL_DETAILS = ("cliff", "rock", "ground", "dirt", "sand")
GREEN_MARGIN = (0.03, 0.10)
# The grass and tufts in the original's deeper green (matched side by side,
# 2026-10-11; B30's own tint is a dry grey).
GRASS_TINT = [0.12, 0.3, 0.08]
# Grass, tufts and lip grass thin out from 100 m to 300 m (80 to 220 m for
# tufts): at 40 to 120 m whole fields went bare a short way off (Blood
# Gulch, 2026-10-12); about 1 ms more a frame there.
TUFT_TINT = [0.3, 0.42, 0.18]
# The grass in patches of three greens (`tints`, by a noise of `tint_cell`
# m): lusher, the original's, sun-dried. One green over a whole field read
# as a carpet (2026-10-12).
GRASS_TINTS = [[0.06, 0.24, 0.05], GRASS_TINT, [0.3, 0.34, 0.1]]
BIO = "/Game/Env/Bio/Grass/"
# Banks grow grass whatever CE painted them (`banks`: from, all by, degrees,
# density there against flat grass: half, about 1.2 ms of Blood Gulch's 2.5):
# the ground masters draw a bank green from about 23 degrees, all green by
# 37 (LAND_PBR_CODE's Slope), and the grass stopped at its foot, the bank
# bare (Blood Gulch, 2026-10-12).
BANKS = [21.0, 34.0, 0.5]
# B30's tall grass, sedge and rushes ("Color Tint" multiplies their tan).
TALL_TINT = [0.45, 0.8, 0.3]

# Each rule: the ground class it grows on and the share of it it needs
# (`share`: [low, high], thinned linearly between), clumps a square metre,
# slope limit (degrees), height above the sea (m), cluster noise (cell
# size m and threshold: None for none), meshes (with their own scale ranges
# and how far to sink them, cm a unit of scale), and the loader settings.
# `patch` [cell m, low, high]: every scale times low..high by a noise of that
# cell, so the grass stands short in some patches and tall in others;
# `tints` and `tint_cell`: a group a tint, chosen by patch; `tint_param` the
# material parameter the loader tints (B30's own MM_Foliage_MET grasses take
# "Color Tint", the Megascans ones "Color Overlay").
# B30's wet beach rocks: Uluwatu in their Waterline materials.
WATERLINE = {ROCKS + f"Rock_Uluwatu_Med_{v}/SM_Rock_Uluwatu_Med_{v}":
             ROCKS + f"Rock_Uluwatu_Med_{v}/Materials/MI_Rock_Uluwatu_Med_{v}_Waterline" for v in "ABC"}

RULES = [
    {"name": "grass", "on": "grass", "share": [0.3, 0.7], "density": 5.0, "slope": 50, "above": [0.3, None],
     "meshes": [(MEGA + "Wild_Grass_vdilbaiia/S_Wild_Grass_vdilbaiia_Var11_lod0", 0.9, 1.5, 0),
                (MEGA + "Wild_Grass_vdilbaiia/S_Wild_Grass_vdilbaiia_Var12_lod0", 0.9, 1.5, 0),
                (MEGA + "Wild_Grass_vdilbaiia/S_Wild_Grass_vdilbaiia_Var4_lod0", 0.9, 1.5, 0),
                (MEGA + "Wild_Grass_vczndjqja/S_Wild_Grass_vczndjqja_Var12_lod0", 0.9, 1.5, 0),
                (MEGA + "Wild_Grass_vczndjqja/S_Wild_Grass_vczndjqja_Var19_lod0", 0.9, 1.5, 0)],
     "patch": [9.0, 0.45, 1.45], "tints": GRASS_TINTS, "tint_cell": 16.0, "banks": BANKS,
     "tint": GRASS_TINT, "cull": [10000, 30000], "bands": 8},
    # B30's own short grass and ground cover between the clumps, in patches.
    {"name": "short grass", "on": "grass", "share": [0.3, 0.7], "density": 1.2, "slope": 45, "above": [0.3, None],
     "banks": BANKS,
     "cluster": [6.0, 0.4],
     # (Not B30's AcorusCalamus: on our maps it drew dark brown spikes.)
     "meshes": [(BIO + "GroundcoverClump/Grass_GroundcoverClump_A/SM_Grass_GroundcoverClump_A", 0.7, 1.3, 0)],
     "cull": [5000, 12000], "bands": 3},
    # Stands of tall grass, sedge and rushes (55 to 100 cm), clustered; 0.2
    # a square metre (0.5 crowded Death Island's slopes, 2026-10-15).
    {"name": "tall grass", "on": "grass", "share": [0.3, 0.7], "density": 0.2, "slope": 35, "above": [0.6, None],
     "cluster": [10.0, 0.5],
     "meshes": [("/Game/Megascans/3D_Plants/Tall_Grass_rbeki/SM_Tall_Grass_rbeki_01", 0.9, 1.3, 0),
                (BIO + "Sedges/Grass_Sedges_A/SM_Grass_Sedges_A_Leaves_A", 0.8, 1.2, 0),
                (BIO + "Sedges/Grass_Sedges_A/SM_Grass_Sedges_A_Leaves_B", 0.8, 1.2, 0),
                (BIO + "Sedges/Grass_Sedges_A/SM_Grass_Sedges_A_Leaves_C", 0.8, 1.2, 0),
                (BIO + "Sedges/Grass_Sedges_A/SM_Grass_Sedges_A_Leaves_E", 0.8, 1.2, 0),
                (BIO + "Sedges/Grass_Sedges_A/SM_Grass_Sedges_A_Flowers_A", 0.8, 1.1, 0),
                (BIO + "Sedges/Grass_Sedges_A/SM_Grass_Sedges_A_Flowers_C", 0.8, 1.1, 0),
                (BIO + "Rushes/Grass_Rushes_A/SM_Grass_Rushes_A", 0.8, 1.2, 0),
                (BIO + "Rushes/Grass_Rushes_B/SM_Grass_Rushes_B", 0.8, 1.2, 0)],
     # B30's own colour is a dry tan; multiplied green (and the light through
     # the blades with it) they stand with the CE grass around them.
     "tint": TALL_TINT, "tint_param": "Color Tint", "params": {"Subsurface Color Tint": [0.6, 1.0, 0.5]},
     "cull": [8000, 20000], "bands": 5},
    # Low leafy weeds and clover here and there.
    {"name": "weeds", "on": "grass", "share": [0.3, 0.7], "density": 0.4, "slope": 35, "above": [0.3, None],
     "cluster": [5.0, 0.68],
     "meshes": [("/Game/Megascans/3D_Plants/Leafy_Dandelions_qmbrl/SM_Leafy_Dandelions_qmbrl_01", 0.8, 1.3, 0),
                ("/Game/Megascans/3D_Plants/Leafy_Dandelions_qmbrl/SM_Leafy_Dandelions_qmbrl_03", 0.8, 1.3, 0),
                ("/Game/Megascans/3D_Plants/Clovers_rbdjz/SM_Clovers_rbdjz_01", 0.8, 1.2, 0),
                ("/Game/Megascans/3D_Plants/Clovers_rbdjz/SM_Clovers_rbdjz_02", 0.8, 1.2, 0),
                ("/Game/Megascans/3D_Plants/Leafy_Weeds_rbcuh/SM_Leafy_Weeds_rbcuh_01", 0.8, 1.3, 0)],
     "cull": [3000, 6000], "bands": 2, "shadow": False},
    {"name": "tufts", "on": "grass", "share": [0.12, 0.45], "density": 0.8, "slope": 40, "above": [0.6, None],
     "falloff": True,
     "meshes": [(MEGA + "Sea_Wheatgrass_ui2oagjia/S_Sea_Wheatgrass_ui2oagjia_0_Var9_lod0", 0.64, 0.96, 0),
                (MEGA + "Sea_Wheatgrass_ui2oagjia/S_Sea_Wheatgrass_ui2oagjia_Var1_lod0", 0.42, 0.58, 0),
                (MEGA + "Ribbon_Grass_tbdpec3r/S_Ribbon_Grass_tbdpec3r_Var2_lod0", 0.53, 0.77, 0),
                (MEGA + "Ribbon_Grass_tbdpec3r/S_Ribbon_Grass_tbdpec3r_Var3_lod0", 0.42, 0.58, 0),
                (MEGA + "Dune_Sword-sedge_ueyoebmia/S_Dune_Sword-sedge_ueyoebmia_0_Var6_lod0", 0.62, 0.79, 0),
                (MEGA + "Dune_Sword-sedge_ueyoebmia/S_Dune_Sword-sedge_ueyoebmia_0_Var7_lod0", 0.62, 0.79, 0)],
     "tint": TUFT_TINT, "cull": [8000, 22000], "bands": 6},
    # B30's own (its placements, 2026-10-20): slabs at scale 0.5 to 0.85
    # (median 0.64), mostly in twos, the groups about 13 m apart, each slab
    # with an Uluwatu stone at its centre (`centre`). Ours were bigger (0.8)
    # in groups of four to nine, 17 m apart, and stood on CE's coarse ground
    # triangles: on ground falling away their edges stood off the sand
    # (Death Island, 2026-10-19). `seat` [half-size cm, most drop cm, both
    # at scale 1]: the slab goes down to where its rim meets the ground, or
    # is left out where the ground falls further.
    {"name": "rocky ground", "align": True, "on": "sand", "share": [0.5, 0.8], "density": 0.03, "slope": 15, "above": [-0.4, 1.5],
     "cluster": [10.0, 0.62], "seat": [150.0, 16.0],
     "meshes": [("/Game/Megascans/3D_Assets/Nordic_Beach_Rocky_Ground_ve3qdhmqx/S_Nordic_Beach_Rocky_Ground_Uluwata_B",
                 0.5, 0.85, 8)],
     "centre": {"name": "rocky ground stones",
                "meshes": [(ROCKS + "Rock_Uluwatu_Med_A/SM_Rock_Uluwatu_Med_A", 0.15, 0.35, 40, 6),
                           (ROCKS + "Rock_Uluwatu_Med_C/SM_Rock_Uluwatu_Med_C", 0.12, 0.25, 80, 4),
                           (ROCKS + "Rock_Uluwatu_Med_B/SM_Rock_Uluwatu_Med_B", 0.10, 0.20, 60, 1)],
                "materials": WATERLINE, "cull": [6000, 11000], "shadow": True},
     "cull": [8000, 14000], "shadow": True},
    {"name": "stones", "align": True, "on": "sand", "share": [0.5, 0.8], "density": 0.15, "slope": 30, "above": [-0.5, 2.5],
     "cluster": [14.0, 0.55],
     "meshes": [(ROCKS + "Rock_Uluwatu_Med_A/SM_Rock_Uluwatu_Med_A", 0.06, 0.25, 40),
                (ROCKS + "Rock_Uluwatu_Med_B/SM_Rock_Uluwatu_Med_B", 0.04, 0.14, 60),
                (ROCKS + "Rock_Uluwatu_Med_C/SM_Rock_Uluwatu_Med_C", 0.04, 0.10, 80)],
     "materials": WATERLINE,
     "cull": [5000, 9000], "shadow": True},
    # B30's big rocks out in the sea (about 450 of its 1500 Uluwatu rocks
    # of scale 1 or more stand 0.75 m or more under the beach line; the
    # biggest, scale 2 and up, at 1.6 m under it), wet in the Waterline
    # materials. Upright, set into the sea bed; they collide
    # (b30_collision.py FOLIAGE_RULES) where a player wades.
    {"name": "sea rocks", "optional": True, "group": "sea", "on": "any", "share": [0.0, 0.0], "density": 0.006, "slope": 25, "above": [-4.0, -0.3],
     "cluster": [40.0, 0.5], "shore": [3.0, 60.0],
     "meshes": [(ROCKS + "Rock_Uluwatu_Med_A/SM_Rock_Uluwatu_Med_A", 0.9, 2.2, 40),
                (ROCKS + "Rock_Uluwatu_Med_B/SM_Rock_Uluwatu_Med_B", 1.0, 2.6, 60),
                (ROCKS + "Rock_Uluwatu_Med_C/SM_Rock_Uluwatu_Med_C", 1.0, 2.4, 80)],
     "materials": WATERLINE, "cull": [25000, 45000], "shadow": True},
    # Grass along every lip (--edge: the landscape's edge map), dense and
    # tall, so blades break the edge's line where the cliff's turf hem
    # (M_CE_CliffPBR) runs down from it: B30's cliff tops are fringed so.
    {"name": "lip grass", "edge": "lip", "on": "any", "share": [0.0, 0.0], "density": 7.0, "slope": 65,
     "above": [0.5, None],
     "meshes": [(MEGA + "Wild_Grass_vdilbaiia/S_Wild_Grass_vdilbaiia_Var11_lod0", 1.1, 1.7, 0),
                (MEGA + "Wild_Grass_vdilbaiia/S_Wild_Grass_vdilbaiia_Var12_lod0", 1.1, 1.7, 0),
                (MEGA + "Sea_Wheatgrass_ui2oagjia/S_Sea_Wheatgrass_ui2oagjia_Var1_lod0", 0.6, 0.9, 0),
                (MEGA + "Ribbon_Grass_tbdpec3r/S_Ribbon_Grass_tbdpec3r_Var2_lod0", 0.6, 0.85, 0)],
     "tint": GRASS_TINT, "cull": [10000, 25000], "bands": 6},
    # B30's beach decorators (its landscape grass types LG_B30_rippledsand_assets
    # and LG_B30_stone_assets): shell-sized coral and beach rocks, 10 to 35 cm,
    # and dry branches half a metre long, all lying in the sand.
    {"name": "shells", "align": True, "on": "sand", "share": [0.5, 0.8], "density": 0.5, "slope": 25, "above": [-0.3, 3.0],
     "cluster": [9.0, 0.45],
     "meshes": [(MEGA3D + "Thai_Beach_Corals_Pack_ufzkbcjfa/S_Thai_Beach_Corals_Pack_ufzkbcjfa_high_Var2", 0.7, 1.2, 4),
                (MEGA3D + "Thai_Beach_Corals_Pack_ufzkbcjfa/S_Thai_Beach_Corals_Pack_ufzkbcjfa_high_Var3", 0.7, 1.2, 2),
                (MEGA3D + "Thai_Beach_Corals_Pack_ufzkbcjfa/S_Thai_Beach_Corals_Pack_ufzkbcjfa_high_Var4", 0.7, 1.2, 2),
                (MEGA3D + "Thai_Beach_Corals_Pack_ufzkbcjfa/S_Thai_Beach_Corals_Pack_ufzkbcjfa_high_Var5", 0.7, 1.2, 1),
                (MEGA3D + "Coral_Stone_wfcmegzr/S_Coral_Stone_wfcmegzr_lod0_Var1", 0.8, 1.4, 0)],
     "cull": [2500, 4000], "shadow": True},
    {"name": "pebbles", "align": True, "on": "sand", "share": [0.4, 0.8], "density": 0.8, "slope": 30, "above": [-0.5, None],
     "cluster": [5.0, 0.64],
     "meshes": [(MEGA3D + "Small_Beach_Rock_wfbscavr/S_Small_Beach_Rock_wfbscavr_lod0_Var1", 0.6, 1.6, 1),
                (MEGA3D + "Small_Beach_Rock_wd5nfa1/S_Small_Beach_Rock_wd5nfa1_high", 0.6, 1.4, 2),
                (MEGA3D + "Small_Beach_Rock_webhcal/S_Small_Beach_Rock_webhcal_high_Var1", 0.6, 1.6, 1),
                (MEGA3D + "Small_Beach_Rock_wd3nech/S_Small_Beach_Rock_wd3nech_lod0_Var1", 0.6, 1.6, 1),
                (MEGA3D + "Small_Beach_Rock_wd2ocdo/S_Small_Beach_Rock_wd2ocdo_high", 0.6, 1.4, 2),
                (MEGA3D + "Small_Beach_Rock_wd5mfgo/S_Small_Beach_Rock_wd5mfgo_high_Var1", 0.6, 1.4, 1),
                (MEGA3D + "Small_Beach_Rock_wfcpeggr/S_Small_Beach_Rock_wfcpeggr_lod0_Var1", 0.8, 2.0, 1)],
     "cull": [3000, 5000], "shadow": True},
    {"name": "driftwood", "align": True, "on": "sand", "share": [0.5, 0.8], "density": 0.025, "slope": 20, "above": [0.3, None],
     "meshes": [(MEGA3D + "DryBranches/SM_DryBranches_01", 1.0, 2.2, 0),
                (MEGA3D + "DryBranches/SM_DryBranches_02", 1.0, 2.2, 0)],
     "cull": [4000, 6500], "shadow": True},
]


def object_path(package):
    return package + "." + package.rsplit("/", 1)[-1]


# --detail name=class pairs: maps whose detail bitmaps say nothing of what
# they are (a protected map's protected_bitm_nNNNN) name them.
EXTRA_DETAILS = []


def detail_class(path):
    lower = path.lower()
    for cls, names in EXTRA_DETAILS + list(DETAIL_CLASSES):
        if any(n in lower for n in names):
            return cls
    return None


def ground_slots(spec):
    """{glTF material name (lower case): (base texture file, primary class,
    secondary class, shader type)} for the shaders whose detail maps are
    sand or grass, or natural ground ("green": its grass in the base)."""
    files = {t["name"]: t["file"] for t in spec["textures"]}
    out = {}
    for s in spec["slots"]:
        m = s["material"]
        tex = m.get("textures") or {}
        base = tex.get("Base", "").rsplit(".", 1)[-1]
        if base not in files or "Environment" not in m.get("parent", ""):
            continue
        primary, secondary = detail_class(tex.get("Primary", "")), detail_class(tex.get("Secondary", ""))
        if not (primary or secondary):
            if not any(n in v.lower() for v in tex.values() for n in NATURAL_DETAILS):
                continue
            primary = "green"
        out[s["pattern"].rstrip("$")] = (files[base], primary, secondary if "Secondary" in tex else None,
                                         (m.get("scalars") or {}).get("Type", 0))
    return out


def class_shares(rgba, primary, secondary, shader_type):
    """{class: share 0..1} at each point: a blended shader picks the primary
    detail where the base alpha is 1; a "green" surface is grass by how
    green its base colour is."""
    n = len(rgba)
    if primary == "green":
        g = rgba[:, 1] - np.maximum(rgba[:, 0], rgba[:, 2])
        return {"grass": np.clip((g - GREEN_MARGIN[0]) / (GREEN_MARGIN[1] - GREEN_MARGIN[0]), 0.0, 1.0)}
    pick = rgba[:, 3] if (shader_type > 0.5 and secondary) else np.ones(n)
    shares = {}
    for cls, w in ((primary, pick), (secondary, 1.0 - pick)):
        if cls:
            shares[cls] = shares.get(cls, np.zeros(n)) + w
    return shares


def sample_rgba(img, uv):
    """The image's RGBA (0..1, gamma) at UVs (wrapping), bilinear."""
    h, w, _ = img.shape
    x = (uv[:, 0] % 1.0) * w - 0.5
    y = (uv[:, 1] % 1.0) * h - 0.5
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    tx, ty = (x - x0)[:, None], (y - y0)[:, None]
    g = lambda yy, xx: img[yy % h, xx % w]
    return (g(y0, x0) * (1 - tx) * (1 - ty) + g(y0, x0 + 1) * tx * (1 - ty)
            + g(y0 + 1, x0) * (1 - tx) * ty + g(y0 + 1, x0 + 1) * tx * ty)


def value_noise(x, y, cell, seed):
    """Smooth value noise in 0..1 over world x, y (cm), cells `cell` m."""
    fx, fy = x / (cell * 100.0), y / (cell * 100.0)
    ix, iy = math.floor(fx), math.floor(fy)
    tx, ty = fx - ix, fy - iy
    tx, ty = tx * tx * (3 - 2 * tx), ty * ty * (3 - 2 * ty)

    def h(i, j):
        return random.Random(hash((i, j, seed)) & 0xFFFFFFFF).random()

    return (h(ix, iy) * (1 - tx) + h(ix + 1, iy) * tx) * (1 - ty) + (h(ix, iy + 1) * (1 - tx) + h(ix + 1, iy + 1) * tx) * ty


def scenery_footprints(gltf, off, staging=None, skip_rocks=False, snow=False):
    """The map's placed scenery (halo2ue's staging/placement.json beside the
    scene) as (x, y, radius, z, reach) cm: the simulation spawns it (B30's
    boulders, trees), so the scene knows nothing of it, and grass grew up
    through the boulders (Blood Gulch, 2026-10-12). The radius is 80% of the
    model's furthest reach across, so the grass still meets its foot; `reach`
    is its furthest reach any way (it may stand turned), which keeps the
    clearing to ground at its own height: a gigantic boulder in Death
    Island's cave left the hilltop 38 m over it bare (2026-10-15).

    `skip_rocks`: none for the boulders scenery_swap.py replaces; the swap
    stage clears the grass inside each B30 rock's own hull instead
    (rock_foliage.py). A circle round a long boulder left bands of bare
    ground up to 2 m wide along its sides (Danger Canyon, 2026-10-19)."""
    from scenery_swap import swap_rule
    staging = staging or os.path.join(os.path.dirname(os.path.abspath(gltf)), "staging")
    path = os.path.join(staging, "placement.json")
    if not os.path.exists(path):
        return []
    placement = json.load(open(path, encoding="utf-8"))
    unit = placement.get("world_unit_meters", 3.048) * 100.0
    reach = {}
    out = []
    for e in placement.get("entries", []):
        if e.get("kind") != "scenery" or not e.get("model"):
            continue
        if skip_rocks and (swap_rule(e, staging, snow) or ("",))[0] in ("rock", "bigrock"):
            continue
        model = os.path.join(staging, e["model"])
        if model not in reach:
            r = tall = 0.0
            try:
                doc = json.load(open(model, encoding="utf-8"))
                if "tree" in e.get("asset", "").lower():
                    # A tree by its trunk's foot (its points within 1.5 m of
                    # its lowest), not its boughs: by the boughs' reach
                    # Timberland's pines stood in bare circles 11 m across
                    # (2026-10-14).
                    data = open(os.path.join(os.path.dirname(model), doc["buffers"][0]["uri"]), "rb").read()
                    pts = np.concatenate([read_accessor(doc, data, prim["attributes"]["POSITION"])
                                          for mesh in doc["meshes"] for prim in mesh["primitives"]])
                    foot = pts[pts[:, 1] < pts[:, 1].min() + 1.5]
                    r = float(np.hypot(foot[:, 0], foot[:, 2]).max())
                    tall = float(np.abs(pts).max())
                else:
                    for mesh in doc["meshes"]:
                        for prim in mesh["primitives"]:
                            acc = doc["accessors"][prim["attributes"]["POSITION"]]
                            ax = max(abs(acc["min"][0]), abs(acc["max"][0]))
                            az = max(abs(acc["min"][2]), abs(acc["max"][2]))
                            r = max(r, math.hypot(ax, az))
                            tall = max(tall, max(abs(v) for v in acc["min"] + acc["max"]))
            except (OSError, KeyError, ValueError, IndexError):
                r = tall = 0.0
            reach[model] = (r * 100.0 * 0.8, tall * 100.0)
        x, y, z = e["pos"]
        r, tall = reach[model]
        out.append((x * unit + off[0], -y * unit + off[1], r, z * unit + off[2], tall))
    return out


def swapped_surface(staging, snow=False):
    """A test for the scene's materials scenery_swap.py hides (its CE
    boulders, trees and plants, drawn in the scene mesh): nothing grows on
    them. Grass on a CE boulder's top floated over the smaller B30 rock that
    stands there instead once the circle no longer cleared it (Danger
    Canyon, 2026-10-19). Its own rule: the slot names it hides by."""
    from scenery_swap import model_shaders, swap_rule
    path = os.path.join(staging, "placement.json")
    tokens, shaders = set(), set()
    if os.path.exists(path):
        for e in json.load(open(path, encoding="utf-8")).get("entries", []):
            if swap_rule(e, staging, snow):
                tokens.add(e["asset"].lower().rsplit("\\", 1)[0].replace("\\", "_").replace(" ", "_") + "_shaders_")
                shaders.update(sh + "__" for sh in model_shaders(os.path.join(staging, e["model"])))
    prefixes = tuple(tokens | shaders)
    return lambda name: bool(prefixes) and name.startswith(prefixes)


SCENERY_CELL = 1000.0


def scenery_grid(scenery):
    """The footprints by 10 m cell, each in every cell its circle reaches."""
    grid = {}
    for sx, sy, r, sz, tall in scenery:
        if r <= 0.0:
            continue
        for i in range(int((sx - r) // SCENERY_CELL), int((sx + r) // SCENERY_CELL) + 1):
            for j in range(int((sy - r) // SCENERY_CELL), int((sy + r) // SCENERY_CELL) + 1):
                grid.setdefault((i, j), []).append((sx, sy, r, sz, tall))
    return grid


# Ground this far (cm) past a scenery object's furthest reach, up or down,
# is still its own: it may sit sunk in the ground.
SCENERY_DEPTH_SLACK = 200.0


def under_scenery(grid, x, y, z):
    for sx, sy, r, sz, tall in grid.get((int(x // SCENERY_CELL), int(y // SCENERY_CELL)), ()):
        if (x - sx) ** 2 + (y - sy) ** 2 < r * r and abs(z - sz) < tall + SCENERY_DEPTH_SLACK:
            return True
    return False


def keep_share(share, lo, hi, falloff):
    """How likely a point is kept for its share of the rule's class: up from
    `lo` to all at `hi`, or (`falloff`, an edge) up to `lo` and back down by
    `hi`."""
    if falloff:
        mid = (lo + hi) / 2
        return max(0.0, 1.0 - abs(share - mid) / ((hi - lo) / 2))
    return min(1.0, max(0.0, (share - lo) / max(hi - lo, 1e-6)))


# Cladding: B30's own cliff rocks (its PCG cliffs are built of them) set into
# the CE cliff walls. The loader spawns them as mesh actors, not instances
# (this game's renderer drew our materials black on instanced meshes), one
# material a group of rocks of like CE light. Set into the walls, sticking
# out 25 to 110 cm (at 15 to 70 the walls still read flat from afar), so the
# flat CE faces get a rock's silhouette, ledges and shadows. They are drawn
# in the cliffs' own world-space rock (M_CE_CliffPBR), so wall and rock read
# as one surface. Nothing sticks out far enough to matter to the simulation,
# which knows only CE's collision. Each rock: (mesh, scale range, its depth
# along the normal at scale 1 in cm, the share of rocks); density a square
# metre of wall; walls steeper than `steep` (normal z); `clear` cm kept
# from built surfaces (ladders, walkways: rocks had walled them off).
CLADDING = {
    "meshes": [(ROCKS + "Rock_Uluwatu_Med_B/SM_Rock_Uluwatu_Med_B", 1.0, 2.4, 140, 0.3),
               (ROCKS + "Rock_Uluwatu_Med_C/SM_Rock_Uluwatu_Med_C", 1.0, 2.4, 160, 0.3),
               (ROCKS + "Rock_Uluwatu_Cliff_B/SM_Rock_Uluwatu_Cliff_B", 0.06, 0.16, 2950, 0.4)],
    "density": 0.1, "steep": 0.8, "protrude": [25, 110], "above": 0.3, "lights": 6, "clear": 150,
}


# A snow map (`--biome snow`, Ice Fields): B40's dressing, not B30's. No
# grass, tufts or shore: its ground reads as "green" to the classes above
# (CE's snow detail is a natural one), and B30's grass covered it. Snowy
# small rocks over all natural ground instead, at B40's own scales (its
# Small_*_Snow scatter, 0.3 to 2.5), and the cliffs clad with its glacial
# rocks (snow-topped by their own materials; depths about 0.4 of the width,
# as the Uluwatu ones; Lrg_B the big cliff piece, as Uluwatu's Cliff_B).
GLACIAL = "/Game/Env/Bio/Rock/Glacial/"
SNOW_RULES = [
    {"name": "snow stones", "align": True, "on": "any", "share": [0.0, 0.0], "density": 0.12, "slope": 35,
     "support": 20.0,
     "above": [None, None], "cluster": [10.0, 0.55],
     # Half buried, as B40 lays them (sunk 1 to 2 cm a unit of scale they
     # stood on the snow, their shadows showing the gap, 2026-10-13).
     "meshes": [(MEGA3D + "Small_Beach_Rock_webhcal/S_Small_Beach_Rock_webhcal_high_Var1_Snow", 0.4, 1.6, 8),
                (MEGA3D + "Small_Beach_Rock_wd2ocdo/S_Small_Beach_Rock_wd2ocdo_high_Snow", 0.4, 1.4, 8),
                (MEGA3D + "SmallStonesPack/SM_SmallStonesPack__Snow", 0.5, 1.5, 4),
                (MEGA3D + "Small_Granite_Rock_wgyxag2/S_Small_Granite_Rock_wgyxag2_lod0_Var1_Snow", 0.4, 1.4, 8)],
     "cull": [4000, 7000], "shadow": True},
    # Where walls meet the ground (the edge map's feet): B40's snowy scree
    # and rubble banked along them, as its own walls stand.
    {"name": "foot rubble", "wall": "foot", "align": True, "on": "any", "share": [0.0, 0.0], "density": 1.0,
     "support": 25.0,
     "slope": 40, "above": [None, None], "cluster": [6.0, 0.35],
     "meshes": [("/Game/Env/Bio/Rock/Scree/Scree_Rock_A/SM_Scree_Rock_01", 0.8, 2.6, 6),
                ("/Game/Env/Bio/Rock/Scree/Scree_Rock_B/SM_Scree_Rock_02", 0.8, 2.6, 5),
                ("/Game/Env/Bio/Rock/Scree/Scree_Rock_C/SM_Scree_Rock_03", 1.0, 3.0, 4),
                (MEGA3D + "Small_Beach_Rock_webhcal/S_Small_Beach_Rock_webhcal_high_Var1_Snow", 1.0, 2.5, 8),
                (MEGA3D + "Small_Granite_Rock_wgyxag2/S_Small_Granite_Rock_wgyxag2_lod0_Var1_Snow", 1.0, 2.2, 8)],
     "cull": [3500, 6000], "shadow": True},
    # (B40's snow drifts along lips were tried and left out: on CE's narrow
    # walkways they stood in the path, mounds a player walks through.)
]
SNOW_CLADDING = {
    "meshes": [(GLACIAL + "Rock_Glacial_Med_B/SM_Rock_Glacial_Med_B", 0.8, 1.8, 180, 0.3),
               (GLACIAL + "Rock_Glacial_Med_C/SM_Rock_Glacial_Med_C", 0.8, 1.8, 215, 0.3),
               (GLACIAL + "Rock_Glacial_Lrg_B/SM_Rock_Glacial_Lrg_B", 0.4, 1.0, 640, 0.4)],
    "density": 0.1, "steep": 0.8, "protrude": [25, 110], "above": 0.3, "lights": 6, "clear": 150,
}


# Cliff shaders by name (--cliff-shaders): Sidewinder's share its ground's
# snow detail map.
CLIFF_SHADERS = []
# A cliff slot in ground_slots' terms: grass by its faces' tilt.
TURF = "turf"
# M_CE_CliffPBR's turf on faces that look up: from normal z 0.7 to all of it
# at 0.88.
TURF_Z = (0.7, 0.88)


# No grass under a roof (COVER_OVER cm or more over it, by CoverGrid): the
# game's grass takes only Unreal's light, and in Death Island's tunnel it
# stood black (2026-10-15). Not by CE's lightmap: thinned by that, it left
# a bare circle under every tree (CE baked their shadows; the swapped trees
# cast their own) and bare dusk-side slopes, a quarter of the grass.
COVER_OVER = 150.0
# ...and no more than COVER_UNDER cm over it: a tunnel's, a room's or a
# bridge's. Higher, it is an overhang the sky reaches under from the side:
# a Forerunner structure 24 m over Yoyorast's slope left it a bare lawn, and
# Death Island's leaning cliffs (8 to 40 m up) bared their feet (2026-10-16).
COVER_UNDER = 800.0


class ShoreGrid:
    """Distance (cm) from land, by SHORE_CELL cell: a cell is land when any
    walkable ground in it stands over the sea (WalkGrid's heights), and the
    rest count their 8-way steps out from the nearest land cell. A rule's
    `shore` [near, far] m keeps it within that band of the shoreline: Death
    Island's sea bed lies 1.5 to 2.6 m under the sea for kilometres out, so a
    depth alone put its sea rocks over all of it (2026-10-20)."""
    def __init__(self, walk, sea, cell=500.0):
        self.cell = cell
        land = set()
        for (ix, iy), zs in walk.cells.items():
            if max(zs) > sea:
                land.add((math.floor(ix * walk.cell / cell), math.floor(iy * walk.cell / cell)))
        self.dist = {c: 0 for c in land}
        frontier, steps = list(land), 0
        # Out to 200 m: no rule asks further.
        while frontier and steps * cell < 20000.0:
            steps += 1
            nxt = []
            for ix, iy in frontier:
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        c = (ix + dx, iy + dy)
                        if c not in self.dist:
                            self.dist[c] = steps
                            nxt.append(c)
            frontier = nxt

    def within(self, x, y, near, far):
        d = self.dist.get((math.floor(x / self.cell), math.floor(y / self.cell)))
        return d is not None and near * 100.0 <= d * self.cell <= far * 100.0


def turf_share(nz):
    """The cliff master's turf share on a face with normal z `nz`."""
    t = min(1.0, max(0.0, (nz - TURF_Z[0]) / (TURF_Z[1] - TURF_Z[0])))
    return t * t * (3.0 - 2.0 * t)


def cliff_slots(spec):
    """{glTF material name: (base file, lightmap file, base object path)} for
    the CE cliff shaders (a cliff detail map and a lightmap page)."""
    files = {t["name"]: t["file"] for t in spec["textures"]}
    out = {}
    for s in spec["slots"]:
        tex = s["material"].get("textures") or {}
        leaf = lambda k: tex.get(k, "").rsplit(".", 1)[-1]
        named = any(x in s["pattern"].lower() for x in CLIFF_SHADERS)
        if ("detail_cliff" in tex.get("Primary", "") or named) and leaf("Base") in files and leaf("Lightmap") in files \
                and "object_lighting" not in tex.get("Lightmap", ""):
            out[s["pattern"].rstrip("$")] = (files[leaf("Base")], files[leaf("Lightmap")], tex["Base"])
    return out


# What a player can stand on (normal z), and the space a player takes over
# it: a standing cylinder (radius, height cm) on every walkable spot.
WALK_Z = 0.6
PLAYER_R = 45.0
PLAYER_H = 220.0
# A rock that would stand in that space is tried again pressed into its
# wall (protruding these cm) before it is left out: the walls beside
# walkways keep their relief (Ice Fields' ramp, bare once its rocks went).
FLUSH = [8.0, 20.0]


def built_points(doc, data, spec, off, step=100.0):
    """Points (Unreal cm, n x 3) over every surface that is not natural ground
    or cliff: CE's ladders, walkways, bases, bridges; a cladding rock keeps
    clear of them. Every triangle sampled about every `step` cm."""
    natural = set(cliff_slots(spec)) | set(ground_slots(spec))
    skip = ("water", "sky", "fog", "wave", "flare", "light")
    pts = []
    for mesh in doc["meshes"]:
        for prim in mesh["primitives"]:
            name = doc["materials"][prim["material"]]["name"].lower()
            key = next((k for k in natural if name.startswith(k.lower())), None)
            if key or any(w in name for w in skip):
                continue
            pos = read_accessor(doc, data, prim["attributes"]["POSITION"]).astype(np.float64)
            pos = np.stack([pos[:, 0] * 100.0, pos[:, 2] * 100.0, pos[:, 1] * 100.0], 1) + np.array(off)
            idx = read_accessor(doc, data, prim["indices"]).reshape(-1, 3)
            for i0, i1, i2 in idx:
                p0, p1, p2 = pos[i0], pos[i1], pos[i2]
                edge = max(np.linalg.norm(p1 - p0), np.linalg.norm(p2 - p1), np.linalg.norm(p0 - p2))
                k = max(1, int(edge / step))
                for u in range(k + 1):
                    for v in range(k + 1 - u):
                        w0, w1 = u / k, v / k
                        pts.append(w0 * p0 + w1 * p1 + (1 - w0 - w1) * p2)
    return np.array(pts) if pts else np.zeros((0, 3))


class CoverGrid:
    """The surfaces facing down (a roof, an overhang, a tunnel's ceiling:
    normal under -0.2, any shader but water and sky, and not CE's scenery
    models, `__lmobj`: its trees' canopies took the grass from a circle
    under each) over each `cell` cm square, sampled at the cell's centre."""
    def __init__(self, doc, data, off, cell=100.0):
        self.cell, self.top = cell, {}
        skip = ("water", "sky", "fog", "wave", "flare", "light")
        for mesh in doc["meshes"]:
            for prim in mesh["primitives"]:
                name = doc["materials"][prim["material"]]["name"].lower()
                if any(w in name for w in skip) or name.endswith("__lmobj"):
                    continue
                pos = read_accessor(doc, data, prim["attributes"]["POSITION"]).astype(np.float64)
                pos = np.stack([pos[:, 0] * 100.0, pos[:, 2] * 100.0, pos[:, 1] * 100.0], 1) + np.array(off)
                idx = read_accessor(doc, data, prim["indices"]).reshape(-1, 3)
                for i0, i1, i2 in idx:
                    a, b, c = pos[i0], pos[i1], pos[i2]
                    n = np.cross(b - a, c - a)
                    ln = np.linalg.norm(n)
                    # Unreal's axes turn the glTF's normal over (WalkGrid):
                    # facing down is +z here.
                    if ln <= 0 or n[2] / ln < 0.2:
                        continue
                    det = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
                    if abs(det) < 1e-6:
                        continue
                    xs, ys = (a[0], b[0], c[0]), (a[1], b[1], c[1])
                    for ix in range(math.floor(min(xs) / cell), math.floor(max(xs) / cell) + 1):
                        px = (ix + 0.5) * cell
                        for iy in range(math.floor(min(ys) / cell), math.floor(max(ys) / cell) + 1):
                            py = (iy + 0.5) * cell
                            w1 = ((b[1] - c[1]) * (px - c[0]) + (c[0] - b[0]) * (py - c[1])) / det
                            w2 = ((c[1] - a[1]) * (px - c[0]) + (a[0] - c[0]) * (py - c[1])) / det
                            if min(w1, w2, 1 - w1 - w2) < 0:
                                continue
                            z = w1 * a[2] + w2 * b[2] + (1 - w1 - w2) * c[2]
                            self.top.setdefault((ix, iy), []).append(z)

    def covered(self, x, y, z):
        """Whether a roof stands COVER_OVER to COVER_UNDER cm over (x, y, z)."""
        zs = self.top.get((math.floor(x / self.cell), math.floor(y / self.cell)))
        return bool(zs) and any(z + COVER_OVER < q <= z + COVER_UNDER for q in zs)


class WalkGrid:
    """The heights of everything a player can stand on (a triangle whose
    normal is at least WALK_Z up: ground, ledges, ramps, floors, of any
    shader but water and sky), by 1 m cell, sampled at each cell's centre:
    a cladding rock keeps out of the space above them (`blocks`)."""
    def __init__(self, doc, data, off, cell=50.0):
        self.cell, self.cells = cell, {}
        skip = ("water", "sky", "fog", "wave", "flare", "light")
        for mesh in doc["meshes"]:
            for prim in mesh["primitives"]:
                name = doc["materials"][prim["material"]]["name"].lower()
                if any(w in name for w in skip):
                    continue
                pos = read_accessor(doc, data, prim["attributes"]["POSITION"]).astype(np.float64)
                pos = np.stack([pos[:, 0] * 100.0, pos[:, 2] * 100.0, pos[:, 1] * 100.0], 1) + np.array(off)
                idx = read_accessor(doc, data, prim["indices"]).reshape(-1, 3)
                for i0, i1, i2 in idx:
                    a, b, c = pos[i0], pos[i1], pos[i2]
                    n = np.cross(b - a, c - a)
                    ln = np.linalg.norm(n)
                    # The glTF's winding in Unreal's axes (y and z swapped)
                    # turns the normal over: up is -z here.
                    if ln <= 0 or -n[2] / ln < WALK_Z:
                        continue
                    det = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
                    if abs(det) < 1e-6:
                        continue
                    xs, ys = (a[0], b[0], c[0]), (a[1], b[1], c[1])
                    for ix in range(math.floor(min(xs) / cell), math.floor(max(xs) / cell) + 1):
                        px = (ix + 0.5) * cell
                        for iy in range(math.floor(min(ys) / cell), math.floor(max(ys) / cell) + 1):
                            py = (iy + 0.5) * cell
                            w1 = ((b[1] - c[1]) * (px - c[0]) + (c[0] - b[0]) * (py - c[1])) / det
                            w2 = ((c[1] - a[1]) * (px - c[0]) + (a[0] - c[0]) * (py - c[1])) / det
                            if min(w1, w2, 1 - w1 - w2) < 0:
                                continue
                            self.cells.setdefault((ix, iy), []).append(w1 * a[2] + w2 * b[2] + (1 - w1 - w2) * c[2])

    def supports(self, x, y, z, r):
        """Whether ground a player can stand on lies under (x, y) and r cm
        out in each of four directions, within 40 cm of z: a piece that
        size sits on it whole, overhanging nothing."""
        for dx, dy in ((0, 0), (r, 0), (-r, 0), (0, r), (0, -r)):
            zs = self.cells.get((math.floor((x + dx) / self.cell), math.floor((y + dy) / self.cell)))
            if not zs or not any(abs(q - z) <= 40.0 for q in zs):
                return False
        return True

    def drop(self, x, y, z, tilt, r):
        """How far (cm) a rigid piece r cm across from (x, y, z), lying on
        the plane of normal `tilt` (its x, y), must go down so no edge
        stands over the ground: the most the ground falls below that plane
        at eight points round its rim (0 where it rises). None if no ground
        within 40 cm is known under one of them."""
        nx, ny = tilt
        nz = math.sqrt(max(1e-6, 1.0 - nx * nx - ny * ny))
        worst = 0.0
        for k in range(8):
            dx, dy = r * math.cos(k * math.pi / 4), r * math.sin(k * math.pi / 4)
            plane = z - (nx * dx + ny * dy) / nz
            zs = self.cells.get((math.floor((x + dx) / self.cell), math.floor((y + dy) / self.cell)))
            near = [q for q in zs or () if abs(q - plane) <= 40.0]
            if not near:
                return None
            worst = max(worst, plane - max(near))
        return worst

    def blocks(self, c, reach, across=PLAYER_R):
        """Whether a rock (a sphere: centre `c`, cm, radius `reach`) enters
        the space a player takes over any walkable spot (`across` cm
        around it, from just under the ground to PLAYER_H over it). With
        across 0 (a rock pressed flush into its wall): whether it rises out
        of a walkable surface, the walkway at the wall's top or the floor
        at its foot; beside one it only thickens the wall by its 8 to 20 cm."""
        r = reach + across
        for ix in range(math.floor((c[0] - r) / self.cell), math.floor((c[0] + r) / self.cell) + 1):
            for iy in range(math.floor((c[1] - r) / self.cell), math.floor((c[1] + r) / self.cell) + 1):
                zs = self.cells.get((ix, iy))
                if not zs:
                    continue
                dx, dy = (ix + 0.5) * self.cell - c[0], (iy + 0.5) * self.cell - c[1]
                dh = math.sqrt(dx * dx + dy * dy)
                if dh > r:
                    continue
                # The sphere's height at the cylinder's nearest side.
                gap = max(0.0, dh - across)
                half = math.sqrt(max(0.0, reach * reach - gap * gap))
                if half <= 0.0:
                    continue
                if any(c[2] - half <= z + PLAYER_H and c[2] + half >= z + (-10.0 if across else 5.0) for z in zs):
                    return True
        return False


class WallGrid:
    """Points over every steep face (normal z under 0.5, any shader but
    water and sky), by 1 m cell: where walls stand, for the scatter's wall
    rules. `foot`: a wall rises over (x, y, z) within FOOT_REACH across;
    `lip`: (x, y, z) stands over a drop, a wall falling away below it."""
    def __init__(self, doc, data, off, step=60.0, cell=100.0):
        self.cell, self.cells = cell, {}
        skip = ("water", "sky", "fog", "wave", "flare", "light")
        for mesh in doc["meshes"]:
            for prim in mesh["primitives"]:
                name = doc["materials"][prim["material"]]["name"].lower()
                if any(w in name for w in skip):
                    continue
                pos = read_accessor(doc, data, prim["attributes"]["POSITION"]).astype(np.float64)
                pos = np.stack([pos[:, 0] * 100.0, pos[:, 2] * 100.0, pos[:, 1] * 100.0], 1) + np.array(off)
                idx = read_accessor(doc, data, prim["indices"]).reshape(-1, 3)
                for i0, i1, i2 in idx:
                    p0, p1, p2 = pos[i0], pos[i1], pos[i2]
                    n = np.cross(p1 - p0, p2 - p0)
                    ln = np.linalg.norm(n)
                    if ln <= 0 or abs(n[2]) / ln >= 0.5:
                        continue
                    edge = max(np.linalg.norm(p1 - p0), np.linalg.norm(p2 - p1), np.linalg.norm(p0 - p2))
                    k = max(1, int(edge / step))
                    for u in range(k + 1):
                        for v in range(k + 1 - u):
                            q = (u / k) * p0 + (v / k) * p1 + (1 - u / k - v / k) * p2
                            self.cells.setdefault((int(q[0] // cell), int(q[1] // cell)), []).append(q)

    def _any(self, x, y, reach, test):
        for ix in range(int((x - reach) // self.cell), int((x + reach) // self.cell) + 1):
            for iy in range(int((y - reach) // self.cell), int((y + reach) // self.cell) + 1):
                for q in self.cells.get((ix, iy), ()):
                    if (q[0] - x) ** 2 + (q[1] - y) ** 2 <= reach * reach and test(q[2]):
                        return True
        return False

    def foot(self, x, y, z):
        return self._any(x, y, FOOT_REACH, lambda qz: z + 60.0 <= qz <= z + 300.0)

    def lip(self, x, y, z):
        return self._any(x, y, LIP_REACH, lambda qz: z - 300.0 <= qz <= z - 80.0)


# How far from a wall the wall rules reach (cm): rubble along its foot, snow
# along the edge of a drop.
FOOT_REACH = 130.0
LIP_REACH = 90.0


class PointGrid:
    """Points hashed into cubes of `cell` cm, for 'anything within r' tests."""
    def __init__(self, pts, cell=300.0):
        self.cell, self.cells = cell, {}
        for q in pts:
            self.cells.setdefault(tuple((q // cell).astype(int)), []).append(q)

    def near(self, c, r):
        lo, hi = ((c - r) // self.cell).astype(int), ((c + r) // self.cell).astype(int)
        for i in range(lo[0], hi[0] + 1):
            for j in range(lo[1], hi[1] + 1):
                for k in range(lo[2], hi[2] + 1):
                    for q in self.cells.get((i, j, k), ()):
                        if np.dot(q - c, q - c) < r * r:
                            return True
        return False


def clad(doc, data, spec, off, a, groups, bases, lights, rng):
    """Scatter the cladding rocks over the cliff walls into `groups` (as the
    rules do), each with its colour: the CE lightmap's chroma where it sits.
    Returns how many."""
    slots = cliff_slots(spec)
    images = {}
    total = 0
    rocks = []
    # Keep clear of what players use: CE's built surfaces (a ladder, a
    # walkway, a base) by the rock's reach plus CLADDING["clear"], and the
    # top of the wall (its lip, by the edge map): no rock above it, where
    # it would stand on the path along the cliff top.
    built = PointGrid(built_points(doc, data, spec, off))
    # And out of the space over walkable ground (a ledge path up a cliff, a
    # ramp, a floor): on a natural ledge Ice Fields' rocks blocked the
    # walkway up to a base (2026-10-13). As CE's walls had nothing on them,
    # nothing may stand where players move.
    walk = WalkGrid(doc, data, off)
    walked = flush = 0
    edge = None
    if a.edge:
        e = json.load(open(a.edge, encoding="utf-8"))["pbr"]["edge"]
        img = np.asarray(Image.open(os.path.join(os.path.dirname(os.path.abspath(a.edge)), "edge.png"))
                         .convert("RGBA"), dtype=np.float32) / 255.0
        edge = (img, e["rect"], e["range"])
    dropped = 0
    weights = [m[4] for m in CLADDING["meshes"]]
    for mesh in doc["meshes"]:
        for prim in mesh["primitives"]:
            hit = slots.get(doc["materials"][prim["material"]]["name"].lower())
            if not hit:
                continue
            base_file, lm_file, base_path = hit
            for f in (lm_file,):
                if f not in images:
                    images[f] = np.asarray(Image.open(f).convert("RGBA"), dtype=np.float32) / 255.0
            lm = images[lm_file]
            pos = read_accessor(doc, data, prim["attributes"]["POSITION"]).astype(np.float64)
            uv1 = read_accessor(doc, data, prim["attributes"]["TEXCOORD_1"]).astype(np.float64)
            idx = read_accessor(doc, data, prim["indices"]).reshape(-1, 3)
            for i0, i1, i2 in idx:
                p0, p1, p2 = pos[i0], pos[i1], pos[i2]
                n = np.cross(p1 - p0, p2 - p0)
                area = 0.5 * np.linalg.norm(n)
                if area <= 0:
                    continue
                # Outward, in Unreal's axes (the glTF's y and z swapped).
                nu = np.array([n[0], n[2], n[1]]) / (2 * area)
                if abs(nu[2]) > CLADDING["steep"]:
                    continue
                count = area * CLADDING["density"]
                k = int(count) + (1 if rng.random() < count - int(count) else 0)
                for _ in range(k):
                    r1, r2 = rng.random(), rng.random()
                    sq = math.sqrt(r1)
                    w0, w1, w2 = 1 - sq, sq * (1 - r2), sq * r2
                    p = w0 * p0 + w1 * p1 + w2 * p2
                    x, y, z = p[0] * 100.0 + off[0], p[2] * 100.0 + off[1], p[1] * 100.0 + off[2]
                    if a.sea is not None and (z - a.sea) / 100.0 < CLADDING["above"]:
                        continue
                    path, smin, smax, depth, _ = rng.choices(CLADDING["meshes"], weights)[0]
                    scale = rng.uniform(smin, smax)
                    out = rng.uniform(*CLADDING["protrude"])
                    inset = depth * scale - out
                    cx, cy, cz = x - nu[0] * inset, y - nu[1] * inset, z - nu[2] * inset
                    reach = depth * scale
                    if built.near(np.array([cx, cy, cz]), reach + CLADDING["clear"]):
                        dropped += 1
                        continue
                    if walk.blocks((cx, cy, cz), reach):
                        # Pressed flush; then smaller, for a short wall (a
                        # walkway's side: the big rocks rose through its top).
                        for k_ in (1.0, 0.45, 0.25):
                            s_ = scale * k_
                            out = rng.uniform(*FLUSH)
                            inset = depth * s_ - out
                            cx, cy, cz = x - nu[0] * inset, y - nu[1] * inset, z - nu[2] * inset
                            if not walk.blocks((cx, cy, cz), depth * s_, across=0.0):
                                scale, reach = s_, depth * s_
                                break
                        else:
                            walked += 1
                            continue
                        flush += 1
                    if edge is not None:
                        img, rect, rng_z = edge
                        h, w = img.shape[:2]
                        uu, vv = (cx - rect[0]) / rect[2], (cy - rect[1]) / rect[3]
                        if 0 <= uu < 1 and 0 <= vv < 1:
                            px = img[int(vv * h), int(uu * w)]
                            top = rng_z[0] + px[0] * (rng_z[1] - rng_z[0])
                            if px[0] > 0.004 and cz + reach * 0.7 > top - 30.0:
                                dropped += 1
                                continue
                    u = w0 * uv1[i0] + w1 * uv1[i1] + w2 * uv1[i2]
                    rgb = sample_rgba(lm, u[None, :])[0, :3]
                    lin = np.power(np.maximum(rgb, 1e-3), 2.2)
                    lum = float(lin @ np.array([0.2126, 0.7152, 0.0722]))
                    col = tuple(float(c) for c in np.clip(lin / max(lum, 1e-3), 0.4, 2.0))
                    tilt = (float(nu[0]), float(nu[1]))
                    # rec[7]: the lightmap's own colour (gamma), the record's
                    # bytes: the loader hands it to the rock (CladLight.a 2).
                    rocks.append((path, [cx, cy, cz, rng.uniform(0, 360), scale, tilt, col,
                                         tuple(float(c) for c in np.clip(rgb, 0.0, 1.0))], base_path))
                    total += 1
    print(f"cladding: {total} rocks, {dropped} left out (near built surfaces or over a lip), "
          f"{flush} pressed flush beside walkable ground, {walked} left out of the space over it "
          f"({len(walk.cells)} walkable cells)")
    # A group a mesh and a light (the loader gives each group one material,
    # its CladLight the cluster's centre): the lights in CLADDING["lights"]
    # clusters (k-means), keyed apart from the stones' groups of the meshes.
    if rocks:
        cols = np.array([r[1][6] for r in rocks])
        k = min(CLADDING["lights"], len(rocks))
        centres = cols[np.linspace(0, len(cols) - 1, k).astype(int)].copy()
        for _ in range(12):
            lab = np.argmin(((cols[:, None, :] - centres[None]) ** 2).sum(-1), 1)
            for c in range(k):
                if (lab == c).any():
                    centres[c] = cols[lab == c].mean(0)
        for (path, rec, base_path), c in zip(rocks, lab):
            key = f"{path}|cladding{c}"
            groups.setdefault(key, ({"name": "cladding", "cull": [0, 0], "shadow": True, "cliff": True},
                                    []))[1].append(rec)
            bases.setdefault(key, base_path)
            lights[key] = [round(float(v), 3) for v in centres[c]]
    return total


def near_lip(edge, x, y, kind="lip"):
    """Whether the edge map has any lip (or foot) at (x, y) Unreal cm."""
    img, rect, _ = edge
    h, w = img.shape[:2]
    u, v = (x - rect[0]) / rect[2], (y - rect[1]) / rect[3]
    return 0 <= u < 1 and 0 <= v < 1 and img[int(v * h), int(u * w)][1 if kind == "lip" else 2] > 0.05


def on_lip(edge, x, y, z, kind="lip"):
    """Whether (x, y, z) Unreal cm is on a lip (or at a wall's foot) by the
    edge map: its mask over half, and within 80 cm of its height."""
    img, rect, rng = edge
    h, w = img.shape[:2]
    u, v = (x - rect[0]) / rect[2], (y - rect[1]) / rect[3]
    if not (0 <= u < 1 and 0 <= v < 1):
        return False
    px = img[int(v * h), int(u * w)]
    if kind == "foot":
        return px[2] > 0.5 and px[3] > 0.0 and abs(z - (rng[0] + px[3] * (rng[1] - rng[0]))) < 80.0
    top = rng[0] + px[0] * (rng[1] - rng[0])
    return px[1] > 0.5 and abs(z - top) < 80.0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("gltf")
    ap.add_argument("spec")
    ap.add_argument("out")
    ap.add_argument("--bin", required=True, help="the instances' binary file (out.json names it)")
    ap.add_argument("--sea", type=float, help="the sea's height (Unreal cm): the rules' heights are above it")
    ap.add_argument("--offset", default="0,0,0", help="the terrain mesh's offset (cm, build_terrain_meshes --offset)")
    ap.add_argument("--lift", type=float, default=0.0,
                    help="cm the visible ground rides over the mesh: a landscape's --lift (build_landscape.py, 8) "
                         "less about half its parallax depth (the sand is drawn that far down; Death Island: 6). "
                         "Without it a rock set into CE's ground lay buried under the landscape")
    ap.add_argument("--edge", help="a landscape.json (build_landscape.py) whose edge map places the lip rules")
    ap.add_argument("--no-cladding", action="store_true", help="leave the cliffs' cladding rocks out")
    ap.add_argument("--detail", action="append", default=[], metavar="NAME=CLASS",
                    help="a detail bitmap (substring of its name) and its class, sand or grass; repeatable")
    ap.add_argument("--center", help="x,y (Unreal cm): only scatter within --radius of it")
    ap.add_argument("--radius", type=float, default=0.0, help="cm")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--cliff-shaders", default="", help="substrings of the cliff shaders' names, comma-separated")
    ap.add_argument("--ground-shaders", default="",
                    help="substrings of the ground shaders' names, comma-separated: only these grow anything "
                         "(a facility's floor whose detail map is 'dirt splotch' read as natural ground)")
    ap.add_argument("--swapped-rocks", action="store_true",
                    help="clear no circle for the boulders scenery_swap.py replaces (rock_foliage.py clears "
                         "their own hulls after the swap)")
    ap.add_argument("--biome", default="b30", choices=["b30", "snow"],
                    help="whose dressing: B30's (grass, beach) or B40's (snow: snowy stones, glacial cladding)")
    ap.add_argument("--only", help="comma-separated rule names")
    ap.add_argument("--extra", action="append", default=[], metavar="RULE",
                    help="an optional rule to add (sea rocks); repeatable")
    ap.add_argument("--staging", help="the conversion's staging folder (placement.json, models/) when it is not "
                                      "beside the scene")
    ap.add_argument("--rule-tint", action="append", default=[], metavar="RULE=R,G,B[:PARAM]",
                    help="a rule's tint for this map (and the material parameter it goes through; Megascans "
                         "3D assets take 'Albedo Tint'): Blood Gulch's pebbles in its red earth; repeatable")
    a = ap.parse_args()

    for pair in a.detail:
        name, cls = pair.split("=", 1)
        EXTRA_DETAILS.append((cls, (name.lower(),)))
    CLIFF_SHADERS.extend(x.lower() for x in a.cliff_shaders.split(",") if x)
    if a.biome == "snow":
        global CLADDING
        CLADDING = SNOW_CLADDING
    rules = [dict(r) for r in (SNOW_RULES if a.biome == "snow" else RULES)
             if (not a.only or r["name"] in a.only.split(","))
             and (not r.get("optional") or r["name"] in a.extra)]
    for spec in a.rule_tint:
        name, _, rest = spec.partition("=")
        rgb, _, param = rest.partition(":")
        for r in rules:
            if r["name"] == name:
                r["tint"] = [float(v) for v in rgb.split(",")]
                r.pop("tints", None)
                if param:
                    r["tint_param"] = param
    if a.sea is None:
        # A rule that lives in a band above the sea has no place on a map
        # without one: unbounded, the shore stones would cover every sand.
        rules = [r for r in rules if r["above"][1] is None]
    edge = None
    if a.edge:
        land = json.load(open(a.edge, encoding="utf-8"))
        e = land["pbr"]["edge"]
        img = np.asarray(Image.open(os.path.join(os.path.dirname(os.path.abspath(a.edge)), "edge.png")).convert("RGBA"),
                         dtype=np.float32) / 255.0
        edge = (img, e["rect"], e["range"])
    else:
        rules = [r for r in rules if not r.get("edge")]
    # The landscape's own floor under the sea (build_landscape.py --sea
    # shelves it away from the shore): a piece under the sea that would stand
    # over it is left out. CE's sandbars half a metre down lie metres over
    # Death Island's seabed, and its stones floated in the troughs
    # (2026-10-14).
    floor = None
    if a.edge and a.sea is not None:
        land = json.load(open(a.edge, encoding="utf-8"))
        n = land["size"]
        hts = np.fromfile(os.path.join(os.path.dirname(os.path.abspath(a.edge)), land["heights"]), "<u2")
        zs = land["location"][2] + (hts.reshape(n, n).astype(np.float64) - 32768) * land["scale"][2] / 128.0
        floor = (zs, land["location"], land["scale"])

    def under_floor(x, y, z):
        if floor is None or z >= a.sea:
            return False
        zs, loc, sc = floor
        i = int(round((x - loc[0]) / sc[0]))
        j = int(round((y - loc[1]) / sc[1]))
        if not (0 <= i < zs.shape[1] and 0 <= j < zs.shape[0]):
            return False
        return z - zs[j, i] > 30.0
    spec = json.load(open(a.spec, encoding="utf-8"))
    slots = ground_slots(spec)
    only = [x.lower() for x in a.ground_shaders.split(",") if x]
    if only:
        # Sidewinder's facility floors (B30's metal panels over a dirt
        # splotch detail) grew snowy stones and rubble (2026-10-13).
        slots = {k: v for k, v in slots.items() if any(x in k.lower() for x in only)}
    # The cliffs' up-facing faces as grass: M_CE_CliffPBR draws turf there
    # (TURF_Z, by the surface's normal), and Death Island's tunnel floor, a
    # cliff shader (its detail rock, so no grass by it), lay as a bare lawn
    # (2026-10-15). Only the grass rules take the turf.
    turfed = set()
    for k, v in cliff_slots(spec).items():
        k = k.lower()
        if not only or any(x in k for x in only):
            turfed.add(k)
            slots.setdefault(k, (v[0], TURF, None, 0))
    doc = json.load(open(a.gltf, encoding="utf-8"))
    data = open(os.path.join(os.path.dirname(os.path.abspath(a.gltf)), doc["buffers"][0]["uri"]), "rb").read()
    center = tuple(float(v) for v in a.center.split(",")) if a.center else None
    off = [float(v) for v in a.offset.split(",")]
    footprints = scenery_footprints(a.gltf, off, a.staging, a.swapped_rocks, a.biome == "snow")
    scenery = scenery_grid(footprints)
    staging_dir = a.staging or os.path.join(os.path.dirname(os.path.abspath(a.gltf)), "staging")
    swapped = swapped_surface(staging_dir, a.biome == "snow") if a.swapped_rocks else (lambda name: False)
    print(f"{len(footprints)} scenery object(s) kept clear of foliage")
    rng = random.Random(a.seed)
    rng_lip = random.Random(a.seed + 7)
    walls = WallGrid(doc, data, off) if any(r.get("wall") for r in rules) else None
    cover = CoverGrid(doc, data, off)
    ground = WalkGrid(doc, data, off) if any(r.get("support") or r.get("seat") or r.get("shore") for r in rules) else None
    shore = ShoreGrid(ground, a.sea) if a.sea is not None and any(r.get("shore") for r in rules) else None
    rng_centre = random.Random(a.seed + 17)
    images = {}
    groups = {}  # mesh -> (rule, instances)
    counts = {r["name"]: 0 for r in rules}
    for mesh in doc["meshes"]:
        for prim in mesh["primitives"]:
            name = doc["materials"][prim["material"]]["name"].lower()
            hit = slots.get(name)
            if not hit or swapped(name):
                continue
            cliff = name in turfed
            file, primary, secondary, shader_type = hit
            if file not in images:
                images[file] = np.asarray(Image.open(file).convert("RGBA"), dtype=np.float32) / 255.0
            img = images[file]
            pos = read_accessor(doc, data, prim["attributes"]["POSITION"]).astype(np.float64)
            uv = read_accessor(doc, data, prim["attributes"]["TEXCOORD_0"]).astype(np.float64)
            idx = read_accessor(doc, data, prim["indices"]).reshape(-1, 3)
            for i0, i1, i2 in idx:
                p0, p1, p2 = pos[i0], pos[i1], pos[i2]
                n = np.cross(p1 - p0, p2 - p0)
                area = 0.5 * np.linalg.norm(n)
                if area <= 0:
                    continue
                slope = math.degrees(math.acos(min(1.0, abs(n[1]) / (2 * area))))
                if center:
                    c = (p0 + p1 + p2) / 3.0 * 100.0
                    reach = max(np.linalg.norm(p0 - p1), np.linalg.norm(p1 - p2), np.linalg.norm(p2 - p0)) * 100.0
                    if math.hypot(c[0] - center[0], c[2] - center[1]) > a.radius + reach:
                        continue
                for rule in rules:
                    if slope > rule["slope"]:
                        continue
                    # Lip rules: only triangles near a lip, from a stream of
                    # their own (the other rules place as they did).
                    R = rng
                    if rule.get("wall"):
                        R = rng_lip
                    if rule.get("edge"):
                        R = rng_lip
                        cx, cy, cz = (p0 + p1 + p2) / 3.0 * 100.0
                        if not near_lip(edge, cx + off[0], cz + off[1], rule["edge"]):
                            continue
                    count = area * rule["density"]
                    k = int(count) + (1 if R.random() < count - int(count) else 0)
                    if not k:
                        continue
                    r1 = np.array([R.random() for _ in range(k)])
                    r2 = np.array([R.random() for _ in range(k)])
                    s = np.sqrt(r1)
                    w0, w1, w2 = 1 - s, s * (1 - r2), s * r2
                    pts = np.outer(w0, p0) + np.outer(w1, p1) + np.outer(w2, p2)
                    uvs = np.outer(w0, uv[i0]) + np.outer(w1, uv[i1]) + np.outer(w2, uv[i2])
                    share = None
                    if primary != TURF:
                        share = (np.ones(len(uvs)) if rule["on"] == "any" else
                                 class_shares(sample_rgba(img, uvs), primary, secondary, shader_type).get(rule["on"]))
                    if cliff and rule["on"] == "grass":
                        turf = turf_share(n[1] / (2 * area))
                        if turf > 0.0:
                            share = np.maximum(share if share is not None else 0.0, turf)
                    if share is None:
                        continue
                    lo, hi = rule["share"]
                    bk = rule.get("banks")
                    thin = None
                    if bk and slope > bk[0]:
                        bank = min(1.0, (slope - bk[0]) / max(bk[1] - bk[0], 1e-3))
                        by_bank = lo + (hi - lo) * bank
                        # Where only the bank grows it, at the bank's density.
                        thin = np.where(by_bank > share, bk[2] if len(bk) > 2 else 1.0, 1.0)
                        share = np.maximum(share, by_bank)
                    for j, (p, sh) in enumerate(zip(pts, share)):
                        if R.random() > keep_share(sh, lo, hi, rule.get("falloff")) * (1.0 if thin is None else thin[j]):
                            continue
                        x, y, z = p[0] * 100.0 + off[0], p[2] * 100.0 + off[1], p[1] * 100.0 + off[2] + a.lift
                        if center and math.hypot(x - center[0], y - center[1]) > a.radius:
                            continue
                        if a.sea is not None:
                            low, high = rule["above"]
                            h = (z - a.lift - a.sea) / 100.0
                            if (low is not None and h < low) or (high is not None and h > high):
                                continue
                        if under_floor(x, y, z - a.lift):
                            continue
                        if rule.get("edge") and not on_lip(edge, x, y, z, rule["edge"]):
                            continue
                        if rule.get("wall") and not getattr(walls, rule["wall"])(x, y, z - a.lift):
                            continue
                        if under_scenery(scenery, x, y, z - a.lift):
                            continue
                        if (rule["on"] == "grass" or rule.get("edge") == "lip") and cover.covered(x, y, z - a.lift):
                            continue
                        cl = rule.get("cluster")
                        if cl and value_noise(x, y, cl[0], a.seed) < cl[1]:
                            continue
                        sb = rule.get("shore")
                        if sb and not (shore and shore.within(x, y, sb[0], sb[1])):
                            continue
                        path, smin, smax, sink = rule["meshes"][R.randrange(len(rule["meshes"]))]
                        scale = R.uniform(smin, smax)
                        # `support` (cm a unit of scale): the piece's half-size,
                        # all of it on walkable ground (on Ice Fields' cliff
                        # ledges the drifts and rubble hung in the air).
                        sup = rule.get("support")
                        if sup and not ground.supports(x, y, z - a.lift, sup * scale):
                            continue
                        pt = rule.get("patch")
                        if pt:
                            scale *= pt[1] + (pt[2] - pt[1]) * value_noise(x, y, pt[0], a.seed + 7)
                        # A rule sharing meshes with another (the sea rocks,
                        # the stones') keeps its own group: its own culling.
                        key = path + ("|" + rule["group"] if rule.get("group") else "")
                        if rule.get("tints"):
                            # Ragged patch edges: the noise jittered a little.
                            v = value_noise(x + 7919.0, y - 3571.0, rule.get("tint_cell", 15.0), a.seed + 11)
                            v = min(0.999, max(0.0, v + (R.random() - 0.5) * 0.2))
                            key = f"{path}|tint{int(v * len(rule['tints']))}"
                        # Along the ground: its normal in Unreal's axes (y and z
                        # swapped from the glTF's, which flips the cross product).
                        tilt = (0.0, 0.0)
                        if rule.get("align"):
                            nu = np.array([n[0], n[2], n[1]]) / (2 * area)
                            if nu[2] < 0:
                                nu = -nu
                            tilt = (float(nu[0]), float(nu[1]))
                        seat = rule.get("seat")
                        if seat:
                            down = ground.drop(x, y, z - a.lift, tilt, seat[0] * scale)
                            if down is None or down > seat[1] * scale:
                                continue
                            z -= down
                        groups.setdefault(key, (rule, []))[1].append(
                            [x, y, z - sink * scale, R.uniform(0, 360), scale, tilt])
                        counts[rule["name"]] += 1
                        cr = rule.get("centre")
                        if cr:
                            # A stone at the piece's centre (its own RNG: the
                            # rest of the scatter stays where it was).
                            pick = rng_centre.choices(cr["meshes"], weights=[m[4] for m in cr["meshes"]])[0]
                            cs = rng_centre.uniform(pick[1], pick[2])
                            groups.setdefault(pick[0] + "|centre", (cr, []))[1].append(
                                [x, y, z - pick[3] * cs, rng_centre.uniform(0, 360), cs, tilt])
                            counts[cr["name"]] = counts.get(cr["name"], 0) + 1
    clad_bases, clad_lights = {}, {}
    if not a.no_cladding:
        n_clad = clad(doc, data, spec, off, a, groups, clad_bases, clad_lights, random.Random(a.seed + 13))
        counts["cladding"] = n_clad
    ordered = sorted(groups.items(), key=lambda kv: kv[0])
    with open(a.bin, "wb") as f:
        f.write(FOLIAGE_MAGIC + struct.pack("<II", 3, len(ordered)))
        for _, (_, inst) in ordered:
            f.write(struct.pack("<I", len(inst)))
            for rec in inst:
                x, y, z, yaw, scale, (nx, ny) = rec[:6]
                if len(rec) > 7:
                    colour = [round(c * 255) for c in rec[7]]
                else:
                    colour = [round(c * 100) for c in (rec[6] if len(rec) > 6 else NO_COLOUR)]
                f.write(struct.pack("<fffBBbbBBB", x, y, z, int(yaw / 360.0 * 256) % 256,
                                    max(1, min(255, round(scale * 100))) & 0xFF,
                                    max(-127, min(127, round(nx * 127))), max(-127, min(127, round(ny * 127))),
                                    *(max(0, min(255, c)) for c in colour)))
    out_groups = []
    for path, (rule, _) in ordered:
        g = {"mesh": object_path(path.split("|")[0]), "rule": rule["name"], "cull": rule["cull"]}
        if rule.get("tint"):
            g["tint"] = rule["tint"]
        if "|tint" in path:
            g["tint"] = rule["tints"][int(path.rsplit("|tint", 1)[1])]
        if rule.get("tint_param"):
            g["tint_param"] = rule["tint_param"]
        if rule.get("params"):
            g["params"] = rule["params"]
        if rule.get("bands"):
            g["bands"] = rule["bands"]
        material = rule.get("materials", {}).get(path.split("|")[0])
        if material:
            g["material"] = object_path(material)
        g["shadow"] = bool(rule.get("shadow", True))
        if rule.get("cliff"):
            # Drawn in the cliffs' rock (M_CE_CliffPBR) with the base map of
            # the wall it clads, its instance colour the wall's CE light.
            g["cliff"] = True
            g["base"] = clad_bases.get(path)
            g["light"] = clad_lights.get(path)
            # Each rock's record carries its CE lightmap colour (0..255).
            g["lm"] = True
        out_groups.append(g)
    json.dump({"file": os.path.basename(a.bin), "groups": out_groups}, open(a.out, "w", encoding="utf-8"), indent=1)
    print(", ".join(f"{v} {k}" for k, v in counts.items()) + f" over {len(slots)} ground slot(s) -> {a.bin}")


if __name__ == "__main__":
    main()

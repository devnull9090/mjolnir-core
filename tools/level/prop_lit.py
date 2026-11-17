"""Materials for meshes that move or are moved: M_CE_PropLit, lit by Unreal
where the mesh is now, in place of M_CE_Environment's object page (the light
baked where it was placed). Shared by the upgrade pipeline
(upgrade_ce_map.py: physics props, turning machines, extra decor) and a fresh
conversion (gen_ce_level.py: the parts of a Halo 2 machine that moves, which
drew black when the light baked at rest was a tunnel's: Triplicate's trains,
2026-11-15)."""


PROP_LIT = "/Game/MJOLNIR/CETrial/M_CE_PropLit.M_CE_PropLit"
PROP_OVERLAY = "/Game/MJOLNIR/CETrial/M_CE_PropOverlay.M_CE_PropOverlay"
PROP_HIDDEN = "/Game/MJOLNIR/CETrial/M_CE_Hidden.M_CE_Hidden"
# A moving prop's glowing parts (a fusion coil's core): brighter than CE drew
# them, pulsing (depth, period s), so the glow reads and Lumen casts it; the
# surface dark under the glow's lines (GlowDarken), so they show green and not
# the base map's white; and the fusion look (M_CE_PropLit's Fusion: energy
# bands a core high, their speed /s, their depth; FusionHaze, the haze
# between the lines).
PROP_GLOW = {"GlowBrightness": 40.0, "GlowDarken": 0.9, "FusionHaze": 0.1}
PROP_GLOW_PULSE = [0.35, 2.4, 0.0, 0.0]
PROP_FUSION = [3.0, 0.45, 0.6, 0.0]
PLAIN_GLOW_BRIGHTNESS = 30.0


def prop_lit(mat, prop):
    """A physics prop's material on M_CE_PropLit (build_ce_materials.py), lit
    by Unreal where it lies: M_CE_Environment's ObjectPage drew the light
    baked where it was placed as emissive, so a knocked-over drum glowed and
    Lumen bounced that round it as a halo (Zanzibar, 2026-11-15). Keeps the
    textures and scalars (same names); drops the lightmap, the CE specular and
    fog, which the lit master has no use for. `prop` may carry "look":
    {scalars} over every slot (Roughness, Metallic, Specular, AlbedoGain)."""
    # Halo 2's `overlay` (a crate's stencil): the converted level's darkening
    # copy (`__overlay`) loses the text that brightens; the prop draws the
    # stencil itself as a 2x multiply (M_CE_PropOverlay, its map imported
    # by h2_physics_props.py beside the copy).
    map0 = str((mat.get("textures") or {}).get("Map0", ""))
    if "__overlay." in map0:
        stem = map0.rsplit("/", 1)[-1].split(".")[0].replace("__overlay", "")
        return {"parent": PROP_OVERLAY,
                "textures": {"Map0": map0.rsplit("/", 1)[0] + f"/{stem}.{stem}"}, "scalars": {}, "vectors": {}}
    # The additive bloom shell over a glowing core (the coil's
    # `fusion_coil_bloom`): Halo 2 tints it with the core's colour functions,
    # the CE additive master drew it white over the orange (2026-11-15). The
    # core's emissive and the engine's bloom stand in for it.
    if "M_CE_TransparentAdd" in str(mat.get("parent", "")) and "_bloom" in map0:
        return PROP_HIDDEN
    if not str(mat.get("parent", "")).endswith("/M_CE_Environment.M_CE_Environment"):
        return mat
    textures = {k: v for k, v in (mat.get("textures") or {}).items() if k != "Lightmap"}
    keep = ("PrimaryScale", "BumpScale", "SelfIllumScale", "HasPrimary", "HasBump", "HasSelfIllum", "BumpIsSpecMask",
            "AlbedoGain")
    scalars = {k: v for k, v in (mat.get("scalars") or {}).items() if k in keep}
    vectors = {}
    # A plain glowing screen (h2_physics_props' `PlainGlow`: the gate
    # keypad's icon): its map lit in its colour, steady, no fusion bands,
    # haze or pulse, the surface under it not darkened.
    if (mat.get("scalars") or {}).get("PlainGlow", 0) > 0.5 and "SelfIllumMap" in textures:
        on = (mat.get("vectors") or {}).get("SelfOn0") or [1.0, 1.0, 1.0, 1.0]
        scalars.update(GlowBrightness=PLAIN_GLOW_BRIGHTNESS, GlowDarken=0.0, FusionHaze=0.0)
        vectors.update(GlowTint=on, GlowPulse=[0.0, 1.0, 0.0, 0.0], Fusion=[3.0, 0.5, 0.0, 0.0])
    elif scalars.get("HasSelfIllum", 0) > 0.5 and "SelfIllumMap" in textures:
        scalars.update(PROP_GLOW)
        vectors["GlowPulse"] = PROP_GLOW_PULSE
        vectors["Fusion"] = PROP_FUSION
        # Halo 2's own glow colours: the self-illumination map is a mask,
        # each channel tinted by its colour, "on" at full health and "off"
        # as the object's health function falls (a fusion coil's core:
        # orange, turning red as it is shot). Read as a picture, the mask's
        # green channel drew the coils green (2026-11-15).
        # The coil's tex_bump_plasma_one_channel_illum: its pixel constant 3
        # (SelfOn0, 255 136 136) is the colour shot, its colour overlay 1's
        # orange (255 143 43) the colour whole, blended by its `health`
        # function (the object's body vitality); M_CE_PropLit's H2Glow.
        src = mat.get("vectors") or {}
        if "SelfOn0" in src:
            # Deeper than the overlay's 255 143 43, which the tonemapper
            # washed to beige at the brightness the glow needs (in game,
            # 2026-11-15).
            vectors["H2Damaged"] = src["SelfOn0"]
            vectors["H2Healthy"] = [1.0, 0.38, 0.04, 1.0]
            vectors["HazeColor"] = [0.22, 0.09, 0.01, 1.0]
            scalars["H2Glow"] = 1.0
            scalars["GlowBrightness"] = 14.0
    scalars.update((prop.get("look") or {}))
    return {"parent": PROP_LIT, "textures": textures, "scalars": scalars, "vectors": vectors}

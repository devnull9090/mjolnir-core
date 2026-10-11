-- The ocean of The Silent Cartographer's beach, as its Fluid Flux surface
-- left it: the material parameters of the dynamic instance the B30 cell
-- cooks for BP_FluxSurface_Coastline (MID_MI_OceanOverGerstner_3, export 64
-- of Levels/Halo1/Solo/B30/B30/_Generated_/25OP0VWSR6YEFJHFXGUSRVBTY; read
-- with `mjolnir ue get --package <cell> --export 64`, 2026-10-10).
--
-- Only the surface's look: its colour preset (scattering, absorption, the
-- colour behind and over the water, shallow and deep) and the detail, foam
-- and specular terms. What depends on the place it is drawn (the wave
-- texture and its offsets, height and choppiness, the coastline, ground and
-- cut-mask maps) the loader works out for each level (applyWater). Without
-- the preset the material kept MI_OceanOver's defaults, whose scattering has
-- no density: Death Island's sea came out a flat dark green.

return {
    scalars = {
        DetailWaveChoppiness = 0.0,
        DetailWaveHeight = 24.0,
        DetailWaveUVOffset = -0.3,
        DetailWaveUVSwitching = 1.35,
        DetailWaveUVVelocityScale = 1000.0,
        WaveDetailWPOScale = 1.1,
        FoamScatteringScale = 4.0,
        PhaseGDeepSunHigh = 0.4,
        PhaseGDeepSunLow = 0.6,
        PhaseGShallowSunHigh = -0.2,
        PhaseGShallowSunLow = 0.4,
        WaveTextureDivergenceOffset = 0.15,
        WaveTextureDivergenceScale = 1.45,
        WaveTextureVelocityScaleBottom = -1.2,
        WaveTextureVelocityScaleTop = 0.2,
        FoamNormalScale = 1.0,
        FoamRoughness = 0.2,
        FoamSpecular = 0.13,
        NormalScatteringFresnelPower = 10.0,
        NormalScatteringIntensity = 0.05,
        CheapScatteringScale = 3.0,
        SurfaceOverlayAlpha = 0.06,
        WaterDepthUpwardBlend = 1.0,
        WaterRefractionDistanceScale = 8000.0,
        WaterRefractionFar = 1.01,
        WaterRefractionNear = 1.04,
        WaterShallowBlend = 1.0,
        WaterSpecularHorizonDistance = 90000.0,
        WaterSpecularHorizonOffset = 6.0,
        WaterRoughnessFromFresnel = 0.3,
        WaterRoughnessFromSpecular = 0.007,
        WaterRoughnessFromSpecularDiv = 0.997,
        WaterRoughnessMin = 0.05,
        SurfacePhaseG0 = 0.0,
        SurfacePhaseG1 = 0.0,
    },
    vectors = {
        SurfaceAbsorption0 = { 120, 250, 350, 4 },
        SurfaceAbsorption1 = { 290, 260, 140, 1 },
        SurfaceScattering0 = { 0.6, 1, 1, 0.00003 },
        SurfaceScattering1 = { 0.95, 0.8, 0.6, 0.0004 },
        ColorBehind0 = { 1, 1.2, 1.15, 0.65 },
        ColorBehind1 = { 1.15, 1, 0.9, 0.6 },
        SurfaceOverlay0 = { 0.117708, 0.294268, 0.470833, 0 },
        SurfaceOverlay1 = { 0.166667, 0.106061, 0.061033, 0.0003 },
        FoamColorBase = { 0.5, 0.5, 0.5, 0.55 },
        CameraRadius = { 0.02, 0.02, 0.004, 1.8 },
        WaterSpecular = { 0.05, 0.369998, 8, 1 },
    },
}

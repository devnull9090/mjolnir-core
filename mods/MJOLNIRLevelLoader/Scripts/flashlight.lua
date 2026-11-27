-- The game's flashlight under a level's light scale.
--
-- A level with manual exposure (environment.post.manual_exposure) lights its
-- world `light_scale` times brighter than the campaign does and exposes for
-- it (lightScale in main.lua): AutoExposureBias = exposure_bias -
-- log2(scale), with no physical camera exposure. The flashlight is the
-- game's own: its Blueprint (BP_Flashlight_EquipmentActor) drives two spot
-- lights at SoftLightIntensityScalar and PointLightIntensityScalar, in EV.
-- Left alone on such a level it was too dim to see in a dark room (Pelican
-- Warfare's bases, 2026-11-21).
--
-- Raising it by the whole log2(scale) (mods 0.54.0 to 0.59.1) was too much.
-- That assumes the campaign exposes at EV 0, but its auto exposure in the
-- dark sits a few stops above that, and the flashlight is tuned for it. At
-- +8 on Battle Creek the beam whited out the screen and the weapon. So the
-- light is raised by what this level's exposure takes away, less
-- CAMPAIGN_EV: log2(scale) - exposure_bias - CAMPAIGN_EV. On Battle Creek
-- (scale 256, bias 0) that is +3, which reads clearly on a wall in shade and
-- does not blow out at arm's length (2026-11-27, judged against +0, +2, +4
-- and +8 in game).
--
-- Both scalars are raised on the class's default object (every flashlight
-- made from then on) and on the flashlights already in the world. Setup
-- only: one write when a level is dressed, and restore() puts the game's own
-- values back when the level is left, so the campaign is never touched.
local Flashlight = {}

local CLASS = "/Game/_Prototypes/SynchronizationTestContent/Assets/Equipments/BP_Flashlight_EquipmentActor"
local FIELDS = { "SoftLightIntensityScalar", "PointLightIntensityScalar" }
local original          -- the game's own scalars, read once
local stops = 0         -- what is applied now

-- The exposure, in stops above EV 0, that the game's flashlight is tuned for.
local CAMPAIGN_EV = 5

local function defaults(findObject)
    local cdo = findObject(CLASS .. ".Default__BP_Flashlight_EquipmentActor_C")
    if cdo and cdo:IsValid() then return cdo end
    return nil
end

local function set(target, extra)
    for _, field in ipairs(FIELDS) do
        target[field] = original[field] + extra
    end
end

--- How many stops a level with light scale `scale` and exposure bias `bias`
--- raises the flashlight by (never below 0; scale 1 leaves it alone).
function Flashlight.boost(scale, bias)
    if type(scale) ~= "number" or scale <= 1 then return 0 end
    local extra = math.log(scale) / math.log(2) - (tonumber(bias) or 0) - CAMPAIGN_EV
    return extra > 0 and extra or 0
end

--- Raise the flashlight for a level's light scale and exposure bias.
function Flashlight.expose(scale, findObject, log, bias)
    local extra = Flashlight.boost(scale, bias)
    if extra == stops then return end
    local ok, err = pcall(function()
        local cdo = defaults(findObject)
        if not cdo then return end      -- not loaded yet: the class arrives with the first player
        if not original then
            original = {}
            for _, field in ipairs(FIELDS) do original[field] = cdo[field] end
        end
        Flashlight.findObject = findObject
        set(cdo, extra)
        for _, actor in ipairs(FindAllOf("BP_Flashlight_EquipmentActor_C") or {}) do
            if actor:IsValid() then set(actor, extra) end
        end
        stops = extra
        if log then log(string.format("flashlight: %+.1f stops for the level's light scale and exposure", extra)) end
    end)
    if not ok and log then log("flashlight: " .. tostring(err)) end
end

--- The game's own flashlight back (leaving a level).
function Flashlight.restore()
    if stops ~= 0 and Flashlight.findObject then Flashlight.expose(1, Flashlight.findObject) end
end

--- What is applied, for the tests.
function Flashlight.stops() return stops end

return Flashlight

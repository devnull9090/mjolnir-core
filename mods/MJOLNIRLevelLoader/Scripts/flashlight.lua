-- The game's flashlight under a level's light scale.
--
-- A level with manual exposure (environment.post.manual_exposure) lights its
-- world `light_scale` times brighter than the campaign does and exposes for
-- it (lightScale in main.lua). The flashlight is the game's own: its
-- Blueprint (BP_Flashlight_EquipmentActor) drives two spot lights at
-- SoftLightIntensityScalar and PointLightIntensityScalar, in EV, tuned for
-- the campaign's exposure. On such a level it was 13 stops too dim: a dark
-- room stayed black with it on (Pelican Warfare's bases, 2026-11-21).
--
-- EV is a power of two, so the light scale is log2(scale) stops: both
-- scalars are raised by that on the class's default object (every flashlight
-- made from then on) and on the flashlights already in the world. Setup
-- only: one write when a level is dressed, and restore() puts the game's own
-- values back when the level is left, so the campaign is never touched.
local Flashlight = {}

local CLASS = "/Game/_Prototypes/SynchronizationTestContent/Assets/Equipments/BP_Flashlight_EquipmentActor"
local FIELDS = { "SoftLightIntensityScalar", "PointLightIntensityScalar" }
local original          -- the game's own scalars, read once
local stops = 0         -- what is applied now

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

--- Raise the flashlight by log2(`scale`) stops (scale 1 leaves it alone).
function Flashlight.expose(scale, findObject, log)
    local extra = (type(scale) == "number" and scale > 1) and math.log(scale) / math.log(2) or 0
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
        if log then log(string.format("flashlight: %+.1f stops for the level's light scale", extra)) end
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

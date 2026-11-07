-- MJOLNIR HUD: where the flags are, in Capture the Flag and Assault.
--
-- No Megalo waypoint reaches Unreal (docs/game_modes.md, B4), so as with the
-- hill this draws its own marker. Assault needs one most: its flag changes base,
-- and nothing else says where it went.
--
-- A flag is an actor of the skull's class, so a marker follows it home, dropped
-- or carried. The simulation hands one actor to the next flag when Assault swaps
-- sides, so its team is read from the actor on every update, never kept. Actors
-- are only held to read this moment's place, and each is checked before use: a
-- stored actor crashes once it is freed.

local FlagMark = {}

local CLASS_PATH = "/Game/Weapons/Melee/Skull/Blueprints/BP_SkullActor.BP_SkullActor_C"
local CLASS = "BP_SkullActor_C"
local MESH_SYNC = { "/Script/BlamSynchronization.BlamMeshSynchronizationComponentBase",
    "/Script/BlamSynchronization.BlamMeshSynchronizationComponent",
    "/Script/BlamEngine.BlamMeshSynchronizationComponentBase" }

local EVERY = 0.2 -- seconds between updates
local HEIGHT_CM = 120 -- the badge, above the flag's origin
local NEAR_CM = 300 -- this close there is nothing to point at, and a carrier stands on it
local PARKED_CM = 1 -- an actor no object uses waits at the origin

--- Red or Blue from a model variant's name (docs/game_modes.md, 2.2): the blue
--- flag's tag is variant `blue`, and the red one is `default`.
function FlagMark.teamOf(variant)
    if type(variant) ~= "string" or variant == "" or variant == "None" then return nil end
    return string.lower(variant) == "blue" and "Blue" or "Red"
end

--- Whether a place is the origin, where an unused actor waits.
function FlagMark.parked(at)
    return math.abs(at.X) < PARKED_CM and math.abs(at.Y) < PARKED_CM and math.abs(at.Z) < PARKED_CM
end

-- Every flag actor since the mod started: the watch outlives a match, and an
-- actor of an old world fails its check and goes.
local actors, watching = {}, false

local function add(actor)
    local ok, name = pcall(function() return actor:GetFullName() end)
    if not ok or type(name) ~= "string" or name:find("Default__", 1, true) then return end
    local address = actor:GetAddress()
    for _, known in ipairs(actors) do
        if known.address == address then
            known.actor = actor
            return
        end
    end
    actors[#actors + 1] = { actor = actor, address = address }
end

local function watch()
    if watching then return end
    watching = pcall(NotifyOnNewObject, CLASS_PATH, add)
    if watching then
        for _, actor in ipairs(FindAllOf(CLASS) or {}) do add(actor) end
    end
end

local function syncClass()
    for _, path in ipairs(MESH_SYNC) do
        local class = StaticFindObject(path)
        if class and class:IsValid() then return class end
    end
    return nil
end

--- The model variant `actor` shows now, or nil.
local function variantOf(actor)
    local class = syncClass()
    if not class then return nil end
    for _, found in ipairs(actor:K2_GetComponentsByClass(class) or {}) do
        local c = type(found) == "userdata" and found.get and found:get() or found
        local ok, name = pcall(function() return c:GetVariantName():ToString() end)
        if ok then return name end
    end
    return nil
end

--- { Red = { x, y, z, r }, Blue = ... } for the flags out now. An actor gone
--- since the last look leaves the list.
local function flagsNow()
    local out = {}
    for i = #actors, 1, -1 do
        local actor = actors[i].actor
        if not actor:IsValid() then
            table.remove(actors, i)
        else
            local at = actor:K2_GetActorLocation()
            local team = FlagMark.teamOf(variantOf(actor))
            if team and not FlagMark.parked(at) then
                out[team] = { x = at.X, y = at.Y, z = at.Z, r = NEAR_CM }
            end
        end
    end
    return out
end

--- One match's markers. Scripts/hill.lua gives the drawing.
function FlagMark.new(Hill)
    local self = { next = 0 }
    local fields = { Red = Hill.field("mjolnir_flag_red"), Blue = Hill.field("mjolnir_flag_blue") }

    function self.hide()
        for _, field in pairs(fields) do field.unmark() end
    end

    function self.frame(pc, now)
        for _, field in pairs(fields) do field.frame(pc, now) end
    end

    function self.tick(now, pc, hidden)
        if now < self.next then return end
        self.next = now + EVERY
        if hidden then return self.hide() end
        pcall(function()
            watch()
            local pawn = pc.Pawn
            local at = pawn and pawn:IsValid() and pawn:K2_GetActorLocation() or nil
            local flags = flagsNow()
            for team, field in pairs(fields) do
                local flag = flags[team]
                local inside, metres, _, level = false, 0, nil, ""
                if flag and at then inside, metres, _, level = Hill.bearing(flag, at, 0) end
                if flag and at and not inside then
                    field.mark(pc, { x = flag.x, y = flag.y, z = flag.z + HEIGHT_CM }, team, "Ctf",
                        Hill.Waypoint and Hill.Waypoint.label(metres, level) or "", now)
                else
                    field.unmark()
                end
            end
        end)
    end

    return self
end

return FlagMark

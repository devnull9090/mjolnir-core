-- MJOLNIR HUD: where the flags are, in Capture the Flag and Assault, and
-- Oddball's ball (FlagMark.ball), which is the same skull actor.
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
--
-- Assault also says who attacks and when the sides swap, in a line under the
-- score. Its clock lives in the script and no Megalo number reaches Unreal, so
-- this counts its own: a swap is the flag changing team, by capture or by the
-- clock, and a side lasts the variant's time. The host counts from the first
-- flag; a player who joined late has no such start, so theirs begins at the first
-- swap they see.

local FlagMark = {}

local CLASS_PATH = "/Game/Weapons/Melee/Skull/Blueprints/BP_SkullActor.BP_SkullActor_C"
local CLASS = "BP_SkullActor_C"
local FP_CLASS = "BP_FP_SkullActor_C"
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

--- "3:42" for seconds left; a part second counts as a whole one.
function FlagMark.clock(seconds)
    local whole = math.max(0, math.ceil(seconds))
    return string.format("%d:%02d", math.floor(whole / 60), whole % 60)
end

--- Assault's line: the player's role against the defending team, and the time
--- to the next swap, either of which can be unknown. Nil when both are.
function FlagMark.sideLine(defender, mine, left)
    local role = mine and (mine == defender and "DEFEND" or "ATTACK") or nil
    local clock = left and ("SIDES SWAP IN " .. FlagMark.clock(left)) or nil
    if role and clock then return role .. "  /  " .. clock end
    return role or clock
end

-- Every flag actor since the mod started: the watch outlives a match, and an
-- actor of an old world fails its check and goes.
local actors, watching = {}, false

local function add(actor)
    local ok, name = pcall(function() return actor:GetFullName() end)
    if not ok or type(name) ~= "string" or name:find("Default__", 1, true) then return end
    local address = actor:GetAddress()
    -- The carrier's first-person copy stands at their camera: never a place.
    local fp = name:find(FP_CLASS, 1, true) ~= nil
    for _, known in ipairs(actors) do
        if known.address == address then
            known.actor, known.fp = actor, fp
            return
        end
    end
    actors[#actors + 1] = { actor = actor, address = address, fp = fp }
end

local function watch()
    if watching then return end
    watching = pcall(NotifyOnNewObject, CLASS_PATH, add)
    if watching then
        for _, actor in ipairs(FindAllOf(CLASS) or {}) do add(actor) end
    end
end

--- The mesh synchronization class, found once and kept: StaticFindObject
--- costs about 1 ms, and this was one a flag (or the ball) every 0.2 s. When no
--- path resolves, it waits before trying the paths again.
local SYNC_RETRY_SECONDS = 5
local meshSync, syncRetryAt = nil, nil
local function syncClass()
    if meshSync and meshSync:IsValid() then return meshSync end
    meshSync = nil
    local t = os.clock()
    if syncRetryAt and t < syncRetryAt then return nil end
    for _, path in ipairs(MESH_SYNC) do
        local class = StaticFindObject(path)
        if class and class:IsValid() then
            meshSync, syncRetryAt = class, nil
            return class
        end
    end
    syncRetryAt = t + SYNC_RETRY_SECONDS
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

--- The simulation object an actor shows (BlamObjectSynchronizationComponent's
--- BlamObjectIndex) as an unsigned handle, or nil.
local OBJECT_SYNC = "/Script/BlamSynchronization.BlamObjectSynchronizationComponent"
local objectSync
local function objectOf(actor)
    local ok, index = pcall(function()
        if not (objectSync and objectSync:IsValid()) then objectSync = StaticFindObject(OBJECT_SYNC) end
        return actor:GetComponentByClass(objectSync).BlamObjectIndex
    end)
    if ok and type(index) == "number" and index ~= -1 then return index % 4294967296 end
    return nil
end

--- Whether handle `a` is a later object than `b` in the same slot of the
--- object table: the salt (its high half) counts up each time the slot is
--- reused, and wraps.
function FlagMark.newer(a, b)
    if not (a and b) or a % 65536 ~= b % 65536 then return false end
    local sa, sb = math.floor(a / 65536), math.floor(b / 65536)
    return sa ~= sb and (sa - sb) % 65536 < 32768
end

--- { Red = { x, y, z, r }, Blue = ... } for the flags out now. An actor gone
--- since the last look leaves the list. A fireteam client can keep the actor
--- of a flag the simulation deleted where it last stood, still showing its
--- colour, while the next flag takes the same slot (Assault on two PCs,
--- 2026-11-07: a second, blue marker at the stand just captured from). An
--- actor whose slot holds a later object is that leftover, and not a flag.
--- Every skull actor out now, but first-person copies: { actor, at, object,
--- team } (team from its model variant, nil without one). An actor gone
--- since the last look leaves the list, and so does one whose slot holds a
--- later object.
local function skullsNow()
    local found = {}
    for i = #actors, 1, -1 do
        local entry = actors[i]
        local actor = entry.actor
        if not actor:IsValid() then
            table.remove(actors, i)
        elseif not entry.fp then
            local at = actor:K2_GetActorLocation()
            if not FlagMark.parked(at) then
                found[#found + 1] = { actor = actor, at = at, object = objectOf(actor),
                    team = FlagMark.teamOf(variantOf(actor)) }
            end
        end
    end
    local out = {}
    for _, skull in ipairs(found) do
        local superseded = false
        for _, other in ipairs(found) do
            if FlagMark.newer(other.object, skull.object) then superseded = true end
        end
        if not superseded then out[#out + 1] = skull end
    end
    return out
end

local function spot(skull)
    return { x = skull.at.X, y = skull.at.Y, z = skull.at.Z, r = NEAR_CM, actor = skull.actor }
end

local function flagsNow()
    local out = {}
    for _, skull in ipairs(skullsNow()) do
        if skull.team then out[skull.team] = spot(skull) end
    end
    return out
end

--- One match's markers. Scripts/hill.lua gives the drawing. `side` is Assault's:
--- { seconds = a side's length, host = whether this machine is the host }.
function FlagMark.new(Hill, side)
    local self = { next = 0 }
    local fields = { Red = Hill.field("mjolnir_flag_red"), Blue = Hill.field("mjolnir_flag_blue") }
    local line = fields.Red -- one line, on either field

    function self.hide()
        for _, field in pairs(fields) do
            field.track(nil)
            field.unmark()
        end
        line.hideLine()
    end

    function self.frame(pc, now)
        for _, field in pairs(fields) do field.frame(pc, now) end
    end

    --- Assault's line. Only one flag is out, and its team defends. Between a
    --- flag going and the next being made there is none: keep what was said.
    local function sayRole(now, pc, flags, mine)
        local defender = flags.Red and "Red" or flags.Blue and "Blue" or nil
        if defender and defender ~= self.defender then
            if self.defender or side.host then self.swapAt = now + side.seconds end
            self.defender = defender
        end
        if not self.defender then return end
        local words = FlagMark.sideLine(self.defender, mine, self.swapAt and self.swapAt - now or nil)
        if words then
            line.ensureLine(pc)
            line.say(words)
        else
            line.hideLine()
        end
    end

    --- `mine` is the local player's team, Red or Blue, nil before it is known.
    function self.tick(now, pc, hidden, mine)
        if now < self.next then return end
        self.next = now + EVERY
        if hidden then return self.hide() end
        pcall(function()
            watch()
            local pawn = pc.Pawn
            local at = pawn and pawn:IsValid() and pawn:K2_GetActorLocation() or nil
            local flags = flagsNow()
            if side then sayRole(now, pc, flags, mine) end
            for team, field in pairs(fields) do
                local flag = flags[team]
                local inside, metres, _, level = false, 0, nil, ""
                if flag and at then inside, metres, _, level = Hill.bearing(flag, at, 0) end
                if flag and at and not inside then
                    field.mark(pc, { x = flag.x, y = flag.y, z = flag.z + HEIGHT_CM }, team, "Ctf",
                        Hill.Waypoint and Hill.Waypoint.label(metres, level) or "", now)
                    field.track(flag.actor, HEIGHT_CM)
                else
                    field.track(nil)
                    field.unmark()
                end
            end
        end)
    end

    return self
end

--- Whether a skull actor hangs off another actor: a carrier.
local function carried(actor)
    local ok, parent = pcall(function() return actor:GetAttachParentActor() end)
    return ok and parent ~= nil and parent:IsValid()
end

--- Oddball's ball: one marker, on the ball loose (gold) or carried (the
--- carrier's colour: orange), and none on the carrier's own screen, where it
--- is in their hands. Nothing else says where the ball is: the variant's
--- waypoint never reaches Unreal (#352).
function FlagMark.ball(Hill)
    local self = { next = 0 }
    local field = Hill.field("mjolnir_ball")

    function self.hide()
        field.track(nil)
        field.unmark()
    end

    function self.frame(pc, now)
        field.frame(pc, now)
    end

    --- The ball now, as { x, y, z, r, actor, carried }, or nil.
    function self.find()
        local skulls = skullsNow()
        local ball = skulls[1]
        if not ball then return nil end
        local out = spot(ball)
        out.carried = carried(ball.actor)
        return out
    end

    function self.tick(now, pc, hidden)
        if now < self.next then return end
        self.next = now + EVERY
        if hidden then return self.hide() end
        pcall(function()
            watch()
            local pawn = pc.Pawn
            local at = pawn and pawn:IsValid() and pawn:K2_GetActorLocation() or nil
            local ball = self.find()
            local inside, metres, _, level = false, 0, nil, ""
            if ball and at then inside, metres, _, level = Hill.bearing(ball, at, 0) end
            if not (ball and at) or inside then return self.hide() end
            field.mark(pc, { x = ball.x, y = ball.y, z = ball.z + HEIGHT_CM }, ball.carried and "other" or "empty",
                "Oddball", Hill.Waypoint and Hill.Waypoint.label(metres, level) or "", now)
            field.track(ball.actor, HEIGHT_CM)
        end)
    end

    return self
end

return FlagMark

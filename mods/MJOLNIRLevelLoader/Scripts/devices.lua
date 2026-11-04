-- MJOLNIR Level Loader: a converted map's scripted devices
--
-- A CE gate or shield is a machine of the simulation's own, cloned from B40's
-- elevator (tools/level/ce_machines.py). The simulation moves it and its
-- collision on every machine in the game and Unreal draws an elevator there;
-- this module hides the elevator and rides the map's own mesh (decor, spawned
-- by main.lua) on the part that moves, so a gate needs nothing per frame.
--
-- The level's `devices` list: { name, class, pos (Unreal cm from the canvas
-- origin), decor (ids), shield }. A machine's actor stays where it was placed
-- and its part moves. A joiner can arrive with a part away from its rest, so
-- each mesh is first shifted by the part's offset, then attached keeping that
-- pose.
--
-- A shield parks under the map at position 0, and the game stops updating an
-- actor it has hidden there, part and position with it, so a mesh riding it
-- would stay up with its collision gone. Its mesh shows only while the actor
-- is shown and at home (`shows`).
--
-- Plain helpers (shifted, near, shows) run under stock Lua in
-- tools/tests/test_devices.lua; nothing touches UE4SS before init.

local Devices = {}

--- How far an actor can stand from its placement and still be that device.
Devices.NEAR_CM = 30

--- How often the actors of unbound devices are scanned for, in seconds.
Devices.SCAN_S = 2

local env
local state = { bound = {}, level = nil, done = false, scanned = 0 }

--- `rest` moved by how far `part` is from `base`.
function Devices.shifted(rest, part, base)
    return { X = rest.X + part.X - base.X, Y = rest.Y + part.Y - base.Y, Z = rest.Z + part.Z - base.Z }
end

--- Whether two { X, Y, Z } points are the same place.
function Devices.near(a, b)
    return Devices.distance(a, b) < Devices.NEAR_CM
end

--- How far apart two { X, Y, Z } points are, as `near` measures it.
function Devices.distance(a, b)
    return math.abs(a.X - b.X) + math.abs(a.Y - b.Y) + math.abs(a.Z - b.Z)
end

--- Whether a shield's mesh shows, from its actor's hidden flag and position.
function Devices.shows(hidden, position)
    return not hidden and position > 0.5
end

local function bind(device, actor)
    local mesh = StaticFindObject("/Script/Engine.StaticMeshComponent")
    local part = actor:K2_GetComponentsByClass(mesh)[1]:get()
    if not part or not part:IsValid() then return false end
    local p, b = part:K2_GetComponentLocation(), actor:K2_GetActorLocation()
    for _, id in ipairs(device.decor) do
        local item = env.Current.actors[id]
        if not (item and item:IsValid()) then return false end
    end
    for _, id in ipairs(device.decor) do
        local item = env.Current.actors[id]
        item:K2_SetActorLocation(Devices.shifted(item:K2_GetActorLocation(), p, b), false, env.Current.hit or {}, false)
        item:K2_AttachToComponent(part, FName("None"), 1, 1, 1, true)
    end
    part:SetVisibility(false, false)
    return true
end

--- Show or hide a bound shield's mesh, when that changes.
local function shield(device, bound)
    if not bound.actor:IsValid() then return end
    local class = StaticFindObject("/Script/BlamSynchronization.BlamDeviceComponent")
    local component = bound.actor:GetComponentByClass(class)
    local want = Devices.shows(bound.actor.bHidden, component:GetPositionFraction())
    if want == bound.shown then return end
    bound.shown = want
    for _, id in ipairs(device.decor) do
        local item = env.Current.actors[id]
        if item and item:IsValid() then item:SetActorHiddenInGame(not want) end
    end
end

--- Scan for the devices not bound yet, a class at a time, and stop once all
--- are: FindAllOf costs about 20 ms. Bound shields are polled every tick.
function Devices.tick()
    if not env then return end
    local level = env.Current.level
    if level ~= state.level then state.level, state.bound, state.done, state.scanned = level, {}, false, 0 end
    if type(level) ~= "table" or type(level.devices) ~= "table" then return end
    for i, device in ipairs(level.devices) do
        if device.shield and state.bound[i] then pcall(shield, device, state.bound[i]) end
    end
    if state.done or os.time() - state.scanned < Devices.SCAN_S then return end
    state.scanned = os.time()
    local origin = (level.canvas and level.canvas.origin) or { 0, 0, 0 }
    local scans, left, taken = {}, 0, {}
    for _, bound in pairs(state.bound) do
        if bound.actor:IsValid() then taken[bound.actor:GetAddress()] = true end
    end
    for i, device in ipairs(level.devices) do
        if not state.bound[i] then
            left = left + 1
            scans[device.class] = scans[device.class] or FindAllOf(device.class) or {}
            local want = { X = origin[1] + device.pos[1], Y = origin[2] + device.pos[2], Z = origin[3] + device.pos[3] }
            -- A door's parts stand centimetres apart, so the nearest actor
            -- not yet taken is this device's.
            local best, distance
            for _, actor in ipairs(scans[device.class]) do
                local ok, at = pcall(function() return actor:K2_GetActorLocation() end)
                if ok and not taken[actor:GetAddress()] and Devices.near(at, want) then
                    local d = Devices.distance(at, want)
                    if not best or d < distance then best, distance = actor, d end
                end
            end
            local ok, done = pcall(function() return best and bind(device, best) end)
            if ok and done then
                taken[best:GetAddress()] = true
                state.bound[i], left = { actor = best }, left - 1
                env.Log(string.format("device %s rides its machine", tostring(device.name)))
            end
        end
    end
    state.done = left == 0
end

function Devices.init(deps)
    env = deps
end

return Devices

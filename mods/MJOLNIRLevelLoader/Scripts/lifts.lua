-- MJOLNIR Level Loader: Halo 2's lifts, jump pads and vents (#235)
--
-- In Halo 2 a gravity lift is a prop whose physics model carries phantoms:
-- shapes that push what enters them along a marker. The simulation our maps
-- run on has none, so the conversion writes each phantom into the level file
-- (`lifts`, from crate::h2::phantom via tools/level/gen_ce_level.py) and this
-- module pushes players with it, setting their velocity through Blam script
-- ((object_set_velocity (player_get N) forward left up), world units per
-- second in the unit's facing frame).
--
-- Each game pushes its own players only: a player's motion is the game
-- that controls it (two PCs, 2026-10-25: a push the host sends a joiner's
-- unit does nothing, and the joiner's own push reaches the host).
--
-- A phantom (Unreal centimetres, relative to canvas.origin): its shape
-- ("planes", n.p + d <= 0 inside, or "pill" ends and "radius"), "bounds"
-- (x, y, z, r), the marker it pushes from ("origin") and along ("forward"),
-- and acceleration and top speed pairs: "direction" (along forward), "axis"
-- (towards the line through origin along forward), "center" (towards
-- origin). "negates_gravity" holds the player up while inside.
--
-- Plain helpers (inside, push, toUnit) run under stock Lua in
-- tools/tests/test_lifts.lua; nothing touches UE4SS before init.

local Lifts = {}

--- The simulation's gravity, cm/s^2 (CE's 0.0035651 world units per tick
--- squared at 30 ticks a second; a pushed biped's GetVelocity loses
--- about this much between pushes).
Lifts.GRAVITY = 978
--- How often a player near a lift is pushed, and how near is near.
Lifts.FAST_MS = 50
Lifts.NEAR_CM = 300

local CM_PER_WU = 304.8

local function dot(a, b) return a[1] * b[1] + a[2] * b[2] + a[3] * b[3] end

--- Whether point `p` ({x, y, z}) is inside a phantom's shape.
function Lifts.inside(lift, p)
    if type(lift.planes) == "table" then
        for _, n in ipairs(lift.planes) do
            if n[1] * p[1] + n[2] * p[2] + n[3] * p[3] + n[4] > 0 then return false end
        end
        return true
    end
    if type(lift.pill) == "table" then
        local a, b = lift.pill[1], lift.pill[2]
        local ab = { b[1] - a[1], b[2] - a[2], b[3] - a[3] }
        local ap = { p[1] - a[1], p[2] - a[2], p[3] - a[3] }
        local len2 = dot(ab, ab)
        local t = len2 > 0 and math.max(0, math.min(1, dot(ap, ab) / len2)) or 0
        local d = { ap[1] - ab[1] * t, ap[2] - ab[2] * t, ap[3] - ab[3] * t }
        return dot(d, d) <= lift.radius * lift.radius
    end
    return false
end

--- Whether `p` is within `margin` of a phantom's bounding sphere.
function Lifts.near(lift, p, margin)
    local b = lift.bounds
    if type(b) ~= "table" then return true end
    local d = { p[1] - b[1], p[2] - b[2], p[3] - b[3] }
    local r = b[4] + margin
    return dot(d, d) <= r * r
end

--- Speed `v` gains towards unit direction `u`, at `acc` up to `max`, over `dt`.
local function towards(v, u, acc, max, dt)
    if not (acc and acc > 0 and max) then return end
    local along = dot(v, u)
    if along >= max then return end
    local dv = math.min(acc * dt, max - along)
    v[1], v[2], v[3] = v[1] + u[1] * dv, v[2] + u[2] * dv, v[3] + u[3] * dv
end

--- The unit vector along `diff` and its length; nil under a centimetre.
local function heading(diff)
    local len = math.sqrt(dot(diff, diff))
    if len < 1 then return nil end
    return { diff[1] / len, diff[2] / len, diff[3] / len }, len
end

--- The velocity (cm/s) a player at `p` moving at `v` has after `dt` seconds
--- in phantom `lift` (gravity aside: see Lifts.sent). Speeds towards the
--- axis or centre are capped so the player slows into it rather than
--- overshooting. `last`, the velocity this push meant one step ago (if it
--- pushed), carries the speed along the push: a biped on the ground reads
--- still after a small push (the ground holds it), so without it a lift
--- never lifts anyone standing.
function Lifts.push(lift, p, v, dt, last)
    v = { v[1], v[2], v[3] }
    local o, f = lift.origin, lift.forward
    local rel = { p[1] - o[1], p[2] - o[2], p[3] - o[3] }
    if last then
        local carry = dot(last, f) - (lift.negates_gravity and 0 or Lifts.GRAVITY * dt * f[3])
        local along = dot(v, f)
        if carry > along then
            v[1], v[2], v[3] = v[1] + f[1] * (carry - along), v[2] + f[2] * (carry - along), v[3] + f[3] * (carry - along)
        end
    end
    local d = lift.direction
    if d then towards(v, f, d[1], d[2], dt) end
    local a = lift.axis
    if a and a[1] > 0 then
        local along = dot(rel, f)
        local u, len = heading({ -(rel[1] - f[1] * along), -(rel[2] - f[2] * along), -(rel[3] - f[3] * along) })
        if u then towards(v, u, a[1], math.min(a[2], len / (2 * dt)), dt) end
    end
    local c = lift.center
    if c and c[1] > 0 then
        local u, len = heading({ -rel[1], -rel[2], -rel[3] })
        if u then towards(v, u, c[1], math.min(c[2], len / (2 * dt)), dt) end
    end
    return v
end

--- What to send for intended velocity `v`: a phantom that negates gravity
--- adds back what the simulation's gravity takes before the next push.
function Lifts.sent(v, negates, dt)
    return negates and { v[1], v[2], v[3] + Lifts.GRAVITY * dt } or v
end

--- An Unreal velocity (cm/s) as object_set_velocity's forward, left and up
--- (world units per second) for a unit facing Unreal yaw `yaw` (degrees).
--- Unreal's Y is Halo's -y, so its left is (sin, -cos).
function Lifts.toUnit(v, yaw)
    local r = math.rad(yaw)
    local c, s = math.cos(r), math.sin(r)
    return (v[1] * c + v[2] * s) / CM_PER_WU, (v[1] * s - v[2] * c) / CM_PER_WU, v[3] / CM_PER_WU
end

local env
local state = { world = nil, seeded = false, bipeds = {}, watched = false, fast = false, idle = 0, inside = {}, pushed = {} }

local SPARTAN = "/Game/_Prototypes/SynchronizationTestContent/TestActor/BP_SpartansBipedActor.BP_SpartansBipedActor_C"
local unitClass

local function remember(actor)
    local ok, key = pcall(function() return actor:GetAddress() end)
    if ok and key then state.bipeds[key] = actor end
end

--- This game's own players' bipeds: those whose controlling player has a
--- pawn here. Each as {actor, index}.
local function localBipeds()
    unitClass = unitClass or StaticFindObject("/Script/BlamSynchronization.BlamUnitComponent")
    local out = {}
    for key, actor in pairs(state.bipeds) do
        if not (actor and actor:IsValid()) then
            state.bipeds[key] = nil
        else
            pcall(function()
                local unit = actor:GetComponentByClass(unitClass)
                if not unit:IsControlledByAnyPlayer() then return end
                local pawn = unit:TryAndGetControllingPlayerPawn()
                if not (pawn and pawn:IsValid() and pawn:IsLocallyControlled()) then return end
                local datum = unit:GetControllingPlayerDatumIndex()
                if type(datum) == "number" and datum ~= -1 then
                    out[#out + 1] = { actor = actor, index = math.floor(datum % 65536) }
                end
            end)
        end
    end
    return out
end

local function levelLifts()
    local level = env.Current.level
    return level and type(level.lifts) == "table" and #level.lifts > 0 and level.lifts or nil, level
end

local function origin(level)
    local o = (level.canvas or {}).origin or { 0, 0, 0 }
    return o[1] or 0, o[2] or 0, o[3] or 0
end

--- One fast step: push every local player inside a phantom. True while any
--- is near a lift.
local function step(lifts, level, dt)
    local ox, oy, oz = origin(level)
    local lines, near = {}, false
    for _, b in ipairs(localBipeds()) do
        local okL, at = pcall(function() return b.actor:K2_GetActorLocation() end)
        if okL and at then
            local p = { at.X - ox, at.Y - oy, at.Z - oz }
            local v, which, negates
            for k, lift in ipairs(lifts) do
                if Lifts.near(lift, p, Lifts.NEAR_CM) then
                    near = true
                    if Lifts.inside(lift, p) then
                        if not v then
                            local okV, vel = pcall(function() return b.actor:GetVelocity() end)
                            v = okV and vel and { vel.X, vel.Y, vel.Z } or { 0, 0, 0 }
                        end
                        v = Lifts.push(lift, p, v, dt, state.pushed[b.index])
                        which = which or k
                        negates = negates or lift.negates_gravity
                    end
                end
            end
            if which ~= state.inside[b.index] then
                env.Log(which and string.format("lifts: player %d in phantom %d (%s) at (%.0f, %.0f, %.0f)", b.index, which,
                    tostring(lifts[which].asset):match("[^\\]+$") or "?", p[1], p[2], p[3])
                    or string.format("lifts: player %d left the lift at (%.0f, %.0f, %.0f)", b.index, p[1], p[2], p[3]))
                state.inside[b.index] = which
            end
            state.pushed[b.index] = v
            if v then
                local okR, rot = pcall(function() return b.actor:K2_GetActorRotation() end)
                local f, l, u = Lifts.toUnit(Lifts.sent(v, negates, dt), okR and rot and rot.Yaw or 0)
                lines[#lines + 1] = string.format("(object_set_velocity (player_get %d) %.3f %.3f %.3f)", b.index, f, l, u)
            end
        end
    end
    if #lines > 0 then env.Script.send(lines) end
    return near
end

local function fast()
    local lifts, level = levelLifts()
    if not lifts then
        state.fast = false
        return
    end
    local ok, near = pcall(step, lifts, level, Lifts.FAST_MS / 1000)
    if not ok then
        env.Log("lifts: " .. tostring(near))
        state.fast = false
        return
    end
    state.idle = near and 0 or state.idle + 1
    if state.idle > 20 then
        state.fast = false
        return
    end
    ExecuteInGameThreadWithDelay(Lifts.FAST_MS, fast)
end

--- MJOLNIRLevelLoader's half-second loop: watch for a local player near a
--- lift, and push at FAST_MS while one is.
function Lifts.tick()
    if not env then return end
    local lifts = levelLifts()
    if not lifts then return end
    local world = env.getWorld()
    if not world then return end
    local okA, address = pcall(function() return world:GetAddress() end)
    if not okA then return end
    if address ~= state.world then
        state.world, state.seeded, state.bipeds, state.inside, state.pushed = address, false, {}, {}, {}
    end
    if not state.watched then state.watched = pcall(NotifyOnNewObject, SPARTAN, remember) end
    if not state.seeded then
        state.seeded = true
        for _, actor in ipairs(FindAllOf("BP_SpartansBipedActor_C") or {}) do remember(actor) end
        env.Log(string.format("lifts: %d phantom(s) on %s", #lifts, tostring(env.Current.scenario)))
    end
    if state.fast then return end
    local level = env.Current.level
    local ox, oy, oz = origin(level)
    for _, b in ipairs(localBipeds()) do
        local okL, at = pcall(function() return b.actor:K2_GetActorLocation() end)
        if okL and at then
            local p = { at.X - ox, at.Y - oy, at.Z - oz }
            for _, lift in ipairs(lifts) do
                if Lifts.near(lift, p, Lifts.NEAR_CM * 3) then
                    state.fast, state.idle = true, 0
                    ExecuteInGameThreadWithDelay(Lifts.FAST_MS, fast)
                    return
                end
            end
        end
    end
end

--- `deps`: Log, getWorld, Current, Script (sim_script.lua).
function Lifts.init(deps)
    env = deps
end

return Lifts

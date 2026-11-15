-- MJOLNIR Level Loader: Halo 2's lifts, jump pads and vents (#235)
--
-- In Halo 2 a gravity lift is a prop whose physics model carries phantoms:
-- shapes that push what enters them along a marker. The simulation our maps
-- run on has none, so the conversion writes each phantom into the level file
-- (`lifts`, from crate::h2::phantom via tools/level/gen_ce_level.py), a Forge
-- pack block can carry one (pack_lifts.lua), and MJOLNIRLobby's DLL pushes
-- each of this game's own players through them on the simulation thread,
-- every tick (native/lobby/lifts_runtime.h). This module only hands the DLL
-- the running map's phantoms, in the simulation's units, when they change:
-- a converted level's once a map, a Forge pack's when a piece moves.
--
-- A phantom here (Unreal centimetres, relative to canvas.origin): its shape
-- ("planes", n.p + d <= 0 inside, or "pill" ends and "radius"), "bounds"
-- (x, y, z, r), the marker it pushes from ("origin") and along ("forward"),
-- and acceleration and top speed pairs: "direction" (along forward), "axis"
-- (towards the line through origin along forward), "center" (towards
-- origin). "negates_gravity" holds the player up while inside.
--
-- Plain helpers (toSim, serialize) run under stock Lua in
-- tools/tests/test_lifts.lua; nothing touches UE4SS before init.

local Lifts = {}

--- The simulation's world unit in Unreal centimetres.
Lifts.CM_PER_WU = 304.8
--- What the DLL reads: native/lobby/lifts_core.h has the form.
Lifts.FILE, Lifts.EXPORT = "lifts.txt", "mjolnir_sim_lifts"
Lifts.EMPTY = "mjolnir-lifts 1\nend\n"
--- The DLL's limits (LIFT_MAX, LIFT_MAX_PLANES, LIFT_PLANE_POOL).
Lifts.MAX, Lifts.MAX_PLANES, Lifts.PLANE_POOL = 128, 256, 4096

local WU = Lifts.CM_PER_WU

local function finite(n) return type(n) == "number" and n == n and n > -math.huge and n < math.huge end

local function vector(v, n)
    if type(v) ~= "table" then return false end
    for i = 1, n do if not finite(v[i]) then return false end end
    return true
end

-- The simulation's world is Unreal's at WU centimetres a unit, its y
-- Unreal's -Y; a level's positions are relative to its canvas origin.
local function point(p, o)
    return { (p[1] + o[1]) / WU, -(p[2] + o[2]) / WU, (p[3] + o[3]) / WU }
end

local function pair(v)
    if not vector(v, 2) then return { 0, 0 } end
    return { v[1] / WU, v[2] / WU }
end

--- A plain name for the DLL's log: the asset's last path part.
function Lifts.name(asset)
    local name = tostring(asset or "lift"):match("[^\\/]+$") or "lift"
    name = name:gsub("[^%w_%.%-]", "_"):sub(1, 47)
    return name ~= "" and name or "lift"
end

--- Phantom `lift` (Unreal cm, relative to canvas origin `origin`) in the
--- simulation's units: world units, per second, its y flipped. Nil and why
--- for one the DLL could not use.
function Lifts.toSim(lift, origin)
    local o = vector(origin, 3) and origin or { 0, 0, 0 }
    if type(lift) ~= "table" then return nil, "not a phantom" end
    if not (vector(lift.origin, 3) and vector(lift.forward, 3) and vector(lift.bounds, 4)) then
        return nil, "no origin, forward or bounds"
    end
    local f = lift.forward
    local length = math.sqrt(f[1] * f[1] + f[2] * f[2] + f[3] * f[3])
    if length < 0.99 or length > 1.01 then return nil, "forward is not a unit vector" end
    local b = point(lift.bounds, o)
    local out = {
        name = Lifts.name(lift.asset), negates = lift.negates_gravity and true or false,
        origin = point(lift.origin, o), forward = { f[1] / length, -f[2] / length, f[3] / length },
        bounds = { b[1], b[2], b[3], lift.bounds[4] / WU },
        direction = pair(lift.direction), axis = pair(lift.axis), center = pair(lift.center),
    }
    if type(lift.planes) == "table" then
        if #lift.planes < 1 or #lift.planes > Lifts.MAX_PLANES then return nil, "too many planes" end
        out.planes = {}
        for i, n in ipairs(lift.planes) do
            if not vector(n, 4) then return nil, "plane " .. i .. " is not four numbers" end
            -- n.(p_rel) + d with p_rel = p_sim*WU (y flipped) - origin.
            out.planes[i] = { n[1], -n[2], n[3], (n[4] - (n[1] * o[1] + n[2] * o[2] + n[3] * o[3])) / WU }
        end
    elseif type(lift.pill) == "table" and vector(lift.pill[1], 3) and vector(lift.pill[2], 3) and finite(lift.radius)
        and lift.radius > 0 then
        out.pill = { point(lift.pill[1], o), point(lift.pill[2], o), lift.radius / WU }
    else
        return nil, "no planes or pill"
    end
    return out
end

local function numbers(v)
    local parts = {}
    for i = 1, #v do parts[i] = string.format("%.6f", v[i]) end
    return table.concat(parts, " ")
end

--- One converted phantom's lines (each ending in a newline).
function Lifts.record(s)
    local head = string.format("lift %s %d %s %s %s %s %s %s", s.name, s.negates and 1 or 0, numbers(s.origin),
        numbers(s.forward), numbers(s.bounds), numbers(s.direction), numbers(s.axis), numbers(s.center))
    if s.pill then
        return head .. " pill " .. numbers(s.pill[1]) .. " " .. numbers(s.pill[2]) .. " " .. numbers({ s.pill[3] }) .. "\n"
    end
    local lines = { head .. " planes " .. #s.planes }
    for i, n in ipairs(s.planes) do lines[i + 1] = "plane " .. numbers(n) end
    return table.concat(lines, "\n") .. "\n"
end

--- The records for phantoms `lifts` (Unreal cm, canvas origin `origin`),
--- within the DLL's limits counting `used` ({count, planes}, updated) records
--- already in the file. `skipped(reason, lift)` hears of each left out.
function Lifts.records(lifts, origin, used, skipped)
    local records = {}
    for _, lift in ipairs(lifts or {}) do
        local s, why = Lifts.toSim(lift, origin)
        if s and used.count >= Lifts.MAX then s, why = nil, "more phantoms than the DLL holds" end
        if s and s.planes and used.planes + #s.planes > Lifts.PLANE_POOL then s, why = nil, "more planes than the DLL holds" end
        if s then
            used.count, used.planes = used.count + 1, used.planes + (s.planes and #s.planes or 0)
            records[#records + 1] = Lifts.record(s)
        elseif skipped then
            skipped(why, lift)
        end
    end
    return table.concat(records)
end

--- The DLL's whole file for `lifts`, and how many phantoms it holds.
function Lifts.serialize(lifts, origin, skipped)
    local used = { count = 0, planes = 0 }
    local records = Lifts.records(lifts, origin, used, skipped)
    return "mjolnir-lifts 1\n" .. records .. "end\n", used.count
end

local env
local state = { world = nil, level = nil, sent = Lifts.EMPTY, count = 0, refused = false, fixed = nil }

local function canvasOrigin(level)
    local o = level and level.canvas and level.canvas.origin
    return vector(o, 3) and o or { 0, 0, 0 }
end

local function leftOut(why, lift)
    env.Log(string.format("lifts: %s left out: %s", Lifts.name(lift and lift.asset), why))
end

--- Hand the DLL `text` unless it already has it.
local function ship(text, count, scenario)
    if text == state.sent or state.refused then return end
    if not env.Script.request(Lifts.FILE, Lifts.EXPORT, text) then
        state.refused = true
        env.Log("lifts: MJOLNIRLobby 0.25.0 or newer pushes players through lifts; this one cannot")
        return
    end
    if count > 0 then
        env.Log(string.format("lifts: %d phantom(s) on %s handed to the simulation", count, tostring(scenario)))
    elseif state.count > 0 then
        env.Log("lifts: the simulation has none now")
    end
    state.sent, state.count = text, count
end

--- MJOLNIRLevelLoader's half-second loop: give the DLL this map's phantoms
--- when they change, and none once the map is gone.
function Lifts.tick()
    if not env then return end
    local world = env.getWorld()
    local ok, address = pcall(function() return world and world:GetAddress() end)
    local level = env.Current.level
    if not ok or not address then
        state.world, state.level = nil, nil
        ship(Lifts.EMPTY, 0, nil)
        return
    end
    local packs = env.PackLifts
    if address ~= state.world or level ~= state.level then
        -- A converted level's phantoms are fixed: write their records once.
        state.world, state.level = address, level
        if packs then packs:refresh() end
        local used = { count = 0, planes = 0 }
        local records = Lifts.records(level and level.lifts, canvasOrigin(level), used, leftOut)
        state.fixed = { records = records, count = used.count, planes = used.planes }
    elseif not (packs and packs:active()) then
        return
    end
    -- A Forge pack's follow their pieces, so they are read again each time.
    local fixed = state.fixed
    local used = { count = fixed.count, planes = fixed.planes }
    local moving = ""
    if packs and packs:active() then
        moving = Lifts.records(packs:collect(world, level and level.canvas and level.canvas.origin),
            canvasOrigin(level), used, nil)
    end
    ship("mjolnir-lifts 1\n" .. fixed.records .. moving .. "end\n", used.count, env.Current.scenario)
end

--- `deps`: Log, getWorld, Current, Script (sim_script.lua), PackLifts.
function Lifts.init(deps)
    env = deps
end

return Lifts

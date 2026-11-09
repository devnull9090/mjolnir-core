-- MJOLNIR HUD: every biped actor the game makes, as it is made.
--
-- The bots (Scripts/bots.lua) need the AI bipeds a placement brings out of the
-- game's pools, and the HUD (main.lua's findBipeds) needs the players' bipeds
-- that no incident named. Both found them with FindAllOf, which walks the whole
-- object array: about 23 ms a class in a match. The bots' seven classes held
-- one poll about 160 ms three seconds into every hosted match with bots, and up
-- to three times more when a placement went unseen. The players' two classes
-- cost 30-46 ms, again every 2 s while no Spartan had been seen. PC 1's hitch
-- logs had Hud tick runs of 50-129 ms on most maps (2026-11-06 to 11-08).
--
-- So one NotifyOnNewObject, armed when the mod loads, before any map, watches
-- the native class every biped Blueprint derives from. It sees each biped actor
-- as it is made: the pools a map makes as it loads, a player's spawn, a pool
-- that grows. A Blueprint class's own path is no good for that: it can only be
-- watched once it is loaded, and a Blueprint class can be unloaded and loaded
-- again between maps at a new address, which leaves a watch on it blind
-- (Scripts/class_lifetime.lua has the same trouble with widget classes).
--
-- A handle is kept by address and checked before every use: a stored actor
-- crashes the game once it is freed, and pcall cannot catch that.
--
-- Runs under stock Lua in tools/tests/test_bipeds.lua, with the UE4SS calls
-- stubbed; nothing touches UE4SS until `arm`.

local Bipeds = {}

--- The biped Blueprints, by class name. Spartans and Elites are the players'
--- bodies too; every one of them can be a bot's (bots.lua).
Bipeds.CLASSES = {
    "BP_SpartansBipedActor_C", "BP_EliteBipedActor_C", "BP_GruntBipedActor_C", "BP_JackalBipedActor_C",
    "BP_BruteBipedActor_C", "BP_MaleMarineBipedActor_C", "BP_FemaleMarineBipedActor_C",
}

--- The native class every biped Blueprint derives from. NotifyOnNewObject
--- reports objects of a class and of every class derived from it, and a native
--- class is never unloaded.
Bipeds.ANCESTOR = "/Script/BlamSynchronization.BlamObjectActor"

local wanted = {}
for _, name in ipairs(Bipeds.CLASSES) do wanted[name] = true end

local known = {} -- class name -> { [address] = actor }
for name in pairs(wanted) do known[name] = {} end
local armed = false

--- How far up a class's parents a biped Blueprint is looked for: FindAllOf,
--- which this replaces, counted a Blueprint derived from one of them too.
local MAX_PARENTS = 4

--- Which of CLASSES a class is or derives from, or false, by class name.
--- `parents(name)` gives the names of a class and its parents in order. Each
--- name is resolved once, the first time an object of it is made.
local resolved = {}
function Bipeds.resolve(name, parents)
    local r = resolved[name]
    if r ~= nil then return r end
    r = false
    for i, parent in ipairs(parents(name)) do
        if i > MAX_PARENTS + 1 then break end
        if wanted[parent] then
            r = parent
            break
        end
    end
    resolved[name] = r
    return r
end

--- Whether an object's own name is a class default object's.
function Bipeds.isDefault(name)
    return type(name) ~= "string" or name:find("^Default__") ~= nil
end

--- Keep `actor` under `class` by its address.
function Bipeds.keep(class, actor)
    local set = known[class]
    if not set then return end
    local ok, at = pcall(function() return actor:GetAddress() end)
    if ok and at then set[at] = actor end
end

local function nameOf(o)
    return o:GetFName():ToString()
end

local function seen(new)
    local ok, cls, name = pcall(function()
        local c = new:GetClass()
        return c, nameOf(c)
    end)
    if not ok then return end
    local class = Bipeds.resolve(name, function()
        local names, at = { name }, cls
        for _ = 1, MAX_PARENTS do
            local okS, super = pcall(function() return at:GetSuperStruct() end)
            if not (okS and super and super:IsValid()) then break end
            at = super
            names[#names + 1] = nameOf(at)
        end
        return names
    end)
    if not class then return end
    local okN, own = pcall(nameOf, new)
    if okN and not Bipeds.isDefault(own) then Bipeds.keep(class, new) end
end

--- Watch for bipeds from now on: once, when the mod loads. False when UE4SS
--- would not watch the class; then only `scan` finds them.
function Bipeds.arm(log)
    if armed then return true end
    if type(NotifyOnNewObject) ~= "function" then return false end
    local ok, err = pcall(NotifyOnNewObject, Bipeds.ANCESTOR, seen)
    armed = ok
    if log then
        log(ok and ("bipeds: watching " .. Bipeds.ANCESTOR)
            or ("bipeds: cannot watch " .. Bipeds.ANCESTOR .. " (" .. tostring(err) .. "); bipeds come from scans"))
    end
    return armed
end

--- Whether every biped made since the mod loaded has been seen.
function Bipeds.armed()
    return armed
end

--- The kept actors of `class`, by address: the module's own set, which a
--- caller may drop a gone actor from. Each must be checked before use.
function Bipeds.of(class)
    return known[class] or {}
end

--- Walk the object array for `class` (about 23 ms in a match): only when
--- the watch could not be armed, or a placement went unseen.
function Bipeds.scan(class)
    if not (type(FindAllOf) == "function" and known[class]) then return 0 end
    local n = 0
    for _, actor in ipairs(FindAllOf(class) or {}) do
        -- A scan finds the class and the classes derived from it.
        local ok, name = pcall(function() return nameOf(actor:GetClass()) end)
        if ok and name then
            if resolved[name] == nil then resolved[name] = class end
            Bipeds.keep(class, actor)
            n = n + 1
        end
    end
    return n
end

--- Drop every kept actor that is gone, or whose address now holds another
--- class's object (a freed actor's memory reused): on each world change and
--- when bots start, so actors from earlier maps do not pile up.
function Bipeds.prune()
    local dropped = 0
    for class, set in pairs(known) do
        for at, actor in pairs(set) do
            local ok, same = pcall(function()
                return actor:IsValid() and resolved[nameOf(actor:GetClass())] == class
            end)
            if not (ok and same) then
                set[at] = nil
                dropped = dropped + 1
            end
        end
    end
    return dropped
end

--- How many actors are kept, for the log.
function Bipeds.count()
    local n = 0
    for _, set in pairs(known) do
        for _ in pairs(set) do n = n + 1 end
    end
    return n
end

return Bipeds

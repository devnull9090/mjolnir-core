-- MJOLNIRHud's biped watch: lua5.4 tools/tests/test_bipeds.lua
local function eq(got, want, what)
    if got ~= want then error(what .. ": got " .. tostring(got) .. ", want " .. tostring(want), 2) end
end

-- The game, as much of it as the module reads: classes with parents, actors
-- with addresses, and the one watch UE4SS keeps.
local function class(name, super)
    local c = { name = name, super = super, valid = true }
    function c:GetFName() return { ToString = function() return self.name end } end
    function c:GetSuperStruct() return self.super end
    function c:IsValid() return self.valid end
    return c
end
local ancestor = class("BlamObjectActor")
local eliteClass = class("BP_EliteBipedActor_C", ancestor)
local spartanClass = class("BP_SpartansBipedActor_C", ancestor)
local rangerClass = class("BP_EliteRangerBipedActor_C", eliteClass) -- a Blueprint derived from one
local weaponClass = class("BP_AssaultRifle_WeaponActor_C", ancestor)
local supers = 0
for _, c in ipairs({ eliteClass, spartanClass, rangerClass, weaponClass }) do
    local get = c.GetSuperStruct
    c.GetSuperStruct = function(self) supers = supers + 1; return get(self) end
end

local nextAddress = 0
local function actor(cls, name)
    nextAddress = nextAddress + 1
    local a = { cls = cls, valid = true, address = nextAddress, name = name or (cls.name .. "_" .. nextAddress) }
    function a:GetClass() return self.cls end
    function a:GetFName() return { ToString = function() return self.name end } end
    function a:GetAddress() return self.address end
    function a:IsValid() return self.valid end
    return a
end

local Bipeds = dofile("mods/MJOLNIRHud/Scripts/bipeds.lua")

-- Without UE4SS there is nothing to watch, and nothing to scan.
eq(Bipeds.arm(), false, "no NotifyOnNewObject, no watch")
eq(Bipeds.armed(), false, "not armed")
eq(Bipeds.scan("BP_EliteBipedActor_C"), 0, "no FindAllOf, no scan")

local watchedPath, made
_G.NotifyOnNewObject = function(path, fn) watchedPath, made = path, fn end
local logged = {}
eq(Bipeds.arm(function(line) logged[#logged + 1] = line end), true, "armed")
eq(watchedPath, Bipeds.ANCESTOR, "one watch, on the native ancestor")
assert(logged[1]:find("watching", 1, true), "says so")
eq(Bipeds.arm(), true, "arming again changes nothing")

-- A map's pools as it loads, a weapon, the class defaults, a derived Blueprint.
local e1, e2 = actor(eliteClass), actor(eliteClass)
local s1 = actor(spartanClass)
local ranger = actor(rangerClass)
made(e1); made(e2); made(s1); made(ranger)
made(actor(weaponClass))
made(actor(eliteClass, "Default__BP_EliteBipedActor_C"))
local function count(set)
    local n = 0
    for _ in pairs(set) do n = n + 1 end
    return n
end
eq(count(Bipeds.of("BP_EliteBipedActor_C")), 3, "two Elites and the derived one; no class default")
eq(Bipeds.of("BP_EliteBipedActor_C")[ranger.address], ranger, "a derived Blueprint counts as its parent")
eq(count(Bipeds.of("BP_SpartansBipedActor_C")), 1, "the Spartan")
eq(Bipeds.count(), 4, "the weapon is not kept")
eq(count(Bipeds.of("BP_NotABiped_C")), 0, "an unknown class has an empty set")

-- Each class's parents are looked up once, not per object.
local before = supers
for _ = 1, 20 do made(actor(weaponClass)); made(actor(eliteClass)) end
eq(supers, before, "a class is resolved the first time only")
eq(count(Bipeds.of("BP_EliteBipedActor_C")), 23, "every new Elite is kept")

-- A world change: gone actors go, and so does an address that now holds
-- another class's object.
for _, a in pairs(Bipeds.of("BP_EliteBipedActor_C")) do
    if a ~= e1 and a ~= ranger then a.valid = false end
end
s1.cls = weaponClass -- its memory reused by a weapon
local dropped = Bipeds.prune()
eq(dropped, 22, "21 gone Elites and the reused address")
eq(count(Bipeds.of("BP_EliteBipedActor_C")), 2, "the live Elite and the derived one stay")
eq(count(Bipeds.of("BP_SpartansBipedActor_C")), 0, "the reused address goes")

-- The backstop scan finds a class and its derived classes, and keeps them.
local stray = actor(rangerClass)
local found = { actor(spartanClass), actor(spartanClass) }
_G.FindAllOf = function(name)
    if name == "BP_SpartansBipedActor_C" then return found end
    if name == "BP_EliteBipedActor_C" then return { stray } end
    return nil
end
eq(Bipeds.scan("BP_SpartansBipedActor_C"), 2, "a scan keeps what it finds")
eq(count(Bipeds.of("BP_SpartansBipedActor_C")), 2, "kept under the class scanned")
eq(Bipeds.scan("BP_JackalBipedActor_C"), 0, "a class with none")
eq(Bipeds.prune(), 0, "scanned actors survive a prune")

-- A watch UE4SS refuses: scans only, and said once.
local Again = dofile("mods/MJOLNIRHud/Scripts/bipeds.lua")
_G.NotifyOnNewObject = function() error("Could not find class") end
logged = {}
eq(Again.arm(function(line) logged[#logged + 1] = line end), false, "a refused watch")
assert(logged[1]:find("cannot watch", 1, true), "says the bipeds come from scans")

print("Bipeds: one watch from load, classes and derived Blueprints, class defaults, pruning, scans")

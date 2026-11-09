-- MJOLNIRHud's bots, how often they read the pooled bipeds: lua5.4 tools/tests/test_bots_scan.lua
--
-- A fake game: a pool of bipeds waiting at the origin, a simulation that takes
-- one out for each `ai_place`, and deaths. The bots must still seat each bot on
-- its own actor, while reading only the actors out of the pool between
-- placements (Scripts/bots.lua liveActors).
local function eq(got, want, what)
    if got ~= want then error(what .. ": got " .. tostring(got) .. ", want " .. tostring(want), 2) end
end

local reads = 0
local nextAddress = 0
local classes = {}
local function classOf(name)
    local c = classes[name]
    if not c then
        c = { GetFName = function() return { ToString = function() return name end } end,
            GetSuperStruct = function() return nil end }
        classes[name] = c
    end
    return c
end
local function biped(class)
    nextAddress = nextAddress + 1
    local a = { class = class, address = nextAddress, X = 0, Y = 0, Z = 0, dead = false, valid = true }
    function a:GetClass() return classOf(self.class) end
    function a:GetFName()
        local own = self.class .. "_" .. self.address
        return { ToString = function() return own end }
    end
    a.BlamObjectDamage = { IsDead = function() return a.dead end }
    function a:IsValid() return self.valid end
    function a:GetAddress() return self.address end
    function a:K2_GetActorLocation()
        reads = reads + 1
        return { X = self.X, Y = self.Y, Z = self.Z }
    end
    return a
end

-- The lobby DLL and its files, faked: script lines are kept for the game.
local sent = {}
_G.package.loadlib = function() return function() end end
local realOpen = io.open
io.open = function(path, mode)
    if path:find("MJOLNIRLobby\\native\\", 1, true) then
        return {
            write = function(_, ...)
                for _, v in ipairs({ ... }) do sent[#sent + 1] = tostring(v) end
            end,
            close = function() end,
        }
    end
    if path:find("bots.json", 1, true) then return nil end
    return realOpen(path, mode)
end

-- The watch, armed as the HUD loads; the map's pools are made after it.
local Bipeds = dofile("mods/MJOLNIRHud/Scripts/bipeds.lua")
local made
_G.NotifyOnNewObject = function(_, fn) made = fn end
Bipeds.arm()
_G.FindAllOf = function() error("no whole-array scan while the watch is armed") end
local spartans, elites = {}, {}
for i = 1, 40 do spartans[i] = biped("BP_SpartansBipedActor_C"); made(spartans[i]) end
for i = 1, 75 do elites[i] = biped("BP_EliteBipedActor_C"); made(elites[i]) end
eq(Bipeds.count(), 115, "the pools are kept")

local Bots = dofile("mods/MJOLNIRHud/Scripts/bots.lua")
local logged = {}
Bots.init("C:\\Game\\ue4ss\\Mods", function(line) logged[#logged + 1] = line end, Bipeds)

-- The simulation: each `ai_place` brings the next free Spartan out of the pool.
local placed, nextFree = {}, 1
local function simulate()
    for _, line in ipairs(sent) do
        for squad in line:gmatch("%(ai_place ([%w_]+)%)") do
            local a = spartans[nextFree]
            nextFree = nextFree + 1
            a.X, a.Y, a.Z = 1000 * nextFree, 500, 100
            placed[squad] = a
        end
    end
    sent = {}
end

local seated = {}
local now = 100
eq(Bots.begin(3, now, function(index) seated[#seated + 1] = index end, { kind = 0 }), true, "bots start")
local function run(seconds)
    local stop = now + seconds
    while now < stop do
        Bots.tick(now, {})
        simulate()
        now = now + 0.1
    end
end

run(6)
eq(#seated, 3, "three bots seated")
local seats = Bots.seats()
eq(#seats, 3, "three seats")

-- Steady state: three bots out, 115 bipeds pooled. A scan reads the three, and
-- every actor only on the full pass every few seconds.
reads = 0
run(10)
local perSecond = reads / 10
assert(perSecond < 115, "between placements the pool is not read every scan: " .. perSecond .. " reads a second")
assert(perSecond > 3 * 3, "the bots out of the pool are read every scan: " .. perSecond)

-- A bot dies with no incident, its body goes back to the pool, and five
-- seconds later it is placed again on a new actor.
local victim
for _, a in pairs(placed) do victim = victim or a end
victim.dead = true
run(3)
victim.dead, victim.X, victim.Y, victim.Z = false, 0, 0, 0
local before = #seated
run(8)
eq(#seated, before + 1, "the dead bot is placed again")
eq(#Bots.seats(), 3, "still three bots")
eq(Bots.seatOf(victim), nil, "the dead bot's old actor is no one's")

-- An Elite out of the pool that no placement brought (a player's old body):
-- it is never taken for the Spartan bot placed next.
elites[1].X, elites[1].Y = 777, 777
for _, a in pairs(placed) do
    if a ~= victim and a.X ~= 0 then
        a.dead = true
        break
    end
end
run(3)
for _, a in ipairs(spartans) do if a.dead then a.dead, a.X, a.Y, a.Z = false, 0, 0, 0 end end
before = #seated
run(8)
eq(#seated, before + 1, "the next bot is placed")
eq(Bots.seatOf(elites[1]), nil, "the stray Elite is no bot's")
local onSpartans = 0
for _, a in ipairs(spartans) do if Bots.seatOf(a) then onSpartans = onSpartans + 1 end end
eq(onSpartans, 3, "every bot is on a Spartan")

for _, line in ipairs(logged) do
    assert(not line:find("never appeared", 1, true), "no placement went unseen: " .. line)
end

io.open = realOpen
print("Bots scan: placements seen, steady state reads the actors out of the pool, strays never taken")

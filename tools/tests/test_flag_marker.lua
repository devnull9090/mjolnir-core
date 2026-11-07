-- MJOLNIRHud's flag marker: lua5.4 tools/tests/test_flag_marker.lua
local function eq(got, want, what)
    if got ~= want then error(what .. ": got " .. tostring(got) .. ", want " .. tostring(want), 2) end
end

-- The game, as much of it as the module reads.
local nextAddress = 0
local function actor(x, y, z, variant)
    nextAddress = nextAddress + 1
    local self = { place = { X = x, Y = y, Z = z }, variant = variant, valid = true, address = nextAddress }
    local component = { GetVariantName = function() return { ToString = function() return self.variant end } end }
    function self:IsValid() return self.valid end
    function self:GetAddress() return self.address end
    function self:GetFullName() return "BP_SkullActor_C /Game/Levels/X.X:PersistentLevel.BP_SkullActor_C_" .. self.address end
    function self:K2_GetActorLocation() return self.place end
    function self:K2_GetComponentsByClass() return { component } end
    return self
end

local world, notify = {}, nil
_G.FindAllOf = function() return world end
_G.NotifyOnNewObject = function(_, fn) notify = fn end
_G.StaticFindObject = function() return { IsValid = function() return true end } end

local FlagMark = dofile("mods/MJOLNIRHud/Scripts/flagmark.lua")

-- Hill's drawing, recorded.
local marks = {}
local Hill = dofile("mods/MJOLNIRHud/Scripts/hill.lua")
Hill.Waypoint = { label = function(metres, level) return metres .. " M" .. (level or "") end }
Hill.field = function(name)
    local team = name:find("red", 1, true) and "Red" or "Blue"
    return {
        mark = function(_, spot, holder, icon, words)
            marks[team] = { spot = spot, holder = holder, icon = icon, words = words }
            return true
        end,
        unmark = function() marks[team] = nil end,
        frame = function() marks.framed = (marks.framed or 0) + 1 end,
        ensureLine = function() end,
        say = function(words) marks.line = words end,
        hideLine = function() marks.line = nil end,
    }
end

local pawn = { IsValid = function() return true end, K2_GetActorLocation = function() return { X = 0, Y = 0, Z = 0 } end }
local pc = { Pawn = pawn }

eq(FlagMark.teamOf("Blue"), "Blue", "the blue tag's variant")
eq(FlagMark.teamOf("blue"), "Blue", "whatever its case")
eq(FlagMark.teamOf("Default"), "Red", "the red tag's is default")
eq(FlagMark.teamOf(nil), nil, "no variant, no team")
eq(FlagMark.teamOf("None"), nil, "nor an unset one")
eq(FlagMark.parked({ X = 0, Y = 0, Z = 0 }), true, "an unused actor waits at the origin")
eq(FlagMark.parked({ X = 3414, Y = -6818, Z = -14863 }), false, "a flag on a stand does not")

local clock = 0
local function tick(mark, hidden)
    clock = clock + 1
    mark.tick(clock, pc, hidden)
end

-- A flag made before the watch, as a first CTF game can be.
local blue = actor(5000, 0, 0, "Blue")
world = { blue }
local mark = FlagMark.new(Hill)
tick(mark)
assert(marks.Blue, "a flag already out is found")
eq(marks.Red, nil, "and only the one that is out")
eq(marks.Blue.holder, "Blue", "the marker takes the flag's team")
eq(marks.Blue.icon, "Ctf", "and the flag icon")
eq(marks.Blue.spot.z, 120, "the badge stands above the flag")
eq(marks.Blue.words, "47 M", "with the distance to its edge")

-- Assault's swap: the same actor, the other flag, the other stand.
blue.variant, blue.place = "Default", { X = -5000, Y = 0, Z = 0 }
tick(mark)
assert(marks.Red, "the actor reused for the next flag is read again")
eq(marks.Blue, nil, "and the old flag's marker goes")
eq(marks.Red.spot.x, -5000, "the marker is on the new stand")

-- CTF: both flags, one made after the watch started.
local other = actor(7000, 0, 0, "Blue")
notify(other)
tick(mark)
assert(marks.Red and marks.Blue, "both flags have markers")
eq(marks.Blue.spot.x, 7000, "each its own")
notify(other)
tick(mark)
assert(marks.Blue, "an actor reported twice is one flag")

-- A flag on top of the player: carried, or being stood on.
other.place = { X = 100, Y = 0, Z = 0 }
tick(mark)
eq(marks.Blue, nil, "nothing to point at this close")
other.place = { X = 7000, Y = 0, Z = 0 }
tick(mark)
assert(marks.Blue, "and it comes back")

-- An actor no object uses waits at the origin.
other.place = { X = 0, Y = 0, Z = 0 }
tick(mark)
eq(marks.Blue, nil, "an unused actor marks nothing")
other.place = { X = 7000, Y = 0, Z = 0 }
tick(mark)

-- A freed actor is dropped, never read.
other.valid = false
other.K2_GetActorLocation = function() error("read a freed actor") end
tick(mark)
eq(marks.Blue, nil, "a freed flag's marker goes")
assert(marks.Red, "and the other stays")

-- Only one look per EVERY.
local reads = 0
local real = blue.K2_GetActorLocation
blue.K2_GetActorLocation = function(self) reads = reads + 1; return real(self) end
clock = clock + 1
mark.tick(clock, pc)
mark.tick(clock + 0.05, pc)
eq(reads, 1, "a marker updates five times a second, not every frame")
blue.K2_GetActorLocation = real

-- The HUD hidden.
tick(mark, true)
eq(marks.Red, nil, "a hidden HUD hides the markers")

-- A dead player has no pawn to measure from.
pc.Pawn = nil
tick(mark)
eq(marks.Red, nil, "no pawn, no markers, and no error")
pc.Pawn = pawn
tick(mark)
assert(marks.Red, "back with the next spawn")

mark.frame(pc, clock)
eq(marks.framed, 2, "every frame reaches both markers")

eq(marks.line, nil, "plain CTF has no line")

-- Assault's line.
eq(FlagMark.clock(222), "3:42", "minutes and seconds")
eq(FlagMark.clock(61.2), "1:02", "a part second counts")
eq(FlagMark.clock(-3), "0:00", "never below nothing")
eq(FlagMark.sideLine("Blue", "Red", 222), "ATTACK  /  SIDES SWAP IN 3:42", "the other team defends")
eq(FlagMark.sideLine("Blue", "Blue", 222), "DEFEND  /  SIDES SWAP IN 3:42", "your team defends")
eq(FlagMark.sideLine("Blue", nil, 60), "SIDES SWAP IN 1:00", "before your team is known")
eq(FlagMark.sideLine("Blue", "Red", nil), "ATTACK", "before the clock is known")
eq(FlagMark.sideLine("Blue", nil, nil), nil, "neither")

local function assault(host)
    marks = {}
    clock = 1000
    blue.variant, blue.place = "Blue", { X = 5000, Y = 0, Z = 0 }
    return FlagMark.new(Hill, { seconds = 300, host = host })
end
local function at(mark, seconds, mine)
    clock = 1000 + seconds
    mark.tick(clock, pc, false, mine)
end

mark = assault(true)
at(mark, 0, "Red")
eq(marks.line, "ATTACK  /  SIDES SWAP IN 5:00", "the host counts from the first flag")
at(mark, 100, "Red")
eq(marks.line, "ATTACK  /  SIDES SWAP IN 3:20", "and down")
-- A capture swaps early, and a full clock starts.
blue.variant = "Default"
at(mark, 120, "Red")
eq(marks.line, "DEFEND  /  SIDES SWAP IN 5:00", "the flag changing team is a swap")
-- Between two flags, nothing changes.
blue.valid = false
at(mark, 130, "Red")
eq(marks.line, "DEFEND  /  SIDES SWAP IN 4:50", "the clock runs on while no flag is out")
blue.valid = true
notify(blue)
at(mark, 140, "Red")
eq(marks.line, "DEFEND  /  SIDES SWAP IN 4:40", "and the same team's flag is no swap")

-- A player who joined late has no start to count from.
mark = assault(false)
at(mark, 0, "Blue")
eq(marks.line, "DEFEND", "a joiner sees the role and no guess at the time")
blue.variant = "Default"
at(mark, 50, "Blue")
eq(marks.line, "ATTACK  /  SIDES SWAP IN 5:00", "and the clock from the first swap")

tick(mark, true)
eq(marks.line, nil, "a hidden HUD hides the line")

print("Flag marker: teams from the variant, Assault's reused actor, both CTF flags, carried and unused flags, freed actors, Assault's role and clock")

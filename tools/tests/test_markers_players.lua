-- MJOLNIRHud's markers: where another player stands. lua5.4 tools/tests/test_markers_players.lua
--
-- On a two-PC match each machine's own pawn follows its player, and another
-- player's pawn sits at the world's origin. The hill (contested, held by
-- another) and the Juggernaut's marker read other players from the biped their
-- spawn named instead, only while it is valid and still theirs.

local function eq(got, want, what)
    if got ~= want then error(what .. ": got " .. tostring(got) .. ", want " .. tostring(want), 2) end
end

StaticFindObject = function() return "BlamUnitComponent" end

local function biped(x, controller, valid)
    local unit = {
        IsValid = function() return true end,
        GetControllingPlayerDatumIndex = function() return controller end,
    }
    return {
        IsValid = function() return valid ~= false end,
        GetComponentByClass = function(_, class)
            assert(class == "BlamUnitComponent", "asks for the unit component")
            return unit
        end,
        K2_GetActorLocation = function() return { X = x, Y = 0, Z = 0 } end,
    }
end

local Markers = dofile("mods/MJOLNIRHud/Scripts/markers.lua").new({ Hill = {} })
local at = Markers.bipedAt

eq(at(nil, 1), nil, "a player the HUD doesn't know")
eq(at({}, 1), nil, "no spawn seen yet")
eq(at({ biped = biped(500, 0x00ab0001) }, 1).X, 500, "their biped")
eq(at({ biped = biped(500, 1) }, 1).X, 500, "a datum with no salt")
eq(at({ biped = biped(500, 0x00ab0002) }, 1), nil, "a pooled actor now someone else's")
eq(at({ biped = biped(500, -1) }, 1), nil, "a body nobody controls")
eq(at({ biped = biped(500, 0x00ab0001, false) }, 1), nil, "a freed actor")
eq(at({ biped = biped(500, 0x00ab0001), dead = true }, 1), nil, "a dead player")

-- A handle whose reads throw is unknown, not an error.
local broken = { IsValid = function() error("freed") end }
eq(at({ biped = broken }, 1), nil, "a read that throws")

-- Seated: the biped hangs off the vehicle but keeps the place they got in at
-- (#348), so the place is the vehicle's, and the vehicle is what to follow.
local seated = biped(500, 0x00ab0001)
local warthog = { IsValid = function() return true end, K2_GetActorLocation = function() return { X = 9000, Y = 0, Z = 0 } end }
seated.GetAttachParentActor = function() return warthog end
local place, body = at({ biped = seated }, 1)
eq(place.X, 9000, "a seated player is where the vehicle is")
eq(body, warthog, "and the vehicle is followed")
local walker = biped(500, 0x00ab0001)
walker.GetAttachParentActor = function() return nil end
place, body = at({ biped = walker }, 1)
eq(place.X, 500, "on foot, their own place")
eq(body, walker, "and their biped")

-- From the simulation's roster (Scripts/roster.lua): every player alive, in
-- seat order, at their unit's or vehicle's place; nobody dead; `me` by the
-- local player's index; team only in a team game; `actor` reads the seat
-- again for the markers that follow every frame.
local asked = {}
local fakeRoster = { at = function(index) asked[#asked + 1] = index; return { X = index * 10, Y = 0, Z = 0 } end }
local withRoster = dofile("mods/MJOLNIRHud/Scripts/markers.lua").new({ Hill = {}, Roster = fakeRoster })
local r = { seats = {
    [5] = { alive = true, at = { X = 500, Y = 1, Z = 2 } },
    [0] = { alive = true, at = { X = 0, Y = 0, Z = 0 } },
    [3] = { alive = false, at = { X = 300, Y = 0, Z = 0 } },
} }
local match = { mode = { teams = true }, players = { [0] = { team = "red" }, [5] = { team = "blue" } } }
local list = withRoster.fromRoster(match, r, 5)
eq(#list, 2, "two alive")
eq(list[1].index, 0, "in seat order")
eq(list[2].index, 5, "then the next")
eq(list[2].me, true, "the local player by index")
eq(list[1].me, false, "another")
eq(list[2].at.X, 500, "their place")
eq(list[2].team, "blue", "their team")
eq(list[2].actor().X, 50, "the follower reads their seat")
eq(asked[1], 5, "by index")
eq(list[2].actor, withRoster.fromRoster(match, r, 5)[2].actor, "one follower a seat, made once")
match.mode.teams = false
eq(withRoster.fromRoster(match, r, 5)[2].team, nil, "no team in free for all")
eq(#withRoster.fromRoster(match, { seats = {} }, 0), 0, "nobody")

-- `me` is the seat this machine's game marks as local user 0, whatever index
-- the HUD read: a joiner whose PlayerStates all said 0 (two copies on one PC)
-- took the host's seat 0 for its own.
local joiner = { seats = {
    [0] = { alive = true, here = false, user = -1, at = { X = 0, Y = 0, Z = 0 } },
    [1] = { alive = true, here = true, user = 0, at = { X = 100, Y = 0, Z = 0 } },
} }
list = withRoster.fromRoster(match, joiner, 0)
eq(list[1].me, false, "the host's seat is not the joiner's")
eq(list[2].me, true, "the joiner's own seat, by its local user")
-- A splitscreen player (local user 1) is this machine's but not the HUD's player.
local split = { seats = {
    [0] = { alive = true, here = true, user = 1, at = { X = 0, Y = 0, Z = 0 } },
    [2] = { alive = true, here = true, user = 0, at = { X = 0, Y = 0, Z = 0 } },
} }
list = withRoster.fromRoster(match, split, 0)
eq(list[1].me, false, "local user 1 is not me")
eq(list[2].me, true, "local user 0 is")
-- No seat marked local (no users map): the HUD's index.
local unmarked = { seats = { [3] = { alive = true, at = { X = 0, Y = 0, Z = 0 } } } }
eq(withRoster.fromRoster(match, unmarked, 3)[1].me, true, "the index when no seat is marked")

print("ok")

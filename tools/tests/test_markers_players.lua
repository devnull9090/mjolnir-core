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

print("ok")

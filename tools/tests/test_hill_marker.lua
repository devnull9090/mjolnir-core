-- MJOLNIRHud's hill marker: lua5.4 tools/tests/test_hill_marker.lua
local Hill = dofile("mods/MJOLNIRHud/Scripts/hill.lua")

local function eq(got, want, what)
    if got ~= want then error(what .. ": got " .. tostring(got) .. ", want " .. tostring(want), 2) end
end

local hills = Hill.parse('{"modes": ["koth"], "koth_hills": [\n  [100.5, -200, 30, 800.0],\n  [1, 2, 3, 4]\n], "x": [[9, 9, 9, 9]]}')
eq(#hills, 2, "hills in the list")
eq(hills[1].x, 100.5, "first x")
eq(hills[2].r, 4, "second radius")
eq(#Hill.parse('{"modes": ["slayer"]}'), 0, "no hills")
eq(#Hill.parse(nil), 0, "no file")

local hill = { x = 0, y = 0, z = 0, r = 500 }
eq(Hill.describe(hill, { X = 100, Y = 0, Z = 10 }, 0), "ON THE HILL", "standing on it")
eq(Hill.describe(hill, { X = 100, Y = 0, Z = 900 }, 0), "HILL BELOW", "over it")
eq(Hill.describe(hill, { X = -2500, Y = 0, Z = 0 }, 0), "HILL 20 M AHEAD", "facing it")
eq(Hill.describe(hill, { X = -2500, Y = 0, Z = 0 }, 180), "HILL 20 M BEHIND", "back to it")
eq(Hill.describe(hill, { X = 0, Y = -2500, Z = 0 }, 0), "HILL 20 M RIGHT", "Unreal: +Y is to the right of +X")
eq(Hill.describe(hill, { X = 0, Y = 2500, Z = 0 }, 0), "HILL 20 M LEFT", "and -Y to the left")
eq(Hill.describe(hill, { X = -2500, Y = 0, Z = -1000 }, 0), "HILL 20 M AHEAD ABOVE", "a floor up")

local marker = Hill.new(function() return '"koth_hills": [[0,0,0,1],[5,5,5,1]]' end)
eq(marker.start("ABC"), 2, "start")
marker.moved(1)
eq(marker.live, 2, "second hill")
marker.moved(9)
eq(marker.live, 2, "a place past the list changes nothing")
print("hill marker: ok")

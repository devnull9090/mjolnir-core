-- Run from the repository root with Lua 5.4.
-- The screen marker's maths, and its failure routes through a fake widget.
local function eq(actual, expected, label)
    assert(actual == expected, (label or "value") .. ": expected " .. tostring(expected) .. ", got " .. tostring(actual))
end
local function near(actual, expected, label, tolerance)
    assert(math.abs(actual - expected) <= (tolerance or 0.01),
        (label or "value") .. ": expected about " .. tostring(expected) .. ", got " .. tostring(actual))
end

local Waypoint = dofile("mods/MJOLNIRHud/Scripts/waypoint.lua")

local W, H, MX, MY = 1280, 720, 64, 100
local function view(yaw, pitch, fov)
    return { x = 0, y = 0, z = 0, pitch = pitch or 0, yaw = yaw or 0, fov = fov or 85 }
end
local function project(camera, x, y, z)
    return Waypoint.project(camera, { x = x, y = y, z = z }, W, H, MX, MY)
end

-- Straight ahead is the middle of the screen, whichever way the camera faces.
local p = project(view(), 3000, 0, 0)
eq(p.seen, true, "ahead is seen")
near(p.x, 640, "ahead is centred")
near(p.y, 360, "at eye level")
eq(p.angle, nil, "and needs no arrow")
p = project(view(90), 0, 3000, 0)
eq(p.seen, true, "yaw turns the view")
near(p.x, 640, "and the spot stays centred")

-- The numbers the game gave: a spot 3000 ahead and 600 right at 85 degrees,
-- which its own ProjectWorldLocationToScreen put at x 778.7.
p = project(view(), 3000, 600, 0)
near(p.x, 779.7, "matches the game's projection", 1.5)
p = project(view(), 3000, -600, 0)
near(p.x, 500.3, "left is left", 1.5)
p = project(view(), 3000, 0, 300)
assert(p.y < 360, "above is up the screen")
p = project(view(0, 30), 3000, 0, 3000 * math.tan(math.rad(30)))
near(p.x, 640, "looking up at it")
near(p.y, 360, "centres it")

-- A narrower field of view (a scope) spreads the same spot further out.
assert(project(view(0, 0, 40), 3000, 600, 0).x > project(view(), 3000, 600, 0).x, "zooming moves it out")

-- Off screen it sits on the margin and points the way to turn.
p = project(view(), 3000, 9000, 0)
eq(p.seen, false, "far right is not seen")
near(p.x, W - MX, "it rests on the right margin")
near(p.angle, 90, "and points right")
p = project(view(), 3000, -9000, 0)
near(p.x, MX, "the left margin")
near(p.angle, -90, "points left")
p = project(view(), 3000, 0, 9000)
near(p.y, MY, "the top margin")
near(p.angle, 0, "points up")
p = project(view(), 3000, 0, -9000)
near(p.y, H - MY, "the bottom margin")
near(math.abs(p.angle), 180, "points down")

-- Behind the camera the answer is left or right, whatever the height.
p = project(view(), -3000, 0, 0)
eq(p.seen, false, "behind is not seen")
near(p.y, H - MY, "dead behind rests on the bottom")
near(math.abs(p.angle), 180, "and points down")
p = project(view(), -3000, 0, 5000)
near(p.y, H - MY, "above and behind does not point up")
p = project(view(), -1000, 6000, 0)
near(p.x, W - MX, "behind to the right goes right", 1)
assert(p.angle > 90 and p.angle < 180, "and leans back")
p = project(view(), -1000, -6000, 0)
near(p.x, MX, "behind to the left goes left", 1)
assert(p.angle < -90 and p.angle > -180, "and leans back")

-- Crossing the edge of the camera's plane does not throw it across the screen.
local before, after = project(view(), 2, 6000, 0), project(view(), -2, 6000, 0)
eq(before.x, after.x, "ahead and behind meet at the side")

-- Whatever it is given, a marker stays inside the margins.
for yaw = -180, 180, 15 do
    for z = -9000, 9000, 3000 do
        p = project(view(yaw, 20), 4000, 1500, z)
        assert(p.x >= MX - 0.01 and p.x <= W - MX + 0.01 and p.y >= MY - 0.01 and p.y <= H - MY + 0.01,
            "inside the margins at yaw " .. yaw .. ", z " .. z)
    end
end
local out = {}
eq(Waypoint.project(view(), { x = 3000, y = 0, z = 0 }, W, H, MX, MY, out), out, "fills the table it is given")

-- What goes under the badge.
eq(Waypoint.label(145, ""), "145 M", "distance")
eq(Waypoint.label(145, " ABOVE"), "145 M ABOVE", "and up")
eq(Waypoint.label(0, " BELOW"), "0 M BELOW", "or down")

-- An arrow pointing down would land on the words, so they move over the badge.
eq(Waypoint.wordsOver(180), true, "straight down")
eq(Waypoint.wordsOver(-150), true, "down and left")
eq(Waypoint.wordsOver(90), false, "right is clear")
eq(Waypoint.wordsOver(0), false, "up is clear")
eq(Waypoint.wordsOver(nil), false, "no arrow, no need")

-- Over the crosshair it fades, and a flashing one never vanishes.
eq(Waypoint.opacity(640, 360, W, H, false, 0), 0.35, "faded over the crosshair")
eq(Waypoint.opacity(100, 100, W, H, false, 0), 1, "clear elsewhere")
for now = 0, 2, 0.05 do
    local alpha = Waypoint.opacity(100, 100, W, H, true, now)
    assert(alpha >= 0.39 and alpha <= 1, "a pulse stays visible")
end

-- A marker that cannot be made says so once and reports false: the caller keeps
-- its text line.
StaticFindObject = function() error("no such class") end
local logged = {}
local marker = Waypoint.new(function(line) logged[#logged + 1] = line end)
local pc = {}
eq(marker.point(pc, { x = 0, y = 0, z = 0 }, { 1, 1, 1 }, "Koth", "1 M", false, 0), false, "no widget, no marker")
eq(marker.point(pc, { x = 0, y = 0, z = 0 }, { 1, 1, 1 }, "Koth", "1 M", false, 0), false, "and it does not try again")
eq(#logged, 1, "said once")
marker.frame(pc, 0)
marker.hide()

print("Waypoint: projection, edges, behind the camera, labels, fading and failure passed")

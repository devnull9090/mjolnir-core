-- lua tools/tests/test_warfare_countdown.lua
local Countdown = dofile("mods/MJOLNIRHud/Scripts/warfare_countdown.lua")
local Warfare = dofile("mods/MJOLNIRHud/Scripts/warfare.lua")
local function eq(a, b, what) assert(a == b, (what or "value") .. ": " .. tostring(a) .. " ~= " .. tostring(b)) end

local function snap(phase, clock, instance)
    return { phase = phase, instance = instance or "7", connected = 2, globals = { phase, 0, Warfare.RULES, clock } }
end

-- What the countdown shows.
eq(Countdown.view(snap(0, -1), 0), nil, "nothing while waiting for players")
eq(Countdown.view(snap(0, 23), 0), nil, "early seconds stay in the status line")
eq(Countdown.view(snap(0, 10), 0), "10", "the last ten seconds are large")
local words, colour = Countdown.view(snap(0, 3), 0)
eq(words, "3"); eq(colour.R, 1, "the last three are gold")
eq(select(2, Countdown.view(snap(0, 7), 0)).R < 1, true, "earlier ones are cyan")
eq(Countdown.view(snap(0, 0), 0), nil, "zero is the launch tick, not a number")
eq(Countdown.view(snap(1, 60), 5, 4), "DEPLOY", "insertion just began")
eq(Countdown.view(snap(1, 60), 7, 4), nil, "and the word goes after two seconds")
eq(Countdown.view(snap(1, 60), 5, nil), nil, "a join during insertion never saw the launch")
eq(Countdown.view(snap(2, 15), 0), nil, "combat clock is not a countdown")
eq(Countdown.view(nil, 0), nil)

-- The widget: made once, text set only when the number changes, hidden not removed.
local calls = { create = 0, text = {}, visibility = {} }
local function valid() return true end
local fakeText = { IsValid = valid, Font = {},
    SetText = function(_, t) calls.text[#calls.text + 1] = t end,
    SetColorAndOpacity = function() end, SetRenderScale = function() end,
    SetShadowOffset = function() end, SetShadowColorAndOpacity = function() end,
    SetRenderTransformPivot = function() end }
local fakeWidget = { IsValid = valid, WidgetTree = {},
    AddToViewport = function() end, SetAnchorsInViewport = function() end, SetAlignmentInViewport = function() end,
    SetVisibility = function(_, v) calls.visibility[#calls.visibility + 1] = v end,
    RemoveFromParent = function() error("never remove a Lua-made widget") end }
local library = { Create = function() calls.create = calls.create + 1; return fakeWidget end }
local c = Countdown.new({
    object = function(path)
        if path:find("WidgetBlueprintLibrary") then return library end
        if path == Countdown.FONT then return { IsValid = valid, font = true } end
        return {}
    end,
    construct = function() return fakeText end,
    FName = function(n) return n end, FText = function(t) return t end })
c.update({}, snap(0, 12), 0)
eq(calls.create, 0, "no widget before it is needed")
c.update({}, snap(0, 10), 0); c.update({}, snap(0, 10), 0.5); c.update({}, snap(0, 9), 1)
eq(calls.create, 1, "one widget"); eq(#calls.text, 2, "text set once per number")
eq(calls.text[1], "10"); eq(calls.text[2], "9")
eq(fakeText.Font.Size, Countdown.SIZE, "font size written before the widget is shown")
eq(fakeText.Font.FontObject.font, true, "the game's countdown face")
c.update({}, snap(0, 1), 9); c.update({}, snap(1, 60), 9.5)
eq(calls.text[#calls.text], "DEPLOY", "the phase edge shows DEPLOY")
c.update({}, snap(1, 60), 12)
eq(calls.visibility[#calls.visibility], 1, "then hides (collapsed)")
local texts = #calls.text
c.update({}, snap(1, 60, "8"), 12.2)
eq(#calls.text, texts, "a new instance in insertion does not replay a launch it never saw")

-- The status line.
local line = Warfare.describe(snap(0, -1))
assert(line:find("WAITING FOR PLAYERS"), line)
line = Warfare.describe(snap(0, 83))
assert(line:find("DEPLOYMENT IN 1:23"), line)
assert(line:find("2 PLAYERS CONNECTED"), line)
print("warfare countdown: ok")

-- Reinforcement waves (60 s interval, 30 s flights).
local function combat(seconds, stage)
    return { phase = 2, instance = "7", connected = 2, reinforcement = { interval = 60, flight = 30 },
        globals = { 2, 0, Warfare.RULES, seconds }, players = { [0] = { stage = stage, localUser = 0 } } }
end
local w = Warfare.wave(combat(12)); eq(w.flying, false); eq(w.departs, 48)
w = Warfare.wave(combat(65)); eq(w.flying, true, "wave 1 in the air")
w = Warfare.wave(combat(95)); eq(w.flying, false); eq(w.departs, 25, "parked for wave 2")
eq(Warfare.wave({ phase = 2, globals = { 2, 0, 0, 5 } }), nil, "no timing, no waves")
local parked = Warfare.describe(combat(37, 2), 0, "SPACE")
assert(parked:find("REINFORCEMENTS DEPART IN 0:23") and parked:find("SPACE: JUMP NOW"), parked)
assert(Warfare.describe(combat(65, 2), 0, "E"):find("E TO JUMP"))
assert(Warfare.describe(combat(37, 1), 0):find("BOARDING"))
eq(Warfare.describe(combat(37, 0), 0), nil, "on foot in combat: the zone tiles say it")
print("warfare reinforcement lines: ok")

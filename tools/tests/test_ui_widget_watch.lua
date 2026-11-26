-- Run from the repository root with Lua 5.4, or Python + lupa.
-- UI.liveWidget with the widget watch (mods/MJOLNIRLobby/Scripts/ui.lua): a
-- class is walked for once, then a hidden or absent menu costs no walk, and a
-- widget made later is found from the watch.
local checks = 0
local function eq(actual, expected, label)
    checks = checks + 1
    assert(actual == expected, (label or "value") .. ": expected " .. tostring(expected) .. ", got " .. tostring(actual))
end

local function widget(name, class, shown)
    local w = { name = name, class = class, shown = shown, valid = true }
    function w.IsValid(self) return self.valid end
    function w.GetFName(self) return { ToString = function() return self.name end } end
    function w.GetClass(self) return { GetFName = function() return { ToString = function() return self.class end } end } end
    function w.IsVisible(self) return self.shown end
    return w
end

local objects, scans, watched = {}, 0, nil
local world = { GetAddress = function() return 7 end }
local pc = { IsValid = function() return true end, GetWorld = function() return world end }
local env = setmetatable({
    FindAllOf = function(class)
        scans = scans + 1
        local out = {}
        for _, w in ipairs(objects) do if w.class == class and w.valid then out[#out + 1] = w end end
        return #out > 0 and out or nil
    end,
    FindFirstOf = function() return { IsValid = function() return true end,
        GameViewport = { GameInstance = { LocalPlayers = { { PlayerController = pc } } } } } end,
    NotifyOnNewObject = function(path, fn)
        eq(path, "/Script/UMG.UserWidget", "one watch on the native widget class")
        watched = fn
    end,
}, { __index = _G })
local UI = assert(loadfile("mods/MJOLNIRLobby/Scripts/ui.lua", "t", env))()

local function shown(w) return w:IsVisible() end
local MENU = "WBP_MainMenu_C"

-- The menu behind the vote: there, but hidden.
local menu = widget("WBP_MainMenu_C_1", MENU, false)
objects[#objects + 1] = widget("Default__WBP_MainMenu_C", MENU, true)
objects[#objects + 1] = menu
eq(UI.liveWidget(MENU, shown), nil, "a hidden menu is not live")
eq(scans, 1, "the first ask walks once")
for _ = 1, 5 do UI.liveWidget(MENU, shown) end
eq(scans, 1, "a hidden menu costs no more walks")

-- A class nobody has made yet: one walk, then none.
eq(UI.liveWidget("WBP_TitleMenu_C", shown), nil, "no title menu")
for _ = 1, 5 do UI.liveWidget("WBP_TitleMenu_C", shown) end
eq(scans, 2, "an absent class is walked for once")

-- The vote ends: the menu shows again.
menu.shown = true
eq(UI.liveWidget(MENU, shown), menu, "the kept menu once shown")

-- A title menu made later is seen from the watch.
local title = widget("WBP_TitleMenu_C_2", "WBP_TitleMenu_C", true)
watched(title)
watched(widget("WBP_Other_C_1", "WBP_Other_C", true))
eq(UI.liveWidget("WBP_TitleMenu_C", shown), title, "a new widget found without a walk")
eq(scans, 2, "still no walk")

-- A freed widget drops out; the newest live one wins.
title.valid = false
local again = widget("WBP_TitleMenu_C_3", "WBP_TitleMenu_C", true)
watched(again)
eq(UI.liveWidget("WBP_TitleMenu_C", shown), again, "freed widget skipped")

-- A churning class keeps only the last 64.
for i = 1, 100 do watched(widget("WBP_Row_C_" .. i, "WBP_Row_C", false)) end
UI.liveWidget("WBP_Row_C", shown) -- registers the class (one walk)
for i = 1, 100 do watched(widget("WBP_Row_C_x" .. i, "WBP_Row_C", false)) end
local rows = widget("WBP_Row_C_last", "WBP_Row_C", true)
watched(rows)
eq(UI.liveWidget("WBP_Row_C", shown), rows, "capped list keeps the newest")
eq(scans, 3, "one walk per class")

print("ui widget watch: " .. checks .. " checks passed")

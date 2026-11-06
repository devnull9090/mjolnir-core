-- Run from the repository root with Lua 5.4.
-- Exercise the actual HUD and key callbacks without a game or UObject cache.
local checks = 0
local function eq(actual, expected)
    checks = checks + 1
    assert(actual == expected, "expected " .. tostring(expected) .. ", got " .. tostring(actual))
end
local function contains(text, part)
    checks = checks + 1
    assert(text:find(part, 1, true), "missing " .. part .. " in " .. text)
end
local function block()
    return setmetatable({
        IsValid = function() return true end,
        AddToViewport = function() end,
        SetText = function(self, text) self.text = text end,
        SetVisibility = function(self, visibility) self.visibility = visibility end,
        SetRenderOpacity = function(self, opacity) self.opacity = opacity end,
        SetColorAndOpacity = function() end,
        SetWidthOverride = function(self, width) self.width = width end,
    }, { __index = function(self, key)
        local child = block()
        rawset(self, key, child)
        return child
    end })
end
local widget, retained = block(), 0
local env = setmetatable({
    FText = function(value) return value end,
    FName = function(value) return value end,
    ExecuteInGameThreadWithDelay = function() end,
    StaticFindObject = function(path)
        if path == "/Script/UMG.Default__WidgetBlueprintLibrary" then
            return { Create = function() eq(retained, 1); return widget end }
        end
        return {
            MakeSoftClassPath = function(_, value) return value end,
            Conv_SoftClassPathToSoftClassRef = function(_, value) return value end,
            LoadClassAsset_Blocking = function() return block() end,
            MakeSoftObjectPath = function(_, value) return value end,
            Conv_SoftObjPathToSoftObjRef = function(_, value) return value end,
            LoadAsset_Blocking = function() return nil end,
        }
    end,
}, { __index = _G })
local Hud = assert(loadfile("mods/MJOLNIRForge/Scripts/hud.lua", "t", env))()
Hud.init({ log = function() end, pc = function() return block() end,
    retainClass = function(_, cls) retained = retained + 1; return cls end })
local keys = {
    toggle = "B", grab = "V", duplicate = "N", delete = "DEL", nearer = "PAGE_DOWN", farther = "PAGE_UP",
    place = "INS", prev_category = "LEFT_ARROW", next_category = "RIGHT_ARROW", prev_item = "UP_ARROW", next_item = "DOWN_ARROW",
    save = "F5", load = "F6", revert = "F2", channel = "P", rotate_left = "OEM_COMMA", rotate_right = "OEM_PERIOD",
    physics = "F3", grid = "F4", rotation_snap = "F10",
}
local row = { palette = 0, entry = 0, group = "bloc", tag = "floor", placeable = true }
local s = { forge = "1", player = "0", editing = "1", held = "ffffffff", cursor = "10001",
    cursor_tag = "player_spawn", cursor_group = "scen", team = "red", physics = "phased", grid_m = "0", rotation_snap = "0" }
eq(Hud.render(s, keys, "Test map", { row }, row), true)
eq(widget.TargetName.text, "Spawn Point  ·  PHASED  ·  RED")
eq(widget.Control2Key.text, "F3")
eq(widget.Control2Act.text, "PHYSICS PHASED")
eq(widget.Control2.opacity, 1)
eq(widget.Control3Key.text, "F4")
eq(widget.Control3Act.text, "GRID OFF")
eq(widget.Control4Key.text, "F10")
eq(widget.Control4Act.text, "SNAP OFF")
contains(widget.PaletteTitle.text, "[F4] GRID OFF")
contains(widget.PaletteTitle.text, "[F10] SNAP OFF")
contains(widget.PaletteTitle.text, "[, / .] TURN 22.5°")
eq(widget.Target1Act.text, "DUPLICATE")
eq(widget.Target2Act.text, "DELETE")

-- The next native snapshot, not the last target, controls visibility and
-- properties. No cursor/tag/team/physics in a partial snapshot means no card.
s = { forge = "1", player = "0", editing = "1", grid_m = "0.25", rotation_snap = "45" }
Hud.render(s, keys, "Test map", {}, nil)
eq(widget.TargetCard.visibility, 1)
eq(widget.TargetName.text, "")
eq(widget.TargetCategory.text, "")
eq(widget.DistanceRow.visibility, 1)
eq(widget.Control2Act.text, "PHYSICS")
eq(widget.Control2.opacity, 0.35)
eq(widget.Control3Act.text, "GRID 0.25 m")
eq(widget.Control4Act.text, "SNAP 45°")
eq(widget.Control5.opacity, 0.35)
eq(widget.PaletteSize.visibility, 1)

-- A different target cannot inherit the spawn point's properties. Settings
-- and key hints are native-authoritative and follow remapped keys.
s.cursor, s.cursor_tag, s.cursor_group, s.physics = "20002", "floor", "bloc", "fixed"
keys.physics, keys.grid, keys.rotation_snap, keys.channel = "H", "I", "U", "M"
Hud.render(s, keys, "Test map", { row }, row)
eq(widget.TargetName.text, "Floor  ·  FIXED")
eq(widget.TargetCard.visibility, 3)
eq(widget.Control2Key.text, "H")
eq(widget.Control3Key.text, "I")
eq(widget.Control4Key.text, "U")
contains(widget.PaletteTitle.text, "[I] GRID 0.25 m")
contains(widget.PaletteTitle.text, "[U] SNAP 45°")
contains(widget.PaletteTitle.text, "[, / .] TURN 45°")
eq(Hud.properties({ channel = "alpha", physics = "normal" }, keys), "  ·  NORMAL  ·  CHANNEL ALPHA [M]")

s.held, s.held_tag, s.held_group, s.distance = "20002", "floor", "bloc", "3.5"
Hud.render(s, keys, "Test map", { row }, row)
eq(widget.Control1Act.text, "DROP")
eq(widget.Target0Act.text, "DROP")
eq(widget.Target1Act.text, "DISTANCE")
eq(widget.Target2Act.text, "DELETE")
eq(widget.DistanceValue.text, "3.5 m")
eq(widget.DistanceRow.visibility, 3)

-- A legacy DLL retains all old controls, with no fictitious settings.
s.physics, s.grid_m, s.rotation_snap = nil, nil, nil
Hud.render(s, keys, "Test map", { row }, row)
eq(widget.Control2Act.text, "DUPLICATE")
eq(widget.Control3Act.text, "DELETE")
eq(widget.Control4Act.text, "DISTANCE")
eq(widget.PaletteTitle.text, "PALETTE")
eq(widget.TargetName.text, "Floor")
s.editing = "0"
Hud.render(s, keys, "Test map", { row }, row)
eq(widget.TargetCard.visibility, 1)
eq(widget.Control1Act.text, "SAVE LAYOUT")
eq(widget.Control4.visibility, 1)
eq(widget.PaletteSize.visibility, 1)
s.forge = "0"
Hud.render(s, keys, "", {}, nil)
eq(widget.visibility, 1)

for _, value in ipairs({ "0", "0.25", "0.5", "1", "2", "4" }) do
    eq(Hud.gridName(value), value == "0" and "OFF" or (value .. " m"))
end
for _, value in ipairs({ "90", "45", "30", "15", "5" }) do eq(Hud.rotationName(value), value .. "°") end
for _, value in ipairs({ "", "-1", "nan", "inf", "bogus", "22.5", "10000" }) do
    eq(Hud.physicsName(value), nil)
    eq(Hud.gridName(value), nil)
    eq(Hud.rotationName(value), nil)
end
eq(Hud.properties({}), "")
eq(Hud.physicsName(nil), nil)
eq(Hud.gridName(nil), nil)
eq(Hud.rotationName(nil), nil)
eq(Hud.editSettings({}, keys), "")
eq(Hud.notice("physics fixed", "Floor"), "PHYSICS  FIXED")
eq(Hud.notice("press again: saved layout goes to history", "Floor", keys),
    "PRESS F2 AGAIN FOR THE MAP'S OWN LAYOUT  YOUR SAVE GOES TO HISTORY")
eq(Hud.notice("press again: map's own layout", "Floor", { revert = "PAGE_UP" }),
    "PRESS PG UP AGAIN FOR THE MAP'S OWN LAYOUT  UNSAVED OBJECTS ARE LOST")
eq(Hud.notice("reverted: saved layout moved to history", "Floor", keys), "THE MAP'S OWN LAYOUT  F6 BRINGS YOUR SAVE BACK")
eq(Hud.notice("reverted to the map's own layout", "Floor", keys), "THE MAP'S OWN LAYOUT")
eq(Hud.notice("restored layout BGL, 127 objects", "Floor", keys), "SAVED LAYOUT RESTORED  127 OBJECTS")
eq(Hud.notice("load failed: cannot restore the layout from history", "Floor", keys),
    "LOAD FAILED: CANNOT RESTORE THE LAYOUT FROM HISTORY")

-- Load the real main.lua in isolation: commands dispatch once, support key
-- overrides, respect match chat, and an old DLL still opens and handles V.
local function keyHarness(overrides, legacy)
    local time, focused = 1, false
    local binds, calls, delayed, pumps, logs = {}, {}, {}, {}, {}
    local chat = { IsValid = function() return true end, IsInViewport = function() return true end,
        GetFName = function() return { ToString = function() return "WBP_MJOLNIRChat_C_1" end } end,
        ChatInput = { HasKeyboardFocus = function() return focused end } }
    local testenv
    testenv = setmetatable({
        Key = setmetatable({}, { __index = function(_, name) return name end }),
        os = { clock = function() return time end },
        print = function(message) logs[#logs + 1] = message end,
        io = { open = function(path)
            if path:match("keys%.txt$") then return { read = function() return overrides or "" end, close = function() end } end
        end },
        RegisterKeyBind = function(key, _, callback) binds[key] = callback end,
        FindAllOf = function() return { chat } end,
        ExecuteInGameThreadWithDelay = function(delay, callback) delayed[delay] = callback end,
        LoopAsync = function(_, callback) pumps[#pumps + 1] = callback end,
        package = { loadlib = function(_, name)
            local action = name:match("mjolnir_forge_(.+)")
            if legacy and (action == "physics" or action == "grid" or action == "rotation_snap") then return nil, "missing export" end
            return function() calls[action] = (calls[action] or 0) + 1 end
        end },
        dofile = function(path)
            if path:match("class_lifetime%.lua$") then return { new = function() return function(_, cls) return cls end end } end
            if path:match("lights%.lua$") then return { new = function() return { setInventory = function() end } end } end
            return assert(loadfile(path:gsub("\\", "/"), "t", testenv))()
        end,
    }, { __index = _G })
    assert(loadfile("mods/MJOLNIRForge/Scripts/main.lua", "t", testenv))()
    delayed[5000]()
    eq(calls.open, 1)
    eq(#pumps, 1)
    return binds, calls, function(typing) time = time + 1; focused = typing end
end
local binds, calls, advance = keyHarness()
for key, action in pairs({ F3 = "physics", F4 = "grid", F10 = "rotation_snap" }) do
    binds[key](); binds[key]()
    eq(calls[action], 1)
    advance(true); binds[key](); eq(calls[action], 1)
    advance(false); binds[key](); eq(calls[action], 2)
end
binds, calls = keyHarness("physics=H\ngrid=I\nrotation_snap=U\n")
eq(binds.F3, nil); eq(binds.F4, nil); eq(binds.F10, nil)
binds.H(); binds.I(); binds.U()
eq(calls.physics, 1); eq(calls.grid, 1); eq(calls.rotation_snap, 1)
binds, calls = keyHarness(nil, true)
binds.V(); binds.F3(); binds.F4(); binds.F10()
eq(calls.grab, 1); eq(calls.physics, nil); eq(calls.grid, nil); eq(calls.rotation_snap, nil)
print("Forge editor controls: " .. checks .. " checks passed")

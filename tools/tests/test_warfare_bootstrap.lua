-- Event bootstrap runs without Unreal; no game mutation is involved.
local Modes = dofile("mods/MJOLNIRLobby/Scripts/modes.lua")
local descriptors = dofile("mods/MJOLNIRLevelLoader/Scripts/mode_descriptors.lua")
assert(Modes.register(descriptors.warfare))
assert(not Modes.register(descriptors.warfare))
assert(Modes.byId("warfare").teams and Modes.slot("warfare") == 3)
assert(descriptors.warfare.maps.PWR and not descriptors.warfare.maps.BGL)
assert(descriptors.warfare.fixedSettings.lives == 0)

local calls, files, loops, bound = {}, {}, {}, {}
local originalLoadlib, originalOpen = package.loadlib, io.open
package.loadlib = function(path, symbol)
    assert(path == "C:\\Mods\\MJOLNIRLobby\\native\\mjolnir_lobby.dll")
    -- The config goes to the DLL in memory (mjolnir_request_put).
    if symbol == "mjolnir_request_put" then
        return function(name, text) files["C:\\Mods\\MJOLNIRLobby\\native\\" .. name] = text; return true end
    end
    return function() calls[symbol] = (calls[symbol] or 0) + 1; return true end
end
-- A development PC (its mark file): the 2 Hz pump for the smoke tools runs.
local originalGetenv = os.getenv
os.getenv = function(name) return name == "LOCALAPPDATA" and "C:\\Local" or originalGetenv(name) end
io.open = function(path, mode)
    if mode == "rb" then
        assert(path == "C:\\Local\\Meteorite\\Saved\\mjolnir_dev.txt")
        return { close = function() end }
    end
    assert(mode == "wb")
    return { write = function(_, text) files[path] = text end, close = function() end }
end
RegisterKeyBind = function(key, _, fn) bound[key] = fn end
RegisterConsoleCommandHandler = function(_, fn) bound.console = fn end
local w = dofile("mods/MJOLNIRLevelLoader/Scripts/warfare.lua")
w.init("C:\\Mods\\MJOLNIRLevelLoader", function() end,
    function(ms, _, fn) assert(ms == 500); loops[#loops + 1] = fn end)
w.select("BGL", "slayer")
assert(not w.active)
w.select("PWR", "warfare")
assert(not w.active and not calls.mjolnir_warfare_open, "missing map revision must fail closed")
w.select("PWR", "warfare", { protocol = 20568, layout_revision = 2 })
assert(not w.active and not calls.mjolnir_warfare_open, "old map revision must fail closed")
local layout = { protocol = 20569, layout_revision = 3 }
w.select("PWR", "warfare", layout)
assert(w.active and calls.mjolnir_warfare_open == 1)
w.select("PWR", "warfare", layout)
assert(calls.mjolnir_warfare_open == 1, "duplicate travel must not reset deployment")
assert(#loops == 1)
loops[1]()
assert(calls.mjolnir_warfare_pump == 1)
assert(not bound[0x20], "modern local controller handles remapped Jump")
bound.console()
assert(calls.mjolnir_warfare_action == 1)
w.select(nil, nil)
assert(not w.active and calls.mjolnir_warfare_close == 1)
bound.console()
loops[1]()
assert(calls.mjolnir_warfare_action == 1 and calls.mjolnir_warfare_pump == 1)
local configs = 0
for path, content in pairs(files) do
    assert(path == "C:\\Mods\\MJOLNIRLobby\\native\\warfare_config.txt")
    assert(content == "warfare-config 2\nmap PWR\nlayout 3\nprotocol 20569\n"); configs = configs + 1
end
assert(configs == 1)
package.loadlib, io.open = originalLoadlib, originalOpen

-- A player's PC (no mark): no pump loop at all; the HUD reads the snapshot
-- from memory.
os.getenv = function(name) return name == "LOCALAPPDATA" and "C:\\Local" or originalGetenv(name) end
local playerLoops = {}
package.loadlib = function() return function() return true end end
io.open = function(_, mode) if mode == "rb" then return nil end return { write = function() end, close = function() end } end
package.loaded["mods/MJOLNIRLevelLoader/Scripts/warfare.lua"] = nil
local p = dofile("mods/MJOLNIRLevelLoader/Scripts/warfare.lua")
p.init("C:\\Mods\\MJOLNIRLevelLoader", function() end, function(_, _, fn) playerLoops[#playerLoops + 1] = fn end)
assert(#playerLoops == 0, "a player's game registers no warfare pump")
package.loadlib, io.open, os.getenv = originalLoadlib, originalOpen, originalGetenv
print("Warfare bootstrap: descriptor, map gate, event-only input, 2Hz snapshot, travel cleanup passed")

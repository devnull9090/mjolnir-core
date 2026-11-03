-- Run from the repository root with Lua 5.4, or Python + lupa.
-- Models class collection during travel, including UE4SS's surviving field
-- cache, and ensures retaining a class never retains a displayed map widget.
local checks = 0
local function eq(actual, expected, label)
    checks = checks + 1
    assert(actual == expected, (label or "value") .. ": expected " .. tostring(expected) .. ", got " .. tostring(actual))
end
local function read(path)
    local f = assert(io.open(path, "rb"))
    local text = f:read("*a"):gsub("\r\n", "\n")
    f:close()
    return text
end
local source = read("mods/MJOLNIRHud/Scripts/class_lifetime.lua")
for _, mod in ipairs({ "MJOLNIRLobby", "MJOLNIRForge" }) do
    eq(read("mods/" .. mod .. "/Scripts/class_lifetime.lua"), source, "self-contained helpers stay identical")
end
local Lifetime = assert(load(source))()
local NAME = "WBP_MJOLNIRKillFeed"
local PATH = "/Game/MJOLNIR/UI/" .. NAME .. "." .. NAME .. "_C"
local PIN = "/Engine/Transient.MJOLNIR_UI_ClassPin_" .. NAME
EObjectFlags = { RF_Transient = 64 }
EInternalObjectFlags = { RootSet = 1073741824 }
FName = function(name) return name end

local function fixture()
    local f = { objects = {}, created = {}, logs = {}, classes = {}, worlds = {}, engineAvailable = true }
    local package = { IsValid = function() return true end, GetFullName = function() return "Package /Engine/Transient" end }
    local engine = { IsValid = function() return true end, GetOuter = function() return f.outer or package end }
    StaticFindObject = function(path) return f.objects[path] end
    FindFirstOf = function(name)
        eq(name, "GameEngine", "only the process engine supplies the outer")
        return f.engineAvailable and engine or nil
    end
    StaticConstructObject = function(cls, outer, name, flags, internal)
        if f.constructError then error("construction unavailable") end
        eq(outer, package, "pin has no world or controller outer")
        eq(flags, 64, "transient object")
        eq(internal, 1073741824, "root flag")
        local obj = { cls = cls, rooted = not f.noRoot, valid = true }
        obj.IsValid = function(self) return self.valid end
        obj.IsA = function(self, expected) return self.cls == expected end
        obj.HasAnyInternalFlags = function(self, flag) return self.rooted and flag == 1073741824 end
        f.created[#f.created + 1] = obj
        f.objects["/Engine/Transient." .. name] = obj
        return obj
    end
    function f.class()
        local cls = { valid = true, field = { valid = true } }
        cls.IsValid = function(self) return self.valid end
        f.classes[#f.classes + 1] = cls
        return cls
    end
    function f.display(cls)
        local w = { cls = cls, valid = true }
        f.worlds[#f.worlds + 1] = w
        return w
    end
    function f.travel()
        -- The old world is released even while its UI class is retained.
        for _, w in ipairs(f.worlds) do w.valid = false end
        for _, cls in ipairs(f.classes) do
            local retained = false
            for _, obj in pairs(f.objects) do retained = retained or (obj.rooted and obj.cls == cls) end
            if not retained then cls.valid, cls.field.valid = false, false end
        end
    end
    function f.keeper(names)
        return Lifetime.new(names or { NAME }, function(message) f.logs[#f.logs + 1] = message end)
    end
    return f
end

-- A surviving reflection pointer alone does not keep its class alive.
local f = fixture()
local cls = f.class()
local cachedField = cls.field
f.display(cls)
f.travel()
eq(cachedField.valid, false, "unretained class leaves a dangling reflection field")

f = fixture()
cls = f.class()
cachedField = cls.field
local keep = f.keeper()
eq(keep(PATH, cls), cls, "retain before reading widget members")
for i = 1, 4 do
    local displayed = f.display(cls)
    f.travel()
    eq(displayed.valid, false, "travel releases displayed widget " .. i)
    eq(cachedField.valid, true, "cached metadata survives travel " .. i)
    eq(keep(PATH, cls), cls, "next map reuses retained class " .. i)
end
eq(#f.created, 1, "one bounded instance across maps")
eq(f.keeper()(PATH, cls), cls, "script reload finds existing named root")
eq(#f.created, 1, "script reload does not accumulate roots")

local forgeName = "WBP_MJOLNIRForge"
local forgePath = "/Game/MJOLNIR/ForgeUI/" .. forgeName .. "." .. forgeName .. "_C"
local forgeClass = f.class()
eq(f.keeper({ forgeName })(forgePath, forgeClass), forgeClass, "Forge UI class uses separate allowlist")
eq(#f.created, 2, "each explicitly allowed class has one root")
for _, bad in ipairs({
    "/Game/Custom/" .. NAME .. "." .. NAME .. "_C",
    "/Game/MJOLNIR/UI/WBP_MJOLNIROther.WBP_MJOLNIROther_C",
    "/Game/MJOLNIR/UI/" .. NAME .. ".Other_C",
    "/Game/MJOLNIR/UI/../" .. NAME .. "." .. NAME .. "_C",
}) do eq(keep(bad, cls), nil, "unapproved class cannot be rooted") end
eq(keep(nil, cls), nil, "missing path fails safely")
eq(#f.created, 2, "rejected names create no roots")

f = fixture()
cls, keep = f.class(), f.keeper()
f.engineAvailable = false
eq(keep(PATH, cls), nil, "missing transient package delays UI")
eq(keep(PATH, cls), nil, "failure can retry")
eq(#f.logs, 1, "repeated failure logs once")
f.engineAvailable = true
eq(keep(PATH, cls), cls, "later retry recovers before UI creation")

for _, failure in ipairs({ "noRoot", "constructError", "wrongOuter", "wrongClass", "invalidClass" }) do
    f = fixture()
    cls, keep = f.class(), f.keeper()
    if failure == "wrongOuter" then
        f.outer = { IsValid = function() return true end, GetFullName = function() return "World /Game/Map" end }
    elseif failure == "wrongClass" then
        local other = f.class()
        f.objects[PIN] = { IsValid = function() return true end, IsA = function(_, c) return c == other end }
    elseif failure == "invalidClass" then cls.valid = false
    else f[failure] = true end
    eq(keep(PATH, cls), nil, "failure prevents unprotected UI: " .. failure)
    eq(#f.logs, 1, "failure is actionable: " .. failure)
end

-- Integration guard: every loaded HUD/Lobby class must pass through the
-- keeper before any Create/BP_AddWidget call can receive it.
for _, mod in ipairs({ "MJOLNIRHud", "MJOLNIRLobby" }) do
    local main = read("mods/" .. mod .. "/Scripts/main.lua")
    eq(main:find("return retainUIClass(path, cls)", 1, true) ~= nil, true, mod .. " loadClass retention")
end

-- Native searches include rooted pins and old-world widgets. Never treat
-- validity alone as proof that a screen is displayed or can receive input.
local function widget(name, viewport, focused)
    return { IsValid = function() return true end,
        GetFName = function() return { ToString = function() return name end } end,
        IsInViewport = function() return viewport end,
        ChatInput = { HasKeyboardFocus = function() return focused end } }
end
local pin = widget("MJOLNIR_UI_ClassPin_WBP_MJOLNIRChat", true, true)
local default = widget("Default__WBP_MJOLNIRChat_C", true, true)
local old = widget("WBP_MJOLNIRChat_C_1", false, true)
local current = widget("WBP_MJOLNIRChat_C_2", true, true)
local found, scans, clock = { pin, default, old, current }, 0, 10
local world = { GetAddress = function() return 10 end }
local pc = { IsValid = function() return true end, GetWorld = function() return world end }
local env = setmetatable({
    FindAllOf = function() scans = scans + 1; return found end,
    FindFirstOf = function() return { IsValid = function() return true end,
        GameViewport = { GameInstance = { LocalPlayers = { { PlayerController = pc } } } } } end,
    os = { clock = function() return clock end },
}, { __index = _G })
local ui = assert(loadfile("mods/MJOLNIRLobby/Scripts/ui.lua", "t", env))()
local aliveCalls = 0
eq(ui.liveWidget("WBP_MJOLNIRChat_C", function(w)
    aliveCalls = aliveCalls + 1
    assert(w ~= pin and w ~= default, "inactive class pins/defaults never reach screen callbacks")
    return w:IsInViewport()
end), current, "screen discovery skips pin, default and previous world")
eq(aliveCalls, 2, "only real widget instances examined")
eq(ui.liveWidget("WBP_MJOLNIRChat_C", function() return true end), current, "live screen cached")
eq(scans, 1, "cached screen avoids object scan")

local main = read("mods/MJOLNIRForge/Scripts/main.lua")
local chatFunctions = assert(main:match("(local chat =.-)\n%-%- A bind"))
local typing = assert(load(chatFunctions .. "\nreturn typingInChat", "Forge chat lookup", "t", env))()
eq(typing(), true, "focused live chat suppresses Forge binds despite earlier pin")
local before = scans
eq(typing(), true, "focused live chat reused")
eq(scans, before, "live chat avoids repeated scans")
current.IsInViewport = function() return false end
eq(typing(), false, "old chat released immediately after travel")
clock = clock + 3
found = { pin, default, old }
eq(typing(), false, "pins alone never consume Forge input")
clock = clock + 3
found[#found + 1] = widget("WBP_MJOLNIRChat_C_3", true, true)
eq(typing(), true, "discovery retries when new world's chat arrives")
print("UI class lifetime: " .. checks .. " checks passed")

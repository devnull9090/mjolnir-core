-- Run from the repository root with Lua 5.4, or Python + lupa.
-- HubNames.avatar (mods/MJOLNIRHud/Scripts/hubnames.lua): a kept texture is
-- reused; a collected one is imported again, never looked for by name (a
-- StaticFindObject that only misses, ~22 ms on a map).
local checks = 0
local function eq(actual, expected, label)
    checks = checks + 1
    assert(actual == expected, (label or "value") .. ": expected " .. tostring(expected) .. ", got " .. tostring(actual))
end

local covers = os.tmpname() .. "_covers"
local function texture(n)
    local t = { valid = true, n = n }
    function t.IsValid(self) return self.valid end
    function t.Blueprint_GetSizeX() return 128 end
    function t.Blueprint_GetSizeY() return 128 end
    function t.GetFullName(self) return "Texture2D /Engine/Transient.Texture2D_" .. self.n end
    return t
end
local imports, finds = 0, {}
local library = {
    IsValid = function() return true end,
    ImportFileAsTexture2D = function(_, _, path)
        imports = imports + 1
        assert(path:find("av_abc%.png$"), "the cached avatar file")
        return texture(imports)
    end,
}
local env = setmetatable({
    StaticFindObject = function(path)
        finds[#finds + 1] = path
        assert(path == "/Script/Engine.Default__KismetRenderingLibrary", "no lookup by texture name: " .. path)
        return library
    end,
}, { __index = _G })
local HubNames = assert(loadfile("mods/MJOLNIRHud/Scripts/hubnames.lua", "t", env))()

-- The avatar file the Lobby caches; HubNames.init takes the Mods folder.
local dir = covers .. "\\MJOLNIRMaps\\_covers\\"
local real = io.open
env.io = setmetatable({ open = function(path, mode)
    if path == dir .. "av_abc.png" then return { close = function() end } end
    return real(path, mode)
end }, { __index = io })
HubNames.init({ modsDir = covers .. "\\Mods" })

local world = {}
local first = HubNames.avatar("abc", world)
eq(imports, 1, "first use imports")
eq(HubNames.avatar("abc", world), first, "a kept texture is reused")
eq(imports, 1, "no import while kept")

first.valid = false -- collected once no feed line or board held it
local second = HubNames.avatar("abc", world)
eq(imports, 2, "a collected texture is imported again")
assert(second ~= first, "the new texture")
eq(#finds, 1, "the rendering library looked up once, nothing else")

eq(HubNames.avatar(nil, world), nil, "no account, no avatar")
print("hub avatars: " .. checks .. " checks passed")

-- MJOLNIR HUD: hub accounts in place of in-game names
-- (docs/player_identity.md).
--
-- MJOLNIRLobby learns which hub (Discord) account each player is, proven to
-- the host by tickets, and writes it to its identities.txt:
-- "<in-game name>\t<account id>\t<hub name>\t<reports>" per player. It also
-- caches each account's avatar as MJOLNIRMaps\_covers\av_<id>.png. The HUD
-- only reads them: names for the scoreboard, kill feed and name tags, and
-- avatars for the scoreboard.

local HubNames = {}

local RELOAD_SECONDS = 2

local file, coversDir
local known = {}         -- [in-game name] = { id, name, reports }
local nextLoad = 0
local textures = {}      -- account id -> texture object name

local function valid(o)
    local ok, v = pcall(function() return o and o:IsValid() end)
    return ok and v
end

local function load()
    if os.clock() < nextLoad then return end
    nextLoad = os.clock() + RELOAD_SECONDS
    local f = io.open(file, "rb")
    if not f then
        known = {}
        return
    end
    local text = f:read("*a")
    f:close()
    local next_ = {}
    for line in text:gmatch("[^\r\n]+") do
        local platform, id, name, reports = line:match("^([^\t]*)\t([%x%-]+)\t([^\t]*)\t(%d*)$")
        if platform and platform ~= "" then
            next_[platform] = { id = id, name = name ~= "" and name or platform, reports = tonumber(reports) or 0 }
        end
    end
    known = next_
end

--- The hub account behind in-game name `name`: { id, name, reports } or nil.
function HubNames.of(name)
    if not name then return nil end
    load()
    return known[name]
end

--- Account `id`'s avatar as a texture, once MJOLNIRLobby has cached it.
--- Kept by name, never by reference: a transient texture no brush holds is
--- collected.
function HubNames.avatar(id, world)
    if not id then return nil end
    if textures[id] then
        local ok, tex = pcall(StaticFindObject, textures[id])
        if ok and valid(tex) then return tex end
    end
    local path = coversDir .. "av_" .. id .. ".png"
    local f = io.open(path, "rb")
    if not f then return nil end
    f:close()
    local krl = StaticFindObject("/Script/Engine.Default__KismetRenderingLibrary")
    if not (valid(krl) and world) then return nil end
    local ok, tex = pcall(function() return krl:ImportFileAsTexture2D(world, path) end)
    if not (ok and valid(tex)) then return nil end
    local okName, full = pcall(function() return tex:GetFullName() end)
    textures[id] = okName and full and full:match("^%S+%s+(.+)$") or nil
    return tex
end

--- deps: { modsDir } (the UE4SS Mods folder).
function HubNames.init(deps)
    file = deps.modsDir .. "\\MJOLNIRLobby\\identities.txt"
    coversDir = (deps.modsDir:match("^(.*)\\Mods$") or deps.modsDir) .. "\\MJOLNIRMaps\\_covers\\"
end

return HubNames

-- MJOLNIR HUD: hub accounts in place of in-game names
-- (docs/player_identity.md).
--
-- MJOLNIRLobby learns which hub (Discord) account each player is, proven to
-- the host by tickets, and shares it in the UE4SS shared variable
-- MJOLNIR.identities (its identities.txt without one):
-- "<in-game name>\t<account id>\t<hub name>\t<reports>" per player. It also
-- caches each account's avatar as MJOLNIRMaps\_covers\av_<id>.png. The HUD
-- only reads them: names for the scoreboard, kill feed and name tags, and
-- avatars for the scoreboard.

local HubNames = {}

local RELOAD_SECONDS = 2

local file, coversDir
local known = {}         -- [in-game name] = { id, name, reports }
local nextLoad = 0
local renderingLibrary = nil
local handles = {}       -- account id -> the texture, while it is valid
local sizes = {}         -- account id -> "<w>x<h>" of the imported texture

local function valid(o)
    local ok, v = pcall(function() return o and o:IsValid() end)
    return ok and v
end

local SHARED_KEY = "MJOLNIR.identities"
local lastText = nil
local function getShared(modRef) return modRef:GetSharedVariable(SHARED_KEY) end

--- The Lobby's roster text: its shared variable, or identities.txt from a
--- Lobby that set none.
local function rosterText()
    local modRef = rawget(_G, "ModRef")
    if modRef then
        local ok, shared = pcall(getShared, modRef)
        if ok and type(shared) == "string" then return shared end
    end
    local f = io.open(file, "rb")
    if not f then return nil end
    local text = f:read("*a")
    f:close()
    return text
end

local function load()
    if os.clock() < nextLoad then return end
    nextLoad = os.clock() + RELOAD_SECONDS
    local text = rosterText()
    if text == lastText then return end
    lastText = text
    if not text then
        known = {}
        return
    end
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

--- "<w>x<h>" of a texture, or nil.
local function sizeOf(tex)
    local ok, w, h = pcall(function() return tex:Blueprint_GetSizeX(), tex:Blueprint_GetSizeY() end)
    return ok and w and h and (w .. "x" .. h) or nil
end

--- Whether `tex` is still the avatar imported for `id`: a transient texture
--- that was collected leaves its name and its memory to the next one
--- imported (a converted map's terrain), which drew as the avatar.
local function stillAvatar(id, tex)
    return valid(tex) and sizes[id] ~= nil and sizeOf(tex) == sizes[id]
end

--- Account `id`'s avatar as a texture, once MJOLNIRLobby has cached it.
--- The texture is kept and checked before each use. A transient texture no
--- brush holds is collected, and then it is imported again (0.1 ms). It was
--- looked for by name first, but a collected texture is gone, so that
--- StaticFindObject only ever missed, at ~22 ms on a map: a hitch on every
--- kill line once the last line showing the avatar had gone (2026-11-25).
function HubNames.avatar(id, world)
    if not id then return nil end
    if handles[id] and stillAvatar(id, handles[id]) then return handles[id] end
    local path = coversDir .. "av_" .. id .. ".png"
    local f = io.open(path, "rb")
    if not f then return nil end
    f:close()
    if not valid(renderingLibrary) then
        renderingLibrary = StaticFindObject("/Script/Engine.Default__KismetRenderingLibrary")
    end
    local krl = renderingLibrary
    if not (valid(krl) and world) then return nil end
    local ok, tex = pcall(function() return krl:ImportFileAsTexture2D(world, path) end)
    if not (ok and valid(tex)) then return nil end
    handles[id], sizes[id] = tex, sizeOf(tex)
    return tex
end

--- deps: { modsDir } (the UE4SS Mods folder).
function HubNames.init(deps)
    file = deps.modsDir .. "\\MJOLNIRLobby\\identities.txt"
    coversDir = (deps.modsDir:match("^(.*)\\Mods$") or deps.modsDir) .. "\\MJOLNIRMaps\\_covers\\"
end

return HubNames

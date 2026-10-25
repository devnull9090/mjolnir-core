-- A small, game-side publisher. Only this module writes Discord's activity;
-- MJOLNIRHud publishes a fresh, session-bound snapshot of its own Lua state.
local Presence = {}
local MODES = { slayer = "Slayer", team_slayer = "Team Slayer", ctf = "Capture the Flag",
    koth = "King of the Hill", oddball = "Oddball", forge = "Forge" }
local context, nativeDir, hudFile, session, Json, log, nativeUpdate

local function text(value, limit)
    local s = tostring(value or ""):gsub("[%c]", " ")
    local parts, size, i = {}, 0, 1
    -- LuaJIT has no utf8 library. Walk complete UTF-8 sequences so neither a
    -- Discord byte limit nor the snapshot writer's bound splits a codepoint.
    -- Invalid input bytes are dropped rather than sending invalid JSON text.
    while i <= #s do
        local lead = s:byte(i)
        local width = lead < 0x80 and 1 or (lead >= 0xC2 and lead <= 0xDF and 2)
            or (lead >= 0xE0 and lead <= 0xEF and 3) or (lead >= 0xF0 and lead <= 0xF4 and 4) or 0
        local valid = width > 0 and i + width - 1 <= #s
        for offset = 1, width - 1 do
            local b = s:byte(i + offset)
            if not b or b < 0x80 or b > 0xBF then valid = false end
        end
        local second = s:byte(i + 1)
        if valid and width >= 3 and ((lead == 0xE0 and second < 0xA0)
            or (lead == 0xED and second > 0x9F) or (lead == 0xF0 and second < 0x90)
            or (lead == 0xF4 and second > 0x8F)) then valid = false end
        if valid then
            if size + width > limit then break end
            parts[#parts + 1] = s:sub(i, i + width - 1)
            size, i = size + width, i + width
        else
            i = i + 1
        end
    end
    return table.concat(parts)
end

local function read(path, limit)
    local f = io.open(path, "rb")
    if not f then return nil end
    local raw = f:read(limit + 1)
    f:close()
    return raw and #raw <= limit and raw or nil
end

function Presence.snapshot(raw, expectedSession, now)
    if type(raw) ~= "string" or #raw > 2048 then return nil end
    local s = {}
    for key, value in raw:gmatch("([a-z_]+)=([^\r\n]*)") do s[key] = value end
    local at, started = tonumber(s.at), tonumber(s.started)
    if s.session ~= expectedSession or not at or at > now + 2 or now - at > 4
        or s.active ~= "1" or not s.code or #s.code > 24 or not s.code:match("^[A-Z0-9_]+$") then return nil end
    s.kills, s.deaths = tonumber(s.kills), tonumber(s.deaths)
    if not s.kills or not s.deaths or s.kills < 0 or s.deaths < 0
        or s.kills > 1000000 or s.deaths > 1000000 or s.kills % 1 ~= 0 or s.deaths % 1 ~= 0 then return nil end
    s.title, s.mode = text(s.title or s.code, 120), text(s.mode or "Multiplayer", 40)
    s.started = started and started > 0 and started <= now and math.floor(started) or nil
    s.players, s.over = tonumber(s.players), s.over == "1"
    return s
end

function Presence.activity(info, hud, public)
    info = info or {}
    local activity = { name = "MJOLNIR Core", type = 0, instance = true }
    if hud and not info.frontend and info.world_code == hud.code then
        activity.details = text((hud.title ~= "" and hud.title or hud.code) .. " | "
            .. (MODES[hud.mode] or hud.mode or "Multiplayer"), 120)
        activity.state = (hud.over and "Match finished | " or "")
            .. string.format("%d kills | %d deaths (observed)", hud.kills, hud.deaths)
        if hud.started and not hud.over then activity.timestamps = { start = hud.started } end
    elseif info.frontend then
        if info.lobby and info.map_title then
            activity.details = text(info.map_title .. " | " .. (MODES[info.mode] or info.mode or "Multiplayer"), 120)
            activity.state = info.postgame and "Post-game lobby" or "In multiplayer lobby"
        else
            activity.details, activity.state = "Main menu", "Choosing a game"
        end
    else
        activity.details, activity.state = "In game", "Loading or playing"
    end
    -- An old HUD snapshot can never make a finished or loading game joinable.
    if public then
        activity.party = { id = "mjolnir:" .. public.id, size = { public.players, public.maxPlayers } }
        if public.joinable and (info.frontend or (hud and not hud.over and info.world_code == hud.code)) then
            activity.secrets = { join = "mjolnir:v1:" .. public.id }
            activity.supported_platforms = { "desktop" }
        end
    end
    return activity
end

-- Stable key ordering avoids spurious updates in the native deduplicator.
function Presence.encode(value)
    if value == nil then return "null" end
    if type(value) == "string" then
        return '"' .. value:gsub('[%c"\\]', function(c) return string.format("\\u%04x", c:byte()) end) .. '"'
    end
    if type(value) ~= "table" then return tostring(value) end
    local parts = {}
    if #value > 0 then
        for _, v in ipairs(value) do parts[#parts + 1] = Presence.encode(v) end
        return "[" .. table.concat(parts, ",") .. "]"
    end
    local keys = {}
    for k in pairs(value) do keys[#keys + 1] = k end
    table.sort(keys)
    for _, k in ipairs(keys) do parts[#parts + 1] = Presence.encode(k) .. ":" .. Presence.encode(value[k]) end
    return "{" .. table.concat(parts, ",") .. "}"
end

function Presence.context(fn) context = fn end

function Presence.init(deps)
    nativeDir = deps.modDir .. "\\native\\"
    hudFile = deps.modDir .. "\\..\\MJOLNIRHud\\discord_match.txt"
    Json, log = deps.json, deps.log
    -- The marker prevents a previous process's snapshot being reused even if
    -- the player restarts the game within the freshness window.
    session = tostring(os.time()) .. "-" .. tostring({}):gsub("[^%w]", "")
    local f = io.open(nativeDir .. "discord_session.txt", "wb")
    if f then f:write(session); f:close() end
    local function publish()
        local info, public
        if context then info, public = context() end
        local hud = Presence.snapshot(read(hudFile, 2048), session, os.time())
        local activity = Presence.activity(info, hud, public)
        -- Optional configured image keys or external images; absent by default.
        local ok, assets = pcall(Json.decode, read(nativeDir .. "discord_assets.json", 2048) or "")
        if ok and type(assets) == "table" then
            local key = hud and hud.code:lower() or "default"
            local image = assets[key] or assets.default
            if type(image) == "string" and #image > 0 and #image <= 256 then
                activity.assets = { large_image = image, large_text = text(hud and hud.title or "MJOLNIR Core", 120) }
            end
        end
        local raw = Presence.encode(activity)
        if #raw > 4095 then raw = "null" end
        local out = io.open(nativeDir .. "discord_activity.json", "wb")
        if not out then return end
        local written, closed = out:write(raw), out:close()
        if not written or not closed then return end
        if not nativeUpdate then
            nativeUpdate = package and package.loadlib and package.loadlib(nativeDir .. "mjolnir_lobby.dll", "mjolnir_discord_update")
        end
        if nativeUpdate then nativeUpdate() end
    end
    local function loop()
        local ok, err = pcall(publish)
        if not ok then log("Discord presence: " .. tostring(err)) end
        ExecuteInGameThreadWithDelay(1000, loop)
    end
    -- Connect before the frontend is signed in; Discord holds a cold-launch
    -- Join callback only briefly. Its request waits in the usual menu queue.
    ExecuteInGameThreadWithDelay(100, loop)
end

return Presence

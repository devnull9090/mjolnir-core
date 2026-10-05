-- MJOLNIR Lobby: the host's game settings (docs/host_game_settings.md).
--
-- What CE's EDIT GAMETYPES pages let a host change, limited to what has
-- been seen working in game: each option names the variant fields it sets
-- (MJOLNIRLevelLoader's variant_settings.lua patches them in), its choices
-- in CE's own steps, and the help line the settings screen shows. The
-- choices are kept per game type only where CE kept them (the score to
-- win); everything else carries over between game types, as in CE.

local Settings = {}

Settings.PAGES = { "GAME", "PLAYERS", "ITEMS" }

local function seconds(n) return n == 0 and "INSTANT" or (n .. " SECONDS") end
local function penalty(n) return n == 0 and "NONE" or (n .. " SECONDS") end
local function minutes(n) return n == 0 and "NONE" or (n .. " MINUTES") end
local function yesNo(v) return v == 1 and "YES" or "NO" end
local function onOff(v) return v == 1 and "ON" or "OFF" end

local function choices(values, text)
    local out = {}
    for _, v in ipairs(values) do out[#out + 1] = { value = v, text = text(v) } end
    return out
end

-- Scores to win, per game type (CE's steps); the default is what the
-- installed variant was written with.
local SCORES = {
    slayer = { label = "KILLS TO WIN", values = { 5, 10, 15, 25, 50 }, default = 25,
        help = "The first player to this many kills wins." },
    team_slayer = { label = "KILLS TO WIN", values = { 10, 25, 50, 75, 100 }, default = 50,
        help = "The first team to this many kills wins." },
    ctf = { label = "CAPTURES TO WIN", values = { 1, 3, 5, 10, 15 }, default = 3,
        help = "The first team to capture the enemy flag this many times wins." },
}

-- Map options: what the map variant may place (variant.rs MAP_FLAGS).
local MAP_GRENADES, MAP_POWERUPS, MAP_DEFAULT = 1, 8, 31

Settings.OPTIONS = {
    {
        id = "score", page = 1,
        -- label, choices, default and help come from SCORES per game type.
    },
    {
        id = "time_limit", page = 1, label = "TIME LIMIT",
        choices = choices({ 0, 5, 10, 15, 20, 25, 30, 45 }, minutes), default = 0,
        help = "The round ends when the time runs out; the highest score wins.",
    },
    {
        id = "respawn", page = 2, label = "RESPAWN TIME",
        choices = choices({ 0, 5, 10, 15 }, seconds), default = 5,
        help = "How long a player waits to spawn again after dying.",
    },
    {
        id = "suicide_penalty", page = 2, label = "SUICIDE PENALTY",
        choices = choices({ 0, 5, 10, 15 }, penalty), default = 5,
        help = "Added to the respawn time after a player kills themselves.",
    },
    {
        id = "shields", page = 2, label = "SHIELDS",
        choices = choices({ 1, 0 }, onOff), default = 1,
        help = "With shields off, every player has only their health.",
    },
    {
        id = "invisible", page = 2, label = "INVISIBLE PLAYERS",
        choices = choices({ 0, 1 }, yesNo), default = 0,
        help = "Every player is permanently camouflaged.",
    },
    {
        id = "grenades", page = 3, label = "GRENADES ON MAP",
        choices = choices({ 1, 0 }, yesNo), default = 1,
        help = "Whether the map's grenade pickups appear. Players still spawn with grenades.",
    },
    {
        id = "powerups", page = 3, label = "POWERUPS ON MAP",
        choices = choices({ 1, 0 }, yesNo), default = 1,
        help = "Whether the map's overshield and active camouflage appear.",
    },
}

--- The option `id` as shown for game type `mode` (the score depends on it),
--- or nil when it does not apply to that game type.
function Settings.option(id, mode)
    for _, o in ipairs(Settings.OPTIONS) do
        if o.id == id then
            if id ~= "score" then return o end
            local s = SCORES[mode]
            if not s then return nil end
            return { id = "score", key = "score." .. mode, page = 1, label = s.label,
                choices = choices(s.values, tostring), default = s.default, help = s.help }
        end
    end
    return nil
end

--- The options on `page` (1-based) for game type `mode`, in order.
function Settings.page(page, mode)
    local out = {}
    for _, o in ipairs(Settings.OPTIONS) do
        local opt = Settings.option(o.id, mode)
        if opt and opt.page == page then out[#out + 1] = opt end
    end
    return out
end

local values = {}

local function keyOf(opt) return opt.key or opt.id end

--- The chosen value of `opt` (its default until changed).
function Settings.value(opt)
    local v = values[keyOf(opt)]
    for _, c in ipairs(opt.choices) do
        if c.value == v then return v end
    end
    return opt.default
end

function Settings.text(opt)
    local v = Settings.value(opt)
    for _, c in ipairs(opt.choices) do
        if c.value == v then return c.text end
    end
    return tostring(v)
end

--- Step `opt` to its next (`delta` 1) or previous (-1) choice, wrapping.
function Settings.step(opt, delta)
    local v = Settings.value(opt)
    local n = #opt.choices
    for i, c in ipairs(opt.choices) do
        if c.value == v then
            values[keyOf(opt)] = opt.choices[(i - 1 + delta) % n + 1].value
            return
        end
    end
end

--- Every option back to its default.
function Settings.reset()
    values = {}
end

--- The choices as saved text, one `key=value` per line.
function Settings.save()
    local keys = {}
    for k in pairs(values) do keys[#keys + 1] = k end
    table.sort(keys)
    local lines = {}
    for _, k in ipairs(keys) do lines[#lines + 1] = k .. "=" .. tostring(values[k]) end
    return table.concat(lines, "\n") .. "\n"
end

function Settings.load(text)
    values = {}
    for k, v in tostring(text or ""):gmatch("([%w_%.]+)=(%d+)") do values[k] = tonumber(v) end
end

--- The variant fields as the line MJOLNIRLevelLoader patches in
--- (`key=value;...`, sorted), with a score to win for every game type
--- (`score.<mode>`): the loader takes the one for the game it stages, so
--- the line stays right when a post-game vote changes the game type. Every
--- field is written, so the line alone decides the rules on every machine.
function Settings.variantLine()
    local f = {}
    for mode in pairs(SCORES) do
        f["score." .. mode] = Settings.value(Settings.option("score", mode))
    end
    f.time_limit = Settings.value(Settings.option("time_limit"))
    f.respawn_seconds = Settings.value(Settings.option("respawn"))
    f.suicide_seconds = Settings.value(Settings.option("suicide_penalty"))
    -- Reach's shield multiplier: 1 is none, 0 leaves the biped's own.
    f["trait.shields"] = Settings.value(Settings.option("shields")) == 1 and 0 or 1
    -- Reach's active camo: 4 kept a player camouflaged in testing.
    f["trait.camo"] = Settings.value(Settings.option("invisible")) == 1 and 4 or 0
    local map = MAP_DEFAULT
    if Settings.value(Settings.option("grenades")) == 0 then map = map - MAP_GRENADES end
    if Settings.value(Settings.option("powerups")) == 0 then map = map - MAP_POWERUPS end
    f.map_flags = map
    local keys = {}
    for k in pairs(f) do keys[#keys + 1] = k end
    table.sort(keys)
    local parts = {}
    for _, k in ipairs(keys) do parts[#parts + 1] = k .. "=" .. tostring(f[k]) end
    return table.concat(parts, ";")
end

--- The settings away from their defaults for game type `mode`, as
--- "LABEL: VALUE" lines (the lobby card's rules).
function Settings.changes(mode)
    local out = {}
    for _, o in ipairs(Settings.OPTIONS) do
        local opt = Settings.option(o.id, mode)
        if opt and Settings.value(opt) ~= opt.default then
            out[#out + 1] = opt.label .. ": " .. Settings.text(opt)
        end
    end
    return out
end

--- The rules a variant line sets, read back as "LABEL: VALUE" lines away
--- from the defaults: what a fireteam client shows of its host's settings.
function Settings.describe(line, mode)
    local saved = values
    values = {}
    local f = {}
    for k, v in tostring(line or ""):gmatch("([%w_%.]+)=(%d+)") do f[k] = tonumber(v) end
    for k, v in pairs(f) do
        if k:sub(1, 6) == "score." then values[k] = v end
    end
    values.time_limit = f.time_limit
    values.respawn = f.respawn_seconds
    values.suicide_penalty = f.suicide_seconds
    if f["trait.shields"] then values.shields = f["trait.shields"] == 1 and 0 or 1 end
    if f["trait.camo"] then values.invisible = f["trait.camo"] ~= 0 and 1 or 0 end
    if f.map_flags then
        values.grenades = math.floor(f.map_flags / MAP_GRENADES) % 2
        values.powerups = math.floor(f.map_flags / MAP_POWERUPS) % 2
    end
    local out = Settings.changes(mode)
    values = saved
    return out
end

return Settings

-- AI bots in a multiplayer match (docs/bots.md), run by the host's HUD.
--
-- A map baked with `blam.bots` carries one single-actor squad per bot,
-- `bot_0` .. `bot_<n-1>`, a zone of firing positions and AI pathfinding
-- (crates/blam-cli/src/level.rs). MJOLNIRLobby's DLL lets `ai_place` work in
-- a Megalo game (mjolnir_bots_enable) and runs the script lines on the
-- simulation thread (mjolnir_sim_script).
--
-- AI are not players: their incidents carry player index -1 and the AI
-- biped's actor. Each bot gets a seat of its own here, BOT_BASE + k, which
-- the HUD's scoreboard and feed treat like a player's. A bot is placed one
-- at a time, so the AI biped that appears next is the one just placed; the
-- actors come from a pool and are reused, so an actor is a bot only between
-- its placement and its death.

local Bots = {}

--- Bot seats start here, clear of the 16 player seats (the match log only
--- records seats 0-15).
Bots.BASE = 100
Bots.RESPAWN_SECONDS = 5
--- How long a placement may take to show an actor before the squad is
--- taken not to exist on this map.
local PLACE_TIMEOUT = 4
local SCAN_SECONDS = 0.25

--- The AI bipeds a bot can be (the squads' characters').
local CLASSES = {
    "BP_EliteBipedActor_C", "BP_GruntBipedActor_C", "BP_JackalBipedActor_C", "BP_BruteBipedActor_C",
    "BP_MaleMarineBipedActor_C", "BP_FemaleMarineBipedActor_C",
}

Bots.NAMES = {
    "Joshua", "Avery", "Marcus", "Riley", "Elena", "Dominic", "Kara", "Tobias", "Nadia", "Victor",
    "Sienna", "Owen", "Lena", "Mateo", "Priya", "Caleb", "Iris", "Felix", "Hana", "Silas",
    "Maya", "Jonah", "Zara", "Wesley", "Tessa", "Adrian", "Noor", "Grant", "Leah", "Rafael",
    "Ivy", "Desmond", "Clara", "Hugo", "Mira", "Simon", "Freya", "Emmett", "June", "Nikolai",
    "Sasha", "Theo", "Alma", "Quinn", "Ronan", "Esme", "Malik", "Vera", "Dalton", "Rosa",
    "Kenji", "Lucia", "Brody", "Anya", "Cyrus", "Nell", "Isaac", "Dara", "Gideon", "Paloma",
    "Reid", "Talia", "Oscar", "Mina", "Jasper", "Rhea", "Ezra", "Ingrid", "Colt", "Yara",
    "Milo", "Selma", "Abel", "Kira", "Lionel", "Opal", "Ansel", "Greta", "Bruno", "Celeste",
    "Duncan", "Ada", "Fletcher", "Wren", "Harlan", "Lola", "Ivan", "Petra", "Jude", "Marisol",
    "Knox", "Elsa", "Rocco", "Thea", "Sterling", "Juno", "Vaughn", "Odette", "Beckett", "Saoirse",
}

local state = nil
local dllDir = nil
local enable, run = nil, nil
local scriptId = os.time() + 7000
local log = function() end

--- `modsDir`: ue4ss\Mods; MJOLNIRLobby's DLL sits in MJOLNIRLobby\native.
function Bots.init(modsDir, logFn)
    dllDir = modsDir .. "\\MJOLNIRLobby\\native\\"
    log = logFn or log
end

local function loadDll()
    if run ~= nil then return run ~= false end
    local ok = package and package.loadlib
    enable = ok and package.loadlib(dllDir .. "mjolnir_lobby.dll", "mjolnir_bots_enable") or false
    run = ok and package.loadlib(dllDir .. "mjolnir_lobby.dll", "mjolnir_sim_script") or false
    return run ~= false
end

--- Run script lines on the simulation thread (MJOLNIRLevelLoader's
--- sim_script.lua does the same; the DLL skips an id it has run).
local function script(lines)
    if not loadDll() then return false end
    scriptId = scriptId + 1
    local f = io.open(dllDir .. "script.txt", "wb")
    if not f then return false end
    f:write(tostring(scriptId), "\n", table.concat(lines, "\n"), "\n")
    f:close()
    pcall(run)
    return true
end

local function address(actor)
    local ok, a = pcall(function() return actor:GetAddress() end)
    return ok and a or nil
end

--- Every AI biped actor there is, by address. FindAllOf walks the whole
--- object array (about 23 ms a class on Blood Gulch, 2026-10-25), so the
--- pools are found once, when bots start, and actors made later arrive
--- through NotifyOnNewObject; a tick only reads positions.
local pool = {}
local watched = {}

local function fillPool()
    pool = {}
    for _, class in ipairs(CLASSES) do
        for _, a in ipairs(FindAllOf(class) or {}) do
            local at = address(a)
            if at then pool[at] = a end
            -- NotifyOnNewObject takes the class's full path.
            if not watched[class] then
                local ok, path = pcall(function() return a:GetClass():GetFullName():match("%s(/%S+)$") end)
                if ok and path then
                    watched[class] = true
                    pcall(NotifyOnNewObject, path, function(new)
                        local id = address(new)
                        if id then pool[id] = new end
                    end)
                end
            end
        end
    end
end

--- Every AI biped out of the pool: a pooled actor waits at the origin.
local function liveActors()
    local out = {}
    for at, a in pairs(pool) do
        local ok, pooled = pcall(function()
            if not a:IsValid() then return nil end
            local l = a:K2_GetActorLocation()
            return math.abs(l.X) + math.abs(l.Y) < 1
        end)
        if ok and pooled == nil then
            pool[at] = nil
        elseif ok and not pooled then
            out[at] = a
        end
    end
    return out
end

local function shuffled(list)
    local out = {}
    for i, v in ipairs(list) do out[i] = v end
    for i = #out, 2, -1 do
        local j = math.random(i)
        out[i], out[j] = out[j], out[i]
    end
    return out
end

--- Start `count` bots. `onSeat(index, name)` is told a bot's seat and name
--- each time it is placed: on the floor, alive.
function Bots.begin(count, now, onSeat)
    if not loadDll() then
        log("bots: MJOLNIRLobby's DLL is not there; no bots")
        return false
    end
    if enable then pcall(enable) end
    fillPool()
    math.randomseed(os.time())
    local names = shuffled(Bots.NAMES)
    state = { slots = {}, onSeat = onSeat, retired = {}, nextScan = 0, placing = nil }
    for k = 0, count - 1 do
        state.slots[#state.slots + 1] = {
            k = k, index = Bots.BASE + k, name = names[(k % #names) + 1] .. " (bot)",
            status = "waiting", nextAt = now + 1 + k * 0.5,
        }
    end
    log(string.format("bots: %d bot(s) for this match", count))
    return true
end

function Bots.stop()
    state = nil
end

function Bots.active()
    return state ~= nil
end

function Bots.isBot(index)
    return type(index) == "number" and index >= Bots.BASE
end

local function slotOf(index)
    if not state or not Bots.isBot(index) then return nil end
    return state.slots[index - Bots.BASE + 1]
end

--- The bot seat an AI biped's actor holds, or nil.
function Bots.seatOf(actor)
    if not state or not actor then return nil end
    local at = address(actor)
    if not at then return nil end
    for _, s in ipairs(state.slots) do
        if s.status == "alive" and s.addr == at then return s.index end
    end
    return nil
end

--- A bot died (its `Kill` incident): back on the floor after the respawn
--- time, as a player is.
function Bots.died(index, now)
    local s = slotOf(index)
    if not s or s.status ~= "alive" then return end
    if s.addr then state.retired[s.addr] = true end
    s.status, s.addr, s.actor = "dead", nil, nil
    s.nextAt = now + Bots.RESPAWN_SECONDS
end

--- AI stand at their firing positions until they see someone. A bot is
--- given somewhere to be every so often: half the time a human player it is
--- made aware of, wherever they are (task `hunt`), otherwise one of the
--- map's areas (task `area_<k>`) to walk to (level.rs bots_finish).
Bots.AREAS = 16
local ROAM_MIN, ROAM_MAX = 12, 25

local function roam(now, humans)
    local lines = {}
    for _, s in ipairs(state.slots) do
        if s.status == "alive" and now >= (s.roamAt or 0) and #lines < 14 then
            s.roamAt = now + ROAM_MIN + math.random() * (ROAM_MAX - ROAM_MIN)
            if humans > 0 and math.random() < 0.5 then
                lines[#lines + 1] = string.format("(ai_set_task bot_%d mjolnir_bots hunt)", s.k)
                lines[#lines + 1] = string.format("(ai_magically_see_object bot_%d (player_get %d))", s.k, math.random(humans) - 1)
            else
                lines[#lines + 1] = string.format("(ai_set_task bot_%d mjolnir_bots area_%d)", s.k, math.random(Bots.AREAS) - 1)
            end
        end
    end
    if #lines > 0 then script(lines) end
end

--- `humans`: how many human players the match has (`player_get`'s range).
function Bots.tick(now, humans)
    if not state or now < state.nextScan then return end
    state.nextScan = now + SCAN_SECONDS
    local live = liveActors()
    -- A retired actor that went back to the pool may be handed out again.
    for at in pairs(state.retired) do
        if not live[at] then state.retired[at] = nil end
    end
    local taken = {}
    for _, s in ipairs(state.slots) do
        if s.status == "alive" then
            if not live[s.addr] then
                -- Gone without a kill we saw (a fall out of the world).
                s.status, s.addr, s.actor, s.nextAt = "dead", nil, nil, now + Bots.RESPAWN_SECONDS
            else
                taken[s.addr] = true
            end
        end
    end
    if not state.placing then roam(now, humans or 0) end
    local p = state.placing
    if p then
        for at, actor in pairs(live) do
            if not taken[at] and not state.retired[at] and not p.before[at] then
                p.status, p.addr, p.actor = "alive", at, actor
                -- A few seconds to look around where it spawned first.
                p.roamAt = now + 3 + math.random() * 4
                state.placing = nil
                p.seated = true
                pcall(state.onSeat, p.index, p.name)
                return
            end
        end
        if now - p.placedAt > PLACE_TIMEOUT then
            p.tries = (p.tries or 0) + 1
            state.placing = nil
            if p.tries >= 2 then
                p.status = "missing"
                log(string.format("bots: bot_%d never appeared; this map has no such squad", p.k))
            else
                p.status, p.nextAt = "waiting", now + 1
            end
        end
        return
    end
    for _, s in ipairs(state.slots) do
        if (s.status == "waiting" or s.status == "dead") and now >= s.nextAt then
            if script({ string.format("(ai_place bot_%d)", s.k) }) then
                -- Whatever is out already is not this bot.
                s.status, s.placedAt, s.before = "placing", now, live
                state.placing = s
            end
            return
        end
    end
end

--- The seats of every bot that has been placed, with their names.
function Bots.seats()
    local out = {}
    if not state then return out end
    for _, s in ipairs(state.slots) do
        if s.seated then out[#out + 1] = { index = s.index, name = s.name, alive = s.status == "alive" } end
    end
    return out
end

--- How many bots the host asked for: `bots` in the game settings line
--- MJOLNIRLobby writes for the loader (variant_settings.txt), 0 without it.
function Bots.wanted(loaderDir)
    local f = io.open(loaderDir .. "\\variant_settings.txt", "rb")
    if not f then return 0 end
    local n = tonumber((f:read("*a") or ""):match("bots=(%d+)"))
    f:close()
    return math.min(n or 0, 15)
end

return Bots

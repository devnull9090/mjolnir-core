-- MJOLNIR HUD: the match log (docs/match_stats.md).
--
-- The host of a public game records each match it runs: every incident the
-- simulation raises, in order, with where the players involved stood, and
-- the final standings. MJOLNIRLobby uploads the record to the hub when the
-- match ends. The host's incident handler gets every player's incidents; a
-- fireteam client's gets almost none (docs/multiplayer_hud.md), so only the
-- host records.
--
-- A match is public when MJOLNIRLobby lists it on the hub at any point while
-- it runs: the Lobby writes the listing's id to its listing.txt.
--
-- Each participant's own game claims its seat in the hub's record, so the
-- seat links to their hub account. A client asks the host for the match's
-- id over ServerExecRPC ("MJOLNIR|matchid"); the host answers on the
-- asker's controller with ClientMessage type "MJOLNIR"
-- ("MJOLNIR|match|<id>|<public>|<index>|<name>"), the channel MJOLNIRLobby's
-- messages use (docs/multiplayer_postgame.md). No object scans either side.
--
-- Files beside this mod, for MJOLNIRLobby to send (Lua has no directory
-- listing, so an outbox file names them):
--   match_<id>.json    a host's record; rewritten as the match runs, so a
--                      crash leaves an abandoned match, not nothing
--   claim_<id>.json    a participant's claim of its seat
--   match_outbox.txt   "<match|claim> <id>" per line, appended when a file
--                      is ready to send
--   match_current.txt  the id of the match being recorded; found at start
--                      up, it names a match a crash cut short

local MatchLog = {}

-- Incidents that say nothing a record needs: the respawn countdown.
local SKIP = { respawn_tick = true, respawn_final_tick = true }
local MAX_EVENTS = 20000
local CHECKPOINT_SECONDS = 30
--- An abandoned match this short with no kill is not worth keeping: a host
--- that went in and straight back out.
local MIN_ABANDONED_SECONDS = 60
local ASK_SECONDS = 10

local dir, lobbyDir, log, version
local Rec = nil         -- the match being recorded (host)
local Known = {}        -- match ids this client has claimed a seat in

local function readFile(path)
    local f = io.open(path, "rb")
    if not f then return nil end
    local data = f:read("*a")
    f:close()
    return data
end

local function writeFile(path, text)
    local f = io.open(path, "wb")
    if not f then return false end
    f:write(text)
    f:close()
    return true
end

local function appendOutbox(kind, id)
    local f = io.open(dir .. "\\match_outbox.txt", "ab")
    if not f then return end
    f:write(kind, " ", id, "\n")
    f:close()
end

--------------------------------------------------------------------------------
-- JSON out
--------------------------------------------------------------------------------

local function str(s)
    return '"' .. tostring(s):gsub('[%c"\\]', function(c)
        if c == '"' then return '\\"' end
        if c == "\\" then return "\\\\" end
        return string.format("\\u%04x", c:byte())
    end) .. '"'
end

local function int(n)
    return string.format("%d", math.floor(tonumber(n) or 0))
end

local function pos(p)
    if not p then return "null" end
    return string.format("[%.1f,%.1f,%.1f]", p[1], p[2], p[3])
end

--------------------------------------------------------------------------------
-- Ids
--------------------------------------------------------------------------------

local seeded = false
local function newId()
    if not seeded then
        -- os.time alone repeats across hosts that start in the same second.
        local salt = tonumber((tostring({}):match("0x(%x+)") or "0"), 16) or 0
        math.randomseed((os.time() + math.floor(os.clock() * 1000000) + salt) % 2147483647)
        seeded = true
    end
    local hex = {}
    for i = 1, 32 do hex[i] = string.format("%x", math.random(0, 15)) end
    return table.concat(hex)
end

--- The hub listing MJOLNIRLobby keeps up for this game, if any.
local function listingId()
    local text = readFile(lobbyDir .. "\\listing.txt")
    return text and text:match("^%s*([%w%-]+)") or nil
end

--------------------------------------------------------------------------------
-- Recording (host)
--------------------------------------------------------------------------------

function MatchLog.recording()
    return Rec ~= nil
end

--- The id of the match being recorded, or nil.
function MatchLog.currentId()
    return Rec and Rec.id or nil
end

local function gameType(variant)
    local t = string.lower(tostring(variant or "slayer")):gsub("[^a-z_]", "_")
    return t:sub(1, 24)
end

--- Start recording `match` (MJOLNIRHud's Match), on the host.
function MatchLog.start(match, at)
    Rec = {
        id = newId(),
        code = match.code,
        gameType = gameType(match.variant),
        teams = match.mode.teams and true or false,
        toWin = match.mode.toWin,
        startedAt = os.time(),
        t0 = at,
        lobby = listingId(),
        events = {},      -- encoded, one string per event
        count = 0,
        kills = 0,
        nextCheckpoint = at + CHECKPOINT_SECONDS,
        nextListing = at + 5,
    }
    writeFile(dir .. "\\match_current.txt", Rec.id)
    log("match log: recording " .. Rec.id .. (Rec.lobby and " (public)" or " (private so far)"))
end

local function playerIndex(v)
    if type(v) ~= "number" or v < 0 or v > 15 then return -1 end
    return math.floor(v)
end

--- One incident, as MJOLNIRHud's hook queued it.
function MatchLog.incident(inc)
    if not Rec or SKIP[inc.name] or Rec.count >= MAX_EVENTS then return end
    local name = inc.name:gsub("[^a-z0-9_]", "_"):sub(1, 40)
    if name == "" then return end
    local parts = {
        '"t_ms":' .. int(math.max(0, (inc.at - Rec.t0) * 1000)),
        '"type":' .. str(name),
        '"cause":' .. int(playerIndex(inc.cause)),
        '"effect":' .. int(playerIndex(inc.effect)),
    }
    if type(inc.value) == "number" then parts[#parts + 1] = '"value":' .. int(inc.value) end
    local weapon = type(inc.damage) == "string" and inc.damage:match("%.([%w_]+)$")
    if weapon and weapon ~= "Invalid" and weapon ~= "None" then
        parts[#parts + 1] = '"weapon":' .. str(weapon:sub(1, 48))
    end
    if type(inc.modifier) == "number" and inc.modifier > 0 then parts[#parts + 1] = '"modifier":' .. int(inc.modifier) end
    if inc.causePos then parts[#parts + 1] = '"cause_pos":' .. pos(inc.causePos) end
    if inc.effectPos then parts[#parts + 1] = '"effect_pos":' .. pos(inc.effectPos) end
    Rec.count = Rec.count + 1
    Rec.events[Rec.count] = "{" .. table.concat(parts, ",") .. "}"
    if name == "kill" then Rec.kills = Rec.kills + 1 end
end

--- The record as the hub's MatchReport (hub/src/lib/api/matches.ts).
local function encode(match, scoreboard, localPlayer, how, at)
    local players = {}
    for index, p in pairs(match.players) do
        if index >= 0 and index <= 15 then
            local team = scoreboard.team(p.team)
            players[#players + 1] = "{" .. table.concat({
                '"index":' .. int(index),
                '"name":' .. str((p.name or ("Player " .. tostring(index + 1))):sub(1, 64)),
                '"team":' .. ((Rec.teams and team) and str(string.lower(team)) or "null"),
                '"score":' .. int(scoreboard.score(p, match.mode)),
                '"kills":' .. int(p.kills),
                '"deaths":' .. int(p.deaths),
                '"suicides":' .. int(p.suicides),
                '"captures":' .. int(p.captures),
                '"left":' .. tostring(p.left == true),
            }, ",") .. "}"
        end
    end
    local teamScores = "null"
    if Rec.teams then
        local totals = scoreboard.totals(match)
        teamScores = string.format('{"red":%s,"blue":%s}', int(totals.Red), int(totals.Blue))
    end
    return "{" .. table.concat({
        '"host_match_id":' .. str(Rec.id),
        '"lobby_id":' .. str(Rec.lobby or ""),
        '"map_code":' .. str(Rec.code),
        '"game_type":' .. str(Rec.gameType),
        '"team_game":' .. tostring(Rec.teams),
        '"score_to_win":' .. (Rec.toWin and int(Rec.toWin) or "null"),
        '"started_at":' .. int(Rec.startedAt),
        '"duration_ms":' .. int(math.max(0, (at - Rec.t0) * 1000)),
        '"end_reason":' .. str(how),
        '"host_index":' .. ((localPlayer and localPlayer >= 0 and localPlayer <= 15) and int(localPlayer) or "null"),
        '"team_scores":' .. teamScores,
        '"client_version":' .. str(version),
        '"players":[' .. table.concat(players, ",") .. "]",
        '"events":[' .. table.concat(Rec.events, ",") .. "]",
    }, ",") .. "}"
end

local function save(match, scoreboard, localPlayer, how, at)
    if not next(match.players) then return false end
    return writeFile(dir .. "\\match_" .. Rec.id .. ".json", encode(match, scoreboard, localPlayer, how, at))
end

--- Once a poll on the host: notice the game going public, and checkpoint.
function MatchLog.tick(match, scoreboard, localPlayer, at)
    if not Rec then return end
    if at >= Rec.nextListing then
        Rec.nextListing = at + 5
        local id = listingId()
        if id and id ~= Rec.lobby then
            if not Rec.lobby then log("match log: " .. Rec.id .. " is public") end
            Rec.lobby = id
        end
    end
    if Rec.lobby and at >= Rec.nextCheckpoint then
        Rec.nextCheckpoint = at + CHECKPOINT_SECONDS
        save(match, scoreboard, localPlayer, "abandoned", at)
    end
end

--- The match is over (`how`: round_over, game_over), or left before its end
--- (abandoned): write the record for MJOLNIRLobby to send, if public.
function MatchLog.finish(match, scoreboard, localPlayer, how, at)
    if not Rec then return end
    local id = Rec.id
    local path = dir .. "\\match_" .. id .. ".json"
    Rec.lobby = Rec.lobby or listingId()
    local short = how == "abandoned" and Rec.kills == 0 and (at - Rec.t0) < MIN_ABANDONED_SECONDS
    if not Rec.lobby or short then
        os.remove(path)
        log("match log: " .. id .. " not kept (" .. (Rec.lobby and "abandoned at once" or "private") .. ")")
    elseif save(match, scoreboard, localPlayer, how, at) then
        appendOutbox("match", id)
        log(string.format("match log: %s %s, %d events, queued for the hub", id, how, Rec.count))
    end
    os.remove(dir .. "\\match_current.txt")
    Rec = nil
end

--------------------------------------------------------------------------------
-- The match id, host to fireteam
--------------------------------------------------------------------------------

--- On the host: a client asked for the match's id; answer on its controller
--- with its own seat as this host recorded it.
function MatchLog.answer(pc, seat)
    if not Rec then return end
    local msg = string.format("MJOLNIR|match|%s|%d|%d|%s", Rec.id, Rec.lobby and 1 or 0,
        seat.index or -1, (tostring(seat.name or "")):gsub("[|\r\n]", "/"))
    pcall(function() pc:ClientMessage(msg, FName("MJOLNIR"), 0) end)
end

--- On a client: the host told us the match id. A public match's seat is
--- claimed once per match, with the index and name the host recorded.
--- Returns the id and whether the seat is claimed (false while the match is
--- private: it may go public later).
function MatchLog.told(text, ownIndex, ownName)
    local id, public, index, name = text:match("^MJOLNIR|match|(%x+)|([01])|(%-?%d+)|(.*)$")
    if not id then return nil, false end
    if Known[id] then return id, true end
    if public ~= "1" then return id, false end
    index = tonumber(index)
    if not index or index < 0 then index = ownIndex end
    if name == "" then name = ownName end
    if type(index) ~= "number" or index < 0 or index > 15 or not name or name == "" then return id, false end
    local body = string.format('{"host_match_id":%s,"player_index":%s,"name":%s}', str(id), int(index), str(name:sub(1, 64)))
    if writeFile(dir .. "\\claim_" .. id .. ".json", body) then
        Known[id] = true
        appendOutbox("claim", id)
        log("match log: claiming seat " .. tostring(index) .. " in public match " .. id)
    end
    return id, Known[id] == true
end

MatchLog.ASK_SECONDS = ASK_SECONDS

--- deps: { modDir, log, version }.
function MatchLog.init(deps)
    dir = deps.modDir
    lobbyDir = (dir:match("^(.*)\\[^\\]*$") or dir) .. "\\MJOLNIRLobby"
    log = deps.log
    version = deps.version or ""
    -- A match still marked current was cut short by a crash or a quit:
    -- its last checkpoint is its record.
    local cut = readFile(dir .. "\\match_current.txt")
    cut = cut and cut:match("^(%x+)")
    if cut then
        if readFile(dir .. "\\match_" .. cut .. ".json") then
            appendOutbox("match", cut)
            log("match log: " .. cut .. " was cut short; its checkpoint is queued")
        end
        os.remove(dir .. "\\match_current.txt")
    end
end

return MatchLog

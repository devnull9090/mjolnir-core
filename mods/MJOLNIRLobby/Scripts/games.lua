-- MJOLNIR Lobby: public games (docs/multiplayer_servers.md).
--
-- A host's game is private, open only to its fireteam and invites, until the
-- host makes it public. A public game is listed on the hub (mjolnircore.com)
-- with its PlayFab lobby's connection string, and a heartbeat every 30 s
-- keeps the listing's map, game type and players current. Going private,
-- joining someone else or leaving the game takes it off: the first two at
-- once, the last when its heartbeat goes stale.
--
-- FIND GAMES lists public games. JOIN asks the hub for the chosen game's
-- connection string and hands it to the game's own Steam "join game"
-- handler, so the join runs exactly as an accepted invite does: the game
-- leaves its fireteam, joins the host's, and follows it into its map.
--
-- The hub, the connection string and the join go through the native half
-- (native/lobby): a request file, then a reply file polled from here. The
-- hub key is the one the MJOLNIR launcher paired, read by the native half;
-- nothing here sees it.

local Games = {}

local HEARTBEAT_SECONDS = 30
local REPLY_TIMEOUT = 20      -- seconds before a hub call counts as failed
local MAX_PLAYERS = 16

local nativeDir, Json, Net, log
local sequence = 0

local Host = {
    public = false,   -- the host's choice; private until switched
    id = nil,         -- the hub's listing, while listed
    token = nil,
    busy = false,     -- a register or heartbeat in flight
    nextBeat = 0,
    status = "",      -- one line for the lobby's footer
    info = nil,       -- function -> { name, map_code, game_type, players, in_game }
    version = "",
}

local function readFile(path)
    local f = io.open(path, "rb")
    if not f then return nil end
    local data = f:read("*a")
    f:close()
    return data
end

local function native(name)
    local fn = package and package.loadlib and package.loadlib(nativeDir .. "mjolnir_lobby.dll", name)
    if not fn then return false end
    local ok = pcall(fn)
    return ok
end

--- A flat object as JSON: strings, numbers and booleans.
local function encode(t)
    local parts = {}
    for k, v in pairs(t) do
        local value
        if type(v) == "string" then
            value = '"' .. (v:gsub('[%c"\\]', function(c) return string.format("\\u%04x", c:byte()) end)) .. '"'
        else
            value = tostring(v)
        end
        parts[#parts + 1] = '"' .. k .. '":' .. value
    end
    return "{" .. table.concat(parts, ",") .. "}"
end

--- JSON null as nil: Json.decode keeps it as a sentinel table, which is
--- truthy, and the hub sends null for fields it doesn't know (ping_ms).
local function denull(v)
    if v == Json.null then return nil end
    if type(v) == "table" then
        for k, x in pairs(v) do v[k] = denull(x) end
    end
    return v
end

--- Call the hub API: done(status, decoded body or nil). Status 0 means the
--- hub could not be reached, or did not answer in time.
local function hub(method, path, body, done)
    sequence = sequence + 1
    local id = string.format("g%d%d", os.time() % 100000, sequence)
    local f = io.open(nativeDir .. "hub_request.txt", "wb")
    if not f then
        done(0, nil)
        return
    end
    f:write(id, " ", method, " ", path, "\n", body and encode(body) or "")
    f:close()
    if not native("mjolnir_hub_call") then
        done(0, nil)
        return
    end
    local reply = nativeDir .. "hub_reply_" .. id .. ".txt"
    local deadline = os.time() + REPLY_TIMEOUT
    local function poll()
        local text = readFile(reply)
        if text then
            os.remove(reply)
            local status, rest = text:match("^(%d+)\n(.*)$")
            local ok, data = pcall(Json.decode, rest or "")
            done(tonumber(status) or 0, ok and denull(data) or nil)
        elseif os.time() > deadline then
            done(0, nil)
        else
            ExecuteInGameThreadWithDelay(100, poll)
        end
    end
    ExecuteInGameThreadWithDelay(100, poll)
end

--- What a failed hub call means to a player.
local function explain(status, data)
    if status == 0 then return "Cannot reach mjolnircore.com." end
    if status == 401 then return "Sign in to the MJOLNIR launcher to use public games." end
    if status == 403 then
        return "Your launcher sign-in is too old for public games: sign out of the launcher and sign in again."
    end
    if status == 404 then return "That game is gone." end
    if status == 409 then return "That game is full." end
    if status == 429 then return "Too many requests to the hub; try again in a minute." end
    return (data and (data.message or data.error)) or ("The hub answered " .. tostring(status) .. ".")
end

--- Whether the native half refuses the game's own leave of its lobby. A
--- match started with the host alone leaves it about a minute in, and
--- nobody could join; a public game keeps it, whoever is in it. Off for a
--- private game, and before joining another (the game must leave then).
local keeping = nil
local function keepLobby(on)
    on = on and true or false
    if keeping == on then return end
    local f = io.open(nativeDir .. "keep_lobby.txt", "wb")
    if not f then return end
    f:write(on and "1" or "0")
    f:close()
    if native("mjolnir_keep_lobby") then keeping = on end
end

--- Whether a session that starts, or is joined while running, with one
--- member stays online instead of leaving to play offline (the native half
--- patches UBlamOnlineSessionSubsystem::SetSessionRunning). On for a joiner
--- going into a public game; a public host gets it with keepLobby. It also
--- arms the joiner's world hold: a match world that begins before its Blam
--- game waits for it (see jipTick).
local function stayOnline(on)
    local f = io.open(nativeDir .. "stay_online.txt", "wb")
    if not f then return end
    f:write(on and "1" or "0")
    f:close()
    native("mjolnir_stay_online")
end

--- A joiner into a match under way holds its world's begin play until its
--- Blam game runs, and starts that game by replaying the travel a normal
--- start goes through. While a world is held (native\jip_held.txt) the
--- native half needs the world's package path; it does the rest from here,
--- once a second on the game thread.
local function jipTick()
    local held = io.open(nativeDir .. "jip_held.txt", "rb")
    if held then
        held:close()
        local ok, full = pcall(function()
            return FindFirstOf("PlayerController"):GetWorld():GetFullName()
        end)
        -- "World /Game/Levels/Halo1/Solo/BCK/BCK.BCK" -> "/Game/Levels/Halo1/Solo/BCK/BCK"
        local path = ok and full and full:match("^%S+%s+([^%.]+)")
        if path then
            local f = io.open(nativeDir .. "jip_map.txt", "wb")
            if f then
                f:write(path, "\n")
                f:close()
            end
        end
    end
    native("mjolnir_jip_tick")
end

--- The current PlayFab lobby's connection string, or nil and why.
local function connectionString()
    if not native("mjolnir_lobby_connection") then return nil, "the native half is not loaded" end
    local text = readFile(nativeDir .. "lobby_connection.txt") or ""
    local conn = text:match("^ok (%S+)")
    if conn then return conn end
    return nil, text:match("^none (.-)%s*$") or "no lobby"
end

-------------------------------------------------------------------------------
-- Hosting: the listing
-------------------------------------------------------------------------------

local function setStatus(text)
    Host.status = text or ""
end

local function unlist(why)
    if Host.id then
        local id, token = Host.id, Host.token
        hub("DELETE", "/lobbies/" .. id, { token = token }, function(status)
            if status ~= 200 and status ~= 404 then log("games: could not take the listing down (" .. status .. ")") end
        end)
        log("games: unlisted (" .. why .. ")")
    end
    Host.id, Host.token = nil, nil
end

local function beat()
    local info = Host.info and Host.info()
    if not (info and info.map_code and info.game_type) then return end
    local conn, why = connectionString()
    if not conn then
        -- The game left its online lobby: a match started with the host
        -- alone in the fireteam plays offline (2026-10-02). A listing kept
        -- up would hand joiners a dead connection string, which the game
        -- reports as a full fireteam, so it comes down until a lobby is back.
        if Host.id then unlist("the game left its online lobby") end
        Host.nextBeat = os.time() + 5
        setStatus(info.in_game and "Not listed: this match is offline. A match started with only you in the fireteam can't be joined."
            or ("Not listed yet: " .. tostring(why)))
        return
    end
    local players = math.max(1, info.players or 1)
    local state = info.in_game and "in_game" or "open"
    if players >= MAX_PLAYERS then state = "full" end
    Host.busy = true
    if not Host.id then
        hub("POST", "/lobbies", {
            name = (info.name or "MJOLNIR"):sub(1, 60),
            map_code = info.map_code,
            game_type = info.game_type,
            players = players,
            max_players = MAX_PLAYERS,
            client_version = Host.version,
            platform = "steam",
            connection_string = conn,
        }, function(status, data)
            Host.busy = false
            if status == 201 and data and data.id then
                if not Host.public then
                    -- Switched back to private while the request was out.
                    Host.id, Host.token = data.id, data.token
                    unlist("private")
                    return
                end
                Host.id, Host.token = data.id, data.token
                Host.nextBeat = os.time() + HEARTBEAT_SECONDS
                setStatus("PUBLIC: listed in FIND GAMES")
                log("games: listed " .. info.map_code .. " " .. info.game_type)
            else
                Host.nextBeat = os.time() + HEARTBEAT_SECONDS
                setStatus("Not listed: " .. explain(status, data))
                log("games: listing failed (" .. status .. ")")
            end
        end)
        return
    end
    hub("POST", "/lobbies/" .. Host.id .. "/heartbeat", {
        token = Host.token,
        players = players,
        map_code = info.map_code,
        game_type = info.game_type,
        state = state,
        connection_string = conn,
    }, function(status, data)
        Host.busy = false
        Host.nextBeat = os.time() + HEARTBEAT_SECONDS
        if status == 404 then
            -- Swept, or replaced by a listing from another session: list again.
            Host.id, Host.token = nil, nil
            Host.nextBeat = 0
        elseif status ~= 200 then
            setStatus("Listing not updated: " .. explain(status, data))
        end
    end)
end

--- Once a second: keep the listing in step with the host's choice.
local function tick()
    if not Host.public then
        if Host.id then unlist("private") end
        return
    end
    if Host.busy or os.time() < Host.nextBeat then return end
    if not Net.isHost() then
        -- Joined someone else's game: this one is not ours to list.
        Host.public = false
        keepLobby(false)
        unlist("no longer the host")
        setStatus("")
        return
    end
    beat()
end

function Games.isPublic() return Host.public end
function Games.status() return Host.status end

function Games.setPublic(on)
    Host.public = on and true or false
    Host.nextBeat = 0
    keepLobby(Host.public)
    if Host.public then
        setStatus("PUBLIC: listing...")
    else
        setStatus("PRIVATE: only your fireteam and invited friends can join")
    end
end

--- The game changed (a new map, game type, or the end of a match): tell the
--- hub on the next tick instead of waiting for the heartbeat.
function Games.changed()
    if Host.id and not Host.busy then Host.nextBeat = 0 end
end

-------------------------------------------------------------------------------
-- Finding and joining
-------------------------------------------------------------------------------

--- Public games, nearest first: done(lobbies) or done(nil, why).
function Games.list(done)
    hub("GET", "/lobbies", nil, function(status, data)
        if status == 200 and data and type(data.lobbies) == "table" then
            done(data.lobbies)
        else
            done(nil, explain(status, data))
        end
    end)
end

--- Join a listed game: done(true) once the join is under way, or
--- done(false, why).
function Games.join(lobby, done)
    hub("GET", "/lobbies/" .. lobby.id .. "/join", nil, function(status, data)
        if status ~= 200 or not (data and data.connection_string) then
            done(false, explain(status, data))
            return
        end
        if Host.public then
            Host.public = false
            unlist("joining another game")
        end
        -- The game leaves its own lobby to join the host's, and stays in the
        -- host's session though it arrives alone in a match under way.
        keepLobby(false)
        stayOnline(true)
        local f = io.open(nativeDir .. "join_request.txt", "wb")
        if not f then
            done(false, "cannot write the join request")
            return
        end
        f:write(data.connection_string, "\n")
        f:close()
        if not native("mjolnir_join") then
            done(false, "the native half is not loaded")
            return
        end
        local deadline = os.time() + 5
        local function poll()
            local reply = readFile(nativeDir .. "join_reply.txt")
            if reply then
                if reply:match("^delivered") then
                    log("games: joining " .. tostring(lobby.host) .. "'s game")
                    done(true)
                else
                    done(false, reply:match("^error (.-)%s*$") or reply)
                end
            elseif os.time() > deadline then
                done(false, "the game did not take the join")
            else
                ExecuteInGameThreadWithDelay(100, poll)
            end
        end
        ExecuteInGameThreadWithDelay(100, poll)
    end)
end

--- deps: { modDir, json, net, log, version, info }.
function Games.init(deps)
    nativeDir = deps.modDir .. "\\native\\"
    Json, Net, log = deps.json, deps.net, deps.log
    Host.version = deps.version or ""
    Host.info = deps.info
    keepLobby(false)
    local function loop()
        local ok, err = pcall(tick)
        if not ok then log("games: " .. tostring(err)) end
        jipTick()
        ExecuteInGameThreadWithDelay(1000, loop)
    end
    ExecuteInGameThreadWithDelay(1000, loop)
end

return Games

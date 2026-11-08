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
-- connection string and hands it to the game's own "join game" handler
-- (Steam's, or the Xbox app's invite handler), so the join runs exactly as an
-- accepted invite does: the game leaves its fireteam, joins the host's, and
-- follows it into its map.
--
-- The hub, the connection string and the join go through the native half
-- (native/lobby): a request file, then a reply file polled from here. The
-- hub key is the one the MJOLNIR launcher paired, read by the native half;
-- nothing here sees it.

local Games = {}

local HEARTBEAT_SECONDS = 30
local REPLY_TIMEOUT = 20      -- seconds before a hub call counts as failed
local LOBBY_LOST_SECONDS = 15 -- this long without a lobby in the menu, it is gone
local MAX_PLAYERS = 16        -- the hub's ceiling, and the fireteam's

local nativeDir, listingFile, noticeFile, Json, Net, log, Session, guest
local publicPresence, presenceCheckedAt, lastWorld, nextPresenceBroadcast = nil, nil, nil, 0
local connectionChecked, online = 0, false
local sequence = 0

local Host = {
    public = false,   -- the host's choice; private until switched
    generation = 0,   -- invalidates asynchronous responses after a session change
    confirmed = nil, -- last successful registration/heartbeat
    world = nil,     -- current world identity, also on clients
    id = nil,         -- the hub's listing, while listed
    token = nil,
    busy = false,     -- a register or heartbeat in flight
    nextBeat = 0,
    status = "",      -- one line for the lobby's footer
    info = nil,       -- function -> { name, map_code, game_type, players, in_game, settings }
    version = "",
    maxPlayers = MAX_PLAYERS,   -- the host's MAX PLAYERS
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
--- hub could not be reached, or did not answer in time. `body` is a flat
--- table, or JSON text sent as it is.
local function hub(method, path, body, done)
    sequence = sequence + 1
    local id = string.format("g%d%d", os.time() % 100000, sequence)
    local f = io.open(nativeDir .. "hub_request.txt", "wb")
    if not f then
        done(0, nil)
        return
    end
    f:write(id, " ", method, " ", path, "\n", type(body) == "string" and body or (body and encode(body)) or "")
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
    if status == 403 and data and data.error == "matchmaking_banned" then
        return data.message or "You are banned from matchmaking."
    end
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
    -- Then 1 in a match: going private there closes the lobby again.
    f:write(on and "1" or "0", (Host.inMatch and Host.inMatch()) and " 1" or " 0")
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

--- A host of our matches stays online when it starts one alone, public or
--- private (the native half's host_online.txt): its lobby, and so the
--- connection string a listing needs, outlives the start, and the game can
--- be made public later, in the lobby or mid-match. As shipped, a private
--- match started alone left the lobby for good (2026-11-07). Set at each
--- start (`on` false for FORGE); campaign before the first is as shipped.
local hostingOnline = nil
function Games.hosting(on)
    on = on and true or false
    if hostingOnline == on then return end
    local f = io.open(nativeDir .. "host_online.txt", "wb")
    if not f then return end
    f:write(on and "1" or "0")
    f:close()
    if native("mjolnir_host_online") then hostingOnline = on end
end

--- A joiner into a match under way holds its world's begin play until its
--- Blam game runs, and starts that game by replaying the travel a normal
--- start goes through. While a world is held (native\jip_held.txt) the
--- native half needs the world's package path; it does the rest from here,
--- once a second on the game thread.
-- The game type of the listed game being joined, and the level loader switch
-- still owed for a match joined under way: { code, url, tries }.
local joiningGameType
local pendingSwitch
local jipJoinedUrl

--- Hand the level loader a joined match's URL (Megalo engine, game type,
--- running.txt for MJOLNIRHud), as the host's travel would, before the
--- native half builds this side's game: MJOLNIRLevelLoader\join_switch.txt,
--- which the loader reads within half a second. Written again every ten
--- seconds until the loader's running.txt names the map. The URL's slot names
--- only the engine, so the listing's exact variant goes in match_variant.txt
--- first (modes.lua).
local function levelSwitchTick()
    if not pendingSwitch then return end
    local loaderDir = nativeDir .. "..\\..\\MJOLNIRLevelLoader\\"
    local running = readFile(loaderDir .. "running.txt") or ""
    if running:sub(1, #pendingSwitch.code + 1) == pendingSwitch.code .. "\t" then
        log("games: the level loader runs " .. pendingSwitch.code .. " for the match joined under way")
        pendingSwitch = nil
        return
    end
    if pendingSwitch.tries >= 60 then
        log("games: the level loader never took " .. pendingSwitch.url)
        pendingSwitch = nil
        return
    end
    if pendingSwitch.tries % 10 == 0 then
        Host.modes.follow(loaderDir:sub(1, -2), pendingSwitch.code, joiningGameType, log)
        local f = io.open(loaderDir .. "join_switch.txt", "wb")
        if f then
            f:write(pendingSwitch.url, "\n")
            f:close()
        end
    end
    pendingSwitch.tries = pendingSwitch.tries + 1
end

-- A player who joins a match under way hears gunfire but no reload, grenade
-- or other object-attached sound: the game binds its audio layer to the
-- match's audio world from a world listener that a joiner's build of the game
-- never runs, so the exe drops those sounds before Wwise
-- (docs/re/client_sound_roles.md). mjolnir_audio_bind does that bind; it
-- answers "already bound" on a player who was in the fireteam at the start,
-- "refused" for a world the game bound and has since unbound (a match being
-- left), and an error until the simulation has asked for its first object
-- sound, so this retries each tick until the world is bound.
--
-- Not in a world's first AUDIO_BIND_WAIT seconds: a host and a player in the
-- fireteam at the start are bound by the game itself as the match starts,
-- and a bind forced before that (a host logged one the second its match
-- began, 2026-10-25) registers the game's world listener twice. Only a
-- player who joined in progress is still unbound by then.
local AUDIO_BIND_WAIT = 10
local audioBoundWorld
local audioSeen = { key = nil, at = 0 }
local function audioBindTick()
    -- Never on a host: the game binds a host's world itself. A host whose
    -- first look came as its match was being left found the block already
    -- unbound, bound it again, and the freed block crashed the game when it
    -- quit (2026-11-01).
    if Net.isHost() then return end
    -- The world through the engine's local player, not FindFirstOf: that
    -- walked every object each second of every match.
    local okW, world = pcall(Host.worldObject)
    if not okW or not world or not world:IsValid() then return end
    -- By address too: a joiner who leaves and joins again lands in a new
    -- world of the same name, and was taken as bound (no object sounds; two
    -- PCs, 2026-10-25, #231).
    local name = world:GetFullName()
    if name:find("Frontend", 1, true) then return end
    name = string.format("%s@%x", name, world:GetAddress())
    if audioBoundWorld == name then return end
    if audioSeen.key ~= name then audioSeen.key, audioSeen.at = name, os.clock() end
    if os.clock() - audioSeen.at < AUDIO_BIND_WAIT then return end
    local okS, subsystem = pcall(FindFirstOf, "HaloAudioInterfaceSubSystem")
    if not okS or not subsystem or not subsystem:IsValid() then return end
    local f = io.open(nativeDir .. "audio_bind.txt", "wb")
    if not f then return end
    f:write(string.format("world %x\nsubsystem %x\n", world:GetAddress(), subsystem:GetAddress()))
    f:close()
    if not native("mjolnir_audio_bind") then return end
    local r = io.open(nativeDir .. "audio_bind_reply.txt", "rb")
    if not r then return end
    local reply = r:read("a") or ""
    r:close()
    if reply:find("already bound", 1, true) or reply:find("\nrefused", 1, true) then
        audioBoundWorld = name
    elseif reply:find("\nok ", 1, true) then
        audioBoundWorld = name
        log("games: audio bound to the match's audio world (a joiner's object sounds play now)")
    end
end

local function jipTick()
    audioBindTick()
    levelSwitchTick()
    local held = io.open(nativeDir .. "jip_held.txt", "rb")
    if not held then jipJoinedUrl = nil end
    if held then
        held:close()
        local ok, full = pcall(function()
            return FindFirstOf("PlayerController"):GetWorld():GetFullName()
        end)
        -- "World /Game/Levels/Halo1/Solo/BCK/BCK.BCK" -> "/Game/Levels/Halo1/Solo/BCK/BCK"
        local path = ok and full and full:match("^%S+%s+([^%.]+)")
        if path then
            -- The URL a host's seamless travel sends (2026-10-03):
            -- /Game/Levels/Halo1/Solo/ICE/ICE?Name=Player?SeamlessTravel?ScenarioName=ICE?InsertionPointIndex=0
            local code = path:match("([^/]+)$")
            local url = path .. "?Name=Player?SeamlessTravel?ScenarioName=" .. code
                .. "?InsertionPointIndex=" .. tostring(Host.modes.slot(joiningGameType) or 0)
            if not (pendingSwitch and pendingSwitch.url == url) and jipJoinedUrl ~= url then
                jipJoinedUrl = url
                pendingSwitch = { code = string.upper(code), url = url, tries = 0 }
                log("games: joined a match under way: " .. url)
                -- Where the host has the map in its campaign list: this
                -- side's must match before its game is built (main.lua,
                -- "where"/"mapindex").
                pcall(Net.toHost, "where", string.upper(code))
            end
            local f = io.open(nativeDir .. "jip_map.txt", "wb")
            if f then
                f:write(url, "\n")
                -- The engine subsystem whose map-loaded step lifts the
                -- loading screen once the Blam game has started.
                local okManager, manager = pcall(function()
                    return FindFirstOf("BlamEngineLoadingManagerEngineSubsystem"):GetAddress()
                end)
                f:write(string.format("%X\n", okManager and manager or 0))
                -- The world's GameState experience component, whose
                -- bWaiting... bits the loading step waits on (logged).
                local okExperience, experience = pcall(function()
                    local gs = FindFirstOf("PlayerController"):GetWorld().GameState
                    local cls = StaticFindObject("/Script/BlamExperience.BlamExperienceManagerComponent")
                    return gs:GetComponentByClass(cls):GetAddress()
                end)
                f:write(string.format("%X\n", okExperience and experience or 0))
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

--- A line for the host's match chat (MJOLNIRHud shows it as a system line):
--- <Mods>\MJOLNIRLobby\chat_notice.txt, "<unix time>\t<line>" a line. Only
--- in a match, where the HUD reads it; it drops lines over 30 s old.
local function notice(text)
    if not (Host.inMatch and Host.inMatch()) then return end
    local f = io.open(noticeFile, "ab")
    if not f then return end
    f:write(os.time(), "\t", text, "\n")
    f:close()
end
Games.notice = notice

--- The listing's status: the lobby's footer, the HOST MENU, and, when it
--- changes in a match, the host's chat.
local function setStatus(text)
    text = text or ""
    if text ~= Host.status and text ~= "" then notice(text) end
    Host.status = text
end

--- The listing's id in listing.txt beside this mod, while there is one:
--- MJOLNIRHud's match log reads it to know the match is public
--- (docs/match_stats.md).
local function noteListing(id)
    if id then
        local f = io.open(listingFile, "wb")
        if f then
            f:write(id, "\n")
            f:close()
        end
    else
        os.remove(listingFile)
    end
end

local function unlist(why)
    Host.generation = Host.generation + 1
    Host.confirmed, Host.busy, publicPresence = nil, false, nil
    if Host.id then
        local id, token = Host.id, Host.token
        hub("DELETE", "/lobbies/" .. id, { token = token }, function(status)
            if status ~= 200 and status ~= 404 then log("games: could not take the listing down (" .. status .. ")") end
        end)
        log("games: unlisted (" .. why .. ")")
    end
    Host.id, Host.token = nil, nil
    noteListing(nil)
end

local function beat()
    local info = Host.info and Host.info()
    if not (info and info.map_code and info.game_type) then return end
    local conn = connectionString()
    local now = os.time()
    if not conn then
        -- The game has no online lobby. A match started alone used to play
        -- offline (2026-10-02); Games.hosting keeps a host online now, but a
        -- lobby can still go (a game update that moves the patched branch).
        -- A listing kept up would hand joiners a dead connection string,
        -- which the game reports as a full fireteam, so it comes down until
        -- a lobby is back.
        if Host.id then unlist("the game left its online lobby") end
        Host.nextBeat = now + 5
        Host.noLobbySince = Host.noLobbySince or now
        if info.in_game then
            setStatus("Not listed: this match is offline. HOST MENU > RETURN TO LOBBY brings your game back online.")
        elseif Host.lobbySeen and now - Host.noLobbySince >= LOBBY_LOST_SECONDS then
            setStatus("Not listed: your game went offline. Start a match, then HOST MENU > RETURN TO LOBBY"
                .. " brings it back online (or restart the game).")
        else
            setStatus("Not listed yet: waiting for your game's online lobby...")
        end
        return
    end
    Host.lobbySeen, Host.noLobbySince = true, nil
    local players = math.max(1, info.players or 1)
    local state = info.in_game and "in_game" or "open"
    if players >= Host.maxPlayers then state = "full" end
    Host.busy = true
    local generation = Host.generation
    if not Host.id then
        hub("POST", "/lobbies", {
            name = (info.name or "MJOLNIR"):sub(1, 60),
            map_code = info.map_code,
            game_type = info.game_type,
            players = players,
            max_players = Host.maxPlayers,
            client_version = Host.version,
            -- The Xbox app's build runs from Binaries\WinGDK.
            platform = nativeDir:find("\\WinGDK\\", 1, true) and "gamepass" or "steam",
            connection_string = conn,
            -- The host's game settings: a player joining mid-match gets
            -- them from /join (docs/host_game_settings.md).
            settings = info.settings,
            -- The hub release of the map: a joiner with another one updates
            -- first (docs/live_map_install.md). A hub from before ignores it.
            map_release_id = info.map_release_id,
            map_version = info.map_version,
        }, function(status, data)
            if generation ~= Host.generation then
                -- The host became private or joined another session while
                -- registration was in flight. Remove only the orphaned row.
                if status == 201 and data and data.id and data.token then
                    hub("DELETE", "/lobbies/" .. data.id, { token = data.token }, function() end)
                end
                return
            end
            Host.busy = false
            if status == 201 and data and data.id then
                if not Host.public then
                    -- Switched back to private while the request was out.
                    Host.id, Host.token = data.id, data.token
                    unlist("private")
                    return
                end
                Host.id, Host.token = data.id, data.token
                Host.confirmed = os.time()
                noteListing(data.id)
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
        max_players = Host.maxPlayers,
        map_code = info.map_code,
        game_type = info.game_type,
        state = state,
        connection_string = conn,
        settings = info.settings,
        map_release_id = info.map_release_id,
        map_version = info.map_version,
    }, function(status, data)
        if generation ~= Host.generation then return end
        Host.busy = false
        Host.confirmed = status == 200 and os.time() or nil
        Host.nextBeat = os.time() + HEARTBEAT_SECONDS
        if status == 200 then
            setStatus("PUBLIC: listed in FIND GAMES")
        elseif status == 404 then
            -- Swept, or replaced by a listing from another session: list again.
            Host.id, Host.token = nil, nil
            noteListing(nil)
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

--- Whether the game has an online lobby now (asked afresh). RETURN TO
--- LOBBY leaves a match without one the way SAVE AND EXIT does, which makes
--- the game create one.
function Games.online() return connectionString() ~= nil end

--- The hub API and what its failures mean, for the match uploader.
Games.call = hub
Games.explain = explain

function Games.setPublic(on)
    local wasPublic = Host.public
    Host.public = on and true or false
    if wasPublic and not Host.public then unlist("private") end
    Host.nextBeat = 0
    keepLobby(Host.public)
    local inMatch = Host.inMatch and Host.inMatch()
    if Host.public then
        setStatus(inMatch and "PUBLIC: listing this match in FIND GAMES..." or "PUBLIC: listing...")
    else
        setStatus(inMatch and "PRIVATE: out of FIND GAMES. Everyone here stays; nobody new can join."
            or "PRIVATE: only your fireteam and invited friends can join")
    end
end

--- The game changed (a new map, game type, or the end of a match): tell the
--- hub on the next tick instead of waiting for the heartbeat.
function Games.changed()
    if Host.id and not Host.busy then Host.nextBeat = 0 end
end

--- The host's MAX PLAYERS, which the listing shows and fills up at.
function Games.setMaxPlayers(size)
    size = math.max(1, math.min(MAX_PLAYERS, math.floor(tonumber(size) or MAX_PLAYERS)))
    if size == Host.maxPlayers then return end
    Host.maxPlayers = size
    Games.changed()
end

-------------------------------------------------------------------------------
-- Finding and joining
-------------------------------------------------------------------------------

--- Public games, nearest first: done(lobbies) or done(nil, why).
--- native\lobbies_sample.json, when present, stands in for the hub (the
--- reply's shape: { "lobbies": [...] }), to try FIND GAMES with many games.
function Games.list(done)
    local sample = readFile(nativeDir .. "lobbies_sample.json")
    if sample then
        local ok, data = pcall(Json.decode, sample)
        data = ok and denull(data) or nil
        ExecuteInGameThreadWithDelay(300, function()
            if data and type(data.lobbies) == "table" then
                done(data.lobbies)
            else
                done(nil, "lobbies_sample.json is not a lobby list")
            end
        end)
        return
    end
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
    guest:joining(lobby.id, os.time())
    publicPresence = nil
    local finish = done
    done = function(ok, why)
        if not ok then guest:leave() end
        finish(ok, why)
    end
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
        -- Another host's game settings: what the listing says, or none until
        -- this host's lobby message brings its own (a match joined under
        -- way gets no lobby message).
        local settings = io.open(nativeDir .. "..\\..\\MJOLNIRLevelLoader\\variant_settings.txt", "w")
        if settings then
            settings:write(type(data.settings) == "string" and data.settings or "")
            settings:close()
        end
        joiningGameType = data.game_type or lobby.game_type
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

-- Public identity is sent on the game's existing host -> client channel.
-- Messages alone are insufficient: a guest also checks the hub's public list.
local function presenceTick()
    local now = os.time()
    local world = Host.world and Host.world()
    if world ~= lastWorld then
        lastWorld = world
        guest:worldChanged(world)
        Host.generation = Host.generation + 1
        Host.confirmed, Host.busy = nil, false
        Host.nextBeat = 0
        connectionChecked = 0
    end
    publicPresence = nil
    if not world then guest:clear(); return end
    if Net.isHost() then
        if guest.id then guest:clear() end
        if now >= connectionChecked then
            connectionChecked = now + 5
            online = connectionString() ~= nil
            -- Public or not: a lobby lost later is then gone, not on its way.
            if online then Host.lobbySeen = true end
        end
        local info = Host.info and Host.info()
        local jip = not (readFile(nativeDir .. "join_in_progress.txt") or ""):match("^%s*0")
        publicPresence = Session.host(Host, info, now, online, jip)
        if now >= nextPresenceBroadcast then
            nextPresenceBroadcast = now + 5
            local p = publicPresence
            Net.toClients("publicsession", p and p.id or "", p and p.joinable and "1" or "0",
                p and p.players or 0, p and p.maxPlayers or 0)
        end
    else
        guest:check(now, function(done)
            -- Do not use lobbies_sample.json: test browser rows must never
            -- advertise a Discord join target.
            hub("GET", "/lobbies", nil, function(status, data)
                done(status == 200 and data and data.lobbies or nil, os.time())
            end)
        end)
        publicPresence = guest:guest(now)
    end
end

function Games.presence()
    -- The publisher has its own loop. If the session producer stalls or
    -- stops, it must not keep refreshing a previously joinable activity.
    local age = presenceCheckedAt and os.time() - presenceCheckedAt
    if not age or age < 0 or age > 3 then return nil end
    return publicPresence
end
function Games.leavePresence()
    publicPresence = nil
    if guest then guest:leave() end
end

--- deps: { modDir, json, net, log, version, info, world, worldObject, modes,
--- inMatch }.

function Games.init(deps)
    nativeDir = deps.modDir .. "\\native\\"
    listingFile = deps.modDir .. "\\listing.txt"
    noticeFile = deps.modDir .. "\\chat_notice.txt"
    Json, Net, log = deps.json, deps.net, deps.log
    Session = dofile(deps.modDir .. "\\Scripts\\publicsession.lua")
    guest = Session.new()
    Host.world = deps.world
    Host.worldObject = deps.worldObject
    Net.on("publicsession", function(fields, sender)
        if sender ~= nil or Net.isHost() then return end
        local world = Host.world and Host.world()
        if not world then return end
        guest:worldChanged(world)
        guest:receive(fields, os.time())
    end)
    -- Left by a session that ended while listed: that listing is gone.
    noteListing(nil)
    Host.version = deps.version or ""
    Host.info = deps.info
    Host.inMatch = deps.inMatch
    Host.modes = deps.modes
    keepLobby(false)
    local function loop()
        local okPresence, errPresence = pcall(presenceTick)
        if okPresence then
            presenceCheckedAt = os.time()
        else
            publicPresence, presenceCheckedAt = nil, nil
            log("Discord session: " .. tostring(errPresence))
        end
        local ok, err = pcall(tick)
        if not ok then log("games: " .. tostring(err)) end
        jipTick()
        ExecuteInGameThreadWithDelay(1000, loop)
    end
    ExecuteInGameThreadWithDelay(1000, loop)
end

return Games

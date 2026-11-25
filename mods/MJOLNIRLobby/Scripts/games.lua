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
-- Until Games.init: from this script's own path (<mod>\Scripts\games.lua), for
-- a Games.put made before it (main.lua opens the fireteam first).
nativeDir = (((debug.getinfo(1, "S").source or ""):gsub("^@", ""):gsub("/", "\\")
    :match("^(.*\\)Scripts\\[^\\]*$")) or "") .. "native\\"
local reportSlow = function() end
local publicPresence, presenceCheckedAt, lastWorld, nextPresenceBroadcast = nil, nil, nil, 0
local connectionChecked, online = 0, false
local sequence = 0

local Host = {
    public = false,   -- the host's choice; public from the first lobby (Games.defaultPublic)
    chosen = false,   -- someone set public or private this launch
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

--- A development PC keeps its games out of public view: its lobby opens
--- private, `mjolnir_auto host` hosts private unless told `public`, and its
--- matches never reach hub history (matches.lua), even when a test lists
--- one to be joined. The mark is a file the launcher and the game never
--- write, so updates leave it alone:
---   %LOCALAPPDATA%\Meteorite\Saved\mjolnir_dev.txt   (any contents)
--- Players never have it, so everyone else opens public as before.
local function readDevMark()
    -- Guarded: test harnesses (tools/tests) load this with a stubbed `os`.
    local base = type(os) == "table" and type(os.getenv) == "function" and os.getenv("LOCALAPPDATA") or nil
    return base ~= nil and readFile(base .. "\\Meteorite\\Saved\\mjolnir_dev.txt") ~= nil
end
Games.dev = readDevMark()

-- Each export once: package.loadlib makes a new closure on every call.
local exports = {}
local function export(name)
    local fn = exports[name]
    if fn == nil then
        fn = package and package.loadlib and package.loadlib(nativeDir .. "mjolnir_lobby.dll", name) or false
        exports[name] = fn
    end
    return fn
end
local function native(name)
    local fn = export(name)
    if not fn then return false end
    local ok = pcall(fn)
    return ok
end

--- Whether a world joined under way is held: mjolnir_jip_held, or
--- native\jip_held.txt from an older DLL (opening it each second waited on
--- Windows Defender's scan).
function Games.worldHeld()
    local fn = export("mjolnir_jip_held")
    if fn then
        local ok, held = pcall(fn)
        if ok and type(held) == "boolean" then return held end
    end
    local f = io.open(nativeDir .. "jip_held.txt", "rb")
    if f then f:close() end
    return f ~= nil
end

--- Hands the request file `name` to the lobby DLL in memory
--- (mjolnir_request_put): "memory", or "file" when it had to be written, nil
--- when neither worked. On a PC with Windows Defender's real-time scan, the
--- DLL opening a file a moment after Lua wrote it waited ~5 ms. `reply`
--- claims that reply for Games.reply; `keep` serves every read until the
--- next put (a setting the DLL reads more than once).
function Games.put(name, text, reply, keep)
    local put = export("mjolnir_request_put")
    if put then
        local ok, held = pcall(put, name, text, reply, keep and true or false)
        if ok and held == true then return "memory" end
    end
    local f = io.open(nativeDir .. name, "wb")
    if not f then return nil end
    f:write(text)
    f:close()
    return "file"
end

--- Claims the next reply `name` for Games.reply, for an export that answers
--- without a request (mjolnir_map_install_status): "memory", or "file".
function Games.claim(name)
    local claim = export("mjolnir_reply_claim")
    if claim then
        local ok, held = pcall(claim, name)
        if ok and held == true then return "memory" end
    end
    return "file"
end

--- The reply `name` to a request Games.put sent by `route`: taken from the
--- DLL's mailbox, or read from its file. nil while there is none.
function Games.reply(name, route)
    if route == "memory" then
        local take = export("mjolnir_reply_take")
        local ok, known, text = pcall(take, name)
        return ok and known and text or nil
    end
    return readFile(nativeDir .. name)
end

--- A UE4SS shared variable for the other mods; false without one (a test,
--- an old UE4SS), when the caller falls back to a file.
local function share(key, value)
    local modRef = rawget(_G, "ModRef")
    return modRef ~= nil and pcall(modRef.SetSharedVariable, modRef, key, value)
end
--- The level loader's key for a joined match's URL (MJOLNIRLevelLoader main.lua).
Games.JOIN_SWITCH_KEY = "MJOLNIR.join_switch"

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
---
--- The request goes to the DLL as an argument (mjolnir_hub_send) and the
--- reply comes back from its mailbox (mjolnir_reply_take); a DLL without
--- them gets hub_request.txt and answers in hub_reply_<id>.txt. On a PC with
--- Windows Defender's real-time scan each of those files waited ~5 ms when
--- opened a moment after it was written.
local function hub(method, path, body, done)
    sequence = sequence + 1
    local id = string.format("g%d%d", os.time() % 100000, sequence)
    local request = id .. " " .. method .. " " .. path .. "\n"
        .. (type(body) == "string" and body or (body and encode(body)) or "")
    local send, take = export("mjolnir_hub_send"), export("mjolnir_reply_take")
    local inMemory = false
    if send and take then
        local ok, sent = pcall(send, request)
        inMemory = ok and sent == true
    end
    if not inMemory then
        local f = io.open(nativeDir .. "hub_request.txt", "wb")
        if not f then
            done(0, nil)
            return
        end
        f:write(request)
        f:close()
        if not native("mjolnir_hub_call") then
            done(0, nil)
            return
        end
    end
    local name = "hub_reply_" .. id .. ".txt"
    local reply = nativeDir .. name
    local deadline = os.time() + REPLY_TIMEOUT
    local function poll()
        local text
        if inMemory then
            local ok, known, got = pcall(take, name)
            text = ok and known and got or nil
        else
            text = readFile(reply)
            if text then os.remove(reply) end
        end
        if text then
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
    -- Then 1 in a match: going private there closes the lobby again.
    local text = (on and "1" or "0") .. ((Host.inMatch and Host.inMatch()) and " 1" or " 0")
    if not Games.put("keep_lobby.txt", text) then return end
    if native("mjolnir_keep_lobby") then keeping = on end
end

--- Whether a session that starts, or is joined while running, with one
--- member stays online instead of leaving to play offline (the native half
--- patches UBlamOnlineSessionSubsystem::SetSessionRunning). On for a joiner
--- going into a public game; a public host gets it with keepLobby. It also
--- arms the joiner's world hold: a match world that begins before its Blam
--- game waits for it (see jipTick).
local function stayOnline(on)
    if not Games.put("stay_online.txt", on and "1" or "0") then return end
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
    if not Games.put("host_online.txt", on and "1" or "0") then return end
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
--- native half builds this side's game: the shared variable
--- Games.JOIN_SWITCH_KEY (MJOLNIRLevelLoader\join_switch.txt without shared
--- variables), which the loader reads within half a second. Written again every ten
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
        if not share(Games.JOIN_SWITCH_KEY, pendingSwitch.url) then
            local f = io.open(loaderDir .. "join_switch.txt", "wb")
            if f then
                f:write(pendingSwitch.url, "\n")
                f:close()
            end
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

-- Subsystems from UE's own SubsystemBlueprintLibrary, by their native class:
-- under 0.01 ms, where FindFirstOf walked every object (~20 ms a call while
-- a joined world loads; a join's games loop held the game thread 89-99 ms
-- on PC 3, 2026-11-25). Each class and the library are looked up once.
local Sub = { lib = nil, classes = {} }
local function subsystemClass(path)
    local cls = Sub.classes[path]
    if cls == nil then
        local ok, found = pcall(StaticFindObject, path)
        cls = ok and found or false
        Sub.classes[path] = cls
    end
    return cls or nil
end
local function subsystemLibrary()
    if Sub.lib == nil then
        local ok, found = pcall(StaticFindObject, "/Script/Engine.Default__SubsystemBlueprintLibrary")
        Sub.lib = ok and found or false
    end
    return Sub.lib or nil
end
--- The engine subsystem of native class `path`, or nil.
local function engineSubsystem(path)
    local lib, cls = subsystemLibrary(), subsystemClass(path)
    if not (lib and cls) then return nil end
    local ok, sub = pcall(function() return lib:GetEngineSubsystem(cls) end)
    if ok and sub and sub:IsValid() then return sub end
    return nil
end
--- The game instance subsystem of native class `path` for `context` (an
--- object in a world), or nil.
local function gameInstanceSubsystem(context, path)
    local lib, cls = subsystemLibrary(), subsystemClass(path)
    if not (lib and cls and context) then return nil end
    local ok, sub = pcall(function() return lib:GetGameInstanceSubsystem(context, cls) end)
    if ok and sub and sub:IsValid() then return sub end
    return nil
end
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
    local subsystem = gameInstanceSubsystem(world, "/Script/HaloAudioUnreal.HaloAudioInterfaceSubSystem")
    if not subsystem then return end
    -- The addresses as arguments and the reply returned (mjolnir_audio_bind_to);
    -- audio_bind.txt and its reply file from a DLL without that export.
    local reply
    local bindTo = export("mjolnir_audio_bind_to")
    if bindTo then
        local ok, text = pcall(bindTo, world:GetAddress(), subsystem:GetAddress())
        if ok and type(text) == "string" then reply = text end
    end
    if not reply then
        local f = io.open(nativeDir .. "audio_bind.txt", "wb")
        if not f then return end
        f:write(string.format("world %x\nsubsystem %x\n", world:GetAddress(), subsystem:GetAddress()))
        f:close()
        if not native("mjolnir_audio_bind") then return end
        local r = io.open(nativeDir .. "audio_bind_reply.txt", "rb")
        if not r then return end
        reply = r:read("a") or ""
        r:close()
    end
    if reply:find("already bound", 1, true) or reply:find("\nrefused", 1, true) then
        audioBoundWorld = name
    elseif reply:find("\nok ", 1, true) then
        audioBoundWorld = name
        log("games: audio bound to the match's audio world (a joiner's object sounds play now)")
    end
end

-- The held world, found once a hold (one FindFirstOf, where the hold ran
-- three each second) and checked before every use: a stored object crashes
-- the game once freed. The jip_map text last handed over: again only when it
-- changes.
local Hold = { world = nil, text = nil }
local function heldWorld()
    local w = Hold.world
    if w then
        local ok, valid = pcall(function() return w:IsValid() end)
        if ok and valid then return w end
        Hold.world = nil
    end
    local ok, found = pcall(function() return FindFirstOf("PlayerController"):GetWorld() end)
    if ok and found and found:IsValid() then
        Hold.world = found
        return found
    end
    return nil
end

local function jipTick()
    audioBindTick()
    levelSwitchTick()
    local held = Games.worldHeld()
    if not held then jipJoinedUrl, Hold.world, Hold.text = nil, nil, nil end
    if held then
        local world = heldWorld()
        local ok, full = pcall(function() return world:GetFullName() end)
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
            -- The engine subsystem whose map-loaded step lifts the loading
            -- screen once the Blam game has started.
            local okManager, manager = pcall(function()
                return engineSubsystem("/Script/BlamEngine.BlamEngineLoadingManagerEngineSubsystem"):GetAddress()
            end)
            -- The world's GameState experience component, whose bWaiting...
            -- bits the loading step waits on (logged).
            local okExperience, experience = pcall(function()
                local cls = subsystemClass("/Script/BlamExperience.BlamExperienceManagerComponent")
                return world.GameState:GetComponentByClass(cls):GetAddress()
            end)
            -- Kept: the DLL may read it on more than one tick of the hold.
            local text = url .. "\n" .. string.format("%X\n%X\n", okManager and manager or 0,
                okExperience and experience or 0)
            if text ~= Hold.text and Games.put("jip_map.txt", text, nil, true) then Hold.text = text end
        end
    end
    native("mjolnir_jip_tick")
end

--- What mjolnir_lobby_connection reports: "ok <string>\nlock <0|1>\nmax <n>\n"
--- or "none <why>\n"; nil without the native half. Returned by
--- mjolnir_lobby_connection_get, or through lobby_connection.txt.
function Games.connectionText()
    local get = export("mjolnir_lobby_connection_get")
    if get then
        local ok, text = pcall(get)
        if ok and type(text) == "string" then return text end
    end
    if not native("mjolnir_lobby_connection") then return nil end
    return readFile(nativeDir .. "lobby_connection.txt") or ""
end

--- The current PlayFab lobby's connection string, or nil and why.
local function connectionString()
    local text = Games.connectionText()
    if not text then return nil, "the native half is not loaded" end
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

--- Why this game may not join or list a multiplayer game, or nil: set by
--- MJOLNIR Lobby to its mod check (outdated.lua, Outdated.mpBlock).
Games.gate = nil

local function gated()
    if not Games.gate then return nil end
    local ok, why = pcall(Games.gate)
    if not ok then return "MJOLNIR could not check your game folder for mods: " .. tostring(why) end
    return why
end

--- Going public: false and why when the mod check keeps this game out.
--- `auto`: set by MJOLNIR, not the host (FORGE), so the next lobby still
--- opens public.
function Games.setPublic(on, auto)
    if on then
        local why = gated()
        if why then
            setStatus(why)
            return false, why
        end
    end
    if not auto then Host.chosen = true end
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

--- A host's lobby opens PUBLIC: MULTIPLAYER lists the game in FIND GAMES
--- unless the host has already picked PUBLIC or PRIVATE this launch (the
--- lobby button, HOST MENU, /private, `mjolnir_auto host ... private`), so a
--- private choice holds through matches and back to the lobby. The mod
--- check can refuse it; the next lobby asks again. A development PC
--- (Games.dev) opens private.
function Games.defaultPublic()
    if not Host.chosen and not Games.dev then Games.setPublic(true) end
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
    local blocked = gated()
    if blocked then return done(false, blocked) end
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
        local route = Games.put("join_request.txt", data.connection_string .. "\n", "join_reply.txt")
        if not route then
            done(false, "cannot write the join request")
            return
        end
        if not native("mjolnir_join") then
            done(false, "the native half is not loaded")
            return
        end
        local deadline = os.time() + 5
        local function poll()
            local reply = Games.reply("join_reply.txt", route)
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

-- Joins into a match under way: on unless native's join_in_progress.txt says
-- 0. A setting nothing changes in a match, read every 30 s, not each second.
local jipSetting = { on = true, at = nil }
local function joinsUnderWay(now)
    if not jipSetting.at or now - jipSetting.at >= 30 then
        jipSetting.at = now
        jipSetting.on = not (readFile(nativeDir .. "join_in_progress.txt") or ""):match("^%s*0")
    end
    return jipSetting.on
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
        -- Only a public game has a session to show (Session.host), so a
        -- private host does not build one: it reads the launcher's state and
        -- every player's name and pawn, each second.
        local info = Host.public and Host.info and Host.info() or nil
        local jip = joinsUnderWay(now)
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
--- inMatch, reportSlow }.

function Games.init(deps)
    nativeDir = deps.modDir .. "\\native\\"
    listingFile = deps.modDir .. "\\listing.txt"
    noticeFile = deps.modDir .. "\\chat_notice.txt"
    Json, Net, log = deps.json, deps.net, deps.log
    reportSlow = deps.reportSlow or reportSlow
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
    -- Timed for the hitch log (MJOLNIRHud's hitches.lua), which saw none of
    -- this loop before: its controller walk every 5 s on a host was the
    -- "none of our timed loops" hitch every 5.1 s.
    local function loop()
        local started = os.clock()
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
        pcall(reportSlow, "games", started)
        ExecuteInGameThreadWithDelay(1000, loop)
    end
    ExecuteInGameThreadWithDelay(1000, loop)
end

return Games

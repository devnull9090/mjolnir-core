-- MJOLNIR Lobby
--
-- The MULTIPLAYER menu: a main-menu entry and the screens behind it, made from
-- the game's own widgets (Scripts/ui.lua), for the classic CE maps that
-- MJOLNIRLevelLoader installs.
--
-- HOST GAME picks a map and a mode, then shows the lobby: the fireteam panel
-- is the game's own co-op squad, so INVITE + brings friends in. START GAME
-- starts the map the way the campaign menu's Start Game does, which is the
-- only start the simulation accepts (docs/multiplayer_menu.md):
--
--   SetCampaignMode -> GetCampaignSetup -> SelectedMission/Difficulty/
--   InsertionPoint -> SetClientLobbyMission/Difficulty -> StartCountdown
--
-- The countdown is the co-op lobby's, seen by every fireteam member; when it
-- ends the game calls LaunchCampaign, which builds the scenario options (with
-- the campaign variant a bare SetAndBeginCampaign lacks) and starts the map.
-- The chosen mode reaches MJOLNIRLevelLoader as pending_variant.txt beside it,
-- read when the map starts. A multiplayer map makes no campaign checkpoints,
-- so the campaign save is never written (checked byte for byte).
--
-- MULTIPLAYER opens MJOLNIR's own lobby and map select screens
-- (WBP_MJOLNIRLobby, WBP_MJOLNIRMapSelect, "Our own screens" below), with the
-- campaign-menu screens as the fallback when the UI container is missing.
-- Finding and joining other players' games is still to come.

local function modDirectory()
    local source = debug.getinfo(1, "S").source or ""
    local root = source:gsub("^@", ""):gsub("/", "\\")
    for _ = 1, 2 do
        root = root:match("^(.*)\\[^\\]*$") or root
    end
    return root
end

local MOD_DIR = modDirectory()
local Json = dofile(MOD_DIR .. "\\Scripts\\json.lua")
local UI = dofile(MOD_DIR .. "\\Scripts\\ui.lua")
local Net = dofile(MOD_DIR .. "\\Scripts\\net.lua")
local BuildLine = dofile(MOD_DIR .. "\\Scripts\\buildline.lua")
local SquadPanel = dofile(MOD_DIR .. "\\Scripts\\squadpanel.lua")
local Games = dofile(MOD_DIR .. "\\Scripts\\games.lua")
local Matches = dofile(MOD_DIR .. "\\Scripts\\matches.lua")
local MODS_DIR = MOD_DIR:match("^(.*)\\[^\\]*$") or MOD_DIR
local LOADER_DIR = (MOD_DIR:match("^(.*)\\[^\\]*$") or MOD_DIR) .. "\\MJOLNIRLevelLoader"
local log = UI.log

local HELPERS = "/Game/UI/Frontend/CampaignMenu/Data/BPFL_CampaignMenuHelpers.Default__BPFL_CampaignMenuHelpers_C"
local SCENARIOS = "/Game/Blueprints/Campaign/DT_Scenarios.DT_Scenarios"
local CAMPAIGN_MODE = 0      -- E_CampaignMode: the campaign's scenario list and save slot
local DIFFICULTY_NORMAL = 1

-- The game types, in menu order. A mode is offered for a map when the map
-- lists it and its variant file is installed. `slot` is the insertion point
-- a game of this type starts at: the host's travel carries the index to
-- every fireteam client, whose loader reads the game type from it (keep in
-- step with MJOLNIRLevelLoader's GAME_TYPE_SLOTS).
local MODES = {
    { id = "slayer", slot = 0, name = "SLAYER", description = "Free for all. Every kill scores a point; the first to the score limit wins." },
    { id = "team_slayer", slot = 2, name = "TEAM SLAYER", teams = true, description = "Red against Blue. Kills score for your team." },
    { id = "koth", slot = 3, name = "KING OF THE HILL", description = "Hold the hill to score. The hill moves." },
    { id = "oddball", slot = 4, name = "ODDBALL", description = "Hold the skull to score." },
    { id = "ctf", slot = 1, name = "CAPTURE THE FLAG", teams = true, description = "Take the enemy flag to your base." },
}

local function readFile(path)
    local f = io.open(path, "rb")
    if not f then return nil end
    local data = f:read("*a")
    f:close()
    return data
end

-- What FIND GAMES compares between a host and a joiner.
local LOBBY_VERSION = (readFile(MOD_DIR .. "\\mod.json") or ""):match('"version"%s*:%s*"([^"]+)"') or "?"

local function fileExists(path)
    local f = io.open(path, "rb")
    if f then f:close() end
    return f ~= nil
end

-- Maps the launcher installs from map packs live beside the mods
-- (docs/map_distribution.md); maps converted on this machine with --install
-- are listed in the loader's own folder.
local MAPS_DIR = (MOD_DIR:match("^(.*)\\Mods\\[^\\]*$") or MOD_DIR) .. "\\MJOLNIRMaps"

local function readMaps(path)
    local raw = readFile(path)
    if not raw then return {} end
    local ok, maps = pcall(Json.decode, raw)
    if not ok or type(maps) ~= "table" then
        log(path .. ": " .. tostring(maps))
        return {}
    end
    return maps
end

--- The installed maps ({ code, title, description, modes }): the launcher's
--- MJOLNIRMaps\maps.json, then MJOLNIRLevelLoader\maps.json (written by
--- `mjolnir level bake --install-test`) for codes it does not list.
local function installedMaps()
    local maps, seen = {}, {}
    for _, path in ipairs({ MAPS_DIR .. "\\maps.json", LOADER_DIR .. "\\maps.json" }) do
        for _, map in ipairs(readMaps(path)) do
            if type(map) == "table" and map.code and not seen[map.code] then
                seen[map.code] = true
                maps[#maps + 1] = map
            end
        end
    end
    return maps
end

local function modesFor(map)
    local listed = {}
    for _, m in ipairs(type(map.modes) == "table" and map.modes or { "slayer" }) do listed[m] = true end
    local out = {}
    for _, mode in ipairs(MODES) do
        if listed[mode.id] and fileExists(LOADER_DIR .. "\\variants\\" .. mode.id .. ".mglo") then
            out[#out + 1] = mode
        end
    end
    return out
end

local function titleOf(map)
    local title = string.upper(tostring(map.title or map.code)):gsub(" %(CLASSIC CE%)", "")
    return title
end

-------------------------------------------------------------------------------
-- Starting a game
-------------------------------------------------------------------------------

local function startGame(map, mode)
    local pc = UI.playerController()
    local helpers = StaticFindObject(HELPERS)
    local table_ = StaticFindObject(SCENARIOS)
    if not (UI.valid(pc) and UI.valid(helpers) and UI.valid(table_)) then
        return false, "the frontend is not ready"
    end
    local row = FName(map.code)
    helpers:SetCampaignMode(pc, CAMPAIGN_MODE, pc)
    local out = {}
    helpers:GetCampaignSetup(pc, pc, out)
    local setup = out.CampaignSetup
    if not UI.valid(setup) then return false, "no campaign setup" end
    helpers:SelectedMission(pc, setup, table_, row, pc, {})
    helpers:SelectedDifficulty(pc, setup, DIFFICULTY_NORMAL, pc)
    helpers:SelectedInsertionPoint(pc, setup, mode.slot or 0, pc)
    helpers:SetClientLobbyMission(table_, row, pc)
    helpers:SetClientLobbyDifficulty(DIFFICULTY_NORMAL, pc)

    -- The mode, for MJOLNIRLevelLoader to stage when the map starts.
    local f = io.open(LOADER_DIR .. "\\pending_variant.txt", "w")
    if f then
        f:write(mode.id)
        f:close()
    end
    helpers:StartCountdown(setup, pc)
    log(string.format("starting %s (%s): countdown", map.code, mode.id))
    Games.changed()
    return true
end

-------------------------------------------------------------------------------
-- Screens
-------------------------------------------------------------------------------

local function lobbyScreen(map, mode)
    local description = string.format(
        "%s on %s.\n\nInvite friends with INVITE + on the right; they join your fireteam. Start when everyone is in.",
        mode.name, titleOf(map))
    local rec
    rec = UI.push({
        title = "LOBBY",
        subtitle = titleOf(map) .. "  -  " .. mode.name,
        description = description,
        buttons = {
            {
                label = "START GAME",
                description = description,
                onClick = function()
                    local ok, err = startGame(map, mode)
                    if not ok then UI.describe(rec, "Could not start: " .. tostring(err)) end
                end,
            },
        },
    })
end

local function modeScreen(map)
    local buttons = {}
    for _, mode in ipairs(modesFor(map)) do
        buttons[#buttons + 1] = {
            label = mode.name,
            description = mode.description,
            onClick = function() lobbyScreen(map, mode) end,
        }
    end
    UI.push({
        title = "GAME TYPE",
        subtitle = titleOf(map),
        description = #buttons > 0 and buttons[1].description or "No game type is installed for this map.",
        buttons = buttons,
    })
end

local function mapScreen()
    local buttons = {}
    for _, map in ipairs(installedMaps()) do
        buttons[#buttons + 1] = {
            label = titleOf(map),
            description = map.description,
            onClick = function() modeScreen(map) end,
        }
    end
    UI.push({
        title = "SELECT MAP",
        subtitle = "HOST GAME",
        description = #buttons > 0 and buttons[1].description
            or "No classic CE maps are installed. Convert one with tools/level/convert_ce_map.sh.",
        buttons = buttons,
    })
end

local function notYet(title)
    UI.push({
        title = title,
        subtitle = "MULTIPLAYER",
        description = "Finding public games needs the MJOLNIR UI (pakchunk984-MJOLNIRUI). "
            .. "Install the CE runtime from the MJOLNIR launcher, or HOST GAME and invite friends.",
        buttons = {},
    })
end

local function rootScreen()
    UI.push({
        title = "MULTIPLAYER",
        subtitle = "CLASSIC CE MAPS",
        description = "Host a game for your fireteam, find a public game, or join a friend's private match.",
        buttons = {
            { label = "HOST GAME", description = "Pick a map and a game type, invite your fireteam, and start.", onClick = mapScreen },
            { label = "FIND GAMES", description = "Browse public games.", onClick = function() notYet("FIND GAMES") end },
            { label = "JOIN PRIVATE", description = "Join a friend's private match.", onClick = function() notYet("JOIN PRIVATE") end },
        },
    })
end

-------------------------------------------------------------------------------
-- Our own screens
-------------------------------------------------------------------------------
--
-- WBP_MJOLNIRLobby and WBP_MJOLNIRMapSelect are MJOLNIR's own widgets, cooked
-- into pakchunk984-MJOLNIRUI (unreal/MJOLNIRMaterials/Scripts/
-- build_mjolnir_ui.py, docs/custom_ui.md). They are CommonActivatableWidgets
-- pushed onto the same ContentStack as the game's screens, so the stack
-- hides the main menu beneath them and Back pops them. Their buttons click
-- on their own: each calls the widget's MJ_Event(<event>), hooked here.
-- Without the container, MULTIPLAYER falls back to the campaign-menu screens
-- above.

local UI_ROOT = "/Game/MJOLNIR/UI/"
local LOBBY_CLASS = UI_ROOT .. "WBP_MJOLNIRLobby.WBP_MJOLNIRLobby_C"
local SELECT_CLASS = UI_ROOT .. "WBP_MJOLNIRMapSelect.WBP_MJOLNIRMapSelect_C"
local FIND_CLASS = UI_ROOT .. "WBP_MJOLNIRFindGames.WBP_MJOLNIRFindGames_C"
local MAP_BUTTONS = 32
local MODE_BUTTONS = 5
local ROSTER_ROWS = 16
local GAME_ROWS = 40
local LAST_GAME = MOD_DIR .. "\\last_game.txt"
local MAX_PLAYERS_FILE = MOD_DIR .. "\\max_players.txt"

local WHITE = { R = 1, G = 1, B = 1, A = 1 }
local ACCENT = { R = 0.55, G = 0.85, B = 1.0, A = 1 }
local NORMAL_BACKGROUND = { R = 1, G = 1, B = 1, A = 1 }
local SELECTED_BACKGROUND = { R = 3.0, G = 3.5, B = 3.5, A = 1 }

-- The fireteam's ceiling: the simulation's players array holds 16
-- (docs/fireteam_join_and_cap.md). The host's MAX PLAYERS narrows it.
local FIRETEAM_SIZE = 16
local MIN_PLAYERS = 2

local Game = { map = nil, mode = nil, maxPlayers = FIRETEAM_SIZE }   -- what START GAME starts
local Lobby, Select = nil, nil           -- the screens on the stack
local Find = nil                         -- FIND GAMES, while it is up
local Found = { all = {}, games = {}, maps = {}, matching = 0, chosen = nil, loading = false }
local listingStatus = nil                -- the lobby footer's last listing line
local Pick = { map = nil, mode = nil }   -- the map select's choice, until SELECT
-- A fireteam client's view of the host's lobby (After a match, below).
local clientLobby = { dismissed = false, at = nil }
-- hooked: class path -> true once its MJ_Event hook is in, false after a
-- failed try. watching (the new-lobby watch): false before the first try,
-- nil after a failed one, true once registered. noUI: the lobby class does
-- not load (no pakchunk984), so there is nothing to watch.
local screenEvents = { hooked = {}, watching = false, noUI = false }

local function setText(block, text)
    pcall(function() block:SetText(FText(text or "")) end)
end

local function setShown(w, shown)
    pcall(function() w:SetVisibility(shown and 0 or 1) end)
end

local function loadClass(path)
    local ok, cls = pcall(function()
        local ksl = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
        return ksl:LoadClassAsset_Blocking(ksl:Conv_SoftClassPathToSoftClassRef(ksl:MakeSoftClassPath(path)))
    end)
    if ok and UI.valid(cls) then return cls end
    return nil
end

--- FIND GAMES is in the installed UI container: one from before it still
--- has the lobby, without the button.
local findGames = nil
local function hasFindGames()
    if findGames == nil then findGames = loadClass(FIND_CLASS) ~= nil end
    return findGames
end

--- Push one of our screens onto the game's menu stack.
local function pushScreen(classPath)
    local layout = UI.layout()
    local cls = loadClass(classPath)
    if not (UI.valid(layout) and cls) then return nil end
    local ok, screen = pcall(function() return layout.ContentStack:BP_AddWidget(cls) end)
    if not (ok and UI.valid(screen)) then return nil end
    setText(screen.Watermark, BuildLine.text(MODS_DIR))
    return screen
end

local function alive(screen)
    if not UI.valid(screen) then return false end
    local ok, active = pcall(function() return screen:IsActivated() end)
    return ok and active
end

--- The last game hosted, or the first installed map and its first mode.
local function defaultGame()
    local maps = installedMaps()
    local raw = readFile(LAST_GAME)
    local code, modeId = (raw or ""):match("^([^\t]+)\t([%w_]+)")
    local chosen
    for _, map in ipairs(maps) do
        if map.code == code then chosen = map end
    end
    chosen = chosen or maps[1]
    if not chosen then return nil, nil end
    local modes = modesFor(chosen)
    local mode = modes[1]
    for _, m in ipairs(modes) do
        if m.id == modeId then mode = m end
    end
    return chosen, mode
end

local function saveGame()
    if not (Game.map and Game.mode) then return end
    local f = io.open(LAST_GAME, "w")
    if f then
        f:write(Game.map.code, "\t", Game.mode.id, "\n")
        f:close()
    end
end

--- The smallest MAX PLAYERS the host can pick with `present` players in the
--- fireteam: PlayFab does not shrink a lobby below its members.
local function minPlayers(present)
    return math.max(MIN_PLAYERS, math.min(present or 0, FIRETEAM_SIZE))
end

--- Hand Game.maxPlayers to the native half, which resizes the PlayFab lobby
--- this game owns (and every lobby it creates from now on), and to the
--- listing. The lobby turns away anyone past it, however they join; the
--- game's GameSession is held to it at once (holdFireteamSize). Returns the
--- native half's reply ("ok", "kept" or "error ..."), or why there is none.
local function applyMaxPlayers()
    Games.setMaxPlayers(Game.maxPlayers)
    local native = MOD_DIR .. "\\native\\"
    local request = io.open(native .. "lobby_max.txt", "wb")
    if not request then return "error cannot write lobby_max.txt" end
    request:write(tostring(Game.maxPlayers))
    request:close()
    local apply = package and package.loadlib and package.loadlib(native .. "mjolnir_lobby.dll", "mjolnir_lobby_max")
    if not apply then return "error the native half is not installed" end
    local ok, err = pcall(apply)
    if not ok then return "error " .. tostring(err) end
    local reply = (readFile(native .. "lobby_max_reply.txt") or "error no reply"):gsub("%s+$", "")
    return reply
end

--- The size PlayFab reports for the lobby, or nil when there is none.
local function lobbyMax()
    local native = MOD_DIR .. "\\native\\"
    local read = package and package.loadlib and package.loadlib(native .. "mjolnir_lobby.dll", "mjolnir_lobby_connection")
    if not (read and pcall(read)) then return nil end
    return tonumber((readFile(native .. "lobby_connection.txt") or ""):match("\nmax (%d+)") or "")
end

-- PlayFab throttles lobby updates: thirty in twenty seconds left the lobby
-- at an early size while every call still returned success (2026-10-04). So
-- a click only changes the number; the lobby gets the last one once the
-- host stops clicking, is read back, and is sent again until it holds it.
local RESIZE_DELAY_MS = 1500
local RESIZE_CHECK_MS = 5000
local RESIZE_TRIES = 5
local resizeToken = 0

local function resizeLobby(delay, tries)
    resizeToken = resizeToken + 1
    local token = resizeToken
    ExecuteInGameThreadWithDelay(delay, function()
        if token ~= resizeToken then return end   -- a newer click took over
        local reply = applyMaxPlayers()
        log("max players: " .. Game.maxPlayers .. " (" .. reply .. ")")
        if reply:match("^error") then
            setText(Lobby and Lobby.Status, "MAX PLAYERS NOT APPLIED: " .. reply:sub(7))
            return
        end
        if not reply:match("^ok") then return end   -- kept for the next lobby
        ExecuteInGameThreadWithDelay(RESIZE_CHECK_MS, function()
            if token ~= resizeToken then return end
            local held = lobbyMax()
            if not held or held == Game.maxPlayers then return end
            if tries >= RESIZE_TRIES then
                log("max players: the lobby still holds " .. held .. " after " .. tries .. " tries")
                setText(Lobby and Lobby.Status, "MAX PLAYERS NOT APPLIED: the lobby still holds " .. held)
                return
            end
            log("max players: the lobby holds " .. held .. "; sending " .. Game.maxPlayers .. " again")
            resizeLobby(0, tries + 1)
        end)
    end)
end

--- The host's MAX PLAYERS, kept within what the fireteam allows and saved
--- for the next session.
local function setMaxPlayers(size, present)
    size = math.max(minPlayers(present), math.min(FIRETEAM_SIZE, size))
    if size == Game.maxPlayers then return end
    Game.maxPlayers = size
    local f = io.open(MAX_PLAYERS_FILE, "w")
    if f then
        f:write(tostring(size), "\n")
        f:close()
    end
    setText(Lobby and Lobby.Status, "UP TO " .. size .. " PLAYERS CAN BE IN THIS FIRETEAM")
    resizeLobby(RESIZE_DELAY_MS, 1)
end

--- The players in the fireteam: the frontend's player states.
local function rosterPlayers()
    local roster = {}
    pcall(function()
        local players = UI.playerController():GetWorld().GameState.PlayerArray
        players:ForEach(function(_, element)
            local ps = element:get()
            local okN, name = pcall(function() return ps:GetPlayerName():ToString() end)
            if okN and name and name ~= "" then
                -- The frontend often has no simulation pawn yet. Leave the
                -- team unknown until the game actually supplies one.
                local okT, team = pcall(function()
                    return ps:GetPawn().BlamGameTeam:GetGameTeamString():ToString():match("EBlamMultiplayerTeam::(%a+)")
                end)
                roster[#roster + 1] = { name = name,
                    team = okT and (team == "Red" or team == "Blue") and team or "Unassigned" }
            end
        end)
    end)
    return roster
end

local function drawLobby()
    if not UI.valid(Lobby) then return end
    local map, mode = Game.map, Game.mode
    setText(Lobby.MapTitle, map and titleOf(map) or "NO MAPS INSTALLED")
    setText(Lobby.MapDescription, map and map.description or
        "Convert a classic CE map (tools/level/convert_ce_map.sh) or install a map pack.")
    setText(Lobby.ModeTitle, mode and mode.name or "")
    setText(Lobby.ModeDescription, mode and mode.description or "")
    local roster = rosterPlayers()
    local teams = mode and mode.teams
    setText(Lobby.PlayersHeading, "PLAYERS  /  " .. tostring(#roster))
    setText(Lobby.MatchFormat, teams and "RED TEAM  /  BLUE TEAM" or "FREE FOR ALL")
    setText(Lobby.TeamHint, teams and "Teams are assigned by the game when the match starts." or "Every Spartan for themselves.")
    -- A fireteam client sees the host's choice; only the host changes it or
    -- starts the game.
    local host = Net.isHost()
    pcall(function() Lobby.Start:SetIsEnabled(host and map ~= nil and mode ~= nil) end)
    for _, key in ipairs({ "Start", "ChangeMap", "GameType", "Listing" }) do setShown(Lobby[key], host) end
    setText(Lobby.ListingLabel, Games.isPublic() and "PUBLIC GAME" or "PRIVATE GAME")
    -- MAX PLAYERS: a runtime pack from before it has no such row, and the
    -- fireteam stays at FIRETEAM_SIZE.
    setShown(Lobby.MaxPlayersRow, host)
    setText(Lobby.MaxPlayersValue, tostring(Game.maxPlayers))
    pcall(function() Lobby.MaxPlayersDown:SetIsEnabled(Game.maxPlayers > minPlayers(#roster)) end)
    pcall(function() Lobby.MaxPlayersUp:SetIsEnabled(Game.maxPlayers < FIRETEAM_SIZE) end)
    setShown(Lobby.FindGames, hasFindGames())
    local status = host and Games.status() or ""
    if status ~= "" and status ~= listingStatus then setText(Lobby.Status, status) end
    listingStatus = status
    for _, group in ipairs({ "FFA", "Red", "Blue", "Unassigned" }) do
        local members = {}
        for _, player in ipairs(roster) do
            if (not teams and group == "FFA") or (teams and player.team == group) then
                members[#members + 1] = player.name
            end
        end
        setShown(Lobby[group .. "Roster"], (group == "FFA" and not teams) or
            (teams and group ~= "FFA" and (group ~= "Unassigned" or #members > 0)))
        local title = group == "FFA" and "FIRETEAM" or
            (group == "Unassigned" and "AWAITING ASSIGNMENT" or string.upper(group) .. " TEAM")
        setText(Lobby[group .. "Heading"], title .. "  /  " .. tostring(#members))
        for i = 0, ROSTER_ROWS - 1 do
            setText(Lobby[group .. "Player" .. i], members[i + 1] or "")
            setShown(Lobby[group .. "Player" .. i], members[i + 1] ~= nil)
        end
    end
end

local function showDetails(map)
    if not (UI.valid(Select) and map) then return end
    setText(Select.MapTitle, titleOf(map))
    setText(Select.MapDescription, map.description)
    local modes = modesFor(map)
    for i = 0, MODE_BUTTONS - 1 do
        local mode, button = modes[i + 1], Select["Mode" .. i]
        setShown(button, mode ~= nil)
        if mode then
            setText(Select["Mode" .. i .. "Label"], mode.name)
            local chosen = Pick.map and Pick.map.code == map.code and Pick.mode == mode
            pcall(function() button:SetBackgroundColor(chosen and SELECTED_BACKGROUND or NORMAL_BACKGROUND) end)
        end
    end
    local shown = (Pick.map and Pick.map.code == map.code and Pick.mode) or modes[1]
    setText(Select.ModeDescription, shown and shown.description or "No game type is installed for this map.")
end

local function drawSelect()
    if not UI.valid(Select) then return end
    pcall(function() Select.Select:SetIsEnabled(Pick.map ~= nil and Pick.mode ~= nil) end)
    local maps = installedMaps()
    for i = 0, MAP_BUTTONS - 1 do
        local map, button = maps[i + 1], Select["Map" .. i]
        setShown(button, map ~= nil)
        if map then
            local label = Select["Map" .. i .. "Label"]
            setText(label, titleOf(map))
            local chosen = Pick.map and Pick.map.code == map.code
            pcall(function()
                button:SetBackgroundColor(chosen and SELECTED_BACKGROUND or NORMAL_BACKGROUND)
                label:SetColorAndOpacity({ SpecifiedColor = chosen and ACCENT or WHITE, ColorUseRule = 0 })
            end)
        end
    end
    showDetails(Pick.map)
end

local function pickMap(map)
    if not map then return end
    local keep
    for _, m in ipairs(modesFor(map)) do
        if Pick.mode and m.id == Pick.mode.id then keep = m end
    end
    Pick.map, Pick.mode = map, keep or modesFor(map)[1]
    drawSelect()
end

local function openMapSelect()
    Pick.map, Pick.mode = Game.map, Game.mode
    Select = pushScreen(SELECT_CLASS)
    if not Select then
        log("map select: could not push " .. SELECT_CLASS)
        return
    end
    drawSelect()
    pcall(function() Select.Select:SetFocus() end)
end

--- The game's own Friends screen (Platform and Cross-Platform friends, each
--- with + Invite), as the fireteam panel's INVITE + rows open it: their
--- click event, called on one of them. The rows belong to the UI layout's
--- squad widget, alive under every screen.
local function openFriends()
    local row = UI.liveWidget("WBP_SquadBlankListViewItem_C", function() return true end)
    if not row then
        setText(Lobby.Status, "The fireteam panel is not loaded; invite from the main menu.")
        return
    end
    local ok, err = pcall(function() row:BP_OnClicked() end)
    if not ok then setText(Lobby.Status, "Could not open Friends: " .. tostring(err)) end
end

-------------------------------------------------------------------------------
-- FIND GAMES
-------------------------------------------------------------------------------
--
-- Public games from the hub (games.lua) as a server table: a row per game
-- with its server name and host, map, game type, players, ping and status,
-- in columns that line up. A column's heading sorts by it (again reverses
-- it); the chips above filter by game type and map, and hide full games,
-- matches under way and maps not installed. Hovering a row previews it,
-- clicking chooses it; JOIN joins the chosen game the way an accepted invite
-- would, and QUICK JOIN joins the best open game the filters allow. The list
-- refreshes itself every AUTO_REFRESH seconds while it is up, and the sort
-- and filters are kept in find_games.txt.
--
-- A UI container from before the table (one button label per row) still
-- works: its rows get the old one-line label, unsorted and unfiltered.

-- One block, so its locals stay out of the main chunk's (Lua allows 200).
local openFindGames, onFindEvent, tickFind, modeName
do
local FIND_PREFS = MOD_DIR .. "\\find_games.txt"
local AUTO_REFRESH = 30   -- seconds
local NOTE_SECONDS = 10   -- how long a join message stays in the footer
local PIPS = 16

-- The screen's colours (build_mjolnir_ui.py), as Lua colours.
local FIND = {
    accent = { R = 0.46, G = 0.79, B = 0.94, A = 1 },
    white = { R = 0.88, G = 0.95, B = 1.0, A = 1 },
    grey = { R = 0.46, G = 0.61, B = 0.70, A = 1 },
    dim = { R = 0.20, G = 0.30, B = 0.36, A = 1 },
    gold = { R = 1.0, G = 0.80, B = 0.35, A = 1 },
    green = { R = 0.45, G = 0.88, B = 0.55, A = 1 },
    red = { R = 1.0, G = 0.32, B = 0.28, A = 1 },
}
local ZEBRA_BACKGROUND = { R = 1.35, G = 1.35, B = 1.35, A = 1.1 }
local ROW_CHOSEN_BACKGROUND = { R = 1.8, G = 2.0, B = 2.0, A = 1.4 }
local CHIP_ON_BACKGROUND = { R = 3.0, G = 3.5, B = 3.5, A = 1.3 }

-- A column: its widget names' key, heading, and the footer's wording.
local SORTS = {
    name = { col = "Name", title = "SERVER", asc = "A TO Z", desc = "Z TO A" },
    map = { col = "Map", title = "MAP", asc = "A TO Z", desc = "Z TO A" },
    type = { col = "Type", title = "GAME TYPE", asc = "A TO Z", desc = "Z TO A" },
    players = { col = "Players", title = "PLAYERS", asc = "FEWEST FIRST", desc = "MOST FIRST", descFirst = true },
    ping = { col = "Ping", title = "PING", asc = "LOWEST FIRST", desc = "HIGHEST FIRST" },
    state = { col = "State", title = "STATUS", asc = "OPEN FIRST", desc = "FULL FIRST" },
}
local SORT_UP, SORT_DOWN = "\226\150\178", "\226\150\188"   -- U+25B2, U+25BC

local STATES = {
    open = { label = "LOBBY", kicker = "IN THE LOBBY", color = FIND.green, rank = 0 },
    in_game = { label = "IN MATCH", kicker = "MATCH UNDER WAY", color = FIND.accent, rank = 1 },
    full = { label = "FULL", kicker = "FULL", color = FIND.red, rank = 2 },
}

-- Saved: the sort, the game type filter and the three toggles. The map
-- filter lasts while the screen is up.
local Prefs = { sort = "ping", desc = false, type = nil, full = false, match = false, have = false }

local function loadFindPrefs()
    for k, v in (readFile(FIND_PREFS) or ""):gmatch("([%w_]+)=([^\r\n]*)") do
        if k == "sort" and SORTS[v] then
            Prefs.sort = v
        elseif k == "desc" or k == "full" or k == "match" or k == "have" then
            Prefs[k] = v == "1"
        elseif k == "type" then
            Prefs.type = v ~= "" and v or nil
        end
    end
end

local function saveFindPrefs()
    local f = io.open(FIND_PREFS, "w")
    if not f then return end
    for _, k in ipairs({ "sort", "desc", "type", "full", "match", "have" }) do
        local v = Prefs[k]
        if type(v) == "boolean" then v = v and "1" or "0" end
        f:write(k, "=", tostring(v or ""), "\n")
    end
    f:close()
end

function modeName(id)
    for _, mode in ipairs(MODES) do
        if mode.id == id then return mode.name end
    end
    return (string.upper(tostring(id or "")):gsub("_", " "))
end

local function teamsMode(id)
    for _, mode in ipairs(MODES) do
        if mode.id == id then return mode.teams == true end
    end
    return false
end

--- The installed maps by code, read once per refresh rather than per row.
local function indexMaps()
    Found.maps = {}
    for _, map in ipairs(installedMaps()) do Found.maps[map.code] = map end
end

local function ownMap(g)
    return Found.maps[g.map_code]
end

local function mapTitle(g)
    local map = ownMap(g)
    if map then return titleOf(map) end
    return (string.upper(tostring(g.map_title or g.map_code or "?")):gsub(" %(CLASSIC CE%)", ""))
end

local function stateOf(g)
    if g.state == "full" or (g.max_players and (g.players or 0) >= g.max_players) then return "full" end
    return g.state == "in_game" and "in_game" or "open"
end

local function otherVersion(g)
    return g.client_version and g.client_version ~= LOBBY_VERSION
end

--- Signal bars for an estimated ping: how many of four, and their colour.
local function pingBars(ms)
    if not ms then return 0, FIND.dim end
    if ms <= 60 then return 4, FIND.green end
    if ms <= 110 then return 3, FIND.green end
    if ms <= 170 then return 2, FIND.gold end
    return 1, FIND.red
end

local function tint(block, color)
    pcall(function() block:SetColorAndOpacity({ SpecifiedColor = color, ColorUseRule = 0 }) end)
end

local function brush(border, color)
    pcall(function() border:SetBrushColor(color) end)
end

--- The table layout, or a container from before it.
local function tableLayout()
    if Found.table == nil then
        local ok, yes = pcall(function() return Find.TableHeader:IsValid() end)
        Found.table = ok and yes == true
    end
    return Found.table
end

local function sortValue(g, key)
    if key == "name" then return string.lower(tostring(g.name or "")) end
    if key == "map" then return mapTitle(g) end
    if key == "type" then return modeName(g.game_type) end
    if key == "players" then return g.players or 0 end
    if key == "ping" then return g.ping_ms or math.huge end
    return STATES[stateOf(g)].rank
end

--- The table's order: the chosen column, then fuller games, then nearer,
--- then the id, so the order is total and rows don't swap on a refresh.
local function before(a, b)
    local va, vb = sortValue(a, Prefs.sort), sortValue(b, Prefs.sort)
    if va ~= vb then
        if Prefs.desc then return va > vb end
        return va < vb
    end
    if (a.players or 0) ~= (b.players or 0) then return (a.players or 0) > (b.players or 0) end
    local pa, pb = a.ping_ms or math.huge, b.ping_ms or math.huge
    if pa ~= pb then return pa < pb end
    return tostring(a.id) < tostring(b.id)
end

local function passes(g)
    if Prefs.type and g.game_type ~= Prefs.type then return false end
    if Found.mapFilter and g.map_code ~= Found.mapFilter then return false end
    local state = stateOf(g)
    if Prefs.full and state == "full" then return false end
    if Prefs.match and state == "in_game" then return false end
    if Prefs.have and not ownMap(g) then return false end
    return true
end

local function filtering()
    return Prefs.type ~= nil or Found.mapFilter ~= nil or Prefs.full or Prefs.match or Prefs.have
end

--- Found.games: the rows, filtered and sorted. The old layout lists the
--- hub's order, unfiltered.
local function applyView()
    local list = {}
    local legacy = not tableLayout()
    for _, g in ipairs(Found.all) do
        if legacy or passes(g) then list[#list + 1] = g end
    end
    if not legacy then table.sort(list, before) end
    Found.matching = #list
    Found.games = {}
    for i = 1, math.min(#list, GAME_ROWS) do Found.games[i] = list[i] end
    -- The chosen game stays chosen while it is in view; otherwise the top row.
    local keep
    for _, g in ipairs(Found.games) do
        if Found.chosen and g.id == Found.chosen.id then keep = g end
    end
    Found.chosen = keep or Found.games[1]
    if Found.hovered then
        local still
        for _, g in ipairs(Found.games) do
            if g.id == Found.hovered.id then still = g end
        end
        Found.hovered = still
    end
end

--- The next value of a cycling filter: nil (ALL), then each choice, then
--- back to ALL.
local function cycle(choices, current)
    if current == nil then return choices[1] end
    for i, v in ipairs(choices) do
        if v == current then return choices[i + 1] end
    end
    return nil
end

--- The game types listed now: menu order first, then any others.
local function typeChoices()
    local present, out, others = {}, {}, {}
    for _, g in ipairs(Found.all) do
        if g.game_type then present[g.game_type] = true end
    end
    for _, mode in ipairs(MODES) do
        if present[mode.id] then
            out[#out + 1] = mode.id
            present[mode.id] = nil
        end
    end
    for id in pairs(present) do others[#others + 1] = id end
    table.sort(others)
    for _, id in ipairs(others) do out[#out + 1] = id end
    return out
end

--- The maps listed now, by title.
local function mapChoices()
    local seen, out = {}, {}
    for _, g in ipairs(Found.all) do
        if g.map_code and not seen[g.map_code] then
            seen[g.map_code] = mapTitle(g)
            out[#out + 1] = g.map_code
        end
    end
    table.sort(out, function(a, b) return seen[a] < seen[b] end)
    return out, seen
end

local function ago(seconds)
    if seconds < 5 then return "JUST NOW" end
    if seconds < 60 then return string.format("%d S AGO", seconds) end
    return string.format("%d MIN AGO", math.floor(seconds / 60))
end

--- The footer: a recent join message, the hub's error, or when the list
--- was fetched.
local function drawFindStatus()
    if not alive(Find) then return end
    local text
    if Found.note and os.time() - Found.note.at < NOTE_SECONDS then
        text = Found.note.text
    elseif Found.error then
        text = "Could not refresh: " .. Found.error
    elseif Found.fetchedAt then
        text = string.format("UPDATED %s   /   REFRESHES EVERY %d S   /   SELECT A COLUMN HEADING TO SORT",
            ago(os.time() - Found.fetchedAt), AUTO_REFRESH)
    else
        text = Found.loading and "Looking for games..." or ""
    end
    if not tableLayout() and not Found.note and not Found.error and Found.fetchedAt then
        text = string.format("%d PUBLIC GAME%s   /   REFRESH FOR MORE", #Found.games, #Found.games == 1 and "" or "S")
    end
    if text ~= Found.statusShown then
        Found.statusShown = text
        setText(Find.Status, text)
    end
end

local function findNote(text)
    Found.note = { text = text, at = os.time() }
    drawFindStatus()
end

local function drawFilters()
    local typeValue = Find.FilterTypeValue
    setText(typeValue, Prefs.type and modeName(Prefs.type) or "ALL")
    tint(typeValue, Prefs.type and FIND.gold or FIND.white)
    local _, titles = mapChoices()
    local mapValue = Find.FilterMapValue
    setText(mapValue, Found.mapFilter and (titles[Found.mapFilter] or Found.mapFilter) or "ALL")
    tint(mapValue, Found.mapFilter and FIND.gold or FIND.white)
    pcall(function() Find.FilterType:SetBackgroundColor(Prefs.type and CHIP_ON_BACKGROUND or NORMAL_BACKGROUND) end)
    pcall(function() Find.FilterMap:SetBackgroundColor(Found.mapFilter and CHIP_ON_BACKGROUND or NORMAL_BACKGROUND) end)
    for key, on in pairs({ Full = Prefs.full, Match = Prefs.match, Have = Prefs.have }) do
        brush(Find["Filter" .. key .. "Check"], on and FIND.accent or FIND.dim)
        tint(Find["Filter" .. key .. "Label"], on and FIND.white or FIND.grey)
        pcall(function() Find["Filter" .. key]:SetBackgroundColor(on and CHIP_ON_BACKGROUND or NORMAL_BACKGROUND) end)
    end
end

local function drawHeadings()
    for key, sort in pairs(SORTS) do
        local active = Prefs.sort == key
        setText(Find["Head" .. sort.col .. "Sort"], active and (Prefs.desc and SORT_DOWN or SORT_UP) or "")
        tint(Find["Head" .. sort.col .. "Label"], active and FIND.white or FIND.grey)
    end
    local sort = SORTS[Prefs.sort]
    setText(Find.ListOrder, "SORTED BY " .. sort.title .. ", " .. (Prefs.desc and sort.desc or sort.asc))
    local total, hidden = #Found.all, #Found.all - Found.matching
    local count = string.format("PUBLIC GAMES   /   %d", total)
    if hidden > 0 then count = count .. string.format("   /   %d HIDDEN BY FILTERS", hidden) end
    if Found.matching > #Found.games then
        count = count .. string.format("   /   SHOWING %d OF %d", #Found.games, Found.matching)
    end
    setText(Find.ListCount, count)
end

local function drawRow(i, g)
    local row = Find["Game" .. i]
    setShown(row, g ~= nil)
    if not g then return end
    local state = STATES[stateOf(g)]
    local own = ownMap(g) ~= nil
    local chosen = Found.chosen and Found.chosen.id == g.id
    local name = Find["Game" .. i .. "Label"]
    setText(name, g.name or "?")
    tint(name, chosen and FIND.gold or FIND.white)
    setText(Find["GameNameNote" .. i], tostring(g.host or "?") .. (g.country and ("   /   " .. g.country) or ""))

    setText(Find["GameMap" .. i], mapTitle(g))
    tint(Find["GameMap" .. i], own and FIND.white or FIND.grey)
    local mapNote = Find["GameMapNote" .. i]
    setText(mapNote, own and "" or "NOT INSTALLED")
    tint(mapNote, FIND.red)

    -- The table's column is narrow: CTF there, the full name in the details.
    setText(Find["GameType" .. i], g.game_type == "ctf" and "CTF" or modeName(g.game_type))
    setText(Find["GameTypeNote" .. i], teamsMode(g.game_type) and "TEAMS" or "FREE FOR ALL")

    local players, max = g.players or 0, g.max_players or 0
    setText(Find["GamePlayers" .. i], string.format("%d / %d", players, max))
    tint(Find["GamePlayers" .. i], stateOf(g) == "full" and FIND.red or FIND.white)
    local free = math.max(0, max - players)
    setText(Find["GamePlayersNote" .. i], free > 0 and string.format("%d OPEN", free) or "NO SLOTS")

    local bars, color = pingBars(g.ping_ms)
    for b = 0, 3 do brush(Find["GamePing" .. i .. "Bar" .. b], b < bars and color or FIND.dim) end
    setText(Find["GamePing" .. i], g.ping_ms and string.format("%d ms", g.ping_ms) or "?")
    tint(Find["GamePing" .. i], g.ping_ms and FIND.white or FIND.grey)

    setText(Find["GameState" .. i], state.label)
    tint(Find["GameState" .. i], state.color)
    local stateNote = Find["GameStateNote" .. i]
    setText(stateNote, otherVersion(g) and ("VERSION " .. g.client_version) or "")
    tint(stateNote, FIND.gold)

    brush(Find["GameStripe" .. i], chosen and FIND.gold or state.color)
    pcall(function()
        row:SetBackgroundColor(chosen and ROW_CHOSEN_BACKGROUND or (i % 2 == 1 and ZEBRA_BACKGROUND or NORMAL_BACKGROUND))
    end)
    pcall(function() Find["GameCols" .. i]:SetRenderOpacity(own and 1.0 or 0.6) end)
end

--- The game JOIN would join, and why it can't.
local function joinable(g)
    if not g then return false, "JOIN" end
    if Found.joining then return false, "JOINING..." end
    if not ownMap(g) then return false, "MAP NOT INSTALLED" end
    if stateOf(g) == "full" then return false, "GAME FULL" end
    return true, stateOf(g) == "in_game" and "JOIN MATCH" or "JOIN"
end

local function showGame(g)
    if not alive(Find) then return end
    if not tableLayout() then
        -- The container from before the table: one block of details.
        setShown(Find.Join, g ~= nil)
        if not g then
            setText(Find.GameKicker, "")
            setText(Find.GameTitle, "")
            setText(Find.GameDetails, "")
            return
        end
        setText(Find.GameKicker, STATES[stateOf(g)].kicker)
        setText(Find.GameTitle, g.name or "")
        local lines = {
            "Host:  " .. tostring(g.host or "?"),
            "Map:  " .. mapTitle(g),
            "Game type:  " .. modeName(g.game_type),
            string.format("Players:  %d / %d", g.players or 0, g.max_players or 0),
        }
        if g.ping_ms then lines[#lines + 1] = string.format("Ping:  about %d ms", g.ping_ms) end
        if not ownMap(g) then
            lines[#lines + 1] = "\nYou don't have this map. Install it from the MJOLNIR launcher's Maps tab."
        end
        if otherVersion(g) then
            lines[#lines + 1] = "\nThe host runs MJOLNIR Lobby " .. g.client_version .. "; you run " .. LOBBY_VERSION .. "."
        end
        setText(Find.GameDetails, table.concat(lines, "\n"))
        return
    end

    -- JOIN is for the game the details show: the cursor leaves a row (and
    -- the details go back to the chosen game) on its way to the button.
    local ok, label = joinable(g)
    pcall(function() Find.Join:SetIsEnabled(ok) end)
    setText(Find.JoinLabel, label)
    tint(Find.JoinLabel, ok and FIND.gold or FIND.grey)
    pcall(function() Find.QuickJoin:SetIsEnabled(not Found.joining) end)

    -- With no game to show, only the title: no empty labels.
    for _, key in ipairs({ "Map", "Type", "Players", "Ping", "Region", "Version" }) do
        setShown(Find["Info" .. key], g ~= nil)
    end
    setShown(Find.Pips, g ~= nil)
    setShown(Find.InfoRule, g ~= nil)
    if not g then
        setText(Find.GameKicker, "")
        setText(Find.GameTitle, Found.loading and "LOOKING FOR GAMES" or "NO GAME SELECTED")
        setText(Find.GameHost, "")
        setText(Find.GameDetails, "")
        return
    end
    local state = stateOf(g)
    local look = STATES[state]
    setText(Find.GameKicker, look.kicker)
    tint(Find.GameKicker, look.color)
    setText(Find.GameTitle, g.name or "")
    setText(Find.GameHost, "Hosted by " .. tostring(g.host or "?"))

    setText(Find.InfoMapValue, mapTitle(g))
    tint(Find.InfoMapValue, ownMap(g) and FIND.white or FIND.red)
    setText(Find.InfoTypeValue, modeName(g.game_type) .. (teamsMode(g.game_type) and "   /   TEAMS" or "   /   FREE FOR ALL"))
    local players, max = g.players or 0, g.max_players or 0
    local free = math.max(0, max - players)
    setText(Find.InfoPlayersValue, string.format("%d / %d", players, max)
        .. (free > 0 and string.format("   /   %d OPEN", free) or "   /   FULL"))
    for p = 0, PIPS - 1 do
        setShown(Find["Pip" .. p .. "Size"], p < max)
        brush(Find["Pip" .. p], p < players and (state == "full" and FIND.red or FIND.accent) or FIND.dim)
    end
    local _, color = pingBars(g.ping_ms)
    setText(Find.InfoPingValue, g.ping_ms and string.format("About %d ms (estimated)", g.ping_ms) or "Unknown")
    tint(Find.InfoPingValue, g.ping_ms and color or FIND.grey)
    local region = g.country or "?"
    if g.colo then region = region .. "   /   " .. g.colo end
    setText(Find.InfoRegionValue, region)
    setText(Find.InfoVersionValue, "MJOLNIR Lobby " .. tostring(g.client_version or "?"))
    tint(Find.InfoVersionValue, otherVersion(g) and FIND.gold or FIND.white)

    local notes = {}
    if not ownMap(g) then
        notes[#notes + 1] = "You don't have " .. mapTitle(g) .. ". Install it from the MJOLNIR launcher's Maps tab."
    end
    if otherVersion(g) then
        notes[#notes + 1] = "The host runs MJOLNIR Lobby " .. g.client_version .. "; you run " .. LOBBY_VERSION
            .. ". Update from the launcher if the join fails."
    end
    if state == "in_game" and ownMap(g) then
        notes[#notes + 1] = "The match is under way: you join it straight away."
    end
    setText(Find.GameDetails, table.concat(notes, "\n\n"))
end

--- The details show the row under the mouse, else the chosen game.
local function shownGame()
    return Found.hovered or Found.chosen
end

local function emptyText()
    if Found.loading and #Found.all == 0 then return "Looking for games..." end
    if Found.error and #Found.all == 0 then return "Could not reach the game list.\n\n" .. Found.error end
    if #Found.all == 0 then return "No public games right now.\n\nHost one, and set it to PUBLIC GAME in the lobby." end
    return string.format("No games match your filters.\n\n%d game%s hidden: change the filters above.",
        #Found.all, #Found.all == 1 and " is" or "s are")
end

local function drawFind()
    if not alive(Find) then return end
    applyView()
    local legacy = not tableLayout()
    for i = 0, GAME_ROWS - 1 do
        local g = Found.games[i + 1]
        if legacy then
            local button = Find["Game" .. i]
            setShown(button, g ~= nil)
            if g then
                setText(Find["Game" .. i .. "Label"], string.format("%s   /   %s   /   %d/%d",
                    mapTitle(g), modeName(g.game_type), g.players or 0, g.max_players or 0))
                pcall(function()
                    button:SetBackgroundColor(Found.chosen == g and SELECTED_BACKGROUND or NORMAL_BACKGROUND)
                end)
            end
        else
            drawRow(i, g)
        end
    end
    setShown(Find.Empty, #Found.games == 0)
    setText(Find.Empty, emptyText())
    if not legacy then
        drawFilters()
        drawHeadings()
    end
    drawFindStatus()
    showGame(shownGame())
end

local function refreshFind()
    if Found.loading then return end
    Found.loading = true
    Found.lastTry = os.time()
    drawFind()
    Games.list(function(games, why)
        Found.loading = false
        if games then
            Found.all, Found.error, Found.fetchedAt = games, nil, os.time()
        else
            -- Keep showing the last list; the footer says why it is stale.
            Found.error = why
        end
        indexMaps()
        drawFind()
        if alive(Find) and not Found.focused and Found.games[1] and tableLayout() then
            Found.focused = true
            pcall(function() Find.Game0:SetFocus() end)
        end
    end)
end

--- While FIND GAMES is up (the main menu's poll): the footer's age, and the
--- automatic refresh.
function tickFind()
    if not alive(Find) then return end
    drawFindStatus()
    if not (Found.loading or Found.joining) and os.time() - (Found.lastTry or 0) >= AUTO_REFRESH then
        refreshFind()
    end
end

function openFindGames()
    Find = pushScreen(FIND_CLASS)
    if not Find then
        log("find games: could not push " .. FIND_CLASS)
        return
    end
    Found.table, Found.chosen, Found.hovered, Found.mapFilter = nil, nil, nil, nil
    Found.note, Found.statusShown, Found.focused = nil, nil, false
    loadFindPrefs()
    indexMaps()
    -- The last list at once, if there is one, while the new one loads.
    drawFind()
    refreshFind()
    pcall(function() Find.Refresh:SetFocus() end)
end

local function joinGame(g)
    if not g or Found.joining then return end
    if not ownMap(g) then
        findNote("You don't have " .. mapTitle(g) .. ". Install it from the MJOLNIR launcher's Maps tab.")
        return
    end
    if stateOf(g) == "full" then
        findNote("That game is full.")
        return
    end
    Found.joining = g
    findNote("Joining " .. tostring(g.host) .. "...")
    showGame(shownGame())
    Games.join(g, function(ok, why)
        Found.joining = nil
        if not alive(Find) then return end
        findNote(ok and ("Joining " .. tostring(g.host) .. "'s fireteam...") or ("Could not join: " .. tostring(why)))
        showGame(shownGame())
    end)
end

local function joinChosen()
    joinGame(Found.chosen)
end

--- QUICK JOIN: of the games the filters show, one that can be joined (its
--- map installed, a free slot), preferring the same MJOLNIR Lobby version,
--- a better connection, then more players.
local function quickJoin()
    local best, bestRank
    for _, g in ipairs(Found.all) do
        if (not tableLayout() or passes(g)) and ownMap(g) and stateOf(g) ~= "full" then
            local bars = pingBars(g.ping_ms)
            local rank = { otherVersion(g) and 0 or 1, bars, g.players or 0, -(g.ping_ms or 999) }
            local better = best == nil
            for k = 1, #rank do
                if better then break end
                if rank[k] ~= bestRank[k] then
                    better = rank[k] > bestRank[k]
                    break
                end
            end
            if better then best, bestRank = g, rank end
        end
    end
    if not best then
        findNote("No open game with a map you have" .. (filtering() and " matches your filters." or "."))
        return
    end
    Found.chosen, Found.hovered = best, nil
    drawFind()
    joinGame(best)
end

local function sortBy(key)
    if not SORTS[key] then return end
    if Prefs.sort == key then
        Prefs.desc = not Prefs.desc
    else
        Prefs.sort, Prefs.desc = key, SORTS[key].descFirst == true
    end
    saveFindPrefs()
    drawFind()
end

local FILTERS = {
    type = function() Prefs.type = cycle(typeChoices(), Prefs.type) end,
    map = function() Found.mapFilter = cycle((mapChoices()), Found.mapFilter) end,
    full = function() Prefs.full = not Prefs.full end,
    match = function() Prefs.match = not Prefs.match end,
    have = function() Prefs.have = not Prefs.have end,
}

local FIND_EVENTS = {
    join = joinChosen,
    quickjoin = quickJoin,
    refresh = refreshFind,
    back = function() pcall(function() Find:DeactivateWidget() end) end,
}

--- One event from FIND GAMES: "game:3", "hover:3", "sort:ping",
--- "filter:full", "join" ...
function onFindEvent(event)
    local verb, arg = event:match("^(%a+):(%w+)$")
    if verb == "sort" then return sortBy(arg) end
    if verb == "filter" then
        local apply = FILTERS[arg]
        if apply then
            apply()
            saveFindPrefs()
            drawFind()
        end
        return
    end
    if verb then
        local g = Found.games[(tonumber(arg) or -1) + 1]
        if verb == "game" and g then
            Found.chosen = g
            drawFind()
        elseif verb == "hover" and g then
            Found.hovered = g
            showGame(g)
        elseif verb == "unhover" then
            if g and Found.hovered and Found.hovered.id == g.id then Found.hovered = nil end
            showGame(shownGame())
        end
        return
    end
    local handler = FIND_EVENTS[event]
    if handler then handler() end
end

end

local LOBBY_EVENTS = {
    invite = openFriends,
    start = function()
        if not (Game.map and Game.mode and Net.isHost()) then return end
        setText(Lobby.Status, "Starting " .. titleOf(Game.map) .. " - " .. Game.mode.name .. "...")
        local ok, err = startGame(Game.map, Game.mode)
        if not ok then setText(Lobby.Status, "Could not start: " .. tostring(err)) end
    end,
    changemap = function()
        if Net.isHost() then openMapSelect() end
    end,
    gametype = function()
        if not (Game.map and Net.isHost()) then return end
        local modes = modesFor(Game.map)
        if #modes == 0 then return end
        local next_ = 1
        for i, m in ipairs(modes) do
            if Game.mode and m.id == Game.mode.id then next_ = i % #modes + 1 end
        end
        Game.mode = modes[next_]
        saveGame()
        Games.changed()
        drawLobby()
    end,
    listing = function()
        if not Net.isHost() then return end
        Games.setPublic(not Games.isPublic())
        drawLobby()
    end,
    -- MAX PLAYERS: - and + step it; the row's middle steps up, and wraps
    -- from the most to the fewest.
    maxdown = function()
        if not Net.isHost() then return end
        setMaxPlayers(Game.maxPlayers - 1, #rosterPlayers())
        drawLobby()
    end,
    maxup = function()
        if not Net.isHost() then return end
        setMaxPlayers(Game.maxPlayers + 1, #rosterPlayers())
        drawLobby()
    end,
    maxplayers = function()
        if not Net.isHost() then return end
        local present = #rosterPlayers()
        setMaxPlayers(Game.maxPlayers >= FIRETEAM_SIZE and minPlayers(present) or Game.maxPlayers + 1, present)
        drawLobby()
    end,
    findgames = function()
        if hasFindGames() then openFindGames() end
    end,
    back = function()
        -- A fireteam client's BACK: the game's own menus until the next vote.
        if not Net.isHost() then clientLobby.dismissed = true end
        pcall(function() Lobby:DeactivateWidget() end)
    end,
}

local SELECT_EVENTS = {
    select = function()
        if Pick.map and Pick.mode then
            Game.map, Game.mode = Pick.map, Pick.mode
            saveGame()
            Games.changed()
        end
        pcall(function() Select:DeactivateWidget() end)
        drawLobby()
    end,
    back = function() pcall(function() Select:DeactivateWidget() end) end,
}

--- One event from a screen: "start", "map:3", "hover:3", "mode:1" ...
local function onScreenEvent(isLobby, event)
    if isLobby == "find" then return onFindEvent(event) end
    local verb, index = event:match("^(%a+):(%d+)$")
    if verb then
        local i = tonumber(index) + 1
        if verb == "map" then
            pickMap(installedMaps()[i])
        elseif verb == "hover" then
            showDetails(installedMaps()[i])
        elseif verb == "mode" and Pick.map then
            local mode = modesFor(Pick.map)[i]
            if mode then
                Pick.mode = mode
                showDetails(Pick.map)
            end
        end
        return
    end
    local handler = (isLobby and LOBBY_EVENTS or SELECT_EVENTS)[event]
    if handler then handler() end
end

--- Hook each of our screens' MJ_Event, once per class; true when all are in.
--- A class whose hook failed is tried again on the next call (adoptLobby,
--- the main menu's poll). Without its hook a screen still shows, since the
--- main menu pushes the lobby natively, but every button on it does nothing
--- (playtest, 2026-10-03).
local function hookScreenEvents()
    local specs = { { LOBBY_CLASS, true }, { SELECT_CLASS, false } }
    if hasFindGames() then specs[#specs + 1] = { FIND_CLASS, "find" } end
    local all = true
    for _, spec in ipairs(specs) do
        if not screenEvents.hooked[spec[1]] then
            local ok, hookErr = pcall(RegisterHook, spec[1] .. ":MJ_Event", function(self, name)
                local okE, event = pcall(function() return name:get():ToString() end)
                if not okE then return end
                -- The main menu pushes the lobby itself: the screen that
                -- sent the event is the lobby on screen.
                if spec[2] == true then
                    local okS, screen = pcall(function() return self:get() end)
                    if okS and UI.valid(screen) then Lobby = screen end
                end
                -- Off the click: pushing and popping screens inside the
                -- button's own handler is not safe.
                ExecuteInGameThread(function()
                    local okH, err = pcall(onScreenEvent, spec[2], event)
                    if not okH then log("screen event " .. event .. ": " .. tostring(err)) end
                end)
            end)
            -- Logged once per class, not on every retry.
            if not ok and screenEvents.hooked[spec[1]] == nil then
                log("cannot hook " .. spec[1] .. ":MJ_Event: " .. tostring(hookErr))
            end
            screenEvents.hooked[spec[1]] = ok
            all = all and ok
        end
    end
    return all
end

--- Our screens' classes loaded and their events hooked.
local function ourScreens()
    return loadClass(LOBBY_CLASS) ~= nil and loadClass(SELECT_CLASS) ~= nil and hookScreenEvents()
end

--- Fill a lobby that is on the stack: one openLobby pushed, or the one the
--- main menu's own MULTIPLAYER button pushed.
local function adoptLobby(screen)
    if not UI.valid(screen) then return end
    Lobby = screen
    hookScreenEvents()
    setText(Lobby.Watermark, BuildLine.text(MODS_DIR))
    -- The cooked footer warns, in gold, that the mods are not running; the
    -- status lines below replace it, in the footer's usual grey.
    pcall(function()
        Lobby.Status:SetColorAndOpacity({ SpecifiedColor = { R = 0.46, G = 0.61, B = 0.70, A = 1 }, ColorUseRule = 0 })
    end)
    local host = Net.isHost()
    if host then
        if not (Game.map and Game.mode) then Game.map, Game.mode = defaultGame() end
        setText(Lobby.Status, "INVITE FRIENDS TO YOUR FIRETEAM   /   START GAME WHEN EVERYONE IS READY")
    else
        -- A fireteam client: the host's map and game type arrive as
        -- "lobby" messages (After a match, below).
        setText(Lobby.Status, "THE HOST PICKS THE MAP AND GAME TYPE   /   THE GAME STARTS WHEN THE HOST IS READY")
    end
    drawLobby()
    pcall(function() (host and Lobby.Start or Lobby.Invite):SetFocus() end)
end

--- MULTIPLAYER from script (the console command, the injected fallback
--- button): our lobby, or the campaign-menu screens without the UI container.
local function openLobby()
    if not ourScreens() then
        log("MJOLNIR UI not installed (pakchunk984-MJOLNIRUI): the campaign-menu screens instead")
        rootScreen()
        return
    end
    local screen = pushScreen(LOBBY_CLASS)
    if not screen then
        log("lobby: could not push " .. LOBBY_CLASS)
        rootScreen()
        return
    end
    adoptLobby(screen)
end

--- The main menu's own MULTIPLAYER button (pakchunk985-MJOLNIRMENU) pushes
--- the lobby without us: fill each new lobby as it is built. The widget is
--- constructed before its tree is, so the fill waits a moment.
---
--- Runs first at startup and again from the main menu's poll until it is
--- registered: a lobby nobody adopts shows, but its buttons do nothing. A
--- watch that comes late adopts a lobby that is already up.
local function watchNewLobbies()
    if screenEvents.watching then return true end
    if screenEvents.noUI then return false end
    if not loadClass(LOBBY_CLASS) then
        screenEvents.noUI = true
        return false
    end
    ourScreens()
    local ok, err = pcall(function()
        NotifyOnNewObject(LOBBY_CLASS, function(screen)
            local okN, name = pcall(function() return screen:GetFName():ToString() end)
            if not okN or name:find("^Default__") then return end
            ExecuteInGameThreadWithDelay(100, function() adoptLobby(screen) end)
        end)
    end)
    if not ok then
        if screenEvents.watching == false then log("cannot watch for new lobbies: " .. tostring(err)) end
        screenEvents.watching = nil
        return false
    end
    if screenEvents.watching == nil then
        local up = UI.liveWidget("WBP_MJOLNIRLobby_C", alive)
        if up then adoptLobby(up) end
    end
    screenEvents.watching = true
    return true
end

--- Keep the lobby's player list current while it is up.
local function refreshLobby()
    if alive(Lobby) then drawLobby() end
end

-------------------------------------------------------------------------------
-- The main-menu entry
-------------------------------------------------------------------------------
--
-- MULTIPLAYER is the main menu's own button when the runtime pack's
-- pakchunk985-MJOLNIRMENU is installed: `mjolnir ue menu-button` adds it to
-- WBP_MainMenu after the (hidden) Remix button, with the menu's styling, and
-- its click pushes WBP_MJOLNIRLobby itself (docs/multiplayer_menu.md).
-- Nothing here has to run for it to appear; watchNewLobbies fills the lobby.
--
-- Without that container the menu has no such button, and the old route
-- takes over: a button of the main menu's kind made from Lua and put in
-- Remix's slot, its click bound through the native half (Scripts/ui.lua).

local MAIN_MENU = "/Game/UI/Frontend/MainMenu/Widgets/WBP_MainMenu.WBP_MainMenu_C"
local entry = { menu = nil, button = nil }
local nativeSeen = nil

--- The main menu on screen. FindFirstOf could hand back the previous
--- frontend's menu, whose Slate widgets are gone (UI.liveWidget).
local function liveMainMenu()
    return UI.liveWidget("WBP_MainMenu_C", function(w) return w:IsVisible() end)
end

--- The menu's own MULTIPLAYER button (pakchunk985-MJOLNIRMENU).
local function nativeEntry(menu)
    local ok, button = pcall(function() return menu.MultiplayerButton end)
    return ok and UI.valid(button)
end

--- The fallback: MULTIPLAYER in the slot of the hidden Remix button.
local function injectMainMenu()
    local menu = liveMainMenu()
    if not UI.valid(menu) or nativeEntry(menu) then return end
    if entry.menu == UI.addressOf(menu) and entry.button and UI.valid(entry.button.widget) then
        UI.label(entry.button, "MULTIPLAYER")
        return
    end
    local container = menu.MainButtonContainer
    local index
    local remix = UI.addressOf(menu.RemixButton)
    local count = 0
    pcall(function() count = container:GetChildrenCount() end)
    for i = 0, count - 1 do
        local ok, child = pcall(function() return container:GetChildAt(i) end)
        if ok and UI.addressOf(child) == remix then index = i end
    end
    local button, err = UI.button(menu, "MULTIPLAYER", openLobby)
    if not button then
        log("main menu entry: " .. tostring(err))
        return
    end
    if index then
        container:ReplaceButtonContainerChildAt(index, button.widget)
    else
        container:AddChildToButtonContainer(button.widget)
    end
    entry.menu, entry.button = UI.addressOf(menu), button
    ExecuteInGameThreadWithDelay(60, function()
        UI.label(button, "MULTIPLAYER")
        pcall(function() button.widget:SetVisibility(0) end)
    end)
    log("MULTIPLAYER added to the main menu (injected: pakchunk985-MJOLNIRMENU is not installed)")
end

-------------------------------------------------------------------------------
-- After a match: the post-game screen and the vote
-------------------------------------------------------------------------------
--
-- At a match's end MJOLNIRHud writes the final standings (its
-- last_match.txt) and the host travels back to the frontend seamlessly, so
-- the fireteam arrives still connected (docs/multiplayer_postgame.md). The
-- host then opens WBP_MJOLNIRPostGame and starts a vote on the next game:
-- the same game again and up to three others. Every member votes on its own
-- copy of the screen, through Scripts/net.lua:
--
--   host -> clients  vote|<id>|<seconds left>|<options>|<counts>|<chosen>,
--                    the whole vote, each second; cancel|<id>;
--                    lobby|<code>|<mode>, the lobby's map and game type
--   client -> host   ballot|<id>|<option>
--
-- When the time runs out, or the host presses START NOW, the host starts the
-- leading game exactly as START GAME would, and the fireteam follows it into
-- the map. LOBBY (or Back) ends the vote and opens the lobby to pick by hand.
-- Each machine shows its own standings: every one counted the same
-- incidents.

local POSTGAME_CLASS = UI_ROOT .. "WBP_MJOLNIRPostGame.WBP_MJOLNIRPostGame_C"
local RESULTS = (MOD_DIR:match("^(.*)\\[^\\]*$") or MOD_DIR) .. "\\MJOLNIRHud\\last_match.txt"
local VOTE_OPTIONS = 4
local RESULT_ROWS = 18
local VOTE_SECONDS = 20
local RESULTS_FRESH = 180   -- seconds; older standings are a previous session's
local GOLD = { R = 1.0, G = 0.80, B = 0.35, A = 1 }
local TEAM_TINT = {
    Red = { R = 1, G = 0.32, B = 0.28, A = 1 },
    Blue = { R = 0.3, G = 0.65, B = 1, A = 1 },
    Unassigned = { R = 0.5, G = 0.66, B = 0.74, A = 1 },
}

--- { screen, results, vote = { id, options, ballots, counts, mine, chosen,
--- left, endsAt, host }, dismissed = vote id }, or nil.
local Post = nil
local seenResults = nil
local postHooked = false
local nextVoteBroadcast = 0

local function inFrontend()
    local ok, name = pcall(function() return UI.playerController():GetWorld():GetFName():ToString() end)
    return ok and name == "Frontend"
end

local function localName()
    local ok, name = pcall(function() return UI.playerController().PlayerState:GetPlayerName():ToString() end)
    return ok and name or nil
end

local function mapByCode(code)
    for _, map in ipairs(installedMaps()) do
        if map.code == code then return map end
    end
    return nil
end

local function modeById(map, id)
    for _, mode in ipairs(map and modesFor(map) or {}) do
        if mode.id == id then return mode end
    end
    return nil
end

--- MJOLNIRHud's standings: { code, variant, title, modeTitle, winner,
--- endedAt, teams = { {team, total} }, players = { {name, score, kills,
--- deaths, team, you} } } in standing order (scoreboard.lua, Board.results).
local function readResults()
    local raw = readFile(RESULTS)
    if not raw then return nil end
    local r = { teams = {}, players = {} }
    for line in raw:gmatch("[^\r\n]+") do
        local f = {}
        for value in (line .. "\t"):gmatch("([^\t]*)\t") do f[#f + 1] = value end
        if f[1] == "match" then
            r.code, r.variant, r.title, r.modeTitle, r.winner = f[2], f[3], f[4], f[5], f[6]
            r.endedAt = tonumber(f[7])
        elseif f[1] == "team" then
            r.teams[#r.teams + 1] = { team = f[2], total = tonumber(f[3]) or 0 }
        elseif f[1] == "player" then
            r.players[#r.players + 1] = { name = f[2], score = f[3], kills = f[4], deaths = f[5],
                team = f[6] ~= "-" and f[6] or nil, you = f[7] == "1" }
        end
    end
    return r.code and r or nil
end

--- The vote's options: the game just played, then other maps in a random
--- order (with the same game type where the map has it), then the played
--- map's other game types.
local function voteOptions(results)
    local options, seen = {}, {}
    local function add(map, mode, again)
        if not (map and mode) or #options >= VOTE_OPTIONS then return end
        local key = map.code .. ":" .. mode.id
        if seen[key] then return end
        seen[key] = true
        options[#options + 1] = { code = map.code, mode = mode.id, again = again }
    end
    local last = results and mapByCode(results.code)
    add(last, last and modeById(last, results.variant), true)
    local others = {}
    for _, map in ipairs(installedMaps()) do
        if not last or map.code ~= last.code then others[#others + 1] = map end
    end
    for i = #others, 2, -1 do
        local j = math.random(i)
        others[i], others[j] = others[j], others[i]
    end
    for _, map in ipairs(others) do
        add(map, modeById(map, results and results.variant) or modesFor(map)[1])
    end
    for _, mode in ipairs(last and modesFor(last) or {}) do add(last, mode) end
    return options
end

local function encodeOptions(options)
    local parts = {}
    for _, o in ipairs(options) do parts[#parts + 1] = o.code .. ":" .. o.mode .. ":" .. (o.again and "1" or "0") end
    return table.concat(parts, ";")
end

local function decodeOptions(text)
    local options = {}
    for code, mode, again in (text or ""):gmatch("([%w_]+):([%w_]+):([01])") do
        options[#options + 1] = { code = code, mode = mode, again = again == "1" }
    end
    return options
end

local function optionLabel(o)
    local map = mapByCode(o.code)
    local mode = modeById(map, o.mode)
    local label = (map and titleOf(map) or o.code) .. "  /  " .. (mode and mode.name or string.upper(o.mode))
    return o.again and ("AGAIN  /  " .. label) or label
end

local function counts(v)
    if v.counts then return v.counts end
    local n = {}
    for i = 1, #v.options do n[i] = 0 end
    for _, choice in pairs(v.ballots or {}) do
        if n[choice] then n[choice] = n[choice] + 1 end
    end
    return n
end

local function broadcastVote()
    local v = Post and Post.vote
    if not (v and v.host) then return end
    Net.toClients("vote", v.id, math.max(0, math.ceil(v.left or 0)), encodeOptions(v.options),
        table.concat(counts(v), ","), v.chosen or "")
end

local function drawResults()
    local s, r = Post.screen, Post.results
    if not r then
        setText(s.Winner, "MATCH OVER")
        setText(s.Summary, "")
        for i = 0, RESULT_ROWS - 1 do setShown(s["Row" .. i], false) end
        return
    end
    setText(s.Winner, r.winner or "")
    local summary = (r.modeTitle or "") .. "   /   " .. string.upper(r.title or r.code or "")
    if #r.teams > 0 then
        local totals = {}
        for _, t in ipairs(r.teams) do totals[#totals + 1] = string.upper(t.team) .. " " .. tostring(t.total) end
        summary = summary .. "   /   " .. table.concat(totals, "  -  ")
    end
    setText(s.Summary, summary)
    setText(s.ScoreH, r.variant == "ctf" and "CAPTURES" or "SCORE")
    local rows = {}
    if #r.teams > 0 then
        local groups = {}
        for _, t in ipairs(r.teams) do groups[#groups + 1] = { team = t.team, total = t.total } end
        groups[#groups + 1] = { team = "Unassigned" }
        for _, g in ipairs(groups) do
            local members = {}
            for _, p in ipairs(r.players) do
                if (p.team or "Unassigned") == g.team then members[#members + 1] = p end
            end
            if g.team ~= "Unassigned" or #members > 0 then
                rows[#rows + 1] = { team = g.team, total = g.total, count = #members }
                for _, p in ipairs(members) do rows[#rows + 1] = { player = p, team = g.team } end
            end
        end
    else
        for _, p in ipairs(r.players) do rows[#rows + 1] = { player = p } end
    end
    for i = 0, RESULT_ROWS - 1 do
        local item, row = rows[i + 1], s["Row" .. i]
        setShown(row, item ~= nil)
        if item then
            local p = item.player
            local tint = item.team and item.team ~= "Unassigned" and TEAM_TINT[item.team] or nil
            local heading = (item.team == "Unassigned" and "AWAITING ASSIGNMENT" or
                string.upper(item.team or "") .. " TEAM") .. "  /  " .. tostring(item.count)
            setText(s["Name" .. i], p and p.name or heading)
            setText(s["Marker" .. i], p and p.you and "YOU" or "")
            setText(s["Score" .. i], p and p.score or (item.total and tostring(item.total) or ""))
            setText(s["Kills" .. i], p and p.kills or "")
            setText(s["Deaths" .. i], p and p.deaths or "")
            local color
            if not p then
                local t = TEAM_TINT[item.team] or TEAM_TINT.Unassigned
                color = { R = t.R, G = t.G, B = t.B, A = 0.24 }
            elseif tint then
                color = { R = tint.R, G = tint.G, B = tint.B, A = p.you and 0.20 or 0.06 }
            elseif p.you then
                color = { R = 1.0, G = 0.85, B = 0.35, A = 0.18 }
            else
                color = { R = 1, G = 1, B = 1, A = (i % 2 == 0) and 0.06 or 0.02 }
            end
            pcall(function()
                row:SetBrushColor(color)
                row.Slot:SetPadding({ Left = 0, Top = p and 2 or 12, Right = 0, Bottom = 0 })
                s["Stripe" .. i]:SetBrushColor(tint or (not p and TEAM_TINT[item.team]) or
                    (p and p.you and GOLD) or { R = 1, G = 1, B = 1, A = 0.06 })
                s["Name" .. i]:SetColorAndOpacity({ SpecifiedColor = (not p and (TEAM_TINT[item.team] or WHITE)) or WHITE,
                    ColorUseRule = 0 })
            end)
        end
    end
end

local function drawVote()
    local s, v = Post.screen, Post.vote
    local host = Net.isHost()
    setShown(s.Start, host)
    setShown(s.Lobby, host)
    if not v then
        setText(s.VoteTimer, host and "NO OTHER GAMES INSTALLED" or "WAITING FOR THE HOST")
        for i = 0, VOTE_OPTIONS - 1 do setShown(s["VoteRow" .. i], false) end
        setText(s.VoteHint, "")
        return
    end
    local n = counts(v)
    local voted = 0
    for i = 0, VOTE_OPTIONS - 1 do
        local o = v.options[i + 1]
        setShown(s["VoteRow" .. i], o ~= nil)
        if o then
            voted = voted + (n[i + 1] or 0)
            setText(s["Vote" .. i .. "Label"], optionLabel(o))
            setText(s["VoteCount" .. i], (n[i + 1] or 0) > 0 and tostring(n[i + 1]) or "")
            local mine, chosen = v.mine == i + 1, v.chosen == i + 1
            pcall(function()
                s["Vote" .. i]:SetBackgroundColor((mine or chosen) and SELECTED_BACKGROUND or NORMAL_BACKGROUND)
                s["Vote" .. i .. "Label"]:SetColorAndOpacity({
                    SpecifiedColor = chosen and GOLD or (mine and ACCENT or WHITE), ColorUseRule = 0 })
                s["Vote" .. i]:SetIsEnabled(v.chosen == nil)
            end)
        end
    end
    if v.chosen and v.options[v.chosen] then
        setText(s.VoteTimer, "NEXT  /  " .. optionLabel(v.options[v.chosen]))
    else
        setText(s.VoteTimer, string.format("VOTING ENDS IN %d", math.max(0, math.ceil(v.left or 0))))
    end
    setText(s.VoteHint, host and
        "Everyone in the fireteam votes. START NOW plays the leading game; LOBBY ends the vote so you can pick by hand." or
        "Vote for the next game. The host starts it when voting ends.")
    pcall(function()
        s.Start:SetIsEnabled(v.chosen == nil)
        s.Lobby:SetIsEnabled(v.chosen == nil)
    end)
    local players = math.max(#rosterPlayers(), voted)
    setText(s.Status, v.chosen and "STARTING THE NEXT GAME   /   THE FIRETEAM TRAVELS TOGETHER" or
        string.format("%d OF %d VOTED", voted, players))
end

local function drawPostGame()
    if not (Post and alive(Post.screen)) then return end
    drawResults()
    drawVote()
end

local function hookPostGame()
    if postHooked then return true end
    postHooked = pcall(function()
        RegisterHook(POSTGAME_CLASS .. ":MJ_Event", function(_, name)
            local okE, event = pcall(function() return name:get():ToString() end)
            if not okE then return end
            ExecuteInGameThread(function()
                local okH, err = pcall(function()
                    local v = Post and Post.vote
                    local index = tonumber(event:match("^vote:(%d+)$") or "")
                    if index and v and not v.chosen and v.options[index + 1] then
                        v.mine = index + 1
                        Net.toHost("ballot", v.id, index + 1)
                        drawPostGame()
                    elseif event == "start" and v and v.host then
                        v.left = 0
                        v.endsAt = os.clock()
                    elseif event == "lobby" and Net.isHost() then
                        Post.cancel = true
                    end
                end)
                if not okH then log("post-game event " .. event .. ": " .. tostring(err)) end
            end)
        end)
    end)
    return postHooked
end

local function openPostGame()
    if alive(Post.screen) then return Post.screen end
    -- The hook needs the class loaded. The host loads it before its own
    -- screen; a fireteam client's first sight of it is this vote.
    if not loadClass(POSTGAME_CLASS) then
        log("post-game: " .. POSTGAME_CLASS .. " is not installed (an older pakchunk984-MJOLNIRUI)")
        return nil
    end
    if not hookPostGame() then
        log("post-game: could not hook the screen's events")
        return nil
    end
    Post.screen = pushScreen(POSTGAME_CLASS)
    if not Post.screen then
        log("post-game: could not push " .. POSTGAME_CLASS)
        return nil
    end
    pcall(function() Post.screen.Vote0:SetFocus() end)
    drawPostGame()
    return Post.screen
end

local function closePostGame()
    if Post and alive(Post.screen) then
        pcall(function() Post.screen:DeactivateWidget() end)
    end
end

--- The host: the vote's end. The most votes wins, the earlier option on a
--- tie; with no votes at all the rotation moves on to the second option.
local function decide()
    local v = Post.vote
    if v.chosen then return end
    local pick, best = nil, 0
    for i, c in ipairs(counts(v)) do
        if c > best then pick, best = i, c end
    end
    pick = pick or (v.options[2] and 2 or 1)
    v.chosen = pick
    broadcastVote()
    drawPostGame()
    local o = v.options[pick]
    local map = mapByCode(o.code)
    local mode = modeById(map, o.mode)
    if not (map and mode) then
        log("post-game: " .. tostring(o.code) .. " / " .. tostring(o.mode) .. " is not installed")
        return
    end
    Game.map, Game.mode = map, mode
    saveGame()
    log(string.format("post-game: the fireteam voted for %s (%s)", map.code, mode.id))
    -- A moment for the outcome to reach every screen before the countdown.
    ExecuteInGameThreadWithDelay(1500, function()
        local ok, err = startGame(map, mode)
        if not ok and Post and alive(Post.screen) then setText(Post.screen.Status, "Could not start: " .. tostring(err)) end
    end)
end

--- The host, back from a match with fresh standings: the post-game screen
--- and a new vote.
local function hostPostGame()
    if Post or not inFrontend() or not Net.isHost() then return end
    local r = readResults()
    if not r or r.endedAt == seenResults or os.time() - (r.endedAt or 0) > RESULTS_FRESH then return end
    if not UI.valid(liveMainMenu()) then return end
    seenResults = r.endedAt
    if not loadClass(POSTGAME_CLASS) then
        log("post-game screen not installed (an older pakchunk984-MJOLNIRUI): the lobby instead")
        openLobby()
        return
    end
    Post = { results = r }
    local options = voteOptions(r)
    if #options > 0 then
        Post.vote = { id = tostring(r.endedAt) .. "-" .. tostring(math.random(1000, 9999)), options = options,
            ballots = {}, host = true, left = VOTE_SECONDS, endsAt = os.clock() + VOTE_SECONDS }
    end
    if not openPostGame() then
        Post = nil
        openLobby()
        return
    end
    broadcastVote()
    log(string.format("post-game: %s, %d option(s) to vote on", tostring(r.winner), #options))
end

--- Every 250 ms: the host's vote clock and broadcasts, and the end of the
--- post-game when its screen goes away or the world changes.
local function postTick()
    if not Post then return end
    if not inFrontend() then
        Post = nil
        return
    end
    local v = Post.vote
    if v and v.host then
        if Post.cancel or (not alive(Post.screen) and not v.chosen) then
            -- LOBBY, or Back: no vote; the lobby to pick by hand.
            Net.toClients("cancel", v.id)
            closePostGame()
            Post = { dismissed = v.id }
            openLobby()
            return
        end
        if not v.chosen then
            v.left = v.endsAt - os.clock()
            if v.left <= 0 then decide() end
        end
        if os.clock() >= nextVoteBroadcast then
            nextVoteBroadcast = os.clock() + 1
            broadcastVote()
        end
    elseif v and not v.chosen and not alive(Post.screen) and os.clock() - (Post.pushedAt or -10) >= 2 then
        -- A client: the game pushes its own CLIENT LOBBY over ours on the
        -- way in, so the vote goes back on top until it ends.
        Post.pushedAt = os.clock()
        Post.screen = nil
        if openPostGame() then log("post-game: the vote is on screen") end
    end
    drawPostGame()
end

Net.on("ballot", function(f, sender)
    local v = Post and Post.vote
    local choice = tonumber(f[2] or "")
    if not (v and v.host and v.id == f[1] and not v.chosen and choice and v.options[choice]) then return end
    v.ballots[sender or "?"] = choice
    if sender == localName() then v.mine = choice end
    broadcastVote()
    drawPostGame()
end)

Net.on("vote", function(f)
    if Net.isHost() or not inFrontend() then return end
    local id = f[1]
    if Post and Post.dismissed == id then return end
    Post = Post or {}
    if not (Post.vote and Post.vote.id == id) then
        local r = readResults()
        Post.results = r and os.time() - (r.endedAt or 0) <= RESULTS_FRESH and r or nil
        Post.vote = { id = id }
    end
    local v = Post.vote
    v.left = tonumber(f[2] or "") or 0
    v.options = decodeOptions(f[3])
    local n = {}
    for c in (f[4] or ""):gmatch("(%d+)") do n[#n + 1] = tonumber(c) end
    v.counts = n
    v.chosen = tonumber(f[5] or "")
    if not alive(Post.screen) and os.clock() - (Post.pushedAt or -10) >= 2 then
        Post.pushedAt = os.clock()
        if openPostGame() then log("post-game: the vote is on screen") end
    end
    drawPostGame()
end)

Net.on("cancel", function(f)
    if Net.isHost() or not (Post and Post.vote and Post.vote.id == f[1]) then return end
    closePostGame()
    Post = { dismissed = f[1] }
    clientLobby.dismissed = false
end)

--- A fireteam client, while the host is in our lobby: our lobby in place of
--- the game's CLIENT LOBBY, showing the host's map and game type.
Net.on("lobby", function(f)
    if Net.isHost() or not inFrontend() then return end
    local map = mapByCode(f[1]) or { code = f[1], title = f[1], description = "This map is not installed on this PC." }
    local mode = modeById(map, f[2])
    if not mode then
        for _, m in ipairs(MODES) do
            if m.id == f[2] then mode = m end
        end
    end
    Game.map, Game.mode = map, mode
    if Post and alive(Post.screen) then return end
    if alive(Lobby) then
        drawLobby()
        return
    end
    -- The game pushes its own CLIENT LOBBY over ours (on joining, and when
    -- the host's lobby data changes), so ours goes back on top; only our
    -- BACK button leaves it. A second or two between pushes.
    if clientLobby.dismissed or os.clock() - (clientLobby.at or -10) < 2 then return end
    clientLobby.at = os.clock()
    if not ourScreens() then
        log("client lobby: our screens are not installed")
        clientLobby.dismissed = true
        return
    end
    local screen = pushScreen(LOBBY_CLASS)
    if screen then
        adoptLobby(screen)
        log("client lobby: " .. tostring(f[1]) .. " / " .. tostring(f[2]) .. " from the host")
    else
        log("client lobby: could not push " .. LOBBY_CLASS)
        clientLobby.dismissed = true
    end
end)

--- The host: the lobby's map and game type to the fireteam, while the lobby
--- is up.
local function broadcastLobby()
    if not (alive(Lobby) and Game.map and Game.mode and inFrontend() and Net.isHost()) then return end
    Net.toClients("lobby", Game.map.code, Game.mode.id)
end

local function watchPostGame()
    local function poll()
        local ok, err = pcall(postTick)
        if not ok then log("post-game: " .. tostring(err)) end
        ExecuteInGameThreadWithDelay(250, poll)
    end
    ExecuteInGameThreadWithDelay(250, poll)
end

-------------------------------------------------------------------------------
-- The fireteam cap
-------------------------------------------------------------------------------
--
-- The game's co-op fireteam stops at four, in layers
-- (docs/fireteam_join_and_cap.md). The native half (native/lobby,
-- mjolnir_fireteam_open) raises the PlayFab lobby's size, the PlayFab Party
-- network's user and device limits and the Steam presence session's
-- connections as the host creates them. Unreal's GameSession is rebuilt at
-- MaxPlayers 4 with every level, so the poll holds it up, and squadpanel.lua
-- lists the players past four on the game's FIRETEAM panel. A match freezes
-- with more than two local players on one PC, so the extra players have to
-- be separate machines. The host's MAX PLAYERS (setMaxPlayers) narrows the
-- lobby and the GameSession below FIRETEAM_SIZE.

local function openFireteam()
    local native = MOD_DIR .. "\\native\\"
    local request = io.open(native .. "fireteam_request.txt", "w")
    if request then
        request:write(tostring(FIRETEAM_SIZE))
        request:close()
    end
    local open = package and package.loadlib and package.loadlib(native .. "mjolnir_lobby.dll", "mjolnir_fireteam_open")
    if not open then
        log("fireteam: the native half is not installed; the fireteam stays at four")
        return
    end
    open()
    log("fireteam: up to " .. FIRETEAM_SIZE .. " players (native\\fireteam.log has the details)")
    -- The last MAX PLAYERS, in place before the game creates its lobby.
    local saved = tonumber((readFile(MAX_PLAYERS_FILE) or ""):match("%d+") or "")
    if saved then Game.maxPlayers = math.max(MIN_PLAYERS, math.min(FIRETEAM_SIZE, saved)) end
    log("max players: " .. Game.maxPlayers .. " (" .. applyMaxPlayers() .. ")")
end

--- The session of the world's game mode, which exists only on the host (a
--- client has none to hold), held at the host's MAX PLAYERS.
local function holdFireteamSize()
    local session = UI.playerController():GetWorld().AuthorityGameMode.GameSession
    if session:IsValid() and session.MaxPlayers ~= Game.maxPlayers then session.MaxPlayers = Game.maxPlayers end
end

--- The FIRETEAM panel's size: the host's MAX PLAYERS; a client does not know
--- its host's, so it shows the ceiling.
local function fireteamSize()
    return Net.isHost() and Game.maxPlayers or FIRETEAM_SIZE
end

--- The fireteam as the squad panel sees it, and the world, logged whenever
--- either changes: the record of what a match end does to a fireteam
--- (docs/two_pc_test.md, Phase 3).
local lastFireteam = nil
local function watchFireteam()
    local vm = FindFirstOf("MeteoriteSquadLobbyViewModel")
    local members = {}
    local count = -1
    if UI.valid(vm) then
        pcall(function() count = vm:GetNumSquadMembers() end)
        pcall(function()
            vm.SquadMembers:ForEach(function(_, e)
                local item = e:get()
                if item.FireteamRowType == 0 then
                    members[#members + 1] = item.EntryName:ToString()
                end
            end)
        end)
    end
    local world = "?"
    pcall(function() world = UI.playerController():GetWorld():GetFName():ToString() end)
    local state = string.format("%s | fireteam %d [%s]", world, count, table.concat(members, ", "))
    if state ~= lastFireteam then
        lastFireteam = state
        log("fireteam: " .. state)
    end
end

local menuHook = false

--- Keeps the lobby's player list current, and runs the fallback whenever a
--- main menu is up without its own MULTIPLAYER button. The poll reschedules
--- itself on the game thread: LoopAsync handing work to ExecuteInGameThread
--- can deadlock on the game thread's lock (it froze the game in
--- MJOLNIRLevelLoader, 2026-10-01).
---
--- Only the fireteam size is held during a match. The rest is the frontend's,
--- and its widget and view-model lookups each walk every object in the game:
--- run in a match, seven walks of ~20 ms each froze a converted map for
--- 140 ms every 1.5 s (2026-10-02).
local function watchMainMenu()
    local function poll()
        local ok, err = pcall(function()
            pcall(holdFireteamSize)
            if not inFrontend() then return end
            -- Retried until they are in: without them the lobby shows but
            -- does nothing. Both return at once when already done.
            pcall(watchNewLobbies)
            if Lobby then pcall(hookScreenEvents) end
            refreshLobby()
            pcall(tickFind)
            pcall(watchFireteam)
            SquadPanel.hook(fireteamSize)
            pcall(SquadPanel.refresh, fireteamSize())
            pcall(hostPostGame)
            pcall(broadcastLobby)
            local menu = liveMainMenu()
            if not UI.valid(menu) then return end
            if nativeEntry(menu) then
                if nativeSeen ~= UI.addressOf(menu) then
                    nativeSeen = UI.addressOf(menu)
                    log("MULTIPLAYER is on the main menu (its own button)")
                end
                return
            end
            if not menuHook then
                menuHook = pcall(function()
                    RegisterHook(MAIN_MENU .. ":BP_OnActivated", function()
                        ExecuteInGameThreadWithDelay(60, injectMainMenu)
                    end)
                end)
            end
            if entry.menu ~= UI.addressOf(menu) or not (entry.button and UI.valid(entry.button.widget)) then
                injectMainMenu()
            end
        end)
        if not ok then log("main menu watch: " .. tostring(err)) end
        ExecuteInGameThreadWithDelay(1500, poll)
    end
    ExecuteInGameThreadWithDelay(1500, poll)
end

-------------------------------------------------------------------------------
-- Host menu (HOST MENU on the pause menu, or `mjolnir_host` at the console):
-- during a match the host can end it, take the fireteam back to the lobby,
-- and kick or ban players.
-------------------------------------------------------------------------------
--
-- END GAME ends the match through the game engine (native
-- mjolnir_sim_end_game), so the results and the post-game vote follow as
-- after any match. RETURN TO LOBBY travels the fireteam back to the frontend
-- (the travel MJOLNIRHud makes after a match) and opens the lobby there.
-- KICK sends the player back to their main menu (the engine's own client RPC
-- ClientReturnToMainMenuWithTextReason, so their game leaves the session
-- itself). BAN kicks and remembers the name in bans.json; a banned name that
-- joins again is sent back as soon as it appears among the players.

local BANS_FILE = MOD_DIR .. "\\bans.json"

--- Call one of native\mjolnir_lobby.dll's exports; true when it ran.
local function native_(name)
    local fn = package and package.loadlib and package.loadlib(MOD_DIR .. "\\native\\mjolnir_lobby.dll", name)
    if not fn then return false end
    return (pcall(fn))
end
local HOST_TRAVEL = "servertravel /Game/Levels/UI/Frontend/Frontend"
local Bans = nil            -- { [lowercase name] = { name, at } }
local lobbyOnReturn = false -- RETURN TO LOBBY: open the lobby once the frontend is up
local hostMenuOpen = nil    -- the HOST MENU screen while it is up
local hostLayout = nil      -- the UI layout the pause menu is on (a match runs two)

local function loadBans()
    if Bans then return Bans end
    Bans = {}
    local raw = readFile(BANS_FILE)
    local ok, t = pcall(function() return raw and Json.decode(raw) end)
    if ok and type(t) == "table" then
        for _, b in ipairs(t) do
            if type(b) == "table" and type(b.name) == "string" then
                Bans[string.lower(b.name)] = { name = b.name, at = b.at }
            end
        end
    end
    return Bans
end

local function saveBans()
    local list = {}
    for _, b in pairs(loadBans()) do
        list[#list + 1] = string.format('{"name":%q,"at":%d}', b.name, tonumber(b.at) or 0)
    end
    local f = io.open(BANS_FILE, "w")
    if f then
        f:write("[" .. table.concat(list, ",") .. "]\n")
        f:close()
    end
end

--- The other players: { name, pc } for each remote controller with a player.
--- The other players: { name, pc } for each remote controller with a
--- connection and a player state, found the way Net.toClients finds them.
--- (GameState.PlayerArray with PlayerState:GetOwner() crashed the host inside
--- UE4SS's function call, 2026-10-03.)
local function remotePlayers()
    local out = {}
    for _, pc in ipairs(FindAllOf("PlayerController") or {}) do
        pcall(function()
            if not pc:IsValid() or pc:IsLocalController() then return end
            if not (UI.valid(pc.Player) and UI.valid(pc.PlayerState)) then return end
            out[#out + 1] = { name = pc.PlayerState:GetPlayerName():ToString(), pc = pc }
        end)
    end
    table.sort(out, function(a, b) return a.name < b.name end)
    return out
end

--- Send a player back to their main menu: a kick message over the lobby's
--- channel (Scripts/net.lua), on which their own game leaves the match.
local function kick(player, why)
    local ok = Net.toClient(player.pc, "kick", why)
    log(string.format("host: %s %s (%s)", ok and "sent back" or "could not send back", player.name, why))
    return ok
end

--- RETURN TO LOBBY: the fireteam travels back to the frontend with the host
--- (as after a match), and the host's lobby opens there.
local function returnToLobby()
    lobbyOnReturn = true
    pcall(function()
        local pc = UI.playerController()
        StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
            :ExecuteConsoleCommand(pc:GetWorld(), HOST_TRAVEL, pc)
    end)
    log("host: returning the fireteam to the lobby")
end

local function closeHostMenu()
    if hostMenuOpen then UI.pop(hostMenuOpen) end
    hostMenuOpen = nil
end

local openHostMenu

local function playerScreen(player)
    UI.push({
        layout = hostLayout,
        title = string.upper(player.name),
        subtitle = "PLAYER",
        description = "Kick sends them back to their main menu. Ban does the same and keeps them out of your games.",
        buttons = {
            { label = "KICK", description = "Send " .. player.name .. " back to their main menu.", onClick = function()
                kick(player, "You were kicked by the host.")
                closeHostMenu()
            end },
            { label = "BAN", description = "Kick " .. player.name .. " and keep them out of your games.", onClick = function()
                loadBans()[string.lower(player.name)] = { name = player.name, at = os.time() }
                saveBans()
                kick(player, "You were banned by the host.")
                closeHostMenu()
            end },
        },
    })
end

local function playersScreen()
    local players = remotePlayers()
    local buttons = {}
    for _, p in ipairs(players) do
        buttons[#buttons + 1] = { label = string.upper(p.name), description = "Kick or ban " .. p.name .. ".",
            onClick = function() playerScreen(p) end }
    end
    UI.push({
        layout = hostLayout,
        title = "PLAYERS",
        subtitle = #players == 1 and "1 OTHER PLAYER" or (#players .. " OTHER PLAYERS"),
        description = #players == 0 and "Nobody else is in the match." or "Pick a player to kick or ban.",
        buttons = buttons,
    })
end

local function bansScreen()
    local buttons = {}
    for key, b in pairs(loadBans()) do
        buttons[#buttons + 1] = { label = string.upper(b.name), description = "Let " .. b.name .. " join again.",
            onClick = function()
                loadBans()[key] = nil
                saveBans()
                log("host: unbanned " .. b.name)
                closeHostMenu()
            end }
    end
    table.sort(buttons, function(a, b) return a.label < b.label end)
    UI.push({
        layout = hostLayout,
        title = "BANNED PLAYERS",
        subtitle = #buttons .. " BANNED",
        description = #buttons == 0 and "Nobody is banned." or "Pick a name to unban it.",
        buttons = buttons,
    })
end

openHostMenu = function()
    if not Net.isHost() then
        log("host menu: only the host has one")
        return
    end
    if inFrontend() then
        log("host menu: in the lobby already")
        return
    end
    local title = Game.map and (titleOf(Game.map) .. "  /  " .. modeName(Game.mode and Game.mode.id)) or "MATCH"
    hostMenuOpen = UI.push({
        layout = hostLayout,
        title = "HOST MENU",
        subtitle = string.upper(title),
        description = "Your match: end it, take everyone back to the lobby, or manage players.",
        buttons = {
            { label = "END GAME", description = "End the match now. Everyone sees the results and votes on the next game.",
                onClick = function()
                    closeHostMenu()
                    native_("mjolnir_sim_end_game")
                end },
            { label = "RETURN TO LOBBY", description = "Take everyone back to the lobby to change the map or game type.",
                onClick = function()
                    closeHostMenu()
                    returnToLobby()
                end },
            { label = "PLAYERS", description = "Kick or ban a player.", onClick = playersScreen },
            { label = "BANNED PLAYERS", description = "Unban a player.", onClick = bansScreen },
        },
    })
end


--- The pause menu in one of our multiplayer matches (MJOLNIRLevelLoader's
--- running.txt names it): RELOAD CHECKPOINT and RESTART MISSION are campaign
--- actions, so they go; the host gets HOST MENU in the first one's place.
local PAUSE_MENU = "/Game/UI/InGame/PauseMenu/WBP_PauseMenu.WBP_PauseMenu_C"
local pauseHooked = false
local pauseEntry = { menu = nil, button = nil }

local function inMultiplayerMatch()
    return not inFrontend() and readFile(LOADER_DIR .. "\\running.txt") ~= nil
end

local function fixPauseMenu(menu)
    if not UI.valid(menu) or not inMultiplayerMatch() then return end
    pcall(function() hostLayout = menu:GetOuter():GetOuter() end)
    pcall(function() menu.RestartMissionButton:SetVisibility(1) end)
    if not Net.isHost() then
        pcall(function() menu.ReloadCheckpointButton:SetVisibility(1) end)
        return
    end
    if pauseEntry.menu == UI.addressOf(menu) and pauseEntry.button and UI.valid(pauseEntry.button.widget) then
        UI.label(pauseEntry.button, "HOST MENU")
        return
    end
    local container = menu.PauseButtonContainer
    local reload = UI.addressOf(menu.ReloadCheckpointButton)
    local index
    local count = 0
    pcall(function() count = container:GetChildrenCount() end)
    for i = 0, count - 1 do
        local ok, child = pcall(function() return container:GetChildAt(i) end)
        if ok and UI.addressOf(child) == reload then index = i end
    end
    local button, err = UI.button(menu, "HOST MENU", openHostMenu)
    if not button then
        log("pause menu: " .. tostring(err))
        return
    end
    local ok = pcall(function()
        if index then
            container:ReplaceButtonContainerChildAt(index, button.widget)
        else
            container:AddChildToButtonContainer(button.widget)
        end
    end)
    if not ok then
        log("pause menu: could not add HOST MENU")
        return
    end
    pauseEntry.menu, pauseEntry.button = UI.addressOf(menu), button
    ExecuteInGameThreadWithDelay(60, function()
        UI.label(button, "HOST MENU")
        pcall(function() button.widget:SetVisibility(0) end)
    end)
    log("pause menu: HOST MENU added")
end

--- Hook the pause menu's activation once its class is loaded (it loads with
--- the first match; loading it here gets the first pause too).
local function hookPauseMenu()
    if pauseHooked then return end
    if not UI.ensureClass(PAUSE_MENU) then return end
    pauseHooked = pcall(function()
        RegisterHook(PAUSE_MENU .. ":BP_OnActivated", function(self)
            local menu = self:get()
            ExecuteInGameThreadWithDelay(60, function() fixPauseMenu(menu) end)
        end)
    end)
    if pauseHooked then log("pause menu: hooked") end
end

--- Each 5 s on the host: send banned names back, and open the lobby after
--- RETURN TO LOBBY once the frontend's main menu is up.
local function watchHost()
    local function poll()
        pcall(function()
            if not pauseHooked and not inFrontend() then hookPauseMenu() end
            if not Net.isHost() then return end
            if lobbyOnReturn and inFrontend() and UI.valid(liveMainMenu()) then
                lobbyOnReturn = false
                openLobby()
            end
            local bans = loadBans()
            if next(bans) then
                for _, p in ipairs(remotePlayers()) do
                    if bans[string.lower(p.name)] then kick(p, "You are banned from this host's games.") end
                end
            end
        end)
        ExecuteInGameThreadWithDelay(5000, poll)
    end
    ExecuteInGameThreadWithDelay(5000, poll)
end

-------------------------------------------------------------------------------
-- Test automation (tools/remote/jip-test.mjs): `mjolnir_auto <verb> ...` at
-- the console, answered in native\auto_state.txt as key=value lines, so a
-- script can host, list, start and join without anyone at the menus.
--   mjolnir_auto state                 where this game is
--   mjolnir_auto host <CODE> <mode>    list publicly and start the map
--   mjolnir_auto public on|off         list or unlist
--   mjolnir_auto join [host name]      join a listed game (the first, or the host's)
-------------------------------------------------------------------------------

local AUTO_FILE = MOD_DIR .. "\\native\\auto_state.txt"

local function autoWrite(fields)
    local lines = {}
    fields.at = os.time()
    for k, v in pairs(fields) do lines[#lines + 1] = k .. "=" .. tostring(v) end
    table.sort(lines)
    local f = io.open(AUTO_FILE, "w")
    if f then
        f:write(table.concat(lines, "\n"), "\n")
        f:close()
    end
end

local function autoState(extra)
    local world = "?"
    pcall(function() world = UI.playerController():GetWorld():GetFName():ToString() end)
    local pawn = "none"
    pcall(function()
        local p = UI.playerController().Pawn
        if UI.valid(p) then pawn = p:GetClass():GetFName():ToString() end
    end)
    local fields = {
        signed_in = UI.valid(liveMainMenu()) and 1 or (inFrontend() and 0 or 1),
        frontend = inFrontend() and 1 or 0,
        world = world,
        pawn = pawn,
        public = Games.isPublic() and 1 or 0,
        status = tostring(Games.status() or ""),
        name = tostring(localName() or ""),
        players = #rosterPlayers(),
    }
    for k, v in pairs(extra or {}) do fields[k] = v end
    autoWrite(fields)
end

local AUTO = {
    state = function() autoState() end,
    hostmenu = function()
        openHostMenu()
        autoState({ result = hostMenuOpen and "host menu open" or "error no host menu" })
    end,
    lobby = function()
        returnToLobby()
        autoState({ result = "returning to the lobby" })
    end,
    endgame = function()
        autoState({ result = native_("mjolnir_sim_end_game") and "end game asked" or "error native" })
    end,
    kick = function(args, ban)
        local wanted = string.lower(table.concat(args, " "))
        for _, p in ipairs(remotePlayers()) do
            if string.lower(p.name):find(wanted, 1, true) then
                if ban then
                    loadBans()[string.lower(p.name)] = { name = p.name, at = os.time() }
                    saveBans()
                end
                return autoState({ result = (kick(p, ban and "You were banned by the host." or "You were kicked by the host.")
                    and (ban and "banned " or "kicked ") or "error kick ") .. p.name })
            end
        end
        autoState({ result = "error no player " .. wanted })
    end,
    unban = function(args)
        local wanted = string.lower(table.concat(args, " "))
        loadBans()[wanted] = nil
        saveBans()
        autoState({ result = "unbanned " .. wanted })
    end,
    public = function(args)
        Games.setPublic(args[1] ~= "off")
        autoState({ result = "public " .. tostring(args[1] ~= "off") })
    end,
    host = function(args)
        local map = mapByCode(string.upper(args[1] or ""))
        if not map then return autoState({ result = "error no installed map " .. tostring(args[1]) }) end
        local mode = modeById(map, args[2] or "slayer") or modesFor(map)[1]
        if not mode then return autoState({ result = "error no mode for " .. map.code }) end
        Game.map, Game.mode = map, mode
        saveGame()
        Games.setPublic(true)
        local ok, why = startGame(map, mode)
        autoState({ result = ok and ("hosting " .. map.code .. " " .. mode.id) or ("error " .. tostring(why)) })
    end,
    join = function(args)
        local wanted = args[1] and string.lower(table.concat(args, " ")) or nil
        autoState({ result = "listing" })
        Games.list(function(lobbies, why)
            if not lobbies then return autoState({ result = "error " .. tostring(why) }) end
            local chosen
            for _, g in ipairs(lobbies) do
                -- The hub lists its account name as host; the game's own
                -- player name is in the listing's name ("<player>'s game").
                local who = string.lower(tostring(g.host or "") .. " " .. tostring(g.name or ""))
                if not chosen and (not wanted or who:find(wanted, 1, true)) then
                    chosen = g
                end
            end
            if not chosen then return autoState({ result = "error no listed game" .. (wanted and (" by " .. wanted) or "") }) end
            autoState({ result = "joining " .. tostring(chosen.host) })
            Games.join(chosen, function(ok, err)
                autoState({ result = ok and ("joined " .. tostring(chosen.host)) or ("error " .. tostring(err)) })
            end)
        end)
    end,
}

local function initialize()
    UI.init(MOD_DIR)
    -- First: the main menu pushes the lobby without us, and if anything
    -- below fails, a lobby nobody watches for shows with dead buttons.
    watchNewLobbies()
    AUTO.ban = function(args) return AUTO.kick(args, true) end
    RegisterConsoleCommandHandler("mjolnir_host", function()
        ExecuteInGameThread(openHostMenu)
        return true
    end)
    watchHost()
    -- A kick from the host: leave its match the way the pause menu's quit
    -- does (BlamCampaignFlowGameSubsystem LeaveGame), off the RPC.
    -- A kick that arrives while this game is still joining (its world held
    -- for the Blam game, which is not built yet) waits for the join to end:
    -- leaving mid-join crashed the joiner in the Blam engine's tick (a ban
    -- enforced as a banned player rejoined, two PCs 2026-10-03).
    Net.on("kick", function(fields)
        log("host: sent back by the host (" .. tostring(fields[1]) .. ")")
        local tries = 0
        local function leave()
            tries = tries + 1
            if readFile(MOD_DIR .. "\\native\\jip_held.txt") and tries < 240 then
                ExecuteInGameThreadWithDelay(500, leave)
                return
            end
            ExecuteInGameThreadWithDelay(tries > 1 and 10000 or 200, function()
                pcall(function() FindFirstOf("BlamCampaignFlowGameSubsystem"):LeaveGame() end)
            end)
        end
        ExecuteInGameThreadWithDelay(200, leave)
    end)
    RegisterConsoleCommandHandler("mjolnir_auto", function(full)
        local args = {}
        for word in tostring(full or ""):gmatch("%S+") do args[#args + 1] = word end
        table.remove(args, 1)
        local verb = table.remove(args, 1) or "state"
        local fn = AUTO[verb]
        ExecuteInGameThread(function()
            local ok, err = pcall(fn or function() autoState({ result = "error unknown verb " .. verb }) end, args)
            if not ok then autoState({ result = "error " .. tostring(err) }) end
        end)
        return true
    end)
    Net.hook()
    openFireteam()
    Games.init({
        modDir = MOD_DIR,
        json = Json,
        net = Net,
        log = log,
        version = LOBBY_VERSION,
        -- The game a public listing shows: the lobby's choice, which a start
        -- (from the lobby or the post-game vote) also sets.
        info = function()
            if not (Game.map and Game.mode) then return nil end
            local name = localName()
            return {
                name = name and (name .. "'s game") or "MJOLNIR game",
                map_code = Game.map.code,
                game_type = Game.mode.id,
                players = #rosterPlayers(),
                in_game = not inFrontend(),
            }
        end,
    })
    -- Public match history: MJOLNIRHud's records and seat claims, to the hub.
    Matches.init({ modDir = MOD_DIR, games = Games, log = log })
    math.randomseed(os.time())
    watchMainMenu()
    watchPostGame()
    RegisterConsoleCommandHandler("mjolnir_lobby", function()
        openLobby()
        return true
    end)
    log("ready (" .. #installedMaps() .. " map(s) installed)")
end

ExecuteInGameThreadWithDelay(5000, initialize)
print("[MJOLNIR Lobby] Module loaded.\n")

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
        description = "Public and private Steam lobbies are the next part of the multiplayer menu. "
            .. "For now, HOST GAME and invite friends to your fireteam.",
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
local MAP_BUTTONS = 32
local MODE_BUTTONS = 5
local ROSTER_ROWS = 16
local LAST_GAME = MOD_DIR .. "\\last_game.txt"

local WHITE = { R = 1, G = 1, B = 1, A = 1 }
local ACCENT = { R = 0.55, G = 0.85, B = 1.0, A = 1 }
local NORMAL_BACKGROUND = { R = 1, G = 1, B = 1, A = 1 }
local SELECTED_BACKGROUND = { R = 3.0, G = 3.5, B = 3.5, A = 1 }

local Game = { map = nil, mode = nil }   -- what START GAME starts
local Lobby, Select = nil, nil           -- the screens on the stack
local Pick = { map = nil, mode = nil }   -- the map select's choice, until SELECT
-- A fireteam client's view of the host's lobby (After a match, below).
local clientLobby = { dismissed = false, at = nil }
local screenEvents = false

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
    for _, key in ipairs({ "Start", "ChangeMap", "GameType" }) do setShown(Lobby[key], host) end
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
        drawLobby()
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
        end
        pcall(function() Select:DeactivateWidget() end)
        drawLobby()
    end,
    back = function() pcall(function() Select:DeactivateWidget() end) end,
}

--- One event from a screen: "start", "map:3", "hover:3", "mode:1" ...
local function onScreenEvent(isLobby, event)
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

local function hookScreenEvents()
    if screenEvents then return true end
    local ok = pcall(function()
        for _, spec in ipairs({ { LOBBY_CLASS, true }, { SELECT_CLASS, false } }) do
            RegisterHook(spec[1] .. ":MJ_Event", function(self, name)
                local okE, event = pcall(function() return name:get():ToString() end)
                if not okE then return end
                -- The main menu pushes the lobby itself: the screen that
                -- sent the event is the lobby on screen.
                if spec[2] then
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
        end
    end)
    screenEvents = ok
    return ok
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
    setText(Lobby.Watermark, BuildLine.text(MODS_DIR))
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
local function watchNewLobbies()
    if not ourScreens() then return false end
    local ok, err = pcall(function()
        NotifyOnNewObject(LOBBY_CLASS, function(screen)
            local okN, name = pcall(function() return screen:GetFName():ToString() end)
            if not okN or name:find("^Default__") then return end
            ExecuteInGameThreadWithDelay(100, function() adoptLobby(screen) end)
        end)
    end)
    if not ok then log("cannot watch for new lobbies: " .. tostring(err)) end
    return ok
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
-- MaxPlayers 4 with every level, so the poll holds it up. The simulation
-- holds 16 players.

local FIRETEAM_SIZE = 16

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
end

local function holdFireteamSize()
    for _, session in ipairs(FindAllOf("GameSession") or {}) do
        pcall(function()
            if session:IsValid() and session.MaxPlayers < FIRETEAM_SIZE then session.MaxPlayers = FIRETEAM_SIZE end
        end)
    end
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
local function watchMainMenu()
    local function poll()
        local ok, err = pcall(function()
            refreshLobby()
            pcall(watchFireteam)
            pcall(holdFireteamSize)
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

local function initialize()
    UI.init(MOD_DIR)
    watchNewLobbies()
    Net.hook()
    openFireteam()
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

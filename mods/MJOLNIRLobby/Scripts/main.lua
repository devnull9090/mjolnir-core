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
local LOADER_DIR = (MOD_DIR:match("^(.*)\\[^\\]*$") or MOD_DIR) .. "\\MJOLNIRLevelLoader"
local log = UI.log

local HELPERS = "/Game/UI/Frontend/CampaignMenu/Data/BPFL_CampaignMenuHelpers.Default__BPFL_CampaignMenuHelpers_C"
local SCENARIOS = "/Game/Blueprints/Campaign/DT_Scenarios.DT_Scenarios"
local CAMPAIGN_MODE = 0      -- E_CampaignMode: the campaign's scenario list and save slot
local DIFFICULTY_NORMAL = 1

-- The game types, in menu order. A mode is offered for a map when the map
-- lists it and its variant file is installed.
local MODES = {
    { id = "slayer", name = "SLAYER", description = "Free for all. Every kill scores a point; the first to the score limit wins." },
    { id = "team_slayer", name = "TEAM SLAYER", description = "Red against Blue. Kills score for your team." },
    { id = "koth", name = "KING OF THE HILL", description = "Hold the hill to score. The hill moves." },
    { id = "oddball", name = "ODDBALL", description = "Hold the skull to score." },
    { id = "ctf", name = "CAPTURE THE FLAG", description = "Take the enemy flag to your base." },
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
    helpers:SelectedInsertionPoint(pc, setup, 0, pc)
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
local ROSTER_ROWS = 8
local LAST_GAME = MOD_DIR .. "\\last_game.txt"

local WHITE = { R = 1, G = 1, B = 1, A = 1 }
local ACCENT = { R = 0.55, G = 0.85, B = 1.0, A = 1 }
local NORMAL_BACKGROUND = { R = 1, G = 1, B = 1, A = 1 }
local SELECTED_BACKGROUND = { R = 2.2, G = 2.2, B = 2.2, A = 1 }

local Game = { map = nil, mode = nil }   -- what START GAME starts
local Lobby, Select = nil, nil           -- the screens on the stack
local Pick = { map = nil, mode = nil }   -- the map select's choice, until SELECT
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
    if ok and UI.valid(screen) then return screen end
    return nil
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
local function rosterNames()
    local names = {}
    pcall(function()
        local players = UI.playerController():GetWorld().GameState.PlayerArray
        players:ForEach(function(_, element)
            local okN, name = pcall(function() return element:get():GetPlayerName():ToString() end)
            if okN and name and name ~= "" then names[#names + 1] = name end
        end)
    end)
    return names
end

local function drawLobby()
    if not UI.valid(Lobby) then return end
    local map, mode = Game.map, Game.mode
    setText(Lobby.MapTitle, map and titleOf(map) or "NO MAPS INSTALLED")
    setText(Lobby.MapDescription, map and map.description or
        "Convert a classic CE map (tools/level/convert_ce_map.sh) or install a map pack.")
    setText(Lobby.ModeTitle, mode and mode.name or "")
    setText(Lobby.ModeDescription, mode and mode.description or "")
    local names = rosterNames()
    for i = 0, ROSTER_ROWS - 1 do
        setText(Lobby["Player" .. i], names[i + 1] or "")
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

local LOBBY_EVENTS = {
    start = function()
        if not (Game.map and Game.mode) then return end
        setText(Lobby.Status, "Starting " .. titleOf(Game.map) .. " - " .. Game.mode.name .. "...")
        local ok, err = startGame(Game.map, Game.mode)
        if not ok then setText(Lobby.Status, "Could not start: " .. tostring(err)) end
    end,
    changemap = openMapSelect,
    gametype = function()
        if not Game.map then return end
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
    back = function() pcall(function() Lobby:DeactivateWidget() end) end,
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
            RegisterHook(spec[1] .. ":MJ_Event", function(_, name)
                local okE, event = pcall(function() return name:get():ToString() end)
                if not okE then return end
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

--- MULTIPLAYER: our lobby, or the campaign-menu screens without the UI
--- container.
local function openLobby()
    if not (loadClass(LOBBY_CLASS) and loadClass(SELECT_CLASS) and hookScreenEvents()) then
        log("MJOLNIR UI not installed (pakchunk984-MJOLNIRUI): the campaign-menu screens instead")
        rootScreen()
        return
    end
    if not (Game.map and Game.mode) then Game.map, Game.mode = defaultGame() end
    Lobby = pushScreen(LOBBY_CLASS)
    if not Lobby then
        log("lobby: could not push " .. LOBBY_CLASS)
        rootScreen()
        return
    end
    setText(Lobby.Status, "Invite friends to your fireteam from the main menu, then START GAME.")
    drawLobby()
    pcall(function() Lobby.Start:SetFocus() end)
end

--- Keep the lobby's player list current while it is up.
local function refreshLobby()
    if alive(Lobby) then drawLobby() end
end

-------------------------------------------------------------------------------
-- The main-menu entry
-------------------------------------------------------------------------------

local MAIN_MENU = "/Game/UI/Frontend/MainMenu/Widgets/WBP_MainMenu.WBP_MainMenu_C"
local entry = { menu = nil, button = nil }

--- Put MULTIPLAYER in the main menu's button column, in the slot of the
--- hidden Remix button (between CAMPAIGN and PLAY CO-OP).
--- The main menu on screen. FindFirstOf could hand back the previous
--- frontend's menu, whose Slate widgets are gone (UI.liveWidget).
local function liveMainMenu()
    return UI.liveWidget("WBP_MainMenu_C", function(w) return w:IsVisible() end)
end

local function injectMainMenu()
    local menu = liveMainMenu()
    if not UI.valid(menu) then return end
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
    log("MULTIPLAYER added to the main menu")
end

local menuHook = false

--- The main menu exists only at the frontend, and is rebuilt each time the
--- game returns there; a light poll puts MULTIPLAYER back whenever a main
--- menu is up without it. The poll reschedules itself on the game thread:
--- LoopAsync handing work to ExecuteInGameThread can deadlock on the game
--- thread's lock (it froze the game in MJOLNIRLevelLoader, 2026-10-01).
local function watchMainMenu()
    local function poll()
        local ok, err = pcall(function()
            refreshLobby()
            local menu = liveMainMenu()
            if not UI.valid(menu) then return end
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
    watchMainMenu()
    RegisterConsoleCommandHandler("mjolnir_lobby", function()
        openLobby()
        return true
    end)
    log("ready (" .. #installedMaps() .. " map(s) installed)")
end

ExecuteInGameThreadWithDelay(5000, initialize)
print("[MJOLNIR Lobby] Module loaded.\n")

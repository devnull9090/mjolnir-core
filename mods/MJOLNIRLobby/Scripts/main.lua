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
-- FIND GAMES and JOIN PRIVATE are the Steam lobby half, still to come.

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
    local button, err = UI.button(menu, "MULTIPLAYER", rootScreen)
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
        rootScreen()
        return true
    end)
    log("ready (" .. #installedMaps() .. " map(s) installed)")
end

ExecuteInGameThreadWithDelay(5000, initialize)
print("[MJOLNIR Lobby] Module loaded.\n")

-- MJOLNIR Multiplayer Experiments
-- Provides verified HCE map paths, travel probes, and player administration commands.

local UEHelpers = require("UEHelpers")

local MAP_URLS = {
    ["a15"] = "/Game/Levels/Halo1/Solo/A15/A15",
    ["a30"] = "/Game/Levels/Halo1/Solo/A30/A30",
    ["a50"] = "/Game/Levels/Halo1/Solo/A50/A50",
    ["b30"] = "/Game/Levels/Halo1/Solo/B30/B30",
    ["b40"] = "/Game/Levels/Halo1/Solo/B40/B40",
    ["c10"] = "/Game/Levels/Halo1/Solo/C10/C10",
    ["c20"] = "/Game/Levels/Halo1/Solo/C20/C20",
    ["c45"] = "/Game/Levels/Halo1/Solo/C45/C45",
    ["d20"] = "/Game/Levels/Halo1/Solo/D20/D20",
    ["d40"] = "/Game/Levels/Halo1/Solo/D40/D40",
    ["e10"] = "/Game/Levels/Halo1/Solo/Extra/E10/E10",
    ["e20"] = "/Game/Levels/Halo1/Solo/Extra/E20/E20",
    ["e30"] = "/Game/Levels/Halo1/Solo/Extra/E30/E30",
}

--- First real parameter of a console command.
---
--- UE4SS hands the handler only the parameters, but some builds prepend the
--- command word itself; tolerate both so the commands survive either shape.
local function commandArg(args, index)
    local offset = (type(args[1]) == "string" and args[1]:lower():find("^mjolnir_")) and 1 or 0
    return args[index + offset]
end

local function eachPlayer(fn)
    local states = UEHelpers.GetAllPlayerStates()
    for _, ps in ipairs(states) do
        if ps and ps:IsValid() then fn(ps) end
    end
end

local function kickPlayer(targetName)
    eachPlayer(function(ps)
        if UEHelpers.SafeGetPlayerName(ps) == targetName then
            local pc = ps.Owner
            if pc and pc:IsValid() then
                local gm = UEHelpers.GetGameModeBase()
                if gm and gm.GameSession and gm.GameSession:IsValid() then
                    gm.GameSession:KickPlayer(pc, FText("Kicked by MJOLNIR Admin"))
                    print(string.format("[MJOLNIR Multiplayer] Kicked player %s\n", targetName))
                end
            end
        end
    end)
end

local function getPlayerController()
    local controllers = UEHelpers.GetAllPlayerControllers()
    for _, controller in ipairs(controllers) do
        if controller and controller:IsValid() then
            return controller
        end
    end
    return nil
end

local function executeConsoleCommand(command)
    local controller = getPlayerController()
    if not controller then
        print("[MJOLNIR Multiplayer] No live PlayerController; command was not dispatched.\n")
        return false
    end

    local ok, err = pcall(function()
        controller:ConsoleCommand(command, true)
    end)
    if ok then
        print(string.format("[MJOLNIR Multiplayer] Dispatched experimental command: %s\n", command))
        return true
    end

    local fallbackOk, fallbackErr = pcall(function()
        local systemLibrary = UEHelpers.FindObjectSafe("/Script/Engine.Default__KismetSystemLibrary")
        local world = controller:GetWorld()
        if not systemLibrary or not world or not world:IsValid() then
            error("KismetSystemLibrary or live World is unavailable")
        end
        systemLibrary:ExecuteConsoleCommand(world, command, controller)
    end)
    if fallbackOk then
        print(string.format("[MJOLNIR Multiplayer] Dispatched via Kismet fallback: %s\n", command))
        return true
    end

    print(string.format(
        "[MJOLNIR Multiplayer] Command dispatch failed: %s | fallback: %s\n",
        tostring(err),
        tostring(fallbackErr)
    ))
    return false
end

local function openMap(mapName, listen)
    local key = string.lower(mapName or "")
    local mapUrl = MAP_URLS[key]
    if not mapUrl then
        print(string.format("[MJOLNIR Multiplayer] Unknown map key '%s'. Run mjolnir_maps.\n", key))
        return
    end

    if listen then
        mapUrl = mapUrl .. "?listen"
    end

    print("[MJOLNIR Multiplayer] Note: `open` skips campaign setup and crashes from the frontend; prefer mjolnir_mission.\n")
    executeConsoleCommand("open " .. mapUrl)
end

local function listMaps()
    print("[MJOLNIR Multiplayer] Verified CU2 root world packages:\n")
    local keys = {}
    for key in pairs(MAP_URLS) do
        table.insert(keys, key)
    end
    table.sort(keys)
    for _, key in ipairs(keys) do
        print(string.format("  %-3s  %s\n", key, MAP_URLS[key]))
    end
end

-- Campaign-flow mission launch (verified on CU3, 2026-08-02).
--
-- BlamCampaignFlowGameSubsystem:SetAndBeginCampaign is the entry point the
-- game's own hidden debug menu uses (main menu -> Test options -> Debug Level
-- Select). Unlike `open`, it performs the full campaign setup and validates
-- the target synchronously: a scenario whose world is not cooked returns
-- false instead of crashing.
--
-- Scenario names come from DT_Scenarios (A15..D40, E10..E30) and
-- DT_Test_Scenarios (testing_*, d40_warthog_testkit). The test worlds are not
-- cooked in CU3, so those return false until a mod container supplies them.

local CAMPAIGN_ASSETS = {
    first = "/Game/Blueprints/Campaign/DA_FirstPlayableCampaign.DA_FirstPlayableCampaign",
    additional = "/Game/Blueprints/Campaign/DA_AdditionalCampaign.DA_AdditionalCampaign",
    test = "/Game/Blueprints/Campaign/DA_TestMapsCampaign.DA_TestMapsCampaign",
}

local CAMPAIGN_SCENARIOS = {
    A15 = "first", A30 = "first", A50 = "first", B30 = "first", B40 = "first",
    C10 = "first", C20 = "first", C45 = "first", D20 = "first", D40 = "first",
    E10 = "additional", E20 = "additional", E30 = "additional",
}

local function resolveScenario(raw)
    local upper = string.upper(raw or "")
    if CAMPAIGN_SCENARIOS[upper] then
        return upper, CAMPAIGN_ASSETS[CAMPAIGN_SCENARIOS[upper]]
    end
    local lower = string.lower(raw or "")
    if lower:find("^testing_") or lower == "d40_warthog_testkit" then
        return lower, CAMPAIGN_ASSETS.test
    end
    return nil, nil
end

local function firstValid(objects)
    for _, o in ipairs(objects or {}) do
        if o and o:IsValid() then return o end
    end
    return nil
end

local function launchMission(rawName)
    local scenario, campaignPath = resolveScenario(rawName)
    if not scenario then
        print(string.format(
            "[MJOLNIR Multiplayer] Unknown scenario '%s'. Use A15..D40, E10..E30, or testing_*.\n",
            tostring(rawName)))
        return
    end

    local subsystem = firstValid(FindAllOf("BlamCampaignFlowGameSubsystem"))
    local campaign = StaticFindObject(campaignPath)
    if not subsystem or not campaign or not campaign:IsValid() then
        print("[MJOLNIR Multiplayer] Campaign flow subsystem or data asset unavailable.\n")
        return
    end

    -- Reuse a live campaign variant when one exists (always true in-mission).
    -- A nil variant is fine: the campaign flow spawns its own default —
    -- verified launching A15 from the frontend with variant nil on CU3.
    local variant = firstValid(FindAllOf("BlamGameEngineCampaignVariant"))
    local ok, accepted = pcall(function()
        return subsystem:SetAndBeginCampaign(campaign, FName(scenario), {
            bLoadFromCoreSave = false,
            SaveSlot = 0,
            SavedFilmName = "",
            CampaignDifficultyLevel = 1,
            InsertionPoint = 0,
            bFriendlyFireEnabled = true,
            bIsLASO = false,
            GameVariant = variant,
        })
    end)

    if not ok then
        print(string.format("[MJOLNIR Multiplayer] SetAndBeginCampaign errored: %s\n", tostring(accepted)))
    elseif accepted then
        print(string.format(
            "[MJOLNIR Multiplayer] Mission '%s' accepted (variant %s). Loading...\n",
            scenario, variant and "reused" or "nil"))
    else
        print(string.format(
            "[MJOLNIR Multiplayer] Mission '%s' rejected — the scenario's world is not cooked or the flow refused it.\n",
            scenario))
    end
end

local function toggleDebugUi()
    local menu = firstValid(FindAllOf("WBP_MainMenu_C"))
    if not menu then
        print("[MJOLNIR Multiplayer] No main menu on screen; mjolnir_debug_ui works at the frontend.\n")
        return
    end
    local ok, err = pcall(function() menu:OnToggleDebugMenu() end)
    if ok then
        print("[MJOLNIR Multiplayer] Toggled the Test options panel (Debug Level Select lives there).\n")
    else
        print(string.format("[MJOLNIR Multiplayer] OnToggleDebugMenu failed: %s\n", tostring(err)))
    end
end

local function initializeMultiplayer()
    print("[MJOLNIR Multiplayer] Registering experimental travel and admin commands...\n")
    RegisterConsoleCommandHandler("mjolnir_mission", function(_, args)
        launchMission(commandArg(args, 1) or "")
        return true
    end)
    RegisterConsoleCommandHandler("mjolnir_debug_ui", function()
        toggleDebugUi()
        return true
    end)
    RegisterConsoleCommandHandler("mjolnir_kick", function(_, args)
        kickPlayer(commandArg(args, 1) or "")
        return true
    end)
    RegisterConsoleCommandHandler("mjolnir_maps", function()
        listMaps()
        return true
    end)
    RegisterConsoleCommandHandler("mjolnir_travel", function(_, args)
        openMap(commandArg(args, 1) or "", false)
        return true
    end)
    RegisterConsoleCommandHandler("mjolnir_listen", function(_, args)
        openMap(commandArg(args, 1) or "", true)
        return true
    end)
end

ExecuteInGameThreadWithDelay(5000, initializeMultiplayer)
print("[MJOLNIR Multiplayer] Module loaded.\n")

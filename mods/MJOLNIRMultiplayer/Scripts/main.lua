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

local function initializeMultiplayer()
    print("[MJOLNIR Multiplayer] Registering experimental travel and admin commands...\n")
    RegisterConsoleCommandHandler("mjolnir_kick", function(_, args)
        kickPlayer(args[2] or "")
        return true
    end)
    RegisterConsoleCommandHandler("mjolnir_maps", function()
        listMaps()
        return true
    end)
    RegisterConsoleCommandHandler("mjolnir_travel", function(_, args)
        openMap(args[2] or "", false)
        return true
    end)
    RegisterConsoleCommandHandler("mjolnir_listen", function(_, args)
        openMap(args[2] or "", true)
        return true
    end)
end

ExecuteInGameThreadWithDelay(5000, initializeMultiplayer)
print("[MJOLNIR Multiplayer] Module loaded.\n")

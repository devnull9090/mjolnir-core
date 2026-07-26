-- MJOLNIR Multiplayer Framework
-- Handles hosting, session travel URLs, player administration, and chat RPC hooks.

local UEHelpers = require("UEHelpers")

local CONFIG = {
    autohost = false,
    server_name = "MJOLNIR Multiplayer Host",
    max_players = 16,
    map = "Campaign_Level_01",
    admins = {},
    bans = {},
}

-- Map registration dictionary (populated via MJOLNIRDiscovery runs)
local MAP_URLS = {
    ["Campaign_Level_01"] = "/Game/Maps/PoA/PillarOfAutumn?listen",
    ["Campaign_Level_02"] = "/Game/Maps/Halo/HaloRing?listen",
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

local function serverTravel(url)
    local ok, err = pcall(function()
        local ob = UEHelpers.FindObjectSafe("/Script/PenguinHotel.Default__OnlineBlueprints")
            or UEHelpers.FindObjectSafe("/Script/Engine.Default__GameModeBase")
        if ob and ob.ServerTravel then
            ob:ServerTravel(url)
            print(string.format("[MJOLNIR Multiplayer] Executing ServerTravel to '%s'\n", url))
        end
    end)
    if not ok then
        print(string.format("[MJOLNIR Multiplayer] ServerTravel error: %s\n", tostring(err)))
    end
end

local function handleChatCommand(sender, message)
    if not message or message:sub(1, 1) ~= "!" then return end
    local cmd, arg = message:match("^!(%S+)%s*(.*)$")
    
    if cmd == "kick" and CONFIG.admins[sender] then
        kickPlayer(arg)
    elseif cmd == "ban" and CONFIG.admins[sender] then
        CONFIG.bans[arg] = true
        kickPlayer(arg)
    elseif cmd == "travel" and CONFIG.admins[sender] then
        if MAP_URLS[arg] then
            serverTravel(MAP_URLS[arg])
        end
    end
end

local function initializeMultiplayer()
    print("[MJOLNIR Multiplayer] Registering console commands and session hooks...\n")
    RegisterConsoleCommandHandler("mjolnir_kick", function(_, args)
        kickPlayer(args[2] or "")
        return true
    end)
    RegisterConsoleCommandHandler("mjolnir_travel", function(_, args)
        local mapName = args[2] or ""
        if MAP_URLS[mapName] then
            serverTravel(MAP_URLS[mapName])
        end
        return true
    end)
end

ExecuteInGameThreadWithDelay(5000, initializeMultiplayer)
print("[MJOLNIR Multiplayer] Module loaded.\n")

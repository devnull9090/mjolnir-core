-- MJOLNIR Core Engine Mod Framework
-- Core entry point & event bus initialization

print("[MJOLNIR Core] Initializing Framework...\n")

local UEHelpers = require("UEHelpers")

local function initializeMJOLNIRCore()
    print("=========================================\n")
    print("   MJOLNIR CORE MODDING FRAMEWORK v1.0   \n")
    print("   Target: Halo Campaign Evolved         \n")
    print("=========================================\n")

    -- Log engine initialization status
    local gm = UEHelpers.GetGameModeBase()
    if gm then
        print("[MJOLNIR Core] Found GameModeBase reference.\n")
    else
        print("[MJOLNIR Core] Waiting for GameModeBase initialization...\n")
    end
end

-- Initialize core framework with slight delay for engine startup
ExecuteInGameThreadWithDelay(2000, initializeMJOLNIRCore)
print("[MJOLNIR Core] Core script loaded successfully.\n")

-- MJOLNIR Core Engine Mod Framework
-- Core entry point & event bus initialization

print("[MJOLNIR Core] Initializing Framework...\n")

local UEHelpers = require("UEHelpers")

local function initializeMJOLNIRCore()
    print("=========================================\n")
    print("   MJOLNIR CORE MODDING FRAMEWORK v1.0   \n")
    print("   Target: Halo Campaign Evolved         \n")
    print("=========================================\n")

    -- Log engine initialization status. This is a one-shot observation, not a
    -- wait: at load time the frontend has no game mode yet, and reporting that
    -- honestly is more useful than the old lookup, which resolved the class
    -- default object and so always claimed success.
    local gm = UEHelpers.GetGameModeBase()
    if gm then
        print("[MJOLNIR Core] Live GameModeBase present at init.\n")
    else
        print("[MJOLNIR Core] No live GameModeBase yet (expected at the frontend).\n")
    end
end

-- Initialize core framework with slight delay for engine startup
ExecuteInGameThreadWithDelay(2000, initializeMJOLNIRCore)
print("[MJOLNIR Core] Core script loaded successfully.\n")

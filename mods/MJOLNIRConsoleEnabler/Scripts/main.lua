-- MJOLNIR Console Enabler Mod (Minimal)
-- Enables Unreal Engine developer console for Halo Campaign Evolved
-- Designed to work without HookManager to avoid performance overhead

local UEHelpers = require("UEHelpers")

local WasConsoleCreated = false

local function TryEnableConsole()
    local ok, result = pcall(function()
        local Engine = UEHelpers.GetEngine()
        if not Engine or not Engine:IsValid() then return false end

        local GameViewport = Engine.GameViewport
        if not GameViewport or not GameViewport:IsValid() then return false end

        local ConsoleClass = StaticFindObject("/Script/Engine.Console")
        if not ConsoleClass or not ConsoleClass:IsValid() then return false end

        if not GameViewport.ViewportConsole or not GameViewport.ViewportConsole:IsValid() then
            local CreatedConsole = StaticConstructObject(ConsoleClass, GameViewport)
            if CreatedConsole and CreatedConsole:IsValid() then
                GameViewport.ViewportConsole = CreatedConsole
                WasConsoleCreated = true
                print("[MJOLNIR ConsoleEnabler] SUCCESS: Console created & attached!\n")
                return true
            end
        else
            WasConsoleCreated = true
            print("[MJOLNIR ConsoleEnabler] SUCCESS: Console already exists.\n")
            return true
        end
        return false
    end)
    return ok and result
end

local function RetryLoop()
    if not WasConsoleCreated then
        if not TryEnableConsole() then
            ExecuteInGameThreadWithDelay(2000, RetryLoop)
        end
    end
end

-- Start retry loop with 2 second intervals
-- No RegisterHook needed - works without HookManager
ExecuteInGameThreadWithDelay(3000, RetryLoop)
print("[MJOLNIR ConsoleEnabler] Module loaded - waiting for viewport...\n")

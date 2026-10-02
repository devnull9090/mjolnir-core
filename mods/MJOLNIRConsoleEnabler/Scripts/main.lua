-- MJOLNIR Console Enabler Mod (Minimal)
-- Enables Unreal Engine developer console for Halo Campaign Evolved
-- Designed to work without HookManager to avoid performance overhead

local UEHelpers = require("UEHelpers")

local WasConsoleCreated = false

-- The game opens the console on Tilde and Tab. Tab is the multiplayer
-- scoreboard (MJOLNIRHud), as in Halo CE on PC, so the console keeps Tilde
-- only. The console reads InputSettings' ConsoleKeys at each key press.
local function FreeTab()
    local ok, moved = pcall(function()
        local settings = StaticFindObject("/Script/Engine.Default__InputSettings")
        local n = 0
        settings.ConsoleKeys:ForEach(function(_, element)
            local key = element:get()
            if key.KeyName:ToString() == "Tab" then
                key.KeyName = FName("Tilde")
                n = n + 1
            end
        end)
        return n
    end)
    if ok and moved and moved > 0 then
        print("[MJOLNIR ConsoleEnabler] Console key: Tilde only (Tab is the scoreboard)\n")
    end
end

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
    FreeTab()
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

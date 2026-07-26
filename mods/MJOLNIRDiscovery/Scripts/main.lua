-- MJOLNIR Discovery & Diagnostics Module
-- Automated UFunction and level travel scanner for Halo Campaign Evolved

local DUMP_FILE = "ue4ss/MJOLNIR_FunctionDump.txt"
local TRAVEL_LOG = "ue4ss/MJOLNIR_TravelLog.txt"

local function appendLog(path, text)
    local f = io.open(path, "a")
    if f then
        f:write(text, "\n")
        f:close()
    end
    print(text .. "\n")
end

local function safeRead(param)
    local ok, v = pcall(function() return param:get() end)
    if not ok then return "?" end
    local ok2, s = pcall(function() return v:ToString() end)
    return ok2 and s or tostring(v)
end

local function hookFunction(functionName)
    local ok, err = pcall(function()
        RegisterHook(functionName, function(self, a, b, c, d)
            appendLog(TRAVEL_LOG, string.format("[HOOK] %s | a=%s b=%s c=%s d=%s",
                functionName, safeRead(a), safeRead(b), safeRead(c), safeRead(d)))
        end)
    end)
    appendLog(TRAVEL_LOG, string.format("Hooking %s: %s", functionName, ok and "Registered" or tostring(err)))
end

local function dumpNetworkFunctions()
    appendLog(DUMP_FILE, "-- MJOLNIR Core Network & Function Discovery Dump --")
    local keywords = {
        "Host", "Travel", "Server", "Client", "Session", "Lobby",
        "Join", "Start", "Match", "GameMode", "PlayerState", "Network"
    }
    
    local ok, functions = pcall(FindAllOf, "Function")
    if ok and functions then
        local seen = {}
        local count = 0
        for i = 1, #functions do
            local fn = functions[i]
            if fn and fn:IsValid() then
                local okName, name = pcall(function() return fn:GetFullName() end)
                if okName and name then
                    for j = 1, #keywords do
                        if name:find(keywords[j], 1, true) and not seen[name] then
                            seen[name] = true
                            count = count + 1
                            appendLog(DUMP_FILE, name)
                            break
                        end
                    end
                end
            end
        end
        print(string.format("[MJOLNIR Discovery] Function scan complete (%d matching functions). Output written to %s\n", count, DUMP_FILE))
    end
end

-- Hook engine travel routines
hookFunction("/Script/Engine.PlayerController:ClientTravelInternalNative")
hookFunction("/Script/Engine.GameModeBase:ServerTravel")

ExecuteInGameThreadWithDelay(10000, dumpNetworkFunctions)
print("[MJOLNIR Discovery] Module loaded.\n")

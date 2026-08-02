-- MJOLNIR Discovery & Diagnostics Module
-- Automated UFunction and level travel scanner for Halo Campaign Evolved

local DUMP_FILE = "ue4ss/MJOLNIR_FunctionDump.txt"
local TRAVEL_LOG = "ue4ss/MJOLNIR_TravelLog.txt"
local BLAM_DUMP_FILE = "ue4ss/MJOLNIR_BlamDiscovery.txt"
local WORLD_DUMP_FILE = "ue4ss/MJOLNIR_WorldDiscovery.txt"
local STATE_DUMP_FILE = "ue4ss/MJOLNIR_MultiplayerState.txt"
local registeredHooks = {}
local stateDumpSequence = 0
local safeValue

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
    return safeValue(v)
end

safeValue = function(value)
    if value == nil then return "nil" end
    local valueType = type(value)
    if valueType == "string" or valueType == "number" or valueType == "boolean" then
        return tostring(value)
    end

    local okName, name = pcall(function() return value:GetFullName() end)
    if okName and name then return name end
    local okString, stringValue = pcall(function() return value:ToString() end)
    if okString and stringValue then return stringValue end
    return tostring(value)
end

local function safeFullName(object)
    if not object or not object:IsValid() then return nil end
    local ok, name = pcall(function() return object:GetFullName() end)
    if ok and name then return name end
    return nil
end

local function resetLog(path, heading)
    local f = io.open(path, "w")
    if f then
        f:write(heading, "\n")
        f:close()
    end
    print(heading .. "\n")
end

local function hookFunction(functionName)
    if registeredHooks[functionName] then
        appendLog(TRAVEL_LOG, "Hook already registered: " .. functionName)
        return true
    end

    local function logCall(phase, self, a, b, c, d)
        appendLog(TRAVEL_LOG, string.format("[HOOK %s] %s | self=%s a=%s b=%s c=%s d=%s",
            phase, functionName, safeRead(self), safeRead(a), safeRead(b), safeRead(c), safeRead(d)))
    end

    local ok, err = pcall(function()
        local preId, postId = RegisterHook(
            functionName,
            function(self, a, b, c, d) logCall("PRE", self, a, b, c, d) end,
            function(self, a, b, c, d) logCall("POST", self, a, b, c, d) end
        )
        registeredHooks[functionName] = { preId = preId, postId = postId }
    end)
    appendLog(TRAVEL_LOG, string.format("Hooking %s: %s", functionName, ok and "Registered" or tostring(err)))
    return ok
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

local function isBlamResearchTarget(name)
    return name:find("/Script/BlamEngine", 1, true)
        or name:find("/Script/BlamGlue", 1, true)
        or name:find("/Script/BlamNetworkSession", 1, true)
        or name:find("/Script/Meteorite.", 1, true)
        or name:find("/Script/MeteoriteOnlineServices", 1, true)
        or (name:find("BlamGameEngine", 1, true) and name:find("Variant", 1, true))
        or name:find("BlamEngineGlueOuterSubsystem", 1, true)
end

local function dumpMatchingObjects(typeName, seen)
    local ok, objects = pcall(FindAllOf, typeName)
    if not ok then
        appendLog(BLAM_DUMP_FILE, string.format("[TYPE ERROR] %s: %s", typeName, tostring(objects)))
        return 0
    end
    if not objects then
        appendLog(BLAM_DUMP_FILE, string.format("[NO INSTANCES] %s", typeName))
        return 0
    end

    local count = 0
    for i = 1, #objects do
        local name = safeFullName(objects[i])
        local matches = typeName ~= "Function" or isBlamResearchTarget(name or "")
        if name and matches and not seen[name] then
            seen[name] = true
            count = count + 1
            appendLog(BLAM_DUMP_FILE, string.format("[%s] %s", typeName, name))
        end
    end
    return count
end

local function dumpBlamObjects()
    resetLog(BLAM_DUMP_FILE, "-- MJOLNIR BlamEngine Runtime Discovery --")
    appendLog(BLAM_DUMP_FILE, "Timestamp UTC: " .. os.date("!%Y-%m-%dT%H:%M:%SZ"))

    local seen = {}
    local count = 0
    for _, typeName in ipairs({
        "Function",
        "BlamGameEngineBaseVariant",
        "BlamGameEngineCampaignVariant",
        "BlamGameEngineVariant",
        "BlamEngineGlueOuterSubsystem",
        "BlamOnlineSessionSubsystem",
        "BlamNetworkGameStateComponent",
        "MeteoriteLobbyNotifier",
        "MeteoriteSquadLobbyViewModel",
    }) do
        count = count + dumpMatchingObjects(typeName, seen)
    end

    local staticCandidates = {
        "/Script/BlamEngine.BlamGameEngineBaseVariant",
        "/Script/BlamEngine.Default__BlamGameEngineBaseVariant",
        "/Script/BlamEngine.BlamGameEngineCampaignVariant",
        "/Script/BlamEngine.Default__BlamGameEngineCampaignVariant",
        "/Script/BlamEngine.BlamGameEngineVariant",
        "/Script/BlamEngine.Default__BlamGameEngineVariant",
        "/Script/BlamGlue.BlamEngineGlueOuterSubsystem",
        "/Script/BlamGlue.Default__BlamEngineGlueOuterSubsystem",
        "/Script/BlamNetworkSession.BlamOnlineSessionSubsystem",
        "/Script/BlamNetworkSession.Default__BlamOnlineSessionSubsystem",
    }
    for _, path in ipairs(staticCandidates) do
        local ok, object = pcall(StaticFindObject, path)
        local name = ok and safeFullName(object) or nil
        appendLog(BLAM_DUMP_FILE, string.format(
            "[STATIC %s] %s",
            name and "FOUND" or "MISS",
            name or path
        ))
    end

    appendLog(BLAM_DUMP_FILE, string.format("Unique matching objects: %d", count))
    print(string.format(
        "[MJOLNIR Discovery] Blam scan complete (%d objects). Output: %s\n",
        count,
        BLAM_DUMP_FILE
    ))
end

local function dumpLoadedWorlds()
    resetLog(WORLD_DUMP_FILE, "-- MJOLNIR Loaded World Discovery --")
    local ok, worlds = pcall(FindAllOf, "World")
    if not ok or not worlds then
        appendLog(WORLD_DUMP_FILE, "World scan failed: " .. tostring(worlds))
        return
    end

    local matchingCount = 0
    local totalCount = 0
    for i = 1, #worlds do
        local name = safeFullName(worlds[i])
        if name then
            totalCount = totalCount + 1
            local lowerName = string.lower(name)
            local isTarget = lowerName:find("/game/levels/halo1/", 1, true)
                or lowerName:find("/game/levels/ui/", 1, true)
            if isTarget then matchingCount = matchingCount + 1 end
            appendLog(WORLD_DUMP_FILE, string.format("[%s] %s", isTarget and "TARGET" or "OTHER", name))
        end
    end
    appendLog(WORLD_DUMP_FILE, string.format("Loaded worlds: %d; matching Halo/UI worlds: %d", totalCount, matchingCount))
end

local function dumpObjectProperties(object)
    local objectName = safeFullName(object)
    if not objectName then return end
    appendLog(STATE_DUMP_FILE, "[OBJECT] " .. objectName)

    local okClass, class = pcall(function() return object:GetClass() end)
    if not okClass or not class or not class:IsValid() then
        appendLog(STATE_DUMP_FILE, "  [CLASS ERROR]")
        return
    end

    local seenProperties = {}
    while class and class:IsValid() do
        appendLog(STATE_DUMP_FILE, "  [CLASS] " .. (safeFullName(class) or "?"))
        local okProperties, propertyError = pcall(function()
            class:ForEachProperty(function(property)
                local okPropertyName, propertyName = pcall(function()
                    return property:GetFName():ToString()
                end)
                if okPropertyName and propertyName and not seenProperties[propertyName] then
                    seenProperties[propertyName] = true
                    local okValue, value = pcall(function()
                        return object:GetPropertyValue(propertyName)
                    end)
                    appendLog(STATE_DUMP_FILE, string.format(
                        "    %s = %s",
                        propertyName,
                        okValue and safeValue(value) or "<unreadable>"
                    ))

                    if propertyName == "CampaignVariantStorage" then
                        local okStruct, struct = pcall(function() return property:GetStruct() end)
                        if okStruct and struct and struct:IsValid() then
                            appendLog(STATE_DUMP_FILE, "    [STRUCT] " .. (safeFullName(struct) or propertyName))
                            local okFields, fieldError = pcall(function()
                                struct:ForEachProperty(function(field)
                                    local okFieldName, fieldName = pcall(function()
                                        return field:GetFName():ToString()
                                    end)
                                    if okFieldName and fieldName then
                                        local okFieldValue, fieldValue = pcall(function()
                                            return value[fieldName]
                                        end)
                                        appendLog(STATE_DUMP_FILE, string.format(
                                            "      %s = %s",
                                            fieldName,
                                            okFieldValue and safeValue(fieldValue) or "<unreadable>"
                                        ))
                                    end
                                end)
                            end)
                            if not okFields then
                                appendLog(STATE_DUMP_FILE, "    [STRUCT ERROR] " .. tostring(fieldError))
                            end
                        end
                    end
                end
            end)
        end)
        if not okProperties then
            appendLog(STATE_DUMP_FILE, "  [PROPERTY ERROR] " .. tostring(propertyError))
        end

        local okSuper, superClass = pcall(function() return class:GetSuperStruct() end)
        if not okSuper or not superClass or not superClass:IsValid() then break end
        class = superClass
    end
end

local function dumpMethodResult(object, methodName)
    local ok, result = pcall(function()
        return object[methodName](object)
    end)
    appendLog(STATE_DUMP_FILE, string.format(
        "  [CALL] %s = %s",
        methodName,
        ok and safeValue(result) or "<error: " .. tostring(result) .. ">"
    ))
end

local function dumpMultiplayerState()
    if stateDumpSequence == 0 then
        resetLog(STATE_DUMP_FILE, "-- MJOLNIR Multiplayer Runtime State --")
    else
        appendLog(STATE_DUMP_FILE, "")
    end
    stateDumpSequence = stateDumpSequence + 1
    appendLog(STATE_DUMP_FILE, string.format("=== SNAPSHOT %d ===", stateDumpSequence))
    appendLog(STATE_DUMP_FILE, "Timestamp UTC: " .. os.date("!%Y-%m-%dT%H:%M:%SZ"))

    local seen = {}
    local count = 0
    for _, typeName in ipairs({
        "BlamGameEngineBaseVariant",
        "BlamGameEngineCampaignVariant",
        "BlamCampaignFlowGameSubsystem",
        "BlamOnlineSessionSubsystem",
        "BlamEngineAudioGameSubsystem",
        "BlamNetworkGameStateComponent",
        "BlamNetworkPlayerStateComponent",
        "MeteoriteLobbyNotifier",
        "MeteoriteSquadLobbyViewModel",
    }) do
        local ok, objects = pcall(FindAllOf, typeName)
        if ok and objects then
            for i = 1, #objects do
                local name = safeFullName(objects[i])
                if name and not seen[name] then
                    seen[name] = true
                    count = count + 1
                    dumpObjectProperties(objects[i])
                    if typeName == "BlamOnlineSessionSubsystem" then
                        dumpMethodResult(objects[i], "IsReadyToPlay")
                    elseif typeName == "BlamEngineAudioGameSubsystem" then
                        dumpMethodResult(objects[i], "IsNetworkCoop")
                    elseif typeName == "MeteoriteSquadLobbyViewModel" then
                        dumpMethodResult(objects[i], "GetNumSquadMembers")
                    elseif typeName == "BlamGameEngineCampaignVariant" then
                        dumpMethodResult(objects[i], "GetFlags")
                        dumpMethodResult(objects[i], "GetPerPlayerTraits")
                        dumpMethodResult(objects[i], "GetSocialOptions")
                    end
                end
            end
        else
            appendLog(STATE_DUMP_FILE, string.format("[NO INSTANCES] %s", typeName))
        end
    end

    appendLog(STATE_DUMP_FILE, string.format("Objects dumped: %d", count))
    print(string.format("[MJOLNIR Discovery] Multiplayer state dump complete (%d objects). Output: %s\n", count, STATE_DUMP_FILE))
end

local function registerNetworkTraceHooks()
    local hooks = {
        "/Script/Engine.PlayerController:ClientTravel",
        "/Script/Engine.PlayerController:ClientTravelInternal",
        "/Script/Engine.PlayerController:LocalTravel",
        "/Script/Engine.GameInstance:HandleTravelError",
        "/Script/OnlineSubsystemUtils.CreateSessionCallbackProxy:CreateSession",
        "/Script/OnlineSubsystemUtils.DestroySessionCallbackProxy:DestroySession",
        "/Script/OnlineSubsystemUtils.FindSessionsCallbackProxy:FindSessions",
        "/Script/OnlineSubsystemUtils.JoinSessionCallbackProxy:JoinSession",
        "/Script/PlayFab.PlayFabMultiplayerAPI:CreateLobby",
        "/Script/PlayFab.PlayFabMultiplayerAPI:JoinArrangedLobby",
        "/Script/PlayFab.PlayFabMultiplayerAPI:JoinLobby",
        "/Script/PlayFab.PlayFabMultiplayerAPI:LeaveLobby",
        "/Script/Meteorite.MeteoriteLobbyNotifier:AcceptInvite",
        "/Script/BlamNetworkSession.BlamNetworkGameStateComponent:OnRep_bSessionRunning",
        "/Script/BlamNetworkSession.BlamNetworkPlayerStateComponent:OnRep_EndpointGeneration",
        "/Script/BlamNetworkSession.BlamNetworkPlayerStateComponent:OnRep_EndpointId",
        "/Script/BlamNetworkSession.BlamNetworkPlayerStateComponent:ServerSetBlamEndpointIds",
        "/Script/BlamNetworkSession.BlamNetworkPlayerStateComponent:ServerSetPrimaryPlayerId",
        "/Script/BlamEngine.BlamCampaignFlowGameSubsystem:BeginCampaign",
        "/Script/BlamEngine.BlamCampaignFlowGameSubsystem:SetActiveCampaign",
        "/Script/BlamEngine.BlamCampaignFlowGameSubsystem:SetAndBeginCampaign",
    }

    appendLog(TRAVEL_LOG, "-- Registering MJOLNIR network lifecycle hooks --")
    local registeredCount = 0
    for _, functionName in ipairs(hooks) do
        if hookFunction(functionName) then registeredCount = registeredCount + 1 end
    end
    print(string.format("[MJOLNIR Discovery] Network trace ready (%d/%d hooks).\n", registeredCount, #hooks))
end

local function registerDiscoveryCommands()
    RegisterConsoleCommandHandler("mjolnir_scan_blam", function()
        ExecuteInGameThread(dumpBlamObjects)
        return true
    end)
    RegisterConsoleCommandHandler("mjolnir_scan_worlds", function()
        ExecuteInGameThread(dumpLoadedWorlds)
        return true
    end)
    RegisterConsoleCommandHandler("mjolnir_trace_network", function()
        ExecuteInGameThread(registerNetworkTraceHooks)
        return true
    end)
    RegisterConsoleCommandHandler("mjolnir_dump_state", function()
        ExecuteInGameThread(dumpMultiplayerState)
        return true
    end)
    print("[MJOLNIR Discovery] Commands registered: mjolnir_scan_blam, mjolnir_scan_worlds, mjolnir_trace_network, mjolnir_dump_state\n")
end

-- Hook engine travel routines
hookFunction("/Script/Engine.PlayerController:ClientTravel")
hookFunction("/Script/Engine.PlayerController:ClientTravelInternal")
hookFunction("/Script/Engine.PlayerController:LocalTravel")

ExecuteInGameThreadWithDelay(5000, registerDiscoveryCommands)
ExecuteInGameThreadWithDelay(6000, registerNetworkTraceHooks)
ExecuteInGameThreadWithDelay(10000, dumpNetworkFunctions)
print("[MJOLNIR Discovery] Module loaded.\n")

-- MJOLNIR Core Engine Helpers Library
-- Provides safe wrapper functions for querying Unreal Engine objects, controllers, and game states.

local UEHelpers = {}

function UEHelpers.GetGameModeBase()
    local ok, gm = pcall(function() return StaticFindObject("/Script/Engine.Default__GameModeBase") end)
    if ok and gm and gm:IsValid() then
        return gm
    end
    return nil
end

function UEHelpers.GetAllPlayerStates()
    local ok, states = pcall(FindAllOf, "PlayerState")
    if ok and states then
        return states
    end
    return {}
end

function UEHelpers.GetAllPlayerControllers()
    local ok, pcs = pcall(FindAllOf, "PlayerController")
    if ok and pcs then
        return pcs
    end
    return {}
end

function UEHelpers.SafeGetPlayerName(playerState)
    if not playerState or not playerState:IsValid() then return "Unknown" end
    local ok, name = pcall(function() return playerState:GetPlayerName():ToString() end)
    if ok and name then return name end
    return "Unknown"
end

function UEHelpers.FindObjectSafe(fullName)
    local ok, obj = pcall(StaticFindObject, fullName)
    if ok and obj and obj:IsValid() then
        return obj
    end
    return nil
end

function UEHelpers.FindFName(name)
    if type(FName) == "function" or type(FName) == "table" or type(FName) == "userdata" then
        local ok, fname = pcall(function() return FName(name) end)
        if ok and fname then return fname end
    end
    return name
end

function UEHelpers.GetEngine()
    local ok, engine = pcall(function()
        local e = StaticFindObject("/Script/Engine.Default__Engine")
        if e and e:IsValid() then return e end
        local engines = FindAllOf("Engine")
        if engines and #engines > 0 then return engines[1] end
        return nil
    end)
    if ok and engine then return engine end
    return nil
end

return UEHelpers


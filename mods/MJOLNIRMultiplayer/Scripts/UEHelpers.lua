-- MJOLNIR Core Engine Helpers Library
-- Provides safe wrapper functions for querying Unreal Engine objects, controllers, and game states.
--
-- A note on class default objects. `StaticFindObject("/Script/Engine.Default__Foo")`
-- resolves the CDO: the archetype Unreal keeps to stamp new instances from. It is
-- always present and always reports IsValid(), so a lookup that returns one looks
-- like a success while every gameplay pointer hanging off it reads back nil. The
-- accessors below return live instances for that reason, and say so in their names.

local UEHelpers = {}

--- True for class default objects and archetypes, which are never live gameplay state.
local function isDefaultObject(object)
    local ok, name = pcall(function() return object:GetFullName() end)
    if not ok or not name then return false end
    return name:find("Default__", 1, true) ~= nil
end

--- First live, non-CDO instance of a class, or nil. FindAllOf matches subclasses,
--- so asking for "GameModeBase" finds the game's own derived game mode.
function UEHelpers.FindFirstInstanceOf(className)
    local ok, objects = pcall(FindAllOf, className)
    if not ok or not objects then return nil end
    for i = 1, #objects do
        local object = objects[i]
        if object and object:IsValid() and not isDefaultObject(object) then
            return object
        end
    end
    return nil
end

--- The live game mode actor. Only the authority has one; clients get nil.
function UEHelpers.GetGameModeBase()
    return UEHelpers.FindFirstInstanceOf("GameModeBase")
end

--- The live GameSession, which owns KickPlayer and the player limits. Reached
--- through the game mode when there is one, since that is the owning pointer,
--- and by direct search otherwise.
function UEHelpers.GetGameSession()
    local gameMode = UEHelpers.GetGameModeBase()
    if gameMode then
        local ok, session = pcall(function() return gameMode.GameSession end)
        if ok and session and session:IsValid() then
            return session
        end
    end
    return UEHelpers.FindFirstInstanceOf("GameSession")
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

--- The live UEngine singleton, the one that actually owns GameViewport. The
--- Engine CDO is deliberately not a fallback here: returning it would satisfy
--- `if engine then` at every call site while GameViewport stayed nil forever.
function UEHelpers.GetEngine()
    local engine = UEHelpers.FindFirstInstanceOf("GameEngine")
    if engine then return engine end
    return UEHelpers.FindFirstInstanceOf("Engine")
end

--- The live world, for APIs that need a world context object.
function UEHelpers.GetWorld()
    return UEHelpers.FindFirstInstanceOf("World")
end

return UEHelpers

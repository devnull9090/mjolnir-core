-- MJOLNIR Co-op 8
--
-- Campaign co-op is capped at four players. That cap is not one number: it is a
-- stack of them, spread across the Unreal session layer, the Meteorite squad UI,
-- the PlayFab lobby, and the Blam simulation. This module raises every limit that
-- is reachable from Lua and records what the unreachable ones do about it, so the
-- next player slot fails in a named place instead of anonymously.
--
-- See docs/coop_player_cap.md for which layer owns which number.
--
-- No `require("UEHelpers")`: everything below uses UE4SS's own globals, so this
-- module does not care which UEHelpers an install happens to provide.

local REPORT_FILE = "ue4ss/MJOLNIR_Coop8.txt"
local DEFAULT_TARGET = 8

-- Applied automatically on load. `mjolnir_coop8_raise <n>` overrides it.
local targetPlayers = DEFAULT_TARGET
local registeredHooks = {}
local reportSequence = 0

-- Every property this module knows how to raise, in the order it tries them.
-- `class` is what FindAllOf is asked for; `property` is the int32 to overwrite.
-- Not all of these exist in every build or at every point in the flow, which is
-- the reason each one is probed rather than assumed.
local CAP_PROPERTIES = {
    { class = "GameSession",         property = "MaxPlayers" },
    { class = "GameSession",         property = "MaxSpectators" },
    { class = "GameSession",         property = "MaxSplitscreensPerConnection" },
    { class = "GameViewportClient",  property = "MaxSplitscreenPlayers" },
}

-- Not listed: UGameMapsSettings. Its CDO resolves, but every property on it reads
-- back as UE4SS's TrivialObject placeholder - including ones that certainly exist,
-- so this is missing reflection data rather than a missing property. Verified on
-- CU3. Anything that needs it has to go through an ini, not through Lua.

-- Console variables that gate the same limits from the other side. `net.MaxPlayersOverride`
-- is stock Unreal: AGameSession::InitOptions prefers it over MaxPlayers whenever it is
-- above zero, which makes it the one lever that survives the session being rebuilt.
local function capCommands(target)
    return {
        string.format("net.MaxPlayersOverride %d", target),
    }
end

-- Read-only observations. These are the numbers that tell us whether raising the
-- caps above actually moved anything, so they are captured before and after.
local OBSERVATIONS = {
    { class = "MeteoriteSquadLobbyViewModel",     property = "TotalPlayerCount" },
    { class = "MeteoriteSquadLobbyViewModel",     property = "bOfferJoinSlots" },
    { class = "BlamNetworkGameStateComponent",    property = "bSessionRunning" },
}

local OBSERVED_CALLS = {
    { class = "MeteoriteSquadLobbyViewModel", method = "GetNumSquadMembers" },
    { class = "MeteoriteSquadLobbyViewModel", method = "CanAddSplitscreenPlayer" },
    { class = "BlamOnlineSessionSubsystem",   method = "IsReadyToPlay" },
    { class = "BlamEngineAudioGameSubsystem", method = "IsNetworkCoop" },
}

-- The points where an extra player gets turned away. Hooking them does not raise
-- anything; it records which one fired, which is what turns "it still says four"
-- into an actionable finding.
local REFUSAL_HOOKS = {
    "/Script/Engine.GameSession:KickPlayer",
    "/Script/Engine.GameModeBase:PostLogin",
    "/Script/Engine.GameInstance:HandleTravelError",
    "/Script/Engine.GameInstance:HandleNetworkError",
    "/Script/PlayFab.PlayFabMultiplayerAPI:CreateLobby",
    "/Script/PlayFab.PlayFabMultiplayerAPI:JoinLobby",
    "/Script/PlayFab.PlayFabMultiplayerAPI:JoinArrangedLobby",
    "/Script/BlamNetworkSession.BlamNetworkPlayerStateComponent:ServerSetBlamEndpointIds",
    "/Script/BlamNetworkSession.BlamNetworkGameStateComponent:OnRep_bSessionRunning",
    "/Script/BlamEngine.BlamCampaignFlowGameSubsystem:BeginCampaign",
}

local function write(text)
    local f = io.open(REPORT_FILE, "a")
    if f then
        f:write(text, "\n")
        f:close()
    end
    print("[MJOLNIR Coop8] " .. text .. "\n")
end

local function resetReport(heading)
    local f = io.open(REPORT_FILE, "w")
    if f then
        f:write(heading, "\n")
        f:close()
    end
    print("[MJOLNIR Coop8] " .. heading .. "\n")
end

local function describe(value)
    if value == nil then return "nil" end
    local kind = type(value)
    if kind == "string" or kind == "number" or kind == "boolean" then
        return tostring(value)
    end
    local ok, name = pcall(function() return value:GetFullName() end)
    if ok and name then return name end
    return tostring(value)
end

local function shortName(object)
    local ok, name = pcall(function() return object:GetFullName() end)
    if ok and name then return name end
    return "<unnamed>"
end

local function eachInstance(className, fn)
    local ok, objects = pcall(FindAllOf, className)
    if not ok or not objects then return 0 end
    local visited = 0
    for i = 1, #objects do
        local object = objects[i]
        if object and object:IsValid() then
            visited = visited + 1
            fn(object)
        end
    end
    return visited
end

-- Writes an int32 property and reports the before/after pair. A property that does
-- not exist on this build reads back nil and is skipped rather than invented.
local function raiseProperty(object, property, target)
    local okRead, current = pcall(function() return object[property] end)
    if not okRead or current == nil then
        return nil, "absent"
    end
    if type(current) ~= "number" then
        return nil, "not numeric (" .. describe(current) .. ")"
    end
    if current >= target then
        return current, "already >= target"
    end

    local okWrite, writeErr = pcall(function() object[property] = target end)
    if not okWrite then
        return current, "write failed: " .. tostring(writeErr)
    end

    local okVerify, applied = pcall(function() return object[property] end)
    if not okVerify or applied == nil then
        return current, "write accepted but read-back failed"
    end
    if applied ~= target then
        return current, string.format("write reverted (%s -> %s)", tostring(current), tostring(applied))
    end
    return current, string.format("raised %s -> %s", tostring(current), tostring(target))
end

--- StaticFindObject, guarded. Deliberately not UEHelpers.FindObjectSafe: that
--- helper is MJOLNIR-only, and `require("UEHelpers")` binds to UE4SS's shared copy
--- for any mod that does not ship its own under `Scripts/`. Depending on it here
--- would mean either a nil call at first use or a fourth duplicate of UEHelpers in
--- the tree, and this module needs exactly one function out of it.
local function findObject(fullName)
    local ok, object = pcall(StaticFindObject, fullName)
    if ok and object and object:IsValid() then return object end
    return nil
end

local function firstLiveOf(className)
    local ok, objects = pcall(FindAllOf, className)
    if not ok or not objects then return nil end
    for i = 1, #objects do
        if objects[i] and objects[i]:IsValid() then return objects[i] end
    end
    return nil
end

local function dispatchConsoleCommand(command)
    local controller = firstLiveOf("PlayerController")

    if controller then
        local ok = pcall(function() controller:ConsoleCommand(command, true) end)
        if ok then return true, "PlayerController" end
    end

    -- The frontend can be reached before any PlayerController exists, which is
    -- exactly when the session limits still matter. ExecuteConsoleCommand resolves
    -- its world from the context object, so that has to be a live World rather
    -- than a class default object, which would resolve to nothing.
    local ok = pcall(function()
        local systemLibrary = findObject("/Script/Engine.Default__KismetSystemLibrary")
        local world = firstLiveOf("World")
        if not systemLibrary or not world then
            error("KismetSystemLibrary or live World unavailable")
        end
        systemLibrary:ExecuteConsoleCommand(world, command, controller)
    end)
    if ok then return true, "KismetSystemLibrary" end

    return false, "no dispatch route"
end

local function applyCaps(target)
    write(string.format("--- Applying co-op caps (target %d) ---", target))

    for _, command in ipairs(capCommands(target)) do
        local ok, route = dispatchConsoleCommand(command)
        write(string.format("  [cvar] %-32s %s (%s)", command, ok and "dispatched" or "FAILED", route))
    end

    for _, cap in ipairs(CAP_PROPERTIES) do
        local touched = eachInstance(cap.class, function(object)
            local _, outcome = raiseProperty(object, cap.property, target)
            write(string.format("  [prop] %s.%s on %s: %s",
                cap.class, cap.property, shortName(object), outcome))
        end)
        if touched == 0 then
            write(string.format("  [prop] %s.%s: no live instances", cap.class, cap.property))
        end
    end
end

local function observe(label)
    write(string.format("--- Observed state: %s ---", label))

    for _, entry in ipairs(OBSERVATIONS) do
        local touched = eachInstance(entry.class, function(object)
            local ok, value = pcall(function() return object[entry.property] end)
            write(string.format("  [read] %s.%s on %s = %s",
                entry.class, entry.property, shortName(object),
                ok and describe(value) or "<error>"))
        end)
        if touched == 0 then
            write(string.format("  [read] %s.%s: no live instances", entry.class, entry.property))
        end
    end

    for _, entry in ipairs(OBSERVED_CALLS) do
        local touched = eachInstance(entry.class, function(object)
            local ok, value = pcall(function() return object[entry.method](object) end)
            write(string.format("  [call] %s:%s on %s = %s",
                entry.class, entry.method, shortName(object),
                ok and describe(value) or "<error: " .. tostring(value) .. ">"))
        end)
        if touched == 0 then
            write(string.format("  [call] %s:%s: no live instances", entry.class, entry.method))
        end
    end
end

local function hookRefusal(functionName)
    if registeredHooks[functionName] then return true end

    local function log(phase, self, a, b, c)
        write(string.format("  [%s] %s | self=%s a=%s b=%s c=%s",
            phase, functionName, describe(self), describe(a), describe(b), describe(c)))
    end

    local ok, err = pcall(function()
        local preId, postId = RegisterHook(
            functionName,
            function(self, a, b, c) log("PRE ", self, a, b, c) end,
            function(self, a, b, c) log("POST", self, a, b, c) end
        )
        registeredHooks[functionName] = { preId = preId, postId = postId }
    end)
    if not ok then
        write(string.format("  [hook] %s: FAILED (%s)", functionName, tostring(err)))
    end
    return ok
end

local function watchRefusals()
    write("--- Registering refusal hooks ---")
    local registered = 0
    for _, functionName in ipairs(REFUSAL_HOOKS) do
        if hookRefusal(functionName) then registered = registered + 1 end
    end
    write(string.format("Refusal hooks active: %d/%d", registered, #REFUSAL_HOOKS))
end

local function runReport(target)
    reportSequence = reportSequence + 1
    if reportSequence == 1 then
        resetReport("-- MJOLNIR Co-op 8 --")
    else
        write("")
    end
    write(string.format("=== PASS %d @ %s ===", reportSequence, os.date("!%Y-%m-%dT%H:%M:%SZ")))
    observe("before")
    applyCaps(target)
    observe("after")
    write("Pass complete. The caps above are the client-reachable ones only; the Blam")
    write("simulation and the PlayFab lobby enforce their own. See docs/coop_player_cap.md.")
end

--- Retitle the frontend fireteam panel: "FIRETEAM 1/4" -> "FIRETEAM 1/<target>".
---
--- The live instance is found by filtering for /Engine/Transient. FindFirstOf on a
--- widget class returns the class-default archetype, whose sub-widget pointers are
--- null, and calling into one reads address 0x10 and takes the process down.
local function liveTransient(className)
    local out = {}
    for _, candidate in ipairs(FindAllOf(className) or {}) do
        if candidate and candidate:IsValid()
            and candidate:GetFullName():find("/Engine/Transient", 1, true) then
            out[#out + 1] = candidate
        end
    end
    return out
end

local function setFireteamHeader(target)
    local widget = liveTransient("WBP_SquadWidget_C")[1]
    if not widget then
        return false
    end

    local okHeader, header = pcall(function() return widget.FireteamHeader end)
    if not okHeader or not header then return false end
    local okValid, valid = pcall(function() return header:IsValid() end)
    if not okValid or not valid then return false end

    -- The count of real members, so the label stays honest about who is present.
    local present = 1
    local viewModel = FindFirstOf("MeteoriteSquadLobbyViewModel")
    if viewModel and viewModel:IsValid() then
        local ok, count = pcall(function() return viewModel.TotalPlayerCount end)
        if ok and type(count) == "number" and count > 0 then present = count end
    end

    local label = string.format("FIRETEAM %d/%d", present, target)
    local ok = pcall(function() header:SetText(FText(label)) end)
    return ok, label
end

--- Top the fireteam list up to `target` rows by appending blank ("INVITE +") items.
---
--- The items are outered to the ListView and carry FireteamRowType 2, matching the
--- blank rows the game builds itself. Adding is idempotent per tick: it only ever
--- appends the shortfall, so the panel settles at `target` instead of growing.
---
--- The count comes from GetNumItems, not from counting row widgets. Discarded row
--- widgets stay alive and findable after the panel rebuilds, so a FindAllOf tally
--- read 8 while the list actually held 4 - and the top-up concluded it had nothing
--- to do. That is why the rows vanished on the first menu transition.
local function topUpFireteamRows(target)
    local widget = liveTransient("WBP_SquadWidget_C")[1]
    if not widget then return 0 end
    local okLv, listView = pcall(function() return widget.SquadListView end)
    if not okLv or not listView then return 0 end
    local okValid, valid = pcall(function() return listView:IsValid() end)
    if not okValid or not valid then return 0 end

    local okCount, current = pcall(function() return listView:GetNumItems() end)
    if not okCount or type(current) ~= "number" then return 0 end
    if current == 0 or current >= target then return 0 end

    local itemClass = StaticFindObject("/Script/Meteorite.MeteoriteSquadLobbyViewItemData")
    if not itemClass or not itemClass:IsValid() then return 0 end

    local added = 0
    for _ = 1, (target - current) do
        local ok = pcall(function()
            local item = StaticConstructObject(itemClass, listView)
            if not item or not item:IsValid() then error("construct failed") end
            item.FireteamRowType = 2
            listView:AddItem(item)
        end)
        if not ok then break end
        added = added + 1
    end
    return added
end

-- Neither half of this holds on its own.
--
-- SetText reverts within about a second when the widget re-applies its binding,
-- and the added rows are discarded outright whenever the panel rebuilds - leaving
-- a menu transition is enough. Both were verified reverting on CU3. So the loop
-- re-asserts both, which is what makes the panel stay at 1/8 with eight slots.
--
-- This is presentation. The rows are inert: they add no player slot anywhere below
-- the UI, and TotalPlayerCount is untouched by them. A real second local player
-- (UGameplayStatics::CreatePlayer) makes the panel populate a genuine row on its
-- own, without any of this.
local uiTarget = nil
local uiLoopRunning = false

local function startFireteamUiLoop()
    if uiLoopRunning then return end
    uiLoopRunning = true
    local lastReported = nil
    LoopAsync(500, function()
        if not uiTarget then
            uiLoopRunning = false
            return true          -- stop the loop
        end
        local ok, label = setFireteamHeader(uiTarget)
        local added = topUpFireteamRows(uiTarget)
        -- Log transitions only. This runs twice a second; logging every pass would
        -- bury the report it shares a file with.
        if ok and label ~= lastReported then
            lastReported = label
            write(string.format("Fireteam panel: holding %s (%d row(s) added)", label, added))
        end
        return false
    end)
end

local function registerCommands()
    print("[MJOLNIR Coop8] Registering co-op cap commands...\n")

    RegisterConsoleCommandHandler("mjolnir_coop8_status", function()
        ExecuteInGameThread(function() observe("on demand") end)
        return true
    end)

    RegisterConsoleCommandHandler("mjolnir_coop8_ui", function(_, args)
        local requested = math.floor(tonumber(args and args[1] or "") or DEFAULT_TARGET)
        if requested == 0 then
            uiTarget = nil          -- the loop sees this and stops on its next tick
            print("[MJOLNIR Coop8] Fireteam label released; it reverts on the next refresh.\n")
            return true
        end
        if requested < 1 or requested > 32 then
            print("[MJOLNIR Coop8] Target must be between 1 and 32, or 0 to release.\n")
            return true
        end
        uiTarget = requested
        ExecuteInGameThread(startFireteamUiLoop)
        return true
    end)

    RegisterConsoleCommandHandler("mjolnir_coop8_raise", function(_, args)
        -- args[1], not args[2]: UE4SS passes the parameters *after* the command
        -- name, so args[2] silently read empty and every target fell back to 8.
        -- Floored because string.format("%d") raises on a non-integer float, and
        -- "mjolnir_coop8_raise 8.5" should not be the thing that breaks the module.
        local requested = math.floor(tonumber(args and args[1] or "") or DEFAULT_TARGET)
        if requested < 1 or requested > 32 then
            -- 32 is the size of the simulation's player datum array; asking for more
            -- than it can hold is a guaranteed no.
            print("[MJOLNIR Coop8] Target must be between 1 and 32.\n")
            return true
        end
        targetPlayers = requested
        ExecuteInGameThread(function() runReport(targetPlayers) end)
        return true
    end)

    RegisterConsoleCommandHandler("mjolnir_coop8_watch", function()
        ExecuteInGameThread(watchRefusals)
        return true
    end)

    ExecuteInGameThread(function() runReport(targetPlayers) end)
end

ExecuteInGameThreadWithDelay(5000, registerCommands)
print("[MJOLNIR Coop8] Module loaded.\n")

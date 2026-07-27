-- MJOLNIR Bridge
--
-- A remote control for the running game.
--
-- Everything the other MJOLNIR mods do has to be typed at the in-game console
-- by a person sitting in front of the game. That makes any experiment needing
-- more than a couple of steps -- load a level, spawn a weapon, read a value,
-- compare it against what the packer wrote -- slow and easy to get wrong.
--
-- This mod turns those steps into something a tool outside the process can
-- drive. It watches a request file, runs what it finds on the game thread, and
-- writes the answer back. The transport is deliberately files: UE4SS's Lua has
-- no sockets, and a file both sides can open needs nothing that is not already
-- there.
--
-- Wire format, both directions (LF only, body length in bytes so a body can
-- contain anything at all, including the header delimiter):
--
--     mjolnir-bridge 1
--     id 42
--     op lua              (requests only)
--     ok 1                (responses only)
--     bytes 17
--     --
--     print("hello")
--
-- Operations:
--   ping      -> current state, and proof the game thread is answering
--   console   -> run a UE console command through the local PlayerController
--   lua       -> compile and run Lua on the game thread, return what it printed
--
-- `lua` is the one that matters. Tag values, ammo counts and pawn state are all
-- reachable by reflection but not through any fixed command, so the useful
-- shape is an eval, not a menu of verbs. The sandbox persists between requests,
-- so a helper defined in one call is still there in the next.

local PROTOCOL = 1
local POLL_MS = 100          -- request latency; also the status heartbeat base
local STATUS_EVERY = 10      -- write status every N polls, so ~1s

--------------------------------------------------------------------------------
-- Paths
--------------------------------------------------------------------------------

--- Absolute path to the bridge directory, derived from this script's location.
---
--- Relative paths would depend on the process working directory, which is the
--- executable's folder rather than UE4SS's, and is not something a mod should
--- have to assume. `debug.getinfo` gives the one path that is always right.
local function bridgeDirectory()
    local source = debug.getinfo(1, "S").source or ""
    local path = source:gsub("^@", ""):gsub("/", "\\")
    -- <ue4ss>\Mods\MJOLNIRBridge\Scripts\main.lua -> <ue4ss>
    local root = path
    for _ = 1, 4 do
        root = root:match("^(.*)\\[^\\]*$") or root
    end
    return root .. "\\mjolnir-bridge\\"
end

local DIR = bridgeDirectory()
local REQUEST = DIR .. "request.txt"
local RESPONSE = DIR .. "response.txt"
local STATUS = DIR .. "status.txt"

--------------------------------------------------------------------------------
-- Wire format
--------------------------------------------------------------------------------

local function readFile(path)
    local f = io.open(path, "rb")
    if not f then return nil end
    local text = f:read("a")
    f:close()
    return text
end

--- Parse a message, or nil if it is not completely written yet.
---
--- The writer is another process, so a read can land mid-write. A short body is
--- how that shows up, and returning nil just means "try again next poll".
local function parseMessage(text)
    if not text then return nil end
    local headers, pos = {}, 1
    while true do
        local newline = text:find("\n", pos, true)
        if not newline then return nil end
        local line = text:sub(pos, newline - 1)
        pos = newline + 1
        if line == "--" then break end
        local key, value = line:match("^(%S+)%s*(.-)%s*$")
        if key then headers[key] = value end
    end
    local body = text:sub(pos)
    local want = tonumber(headers.bytes or "0") or 0
    if #body < want then return nil end
    return headers, body:sub(1, want)
end

local function writeMessage(path, headers, body)
    body = body or ""
    local f = io.open(path, "wb")
    if not f then return false end
    f:write("mjolnir-bridge ", tostring(PROTOCOL), "\n")
    for _, pair in ipairs(headers) do
        f:write(pair[1], " ", tostring(pair[2]), "\n")
    end
    f:write("bytes ", tostring(#body), "\n--\n", body)
    f:close()
    return true
end

--------------------------------------------------------------------------------
-- Reflection helpers, exposed to `lua` requests as `mj`
--------------------------------------------------------------------------------

local function safeName(object)
    if object == nil then return nil end
    local ok, name = pcall(function() return object:GetFullName() end)
    if ok and name then return name end
    return nil
end

local function describe(value)
    if value == nil then return "nil" end
    local kind = type(value)
    if kind == "string" or kind == "number" or kind == "boolean" then
        return tostring(value)
    end
    return safeName(value) or tostring(value)
end

local function playerController()
    local ok, controller = pcall(FindFirstOf, "PlayerController")
    if ok and controller and controller:IsValid() then return controller end
    local okAll, all = pcall(FindAllOf, "PlayerController")
    if okAll and all then
        for _, candidate in ipairs(all) do
            if candidate and candidate:IsValid() then return candidate end
        end
    end
    return nil
end

local function playerPawn()
    local controller = playerController()
    if not controller then return nil end
    local ok, pawn = pcall(function() return controller.Pawn end)
    if ok and pawn and pawn:IsValid() then return pawn end
    return nil
end

local function currentWorld()
    local controller = playerController()
    if controller then
        local ok, world = pcall(function() return controller:GetWorld() end)
        if ok and world and world:IsValid() then return world end
    end
    local okHelper, helpers = pcall(require, "UEHelpers")
    if okHelper and helpers and helpers.GetWorld then
        local ok, world = pcall(helpers.GetWorld)
        if ok and world and world:IsValid() then return world end
    end
    return nil
end

--- Every readable property of an object and its parent classes.
---
--- Returned as a table rather than printed so a caller can pick one value out
--- instead of parsing a dump. The class walk matters: what looks like a field
--- on a weapon is usually declared on a shared base.
local function properties(object)
    local values = {}
    if object == nil then return values end
    local okClass, class = pcall(function() return object:GetClass() end)
    if not okClass or not class or not class:IsValid() then return values end
    while class and class:IsValid() do
        pcall(function()
            class:ForEachProperty(function(property)
                local okName, name = pcall(function()
                    return property:GetFName():ToString()
                end)
                if not okName or not name or values[name] ~= nil then return end
                local okValue, value = pcall(function()
                    return object:GetPropertyValue(name)
                end)
                values[name] = okValue and describe(value) or "<unreadable>"
            end)
        end)
        local okSuper, super = pcall(function() return class:GetSuperStruct() end)
        class = (okSuper and super and super:IsValid()) and super or nil
    end
    return values
end

local function runConsole(command)
    command = (command or ""):gsub("^%s+", ""):gsub("%s+$", "")
    if command == "" then return false, "empty command" end

    local controller = playerController()
    if not controller then
        return false, "no live PlayerController -- the game is probably still at the menu"
    end

    local ok, err = pcall(function() controller:ConsoleCommand(command, true) end)
    if ok then return true, "dispatched: " .. command end

    local fallbackOk, fallbackErr = pcall(function()
        local library = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
        local world = controller:GetWorld()
        if not library or not world or not world:IsValid() then
            error("KismetSystemLibrary or live World unavailable")
        end
        library:ExecuteConsoleCommand(world, command, controller)
    end)
    if fallbackOk then return true, "dispatched via Kismet fallback: " .. command end

    return false, string.format("dispatch failed: %s | fallback: %s",
        tostring(err), tostring(fallbackErr))
end

--------------------------------------------------------------------------------
-- Sandbox for `lua` requests
--------------------------------------------------------------------------------

local realPrint = print

local sandbox = {}
sandbox.mj = {
    pc = playerController,
    pawn = playerPawn,
    world = currentWorld,
    props = properties,
    name = safeName,
    describe = describe,
    console = runConsole,
    find = function(className)
        local ok, objects = pcall(FindAllOf, className)
        return (ok and objects) or {}
    end,
}
setmetatable(sandbox, { __index = _G })

local function runLua(source)
    local output = {}
    sandbox.print = function(...)
        local parts = {}
        for i = 1, select("#", ...) do
            parts[#parts + 1] = tostring((select(i, ...)))
        end
        local line = table.concat(parts, "\t")
        output[#output + 1] = line
        realPrint(line .. "\n")
    end

    local chunk, compileError = load(source, "@mjolnir-bridge", "t", sandbox)
    if not chunk then
        return false, "compile error: " .. tostring(compileError)
    end

    local results = table.pack(pcall(chunk))
    if not results[1] then
        output[#output + 1] = "error: " .. tostring(results[2])
        return false, table.concat(output, "\n")
    end
    for i = 2, results.n do
        output[#output + 1] = "= " .. describe(results[i])
    end
    return true, table.concat(output, "\n")
end

--------------------------------------------------------------------------------
-- State, refreshed on the game thread and reported by the poll thread
--------------------------------------------------------------------------------

local state = {
    refreshed = 0,
    world = "?",
    pawn = "?",
    controller = "no",
}
local refreshInFlight = false

local function refreshState()
    refreshInFlight = false
    state.refreshed = os.time()
    local world = currentWorld()
    state.world = world and (safeName(world) or "?") or "none"
    local pawn = playerPawn()
    state.pawn = pawn and (safeName(pawn) or "?") or "none"
    state.controller = playerController() and "yes" or "no"
end

local served = 0
local pending = nil
local polls = 0

--- Human-readable state, and the answer to a `ping`.
---
--- `refreshed` is the load-bearing field: it is stamped on the game thread, so
--- a value far behind `now` means the game is hung or loading, which is not
--- something the poll thread could tell you on its own.
local function statusText()
    return table.concat({
        "protocol " .. PROTOCOL,
        "now " .. os.time(),
        "refreshed " .. state.refreshed,
        "polls " .. polls,
        "served " .. served,
        "controller " .. state.controller,
        "world " .. state.world,
        "pawn " .. state.pawn,
    }, "\n")
end

local function writeStatus()
    writeMessage(STATUS, { { "id", served } }, statusText())
end

--------------------------------------------------------------------------------
-- Request handling
--------------------------------------------------------------------------------

local function serve(id, op, payload)
    local ok, body
    if op == "ping" then
        refreshState()
        ok, body = true, statusText()
    elseif op == "console" then
        ok, body = runConsole(payload)
    elseif op == "lua" then
        ok, body = runLua(payload)
    else
        ok, body = false, "unknown op: " .. tostring(op)
    end

    writeMessage(RESPONSE, { { "id", id }, { "ok", ok and 1 or 0 } }, body)
    served = id
    pending = nil
end

local function serveSafely(id, op, payload)
    local ok, err = pcall(serve, id, op, payload)
    if not ok then
        -- Never leave `pending` set: one bad request would wedge the bridge for
        -- the rest of the session, and the caller would only see a timeout.
        writeMessage(RESPONSE, { { "id", id }, { "ok", 0 } },
            "bridge error: " .. tostring(err))
        served = id
        pending = nil
    end
end

--- Ignore whatever request file is lying around from a previous session.
---
--- Without this, the last command of the last run executes on startup, which is
--- both surprising and, if it was a level travel, disruptive.
local function adoptExistingRequest()
    local headers = parseMessage(readFile(REQUEST))
    local id = headers and tonumber(headers.id or "")
    if id then served = id end
end

local function start()
    adoptExistingRequest()
    writeStatus()

    LoopAsync(POLL_MS, function()
        polls = polls + 1

        if not pending then
            local headers, body = parseMessage(readFile(REQUEST))
            if headers then
                local id = tonumber(headers.id or "")
                if id and id ~= served then
                    pending = id
                    local op = headers.op or "ping"
                    ExecuteInGameThread(function() serveSafely(id, op, body) end)
                end
            end
        end

        if polls % STATUS_EVERY == 0 then
            if not refreshInFlight then
                refreshInFlight = true
                ExecuteInGameThread(refreshState)
            end
            writeStatus()
        end

        return false
    end)
end

RegisterConsoleCommandHandler("mjolnir_bridge", function()
    ExecuteInGameThread(function()
        refreshState()
        realPrint("[MJOLNIR Bridge] " .. DIR .. "\n")
        realPrint(statusText() .. "\n")
    end)
    return true
end)

start()
realPrint("[MJOLNIR Bridge] listening in " .. DIR .. "\n")

-- MJOLNIR Lobby: messages between the host and its fireteam.
--
-- Two of the engine's own PlayerController RPCs carry them, so no new
-- replicated class is needed (docs/multiplayer_postgame.md):
--
--   client -> host   ServerExecRPC(Msg). Its body is compiled out of a
--                    Shipping build, so it does nothing; the host's hook
--                    reads Msg, and `self` is the sender's controller.
--   host -> client   ClientMessage(S, Type, MsgLifeTime) with Type
--                    "MJOLNIR". The engine prints a message only for the
--                    types None and Say, so ours stays off screen; the
--                    client's hook reads S.
--
-- A message is "MJOLNIR|<verb>|<field>|<field>...". The host handles its
-- own messages directly, and sends to itself through ServerExecRPC like any
-- client, so one handler serves both.

local Net = {}

local PREFIX = "MJOLNIR|"
local TYPE = "MJOLNIR"
local handlers = {}
local hooked = false
-- The log notes each verb's traffic when it starts or changes, not every
-- message: the vote is sent every second.
local lastReceived, lastSent = {}, {}
local log = function(msg) print("[MJOLNIR Lobby] " .. tostring(msg) .. "\n") end

local function valid(o)
    local ok, v = pcall(function() return o and o:IsValid() end)
    return ok and v
end

local function isLocal(pc)
    local ok, yes = pcall(function() return pc:IsLocalController() end)
    return ok and yes
end

--- This machine runs the game the fireteam plays: the frontend's or the
--- map's game mode exists only on the host (and on a player alone).
function Net.isHost()
    local ok, yes = pcall(function()
        for _, pc in ipairs(FindAllOf("PlayerController") or {}) do
            if valid(pc) and isLocal(pc) then return pc:GetWorld().AuthorityGameMode:IsValid() end
        end
        return false
    end)
    return ok and yes == true
end

local function compose(verb, ...)
    local parts = { verb }
    for _, field in ipairs({ ... }) do
        parts[#parts + 1] = (tostring(field == nil and "" or field):gsub("[|\r\n]", "/"))
    end
    return PREFIX .. table.concat(parts, "|")
end

local function dispatch(text, sender)
    if type(text) ~= "string" or text:sub(1, #PREFIX) ~= PREFIX then return end
    local fields = {}
    for field in (text:sub(#PREFIX + 1) .. "|"):gmatch("([^|]*)|") do fields[#fields + 1] = field end
    local verb = table.remove(fields, 1)
    local handler = handlers[verb]
    if not handler then return end
    local now = os.clock()
    if not lastReceived[verb] or now - lastReceived[verb] > 30 then
        log("messages: " .. tostring(verb) .. " received" .. (sender and (" from " .. sender) or " from the host"))
    end
    lastReceived[verb] = now
    -- Off the RPC: screens must not be pushed from inside the call.
    ExecuteInGameThread(function()
        local ok, err = pcall(handler, fields, sender)
        if not ok then log("message " .. tostring(verb) .. ": " .. tostring(err)) end
    end)
end

--- Handle `verb`: fn(fields, sender), sender being the player's name for a
--- message to the host, nil for one from the host.
function Net.on(verb, fn)
    handlers[verb] = fn
end

function Net.hook()
    if hooked then return true end
    hooked = pcall(function()
        RegisterHook("/Script/Engine.PlayerController:ServerExecRPC", function(self, msg)
            local okM, text = pcall(function() return msg:get():ToString() end)
            if not okM or not Net.isHost() then return end
            local sender = "?"
            pcall(function() sender = self:get().PlayerState:GetPlayerName():ToString() end)
            dispatch(text, sender)
        end)
        RegisterHook("/Script/Engine.PlayerController:ClientMessage", function(_, s, kind)
            local okK, name = pcall(function() return kind:get():ToString() end)
            if not okK or name ~= TYPE or Net.isHost() then return end
            local okS, text = pcall(function() return s:get():ToString() end)
            if okS then dispatch(text, nil) end
        end)
    end)
    if not hooked then log("messages: could not hook the controller RPCs") end
    return hooked
end

--- To the host (from the host too).
function Net.toHost(verb, ...)
    local msg = compose(verb, ...)
    for _, pc in ipairs(FindAllOf("PlayerController") or {}) do
        if valid(pc) and isLocal(pc) then
            pcall(function() pc:ServerExecRPC(msg) end)
            return
        end
    end
end

--- To every connected fireteam client. A controller left over from the
--- previous world has no player and no player state; a client RPC on one
--- with no connection would run here, on the host.
function Net.toClients(verb, ...)
    local msg = compose(verb, ...)
    local sent = 0
    for _, pc in ipairs(FindAllOf("PlayerController") or {}) do
        if valid(pc) and not isLocal(pc) then
            local ok = pcall(function()
                if not (valid(pc.Player) and valid(pc.PlayerState)) then error("not connected") end
                pc:ClientMessage(msg, FName(TYPE), 0)
            end)
            if ok then sent = sent + 1 end
        end
    end
    if lastSent[verb] ~= sent then
        lastSent[verb] = sent
        log(string.format("messages: %s to %d client(s)", verb, sent))
    end
    return sent
end

return Net

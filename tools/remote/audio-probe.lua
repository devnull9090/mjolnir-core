-- Audio-role probe: who a game thinks each player's biped belongs to.
--
-- Loaded into the MJOLNIR bridge's Lua sandbox on either PC
-- (node tools/remote/remote.mjs probe load, or game_lua with this file), it
-- defines AudioProbe and keeps it between calls. A sample records what the
-- exe's HaloAudio layer reads when it decides whether a sound is the local
-- player's own (docs/re/client_sound_roles.md): every PlayerState's
-- BlamAbsolutePlayerIndex, the local pawn and its player, and each Spartan
-- biped's and first-person weapon actor's Owner chain, controlling player and
-- object ids. Lines go to <ue4ss>\mjolnir-bridge\audio-probe.log, which the
-- agent serves (root ue4ss), and to the bridge's print output when asked.
--
--   AudioProbe.start("jip", 60, 1000)   one sample a second for 60 s, on the game thread
--   AudioProbe.mark("reload pressed")   a marker line, for lining up with what was heard
--   AudioProbe.snapshot("now", true)    one sample, also printed
--   AudioProbe.stop()
AudioProbe = AudioProbe or {}
local P = AudioProbe

-- The bridge's folder, from the path of a function the bridge defined.
if not P.path then
    local source = ""
    pcall(function() source = debug.getinfo(mj.pc, "S").source or "" end)
    local path = source:gsub("^@", ""):gsub("/", "\\")
    for _ = 1, 4 do path = path:match("^(.*)\\[^\\]*$") or path end
    P.path = path .. "\\mjolnir-bridge\\audio-probe.log"
end

local function short(o)
    local ok, full = pcall(function() return o:GetFullName() end)
    if not ok or not full then return "?" end
    -- "BP_X_C /Game/...:PersistentLevel.BP_X_C_123" -> "BP_X_C_123"
    -- "MeteoriteLocalPlayer /Engine/Transient.GameEngine_1:MeteoriteLocalPlayer_2" -> "MeteoriteLocalPlayer_2"
    return full:match("[%.:]([%w_]+)$") or full
end

local function valid(o)
    local ok, v = pcall(function() return o and o:IsValid() end)
    return ok and v
end

local function ownerChain(a)
    local parts, cur = {}, a
    for _ = 1, 6 do
        if not valid(cur) then break end
        parts[#parts + 1] = short(cur)
        local ok, own = pcall(function() return cur.Owner end)
        if not ok then break end
        cur = own
    end
    return table.concat(parts, "<-")
end

local AC = StaticFindObject("/Script/Engine.ActorComponent")
local function components(a)
    local list = {}
    local ok, cs = pcall(function() return a:K2_GetComponentsByClass(AC) end)
    if not ok or not cs then return list end
    for _, c in ipairs(cs) do
        local o = c
        if type(c.get) == "function" then o = c:get() end
        if valid(o) then list[#list + 1] = o end
    end
    return list
end

local function bipedLine(a)
    local ctl, any, idx, gsid = "?", "?", "?", "?"
    for _, c in ipairs(components(a)) do
        local full = c:GetFullName()
        if full:find("BlamUnitComponent") then
            pcall(function() ctl = c:GetControllingPlayerDatumIndex() end)
            pcall(function() any = tostring(c:IsControlledByAnyPlayer()) end)
        elseif full:find("BlamObjectSynchronizationComponent") then
            pcall(function() idx = c.BlamObjectIndex end)
            pcall(function() gsid = c.BlamObjectGameStateIdentifier end)
        end
    end
    -- A controlling player datum's low 16 bits are the Blam player index.
    local player = type(ctl) == "number" and ctl ~= -1 and (ctl & 0xffff) or -1
    return string.format("BIPED %s owner=%s player=%d ctl=%s any=%s idx=%s gsid=%s",
        short(a), ownerChain(a), player, tostring(ctl), any, tostring(idx), tostring(gsid))
end

function P.sample(label)
    local out = {}
    local pc = mj.pc()
    local pawn = valid(pc) and pc.Pawn or nil
    local ps = valid(pc) and pc.PlayerState or nil
    out[#out + 1] = string.format("t=%d clock=%.2f label=%s world=%s", os.time(), os.clock(), tostring(label),
        valid(mj.world()) and short(mj.world()) or "?")
    out[#out + 1] = string.format("PC %s player=%s pawn=%s pawnOwner=%s ps=%s",
        valid(pc) and short(pc) or "nil", valid(pc) and valid(pc.Player) and short(pc.Player) or "nil",
        valid(pawn) and short(pawn) or "nil", valid(pawn) and ownerChain(pawn.Owner) or "nil",
        valid(ps) and short(ps) or "nil")
    pcall(function()
        local players = pc:GetWorld().GameState.PlayerArray
        local lines = {}
        players:ForEach(function(_, el)
            local p = el:get()
            local index, name = "?", "?"
            pcall(function() index = p.BlamPlayerStateComponent.BlamAbsolutePlayerIndex end)
            pcall(function() name = p:GetPlayerName():ToString() end)
            local mine = valid(ps) and p:GetFullName() == ps:GetFullName()
            lines[#lines + 1] = string.format("%s:%s:%s%s", short(p), name, tostring(index), mine and ":local" or "")
        end)
        out[#out + 1] = "PLAYERS " .. table.concat(lines, " ")
    end)
    local bipeds = {}
    pcall(function() bipeds = FindAllOf("BP_SpartansBipedActor_C") or {} end)
    for _, a in ipairs(bipeds) do
        if valid(a) then out[#out + 1] = bipedLine(a) end
    end
    pcall(function()
        for _, a in ipairs(FindAllOf("BlamObjectActor") or {}) do
            if valid(a) and a:GetFullName():find("BP_FP_") then
                out[#out + 1] = string.format("FP %s owner=%s", short(a), ownerChain(a))
            end
        end
    end)
    return out
end

local function append(lines)
    local f = io.open(P.path, "a")
    if not f then return false end
    f:write(table.concat(lines, "\n"), "\n--\n")
    f:close()
    return true
end

function P.snapshot(label, show)
    local lines = P.sample(label or "snapshot")
    local ok = append(lines)
    if show then print(table.concat(lines, "\n")) end
    if not ok then print("audio-probe: cannot write " .. P.path) end
    return lines
end

function P.mark(text)
    append({ string.format("t=%d clock=%.2f MARK %s", os.time(), os.clock(), tostring(text)) })
end

P.run = P.run or 0

function P.stop()
    P.stopAt = 0
    P.run = P.run + 1
end

--- Sample every `everyMs` (default 1000) for `seconds` (default 60), on the game thread.
---
--- One persistent function re-armed with ExecuteInGameThreadWithDelay, as the
--- shipped mods' `every` loops do. A LoopAsync that queued a fresh closure to
--- the game thread each tick lost its registry ref after a few minutes
--- ("[Lua::Registry::get_function_ref] Ref was not function") and took the
--- bridge's own poll loop down with it (2026-10-24, PC 1).
function P.start(label, seconds, everyMs)
    P.label = label or "run"
    P.stopAt = os.clock() + (seconds or 60)
    P.run = P.run + 1
    local run = P.run
    local every = everyMs or 1000
    P.mark("start " .. P.label)
    local function tick()
        if run ~= P.run then return end          -- a newer start or a stop took over
        if os.clock() >= P.stopAt then
            P.mark("stop " .. P.label)
            return
        end
        local ok, err = pcall(P.snapshot, P.label, false)
        if not ok then append({ "ERROR " .. tostring(err) }) end
        ExecuteInGameThreadWithDelay(every, tick)
    end
    ExecuteInGameThreadWithDelay(every, tick)
    return "sampling '" .. P.label .. "' to " .. P.path
end

print("AudioProbe ready: " .. P.path)

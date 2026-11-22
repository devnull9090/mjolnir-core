-- Pelican Warfare: while a reinforcement rider waits in their team's parked
-- Pelican, the view follows a teammate on the ground; it comes back to the
-- cabin a few seconds before the wave leaves.
--
-- Unreal does the following: one CameraActor attached behind the teammate's
-- biped actor follows it with no Lua loop, and the player controller's view
-- target switches to it (SetViewTargetWithBlend, as FlyCam and the bench do).
-- This module only decides, twice a second with the HUD's snapshot, whom to
-- watch, and attaches or restores. Restoring is the default: any tick that is
-- not "fresh snapshot, my player seated, wave parked" puts the view back.
-- A biped actor handle is checked (IsValid, and the same player index through
-- bipedAt) before every use: a freed handle crashes past pcall.
--
-- The game hides actors outside its own player's view (that player sits in a
-- Pelican far away), so the watched body would be missing from the shot. It is
-- un-hidden while watched, re-applied each update in case the game hides it
-- again. Nothing hides it afterwards: the game's own culling decides that, and
-- forcing it hidden could leave a teammate invisible the game meant to show.
local Spectate = {}

-- Hand the view back this many seconds before the wave leaves (the HUD ticks
-- at 2 Hz, so the departure itself must never be watched from outside).
Spectate.RETURN_BEFORE = 3
-- The chase camera, relative to the watched biped: behind, above, looking down.
Spectate.OFFSET = { X = -450, Y = 0, Z = 220 }
Spectate.PITCH = -14
local BLEND_IN, BLEND_OUT = 0.6, 0.35
local SNAP, KEEP_WORLD = 2, 1 -- EAttachmentRule

-- Stages a watchable teammate can be in: on foot (ground, landed, failed).
local ON_FOOT = { [0] = true, [5] = true, [6] = true }

--- Whether this snapshot wants the local player spectating: their row is
--- seated (2) in combat and the reinforcement wave is parked long enough.
function Spectate.wanted(s, me, wave)
    local p = s and s.players and s.players[me]
    return p ~= nil and p.localUser >= 0 and s.phase == 2 and p.stage == 2
        and wave ~= nil and not wave.flying and wave.departs > Spectate.RETURN_BEFORE
end

--- Teammates to watch, in a stable order: same team, on foot, not me.
function Spectate.candidates(s, me)
    local mine = s and s.players and s.players[me]
    local out = {}
    if not mine then return out end
    for index = 0, 15 do
        local p = s.players[index]
        if index ~= me and p and p.team == mine.team and ON_FOOT[p.stage] then out[#out + 1] = index end
    end
    return out
end

-- deps.bipedAt(player, index) -> at, body, biped (markers.lua); deps.camera(world)
-- makes the camera actor (defaults to spawning an Engine CameraActor).
function Spectate.new(deps)
    local self = {}
    local camera, previous, watching, lastPc
    local name = deps.FName or FName

    local function valid(o) return o ~= nil and o:IsValid() end

    local function makeCamera(world)
        if deps.camera then return deps.camera(world) end
        local class = StaticFindObject("/Script/Engine.CameraActor")
        return world:SpawnActor(class, { X = 0, Y = 0, Z = 0 }, { Pitch = 0, Yaw = 0, Roll = 0 })
    end

    local function show(body)
        pcall(function() body:SetActorHiddenInGame(false) end)
    end

    --- Put the view back where it was (the pawn, normally) and let go of the target.
    function self.restore(pc)
        pc = pc or lastPc
        if watching == nil then return end
        watching = nil
        pcall(function()
            if valid(camera) then camera:K2_DetachFromActor(KEEP_WORLD, KEEP_WORLD, KEEP_WORLD) end
        end)
        pcall(function()
            if not valid(pc) then return end
            local back = valid(previous) and previous or pc.Pawn
            if valid(back) then pc:SetViewTargetWithBlend(back, BLEND_OUT, 0, 0, false) end
        end)
        previous = nil
    end

    --- The watched index, or nil. `players` is match.players (absolute index).
    function self.watching() return watching end

    local function same(a, b)
        local ok, equal = pcall(function() return valid(a) and valid(b) and a:GetAddress() == b:GetAddress() end)
        return ok and equal
    end

    function self.update(pc, s, me, players, wave, hidden)
        if valid(pc) then lastPc = pc end
        if hidden or not valid(pc) or not Spectate.wanted(s, me, wave) then return self.restore(pc) end
        -- Keep the current teammate while they stay a candidate with the same body.
        local order = Spectate.candidates(s, me)
        local pick, body
        for i, index in ipairs(order) do
            if index == watching then table.remove(order, i); table.insert(order, 1, index); break end
        end
        for _, index in ipairs(order) do
            local _, _, biped = deps.bipedAt(players and players[index], index)
            if valid(biped) then pick, body = index, biped; break end
        end
        if not pick then return self.restore(pc) end
        local world = pc:GetWorld()
        if not valid(world) then return self.restore(pc) end
        if not valid(camera) then camera = makeCamera(world) end
        if not valid(camera) then return self.restore(pc) end
        show(body)
        if pick == watching and same(camera:GetAttachParentActor(), body) then return end
        camera:K2_AttachToActor(body, name("None"), SNAP, SNAP, KEEP_WORLD, false)
        camera:K2_SetActorRelativeLocation(Spectate.OFFSET, false, {}, false)
        camera:K2_SetActorRelativeRotation({ Pitch = Spectate.PITCH, Yaw = 0, Roll = 0 }, false, {}, false)
        if watching == nil then
            local ok, current = pcall(function() return pc:GetViewTarget() end)
            previous = ok and current or nil
            pc:SetViewTargetWithBlend(camera, BLEND_IN, 0, 0, false)
        end
        watching = pick
    end

    return self
end

return Spectate

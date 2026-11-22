-- lua tools/tests/test_warfare_spectate.lua
local Spectate = dofile("mods/MJOLNIRHud/Scripts/warfare_spectate.lua")
local function eq(a, b, what) assert(a == b, (what or "value") .. ": " .. tostring(a) .. " ~= " .. tostring(b)) end

local parked = { flying = false, departs = 20 }
local function snap(rows)
    local s = { phase = 2, players = {} }
    for index, row in pairs(rows) do
        s.players[index] = { index = index, team = row[1], stage = row[2], localUser = row[3] or -1 }
    end
    return s
end

-- When: seated in a parked wave, with time to spare.
local s = snap({ [0] = { 0, 2, 0 }, [1] = { 0, 5 }, [2] = { 1, 0 }, [3] = { 0, 2 }, [4] = { 0, 0 } })
eq(Spectate.wanted(s, 0, parked), true)
eq(Spectate.wanted(s, 0, { flying = true, departs = 50 }), false, "not once the wave flies")
eq(Spectate.wanted(s, 0, { flying = false, departs = 3 }), false, "handed back before departure")
eq(Spectate.wanted(s, 0, nil), false, "no waves on this map")
eq(Spectate.wanted(snap({ [0] = { 0, 5, 0 } }), 0, parked), false, "on foot: own view")
eq(Spectate.wanted(nil, 0, parked), false, "no fresh snapshot: own view")

-- Whom: teammates on foot, never the enemy, never another rider.
local list = Spectate.candidates(s, 0)
eq(#list, 2); eq(list[1], 1); eq(list[2], 4)

-- The camera: attached to the teammate, view switched once, restored to what it was.
local function actor(address, alive)
    local a = { address = address, alive = alive ~= false, bHidden = true }
    function a:IsValid() return self.alive end
    function a:SetActorHiddenInGame(h) self.bHidden = h end
    function a:GetAddress() return self.address end
    return a
end
local log = {}
local camera = actor(900)
function camera:K2_AttachToActor(parent) self.parent = parent; log[#log + 1] = "attach " .. parent.address end
function camera:K2_DetachFromActor() self.parent = nil; log[#log + 1] = "detach" end
function camera:K2_SetActorRelativeLocation() end
function camera:K2_SetActorRelativeRotation() end
function camera:GetAttachParentActor() return self.parent end
local pawn = actor(1)
local pc = actor(2)
pc.Pawn = pawn
pc.view = pawn
function pc:GetWorld() return actor(3) end
function pc:GetViewTarget() return self.view end
function pc:SetViewTargetWithBlend(target) self.view = target; log[#log + 1] = "view " .. target.address end

local bodies = { [1] = actor(101), [4] = actor(104) }
local players = { [1] = { name = "rosa" }, [4] = { name = "kai" } }
local spectate = Spectate.new({
    camera = function() return camera end,
    FName = function(n) return n end,
    bipedAt = function(p, index)
        local body = p and bodies[index]
        if body and body:IsValid() then return {}, body, body end
        return nil
    end,
})
spectate.update(pc, s, 0, players, parked, false)
eq(spectate.watching(), 1); eq(pc.view, camera, "watching through the camera"); eq(camera.parent, bodies[1])
eq(bodies[1].bHidden, false, "the watched body is drawn even far from the player")
local before = #log
spectate.update(pc, s, 0, players, parked, false)
eq(#log, before, "same teammate, same body: nothing to do")

-- The watched teammate's body goes (death, a pooled actor): the next one, never the stale handle.
bodies[1].alive = false
spectate.update(pc, s, 0, players, parked, false)
eq(spectate.watching(), 4); eq(camera.parent, bodies[4])
eq(pc.view, camera, "the view stays on the camera while switching teammates")

-- Departure close: the view comes back to the pawn and the camera lets go.
spectate.update(pc, s, 0, players, { flying = false, departs = 2 }, false)
eq(spectate.watching(), nil); eq(pc.view, pawn); eq(camera.parent, nil)
eq(bodies[4].bHidden, false, "nothing forces it hidden again: the game's culling decides")

-- Nobody to watch: the cabin view is left alone.
bodies[4].alive = false
log = {}
spectate.update(pc, s, 0, players, parked, false)
eq(spectate.watching(), nil); eq(#log, 0, "no view change without a teammate")

-- Hidden HUD or the match over: restore.
bodies[4].alive = true
spectate.update(pc, s, 0, players, parked, false); eq(pc.view, camera)
spectate.update(pc, s, 0, players, parked, true); eq(pc.view, pawn, "hidden restores")
spectate.update(pc, s, 0, players, parked, false); eq(pc.view, camera)
spectate.restore(); eq(pc.view, pawn, "restore without a controller uses the last one")
print("warfare spectate: ok")

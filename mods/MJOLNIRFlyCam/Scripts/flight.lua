-- Camera motion, modelled on the Forge Monitor: fly where you look, strafe
-- level, jump/crouch keys straight up and down, with a short ease in and out
-- so starts and stops do not jerk. Pure Lua (tools/tests/test_flycam_shots.lua).

local Flight = {}

Flight.DEFAULT_SPEED = 750.0   -- cm/s; the Monitor flies about 660-820
Flight.MIN_SPEED = 50.0
Flight.MAX_SPEED = 20000.0
Flight.BOOST = 3.0
Flight.SLOW = 0.25
Flight.RESPONSE = 9.0          -- 1/s: how quickly velocity reaches the target
Flight.MIN_FOV = 5.0
Flight.MAX_FOV = 170.0

local function rad(deg) return deg * (math.pi / 180.0) end

function Flight.forward(rot)
    local p, y = rad(rot.Pitch), rad(rot.Yaw)
    return { X = math.cos(p) * math.cos(y), Y = math.cos(p) * math.sin(y), Z = math.sin(p) }
end

function Flight.right(rot)
    local y = rad(rot.Yaw + 90.0)
    return { X = math.cos(y), Y = math.sin(y), Z = 0.0 }
end

function Flight.new()
    return { vel = { X = 0.0, Y = 0.0, Z = 0.0 } }
end

function Flight.stop(state)
    state.vel = { X = 0.0, Y = 0.0, Z = 0.0 }
end

--- Camera-relative offset (forward, right, up in cm) as a world vector.
function Flight.offset(rot, fwd, right, up)
    local f, r = Flight.forward(rot), Flight.right(rot)
    return {
        X = f.X * fwd + r.X * right,
        Y = f.Y * fwd + r.Y * right,
        Z = f.Z * fwd + up,
    }
end

--- Advance one frame. axes: fwd/right/up in -1..1; speed in cm/s. Returns the
--- world displacement for this frame.
function Flight.step(state, rot, axes, speed, dt)
    local target = Flight.offset(rot, axes.fwd or 0, axes.right or 0, axes.up or 0)
    local len = math.sqrt(target.X ^ 2 + target.Y ^ 2 + target.Z ^ 2)
    if len > 1 then
        target.X, target.Y, target.Z = target.X / len, target.Y / len, target.Z / len
    end
    local blend = 1.0 - math.exp(-Flight.RESPONSE * dt)
    local v = state.vel
    v.X = v.X + (target.X * speed - v.X) * blend
    v.Y = v.Y + (target.Y * speed - v.Y) * blend
    v.Z = v.Z + (target.Z * speed - v.Z) * blend
    if len == 0 and (v.X ^ 2 + v.Y ^ 2 + v.Z ^ 2) < 1.0 then Flight.stop(state) end
    return { X = state.vel.X * dt, Y = state.vel.Y * dt, Z = state.vel.Z * dt }
end

function Flight.clampSpeed(s)
    return math.max(Flight.MIN_SPEED, math.min(Flight.MAX_SPEED, s))
end

function Flight.clampFov(f)
    return math.max(Flight.MIN_FOV, math.min(Flight.MAX_FOV, f))
end

--- Pitch stays short of straight up/down; yaw wraps to -180..180.
function Flight.normalizeRot(rot)
    rot.Pitch = math.max(-89.0, math.min(89.0, rot.Pitch))
    rot.Yaw = (rot.Yaw + 180.0) % 360.0 - 180.0
    return rot
end

return Flight

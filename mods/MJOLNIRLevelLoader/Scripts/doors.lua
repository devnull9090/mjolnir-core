--- Halo 2 doors opened by their controls (Zanzibar's house gate and keypad).
---
--- A level's `doors` (tools/level/h2_physics_props.py doors.json, from the
--- map's own tags: crate::h2::door) name each door's parts (decor actors, a
--- mesh a moving node of the door), every part's world transform at every
--- frame of Halo 2's `device:position` animation (x and z axes, translation
--- in cm, about the world origin), the seconds the opening takes, where its
--- control stands and its sounds. Pressing the interact key (E) within reach
--- of the control, or the console command `mjolnir_door`, opens a closed
--- door and closes an open one, as Halo 2's keypad toggles its device
--- group. The door runs between the frames at Halo 2's speed.
---
--- Drawn on this machine only: the simulation has no device of its own for
--- it, so another player does not see it move, and it has no collision.
local Doors = {}

--- deps: Log, Current, findObject, resolveMesh, getWorld, gameVolume.
function Doors.new(d)
    local self = { doors = nil, world = nil }
    local REACH_CM = 220.0

    local function build()
        local list = d.Current.level and d.Current.level.doors
        if type(list) ~= "table" then return {} end
        local out = {}
        for _, spec in ipairs(list) do
            local door = { spec = spec, p = 0.0, target = 0.0, parts = {}, playing = false }
            for _, part in ipairs(spec.parts or {}) do
                door.parts[#door.parts + 1] = { spec = part }
            end
            out[#out + 1] = door
        end
        return out
    end

    local function sound(world, group, at)
        if type(group) ~= "table" or type(group.paths) ~= "table" or #group.paths == 0 then return end
        local statics = d.findObject("/Script/Engine.Default__GameplayStatics")
        local wave = d.resolveMesh(group.paths[math.random(#group.paths)])
        local volume = (tonumber(group.gain) or 1.0) * (d.gameVolume and d.gameVolume("ambient") or 1.0)
        if not (statics and wave) or volume <= 0 then return end
        pcall(function()
            statics:SpawnSoundAtLocation(world, wave, { X = at[1], Y = at[2], Z = at[3] },
                { Pitch = 0, Yaw = 0, Roll = 0 }, math.min(1.0, volume * 3.0), 1.0, 0.0, nil, nil, true)
        end)
    end

    --- Toggle the nearest door whose control is within reach of the local
    --- player (any door at all when `any`, for the console).
    function self.press(any)
        local world = d.getWorld()
        if not world then return end
        if self.world ~= d.Current.worldName then
            self.world, self.doors = d.Current.worldName, build()
        end
        local pawn
        pcall(function() pawn = FindFirstOf("PlayerController"):K2_GetPawn() end)
        local here = pawn and pawn:IsValid() and pawn:K2_GetActorLocation()
        for _, door in ipairs(self.doors or {}) do
            local c = door.spec.control_cm
            local near = false
            if here and type(c) == "table" then
                local dx, dy, dz = here.X - c[1], here.Y - c[2], here.Z - c[3]
                near = dx * dx + dy * dy + dz * dz < REACH_CM * REACH_CM
            end
            if near or any then
                door.target = door.target > 0.5 and 0.0 or 1.0
                if type(c) == "table" then sound(world, door.spec.sounds and door.spec.sounds.press, c) end
                local key = door.target > 0.5 and "open" or "close"
                local s = door.spec.sounds or {}
                sound(world, s[key] or s.open, door.spec.at_cm or c or { 0, 0, 0 })
                d.Log(string.format("door: %s %s", tostring(door.spec.asset):match("[^\\]+$") or "?",
                    door.target > 0.5 and "opening" or "closing"))
                return true
            end
        end
        return false
    end

    local function lerp(a, b, t)
        return { a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t }
    end

    --- Move every door toward its target and pose its parts; `dt` seconds.
    function self.tick(dt)
        if self.world ~= d.Current.worldName then
            self.world, self.doors = d.Current.worldName, build()
        end
        local math_lib = d.findObject("/Script/Engine.Default__KismetMathLibrary")
        for _, door in ipairs(self.doors or {}) do
            local seconds = math.max(0.1, tonumber(door.spec.seconds) or 1.0)
            local before = door.p
            if door.p < door.target then
                door.p = math.min(door.target, door.p + dt / seconds)
            elseif door.p > door.target then
                door.p = math.max(door.target, door.p - dt / seconds)
            end
            local moved = door.p ~= before or not door.posed
            if moved then
                door.posed = true
                if before < 1.0 and door.p >= 1.0 then
                    local s = door.spec.sounds or {}
                    sound(d.getWorld(), s.opened, door.spec.at_cm or { 0, 0, 0 })
                end
                for _, part in ipairs(door.parts) do
                    local actor = d.Current.actors and d.Current.actors[part.spec.id]
                    if actor and actor:IsValid() then
                        if not part.rest then
                            local l = actor:K2_GetActorLocation()
                            part.rest = { l.X, l.Y, l.Z }
                        end
                        local frames = part.spec.frames
                        local n = #frames
                        local f = door.p * (n - 1)
                        local i = math.min(n - 1, math.floor(f))
                        local t = f - i
                        local a, b = frames[i + 1], frames[math.min(n, i + 2)]
                        local x, z, tr = lerp(a.x, b.x, t), lerp(a.z, b.z, t), lerp(a.t, b.t, t)
                        -- y = z x x: the rotation's columns, applied to the
                        -- part's rest position (its actor origin).
                        local y = { z[2] * x[3] - z[3] * x[2], z[3] * x[1] - z[1] * x[3], z[1] * x[2] - z[2] * x[1] }
                        local r = part.rest
                        local loc = {
                            X = x[1] * r[1] + y[1] * r[2] + z[1] * r[3] + tr[1],
                            Y = x[2] * r[1] + y[2] * r[2] + z[2] * r[3] + tr[2],
                            Z = x[3] * r[1] + y[3] * r[2] + z[3] * r[3] + tr[3],
                        }
                        pcall(function()
                            local rot = math_lib:MakeRotFromXZ({ X = x[1], Y = x[2], Z = x[3] }, { X = z[1], Y = z[2], Z = z[3] })
                            actor:K2_SetActorLocationAndRotation(loc, rot, false, d.Current.emptyHit(), false)
                        end)
                    end
                end
            end
        end
    end

    return self
end

return Doors

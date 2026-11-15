--- Halo 2 doors (Zanzibar's house gate), opened in the simulation.
---
--- A level's `doors` (tools/level/h2_physics_props.py doors.json, from the
--- map's own tags: crate::h2::door, h2_door_machines.py) name each door's
--- parts (decor actors, a mesh a moving node of the door) with every part's
--- world transform at every frame of Halo 2's opening, and the door's
--- `machines`: device machines of the simulation's own, cloned from B40's
--- elevator, one a sliding part, that carry its collision. The door's
--- control (B40's switch at the keypad) shares their device group, so a
--- player pressing it opens the door in the simulation, for every player in
--- the match, collision and all. This module only draws it: it hides the
--- elevators the machines would draw and poses the door's meshes from how far
--- the machines' parts have moved (`progress`: the largest part offset over
--- the largest travel; the machines all stand at the door's origin), easing
--- between the frames at Halo 2's speed while they move. Halo 2's sounds play
--- as it starts, and as it finishes opening.
local Doors = {}

Doors.NEAR_CM = 40
Doors.SCAN_S = 2.0
Doors.CONTROL_CLASS = "BP_FR_ControlPanel_C"
--- Poll the machines this often (ms) while the door stands still, every
--- 33 ms while it moves: nine machines' two locations at 30 Hz, all the
--- time, were garbage the collector paid for in 10-15 ms frames.
Doors.IDLE_MS = 150
Doors.MOVING_MS = 33

--- deps: Log, Current, findObject, resolveMesh, getWorld, gameVolume.
function Doors.new(d)
    local self = { doors = nil, world = nil }

    local function build()
        local list = d.Current.level and d.Current.level.doors
        if type(list) ~= "table" then return {} end
        local out = {}
        for _, spec in ipairs(list) do
            local travel = 0
            for _, m in ipairs(spec.machines or {}) do
                local t = m.travel_cm or { 0, 0, 0 }
                travel = math.max(travel, math.sqrt(t[1] * t[1] + t[2] * t[2] + t[3] * t[3]))
            end
            out[#out + 1] = { spec = spec, p = 0.0, target = 0.0, parts = {}, actors = {}, travel = travel,
                last = 0.0, seek = -100 }
            for _, part in ipairs(spec.parts or {}) do
                out[#out].parts[#out[#out].parts + 1] = { spec = part }
            end
        end
        return out
    end

    local function sound(group, at)
        if type(group) ~= "table" or type(group.paths) ~= "table" or #group.paths == 0 or not at then return end
        local world = d.getWorld()
        local statics = d.findObject("/Script/Engine.Default__GameplayStatics")
        local wave = d.resolveMesh(group.paths[math.random(#group.paths)])
        local volume = (tonumber(group.gain) or 1.0) * (d.gameVolume and d.gameVolume("ambient") or 1.0)
        if not (world and statics and wave) or volume <= 0 then return end
        pcall(function()
            statics:SpawnSoundAtLocation(world, wave, { X = at[1], Y = at[2], Z = at[3] },
                { Pitch = 0, Yaw = 0, Roll = 0 }, math.min(1.0, volume * 3.0), 1.0, 0.0, nil, nil, true)
        end)
    end

    --- The door's control: B40's switch panel stands at Halo 2's keypad (the
    --- simulation's control a player presses); the keypad's own mesh is
    --- decor, so the panel's components (its meshes and sparks) are hidden,
    --- its device left working. The actor's own hidden flag is reset by the
    --- game; the components' stay, and are set again at every scan.
    local function hide_control(door)
        local c = door.spec.sim_control and door.spec.sim_control.at_cm
        if not c then return end
        if not door.panel and (door.panel_tries or 0) < 15 then
            door.panel_tries = (door.panel_tries or 0) + 1
            local scene = d.findObject("/Script/Engine.SceneComponent")
            for _, a in ipairs(FindAllOf(Doors.CONTROL_CLASS) or {}) do
                local ok, l = pcall(function() return a:K2_GetActorLocation() end)
                if ok and l and math.abs(l.X - c[1]) + math.abs(l.Y - c[2]) + math.abs(l.Z - c[3]) < Doors.NEAR_CM then
                    door.panel = {}
                    pcall(function()
                        for _, comp in ipairs(a:K2_GetComponentsByClass(scene)) do
                            door.panel[#door.panel + 1] = comp:get()
                        end
                    end)
                end
            end
        end
        for _, comp in ipairs(door.panel or {}) do
            pcall(function() comp:SetHiddenInGame(true, false) end)
        end
    end

    --- The door's machines' actors: every actor of their class standing at
    --- the door's origin, its elevator mesh hidden.
    local function bind(door, now)
        local want = #(door.spec.machines or {})
        if want == 0 or now - door.seek < Doors.SCAN_S then return end
        door.seek = now
        hide_control(door)
        if #door.actors >= want then return end
        local m = door.spec.machines[1]
        local at, found = m.at_cm, {}
        for _, a in ipairs(FindAllOf(tostring(m.class)) or {}) do
            local ok, l = pcall(function() return a:K2_GetActorLocation() end)
            if ok and l and math.abs(l.X - at[1]) + math.abs(l.Y - at[2]) + math.abs(l.Z - at[3]) < Doors.NEAR_CM then
                local part
                pcall(function()
                    part = a:K2_GetComponentsByClass(d.findObject("/Script/Engine.StaticMeshComponent"))[1]:get()
                    part:SetVisibility(false, false)
                end)
                if part then
                    found[#found + 1] = { actor = a, part = part, at = a.K2_GetActorLocation,
                        partAt = part.K2_GetComponentLocation }
                end
            end
        end
        door.actors = found
        if #found > 0 then d.Log(string.format("door: %d of %d machine(s) bound", #found, want)) end
    end

    --- 0 closed .. 1 open, from the machines' parts.
    local function progress(door)
        if door.travel <= 0 then return nil end
        local most, any = 0, false
        for _, b in ipairs(door.actors) do
            local oa, a = pcall(b.at, b.actor)
            local op, p = pcall(b.partAt, b.part)
            if oa and op and a and p then
                most, any = math.max(most, math.sqrt((p.X - a.X) ^ 2 + (p.Y - a.Y) ^ 2 + (p.Z - a.Z) ^ 2)), true
            end
        end
        if not any then return nil end
        return math.max(0.0, math.min(1.0, most / door.travel))
    end

    local function lerp(a, b, t)
        return { a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t }
    end

    local function pose(door)
        local math_lib = d.findObject("/Script/Engine.Default__KismetMathLibrary")
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
                -- y = z x x: the rotation's columns, applied to the part's
                -- rest position (its actor origin).
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

    --- Follow the machines; `dt` seconds since the last call, `now` the
    --- clock. Returns how long to wait before the next call, in ms.
    function self.tick(dt, now)
        local moving = false
        if self.world ~= d.Current.worldName then
            self.world, self.doors = d.Current.worldName, build()
        end
        for _, door in ipairs(self.doors or {}) do
            bind(door, now)
            local s = progress(door)
            if s then
                local s_snd = door.spec.sounds or {}
                local at = door.spec.at_cm
                local was = door.target
                if s > door.last + 0.002 then
                    door.target = 1.0
                elseif s < door.last - 0.002 then
                    door.target = 0.0
                elseif s < 0.02 then
                    door.target = 0.0
                elseif s > 0.98 then
                    door.target = 1.0
                end
                if door.target ~= was and door.started then
                    sound(s_snd.press, door.spec.control_cm)
                    sound(door.target > 0.5 and s_snd.open or (s_snd.close or s_snd.open), at)
                end
                door.started = true
                if math.abs(s - door.last) > 0.0005 then moving = true end
                door.last = s
            end
            local seconds = math.max(0.1, tonumber(door.spec.seconds) or 1.0)
            local before = door.p
            if door.p < door.target then
                door.p = math.min(door.target, door.p + dt / seconds)
            elseif door.p > door.target then
                door.p = math.max(door.target, door.p - dt / seconds)
            end
            -- Never far from what the simulation shows (a joiner, a hitch).
            if s and math.abs(door.p - s) > 0.25 then door.p = s end
            if before < 1.0 and door.p >= 1.0 then sound((door.spec.sounds or {}).opened, door.spec.at_cm) end
            if door.p ~= before or door.p ~= door.target then moving = true end
            if door.p ~= before or not door.posed then
                door.posed = true
                pose(door)
            end
        end
        return moving and Doors.MOVING_MS or Doors.IDLE_MS
    end

    return self
end

return Doors

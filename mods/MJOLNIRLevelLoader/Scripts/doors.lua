--- Halo 2 doors (Zanzibar's house gate, any door a map's tags make one),
--- opened in the simulation and moved by Unreal.
---
--- A level's `doors` (tools/level/h2_physics_props.py doors.json, from the
--- map's own tags: crate::h2::door, h2_door_machines.py) name each door's
--- parts (decor actors, a mesh a node of the door) and its `machines`:
--- device machines of the simulation's own, one a node, each standing at its
--- node's own place, whose root turns and slides exactly as its node does in
--- Halo 2's opening and carries its collision. The door's control (B40's
--- switch at the keypad) shares their device group, so a player pressing it
--- opens the door in the simulation, for every player in the match.
---
--- This module only sets it up: it finds each machine's Unreal actor by
--- where it stands, hides the elevator mesh the machine would draw, and
--- attaches the node's meshes to the machine's moving component once. Unreal
--- carries them from then on; nothing here poses a mesh.
---
--- What still polls: Halo 2's door sounds (as it starts, and as it finishes
--- opening). The simulation plays a device's sounds through Wwise events our
--- converted sounds do not have, so one machine is watched, at 4 Hz while
--- the door stands and 10 Hz while it moves: two bound calls a look.
local Doors = {}

Doors.SCAN_S = 2.0
Doors.SCAN_TRIES = 30
--- Machines stand 15 cm apart (h2_door_machines.SPACING); an actor binds
--- to the machine it stands within this of.
Doors.MATCH_CM = 5
Doors.NEAR_CM = 40
Doors.CONTROL_CLASS = "BP_FR_ControlPanel_C"
Doors.IDLE_MS = 250
Doors.MOVING_MS = 100
Doors.QUIET_MS = 2000

--- deps: Log, Current, findObject, resolveMesh, getWorld, gameVolume.
--- findObject is a StaticFindObject every call (~1-20 ms): each lookup
--- here is made once and kept.
function Doors.new(d)
    local self = { doors = nil, world = nil }

    local function build()
        local list = d.Current.level and d.Current.level.doors
        if type(list) ~= "table" then return {} end
        local out = {}
        for _, spec in ipairs(list) do
            local door = { spec = spec, machines = {}, parts = {}, bound = 0, tries = 0, seek = -100,
                last = 0.0, target = 0.0, started = false }
            for _, part in ipairs(spec.parts or {}) do
                door.parts[part.node] = door.parts[part.node] or {}
                table.insert(door.parts[part.node], { id = part.id })
            end
            for _, m in ipairs(spec.machines or {}) do
                local t = m.travel_cm or { 0, 0, 0 }
                door.machines[#door.machines + 1] = { spec = m,
                    travel = math.sqrt(t[1] * t[1] + t[2] * t[2] + t[3] * t[3]) }
            end
            out[#out + 1] = door
        end
        return out
    end

    --- Play one of a sound group's waves at `at`; whether it played.
    local function sound(group, at)
        if type(group) ~= "table" or type(group.paths) ~= "table" or #group.paths == 0 or not at then return false end
        local world = d.getWorld()
        self.statics = self.statics or d.findObject("/Script/Engine.Default__GameplayStatics")
        local statics = self.statics
        local wave = d.resolveMesh(group.paths[math.random(#group.paths)])
        local volume = (tonumber(group.gain) or 1.0) * (d.gameVolume and d.gameVolume("ambient") or 1.0)
        if not (world and statics and wave) or volume <= 0 then return false end
        return (pcall(function()
            statics:SpawnSoundAtLocation(world, wave, { X = at[1], Y = at[2], Z = at[3] },
                { Pitch = 0, Yaw = 0, Roll = 0 }, math.min(1.0, volume * 3.0), 1.0, 0.0, nil, nil, true)
        end))
    end

    --- The door's control: B40's switch panel stands at Halo 2's keypad (the
    --- simulation's control a player presses); the keypad's own mesh is
    --- decor, so the panel's components (its meshes and sparks) are hidden,
    --- its device left working. The actor's own hidden flag is reset by the
    --- game; the components' stay, and are set again at every scan.
    local function hide_control(door, scans)
        local c = door.spec.sim_control and door.spec.sim_control.at_cm
        if not c then return end
        if not door.panel and (door.panel_tries or 0) < 15 then
            door.panel_tries = (door.panel_tries or 0) + 1
            self.sceneClass = self.sceneClass or d.findObject("/Script/Engine.SceneComponent")
            local scene = self.sceneClass
            scans[Doors.CONTROL_CLASS] = scans[Doors.CONTROL_CLASS] or FindAllOf(Doors.CONTROL_CLASS) or {}
            for _, a in ipairs(scans[Doors.CONTROL_CLASS]) do
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

    --- Attach a node's meshes to its machine's moving component, keeping
    --- each where it stands relative to the machine at rest: the root's
    --- transform at rest is the actor's own, whatever the door's position
    --- now (a player joining an open door).
    local function attach(door, machine, actor, part)
        local math_lib, base
        for _, p in ipairs(door.parts[machine.spec.node] or {}) do
            local mesh = not p.attached and d.Current.actors and d.Current.actors[p.id]
            if mesh and mesh:IsValid() then
                -- Looked up only while something is left to attach: a
                -- lookup a scan was a 15 ms frame.
                self.mathLib = self.mathLib or d.findObject("/Script/Engine.Default__KismetMathLibrary")
                math_lib, base = self.mathLib, base or actor:GetTransform()
                local ok, err = pcall(function()
                    local rel = math_lib:MakeRelativeTransform(mesh:GetTransform(), base)
                    mesh:K2_SetActorTransform(rel, false, d.Current.emptyHit(), false)
                    mesh:K2_AttachToComponent(part, FName("None"), 0, 0, 0, false)
                end)
                p.attached = ok
                if not ok then d.Log("door: attaching " .. tostring(p.id) .. " failed: " .. tostring(err)) end
            end
        end
    end

    local function attached(door)
        local n, all = 0, 0
        for _, list in pairs(door.parts) do
            for _, p in ipairs(list) do
                all = all + 1
                if p.attached then n = n + 1 end
            end
        end
        return n, all
    end

    --- Each machine's actor, by where it stands; its node's meshes ride it.
    --- `scans`: one FindAllOf a class a tick, shared by every door (each is
    --- ~20 ms; Triplicate's seven placements scanning their own were one
    --- 147 ms frame).
    local function bind(door, now, scans)
        if door.done or now - door.seek < Doors.SCAN_S then return end
        door.seek, door.tries = now, door.tries + 1
        hide_control(door, scans)
        for _, m in ipairs(door.machines) do
            if m.actor and m.actor:IsValid() then
                attach(door, m, m.actor, m.part)
            else
                if m.actor then
                    m.actor, door.bound = nil, door.bound - 1
                    for _, p in ipairs(door.parts[m.spec.node] or {}) do p.attached = false end
                end
                self.meshClass = self.meshClass or d.findObject("/Script/Engine.StaticMeshComponent")
                local mesh_class = self.meshClass
                local class = tostring(m.spec.class)
                scans[class] = scans[class] or FindAllOf(class) or {}
                local at = m.spec.at_cm
                for _, a in ipairs(scans[class]) do
                    local ok, l = pcall(function() return a:K2_GetActorLocation() end)
                    if ok and l and math.sqrt((l.X - at[1]) ^ 2 + (l.Y - at[2]) ^ 2 + (l.Z - at[3]) ^ 2) < Doors.MATCH_CM then
                        local part
                        pcall(function()
                            part = a:K2_GetComponentsByClass(mesh_class)[1]:get()
                            part:SetVisibility(false, false)
                        end)
                        if part then
                            m.actor, m.part = a, part
                            m.at, m.partAt = a.K2_GetActorLocation, part.K2_GetComponentLocation
                            door.bound = door.bound + 1
                            attach(door, m, a, part)
                        end
                        break
                    end
                end
            end
        end
        local n, all = attached(door)
        if door.bound ~= door.logged_bound or n ~= door.logged_n then
            door.logged_bound, door.logged_n = door.bound, n
            d.Log(string.format("door: %d of %d machine(s) bound, %d of %d mesh(es) riding them",
                door.bound, #door.machines, n, all))
        end
        -- Done when everything rides its machine (and the panel has been
        -- hidden a few scans past the last bind), or on giving up.
        if door.bound >= #door.machines and n >= all then
            door.settled = (door.settled or 0) + 1
        end
        if (door.settled or 0) >= 3 or door.tries >= Doors.SCAN_TRIES then
            door.done = true
            if n < all then d.Log("door: gave up; " .. (all - n) .. " mesh(es) stand at rest") end
        end
        -- The machine that travels furthest tells when the door moves.
        for _, m in ipairs(door.machines) do
            if m.actor and m.travel > 0 and (not door.watch or m.travel > door.watch.travel) then door.watch = m end
        end
    end

    --- 0 closed .. 1 open, from the watched machine.
    local function progress(door)
        local m = door.watch
        if not m then return nil end
        local oa, a = pcall(m.at, m.actor)
        local op, p = pcall(m.partAt, m.part)
        if not (oa and op and a and p) then return nil end
        return math.max(0.0, math.min(1.0, math.sqrt((p.X - a.X) ^ 2 + (p.Y - a.Y) ^ 2 + (p.Z - a.Z) ^ 2) / m.travel))
    end

    --- Bind what is unbound and play the doors' sounds. Returns how long to
    --- wait before the next call, in ms.
    function self.tick(now)
        if self.world ~= d.Current.worldName then
            self.world, self.doors = d.Current.worldName, build()
        end
        local wait = Doors.QUIET_MS
        local scans = {}
        for _, door in ipairs(self.doors or {}) do
            bind(door, now, scans)
            if not door.done then
                wait = math.min(wait, Doors.SCAN_S * 1000)
            end
            local snd = door.spec.sounds or {}
            local s = next(snd) and progress(door)
            if s then
                local was = door.target
                if s > door.last + 0.002 then
                    door.target = 1.0
                elseif s < door.last - 0.002 then
                    door.target = 0.0
                end
                if door.target ~= was and door.started then
                    local ok1 = sound(snd.press, door.spec.control_cm)
                    local ok2 = sound(door.target > 0.5 and snd.open or (snd.close or snd.open), door.spec.at_cm)
                    d.Log(string.format("door: %s (press sound %s, %s sound %s)", door.target > 0.5 and "opening" or "closing",
                        tostring(ok1), door.target > 0.5 and "open" or "close", tostring(ok2)))
                end
                if door.started and door.last < 0.98 and s >= 0.98 then
                    d.Log("door: open (opened sound " .. tostring(sound(snd.opened, door.spec.at_cm)) .. ")")
                end
                local moving = math.abs(s - door.last) > 0.0005
                door.started, door.last = true, s
                wait = math.min(wait, moving and Doors.MOVING_MS or Doors.IDLE_MS)
            end
        end
        return wait
    end

    return self
end

return Doors

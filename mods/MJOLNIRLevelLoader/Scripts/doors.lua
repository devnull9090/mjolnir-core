--- Halo 2 machines that move in parts (Zanzibar's house gate, Triplicate's
--- garage gates and trains: any machine a map's tags make one).
---
--- The simulation moves them and Unreal draws them; this module only dresses
--- them. A level's `doors` (tools/level/h2_physics_props.py doors.json, or
--- gen_ce_level.py --doors, from the map's own tags: crate::h2::door,
--- h2_door_machines.py) name each placement's `machines`: device machines of
--- the simulation's own, one a node, whose root turns and slides exactly as
--- the node does and carries its collision. Each machine's actor is its own
--- Blueprint (B40's elevator cloned, h2_door_machines.write_actors) wearing
--- the node's part meshes on its moving bone, so Unreal moves the part with
--- no script, for every player, a joiner included.
---
--- What runs here: once a machine's actor exists, its mesh components get
--- their materials (the parts' `materials`, the level's material lists); the
--- door's control (B40's switch panel at Halo 2's keypad) has its components
--- hidden; and Halo 2's door sounds play as a door starts and finishes
--- opening. The simulation plays a device's sounds through Wwise events our
--- converted sounds do not have, so one machine is watched, at 4 Hz while
--- the door stands and 10 Hz while it moves: two bound calls a look.
local Doors = {}

Doors.SCAN_S = 2.0
Doors.SCAN_TRIES = 30
Doors.NEAR_CM = 40
Doors.CONTROL_CLASS = "BP_FR_ControlPanel_C"
Doors.ACTOR_CLASS = "BlamObjectActor"
Doors.IDLE_MS = 250
Doors.MOVING_MS = 100
Doors.QUIET_MS = 2000

--- deps: Log, Current, findObject, resolveMesh, getWorld, gameVolume,
--- applyMaterials. findObject is a StaticFindObject every call (~1-20 ms):
--- each lookup here is made once and kept.
function Doors.new(d)
    local self = { doors = nil, world = nil }

    local function build()
        local list = d.Current.level and d.Current.level.doors
        if type(list) ~= "table" then return {} end
        local out = {}
        for _, spec in ipairs(list) do
            local door = { spec = spec, machines = {}, tries = 0, seek = -100,
                last = 0.0, target = 0.0, started = false }
            -- A part's materials by its mesh's name (the actor's components
            -- carry the meshes the Blueprint lists).
            local byMesh = {}
            for _, part in ipairs(spec.parts or {}) do
                local leaf = tostring(part.mesh or ""):match("%.([^%.]+)$")
                if leaf then byMesh[leaf] = part end
            end
            for _, m in ipairs(spec.machines or {}) do
                local t = m.travel_cm or { 0, 0, 0 }
                door.machines[#door.machines + 1] = { spec = m, byMesh = byMesh,
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
    --- game; the components' stay.
    local function hide_control(door, scans)
        local c = door.spec.sim_control and door.spec.sim_control.at_cm
        if not c then return end
        if not door.panel and (door.panel_tries or 0) < 15 then
            door.panel_tries = (door.panel_tries or 0) + 1
            self.sceneClass = self.sceneClass or d.findObject("/Script/Engine.SceneComponent")
            scans[Doors.CONTROL_CLASS] = scans[Doors.CONTROL_CLASS] or FindAllOf(Doors.CONTROL_CLASS) or {}
            for _, a in ipairs(scans[Doors.CONTROL_CLASS]) do
                local ok, l = pcall(function() return a:K2_GetActorLocation() end)
                if ok and l and math.abs(l.X - c[1]) + math.abs(l.Y - c[2]) + math.abs(l.Z - c[3]) < Doors.NEAR_CM then
                    door.panel = {}
                    pcall(function()
                        for _, comp in ipairs(a:K2_GetComponentsByClass(self.sceneClass)) do
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

    --- The machine actors in play, by class name: one scan of the Blam
    --- object actors a tick, shared by every door.
    local function actorsByClass(scans)
        if scans.byClass then return scans.byClass end
        local byClass = {}
        for _, a in ipairs(FindAllOf(Doors.ACTOR_CLASS) or {}) do
            local ok, name = pcall(function() return a:GetClass():GetFName():ToString() end)
            if ok and name then byClass[name] = a end
        end
        scans.byClass = byClass
        return byClass
    end

    --- Dress a machine's actor: each mesh component its part's materials.
    --- Returns how many it dressed.
    local function dress(m, actor)
        self.meshClass = self.meshClass or d.findObject("/Script/Engine.StaticMeshComponent")
        local world = d.getWorld()
        local n = 0
        pcall(function()
            for _, c in ipairs(actor:K2_GetComponentsByClass(self.meshClass)) do
                local comp = c:get()
                local leaf = comp.StaticMesh and comp.StaticMesh:GetFName():ToString()
                local part = leaf and m.byMesh[leaf]
                if part and type(part.materials) == "table" then
                    d.applyMaterials(comp, part.materials, world, part.id)
                    -- Its own bounds, not the skeleton's: the elevator
                    -- Blueprint the machines are cloned from culls its mesh
                    -- by its parent's, and a Halo 2 part stands far from its
                    -- machine's origin (Containment's gate door 28 m), so the
                    -- door blinked out whenever that distant box left the
                    -- view or went behind a wall (2026-11-17). The cooked
                    -- clones of every map would need rewriting to fix it at
                    -- the source; this runs once a part. The visibility
                    -- round trip makes the renderer take the new bounds.
                    comp.bUseAttachParentBound = false
                    local shown = comp:IsVisible()
                    comp:SetVisibility(not shown, false)
                    comp:SetVisibility(shown, false)
                    n = n + 1
                    m.part = m.part or comp
                end
            end
        end)
        return n
    end

    --- Find and dress each machine's actor, once.
    local function setup(door, now, scans)
        if door.done or now - door.seek < Doors.SCAN_S then return end
        door.seek, door.tries = now, door.tries + 1
        hide_control(door, scans)
        local byClass = actorsByClass(scans)
        local found, meshes = 0, 0
        for _, m in ipairs(door.machines) do
            if not (m.actor and m.actor:IsValid()) then
                m.actor, m.part, m.dressed = byClass[m.spec.class], nil, false
            end
            local a = m.actor
            if a and a:IsValid() then
                found = found + 1
                if not m.dressed then
                    m.meshes, m.dressed = dress(m, a), true
                    m.at = a.K2_GetActorLocation
                    m.partAt = m.part and m.part.K2_GetComponentLocation
                end
                meshes = meshes + (m.meshes or 0)
            end
        end
        if found ~= door.logged_found then
            door.logged_found = found
            d.Log(string.format("door: %d of %d machine actor(s), %d part mesh(es) dressed", found,
                #door.machines, meshes))
        end
        -- Done once every actor is dressed and the control's panel found:
        -- each scan of the Blam actors is ~25 ms.
        local panel = not door.spec.sim_control or door.panel ~= nil
        if (found >= #door.machines and panel) or door.tries >= Doors.SCAN_TRIES then
            door.done = true
            if found < #door.machines then
                d.Log("door: gave up on " .. (#door.machines - found) .. " machine actor(s)")
            end
        end
        -- The machine that travels furthest, wearing a part, tells when the
        -- door moves.
        for _, m in ipairs(door.machines) do
            if m.partAt and m.travel > 0 and (not door.watch or m.travel > door.watch.travel) then door.watch = m end
        end
    end

    --- 0 closed .. 1 open, from the watched machine: its part's offset from
    --- where it stood when first read (at rest: a level loads closed). A
    --- machine the player cannot see is hidden by the game and posed again
    --- once seen, so this reads still while unseen; its sounds are unheard
    --- then anyway.
    local function progress(door)
        local m = door.watch
        if not (m and m.actor and m.actor:IsValid()) then return nil end
        local oa, a = pcall(m.at, m.actor)
        local op, p = pcall(m.partAt, m.part)
        if not (oa and op and a and p) then return nil end
        local x, y, z = p.X - a.X, p.Y - a.Y, p.Z - a.Z
        door.rest = door.rest or { x, y, z }
        local r = door.rest
        return math.max(0.0, math.min(1.0, math.sqrt((x - r[1]) ^ 2 + (y - r[2]) ^ 2 + (z - r[3]) ^ 2) / m.travel))
    end

    --- Set up what is not yet and play the doors' sounds. Returns how long
    --- to wait before the next call, in ms.
    function self.tick(now)
        if self.world ~= d.Current.worldName then
            self.world, self.doors = d.Current.worldName, build()
        end
        local wait = Doors.QUIET_MS
        local scans = {}
        for _, door in ipairs(self.doors or {}) do
            setup(door, now, scans)
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
                    d.Log(string.format("door: %s (press sound %s, %s sound %s)",
                        door.target > 0.5 and "opening" or "closing", tostring(ok1),
                        door.target > 0.5 and "open" or "close", tostring(ok2)))
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

--- Halo 2's turning parts (Ascension's antennas, Zanzibar's wheels and
--- flywheels, Foundation's fans), worn by their machines' actors.
---
--- A level's `gears` (tools/level/gen_ce_level.py add_gears) name each part
--- mesh, the class of the machine actor that wears it (h2_machines.py
--- actors: B40's elevator Blueprint cloned per placement, the part on its
--- moving bone), its materials and its turn (`motion`: period, keys, axis,
--- its sounds' events). The simulation turns the machine and Unreal draws
--- the part; nothing here moves anything.
---
--- What runs here: once a gear's actor exists, its mesh component gets its
--- materials; and a gear with sounds has them played as its turn passes
--- their times. The simulation runs a gear from its own clock, so its phase
--- is fitted once to what the part does (its angle about the axis, sampled
--- while the player can see it: the game poses no part it hides), then the
--- events play on the clock, the loop sleeping until the next is due.
--- Whether `actor` belongs to the world named `worldName` (a world's
--- GetFullName, "World /Game/.../CNT/CNT.CNT"). Right after a map change
--- FindAllOf still returns the last map's actors, being destroyed but not
--- yet freed; reading one (its location, its components) crashed the game
--- in UE4SS going from Zanzibar to Containment (2026-11-18), whose gate
--- panels are found the moment the map is dressed.
local function inWorld(actor, worldName)
    local path = type(worldName) == "string" and worldName:match("^%S+%s+(.+)$")
    if not path then return false end
    local ok, name = pcall(function() return actor:GetFullName() end)
    return ok and type(name) == "string" and name:find(path .. ":", 1, true) ~= nil
end

local Gears = {}

Gears.SCAN_S = 2.0
Gears.SCAN_TRIES = 30
Gears.ACTOR_CLASS = "BlamObjectActor"
Gears.SAMPLE_MS = 100
Gears.UNSEEN_MS = 1000
Gears.FIT_S = 8.0
Gears.FIT_RANGE_DEG = 5.0
Gears.QUIET_MS = 2000

--- deps: Log, Current, findObject, resolveMesh, getWorld, gameVolume,
--- applyMaterials.
function Gears.new(d)
    local self = { gears = nil, world = nil }

    local function build()
        local list = d.Current.level and d.Current.level.gears
        if type(list) ~= "table" then return {} end
        local out = {}
        for _, spec in ipairs(list) do
            local m = spec.motion or {}
            -- Every gear is looked for once, a quiet one in cooked materials
            -- too: its part must cull by its own bounds (setup).
            out[#out + 1] = { spec = spec, period = tonumber(m.period) or 0, keys = m.keys or {},
                events = m.events or {}, axis = m.axis or { 0, 0, 1 }, hist = {}, seek = -100, tries = 0 }
        end
        return out
    end

    --- The turn's angle (degrees) at t seconds into it, from its keys.
    local function at(g, t)
        local keys = g.keys
        if #keys == 0 then return 0 end
        for k = 2, #keys do
            if t <= keys[k][1] then
                local a, b = keys[k - 1], keys[k]
                return b[1] > a[1] and (a[2] + (b[2] - a[2]) * (t - a[1]) / (b[1] - a[1])) or b[2]
            end
        end
        return keys[#keys][2]
    end

    --- The part's angle about its axis: its mesh stands world-aligned at
    --- rest, so the angle is how far the component's frame has turned from
    --- the world's (a vector of each, across the axis).
    local function angle(g)
        local k = g.axis
        local ok, f = pcall(function()
            local useUp = math.abs(k[1]) > 0.9
            local v = useUp and g.comp:GetUpVector() or g.comp:GetForwardVector()
            return { useUp, v.X, v.Y, v.Z }
        end)
        if not ok then return nil end
        local a = f[1] and { 0, 0, 1 } or { 1, 0, 0 }
        local b = { f[2], f[3], f[4] }
        local ak = a[1] * k[1] + a[2] * k[2] + a[3] * k[3]
        local bk = b[1] * k[1] + b[2] * k[2] + b[3] * k[3]
        local cross = k[1] * (a[2] * b[3] - a[3] * b[2]) + k[2] * (a[3] * b[1] - a[1] * b[3])
            + k[3] * (a[1] * b[2] - a[2] * b[1])
        return math.deg(math.atan(cross, a[1] * b[1] + a[2] * b[2] + a[3] * b[3] - ak * bk))
    end

    local function play(g, e)
        local world = d.getWorld()
        if not (world and g.loc) then return end
        self.statics = self.statics or d.findObject("/Script/Engine.Default__GameplayStatics")
        self.attClass = self.attClass or d.findObject("/Script/Engine.SoundAttenuation")
        pcall(function()
            local wave = d.resolveMesh(e.wave)
            if not wave then return end
            self.plays = (self.plays or 0) + 1
            local att = StaticConstructObject(self.attClass, world, FName("MJOLNIR_GearAtt_" .. self.plays))
            local a = att.Attenuation
            a.bAttenuate = true
            a.bSpatialize = true
            a.DistanceAlgorithm = 0
            a.AttenuationShape = 0
            a.AttenuationShapeExtents = { X = e.inner, Y = 0, Z = 0 }
            a.FalloffDistance = e.falloff
            self.statics:SpawnSoundAtLocation(world, wave, g.loc, { Pitch = 0, Yaw = 0, Roll = 0 },
                (e.gain or 1.0) * (d.gameVolume and d.gameVolume("ambient") or 1.0)
                * (d.Current.mix and d.Current.mix.factor(e.source or e.wave) or 1.0), 1.0, 0.0, att, nil, true)
        end)
    end

    --- Find and dress each gear's actor, once (one scan of the Blam object
    --- actors a pass, shared by every gear).
    local function setup(now)
        local byClass
        for _, g in ipairs(self.gears or {}) do
            if not g.dressed and g.tries < Gears.SCAN_TRIES and now - g.seek >= Gears.SCAN_S then
                g.seek, g.tries = now, g.tries + 1
                if not byClass then
                    byClass = {}
                    for _, a in ipairs(FindAllOf(Gears.ACTOR_CLASS) or {}) do
                        if inWorld(a, d.Current.worldName) then
                            local ok, name = pcall(function() return a:GetClass():GetFName():ToString() end)
                            if ok and name then byClass[name] = a end
                        end
                    end
                end
                local a = byClass[g.spec.class]
                if a then
                    self.meshClass = self.meshClass or d.findObject("/Script/Engine.StaticMeshComponent")
                    local leaf = tostring(g.spec.mesh or ""):match("%.([^%.]+)$")
                    pcall(function()
                        for _, c in ipairs(a:K2_GetComponentsByClass(self.meshClass)) do
                            local comp = c:get()
                            -- A part whose mesh has not streamed in yet
                            -- reads as a null object, and its name read
                            -- crashes (doors.lua dress): skipped, looked at
                            -- again next pass.
                            local mesh = comp.StaticMesh
                            if mesh and mesh:IsValid() and mesh:GetFName():ToString() == leaf then
                                if type(g.spec.materials) == "table" and #g.spec.materials > 0 then
                                    d.applyMaterials(comp, g.spec.materials, d.getWorld(), g.spec.id)
                                end
                                -- Its own bounds, not the skeleton's: the
                                -- game's mesh sync spawns the part culled by
                                -- its parent's, which stand far from a
                                -- Halo 2 part (Zanzibar's big wheel blinked
                                -- out as the view turned, 2026-11-18). No
                                -- cooked field says otherwise (the
                                -- Blueprint's mesh list has none), so it is
                                -- set here, once a part; the visibility round
                                -- trip makes the renderer take the bounds.
                                comp.bUseAttachParentBound = false
                                local shown = comp:IsVisible()
                                comp:SetVisibility(not shown, false)
                                comp:SetVisibility(shown, false)
                                g.comp = comp
                            end
                        end
                    end)
                    g.actor, g.dressed = a, g.comp ~= nil
                    if g.dressed then
                        local l = a:K2_GetActorLocation()
                        g.loc = { X = l.X, Y = l.Y, Z = l.Z }
                    end
                end
            end
        end
    end

    --- Dress what is not yet and play the gears' sounds. Returns how long to
    --- wait before the next call, in ms.
    function self.tick(now)
        if self.world ~= d.Current.worldName then
            self.world, self.gears, self.logged = d.Current.worldName, build(), nil
        end
        setup(now)
        local wait, dressed, all = Gears.QUIET_MS, 0, 0
        for _, g in ipairs(self.gears or {}) do
            all = all + 1
            if g.dressed then dressed = dressed + 1 elseif g.tries < Gears.SCAN_TRIES then
                wait = math.min(wait, Gears.SCAN_S * 1000)
            end
            if g.dressed and #g.events > 0 and g.period > 0 then
                if not g.offset then
                    -- Fit the phase: sample while the game shows the part.
                    local seen = g.actor:IsValid() and not g.actor.bHidden
                    local th = seen and angle(g)
                    if th then
                        local h = g.hist
                        h[#h + 1] = { now, th }
                        local lo, hi = th, th
                        for _, s in ipairs(h) do lo, hi = math.min(lo, s[2]), math.max(hi, s[2]) end
                        if now - h[1][1] > Gears.FIT_S and hi - lo > Gears.FIT_RANGE_DEG then
                            -- Coarse over the turn (half seconds), then fine
                            -- (tenths) about each sign's best: one short frame.
                            local function cost(sign, o)
                                local c = 0
                                for i = 1, #h, 3 do
                                    local e = (sign * at(g, (h[i][1] - o) % g.period) - h[i][2] + 540) % 360 - 180
                                    c = c + e * e
                                end
                                return c
                            end
                            local best, bestCost = 0, math.huge
                            for _, sign in ipairs({ 1, -1 }) do
                                local o0, c0 = 0, math.huge
                                for o = 0, g.period, 0.5 do
                                    local c = cost(sign, o)
                                    if c < c0 then o0, c0 = o, c end
                                end
                                for o = o0 - 0.5, o0 + 0.5, 0.1 do
                                    local c = cost(sign, o % g.period)
                                    if c < bestCost then best, bestCost = o % g.period, c end
                                end
                            end
                            g.offset, g.hist = best, nil
                            d.Log(string.format("gear %s: phase %.1f s from the clock", tostring(g.spec.id), best))
                        elseif #h > 600 then
                            table.remove(h, 1)
                        end
                    end
                    -- Unseen, look again in a second, not ten times one.
                    wait = math.min(wait, seen and Gears.SAMPLE_MS or Gears.UNSEEN_MS)
                else
                    -- Its sounds whose time the turn passed since the last
                    -- pass (across the wrap too); then sleep to the next.
                    local t = (now - g.offset) % g.period
                    local last = g.last
                    g.last = t
                    local nextIn = g.period
                    for _, e in ipairs(g.events) do
                        if last and ((last < t and e.t > last and e.t <= t) or (t < last and (e.t > last or e.t <= t))) then
                            play(g, e)
                        end
                        local dt = (e.t - t) % g.period
                        if dt > 0 and dt < nextIn then nextIn = dt end
                    end
                    wait = math.min(wait, math.max(20, math.floor(nextIn * 1000)))
                end
            end
        end
        if all > 0 and dressed ~= self.logged then
            self.logged = dressed
            d.Log(string.format("gears: %d of %d turning part(s) found on their machine actors (to dress or to sound)", dressed, all))
        end
        return wait
    end

    return self
end

return Gears

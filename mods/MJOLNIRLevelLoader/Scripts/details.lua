--- Halo 2's detail sounds: the one-shots a looping sound plays at random
--- times (Zanzibar's shore waves, gulls, birds, horn and distant battle).
---
--- A level's `environment.sounds.details` (tools/level/gen_ce_level.py
--- ambient_sounds) lists each: its variants (`waves`), gain, the bounds of
--- the wait between plays (`period`, seconds), and either `pos` with
--- `inner`/`falloff` (cm; at its sound scenery, falling off as the loop
--- would) or, with none, around the listener in its background `set`.
---
--- Why a loop: each play is a random variant after a random wait, which no
--- cooked asset of ours can say (a SoundCue's Random and Delay nodes would,
--- but this project cannot build SoundCue graphs from its editor scripts),
--- and Halo 2 places them by the tags, so they are known only at load. The
--- loop sleeps until the next play is due (seconds apart) and allocates
--- only the sound it plays and its attenuation.
local Details = {}

Details.MIN_WAIT_MS = 250
Details.IDLE_MS = 2000

--- deps: Log, Current, findObject, resolveMesh, getWorld, gameVolume,
--- getCamera.
function Details.new(d)
    local self = { list = nil, world = nil }

    local function build()
        local env = d.Current.level and d.Current.level.environment
        local list = type(env) == "table" and type(env.sounds) == "table" and env.sounds.details
        if type(list) ~= "table" then return {} end
        local origin = (d.Current.level.canvas or {}).origin or { 0, 0, 0 }
        local out, waves = {}, 0
        for _, s in ipairs(list) do
            -- Paths, each found when it plays: finding Zanzibar's 68 at once
            -- held the game thread 1.6 s.
            local variants = {}
            for _, w in ipairs(type(s.waves) == "table" and s.waves or {}) do
                if type(w) == "string" then variants[#variants + 1] = w end
            end
            if #variants > 0 then
                waves = waves + #variants
                local e = { waves = variants, gain = tonumber(s.gain) or 1.0, set = s.set, key = s.source or variants[1],
                    lo = (s.period and tonumber(s.period[1])) or 10.0, hi = (s.period and tonumber(s.period[2])) or 30.0 }
                if type(s.pos) == "table" then
                    e.at = { X = origin[1] + s.pos[1], Y = origin[2] + s.pos[2], Z = origin[3] + s.pos[3] }
                    e.inner, e.falloff = s.inner or 150.0, s.falloff or 600.0
                    e.reach = e.inner + e.falloff
                end
                out[#out + 1] = e
            end
        end
        if #out > 0 then d.Log(string.format("detail sounds: %d, %d variant(s)", #out, waves)) end
        return out
    end

    --- Nothing made or found here is kept from Lua across plays: an object
    --- only Lua holds is freed by the next garbage collection and its handle
    --- then points at freed memory (a kept attenuation crashed the game on
    --- the first play, 2026-11-18). Waves go through resolveMesh each time,
    --- which checks its cached handle; the attenuation is made per play and
    --- held by the sound it plays, like the gears'.
    local function play(e, world)
        self.statics = self.statics or d.findObject("/Script/Engine.Default__GameplayStatics")
        self.attClass = self.attClass or d.findObject("/Script/Engine.SoundAttenuation")
        if #e.waves == 0 then return end
        local k = math.random(#e.waves)
        local wave = d.resolveMesh(e.waves[k])
        if not wave then
            table.remove(e.waves, k)
            return
        end
        local volume = e.gain * (d.gameVolume and d.gameVolume("ambient") or 1.0)
            * (d.Current.mix and d.Current.mix.factor(e.key) or 1.0)
        if volume <= 0 then return end
        pcall(function()
            if e.at then
                self.plays = (self.plays or 0) + 1
                local att = StaticConstructObject(self.attClass, world, FName("MJOLNIR_DetailAtt_" .. self.plays))
                local a = att.Attenuation
                a.bAttenuate = true
                a.bSpatialize = true
                a.DistanceAlgorithm = 0
                a.AttenuationShape = 0
                a.AttenuationShapeExtents = { X = e.inner, Y = 0, Z = 0 }
                a.FalloffDistance = e.falloff
                self.statics:SpawnSoundAtLocation(world, wave, e.at, { Pitch = 0, Yaw = 0, Roll = 0 },
                    volume, 1.0, 0.0, att, nil, true)
            else
                self.statics:SpawnSound2D(world, wave, volume, 1.0, 0.0, nil, false, true)
            end
        end)
    end

    --- Play what is due and schedule its next. Returns the wait in ms.
    function self.tick(now)
        if self.world ~= d.Current.worldName then
            self.world, self.list = d.Current.worldName, build()
            for _, e in ipairs(self.list) do e.due = now + e.lo + math.random() * (e.hi - e.lo) end
        end
        if #self.list == 0 then return Details.IDLE_MS end
        local world = d.getWorld()
        local cam = world and d.getCamera()
        local nextDue = math.huge
        for _, e in ipairs(self.list) do
            if now >= e.due then
                e.due = now + e.lo + math.random() * (e.hi - e.lo)
                local heard
                if e.at then
                    heard = cam and ((cam.X - e.at.X) ^ 2 + (cam.Y - e.at.Y) ^ 2 + (cam.Z - e.at.Z) ^ 2) < e.reach * e.reach
                else
                    heard = e.set == nil or e.set == d.Current.soundSet
                end
                if heard and world then play(e, world) end
            end
            if e.due < nextDue then nextDue = e.due end
        end
        return math.max(Details.MIN_WAIT_MS, math.floor((nextDue - now) * 1000))
    end

    return self
end

return Details

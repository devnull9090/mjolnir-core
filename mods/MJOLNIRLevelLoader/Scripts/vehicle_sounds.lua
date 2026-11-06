-- MJOLNIR Level Loader: a converted vehicle's own sounds
--
-- A tag here can only name a shipped Wwise event, so a CE vehicle's samples
-- play through Unreal's audio engine, as a level's ambient sound does. The
-- level's folder holds vehicle_sounds.json (tools/level/ce_vehicle_sounds.py):
-- by actor class, { top_speed, sounds = { { drive, gain, fade_in, fade_out,
-- start, start_s, end, end_s, ranges, pitch, inner, falloff } }, lights }.
--
-- A sound's `drive` says when it runs: `engine` while the Blueprint's EngineOn
-- says the driver's seat is taken, `crouch` while the driver holds crouch,
-- CE's horn. A start plays, then the loop; with a fade the loop fades in under
-- it, as CE's engine does. A loop with pitch ranges runs one wave a range, and
-- the engine's revs move the pitch and the fade between them.
--
-- The clone's own engine loop is cut from its Blueprint
-- (crates/ue-asset/examples/vehicle_mute.rs), which leaves EngineOn working.
--
-- Units are reported as their component is made, once per spawn: a native
-- class, so the watch arms at once and nothing scans. Sounds follow by position
-- on the tick, as main.lua's moving sounds do.
--
-- Plain helpers (bend, weight, rate, clamp, revs) run under stock Lua in
-- tools/tests/test_vehicle_sounds.lua; nothing touches UE4SS before init.

local VehicleSounds = {}

--- Every vehicle has one, whatever its donor; so does a biped, which `bind` drops.
VehicleSounds.WATCH = "/Script/BlamSynchronization.BlamUnitComponent"

--- The pitch either side of a range's bound over which two ranges cross.
VehicleSounds.CROSS = 0.04

--- How far the engine's value moves a second, up and down.
VehicleSounds.RISE, VehicleSounds.FALL = 1.5, 1.0

--- How long after a component is made its actor is looked at, in ms.
local SETTLE_MS = 1000

--- How often the sliders are read while a sound runs, in seconds.
local VOLUME_S = 0.5

local env
local state = {
    level = nil, table = nil, watching = false, new = {}, bound = {}, serial = 0,
    volume = 1.0, volumeAt = -1, crouchFailed = false, revsLogged = false,
}

function VehicleSounds.clamp(v, low, high)
    return math.max(low, math.min(high, v))
end

--- The engine's value 0..1 from what can be read: the simulation's engine and
--- the speed. A getter that gives nothing leaves the speed to carry it.
function VehicleSounds.revs(fraction, speed, top)
    local bySpeed = top and top > 0 and speed / top or 0
    return VehicleSounds.clamp(math.max(fraction or 0, bySpeed), 0, 1)
end

--- `value` moved towards `want` over `dt` seconds.
function VehicleSounds.bend(value, want, dt)
    if want > value then return math.min(want, value + VehicleSounds.RISE * dt) end
    return math.max(want, value - VehicleSounds.FALL * dt)
end

--- A range's share of the sound at pitch `p`, 0..1. Past either end of all the
--- ranges the nearest one keeps playing: `first` and `last` leave that side open.
function VehicleSounds.weight(p, range, first, last)
    local c = VehicleSounds.CROSS
    local up = first and 1 or VehicleSounds.clamp((p - (range.low - c)) / (2 * c), 0, 1)
    local down = last and 1 or VehicleSounds.clamp(((range.high + c) - p) / (2 * c), 0, 1)
    return math.min(up, down)
end

--- A range's playback rate: its samples are at its natural pitch.
function VehicleSounds.rate(p, range)
    if not range.natural or range.natural <= 0 then return 1.0 end
    return p / range.natural
end

--- The sliders, read at most every VOLUME_S.
local function sliders(now)
    if now - state.volumeAt >= VOLUME_S then
        state.volumeAt, state.volume = now, env.gameVolume("gameplay")
    end
    return state.volume
end

local function attenuation(world, sound)
    local class = env.findObject("/Script/Engine.SoundAttenuation")
    if not class then return nil end
    state.serial = state.serial + 1
    local att
    pcall(function()
        att = StaticConstructObject(class, world, FName("MJOLNIR_VehicleAtt_" .. state.serial))
        local a = att.Attenuation
        a.bAttenuate = true
        a.bSpatialize = true
        a.DistanceAlgorithm = 0 -- linear, as CE
        a.AttenuationShape = 0 -- sphere
        a.AttenuationShapeExtents = { X = sound.inner or 300.0, Y = 0, Z = 0 }
        a.FalloffDistance = sound.falloff or 3000.0
    end)
    return att
end

local function spawn(world, wavePath, sound, at, volume, pitch, autoDestroy)
    local wave = env.resolveMesh(wavePath)
    if not wave then return nil end
    -- A virtualized loop restarts late when it comes back in range.
    pcall(function() wave.VirtualizationMode = 1 end)
    local gs = env.findObject("/Script/Engine.Default__GameplayStatics")
    local ok, comp = pcall(function()
        return gs:SpawnSoundAtLocation(world, wave, at, { Pitch = 0, Yaw = 0, Roll = 0 }, volume, pitch, 0.0,
            attenuation(world, sound), nil, autoDestroy)
    end)
    if ok and comp and comp:IsValid() then return comp end
    env.Log("vehicle sound did not spawn: " .. tostring(wavePath))
    return nil
end

--- One of the sound's start or end waves, at random as CE picks a permutation.
local function oneShot(run, waves, seconds, world, at, volume, now)
    if #waves == 0 then return end
    local comp = spawn(world, waves[math.random(#waves)], run.sound, at, run.sound.gain * volume, 1.0, true)
    if comp then run.shots[#run.shots + 1] = { comp = comp, untilAt = now + seconds } end
end

local function startLoops(run, world, at, volume)
    local sound = run.sound
    for i, range in ipairs(sound.ranges or {}) do
        local comp = run.loops[i]
        if comp and comp:IsValid() then
            pcall(function() comp:FadeIn(sound.fade_in or 0, 1.0, 0.0, 0) end)
        else
            comp = spawn(world, range.wave, sound, at, sound.gain * volume, 1.0, false)
            run.loops[i] = comp
            if comp and (sound.fade_in or 0) > 0 then
                pcall(function() comp:FadeIn(sound.fade_in, 1.0, 0.0, 0) end)
            end
        end
    end
end

local function stopLoops(run)
    local fade = run.sound.fade_out or 0
    for _, comp in pairs(run.loops) do
        if comp:IsValid() then
            pcall(function()
                if fade > 0 then comp:FadeOut(fade, 0.0, 0) else comp:Stop() end
            end)
        end
    end
end

--- Whether the driver holds crouch. A getter that fails is not tried again.
local function crouching(actor)
    if state.crouchFailed then return false end
    local ok, v = pcall(function() return actor.BlamUnit:GetCrouch() end)
    if not ok then
        state.crouchFailed = true
        env.Log("vehicle sounds: GetCrouch failed, no horn: " .. tostring(v))
        return false
    end
    if type(v) == "number" then return v > 0.5 end
    return v == true
end

--- The engine's revs this tick and the speed behind them.
local function measure(bound, actor, at, now)
    local dt = now - (bound.seen or now)
    local speed = bound.speed or 0
    if dt > 0 and bound.at then
        local dx, dy, dz = at.X - bound.at.X, at.Y - bound.at.Y, at.Z - bound.at.Z
        speed = math.sqrt(dx * dx + dy * dy + dz * dz) / dt
    end
    bound.at, bound.seen, bound.speed = { X = at.X, Y = at.Y, Z = at.Z }, now, speed
    local ok, fraction = pcall(function() return actor.BlamVehicleHumanJeep:GetEngineAngularVelocityFraction() end)
    if type(fraction) ~= "number" or fraction ~= fraction then ok, fraction = false, nil end
    if not state.revsLogged then
        state.revsLogged = true
        env.Log("vehicle sounds: engine fraction " .. (ok and "read" or "not read, revs follow the speed"))
    end
    bound.revs = VehicleSounds.bend(bound.revs or 0, VehicleSounds.revs(fraction, speed, bound.entry.top_speed), dt)
end

local function drive(run, on, world, at, volume, now)
    local sound = run.sound
    if on and not run.on then
        run.on = true
        oneShot(run, sound.start or {}, sound.start_s or 0, world, at, volume, now)
        -- With a fade the loop comes up under the start; without one it follows it.
        run.loopAt = (sound.fade_in or 0) > 0 and now or now + (sound.start_s or 0)
    elseif run.on and not on then
        run.on = false
        if run.playing then stopLoops(run) end
        run.playing, run.loopAt = false, nil
        oneShot(run, sound["end"] or {}, sound.end_s or 0, world, at, volume, now)
    end
    if run.on and not run.playing and run.loopAt and now >= run.loopAt then
        run.playing = true
        startLoops(run, world, at, volume)
    end
end

--- Every running component to the vehicle, and each loop to its pitch and share.
local function follow(run, bound, at, volume, now)
    local sound = run.sound
    local hit = env.Current.hit or {}
    for i = #run.shots, 1, -1 do
        local shot = run.shots[i]
        if now > shot.untilAt or not shot.comp:IsValid() then
            table.remove(run.shots, i)
        else
            shot.comp:K2_SetWorldLocation(at, false, hit, false)
        end
    end
    if not run.playing then return end
    local low, high = (sound.pitch or {})[1] or 1.0, (sound.pitch or {})[2] or 1.0
    local p = low + (high - low) * (bound.revs or 0)
    local ranges = sound.ranges or {}
    for i, range in ipairs(ranges) do
        local comp = run.loops[i]
        if comp and comp:IsValid() then
            comp:K2_SetWorldLocation(at, false, hit, false)
            local share = VehicleSounds.weight(p, range, i == 1, i == #ranges)
            comp:SetVolumeMultiplier(sound.gain * volume * share)
            if share > 0 then comp:SetPitchMultiplier(VehicleSounds.rate(p, range)) end
        end
    end
end

local function silence(bound)
    for _, run in ipairs(bound.runs) do
        for _, comp in pairs(run.loops) do
            if comp:IsValid() then pcall(function() comp:Stop() end) end
        end
    end
end

local function update(bound, world, now)
    local actor = bound.actor
    local at = actor:K2_GetActorLocation()
    local engine = actor.EngineOn == true
    if engine then measure(bound, actor, at, now) else bound.at, bound.seen, bound.revs = nil, nil, 0 end
    local volume = sliders(now)
    for _, run in ipairs(bound.runs) do
        local on = engine
        if run.sound.drive == "crouch" then on = engine and crouching(actor) end
        drive(run, on, world, at, volume, now)
        follow(run, bound, at, volume, now)
    end
end

--- The class's name, for its row in the table. Nil for what is not an actor
--- in a world, such as a class default.
local function className(actor)
    local full = actor:GetFullName()
    if type(full) ~= "string" or full:find("Default__", 1, true) then return nil end
    return actor:GetClass():GetFName():ToString()
end

-- The donor's lights ride sockets of its rig, not the CE body. Niagara
-- components can't be edited in the cooked Blueprint, so they move here, once a
-- vehicle (tools/level/ce_vehicle_lights.py).
local function placeLights(actor, lights)
    if type(lights) ~= "table" then return end
    local move, hide = lights.move or {}, {}
    for _, name in ipairs(lights.hide or {}) do hide[name] = true end
    state.sceneClass = state.sceneClass or env.findObject("/Script/Engine.SceneComponent")
    local components = actor:K2_GetComponentsByClass(state.sceneClass)
    for i = 1, #components do
        local component = components[i]:get()
        local name = component:GetFName():ToString()
        local at = move[name]
        if at then
            component:K2_SetRelativeLocation({ X = at[1], Y = at[2], Z = at[3] }, false, {}, false)
        elseif hide[name] then
            component:SetVisibility(false, false)
        end
    end
end

local function bind(actor)
    local name = className(actor)
    local entry = name and state.table[name]
    if type(entry) ~= "table" then return end
    -- The sweep and the watch can both report a vehicle.
    local address = actor:GetAddress()
    for _, bound in ipairs(state.bound) do
        if bound.address == address and bound.actor:IsValid() then return end
    end
    local runs = {}
    for _, sound in ipairs(entry.sounds or {}) do
        runs[#runs + 1] = { sound = sound, loops = {}, shots = {} }
    end
    state.bound[#state.bound + 1] = { actor = actor, address = address, entry = entry, runs = runs }
    placeLights(actor, entry.lights)
    env.Log(string.format("vehicle sounds: %s, %d sound(s)", name, #runs))
end

local function loadTable(level)
    -- A reload keeps the world, so a loop dropped here would play on for good.
    for _, bound in ipairs(state.bound) do silence(bound) end
    state.table, state.bound = {}, {}
    if type(level) ~= "table" or not level._dir then return end
    local raw = env.readFile(level._dir .. "\\vehicle_sounds.json")
    if not raw then return end
    local ok, t = pcall(env.decode, raw)
    if ok and type(t) == "table" then
        state.table = t
        -- A placed vehicle can be made before this file is read, and a joiner's
        -- before the loader looks: one scan a class, once a level.
        for class in pairs(t) do
            local found, actors = pcall(FindAllOf, class)
            if found and type(actors) == "table" then
                for _, actor in ipairs(actors) do state.new[#state.new + 1] = actor end
            end
        end
    else
        env.Log("vehicle_sounds.json: " .. tostring(t))
    end
end

--- A tick: the vehicles made since the last, then every vehicle with sounds.
function VehicleSounds.tick()
    if not env then return end
    local level = env.Current.level
    if level ~= state.level then
        state.level = level
        loadTable(level)
    end
    if not state.table or next(state.table) == nil then
        state.new = {}
        return
    end
    local new = state.new
    state.new = {}
    for _, actor in ipairs(new) do
        local ok, err = pcall(function() if actor:IsValid() then bind(actor) end end)
        if not ok then env.Log("vehicle sounds: " .. tostring(err)) end
    end
    if #state.bound == 0 then return end
    local world = env.getWorld()
    if not (world and world:IsValid()) then return end
    state.kismet = state.kismet or env.findObject("/Script/Engine.Default__KismetSystemLibrary")
    local now = state.kismet:GetGameTimeInSeconds(world)
    for i = #state.bound, 1, -1 do
        local bound = state.bound[i]
        -- A handle reads freed memory once its actor is gone: check every use.
        if bound.actor:IsValid() then
            local ok, err = pcall(update, bound, world, now)
            if not ok then
                env.Log("vehicle sounds: " .. tostring(err))
                silence(bound)
                table.remove(state.bound, i)
            end
        else
            silence(bound)
            table.remove(state.bound, i)
        end
    end
end

--- A unit component was made: its actor is looked at once it is on one.
local function noted(component)
    -- A level with no table pays nothing; loadTable sweeps for what came first.
    if not state.table or next(state.table) == nil then return end
    ExecuteInGameThreadWithDelay(SETTLE_MS, function()
        pcall(function()
            if not component:IsValid() then return end
            local actor = component:GetOwner()
            if actor and actor:IsValid() then state.new[#state.new + 1] = actor end
        end)
    end)
end

function VehicleSounds.init(deps)
    env = deps
    state.watching = pcall(NotifyOnNewObject, VehicleSounds.WATCH, noted)
    env.Log(state.watching and "vehicle sounds: watching" or "vehicle sounds: could not watch vehicles")
end

return VehicleSounds

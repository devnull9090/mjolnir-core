-- Frame-time benches: what one thing costs, measured in the game.
--
-- `mjolnir_bench` holds the camera where it is and takes turns between the
-- map as it is and the map with one thing taken away: the loader's
-- foliage (grass, tufts, pebbles, shells, leaves: every instanced mesh it
-- scatters), the foliage's shadows, its wind. `mjolnir_bench <cvar> <value>` does the
-- same between a console variable's current value and another (say
-- `mjolnir_bench r.Shadow.Virtual.Enable 0`). Each turn settles for 2.5 s
-- and is then timed for 6 s; the conditions alternate with the baseline,
-- so a slow drift does not read as a cost. The table goes to UE4SS.log and
-- to bench.log in this mod's folder, under a line with the settings it was
-- taken at (Bench.settings), without which a row means nothing on another
-- PC.
--
-- How to read it (docs/performance.md):
-- - The first minutes after a map loads run slow while shaders and textures
--   arrive (Death Island: 12.6 ms against 8.1 steady, 2026-10-17). A bench
--   inside BENCH_WARM seconds of the player entering the world says so.
-- - Frame time is what the slowest of the game thread, the render thread
--   and the GPU allows. A GPU saving shows only on a GPU-bound frame: on a
--   fast card, raise r.ScreenPercentage to 200 to bench GPU costs.
-- - `stat unit` (it works in this Shipping build; `stat gpu` does not)
--   names the slow one. Its Game figure includes the game thread's wait
--   for the GPU, so a GPU change moves Game too.
--
-- Turns are driven from the HUD's frame hook (Hitches.listen), never
-- ExecuteWithDelay: a failing delayed callback took a game-thread hook down
-- with it (2026-10-17).

local Bench = {}

local SETTLE_S, SAMPLE_S = 2.5, 6
local BENCH_WARM = 180
local CVAR_PAIRS = 3
local SG = { "ViewDistance", "AntiAliasing", "Shadow", "GlobalIllumination", "Reflection", "PostProcess",
    "Texture", "Effects", "Foliage", "Shading" }

local log = print
local filePath = nil
local pcOf = function() return nil end
local liveFor = function() return nil end
local mapOf = function() return "?" end

--- The bench under way: steps, the step now, its phase, the results.
local run = nil

local function object(path)
    local ok, o = pcall(StaticFindObject, path)
    if ok and o and o:IsValid() then return o end
    return nil
end

local function ksl() return object("/Script/Engine.Default__KismetSystemLibrary") end

local function append(lines)
    if not filePath then return end
    local f = io.open(filePath, "ab")
    if not f then return end
    for _, line in ipairs(lines) do f:write(line, "\n") end
    f:close()
end

local function say(line)
    log(line)
    append({ line })
end

--------------------------------------------------------------------------------
-- Settings
--------------------------------------------------------------------------------

--- The GPU's name and the score the game's own benchmark gave it
--- (Saved/GpuBenchmark.json, written at the game's first start).
local function gpu()
    local dir = os.getenv("LOCALAPPDATA")
    local f = dir and io.open(dir .. "\\Meteorite\\Saved\\GpuBenchmark.json", "rb")
    if not f then return "GPU ?" end
    local text = f:read("*a") or ""
    f:close()
    return string.format("%s (score %s)", text:match('"cardName"%s*:%s*"([^"]*)"') or "?",
        text:match('"gpuScore"%s*:%s*(%d+)') or "?")
end

--- The viewport as drawn: in borderless the saved resolution is not the
--- one rendered (1280x720 saved, the desktop's size drawn, 2026-10-17).
local function display()
    local gus = object("/Script/Engine.Default__GameUserSettings"):GetGameUserSettings()
    local size = object("/Script/UMG.Default__WidgetLayoutLibrary"):GetViewportSize(pcOf())
    local modes = { [0] = "fullscreen", [1] = "borderless", [2] = "windowed" }
    local limit = gus:GetFrameRateLimit()
    return string.format("%.0fx%.0f %s, vsync %s, fps limit %s", size.X, size.Y, modes[gus:GetFullscreenMode()] or "?",
        gus:IsVSyncEnabled() and "on" or "off", limit > 0 and string.format("%.0f", limit) or "none")
end

local function quality()
    local k = ksl()
    local parts = {}
    for _, name in ipairs(SG) do
        local ok, v = pcall(function() return k:GetConsoleVariableIntValue("sg." .. name .. "Quality") end)
        parts[#parts + 1] = string.format("%s %s", name, ok and tostring(v) or "?")
    end
    local okS, sp = pcall(function() return k:GetConsoleVariableFloatValue("r.ScreenPercentage") end)
    return string.format("sg: %s; r.ScreenPercentage %s", table.concat(parts, ", "),
        okS and string.format("%g", sp) or "?")
end

--- One line: what the numbers beside it were taken on.
function Bench.settings()
    local okD, d = pcall(display)
    local okQ, q = pcall(quality)
    return string.format("settings: %s; %s; %s; CPU %s x%s", okD and d or "display ?", okQ and q or "sg ?", gpu(),
        os.getenv("PROCESSOR_IDENTIFIER") or "?", os.getenv("NUMBER_OF_PROCESSORS") or "?")
end

--------------------------------------------------------------------------------
-- Conditions
--------------------------------------------------------------------------------

--- The level loader's foliage: the hierarchical instanced meshes on the
--- StaticMeshActors it spawns (MJOLNIRLevelLoader Foliage.spawn). One
--- FindAllOf per bench, never per frame (~20 ms on a converted map).
local function foliage()
    local cls = object("/Script/Engine.HierarchicalInstancedStaticMeshComponent")
    local out = {}
    if not cls then return out end
    for _, actor in ipairs(FindAllOf("StaticMeshActor") or {}) do
        if actor:IsValid() then
            local comps = actor:K2_GetComponentsByClass(cls)
            for i = 1, comps and #comps or 0 do
                local c = comps[i]:get()
                if c and c:IsValid() then
                    out[#out + 1] = { c = c, shadow = c.CastShadow, wind = c.bEvaluateWorldPositionOffset }
                end
            end
        end
    end
    return out
end

local function each(list, fn)
    for _, g in ipairs(list) do
        if g.c:IsValid() then fn(g) end
    end
end

local function foliageConditions(list)
    return {
        { name = "no foliage",
            apply = function() each(list, function(g) g.c:SetVisibility(false, false) end) end,
            undo = function() each(list, function(g) g.c:SetVisibility(true, false) end) end },
        { name = "no foliage shadows",
            apply = function() each(list, function(g) if g.shadow then g.c:SetCastShadow(false) end end) end,
            undo = function() each(list, function(g) if g.shadow then g.c:SetCastShadow(true) end end) end },
        { name = "no foliage wind",
            apply = function() each(list, function(g) if g.wind then g.c:SetEvaluateWorldPositionOffset(false) end end) end,
            undo = function() each(list, function(g) if g.wind then g.c:SetEvaluateWorldPositionOffset(true) end end) end },
    }
end

local function console(cmd)
    local pc = pcOf()
    ksl():ExecuteConsoleCommand(pc and pc:GetWorld() or nil, cmd, pc)
end

local function cvarCondition(name, value)
    local before = ksl():GetConsoleVariableFloatValue(name)
    local was = string.format("%g", before)
    return { name = name .. " " .. value,
        apply = function() console(name .. " " .. value) end,
        undo = function() console(name .. " " .. was) end }, was
end

--------------------------------------------------------------------------------
-- Camera
--------------------------------------------------------------------------------

--- Holds the view where the camera is now, so a player walking off does
--- not change the scene under a bench.
local function lockView(r)
    local pc = pcOf()
    local cam = pc.PlayerCameraManager
    local l, o = cam:GetCameraLocation(), cam:GetCameraRotation()
    local at, rot = { X = l.X, Y = l.Y, Z = l.Z }, { Pitch = o.Pitch, Yaw = o.Yaw, Roll = o.Roll }
    r.viewTarget = pc:GetViewTarget()
    r.camera = pc:GetWorld():SpawnActor(object("/Script/Engine.CameraActor"), at, rot)
    pc:SetViewTargetWithBlend(r.camera, 0, 0, 0, false)
    return string.format("(%.0f, %.0f, %.0f) pitch %.1f yaw %.1f", at.X, at.Y, at.Z, rot.Pitch, rot.Yaw)
end

local function unlockView(r)
    pcall(function()
        local pc = pcOf()
        if r.viewTarget and r.viewTarget:IsValid() then pc:SetViewTargetWithBlend(r.viewTarget, 0, 0, 0, false) end
    end)
    pcall(function() if r.camera and r.camera:IsValid() then r.camera:K2_DestroyActor() end end)
end

--------------------------------------------------------------------------------
-- The run
--------------------------------------------------------------------------------

local function mean(list)
    local sum = 0
    for _, v in ipairs(list) do sum = sum + v end
    return sum / #list
end

local function report(r)
    local base = r.ms.base
    local b = mean(base)
    local lo, hi = math.huge, 0
    for _, v in ipairs(base) do lo, hi = math.min(lo, v), math.max(hi, v) end
    say(string.format("bench on %s: base %.2f ms (%.0f fps), %d runs from %.2f to %.2f", r.map, b, 1000 / b, #base, lo, hi))
    for _, name in ipairs(r.order) do
        local m = mean(r.ms[name])
        say(string.format("bench on %s:   %-28s %.2f ms  %+.2f ms  %+.1f%%", r.map, name, m, m - b, (m - b) * 100 / b))
    end
end

local function finish(r, why)
    run = nil
    unlockView(r)
    if why then
        -- Stopped mid-turn: put back what this turn took away.
        local step = r.steps[r.i]
        if step and step.applied then pcall(step.undo) end
        say("bench stopped: " .. why)
        return
    end
    report(r)
end

local function begin(r, t)
    local step = r.steps[r.i]
    step.applied = true
    local ok, err = pcall(step.apply)
    if not ok then return finish(r, step.name .. ": " .. tostring(err)) end
    r.phase, r.at, r.frames = "settle", t, 0
end

--- Every local frame (Hitches.listen), with os.clock.
function Bench.frame(t)
    local r = run
    if not r then return end
    if r.phase == "settle" then
        if t - r.at >= SETTLE_S then r.phase, r.at, r.frames = "sample", t, 0 end
        return
    end
    r.frames = r.frames + 1
    if t - r.at < SAMPLE_S then return end
    local step = r.steps[r.i]
    local ms = (t - r.at) * 1000 / r.frames
    r.ms[step.key] = r.ms[step.key] or {}
    table.insert(r.ms[step.key], ms)
    step.applied = false
    local ok, err = pcall(step.undo)
    if not ok then return finish(r, step.name .. " undo: " .. tostring(err)) end
    r.i = r.i + 1
    if r.i > #r.steps then return finish(r) end
    begin(r, t)
end

local BASE = { name = "base", key = "base", apply = function() end, undo = function() end }

--- base, a, base, b, base, ... base.
local function interleave(conditions)
    local steps, order = { BASE }, {}
    for _, c in ipairs(conditions) do
        c.key = c.name
        steps[#steps + 1] = c
        steps[#steps + 1] = BASE
        if order[#order] ~= c.name then order[#order + 1] = c.name end
    end
    return steps, order
end

local function start(conditions, what)
    local pc = pcOf()
    if not (pc and pc:GetWorld()) then return "no player in a world to bench" end
    local steps, order = interleave(conditions)
    local r = { steps = steps, order = order, i = 1, ms = {}, map = mapOf() }
    local okV, view = pcall(lockView, r)
    if not okV then
        unlockView(r)
        return "could not hold the camera: " .. tostring(view)
    end
    local live = liveFor()
    append({ "", os.date("== %Y-%m-%d %H:%M:%S ") .. r.map .. ": " .. what .. " ==", Bench.settings(),
        "view: " .. view })
    if not live or live < BENCH_WARM then
        say(string.format("bench: only %s s since the player entered the world; the first minutes read slow",
            live and string.format("%.0f", live) or "0"))
    end
    run = r
    begin(r, os.clock())
    return string.format("bench started: %s, %d turns of %.1f s; stand still, the camera is held",
        what, #steps, SETTLE_S + SAMPLE_S)
end

--- `mjolnir_bench`, `mjolnir_bench <cvar> <value>`, `mjolnir_bench stop`.
function Bench.command(args)
    local a, b = args and args[1], args and args[2]
    if a and a:lower() == "stop" then
        if not run then return "no bench running" end
        finish(run, "stopped from the console")
        return "bench stopped"
    end
    if run then return "a bench is already running (mjolnir_bench stop)" end
    if a and b then
        local okC, c, was = pcall(cvarCondition, a, b)
        if not okC then return "cannot read " .. a .. ": " .. tostring(c) end
        local list = {}
        for i = 1, CVAR_PAIRS do list[i] = c end
        return start(list, string.format("%s %s against %s", a, b, was))
    end
    if a then return "usage: mjolnir_bench | mjolnir_bench <cvar> <value> | mjolnir_bench stop" end
    local list = foliage()
    if #list == 0 then return "no level loader foliage on this map; try mjolnir_bench <cvar> <value>" end
    return start(foliageConditions(list), string.format("foliage (%d meshes)", #list))
end

function Bench.running() return run ~= nil end

function Bench.init(opts)
    log = opts.log or log
    filePath = opts.file
    pcOf = opts.pc or pcOf
    liveFor = opts.liveFor or liveFor
    mapOf = opts.map or mapOf
end

return Bench

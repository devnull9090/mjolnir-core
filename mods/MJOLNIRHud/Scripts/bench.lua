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
local SEND_WARM = 120 -- /bench waits this long; the hub's summary skips younger runs
local CVAR_PAIRS = 3
local SG = { "ViewDistance", "AntiAliasing", "Shadow", "GlobalIllumination", "Reflection", "PostProcess",
    "Texture", "Effects", "Foliage", "Shading" }

local log = print
local filePath = nil
local pcOf = function() return nil end
local liveFor = function() return nil end
local mapOf = function() return "?" end
local dirPath, version = nil, nil
local queue = function() end

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
local function gpu(out)
    local dir = os.getenv("LOCALAPPDATA")
    local f = dir and io.open(dir .. "\\Meteorite\\Saved\\GpuBenchmark.json", "rb")
    if not f then return end
    local text = f:read("*a") or ""
    f:close()
    out.gpu_name = text:match('"cardName"%s*:%s*"([^"]*)"')
    out.gpu_score = tonumber(text:match('"gpuScore"%s*:%s*(%d+)') or "")
end

--- The viewport as drawn: in borderless the saved resolution is not the
--- one rendered (1280x720 saved, the desktop's size drawn, 2026-10-17).
local function display(out)
    local size = object("/Script/UMG.Default__WidgetLayoutLibrary"):GetViewportSize(pcOf())
    out.viewport_w, out.viewport_h = math.floor(size.X + 0.5), math.floor(size.Y + 0.5)
    local gus = object("/Script/Engine.Default__GameUserSettings"):GetGameUserSettings()
    local modes = { [0] = "fullscreen", [1] = "borderless", [2] = "windowed" }
    out.window_mode = modes[gus:GetFullscreenMode()]
    out.vsync = gus:IsVSyncEnabled() == true
    out.fps_limit = gus:GetFrameRateLimit()
end

local function quality(out)
    local k = ksl()
    out.sg = {}
    for _, name in ipairs(SG) do
        local ok, v = pcall(function() return k:GetConsoleVariableIntValue("sg." .. name .. "Quality") end)
        if ok and type(v) == "number" then out.sg[name] = v end
    end
    local okS, sp = pcall(function() return k:GetConsoleVariableFloatValue("r.ScreenPercentage") end)
    if okS then out.screen_percentage = sp end
end

--- What a run was taken on: the size drawn, window mode, vsync, frame
--- limit, every sg.*Quality, r.ScreenPercentage, the GPU and the CPU.
function Bench.settingsTable()
    local out = { sg = {} }
    pcall(display, out)
    pcall(quality, out)
    pcall(gpu, out)
    out.cpu = os.getenv("PROCESSOR_IDENTIFIER")
    out.cpu_threads = tonumber(os.getenv("NUMBER_OF_PROCESSORS") or "")
    return out
end

--- One line: what the numbers beside it were taken on.
function Bench.settings(s)
    s = s or Bench.settingsTable()
    local parts = {}
    for _, name in ipairs(SG) do parts[#parts + 1] = string.format("%s %s", name, tostring(s.sg[name] or "?")) end
    return string.format("settings: %sx%s %s, vsync %s, fps limit %s; sg: %s; r.ScreenPercentage %s; %s (score %s); CPU %s x%s",
        tostring(s.viewport_w or "?"), tostring(s.viewport_h or "?"), s.window_mode or "?", s.vsync and "on" or "off",
        (s.fps_limit or 0) > 0 and string.format("%.0f", s.fps_limit) or "none", table.concat(parts, ", "),
        s.screen_percentage and string.format("%g", s.screen_percentage) or "?", s.gpu_name or "GPU ?",
        tostring(s.gpu_score or "?"), s.cpu or "?", tostring(s.cpu_threads or "?"))
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

--- The player's own body as only others see it (bOwnerNoSee: the
--- "shadow" meshes on the pawn and its weapon). With a camera of ours as
--- the view target the engine draws it, from inside the head; hidden with
--- its shadow kept, the frame is the one the player normally sees.
local function hideOwnBody(r, pc)
    r.body = {}
    local pawn = pc.Pawn
    if not (pawn and pawn:IsValid()) then return end
    local prim = object("/Script/Engine.PrimitiveComponent")
    local actors = { pawn }
    pcall(function()
        local attached = {}
        pawn:GetAttachedActors(attached, true, false)
        for i = 1, #attached do actors[#actors + 1] = attached[i]:get() end
    end)
    for _, actor in ipairs(actors) do
        local comps = actor and actor:IsValid() and actor:K2_GetComponentsByClass(prim)
        for i = 1, comps and #comps or 0 do
            local c = comps[i]:get()
            if c and c:IsValid() and c.bOwnerNoSee and not c.bHiddenInGame then
                r.body[#r.body + 1] = { c = c, castHidden = c.bCastHiddenShadow }
                c.bCastHiddenShadow = true
                c:SetHiddenInGame(true, false)
            end
        end
    end
end

local function showOwnBody(r)
    for _, b in ipairs(r.body or {}) do
        pcall(function()
            if b.c:IsValid() then
                b.c:SetHiddenInGame(false, false)
                b.c.bCastHiddenShadow = b.castHidden
            end
        end)
    end
    r.body = nil
end

--- Holds the view where the camera is now, so a player walking off does
--- not change the scene under a bench.
local function lockView(r)
    local pc = pcOf()
    local cam = pc.PlayerCameraManager
    local l, o = cam:GetCameraLocation(), cam:GetCameraRotation()
    -- No roll: a camera shake's tilt would be held for the whole run.
    local at, rot = { X = l.X, Y = l.Y, Z = l.Z }, { Pitch = o.Pitch, Yaw = o.Yaw, Roll = 0 }
    r.viewTarget = pc:GetViewTarget()
    -- Placed after spawning: SpawnActor's rotation came out rolled and
    -- pitched wrong (spawned at pitch -18.7, roll 0; read back -15.7 and
    -- -10.3, 2026-10-17).
    r.camera = pc:GetWorld():SpawnActor(object("/Script/Engine.CameraActor"), at, { Pitch = 0, Yaw = 0, Roll = 0 })
    r.camera:K2_SetActorLocationAndRotation(at, rot, false, {}, true)
    pcall(hideOwnBody, r, pc)
    pc:SetViewTargetWithBlend(r.camera, 0, 0, 0, false)
    return string.format("(%.0f, %.0f, %.0f) pitch %.1f yaw %.1f", at.X, at.Y, at.Z, rot.Pitch, rot.Yaw)
end

local function unlockView(r)
    showOwnBody(r)
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
    r.summary = { base = b, lo = lo, hi = hi, results = {} }
    for _, name in ipairs(r.order) do
        local m = mean(r.ms[name])
        say(string.format("bench on %s:   %-28s %.2f ms  %+.2f ms  %+.1f%%", r.map, name, m, m - b, (m - b) * 100 / b))
        table.insert(r.summary.results, { name = name, ms = m })
    end
end

--------------------------------------------------------------------------------
-- Sending (the hub's POST /benches, through MJOLNIRLobby's outbox)
--------------------------------------------------------------------------------

local function jstr(v)
    return '"' .. tostring(v):gsub('[%c"\\]', function(c)
        if c == '"' then return '\\"' end
        if c == "\\" then return "\\\\" end
        return string.format("\\u%04x", c:byte())
    end) .. '"'
end

--- Lua value -> JSON: a table with [1] is an array, a fractional number
--- keeps three decimals, a nil field is left out.
local function json(v)
    local t = type(v)
    if t == "nil" then return "null" end
    if t == "boolean" then return v and "true" or "false" end
    if t == "number" then
        if v == math.floor(v) and math.abs(v) < 1e15 then return string.format("%d", v) end
        return string.format("%.3f", v)
    end
    if t ~= "table" then return jstr(v) end
    local parts = {}
    if v[1] ~= nil then
        for _, x in ipairs(v) do parts[#parts + 1] = json(x) end
        return "[" .. table.concat(parts, ",") .. "]"
    end
    local keys = {}
    for k in pairs(v) do keys[#keys + 1] = k end
    table.sort(keys)
    for _, k in ipairs(keys) do parts[#parts + 1] = jstr(k) .. ":" .. json(v[k]) end
    return "{" .. table.concat(parts, ",") .. "}"
end

local seeded = false
local function newId()
    if not seeded then
        -- os.time alone repeats across PCs that start in the same second.
        local salt = tonumber((tostring({}):match("0x(%x+)") or "0"), 16) or 0
        math.randomseed((os.time() + math.floor(os.clock() * 1000000) + salt) % 2147483647)
        seeded = true
    end
    local hex = {}
    for i = 1, 32 do hex[i] = string.format("%x", math.random(0, 15)) end
    return table.concat(hex)
end

--- The run as the hub's BenchReport, written beside this mod and named in
--- the outbox MJOLNIRLobby sends from (its Scripts/matches.lua).
local function submit(r)
    local s, settings = r.summary, r.settings
    if (settings.fps_limit or 0) <= 0 then settings.fps_limit = nil end
    local id = newId()
    local body = json({
        bench_id = id, map_code = r.map, kind = r.kind, label = r.what, settings = settings,
        seconds_in_world = r.live and math.floor(r.live) or nil,
        base_ms = s.base, base_min_ms = s.lo, base_max_ms = s.hi, results = s.results,
        client_version = version,
    })
    local f = dirPath and io.open(dirPath .. "\\bench_" .. id .. ".json", "wb")
    if not f then return false end
    f:write(body)
    f:close()
    queue("bench", id)
    say("bench " .. id .. " queued for the hub")
    return true
end

--- The chat's lines for a finished run: the frame rate, what the foliage
--- costs and its parts.
local function chatLines(r, sent)
    local s, st = r.summary, r.settings
    local by = {}
    for _, x in ipairs(s.results) do by[x.name] = s.base - x.ms end
    local lines = { string.format("Bench on %s at %sx%s: %.0f fps (%.1f ms a frame).", r.map,
        tostring(st.viewport_w or "?"), tostring(st.viewport_h or "?"), 1000 / s.base, s.base) }
    if by["no foliage"] then
        lines[#lines + 1] = string.format("Foliage costs %.1f ms (%.0f%%): its shadows %.1f, its wind %.1f.",
            by["no foliage"], by["no foliage"] * 100 / s.base, by["no foliage shadows"] or 0, by["no foliage wind"] or 0)
    end
    if r.send then
        lines[#lines + 1] = sent and "Sending to the hub: see mjolnircore.com/benchmarks in a minute."
            or "Not sent: the hub outbox could not be written."
    end
    return lines
end

local function finish(r, why)
    run = nil
    unlockView(r)
    if why then
        -- Stopped mid-turn: put back what this turn took away.
        local step = r.steps[r.i]
        if step and step.applied then pcall(step.undo) end
        say("bench stopped: " .. why)
        if r.notify then pcall(r.notify, { "Bench stopped: " .. why .. "." }) end
        return
    end
    report(r)
    local sent = r.send and submit(r)
    if r.notify then pcall(r.notify, chatLines(r, sent)) end
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

--- opts: { kind = "foliage" | "cvar", send, notify (lines) }.
local function start(conditions, what, opts)
    local pc = pcOf()
    if not (pc and pc:GetWorld()) then return "no player in a world to bench" end
    local steps, order = interleave(conditions)
    local r = { steps = steps, order = order, i = 1, ms = {}, map = mapOf(), what = what, kind = opts.kind,
        send = opts.send, notify = opts.notify, settings = Bench.settingsTable(), live = liveFor() }
    local okV, view = pcall(lockView, r)
    if not okV then
        unlockView(r)
        return "could not hold the camera: " .. tostring(view)
    end
    local live = r.live
    append({ "", os.date("== %Y-%m-%d %H:%M:%S ") .. r.map .. ": " .. what .. " ==", Bench.settings(r.settings),
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

local function foliageBench(opts)
    local list = foliage()
    if #list == 0 then return nil end
    opts.kind = "foliage"
    return start(foliageConditions(list), string.format("foliage (%d meshes)", #list), opts)
end

--- `/bench` in match chat: the foliage bench, sent to the hub, its result
--- back in the chat through `notify`. Returns the lines to answer with now.
function Bench.chat(notify)
    if run then return { "A bench is already running." } end
    local live = liveFor()
    if not live or live < SEND_WARM then
        return { string.format("Wait %d more seconds: the first minutes on a map run slow while it loads in.",
            math.ceil(SEND_WARM - (live or 0))) }
    end
    local said = foliageBench({ send = true, notify = notify })
    if not said then return { "This map has no MJOLNIR foliage to bench." } end
    if not run then return { "Bench: " .. said } end
    return { "Benching for about a minute: the camera is held, so stay somewhere safe." }
end

--- `mjolnir_bench`, `mjolnir_bench send`, `mjolnir_bench <cvar> <value>`,
--- `mjolnir_bench stop`.
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
        return start(list, string.format("%s %s against %s", a, b, was), { kind = "cvar" })
    end
    if a and a:lower() ~= "send" then
        return "usage: mjolnir_bench [send] | mjolnir_bench <cvar> <value> | mjolnir_bench stop"
    end
    return foliageBench({ send = a ~= nil })
        or "no level loader foliage on this map; try mjolnir_bench <cvar> <value>"
end

function Bench.running() return run ~= nil end

--- opts: { log, file (bench.log), dir (this mod's folder), queue (kind, id),
--- version, pc, liveFor, map }.
function Bench.init(opts)
    log = opts.log or log
    filePath = opts.file
    dirPath = opts.dir
    queue = opts.queue or queue
    version = opts.version
    pcOf = opts.pc or pcOf
    liveFor = opts.liveFor or liveFor
    mapOf = opts.map or mapOf
end

return Bench

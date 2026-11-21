-- Installs a session-scoped observer. The controller hook stays idle outside measured windows.
assert(not PWRAlpineBench, "An alpine benchmark observer already exists")
local pc = assert(mj.pc())
local world = pc:GetWorld()
assert(world:GetFullName() == "World /Game/Levels/Halo1/Solo/PWR/PWR.PWR")
local times = assert(package.loadlib(__DLL__, "mjolnir_frame_times_sample"))
local flush = assert(package.loadlib(__DLL__, "mjolnir_frame_times_flush"))
local function enginePeriods()
    flush()
    local file = assert(io.open(__TIMES__, "rb"), "Native frame telemetry did not publish a result")
    local line = file:read("*l") or ""
    file:close()
    assert(line:match("^ok %d+ "), "Native frame telemetry unavailable: " .. line)
    return line
end
enginePeriods() -- Resolve and prime outside all measured windows.
local gs = StaticFindObject("/Script/Engine.Default__GameplayStatics")
local s = {pc = pc, address = pc:GetAddress(), func = "/Game/Blueprints/BP_MeteoritePlayerController.BP_MeteoritePlayerController_C:ReceiveTick"}
function s.begin(seconds)
    assert(not s.active and seconds >= 3 and seconds <= 60)
    enginePeriods()
    s.window = {duration=seconds, n=0, hist={}, elapsed=0, max=0, started=false, done=false}
    s.active = true
end
local function tick(context)
    if not s.active or context:get():GetAddress() ~= s.address then return end
    local t = os.clock()
    local w = s.window
    if not w.started then
        w.started = true
        w.start, w.last, w.engineStart = t, t, gs:GetRealTimeSeconds(pc)
        return
    end
    local ms = 1000 * (t - w.last)
    w.last, w.elapsed = t, t-w.start
    w.n = w.n + 1
    w.max = math.max(w.max, ms)
    local bin = math.max(0, math.floor(ms * 10 + 0.5))
    w.hist[bin] = (w.hist[bin] or 0) + 1
    times()
    if w.elapsed >= w.duration then
        s.active = false
        w.engineElapsed = gs:GetRealTimeSeconds(pc) - w.engineStart
        -- Both clocks and all samples are closed before flushing the native accumulator.
        local ok, readback = pcall(enginePeriods)
        w.native, w.done = ok and readback or ("ERROR " .. tostring(readback)), true
    end
end
s.pre, s.post = RegisterHook(s.func, tick)
PWRAlpineBench = s
print("BENCH_READY")


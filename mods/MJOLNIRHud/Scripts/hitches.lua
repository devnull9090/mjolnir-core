-- Frame hitches: how long each frame took, and the frames that ran long
-- against the ones around them.
--
-- Players report "stutters" on the converted maps, and the kind of stutter
-- points at the cause: a hitch the first time something comes into view is
-- the GPU building a pipeline state for a new material, a steady beat is a
-- periodic job (garbage collection, one of our loops), and a hitch on every
-- kill is work done per event. Each hitch is logged with where the camera
-- was and which of our Lua loops ran in that frame. When a map ends, its
-- frame times are summed up: median, 95th and 99th percentile, worst frame,
-- hitches by size, and the time each Lua loop took. Everything goes to
-- UE4SS.log and to hitches.log in this mod's folder, which, unlike
-- UE4SS.log, survives the game's next start.
--
-- Frames are timed between the local player controller's ticks (main.lua's
-- frame hook) on os.clock, which counts milliseconds on Windows. A frame is
-- a hitch when it took 1.8 times the median of the last 120 frames and at
-- least 8 ms more. Frames before the player is in the world (their pawn
-- off the origin) do not count. A frame of a second or more is logged on
-- its own, loading or not.
--
-- The other mods' loops report each run that read a millisecond or more
-- through the UE4SS shared variable MJOLNIR.work, as
-- "<start>|<mod>|<loop>|<ms>;". Each mod is its own Lua state, and a shared
-- variable is the one thing they all see.
--
-- Only the frame's length is known here, not where the engine spent it:
-- `stat unit` tells a game-thread frame from a GPU one.
--
-- `mjolnir_hitches` (console): this map's numbers so far. `off` / `on`
-- stop and restart the timing, `reset` starts the numbers again.

local Hitches = {}

local WORK_KEY = "MJOLNIR.work"
local RING = 120           -- frames in the rolling median
local RATIO, OVER = 1.8, 8 -- a hitch: RATIO times the median, and OVER ms more
local LONG_MS = 1000       -- a frame this long is logged on its own
local LINES_PER_MINUTE = 30
local SO_FAR_SECONDS = 300 -- this often, a summary so far into hitches.log
local FILE_CAP = 512 * 1024
local TOP_LOOPS = 8

local log = print
local filePath = nil
local modRef = rawget(_G, "ModRef")

--- This world's numbers; nil in the menu.
local S = nil
local state = { on = true, world = nil, pc = nil, last = nil }

local function fresh(world)
    return {
        world = world, live = false, liveAt = 0, soFarAt = 0,
        ring = {}, ringNext = 1, ringHist = {}, ringCount = 0, median = nil, sinceMedian = 0,
        hist = {}, frames = 0, worst = 0, long = {},
        hitches = 0, buckets = { 0, 0, 0, 0 }, lastHitchAt = nil,
        windowAt = -100, printed = 0, unprinted = 0,
        recent = {}, work = {},
    }
end

local function append(lines)
    if not filePath then return end
    local f = io.open(filePath, "ab")
    if not f then return end
    for _, line in ipairs(lines) do f:write(line, "\n") end
    f:close()
end

local function say(line, fileOnly)
    if not fileOnly then log(line) end
    append({ os.date("%H:%M:%S ") .. line })
end

--------------------------------------------------------------------------------
-- Our loops' work
--------------------------------------------------------------------------------

local function addWork(s, start, name, ms)
    -- Runs from before the player was in the world (the loader dressing
    -- the map, the menu's loops waiting in the variable) are not play.
    if s.live and start >= s.liveAt then
        local w = s.work[name]
        if not w then
            w = { ms = 0, worst = 0 }
            s.work[name] = w
        end
        w.ms = w.ms + ms
        if ms > w.worst then w.worst = ms end
    end
    local r = s.recent
    r[#r + 1] = { start, name, ms }
    if #r > 64 then table.remove(r, 1) end
end

local function getWork() return modRef:GetSharedVariable(WORK_KEY) end
local function clearWork() modRef:SetSharedVariable(WORK_KEY, "") end

--- The runs the other mods reported since the last frame.
local function collect(s)
    if not modRef then return end
    local ok, w = pcall(getWork)
    if not ok or type(w) ~= "string" or w == "" then return end
    pcall(clearWork)
    for start, mod, loop, ms in w:gmatch("([%d%.]+)|([^|;]*)|([^|;]*)|([%d%.]+);") do
        addWork(s, tonumber(start), mod .. " " .. loop, tonumber(ms))
    end
end

--- The loops that started between two ticks, i.e. ran in that frame.
local function ranIn(s, from, to)
    local names = {}
    for _, e in ipairs(s.recent) do
        if e[1] >= from - 0.0005 and e[1] <= to + 0.0005 then
            names[#names + 1] = string.format("%s %.0f ms", e[2], e[3])
        end
    end
    return #names > 0 and table.concat(names, ", ") or "none of our timed loops"
end

--- A run of this HUD's own (its poll), reported straight in.
function Hitches.work(mod, loop, started, took)
    if S and took >= 0.001 then addWork(S, started, mod .. " " .. loop, math.floor(took * 1000 + 0.5)) end
end

--------------------------------------------------------------------------------
-- Frames
--------------------------------------------------------------------------------

local function count(s, ms)
    s.frames = s.frames + 1
    s.hist[ms] = (s.hist[ms] or 0) + 1
    if ms > s.worst then s.worst = ms end
    local old = s.ring[s.ringNext]
    if old then
        s.ringHist[old] = s.ringHist[old] - 1
    else
        s.ringCount = s.ringCount + 1
    end
    s.ring[s.ringNext] = ms
    s.ringHist[ms] = (s.ringHist[ms] or 0) + 1
    s.ringNext = s.ringNext % RING + 1
    s.sinceMedian = s.sinceMedian + 1
    if s.ringCount >= RING / 2 and (s.sinceMedian >= 30 or not s.median) then
        s.sinceMedian = 0
        local acc, half = 0, s.ringCount / 2
        for v = 0, LONG_MS do
            acc = acc + (s.ringHist[v] or 0)
            if acc >= half then
                s.median = math.max(v, 1)
                break
            end
        end
    end
end

local function percentile(s, p)
    local want, acc = s.frames * p, 0
    for v = 0, LONG_MS do
        acc = acc + (s.hist[v] or 0)
        if acc >= want then return v end
    end
    return s.worst
end

local function cameraOf(ctx)
    local cm = ctx:get().PlayerCameraManager
    local at, rot = cm:GetCameraLocation(), cm:GetCameraRotation()
    return string.format(" at (%.0f, %.0f, %.0f) facing %.0f", at.X, at.Y, at.Z, rot.Yaw)
end

local function hitch(s, ctx, from, to, ms)
    s.hitches = s.hitches + 1
    local b = ms < 50 and 1 or ms < 100 and 2 or ms < 250 and 3 or 4
    s.buckets[b] = s.buckets[b] + 1
    local since = s.lastHitchAt and string.format(", %.1f s after the last", to - s.lastHitchAt) or ""
    s.lastHitchAt = to
    if to - s.windowAt >= 60 then s.windowAt, s.printed = to, 0 end
    if s.printed >= LINES_PER_MINUTE then
        s.unprinted = s.unprinted + 1
        return
    end
    s.printed = s.printed + 1
    local okCam, cam = pcall(cameraOf, ctx)
    say(string.format("hitch: %d ms frame on %s (median %d ms), %.1f s in%s%s; Lua: %s",
        ms, s.world, s.median, from - s.liveAt, since, okCam and cam or "", ranIn(s, from, to)))
end

local function longFrame(s, from, to, ms)
    s.long[#s.long + 1] = ms
    say(string.format("long frame: %.1f s on %s, %s; Lua: %s", ms / 1000, s.world,
        s.live and string.format("%.1f s in", from - s.liveAt) or "before the player was in the world",
        ranIn(s, from, to)))
end

local function addressOf(ctx) return ctx:get():GetAddress() end

--- Every call of the player controller tick hook: on a host it runs once
--- per controller each frame, and only the local one times the frame.
function Hitches.frame(ctx, t)
    local s = S
    if not (state.on and s and state.pc) then return end
    local ok, address = pcall(addressOf, ctx)
    if not ok or address ~= state.pc then return end
    collect(s)
    local from = state.last
    state.last = t
    if not from then return end
    local ms = math.floor((t - from) * 1000 + 0.5)
    if ms >= LONG_MS then return longFrame(s, from, t, ms) end
    if not s.live then return end
    if s.median and ms >= RATIO * s.median and ms >= s.median + OVER then hitch(s, ctx, from, t, ms) end
    count(s, ms)
end

--------------------------------------------------------------------------------
-- Summaries
--------------------------------------------------------------------------------

local function duration(seconds)
    seconds = math.max(0, math.floor(seconds + 0.5))
    return string.format("%d min %02d s", math.floor(seconds / 60), seconds % 60)
end

local function summary(s, label, fileOnly)
    if not (s and s.live and s.frames > 0) then return end
    local played = math.max(os.clock() - s.liveAt, 1)
    local long = ""
    if #s.long > 0 then
        local worst = 0
        for _, ms in ipairs(s.long) do worst = math.max(worst, ms) end
        long = string.format("; %d frame(s) of a second or more, the longest %.1f s", #s.long, worst / 1000)
    end
    say(string.format("frames on %s%s: %s, %d frames, median %d ms, p95 %d ms, p99 %d ms, worst %d ms; "
        .. "%d hitch(es): %d under 50 ms, %d of 50-100 ms, %d of 100-250 ms, %d over 250 ms%s%s",
        s.world, label, duration(played), s.frames, percentile(s, 0.5), percentile(s, 0.95),
        percentile(s, 0.99), s.worst, s.hitches, s.buckets[1], s.buckets[2], s.buckets[3], s.buckets[4],
        s.unprinted > 0 and string.format(" (%d not logged one by one)", s.unprinted) or "", long), fileOnly)
    local loops = {}
    for name, w in pairs(s.work) do loops[#loops + 1] = { name = name, ms = w.ms, worst = w.worst } end
    table.sort(loops, function(a, b) return a.ms > b.ms end)
    local parts = {}
    for i = 1, math.min(#loops, TOP_LOOPS) do
        local l = loops[i]
        parts[#parts + 1] = string.format("%s %.1f ms/s (worst %.0f ms)", l.name, l.ms / played, l.worst)
    end
    say(string.format("Lua on %s%s: %s", s.world, label,
        #parts > 0 and table.concat(parts, ", ") or "no loop run read a millisecond"), fileOnly)
end

--------------------------------------------------------------------------------
-- The poll and the command
--------------------------------------------------------------------------------

--- The player is in the world once their pawn has left the origin: it
--- waits there until the simulation starts, through the loader dressing
--- the map (a 16 s frame on Death Island, 2026-10-17).
local function pawnOf(pc)
    local pawn = pc.Pawn
    if not (pawn and pawn:IsValid()) then return false end
    local p = pawn:K2_GetActorLocation()
    return math.abs(p.X) + math.abs(p.Y) > 1
end

local function addressOfPc(pc) return pc:GetAddress() end

--- Each HUD poll, with the local controller and the world's scenario code.
--- Returns whether this world's frames are timed (every map, not the menu).
function Hitches.poll(pc, world)
    local timed = world ~= nil and world ~= "FRONTEND" and not world:find("SEAMLESSTRAVEL", 1, true)
    if world ~= state.world then
        summary(S, "", false)
        state.world, state.last = world, nil
        S = timed and fresh(world) or nil
        if S then append({ "", os.date("== %Y-%m-%d %H:%M:%S ") .. world .. " ==" }) end
    end
    if not (S and pc) then
        state.pc = nil
        return false
    end
    local ok, address = pcall(addressOfPc, pc)
    address = ok and address or nil
    if address ~= state.pc then state.pc, state.last = address, nil end
    local t = os.clock()
    if not S.live then
        local okPawn, here = pcall(pawnOf, pc)
        if okPawn and here then S.live, S.liveAt, S.soFarAt = true, t, t end
    elseif t - S.soFarAt >= SO_FAR_SECONDS then
        S.soFarAt = t
        summary(S, " so far", true)
    end
    return timed
end

function Hitches.command(args)
    local a = (args and args[1] or ""):lower()
    if a == "off" then
        state.on = false
        return "hitch log off"
    elseif a == "on" then
        state.on, state.last = true, nil
        return "hitch log on"
    elseif a == "reset" then
        if S then
            local live = S.live
            S = fresh(S.world)
            if live then S.live, S.liveAt, S.soFarAt = true, os.clock(), os.clock() end
        end
        return "hitch numbers reset"
    end
    if not (S and S.live and S.frames > 0) then return "no frames timed on this map yet" end
    summary(S, " so far", false)
    return "hitch summary written to UE4SS.log and hitches.log"
end

function Hitches.init(opts)
    log = opts.log or log
    filePath = opts.file
    -- Past the cap the file starts again, the one before kept as hitches.old.log.
    local f = filePath and io.open(filePath, "rb")
    if f then
        local size = f:seek("end")
        f:close()
        if size and size > FILE_CAP then
            local old = filePath:gsub("%.log$", ".old.log")
            os.remove(old)
            os.rename(filePath, old)
        end
    end
    if not modRef then log("hitch log: no ModRef, the other mods' loops will not be named") end
end

return Hitches

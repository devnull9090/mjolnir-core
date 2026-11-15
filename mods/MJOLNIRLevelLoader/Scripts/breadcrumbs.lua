--- What a map load was doing when the game died: one line a step, written
--- straight to disk (unbuffered), so the last line survives a crash.
---
--- The game is a Shipping build: Unreal's own log is compiled out, and a
--- crash leaves a dump with stacks but no idea which map step or asset was
--- loading. tools/crash/analyze.py prints this file's last lines beside a
--- crash written within a minute of it (2026-11-15: a night of
--- "I/O Error (Not Found)" crashes took hours of bisecting to pin on one
--- container).
---
--- File: <mod>/breadcrumbs.txt, started afresh at each map load, at most
--- MAX_LINES lines (asset lines stop first; step lines keep going).
local Crumbs = {}

local MAX_LINES = 4000
local MAX_ASSETS = 3000

local file, lines, assets = nil, 0, 0
local dir = nil

function Crumbs.init(modDir)
    dir = modDir
end

local function stamp()
    local t = os.clock()
    return os.date("%H:%M:%S") .. string.format(".%03d", math.floor((t % 1) * 1000))
end

local function write(kind, text)
    if not file or lines >= MAX_LINES then return end
    lines = lines + 1
    pcall(function() file:write(stamp(), " ", kind, " ", tostring(text), "\n") end)
end

--- A map's load begins: a fresh file, headed with the map and version.
function Crumbs.begin(what, version)
    if not dir then return end
    if file then pcall(function() file:close() end) end
    file, lines, assets = nil, 0, 0
    local ok, f = pcall(io.open, dir .. "\\breadcrumbs.txt", "w")
    if not ok or not f then return end
    pcall(function() f:setvbuf("no") end)
    file = f
    write("begin", tostring(what) .. " (MJOLNIRLevelLoader " .. tostring(version) .. ")")
end

--- A step is about to run.
function Crumbs.step(name)
    write("step", name)
end

--- A step finished (the load timer's laps).
function Crumbs.done(name)
    write("done", name)
end

--- An asset is about to be loaded from disk (not one already in memory).
function Crumbs.asset(path)
    if assets >= MAX_ASSETS then return end
    assets = assets + 1
    write("load", path)
end

--- Anything else worth a line.
function Crumbs.note(text)
    write("note", text)
end

--- The load is over: the file stays as the record of the last load.
function Crumbs.finish(text)
    write("end", text or "dressed")
    if file then pcall(function() file:close() end) end
    file = nil
end

return Crumbs

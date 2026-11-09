-- MJOLNIR Level Loader: a load's steps, a few to a frame.
--
-- Dressing a converted map is thousands of calls into the engine: the
-- baked scenery, the foliage, the landscape's materials. Made in one go
-- they held the game thread for one frame of 1.5 s on Timberland
-- (docs/lua_native_audit.md, "Lua fixes" #3). Native code cannot take
-- that work over: it is UE4SS calls on objects only Lua can hold. Spread
-- over frames, each frame takes only a slice of it.
--
-- Run a list of steps ({ name, fn, alone }) in order, on the game thread:
-- each frame runs steps until its budget is spent, and the next frame goes
-- on from there (UE4SS-settings.ini DefaultExecuteInGameThreadMethod =
-- EngineTick: a deferred call runs on a later engine tick, one batch a
-- frame).
--
-- - `fn(deadline)` does the step's work. A step with a long list to get
--   through (the baked pieces) works on it until os.clock() passes
--   `deadline`, and returns true while it has more: it is called again on
--   the next frame. Any other return ends the step.
-- - `alone`: the step starts a frame of its own, for a single call that
--   cannot be cut (a whole-array scan, ~20 ms) and would otherwise land on
--   a frame that has spent its budget already.
-- - An error ends its step, not the load: it is handed to `onError` and the
--   next step runs.

local Dress = {}

--- Lua time a frame may spend before the next step waits for the next
--- frame. A step that is already running is not cut, so a frame can run
--- over by one step's length.
Dress.BUDGET_MS = 12

--- opts:
---   defer(fn)          run fn on a later frame
---   alive()            false once the load is stale (another world, a
---                      reload): the remaining steps are dropped
---   clock()            seconds, os.clock by default
---   budget             ms a frame, Dress.BUDGET_MS by default
---   onError(name, err)
---   onFrame(started, took, names)   each frame's Lua time and its steps
---   onDone(stats)      once every step has run
--- Returns the stats it keeps as it goes: frames, busy and wall seconds,
--- the longest frame (seconds) and its steps, the shortest gap between two
--- frames, and `cancelled` once a stale load was dropped.
function Dress.run(steps, opts)
    local clock = opts.clock or os.clock
    local budget = (opts.budget or Dress.BUDGET_MS) / 1000
    local stats = { frames = 0, busy = 0, longest = 0, longestSteps = "", minGap = nil, startedAt = clock() }
    local i, lastEnd = 1, nil
    local function frame()
        local okAlive, alive = pcall(opts.alive)
        if not (okAlive and alive) then
            stats.cancelled = true
            return
        end
        local started = clock()
        if lastEnd then
            local gap = started - lastEnd
            if not stats.minGap or gap < stats.minGap then stats.minGap = gap end
        end
        local deadline = started + budget
        local names = {}
        while i <= #steps do
            local s = steps[i]
            if s.alone and #names > 0 then break end
            local ok, more = pcall(s.fn, deadline)
            names[#names + 1] = s.name
            if not ok then
                if opts.onError then pcall(opts.onError, s.name, more) end
                more = false
            end
            if more == true then break end
            i = i + 1
            if clock() >= deadline then break end
        end
        local now = clock()
        local took = now - started
        lastEnd = now
        stats.frames = stats.frames + 1
        stats.busy = stats.busy + took
        if took > stats.longest then stats.longest, stats.longestSteps = took, table.concat(names, " + ") end
        if opts.onFrame then pcall(opts.onFrame, started, took, names) end
        if i > #steps then
            stats.wall = now - stats.startedAt
            if opts.onDone then pcall(opts.onDone, stats) end
            return
        end
        opts.defer(frame)
    end
    opts.defer(frame)
    return stats
end

--- A step that works through `list` a slice a frame: `each(item, index)`
--- for every item, until the frame's deadline. `each` errors are caught
--- per item (handed to `onError(item, index, err)` when given), so one bad
--- item does not stop the rest. `clock` defaults to os.clock.
function Dress.slices(list, each, onError, clock)
    clock = clock or os.clock
    local index = 1
    return function(deadline)
        while index <= #list do
            local ok, err = pcall(each, list[index], index)
            if not ok and onError then pcall(onError, list[index], index, err) end
            index = index + 1
            if index <= #list and clock() >= deadline then return true end
        end
        return false
    end
end

return Dress

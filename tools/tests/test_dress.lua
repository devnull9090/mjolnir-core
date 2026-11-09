-- Plain checks for MJOLNIRLevelLoader's dress.lua (a load's steps spread
-- over frames); run with stock Lua from the repository root.
package.path = "mods/MJOLNIRLevelLoader/Scripts/?.lua;" .. package.path
local Dress = require("dress")

--- A fake game thread: a clock steps only advance, and a queue of deferred
--- calls, one frame each.
local function harness()
    local h = { now = 0, queue = {}, frames = {}, ran = {} }
    h.clock = function() return h.now end
    h.defer = function(fn) h.queue[#h.queue + 1] = fn end
    --- Run the deferred calls frame by frame, 5 ms of engine time between.
    function h.drain(limit)
        local n = 0
        while #h.queue > 0 do
            n = n + 1
            assert(n <= (limit or 1000), "the load never ended")
            local fn = table.remove(h.queue, 1)
            h.now = h.now + 0.005
            h.frames[#h.frames + 1] = {}
            fn()
        end
        return n
    end
    --- A step that takes `ms` of the fake clock.
    function h.step(name, ms, alone)
        return { name = name, alone = alone, fn = function()
            h.now = h.now + ms / 1000
            h.ran[#h.ran + 1] = name
            local f = h.frames[#h.frames]
            f[#f + 1] = name
        end }
    end
    return h
end

-- Nothing runs in the frame that asks: the first step waits for the next.
do
    local h = harness()
    Dress.run({ h.step("a", 1) }, { defer = h.defer, clock = h.clock, alive = function() return true end })
    assert(#h.ran == 0, "the load starts on a later frame")
    h.drain()
    assert(#h.ran == 1)
end

-- Steps share a frame until its budget is spent; the rest go to the next.
do
    local h = harness()
    local done
    Dress.run({ h.step("a", 4), h.step("b", 4), h.step("c", 4), h.step("d", 4), h.step("e", 4) },
        { defer = h.defer, clock = h.clock, budget = 10, alive = function() return true end,
          onDone = function(stats) done = stats end })
    h.drain()
    assert(table.concat(h.ran, "") == "abcde", "every step runs, in order")
    assert(#h.frames == 2, "two frames: a, b, c spend the first's 10 ms, got " .. #h.frames)
    assert(table.concat(h.frames[1], "") == "abc" and table.concat(h.frames[2], "") == "de")
    assert(done and done.frames == 2, "onDone once every step has run")
    assert(math.abs(done.busy - 0.020) < 1e-9, "busy is the steps' time")
    assert(math.abs(done.longest - 0.012) < 1e-9 and done.longestSteps == "a + b + c")
    assert(math.abs(done.minGap - 0.005) < 1e-9, "the gap between frames is the engine's time")
end

-- A step marked alone starts a frame of its own.
do
    local h = harness()
    Dress.run({ h.step("a", 1), h.step("scan", 20, true), h.step("b", 1) },
        { defer = h.defer, clock = h.clock, budget = 10, alive = function() return true end })
    h.drain()
    assert(table.concat(h.frames[1], ",") == "a", "the scan does not join a frame that ran something")
    assert(table.concat(h.frames[2], ",") == "scan", "it ran over budget: b waits")
    assert(table.concat(h.frames[3], ",") == "b")
end

-- A long list, a slice a frame: Dress.slices stops at the deadline and
-- picks up where it stopped.
do
    local h = harness()
    local list, seen = {}, {}
    for i = 1, 50 do list[i] = i end
    local slices = Dress.slices(list, function(item, index)
        assert(item == index)
        seen[#seen + 1] = item
        h.now = h.now + 0.001
    end, nil, h.clock)
    local done
    Dress.run({ { name = "list", fn = slices }, h.step("after", 1) },
        { defer = h.defer, clock = h.clock, budget = 10, alive = function() return true end,
          onDone = function(stats) done = stats end })
    h.drain()
    assert(#seen == 50, "every item once")
    for i = 1, 50 do assert(seen[i] == i, "in order") end
    assert(done.frames == 6, "ten items a 10 ms frame, then the step after on its own; got " .. done.frames)
    assert(done.longest <= 0.0101, "no frame runs past its budget by more than one item")
end

-- An error ends its step, not the load; a bad item, not its list.
do
    local h = harness()
    local errors = {}
    local list = { 1, 2, 3 }
    local done
    Dress.run({
        { name = "broken", fn = function() error("boom") end },
        { name = "list", fn = Dress.slices(list, function(item)
            if item == 2 then error("bad item") end
            h.ran[#h.ran + 1] = item
        end, function(item, _, err) errors[#errors + 1] = "item " .. item .. ": " .. tostring(err) end, h.clock) },
        h.step("after", 1),
    }, { defer = h.defer, clock = h.clock, alive = function() return true end,
         onError = function(name, err) errors[#errors + 1] = name .. ": " .. tostring(err) end,
         onDone = function(stats) done = stats end })
    h.drain()
    assert(done, "the load finished")
    assert(#errors == 2 and errors[1]:find("^broken: .*boom") and errors[2]:find("^item 2: .*bad item"))
    assert(h.ran[1] == 1 and h.ran[2] == 3 and h.ran[3] == "after", "the rest ran")
end

-- A stale load (another world, a reload) drops its remaining steps.
do
    local h = harness()
    local alive, done = true, false
    local stats = Dress.run({ h.step("a", 8), h.step("b", 8), h.step("c", 8) },
        { defer = h.defer, clock = h.clock, budget = 10, alive = function() return alive end,
          onDone = function() done = true end })
    local fn = table.remove(h.queue, 1)
    h.frames[1] = {}
    fn()
    assert(table.concat(h.ran, "") == "ab")
    alive = false
    h.drain()
    assert(table.concat(h.ran, "") == "ab" and not done and stats.cancelled, "c never runs, onDone never comes")
end

-- A failing alive() counts as stale rather than stopping the game thread.
do
    local h = harness()
    local stats = Dress.run({ h.step("a", 1) },
        { defer = h.defer, clock = h.clock, alive = function() error("handle gone") end })
    h.drain()
    assert(#h.ran == 0 and stats.cancelled)
end

-- An empty list is done at once.
do
    local h = harness()
    local done
    Dress.run({ { name = "nothing", fn = Dress.slices({}, function() error("never") end, nil, h.clock) } },
        { defer = h.defer, clock = h.clock, alive = function() return true end, onDone = function(s) done = s end })
    h.drain()
    assert(done and done.frames == 1)
end

-- A queue: a step hands lists to a later step, which works through them a
-- slice a frame, in the order they came, lists added mid-run included.
do
    local h = harness()
    local errors = {}
    local q = Dress.queue(function(err) errors[#errors + 1] = tostring(err) end, h.clock)
    local seen = {}
    local function each(item)
        if item == "bad" then error("no component") end
        seen[#seen + 1] = item
        h.now = h.now + 0.001
    end
    local a, b = {}, {}
    for i = 1, 15 do a[i] = "a" .. i end
    for i = 1, 6 do b[i] = "b" .. i end
    b[3] = "bad"
    local done
    Dress.run({
        { name = "hand on", fn = function()
            q.add(a, each)
            q.add({}, each)
        end },
        { name = "work", fn = function(deadline)
            -- One more list arrives while the work runs.
            if #q.lists == 2 then q.add(b, each) end
            return q.step(deadline)
        end },
        h.step("after", 1),
    }, { defer = h.defer, clock = h.clock, budget = 10, alive = function() return true end,
         onDone = function(stats) done = stats end })
    h.drain()
    assert(done, "the load finished")
    assert(q.count == 21, "21 items queued")
    assert(#seen == 20 and seen[1] == "a1" and seen[15] == "a15" and seen[16] == "b1" and seen[20] == "b6",
        "every item, in order, the bad one skipped")
    assert(#errors == 1 and errors[1]:find("no component"))
    assert(done.frames >= 3, "spread over frames, got " .. done.frames)
    assert(done.longest <= 0.0111, "no frame past its budget by more than one item")
end

-- A queue nothing was added to is done at once.
do
    local q = Dress.queue()
    assert(q.step(math.huge) == false)
end

print("test_dress: ok")

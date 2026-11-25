-- lua tools/tests/test_warfare_voice.lua
local Voice = dofile("mods/MJOLNIRHud/Scripts/warfare_voice.lua")
local function eq(a, b, what) assert(a == b, (what or "value") .. ": " .. tostring(a) .. " ~= " .. tostring(b)) end
local function said(list) return table.concat(list, ",") end

-- A snapshot as warfare.lua's parser leaves it, reduced to what the voice reads.
local function snap(t)
    local g = { t.phase or 2, 0, 20571, t.clock or 0, t.defeat or 60, 0, 0, 0, 0, 0, 0, 0 }
    local owner = t.owner or { 0, 0, 0 }
    local sites = {}
    for i = 1, 3 do sites[i] = { owner = owner[i], covenant = t.present and t.present[i] or false } end
    return {
        instance = t.instance or "7", phase = t.phase or 2, globals = g, owner = owner, sites = sites,
        score = t.score or { 0, 0 }, rate = 60, elapsed_ticks = t.ticks or 0, insertion_seconds = t.insertion or 30,
        players = { [0] = { team = t.team == nil and 0 or t.team, stage = t.stage or 0, localUser = 0 } },
        clearance = { [0] = t.clearance }, flight = { [0] = t.sink and { vz = -t.sink } or nil },
    }
end

-- Baselines: only the title, and only in warmup.
local m = {}
eq(said(Voice.decide(m, snap({ phase = 0, clock = 40 }), 0, 0)), "title", "a warmup join hears the title")
eq(said(Voice.decide({}, snap({ phase = 2, owner = { 1, 3, 2 } }), 0, 0)), "", "a combat join hears nothing")

-- Warmup, insertion and the jump.
eq(said(Voice.decide(m, snap({ phase = 0, clock = 21 }), 0, 1)), "")
eq(said(Voice.decide(m, snap({ phase = 0, clock = 20 }), 0, 2)), "warmup", "twenty seconds left")
eq(said(Voice.decide(m, snap({ phase = 0, clock = 19 }), 0, 3)), "", "said once")
eq(said(Voice.decide(m, snap({ phase = 1, ticks = 0, stage = 2 }), 0, 4)), "insertion")
eq(said(Voice.decide(m, snap({ phase = 1, ticks = 3 * 60, stage = 2 }), 0, 7)), "briefing", "three seconds in")
eq(said(Voice.decide(m, snap({ phase = 1, ticks = 9 * 60, stage = 2 }), 0, 13)), "", "nine seconds seated")
eq(said(Voice.decide(m, snap({ phase = 1, ticks = 22 * 60, stage = 2 }), 0, 26)), "jump_now", "eleven seconds seated, still aboard")
eq(said(Voice.decide(m, snap({ phase = 1, ticks = 23 * 60, stage = 2 }), 0, 27)), "", "told once")

-- The drop: warn, yell, and the line when the ground wins (no chute opens
-- itself any more; native WF_SPLAT).
eq(said(Voice.decide(m, snap({ phase = 1, ticks = 24 * 60, stage = 3, clearance = 280, sink = 30 }), 0, 28)), "",
    "no warning in the first two seconds of a fall")
eq(said(Voice.decide(m, snap({ phase = 1, ticks = 26 * 60, stage = 3, clearance = 250, sink = 45 }), 0, 30.5)), "altitude_warn")
eq(said(Voice.decide(m, snap({ phase = 1, ticks = 27 * 60, stage = 3, clearance = 140, sink = 52 }), 0, 31.5)), "altitude_yell")
eq(said(Voice.decide(m, snap({ phase = 1, ticks = 28 * 60, stage = 3, clearance = 6, sink = 54 }), 0, 33.9)), "")
eq(said(Voice.decide(m, snap({ phase = 1, ticks = 28 * 60, stage = 5 }), 0, 34)), "splat", "hit the ground at freefall speed")
local landed = {}
Voice.decide(landed, snap({ phase = 1, stage = 4, clearance = 4, sink = 16 }), 0, 0)
eq(said(Voice.decide(landed, snap({ phase = 1, stage = 5 }), 0, 0.1)), "", "a canopy landing: nothing to say")
local late = {}
Voice.decide(late, snap({ phase = 1, stage = 4, clearance = 3, sink = 40 }), 0, 0)
eq(said(Voice.decide(late, snap({ phase = 1, stage = 0 }), 0, 0.1)), "splat", "a pull too late is still a splat")
local sent = {}
Voice.decide(sent, snap({ phase = 1, stage = 3, clearance = 20, sink = 50 }), 0, 0)
eq(said(Voice.decide(sent, snap({ phase = 1, stage = 6 }), 0, 0.1)), "", "a failed descent sent home is not a splat")
local high = {}
Voice.decide(high, snap({ phase = 1, stage = 3, clearance = 600, sink = 20 }), 0, 0)
eq(said(Voice.decide(high, snap({ phase = 1, stage = 4, clearance = 590, sink = 25 }), 0, 1)), "", "a pull up high: nothing to say")

-- Combat: zones open, the waves, the zones.
eq(said(Voice.decide(m, snap({ phase = 2, clock = 0 }), 0, 40)), "zones_open")
eq(said(Voice.decide(m, snap({ phase = 2, clock = 34 }), 0, 74)), "")
eq(said(Voice.decide(m, snap({ phase = 2, clock = 35 }), 0, 75)), "first_wave", "ten seconds before the first wave")
eq(said(Voice.decide(m, snap({ phase = 2, clock = 125 }), 0, 165)), "wave_inbound", "ten seconds before the second")
local busy = {}
Voice.decide(busy, snap({ phase = 2, clock = 120, present = { true, false, false } }), 0, 0)
eq(said(Voice.decide(busy, snap({ phase = 2, clock = 126, present = { true, false, false } }), 0, 6)), "",
    "no warning while Covenant already stand in a zone (the wave may be skipped at the cap)")

-- A respawn's reinforcement Pelican, seen boarding or already seated.
local r = {}
Voice.decide(r, snap({ phase = 2, stage = 0 }), 0, 0)
eq(said(Voice.decide(r, snap({ phase = 2, stage = 2 }), 0, 1)), "reinforcements", "ground straight to seated")
eq(said(Voice.decide(r, snap({ phase = 2, stage = 2 }), 0, 12)), "", "no jump call outside insertion")

-- Team 0 is red, owner 1 (warfare.lua OWNER).
local z = {}
Voice.decide(z, snap({ owner = { 0, 0, 0 } }), 0, 100)
eq(said(Voice.decide(z, snap({ owner = { 0, 1, 0 } }), 0, 101)), "zone_secured_b")
eq(said(Voice.decide(z, snap({ owner = { 0, 0, 0 } }), 0, 102)), "zone_lost_b")
eq(said(Voice.decide(z, snap({ owner = { 0, 2, 0 } }), 0, 103)), "zone_enemy_b")
eq(said(Voice.decide(z, snap({ owner = { 0, 3, 0 } }), 0, 104)), "covenant_take_b")
eq(said(Voice.decide(z, snap({ owner = { 0, 1, 0 } }), 0, 105)), "retaken,zone_secured_b", "taken back from the Covenant")
Voice.decide(z, snap({ owner = { 0, 3, 0 } }), 0, 106)
eq(said(Voice.decide(z, snap({ owner = { 0, 0, 0 } }), 0, 107)), "", "drained to neutral: it was the Covenant's, nothing lost")
eq(said(Voice.decide(z, snap({ owner = { 0, 1, 0 } }), 0, 108)), "retaken,zone_secured_b",
    "drained, then captured: still a retake (the real 3 -> 0 -> ours path)")
Voice.decide(z, snap({ owner = { 0, 0, 0 } }), 0, 109)
eq(said(Voice.decide(z, snap({ owner = { 0, 1, 0 } }), 0, 110)), "zone_secured_b", "ours, lost to neutral, ours again: no retake")
local blue = {}
Voice.decide(blue, snap({ team = 1, owner = { 0, 0, 0 } }), 0, 0)
eq(said(Voice.decide(blue, snap({ team = 1, owner = { 2, 1, 0 } }), 0, 1)), "zone_secured_a,zone_enemy_b", "blue's view")
local none = {}
Voice.decide(none, snap({ team = -1, owner = { 0, 0, 0 } }), 0, 0)
eq(said(Voice.decide(none, snap({ team = -1, owner = { 1, 3, 0 } }), 0, 1)), "covenant_take_b",
    "no team: only the Covenant's lines")

-- Covenant presence: contested on our zone, a landing elsewhere after a quiet spell.
local p = {}
Voice.decide(p, snap({ owner = { 1, 0, 0 } }), 0, 0)
eq(said(Voice.decide(p, snap({ owner = { 1, 0, 0 }, present = { true, false, false } }), 0, 30)), "zone_contested_a")
eq(said(Voice.decide(p, snap({ owner = { 1, 0, 0 }, present = { true, true, false } }), 0, 31)), "",
    "a second zone while they are already here: no landing line")
local q = {}
Voice.decide(q, snap({ owner = { 1, 0, 0 } }), 0, 0)
eq(said(Voice.decide(q, snap({ owner = { 1, 0, 0 }, present = { false, false, true } }), 0, 30)), "covenant_landing_c")
eq(said(Voice.decide(q, snap({ owner = { 1, 0, 0 } }), 0, 40)), "")
eq(said(Voice.decide(q, snap({ owner = { 1, 0, 0 }, present = { false, true, false } }), 0, 45)), "",
    "seen five seconds ago: not a new landing")
eq(said(Voice.decide(q, snap({ owner = { 1, 0, 0 } }), 0, 46)), "")
eq(said(Voice.decide(q, snap({ owner = { 1, 0, 0 }, present = { false, true, false } }), 0, 70)), "covenant_landing_b")

-- Two zones, all three (the defeat clock), ten seconds, and breaking it.
local d = {}
Voice.decide(d, snap({ owner = { 3, 0, 1 }, defeat = 60 }), 0, 0)
eq(said(Voice.decide(d, snap({ owner = { 3, 3, 1 }, defeat = 60 }), 0, 1)), "covenant_take_b,covenant_two")
eq(said(Voice.decide(d, snap({ owner = { 3, 3, 3 }, defeat = 60 }), 0, 2)), "covenant_all", "the third zone: one line, not two")
eq(said(Voice.decide(d, snap({ owner = { 3, 3, 3 }, defeat = 11 }), 0, 51)), "")
eq(said(Voice.decide(d, snap({ owner = { 3, 3, 3 }, defeat = 10 }), 0, 52)), "defeat_ten")
eq(said(Voice.decide(d, snap({ owner = { 3, 3, 0 }, defeat = 60 }), 0, 53)), "covenant_broken")
local norule = {}
Voice.decide(norule, snap({ owner = { 3, 3, 0 }, defeat = -1 }), 0, 0)
eq(said(Voice.decide(norule, snap({ owner = { 3, 3, 3 }, defeat = -1 }), 0, 1)), "covenant_take_c",
    "without the hold rule there is no defeat clock to warn of")

-- The end.
local e = {}
Voice.decide(e, snap({ owner = { 3, 3, 3 }, defeat = 1 }), 0, 0)
eq(said(Voice.decide(e, snap({ phase = 3, owner = { 3, 3, 3 }, defeat = 0 }), 0, 1)), "covenant_win")
local w = {}
Voice.decide(w, snap({ score = { 400, 300 } }), 0, 0)
eq(said(Voice.decide(w, snap({ phase = 3, score = { 500, 300 } }), 0, 1)), "victory,well_done")
local l = {}
Voice.decide(l, snap({ score = { 400, 300 } }), 0, 0)
eq(said(Voice.decide(l, snap({ phase = 3, team = 1, score = { 500, 300 } }), 0, 1)), "defeat")

-- A new instance is a new baseline, whatever changed.
eq(said(Voice.decide(z, snap({ instance = "8", owner = { 3, 3, 3 } }), 0, 200)), "", "new match: baseline")

-- The queue: one at a time, urgent lines cut calm ones, stale lines drop,
-- and a missing container turns the voice off without retries.
local played, stopped, loads = {}, {}, 0
local io = {
    lines = { title = { { "announcer_title_a", 1.5 } }, warmup = { { "cortana_warmup_a", 4.0 } },
        altitude_yell = { { "cortana_altitude_yell_a", 1.8 } }, briefing = { { "cortana_briefing_a", 5.0 } } },
    load = function(path) loads = loads + 1; return { path = path } end,
    spawn = function(wave) played[#played + 1] = wave.path:match("([%w_]+)%.") return { name = wave.path } end,
    stop = function(c) stopped[#stopped + 1] = c.name end,
    volume = function() return 0.8 end, random = function() return 1 end,
}
local v = Voice.new(io)
v.observe(snap({ phase = 0, clock = 40 }), 0, 0)
v.pump(0)
eq(played[1], "announcer_title_a", "the title plays")
v.observe(snap({ phase = 0, clock = 20 }), 0, 0.5)
v.pump(0.5)
eq(#played, 1, "the warmup line waits for the title")
v.pump(1.9)
eq(played[2], "cortana_warmup_a", "then plays")
v.memory.stage, v.memory.drop = 3, { at = -10 }
v.observe(snap({ phase = 0, clock = 18, stage = 3, clearance = 150 }), 0, 2.0)
v.pump(2.0)
eq(played[3], "cortana_altitude_yell_a", "the yell cuts in"); eq(#stopped, 1, "over the calm line")
local quiet = Voice.new(io)
quiet.queue = { { event = "briefing", priority = 1, expires = 5, at = 0 } }
quiet.pump(6)
eq(#played, 3, "a line that waited too long is dropped")
local missing = Voice.new({ lines = io.lines, load = function() loads = loads + 1 return nil end,
    spawn = io.spawn, volume = io.volume, random = io.random, log = function() end })
local before = loads
missing.observe(snap({ phase = 0, clock = 40 }), 0, 0)
missing.pump(0); missing.observe(snap({ phase = 0, clock = 20 }), 0, 1); missing.pump(10)
eq(loads - before, 1, "one failed load, then silence"); eq(missing.disabled, true)

-- A line cut in its first second plays again after the urgent one; one cut
-- later is gone.
local heardAgain = {}
local again = Voice.new({
    lines = { zones_open = { { "announcer_zones_open_a", 1.6 } }, altitude_yell = { { "cortana_altitude_yell_a", 1.8 } } },
    load = function(path) return { path = path } end,
    spawn = function(wave) heardAgain[#heardAgain + 1] = wave.path:match("([%w_]+)%.") return {} end,
    stop = function() end, volume = function() return 1 end, random = function() return 1 end })
again.queue = { { event = "zones_open", priority = 2, expires = 4, at = 0 } }
again.pump(0)
again.queue[#again.queue + 1] = { event = "altitude_yell", priority = 3, expires = 1.3, at = 0.1 }
again.pump(0.1)
again.pump(2.3)
eq(table.concat(heardAgain, ","), "announcer_zones_open_a,cortana_altitude_yell_a,announcer_zones_open_a",
    "cut at once, heard after the yell")
-- ...and before a line that queued behind it ("They've taken Zone B" cut by
-- the yell, then "That's two zones": the take first).
local order = {}
local inLine = Voice.new({
    lines = { covenant_take_b = { { "cortana_covenant_take_b", 2.5 } }, covenant_two = { { "cortana_covenant_two_a", 2.5 } },
        altitude_yell = { { "cortana_altitude_yell_a", 1.8 } } },
    load = function(path) return { path = path } end,
    spawn = function(wave) order[#order + 1] = wave.path:match("cortana_([%w_]+)%.") return {} end,
    stop = function() end, volume = function() return 1 end, random = function() return 1 end })
inLine.queue = { { event = "covenant_take_b", priority = 2, expires = 9, at = 0 }, { event = "covenant_two", priority = 2, expires = 9, at = 0.01 } }
inLine.pump(0)
inLine.queue[#inLine.queue + 1] = { event = "altitude_yell", priority = 3, expires = 1.3, at = 0.2 }
inLine.pump(0.2); inLine.pump(2.5); inLine.pump(5.5)
eq(table.concat(order, ","), "covenant_take_b,altitude_yell_a,covenant_take_b,covenant_two_a", "the cut line keeps its place")

-- Turns with the loader's announcer (MJOLNIR.voiceUntil): a calm line waits
-- for it, the player's own fall does not, and a line takes the floor.
local sharedUntil, spoke = 5, {}
local turns = Voice.new({
    lines = { briefing = { { "cortana_briefing_a", 4.0 } }, altitude_yell = { { "cortana_altitude_yell_a", 1.8 } } },
    load = function(path) return { path = path } end,
    spawn = function(wave) spoke[#spoke + 1] = wave.path:match("([%w_]+)%.") return {} end,
    volume = function() return 1 end, random = function() return 1 end,
    floor = function() return sharedUntil end, setFloor = function(t) sharedUntil = t end })
turns.queue = { { event = "briefing", priority = 2, expires = 9, at = 0 } }
turns.pump(1); eq(#spoke, 0, "a calm line waits while the announcer speaks")
turns.pump(5.1); eq(spoke[1], "cortana_briefing_a", "then plays"); assert(sharedUntil > 9, "and holds the floor")
sharedUntil = 20
turns.queue = { { event = "altitude_yell", priority = 3, expires = 21, at = 19.9 } }
turns.pump(19.95); eq(spoke[2], "cortana_altitude_yell_a", "the fall does not wait")

-- Only the fall talks over the announcer: the end of the match waits its turn.
local endSpoke, endFloor = {}, 30
local ending = Voice.new({
    lines = { covenant_win = { { "cortana_covenant_win_a", 2.1 } } },
    load = function(path) return { path = path } end,
    spawn = function(wave) endSpoke[#endSpoke + 1] = wave.path return {} end,
    volume = function() return 1 end, random = function() return 1 end,
    floor = function() return endFloor end, setFloor = function(t) endFloor = t end })
ending.queue = { { event = "covenant_win", priority = 3, expires = 40, at = 28 } }
ending.pump(29); eq(#endSpoke, 0, "covenant_win waits for game_over")
ending.pump(30.1); eq(#endSpoke, 1, "then plays")

-- A full queue and a cut-in: the urgent line plays once and the cut line is kept.
local fullSpoke = {}
local full = Voice.new({
    lines = { zones_open = { { "announcer_zones_open_a", 1.6 } }, altitude_yell = { { "cortana_altitude_yell_a", 1.8 } },
        first_wave = { { "cortana_first_wave_a", 3.0 } } },
    load = function(path) return { path = path } end,
    spawn = function(wave) fullSpoke[#fullSpoke + 1] = wave.path:match("_([%w]+_[%w]+)_a%.") return {} end,
    stop = function() end, volume = function() return 1 end, random = function() return 1 end })
full.queue = { { event = "zones_open", priority = 2, expires = 9, at = 0 } }
full.pump(0)
for i = 1, 7 do full.queue[#full.queue + 1] = { event = "first_wave", priority = 1, expires = 60, at = 0.01 * i } end
full.queue[#full.queue + 1] = { event = "altitude_yell", priority = 3, expires = 2, at = 0.2 }
full.pump(0.2)
local yells, zones = 0, 0
for _, e in ipairs(full.queue) do
    if e.event == "altitude_yell" then yells = yells + 1 end
    if e.event == "zones_open" then zones = zones + 1 end
end
eq(yells, 0, "the yell is not left queued to play twice"); eq(zones, 1, "the cut line is queued again")

-- The launch sequence as it plays: the launch line, the briefing after it,
-- and the call to jump waiting for the briefing to finish, never cutting it.
local heard, cut = {}, {}
local seq = Voice.new({
    lines = { insertion = { { "cortana_insertion_a", 2.7 } }, briefing = { { "cortana_briefing_a", 6.0 } },
        jump_now = { { "cortana_jump_now_a", 2.0 } } },
    load = function(path) return { path = path } end,
    spawn = function(wave) heard[#heard + 1] = wave.path:match("([%w_]+)%.") return { name = wave.path } end,
    stop = function(c) cut[#cut + 1] = c.name end, volume = function() return 1 end, random = function() return 1 end })
seq.observe(snap({ phase = 0, clock = 1, stage = 0 }), 0, 0)
local t = 0
for i = 1, 140 do
    t = i / 10
    seq.observe(snap({ phase = 1, ticks = math.floor(t * 60), stage = 2 }), 0, t)
    seq.pump(t)
end
eq(table.concat(heard, ","), "cortana_insertion_a,cortana_briefing_a,cortana_jump_now_a", "launch, briefing, jump")
eq(#cut, 0, "nothing in the launch sequence is cut off")

-- The wave timing restates native warfare_core.h: keep them equal.
local core = _G.io.open("native/lobby/warfare_core.h"):read("a")
eq(tonumber(core:match("#define WARFARE_WAVE_FIRST (%d+)")), Voice.WAVE_FIRST, "WARFARE_WAVE_FIRST")
eq(tonumber(core:match("#define WARFARE_WAVE_INTERVAL (%d+)")), Voice.WAVE_INTERVAL, "WARFARE_WAVE_INTERVAL")
eq(tonumber(core:match("#define WARFARE_SPLAT_SINK ([%d.]+)f")), Voice.SPLAT_SINK, "WARFARE_SPLAT_SINK")

-- The loader no longer announces Warfare as King of the Hill; the voice does.
local modes = dofile("mods/MJOLNIRLevelLoader/Scripts/mode_descriptors.lua")
local events = _G.io.open("mods/MJOLNIRLevelLoader/events.json"):read("a")
assert(not events:find('"' .. modes.warfare.startEvent .. '"', 1, true), "warfare's start event must have no loader sound")

-- Every line the voice can ask for has a wave, when the catalogue is built.
local f = _G.io.open("mods/MJOLNIRHud/Scripts/warfare_voice_lines.lua")
if f then
    f:close()
    local lines = dofile("mods/MJOLNIRHud/Scripts/warfare_voice_lines.lua")
    local wanted = { "title", "warmup", "insertion", "briefing", "jump_now", "altitude_warn", "altitude_yell", "splat",
        "zones_open", "first_wave", "wave_inbound", "covenant_two", "covenant_all", "defeat_ten", "covenant_broken",
        "retaken", "reinforcements", "victory", "defeat", "well_done", "covenant_win" }
    for _, zone in ipairs({ "zone_secured", "zone_lost", "zone_enemy", "zone_contested", "covenant_landing", "covenant_take" }) do
        for _, letter in ipairs({ "a", "b", "c" }) do wanted[#wanted + 1] = zone .. "_" .. letter end
    end
    for _, event in ipairs(wanted) do assert(lines[event] and #lines[event] > 0, "no wave for " .. event) end
end
print("warfare voice tests passed")

-- lua tools/tests/test_announcer.lua
local Announcer = dofile("mods/MJOLNIRLevelLoader/Scripts/announcer.lua")
local function eq(a, b, what) assert(a == b, (what or "value") .. ": " .. tostring(a) .. " ~= " .. tostring(b)) end

-- A fake game thread: a clock and the delayed calls, run in time order.
local clock, timers, played, floor = 0, {}, {}, 0
local LENGTH = { ["sound_dialog_double"] = 1.0, ["sound_dialog_triple"] = 1.0, ["sound_dialog_overkill"] = 1.2,
    ["sound_dialog_spree"] = 1.4, ["sound_dialog_slayer"] = 1.0, ["sound_dialog_gameover"] = 1.5 }
local function reset() clock, timers, played, floor = 0, {}, {}, 0 end
local io = {
    now = function() return clock end,
    schedule = function(seconds, fn) timers[#timers + 1] = { at = clock + seconds, fn = fn } end,
    play = function(path) played[#played + 1] = { path = path, at = clock } return LENGTH[path] end,
    floor = function() return floor end,
    setFloor = function(t) floor = t end,
}
local function run(untilAt)
    while true do
        table.sort(timers, function(a, b) return a.at < b.at end)
        local t = timers[1]
        if not t or t.at > untilAt then break end
        table.remove(timers, 1)
        clock = t.at
        t.fn()
    end
    clock = untilAt
end
local function names()
    local out = {}
    for _, p in ipairs(played) do out[#out + 1] = p.path:gsub("sound_dialog_", "") end
    return table.concat(out, ",")
end

assert(Announcer.isVoice("/Game/MJOLNIR/Sounds/Events/sound_dialog_multiplayer1_killing_spree_v0.x"))
assert(not Announcer.isVoice("/Game/MJOLNIR/Sounds/Events/sound_sfx_ui_pickup_health_v0.x"))

-- One grenade, five kills: the burst collapses to its best multi-kill, and the
-- spree follows it, never on top of it.
reset()
local a = Announcer.new(io)
a.push("multikill_x2", "sound_dialog_double")
clock = 0.05; a.push("multikill_x3", "sound_dialog_triple")
clock = 0.1; a.push("multikill_x4", "sound_dialog_overkill")
clock = 0.12; a.push("5_in_a_row", "sound_dialog_spree")
run(5)
eq(names(), "overkill,spree", "a burst says its best line, then the spree")
assert(played[2].at >= played[1].at + 1.2, "the spree waits for the multi-kill to finish")

-- A burst keeps settling for at most a second.
reset()
local b = Announcer.new(io)
for i = 0, 9 do clock = i * 0.3; b.push(i % 2 == 0 and "multikill_x2" or "multikill_x3", i % 2 == 0 and "sound_dialog_double" or "sound_dialog_triple") end
run(10)
assert(played[1].at <= 1.0 + 1e-9, "the first line starts within a second of the burst")

-- Another voice (the Warfare HUD) holds the floor: wait for it.
reset()
local c = Announcer.new(io)
floor = 2.0
c.push("slayer_start", "sound_dialog_slayer")
run(5)
eq(played[1].at, 2.0, "waits for the shared floor"); eq(floor, 3.15, "and takes it for its own length")

-- A line kept waiting past its time is dropped; a game's closing line is not.
reset()
local d = Announcer.new(io)
floor = 4.0
d.push("multikill_x2", "sound_dialog_double")
d.push("game_over", "sound_dialog_gameover")
run(8)
eq(names(), "gameover", "the stale multi-kill is dropped, game over is kept")

-- Nothing is armed once the queue is empty.
reset()
local e = Announcer.new(io)
e.push("slayer_start", "sound_dialog_slayer")
run(3)
eq(#timers, 0, "no timer left armed"); eq(e.armed, false)
print("announcer queue tests passed")

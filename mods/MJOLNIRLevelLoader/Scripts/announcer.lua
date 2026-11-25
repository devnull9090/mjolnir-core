-- The announcer's lines one at a time.
--
-- A grenade into a squad raises several incidents in the same moment
-- (multikill_x2, x3, x4, a spree), and each used to start its line at once:
-- five or six voices on top of each other (PC 1, 2026-11-24). Voice lines now
-- go through this queue:
--
--   - A line waits HOLD seconds before it plays, so a burst can settle. A newer
--     multi-kill replaces a waiting one if it ranks higher (one grenade, five
--     kills: "Overkill", not the four before it). Sprees work the same way.
--   - One line at a time, each for its own length (the wave's Duration), and
--     never over MJOLNIRHud's Warfare voice: both keep the shared variable
--     MJOLNIR.voiceUntil (os.clock seconds) up to date and wait for it.
--   - A line that cannot start within TTL seconds is dropped, except a game's
--     opening and closing lines.
--
-- Effects (respawn ticks, pickups, teleports) are not voice and play at once.
-- What is voice is the tag's own path: CE's announcer lines are
-- sound\dialog\..., cooked as sound_dialog_* (tools/level/ce_sounds.py).
--
-- Why Lua: the engine's sound concurrency (a USoundConcurrency the loader
-- already builds for ambient loops) can stop or refuse a sound but cannot
-- hold one back and play it afterwards, so a burst would lose lines, not
-- queue them. Nothing here runs per frame: a one-shot delayed call is armed
-- only while a line waits.
local Announcer = {}

Announcer.HOLD, Announcer.TTL, Announcer.GAP = 0.35, 2.5, 0.15
Announcer.SETTLE_MAX = 1.0
Announcer.FLOOR = "MJOLNIR.voiceUntil"

function Announcer.isVoice(path)
    return type(path) == "string" and path:find("sound_dialog_", 1, true) ~= nil
end

--- A multi-kill or a spree, and its rank, for collapsing a burst.
local function family(name)
    local n = name:match("^multikill_x(%d+)$")
    if n then return "multikill", tonumber(n) end
    n = name:match("^(%d+)_in_a_row$")
    if n then return "spree", tonumber(n) end
    return nil, 0
end

--- A game's opening and closing lines are never dropped for waiting.
local function keeps(name)
    return name == "game_over" or name:find("_start$") ~= nil
end

--- io: now() -> seconds; schedule(seconds, fn) runs fn once later on the game
--- thread; play(path) -> the line's length in seconds, or nil if it did not
--- play; floor() -> seconds until which another voice is speaking (0 if none);
--- setFloor(seconds).
function Announcer.new(io)
    local self = { pending = {}, busy = 0, armed = false }

    local function arm(delay)
        if self.armed then return end
        self.armed = true
        io.schedule(math.max(0.05, delay), function()
            self.armed = false
            self.pump()
        end)
    end

    --- Queue a voice line for `name` (an incident), wave `path`.
    function self.push(name, path)
        local now = io.now()
        local kind, rank = family(name)
        if kind then
            for _, e in ipairs(self.pending) do
                if e.kind == kind then
                    if rank > e.rank then e.name, e.path, e.rank = name, path, rank end
                    e.ready = math.min(e.first + Announcer.SETTLE_MAX, now + Announcer.HOLD)
                    arm(e.ready - now)
                    return
                end
            end
        end
        self.pending[#self.pending + 1] = { name = name, path = path, kind = kind, rank = rank,
            first = now, ready = now + Announcer.HOLD, keep = keeps(name) }
        arm(Announcer.HOLD)
    end

    --- Play the next line if the floor is free; re-arm while lines wait.
    function self.pump()
        local now = io.now()
        for i = #self.pending, 1, -1 do
            local e = self.pending[i]
            if not e.keep and now - e.first > Announcer.TTL then table.remove(self.pending, i) end
        end
        if #self.pending == 0 then return end
        local free = math.max(self.busy, io.floor() or 0)
        if now < free then return arm(free - now) end
        local index, soonest
        for i, e in ipairs(self.pending) do
            if e.ready <= now then index = i; break end
            soonest = math.min(soonest or e.ready, e.ready)
        end
        if not index then return arm(soonest - now) end
        local e = table.remove(self.pending, index)
        local seconds = io.play(e.path)
        if seconds then
            self.busy = now + seconds + Announcer.GAP
            io.setFloor(self.busy)
        end
        if #self.pending > 0 then arm(math.max(self.busy - now, 0.05)) end
    end

    return self
end

return Announcer

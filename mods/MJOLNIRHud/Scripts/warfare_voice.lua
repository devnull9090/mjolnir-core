-- Pelican Warfare's voice: Cortana talks the player through the match and the
-- announcer names the game, the zones and the result.
--
-- Every line comes from a change between two accepted warfare snapshots the
-- HUD already reads (warfare.lua's tick), so there is no loop of its own and
-- every machine decides for itself from replicated state: the phase, the three
-- zones' owners and Covenant presence, the defeat clock, and the local
-- player's own drop (stage and clearance). The first sample of a match
-- instance, and the first after the snapshot went stale, only sets the
-- baseline: a joiner hears nothing that already happened.
--
-- One line plays at a time. A more urgent line cuts a calmer one off; lines
-- that wait too long are dropped. The waves are SoundWaves in their own
-- container (/Game/MJOLNIR/Sounds/Warfare, unreal/MJOLNIRMaterials/Scripts/
-- build_warfare_voice.py); warfare_voice_lines.lua lists them with their
-- lengths (tools/voice/voice_catalog.py). When the first wave does not load
-- (the container is not installed) the voice turns itself off for the session.
local Voice = {}

Voice.ROOT = "/Game/MJOLNIR/Sounds/Warfare/"

-- Priorities: 3 the player's own urgent moment (the fall), 2 the match turning
-- (zones open, the Covenant holding everything), 1 the rest. TTL: seconds a
-- line may wait in the queue before it is stale.
local LINE = {
    title = { 2, 6 }, warmup = { 1, 4 }, insertion = { 2, 4 }, briefing = { 2, 8 },
    -- The same priority as the briefing, so it waits for it rather than cut it off.
    jump_now = { 2, 4 }, altitude_warn = { 2, 1.5 }, altitude_yell = { 3, 1.2 }, auto_chute = { 3, 2 },
    zones_open = { 2, 4 }, first_wave = { 1, 6 }, wave_inbound = { 1, 6 },
    covenant_landing = { 1, 5 }, covenant_take = { 2, 6 }, covenant_two = { 2, 6 },
    covenant_all = { 3, 6 }, defeat_ten = { 3, 3 }, covenant_broken = { 2, 5 },
    retaken = { 1, 5 }, reinforcements = { 1, 6 },
    zone_secured = { 1, 4 }, zone_lost = { 1, 4 }, zone_enemy = { 1, 4 }, zone_contested = { 2, 4 },
    victory = { 2, 10 }, defeat = { 2, 10 }, well_done = { 1, 12 }, covenant_win = { 3, 10 },
}

-- The drop: the chute opens itself at max(38, 18 + 1.05 x sink) metres
-- (native warfare_need_canopy, about 76 m at freefall's ~55 m/s), so she warns
-- above that and, if the player never pulls it, makes the joke as it opens.
Voice.WARN_M, Voice.YELL_M, Voice.AUTO_BELOW_M = 320, 170, 115
-- The Covenant's waves leave on the combat clock (native warfare_core.h
-- WARFARE_WAVE_FIRST / WARFARE_WAVE_INTERVAL). The clock only predicts a
-- wave (one is skipped at the cap), so later warnings are hedged by presence:
-- none while Covenant already stand in a zone.
Voice.WAVE_FIRST, Voice.WAVE_INTERVAL, Voice.WAVE_LEAD = 45, 90, 10
-- The briefing (up to 6 s) follows the launch line, and the call to jump comes
-- after it: riders are put out about 15 s after boarding on PWR.
Voice.WARMUP_AT, Voice.BRIEFING_AT, Voice.JUMP_NOW_AT, Voice.QUIET_BEFORE_LANDING = 20, 3, 11, 20
local LETTER = { "a", "b", "c" }
local COVENANT = 3

local function team(s, me)
    local p = s.players and s.players[me]
    local t = p and p.team
    if t == 0 or t == 1 then return t + 1 end
    return nil
end

local function covenantCount(owner)
    local n = 0
    for i = 1, 3 do if owner[i] == COVENANT then n = n + 1 end end
    return n
end

local function present(s, i)
    return s.sites and s.sites[i] and s.sites[i].covenant or false
end

--- The defeat clock while the Covenant hold all three, else nil (warfare.lua's
--- Warfare.defeatIn, restated so this module stands alone in tests).
local function defeatIn(s)
    if s.phase ~= 2 or not s.globals or s.globals[5] <= 0 or covenantCount(s.owner) < 3 then return nil end
    return s.globals[5]
end

local function add(out, event) out[#out + 1] = event end

local function combatSeconds(s)
    if (s.phase == 2 or s.phase == 3) and s.globals then return math.max(0, s.globals[4]) end
    return nil
end


--- The lines a change from `m` (the memory of the last sample) to snapshot
--- `s` calls for, as event names (zone events carry their letter), in the
--- order they should be heard, into `out` (cleared; a new table when nil).
--- Updates `m`. Pure apart from `m` and `out`. It runs on every accepted
--- sample (10 Hz in flight), so a quiet sample allocates nothing.
function Voice.decide(m, s, me, now, out)
    if out then for k = #out, 1, -1 do out[k] = nil end else out = {} end
    local mine = team(s, me)
    local p = s.players and s.players[me]
    local stage = p and p.localUser >= 0 and p.stage or nil
    local clearance = s.clearance and s.clearance[me]
    if m.instance ~= s.instance then
        -- A new match, or a join: baseline only, apart from the title for
        -- anyone who arrives during warmup.
        for k in pairs(m) do m[k] = nil end
        m.instance = s.instance
        m.phase, m.owner, m.present = s.phase, { s.owner[1], s.owner[2], s.owner[3] }, { present(s, 1), present(s, 2), present(s, 3) }
        m.held = { s.owner[1], s.owner[2], s.owner[3] }
        m.defeat, m.stage, m.clearance = defeatIn(s), stage, clearance
        m.warmupLeft, m.combat, m.covenantSeenAt = s.phase == 0 and s.globals[4] or nil, combatSeconds(s), nil
        m.briefed = s.phase ~= 0 and s.phase ~= 1
        if s.phase == 0 then add(out, "title") end
        return out
    end
    -- Warmup and insertion.
    if s.phase == 0 then
        local left = s.globals[4]
        if m.warmupLeft and left >= 0 and m.warmupLeft > Voice.WARMUP_AT and left <= Voice.WARMUP_AT then add(out, "warmup") end
        m.warmupLeft = left
    end
    if m.phase == 0 and s.phase == 1 then add(out, "insertion") end
    if s.phase == 1 then
        if not m.briefed and s.rate > 0 and s.elapsed_ticks / s.rate >= Voice.BRIEFING_AT then
            m.briefed = true
            add(out, "briefing")
        end
        -- A rider who has not jumped is put out when the Pelican's flight ends
        -- (native WF_SEATED -> WF_EXITING on flight_over), which can be long
        -- before the insertion's clock runs out (15 s into 60 on PWR,
        -- 2026-11-24): so she calls it from the time seated, not time left.
        if stage == 2 and m.seatedAt and now - m.seatedAt >= Voice.JUMP_NOW_AT and not m.toldToJump then
            m.toldToJump = true
            add(out, "jump_now")
        end
    end
    if stage == 2 and m.stage ~= 2 then m.seatedAt = now end
    -- The player's own drop (insertion or a reinforcement wave).
    if stage == 3 and m.stage ~= 3 then m.drop = { at = now } end
    if stage == 3 and m.drop and clearance then
        if not m.drop.warned and clearance < Voice.WARN_M and now - m.drop.at >= 2 then
            m.drop.warned = true
            add(out, "altitude_warn")
        end
        if not m.drop.yelled and clearance < Voice.YELL_M and now - m.drop.at >= 1 then
            m.drop.yelled, m.drop.warned = true, true
            add(out, "altitude_yell")
        end
    end
    if m.stage == 3 and stage == 4 and m.clearance and m.clearance < Voice.AUTO_BELOW_M then add(out, "auto_chute") end
    -- Boarding a reinforcement Pelican: at the HUD's 2 Hz a respawn went from
    -- the ground straight to seated (PC 1, 2026-11-24), so either counts.
    local aboard = stage == 1 or stage == 2
    if s.phase == 2 and aboard and not (m.stage == 1 or m.stage == 2) then add(out, "reinforcements") end
    -- Combat.
    if m.phase == 1 and s.phase == 2 then add(out, "zones_open") end
    local combat = combatSeconds(s)
    if s.phase == 2 and combat and m.combat then
        local anyPresent = present(s, 1) or present(s, 2) or present(s, 3)
        if m.combat < Voice.WAVE_FIRST - Voice.WAVE_LEAD and combat >= Voice.WAVE_FIRST - Voice.WAVE_LEAD then
            add(out, "first_wave")
        else
            for k = 1, 64 do
                local at = Voice.WAVE_FIRST + k * Voice.WAVE_INTERVAL - Voice.WAVE_LEAD
                if at > combat then break end
                if m.combat < at and not anyPresent then add(out, "wave_inbound") end
            end
        end
    end
    if s.phase == 2 and m.phase == 2 then
        local quiet = not (m.present[1] or m.present[2] or m.present[3])
            and (not m.covenantSeenAt or now - m.covenantSeenAt >= Voice.QUIET_BEFORE_LANDING)
        local landed = false
        for i = 1, 3 do
            local was, is, letter = m.owner[i], s.owner[i], LETTER[i]
            if is ~= was then
                if is == COVENANT then add(out, "covenant_take_" .. letter)
                elseif mine and is == mine then
                    -- Players drain a Covenant zone to neutral before they
                    -- capture it (3 -> 0 -> ours), so "held" is who had it
                    -- before it went neutral (PC 1, 2026-11-24).
                    if m.held[i] == COVENANT then add(out, "retaken") end
                    add(out, "zone_secured_" .. letter)
                elseif mine and is == 3 - mine then add(out, "zone_enemy_" .. letter)
                elseif mine and was == mine then add(out, "zone_lost_" .. letter) end
            end
            if present(s, i) and not m.present[i] then
                if mine and s.owner[i] == mine then add(out, "zone_contested_" .. letter)
                elseif quiet and not landed then
                    landed = true
                    add(out, "covenant_landing_" .. letter)
                end
            end
        end
        if covenantCount(s.owner) == 2 and covenantCount(m.owner) < 2 then add(out, "covenant_two") end
        local defeat = defeatIn(s)
        if defeat and not m.defeat then
            -- "They hold every zone" says what the third zone's line would,
            -- and plays first (it is more urgent): drop the single-zone line
            -- rather than hear it after (PC 1, 2026-11-24).
            for k = #out, 1, -1 do
                if out[k]:find("^covenant_take_") or out[k] == "covenant_two" then table.remove(out, k) end
            end
            add(out, "covenant_all")
        elseif defeat and m.defeat and m.defeat > 10 and defeat <= 10 then add(out, "defeat_ten")
        elseif m.defeat and not defeat then add(out, "covenant_broken") end
    end
    if present(s, 1) or present(s, 2) or present(s, 3) then m.covenantSeenAt = now end
    -- The end.
    if m.phase ~= 3 and s.phase == 3 then
        if s.globals[5] == 0 and covenantCount(s.owner) == 3 then add(out, "covenant_win")
        elseif mine then
            local ours, theirs = s.score[mine], s.score[3 - mine]
            if ours > theirs then add(out, "victory"); add(out, "well_done")
            elseif ours < theirs then add(out, "defeat") end
        end
    end
    m.phase, m.combat, m.defeat = s.phase, combat, defeatIn(s)
    for i = 1, 3 do
        m.owner[i], m.present[i] = s.owner[i], present(s, i)
        if s.owner[i] ~= 0 then m.held[i] = s.owner[i] end
    end
    m.stage, m.clearance = stage, clearance
    return out
end

--- io: lines (warfare_voice_lines.lua), load(path) -> wave or nil,
--- spawn(wave, volume, pc) -> playing component or nil, stop(component),
--- volume() -> 0..1 (the dialogue slider), log(text), random(n) -> 1..n.
function Voice.new(io)
    local self = { memory = {}, queue = {}, disabled = false }
    local playing = nil
    local random = io.random or math.random

    local function enqueue(event, now)
        local spec = LINE[event:match("^(.-)_[abc]$") or event] or LINE[event] or { 1, 4 }
        if #self.queue >= 8 then table.remove(self.queue, 1) end
        self.queue[#self.queue + 1] = { event = event, priority = spec[1], expires = now + spec[2], at = now }
    end

    local function start(entry, now, pc)
        -- A zone line is asked for by its full name (zone_secured_b), any
        -- other by its event, which lists its variants (auto_chute: a, b, c).
        local waves = io.lines[entry.event]
        if not waves or #waves == 0 then return false end
        local pick = waves[random(#waves)]
        local ok, wave = pcall(io.load, Voice.ROOT .. pick[1] .. "." .. pick[1])
        if not ok or not wave then
            -- The first wave that does not load means the container is not
            -- installed: stop for the session rather than retry every tick.
            self.disabled = true
            if io.log then io.log("warfare voice: " .. pick[1] .. " did not load; the voice is off this session") end
            return false
        end
        -- One line in the log per line spoken, so a playtest's log says what
        -- she said and when (a handful a minute).
        if io.log then io.log("warfare voice: " .. entry.event .. " (" .. pick[1] .. ")") end
        local volume = io.volume and io.volume() or 1
        if volume <= 0 then return true end
        local okS, component = pcall(io.spawn, wave, volume, pc)
        playing = { component = okS and component or nil, priority = entry.priority,
            ends = now + pick[2] + 0.35, event = entry.event }
        return true
    end

    local said = {}

    --- Feed an accepted snapshot (warfare.lua's tick).
    function self.observe(s, me, now)
        if self.disabled or not s then return end
        for _, event in ipairs(Voice.decide(self.memory, s, me, now, said)) do enqueue(event, now) end
    end

    --- The snapshot went stale or the match ended: the next sample is a new
    --- baseline. Called every tick off the map, so it clears in place.
    function self.reset()
        for k in pairs(self.memory) do self.memory[k] = nil end
        for k = #self.queue, 1, -1 do self.queue[k] = nil end
    end

    --- Play or cut what the queue holds; called every tick.
    function self.pump(now, pc)
        if self.disabled then return end
        local best, index = nil, nil
        for i = #self.queue, 1, -1 do
            local e = self.queue[i]
            if now > e.expires then table.remove(self.queue, i)
            elseif not best or e.priority > best.priority or (e.priority == best.priority and e.at <= best.at) then
                best, index = e, i
            end
        end
        if not best then return end
        if playing and now < playing.ends then
            if best.priority <= playing.priority then return end
            if playing.component and io.stop then pcall(io.stop, playing.component) end
        end
        table.remove(self.queue, index)
        playing = nil
        start(best, now, pc)
    end

    return self
end

return Voice

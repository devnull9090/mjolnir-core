-- Pelican Warfare presentation. The native snapshot is read twice a second;
-- Megalo owns capture/score/phase and the native adapter owns all movement.
-- There are no world scans, gameplay writes, or inferred objective scores.
local Warfare = {}
local EVERY, FLIGHT_EVERY, STALE = 0.5, 0.1, 2
local OWNER = { [0] = "NEUTRAL", [1] = "RED", [2] = "BLUE", [3] = "COVENANT" }
local COLOUR = { [0] = "empty", [1] = "Red", [2] = "Blue", [3] = "Covenant" }

-- Megalo publishes each site as one packed number (blam-megalo warfare.rs
-- SiteState): owner in the low two bits (3: the Covenant hold it), who stands
-- in it in the next two, and its capture progress in steps of PROGRESS_STEPS
-- toward Red (+) or Blue (-) above, or from COVENANT_STEP_BASE up the
-- Covenant's progress. Below 16 there is no progress (an older variant):
-- owner only. COVENANT_PRESENT on top: Covenant stand in the zone.
Warfare.PROGRESS_STEPS = 16
Warfare.OWNER_COVENANT = 3
Warfare.COVENANT_PRESENT = 8192
local COVENANT_STEP_BASE = 2 * Warfare.PROGRESS_STEPS + 2
-- Megalo rules revision in slot 2 (warfare.rs MAGIC). The map's own layout
-- protocol (20569) is checked by the loader, not here.
Warfare.RULES = 20571

--- Whole seconds of warmup left, -1 while waiting for the minimum players,
--- or nil outside warmup (slot 3, warfare.rs CLOCK).
function Warfare.warmupLeft(s)
    if s and s.phase == 0 and s.globals then return s.globals[4] end
    return nil
end

local function clock(seconds)
    return string.format("%d:%02d", math.floor(seconds / 60), seconds % 60)
end

--- Whole seconds of combat so far (slot 3 from combat on), or nil before it.
function Warfare.matchClock(s)
    if s and (s.phase == 2 or s.phase == 3) and s.globals then return math.max(0, s.globals[4]) end
    return nil
end

local function covenantHoldAll(s)
    if not (s and s.sites and #s.sites == 3) then return false end
    for i = 1, 3 do
        if s.sites[i].owner ~= Warfare.OWNER_COVENANT then return false end
    end
    return true
end

--- Whole seconds before the Covenant win while they hold all three zones,
--- or nil (slot 4 from combat on, warfare.rs DEFEAT; -1 when the match has
--- no such rule).
function Warfare.defeatIn(s)
    if not (s and s.phase == 2 and s.globals and s.globals[5] > 0) then return nil end
    if not covenantHoldAll(s) then return nil end
    return s.globals[5]
end

--- The match ended because the Covenant held every zone.
function Warfare.covenantWon(s)
    return s ~= nil and s.phase == 3 and s.globals ~= nil and s.globals[5] == 0 and covenantHoldAll(s)
end

--- Whole seconds until the zones open (insertion ends and combat begins), or
--- nil outside insertion. Megalo publishes the insertion's length in slot 3
--- and counts its ticks in slot 1 from the launch tick (warfare.rs), so every
--- client reaches 0 on the same tick.
function Warfare.insertionLeft(s)
    if not (s and s.phase == 1 and s.insertion_seconds and s.elapsed_ticks and s.rate and s.rate > 0) then return nil end
    return math.max(0, s.insertion_seconds - math.floor(s.elapsed_ticks / s.rate))
end
--- Whether a large countdown is showing or about to (warmup's or the
--- insertion's last seconds, DEPLOY, CAPTURE): the HUD then reads ten times a
--- second and has the native state written each time, as in flight. At the
--- 2 Hz snapshot each machine showed a number up to half a second late, at
--- its own phase, so a joiner's numbers trailed the host's (2026-11-23).
Warfare.COUNTDOWN_NEAR = 13
function Warfare.countdownNear(s)
    if not s then return false end
    if s.phase == 0 then
        local left = s.globals and s.globals[4]
        return type(left) == "number" and left >= 0 and left <= Warfare.COUNTDOWN_NEAR
    end
    if s.phase == 1 then
        local left = Warfare.insertionLeft(s)
        local age = s.elapsed_ticks and s.rate and s.rate > 0 and s.elapsed_ticks / s.rate
        return (left ~= nil and left <= Warfare.COUNTDOWN_NEAR) or (age ~= nil and age < 3)
    end
    return false
end
-- Moving zones add CANDIDATE_STRIDE * the site's chosen candidate on top.
Warfare.CANDIDATE_STRIDE = 1024
function Warfare.site(value)
    local covenant = value >= Warfare.COVENANT_PRESENT
    value = value % Warfare.COVENANT_PRESENT
    local candidate = math.floor(value / Warfare.CANDIDATE_STRIDE)
    value = value % Warfare.CANDIDATE_STRIDE
    local k = math.floor(value / 16)
    local taking = k >= COVENANT_STEP_BASE
    return { owner = value % 4, red = math.floor(value / 4) % 2 == 1, blue = math.floor(value / 8) % 2 == 1,
        progress = taking and 0 or (k > 0 and (k - Warfare.PROGRESS_STEPS - 1) or nil), candidate = candidate,
        covenant = covenant, covenantProgress = taking and (k - COVENANT_STEP_BASE) or 0 }
end

--- Each site's extra spots from the level's `warfare.capture_candidates`
--- (Unreal cm, one list per site; candidate k is entry k). Empty without them.
function Warfare.candidates(text)
    local out = { {}, {}, {} }
    local list = type(text) == "string" and text:match('"capture_candidates"%s*:%s*(%b[])') or nil
    if not list then return out end
    local n, c = "([-%d.eE+]+)", "%s*,%s*"
    local site = 0
    for group in list:sub(2, -2):gmatch("%b[]") do
        site = site + 1
        if site > 3 then break end
        for x, y, z in group:gmatch("%[%s*" .. n .. c .. n .. c .. n .. "%s*%]") do
            out[site][#out[site] + 1] = { x = tonumber(x), y = tonumber(y), z = tonumber(z) }
        end
    end
    return out
end

local function integer(s, low, high)
    if type(s) ~= "string" or not s:match("^%-?%d+$") then return nil end
    local n = tonumber(s)
    if not n or n < low or n > high then return nil end
    return n
end

-- Versioned, bounded parser. The writer uses fopen/write/close, so a partial
-- read is possible: incomplete or inconsistent samples never update scores.
-- Keep instance as text: its uint64 value need not fit a Lua double.
function Warfare.parse(text)
    if type(text) ~= "string" or #text > 16384 or text:sub(-1) ~= "\n" then return nil end
    text = text:gsub("\r\n", "\n")
    if text:sub(1, 16) ~= "warfare-state 3\n" then return nil end
    local s = { players = {}, ordinals = {}, flight = {}, clearance = {} }
    local limits = {
        ready = {0, 1}, status = {-16, 16}, host = {0, 1}, tick = {0, 2147483647},
        sampled_ms = {0, 9007199254740991}, phase = {0, 3}, elapsed_ticks = {0, 32767},
        rate = {0, 240}, connected = {-1, 3600}, layout = {0, 32767}, insertion_seconds = {0, 32767},
    }
    for line in text:sub(17):gmatch("([^\n]+)\n") do
        local words = {}
        for word in line:gmatch("%S+") do words[#words + 1] = word end
        local key = table.remove(words, 1)
        if not key or (key ~= "player" and key ~= "ordinal" and key ~= "flight"
            and key ~= "clearance" and s[key] ~= nil) then return nil end
        if limits[key] then
            if #words ~= 1 then return nil end
            s[key] = integer(words[1], limits[key][1], limits[key][2])
            if s[key] == nil then return nil end
        elseif key == "instance" then
            if #words ~= 1 or not words[1]:match("^%d+$") or #words[1] > 20 then return nil end
            s.instance = words[1]
        elseif key == "score" or key == "owner" or key == "globals" then
            local count = key == "score" and 2 or key == "owner" and 3 or 12
            if #words ~= count then return nil end
            local values = {}
            for i, word in ipairs(words) do
                values[i] = integer(word, key == "globals" and -32768 or 0, key == "owner" and 3 or 32767)
                if values[i] == nil then return nil end
            end
            s[key] = values
        elseif key == "reinforcement" then
            -- Wave timing from the map's layout (interval 0: no waves).
            if #words ~= 2 then return nil end
            local interval, flight = integer(words[1], 0, 600), integer(words[2], 0, 600)
            if not interval or not flight or (interval > 0 and flight >= interval) then return nil end
            s.reinforcement = { interval = interval, flight = flight }
        elseif key == "ordinal" then
            if #words ~= 2 then return nil end
            local index, rank = integer(words[1], 0, 15), integer(words[2], 0, 15)
            if not index or not rank or s.ordinals[index] then return nil end
            s.ordinals[index] = rank
        elseif key == "flight" then
            if #words ~= 6 then return nil end
            local index, brake = integer(words[1], 0, 15), integer(words[5], 0, 1)
            if not index or not brake or s.flight[index] then return nil end
            local f = { brake = brake == 1 }
            for i, name in ipairs({"vx", "vy", "vz", "steer"}) do
                local n = tonumber(words[i == 4 and 6 or i + 1])
                if not n or n ~= n or math.abs(n) > (i == 4 and 1 or 2000) then return nil end
                f[name] = n
            end
            s.flight[index] = f
        elseif key == "clearance" then
            if #words ~= 2 then return nil end
            local index, value = integer(words[1], 0, 15), tonumber(words[2])
            if not index or s.clearance[index] or not value or value ~= value or value < 0 or value > 100000 then return nil end
            s.clearance[index] = value
        elseif key == "player" then
            if #words ~= 8 then return nil end
            local p = { index = integer(words[1], 0, 15), team = integer(words[2], -1, 7),
                stage = integer(words[3], 0, 8), localUser = integer(words[4], -1, 3),
                unit = integer(words[8], 0, 4294967295) }
            if not p.index or not p.team or not p.stage or not p.localUser or not p.unit or s.players[p.index] then return nil end
            for i = 5, 7 do
                local n = tonumber(words[i])
                if not n or n ~= n or math.abs(n) > 1000000 then return nil end
                p[({"x", "y", "z"})[i - 4]] = n
            end
            s.players[p.index] = p
        else
            return nil
        end
    end
    for key in pairs(limits) do if s[key] == nil then return nil end end
    if not (s.instance and s.score and s.owner and s.globals) then return nil end
    for _, rows in ipairs({s.flight,s.clearance}) do
        for index in pairs(rows) do
            local p = s.players[index]
            if not p or p.localUser < 0 or (p.stage ~= 3 and p.stage ~= 4) then return nil end
        end
    end
    if s.ready == 1 then
        local g = s.globals
        if s.status ~= 2 or s.instance == "0" or s.sampled_ms == 0 or s.rate < 10
            or s.layout ~= 3 or s.insertion_seconds < 1
            or g[1] ~= s.phase or g[2] ~= s.elapsed_ticks or g[3] ~= Warfare.RULES
            or (s.phase == 1 and g[4] ~= s.insertion_seconds)
            or (s.phase == 0 and g[4] < -1)
            or g[5] ~= s.connected or g[8] ~= s.score[1] or g[9] ~= s.score[2]
            or g[10] % 4 ~= s.owner[1] or g[11] % 4 ~= s.owner[2] or g[12] % 4 ~= s.owner[3] then return nil end
    end
    s.sites = {}
    for i = 1, 3 do
        local site = Warfare.site(math.max(0, s.globals[9 + i]))
        if site.owner ~= s.owner[i] or (site.progress and math.abs(site.progress) > Warfare.PROGRESS_STEPS)
            or site.covenantProgress > Warfare.PROGRESS_STEPS then return nil end
        s.sites[i] = site
    end
    return s
end

--- The reinforcement wave in combat, from the combat clock and the map's
--- timing (native warfare_reinforcement_sortie does the same sums): whether
--- a wave is in the air, and whole seconds until the next one leaves. Nil
--- outside combat or on a map without waves.
function Warfare.wave(s)
    local r = s and s.reinforcement
    if not r or r.interval <= 0 or s.phase ~= 2 or not s.globals then return nil end
    local seconds = math.max(0, s.globals[4])
    local wave = math.floor(seconds / r.interval)
    local age = seconds - wave * r.interval
    return { flying = wave >= 1 and age < r.flight, departs = r.interval - age }
end

--- `jump` names the jump key (Space by default).
function Warfare.describe(s, me, jump)
    jump = jump or "SPACE"
    if not s then return "PELICAN WARFARE  /  WAITING FOR LIVE MATCH STATE" end
    local wave = Warfare.wave(s)
    if wave then
        local player = s.players[me]
        local stage = player and player.stage
        if stage == 1 then return "REINFORCEMENTS  /  BOARDING YOUR TEAM'S PELICAN" end
        -- Native WF_WAITING: respawned at home while the Pelican cannot be
        -- boarded; shielded and unarmed, watching a teammate (warfare_spectate).
        if stage == 8 then
            return "WAITING FOR YOUR PELICAN  /  IT LEAVES IN " .. clock(wave.departs) .. "  /  MOVE TO PLAY FROM BASE"
        end
        if stage == 2 and not wave.flying then
            return "REINFORCEMENTS DEPART IN " .. clock(wave.departs) .. "  /  " .. jump .. ": JUMP NOW"
        end
        if stage == 2 then return "REINFORCEMENTS  /  " .. jump .. " TO JUMP" end
    end
    if s.phase == 0 then
        local left = Warfare.warmupLeft(s)
        local players = s.connected .. (s.connected == 1 and " PLAYER" or " PLAYERS") .. " CONNECTED"
        if not left or left < 0 then return "WARMUP  /  WAITING FOR PLAYERS  /  " .. players end
        return "WARMUP  /  DEPLOYMENT IN " .. clock(left) .. "  /  " .. players
    end
    if s.phase == 3 and Warfare.covenantWon(s) then return "OPERATION FAILED  /  THE COVENANT HOLD EVERY ZONE" end
    if s.phase == 3 then return "OPERATION COMPLETE  /  RED " .. s.score[1] .. "  :  " .. s.score[2] .. " BLUE" end
    local player = s.players[me]
    local stage = player and player.stage
    -- During insertion every line ends with when the zones open.
    local left = Warfare.insertionLeft(s)
    local opens = left and ("  /  ZONES OPEN IN " .. clock(left)) or ""
    if stage == 1 then return "INSERTION  /  BOARDING YOUR TEAM'S PELICAN" .. opens end
    if stage == 2 then return "INSERTION  /  " .. jump .. " TO JUMP" .. opens end
    if stage == 7 then return "INSERTION  /  EXITING PELICAN" .. opens end
    if stage == 3 then return "FREEFALL  /  SPACE TO DEPLOY PARACHUTE" .. opens end
    if stage == 4 then return "PARACHUTE DEPLOYED  /  STEER TOWARD A CAPTURE SITE" .. opens end
    if stage == 6 then return "DEPLOYMENT UNAVAILABLE  /  RESPAWN AT YOUR HOME BASE" end
    if s.phase == 1 then return "ZONES OPEN IN " .. clock(left or 0) .. "  /  PREPARE TO CAPTURE A, B AND C" end
    -- In combat the zone bars in the top left say who holds what
    -- (warfare_zones.lua); the line keeps the match clock, and warns while
    -- the Covenant hold every zone.
    local defeat = Warfare.defeatIn(s)
    if defeat then return "THE COVENANT HOLD EVERY ZONE  /  RETAKE ONE IN " .. clock(defeat) .. " OR LOSE THE ISLAND" end
    local played = Warfare.matchClock(s)
    if played then return "MATCH TIME " .. clock(played) end
    return nil
end

-- deps.readSnapshot(), readLevel(code), Hill; bipedAt and canopy are optional
-- presentation helpers. `match` and the current world's code must agree.
function Warfare.new(deps)
    local self = { next = 0, fields = {}, hills = {} }
    if deps.Canopy and deps.bipedAt then self.canopy = deps.Canopy.new(deps.bipedAt, deps.Grips) end
    -- A fireteam client's rider asks its host to leave the cabin: the host
    -- owns vehicle seats, so only it can detach the rider (requestJump).
    local controls = deps.controls
    if controls and deps.requestJump then
        controls = function(user, unit, forward, right, brake, yaw, edge)
            local result = deps.controls(user, unit, forward, right, brake, yaw, edge)
            local s = self.snapshot
            if edge and s and s.host == 0 then
                for index, p in pairs(s.players) do
                    if p.localUser == user and p.unit == unit and p.stage == 2 then
                        pcall(deps.requestJump, index)
                        break
                    end
                end
            end
            return result
        end
    end
    if deps.Input then self.input = deps.Input.new(controls, deps.blocked) end
    -- On the host, every rider's cabin exit (2 seated -> 7 exiting, 3 falling
    -- or 4 canopy) once an insertion, for the feed (onJump).
    local seated, jumped = {}, {}
    if deps.Instruments then self.instruments = deps.Instruments.new() end
    if deps.Countdown then self.countdown = deps.Countdown.new() end
    -- With no teammate to watch while waiting, the view looks over the three
    -- zones from behind and above them (their centre, Unreal cm).
    local function overview()
        local x, y, z, n = 0, 0, 0, 0
        for i = 1, 3 do
            local spot = self.spot(i)
            if spot then x, y, z, n = x + spot.x, y + spot.y, z + spot.z, n + 1 end
        end
        if n == 0 then return nil end
        x, y, z = x / n, y / n, z / n
        return { at = { X = x - 9000, Y = y, Z = z + 7500 }, rot = { Pitch = -38, Yaw = 0, Roll = 0 } }
    end
    if deps.Spectate and deps.bipedAt then self.spectate = deps.Spectate.new({ bipedAt = deps.bipedAt, overview = overview }) end
    -- Cortana and the announcer (warfare_voice.lua): fed each accepted
    -- snapshot below, silent when its waves are not installed.
    if deps.Voice and deps.voiceIO then self.voice = deps.Voice.new(deps.voiceIO) end
    local pending, refreshedAt, line

    --- Where site `i` is this match: its chosen candidate (candidate 0 is the
    --- classic spot), or nil when the snapshot names one this map lacks.
    function self.spot(i)
        local classic = self.hills[i]
        local site = self.snapshot and self.snapshot.sites and self.snapshot.sites[i]
        local k = site and site.candidate or 0
        if not classic or k == 0 then return classic end
        local c = self.candidates and self.candidates[i] and self.candidates[i][k]
        return c and { x = c.x, y = c.y, z = c.z, r = classic.r } or nil
    end

    --- The three sites where this match put them (for the zone tiles).
    function self.spots()
        return { self.spot(1), self.spot(2), self.spot(3) }
    end

    function self.start(code)
        self.code = code
        self.hills = deps.Hill.parse(deps.readLevel(code))
        -- This mode has exactly three authored sites. Never draw an invented
        -- location if level metadata is absent or an incompatible map loads.
        if #self.hills ~= 3 then self.hills = {} end
        self.candidates = Warfare.candidates(deps.readLevel(code))
        for i = 1, 3 do self.fields[i] = deps.Hill.field("mjolnir_warfare_" .. i) end
        line = deps.Hill.field("mjolnir_warfare_status")
        return #self.hills
    end

    local function hideMarkers()
        if line then line.hide() end
        if self.instruments then self.instruments.hide() end
        if self.countdown then self.countdown.hide() end
        if self.spectate then pcall(self.spectate.restore) end
        for _, field in ipairs(self.fields) do field.hide() end
    end

    function self.hide()
        hideMarkers()
        if self.canopy then self.canopy.hide() end
        if self.input then self.input.clear() end
    end

    -- Require two advancing samples before trusting a file found on disk.
    -- Opening an old file at game launch cannot revive an old match's score.
    function self.accept(s, now)
        if not s or s.ready ~= 1 then
            if s then self.snapshot, pending, refreshedAt = nil, nil, nil end
            return false
        end
        local previous = self.snapshot or pending
        if not previous or previous.instance ~= s.instance then
            self.snapshot, pending, refreshedAt = nil, s, now
            return false
        end
        -- The engine can reset its next round just before the HUD's lobby
        -- travel. A terminal result belongs to this instance until a new
        -- instance or explicit map/mode reset, even if that tick advances.
        if self.snapshot and self.snapshot.phase == 3 then return false end
        if s.tick > previous.tick and s.sampled_ms > previous.sampled_ms then
            if not self.snapshot and now - refreshedAt > STALE then
                pending, refreshedAt = s, now
                return false
            end
            self.snapshot, pending, refreshedAt = s, nil, now
            return true
        end
        return false
    end

    function self.tick(match, now, pc, hidden, me, currentCode)
        if match.variant ~= "warfare" or match.code ~= "PWR" or currentCode ~= "PWR" then
            self.snapshot, pending, refreshedAt = nil, nil, nil
            if self.voice then self.voice.reset() end
            self.hide()
            return false
        end
        if now < self.next then return false end
        local prev = self.snapshot and self.snapshot.players[me]
        local activeFlight = prev and prev.localUser >= 0 and (prev.stage == 2 or prev.stage == 7 or prev.stage == 3 or prev.stage == 4)
        local fast = activeFlight or Warfare.countdownNear(self.snapshot)
        self.next = now + (fast and FLIGHT_EVERY or EVERY)
        local changed = false
        if not match.over then
            if fast and deps.pumpFlight then deps.pumpFlight() end
            local s = Warfare.parse(deps.readSnapshot())
            local accepted = self.accept(s, now)
            -- A verified terminal snapshot remains valid while the sim is
            -- stopped in postgame. Normal phases expire when ticks stop.
            local lifetime = activeFlight and deps.pumpFlight and .8 or STALE
            if refreshedAt and now - refreshedAt > lifetime and self.snapshot and self.snapshot.phase ~= 3 then
                self.snapshot, pending = nil, nil
                -- After a gap the next sample is a fresh baseline: no burst of
                -- lines for what changed while the state was not read.
                if self.voice then self.voice.reset() end
            end
            if accepted then
                local snap = self.snapshot
                if snap.host == 1 and deps.onJump then
                    if jumped.instance ~= snap.instance then seated, jumped = {}, { instance = snap.instance } end
                    for index, p in pairs(snap.players) do
                        if p.stage == 2 then seated[index] = p.unit
                        elseif seated[index] == p.unit and not jumped[index]
                            and (p.stage == 7 or p.stage == 3 or p.stage == 4) then
                            jumped[index] = true
                            pcall(deps.onJump, index, p.team)
                        end
                    end
                end
                -- Site changes between two accepted samples of one instance in combat
                -- go to the feed (onSite); the first sample (a join) only sets the baseline.
                if deps.onSite then
                    local seen = self.seenOwners
                    if snap.phase == 2 and seen and seen.instance == snap.instance then
                        for i = 1, 3 do
                            if snap.owner[i] ~= seen[i] then pcall(deps.onSite, i, snap.owner[i], seen[i], snap.sites[i]) end
                        end
                    end
                    self.seenOwners = snap.phase == 2 and { instance = snap.instance, snap.owner[1], snap.owner[2], snap.owner[3] } or nil
                end
                if self.voice then
                    local ok, err = pcall(self.voice.observe, snap, me, now)
                    if not ok and deps.log then deps.log("warfare voice: " .. tostring(err)) end
                end
                local score = self.snapshot.score
                changed = match.teams[0] ~= score[1] or match.teams[1] ~= score[2]
                match.teams[0], match.teams[1] = score[1], score[2]
                match.warfareInstance = self.snapshot.instance
            end
        end
        -- Every tick, after the match too: the result lines are queued by the
        -- last accepted sample and play out over the postgame.
        if self.voice then pcall(self.voice.pump, now, pc) end
        local s = self.snapshot
        if self.input then
            self.input.tick(not match.over and s or nil, pc, hidden)
            if self.input.frame then self.input.frame(now) end
        end
        if self.canopy then self.canopy.tick(match, not match.over and s or nil, pc, now) end
        if hidden then hideMarkers(); return changed end
        pcall(function()
            local world = line.worldOf(pc)
            if not world then return end
            local player = s and s.players[me]
            local airborne = player and player.localUser >= 0 and (player.stage == 3 or player.stage == 4)
            local blocked = deps.blocked and deps.blocked()
            if self.countdown then
                local ok, err = pcall(self.countdown.update, pc, not match.over and s or nil, now)
                if not ok and deps.log then deps.log("warfare countdown: " .. tostring(err)) end
            end
            if self.spectate then
                local ok, err = pcall(self.spectate.update, pc, s, me, match.players, Warfare.wave(s), match.over)
                if not ok then
                    pcall(self.spectate.restore, pc)
                    if deps.log then deps.log("warfare spectate: " .. tostring(err)) end
                end
            end
            local instrumentsShown = false
            if self.instruments then
                if airborne and not blocked and not match.over and s.phase ~= 3 then
                    local jump, brake
                    if self.input and self.input.labels then jump, brake = self.input.labels(player.localUser) end
                    local ok, shown = pcall(self.instruments.update, pc, player.stage, s.flight[me], s.clearance[me], jump, brake,
                        Warfare.insertionLeft(s))
                    instrumentsShown = ok and shown
                else self.instruments.hide() end
            end
            if instrumentsShown or (airborne and blocked) then line.hideLine()
            else
                line.ensureLine(pc)
                local jump
                if player and self.input and self.input.labels then jump = self.input.labels(player.localUser) end
                local text = Warfare.describe(s, me, jump)
                if player and player.stage == 2 and jump and s.phase == 1 then
                    local left = Warfare.insertionLeft(s)
                    text = "INSERTION  /  " .. jump .. " TO JUMP" .. (left and ("  /  ZONES OPEN IN " .. clock(left)) or "")
                end
                local watched = self.spectate and self.spectate.watching()
                local who = watched and match.players[watched] and match.players[watched].name
                if text and watched then text = text .. "  /  WATCHING " .. string.upper(who or "A TEAMMATE") end
                if text then line.say(text .. "   /   M: MAP") else line.hideLine() end
            end
            -- A zone's first draw spawns its wall and traces the ground under
            -- each panel; all three at once held the launch tick ~25 ms (GTX
            -- 1080 Ti test PC, 2026-11-25). One new zone a tick spreads it.
            local placed = false
            for i, field in ipairs(self.fields) do
                local spot = self.spot(i)
                -- From insertion on: the zones may have moved, so riders see where to steer.
                if s and (s.phase == 1 or s.phase == 2) and spot and not match.over then
                    local owner = s.owner[i]
                    if field.drawn == i or not placed then
                        if field.drawn ~= i then placed = true end
                        field.draw(world, now, i, spot)
                    end
                    field.paint(COLOUR[owner], now)
                    field.mark(pc, deps.Hill.markerSpot(spot), COLOUR[owner], "Koth",
                        string.char(64 + i) .. "  /  " .. OWNER[owner], now)
                else field.hide() end
            end
        end)
        return changed
    end

    function self.frame(pc, now)
        if self.input and self.input.frame then self.input.frame(now) end
        if self.canopy and self.canopy.frame then self.canopy.frame(now, self.input) end
        if self.instruments then self.instruments.frame(pc, now) end
        for _, field in ipairs(self.fields) do field.frame(pc, now) end
    end
    return self
end

return Warfare

-- Pelican Warfare presentation. The native snapshot is read twice a second;
-- Megalo owns capture/score/phase and the native adapter owns all movement.
-- There are no world scans, gameplay writes, or inferred objective scores.
local Warfare = {}
local EVERY, FLIGHT_EVERY, STALE = 0.5, 0.1, 2
local OWNER = { [0] = "NEUTRAL", [1] = "RED", [2] = "BLUE" }
local COLOUR = { [0] = "empty", [1] = "Red", [2] = "Blue" }

-- Megalo publishes each site as one packed number (blam-megalo warfare.rs
-- SiteState): owner in the low two bits, who stands in it in the next two,
-- and its capture progress in steps of PROGRESS_STEPS toward Red (+) or Blue
-- (-) above. Below 16 there is no progress (an older variant): owner only.
Warfare.PROGRESS_STEPS = 16
function Warfare.site(value)
    local k = math.floor(value / 16)
    return { owner = value % 4, red = math.floor(value / 4) % 2 == 1, blue = math.floor(value / 8) % 2 == 1,
        progress = k > 0 and (k - Warfare.PROGRESS_STEPS - 1) or nil }
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
    if text:sub(1, 16) ~= "warfare-state 2\n" then return nil end
    local s = { players = {}, ordinals = {}, flight = {}, clearance = {} }
    local limits = {
        ready = {0, 1}, status = {-16, 16}, host = {0, 1}, tick = {0, 2147483647},
        sampled_ms = {0, 9007199254740991}, phase = {0, 3}, elapsed_ticks = {0, 32767},
        rate = {0, 240}, connected = {0, 16}, layout = {0, 32767}, insertion_seconds = {0, 32767},
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
                values[i] = integer(word, key == "globals" and -32768 or 0, key == "owner" and 2 or 32767)
                if values[i] == nil then return nil end
            end
            s[key] = values
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
                stage = integer(words[3], 0, 7), localUser = integer(words[4], -1, 3),
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
            or g[1] ~= s.phase or g[2] ~= s.elapsed_ticks or g[3] ~= 20569
            or (s.phase < 2 and g[4] ~= s.insertion_seconds)
            or g[5] ~= s.connected or g[8] ~= s.score[1] or g[9] ~= s.score[2]
            or g[10] % 4 ~= s.owner[1] or g[11] % 4 ~= s.owner[2] or g[12] % 4 ~= s.owner[3] then return nil end
    end
    s.sites = {}
    for i = 1, 3 do
        local site = Warfare.site(math.max(0, s.globals[9 + i]))
        if site.owner ~= s.owner[i] or (site.progress and math.abs(site.progress) > Warfare.PROGRESS_STEPS) then return nil end
        s.sites[i] = site
    end
    return s
end

function Warfare.describe(s, me)
    if not s then return "PELICAN WARFARE  /  WAITING FOR LIVE MATCH STATE" end
    if s.phase == 0 then return "WARMUP  /  " .. s.connected .. " PLAYERS CONNECTED  /  ASSEMBLE FOR DEPLOYMENT" end
    if s.phase == 3 then return "OPERATION COMPLETE  /  RED " .. s.score[1] .. "  :  " .. s.score[2] .. " BLUE" end
    local player = s.players[me]
    local stage = player and player.stage
    if stage == 1 then return "INSERTION  /  BOARDING YOUR TEAM'S PELICAN" end
    if stage == 2 then return "INSERTION  /  SPACE TO JUMP" end
    if stage == 7 then return "INSERTION  /  EXITING PELICAN" end
    if stage == 3 then return "FREEFALL  /  SPACE TO DEPLOY PARACHUTE" end
    if stage == 4 then return "PARACHUTE DEPLOYED  /  STEER TOWARD A CAPTURE SITE" end
    if stage == 6 then return "DEPLOYMENT UNAVAILABLE  /  RESPAWN AT YOUR HOME BASE" end
    if s.phase == 1 then return "INSERTION IN PROGRESS  /  PREPARE TO CAPTURE A, B AND C" end
    -- In combat the zone tiles under the score say it (warfare_zones.lua): no line.
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
    local pending, refreshedAt, line

    function self.start(code)
        self.code = code
        self.hills = deps.Hill.parse(deps.readLevel(code))
        -- This mode has exactly three authored sites. Never draw an invented
        -- location if level metadata is absent or an incompatible map loads.
        if #self.hills ~= 3 then self.hills = {} end
        for i = 1, 3 do self.fields[i] = deps.Hill.field("mjolnir_warfare_" .. i) end
        line = deps.Hill.field("mjolnir_warfare_status")
        return #self.hills
    end

    local function hideMarkers()
        if line then line.hide() end
        if self.instruments then self.instruments.hide() end
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
            self.hide()
            return false
        end
        if now < self.next then return false end
        local prev = self.snapshot and self.snapshot.players[me]
        local activeFlight = prev and prev.localUser >= 0 and (prev.stage == 2 or prev.stage == 7 or prev.stage == 3 or prev.stage == 4)
        self.next = now + (activeFlight and FLIGHT_EVERY or EVERY)
        local changed = false
        if not match.over then
            if activeFlight and deps.pumpFlight then deps.pumpFlight() end
            local s = Warfare.parse(deps.readSnapshot())
            local accepted = self.accept(s, now)
            -- A verified terminal snapshot remains valid while the sim is
            -- stopped in postgame. Normal phases expire when ticks stop.
            local lifetime = activeFlight and deps.pumpFlight and .8 or STALE
            if refreshedAt and now - refreshedAt > lifetime and self.snapshot and self.snapshot.phase ~= 3 then
                self.snapshot, pending = nil, nil
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
                local score = self.snapshot.score
                changed = match.teams[0] ~= score[1] or match.teams[1] ~= score[2]
                match.teams[0], match.teams[1] = score[1], score[2]
                match.warfareInstance = self.snapshot.instance
            end
        end
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
            local instrumentsShown = false
            if self.instruments then
                if airborne and not blocked and not match.over and s.phase ~= 3 then
                    local jump, brake
                    if self.input and self.input.labels then jump, brake = self.input.labels(player.localUser) end
                    local ok, shown = pcall(self.instruments.update, pc, player.stage, s.flight[me], s.clearance[me], jump, brake)
                    instrumentsShown = ok and shown
                else self.instruments.hide() end
            end
            if instrumentsShown or (airborne and blocked) then line.hideLine()
            else
                line.ensureLine(pc)
                local text = Warfare.describe(s, me)
                if player and player.stage == 2 and self.input and self.input.labels then
                    text = "INSERTION  /  " .. self.input.labels(player.localUser) .. " TO JUMP"
                end
                if text then line.say(text .. "   /   M: MAP") else line.hideLine() end
            end
            for i, field in ipairs(self.fields) do
                local spot = self.hills[i]
                if s and s.phase == 2 and spot and not match.over then
                    local owner = s.owner[i]
                    field.draw(world, now, i, spot)
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

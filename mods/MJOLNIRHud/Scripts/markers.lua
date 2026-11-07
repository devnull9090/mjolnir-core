-- MJOLNIR HUD: what a match marks in the world, by game type family: the hill
-- (Scripts/hill.lua), the next flag (Scripts/race.lua), the Juggernaut
-- (Scripts/juggernaut.lua), the flags (Scripts/flagmark.lua). main.lua holds this
-- one module, so its tick and handlers do not each carry the four.

local Markers = {}

--- `deps`: Hill, Race, Juggernaut, FlagMark, Board, Waypoint (the modules), readLevel(map),
--- log(text).
function Markers.new(deps)
    local self = {}
    deps.Hill.Waypoint, deps.Hill.log = deps.Waypoint, deps.log

    local unitClass

    --- Where another player's body stands: the biped their spawn named
    --- (main.lua's player_spawn), while it is still valid, they are alive,
    --- and it is still their unit (actors are pooled). nil when unknown.
    local function bipedAt(p, index)
        local biped = p and not p.dead and p.biped
        if not biped then return nil end
        local at
        pcall(function()
            if not biped:IsValid() then return end
            unitClass = unitClass or StaticFindObject("/Script/BlamSynchronization.BlamUnitComponent")
            local unit = biped:GetComponentByClass(unitClass)
            if not (unit and unit:IsValid()) then return end
            local datum = unit:GetControllingPlayerDatumIndex()
            if type(datum) ~= "number" or datum == -1 or math.floor(datum % 65536) ~= index then return end
            at = biped:K2_GetActorLocation()
        end)
        return at
    end
    self.bipedAt = bipedAt

    --- Each player with a body: { index, at, team, me }. Players, not AI: the
    --- scripts walk players, so bots neither hold a hill nor contest one. Every
    --- pawn is read here and now, never kept. Only this machine's own pawn
    --- follows its player: another player's sits at the world's origin here,
    --- or on a fireteam client is gone altogether (two PCs, 2026-11-07, which
    --- hid a contested hill and put a remote Juggernaut's marker at the
    --- origin), so they are read from their biped, and left out while it is
    --- unknown.
    local function playersOn(match, pc)
        return function()
            local players = {}
            local mine = pc.Pawn
            local myAddress = mine and mine:IsValid() and mine:GetAddress() or nil
            pc:GetWorld().GameState.PlayerArray:ForEach(function(_, element)
                local ps = element:get()
                local pawn = ps:GetPawn()
                local index = ps.BlamPlayerStateComponent.BlamAbsolutePlayerIndex
                local p = match.players[index]
                local me = pawn and pawn:IsValid() and pawn:GetAddress() == myAddress
                local at = me and pawn:K2_GetActorLocation() or bipedAt(p, index)
                if at then
                    players[#players + 1] = {
                        index = index,
                        at = at,
                        team = match.mode.teams and p and p.team or nil,
                        me = me or false,
                    }
                end
            end)
            return players
        end
    end

    --- The laps the local player's side has done: its own, or in a team game
    --- the team's, as the score to win counts them.
    local function lapsDone(match, me)
        local mine = match.players[me]
        if not mine then return 0 end
        if match.mode.teams then return deps.Board.totals(match)[mine.team] or 0 end
        return mine.objectiveScore or 0
    end

    local function made(match)
        local family = match.mode.family
        if family == "king" and not match.hill then
            match.hill = deps.Hill.new(deps.readLevel)
            deps.log("hill marker: " .. match.hill.start(match.code) .. " hill(s)")
        elseif family == "race" and not match.race then
            match.race = deps.Race.new(deps.Hill, deps.readLevel, match.mode.rally)
            deps.log("race marker: " .. match.race.start(match.code) .. " flag(s)")
        elseif family == "juggernaut" and not match.juggernaut then
            match.juggernaut = deps.Juggernaut.new(deps.Hill, match.mode.holder)
        elseif family == "ctf" and not match.flags then
            local seconds = match.mode.sideSeconds
            match.flags = deps.FlagMark.new(deps.Hill, seconds and { seconds = seconds, host = match.host } or nil)
        end
    end

    function self.tick(match, now, pc, hidden, me)
        made(match)
        if match.hill then match.hill.tick(now, pc, hidden, playersOn(match, pc)) end
        if match.race then match.race.tick(now, pc, hidden, lapsDone(match, me), match.mode.toWin or 0) end
        if match.juggernaut then match.juggernaut.tick(now, pc, hidden, me, playersOn(match, pc)) end
        if match.flags then
            local mine = match.players[me]
            match.flags.tick(now, pc, hidden, mine and mine.team)
        end
    end

    --- Every frame, from any player controller: on a host that can be a
    --- client's, and the marker is the local player's.
    function self.frame(match, pc, now)
        local marker = match.hill or match.race or match.juggernaut or match.flags
        if marker and pc:IsLocalController() then marker.frame(pc, now) end
    end

    function self.hide(match)
        for _, marker in ipairs({ match.hill or false, match.race or false, match.juggernaut or false,
            match.flags or false }) do
            if marker then marker.hide() end
        end
    end

    --- What the markers know, as one line (`mjolnir_markers` logs it): the
    --- live hill or the Juggernaut, and where each player stands for them.
    function self.describe(match, pc)
        if not match then return "no match" end
        local parts = { "family " .. tostring(match.mode and match.mode.family) }
        if match.hill then parts[#parts + 1] = "hill " .. tostring(match.hill.live) end
        if match.juggernaut then parts[#parts + 1] = "it " .. tostring(match.juggernaut.it) end
        local seen = {}
        for _, p in ipairs(playersOn(match, pc)()) do
            seen[p.index] = true
            parts[#parts + 1] = string.format("p%d%s at %.0f %.0f %.0f", p.index, p.me and " (me)" or "",
                p.at.X, p.at.Y, p.at.Z)
        end
        for index, p in pairs(match.players or {}) do
            if not seen[index] and p.name and not p.bot then
                parts[#parts + 1] = string.format("p%d unknown (%s%s)", index, p.dead and "dead" or "alive",
                    p.biped and ", stale biped" or ", no biped")
            end
        end
        return table.concat(parts, "; ")
    end

    --- An incident a marker reads. Returns true when someone new became the
    --- Juggernaut, for the feed.
    function self.incident(match, inc, me)
        if inc.name == "hill_moved" and match.hill then
            match.hill.moved(inc.value)
        elseif inc.name == "checkpoint_reached" and match.race then
            match.race.checkpoint(inc.cause, inc.value, me)
        elseif inc.name == "checkpoint_reached" and match.hill then
            -- A moving hill's silent resend on each spawn, for joiners.
            match.hill.moved(inc.value)
        elseif inc.name == "new_juggernaut" and match.juggernaut then
            return match.juggernaut.named(inc.cause)
        end
        return false
    end

    return self
end

return Markers

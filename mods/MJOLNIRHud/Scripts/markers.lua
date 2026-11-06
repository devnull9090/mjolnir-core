-- MJOLNIR HUD: what a match marks in the world, by game type family: the hill
-- (Scripts/hill.lua), the next flag (Scripts/race.lua), the Juggernaut
-- (Scripts/juggernaut.lua). main.lua holds this one module, so its tick and
-- handlers do not each carry the three.

local Markers = {}

--- `deps`: Hill, Race, Juggernaut, Board (the modules), readLevel(map), log(text).
function Markers.new(deps)
    local self = {}

    --- Each player with a body: { index, at, team, me }. Players, not AI: the
    --- scripts walk players, so bots neither hold a hill nor contest one. Every
    --- pawn is read here and now, never kept.
    local function playersOn(match, pc)
        return function()
            local players = {}
            local mine = pc.Pawn
            local myAddress = mine and mine:IsValid() and mine:GetAddress() or nil
            pc:GetWorld().GameState.PlayerArray:ForEach(function(_, element)
                local ps = element:get()
                local pawn = ps:GetPawn()
                if pawn and pawn:IsValid() then
                    local index = ps.BlamPlayerStateComponent.BlamAbsolutePlayerIndex
                    local p = match.players[index]
                    players[#players + 1] = {
                        index = index,
                        at = pawn:K2_GetActorLocation(),
                        team = match.mode.teams and p and p.team or nil,
                        me = pawn:GetAddress() == myAddress,
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
        end
    end

    function self.tick(match, now, pc, hidden, me)
        made(match)
        if match.hill then match.hill.tick(now, pc, hidden, playersOn(match, pc)) end
        if match.race then match.race.tick(now, pc, hidden, lapsDone(match, me), match.mode.toWin or 0) end
        if match.juggernaut then match.juggernaut.tick(now, pc, hidden, me, playersOn(match, pc)) end
    end

    function self.hide(match)
        for _, marker in ipairs({ match.hill or false, match.race or false, match.juggernaut or false }) do
            if marker then marker.hide() end
        end
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

-- Presentation model, independent of Unreal. Teams are reported by the
-- simulation, never guessed from player order or alternating player indices.
local Board = {}

Board.modes = {
    slayer = { title = "SLAYER", toWin = 25, unit = "kills", stat = "kills" },
    team_slayer = { title = "TEAM SLAYER", toWin = 50, unit = "kills", stat = "kills", teams = true },
    ctf = { title = "CAPTURE THE FLAG", toWin = 3, unit = "captures", stat = "captures", teams = true },
}

function Board.team(value)
    if value == "Red" or value == "Blue" then return value end
    return nil
end

function Board.score(player, mode)
    return player[mode.stat or "kills"] or 0
end

function Board.totals(match)
    if match.variant ~= "team_slayer" then
        return { Red = match.teams[0] or 0, Blue = match.teams[1] or 0 }
    end
    local totals = { Red = 0, Blue = 0 }
    for _, kill in ipairs(match.teamKills) do
        -- Resolve delayed assignment once; a later switch or quit must not
        -- transfer or erase an earned team point.
        local player = match.players[kill.player]
        kill.team = kill.team or (player and Board.team(player.team))
        if totals[kill.team] then totals[kill.team] = totals[kill.team] + 1 end
    end
    return totals
end

function Board.summary(match, localPlayer)
    local mine = match.players[localPlayer]
    if match.mode.teams then
        local totals = Board.totals(match)
        return { left = totals.Red, right = totals.Blue,
            leftLabel = mine and mine.team == "Red" and "RED / YOU" or "RED",
            rightLabel = mine and mine.team == "Blue" and "BLUE / YOU" or "BLUE",
            leftTeam = "Red", rightTeam = "Blue" }
    end
    local best = 0
    for _, player in pairs(match.players) do
        if not player.left then best = math.max(best, Board.score(player, match.mode)) end
    end
    return { left = mine and Board.score(mine, match.mode) or 0, right = best,
        leftLabel = "YOU", rightLabel = "LEADER" }
end

function Board.rows(players, mode, totals)
    local sorted = {}
    for _, player in pairs(players) do
        if not player.left then sorted[#sorted + 1] = player end
    end
    table.sort(sorted, function(a, b)
        local sa, sb = Board.score(a, mode), Board.score(b, mode)
        if sa ~= sb then return sa > sb end
        if a.kills ~= b.kills then return a.kills > b.kills end
        if a.deaths ~= b.deaths then return a.deaths < b.deaths end
        return a.index < b.index
    end)
    local rows = {}
    if not mode.teams then
        for _, p in ipairs(sorted) do rows[#rows + 1] = { player = p } end
        return rows
    end
    for _, team in ipairs({ "Red", "Blue", "Unassigned" }) do
        local members = {}
        for _, p in ipairs(sorted) do
            if (Board.team(p.team) or "Unassigned") == team then members[#members + 1] = p end
        end
        if team ~= "Unassigned" or #members > 0 then
            rows[#rows + 1] = { team = team, count = #members,
                total = team ~= "Unassigned" and ((totals or {})[team] or 0) or nil }
            for _, p in ipairs(members) do rows[#rows + 1] = { player = p } end
        end
    end
    return rows
end

return Board

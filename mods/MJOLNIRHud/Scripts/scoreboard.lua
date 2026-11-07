-- Presentation model, independent of Unreal. Teams are reported by the
-- simulation, never guessed from player order or alternating player indices.
local Board = {}

-- One row per variant id. `family` is what the variants of an engine share
-- (the hill, the ball, the flags); `snapshot` is the incident that carries a
-- player's absolute score, for the stat `objectiveScore`
-- (crates/blam-megalo/src/objectives.rs); `suicidePenalty` says the script takes
-- a point for a suicide; `rally` is one live flag for everyone. The `juggernaut`
-- family's `holder` says what the one who holds the role reads (`line`), what
-- the feed says of them (`feed`), and `unseen` that nobody gets a beacon on
-- them, because the mode hides them (Scripts/juggernaut.lua).
local function timed(title, family, snapshot, teams)
    return { title = title, toWin = 120, unit = "seconds", stat = "objectiveScore", family = family,
        snapshot = snapshot, teams = teams }
end
local function flags(title, toWin, unit, teams, rally)
    return { title = title, toWin = toWin, unit = unit, stat = "objectiveScore", family = "race",
        snapshot = "final_lap", teams = teams, rally = rally }
end

Board.modes = {
    slayer = { title = "SLAYER", toWin = 25, unit = "kills", stat = "kills", family = "slayer", suicidePenalty = true },
    team_slayer = { title = "TEAM SLAYER", toWin = 50, unit = "kills", stat = "kills", teams = true,
        family = "slayer", suicidePenalty = true },
    ctf = { title = "CAPTURE THE FLAG", toWin = 3, unit = "captures", stat = "captures", teams = true, family = "ctf" },
    assault = { title = "ASSAULT", toWin = 3, unit = "captures", stat = "captures", teams = true, family = "ctf" },
    oddball = timed("ODDBALL", "oddball", "ball_taken"),
    team_oddball = timed("TEAM ODDBALL", "oddball", "ball_taken", true),
    juggernaut = { title = "JUGGERNAUT", toWin = 15, unit = "points", stat = "objectiveScore", family = "juggernaut",
        snapshot = "ball_taken", holder = { line = "YOU ARE THE JUGGERNAUT", feed = "is the Juggernaut" } },
    stalker = { title = "STALKER", toWin = 10, unit = "points", stat = "objectiveScore", family = "juggernaut",
        snapshot = "ball_taken", holder = { line = "YOU ARE THE STALKER", feed = "is the Stalker", unseen = true } },
    reverse_tag = { title = "REVERSE TAG", toWin = 120, unit = "seconds", stat = "objectiveScore", family = "juggernaut",
        snapshot = "ball_taken", holder = { line = "YOU ARE IT", feed = "is it" } },
    koth = timed("KING OF THE HILL", "king", "hill_controlled"),
    crazy_king = timed("CRAZY KING", "king", "hill_controlled"),
    team_koth = timed("TEAM KING", "king", "hill_controlled", true),
    race = flags("RACE", 3, "laps"),
    team_race = flags("TEAM RACE", 6, "laps", true),
    rally = flags("RALLY", 15, "flags", nil, true),
    team_rally = flags("TEAM RALLY", 15, "flags", true, true),
    forge = { title = "FORGE", toWin = 25, unit = "kills", stat = "kills", family = "forge" },
}

function Board.team(value)
    if value == "Red" or value == "Blue" then return value end
    return nil
end

function Board.score(player, mode)
    return player[mode.stat or "kills"] or 0
end

function Board.totals(match)
    local mode = Board.modes[match.variant]
    if mode and mode.teams and mode.stat == "objectiveScore" then
        -- A team's score is the sum of its players', as the simulation adds it
        -- up. Those who left are still in the list, with what they earned.
        local totals = { Red = 0, Blue = 0 }
        for _, player in pairs(match.players) do
            local team = Board.team(player.team)
            if team then totals[team] = totals[team] + (player.objectiveScore or 0) end
        end
        return totals
    end
    if match.variant ~= "team_slayer" then
        return { Red = match.teams[0] or 0, Blue = match.teams[1] or 0 }
    end
    local totals = { Red = 0, Blue = 0 }
    for _, kill in ipairs(match.teamKills) do
        -- Resolve delayed assignment once; a later switch or quit must not
        -- transfer or erase an earned team point.
        local player = match.players[kill.player]
        kill.team = kill.team or (player and Board.team(player.team))
        if totals[kill.team] then totals[kill.team] = totals[kill.team] + (kill.points or 1) end
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

--- Who won: "RED TEAM WINS", "<name> WINS", or "DRAW" when the lead is
--- shared (or nobody scored).
function Board.winner(match)
    if match.mode.teams then
        local totals = Board.totals(match)
        if totals.Red == totals.Blue then return "DRAW" end
        return (totals.Red > totals.Blue and "RED" or "BLUE") .. " TEAM WINS"
    end
    local rows = Board.rows(match.players, match.mode)
    local first, second = rows[1] and rows[1].player, rows[2] and rows[2].player
    if not first or Board.score(first, match.mode) == 0 then return "DRAW" end
    if second and Board.score(second, match.mode) == Board.score(first, match.mode) then return "DRAW" end
    return string.upper(first.display or first.name or ("Player " .. tostring(first.index + 1))) .. " WINS"
end

local function field(value)
    return (tostring(value == nil and "" or value):gsub("[\t\r\n]", " "))
end

--- The finished match as tab-separated lines, for the post-game screen on
--- the menu (MJOLNIRLobby reads them back):
---   match  <code> <variant> <title> <mode title> <winner> <ended at> <match id or ->
---   team   <Red|Blue> <total>
---   player <name> <score> <kills> <deaths> <team or -> <1 if local>
---          <hub account id or -> <hub name or -> <reports>
--- Players in standing order. The name is the in-game one; the account is
--- the hub's (docs/player_identity.md), which the post-game screen shows and
--- reports cite, with the match id.
function Board.results(match, localPlayer, endedAt, matchId)
    local lines = { table.concat({ "match", field(match.code), field(match.variant), field(match.title),
        field(match.mode.title), field(Board.winner(match)), field(endedAt), field(matchId or "-") }, "\t") }
    if match.mode.teams then
        local totals = Board.totals(match)
        for _, team in ipairs({ "Red", "Blue" }) do
            lines[#lines + 1] = table.concat({ "team", team, field(totals[team]) }, "\t")
        end
    end
    for _, row in ipairs(Board.rows(match.players, match.mode, Board.totals(match))) do
        local p = row.player
        if p then
            lines[#lines + 1] = table.concat({ "player", field(p.name or ("Player " .. tostring(p.index + 1))),
                field(Board.score(p, match.mode)), field(p.kills), field(p.deaths),
                field(Board.team(p.team) or "-"), p.index == localPlayer and "1" or "0",
                field(p.userId or "-"), field(p.display or "-"), field(p.reports or 0) }, "\t")
        end
    end
    return table.concat(lines, "\n") .. "\n"
end

return Board

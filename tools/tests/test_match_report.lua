-- MJOLNIRHud's match report stays inside what the hub accepts
-- (hub/src/lib/api/matches.ts): a refused report loses the whole match.
-- lua5.4 tools/tests/test_match_report.lua

-- luacheck: globals io
local files = {}
local realOpen = io.open
io.open = function(path, mode)
    if mode == "rb" then
        if not files[path] then return nil end
        return { read = function() return files[path] end, close = function() end }
    end
    files[path] = files[path] or ""
    if mode == "wb" then files[path] = "" end
    return {
        write = function(_, ...) files[path] = files[path] .. table.concat({ ... }) end,
        close = function() end,
    }
end

local MatchLog = dofile("mods/MJOLNIRHud/Scripts/matchlog.lua")
local Board = dofile("mods/MJOLNIRHud/Scripts/scoreboard.lua")

local function eq(got, want, what)
    if got ~= want then error(what .. ": got " .. tostring(got) .. ", want " .. tostring(want), 2) end
end

local DIR = "mods\\MJOLNIRHud"
files["mods\\MJOLNIRLobby\\listing.txt"] = "lobby-1"
MatchLog.init({ modDir = DIR, log = function() end, version = "test" })

local function player(index, team, kills, rawKills, suicides)
    return { index = index, team = team, kills = kills, rawKills = rawKills,
        deaths = suicides, suicides = suicides, captures = 0, name = "P" .. index }
end

local function report(match)
    match.mode = Board.modes[match.variant]
    match.code = "BGL"
    MatchLog.start(match, 0)
    local id = MatchLog.currentId()
    MatchLog.finish(match, Board, 0, "game_over", 120)
    return files[DIR .. "\\match_" .. id .. ".json"]
end

-- Slayer: a fall before the first kill is -1 on the board, and to the hub a
-- score of -1 with no kills.
local slayer = report({ variant = "slayer", teamKills = {}, teams = {},
    players = { [0] = player(0, nil, -1, 0, 1) } })
eq(slayer:find('"score":-1,"kills":0', 1, true) ~= nil, true, "the penalty stays in the score")

-- Kills survive the penalty: three kills and two suicides are three kills.
local later = report({ variant = "slayer", teamKills = {}, teams = {},
    players = { [0] = player(0, nil, 1, 3, 2) } })
eq(later:find('"score":1,"kills":3', 1, true) ~= nil, true, "a suicide takes no kill away")

-- Team Slayer: a team below 0 is reported as 0.
local team = report({ variant = "team_slayer", teams = {},
    teamKills = { { player = 0, team = "Red", points = -1 }, { player = 1, team = "Blue", points = 1 } },
    players = { [0] = player(0, "Red", -1, 0, 1), [1] = player(1, "Blue", 1, 1, 0) } })
eq(team:find('"team_scores":{"red":0,"blue":1}', 1, true) ~= nil, true, "team totals never go below 0")
eq(team:find('"kills":-', 1, true), nil, "no negative kills")

io.open = realOpen
print("ok")

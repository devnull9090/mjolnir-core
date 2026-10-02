-- Run from the repository root with Lua 5.4, or Python + lupa:
-- python -c "from lupa import LuaRuntime; LuaRuntime().execute(open('tools/tests/test_multiplayer_ui.lua').read())"
local model = dofile("mods/MJOLNIRHud/Scripts/scoreboard.lua")
local function eq(actual, expected, label)
    assert(actual == expected, (label or "value") .. ": expected " .. tostring(expected) .. ", got " .. tostring(actual))
end
local function player(index, team, kills, captures, deaths)
    return { index = index, team = team, kills = kills or 0, captures = captures or 0, deaths = deaths or 0 }
end

-- CTF groups by the reported team and orders by captures, not kills.
local players = { player(7, "Blue", 20, 0), player(4, "Red", 3, 2), player(1, "Red", 9, 1), player(0, nil, 1, 0) }
local rows = model.rows(players, model.modes.ctf, { Red = 3, Blue = 0 })
eq(#rows, 7)
eq(rows[1].team, "Red"); eq(rows[1].total, 3)
eq(rows[2].player.index, 4); eq(rows[3].player.index, 1)
eq(rows[4].team, "Blue"); eq(rows[6].team, "Unassigned")
eq(rows[7].player.index, 0)
-- Both empty teams remain legible. Unknown/non-player teams are never Red.
eq(#model.rows({}, model.modes.ctf, {}), 2)
eq(model.team("None"), nil); eq(model.team("Green"), nil)
-- Full rosters and uneven teams use all sixteen slots, not eight per team.
local full = {}
for i = 0, 15 do full[i] = player(i, i == 15 and nil or "Red", i) end
full[15].team = nil
rows = model.rows(full, model.modes.team_slayer, { Red = 120 })
eq(#rows, 19); eq(rows[1].count, 15); eq(rows[2].player.index, 14)
eq(rows[17].team, "Blue"); eq(rows[19].player.index, 15)
-- FFA has no team headings. Ties use kills, fewer deaths, then stable index.
rows = model.rows({ player(2, "Red", 3, 9, 2), player(1, "Blue", 3, 0, 1), player(0, nil, 3, 0, 1) }, model.modes.slayer)
eq(#rows, 3); eq(rows[1].player.index, 0); eq(rows[2].player.index, 1)
full[14].left = true
eq(#model.rows(full, model.modes.slayer), 15)

-- Drive the real HUD through its scheduled poll and incident hook using a
-- minimal reflected game. These tests assert visible results, not local helpers.
local function runHUD(variant)
    local time, scheduled, incidentHook, held = 5, nil, nil, true
    local widgets, names, teams = {}, { "Alpha", "Bravo", "Charlie" }, {}
    local function block()
        return setmetatable({ IsValid = function() return true end,
            SetText = function(self, v) self.text = v end,
            SetVisibility = function(self, v) self.visibility = v end,
            SetBrushColor = function(self, v) self.color = v end,
            SetColorAndOpacity = function() end, SetRenderOpacity = function() end,
            SetPadding = function() end, AddToViewport = function() end },
            { __index = function(t, k) local child = block(); rawset(t, k, child); return child end })
    end
    local function biped(index)
        return { BlamGameTeam = { GetGameTeamString = function()
            return { ToString = function() return "EBlamMultiplayerTeam::" .. (teams[index] or "None") end }
        end } }
    end
    local world = { GetFullName = function() return "World /Game/Levels/Halo1/Solo/DCN/DCN.DCN" end,
        GameState = { PlayerArray = { ForEach = function(_, fn)
            for i, name in ipairs(names) do
                local ps = { BlamPlayerStateComponent = { BlamAbsolutePlayerIndex = i - 1 },
                    GetPlayerName = function() return { ToString = function() return name end } end,
                    GetPawn = function() return nil end }
                fn(i, { get = function() return ps end })
            end
        end } } }
    local pc = { IsValid = function() return true end, GetWorld = function() return world end,
        IsInputKeyDown = function() return held end,
        PlayerState = { BlamPlayerStateComponent = { BlamAbsolutePlayerIndex = 1 } } }
    local env = setmetatable({ FText = function(v) return v end, FName = function(v) return v end,
        dofile = function(path) return dofile((path:gsub("\\", "/"))) end,
        print = function() end, os = { clock = function() return time end },
        io = { open = function(path, mode)
            if path:match("running.txt$") then return { read = function() return "DCN\t" .. variant .. "\tDanger Canyon" end, close = function() end } end
            return io.open(path, mode)
        end },
        FindAllOf = function(class) return class == "PlayerController" and { pc } or {} end,
        RegisterHook = function(_, fn) incidentHook = fn end,
        NotifyOnNewObject = function() end,
        ExecuteInGameThreadWithDelay = function(_, fn) scheduled = fn end,
        StaticFindObject = function(path)
            if path:find("GameplayStatics") then return { GetPlayerController = function() return pc end } end
            if path:find("KismetSystemLibrary") then
                return { MakeSoftClassPath = function(_, p) return p end,
                    Conv_SoftClassPathToSoftClassRef = function(_, p) return p end,
                    LoadClassAsset_Blocking = function() return { IsValid = function() return true end } end }
            end
            return { Create = function() local w = block(); widgets[#widgets + 1] = w; return w end }
        end }, { __index = _G })
    assert(loadfile("mods/MJOLNIRHud/Scripts/main.lua", "t", env))()
    local function poll() time = time + 1.1; scheduled() end
    local function incident(name, cause, effect, value)
        incidentHook(nil, { get = function() return { Name = { ToString = function() return name end },
            CausePlayerAbsoluteIndex = cause, EffectPlayerAbsoluteIndex = effect, CustomValue = value,
            CauseObjectActor = cause and biped(cause), EffectObjectActor = effect and biped(effect) } end })
        poll()
    end
    poll()
    return { board = widgets[2], feed = widgets[1], teams = teams, incident = incident, poll = poll,
        hold = function(v) held = v; poll() end }
end

local ctf = runHUD("ctf")
eq(ctf.board.Name0.text, "RED TEAM  /  0")
eq(ctf.board.Name2.text, "AWAITING ASSIGNMENT  /  3")
ctf.teams[0] = "Red"; ctf.teams[1] = "Blue"
ctf.incident("player_spawn", 0, -1, 0); ctf.incident("player_spawn", 1, -1, 0)
ctf.incident("flag_scored", 1, -1, 0)
eq(ctf.board.ScoreH.text, "CAPTURES")
eq(ctf.board.Name2.text, "BLUE TEAM  /  1"); eq(ctf.board.Score2.text, "1")
eq(ctf.board.Name3.text, "Bravo"); eq(ctf.board.Marker3.text, "YOU")
eq(ctf.board.Score3.text, "1")
eq(ctf.feed.ScoreLeftValue.text, "0"); eq(ctf.feed.ScoreRightValue.text, "1")
eq(ctf.feed.ScoreRightLabel.text, "BLUE / YOU"); eq(ctf.feed.ScoreTarget.text, "3")
ctf.incident("flag_scored", -1, -1, 99) -- invalid values cannot invent Red scores
eq(ctf.board.Score0.text, "0"); eq(ctf.board.Score2.text, "1")
ctf.hold(false); eq(ctf.board.visibility, 1); eq(ctf.feed.MatchScore.visibility, 3)
ctf.incident("flag_scored", 1, -1, 0)
eq(ctf.feed.ScoreRightValue.text, "2") -- updates while the big board is closed
ctf.hold(true); eq(ctf.board.visibility, 3); eq(ctf.feed.MatchScore.visibility, 1)
eq(ctf.board.Score2.text, "2")

local slayer = runHUD("team_slayer")
slayer.incident("player_spawn", 0, -1, 0) -- team arrives after the spawn
slayer.incident("Kill", 0, 1, 0)
slayer.teams[0] = "Red"; slayer.teams[1] = "Blue"
slayer.poll()
eq(slayer.board.ScoreH.text, "SCORE"); eq(slayer.board.Score0.text, "1")
eq(slayer.board.Score1.text, "1"); eq(slayer.board.Kills1.text, "1")
slayer.teams[0] = "Blue"; slayer.incident("player_spawn", 0, -1, 0)
eq(slayer.board.Score0.text, "1") -- earned team point stays Red after a switch
slayer.incident("player_quit", 0, -1, 0)
eq(slayer.board.PlayerCount.text, "2 PLAYERS")
eq(slayer.board.Score0.text, "1") -- quitting cannot erase the team score
eq(slayer.feed.ScoreLeftValue.text, "1"); eq(slayer.feed.ScoreTarget.text, "50")

local ffa = runHUD("slayer")
ffa.incident("Kill", 2, 0, 0)
eq(ffa.board.Name0.text, "Charlie"); eq(ffa.board.Score0.text, "1")
eq(ffa.board.PlayerCount.text, "3 PLAYERS")
eq(ffa.feed.ScoreLeftLabel.text, "YOU"); eq(ffa.feed.ScoreRightLabel.text, "LEADER")
eq(ffa.feed.ScoreLeftValue.text, "0"); eq(ffa.feed.ScoreRightValue.text, "1")
ffa.incident("player_quit", 2, -1, 0)
eq(ffa.feed.ScoreRightValue.text, "0") -- departed leaders are not the active leader
ffa.incident("player_rejoined", 2, -1, 0)
eq(ffa.feed.ScoreRightValue.text, "1")
ffa.hold(false)
ffa.incident("Kill", 1, 2, 0) -- local player ties for the lead
eq(ffa.feed.ScoreLeftValue.text, "1"); eq(ffa.feed.ScoreRightValue.text, "1")
ffa.incident("Kill", 1, 2, 0) -- local player takes the lead
eq(ffa.feed.ScoreLeftValue.text, "2"); eq(ffa.feed.ScoreRightValue.text, "2")
eq(ffa.feed.ScoreTarget.text, "25")
print("Multiplayer UI: grouping, full rosters, CTF, Team Slayer, delayed teams, switching, quitting, FFA and live score strip passed")

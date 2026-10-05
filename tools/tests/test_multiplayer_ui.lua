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
local function runHUD(variant, client, variantFile, listing)
    local time, scheduled, held = 5, nil, true
    local written, commands = {}, {}
    -- Hooks by function path; the match log's files in memory, by path; what
    -- this machine asked its host over ServerExecRPC.
    local hooks, files, asked = {}, {}, {}
    local function memfile(path, mode)
        if mode:match("^r") then
            local data = files[path]
            if not data then return nil end
            return { read = function() return data end, close = function() end }
        end
        if mode:match("^w") or not files[path] then files[path] = "" end
        return { write = function(_, ...)
            for _, v in ipairs({ ... }) do files[path] = files[path] .. tostring(v) end
        end, close = function() end }
    end
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
        return { IsValid = function() return true end,
            K2_GetActorLocation = function() return { X = index * 100, Y = 1, Z = 2 } end,
            BlamGameTeam = { GetGameTeamString = function()
            return { ToString = function() return "EBlamMultiplayerTeam::" .. (teams[index] or "None") end }
        end } }
    end
    local world = { GetFullName = function() return "World /Game/Levels/Halo1/Solo/DCN/DCN.DCN" end,
        AuthorityGameMode = { IsValid = function() return not client end },
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
        ServerExecRPC = function(_, msg) asked[#asked + 1] = msg end,
        PlayerState = { BlamPlayerStateComponent = { BlamAbsolutePlayerIndex = 1 } } }
    local env
    env = setmetatable({ FText = function(v) return v end, FName = function(v) return v end,
        -- The HUD's own modules run in this environment too, as in the game.
        dofile = function(path) return assert(loadfile((path:gsub("\\", "/")), "t", env))() end,
        print = function() end, os = { clock = function() return time end, time = function() return 1000 end,
            remove = function(path) files[path] = nil end },
        io = { open = function(path, mode)
            mode = mode or "r"
            local own = path:match("MJOLNIRHud[\\/]([%w_]+%.%w+)$")
            if own and (own:match("^match_") or own:match("^claim_")) then return memfile(path, mode) end
            if path:match("MJOLNIRLobby[\\/]listing%.txt$") then
                if listing and mode:match("^r") then
                    return { read = function() return listing .. "\n" end, close = function() end }
                end
                return nil
            end
            if path:match("last_match.txt$") and mode == "w" then
                return { write = function(_, ...) for _, v in ipairs({ ... }) do written[#written + 1] = v end end,
                    close = function() end }
            end
            if path:match("variants[\\/][%w_]+%.mglo$") then
                return variantFile and io.open(variantFile, "rb") or nil
            end
            if path:match("running.txt$") then return { read = function() return "DCN\t" .. variant .. "\tDanger Canyon" end, close = function() end } end
            return io.open(path, mode)
        end },
        FindAllOf = function() return {} end,
        FindFirstOf = function(class)
            if class ~= "GameEngine" then return nil end
            return { IsValid = function() return true end,
                GameViewport = { GameInstance = { LocalPlayers = { { PlayerController = pc } } } } }
        end,
        RegisterHook = function(path, fn) hooks[path] = fn end,
        NotifyOnNewObject = function() end,
        ExecuteInGameThread = function(fn) fn() end,
        ExecuteInGameThreadWithDelay = function(_, fn) scheduled = fn end,
        StaticFindObject = function(path)
            if path:find("GameplayStatics") then return { GetPlayerController = function() return pc end } end
            if path:find("KismetSystemLibrary") then
                return { MakeSoftClassPath = function(_, p) return p end,
                    Conv_SoftClassPathToSoftClassRef = function(_, p) return p end,
                    LoadClassAsset_Blocking = function() return { IsValid = function() return true end } end,
                    ExecuteConsoleCommand = function(_, _, command) commands[#commands + 1] = command end }
            end
            return { Create = function() local w = block(); widgets[#widgets + 1] = w; return w end }
        end }, { __index = _G })
    assert(loadfile("mods/MJOLNIRHud/Scripts/main.lua", "t", env))()
    local function poll() time = time + 1.1; scheduled() end
    local function incident(name, cause, effect, value)
        local incidentHook
        for path, fn in pairs(hooks) do
            if path:find("OnIncident_Event", 1, true) then incidentHook = fn end
        end
        incidentHook(nil, { get = function() return { Name = { ToString = function() return name end },
            CausePlayerAbsoluteIndex = cause, EffectPlayerAbsoluteIndex = effect, CustomValue = value,
            -- No player, no object: as the game sends index -1.
            CauseObjectActor = cause and cause >= 0 and biped(cause) or nil,
            EffectObjectActor = effect and effect >= 0 and biped(effect) or nil } end })
        poll()
    end
    poll()
    return { board = widgets[2], feed = widgets[1], teams = teams, incident = incident, poll = poll,
        hold = function(v) held = v; poll() end,
        written = function() return table.concat(written) end, commands = commands,
        hooks = hooks, asked = asked,
        --- The match log's file whose name matches `pattern`, and its name.
        file = function(pattern)
            for path, data in pairs(files) do
                local name = path:match("([^\\/]+)$")
                if name:match(pattern) then return data, name end
            end
            return nil
        end }
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
-- The respawn countdown clears even when the final tick and the spawn never
-- reach a fireteam client.
ffa.incident("death", -1, 1, 0)
eq(ffa.feed.Respawn.text, "Respawning")
for _ = 1, 3 do ffa.incident("respawn_tick", 1, -1, 0) end
eq(ffa.feed.Respawn.text, "Respawn in 1")
for _ = 1, 3 do ffa.poll() end
eq(ffa.feed.Respawn.text, "")

-- The end of the match: the final standings on every machine, without Tab;
-- the results for the post-game screen; and, after the standings have been
-- up a while, the host's seamless travel back to the lobby.
ffa.incident("round_over", -1, -1, 0)
eq(ffa.board.visibility, 3)
eq(ffa.board.BoardLabel.text, "MULTIPLAYER  /  FINAL STANDINGS")
eq(ffa.board.Title.text, "BRAVO WINS")
eq(ffa.board.Subtitle.text, "SLAYER   /   DANGER CANYON")
eq(ffa.board.BoardHint.text, "RETURNING TO THE LOBBY")
local results = ffa.written()
assert(results:find("^match\tDCN\tslayer\tDanger Canyon\tSLAYER\tBRAVO WINS\t1000\n"), results)
assert(results:find("\nplayer\tBravo\t2\t2\t1\t%-\t1\n"), results)
ffa.incident("Kill", 2, 1, 0) -- the round the game resets behind the standings does not score
eq(ffa.board.Score0.text, "2"); eq(ffa.board.Name0.text, "Bravo")
eq(#ffa.commands, 0)
for _ = 1, 7 do ffa.poll() end
eq(#ffa.commands, 1); eq(ffa.commands[1], "servertravel /Game/Levels/UI/Frontend/Frontend")
for _ = 1, 3 do ffa.poll() end
eq(#ffa.commands, 1) -- once

-- A fireteam client shows the same standings and writes its own results,
-- but only the host travels.
local member = runHUD("ctf", true)
member.teams[0] = "Red"; member.teams[1] = "Blue"
member.incident("player_spawn", 0, -1, 0); member.incident("player_spawn", 1, -1, 0)
member.incident("flag_scored", 1, -1, 0)
member.incident("game_over", -1, -1, 0)
eq(member.board.Title.text, "BLUE TEAM WINS")
assert(member.written():find("\nteam\tBlue\t1\n"))
for _ = 1, 10 do member.poll() end
eq(#member.commands, 0)

-- The match log (docs/match_stats.md). A private match is recorded and
-- thrown away: the final standings above left nothing queued.
assert(not ffa.file("^match_outbox%.txt$"), "a private match was queued")
assert(not ffa.file("^match_current%.txt$"), "a finished match is still current")

-- A public host's match: every incident in order, with where the cause's and
-- the effect's bipeds stood, queued for MJOLNIRLobby when it ends.
local pub = runHUD("slayer", false, nil, "lobby-1")
local current = pub.file("^match_current%.txt$")
assert(current and current:match("^%x+$"), "no match being recorded")
pub.incident("player_spawn", 0, -1, 0)
pub.incident("Kill", 2, 0, 0)
pub.incident("respawn_tick", 0, -1, 0) -- the countdown is not kept
pub.incident("round_over", -1, -1, 0)
eq(pub.board.Title.text, "CHARLIE WINS") -- the HUD's own end is untouched
local outbox = pub.file("^match_outbox%.txt$")
local id = outbox and outbox:match("^match (%x+)\n$")
assert(id and #id == 32, "outbox: " .. tostring(outbox))
eq(id, current)
local record = pub.file("^match_" .. id .. "%.json$")
assert(record, "no record for " .. id)
for _, want in ipairs({
    '"host_match_id":"' .. id .. '"', '"lobby_id":"lobby-1"', '"map_code":"DCN"', '"game_type":"slayer"',
    '"team_game":false', '"score_to_win":25', '"started_at":1000', '"end_reason":"round_over"',
    '"host_index":1',
    '{"t_ms":0,"type":"player_spawn","cause":0,"effect":-1,"value":0,"cause_pos":[0.0,1.0,2.0]}',
    '"type":"kill","cause":2,"effect":0,"value":0,"cause_pos":[200.0,1.0,2.0],"effect_pos":[0.0,1.0,2.0]}',
    '"type":"round_over","cause":-1,"effect":-1,"value":0}',
    '{"index":2,"name":"Charlie","team":null,"score":1,"kills":1,"deaths":0,"suicides":0,"captures":0,"left":false}',
}) do
    assert(record:find(want, 1, true), "record lacks " .. want .. "\n" .. record)
end
assert(not record:find("respawn_tick", 1, true), "the respawn countdown was recorded")
assert(not pub.file("^match_current%.txt$"), "a finished match is still current")

-- The host answers a client's question with the client's own seat, and says
-- nothing while the asker's index is not yet its own: a joiner reads index 0
-- (the host's) for a moment after the host seats it.
local host = runHUD("slayer", false, nil, "lobby-1")
local hostId = host.file("^match_current%.txt$")
local function ask(index, name)
    local sent = {}
    local asker = { IsValid = function() return true end,
        ClientMessage = function(_, msg, kind) sent[#sent + 1] = kind .. " " .. msg end,
        PlayerState = { BlamPlayerStateComponent = { BlamAbsolutePlayerIndex = index },
            GetPlayerName = function() return { ToString = function() return name end } end } }
    host.hooks["/Script/Engine.PlayerController:ServerExecRPC"](
        { get = function() return asker end },
        { get = function() return { ToString = function() return "MJOLNIR|matchid" end } end })
    return sent
end
eq(#ask(0, "Charlie"), 0)     -- not yet seated: index 0 is someone else's
eq(#ask(1, "Bravo"), 0)       -- the host's own seat (LOCAL_PLAYER) is never handed out
eq(#ask(2, "Somebody"), 0)    -- a seat recorded under another name
eq(ask(2, "Charlie")[1], "MJOLNIR MJOLNIR|match|" .. hostId .. "|1|2|Charlie")

-- The host answers a client's question for the match id with nothing to
-- send while it records nothing; a client asks until it is told, then claims
-- the seat the host named, once.
local guest = runHUD("slayer", true)
for _ = 1, 3 do guest.poll() end
eq(guest.asked[1], "MJOLNIR|matchid")
local hexId = string.rep("ab", 16)
local function tell(text)
    guest.hooks["/Script/Engine.PlayerController:ClientMessage"](nil,
        { get = function() return { ToString = function() return text end } end },
        { get = function() return { ToString = function() return "MJOLNIR" end } end })
    guest.poll()
end
tell("MJOLNIR|match|" .. hexId .. "|0|1|Bravo") -- private: nothing to claim yet
assert(not guest.file("^claim_"), "claimed a seat in a private match")
tell("MJOLNIR|match|" .. hexId .. "|1|1|Bravo")
local claim, claimName = guest.file("^claim_")
eq(claimName, "claim_" .. hexId .. ".json")
eq(claim, '{"host_match_id":"' .. hexId .. '","player_index":1,"name":"Bravo"}')
eq(guest.file("^match_outbox%.txt$"), "claim " .. hexId .. "\n")
local askedBefore = #guest.asked
tell("MJOLNIR|match|" .. hexId .. "|1|1|Bravo")
for _ = 1, 20 do guest.poll() end
eq(guest.file("^match_outbox%.txt$"), "claim " .. hexId .. "\n") -- once
eq(#guest.asked, askedBefore) -- and no more questions
print("Multiplayer UI: the match log records public matches with positions and claims seats")

-- Winners: a shared lead, or nobody scoring, is a draw.
local function match(mode, players, teams)
    return { mode = model.modes[mode], players = players, teams = teams or { [0] = 0, [1] = 0 }, teamKills = {},
        variant = mode }
end
eq(model.winner(match("slayer", { player(0, nil, 3), player(1, nil, 3) })), "DRAW")
eq(model.winner(match("slayer", { player(0, nil, 0) })), "DRAW")
eq(model.winner(match("ctf", {}, { [0] = 2, [1] = 2 })), "DRAW")
eq(model.winner(match("ctf", {}, { [0] = 3, [1] = 1 })), "RED TEAM WINS")
print("Multiplayer UI: grouping, full rosters, CTF, Team Slayer, delayed teams, switching, quitting, FFA, live score strip, final standings and results passed")

-- The score to win comes from the variant the simulation loads, not a
-- built-in number (fixtures written by `mjolnir megalo write`).
local Variant = dofile("mods/MJOLNIRHud/Scripts/variant.lua")
local function bytes(path)
    local f = assert(io.open(path, "rb"))
    local data = f:read("a")
    f:close()
    return data
end
eq(Variant.scoreToWin(bytes("tools/tests/fixtures/slayer_7.mglo")), 7)
eq(Variant.scoreToWin(bytes("tools/tests/fixtures/ctf_2.mglo")), 2)       -- a string table of labels
eq(Variant.scoreToWin(bytes("tools/tests/fixtures/tick_450.mglo")), 450)
eq(Variant.scoreToWin("not a variant"), nil)
eq(Variant.scoreToWin(nil), nil)
local seven = runHUD("slayer", false, "tools/tests/fixtures/slayer_7.mglo")
eq(seven.feed.ScoreTarget.text, "7")
seven.hold(true)
eq(seven.board.Subtitle.text, "DANGER CANYON   /   FIRST TO 7 KILLS")
print("Multiplayer UI: the score to win comes from the variant")

-- The build line names the game update and its changelist.
local BuildLine = dofile("mods/MJOLNIRHud/Scripts/buildline.lua")
eq(BuildLine.game("5.5.4-1121610+++Meteorite+Rel-i343-Meteorite-2607-CU4"), "CU4 1121610")
eq(BuildLine.game("5.5.4-1112544+++Meteorite+Rel-i343-Meteorite-2607-CU3"), "CU3 1112544")
eq(BuildLine.game("5.5.4-1200000+++Meteorite+Main"), "1200000")
eq(BuildLine.game(nil), nil)
print("Multiplayer UI: the build line")

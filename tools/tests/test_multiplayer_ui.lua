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
local function runHUD(variant, client, variantFile, listing, identities, legacy)
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
    -- A remote player's controller on the host: what it is sent.
    local remote = { sent = {}, IsValid = function() return true end, GetAddress = function() return 4242 end,
        IsLocalController = function() return false end,
        Player = { IsValid = function() return true end }, PlayerState = { IsValid = function() return true end,
            GetPlayerName = function() return { ToString = function() return "Charlie" end } end } }
    remote.ClientMessage = function(_, msg, kind) remote.sent[#remote.sent + 1] = kind .. " " .. msg end
    local function block()
        return setmetatable({ IsValid = function() return true end,
            SetText = function(self, v) self.text = v end,
            SetVisibility = function(self, v) self.visibility = v end,
            SetBrushColor = function(self, v) self.color = v end,
            SetColorAndOpacity = function(self, v) self.tint = v end,
            SetRenderOpacity = function(self, v) self.opacity = v end,
            SetRenderTranslation = function(self, v) self.translation = v end,
            SetRenderScale = function(self, v) self.scale = v end,
            SetWidthOverride = function(self, v) self.width = v end,
            SetHeightOverride = function(self, v) self.height = v end,
            SetBrushFromTexture = function(self, tex) self.brush = tex end,
            -- The weapon's brush: the game's icon material, made dynamic.
            SetBrushFromMaterial = function(self, m)
                self.brush = m
                self.mid = { params = {},
                    SetTextureParameterValue = function(mid, k, v) mid.params[k] = v end,
                    SetScalarParameterValue = function(mid, k, v) mid.params[k] = v end }
            end,
            GetDynamicMaterial = function(self) return self.mid end,
            SetFont = function(self, f) self.font = f end,
            GetText = function(self) return { ToString = function() return self.text or "" end } end,
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
        PlayerState = { BlamPlayerStateComponent = { BlamAbsolutePlayerIndex = 1 },
            GetPlayerName = function() return { ToString = function() return "Bravo" end } end } }
    local env
    -- The chat's key binds (Scripts/chat.lua), by key name.
    local binds = {}
    -- The input modes the chat set (UI-only while typing).
    local modes = {}
    local pumps = { 0 }
    env = setmetatable({ FText = function(v) return v end, FName = function(v) return v end,
        Key = setmetatable({}, { __index = function(_, k) return k end }),
        -- MJOLNIRBlamConsole's native half: each pump counted.
        package = { loadlib = function() return function() pumps[1] = pumps[1] + 1 end end },
        RegisterKeyBind = function(key, _, fn) binds[key] = fn end,
        -- The HUD's own modules run in this environment too, as in the game.
        dofile = function(path) return assert(loadfile((path:gsub("\\", "/")), "t", env))() end,
        print = function() end, os = { clock = function() return time end, time = function() return 1000 end,
            remove = function(path) files[path] = nil end },
        io = { open = function(path, mode)
            mode = mode or "r"
            local own = path:match("MJOLNIRHud[\\/]([%w_]+%.%w+)$")
            if own and (own:match("^match_") or own:match("^claim_") or own:match("^chat_")) then
                return memfile(path, mode)
            end
            -- The Blam console's mailbox (slash commands): never the real file.
            if path:match("MJOLNIRBlamConsole[\\/]native[\\/]request%.txt$") then return memfile(path, mode) end
            if path:match("MJOLNIRLobby[\\/]listing%.txt$") then
                if listing and mode:match("^r") then
                    return { read = function() return listing .. "\n" end, close = function() end }
                end
                return nil
            end
            -- MJOLNIRLobby's roster of hub accounts (docs/player_identity.md).
            if path:match("MJOLNIRLobby[\\/]identities%.txt$") then
                if identities and mode:match("^r") then
                    return { read = function() return identities end, close = function() end }
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
            -- A hub avatar MJOLNIRLobby has cached (docs/player_identity.md).
            if path:match("av_[%w%-]+%.png$") and mode:match("^r") then
                return { read = function() return "png" end, close = function() end }
            end
            if path:match("running.txt$") then return { read = function() return "DCN\t" .. variant .. "\tDanger Canyon" end, close = function() end } end
            return io.open(path, mode)
        end },
        FindAllOf = function(class) return class == "PlayerController" and { remote } or {} end,
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
            -- The feed's pictures: our glyphs, the game's silhouettes and
            -- icon material, its fonts.
            if path:find("^/Game/MJOLNIR/UI/Icons/") or path:find("^/Game/UI/Hud/") or path:find("^/Game/Fonts/") then
                return { IsValid = function() return true end, path = path,
                    Blueprint_GetSizeX = function() return 312 end, Blueprint_GetSizeY = function() return 112 end }
            end
            if path:find("KismetRenderingLibrary") then
                return { IsValid = function() return true end,
                    ImportFileAsTexture2D = function(_, _, file)
                        return { IsValid = function() return true end, file = file,
                            GetFullName = function() return "Texture2D /Engine/Transient." .. file:match("(av_[%w%-]+)%.png$") end }
                    end }
            end
            if path:find("KismetSystemLibrary") then
                return { MakeSoftClassPath = function(_, p) return p end,
                    Conv_SoftClassPathToSoftClassRef = function(_, p) return p end,
                    LoadClassAsset_Blocking = function() return { IsValid = function() return true end } end,
                    ExecuteConsoleCommand = function(_, _, command) commands[#commands + 1] = command end }
            end
            return { SetInputMode_UIOnlyEx = function(_, _, focus) modes[#modes + 1] = focus and "ui" or "ui-nofocus" end,
                SetInputMode_GameOnly = function() modes[#modes + 1] = "game" end,
                Create = function()
                local w = block()
                -- A UI container from before the feed's rows has none.
                if legacy and #widgets == 0 then rawset(w, "FeedEdge0", { IsValid = function() return false end }) end
                widgets[#widgets + 1] = w
                return w
            end }
        end }, { __index = _G })
    assert(loadfile("mods/MJOLNIRHud/Scripts/main.lua", "t", env))()
    local function poll() time = time + 1.1; scheduled() end
    --- Raises an incident without polling; `damage` = { modifier, damage tag }.
    local function raise(name, cause, effect, value, damage)
        local incidentHook
        for path, fn in pairs(hooks) do
            if path:find("OnIncident_Event", 1, true) then incidentHook = fn end
        end
        damage = damage or {}
        incidentHook(nil, { get = function() return { Name = { ToString = function() return name end },
            CausePlayerAbsoluteIndex = cause, EffectPlayerAbsoluteIndex = effect, CustomValue = value,
            DamageReportingInfo = { Modifier = damage.modifier,
                Type = { TagName = { ToString = function() return damage.damage or "Blam.DamageReporting.Type.Invalid" end } } },
            -- No player, no object: as the game sends index -1.
            CauseObjectActor = cause and cause >= 0 and biped(cause) or nil,
            EffectObjectActor = effect and effect >= 0 and biped(effect) or nil } end })
    end
    local function incident(name, cause, effect, value, damage)
        raise(name, cause, effect, value, damage)
        poll()
    end
    --- Several incidents in one tick, as the game raises a kill's medals.
    local function burst(list)
        for _, i in ipairs(list) do raise(i[1], i[2], i[3], i[4], i[5]) end
        poll()
    end
    poll()
    return { board = widgets[2], feed = widgets[1], teams = teams, incident = incident, poll = poll, burst = burst,
        -- Time passes without a poll (the per-frame animation's view).
        wait = function(seconds) time = time + seconds end,
        hold = function(v) held = v; poll() end,
        written = function() return table.concat(written) end, commands = commands,
        hooks = hooks, asked = asked, remote = remote, binds = binds, widgets = widgets, modes = modes, pumps = pumps,
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
eq(ffa.feed.RespawnBox.visibility, 3)
eq(ffa.feed.RespawnLabel.text, "RESPAWNING"); eq(ffa.feed.Respawn.text, "")
for _ = 1, 3 do ffa.incident("respawn_tick", 1, -1, 0) end
eq(ffa.feed.RespawnLabel.text, "RESPAWN IN"); eq(ffa.feed.Respawn.text, "1")
for _ = 1, 3 do ffa.poll() end
eq(ffa.feed.RespawnBox.visibility, 1)

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
assert(results:find("^match\tDCN\tslayer\tDanger Canyon\tSLAYER\tBRAVO WINS\t1000\t%x+\n"), results)
assert(results:find("\nplayer\tBravo\t2\t2\t1\t%-\t1\t%-\t%-\t0\n"), results)
ffa.incident("Kill", 2, 1, 0) -- the round the game resets behind the standings does not score
eq(ffa.board.Score0.text, "2"); eq(ffa.board.Name0.text, "Bravo")
eq(#ffa.commands, 0)
for _ = 1, 7 do ffa.poll() end
eq(#ffa.commands, 1); eq(ffa.commands[1], "servertravel /Game/Levels/UI/Frontend/Frontend")
for _ = 1, 3 do ffa.poll() end
eq(#ffa.commands, 1) -- once

-- Hub accounts (docs/player_identity.md): MJOLNIRLobby's roster puts the
-- hub name in place of the in-game one on the board and in the winner, and
-- the results carry the account for the post-game screen's reports.
local hub = runHUD("slayer", false, nil, nil, "Bravo\t0000-b\tbravo_hub\t3\nCharlie\t0000-c\tCharlie Hub\t0\n")
hub.incident("Kill", 2, 0, 0)
eq(hub.board.Name0.text, "Charlie Hub")
hub.incident("Kill", 1, 2, 0); hub.incident("Kill", 1, 2, 0)
eq(hub.board.Name0.text, "bravo_hub")
hub.incident("round_over", -1, -1, 0)
eq(hub.board.Title.text, "BRAVO_HUB WINS")
local hubResults = hub.written()
-- A joiner's "joined" line names its hub account: at once when the account
-- is known, otherwise after a short wait for it, under the in-game name.
--- The feed row (0..6) showing `lead` ... `tail`, if one is up.
local function feedRow(h, lead, tail)
    for i = 0, 6 do
        local f = h.feed
        if f["FeedEdge" .. i].visibility == 3 and f["FeedLead" .. i].text == lead
            and (tail == nil or f["FeedTail" .. i].text == tail) then
            return i
        end
    end
    return nil
end
local function feedHas(h, lead, tail) return feedRow(h, lead, tail) ~= nil end
local joins = runHUD("slayer", false, nil, nil, "Charlie\t0000-c\tCharlie Hub\t0\n")
joins.incident("player_joined", 2, -1, 0); joins.poll()
assert(feedHas(joins, "Charlie Hub", "joined the game"), "a known account joins at once")
joins.incident("player_joined", 0, -1, 0); joins.poll()
assert(not feedHas(joins, "Alpha", "joined the game"), "an unknown account waits")
for _ = 1, 8 do joins.poll() end
assert(feedHas(joins, "Alpha", "joined the game"), "then joins under its in-game name")
local joined = feedRow(joins, "Alpha", "joined the game")
assert(joins.feed["FeedGlyph" .. joined].brush.path:find("T_MJHud_Joined", 1, true), "the joined glyph")
assert(hubResults:find("\nplayer\tBravo\t2\t2\t0\t%-\t1\t0000%-b\tbravo_hub\t3\n"), hubResults)
assert(hubResults:find("\nplayer\tAlpha\t0\t0\t0\t%-\t0\t%-\t%-\t0\n"), hubResults)

-- The kill feed's rows (Scripts/feed.lua, docs/multiplayer_hud.md). The local
-- player here is Bravo (index 1).
local DT = "Blam.DamageReporting.Type."
local kills = runHUD("slayer")
kills.incident("Kill", 2, 0, 0, { modifier = 1, damage = DT .. "SniperRifle" })
local r = feedRow(kills, "Charlie", "Alpha")
assert(r, "a kill line names the killer and the victim")
local f = kills.feed
-- The game's own silhouette, through the game's icon material, facing the victim.
assert(f["FeedWeapon" .. r].brush.path:find("MI_HUDCradleIcon", 1, true), "the game's icon material")
assert(f["FeedWeapon" .. r].mid.params.InputTexture.path:find("T_UI_SniperRifle_WeaponIcon", 1, true))
eq(f["FeedWeapon" .. r].scale.X, -1)
eq(f["FeedWeapon" .. r .. "Box"].visibility, 3); eq(f["FeedWeapon" .. r .. "Box"].width, 28 * 312 / 112)
assert(f["FeedMod" .. r].brush.path:find("T_MJHud_Headshot", 1, true), "a headshot glyph")
eq(f["FeedMod" .. r .. "Box"].visibility, 3)
eq(f["FeedEdge" .. r].color.A, 0) -- no rim: the line does not name the local player
-- A melee kill by the local player: our glyph in the weapon's place, no
-- modifier, and the gold rim.
kills.incident("Kill", 1, 2, 0, { modifier = 0, damage = DT .. "Melee" })
r = feedRow(kills, "Bravo", "Charlie")
assert(f["FeedWeapon" .. r].brush.path:find("T_MJHud_Melee", 1, true), "the melee glyph")
eq(f["FeedWeapon" .. r].scale.X, 1)
eq(f["FeedMod" .. r .. "Box"].visibility, 1)
assert(f["FeedEdge" .. r].color.A > 0.5, "the local player's line has a rim")
-- A weapon the game has no silhouette for is named instead.
kills.incident("Kill", 0, 2, 0, { damage = DT .. "FlameThrower" })
r = feedRow(kills, "Alpha", "Charlie")
eq(f["FeedNote" .. r].text, "Flame Thrower"); eq(f["FeedNote" .. r].visibility, 3)
-- Newest at the bottom: every row is stacked by its translation, once the
-- older ones have risen.
kills.poll()
eq(f["FeedEdge" .. r].translation.Y, 0)
eq(f["FeedEdge" .. feedRow(kills, "Bravo", "Charlie")].translation.Y, -48)
eq(f["FeedEdge" .. feedRow(kills, "Charlie", "Alpha")].translation.Y, -96)
-- A medal arrives before the kill that earned it, in the same tick; the feed
-- lists it after the kill, and the local player's comes up in the middle.
kills.burst({ { "multikill_x2", 1, -1, 0 }, { "Kill", 1, 0, 0, { damage = DT .. "AssaultRifle" } } })
local medalRow, killRow = feedRow(kills, "Bravo", "Double Kill"), feedRow(kills, "Bravo", "Alpha")
assert(medalRow and killRow, "the medal and the kill")
eq(f.Callout.visibility, 3); eq(f.CalloutTitle.text, "DOUBLE KILL")
kills.poll()
eq(f["FeedEdge" .. medalRow].translation.Y, 0); eq(f["FeedEdge" .. killRow].translation.Y, -48)
for _ = 1, 2 do kills.poll() end
eq(f.Callout.visibility, 1)
-- Lines leave after six seconds; past six on screen, the oldest goes at once.
for _ = 1, 6 do kills.poll() end
for i = 0, 6 do assert(f["FeedEdge" .. i].visibility ~= 3, "row " .. i .. " after its time") end
local many = {}
for _ = 1, 8 do many[#many + 1] = { "Kill", 0, 2, 0, { damage = DT .. "Shotgun" } } end
kills.burst(many)
kills.poll() -- the oldest pushed out has finished leaving
local shown = 0
for i = 0, 6 do if f["FeedEdge" .. i].visibility == 3 then shown = shown + 1 end end
eq(shown, 6)
-- The score bar fills toward the score to win (25): Bravo, the local
-- player, has 2 kills.
eq(f.ScoreLeftValue.text, "2")
assert(math.abs(f.ScoreLeftFill.width - 320 * 2 / 25) < 1e-6, "the bar: " .. tostring(f.ScoreLeftFill.width))
-- Deaths with no killer say what killed them.
kills.incident("death", -1, 2, 0, { damage = DT .. "FallingDamage" })
kills.poll()
r = feedRow(kills, "Charlie", "fell to their death")
assert(r and f["FeedGlyph" .. r].brush.path:find("T_MJHud_Fall", 1, true), "a fall")
print("Multiplayer UI: the kill feed's rows, glyphs, medals, callouts and score bars")

-- Hub avatars beside the names, as on the scoreboard: Charlie has a hub
-- account with a cached picture, Alpha none.
local faces = runHUD("slayer", false, nil, nil, "Charlie\t0000-c\tCharlie Hub\t0\n")
faces.incident("Kill", 2, 0, 0, { damage = DT .. "Shotgun" })
r = feedRow(faces, "Charlie Hub", "Alpha")
eq(faces.feed["FeedLeadAvatar" .. r .. "Box"].visibility, 3)
assert(faces.feed["FeedLeadAvatar" .. r].brush.file:find("av_0000%-c%.png$"), "Charlie's avatar")
eq(faces.feed["FeedTailAvatar" .. r .. "Box"].visibility, 1) -- Alpha has none
print("Multiplayer UI: hub avatars in the feed")

-- Fireteam clients (Scripts/relay.lua): the host sends the feed's incidents
-- to every remote player, one message per drain.
local Relay = dofile("mods/MJOLNIRHud/Scripts/relay.lua")
local wire = Relay.encode({ { name = "kill", cause = 2, effect = 0, value = 0, modifier = 1, damage = DT .. "SniperRifle" },
    { name = "respawn_tick", cause = 0 }, { name = "multikill_x2", cause = 2, effect = -1, value = 0 } })
eq(wire, "MJOLNIR|feed|kill,2,0,0,1,SniperRifle;multikill_x2,2,-1,0,0,")
local back = Relay.decode(wire, 7)
eq(#back, 2); eq(back[1].name, "kill"); eq(back[1].damage, "SniperRifle"); eq(back[1].modifier, 1)
eq(back[2].damage, nil); eq(back[2].relayed, true)
eq(Relay.decode("MJOLNIR|clock|30.0", 7), nil)
-- One incident from two sources is taken once; two from one source are two.
local recent = {}
eq(Relay.seen(recent, { name = "kill", cause = 2, effect = 0, at = 10 }), false)
eq(Relay.seen(recent, { name = "kill", cause = 2, effect = 0, at = 10.6, relayed = true }), true)
eq(Relay.seen(recent, { name = "kill", cause = 2, effect = 0, at = 11 }), false)
eq(Relay.seen(recent, { name = "kill", cause = 2, effect = 0, at = 11.2 }), false)
eq(Relay.seen(recent, { name = "kill", cause = 2, effect = 0, at = 20, relayed = true }), false)
-- The host sends a kill, with what killed, to its fireteam.
local relayHost = runHUD("slayer")
for _ = 1, 3 do relayHost.poll() end -- the host finds its fireteam a few seconds in
relayHost.incident("Kill", 2, 0, 0, { modifier = 1, damage = DT .. "SniperRifle" })
local sent = relayHost.remote.sent[#relayHost.remote.sent]
assert(sent and sent:find("^MJOLNIR MJOLNIR|feed|kill,2,0,0,1,SniperRifle"), "the host's relay: " .. tostring(sent))
-- A client draws the line and counts the kill from the host's message alone,
-- and takes a kill it also had from its own handler once.
local function hear(h, text)
    h.hooks["/Script/Engine.PlayerController:ClientMessage"](nil,
        { get = function() return { ToString = function() return text end } end },
        { get = function() return { ToString = function() return "MJOLNIR" end } end })
    h.poll()
end
local joiner = runHUD("slayer", true)
hear(joiner, "MJOLNIR|feed|kill,2,0,0,1,SniperRifle;death,2,0,0,0,SniperRifle")
r = feedRow(joiner, "Charlie", "Alpha")
assert(r, "the relayed kill line")
assert(joiner.feed["FeedMod" .. r].brush.path:find("T_MJHud_Headshot", 1, true), "the relayed headshot")
eq(joiner.board.Name0.text, "Charlie"); eq(joiner.board.Kills0.text, "1")
joiner.burst({ { "Kill", 0, 2, 0 } })
hear(joiner, "MJOLNIR|feed|kill,0,2,0,0,")
local alphaKills = 0
for i = 0, 2 do if joiner.board["Name" .. i].text == "Alpha" then alphaKills = joiner.board["Kills" .. i].text end end
eq(alphaKills, "1") -- once, not twice
-- The host never takes its own relay back.
hear(relayHost, "MJOLNIR|feed|kill,2,0,0,0,")
local charlieKills = 0
for i = 0, 2 do if relayHost.board["Name" .. i].text == "Charlie" then charlieKills = relayHost.board["Kills" .. i].text end end
eq(charlieKills, "1")
print("Multiplayer UI: the feed's relay to fireteam clients")

-- An older UI container (no feed rows): the lines go to its six text lines,
-- newest at the bottom, and the respawn countdown is one line again.
local old = runHUD("slayer", false, nil, nil, nil, true)
old.incident("Kill", 2, 0, 0, { modifier = 1, damage = DT .. "SniperRifle" })
eq(old.feed.Line5.text, "Charlie  [Sniper Rifle]  Alpha")
old.incident("player_quit", 0, -1, 0)
eq(old.feed.Line5.text, "Alpha left the game"); eq(old.feed.Line4.text, "Charlie  [Sniper Rifle]  Alpha")
old.incident("death", -1, 1, 0)
eq(old.feed.Respawn.text, "Respawning")
old.incident("respawn_tick", 1, -1, 0)
eq(old.feed.Respawn.text, "Respawn in 3")
print("Multiplayer UI: an older UI container gets a text feed")

-- The feed's model on its own: poses are a function of the time.
local Rows = dofile("mods/MJOLNIRHud/Scripts/feed.lua")
local state = Rows.new()
local a = Rows.push(state, { lead = "A" }, 10)
local x, y, alpha = Rows.pose(a, 10)
eq(alpha, 0); eq(x, -44); eq(y, 0)
x, y, alpha = Rows.pose(a, 10 + Rows.ENTER)
eq(alpha, 1); eq(x, 0)
local b = Rows.push(state, { lead = "B" }, 11)
eq(a.slot, 1); eq(b.slot, 0)
_, y = Rows.pose(a, 11); eq(y, 0)                        -- it starts where it was
_, y = Rows.pose(a, 11 + Rows.MOVE); eq(y, -Rows.STEP)   -- and rises a row
assert(Rows.busy(state, 11.1))
Rows.step(state, 10 + Rows.HOLD + Rows.EXIT)
eq(#state.entries, 1); eq(b.slot, 0)
state.hide, b.fresh = {}, false -- as Rows.draw leaves them
assert(not Rows.busy(state, 13))
local Icons = dofile("mods/MJOLNIRHud/Scripts/hudicons.lua")
eq(Icons.forKill(DT .. "PlasmaGrenade", 4).mod, "Stuck")
eq(Icons.forKill(DT .. "Ghost", 3).mod, "Splatter")
eq(Icons.forKill(DT .. "WarthogDriver", 3).glyph, "Splatter"); eq(Icons.forKill(DT .. "WarthogDriver", 3).mod, nil)
eq(Icons.forKill(DT .. "MagnumPistol", 2).glyph, "Assassination")
eq(Icons.forKill(DT .. "Invalid", nil).glyph, "Skull")
print("Multiplayer UI: the feed's model and icon choices")

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

-- Match chat (Scripts/chat.lua): the wire, the host's relay and record, and
-- a client's send.
local Chat = dofile("mods/MJOLNIRHud/Scripts/chat.lua")
eq(Chat.clean("  hi|there\n  you "), "hi/there you")
eq(Chat.clean(nil), "")
local accents = Chat.clean(string.rep("\195\169", 100)) -- 200 bytes of é
eq(#accents, 160); assert(accents:match("^[\195\169]+$") and #accents % 2 == 0, "cut on a character")
local cut = Chat.clean(string.rep("a", 159) .. "\195\169")
eq(#cut, 159) -- the half character goes
local ch, said = Chat.decodeSay(Chat.encodeSay("team", "gg"))
eq(ch, "team"); eq(said, "gg")
eq(Chat.decodeSay("MJOLNIR|say|a|   "), nil)
eq(Chat.decodeSay("MJOLNIR|matchid"), nil)
local line = Chat.decodeLine(Chat.encodeLine({ channel = "team", team = "Red", index = 2, name = "Char|lie", text = "go a|b" }))
eq(line.channel, "team"); eq(line.team, "Red"); eq(line.index, 2); eq(line.name, "Char/lie"); eq(line.text, "go a/b")
line = Chat.decodeLine(Chat.encodeLine({ channel = "all", index = -1, name = "", text = "note" }))
eq(line.team, nil); eq(line.index, nil); eq(line.name, "")
local seen = {}
for i = 1, 5 do eq(Chat.allow(seen, "x", i * 0.1), true) end
eq(Chat.allow(seen, "x", 0.6), false)
eq(Chat.allow(seen, "y", 0.6), true)
eq(Chat.allow(seen, "x", 7), true)
eq(Chat.encodeRecord("ab12", "BGL", 100, { { t_ms = 1500.4, index = 2, name = "C\"x", channel = "team", text = "hi", teamName = "red" } }),
    '{"host_match_id":"ab12","map_code":"BGL","started_at":100,"lines":[{"t_ms":1500,"index":2,"name":"C\\"x",'
    .. '"user_id":null,"display":null,"team":"red","channel":"team","text":"hi"}]}')

local function say(h, pc, text)
    h.hooks["/Script/Engine.PlayerController:ServerExecRPC"](
        { get = function() return pc end },
        { get = function() return { ToString = function() return text end } end })
end
--- The first T shows the chat rules; Enter agrees and opens the box the
--- player asked for, as `open` (a key bind) would have.
local function agreeFirst(h, open)
    open()
    local w = h.widgets[3]
    eq(w.ChatRules.visibility, 0)
    eq(w.ChatInputBar.visibility == 4, false) -- no box before agreeing
    h.wait(0.3)
    h.binds.RETURN()
    eq(w.ChatRules.visibility, 1)
    h.wait(0.3)
end
local function chatWidget(h)
    for _, w in ipairs(h.widgets) do if rawget(w, "ChatLine0") or rawget(w, "ChatInput") then return w end end
    return h.widgets[3]
end
-- The host (Bravo) relays a client's all chat to everyone and shows it, and
-- keeps it under the match's id.
local chatHost = runHUD("team_slayer", false, nil, "lobby-1", "Charlie\t0000-c\tCharlie Hub\t0\n")
chatHost.teams[1] = "Red"; chatHost.teams[2] = "Blue"
chatHost.incident("player_spawn", 1, -1, 0); chatHost.incident("player_spawn", 2, -1, 0)
for _ = 1, 4 do chatHost.poll() end
local before = #chatHost.remote.sent
say(chatHost, chatHost.remote, "MJOLNIR|say|a|hello  there")
chatHost.poll()
eq(chatHost.remote.sent[before + 1], "MJOLNIR MJOLNIR|chat|a|Blue|2|Charlie Hub|hello there")
local cw = chatWidget(chatHost)
eq(cw.ChatText9.text, "hello there"); eq(cw.ChatName9.text, "Charlie Hub:")
eq(cw.ChatLine9.visibility, 3)
-- The sender's hub avatar, as the feed draws it.
assert(cw.ChatAvatar9.brush and cw.ChatAvatar9.brush.file:find("av_0000%-c%.png$"), "the chat line's avatar")
eq(cw.ChatAvatar9Box.visibility, 3)
-- Team chat goes to the sender's team only: the host is Red.
say(chatHost, chatHost.remote, "MJOLNIR|say|t|blue only")
chatHost.poll()
eq(chatHost.remote.sent[#chatHost.remote.sent], "MJOLNIR MJOLNIR|chat|t|Blue|2|Charlie Hub|blue only")
eq(cw.ChatText9.text, "hello there")
-- Flooding: the sixth line in a few seconds is dropped, and the sender told.
for i = 1, 4 do say(chatHost, chatHost.remote, "MJOLNIR|say|a|spam " .. i) end
chatHost.poll()
local told = chatHost.remote.sent[#chatHost.remote.sent]
assert(told:find("slow down", 1, true), told)
for _ = 1, 6 do chatHost.poll() end
local chatId = chatHost.file("^match_current%.txt$")
local record = chatHost.file("^chat_" .. chatId .. "%.json$")
assert(record, "the host's chat record")
assert(record:find('"name":"Charlie","user_id":"0000-c","display":"Charlie Hub","team":"blue","channel":"all","text":"hello there"', 1, true), record)
assert(record:find('"channel":"team","text":"blue only"', 1, true), record)
assert(not record:find("spam 4", 1, true), "a dropped line was recorded")
-- The host's own line goes straight out, without the RPC. The first time,
-- the rules come first: Esc is "not now" and chat stays shut; Enter agrees,
-- once, remembered beside the mod.
chatHost.binds.T()
eq(cw.ChatRules.visibility, 0)
assert(cw.ChatRulesBody.text:find("recorded and logged to your player account", 1, true), cw.ChatRulesBody.text)
chatHost.wait(0.3)
chatHost.binds.ESCAPE()
eq(cw.ChatRules.visibility, 1); eq(chatHost.modes[#chatHost.modes], "game")
assert(not chatHost.file("^chat_rules%.txt$"), "declining was remembered")
chatHost.wait(0.3)
agreeFirst(chatHost, chatHost.binds.T)
eq(chatHost.file("^chat_rules%.txt$"), "1\n")
eq(cw.ChatInputBar.visibility, 4); eq(cw.ChatChannel.text, "ALL")
cw.ChatInput.text = "from the host"
chatHost.binds.RETURN()
eq(cw.ChatInputBar.visibility, 1)
eq(chatHost.remote.sent[#chatHost.remote.sent], "MJOLNIR MJOLNIR|chat|a|Red|1|Bravo|from the host")
print("Multiplayer UI: chat relayed, filtered by team, limited and recorded by the host")

-- A client sends over ServerExecRPC and draws what the host relays.
local chatClient = runHUD("slayer", true)
for _ = 1, 3 do chatClient.poll() end
agreeFirst(chatClient, chatClient.binds.Y) -- team chat in free for all is all chat
local ccw = chatWidget(chatClient)
eq(ccw.ChatChannel.text, "ALL")
eq(chatClient.modes[#chatClient.modes], "ui") -- the viewport ignores keys while typing
chatClient.binds.T() -- already open: nothing
ccw.ChatInput.text = "  hi all  "
chatClient.binds.RETURN()
eq(chatClient.asked[#chatClient.asked], "MJOLNIR|say|a|hi all")
eq(chatClient.modes[#chatClient.modes], "game")
chatClient.binds.RETURN() -- closed: nothing more
eq(chatClient.asked[#chatClient.asked], "MJOLNIR|say|a|hi all")
hear(chatClient, "MJOLNIR|chat|a|-|2|Charlie|hey")
eq(ccw.ChatText9.text, "hey"); eq(ccw.ChatName9.text, "Charlie:")
assert(not chatClient.file("^chat_%x+%.json$"), "a client recorded chat")
print("Multiplayer UI: a client's chat")

-- Slash commands (Scripts/commands.lua).
local Commands = dofile("mods/MJOLNIRHud/Scripts/commands.lua")
local cname, crest = Commands.parse("  /Kick  bob smith ")
eq(cname, "kick"); eq(crest, "bob smith")
eq(Commands.parse("hello /kick"), nil)
local function labels(list)
    local out = {}
    for _, i in ipairs(list) do out[#out + 1] = i.label end
    return table.concat(out, ",")
end
eq(labels(Commands.suggest("/", false)), "/help,/players,/suicide")
eq(labels(Commands.suggest("/k", true)), "/kick <player>")
eq(Commands.suggest("/k", true)[1].complete, "/kick ")
eq(labels(Commands.suggest("/k", false)), "") -- host commands are not offered to clients
eq(labels(Commands.suggest("/kick ch", true, { "Alpha", "Charlie Hub" })), "Charlie Hub")
eq(Commands.suggest("/kick ch", true, { "Alpha", "Charlie Hub" })[1].complete, "/kick Charlie Hub")
local roster = { { index = 0, name = "Alpha" }, { index = 1, name = "Bob" }, { index = 2, name = "Bobby" },
    { index = 3, name = "x9", display = "Charlie Hub" } }
eq(Commands.resolve(roster, "bob").index, 1)       -- exact beats a longer name
eq(Commands.resolve(roster, "char").index, 3)      -- the hub name counts
eq(Commands.resolve(roster, "X9").index, 3)        -- and the in-game one
local none, why = Commands.resolve(roster, "b")
eq(none, nil); assert(why:find("Bob, Bobby", 1, true), why)
local function runAs(who, text)
    local said = { kicked = {}, blam = {} }
    local cx = { isHost = who.here, players = function() return roster end,
        kick = function(n, ban) said.kicked[#said.kicked + 1] = (ban and "ban " or "kick ") .. n end,
        unban = function(n) said.unbanned = n end,
        blam = function(line) said.blam[#said.blam + 1] = line end }
    said.answer = table.concat(Commands.run(cx, who, text), " | ")
    return said
end
local r = runAs({ here = true, index = 0 }, "/kick bob")
eq(r.kicked[1], "kick Bob"); eq(r.answer, "Kicked Bob.")
eq(runAs({ here = true, index = 0 }, "/ban char").kicked[1], "ban x9")
eq(runAs({ here = false, index = 2 }, "/kick bob").answer, "/kick is for the host.") -- never from a client
eq(#runAs({ here = false, index = 2 }, "/kick bob").kicked, 0)
eq(runAs({ here = true, index = 1 }, "/kick bob").answer, "You can't kick yourself.")
eq(runAs({ here = false, index = 2 }, "/suicide").blam[1], "(unit_kill (player_get 2))")
eq(runAs({ here = false }, "/suicide").answer, "You are not seated yet. Try again in a few seconds.")
eq(#runAs({ here = false }, "/suicide").blam, 0)
eq(runAs({ here = true, index = 0 }, "/slay bobby").blam[1], "(unit_kill (player_get 2))")
local tp = runAs({ here = true, index = 0 }, "/tp bobby")
eq(tp.blam[1], '(objects_attach (player_get 2) "" (player_get 0) "")')
eq(tp.blam[2], "(objects_detach (player_get 2) (player_get 0))")
eq(runAs({ here = true, index = 0 }, "/bring bobby").blam[1], '(objects_attach (player_get 0) "" (player_get 2) "")')
assert(runAs({ here = true, index = 0 }, "/nope").answer:find("Unknown command /nope", 1, true))
assert(runAs({ here = false, index = 2 }, "/help").answer:find("/suicide", 1, true))
assert(not runAs({ here = false, index = 2 }, "/help").answer:find("/kick", 1, true))
print("Multiplayer UI: slash commands parse, suggest, resolve players and keep host commands to the host")

-- In a match: the host's own /kick reaches the Lobby; a client's /suicide
-- goes to the host, which kills that client's seat through the Blam mailbox.
local cmdHost = runHUD("slayer", false, nil, "lobby-1")
for _ = 1, 4 do cmdHost.poll() end
local hw = chatWidget(cmdHost)
agreeFirst(cmdHost, cmdHost.binds.T)
hw.ChatInput.text = "/k"
cmdHost.poll()
eq(hw.ChatSugName0.text, "/kick <player>"); eq(hw.ChatSuggest.visibility, 4)
cmdHost.binds.TAB()
eq(hw.ChatInput.text, "/kick ")
cmdHost.poll()
cmdHost.wait(0.3)
cmdHost.binds.TAB()
eq(hw.ChatInput.text, "/kick Alpha")
cmdHost.wait(0.3) -- past the binds' double-fire guard
cmdHost.binds.TAB() -- the next player
eq(hw.ChatInput.text, "/kick Charlie")
cmdHost.binds.RETURN()
eq(cmdHost.commands[#cmdHost.commands], "mjolnir_auto kick Charlie")
eq(hw.ChatSuggest.visibility, 1)
assert(not cmdHost.remote.sent[#cmdHost.remote.sent] or not cmdHost.remote.sent[#cmdHost.remote.sent]:find("/kick", 1, true),
    "a command was relayed as chat")
cmdHost.poll()
eq(hw.ChatText9.text, "Kicked Charlie.")
-- The remote controller is Charlie, index 2 in the mock's roster.
cmdHost.remote.PlayerState.BlamPlayerStateComponent = { BlamAbsolutePlayerIndex = 2 }
local pumpsBefore = cmdHost.pumps[1]
say(cmdHost, cmdHost.remote, "MJOLNIR|cmd|/suicide")
cmdHost.poll()
eq(cmdHost.file("^request%.txt$"):match("\n(.*)\n$"), "(unit_kill (player_get 2))")
assert(cmdHost.pumps[1] > pumpsBefore, "the mailbox was not pumped")
-- A client that still reads the host's seat is told to wait, and nobody dies.
cmdHost.remote.PlayerState.BlamPlayerStateComponent = { BlamAbsolutePlayerIndex = 1 }
local sentBefore = #cmdHost.remote.sent
say(cmdHost, cmdHost.remote, "MJOLNIR|cmd|/suicide")
cmdHost.poll()
assert(cmdHost.remote.sent[sentBefore + 1]:find("not seated yet", 1, true), tostring(cmdHost.remote.sent[sentBefore + 1]))
-- A client's host command is refused.
say(cmdHost, cmdHost.remote, "MJOLNIR|cmd|/kick Bravo")
cmdHost.poll()
assert(cmdHost.remote.sent[#cmdHost.remote.sent]:find("is for the host", 1, true))
eq(cmdHost.commands[#cmdHost.commands], "mjolnir_auto kick Charlie")

local cmdClient = runHUD("slayer", true)
for _ = 1, 3 do cmdClient.poll() end
local cw2 = chatWidget(cmdClient)
agreeFirst(cmdClient, cmdClient.binds.T)
cw2.ChatInput.text = "/suicide"
cmdClient.binds.RETURN()
eq(cmdClient.asked[#cmdClient.asked], "MJOLNIR|cmd|/suicide")
cmdClient.wait(0.3)
cmdClient.binds.T()
cw2.ChatInput.text = "/kick Alpha"
cmdClient.wait(0.3)
cmdClient.binds.RETURN()
eq(cmdClient.asked[#cmdClient.asked], "MJOLNIR|cmd|/suicide") -- not sent: host only
cmdClient.poll()
eq(cw2.ChatText9.text, "/kick is for the host.")
print("Multiplayer UI: slash commands in a match, on the host and a client")

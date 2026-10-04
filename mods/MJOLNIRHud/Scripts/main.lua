-- MJOLNIR HUD
--
-- The multiplayer HUD for the classic CE maps MJOLNIRLevelLoader runs under
-- the simulation's Megalo engine: a kill feed, the respawn countdown, a
-- persistent match score, a scoreboard while Tab (or the gamepad's View
-- button) is held, and name tags
-- over teammates only (none in free for all).
--
-- The widgets are MJOLNIR's own, cooked into pakchunk984-MJOLNIRUI
-- (unreal/MJOLNIRMaterials/Scripts/build_mjolnir_ui.py, docs/custom_ui.md):
-- layout only, filled from here.
--
-- Everything comes from the simulation's incidents, which reach the game
-- state's incident handler with the cause and effect players' absolute
-- indices (docs/multiplayer_hud.md): `Kill`, `suicide` and `death` for the
-- feed and the tallies, `respawn_tick` for the countdown, `flag_scored` for
-- Capture the Flag. Scores follow the variants MJOLNIR writes
-- (crates/blam-megalo): Slayer gives a point per kill of another player,
-- CTF a point to the team per capture. The hook only queues; the work runs
-- in this mod's own game-thread poll, as the loader's event sounds do.
--
-- On the host of a public game the same incidents, with where the players
-- stood, become the match's record for the hub (Scripts/matchlog.lua,
-- docs/match_stats.md).

local function modDirectory()
    local source = debug.getinfo(1, "S").source or ""
    local root = source:gsub("^@", ""):gsub("/", "\\")
    for _ = 1, 2 do
        root = root:match("^(.*)\\[^\\]*$") or root
    end
    return root
end

local MOD_DIR = modDirectory()
local Scoreboard = dofile(MOD_DIR .. "\\Scripts\\scoreboard.lua")
local Variant = dofile(MOD_DIR .. "\\Scripts\\variant.lua")
local BuildLine = dofile(MOD_DIR .. "\\Scripts\\buildline.lua")
local MatchLog = dofile(MOD_DIR .. "\\Scripts\\matchlog.lua")
local LOADER_DIR = (MOD_DIR:match("^(.*)\\[^\\]*$") or MOD_DIR) .. "\\MJOLNIRLevelLoader"

local function Log(msg)
    print("[MJOLNIR Hud] " .. tostring(msg) .. "\n")
end

--- The match log must never break the HUD: a failure in it is logged, and
--- the feed, the board and the end of the match go on.
local function logSafely(what, fn, ...)
    local ok, err = pcall(fn, ...)
    if not ok then Log("match log " .. what .. ": " .. tostring(err)) end
end

local UI_ROOT = "/Game/MJOLNIR/UI/"
local FEED_CLASS = UI_ROOT .. "WBP_MJOLNIRKillFeed.WBP_MJOLNIRKillFeed_C"
local BOARD_CLASS = UI_ROOT .. "WBP_MJOLNIRScoreboard.WBP_MJOLNIRScoreboard_C"
local INCIDENT_EVENT = "/Game/Blueprints/BPC_MeteoriteIncidentHandlerComponent.BPC_MeteoriteIncidentHandlerComponent_C:OnIncident_Event"

local POLL_MS = 100
--- The end of a match: the final standings stay up this long before the host
--- takes the fireteam back to the lobby (docs/multiplayer_postgame.md).
local FINAL_SECONDS = 7
--- The menu, reached by a seamless server travel: the fireteam clients follow
--- the host still connected. The game's own return at a game's end sends
--- each client to its own menu, out of the fireteam.
local LOBBY_TRAVEL = "servertravel /Game/Levels/UI/Frontend/Frontend"
local RESULTS_FILE = MOD_DIR .. "\\last_match.txt"
local FEED_LINES = 6     -- WBP_MJOLNIRKillFeed's Line0..Line5
local SCORE_ROWS = 19    -- 16 players plus Red, Blue and unassigned headings
local FEED_SECONDS = 6
local FADE_SECONDS = 1
--- A death is printed on its own ("X died.") only when no kill or suicide
--- line names its victim within this long: the incidents of one death arrive
--- together, in no promised order.
local DEATH_GRACE = 0.4

--- The local player's absolute index: 0 on the host, the joiner's own slot on
--- a fireteam client. Refreshed each tick from the local controller's
--- BlamPlayerStateComponent (refreshLocalPlayer).
local LOCAL_PLAYER = 0

-- ESlateVisibility
local VISIBLE = 3        -- HitTestInvisible: drawn, never takes the mouse
local COLLAPSED = 1

local MODES = Scoreboard.modes

-- EBlamDamageReportingModifier
local MODIFIER_VERBS = {
    [1] = "headshot",     -- Headshot
    [2] = "assassinated", -- SilentMelee
    [3] = "splattered",   -- CollisionDamage
    [4] = "stuck",        -- AttachedDamage
    [5] = "assassinated", -- FancyAssassination
}

local TEAM_NAMES = { [0] = "Red", [1] = "Blue" }

local WHITE = { R = 1, G = 1, B = 1, A = 1 }
local YOU = { R = 1.0, G = 0.85, B = 0.35, A = 1 }       -- lines that name the local player
local ROW_EVEN = { R = 1, G = 1, B = 1, A = 0.06 }
local ROW_ODD = { R = 1, G = 1, B = 1, A = 0.02 }
local ROW_YOU = { R = 1.0, G = 0.85, B = 0.35, A = 0.18 }
local TEAM_COLORS = {
    Red = { R = 1, G = 0.32, B = 0.28, A = 1 },
    Blue = { R = 0.3, G = 0.65, B = 1, A = 1 },
    Unassigned = { R = 0.5, G = 0.66, B = 0.74, A = 1 },
}

--------------------------------------------------------------------------------
-- Helpers
--------------------------------------------------------------------------------

local function readFile(path)
    local f = io.open(path, "rb")
    if not f then return nil end
    local data = f:read("*a")
    f:close()
    return data
end

--- The first local player's controller, read through the engine: a few
--- property reads. It was FindAllOf("PlayerController"), which walks every
--- object in the game, ~20 ms on a converted map (200,000 objects,
--- 2026-10-02); twice a poll, ten polls a second, that alone was 400 ms of
--- every second of game thread. FindAllOf also returns the frontend's
--- controllers, left over in a map's world with no player (and listed
--- first), and a split-screen player's; the engine's first local player is
--- the one wanted.
local Engine = nil
local function playerController()
    if not (Engine and Engine:IsValid()) then
        Engine = FindFirstOf("GameEngine")
        if not (Engine and Engine:IsValid()) then return nil end
    end
    local ok, pc = pcall(function()
        return Engine.GameViewport.GameInstance.LocalPlayers[1].PlayerController
    end)
    if ok and pc and pc:IsValid() then return pc end
    return nil
end

local function now()
    return os.clock()
end

local function refreshLocalPlayer()
    local ok, index = pcall(function()
        return playerController().PlayerState.BlamPlayerStateComponent.BlamAbsolutePlayerIndex
    end)
    if ok and type(index) == "number" and index >= 0 then LOCAL_PLAYER = index end
end

--- "World /Game/Levels/Halo1/Solo/BGL/BGL.BGL" -> "BGL".
local function scenarioOf(world)
    local ok, name = pcall(function() return world:GetFullName() end)
    if not ok or type(name) ~= "string" then return nil end
    local asset = name:match("%.([%w_]+)$")
    return asset and string.upper(asset) or nil
end

--- The match MJOLNIRLevelLoader started (running.txt), if any.
local function runningMatch()
    local raw = readFile(LOADER_DIR .. "\\running.txt")
    if not raw then return nil end
    local code, variant, title = raw:match("^([^\t]*)\t([^\t]*)\t([^\r\n]*)")
    if not code or code == "" then return nil end
    return { code = string.upper(code), variant = variant, title = title }
end

local function loadClass(path)
    local ok, cls = pcall(function()
        local ksl = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
        return ksl:LoadClassAsset_Blocking(ksl:Conv_SoftClassPathToSoftClassRef(ksl:MakeSoftClassPath(path)))
    end)
    if ok and cls and cls:IsValid() then return cls end
    return nil
end

local function createWidget(path, zOrder)
    local cls = loadClass(path)
    local pc = playerController()
    if not cls or not pc then return nil end
    local ok, w = pcall(function()
        local wbl = StaticFindObject("/Script/UMG.Default__WidgetBlueprintLibrary")
        local created = wbl:Create(pc, cls, pc)
        created:AddToViewport(zOrder)
        return created
    end)
    if ok and w and w:IsValid() then return w end
    return nil
end

local function setText(block, text)
    pcall(function() block:SetText(FText(text)) end)
end

local function setVisible(w, visible)
    pcall(function() w:SetVisibility(visible and VISIBLE or COLLAPSED) end)
end

local function bipedTeam(actor)
    local ok, team = pcall(function()
        return actor.BlamGameTeam:GetGameTeamString():ToString():match("EBlamMultiplayerTeam::(%a+)")
    end)
    return ok and Scoreboard.team(team) or nil
end

--------------------------------------------------------------------------------
-- The match
--------------------------------------------------------------------------------

--- The match in progress: { code, variant, title, mode, players = { [index] =
--- stats }, feed = { {text, at, you} }, deaths = { {victim, at} }, teams =
--- { [0] = n, [1] = n }, respawnTicks, dead }, or nil.
local Match = nil
local Feed = nil
local Board = nil
local Queue = {}
local incidentHooked = false
local lastWorld = nil
local nextRunningCheck = 0
local boardShown = false
local boardDirty = true
local nextRosterRefresh = 0

local function stats(index)
    local p = Match.players[index]
    if not p then
        p = { index = index, kills = 0, deaths = 0, suicides = 0, captures = 0, name = nil }
        Match.players[index] = p
    end
    return p
end

--- Player names, by absolute index, from the game state's player states
--- (each BlamPlayerState's BlamPlayerStateComponent carries the index).
local function refreshNames()
    local pc = playerController()
    if not pc then return end
    pcall(function()
        local players = pc:GetWorld().GameState.PlayerArray
        players:ForEach(function(_, element)
            local ps = element:get()
            local okI, index = pcall(function() return ps.BlamPlayerStateComponent.BlamAbsolutePlayerIndex end)
            if okI and type(index) == "number" and index >= 0 then
                local okN, name = pcall(function() return ps:GetPlayerName():ToString() end)
                local p = stats(index)
                if okN and name and name ~= "" then p.name = name end
                -- A spawn can precede our incident hook. Use the replicated
                -- pawn when it exposes a team, and retry the incident's biped
                -- while a new spawn is still acquiring its simulation team.
                local okP, pawn = pcall(function() return ps:GetPawn() end)
                local team = bipedTeam(p.biped) or (okP and bipedTeam(pawn))
                if team then p.team = team end
            end
        end)
    end)
end

local function nameOf(index)
    if type(index) ~= "number" or index < 0 then return nil end
    local p = stats(index)
    if not p.name then refreshNames() end
    return p.name or ("Player " .. tostring(index + 1))
end

local function feedLine(text, you)
    Match.feed[#Match.feed + 1] = { text = text, at = now(), you = you }
    while #Match.feed > FEED_LINES do table.remove(Match.feed, 1) end
end

local function score(p)
    return Scoreboard.score(p, Match.mode)
end

--------------------------------------------------------------------------------
-- Incidents
--------------------------------------------------------------------------------

local HANDLERS = {}

--- "Blam.DamageReporting.Type.AssaultRifle" -> "Assault Rifle"; nothing
--- for the Invalid type an incident without damage carries.
local function weaponOf(damage)
    local tail = type(damage) == "string" and damage:match("%.([%w_]+)$")
    if not tail or tail == "Invalid" or tail == "None" then return nil end
    return (tail:gsub("(%l)(%u)", "%1 %2"):gsub("_", " "))
end

HANDLERS.kill = function(inc)
    local killer, victim = inc.cause, inc.effect
    if type(victim) ~= "number" or victim < 0 then return end
    if killer == victim or type(killer) ~= "number" or killer < 0 then return end
    stats(killer).kills = stats(killer).kills + 1
    if Match.variant == "team_slayer" then
        Match.teamKills[#Match.teamKills + 1] = { player = killer, team = stats(killer).team }
    end
    stats(victim).lastLine = inc.at
    local verb = MODIFIER_VERBS[inc.modifier] or "killed"
    local weapon = weaponOf(inc.damage)
    feedLine(nameOf(killer) .. " " .. verb .. " " .. nameOf(victim) .. (weapon and ("  (" .. weapon .. ")") or ""),
        killer == LOCAL_PLAYER or victim == LOCAL_PLAYER)
    boardDirty = true
end

HANDLERS.suicide = function(inc)
    local victim = inc.effect
    if type(victim) ~= "number" or victim < 0 then return end
    stats(victim).suicides = stats(victim).suicides + 1
    stats(victim).lastLine = inc.at
    feedLine(nameOf(victim) .. " committed suicide", victim == LOCAL_PLAYER)
    boardDirty = true
end

HANDLERS.death = function(inc)
    local victim = inc.effect
    if type(victim) ~= "number" or victim < 0 then return end
    stats(victim).deaths = stats(victim).deaths + 1
    Match.deaths[#Match.deaths + 1] = { victim = victim, at = inc.at }
    if victim == LOCAL_PLAYER then
        Match.dead = true
        Match.respawnTicks = 0
        Match.diedAt = inc.at
        Match.lastRespawnTick = nil
    end
    boardDirty = true
end

HANDLERS.respawn_tick = function(inc)
    if inc.cause ~= LOCAL_PLAYER then return end
    Match.respawnTicks = (Match.respawnTicks or 0) + 1
    Match.lastRespawnTick = inc.at
end

HANDLERS.respawn_final_tick = function(inc)
    if inc.cause ~= LOCAL_PLAYER then return end
    Match.dead = false
end

HANDLERS.player_spawn = function(inc)
    if inc.cause == LOCAL_PLAYER then Match.dead = false end
    -- The spawn names the player's new biped, which knows its team.
    if type(inc.cause) == "number" and inc.cause >= 0 and inc.biped then
        stats(inc.cause).biped = inc.biped
        stats(inc.cause).left = false
        stats(inc.cause).team = bipedTeam(inc.biped) or stats(inc.cause).team
    end
    refreshNames()
    boardDirty = true
end

--- flag_scored: the carrier is the cause; the value is the captured flag's
--- team (0 red, 1 blue), so the point is the other team's (blam_megalo::ctf).
HANDLERS.flag_scored = function(inc)
    if inc.value ~= 0 and inc.value ~= 1 then return end
    if type(inc.cause) == "number" and inc.cause >= 0 then
        stats(inc.cause).captures = stats(inc.cause).captures + 1
    end
    local scorer = (inc.value == 0) and 1 or 0
    Match.teams[scorer] = (Match.teams[scorer] or 0) + 1
    feedLine((nameOf(inc.cause) or TEAM_NAMES[scorer] .. " team") .. " captured the " .. TEAM_NAMES[inc.value] .. " flag",
        inc.cause == LOCAL_PLAYER)
    boardDirty = true
end

HANDLERS.player_joined = function(inc)
    if type(inc.cause) ~= "number" or inc.cause < 0 then return end
    stats(inc.cause).left = false
    refreshNames()
    feedLine(nameOf(inc.cause) .. " joined the game", false)
    boardDirty = true
end

HANDLERS.player_rejoined = HANDLERS.player_joined

--- The end of the match. MJOLNIR's variants give a match one round of 31,
--- so the first `round_over` is the end (the game would reset the round in
--- place). `game_over` comes from a variant of one round, whose end the game
--- would follow with its own return to the menu: the host travels at once to
--- beat it. Either way every machine freezes its tallies, shows the final
--- standings and writes them for the post-game screen; the host then takes
--- the fireteam back to the lobby with a seamless travel.
local function finishMatch(how)
    if Match.over then return end
    refreshNames()
    local parts = {}
    for index, p in pairs(Match.players) do
        parts[#parts + 1] = string.format("%s %d/%d", tostring(nameOf(index) or index), p.kills, p.deaths)
    end
    table.sort(parts)
    Log(how .. ": " .. (#parts > 0 and table.concat(parts, ", ") or "no players"))
    Match.over = { at = now(), winner = Scoreboard.winner(Match) }
    logSafely("finish", MatchLog.finish, Match, Scoreboard, LOCAL_PLAYER, how == "game over" and "game_over" or "round_over", now())
    local f = io.open(RESULTS_FILE, "w")
    if f then
        f:write(Scoreboard.results(Match, LOCAL_PLAYER, os.time()))
        f:close()
    end
    local host = false
    pcall(function() host = playerController():GetWorld().AuthorityGameMode:IsValid() end)
    -- hold_match.txt beside this mod keeps a finished match where it is, so
    -- its game state can be read (tools/remote/blam-arena.py).
    local hold = io.open(MOD_DIR .. "\\hold_match.txt", "r")
    if hold then
        hold:close()
        Log("hold_match.txt: staying in the finished match")
    elseif host then
        Match.travelAt = now() + (how == "game over" and 0 or FINAL_SECONDS)
    end
    boardDirty = true
end

HANDLERS.round_over = function() finishMatch("round over") end
HANDLERS.game_over = function() finishMatch("game over") end

HANDLERS.player_quit = function(inc)
    if type(inc.cause) ~= "number" or inc.cause < 0 then return end
    feedLine(nameOf(inc.cause) .. " quit", false)
    stats(inc.cause).left = true
    boardDirty = true
end

HANDLERS.player_booted_player = function(inc)
    if type(inc.effect) ~= "number" or inc.effect < 0 then return end
    feedLine(nameOf(inc.effect) .. " was booted", false)
    stats(inc.effect).left = true
    boardDirty = true
end

--- Where an incident's actor stands, as { X, Y, Z } in the world's space.
local function actorPosition(actor)
    if not (actor and actor:IsValid()) then return nil end
    local l = actor:K2_GetActorLocation()
    return { l.X, l.Y, l.Z }
end

--- Every incident, queued with what the handlers read. Reading the struct is
--- all the hook does; while the match log records (the host), that includes
--- where the cause's and the effect's objects stand at that moment.
local function hookIncidents()
    if incidentHooked then return end
    incidentHooked = pcall(function()
        RegisterHook(INCIDENT_EVENT, function(_, incident)
            if #Queue >= 64 then return end
            pcall(function()
                local i = incident:get()
                local entry = {
                    -- Lower-cased: the kill incident arrives as "Kill".
                    name = string.lower(i.Name:ToString()),
                    cause = i.CausePlayerAbsoluteIndex,
                    effect = i.EffectPlayerAbsoluteIndex,
                    value = i.CustomValue,
                    at = now(),
                }
                pcall(function() entry.modifier = i.DamageReportingInfo.Modifier end)
                pcall(function() entry.biped = i.CauseObjectActor end)
                pcall(function() entry.victimBiped = i.EffectObjectActor end)
                pcall(function() entry.damage = i.DamageReportingInfo.Type.TagName:ToString() end)
                if MatchLog.recording() then
                    pcall(function() entry.causePos = actorPosition(i.CauseObjectActor) end)
                    pcall(function() entry.effectPos = actorPosition(i.EffectObjectActor) end)
                end
                Queue[#Queue + 1] = entry
            end)
        end)
    end)
    if incidentHooked then Log("incident hook armed") end
end

local function drain()
    local queued = Queue
    Queue = {}
    for _, inc in ipairs(queued) do
        -- After the end the tallies are final: the round the game resets in
        -- place behind the standings must not score.
        if Match and not Match.over then logSafely("incident", MatchLog.incident, inc) end
        local handler = Match and not Match.over and HANDLERS[inc.name]
        if handler then
            for _, actor in ipairs({ { inc.cause, inc.biped }, { inc.effect, inc.victimBiped } }) do
                local index, biped = actor[1], actor[2]
                if type(index) == "number" and index >= 0 and biped then
                    local team = bipedTeam(biped)
                    if team then stats(index).team = team end
                end
            end
            local ok, err = pcall(handler, inc)
            if not ok then Log("incident " .. inc.name .. ": " .. tostring(err)) end
        end
    end
    -- Deaths no kill or suicide line explained: a fall, the guardians.
    local t = now()
    local keep = {}
    for _, d in ipairs(Match and Match.deaths or {}) do
        local p = stats(d.victim)
        local explained = p.lastLine and p.lastLine >= d.at - DEATH_GRACE
        if not explained then
            if t - d.at >= DEATH_GRACE then
                feedLine(nameOf(d.victim) .. " died", d.victim == LOCAL_PLAYER)
            else
                keep[#keep + 1] = d
            end
        end
    end
    if Match then Match.deaths = keep end
end

--------------------------------------------------------------------------------
-- Drawing
--------------------------------------------------------------------------------

local function drawFeed()
    if not (Feed and Feed:IsValid()) then return end
    local t = now()
    local live = {}
    for _, line in ipairs(Match.feed) do
        if t - line.at < FEED_SECONDS then live[#live + 1] = line end
    end
    Match.feed = live
    -- The newest line at the bottom: Line(FEED_LINES-1).
    local first = FEED_LINES - #live
    for i = 0, FEED_LINES - 1 do
        local block = Feed["Line" .. i]
        local line = live[i - first + 1]
        if line then
            setText(block, line.text)
            local age = t - line.at
            local alpha = math.min(1, math.max(0, (FEED_SECONDS - age) / FADE_SECONDS))
            pcall(function()
                block:SetColorAndOpacity({ SpecifiedColor = line.you and YOU or WHITE, ColorUseRule = 0 })
                block:SetRenderOpacity(alpha)
            end)
        else
            setText(block, "")
        end
    end
    -- A fireteam client does not always get the respawn's final tick or its
    -- spawn: the countdown stuck at "Respawn in 1" after the player was
    -- back (two PCs, 2026-10-02). The ticks are a second apart and the
    -- respawn takes five.
    if Match.dead and ((Match.lastRespawnTick and t - Match.lastRespawnTick > 2.5) or
            (Match.diedAt and t - Match.diedAt > 10)) then
        Match.dead = false
    end
    local respawn = ""
    if Match.dead then
        local ticks = Match.respawnTicks or 0
        respawn = ticks > 0 and ("Respawn in " .. tostring(math.max(1, 4 - ticks))) or "Respawning"
    end
    setText(Feed.Respawn, respawn)
end

local function boardHeld(pc)
    local held = false
    for _, key in ipairs({ "Tab", "Gamepad_Special_Left" }) do
        local ok, down = pcall(function() return pc:IsInputKeyDown({ KeyName = FName(key) }) end)
        if ok and down then held = true end
    end
    return held
end

local function drawScoreStrip()
    if not (Feed and Feed:IsValid()) then return end
    local summary = Scoreboard.summary(Match, LOCAL_PLAYER)
    setText(Feed.ScoreLeftLabel, summary.leftLabel)
    setText(Feed.ScoreRightLabel, summary.rightLabel)
    setText(Feed.ScoreLeftValue, tostring(summary.left))
    setText(Feed.ScoreRightValue, tostring(summary.right))
    setText(Feed.ScoreTarget, tostring(Match.mode.toWin))
    for _, side in ipairs({ "Left", "Right" }) do
        local team = summary[string.lower(side) .. "Team"]
        local color = TEAM_COLORS[team] or (side == "Left" and YOU or TEAM_COLORS.Unassigned)
        pcall(function()
            Feed["Score" .. side .. "Accent"]:SetBrushColor(color)
            Feed["Score" .. side .. "Label"]:SetColorAndOpacity({ SpecifiedColor = color, ColorUseRule = 0 })
        end)
    end
end

local function drawBoard()
    if not (Board and Board:IsValid()) then return end
    local mode = Match.mode
    if Match.over then
        -- The final standings: who won, over the game type and map.
        setText(Board.BoardLabel, "MULTIPLAYER  /  FINAL STANDINGS")
        setText(Board.Title, Match.over.winner)
        setText(Board.Subtitle, mode.title .. "   /   " .. string.upper(Match.title or Match.code))
        setText(Board.BoardHint, "RETURNING TO THE LOBBY")
    else
        setText(Board.Title, mode.title)
        setText(Board.Subtitle, string.upper(Match.title or Match.code) .. "   /   " ..
            string.format("FIRST TO %d %s", mode.toWin, string.upper(mode.unit)))
    end
    setText(Board.ScoreH, mode.stat == "captures" and "CAPTURES" or "SCORE")
    refreshNames()
    local totals = Scoreboard.totals(Match)
    local rows = Scoreboard.rows(Match.players, mode, totals)
    local count = 0
    for _, r in ipairs(rows) do if r.player then count = count + 1 end end
    setText(Board.PlayerCount, tostring(count) .. (count == 1 and " PLAYER" or " PLAYERS"))
    for i = 0, SCORE_ROWS - 1 do
        local entry = rows[i + 1]
        local p = entry and entry.player
        local row = Board["Row" .. i]
        if entry then
            setVisible(row, true)
            local team = entry.team or (p and mode.teams and Scoreboard.team(p.team))
            local tint = TEAM_COLORS[team]
            local you = p and p.index == LOCAL_PLAYER
            local name = p and (p.name or ("Player " .. tostring(p.index + 1))) or
                ((team == "Unassigned" and "AWAITING ASSIGNMENT" or string.upper(team) .. " TEAM") ..
                    "  /  " .. tostring(entry.count))
            setText(Board["Name" .. i], name)
            setText(Board["Marker" .. i], you and "YOU" or "")
            setText(Board["Score" .. i], p and tostring(score(p)) or (entry.total and tostring(entry.total) or ""))
            setText(Board["Kills" .. i], p and tostring(p.kills) or "")
            setText(Board["Deaths" .. i], p and tostring(p.deaths) or "")
            local color = you and ROW_YOU or ((i % 2 == 0) and ROW_EVEN or ROW_ODD)
            if tint then color = { R = tint.R, G = tint.G, B = tint.B, A = entry.team and 0.24 or (you and 0.20 or 0.06) } end
            pcall(function()
                row:SetBrushColor(color)
                row.Slot:SetPadding({ Left = 0, Top = entry.team and 12 or 2, Right = 0, Bottom = 0 })
                Board["Stripe" .. i]:SetBrushColor(tint or (you and YOU or ROW_EVEN))
                Board["Name" .. i]:SetColorAndOpacity({ SpecifiedColor = entry.team and tint or WHITE, ColorUseRule = 0 })
            end)
        else
            setVisible(row, false)
        end
    end
end

--------------------------------------------------------------------------------
-- The match log
--------------------------------------------------------------------------------
-- The host records (Scripts/matchlog.lua); each client asks it for the
-- match's id over ServerExecRPC and claims its seat from the answer, which
-- comes back on its controller as ClientMessage type "MJOLNIR". Both RPCs
-- are the ones MJOLNIRLobby's messages ride (docs/multiplayer_postgame.md).

local ASK = "MJOLNIR|matchid"
local logHooked = false
local Told = {}       -- host answers waiting for the game thread

local function isHostWorld(pc)
    local ok, yes = pcall(function() return pc:GetWorld().AuthorityGameMode:IsValid() end)
    return ok and yes == true
end

local function hookMatchLog()
    if logHooked then return end
    logHooked = pcall(function()
        RegisterHook("/Script/Engine.PlayerController:ServerExecRPC", function(self, msg)
            local okM, text = pcall(function() return msg:get():ToString() end)
            if not okM or text ~= ASK or not MatchLog.recording() then return end
            local pc = self:get()
            -- Off the RPC, as MJOLNIRLobby answers its messages.
            ExecuteInGameThread(function()
                if not (Match and pc:IsValid()) then return end
                local seat = {}
                pcall(function() seat.index = pc.PlayerState.BlamPlayerStateComponent.BlamAbsolutePlayerIndex end)
                pcall(function() seat.name = pc.PlayerState:GetPlayerName():ToString() end)
                -- Answer only with the asker's own seat, as recorded: a player
                -- joining a match under way reads index 0 (the host's) for a
                -- few seconds after the host seats it (two PCs, 2026-10-03).
                -- Until then say nothing; the client asks again.
                local p = type(seat.index) == "number" and seat.index ~= LOCAL_PLAYER and Match.players[seat.index]
                if not (p and p.name and p.name == seat.name) then return end
                MatchLog.answer(pc, seat)
            end)
        end)
        RegisterHook("/Script/Engine.PlayerController:ClientMessage", function(_, s, kind)
            local okK, name = pcall(function() return kind:get():ToString() end)
            if not okK or name ~= "MJOLNIR" then return end
            local okS, text = pcall(function() return s:get():ToString() end)
            if okS and type(text) == "string" and text:sub(1, 14) == "MJOLNIR|match|" and #Told < 8 then
                Told[#Told + 1] = text
            end
        end)
    end)
    if not logHooked then Log("match log: could not hook the controller RPCs") end
end

local function matchLogTick(pc)
    hookMatchLog()
    if not Match.logChecked and not Match.over then
        -- The host records. Its world's game mode is there from the start;
        -- a few seconds' grace covers a world still coming up.
        if isHostWorld(pc) then
            Match.logChecked = true
            MatchLog.start(Match, Match.startedAt)
        elseif now() - Match.startedAt > 15 then
            Match.logChecked = true
        end
    end
    MatchLog.tick(Match, Scoreboard, LOCAL_PLAYER, now())
    local told = Told
    Told = {}
    -- The host's own hook sees the answers it sends its clients.
    if MatchLog.recording() or isHostWorld(pc) then told = {} end
    for _, text in ipairs(told) do
        local ownName = nil
        pcall(function() ownName = pc.PlayerState:GetPlayerName():ToString() end)
        local id, claimed = MatchLog.told(text, LOCAL_PLAYER, ownName)
        if id then
            Match.logId = id
            Match.claimed = claimed
            -- A private match may go public: ask again now and then.
            Match.nextAsk = now() + (claimed and math.huge or 30)
        end
    end
    if not MatchLog.recording() and not Match.claimed and not Match.over and now() >= Match.nextAsk
        and not isHostWorld(pc) then
        Match.nextAsk = now() + MatchLog.ASK_SECONDS
        pcall(function() pc:ServerExecRPC(ASK) end)
    end
end

--------------------------------------------------------------------------------
-- The poll
--------------------------------------------------------------------------------

--------------------------------------------------------------------------------
-- Name tags
--------------------------------------------------------------------------------
-- The co-op HUD draws every other fireteam member's name over their head
-- (WBP_NavpointWidgetPlayer_C; PlayerNameValue is the name), enemies
-- included. Free for all: no tags. Team games: teammates only, as in Halo.
-- Collapsing a tag sticks; the widget does not show itself again. New tags
-- are caught as they are made, and a pass each second over the known ones
-- covers a tag whose name or team was not known yet. Only arming the watch
-- walks the object array (FindAllOf, ~20 ms on a converted map): a sweep
-- each second was a 20 ms hitch each second.

local NAVPOINT_CLASS = "/Game/UI/Hud/Navpoints/WBP_NavpointWidgetPlayer.WBP_NavpointWidgetPlayer_C"
local NAVPOINT_SHOWN = 4 -- SelfHitTestInvisible, as the HUD makes it
local nextTagSweep = 0
local tagWatch = false
--- Every name tag seen, by address; a tag leaves when it is gone.
local Tags = {}

local function trackTag(tag)
    local ok, address = pcall(function() return tag:GetAddress() end)
    if ok and address then Tags[address] = tag end
end

local function teamOfName(name)
    for _, p in pairs(Match.players) do
        if p.name == name then return p.team end
    end
    return nil
end

local function applyTag(tag)
    if not Match then return end
    local show = false
    if Match.mode.teams then
        local okN, name = pcall(function() return tag.PlayerNameValue:GetText():ToString() end)
        local mine = Match.players[LOCAL_PLAYER] and Match.players[LOCAL_PLAYER].team
        show = okN and mine ~= nil and teamOfName(name) == mine
    end
    pcall(function() tag:SetVisibility(show and NAVPOINT_SHOWN or COLLAPSED) end)
end

local function sweepTags()
    if now() < nextTagSweep then return end
    nextTagSweep = now() + 1
    if not tagWatch then
        tagWatch = pcall(function()
            NotifyOnNewObject(NAVPOINT_CLASS, function(tag)
                trackTag(tag)
                ExecuteInGameThreadWithDelay(50, function()
                    if tag:IsValid() then applyTag(tag) end
                end)
            end)
        end)
        if tagWatch then
            for _, tag in ipairs(FindAllOf("WBP_NavpointWidgetPlayer_C") or {}) do trackTag(tag) end
        end
    end
    for address, tag in pairs(Tags) do
        if tag:IsValid() then applyTag(tag) else Tags[address] = nil end
    end
end

--- The game type: the HUD's model of it, with the score to win read from the
--- variant the simulation loads (MJOLNIRLevelLoader's variants/<mode>.mglo)
--- rather than assumed.
local function modeFor(variant)
    local mode = {}
    for k, v in pairs(MODES[variant] or MODES.slayer) do mode[k] = v end
    local name = tostring(variant or ""):match("^[%w_]+$")
    local toWin = name and Variant.scoreToWin(readFile(LOADER_DIR .. "\\variants\\" .. name .. ".mglo"))
    if toWin and toWin > 0 then mode.toWin = toWin end
    return mode
end

local function startMatch(running, world)
    Match = {
        code = running.code,
        variant = running.variant,
        title = running.title,
        mode = modeFor(running.variant),
        players = {},
        feed = {},
        deaths = {},
        teams = { [0] = 0, [1] = 0 },
        teamKills = {},
        world = world,
        startedAt = now(),
        -- The match log: the host records; a client asks the host for the
        -- match's id to claim its seat.
        logChecked = false,
        nextAsk = now() + 3,
    }
    Feed, Board = nil, nil
    boardShown = false
    boardDirty = true
    nextRosterRefresh = 0
    Log("match: " .. running.code .. " " .. tostring(running.variant))
end

--- The widgets, once the map's world is up: created too early (while the
--- level is still loading) Create returns nothing, so this retries each
--- second until both exist.
local nextWidgetTry = 0
local widgetTries = 0

local function ensureWidgets()
    if Feed and Feed:IsValid() and Board and Board:IsValid() then return end
    if now() < nextWidgetTry then return end
    nextWidgetTry = now() + 1
    widgetTries = widgetTries + 1
    if not (Feed and Feed:IsValid()) then
        Feed = createWidget(FEED_CLASS, 40)
        if Feed then setText(Feed.Watermark, BuildLine.text(MOD_DIR:match("^(.*)\\[^\\]*$") or MOD_DIR)) end
    end
    if not (Board and Board:IsValid()) then
        Board = createWidget(BOARD_CLASS, 45)
        if Board then setVisible(Board, false) end
    end
    if Feed and Board then
        Log("kill feed and scoreboard up")
        refreshNames()
    elseif widgetTries == 30 then
        Log("WIDGETS MISSING after 30 s (is pakchunk984-MJOLNIRUI installed?)")
    end
end

local function endMatch()
    if Match and MatchLog.recording() then
        logSafely("finish", MatchLog.finish, Match, Scoreboard, LOCAL_PLAYER, "abandoned", now())
    end
    widgetTries = 0
    if Feed and Feed:IsValid() then setVisible(Feed, false) end
    if Board and Board:IsValid() then setVisible(Board, false) end
    Match, Feed, Board = nil, nil, nil
    Queue = {}
end

local function tick()
    local pc = playerController()
    local world = pc and pc:GetWorld()
    local code = world and scenarioOf(world)
    if code ~= lastWorld then
        lastWorld = code
        local running = runningMatch()
        if Match then endMatch() end
        if running and code == running.code then startMatch(running, code) end
    elseif not Match and code and now() >= nextRunningCheck then
        -- A player who joins a match under way is in its world before the
        -- level loader knows the match: look again once a second.
        nextRunningCheck = now() + 1
        local running = runningMatch()
        if running and code == running.code then startMatch(running, code) end
    end
    if not Match then
        Queue = {}
        return
    end
    hookIncidents()
    ensureWidgets()
    refreshLocalPlayer()
    if now() >= nextRosterRefresh then
        nextRosterRefresh = now() + 1
        refreshNames()
        boardDirty = true
    end
    -- Before the drain: the host's log is recording by the first incident.
    logSafely("tick", matchLogTick, pc)
    drain()
    sweepTags()
    drawFeed()
    local held = boardHeld(pc) or Match.over ~= nil
    if Match.travelAt and now() >= Match.travelAt then
        Match.travelAt = nil
        Log("final standings shown: taking the fireteam back to the lobby")
        pcall(function()
            StaticFindObject("/Script/Engine.Default__KismetSystemLibrary"):ExecuteConsoleCommand(world, LOBBY_TRAVEL, pc)
        end)
    end
    if held ~= boardShown then
        boardShown = held
        if held then boardDirty = true end
        setVisible(Board, held)
        if Feed and Feed:IsValid() then setVisible(Feed.MatchScore, not held) end
    end
    if boardDirty then
        boardDirty = false
        drawScoreStrip()
        if boardShown then drawBoard() end
    end
end

local function poll()
    local ok, err = pcall(tick)
    if not ok then Log("tick: " .. tostring(err)) end
    ExecuteInGameThreadWithDelay(POLL_MS, poll)
end

logSafely("init", MatchLog.init, {
    modDir = MOD_DIR,
    log = Log,
    version = (readFile(MOD_DIR .. "\\mod.json") or ""):match('"version"%s*:%s*"([^"]+)"'),
})

Log("Module loaded.")
ExecuteInGameThreadWithDelay(5000, poll)

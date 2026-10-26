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
local publishPresence = dofile(MOD_DIR .. "\\Scripts\\presence_snapshot.lua").new(MOD_DIR)
local Variant = dofile(MOD_DIR .. "\\Scripts\\variant.lua")
local BuildLine = dofile(MOD_DIR .. "\\Scripts\\buildline.lua")
local MatchLog = dofile(MOD_DIR .. "\\Scripts\\matchlog.lua")
local HubNames = dofile(MOD_DIR .. "\\Scripts\\hubnames.lua")
local Rows = dofile(MOD_DIR .. "\\Scripts\\feed.lua")
local Anim = dofile(MOD_DIR .. "\\Scripts\\anim.lua")
local Icons = dofile(MOD_DIR .. "\\Scripts\\hudicons.lua")
local Relay = dofile(MOD_DIR .. "\\Scripts\\relay.lua")
local Hitches = dofile(MOD_DIR .. "\\Scripts\\hitches.lua")
local Bench = dofile(MOD_DIR .. "\\Scripts\\bench.lua")
local Chat = dofile(MOD_DIR .. "\\Scripts\\chat.lua")
local Bots = dofile(MOD_DIR .. "\\Scripts\\bots.lua")
HubNames.init({ modsDir = MOD_DIR:match("^(.*)\\[^\\]*$") or MOD_DIR })
local LOADER_DIR = (MOD_DIR:match("^(.*)\\[^\\]*$") or MOD_DIR) .. "\\MJOLNIRLevelLoader"

local function Log(msg)
    print("[MJOLNIR Hud] " .. tostring(msg) .. "\n")
end
Bots.init(MOD_DIR:match("^(.*)\\[^\\]*$") or MOD_DIR, Log)

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
local SCORE_ROWS = 19    -- 16 players plus Red, Blue and unassigned headings
local SCORE_TRACK = 320  -- a score bar's full width (build_mjolnir_ui.py SCORE_TRACK)
--- A death is printed on its own ("X died.") only when no kill or suicide
--- line names its victim within this long: the incidents of one death arrive
--- together, in no promised order.
local DEATH_GRACE = 0.4

--- The local player's absolute index: 0 on the host, the joiner's own slot on
--- a fireteam client. Refreshed each tick from the local controller's
--- BlamPlayerStateComponent (refreshLocalPlayer).
local LOCAL_PLAYER = 0
local presencePlayerKnown = false

-- ESlateVisibility
local VISIBLE = 3        -- HitTestInvisible: drawn, never takes the mouse
local COLLAPSED = 1

local MODES = Scoreboard.modes

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
-- The feed's colours (Scripts/feed.lua): names, the words of an event line,
-- and the glyphs.
local FEED = {
    name = { R = 0.92, G = 0.95, B = 1, A = 1 },
    words = { R = 0.64, G = 0.75, B = 0.84, A = 1 },
    headshot = { R = 1.0, G = 0.44, B = 0.32, A = 1 },
    joined = { R = 0.48, G = 0.90, B = 0.58, A = 1 },
    kicked = { R = 1.0, G = 0.40, B = 0.34, A = 1 },
    medal = { R = 1.0, G = 0.80, B = 0.35, A = 1 },
    spree = { R = 1.0, G = 0.56, B = 0.24, A = 1 },
    blood = { R = 0.95, G = 0.26, B = 0.24, A = 1 },
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
    presencePlayerKnown = ok and type(index) == "number" and index >= 0
    if presencePlayerKnown then LOCAL_PLAYER = index end
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

--- A stored biped may be gone: a dead or departed player's body is destroyed
--- and freed, and reading through its handle is an access violation pcall
--- cannot catch (crash 2026-10-17, BGL, after a player dropped).
local function bipedTeam(actor)
    if not actor then return nil end
    local okV, valid = pcall(function() return actor:IsValid() end)
    if not (okV and valid) then return nil end
    local ok, team = pcall(function()
        return actor.BlamGameTeam:GetGameTeamString():ToString():match("EBlamMultiplayerTeam::(%a+)")
    end)
    return ok and Scoreboard.team(team) or nil
end

--------------------------------------------------------------------------------
-- The match
--------------------------------------------------------------------------------

--- The match in progress: { code, variant, title, mode, players = { [index] =
--- stats }, feed (Scripts/feed.lua), anim (Scripts/anim.lua), deaths =
--- { {victim, at, damage} }, medals (lines waiting for the end of a drain),
--- teams = { [0] = n, [1] = n }, respawnTicks, dead }, or nil.
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
        p = { index = index, kills = 0, rawKills = 0, deaths = 0, suicides = 0, captures = 0, name = nil }
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
                if okN and name and name ~= "" then
                    -- A seat someone left, now taken: by them again, their
                    -- tallies stand; by another player, the seat starts from
                    -- nothing, as the game's own score does (#236).
                    if p.arriving and p.leftName and name ~= p.leftName then
                        Log(string.format("seat %d: %s took %s's seat; its tallies start again", index, name, p.leftName))
                        p.kills, p.rawKills, p.deaths, p.suicides, p.captures = 0, 0, 0, 0, 0
                        p.display, p.userId, p.reports, p.team = nil, nil, nil, nil
                        boardDirty = true
                    end
                    if p.arriving then p.arriving, p.leftName = nil, nil end
                    p.name = name
                end
                -- The hub account MJOLNIRLobby resolved for that name, shown
                -- in its place (docs/player_identity.md). p.name stays the
                -- in-game name: seats, claims and bans are keyed by it.
                local hub = HubNames.of(p.name)
                p.display, p.userId, p.reports = hub and hub.name, hub and hub.id, hub and hub.reports
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

--- A fireteam client asks its host for the bots' names (Relay.BOTS_ASK)
--- when it meets a bot seat it cannot name; a few times at most.
local function askBotNames()
    if not Match or Match.host or Match.botsHeard then return end
    local t = now()
    if t < (Match.nextBotAsk or 0) or (Match.botAsks or 0) >= 5 then return end
    Match.nextBotAsk = t + 3
    Match.botAsks = (Match.botAsks or 0) + 1
    local pc = playerController()
    if pc then pcall(function() pc:ServerExecRPC(Relay.BOTS_ASK) end) end
end

local function nameOf(index)
    if type(index) ~= "number" or index < 0 then return nil end
    local p = stats(index)
    if not p.name and Bots.isBot(index) then askBotNames() end
    if not p.name then refreshNames() end
    return p.display or p.name or ("Player " .. tostring(index + 1))
end

--- A name as the feed shows it: at most 22 characters.
local function short(name)
    if type(name) ~= "string" or #name <= 22 then return name end
    local chars = {}
    for ch in name:gmatch("[%z\1-\127\194-\244][\128-\191]*") do
        chars[#chars + 1] = ch
        if #chars > 22 then return table.concat(chars, "", 1, 20) .. "…" end
    end
    return name
end

--- A player's colour in the feed: the team's in team games, gold for the
--- local player in free for all, the rest near white.
local function nameColor(index)
    local p = Match.players[index]
    if Match.mode.teams and p and p.team and TEAM_COLORS[p.team] then return TEAM_COLORS[p.team] end
    if index == LOCAL_PLAYER then return YOU end
    return FEED.name
end

--- A player's hub avatar, as the scoreboard shows it: nil without a hub
--- account or before MJOLNIRLobby has cached the picture.
local function avatarOf(index)
    local p = type(index) == "number" and Match.players[index]
    if not (p and p.userId) then return nil end
    local ok, tex = pcall(HubNames.avatar, p.userId, playerController())
    return ok and tex or nil
end

--- A line in the feed (Scripts/feed.lua).
local function feedPush(entry)
    Rows.push(Match.feed, entry, now())
end

--- A line about one player: a glyph, the name, and what happened.
local function eventLine(index, glyph, glyphColor, words, wordsColor)
    feedPush({ glyph = glyph, glyphColor = glyphColor, lead = short(nameOf(index)), leadColor = nameColor(index),
        leadAvatar = avatarOf(index), tail = words, tailColor = wordsColor or FEED.words, accent = glyphColor, you = index == LOCAL_PLAYER })
end

local function score(p)
    return Scoreboard.score(p, Match.mode)
end

--------------------------------------------------------------------------------
-- Incidents
--------------------------------------------------------------------------------

local HANDLERS = {}

--- A kill: the killer, the weapon (the game's own silhouette, or one of our
--- glyphs), what made it special (a headshot ...), the victim.
HANDLERS.kill = function(inc)
    local killer, victim = inc.cause, inc.effect
    if type(victim) ~= "number" or victim < 0 then return end
    if killer == victim or type(killer) ~= "number" or killer < 0 then return end
    local teamOf = stats(killer).team
    local betrayal = Match.mode.teams and teamOf ~= nil and teamOf == stats(victim).team
    -- Team Slayer's script takes a point from a teammate's killer
    -- (blam_megalo Variant::team_slayer); the tallies do the same.
    local point = (betrayal and Match.variant == "team_slayer") and -1 or 1
    stats(killer).kills = stats(killer).kills + point
    stats(killer).rawKills = (stats(killer).rawKills or 0) + 1
    if Match.variant == "team_slayer" then
        Match.teamKills[#Match.teamKills + 1] = { player = killer, team = teamOf, points = point }
    end
    stats(victim).lastLine = inc.at
    local shown = Icons.forKill(inc.damage, inc.modifier)
    feedPush({
        lead = short(nameOf(killer)), leadColor = nameColor(killer), leadAvatar = avatarOf(killer),
        weapon = shown.weapon, weaponGlyph = shown.glyph,
        mod = shown.mod, modColor = shown.mod == "Headshot" and FEED.headshot or nil,
        tail = short(nameOf(victim)), tailColor = nameColor(victim), tailAvatar = avatarOf(victim),
        note = betrayal and "BETRAYAL" or shown.note, noteColor = betrayal and FEED.kicked or FEED.words,
        accent = nameColor(killer), you = killer == LOCAL_PLAYER or victim == LOCAL_PLAYER,
        label = Icons.label(Icons.damageType(inc.damage)),
    })
    boardDirty = true
end

HANDLERS.suicide = function(inc)
    local victim = inc.effect
    if type(victim) ~= "number" or victim < 0 then return end
    stats(victim).suicides = stats(victim).suicides + 1
    stats(victim).lastLine = inc.at
    eventLine(victim, "Skull", FEED.words, "committed suicide")
    boardDirty = true
end

--- Medals: everyone's go to the feed after the kill line that earned them
--- (they arrive before it in the same tick); the local player's also come
--- up in the middle of the screen. Multi-kills and sprees are relayed by the
--- host to fireteam clients (MJOLNIRLevelLoader plays their sounds).
local MEDALS = { first_blood = { "First Blood", "FirstBlood", FEED.blood } }
for i, title in ipairs({ "Double Kill", "Triple Kill", "Overkill", "Killtacular", "Killtrocity",
    "Killimanjaro", "Killtastrophe", "Killpocalypse", "Killionaire" }) do
    MEDALS["multikill_x" .. (i + 1)] = { title, "Medal", FEED.medal }
end
for n, title in pairs({ [5] = "Killing Spree", [10] = "Killing Frenzy", [15] = "Running Riot", [20] = "Rampage",
    [25] = "Untouchable", [30] = "Invincible" }) do
    MEDALS[n .. "_in_a_row"] = { title, "Spree", FEED.spree }
end

local function medal(inc)
    local m = MEDALS[inc.name]
    if not m or type(inc.cause) ~= "number" or inc.cause < 0 then return end
    Match.medals[#Match.medals + 1] = { index = inc.cause, medal = m }
end
for name in pairs(MEDALS) do HANDLERS[name] = medal end

local function announceMedals()
    for _, waiting in ipairs(Match.medals) do
        local m = waiting.medal
        eventLine(waiting.index, m[2], m[3], m[1], m[3])
        if waiting.index == LOCAL_PLAYER then
            Anim.callout(Match.anim, { title = string.upper(m[1]), glyph = m[2], color = m[3] }, now())
        end
    end
    Match.medals = {}
end

HANDLERS.death = function(inc)
    local victim = inc.effect
    if type(victim) ~= "number" or victim < 0 then return end
    stats(victim).deaths = stats(victim).deaths + 1
    -- Dead on the scoreboard until the next spawn (#249).
    stats(victim).dead = true
    Match.deaths[#Match.deaths + 1] = { victim = victim, at = inc.at, damage = inc.damage }
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

--- The round clock (a time limit set in the host's game settings). The
--- engine counts it down but shows nothing, so the HUD keeps its own: from
--- the first spawn, which comes about a second before the round clock starts
--- (2026-10-04: spawn 00:05:58.8, round over 00:06:59.5 on a one-minute
--- limit), set right by the engine's own countdown incidents, and on a
--- fireteam client by the host's (see hookMatchLog).
local CLOCK_LAG = 0.8

local function clockFrom(remaining, at)
    if Match and (Match.mode.timeLimit or 0) > 0 then Match.clockEnd = (at or now()) + remaining end
end

HANDLERS["30_seconds_remaining"] = function(inc) clockFrom(30, inc.at) end
HANDLERS["10_seconds_remaining"] = function(inc) clockFrom(10, inc.at) end

HANDLERS.player_spawn = function(inc)
    if inc.cause == LOCAL_PLAYER then Match.dead = false end
    if type(inc.cause) == "number" and inc.cause >= 0 then stats(inc.cause).dead = false end
    if inc.cause == LOCAL_PLAYER and not Match.clockEnd then
        clockFrom((Match.mode.timeLimit or 0) * 60 + CLOCK_LAG, inc.at)
    end
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
    local words = "captured the " .. TEAM_NAMES[inc.value] .. " flag"
    if type(inc.cause) == "number" and inc.cause >= 0 then
        eventLine(inc.cause, "Flag", TEAM_COLORS[TEAM_NAMES[scorer]], words)
    else
        feedPush({ glyph = "Flag", glyphColor = TEAM_COLORS[TEAM_NAMES[scorer]], lead = TEAM_NAMES[scorer] .. " team",
            leadColor = TEAM_COLORS[TEAM_NAMES[scorer]], tail = words, tailColor = FEED.words,
            accent = TEAM_COLORS[TEAM_NAMES[scorer]] })
    end
    boardDirty = true
end

--- A joiner's hub account reaches the host a few seconds after the join
--- (its identity ticket, docs/player_identity.md), and every client a moment
--- later. Its "joined" line waits up to JOIN_WAIT seconds for it, so the
--- line names the account rather than the Steam or Xbox name.
local JOIN_WAIT = 8

HANDLERS.player_joined = function(inc)
    if type(inc.cause) ~= "number" or inc.cause < 0 then return end
    local seat = stats(inc.cause)
    -- Whose seat this is now is settled by name once its player state has
    -- one (refreshNames).
    if seat.left then seat.arriving = true end
    seat.left = false
    refreshNames()
    Match.joins = Match.joins or {}
    Match.joins[#Match.joins + 1] = { index = inc.cause, at = now() }
    boardDirty = true
end

--- Each tick: the held "joined" lines whose account is known, or whose wait
--- is over.
local function announceJoins()
    local waiting = {}
    for _, j in ipairs(Match.joins or {}) do
        if stats(j.index).display or now() - j.at >= JOIN_WAIT then
            eventLine(j.index, "Joined", FEED.joined, "joined the game")
        else
            waiting[#waiting + 1] = j
        end
    end
    Match.joins = waiting
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
    -- The match's id, which the post-game screen's reports cite: the host's
    -- own record's, or the one the host told this client.
    Match.logId = MatchLog.currentId() or Match.logId
    logSafely("finish", MatchLog.finish, Match, Scoreboard, LOCAL_PLAYER, how == "game over" and "game_over" or "round_over", now())
    local f = io.open(RESULTS_FILE, "w")
    if f then
        f:write(Scoreboard.results(Match, LOCAL_PLAYER, os.time(), Match.logId))
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

--- With bots the host ends the match itself: Slayer's own script counts kills
--- of players only, so a score made on bots never ends the round.
local function botScoreReached()
    if not (Match and Match.host and Bots.active()) or Match.over then return false end
    local toWin = Match.mode.toWin or 0
    if toWin <= 0 then return false end
    if Match.mode.teams then
        for _, total in pairs(Scoreboard.totals(Match)) do
            if total >= toWin then return true end
        end
        return false
    end
    for _, p in pairs(Match.players) do
        if not p.left and score(p) >= toWin then return true end
    end
    return false
end
HANDLERS.game_over = function() finishMatch("game over") end

HANDLERS.player_quit = function(inc)
    if type(inc.cause) ~= "number" or inc.cause < 0 then return end
    eventLine(inc.cause, "Left", FEED.words, "left the game")
    stats(inc.cause).left = true
    stats(inc.cause).leftName = stats(inc.cause).name
    stats(inc.cause).biped = nil
    boardDirty = true
end

HANDLERS.player_booted_player = function(inc)
    if type(inc.effect) ~= "number" or inc.effect < 0 then return end
    eventLine(inc.effect, "Kicked", FEED.kicked, "was kicked")
    stats(inc.effect).left = true
    stats(inc.effect).leftName = stats(inc.effect).name
    stats(inc.effect).biped = nil
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

--- What the simulation says differently for an AI: a player who kills a bot
--- raises `Kill` but no `death`, and a bot that kills a player raises the
--- player's `death` but no `Kill`.
local function botIncident(inc)
    if inc.name == "kill" and Bots.isBot(inc.effect) then
        local p = stats(inc.effect)
        p.deaths = p.deaths + 1
        p.dead = true
        Bots.died(inc.effect, now())
        boardDirty = true
    elseif inc.name == "death" and Bots.isBot(inc.cause) and type(inc.effect) == "number" and inc.effect >= 0 then
        HANDLERS.kill(inc)
    end
end

--- The bots' names to each fireteam player who has not had them yet: a new
--- name (a bot placed for the first time) or a player who just arrived.
local function syncBotNames()
    if not (Match and Match.host and Bots.active()) then return end
    local seats = Bots.seats()
    if #seats == 0 then return end
    local message = Relay.encodeBots(seats)
    pcall(Relay.syncBots, message, message)
end

local function drain()
    local queued = Queue
    Queue = {}
    local outgoing = {}
    local held = {}
    for _, inc in ipairs(queued) do
        -- A client's first bot line waits (3 s at most) for the bots' names.
        local unnamed = Match and not Match.host and not Match.botsHeard and inc.relayed
            and (Bots.isBot(inc.cause) or Bots.isBot(inc.effect)) and now() - (inc.at or 0) < 3
        if unnamed then
            askBotNames()
            held[#held + 1] = inc
            goto continue
        end
        -- A host ignores the relay it sends (its own ClientMessage hook sees
        -- it); anyone takes an incident once, from its handler or a relay
        -- (Scripts/relay.lua).
        local skip = not Match or (inc.relayed and Match.host)
        -- A client with bots in its match hears a bot's kills and deaths
        -- from the host by seat; its own copies name the AI as -1.
        if not skip and not inc.relayed and not Match.host and Match.botsHeard
            and (inc.name == "kill" or inc.name == "death") and (inc.cause == -1 or inc.effect == -1) then
            skip = true
        end
        if not skip and Bots.active() then
            -- An AI's incidents name it by player index -1 and its biped.
            if inc.cause == -1 then inc.cause = Bots.seatOf(inc.biped) or -1 end
            if inc.effect == -1 then inc.effect = Bots.seatOf(inc.victimBiped) or -1 end
        end
        if not skip and Relay.carried(inc.name) then
            skip = Relay.seen(Match.recent, inc)
            if not skip and not inc.relayed and Match.host and not Match.over then outgoing[#outgoing + 1] = inc end
        end
        -- After the end the tallies are final: the round the game resets in
        -- place behind the standings must not score.
        if not skip and not Match.over and not inc.relayed then logSafely("incident", MatchLog.incident, inc) end
        local handler = not skip and not Match.over and HANDLERS[inc.name]
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
        if not skip and not Match.over then
            local ok, err = pcall(botIncident, inc)
            if not ok then Log("bots: " .. tostring(err)) end
        end
        ::continue::
    end
    for _, inc in ipairs(held) do Queue[#Queue + 1] = inc end
    if not Match then return end
    if #outgoing > 0 then
        -- A joiner has the bots' names before the first line that needs them.
        syncBotNames()
        local ok, sent = pcall(Relay.send, outgoing)
        if not ok then
            Log("relay: " .. tostring(sent))
        elseif sent > 0 and not Match.relayed then
            Match.relayed = true
            Log("relay: the feed to " .. tostring(sent) .. " player(s)")
        end
    end
    if #Match.medals > 0 then announceMedals() end
    if botScoreReached() then finishMatch("round over") end
    -- Deaths no kill or suicide line explained: a fall, the guardians.
    local t = now()
    local keep = {}
    for _, d in ipairs(Match.deaths) do
        local p = stats(d.victim)
        local explained = p.lastLine and p.lastLine >= d.at - DEATH_GRACE
        if not explained then
            if t - d.at >= DEATH_GRACE then
                local kind = Icons.damageType(d.damage)
                local glyph, words = "Skull", "died"
                if kind == "FallingDamage" then
                    glyph, words = "Fall", "fell to their death"
                elseif kind == "KnownGuardians" then
                    glyph, words = "Guardians", "was taken by the Guardians"
                elseif kind == "Teleporter" then
                    glyph, words = "Telefrag", "was telefragged"
                end
                eventLine(d.victim, glyph, FEED.words, words)
            else
                keep[#keep + 1] = d
            end
        end
    end
    Match.deaths = keep
end

--- What a fireteam client hears from its host: the feed's incidents
--- (Scripts/relay.lua), and the medals MJOLNIRLevelLoader relays for their
--- sounds (from a host whose HUD is older). drain takes each incident once.
--- The host's bot names (Relay.syncBots sends them once): kept until this
--- machine's match is up, which can be after the host sees it arrive.
local HeardBots = nil

local function applyBotNames()
    if not (HeardBots and Match) or Match.host then return end
    for seat, name in pairs(HeardBots) do
        local p = stats(seat)
        if p.name ~= name then
            p.name, p.bot = name, true
            boardDirty = true
        end
    end
    Match.botsHeard = true
end

local function relayed(text)
    local roster = Relay.decodeBots(text)
    if roster then
        HeardBots = roster
        applyBotNames()
        return
    end
    local batch = Relay.decode(text, now())
    if batch then
        for _, inc in ipairs(batch) do
            if #Queue < 64 then Queue[#Queue + 1] = inc end
        end
        return
    end
    local name, cause, value, effect = text:match("^MJOLNIR|event|([%w_]+)|(-?%d+)|(-?%d+)|(-?%d+)$")
    if not name or not MEDALS[name] or #Queue >= 64 then return end
    Queue[#Queue + 1] = { name = name, cause = tonumber(cause), value = tonumber(value), effect = tonumber(effect),
        at = now(), relayed = true, source = "sound" }
end

--------------------------------------------------------------------------------
-- Drawing
--------------------------------------------------------------------------------

--- The respawn countdown: RESPAWN IN over the seconds left, each new number
--- popping in; RESPAWNING before the first tick.
local function drawRespawn()
    if not (Feed and Feed:IsValid()) then return end
    local t = now()
    -- A fireteam client does not always get the respawn's final tick or its
    -- spawn: the countdown stuck at "Respawn in 1" after the player was
    -- back (two PCs, 2026-10-02). The ticks are a second apart and the
    -- respawn takes five.
    if Match.dead and ((Match.lastRespawnTick and t - Match.lastRespawnTick > 2.5) or
            (Match.diedAt and t - Match.diedAt > 10)) then
        Match.dead = false
    end
    local count, label = "", ""
    if Match.dead then
        local ticks = Match.respawnTicks or 0
        if ticks > 0 then
            count, label = tostring(math.max(1, 4 - ticks)), "RESPAWN IN"
        else
            label = "RESPAWNING"
        end
    end
    if count == Match.respawnShown and label == Match.respawnLabel then return end
    Match.respawnShown, Match.respawnLabel = count, label
    if Match.legacyFeed then
        -- An older UI container: one line of text, as before.
        setText(Feed.Respawn, label == "" and "" or (count == "" and "Respawning" or "Respawn in " .. count))
        return
    end
    setVisible(Feed.RespawnBox, label ~= "")
    setText(Feed.RespawnLabel, label)
    setText(Feed.Respawn, count)
    if count ~= "" then Anim.value(Match.anim, "Respawn", count, t) end
end

--- One frame of everything that moves: the feed's rows, the medal callout,
--- the score bars and the numbers that pop. Run by the per-frame hook and by
--- the poll; every pose depends only on the time.
--- A UI container from before the feed's rows (an older CE runtime) has
--- six text lines, Line0..5: the lines go there as text, newest at the
--- bottom, and nothing moves.
local function drawLegacy(t)
    Rows.step(Match.feed, t)
    local entries = Match.feed.entries
    for i = 0, 5 do
        local e = entries[#entries - 5 + i]
        local text = ""
        if e then
            text = (e.lead or "") .. (e.label and ("  [" .. e.label .. "]  ") or " ") .. (e.tail or "")
        end
        setText(Feed["Line" .. i], text)
        pcall(function() Feed["Line" .. i]:SetColorAndOpacity({ SpecifiedColor = e and e.you and YOU or WHITE, ColorUseRule = 0 }) end)
    end
end

local function animate(t)
    if not (Match and Feed and Feed:IsValid()) then return end
    if Match.legacyFeed then return drawLegacy(t) end
    Rows.draw(Match.feed, Feed, t, Icons)
    local a = Match.anim
    local wasShowing = a.call ~= nil
    Anim.nextCall(a, t)
    local c, scale, alpha = Anim.callPose(a, t)
    if c then
        if c.fresh then
            c.fresh = false
            setText(Feed.CalloutTitle, c.title)
            setText(Feed.CalloutSub, c.sub or "")
            setVisible(Feed.CalloutSub, (c.sub or "") ~= "")
            pcall(function()
                Feed.CalloutTitle:SetColorAndOpacity({ SpecifiedColor = c.color or WHITE, ColorUseRule = 0 })
                local tex = Icons.glyph(c.glyph)
                if tex then
                    Feed.CalloutIcon:SetBrushFromTexture(tex, false)
                    Feed.CalloutIcon:SetColorAndOpacity(c.color or WHITE)
                end
                Feed.CalloutIconBox:SetVisibility(tex and VISIBLE or COLLAPSED)
            end)
            setVisible(Feed.Callout, true)
        end
        pcall(function()
            Feed.Callout:SetRenderScale({ X = scale, Y = scale })
            Feed.Callout:SetRenderOpacity(alpha)
        end)
    elseif wasShowing then
        setVisible(Feed.Callout, false)
    end
    local busy = Anim.busy(a, t)
    if not (busy or a.wasBusy) then return end
    a.wasBusy = busy
    for _, side in ipairs({ "Left", "Right" }) do
        local s = Anim.scale(a, side, t)
        pcall(function()
            Feed["Score" .. side .. "Fill"]:SetWidthOverride(SCORE_TRACK * Anim.barAt(a, side, t))
            Feed["Score" .. side .. "Value"]:SetRenderScale({ X = s, Y = s })
        end)
    end
    local s = Anim.scale(a, "Respawn", t)
    pcall(function() Feed.Respawn:SetRenderScale({ X = s, Y = s }) end)
end

--- `mjolnir_scoreboard on` keeps the board up (two-PC tests, screenshots).
local BoardPin = { on = false }

local function boardHeld(pc)
    if BoardPin.on then return true end
    local held = false
    for _, key in ipairs({ "Tab", "Gamepad_Special_Left" }) do
        local ok, down = pcall(function() return pc:IsInputKeyDown({ KeyName = FName(key) }) end)
        if ok and down then held = true end
    end
    return held
end

local function drawScoreStrip()
    if not (Feed and Feed:IsValid()) then return end
    -- A FORGE game (MJOLNIRForge) keeps no score: no strip.
    if Match.variant == "forge" then
        setVisible(Feed.MatchScore, false)
        return
    end
    local summary = Scoreboard.summary(Match, LOCAL_PLAYER)
    setText(Feed.ScoreLeftLabel, summary.leftLabel)
    setText(Feed.ScoreRightLabel, summary.rightLabel)
    setText(Feed.ScoreTarget, tostring(Match.mode.toWin))
    -- Each bar fills toward the score to win; a new score eases in and its
    -- number pops (animate). The feed demo holds its own for a while.
    local t, toWin = now(), math.max(1, Match.mode.toWin or 1)
    if not (Match.demoUntil and t < Match.demoUntil) then
        setText(Feed.ScoreLeftValue, tostring(summary.left))
        setText(Feed.ScoreRightValue, tostring(summary.right))
        Anim.bar(Match.anim, "Left", (tonumber(summary.left) or 0) / toWin, t)
        Anim.bar(Match.anim, "Right", (tonumber(summary.right) or 0) / toWin, t)
        Anim.value(Match.anim, "Left", summary.left, t)
        Anim.value(Match.anim, "Right", summary.right, t)
        Match.anim.wasBusy = true
    end
    for _, side in ipairs({ "Left", "Right" }) do
        local team = summary[string.lower(side) .. "Team"]
        local color = TEAM_COLORS[team] or (side == "Left" and YOU or TEAM_COLORS.Unassigned)
        pcall(function()
            Feed["Score" .. side .. "Accent"]:SetBrushColor(color)
            Feed["Score" .. side .. "Label"]:SetColorAndOpacity({ SpecifiedColor = color, ColorUseRule = 0 })
        end)
    end
end

--- The clock under TO WIN, `M:SS`, redrawn only when it changes; hidden
--- with no time limit (and in a runtime pack from before it, which has no
--- MatchClock).
local function drawClock()
    if not (Feed and Feed:IsValid()) then return end
    local text = ""
    if Match.clockEnd and not Match.over then
        local left = math.max(0, math.ceil(Match.clockEnd - now()))
        text = string.format("%d:%02d", math.floor(left / 60), left % 60)
    end
    if text == Match.clockText then return end
    Match.clockText = text
    setText(Feed.MatchClock, text)
    setVisible(Feed.MatchClock, text ~= "")
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
            local name = p and (p.display or p.name or ("Player " .. tostring(p.index + 1))) or
                ((team == "Unassigned" and "AWAITING ASSIGNMENT" or string.upper(team) .. " TEAM") ..
                    "  /  " .. tostring(entry.count))
            setText(Board["Name" .. i], name)
            -- The hub avatar; a board from an older UI container has none.
            local okA, image = pcall(function() return Board["Avatar" .. i] end)
            if okA and image and image:IsValid() then
                local tex = p and HubNames.avatar(p.userId, playerController())
                pcall(function()
                    if tex then image:SetBrushFromTexture(tex, false) end
                    image:SetVisibility(tex and VISIBLE or 2)
                end)
            end
            -- Dead until the next spawn (#249); a player nothing was heard of
            -- yet (joined mid-match) counts as alive.
            local dead = p and p.dead
            setText(Board["Marker" .. i], dead and "DEAD" or (you and "YOU" or ""))
            setText(Board["Score" .. i], p and tostring(score(p)) or (entry.total and tostring(entry.total) or ""))
            setText(Board["Kills" .. i], p and tostring(p.kills) or "")
            setText(Board["Deaths" .. i], p and tostring(p.deaths) or "")
            local color = you and ROW_YOU or ((i % 2 == 0) and ROW_EVEN or ROW_ODD)
            if tint then color = { R = tint.R, G = tint.G, B = tint.B, A = entry.team and 0.24 or (you and 0.20 or 0.06) } end
            pcall(function()
                row:SetBrushColor(color)
                row.Slot:SetPadding({ Left = 0, Top = entry.team and 12 or 2, Right = 0, Bottom = 0 })
                Board["Stripe" .. i]:SetBrushColor(tint or (you and YOU or ROW_EVEN))
                local nameTint = entry.team and tint or WHITE
                if dead then nameTint = { R = nameTint.R, G = nameTint.G, B = nameTint.B, A = 0.45 } end
                Board["Name" .. i]:SetColorAndOpacity({ SpecifiedColor = nameTint, ColorUseRule = 0 })
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
local ClockTold = {}  -- { seconds remaining, when heard } from the host
-- How often the host tells its fireteam the round clock, for players who
-- joined mid-match and have no first spawn to count from. The controllers
-- are the relay's (Scripts/relay.lua), found without a scan each time.
local CLOCK_SHARE_SECONDS = 30

local function isHostWorld(pc)
    local ok, yes = pcall(function() return pc:GetWorld().AuthorityGameMode:IsValid() end)
    return ok and yes == true
end

local function hookMatchLog()
    if logHooked then return end
    logHooked = pcall(function()
        RegisterHook("/Script/Engine.PlayerController:ServerExecRPC", function(self, msg)
            local okM, text = pcall(function() return msg:get():ToString() end)
            if okM and Chat.heardSay(self:get(), text) then return end
            -- A fireteam player asking for the bots' names (Relay.BOTS_ASK).
            if okM and text == Relay.BOTS_ASK then
                local asker = self:get()
                ExecuteInGameThread(function()
                    if not (Match and Match.host and Bots.active() and asker:IsValid()) then return end
                    local seats = Bots.seats()
                    if #seats == 0 then return end
                    pcall(function() asker:ClientMessage(Relay.encodeBots(seats), FName("MJOLNIR"), 0) end)
                end)
                return
            end
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
            if okS and Chat.heardLine(text) then return end
            if okS and type(text) == "string" and text:sub(1, 14) == "MJOLNIR|match|" and #Told < 8 then
                Told[#Told + 1] = text
            end
            -- The round clock from the host: its own count every
            -- CLOCK_SHARE_SECONDS, and the engine's countdown incidents
            -- MJOLNIRLevelLoader relays.
            local remaining = okS and type(text) == "string" and (tonumber(text:match("^MJOLNIR|clock|([%d%.]+)$") or "")
                or (text:match("^MJOLNIR|event|30_seconds_remaining|") and 30)
                or (text:match("^MJOLNIR|event|10_seconds_remaining|") and 10))
            if remaining and #ClockTold < 8 then ClockTold[#ClockTold + 1] = { remaining, now() } end
            if okS and type(text) == "string" then relayed(text) end
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
    -- The round clock: a client takes the host's; the host shares its own.
    local clock = ClockTold
    ClockTold = {}
    local host = isHostWorld(pc)
    if not host then
        for _, c in ipairs(clock) do clockFrom(c[1], c[2]) end
    elseif Match.clockEnd and not Match.over and now() >= (Match.nextClockShare or 0) then
        Match.nextClockShare = now() + CLOCK_SHARE_SECONDS
        local msg = string.format("MJOLNIR|clock|%.1f", math.max(0, Match.clockEnd - now()))
        local kind = FName("MJOLNIR")
        for _, other in ipairs(Relay.controllers()) do
            pcall(function() other:ClientMessage(msg, kind, 0) end)
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
        if p.name == name or (p.display and p.display == name) then return p.team end
    end
    return nil
end

--- A shown tag names the hub account in place of the in-game name.
local function hubTag(tag, name)
    local hub = HubNames.of(name)
    if hub and hub.name ~= name then
        pcall(function() tag.PlayerNameValue:SetText(FText(hub.name)) end)
    end
end

--- Whether the game's HUD is shown: the HUD actor's bShowHUD, which
--- MJOLNIRFlyCam's F7 (and anything else that hides the HUD) turns off.
--- Our widgets follow it, so a screenshot without the game's HUD has none of
--- ours either.
local HudHidden = false

local function hudShown(pc)
    local ok, shown = pcall(function() return pc.MyHUD.bShowHUD end)
    return not ok or shown ~= false
end

local function applyTag(tag)
    if not Match then return end
    local show = false
    if Match.mode.teams and not HudHidden then
        local okN, name = pcall(function() return tag.PlayerNameValue:GetText():ToString() end)
        local mine = Match.players[LOCAL_PLAYER] and Match.players[LOCAL_PLAYER].team
        show = okN and mine ~= nil and teamOfName(name) == mine
        if show then hubTag(tag, name) end
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

--- The game type: the HUD's model of it, with the score to win and the time
--- limit read from the variant the simulation loads rather than assumed.
--- That is the level loader's staged copy (native\variant.mglo), which holds
--- the host's game settings; the installed variants/<mode>.mglo before one
--- is staged.
local function modeFor(variant)
    local mode = {}
    for k, v in pairs(MODES[variant] or MODES.slayer) do mode[k] = v end
    local name = tostring(variant or ""):match("^[%w_]+$")
    local bytes = readFile(LOADER_DIR .. "\\native\\variant.mglo")
        or (name and readFile(LOADER_DIR .. "\\variants\\" .. name .. ".mglo"))
    local toWin = Variant.scoreToWin(bytes)
    if toWin and toWin > 0 then mode.toWin = toWin end
    mode.timeLimit = Variant.timeLimit(bytes) or 0
    return mode
end

local function startMatch(running, world)
    Match = {
        code = running.code,
        variant = running.variant,
        title = running.title,
        mode = modeFor(running.variant),
        players = {},
        feed = Rows.new(),
        anim = Anim.new(),
        medals = {},
        recent = {},
        deaths = {},
        teams = { [0] = 0, [1] = 0 },
        teamKills = {},
        world = world,
        startedAt = now(),
        presenceStarted = os.time(),
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
    -- Bot names heard while this match was still loading (a host's next
    -- match replaces them as soon as it is up).
    applyBotNames()
end

--- The widgets, once the map's world is up: created too early (while the
--- level is still loading) Create returns nothing, so this retries each
--- second until both exist.
local nextWidgetTry = 0
local widgetTries = 0

--- The game's own faces on the feed's text, at the sizes the widget was
--- built with (build_mjolnir_ui.py): Oxanium, the menus' squared face, for
--- numbers and captions; Normative Pro for names. Without them (another
--- game build) the cooked Roboto stays.
local FONT_ROLES = {
    { "FeedLead", "NormativePro", "Bold", 0, true }, { "FeedTail", "NormativePro", "Bold", 0, true },
    { "FeedNote", "NormativePro", "Medium", 0, true },
    { "CalloutTitle", "Oxanium", "ExtraBold", 60 }, { "CalloutSub", "NormativePro", "Medium", 0 },
    { "RespawnLabel", "Oxanium", "Bold", 220 }, { "Respawn", "Oxanium", "Bold", 0 },
    { "ScoreLeftLabel", "Oxanium", "Bold", 90 }, { "ScoreRightLabel", "Oxanium", "Bold", 90 },
    { "ScoreLeftValue", "Oxanium", "ExtraBold", 0 }, { "ScoreRightValue", "Oxanium", "ExtraBold", 0 },
    { "MatchClock", "Oxanium", "SemiBold", 40 }, { "ScoreTargetLabel", "Oxanium", "Bold", 160 },
    { "ScoreTarget", "Oxanium", "Bold", 40 },
}

local function applyFonts(w)
    local fonts = {}
    for _, role in ipairs(FONT_ROLES) do
        local name, family, face, spacing, perRow = role[1], role[2], role[3], role[4], role[5]
        if fonts[family] == nil then fonts[family] = Icons.font(family) or false end
        local font = fonts[family]
        local blocks = {}
        if perRow then
            for i = 0, Rows.ROWS - 1 do blocks[#blocks + 1] = w[name .. i] end
        else
            blocks[1] = w[name]
        end
        for _, block in ipairs(blocks) do
            if font then
                pcall(function()
                    local size = block.Font.Size
                    if type(size) ~= "number" then return end
                    block:SetFont({ FontObject = font, TypefaceFontName = FName(face), Size = size,
                        LetterSpacing = spacing, SkewAmount = 0, OutlineSettings = { OutlineSize = 0 } })
                end)
            end
        end
    end
end

local function ensureWidgets()
    if Feed and Feed:IsValid() and Board and Board:IsValid() then return end
    if now() < nextWidgetTry then return end
    nextWidgetTry = now() + 1
    widgetTries = widgetTries + 1
    if not (Feed and Feed:IsValid()) then
        Feed = createWidget(FEED_CLASS, 40)
        if Feed then
            setText(Feed.Watermark, BuildLine.text(MOD_DIR:match("^(.*)\\[^\\]*$") or MOD_DIR))
            applyFonts(Feed)
            if HudHidden then setVisible(Feed, false) end
            local okE, edge = pcall(function() return Feed.FeedEdge0 end)
            local okV, isRow = pcall(function() return edge:IsValid() end)
            if Match then Match.legacyFeed = not (okE and okV and isRow) end
            if Match and Match.legacyFeed then
                Log("the UI container has no feed rows (an older CE runtime): text feed")
            end
            -- A new widget starts bare: the rows come back from the model.
            if Match then
                Match.feed = Rows.new()
                Match.respawnShown, Match.respawnLabel = nil, nil
                boardDirty = true
            end
        end
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

--- Every frame, the feed and the bars move (animate). The poll runs ten
--- times a second; animation needs the frame, so this hooks the game's
--- player controller tick, as MJOLNIRFlyCam does. The hook is never
--- removed (tearing a trampoline out of a hot per-frame function crashed the
--- game); a level change collects the hooked function, so each new one is
--- hooked again. A host's tick runs once per player controller each frame:
--- the second call in a frame does nothing. The same hook times every frame
--- for the hitch log (Scripts/hitches.lua), on every map, match or not.
local TICK_FUNCTION = "/Game/Blueprints/BP_MeteoritePlayerController.BP_MeteoritePlayerController_C:ReceiveTick"
local FrameHook = { fn = nil, last = -1, errors = 0, hitchErrors = 0, nextTry = 0 }

local function ensureFrameHook()
    if FrameHook.fn and FrameHook.fn:IsValid() then return end
    -- Finding the function by path costs ~2 ms: not every poll.
    if now() < FrameHook.nextTry then return end
    FrameHook.nextTry = now() + 5
    local ok, fn = pcall(StaticFindObject, TICK_FUNCTION)
    if not (ok and fn) then return end
    local okValid, isValid = pcall(function() return fn:IsValid() end)
    if not (okValid and isValid) then return end
    local hooked = pcall(RegisterHook, TICK_FUNCTION, function(ctx)
        local t = now()
        if FrameHook.hitchErrors < 10 then
            local okH, errH = pcall(Hitches.frame, ctx, t)
            if not okH then
                FrameHook.hitchErrors = FrameHook.hitchErrors + 1
                if FrameHook.hitchErrors == 10 then Log("hitch log off after repeated errors: " .. tostring(errH)) end
            end
        end
        if t - FrameHook.last < 0.004 or FrameHook.errors >= 10 then return end
        FrameHook.last = t
        local okA, err = pcall(animate, t)
        if okA and Match then okA, err = pcall(Chat.frame, t) end
        if not okA then
            FrameHook.errors = FrameHook.errors + 1
            if FrameHook.errors == 10 then Log("frame animation off after repeated errors: " .. tostring(err)) end
        end
    end)
    if hooked then
        FrameHook.fn = fn
        Log("frame hook armed")
    end
end

local function endMatch()
    local okChat, errChat = pcall(Chat.finish)
    if not okChat then Log("chat: " .. tostring(errChat)) end
    if Match and MatchLog.recording() then
        logSafely("finish", MatchLog.finish, Match, Scoreboard, LOCAL_PLAYER, "abandoned", now())
    end
    Bots.stop()
    widgetTries = 0
    if Feed and Feed:IsValid() then setVisible(Feed, false) end
    if Board and Board:IsValid() then setVisible(Board, false) end
    Match, Feed, Board = nil, nil, nil
    Queue = {}
end

--- `mjolnir_feed_demo` (Scripts/demo.lua): the feed's lines, a medal and the
--- bars, played through the HUD's own drawing with made-up names. Nothing it
--- shows is counted.
local DemoRun = { steps = nil, at = 0 }

local function demoTick()
    if not (DemoRun.steps and Match) then return end
    local t = now()
    local left = {}
    for _, s in ipairs(DemoRun.steps) do
        if t - DemoRun.at < s[1] then
            left[#left + 1] = s
        else
            local you = s[3] == "YOU"
            local lead = you and short(nameOf(LOCAL_PLAYER)) or s[3]
            local leadColor = you and YOU or FEED.name
            local leadAvatar = you and avatarOf(LOCAL_PLAYER) or nil
            if s[2] == "kill" then
                local shown = Icons.forKill(s[5], s[6])
                local victimYou = s[4] == "YOU"
                feedPush({ lead = lead, leadColor = leadColor, leadAvatar = leadAvatar,
                    weapon = shown.weapon, weaponGlyph = shown.glyph,
                    mod = shown.mod, modColor = shown.mod == "Headshot" and FEED.headshot or nil,
                    tail = victimYou and short(nameOf(LOCAL_PLAYER)) or s[4], tailColor = victimYou and YOU or FEED.name,
                    tailAvatar = victimYou and avatarOf(LOCAL_PLAYER) or nil,
                    note = shown.note, noteColor = FEED.words, accent = leadColor, you = you or victimYou })
            elseif s[2] == "medal" or s[2] == "event" then
                local c = FEED[s[5]]
                if s[2] == "medal" then
                    feedPush({ glyph = s[5], glyphColor = FEED[s[6]], lead = lead, leadColor = leadColor,
                        leadAvatar = leadAvatar, tail = s[4], tailColor = FEED[s[6]], accent = FEED[s[6]], you = you })
                    if you then
                        Anim.callout(Match.anim, { title = string.upper(s[4]), glyph = s[5], color = FEED[s[6]] }, t)
                    end
                else
                    feedPush({ glyph = s[4], glyphColor = c, lead = lead, leadColor = leadColor, tail = s[6],
                        tailColor = FEED.words, accent = c, you = you })
                end
            elseif s[2] == "respawn" then
                if s[3] == "dead" then
                    Match.dead, Match.respawnTicks, Match.diedAt, Match.lastRespawnTick = true, 0, t, nil
                elseif s[3] == "tick" then
                    Match.respawnTicks, Match.lastRespawnTick = (Match.respawnTicks or 0) + 1, t
                else
                    Match.dead = false
                end
            elseif s[2] == "bars" then
                Anim.bar(Match.anim, "Left", s[3], t); Anim.value(Match.anim, "Left", s[4], t)
                Anim.bar(Match.anim, "Right", s[5], t); Anim.value(Match.anim, "Right", s[6], t)
                setText(Feed.ScoreLeftValue, tostring(s[4])); setText(Feed.ScoreRightValue, tostring(s[6]))
            end
        end
    end
    DemoRun.steps = #left > 0 and left or nil
end

--- Whether the actor at `address` is a player's biped (their spawns name
--- it): a Spartan bot is the players' own class.
local function isPlayerBiped(address)
    for index, p in pairs(Match and Match.players or {}) do
        if index <= 15 and p.biped then
            local ok, at = pcall(function() return p.biped:GetAddress() end)
            if ok and at == address then return true end
        end
    end
    return false
end

--- Bots for this match (Scripts/bots.lua): each gets a seat on the board
--- under its name, and is alive again each time it is placed (an AI raises
--- no `player_spawn`).
local function startBots(count, kind)
    Bots.stop()
    if not (Match and Match.host) or count <= 0 then return end
    Bots.begin(count, now(), function(index, name)
        local p = stats(index)
        p.name, p.bot, p.dead, p.left = name, true, false, nil
        boardDirty = true
    end, kind or Bots.wantedKind(LOADER_DIR), isPlayerBiped)
end

--- The host changes how many bots play (`/bots`, `mjolnir_bots`): the ones
--- playing stay, new ones are placed, the last ones past `count` leave.
--- Returns what to tell the host.
local function setBots(count, kind)
    if not (Match and Match.host) then return "Only the host can change the bots." end
    count = math.max(0, math.min(math.floor(count), 15))
    if kind or not Bots.active() then
        -- Another kind: the bots there are leave, the new ones come in.
        for _, seat in ipairs(Bots.seats()) do
            local p = stats(seat.index)
            -- The seat is someone else's when it is taken again.
            p.left, p.kills, p.rawKills, p.deaths, p.suicides = true, 0, 0, 0, 0
        end
        startBots(count, kind)
    else
        for _, index in ipairs(Bots.resize(count, now())) do
            stats(index).left = true
        end
        if count == 0 then Bots.stop() end
    end
    boardDirty = true
    if count == 0 then return "No bots." end
    return string.format("%d bot(s). Maps built without bot squads have none.", count)
end

--- `mjolnir_bots <n>`: this match's bots, as `/bots <n>` in chat sets them
--- (the host's game settings set the number each match starts with).
pcall(RegisterConsoleCommandHandler, "mjolnir_bots", function(_, args, ar)
    local n = tonumber(args and args[1]) or 0
    ExecuteInGameThread(function() Log("bots: " .. setBots(n)) end)
    pcall(function() ar:Log("MJOLNIR HUD: " .. n .. " bot(s)") end)
    return true
end)

pcall(RegisterConsoleCommandHandler, "mjolnir_feed_demo", function(_, _, ar)
    local Demo = dofile(MOD_DIR .. "\\Scripts\\demo.lua")
    ExecuteInGameThread(function()
        if not Match then return end
        DemoRun.steps, DemoRun.at, Match.demoUntil = {}, now(), now() + Demo.SECONDS
        for _, s in ipairs(Demo.STEPS) do DemoRun.steps[#DemoRun.steps + 1] = s end
    end)
    pcall(function() ar:Log("MJOLNIR HUD: feed demo started") end)
    return true
end)

local function tick()
    local pc = playerController()
    local world = pc and pc:GetWorld()
    local code = world and scenarioOf(world)
    local okHitches, timed = pcall(Hitches.poll, pc, code)
    if not okHitches then
        Log("hitch log: " .. tostring(timed))
    elseif timed then
        ensureFrameHook()
    end
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
        publishPresence(nil, LOCAL_PLAYER)
        return
    end
    hookIncidents()
    ensureWidgets()
    ensureFrameHook()
    refreshLocalPlayer()
    Match.host = isHostWorld(pc)
    -- The host finds its fireteam's controllers once, then as they come; a
    -- few seconds in, off the tick that makes the widgets.
    if Match.host and not Match.relayArmed and now() - Match.startedAt > 3 then
        Match.relayArmed = true
        pcall(Relay.arm)
    end
    if Match.host and not Match.botsChecked and now() - Match.startedAt > 3 then
        Match.botsChecked = true
        startBots(Bots.wanted(LOADER_DIR))
    end
    local humans = 0
    for index, p in pairs(Match.players) do
        if index >= 0 and index <= 15 and not p.left then humans = humans + 1 end
    end
    local okBots, errBots = pcall(Bots.tick, now(), humans)
    if not okBots then Log("bots: " .. tostring(errBots)) end
    if now() >= (Match.nextBotRoster or 0) then
        Match.nextBotRoster = now() + 1
        syncBotNames()
    end
    if now() >= nextRosterRefresh then
        nextRosterRefresh = now() + 1
        refreshNames()
        boardDirty = true
    end
    if Match.joins and #Match.joins > 0 then announceJoins() end
    -- Before the drain: the host's log is recording by the first incident.
    logSafely("tick", matchLogTick, pc)
    local okChat, errChat = pcall(Chat.tick, Match)
    if not okChat then Log("chat: " .. tostring(errChat)) end
    drain()
    publishPresence(presencePlayerKnown and Match or nil, LOCAL_PLAYER)
    demoTick()
    if Match.demoUntil and now() >= Match.demoUntil then
        Match.demoUntil = nil
        boardDirty = true
    end
    sweepTags()
    drawRespawn()
    drawClock()
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
        setVisible(Board, held and not HudHidden)
        if Feed and Feed:IsValid() then setVisible(Feed.MatchScore, not held and Match.variant ~= "forge") end
    end
    -- The game's HUD hidden (MJOLNIRFlyCam's F7): ours goes with it, and
    -- comes back as it was.
    local hidden = not hudShown(pc)
    if hidden ~= HudHidden then
        HudHidden = hidden
        if Feed and Feed:IsValid() then setVisible(Feed, not hidden) end
        if Board and Board:IsValid() then setVisible(Board, boardShown and not hidden) end
        for address, tag in pairs(Tags) do
            if tag:IsValid() then applyTag(tag) else Tags[address] = nil end
        end
    end
    if boardDirty then
        boardDirty = false
        drawScoreStrip()
        if boardShown then drawBoard() end
    end
    -- The per-frame hook animates between polls; the poll draws too, so the
    -- HUD still moves (at its rate) if the hook never armed.
    animate(now())
    pcall(Chat.frame, now())
end

-- The Lua collector in generational mode. The HUD keeps ~0.5 MB but makes
-- ~350 KB of garbage a second (object handles, at every frame and poll), and
-- the incremental collector finished a cycle every ~15 s by sweeping ~5 MB of
-- it in one step: a 4-6 ms tick every 15 s, standing still (MJOLNIRHud hitch
-- log, 2026-10-18). Young collections take what was made since the last:
-- the worst tick was 2-3 ms. UE4SS ships Lua 5.4.7.
pcall(collectgarbage, "generational")

--- A tick that holds the game thread past 50 ms is logged (at most every
--- 30 s): a CTF host froze ~250 ms every 3.24 s in Lua, and nothing said
--- which mod's loop it was (playtest, 2026-10-03).
local slowReportedAt = -100
local function poll()
    local started = os.clock()
    local ok, err = pcall(tick)
    if not ok then Log("tick: " .. tostring(err)) end
    local took = os.clock() - started
    Hitches.work("Hud", "tick", started, took)
    if took > 0.05 and started - slowReportedAt > 30 then
        slowReportedAt = started
        Log(string.format("slow: the HUD tick held the game thread %.0f ms", took * 1000))
    end
    ExecuteInGameThreadWithDelay(POLL_MS, poll)
end

pcall(RegisterConsoleCommandHandler, "mjolnir_scoreboard", function(_, args, ar)
    local on = tostring(args and args[1] or ""):lower()
    BoardPin.on = on == "on" or on == "1"
    pcall(function() ar:Log("MJOLNIR HUD: scoreboard " .. (BoardPin.on and "kept up" or "on Tab")) end)
    return true
end)

pcall(RegisterConsoleCommandHandler, "mjolnir_hitches", function(_, args, ar)
    ExecuteInGameThread(function()
        local okC, said = pcall(Hitches.command, args)
        Log(okC and said or ("mjolnir_hitches: " .. tostring(said)))
    end)
    pcall(function() ar:Log("MJOLNIR HUD: see UE4SS.log") end)
    return true
end)

pcall(RegisterConsoleCommandHandler, "mjolnir_bench", function(_, args, ar)
    ExecuteInGameThread(function()
        local okC, said = pcall(Bench.command, args)
        Log(okC and said or ("mjolnir_bench: " .. tostring(said)))
    end)
    pcall(function() ar:Log("MJOLNIR HUD: see UE4SS.log") end)
    return true
end)

Hitches.init({ log = Log, file = MOD_DIR .. "\\hitches.log", settings = Bench.settings })
-- Benches (Scripts/bench.lua) take their turns on the hitch log's frames.
Bench.init({
    log = Log,
    file = MOD_DIR .. "\\bench.log",
    -- /bench's report goes out as bench_<id>.json through the outbox
    -- MJOLNIRLobby sends match records from.
    dir = MOD_DIR,
    queue = MatchLog.queue,
    version = (readFile(MOD_DIR .. "\\mod.json") or ""):match('"version"%s*:%s*"([^"]+)"'),
    pc = playerController,
    liveFor = Hitches.liveSeconds,
    map = function()
        local pc = playerController()
        return pc and scenarioOf(pc:GetWorld()) or "?"
    end,
})
Hitches.listen(Bench.frame)
-- Match chat (Scripts/chat.lua): what it needs of the match, read as used.
Chat.init({
    dir = MOD_DIR,
    log = Log,
    now = now,
    pc = playerController,
    createWidget = createWidget,
    font = Icons.font,
    match = function() return Match ~= nil end,
    isHost = function() return Match ~= nil and Match.host == true end,
    teams = function() return Match ~= nil and Match.mode.teams == true end,
    localTeam = function()
        return Match and Match.mode.teams and Scoreboard.team(stats(LOCAL_PLAYER).team) or nil
    end,
    teamColor = function()
        return TEAM_COLORS[Match and Scoreboard.team(stats(LOCAL_PLAYER).team) or ""] or FEED.name
    end,
    localName = function()
        local okN, name = pcall(function() return playerController().PlayerState:GetPlayerName():ToString() end)
        return okN and name or nil
    end,
    seatOf = function(name)
        if not (Match and name) then return nil end
        for index, p in pairs(Match.players) do
            if p.name == name then
                local team = Match.mode.teams and Scoreboard.team(p.team) or nil
                return { index = index, team = team, teamName = team and string.lower(team) or nil,
                    display = p.display, userId = p.userId }
            end
        end
        return nil
    end,
    colorOf = function(index, team)
        if team and TEAM_COLORS[team] then return TEAM_COLORS[team] end
        if index == LOCAL_PLAYER then return YOU end
        return FEED.name
    end,
    avatar = function(index) return Match and avatarOf(index) end,
    -- Slash commands (Scripts/commands.lua): the players still in the match,
    -- this machine's seat, and the console the Lobby's kick and ban answer on.
    players = function()
        local out = {}
        for index, p in pairs(Match and Match.players or {}) do
            -- Bots are not players to kick or teleport to.
            if p.name and not p.left and not p.bot then out[#out + 1] = { index = index, name = p.name, display = p.display } end
        end
        return out
    end,
    localIndex = function() return LOCAL_PLAYER end,
    console = function(command)
        local pc = playerController()
        pcall(function()
            StaticFindObject("/Script/Engine.Default__KismetSystemLibrary"):ExecuteConsoleCommand(pc:GetWorld(), command, pc)
        end)
    end,
    controllers = Relay.controllers,
    matchId = function() return MatchLog.currentId() or (Match and Match.logId) end,
    queue = MatchLog.queue,
    hidden = function() return HudHidden end,
    bench = Bench.chat,
    setBots = setBots,
    botCount = function() return Bots.count() end,
})
logSafely("init", MatchLog.init, {
    modDir = MOD_DIR,
    log = Log,
    version = (readFile(MOD_DIR .. "\\mod.json") or ""):match('"version"%s*:%s*"([^"]+)"'),
})

Log("Module loaded.")
ExecuteInGameThreadWithDelay(5000, poll)

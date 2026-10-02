-- MJOLNIR HUD
--
-- The multiplayer HUD for the classic CE maps MJOLNIRLevelLoader runs under
-- the simulation's Megalo engine: a kill feed, the respawn countdown, and a
-- scoreboard while Tab (or the gamepad's View button) is held.
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

local function modDirectory()
    local source = debug.getinfo(1, "S").source or ""
    local root = source:gsub("^@", ""):gsub("/", "\\")
    for _ = 1, 2 do
        root = root:match("^(.*)\\[^\\]*$") or root
    end
    return root
end

local MOD_DIR = modDirectory()
local LOADER_DIR = (MOD_DIR:match("^(.*)\\[^\\]*$") or MOD_DIR) .. "\\MJOLNIRLevelLoader"

local function Log(msg)
    print("[MJOLNIR Hud] " .. tostring(msg) .. "\n")
end

local UI_ROOT = "/Game/MJOLNIR/UI/"
local FEED_CLASS = UI_ROOT .. "WBP_MJOLNIRKillFeed.WBP_MJOLNIRKillFeed_C"
local BOARD_CLASS = UI_ROOT .. "WBP_MJOLNIRScoreboard.WBP_MJOLNIRScoreboard_C"
local INCIDENT_EVENT = "/Game/Blueprints/BPC_MeteoriteIncidentHandlerComponent.BPC_MeteoriteIncidentHandlerComponent_C:OnIncident_Event"

local POLL_MS = 100
local FEED_LINES = 6     -- WBP_MJOLNIRKillFeed's Line0..Line5
local SCORE_ROWS = 16    -- WBP_MJOLNIRScoreboard's Row0..Row15
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

local MODES = {
    slayer = { title = "SLAYER", toWin = 25, unit = "kills" },
    team_slayer = { title = "TEAM SLAYER", toWin = 50, unit = "kills" },
    ctf = { title = "CAPTURE THE FLAG", toWin = 3, unit = "captures", teams = true },
}

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

local function firstValid(list)
    for _, o in ipairs(list or {}) do
        if o and o:IsValid() then return o end
    end
    return nil
end

--- The first local player's controller. FindAllOf also returns the
--- frontend's controllers, left over in a map's world with no player (and
--- listed first), and a split-screen player's.
local function playerController()
    local any = firstValid(FindAllOf("PlayerController"))
    if not any then return nil end
    local ok, pc = pcall(function()
        return StaticFindObject("/Script/Engine.Default__GameplayStatics"):GetPlayerController(any, 0)
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
local boardShown = false
local boardDirty = true

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
    if Match.mode.teams then return p.captures end
    return p.kills
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
    end
    boardDirty = true
end

HANDLERS.respawn_tick = function(inc)
    if inc.cause ~= LOCAL_PLAYER then return end
    Match.respawnTicks = (Match.respawnTicks or 0) + 1
end

HANDLERS.respawn_final_tick = function(inc)
    if inc.cause ~= LOCAL_PLAYER then return end
    Match.dead = false
end

HANDLERS.player_spawn = function(inc)
    if inc.cause == LOCAL_PLAYER then Match.dead = false end
    refreshNames()
    boardDirty = true
end

--- flag_scored: the carrier is the cause; the value is the captured flag's
--- team (0 red, 1 blue), so the point is the other team's (blam_megalo::ctf).
HANDLERS.flag_scored = function(inc)
    if type(inc.cause) == "number" and inc.cause >= 0 then
        stats(inc.cause).captures = stats(inc.cause).captures + 1
    end
    local scorer = (inc.value == 0) and 1 or 0
    Match.teams[scorer] = (Match.teams[scorer] or 0) + 1
    feedLine(nameOf(inc.cause) .. " captured the " .. (TEAM_NAMES[inc.value] or "enemy") .. " flag",
        inc.cause == LOCAL_PLAYER)
    boardDirty = true
end

HANDLERS.player_joined = function(inc)
    refreshNames()
    feedLine(nameOf(inc.cause) .. " joined the game", false)
    boardDirty = true
end

HANDLERS.player_rejoined = HANDLERS.player_joined

HANDLERS.player_quit = function(inc)
    feedLine(nameOf(inc.cause) .. " quit", false)
    boardDirty = true
end

HANDLERS.player_booted_player = function(inc)
    feedLine(nameOf(inc.effect) .. " was booted", false)
    boardDirty = true
end

--- Every incident, queued with what the handlers read. Reading the struct is
--- all the hook does.
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
                pcall(function() entry.damage = i.DamageReportingInfo.Type.TagName:ToString() end)
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
        local handler = Match and HANDLERS[inc.name]
        if handler then
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

local function drawBoard()
    if not (Board and Board:IsValid()) then return end
    local mode = Match.mode
    setText(Board.Title, mode.title .. "  -  " .. string.upper(Match.title or Match.code))
    if mode.teams then
        setText(Board.Subtitle, string.format("Red %d  -  Blue %d      First to %d %s",
            Match.teams[0] or 0, Match.teams[1] or 0, mode.toWin, mode.unit))
    else
        setText(Board.Subtitle, string.format("First to %d %s", mode.toWin, mode.unit))
    end
    setText(Board.ScoreH, mode.teams and "CAPTURES" or "SCORE")
    refreshNames()
    local rows = {}
    for _, p in pairs(Match.players) do rows[#rows + 1] = p end
    table.sort(rows, function(a, b)
        if score(a) ~= score(b) then return score(a) > score(b) end
        if a.kills ~= b.kills then return a.kills > b.kills end
        if a.deaths ~= b.deaths then return a.deaths < b.deaths end
        return a.index < b.index
    end)
    for i = 0, SCORE_ROWS - 1 do
        local p = rows[i + 1]
        local row = Board["Row" .. i]
        if p then
            setVisible(row, true)
            setText(Board["Name" .. i], p.name or ("Player " .. tostring(p.index + 1)))
            setText(Board["Score" .. i], tostring(score(p)))
            setText(Board["Kills" .. i], tostring(p.kills))
            setText(Board["Deaths" .. i], tostring(p.deaths))
            local color = (p.index == LOCAL_PLAYER) and ROW_YOU or ((i % 2 == 0) and ROW_EVEN or ROW_ODD)
            pcall(function() row:SetBrushColor(color) end)
        else
            setVisible(row, false)
        end
    end
end

--------------------------------------------------------------------------------
-- The poll
--------------------------------------------------------------------------------

local function startMatch(running, world)
    Match = {
        code = running.code,
        variant = running.variant,
        title = running.title,
        mode = MODES[running.variant] or MODES.slayer,
        players = {},
        feed = {},
        deaths = {},
        teams = { [0] = 0, [1] = 0 },
        world = world,
    }
    Feed, Board = nil, nil
    boardShown = false
    boardDirty = true
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
    if not (Feed and Feed:IsValid()) then Feed = createWidget(FEED_CLASS, 40) end
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
    end
    if not Match then
        Queue = {}
        return
    end
    hookIncidents()
    ensureWidgets()
    refreshLocalPlayer()
    drain()
    drawFeed()
    local held = boardHeld(pc)
    if held ~= boardShown then
        boardShown = held
        if held then boardDirty = true end
        setVisible(Board, held)
    end
    if boardShown and boardDirty then
        boardDirty = false
        drawBoard()
    end
end

local function poll()
    local ok, err = pcall(tick)
    if not ok then Log("tick: " .. tostring(err)) end
    ExecuteInGameThreadWithDelay(POLL_MS, poll)
end

Log("Module loaded.")
ExecuteInGameThreadWithDelay(5000, poll)

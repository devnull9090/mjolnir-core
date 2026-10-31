-- AI bots in a multiplayer match (docs/bots.md), run by the host's HUD.
--
-- A map baked with `blam.bots` carries one single-actor squad per bot,
-- `bot_0` .. `bot_<n-1>`, a zone of firing positions and AI pathfinding
-- (crates/blam-cli/src/level.rs). MJOLNIRLobby's DLL lets `ai_place` work in
-- a Megalo game (mjolnir_bots_enable), runs the script lines on the
-- simulation thread (mjolnir_sim_script) and, in a team game, gives the bots
-- a multiplayer team (mjolnir_bots_teams).
--
-- AI are not players: their incidents carry player index -1 and the AI
-- biped's actor. Each bot gets a seat of its own here, BOT_BASE + k, which
-- the HUD's scoreboard and feed treat like a player's. A bot is placed one
-- at a time, so the AI biped that appears next is the one just placed; the
-- actors come from a pool and are reused, so an actor is a bot only between
-- its placement and its death.

local Bots = {}

--- Bot seats start here, clear of the 16 player seats (the match log only
--- records seats 0-15).
Bots.BASE = 100
Bots.RESPAWN_SECONDS = 5
--- How long a placement may take to show an actor before the squad is
--- taken not to exist on this map.
local PLACE_TIMEOUT = 4
local SCAN_SECONDS = 0.25

--- The AI bipeds a bot can be (the squads' characters').
--- Spartans are the players' own class: `isPlayer` keeps their bodies out.
local CLASSES = {
    "BP_SpartansBipedActor_C", "BP_EliteBipedActor_C", "BP_GruntBipedActor_C", "BP_JackalBipedActor_C",
    "BP_BruteBipedActor_C", "BP_MaleMarineBipedActor_C", "BP_FemaleMarineBipedActor_C",
}

--- The kinds of bot a map baked with `blam.bots.types` offers, as the
--- host's BOT TYPE setting numbers them (MJOLNIRLobby settings.lua); MIXED
--- takes them in turn. A map baked before kinds has `bot_<k>` only, which
--- every kind falls back to.
Bots.KINDS = { "spartan", "elite", "grunt", "jackal" }
Bots.MIXED = #Bots.KINDS

--- The host's BOT DIFFICULTY: each level is a set of squads,
--- `<kind>_<level>_<k>`, playing that level's characters (their accuracy;
--- tools/level/build_bot_characters.sh). A map baked before levels has
--- `<kind>_<k>`, and one before kinds `bot_<k>`, which a slot falls back to.
Bots.LEVELS = { "normal", "heroic", "legendary" }
Bots.LEGENDARY = 2

Bots.NAMES = {
    "Joshua", "Avery", "Marcus", "Riley", "Elena", "Dominic", "Kara", "Tobias", "Nadia", "Victor",
    "Sienna", "Owen", "Lena", "Mateo", "Priya", "Caleb", "Iris", "Felix", "Hana", "Silas",
    "Maya", "Jonah", "Zara", "Wesley", "Tessa", "Adrian", "Noor", "Grant", "Leah", "Rafael",
    "Ivy", "Desmond", "Clara", "Hugo", "Mira", "Simon", "Freya", "Emmett", "June", "Nikolai",
    "Sasha", "Theo", "Alma", "Quinn", "Ronan", "Esme", "Malik", "Vera", "Dalton", "Rosa",
    "Kenji", "Lucia", "Brody", "Anya", "Cyrus", "Nell", "Isaac", "Dara", "Gideon", "Paloma",
    "Reid", "Talia", "Oscar", "Mina", "Jasper", "Rhea", "Ezra", "Ingrid", "Colt", "Yara",
    "Milo", "Selma", "Abel", "Kira", "Lionel", "Opal", "Ansel", "Greta", "Bruno", "Celeste",
    "Duncan", "Ada", "Fletcher", "Wren", "Harlan", "Lola", "Ivan", "Petra", "Jude", "Marisol",
    "Knox", "Elsa", "Rocco", "Thea", "Sterling", "Juno", "Vaughn", "Odette", "Beckett", "Saoirse",
}

--- In a team game each bot plays for a side: a campaign team its bots are
--- moved to (`ai_set_team`) and the multiplayer team that campaign team plays
--- for. MJOLNIRLobby's DLL reads the pairs from native\bot_teams.txt both ways:
--- an AI unit takes the multiplayer team of its campaign team, and a player
--- the campaign team of their multiplayer team, since an AI picks its enemies
--- by campaign teams alone (docs/re/ai_in_multiplayer.md "How an AI picks its
--- enemies"). Covenant is the squads' own team.
Bots.SIDES = {
    Red = { team = "covenant", campaign = 3, multiplayer = 0 },
    Blue = { team = "flood", campaign = 8, multiplayer = 1 },
}

local state = nil
local dllDir, mapsDir, levelsDir = nil, nil, nil
local enable, run, setTeams = nil, nil, nil
local scriptId = os.time() + 7000
local log = function() end

--- `modsDir`: ue4ss\Mods; MJOLNIRLobby's DLL sits in MJOLNIRLobby\native.
function Bots.init(modsDir, logFn)
    dllDir = modsDir .. "\\MJOLNIRLobby\\native\\"
    mapsDir = (modsDir:match("^(.*)\\[^\\]*$") or modsDir) .. "\\MJOLNIRMaps\\"
    levelsDir = modsDir .. "\\MJOLNIRLevelLoader\\levels\\"
    log = logFn or log
end

--- Where the map's bot squads stand, by squad index (every kind's squad `k`
--- on start `k`), in Unreal cm: the bake's `bots.json` beside the level
--- file, in MJOLNIRMaps\<CODE>\ for a map pack and in MJOLNIRLevelLoader's
--- levels\ for a test install (the launcher prunes MJOLNIRMaps of files no
--- release ships). nil for a map baked before the file.
local function readStarts(code)
    if type(code) ~= "string" or code == "" then return nil end
    for _, path in ipairs({ mapsDir .. code .. "\\bots.json", levelsDir .. code .. ".bots.json" }) do
        local f = io.open(path, "rb")
        if f then
            local text = f:read("*a") or ""
            f:close()
            local starts = {}
            local list = text:match('"starts"%s*:%s*(%b[])') or ""
            local n = "([-%d.eE+]+)"
            for x, y, z in list:gmatch("%[%s*" .. n .. "%s*,%s*" .. n .. "%s*,%s*" .. n .. "%s*%]") do
                starts[#starts + 1] = { tonumber(x), tonumber(y), tonumber(z) }
            end
            if #starts > 0 then return starts end
        end
    end
    return nil
end

local function loadDll()
    if run ~= nil then return run ~= false end
    local ok = package and package.loadlib
    local dll = dllDir .. "mjolnir_lobby.dll"
    enable = ok and package.loadlib(dll, "mjolnir_bots_enable") or false
    run = ok and package.loadlib(dll, "mjolnir_sim_script") or false
    setTeams = ok and package.loadlib(dll, "mjolnir_bots_teams") or false
    return run ~= false
end

--- Each side's campaign team plays for its multiplayer team (`on`), or the
--- DLL puts the simulation's own code back.
local function teamTable(on)
    if not (loadDll() and setTeams) then return false end
    local f = io.open(dllDir .. "bot_teams.txt", "wb")
    if not f then return false end
    if on then
        for _, side in pairs(Bots.SIDES) do f:write(string.format("%d %d\n", side.campaign, side.multiplayer)) end
    end
    f:close()
    pcall(setTeams)
    return true
end

--- Run script lines on the simulation thread (MJOLNIRLevelLoader's
--- sim_script.lua does the same; the DLL skips an id it has run).
local function script(lines)
    if not loadDll() then return false end
    scriptId = scriptId + 1
    local f = io.open(dllDir .. "script.txt", "wb")
    if not f then return false end
    f:write(tostring(scriptId), "\n", table.concat(lines, "\n"), "\n")
    f:close()
    pcall(run)
    return true
end

local function address(actor)
    local ok, a = pcall(function() return actor:GetAddress() end)
    return ok and a or nil
end

--- Every AI biped actor there is, by address. FindAllOf walks the whole
--- object array (about 23 ms a class on Blood Gulch, 2026-10-25), so the
--- pools are found once, when bots start, and actors made later arrive
--- through NotifyOnNewObject; a tick only reads positions.
local pool = {}
local watched = {}

local function fillPool()
    pool = {}
    for _, class in ipairs(CLASSES) do
        for _, a in ipairs(FindAllOf(class) or {}) do
            local at = address(a)
            if at then pool[at] = a end
            -- NotifyOnNewObject takes the class's full path.
            if not watched[class] then
                local ok, path = pcall(function() return a:GetClass():GetFullName():match("%s(/%S+)$") end)
                if ok and path then
                    watched[class] = true
                    pcall(NotifyOnNewObject, path, function(new)
                        local id = address(new)
                        if id then pool[id] = new end
                    end)
                end
            end
        end
    end
end

--- Every AI biped out of the pool (a pooled actor waits at the origin),
--- and where each stands.
local function liveActors()
    local out, where = {}, {}
    for at, a in pairs(pool) do
        local ok, l = pcall(function()
            if not a:IsValid() then return nil end
            return a:K2_GetActorLocation()
        end)
        if ok and l == nil then
            pool[at] = nil
        elseif ok and math.abs(l.X) + math.abs(l.Y) >= 1 then
            out[at], where[at] = a, { l.X, l.Y, l.Z }
        end
    end
    return out, where
end

--- An erased AI leaves its actor where it stood, and the next placement may
--- take that actor: it then jumps to the spawn point.
local JUMP_CM = 400

local function jumped(from, to)
    if not (from and to) then return false end
    local dx, dy, dz = to[1] - from[1], to[2] - from[2], to[3] - from[3]
    return dx * dx + dy * dy + dz * dz > JUMP_CM * JUMP_CM
end

local function shuffled(list)
    local out = {}
    for i, v in ipairs(list) do out[i] = v end
    for i = #out, 2, -1 do
        local j = math.random(i)
        out[i], out[j] = out[j], out[i]
    end
    return out
end

--- Start `count` bots. `onSeat(index, name, side)` is told a bot's seat,
--- name and side ("Red" or "Blue" in a team game) each time it is placed:
--- on the floor, alive. `opts`:
---   kind, level  the host's BOT TYPE and BOT DIFFICULTY (Bots.KINDS, LEVELS)
---   isPlayer     isPlayer(address): whether an actor is a player's biped
---   teams        a team game: each bot plays for red or blue
---   onKill       onKill(killer, victim, death): a bot killed a bot, which
---                no incident reports; `death` is { by, actor, damage,
---                modifier }, the two actors and the incident's damage fields
---   map          the map's code, whose bots.json says where its squads stand
function Bots.begin(count, now, onSeat, opts)
    opts = opts or {}
    if not loadDll() then
        log("bots: MJOLNIRLobby's DLL is not there; no bots")
        return false
    end
    if enable then pcall(enable) end
    -- A free-for-all clears what a team game before it asked for.
    if not teamTable(opts.teams) and opts.teams then
        log("bots: MJOLNIRLobby's DLL cannot give bots a team; they fight both sides")
    end
    fillPool()
    math.randomseed(os.time())
    local level = opts.level or Bots.LEGENDARY
    state = { slots = {}, onSeat = onSeat, onKill = opts.onKill or function() end, retired = {}, nextScan = 0,
        placing = nil, names = shuffled(Bots.NAMES), kind = opts.kind or 0,
        isPlayer = opts.isPlayer or function() return false end, teams = opts.teams and true or false,
        level = Bots.LEVELS[level + 1] or Bots.LEVELS[Bots.LEGENDARY + 1],
        starts = readStarts(opts.map), began = now }
    Bots.resize(count, now)
    log(string.format("bots: %d bot(s) for this match%s; %s", count, opts.teams and ", on red and blue" or "",
        state.starts and string.format("each placed on the best of %d starts", #state.starts)
            or "no bots.json: each keeps its squad's start"))
    return true
end

--- Change how many bots play, keeping the ones there are: new seats are
--- placed as usual, the last ones past `count` are erased from the world.
--- Returns the seats taken out, so their rows can leave the board.
function Bots.resize(count, now)
    if not state then return {} end
    local removed = {}
    local lines = {}
    while #state.slots > count do
        local s = table.remove(state.slots)
        if state.placing == s then state.placing = nil end
        if s.addr then state.retired[s.addr] = true end
        -- A dead bot's squad may be another bot's by now.
        if s.status == "alive" or s.status == "placing" then
            lines[#lines + 1] = string.format("(ai_erase %s)", s.squad)
        end
        if s.seated then removed[#removed + 1] = s.index end
    end
    for k = #state.slots, count - 1 do
        local kind = state.kind >= Bots.MIXED and Bots.KINDS[k % #Bots.KINDS + 1]
            or Bots.KINDS[state.kind + 1] or Bots.KINDS[1]
        -- A slot's squad is `<family>_<j>`: `j` is picked at each placement
        -- (pickSquad), `k` on a map without bots.json. Older maps name their
        -- squads `<kind>_<k>` (before levels) or `bot_<k>` (before kinds).
        local family = kind .. "_" .. state.level
        state.slots[#state.slots + 1] = {
            k = k, index = Bots.BASE + k, name = state.names[(k % #state.names) + 1] .. " (bot)",
            family = family, primary = family, j = k, squad = family .. "_" .. k,
            fallbacks = { kind, "bot" },
            status = "waiting", nextAt = now + 1 + (k - #state.slots) * 0.5,
        }
    end
    if #lines > 0 then script(lines) end
    return removed
end

--- How many bots this match has asked for.
function Bots.count()
    return state and #state.slots or 0
end

--- No more bots: every one placed is erased, and AI units have no
--- multiplayer team again.
function Bots.stop()
    if state then
        Bots.resize(0, 0)
        if state.teams then teamTable(false) end
    end
    state = nil
end

function Bots.active()
    return state ~= nil
end

function Bots.isBot(index)
    return type(index) == "number" and index >= Bots.BASE
end

local function slotOf(index)
    if not state or not Bots.isBot(index) then return nil end
    return state.slots[index - Bots.BASE + 1]
end

--- The bot seat an AI biped's actor holds, or nil.
function Bots.seatOf(actor)
    if not state or not actor then return nil end
    local at = address(actor)
    if not at then return nil end
    for _, s in ipairs(state.slots) do
        if s.status == "alive" and s.addr == at then return s.index end
    end
    return nil
end

--- Off the floor until the respawn time has passed, as a player is. Its
--- body stays an actor of the pool's until a placement takes it again.
local function bury(s, now)
    if s.addr then state.retired[s.addr] = true end
    s.status, s.addr, s.actor, s.deadAt = "dead", nil, nil, nil
    s.nextAt = now + Bots.RESPAWN_SECONDS
end

--- A bot died (its `Kill` incident, or the HUD's own for a bot's kill).
function Bots.died(index, now)
    local s = slotOf(index)
    if not s or s.status ~= "alive" then return end
    bury(s, now)
end

--- How long a bot's death waits for a player's `Kill` to name it before it
--- is taken for one no incident reports (a fall, its own grenade).
local UNCLAIMED_SECONDS = 2

--- Whether a bot's unit is dead and, when the blow that killed it is the
--- last damage its actor took, who dealt it. The simulation reports no
--- incident when an AI kills an AI; the actor's blueprint keeps each hit's
--- aftermath (`Blam Aftermath Result`: the damage owner, the incident's
--- damage fields, and `bBodyDepleted` on the killing blow).
local function deathOf(actor)
    local okDead, dead = pcall(function() return actor.BlamObjectDamage:IsDead() end)
    if not (okDead and dead) then return nil end
    local death = { actor = actor }
    pcall(function()
        local r = actor["Blam Aftermath Result"]
        if not r.Flags.bBodyDepleted then return end
        death.by = r.DamageOwner.DamageOwnerObject
        death.modifier = r.DamageReportingInfo.Modifier
        death.damage = r.DamageReportingInfo.Type.TagName:ToString()
    end)
    return death
end

--- Bots dead with no incident to say so. Read before any is buried, so two
--- bots that kill each other in one scan both find their killer.
local function deaths(now, live)
    local found = {}
    for _, s in ipairs(state.slots) do
        if s.status == "alive" and live[s.addr] then
            local death = deathOf(s.actor)
            if death then found[#found + 1] = { slot = s, death = death } else s.deadAt = nil end
        end
    end
    local byAddress = {}
    for _, s in ipairs(state.slots) do
        if s.status == "alive" then byAddress[s.addr] = s end
    end
    for _, d in ipairs(found) do
        local s = d.slot
        s.deadAt = s.deadAt or now
        local killer = d.death.by and byAddress[address(d.death.by)]
        if killer and killer ~= s then
            pcall(state.onKill, killer.index, s.index, d.death)
            bury(s, now)
        elseif now - s.deadAt >= UNCLAIMED_SECONDS then
            bury(s, now)
        end
    end
end

--- AI stand at their firing positions until they see someone. A bot is
--- given somewhere to be every so often: mostly an enemy it is made aware
--- of, otherwise one of the map's areas (task `area_<k>`) to walk to
--- (level.rs bots_finish). An enemy human is hunted (task `hunt`, which
--- keeps near the players); an enemy bot, in a team game, is not a player,
--- so the bot walks to an area knowing where that bot is.
Bots.AREAS = 16
local ROAM_MIN, ROAM_MAX = 8, 16
--- How often an order is a hunt (an enemy, wherever they are) rather than a
--- walk to a random area.
local HUNT_SHARE = 0.75

--- Someone for bot `s` to go after: a human player (as `player_get` counts
--- them) or, in a team game, a bot of the other side (its squad). A human
--- whose side is not known yet is no one's enemy in a team game.
local function pickEnemy(s, humans)
    local enemies = {}
    for _, h in ipairs(humans) do
        if not s.side or (h.team and h.team ~= s.side) then enemies[#enemies + 1] = { nth = h.nth } end
    end
    if s.side then
        for _, o in ipairs(state.slots) do
            if o.status == "alive" and o.side and o.side ~= s.side then enemies[#enemies + 1] = { squad = o.squad } end
        end
    end
    return #enemies > 0 and enemies[math.random(#enemies)] or nil
end

local function roam(now, humans)
    local lines = {}
    for _, s in ipairs(state.slots) do
        if s.status == "alive" and now >= (s.roamAt or 0) and #lines < 14 then
            s.roamAt = now + ROAM_MIN + math.random() * (ROAM_MAX - ROAM_MIN)
            local enemy = math.random() < HUNT_SHARE and pickEnemy(s, humans) or nil
            if enemy and enemy.nth then
                lines[#lines + 1] = string.format("(ai_set_task %s mjolnir_bots hunt)", s.squad)
                lines[#lines + 1] = string.format("(ai_magically_see_object %s (player_get %d))", s.squad, enemy.nth)
            else
                lines[#lines + 1] = string.format("(ai_set_task %s mjolnir_bots area_%d)", s.squad, math.random(Bots.AREAS) - 1)
                if enemy then lines[#lines + 1] = string.format("(ai_magically_see %s %s)", s.squad, enemy.squad) end
            end
        end
    end
    if #lines > 0 then script(lines) end
end

--- The side with fewer players, humans and bots; on a tie, the one with
--- fewer humans (a human plays better than a bot), else Blue.
local function chooseSide(humans)
    local all, people = { Red = 0, Blue = 0 }, { Red = 0, Blue = 0 }
    for _, h in ipairs(humans) do
        if all[h.team] then all[h.team], people[h.team] = all[h.team] + 1, people[h.team] + 1 end
    end
    for _, s in ipairs(state.slots) do
        if s.side then all[s.side] = all[s.side] + 1 end
    end
    if all.Red ~= all.Blue then return all.Red < all.Blue and "Red" or "Blue" end
    if people.Red ~= people.Blue then return people.Red < people.Blue and "Red" or "Blue" end
    return "Blue"
end

--- Where a bot comes in, from the map's bots.json (docs/bots.md "Where bots
--- spawn"). A side has no base of its own: a converted map's player spawns
--- are neutral, and a team game's first spawn lands at either end. So a bot
--- comes in where its side is, as the game's own respawns bring players in:
--- clear of its enemies, then near its side. In order:
---   1. a free squad of its kind (none another bot out holds);
---   2. never onto anyone (CROWD_CM);
---   3. with an enemy about: a start no enemy is within DANGER_CM of, or
---      failing that the ones farthest from the enemies (within SPREAD_CM);
---   4. with its side about, and enemies all clear: the starts nearest one of
---      its side (within NEAR_CM of the nearest);
---   5. with no one about at all, its own squad `k`, the bake's farthest-first
---      order; otherwise one of what is left at random.
local WU = 30.48 * 10
local CROWD_CM = 2 * WU
local DANGER_CM = 25 * WU
local SPREAD_CM = 10 * WU
local NEAR_CM = 8 * WU
--- The first bots wait this long for the humans' first spawn: placed before a
--- human is known, a bot could come in beside an enemy.
local HUMANS_WAIT = 5

local function position(actor)
    local ok, l = pcall(function()
        if not (actor and actor:IsValid()) then return nil end
        return actor:K2_GetActorLocation()
    end)
    return ok and l and { l.X, l.Y, l.Z } or nil
end

local function nearest(p, list)
    local best = math.huge
    for _, q in ipairs(list) do
        local dx, dy, dz = p[1] - q[1], p[2] - q[2], p[3] - q[3]
        best = math.min(best, dx * dx + dy * dy + dz * dz)
    end
    return math.sqrt(best)
end

local function filter(list, test)
    local out = {}
    for _, j in ipairs(list) do
        if test(j) then out[#out + 1] = j end
    end
    return out
end

--- The squad index slot `s` is placed on.
local function pickSquad(s, humans, at)
    local starts = state.starts
    if not starts or s.family ~= s.primary then return s.k end
    local taken = {}
    for _, o in ipairs(state.slots) do
        if o ~= s and o.family == s.family and (o.status == "alive" or o.status == "placing") then taken[o.j] = true end
    end
    local free = {}
    for j = 0, #starts - 1 do
        if not taken[j] and not (s.bad and s.bad[j]) then free[#free + 1] = j end
    end
    if #free == 0 then return nil end

    local everyone, enemies, friends = {}, {}, {}
    local function add(p, side)
        if not p then return end
        everyone[#everyone + 1] = p
        if not state.teams or (side and side ~= s.side) then
            enemies[#enemies + 1] = p
        elseif side then
            friends[#friends + 1] = p
        end
    end
    for _, h in ipairs(humans) do
        -- A human whose side is not known yet is no one's enemy or friend.
        if h.biped and not h.dead then add(position(h.biped), state.teams and h.team or nil) end
    end
    for _, o in ipairs(state.slots) do
        if o ~= s and o.status == "alive" then add(at[o.addr], o.side) end
    end
    local function from(j, list) return nearest(starts[j + 1], list) end

    local picks = filter(free, function(j) return from(j, everyone) >= CROWD_CM end)
    if #picks == 0 then picks = free end
    local clear = true
    if #enemies > 0 then
        local safe = filter(picks, function(j) return from(j, enemies) >= DANGER_CM end)
        if #safe > 0 then
            picks = safe
        else
            clear = false
            local far = 0
            for _, j in ipairs(picks) do far = math.max(far, from(j, enemies)) end
            picks = filter(picks, function(j) return from(j, enemies) >= far - SPREAD_CM end)
        end
    end
    if clear and #friends > 0 then
        local close = math.huge
        for _, j in ipairs(picks) do close = math.min(close, from(j, friends)) end
        picks = filter(picks, function(j) return from(j, friends) <= close + NEAR_CM end)
    elseif #everyone == 0 then
        for _, j in ipairs(picks) do
            if j == s.k then return j end
        end
    end
    return picks[math.random(#picks)]
end

local function step(now, humans, live, where)
    -- A retired actor that went back to the pool may be handed out again.
    for at in pairs(state.retired) do
        if not live[at] then state.retired[at] = nil end
    end
    local taken = {}
    for _, s in ipairs(state.slots) do
        if s.status == "alive" then
            if not live[s.addr] then
                -- Gone without a kill we saw (a fall out of the world).
                bury(s, now)
            else
                taken[s.addr] = true
            end
        end
    end
    deaths(now, live)
    if not state.placing then roam(now, humans) end
    local p = state.placing
    if p then
        for at, actor in pairs(live) do
            -- Out of the pool since the ai_place, or teleported (a jump between
            -- two scans no one runs) onto the spawn.
            local fresh = not p.before[at] and not state.retired[at]
            local teleported = p.before[at] and jumped(state.lastWhere and state.lastWhere[at], where[at])
            if not taken[at] and (fresh or teleported) and not state.isPlayer(at) then
                p.status, p.addr, p.actor = "alive", at, actor
                -- A few seconds to look around where it spawned first.
                p.roamAt = now + 3 + math.random() * 4
                state.placing = nil
                p.seated = true
                pcall(state.onSeat, p.index, p.name, p.side)
                return
            end
        end
        if now - p.placedAt > PLACE_TIMEOUT then
            p.tries = (p.tries or 0) + 1
            state.placing = nil
            if state.starts and p.family == p.primary then
                -- The map's bots.json lists this squad, so the map has it: another
                -- one next time.
                p.bad = p.bad or {}
                p.bad[p.j] = true
                if p.tries >= 4 then
                    p.status = "missing"
                    log(string.format("bots: %s never appeared, nor three other squads", p.squad))
                else
                    p.status, p.nextAt = "waiting", now + 1
                end
            elseif p.tries >= 2 and #p.fallbacks > 0 then
                -- A map baked before levels (or kinds) names its squads so.
                p.family, p.tries, p.status, p.nextAt = table.remove(p.fallbacks, 1), 0, "waiting", now
            elseif p.tries >= 2 then
                p.status = "missing"
                log(string.format("bots: %s never appeared; this map has no such squad", p.squad))
            else
                p.status, p.nextAt = "waiting", now + 1
            end
        end
        return
    end
    -- The first bots wait for the humans' first spawn, for a few seconds.
    if state.starts and now - state.began < HUMANS_WAIT then
        for _, h in ipairs(humans) do
            if not h.biped and not h.dead then return end
        end
    end
    for _, s in ipairs(state.slots) do
        if (s.status == "waiting" or s.status == "dead") and now >= s.nextAt then
            -- A side is chosen when a bot is first placed, when the humans'
            -- sides are known, and kept for the match.
            if state.teams and not s.side then s.side = chooseSide(humans) end
            local j = pickSquad(s, humans, where)
            if not j then
                s.status = "missing"
                log(string.format("bots: no %s squad left for %s", s.family, s.name))
                return
            end
            s.j, s.squad = j, s.family .. "_" .. j
            if state.starts then
                local start = state.starts[j + 1]
                log(string.format("bots: %s%s comes in on %s at (%.0f, %.0f)", s.name,
                    s.side and (" (" .. s.side .. ")") or "", s.squad, start and start[1] or 0, start and start[2] or 0))
            end
            -- The squad's team before it is placed, which its new actor takes:
            -- placed covenant and moved after, a blue bot was red for a tick,
            -- and a blue Spartan could keep the red armour MJOLNIRLevelLoader
            -- tinted it as it appeared.
            local lines = {}
            if s.side then lines[1] = string.format("(ai_set_team %s %s)", s.squad, Bots.SIDES[s.side].team) end
            lines[#lines + 1] = string.format("(ai_place %s)", s.squad)
            -- Active wherever it is: AI far from every player otherwise idle, and
            -- a bot hunting across the map must not.
            lines[#lines + 1] = string.format("(ai_force_active %s true)", s.squad)
            if script(lines) then
                -- Whatever is out already is not this bot.
                s.status, s.placedAt, s.before = "placing", now, where
                state.placing = s
            end
            return
        end
    end
end

--- `humans`: the match's human players in seat order, each `{ nth, team,
--- biped, dead }`: `player_get <nth>` is that player (it counts the players
--- there are), `team` is "Red", "Blue" or nil, and `biped` their biped's actor
--- since they last spawned.
function Bots.tick(now, humans)
    if not state or now < state.nextScan then return end
    state.nextScan = now + SCAN_SECONDS
    local live, where = liveActors()
    step(now, humans or {}, live, where)
    -- Where each actor stood this scan, for the next one's teleport test.
    if state then state.lastWhere = where end
end

--- The seats of every bot that has been placed, with their names and sides.
function Bots.seats()
    local out = {}
    if not state then return out end
    for _, s in ipairs(state.slots) do
        if s.seated then out[#out + 1] = { index = s.index, name = s.name, alive = s.status == "alive", side = s.side } end
    end
    return out
end

--- The kind of bot the host chose: `bot_type` in the game settings line
--- (an index into Bots.KINDS, or Bots.MIXED), Spartans without one.
function Bots.wantedKind(loaderDir)
    local f = io.open(loaderDir .. "\\variant_settings.txt", "rb")
    if not f then return 0 end
    local n = tonumber((f:read("*a") or ""):match("bot_type=(%d+)"))
    f:close()
    return math.min(n or 0, Bots.MIXED)
end

--- The difficulty the host chose: `bot_level` in the game settings line
--- (an index into Bots.LEVELS), Legendary without one.
function Bots.wantedLevel(loaderDir)
    local f = io.open(loaderDir .. "\\variant_settings.txt", "rb")
    if not f then return Bots.LEGENDARY end
    local n = tonumber((f:read("*a") or ""):match("bot_level=(%d+)"))
    f:close()
    return math.min(n or Bots.LEGENDARY, #Bots.LEVELS - 1)
end

--- How many bots the host asked for: `bots` in the game settings line
--- MJOLNIRLobby writes for the loader (variant_settings.txt), 0 without it.
function Bots.wanted(loaderDir)
    local f = io.open(loaderDir .. "\\variant_settings.txt", "rb")
    if not f then return 0 end
    local n = tonumber((f:read("*a") or ""):match("bots=(%d+)"))
    f:close()
    return math.min(n or 0, 15)
end

return Bots

-- MJOLNIR Level Loader: kill floors (#234)
--
-- Halo CE's pits kill through the engine's falling death. Our multiplayer
-- matches run under Reach's Megalo game engine, which has none (Reach maps
-- use kill volumes), and a converted map carries no kill volumes: on
-- Gephyrophobia a 110 m fall from the bridge lands a player alive on the
-- canyon floor (2026-10-24, flung off the bridge from Blam script).
--
-- A kill floor is a height below which a player dies, as a kill volume
-- spanning the whole map would. The host checks its Spartans twice a second
-- and kills, through MJOLNIRBlamConsole's mailbox, any whose biped is below
-- the floor; the death is the engine's own, so respawns, the kill feed and
-- the scores follow as for any death. Floors are per map: the table below,
-- or "kill_floor" (Unreal centimetres) in a level's JSON, which wins.
--
-- Plain helpers (KillFloor.floorFor, KillFloor.below) run under stock Lua in
-- tools/tests/test_kill_floor.lua; nothing touches UE4SS before init.

local KillFloor = {}

--- Floors by map code, in Unreal centimetres. Gephyrophobia: its lowest
--- playable spot is the hill under the bridge at -6192 and the canyon floor
--- is at -7657, so a fall dies a few metres above the floor.
KillFloor.FLOORS = {
    GPH = -7000,
}

--- How long a player stays marked as killed before another kill is sent
--- (the biped may lie below the floor until it is taken away).
KillFloor.RETRY_SECONDS = 3

--- The floor for a map: the level's own "kill_floor" (a number), else the
--- table's, else nil.
function KillFloor.floorFor(code, level)
    if type(level) == "table" and type(level.kill_floor) == "number" then return level.kill_floor end
    if type(code) ~= "string" then return nil end
    return KillFloor.FLOORS[string.upper(code)]
end

--- Whether a height is below a floor (nil floor: never).
function KillFloor.below(z, floor)
    return type(z) == "number" and type(floor) == "number" and z < floor
end

local env
local state = { world = nil, seeded = false, bipeds = {}, killed = {}, watched = false, consoleDir = nil, id = 7300000 }

local SPARTAN = "/Game/_Prototypes/SynchronizationTestContent/TestActor/BP_SpartansBipedActor.BP_SpartansBipedActor_C"

local function remember(actor)
    local ok, key = pcall(function() return actor:GetAddress() end)
    if ok and key then state.bipeds[key] = actor end
end

--- The Blam player index controlling a biped, or nil. Only a unit a player
--- still controls counts: a body left below the floor must never send
--- (unit_kill (player_get N)), which would kill that player's next spawn.
local function playerOf(actor)
    local index
    pcall(function()
        local cls = StaticFindObject("/Script/BlamSynchronization.BlamUnitComponent")
        local unit = actor:GetComponentByClass(cls)
        if not unit:IsControlledByAnyPlayer() then return end
        local datum = unit:GetControllingPlayerDatumIndex()
        if type(datum) == "number" and datum ~= -1 then index = math.floor(datum % 65536) end
    end)
    return index
end

--- One line into MJOLNIRBlamConsole's mailbox (native\request.txt, flags 1:
--- run whether or not the console thinks a game is in progress), then its
--- pump. False when the console mod is not installed.
local function blam(line)
    local dir = state.consoleDir
    local pump = package and package.loadlib and package.loadlib(dir .. "mjolnir_blam_console.dll", "mjolnir_blam_pump")
    if not pump then return false end
    state.id = state.id + 1
    local f = io.open(dir .. "request.txt", "wb")
    if not f then return false end
    f:write(string.format("%d 1\n%s\n", state.id, line))
    f:close()
    pcall(pump)
    return true
end

local function newWorld(world)
    state.world = world
    state.seeded = false
    state.bipeds = {}
    state.killed = {}
end

--- MJOLNIRLevelLoader's half-second loop.
function KillFloor.tick()
    if not env then return end
    local world = env.getWorld()
    if not world then return end
    -- Two UE4SS handles on one UObject never compare equal: compare addresses.
    local okA, address = pcall(function() return world:GetAddress() end)
    if not okA then return end
    if address ~= state.world then newWorld(address) end
    local floor = KillFloor.floorFor(env.Current.scenario, env.Current.level)
    if not floor or not env.isHost() then return end
    if not state.watched then
        state.watched = pcall(NotifyOnNewObject, SPARTAN, remember)
    end
    if not state.seeded then
        state.seeded = true
        for _, actor in ipairs(FindAllOf("BP_SpartansBipedActor_C") or {}) do remember(actor) end
    end
    local now = os.clock()
    for key, actor in pairs(state.bipeds) do
        if not (actor and actor:IsValid()) then
            state.bipeds[key] = nil
        else
            local okL, at = pcall(function() return actor:K2_GetActorLocation() end)
            if okL and at and KillFloor.below(at.Z, floor) then
                local index = playerOf(actor)
                if index and now - (state.killed[index] or -100) >= KillFloor.RETRY_SECONDS then
                    state.killed[index] = now
                    if blam(string.format("(unit_kill (player_get %d))", index)) then
                        env.Log(string.format("kill floor: player %d fell below %d cm on %s", index, floor,
                            tostring(env.Current.scenario)))
                    end
                end
            end
        end
    end
end

--- `deps`: Log, getWorld, isHost, Current, modDir.
function KillFloor.init(deps)
    env = deps
    state.consoleDir = deps.modDir:gsub("[\\/]MJOLNIRLevelLoader[\\/]?$", "") .. "\\MJOLNIRBlamConsole\\native\\"
end

return KillFloor

-- MJOLNIR Level Loader: team colours (docs/game_modes.md, 2.2 and 2.3)
--
-- The simulation knows every object's team, and draws it through change
-- colours that never reach Unreal. What does reach Unreal is an object's
-- model variant and, for a player's biped, the multiplayer half of its team
-- component (docs/game_modes.md 2.1). This module colours by those two:
--
-- Capture the Flag. Each team's flag is a tag of its own
-- (tools/level/build_ctf_flag.sh): objects\weapons\multiplayer\flag\flag,
-- model variant "default", is red, and flag\flag_blue, variant "blue", is
-- blue, and the CTF variant makes each stand's flag of its team's type. The
-- flag actor's mesh synchronization component names the variant
-- (GetVariantName), so a flag's colour is read off the actor, never guessed
-- from stands or incidents (every such guess had a path to the wrong colour,
-- docs/game_modes.md 2.2). The flag in first person is the enemy of the local
-- player's team: only enemies may pick a flag up.
--
-- Team armour. In a team game every Spartan wears Mk V Classic, the one
-- armour whose material takes a colour. The native half makes the
-- simulation choose it for everyone (mjolnir_team_armor_on, switched by
-- main.lua as the map starts), and the armour is tinted on the game's own
-- Blueprint events: a biped starting to stand for a player
-- (BP_OnGameplayStart) and each mesh apply (OnRegionsChanged, which the mesh
-- synchronization raises after it has put the meshes and materials on). A
-- Spartan still in another armour (no native switch) is swapped to Mk V here
-- and its plates and helmet hidden. A check every 1.5 s covers a pooled
-- actor reused with no mesh event.
--
-- Split out of main.lua, whose main chunk is at Lua's 200 locals. Nothing
-- here touches UE4SS before Teams.init, so tools/tests/test_teams.lua runs
-- the plain helpers under stock Lua.

local Teams = {}

--------------------------------------------------------------------------------
-- Plain helpers (tools/tests/test_teams.lua)
--------------------------------------------------------------------------------

--- The game types played by teams (MJOLNIRLobby's MODES with `teams`).
Teams.TEAM_GAMES = { ctf = true, team_slayer = true }

--- A flag lying within this of its own team's stand is at home, and is drawn
--- exactly on the stand: the flag object settles a little off it and turned
--- (Gephyrophobia). The old 4 m caught an enemy flag dropped beside a stand.
Teams.PIN_CM = 150

--- The CE runtime pack's container with the blue flag tag
--- (tools/level/build_ctf_flag.sh). On a PC without it, a CTF variant that
--- names the blue flag's object type is wiped whole by the simulation (sim
--- 0x409c40 -> 0x40a310): no flags and no captures.
Teams.BLUE_FLAG_CONTAINER = "pakchunk990-MJOLNIRFLAGB_P"

--- The native team-armour switch as main.lua last set it (loadMegaloSwitch):
--- "on", "off", or "missing" (a native DLL without it), for
--- mjolnir_level_status.
Teams.native = "missing"

local NUMBERED = { [0] = "red", [1] = "blue" }
local ENEMY = { red = "blue", blue = "red" }

--- A flag's team from its model variant: "blue" is blue, any other name (the
--- red flag's "default") is red, and nothing ("" or None, before the actor's
--- first update) is nil, never a guess. Compared case-blind, as Unreal
--- compares names: a name reads back as it was first registered.
function Teams.flagTeam(variant)
    if type(variant) ~= "string" then return nil end
    local v = variant:lower()
    if v == "" or v == "none" then return nil end
    return v == "blue" and "blue" or "red"
end

--- "red", "blue", ... from GetGameTeamString
--- ("EBlamAllegianceTeam::None|EBlamMultiplayerTeam::Red"): the multiplayer
--- half, the team a player is on in a Megalo game, where the allegiance half
--- is None for everyone. Nil for None or anything unreadable.
function Teams.parseTeam(text)
    if type(text) ~= "string" then return nil end
    local team = text:match("EBlamMultiplayerTeam::(%a+)")
    if not team or team == "None" then return nil end
    return team:lower()
end

--- The other team of a two-team game; nil for anything else.
function Teams.enemyOf(team)
    return ENEMY[team]
end

--- A stand's team as the level file gives it ("red", or 0 and 1 in older
--- files).
function Teams.standTeam(team)
    if type(team) == "string" then return team:lower() end
    return NUMBERED[team]
end

--- The stand of `team` (the level's `ctf.stands`) within `radius` cm of `at`
--- ({ X, Y, Z } as Unreal gives a location, or { x, y, z }), or nil. Only the
--- flag's own stand counts: a red flag dropped by the blue stand is not home.
function Teams.homeStand(stands, team, at, radius)
    if type(stands) ~= "table" or not team or type(at) ~= "table" then return nil end
    local x, y, z = at.X or at[1], at.Y or at[2], at.Z or at[3]
    if not (x and y and z) then return nil end
    local reach = (radius or Teams.PIN_CM) ^ 2
    for _, s in ipairs(stands) do
        local p = type(s) == "table" and s.pos
        if type(p) == "table" and Teams.standTeam(s.team) == team then
            local dx, dy, dz = x - p[1], y - p[2], z - p[3]
            if dx * dx + dy * dy + dz * dz <= reach then return s end
        end
    end
    return nil
end

--- The game's Paks folder from a mod's folder: the mods live in
--- <root>\Meteorite\Binaries\<Win64 or WinGDK>\ue4ss\Mods\<mod>, the
--- containers in <root>\Meteorite\Content\Paks. Nil if the path says neither.
function Teams.paksDir(modDir)
    if type(modDir) ~= "string" then return nil end
    local at = modDir:lower():find("\\binaries\\", 1, true)
    if not at then return nil end
    return modDir:sub(1, at - 1) .. "\\Content\\Paks"
end

--- Whether the launcher's hub state (hub_state.json, decoded) mounts the
--- container `stem`: an installed mod that lists it, enabled in the active
--- profile. The launcher copies each hub container into Paks under a
--- load-order name of its own (pakchunk9NN-MJOLNIRHUB-<slug>-<j>_P), so on
--- a hub install the original name is only in this record.
function Teams.hubMounts(state, stem)
    if type(state) ~= "table" or type(state.installed) ~= "table" then return false end
    local enabled = {}
    for _, p in ipairs(type(state.profiles) == "table" and state.profiles or {}) do
        if type(p) == "table" and p.name == state.active and type(p.entries) == "table" then
            for _, e in ipairs(p.entries) do
                if type(e) == "table" and e.enabled == true and e.slug ~= nil then enabled[e.slug] = true end
            end
        end
    end
    for _, m in ipairs(state.installed) do
        if type(m) == "table" and enabled[m.slug] and type(m.containers) == "table" then
            for _, c in ipairs(m.containers) do
                if c == stem then return true end
            end
        end
    end
    return false
end

--- Whether this PC mounts the container `stem`: its stub .pak in Paks under
--- its own name (a manual install, or a build script's --install), or a hub
--- mod that carries it (hubMounts). `decode` is a JSON decoder.
function Teams.containerInstalled(stem, modDir, decode)
    local paks = Teams.paksDir(modDir)
    local f = paks and io.open(paks .. "\\" .. stem .. ".pak", "rb")
    if f then
        f:close()
        return true
    end
    local appdata = os.getenv("APPDATA")
    f = appdata and io.open(appdata .. "\\com.devnull9090.mjolnir-launcher\\hub_state.json", "rb")
    if not f then return false end
    local text = f:read("*a")
    f:close()
    local ok, state = pcall(decode, text)
    return ok and Teams.hubMounts(state, stem)
end

--------------------------------------------------------------------------------
-- In the game
--------------------------------------------------------------------------------

-- main.lua's helpers and state, from Teams.init.
local env = nil

local function Log(msg)
    if env then env.Log(msg) end
end

local MOBILITY_MOVABLE = 2
local COLLISION_NONE = 0

--- Classes by path, each looked up once a world (a lookup is ~1 ms, too
--- much for the loops) and kept while valid; false for one that did not
--- resolve, so it is not looked up again until the next world.
local Classes = {}

--- The first of `paths` that resolves.
local function classOf(paths)
    local key = paths[1]
    local known = Classes[key]
    if known == false then return nil end
    if known and known:IsValid() then return known end
    for _, path in ipairs(paths) do
        local found = env.findObject(path)
        if found then
            if path ~= key then Log("team colours: " .. key .. " is " .. path) end
            Classes[key] = found
            return found
        end
    end
    Classes[key] = false
    Log("team colours: no class " .. key)
    return nil
end

local SKELETAL = { "/Script/Engine.SkeletalMeshComponent" }
local STATIC = { "/Script/Engine.StaticMeshComponent" }
local ACTOR_COMPONENT = { "/Script/Engine.ActorComponent" }
-- The two Blam synchronization components every synced actor has. Their
-- module is read off the exe's string table (the names lie among
-- BlamSynchronization's classes, beside BlamObjectActor and
-- BlamPlayerStateComponent); BlamEngine is the one other place they could be.
-- The concrete mesh component's path is certain: the skull's and the
-- Spartan's cooked packages import it by the hash of exactly that path.
local MESH_SYNC = { "/Script/BlamSynchronization.BlamMeshSynchronizationComponentBase",
    "/Script/BlamSynchronization.BlamMeshSynchronizationComponent",
    "/Script/BlamEngine.BlamMeshSynchronizationComponentBase" }
local OBJECT_SYNC = { "/Script/BlamSynchronization.BlamObjectSynchronizationComponent",
    "/Script/BlamEngine.BlamObjectSynchronizationComponent" }

--- `actor`'s components of a class (one of `paths`).
local function components(actor, paths)
    local cls = classOf(paths)
    if not cls then return {} end
    local out = {}
    for _, c in ipairs(actor:K2_GetComponentsByClass(cls) or {}) do
        if type(c) == "userdata" and c.get then c = c:get() end
        out[#out + 1] = c
    end
    return out
end

local function classNameOf(object)
    return object:GetClass():GetFName():ToString()
end

--- The model variant the simulation gave `actor`'s object, as its mesh
--- synchronization component has it (GetVariantName, exe 0x79f2210: the
--- name the mesh state's first word carries, exe 0x7a20850); nil if the
--- actor has no such component.
local function variantOf(actor)
    for _, c in ipairs(components(actor, MESH_SYNC)) do
        local ok, name = pcall(function() return c:GetVariantName():ToString() end)
        if ok and type(name) == "string" then return name end
    end
    return nil
end

--- `actor`'s tag index, object index and parent object index
--- (BlamObjectSynchronizationComponent), for the log: the two flag types
--- have different tag indices, which cross-checks the variant.
local function indicesOf(actor)
    for _, c in ipairs(components(actor, OBJECT_SYNC)) do
        local ok, tag, object, parent = pcall(function()
            return c.BlamTagDefinitionIndex, c.BlamObjectIndex, c.ParentObjectIndex
        end)
        if ok then return tag, object, parent end
    end
    return nil
end

--- The team of a unit's actor (a Spartan biped), from its team component's
--- multiplayer half; nil before the simulation has put it on one.
local function teamOf(actor)
    local ok, text = pcall(function() return actor.BlamGameTeam:GetGameTeamString():ToString() end)
    return ok and Teams.parseTeam(text) or nil
end

--- The team of the player a pawn is: the unit it drives
--- (ABlamPawn::GetBlamObjectActor, exe 0x7b0b0a0, the actor of its unit
--- datum) and that unit's team. Never the nearest biped's: in a melee, a
--- vehicle or a death that was an enemy or a corpse. Nil while the pawn has
--- no unit (dead, not spawned yet) or the unit no team.
local function pawnTeam(pawn)
    local ok, unit = pcall(function() return pawn:GetBlamObjectActor() end)
    if not (ok and unit and unit:IsValid()) then return nil end
    return teamOf(unit)
end

--- A line said once a world (`key` names it).
local Said = {}
local function sayOnce(key, msg)
    if Said[key] then return end
    Said[key] = true
    Log(msg)
end

--------------------------------------------------------------------------------
-- Capture the Flag flags
--------------------------------------------------------------------------------

--- The flag borrows the oddball's actor, since nothing ships for it
--- (tools/level/build_ctf_flag.sh): each flag that turns up is a skull, and
--- gets CE's flag mesh in its team's colours instead. The first-person one
--- is a subclass.
local SKULL_ACTOR_CLASS_PATH = "/Game/Weapons/Melee/Skull/Blueprints/BP_SkullActor.BP_SkullActor_C"
local FLAG_ACTOR_CLASS = "BP_SkullActor_C"
local FP_FLAG_ACTOR_CLASS = "BP_FP_SkullActor_C"

--- The skull's ghostly fire (BP_SkullEffect) and its whispering, which is
--- the actor's own audio component (HaloAudioTracking): removing the effect
--- alone left the whisper playing. The game makes the effect again as the
--- flag is picked up and dropped, so it is removed again then, from the
--- first-person actor too.
local SKULL_PARTS = { "BP_SkullEffect", "HaloAudioTracking" }

--- The flag in first person: the carrier's own copy of the skull actor,
--- whose origin is the camera. Its skull is drawn by the first-person
--- renderer, which a mesh of ours does not take part in, so the flag is held
--- as an ordinary mesh at a fixed place before the camera: low on the right,
--- its pole leaning up and to the left, as in CE. Relative to the actor, X
--- is forward, Y up and Z left. Found by hand, holding the flag (2026-10-01).
local FP_FLAG = { pos = { 65, -42, -28 }, rot = { -10, -20, 60 }, scale = 0.7 }

local Flags = {
    -- Each flag actor seen, by full name (UE4SS handles to one actor never
    -- compare equal): { actor, name, fp, comp (our mesh), team (the colours
    -- it wears), home (the stand it is pinned to), waiting (a first dress
    -- still retrying) }.
    known = {},
    -- The entry pinned on each team's stand.
    homes = {},
    -- Teams whose flag the incidents say is away from home (grabbed, until
    -- it is reset, recovered or scored): never pinned meanwhile, so a flag
    -- just grabbed off its own stand is not drawn back on it. Only placement
    -- follows incidents; colours never do.
    away = {},
    -- Every skull actor the watch has seen (main.lua's track/liveIn).
    skulls = {},
    watched = false,
    sweeps = 0,
}

--- The level's `ctf` block while a CTF game runs on it. Every converted map
--- has the block, and Oddball's ball is the same skull actor: on a map that
--- offers both (TST) the ball was dressed as a flag.
function Teams.ctfLevel()
    local level = env and env.Current.level
    local ctf = type(level) == "table" and level.ctf
    if type(ctf) ~= "table" or type(ctf.flag) ~= "table" then return nil end
    if string.lower(tostring(env.variant())) ~= "ctf" then return nil end
    return ctf
end

--- Hide the skull's own meshes, all but ours (`mine`). The game shows them
--- again (the skull came back at the foot of the flag after it was dressed),
--- so this runs whenever the skull's parts are removed.
local function hideSkull(actor, mine)
    if not mine then
        local entry = Flags.known[actor:GetFullName()]
        mine = entry and entry.comp
    end
    env.hideAllBut(actor, mine)
end

local function quenchSkull(actor)
    hideSkull(actor)
    for _, c in ipairs(components(actor, ACTOR_COMPONENT)) do
        pcall(function()
            local name = c:GetFullName()
            for _, part in ipairs(SKULL_PARTS) do
                if name:find(part, 1, true) then
                    c:Deactivate()
                    c:K2_DestroyComponent(c)
                end
            end
        end)
    end
end

--- Put CE's flag mesh on a skull actor, at `pos` (cm), `rot` (pitch, yaw,
--- roll) and `scale` relative to it, in `team`'s colours. The skull's own
--- meshes go (quenchSkull hides them, now and whenever the game shows them
--- again); the actor, which follows the flag, stays.
local function attachFlagMesh(world, entry, ctf, team, pos, rot, scale)
    local flag, actor = ctf.flag, entry.actor
    local mesh = env.resolveMesh(flag.mesh)
    if not mesh then error("mesh not found: " .. tostring(flag.mesh)) end
    local comp = actor:AddComponentByClass(classOf(STATIC), false, {
        Rotation = { X = 0, Y = 0, Z = 0, W = 1 },
        Translation = { X = 0, Y = 0, Z = 0 },
        Scale3D = { X = 1, Y = 1, Z = 1 },
    }, false)
    if not (comp and comp:IsValid()) then error("no mesh component") end
    comp.Mobility = MOBILITY_MOVABLE
    comp:SetStaticMesh(mesh)
    comp:SetCollisionEnabled(COLLISION_NONE)
    comp:K2_SetRelativeLocationAndRotation({ X = pos[1], Y = pos[2], Z = pos[3] },
        { Pitch = rot[1], Yaw = rot[2], Roll = rot[3] }, false, env.Current.hit, false)
    comp:SetRelativeScale3D({ X = scale, Y = scale, Z = scale })
    hideSkull(actor, comp)
    local materials = type(flag.materials) == "table" and flag.materials[team]
    local applied, failed = env.applyMaterials(comp, materials, world, "flag_" .. team)
    Log(string.format("CTF: %s flag dressed%s (%d material(s), %d failed)", team,
        entry.fp and " in first person" or "", applied, failed))
    return comp
end

--- Take `entry` off every stand it is recorded on.
local function release(entry)
    for team, home in pairs(Flags.homes) do
        if home == entry then Flags.homes[team] = nil end
    end
end

--- Picked up (or no longer by its stand), a flag follows its actor again.
local function unpin(entry, flag)
    release(entry)
    local was = entry.home
    entry.home = nil
    local comp = entry.comp
    if not (was and comp and comp:IsValid()) then return end
    local p = type(flag) == "table" and flag.pos or { 0, 0, 0 }
    comp:SetAbsolute(false, false, false)
    comp:K2_SetRelativeLocationAndRotation({ X = p[1], Y = p[2], Z = p[3] },
        { Pitch = 0, Yaw = 0, Roll = 0 }, false, env.Current.hit, false)
end

--- A flag at home is drawn exactly on its stand, facing the stand's way.
local function pin(entry, flag, stand)
    local other = Flags.homes[entry.team]
    if other and other ~= entry then unpin(other, flag) end
    release(entry)
    local p, yaw = flag.pos or { 0, 0, 0 }, math.rad(stand.yaw or 0)
    entry.comp:SetAbsolute(true, true, false)
    entry.comp:K2_SetWorldLocationAndRotation({
        X = stand.pos[1] + p[1] * math.cos(yaw) - p[2] * math.sin(yaw),
        Y = stand.pos[2] + p[1] * math.sin(yaw) + p[2] * math.cos(yaw),
        Z = stand.pos[3] + p[3],
    }, { Pitch = 0, Yaw = stand.yaw or 0, Roll = 0 }, false, env.Current.hit, false)
    entry.home = stand
    Flags.homes[entry.team] = entry
end

--- Whether a flag hangs off another actor (a carrier).
local function attached(actor)
    local ok, parent = pcall(function() return actor:GetAttachParentActor() end)
    return ok and parent ~= nil and parent:IsValid()
end

--- Pin a world flag that lies by its own team's stand, loose and with its
--- team's flag not away; let any other follow its actor.
local function placeFlag(entry, ctf)
    local comp = entry.comp
    if entry.fp or not (comp and comp:IsValid()) then return end
    local stand = nil
    if not Flags.away[entry.team] and not attached(entry.actor) then
        stand = Teams.homeStand(ctf.stands, entry.team, entry.actor:K2_GetActorLocation(), Teams.PIN_CM)
    end
    if stand and entry.home ~= stand then
        pin(entry, ctf.flag, stand)
    elseif not stand and entry.home then
        unpin(entry, ctf.flag)
    end
end

--- The team a flag actor's colours should be, and what it was read from:
--- a world flag's model variant; for the flag in first person, the enemy of
--- the local player's team.
local function flagTeamOf(entry)
    if entry.fp then
        local pawn = env.getPawn()
        local own = pawn and pawnTeam(pawn)
        return Teams.enemyOf(own), own
    end
    local variant = variantOf(entry.actor)
    return Teams.flagTeam(variant), variant
end

--- What the user's test reads: the variant beside the tag index, which
--- differs between the two flag types.
local function describe(entry, team, read)
    if entry.fp then
        return string.format("CTF: %s: first-person flag is %s (the local player is on %s; its own variant %q)",
            entry.name, team, tostring(read), tostring(variantOf(entry.actor)))
    end
    local tag, object, parent = indicesOf(entry.actor)
    return string.format("CTF: %s: variant %q, tag index %s, object %s, parent %s: %s",
        entry.name, tostring(read), tostring(tag), tostring(object), tostring(parent), team)
end

--- Dress a flag actor in its team's colours, or recolour it if its team
--- reads differently now (an actor the game reused), and place it. `tries`
--- (a first dress) retries every 100 ms while the team cannot be read yet:
--- a world flag's variant arrives with its first update, normally within
--- the 50 ms the watch waits; the local player's team after their spawn.
--- After 2 s the flag is left as the skull it is drawn by, and logged,
--- rather than given a guessed colour; the sweep reads it again. The skull
--- is put out only once the flag mesh is on, so a flag whose team cannot be
--- read is still seen and carried.
local function dress(entry, tries)
    local actor = entry.actor
    if not actor:IsValid() then return end
    local ctf, world = Teams.ctfLevel(), env.getWorld()
    if not (ctf and world) then return end
    local team, read = flagTeamOf(entry)
    if not team then
        if tries and tries < 20 then
            entry.waiting = true
            ExecuteInGameThreadWithDelay(100, function()
                local ok, err = pcall(dress, entry, tries + 1)
                if not ok then
                    entry.waiting = false
                    Log("CTF flag: " .. tostring(err))
                end
            end)
            return
        end
        entry.waiting = false
        if not entry.unreadSaid then
            entry.unreadSaid = true
            if entry.fp then
                Log(string.format("CTF: %s: the local player's team cannot be read (%s); the flag in first person waits",
                    entry.name, tostring(read)))
            else
                local tag, object = indicesOf(actor)
                Log(string.format("CTF: %s: no model variant after 2 s (%q, tag index %s, object %s); left as the skull",
                    entry.name, tostring(read), tostring(tag), tostring(object)))
            end
        end
        return
    end
    entry.waiting = false
    local comp = entry.comp
    if not (comp and comp:IsValid()) then
        local f = entry.fp and FP_FLAG or { pos = ctf.flag.pos or { 0, 0, 0 }, rot = { 0, 0, 0 }, scale = ctf.flag.scale or 1.0 }
        release(entry)
        entry.home = nil
        entry.comp = attachFlagMesh(world, entry, ctf, team, f.pos, f.rot, f.scale)
        entry.team = team
        pcall(quenchSkull, actor)
        Log(describe(entry, team, read))
    elseif entry.team ~= team then
        env.applyMaterials(comp, type(ctf.flag.materials) == "table" and ctf.flag.materials[team], world,
            "flag_" .. team)
        Log(describe(entry, team, read) .. " (was " .. tostring(entry.team) .. ": recoloured)")
        release(entry)
        entry.team = team
    end
    placeFlag(entry, ctf)
end

local function forget(key, entry)
    release(entry)
    Flags.known[key] = nil
end

--- Whether `entry` wears its flag mesh, so its skull may be put out.
local function dressed(entry)
    return entry ~= nil and entry.comp ~= nil and entry.comp:IsValid()
end

--- Take in a flag actor not known yet, and quench a dressed one's skull.
local function handleSkull(actor)
    if not actor:IsValid() then return end
    local key = actor:GetFullName()
    local entry = Flags.known[key]
    -- A name the game used again (a new actor where a destroyed one was) is
    -- a new flag; the comp check in dress re-dresses a reused one.
    if entry and entry.actor:IsValid() then
        if dressed(entry) then pcall(quenchSkull, actor) end
        return
    end
    if entry then release(entry) end
    local class = classNameOf(actor)
    if class ~= FLAG_ACTOR_CLASS and class ~= FP_FLAG_ACTOR_CLASS then return end
    entry = { actor = actor, name = key:match("([^%.:]+)$") or key, fp = class == FP_FLAG_ACTOR_CLASS }
    Flags.known[key] = entry
    dress(entry, 0)
end

--- Every skull actor the game makes from now on (a flag made, and maybe
--- picked up or dropped, and the first-person one) is handled as it
--- appears, once its components exist. A FindAllOf covers those made
--- before, once, as the watch is armed.
local function watchSkulls()
    if Flags.watched or not env.mayArm("skulls") then return end
    Flags.watched = pcall(NotifyOnNewObject, SKULL_ACTOR_CLASS_PATH, function(actor)
        env.track(Flags.skulls, actor)
        ExecuteInGameThreadWithDelay(50, function()
            if not Teams.ctfLevel() then return end
            local ok, err = pcall(handleSkull, actor)
            if not ok then Log("CTF flag: " .. tostring(err)) end
        end)
        -- The effect and its sound start a little after the actor.
        for _, ms in ipairs({ 500, 2000 }) do
            ExecuteInGameThreadWithDelay(ms, function()
                if Teams.ctfLevel() and actor:IsValid() and dressed(Flags.known[actor:GetFullName()]) then
                    pcall(quenchSkull, actor)
                end
            end)
        end
    end)
    if Flags.watched then
        for _, actor in ipairs(FindAllOf(FLAG_ACTOR_CLASS) or {}) do env.track(Flags.skulls, actor) end
        Log("CTF: watching for flag actors")
    end
end

--- Each known flag: quenched (the skull's effect comes back as a flag changes
--- hands), its team read again and repaired, its place checked.
local function refreshFlags()
    for key, entry in pairs(Flags.known) do
        if not entry.actor:IsValid() then
            forget(key, entry)
        else
            if dressed(entry) then pcall(quenchSkull, entry.actor) end
            if not entry.waiting then
                local ok, err = pcall(dress, entry)
                if not ok then Log("CTF flag: " .. tostring(err)) end
            end
        end
    end
end

--- MJOLNIRLevelLoader's 1.5 s loop on a CTF level: arms the watch, and every
--- other pass takes in any skull the watch's own handling missed and
--- refreshes every flag. The sweep was a FindAllOf once: at 0.3 s, twice a
--- pass, the game stuttered, and at 3 s it still cost a 20 ms frame.
function Teams.flagTick()
    if not (env and env.Current.furnished and Teams.ctfLevel()) then return end
    watchSkulls()
    Flags.sweeps = Flags.sweeps + 1
    if Flags.sweeps % 2 == 0 then return end
    for _, actor in ipairs(env.liveIn(Flags.skulls)) do
        local ok, err = pcall(handleSkull, actor)
        if not ok then Log("CTF flag: " .. tostring(err)) end
    end
    refreshFlags()
end

--- A new round resets in place, on the same world: every flag is made again
--- at its stand.
local function roundReset()
    local flag = Teams.ctfLevel() and Teams.ctfLevel().flag
    for _, entry in pairs(Flags.known) do
        if entry.home then pcall(unpin, entry, flag) end
    end
    Flags.homes, Flags.away = {}, {}
end

--- An incident, as the loader plays it (main.lua's playEvent). A flag's
--- incident carries the flag's team as its value (CTF's TEAM_INDEX, 0 red,
--- 1 blue): a grab takes that team's flag off its stand at once, and any
--- flag incident is the cue to look at the flags again 200 ms on. `round_over`
--- starts the next round.
function Teams.onIncident(name, value)
    if type(name) ~= "string" then return end
    if name == "round_over" then
        roundReset()
        return
    end
    if not name:find("^flag_") or not Teams.ctfLevel() then return end
    local team = NUMBERED[value]
    if team and name == "flag_grabbed" then
        Flags.away[team] = true
        local home = Flags.homes[team]
        if home then pcall(unpin, home, Teams.ctfLevel().flag) end
    elseif team and (name == "flag_reset" or name == "flag_recovered" or name == "flag_scored") then
        Flags.away[team] = nil
    end
    ExecuteInGameThreadWithDelay(200, function()
        if Teams.ctfLevel() then refreshFlags() end
    end)
end

--- Whether this PC has the blue flag's container (asked once a session).
function Teams.blueFlagInstalled()
    if Teams.blueFlag == nil then
        local ok, found = pcall(Teams.containerInstalled, Teams.BLUE_FLAG_CONTAINER, env and env.modDir, env and env.decode)
        Teams.blueFlag = ok and found == true
    end
    return Teams.blueFlag
end

--------------------------------------------------------------------------------
-- Team armour
--------------------------------------------------------------------------------

--- The Spartan's Mk V Classic armour material has one colour (`Armor
--- Color`, Master Chief's olive) whatever team the simulation puts the
--- player on, though the biped's team component knows it.
local ARMOR = {
    red = { R = 1.0, G = 0.0, B = 0.0, A = 1 },
    blue = { R = 0.03, G = 0.15, B = 1.0, A = 1 },
}
-- The colour the armour shows is `Armor Color` with association 0 (a layer
-- parameter, EMaterialParameterAssociation::LayerParameter) at index 0,
-- which only the by-info setter reaches: the plain setter writes index -1,
-- which this layered material never reads, and changed nothing on screen.
-- Found by giving each association and index its own colour (2026-10-01).
-- Made in init: an FName needs UE4SS.
local ARMOR_COLOR = nil

local SPARTAN_CLASS_PATH = "/Game/_Prototypes/SynchronizationTestContent/TestActor/BP_SpartansBipedActor.BP_SpartansBipedActor_C"
local PAWN_CLASS_PATH = "/Game/Blueprints/BP_MeteoritePawn.BP_MeteoritePawn_C"

--- The game's own events, all Blueprint functions with bytecode of their
--- own (`mjolnir ue disasm`: each stores its parameters and enters the
--- ubergraph). A hook on a native function with parameters crashed UE4SS;
--- these are safe. Each fires once a spawn or a mesh apply.
local HOOKS = {
    -- An actor starts standing for a biped: a spawn, or a pooled actor
    -- reused (exe 0x7a19690), which raises no mesh event when the armour is
    -- the same.
    { SPARTAN_CLASS_PATH .. ":BP_OnGameplayStart", "start" },
    -- The mesh synchronization has applied meshes and materials (raised
    -- last, exe 0x7a26040). The node keeps the Elite Blueprint's name it was
    -- copied from.
    { SPARTAN_CLASS_PATH .. ":BndEvt__BP_EliteBipedActor_BlamMeshSynchronization_K2Node_ComponentBoundEvent_4_OnRegionsChanged__DelegateSignature", "biped" },
    -- The same for the local player's own arms and legs.
    { PAWN_CLASS_PATH .. ":BndEvt__BP_MeteoritePawn_ArmsMeshSynchronizationComponent_K2Node_ComponentBoundEvent_1_OnRegionsChanged__DelegateSignature", "pawn" },
    { PAWN_CLASS_PATH .. ":BndEvt__BP_MeteoritePawn_LegsMeshSynchronizationComponent_K2Node_ComponentBoundEvent_0_OnRegionsChanged__DelegateSignature", "pawn" },
}

--- Each mesh component's class names its role, the same whatever armour
--- the simulation chose, and the role names the Mk V mesh; `armor` roles
--- also take the team colour. The shields keep their own material (an empty
--- or camo shell, the same for every armour).
local MKV = "/Game/Characters/Spartans/MkV_Classic/"
local MKV_FP = "/Game/Characters/SpartansFP/MkV_Classic/"
local MKV_ARMOR = MKV .. "Materials/MI_Spartans_MkV_Classic.MI_Spartans_MkV_Classic"
local BIPED_ROLES = {
    BPC_SkeletalMesh_C = { mesh = MKV .. "Mesh/SK_Spartans_MkV_Classic.SK_Spartans_MkV_Classic", armor = true },
    BPC_TranslucentSkeletalMesh_C = { mesh = MKV .. "Mesh/SK_Spartans_MkV_Classic_Shield.SK_Spartans_MkV_Classic_Shield" },
}
-- The local player's own view: first-person arms and their shield, the legs
-- seen looking down and their shield, and the body that casts its shadow.
local PAWN_ROLES = {
    BPC_FP_SkeletalMesh_C = { mesh = MKV_FP .. "Mesh/SK_SpartansFP_MkV_Classic.SK_SpartansFP_MkV_Classic", armor = true },
    BPC_FP_TranslucentSkeletalMesh_C = { mesh = MKV_FP .. "Mesh/SK_SpartansFP_MkV_Classic_Shield.SK_SpartansFP_MkV_Classic_Shield" },
    BPC_PAWN_SkeletalMesh_C = { mesh = MKV .. "Mesh/SK_Spartans_MkV_Classic_Legs.SK_Spartans_MkV_Classic_Legs", armor = true },
    BPC_FP_ShadowSkeletalMesh_C = {
        mesh = MKV .. "Mesh/SK_Spartans_MkV_Classic_NonNanite_Shadow.SK_Spartans_MkV_Classic_NonNanite_Shadow",
        armor = true,
    },
    BPC_TranslucentSkeletalMesh_C = { mesh = MKV .. "Mesh/SK_Spartans_MkV_Classic_ShieldLegs.SK_Spartans_MkV_Classic_ShieldLegs" },
}
--- Every other armour hangs static plates and a helmet on the body (11 to 17
--- plates on the biped, 6 on the arms and 9 on the legs for Chief's
--- default), each in its own coating: Mk V Classic has none, so in a team
--- game any there are hidden.
local PLATES = { BPC_StaticMesh_C = true, BPC_FP_StaticMesh_C = true, BPC_PAWN_StaticMesh_C = true }

local Armor = {
    -- Bipeds and pawns seen, by full name: { actor, pawn, team (the colour
    -- it wears), body (its armour mesh), pending }.
    records = {},
    -- Hook path -> the function hooked (hooked again once it is gone;
    -- never removed).
    hooks = {},
    -- Components hidden here, by full name: only these are ever shown again
    -- (the shadow body is hidden by the game and must stay so).
    hidden = {},
    seeded = false,
}

--- A skeletal mesh component's mesh, through its getter. The `SkeletalMesh`
--- property is UE 5.1's deprecated mirror of `SkinnedAsset` (both are in the
--- game's reflection), which a mesh set at run time need not update: read
--- alone, every armour mesh could come back empty and nothing be dressed.
local function meshOf(c)
    for _, read in ipairs({
        function() return c:GetSkeletalMeshAsset() end,
        function() return c.SkinnedAsset end,
        function() return c.SkeletalMesh end,
    }) do
        local ok, mesh = pcall(read)
        if ok and mesh and mesh:IsValid() then return mesh end
    end
    return nil
end

--- Lone Wolf's and Spartan's cloth and MkIV's thighs: second meshes of a
--- role, which no Mk V has.
local function extraPart(meshName)
    return meshName:find("_Cloth", 1, true) ~= nil or meshName:find("Thigh", 1, true) ~= nil
end

local function hidePart(c)
    c:SetHiddenInGame(true, false)
    c:SetVisibility(false, false)
    Armor.hidden[c:GetFullName()] = true
end

local function showPart(c)
    local key = c:GetFullName()
    if not Armor.hidden[key] then return end
    Armor.hidden[key] = nil
    c:SetHiddenInGame(false, false)
    c:SetVisibility(true, false)
end

--- Dress `actor`'s Spartan meshes (`roles`) for a team: the main mesh of each
--- role in Mk V Classic, swapped when the simulation chose another armour;
--- any second mesh of a role, and the plain-class MkIV thighs, hidden; every
--- plate and helmet hidden; the armour tinted `color` on an MJOLNIR instance
--- of the Mk V material. The biped's own plain `body` component is the
--- animation leader, never drawn, and never touched; nor is a component
--- with no mesh. Returns how many armour meshes were tinted, the first
--- foreign mesh swapped (nil if none), and the first armour mesh.
local function dressMeshes(actor, roles, color)
    local kept, armour, swapped = {}, {}, nil
    for _, c in ipairs(components(actor, SKELETAL)) do
        local cls = classNameOf(c)
        local current = meshOf(c)
        local meshName = current and current:GetFName():ToString() or ""
        local role = meshName ~= "" and roles[cls] or nil
        if role and not kept[cls] and not extraPart(meshName) then
            kept[cls] = true
            local mk5 = env.resolveMesh(role.mesh)
            if mk5 then
                if not (current and current:IsValid() and current:GetFullName() == mk5:GetFullName()) then
                    c:SetSkeletalMeshAsset(mk5)
                    swapped = swapped or meshName
                end
                showPart(c)
                if role.armor then armour[#armour + 1] = c end
            end
        elseif role or (cls == "SkeletalMeshComponent" and meshName:find("Thigh", 1, true)) then
            hidePart(c)
        end
    end
    for _, c in ipairs(components(actor, STATIC)) do
        if PLATES[classNameOf(c)] then hidePart(c) end
    end
    local base = #armour > 0 and env.resolveMesh(MKV_ARMOR)
    local tinted = 0
    for _, c in ipairs(armour) do
        local mat = c:GetMaterial(0)
        local matName = mat and mat:IsValid() and mat:GetFName():ToString() or ""
        if not matName:find("^MJ_TeamArmor") then
            mat = base and c:CreateDynamicMaterialInstance(0, base, FName("MJ_TeamArmor"))
        end
        if mat and mat:IsValid() then
            mat:SetVectorParameterValueByInfo(ARMOR_COLOR, color)
            tinted = tinted + 1
        end
    end
    return tinted, swapped, armour[1]
end

local function recordTeam(r)
    if r.pawn then return pawnTeam(r.actor) end
    return teamOf(r.actor)
end

--- Tint a recorded biped or pawn for its team; false while it has none.
local function tint(r)
    local actor = r.actor
    if not (actor and actor:IsValid() and Teams.teamGame()) then return false end
    local team = recordTeam(r)
    local color = team and ARMOR[team]
    if not color then
        r.team = nil
        return false
    end
    local tinted, swapped, body = dressMeshes(actor, r.pawn and PAWN_ROLES or BIPED_ROLES, color)
    r.team, r.body = tinted > 0 and team or nil, body
    -- Which way the armour came, once a world each, for the user's test.
    if swapped then
        r.swapped = true
        sayOnce("swapped", string.format("team colours: %s wore %s: swapped to Mk V Classic here, plates and helmet "
            .. "hidden (the native team-armour switch is off or missing)", r.name, swapped))
    elseif tinted > 0 and not r.swapped then
        sayOnce("native", "team colours: " .. r.name .. " came in Mk V Classic from the simulation; tinted " .. team)
    elseif tinted == 0 then
        -- Normal for a moment while a mesh loads; every Spartan staying
        -- olive with only this line means no armour mesh was read at all.
        sayOnce("untinted", "team colours: " .. r.name .. " on " .. team .. " has no armour mesh to tint yet")
    end
    return tinted > 0
end

--- Whether a tinted record still wears its tint: its armour mesh is Mk V
--- with an MJOLNIR instance on it (a late mesh apply puts the player's own
--- armour back).
local function intact(r)
    local body = r.body
    if not (body and body:IsValid()) then return false end
    local ok, good = pcall(function()
        local mesh, mat = meshOf(body), body:GetMaterial(0)
        return mesh ~= nil and mesh:GetFName():ToString():find("MkV_Classic", 1, true) ~= nil
            and mat:IsValid() and mat:GetFName():ToString():find("^MJ_TeamArmor") ~= nil
    end)
    return ok and good == true
end

--- The record of a biped or pawn, made on first sight.
local function record(actor, isPawn)
    local ok, key = pcall(function() return actor:GetFullName() end)
    if not ok or type(key) ~= "string" or key:find("Default__", 1, true) then return nil end
    local r = Armor.records[key]
    if not r then
        r = { pawn = isPawn, name = key:match("([^%.:]+)$") or key }
        Armor.records[key] = r
    end
    r.actor = actor
    return r
end

--- Tint on the next tick (out of the hook), and for a new biped again 0.5 s
--- on: its team may arrive after the event.
local function queueTint(actor, isPawn, again)
    local r = record(actor, isPawn)
    if not r or r.pending then return end
    r.pending = true
    ExecuteInGameThread(function()
        r.pending = false
        local ok, err = pcall(tint, r)
        if not ok then Log("team colours: " .. tostring(err)) end
    end)
    if again then
        ExecuteInGameThreadWithDelay(500, function()
            local ok, err = pcall(tint, r)
            if not ok then Log("team colours: " .. tostring(err)) end
        end)
    end
end

--- The hooks only note the actor and queue the work.
local function onHook(kind, ctx)
    if not Teams.teamGame() then return end
    local ok, actor = pcall(function() return ctx:get() end)
    if ok and actor and actor:IsValid() then queueTint(actor, kind == "pawn", kind == "start") end
end

--- Whether the function a hook was put on is still there: valid, and by
--- name, since a collected function's slot can hold another object.
local function hooked(path)
    local fn = Armor.hooks[path]
    if fn == nil then return false end
    local ok, name = pcall(function() return fn:IsValid() and fn:GetFullName() end)
    return ok and type(name) == "string" and name:sub(-#path) == path
end

--- RegisterHook raises while the Blueprint is not loaded (not at the main
--- menu, where the mod starts), so the hooks are armed in a map, each once
--- its function is found (~2 ms by path), at most every 10 s. A level change
--- can collect a Blueprint's functions, and a hook on the old one never
--- fires again: one whose function is gone is hooked again, as MJOLNIRHud
--- does its frame hook. Hooks are never removed.
local function armHooks()
    local missing = false
    for _, h in ipairs(HOOKS) do
        if not hooked(h[1]) then missing = true end
    end
    if not missing or not env.mayArm("team hooks") then return end
    for _, h in ipairs(HOOKS) do
        local fn = not hooked(h[1]) and env.findObject(h[1])
        if fn then
            local kind = h[2]
            if pcall(RegisterHook, h[1], function(ctx) onHook(kind, ctx) end) then
                Armor.hooks[h[1]] = fn
                Log("team colours: hooked " .. h[1]:match("([^%.]+)$"))
            end
        end
    end
end

function Teams.teamGame()
    local level = env and env.Current.level
    return type(level) == "table" and level.multiplayer == true
        and Teams.TEAM_GAMES[string.lower(tostring(env.variant()))] == true
end

--- MJOLNIRLevelLoader's 1.5 s loop in a team game: arms the hooks, takes in
--- the Spartans there before them (one FindAllOf a world, once the hooks are
--- in), and checks each record: a team change or a tint undone (a pooled
--- actor reused with no mesh event, a late apply) is tinted again. No object
--- walks here.
function Teams.armorTick()
    if not (env and env.Current.furnished and Teams.teamGame()) then return end
    armHooks()
    local pawn = env.getPawn()
    if pawn then record(pawn, true) end
    if not Armor.seeded and hooked(HOOKS[1][1]) then
        Armor.seeded = true
        for _, actor in ipairs(FindAllOf("BP_SpartansBipedActor_C") or {}) do record(actor, false) end
    end
    for key, r in pairs(Armor.records) do
        if not (r.actor and r.actor:IsValid()) then
            Armor.records[key] = nil
        elseif not r.pending then
            local team = recordTeam(r)
            if team and (team ~= r.team or not intact(r)) then
                local ok, err = pcall(tint, r)
                if not ok then Log("team colours: " .. tostring(err)) end
            end
        end
    end
end

--------------------------------------------------------------------------------
-- Set-up and state
--------------------------------------------------------------------------------

--- `deps`: main.lua's Log, findObject, resolveMesh, applyMaterials,
--- hideAllBut, getPawn, getWorld, track, liveIn and mayArm; Current; `variant`,
--- a function returning the running game type; modDir; decode (JSON).
function Teams.init(deps)
    env = deps
    ARMOR_COLOR = { Name = FName("Armor Color"), Association = 0, Index = 0 }
end

--- A new world: nothing of the last one's flags or Spartans carries over.
function Teams.reset()
    Flags.known, Flags.homes, Flags.away = {}, {}, {}
    Armor.records, Armor.hidden, Armor.seeded = {}, {}, false
    Classes, Said = {}, {}
end

--- For mjolnir_level_status.
function Teams.status()
    local hooks, records, tinted, flags = 0, 0, 0, 0
    for _, h in ipairs(HOOKS) do
        if hooked(h[1]) then hooks = hooks + 1 end
    end
    for _, r in pairs(Armor.records) do
        records = records + 1
        if r.team then tinted = tinted + 1 end
    end
    for _ in pairs(Flags.known) do flags = flags + 1 end
    local homes = {}
    for team in pairs(Flags.homes) do homes[#homes + 1] = team end
    table.sort(homes)
    Log(string.format("team colours: %s game, native switch %s, %d/%d hook(s), %d Spartan(s) and pawn(s) seen, %d tinted",
        Teams.teamGame() and "team" or "not a team", tostring(Teams.native), hooks, #HOOKS, records, tinted))
    if Teams.ctfLevel() then
        Log(string.format("CTF: %d flag actor(s) known, at home: %s; blue flag container %s", flags,
            #homes > 0 and table.concat(homes, ", ") or "none", Teams.blueFlagInstalled() and "installed" or "MISSING"))
    end
end

return Teams

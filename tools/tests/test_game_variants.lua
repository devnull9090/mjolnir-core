-- Run from the repository root with Lua 5.4, or Python + lupa:
-- python -c "from lupa import LuaRuntime; LuaRuntime().execute(open('tools/tests/test_game_variants.lua').read())"
--
-- MJOLNIRLobby's modes.lua, and the tables in other files that must agree
-- with it: the engine tiles, what a map's modes list brings, the exact-variant
-- channel to the level loader, and every id-keyed table a game type needs.
local Modes = dofile("mods/MJOLNIRLobby/Scripts/modes.lua")
local VariantSettings = dofile("mods/MJOLNIRLevelLoader/Scripts/variant_settings.lua")
local VehicleSets = dofile("mods/MJOLNIRLevelLoader/Scripts/vehicle_sets.lua")
local Teams = dofile("mods/MJOLNIRLevelLoader/Scripts/teams.lua")

local function eq(actual, expected, label)
    assert(actual == expected, (label or "value") .. ": expected " .. tostring(expected) .. ", got " .. tostring(actual))
end

local function read(path)
    local f = assert(io.open(path, "rb"), path)
    local data = f:read("a")
    f:close()
    return data
end

local function ids(list)
    local out = {}
    for _, m in ipairs(list) do out[#out + 1] = m.id end
    return table.concat(out, " ")
end

-- The contract: every id is a variant file name and a hub game_type.
local seen = {}
for _, mode in ipairs(Modes) do
    assert(mode.id:match("^[a-z_]+$") and #mode.id <= 24, mode.id .. ": not a game_type the hub takes")
    assert(not seen[mode.id], mode.id .. ": listed twice")
    seen[mode.id] = true
    assert(mode.engine and mode.name and mode.description and mode.slot, mode.id .. ": incomplete row")
    assert(mode.slot <= 7, mode.id .. ": past the eight insertion point copies")
end
eq(#Modes, 16, "16 variants")
eq(Modes.byId("crazy_king").name, "CRAZY KING", "byId")
eq(Modes.byId("nope"), nil, "unknown id")
eq(Modes.slot("rally"), 6, "the Race family's slot")
eq(Modes.slot("juggernaut"), 4, "Juggernaut's slot is the Oddball family's")
eq(Modes.slot("stalker"), 4, "Stalker's too")
eq(Modes.slot("reverse_tag"), 4, "Reverse Tag's too")
eq(Modes.byId("stalker").name, "STALKER", "Stalker's menu name")
eq(Modes.byId("reverse_tag").name, "REVERSE TAG", "Reverse Tag's menu name")
eq(Modes.byId("trait_test"), nil, "the trait test is never in the lobby")
eq(Modes.slot("nope"), nil, "an unknown id has no slot")

-- Six tiles, in the menu's order, with every variant under its engine.
local tiles = Modes.engines(Modes)
eq(#tiles, 6, "six tiles: the cooked screens have no more")
eq(ids(tiles), "slayer ctf oddball koth race forge", "tile order")
eq(ids(tiles[1].variants), "slayer team_slayer", "Slayer's variants")
eq(ids(tiles[2].variants), "ctf", "CTF's variants")
eq(ids(tiles[3].variants), "oddball team_oddball juggernaut stalker reverse_tag", "Oddball's variants")
eq(ids(tiles[4].variants), "koth crazy_king team_koth", "King's variants")
eq(ids(tiles[5].variants), "race team_race rally team_rally", "Race's variants")
eq(tiles[2].name, "CAPTURE THE FLAG", "a tile has its engine's name")
eq(tiles[4].name, "KING OF THE HILL", "a tile has its engine's name")

-- What a level's engine ids bring.
local function offered(...)
    local listed = {}
    for _, id in ipairs({ ... }) do listed[id] = true end
    Modes.derive(listed)
    local out = {}
    for _, mode in ipairs(Modes) do
        if listed[mode.id] then out[#out + 1] = mode end
    end
    return out
end
eq(ids(offered("slayer")), "slayer team_slayer juggernaut stalker reverse_tag",
    "Slayer brings Team Slayer, and Stalker and Reverse Tag wherever Juggernaut goes")
eq(ids(offered("koth")), "koth crazy_king team_koth", "King brings its family")
eq(ids(offered("oddball")), "oddball team_oddball", "Oddball brings Team Oddball")
eq(ids(offered("race")), "race team_race rally team_rally", "Race brings its family")
eq(ids(offered("ctf")), "ctf", "CTF brings nothing")
-- On a Slayer-only map the Oddball tile holds the variants that only spawn.
local slayerOnly = Modes.engines(offered("slayer"))
eq(ids(slayerOnly), "slayer oddball", "tiles on a Slayer-only map")
eq(ids(slayerOnly[2].variants), "juggernaut stalker reverse_tag", "the Oddball tile's variants there")
eq(slayerOnly[2].name, "JUGGERNAUT", "a tile without its namesake goes by its first variant")
eq(Modes.engines({ Modes.byId("oddball"), Modes.byId("juggernaut") })[1].name, "ODDBALL", "with it, the engine's name")

-- A tile steps through its variants; another tile keeps what it showed.
Modes.memory = {}
local slayer, king = tiles[1], tiles[4]
eq(Modes.shown(king, Modes[1]).id, "koth", "a tile starts on its first variant")
local choice = Modes.step(king, Modes[1])
eq(choice.id, "koth", "the first click only chooses the tile")
choice = Modes.step(king, choice)
eq(choice.id, "crazy_king", "the next click steps")
choice = Modes.step(king, choice)
choice = Modes.step(king, choice)
eq(choice.id, "koth", "the last variant wraps round")
choice = Modes.step(king, choice)
eq(Modes.step(slayer, choice).id, "slayer", "another tile chooses what it shows")
eq(Modes.shown(king, Modes.byId("slayer")).id, "crazy_king", "a tile left keeps its variant")
eq(Modes.step(king, Modes.byId("slayer")).id, "crazy_king", "and comes back to it")
eq(Modes.step(tiles[2], Modes.byId("ctf")).id, "ctf", "a lone variant stays")
Modes.memory = { koth = "gone" }
eq(Modes.shown(king, nil).id, "koth", "a remembered variant no longer offered is dropped")
Modes.memory = {}

-- The exact variant on disk, against a file system in memory.
do
    local files, writes = {}, 0
    local realOpen = io.open
    io.open = function(path, how)
        if how == "wb" then
            return {
                write = function(_, ...) files[path] = table.concat({ ... }); writes = writes + 1 end,
                close = function() end,
            }
        end
        local data = files[path]
        if not data then return nil end
        return { read = function() return data end, close = function() end }
    end
    local logged = {}
    local function log(line) logged[#logged + 1] = line end
    files["L\\variants\\crazy_king.mglo"] = "x"
    Modes.follow("L", "BGL", "crazy_king", log)
    eq(files["L\\match_variant.txt"], "BGL\tcrazy_king\n", "the id is written with its map")
    eq(Modes.missing, nil, "an installed variant is not missing")
    eq(Modes.missingNote(), "", "and the lobby says nothing")
    local before = writes
    Modes.follow("L", "BGL", "crazy_king", log)
    eq(writes, before, "the same choice is not written again")
    Modes.follow("L", "BGL", "", log)
    Modes.follow("L", "BGL", nil, log)
    Modes.follow("L", "BGL", "../evil", log)
    eq(files["L\\match_variant.txt"], "BGL\tcrazy_king\n", "an old host's empty field or a bad id changes nothing")
    Modes.follow("L", "BGL", "rally", log)
    eq(files["L\\match_variant.txt"], "BGL\trally\n", "a variant this PC lacks is still named")
    eq(Modes.missing, "rally", "and noted")
    assert(logged[1]:find("rally", 1, true), "and logged")
    assert(Modes.missingNote():find("RALLY", 1, true), "and the lobby says so")
    Modes.follow("L", "BGL", "rally", log)
    eq(#logged, 1, "logged once")
    Modes.follow("L", "BGL", "forge", log)
    eq(Modes.missing, nil, "Forge needs no variant file")
    io.open = realOpen
end

-- The loader takes that id only for its map and only where the slot agrees.
do
    local function have() return true end
    local function lack() return false end
    local exact = VariantSettings.exactVariant
    eq(exact("BGL\tcrazy_king\n", "BGL", 3, have), "crazy_king", "the file beats the slot's engine")
    eq(exact("BGL\tcrazy_king\r\n", "bgl", 3, have), "crazy_king", "any case, any line ending")
    eq(exact("BGL\tcrazy_king\n", "BGL", nil, have), "crazy_king", "a URL with no slot")
    eq(exact(nil, "BGL", 3, have), nil, "no file: the slot")
    eq(exact("", "BGL", 3, have), nil, "an empty file: the slot")
    eq(exact("BGL\tcrazy_king\n", nil, 3, have), nil, "a travel to the frontend")
    eq(exact("DTI\tcrazy_king\n", "BGL", 3, have), nil, "another map's choice: the slot")
    local id, why = exact("BGL\tcrazy_king\n", "BGL", 0, have)
    eq(id, nil, "a stale choice loses to the slot")
    assert(why:find("slot", 1, true), "and says so")
    id, why = exact("BGL\trally\n", "BGL", 6, lack)
    eq(id, nil, "a variant this PC lacks falls back")
    assert(why:find("rally.mglo", 1, true), "and says which")
    eq(exact("BGL\tforge\n", "BGL", 5, lack), "forge", "Forge has no file")
    eq(exact("BGL\tassault\n", "BGL", 3, have), "assault", "a newer host's id runs on its file")
end

-- The tables other files keep.
local function slots(text)
    local out = {}
    for slot, id in text:gmatch("%[(%d+)%]%s*=%s*\"([%w_]+)\"") do out[tonumber(slot)] = id end
    return out
end
local loader = read("mods/MJOLNIRLevelLoader/Scripts/main.lua")
local fallback = slots(assert(loader:match("local GAME_TYPE_SLOTS = (%b{})"), "GAME_TYPE_SLOTS"))
for _, mode in ipairs(Modes) do
    eq(VariantSettings.VARIANT_SLOTS[mode.id], mode.slot, mode.id .. " in VARIANT_SLOTS")
    eq(Modes.slot(fallback[mode.slot]), mode.slot, mode.id .. ": the slot's fallback is of the same family")
    eq(Teams.TEAM_GAMES[mode.id], mode.teams, mode.id .. " in Teams.TEAM_GAMES")
end
-- One vehicle per CE game type bit: which one a game type takes is its set.
local probes = {
    { type = "warthog", team = "red", label = "slayer", default = 1 },
    { type = "warthog", team = "red", label = "ctf", default = 2 },
    { type = "warthog", team = "red", label = "king", default = 4 },
    { type = "warthog", team = "red", label = "oddball", default = 8 },
}
local SETS = { slayer = "slayer", team_slayer = "slayer", ctf = "ctf", koth = "king", crazy_king = "king",
    team_koth = "king", oddball = "oddball", team_oddball = "oddball", juggernaut = "oddball",
    stalker = "oddball", reverse_tag = "oddball",
    race = "slayer", team_race = "slayer", rally = "slayer", team_rally = "slayer" }
for _, mode in ipairs(Modes) do
    if not mode.forge then
        local labels = VehicleSets.labelsFor(probes, mode.id, "red", { set = VehicleSets.DEFAULT })
        assert(labels[SETS[mode.id]], mode.id .. " should take " .. tostring(SETS[mode.id]) .. "'s vehicles")
    end
end

-- The start announcement matches by substring, in table order.
local events = assert(loader:match("local START_EVENTS = (%b{})"), "START_EVENTS")
local rows = {}
for key, event in events:gmatch("{%s*\"([%w_]+)\",%s*\"([%w_]+)\"%s*}") do rows[#rows + 1] = { key, event } end
local function startEvent(mode)
    for _, e in ipairs(rows) do
        if mode:find(e[1], 1, true) then return e[2] end
    end
    return "slayer_start"
end
local EXPECTED = { slayer = "slayer_start", team_slayer = "slayer_start", ctf = "ctf_game_start",
    oddball = "ball_game_start", team_oddball = "ball_game_start", juggernaut = "juggernaut_game_start",
    stalker = "juggernaut_game_start", reverse_tag = "juggernaut_game_start",
    koth = "koth_game_start", crazy_king = "koth_game_start", team_koth = "koth_game_start",
    race = "race_game_start", team_race = "race_game_start", rally = "race_game_start",
    team_rally = "race_game_start" }
for id, event in pairs(EXPECTED) do eq(startEvent(id), event, id .. "'s announcement") end

-- Every game type has a name in Discord and an icon that is cooked.
local presence = read("mods/MJOLNIRLobby/Scripts/presence.lua")
local gametype = read("mods/MJOLNIRLobby/Scripts/gametype.lua")
local icons = assert(gametype:match("local ICONS = (%b{})"), "ICONS")
local names = assert(presence:match("local MODES = (%b{})"), "presence names")
for _, mode in ipairs(Modes) do
    assert(names:find(mode.id .. " = ", 1, true), mode.id .. " has no Discord name")
    assert(icons:find(mode.id .. " = ", 1, true), mode.id .. " has no icon")
end

-- The lobby's main chunk has no room for locals (Lua's limit is 200).
assert(loadfile("mods/MJOLNIRLobby/Scripts/main.lua"), "the Lobby's main.lua compiles")
assert(loadfile("mods/MJOLNIRLevelLoader/Scripts/main.lua"), "the loader's main.lua compiles")

print("ok")

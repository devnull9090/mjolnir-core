-- Run from the repository root with Lua 5.4, or Python + lupa:
-- python -c "from lupa import LuaRuntime; LuaRuntime(encoding=None).execute(open('tools/tests/test_vehicle_sets.lua','rb').read())"
--
-- MJOLNIRLevelLoader's vehicle_sets.lua: which labels each team's vehicle
-- set takes, and the filters it appends to the variants
-- `mjolnir megalo write --vehicle-label-pool` makes
-- (tools/tests/fixtures/vehicle_sets).
local VehicleSets = dofile("mods/MJOLNIRLevelLoader/Scripts/vehicle_sets.lua")
local VariantSettings = dofile("mods/MJOLNIRLevelLoader/Scripts/variant_settings.lua")
local Json = dofile("mods/MJOLNIRLevelLoader/Scripts/json.lua")

local function eq(actual, expected, label)
    assert(actual == expected, (label or "value") .. ": expected " .. tostring(expected) .. ", got " .. tostring(actual))
end

local function read(path)
    local f = assert(io.open(path, "rb"), path)
    local data = f:read("a")
    f:close()
    return data
end

local function keys(set)
    local out = {}
    for k in pairs(set) do out[#out + 1] = k end
    table.sort(out)
    return table.concat(out, ",")
end

-- A symmetric map in the shape gen_ce_level.py writes (CE spawn flags:
-- default bits 0-3 slayer/ctf/king/oddball, allowed bits likewise).
local SLAYER, CTF = 1, 2
local vehicles = {}
local function place(type_, label, default, allowed)
    for _, team in ipairs({ "red", "blue" }) do
        vehicles[#vehicles + 1] = { type = type_, team = team, label = label, default = default, allowed = allowed }
    end
end
place("warthog", "ce_warthog_1", SLAYER + CTF, 15)
place("warthog", "ce_warthog_2", 0, 15)
place("ghost", "ce_ghost_1", SLAYER, 15)
place("ghost", "ce_ghost_2", 0, CTF)
place("scorpion", "ce_scorpion_1", CTF, 15)
place("banshee", "ce_banshee_1", 0, 15)

local default = VehicleSets.fromSettings({})
eq(keys(VehicleSets.labelsFor(vehicles, "slayer", "red", default.red)), "ce_ghost_1,ce_warthog_1", "Slayer default")
eq(keys(VehicleSets.labelsFor(vehicles, "ctf", "red", default.red)), "ce_scorpion_1,ce_warthog_1", "CTF default")
local choices = VehicleSets.fromSettings({ ["vehicles.red"] = 1 })
eq(keys(VehicleSets.labelsFor(vehicles, "slayer", "red", choices.red)), "", "NONE")
choices = VehicleSets.fromSettings({ ["vehicles.red"] = 2 })
eq(keys(VehicleSets.labelsFor(vehicles, "slayer", "red", choices.red)), "ce_warthog_1,ce_warthog_2", "WARTHOGS")
-- Custom: lowest ranks first, only what CE allows in the game type.
choices = VehicleSets.fromSettings({ ["vehicles.red"] = 8, ["vehicles.red.ghost"] = 2, ["vehicles.red.warthog"] = 1 })
eq(keys(VehicleSets.labelsFor(vehicles, "slayer", "red", choices.red)), "ce_ghost_1,ce_warthog_1", "CUSTOM in Slayer")
eq(keys(VehicleSets.labelsFor(vehicles, "ctf", "red", choices.red)), "ce_ghost_1,ce_ghost_2,ce_warthog_1", "CUSTOM in CTF")

-- Shared labels need no team; one team's alone are constrained to it.
choices = VehicleSets.fromSettings({ ["vehicles.blue"] = 6 })
local filters = VehicleSets.filters(vehicles, "slayer", choices)
local seen = {}
for _, f in ipairs(filters) do seen[#seen + 1] = f.label .. "@" .. tostring(f.team) end
eq(table.concat(seen, " "), "ce_banshee_1@1 ce_ghost_1@0 ce_warthog_1@0", "red default + blue banshees")

-- The filters go in after the variant's own and read back from the bits.
local function readFilters(bytes, at)
    local pos = at
    local function get(n)
        local v = 0
        for _ = 1, n do
            local byte = bytes:byte(math.floor(pos / 8) + 1)
            v = v * 2 + math.floor(byte / 2 ^ (7 - pos % 8)) % 2
            pos = pos + 1
        end
        return v
    end
    local out = {}
    for _ = 1, get(5) do
        local label = get(7) - 1
        local flags = get(3)
        local team = flags == 2 and (get(4) - 1) or nil
        get(7)
        out[#out + 1] = { label = label, team = team }
    end
    return out, #bytes * 8 - pos
end
-- Stalker is the one with script traits: the section sits before the filters.
for _, mode in ipairs({ "slayer", "ctf", "stalker" }) do
    local bytes = read("tools/tests/fixtures/vehicle_sets/" .. mode .. ".mglo")
    local layout = Json.decode(read("tools/tests/fixtures/vehicle_sets/" .. mode .. ".layout.json"))
    -- The layout's filters_at is where the variant's own filters really are,
    -- and they end the stream.
    local own, ownSpare = readFilters(bytes, layout.filters_at)
    eq(#own, #layout.filters, mode .. " own filters at filters_at")
    for i, filter in ipairs(layout.filters) do
        eq(own[i].label, filter.label, mode .. " own filter " .. i .. " at filters_at")
    end
    assert(ownSpare >= 0 and ownSpare < 8, mode .. ": " .. ownSpare .. " bits after its own filters")
    local out, added, dropped = VehicleSets.apply(bytes, layout, filters)
    assert(out, mode .. ": " .. tostring(added))
    eq(added, 3, mode .. " filters added")
    eq(dropped, 0, mode .. " none dropped")
    local back, spare = readFilters(out, layout.filters_at)
    eq(#back, #layout.filters + 3, mode .. " filters read back")
    for i, own in ipairs(layout.filters) do
        eq(back[i].label, own.label, mode .. " own filter " .. i .. " stays")
    end
    assert(spare >= 0 and spare < 8, mode .. ": " .. spare .. " bits after the filters")
    local last = back[#back]
    eq(last.label, layout.labels["ce_warthog_1"], mode .. " last filter's label")
    eq(last.team, 0, mode .. " last filter's team")
    -- The bits before the filters are the variant's own.
    eq(out:sub(1, math.floor(layout.filters_at / 8)), bytes:sub(1, math.floor(layout.filters_at / 8)),
        mode .. " untouched before the filters")
end

-- Stalker's two trait sets take strings 0-3 for their names and descriptions,
-- so every label sits four above Slayer's. A fixture without them fails here.
local slayer = Json.decode(read("tools/tests/fixtures/vehicle_sets/slayer.layout.json"))
local stalker = Json.decode(read("tools/tests/fixtures/vehicle_sets/stalker.layout.json"))
eq(stalker.filters[1].label, slayer.filters[1].label + 4, "Stalker's own filter above the trait names")
for label, index in pairs(slayer.labels) do
    eq(stalker.labels[label], index + 4, label .. " above the trait names")
end

-- The loader's order on a host: settings first, then the vehicle filters.
local hostSettings = VariantSettings.parse(read("tools/tests/fixtures/settings/settings.txt"))
local patched = assert(VariantSettings.apply(read("tools/tests/fixtures/vehicle_sets/stalker.mglo"), hostSettings))
local hosted = assert(VehicleSets.apply(patched, stalker, filters))
local back = readFilters(hosted, stalker.filters_at)
eq(#back, #stalker.filters + 3, "Stalker's filters after the host's settings")
eq(back[#back].label, stalker.labels["ce_warthog_1"], "Stalker's last filter after the host's settings")
eq(VariantSettings.get(hosted, "score"), 15, "the host's score survives the filters")

-- The variant holds 16 filters: the highest ranks are left out.
local many = {}
for r = 1, 20 do many[#many + 1] = { label = "ce_ghost_" .. math.min(r, 10), team = r % 2 } end
local layout = Json.decode(read("tools/tests/fixtures/vehicle_sets/ctf.layout.json"))
local _, added, dropped = VehicleSets.apply(read("tools/tests/fixtures/vehicle_sets/ctf.mglo"), layout, many)
eq(added, 16 - #layout.filters, "CTF fills to 16")
eq(dropped, 20 - added, "the rest left out")

print("Vehicle sets: defaults, NONE, one-type and custom sets per game type, team constraints, "
    .. "filters appended and read back with and without script traits, the 16-filter cap")

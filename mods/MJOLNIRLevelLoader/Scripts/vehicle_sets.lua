-- CE's vehicle sets, as object filters on a Megalo game variant
-- (docs/ce_map_conversion.md, "Vehicle sets").
--
-- A converted map places every CE vehicle hidden ("hide unless megalo
-- required") under a label it shares with its counterpart on the other team
-- (`ce_<type>_<rank>`), and lists them in its level's `vehicle_sets`: type,
-- team, label, and CE's default and allowed game types. The simulation
-- places a hidden vehicle only if the variant has an object filter on its
-- label (with a team constraint, only that team's). When a match starts the
-- loader picks each team's vehicles from the host's vehicle settings, as
-- CE's game variants did, and appends their filters to the variant.
--
-- The variants are written with every label in their string table and a
-- `<mode>.layout.json` beside them (`mjolnir megalo write
-- --vehicle-label-pool`): the bit their filters begin at (they end the
-- stream), the filters they already have, and each label's string index.
--
-- Plain arithmetic, no bitwise operators: the release lint reads mods as
-- LuaJIT + 5.2.

local VehicleSets = {}

-- CE's vehicle set choices, in its order; the settings line carries the
-- index (`vehicles.red=0`).
VehicleSets.SETS = { "DEFAULT", "NONE", "WARTHOGS", "GHOSTS", "SCORPIONS", "ROCKET WARTHOGS",
    "BANSHEES", "GUN TURRETS", "CUSTOM" }
VehicleSets.DEFAULT, VehicleSets.NONE, VehicleSets.CUSTOM = 0, 1, 8
-- The type each one-type set places, and the custom counts' keys, in CE's
-- order (`vehicles.red.warthog=2`).
VehicleSets.TYPES = { "warthog", "ghost", "scorpion", "rwarthog", "banshee", "turret" }
local PRESET_TYPE = { [2] = "warthog", [3] = "ghost", [4] = "scorpion", [5] = "rwarthog",
    [6] = "banshee", [7] = "turret" }
-- A game type's bit in CE's spawn flags (default bits 0-3, allowed 8-11).
local MODE_BIT = { slayer = 0, team_slayer = 0, ctf = 1, king = 2, koth = 2, oddball = 3 }
-- Owner team on the placements (gen_ce_level.py CE_OWNER_TEAMS): red 0, blue 1.
local TEAM_INDEX = { red = 0, blue = 1 }

local function hasBit(mask, bit) return math.floor((mask or 0) / 2 ^ bit) % 2 == 1 end

local function rankOf(label) return tonumber(tostring(label):match("_(%d+)$")) or 0 end

--- The host's vehicle settings out of a parsed settings line (`vehicles.*`
--- keys), with every other key left out; a team without one keeps CE's
--- default set.
function VehicleSets.fromSettings(settings)
    local out = {}
    for _, team in ipairs({ "red", "blue" }) do
        local choice = { set = (settings or {})["vehicles." .. team] or VehicleSets.DEFAULT, counts = {} }
        for _, t in ipairs(VehicleSets.TYPES) do
            choice.counts[t] = (settings or {})["vehicles." .. team .. "." .. t] or 0
        end
        out[team] = choice
    end
    return out
end

--- The labels team `team` (red/blue) takes for game type `mode` under
--- `choice` ({set, counts}), as a set of label -> true. A placement
--- without a team counts as red's.
function VehicleSets.labelsFor(vehicles, mode, team, choice)
    local bit = MODE_BIT[tostring(mode)] or 0
    local mine = {}
    for _, v in ipairs(vehicles or {}) do
        local t = (v.team == "blue") and "blue" or "red"
        if t == team and v.label then mine[#mine + 1] = v end
    end
    local out = {}
    local set = choice and choice.set or VehicleSets.DEFAULT
    if set == VehicleSets.NONE then return out end
    if set == VehicleSets.DEFAULT then
        for _, v in ipairs(mine) do
            if hasBit(v.default, bit) then out[v.label] = true end
        end
        return out
    end
    -- One type, or custom counts: the vehicles CE allows in this game
    -- type's custom sets, lowest ranks first.
    local want = {}
    if set == VehicleSets.CUSTOM then
        for t, n in pairs(choice.counts or {}) do want[t] = n end
    elseif PRESET_TYPE[set] then
        want[PRESET_TYPE[set]] = math.huge
    end
    local byType = {}
    for _, v in ipairs(mine) do
        if want[v.type] and hasBit(v.allowed, bit) then
            byType[v.type] = byType[v.type] or {}
            table.insert(byType[v.type], v)
        end
    end
    for t, list in pairs(byType) do
        table.sort(list, function(a, b) return rankOf(a.label) < rankOf(b.label) end)
        for i = 1, math.min(want[t], #list) do out[list[i].label] = true end
    end
    return out
end

--- The filters for both teams: a label both take has no team constraint,
--- one only a team takes is constrained to it. Each is {label, team};
--- lowest ranks first, so a cut drops the highest.
function VehicleSets.filters(vehicles, mode, choices)
    local red = VehicleSets.labelsFor(vehicles, mode, "red", choices.red)
    local blue = VehicleSets.labelsFor(vehicles, mode, "blue", choices.blue)
    local out = {}
    for label in pairs(red) do
        local both = blue[label]
        out[#out + 1] = { label = label, team = (not both) and TEAM_INDEX.red or nil }
    end
    for label in pairs(blue) do
        if not red[label] then out[#out + 1] = { label = label, team = TEAM_INDEX.blue } end
    end
    table.sort(out, function(a, b)
        if rankOf(a.label) ~= rankOf(b.label) then return rankOf(a.label) < rankOf(b.label) end
        if a.label ~= b.label then return a.label < b.label end
        return (a.team or -1) < (b.team or -1)
    end)
    return out
end

-- MSB-first bits appended to a byte string cut at bit `at`.
local function writer(bytes, at)
    local w = { parts = { bytes:sub(1, math.floor(at / 8)) }, acc = 0, n = 0 }
    -- The partial byte the filters start in keeps its leading bits.
    local rest = at % 8
    if rest > 0 then
        local byte = bytes:byte(math.floor(at / 8) + 1)
        w.acc, w.n = math.floor(byte / 2 ^ (8 - rest)), rest
    end
    function w.put(value, bits)
        for i = bits - 1, 0, -1 do
            w.acc = w.acc * 2 + math.floor(value / 2 ^ i) % 2
            w.n = w.n + 1
            if w.n == 8 then
                w.parts[#w.parts + 1] = string.char(w.acc)
                w.acc, w.n = 0, 0
            end
        end
    end
    function w.finish()
        if w.n > 0 then w.parts[#w.parts + 1] = string.char(w.acc * 2 ^ (8 - w.n)) end
        return table.concat(w.parts)
    end
    return w
end

--- `bytes` (a variant written with --vehicle-label-pool) with the vehicle
--- filters added after its own, as `layout` (its layout.json, decoded)
--- describes them. Returns the bytes, how many vehicle filters went in, and
--- how many did not fit; or nil and why.
function VehicleSets.apply(bytes, layout, wanted)
    if type(layout) ~= "table" or type(layout.filters_at) ~= "number" or type(layout.labels) ~= "table" then
        return nil, "no layout for the variant's filters"
    end
    local max = layout.max_filters or 16
    local filters = {}
    for _, f in ipairs(layout.filters or {}) do
        -- JSON null may decode to a sentinel rather than nil.
        filters[#filters + 1] = { index = f.label, team = type(f.team) == "number" and f.team or nil }
    end
    local own = #filters
    local dropped = 0
    for _, f in ipairs(wanted or {}) do
        local index = layout.labels[f.label]
        if index == nil then
            dropped = dropped + 1
        elseif #filters >= max then
            dropped = dropped + 1
        else
            filters[#filters + 1] = { index = index, team = f.team }
        end
    end
    if layout.filters_at > #bytes * 8 then return nil, "the layout does not match the variant" end
    local w = writer(bytes, layout.filters_at)
    w.put(#filters, 5)
    for _, f in ipairs(filters) do
        w.put(f.index + 1, 7)          -- string index, stored plus one
        if f.team then
            w.put(2, 3)                -- constraints: team
            w.put(f.team + 1, 4)       -- team, stored plus one
        else
            w.put(0, 3)
        end
        -- Minimum count 0. The label's object count here lost the GPU
        -- device ten seconds into the match, as 17 filters did (Death
        -- Island, 2026-10-08).
        w.put(0, 7)
    end
    return w.finish(), #filters - own, dropped
end

--- "RED: DEFAULT, BLUE: SCORPIONS" (the log line).
function VehicleSets.describe(choices)
    local parts = {}
    for _, team in ipairs({ "red", "blue" }) do
        local c = choices[team]
        local text = VehicleSets.SETS[(c.set or 0) + 1] or tostring(c.set)
        if c.set == VehicleSets.CUSTOM then
            local counts = {}
            for _, t in ipairs(VehicleSets.TYPES) do
                if (c.counts[t] or 0) > 0 then counts[#counts + 1] = c.counts[t] .. " " .. t end
            end
            text = text .. " (" .. (#counts > 0 and table.concat(counts, ", ") or "nothing") .. ")"
        end
        parts[#parts + 1] = team:upper() .. ": " .. text
    end
    return table.concat(parts, ", ")
end

return VehicleSets

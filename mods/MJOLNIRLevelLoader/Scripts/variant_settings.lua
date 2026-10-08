-- The host's game settings, patched into a Megalo game variant (.mglo)
-- before it is staged (docs/host_game_settings.md).
--
-- Settings travel as one line, `key=value;key=value`, the same on the host
-- and every fireteam client, so each machine's simulation loads the same
-- variant. Every key is a fixed-width field of the variant's base options,
-- the player traits, or the score to win; the field layout follows
-- crates/blam-megalo (`write_base`, `TRAITS`), and tools/tests checks the
-- result against files the Rust writer made with the same settings.
--
-- Plain arithmetic, no bitwise operators: the release lint reads mods as
-- LuaJIT + 5.2.

local VariantSettings = {}

-- Reach's player traits in stream order: name, width
-- (blam_megalo::variant::TRAITS). The movement group's optional jump height
-- sits before "camo".
local TRAITS = {
    { "damage_resistance", 4 }, { "health", 3 }, { "health_regen", 4 }, { "shields", 3 },
    { "shield_regen", 4 }, { "overshield_regen", 4 }, { "headshot_immunity", 2 }, { "vampirism", 3 },
    { "assassination_immunity", 2 }, { "cannot_die", 2 },
    { "damage", 4 }, { "melee_damage", 4 }, { "primary_weapon", 8 }, { "secondary_weapon", 8 },
    { "grenades", 4 }, { "infinite_ammo", 2 }, { "grenade_regen", 2 }, { "weapon_pickup", 2 },
    { "ability_usage", 2 }, { "abilities_drop", 2 }, { "infinite_ability", 2 }, { "ability", 8 },
    { "speed", 5 }, { "gravity", 4 }, { "vehicle_use", 4 }, { "double_jump", 2 },
    { "camo", 3 }, { "waypoint", 2 }, { "name_visible", 2 }, { "aura", 3 }, { "forced_color", 4 },
    { "radar", 3 }, { "radar_range", 3 }, { "directional_damage", 2 },
}
local JUMP_HEIGHT_BEFORE = "camo"

local function reader(bytes)
    local r = { at = 0, bits = #bytes * 8 }

    function r.read(n)
        if r.at + n > r.bits then error("truncated") end
        local v = 0
        for _ = 1, n do
            local byte = bytes:byte(math.floor(r.at / 8) + 1)
            v = v * 2 + math.floor(byte / 2 ^ (7 - r.at % 8)) % 2
            r.at = r.at + 1
        end
        return v
    end

    function r.skip(...)
        for _, n in ipairs({ ... }) do
            if r.at + n > r.bits then error("truncated") end
            r.at = r.at + n
        end
    end

    function r.bool() return r.read(1) == 1 end
    return r
end

--- Where each field sits: name -> { at = bit offset, bits = width }.
local function traits(r, fields, prefix)
    for _, t in ipairs(TRAITS) do
        if t[1] == JUMP_HEIGHT_BEFORE and r.bool() then r.skip(9) end
        if fields then fields[prefix .. t[1]] = { at = r.at, bits = t[2] } end
        r.skip(t[2])
    end
end

local function strings(r, cw, ow, sw)
    local count = r.read(cw)
    for _ = 1, count do
        for _ = 1, 12 do
            if r.bool() then r.skip(ow) end
        end
    end
    if count == 0 then return end
    local size = r.read(sw)
    if r.bool() then error("a compressed string table") end
    r.skip(size * 8)
end

local function contentHeader(r)
    local kind = r.read(4) - 1
    r.skip(32, 64, 64, 64, 64, 3)
    local mode = r.read(3)
    r.skip(3, 32, 8)
    for _ = 1, 2 do
        r.skip(64, 64)
        for _ = 1, 16 do
            if r.read(8) == 0 then break end
        end
        r.skip(1)
    end
    for _ = 1, 2 do
        for _ = 1, 128 do
            if r.read(16) == 0 then break end
        end
    end
    if kind == 3 or kind == 4 then r.skip(32) elseif kind == 6 then r.skip(8) end
    if mode == 1 then r.skip(8, 2, 2, 8, 32) elseif mode == 2 then r.skip(2, 32) end
end

--- Record a field of `bits` at the reader's position and step over it.
local function field(r, fields, name, bits)
    fields[name] = { at = r.at, bits = bits }
    r.skip(bits)
end

--- Every patchable field of a variant, or nil and why.
function VariantSettings.layout(bytes)
    if type(bytes) ~= "string" or #bytes < 8 then return nil, "not a variant" end
    local fields = {}
    local ok, err = pcall(function()
        local r = reader(bytes)
        local version = r.read(32)
        if version ~= 0x6a and version ~= 0x6b then error("encoding version " .. version) end
        r.skip(32)
        contentHeader(r)
        r.skip(1)
        -- misc: teams and 3 flags, time limit, rounds, u4, sudden death, grace
        r.skip(1, 1, 1, 1)
        field(r, fields, "time_limit", 8)
        r.skip(5, 4)
        field(r, fields, "sudden_death_raw", 7)
        r.skip(5)
        -- respawn
        r.skip(1, 1, 1, 1)
        field(r, fields, "lives", 6)
        field(r, fields, "team_lives", 7)
        field(r, fields, "respawn_seconds", 8)
        field(r, fields, "suicide_seconds", 8)
        field(r, fields, "betrayal_seconds", 8)
        field(r, fields, "respawn_growth", 4)
        r.skip(4)
        field(r, fields, "respawn_traits_seconds", 6)
        traits(r, fields, "respawn_trait.")
        r.skip(1)
        -- social
        field(r, fields, "team_changing", 2)
        field(r, fields, "social_flags", 5)
        -- map
        field(r, fields, "map_flags", 6)
        traits(r, fields, "trait.")
        r.skip(8, 8)
        for _ = 1, 3 do traits(r) end
        r.skip(7, 7, 7, 3, 3, 2)
        for _ = 1, 8 do
            r.skip(4)
            strings(r, 1, 5, 6)
            r.skip(4, 1, 32, 32, 32, 5)
        end
        r.skip(2)
        for _ = 1, 30 do
            r.skip(1)
            if not r.bool() then r.skip(7) end
            r.skip(8, 8, 8, 4)
        end
        if r.read(5) ~= 0 or r.read(5) ~= 0 then error("player traits or user options") end
        strings(r, 7, 15, 15)
        r.skip(7)
        strings(r, 1, 9, 9)
        strings(r, 1, 12, 12)
        strings(r, 1, 9, 9)
        r.skip(5, 5)
        for _ = 1, r.read(6) do r.skip(16) end
        r.skip(1)
        for _ = 1, 15 do r.skip(32) end
        r.skip(1)
        field(r, fields, "score", 16)
    end)
    if not ok then return nil, tostring(err) end
    return fields
end

--- `text` ("key=value;key=value") as a table of whole numbers; unknown
--- shapes are dropped.
function VariantSettings.parse(text)
    local settings = {}
    for key, value in tostring(text or ""):gmatch("([%w_%.]+)=(%d+)") do
        settings[key] = tonumber(value)
    end
    return settings
end

--- The settings for game type `mode`: the host's line carries a score to
--- win per game type (`score.slayer=25;score.ctf=3`), so it stays right
--- whichever game type the next match turns out to be (a post-game vote can
--- change it). That game type's becomes `score`; the others are dropped.
function VariantSettings.forMode(settings, mode)
    local out = {}
    for key, value in pairs(settings or {}) do
        -- `vehicles.*` are the vehicle sets (vehicle_sets.lua), not fields.
        if key:sub(1, 6) ~= "score." and key:sub(1, 9) ~= "vehicles." then out[key] = value end
    end
    out.score = (settings or {})["score." .. tostring(mode)] or (settings or {}).score
    return out
end

--- `settings` as one line, keys sorted so equal settings give equal text.
function VariantSettings.format(settings)
    local keys = {}
    for k in pairs(settings or {}) do keys[#keys + 1] = k end
    table.sort(keys)
    local parts = {}
    for _, k in ipairs(keys) do parts[#parts + 1] = k .. "=" .. tostring(settings[k]) end
    return table.concat(parts, ";")
end

--- `bytes` with the bits from `at` (MSB first) replaced by `value`.
local function putBits(bytes, at, bits, value)
    local out = { bytes:byte(1, -1) }
    for i = bits - 1, 0, -1 do
        local bit = math.floor(value / 2 ^ i) % 2
        local index = math.floor(at / 8) + 1
        local weight = 2 ^ (7 - at % 8)
        local current = math.floor(out[index] / weight) % 2
        out[index] = out[index] + (bit - current) * weight
        at = at + 1
    end
    -- string.char in chunks: very long argument lists overflow the stack.
    local parts = {}
    for i = 1, #out, 4096 do
        parts[#parts + 1] = string.char(table.unpack(out, i, math.min(i + 4095, #out)))
    end
    return table.concat(parts)
end

--- The variant with every setting written in, or nil and why. A setting
--- that is not a field, or too wide for it, is refused: the variant is
--- either patched as asked or left alone.
function VariantSettings.apply(bytes, settings)
    local fields, err = VariantSettings.layout(bytes)
    if not fields then return nil, err end
    for key, value in pairs(settings or {}) do
        local f = fields[key]
        if not f then return nil, "no setting " .. tostring(key) end
        if type(value) ~= "number" or value < 0 or value >= 2 ^ f.bits or value % 1 ~= 0 then
            return nil, key .. "=" .. tostring(value) .. " does not fit " .. f.bits .. " bits"
        end
    end
    for key, value in pairs(settings or {}) do
        local f = fields[key]
        bytes = putBits(bytes, f.at, f.bits, value)
    end
    return bytes
end

--- One field's value, or nil (for the HUD and tests).
function VariantSettings.get(bytes, key)
    local fields = VariantSettings.layout(bytes)
    local f = fields and fields[key]
    if not f then return nil end
    local r = reader(bytes)
    r.at = f.at
    return r.read(f.bits)
end

return VariantSettings

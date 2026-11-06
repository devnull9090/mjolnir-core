-- Run from the repository root with Lua 5.4, or Python + lupa:
-- python -c "from lupa import LuaRuntime; LuaRuntime().execute(open('tools/tests/test_variant_settings.lua').read())"
--
-- MJOLNIRLevelLoader's variant_settings.lua against the Rust writer: the
-- fixtures in tools/tests/fixtures/settings are written by blam-megalo's
-- settings_fixtures_are_current test, a default variant and the same variant
-- written with settings.txt; patching the first must give the second.
local VariantSettings = dofile("mods/MJOLNIRLevelLoader/Scripts/variant_settings.lua")
-- MJOLNIRHud's own reader of the staged variant (score strip, round clock).
local HudVariant = dofile("mods/MJOLNIRHud/Scripts/variant.lua")

local function read(path)
    local f = assert(io.open(path, "rb"), path)
    local data = f:read("a")
    f:close()
    return data
end

local function eq(actual, expected, label)
    assert(actual == expected, (label or "value") .. ": expected " .. tostring(expected) .. ", got " .. tostring(actual))
end

local dir = "tools/tests/fixtures/settings/"
local text = read(dir .. "settings.txt")
local settings = VariantSettings.parse(text)
eq(VariantSettings.format(settings), text, "format(parse(text))")

for _, mode in ipairs({ "slayer", "ctf", "team_koth", "juggernaut", "stalker", "reverse_tag", "race" }) do
    local default = read(dir .. mode .. "_default.mglo")
    local expected = read(dir .. mode .. "_settings.mglo")
    local patched, err = VariantSettings.apply(default, settings)
    assert(patched, mode .. ": " .. tostring(err))
    eq(#patched, #expected, mode .. " length")
    for i = 1, #expected do
        if patched:byte(i) ~= expected:byte(i) then
            error(string.format("%s: byte %d is %02x, the writer's is %02x", mode, i - 1, patched:byte(i), expected:byte(i)))
        end
    end
    eq(VariantSettings.get(patched, "score"), 15, mode .. " score")
    eq(VariantSettings.get(patched, "time_limit"), 10, mode .. " time limit")
    eq(VariantSettings.get(default, "respawn_seconds"), 5, mode .. " default respawn")
    eq(HudVariant.scoreToWin(patched), 15, mode .. " score as the HUD reads it")
    eq(HudVariant.timeLimit(patched), 10, mode .. " time limit as the HUD reads it")
    eq(HudVariant.timeLimit(default), 0, mode .. " no time limit as the HUD reads it")
    -- Nothing to change: the bytes come back as they were.
    eq(VariantSettings.apply(default, {}), default, mode .. " no settings")
end

local default = read(dir .. "slayer_default.mglo")
local none, why = VariantSettings.apply(default, { no_such_field = 1 })
assert(none == nil and why:find("no setting"), "an unknown setting is refused")
none, why = VariantSettings.apply(default, { ["trait.shields"] = 8 })
assert(none == nil and why:find("does not fit"), "a value too wide is refused")
none = VariantSettings.apply("not a variant", { time_limit = 1 })
assert(none == nil, "a file that is not a variant is refused")

-- Script traits: both readers step over the section, whatever it holds. The
-- section goes into a real variant by hand, at the bit the reader finds it.
local source = read("mods/MJOLNIRLevelLoader/Scripts/variant_settings.lua")
local probed, hits = source:gsub("local sets = r%.read%(5%)", "SECTION_AT = r.at; %0")
eq(hits, 1, "the section's count read")
assert(load(probed))().layout(default)
local sectionAt = assert(SECTION_AT, "the reader reached the section")

local function toBits(bytes)
    local bits = {}
    for i = 1, #bytes do
        for b = 7, 0, -1 do bits[#bits + 1] = math.floor(bytes:byte(i) / 2 ^ b) % 2 end
    end
    return bits
end

local function toBytes(bits)
    local out = {}
    for i = 1, #bits, 8 do
        local v = 0
        for j = i, i + 7 do v = v * 2 + (bits[j] or 0) end
        out[#out + 1] = string.char(v)
    end
    return table.concat(out)
end

local function put(bits, value, width)
    for b = width - 1, 0, -1 do bits[#bits + 1] = math.floor(value / 2 ^ b) % 2 end
end

--- One set's bits: 94 bits of traits, the jump height's flag and optional u9,
--- then 22 more. Every trait bit is set, so a misread cannot pass as zeros.
local function traitSet(bits, name, description, jump)
    put(bits, name, 7)
    put(bits, description, 7)
    for _ = 1, 94 do bits[#bits + 1] = 1 end
    put(bits, jump and 1 or 0, 1)
    if jump then put(bits, 150, 9) end
    for _ = 1, 22 do bits[#bits + 1] = 1 end
end

--- `bytes` with a section of `count` sets in place of the empty one.
local function withSection(bytes, count, userOptions)
    local bits = toBits(bytes)
    local section = {}
    put(section, count, 5)
    for i = 1, count do traitSet(section, 2 * i, 2 * i + 1, i % 2 == 1) end
    put(section, userOptions or 0, 5)
    local out = {}
    for i = 1, sectionAt do out[i] = bits[i] end
    for _, bit in ipairs(section) do out[#out + 1] = bit end
    for i = sectionAt + 11, #bits do out[#out + 1] = bits[i] end
    return toBytes(out), #section - 10
end

local traited, grew = withSection(default, 2)
eq(VariantSettings.get(traited, "score"), VariantSettings.get(default, "score"), "the score past two trait sets")
eq(HudVariant.scoreToWin(traited), HudVariant.scoreToWin(default), "as the HUD reads it")
local full = withSection(default, 16)
eq(VariantSettings.get(full, "score"), VariantSettings.get(default, "score"), "the store's 16 sets")
eq(HudVariant.scoreToWin(full), HudVariant.scoreToWin(default), "as the HUD reads them")

-- The host's settings land where the writer's did: take the section out of a
-- patched variant and it is the writer's file.
local patchedTraits = assert(VariantSettings.apply(traited, settings))
eq(VariantSettings.get(patchedTraits, "score"), 15, "the host's score past the section")
eq(HudVariant.scoreToWin(patchedTraits), 15, "as the HUD reads it")
eq(HudVariant.timeLimit(patchedTraits), 10, "the host's time limit")
local bits, plain = toBits(patchedTraits), {}
for i = 1, sectionAt do plain[i] = bits[i] end
for _ = 1, 5 do plain[#plain + 1] = 0 end
for i = sectionAt + 6 + grew, #bits do plain[#plain + 1] = bits[i] end
eq(toBytes(plain):sub(1, #default), read(dir .. "slayer_settings.mglo"), "the same variant, section aside")

-- User options stay refused, and so does a count past the store.
none, why = VariantSettings.apply(withSection(default, 1, 1), {})
assert(none == nil and why:find("user options"), "user options are refused")
eq(HudVariant.scoreToWin(withSection(default, 1, 1)), nil, "the HUD keeps its default")
none, why = VariantSettings.apply(withSection(default, 17), {})
assert(none == nil and why:find("too many"), "more trait sets than the store holds are refused")
eq(HudVariant.scoreToWin(withSection(default, 17)), nil, "the HUD keeps its default")

print("Variant settings: patched Slayer, CTF, Team King, Juggernaut, Stalker, Reverse Tag and Race match the Rust writer; bad settings are refused; script traits are stepped over")

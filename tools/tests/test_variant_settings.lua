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

for _, mode in ipairs({ "slayer", "ctf" }) do
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

print("Variant settings: patched Slayer and CTF match the Rust writer; bad settings are refused")

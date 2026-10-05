-- Run from the repository root with Lua 5.4, or Python + lupa:
-- python -c "from lupa import LuaRuntime; LuaRuntime().execute(open('tools/tests/test_game_settings.lua').read())"
--
-- MJOLNIRLobby's settings.lua (the host's GAME SETTINGS) and the line it
-- hands MJOLNIRLevelLoader: every line it can make must patch cleanly into
-- the variants the Rust writer makes.
local Settings = dofile("mods/MJOLNIRLobby/Scripts/settings.lua")
local VariantSettings = dofile("mods/MJOLNIRLevelLoader/Scripts/variant_settings.lua")

local function eq(actual, expected, label)
    assert(actual == expected, (label or "value") .. ": expected " .. tostring(expected) .. ", got " .. tostring(actual))
end

local function read(path)
    local f = assert(io.open(path, "rb"), path)
    local data = f:read("a")
    f:close()
    return data
end

-- Defaults: the rules MJOLNIR's variants have always had.
eq(Settings.variantLine(),
    "map_flags=31;respawn_seconds=5;score.ctf=3;score.slayer=25;score.team_slayer=50;suicide_seconds=5;"
        .. "time_limit=0;trait.camo=0;trait.shields=0",
    "defaults")
-- The loader keeps the score of the game type it stages.
local forCtf = VariantSettings.forMode(VariantSettings.parse(Settings.variantLine()), "ctf")
eq(forCtf.score, 3, "CTF's score for a CTF variant")
eq(forCtf["score.slayer"], nil, "other game types' scores dropped")
eq(#Settings.changes("slayer"), 0, "no changes at the defaults")
eq(Settings.option("score", "oddball"), nil, "no score option for a game type without one")

-- Stepping wraps both ways.
local score = Settings.option("score", "slayer")
Settings.step(score, 1)
eq(Settings.value(score), 50, "25 -> 50")
Settings.step(score, 1)
eq(Settings.value(score), 5, "50 wraps to 5")
Settings.step(score, -1)
eq(Settings.value(score), 50, "5 back to 50")
-- The score is per game type; CTF keeps its own.
eq(Settings.value(Settings.option("score", "ctf")), 3, "CTF's score untouched")

for _, id in ipairs({ "time_limit", "shields", "invisible", "grenades", "powerups" }) do
    Settings.step(Settings.option(id), 1)
end
Settings.step(Settings.option("respawn"), -1)
local line = Settings.variantLine()
eq(line, "map_flags=22;respawn_seconds=0;score.ctf=3;score.slayer=50;score.team_slayer=50;suicide_seconds=5;"
    .. "time_limit=5;trait.camo=4;trait.shields=1", "changed line")
eq(table.concat(Settings.changes("slayer"), "|"),
    "KILLS TO WIN: 50|TIME LIMIT: 5 MINUTES|RESPAWN TIME: INSTANT|SHIELDS: OFF|INVISIBLE PLAYERS: YES|"
        .. "GRENADES ON MAP: NO|POWERUPS ON MAP: NO", "the lobby card's rules")

-- A client reads the same rules back from the line alone.
local saved = Settings.save()
eq(table.concat(Settings.describe(line, "slayer"), "|"), table.concat(Settings.changes("slayer"), "|"), "describe(line)")
Settings.reset()
eq(#Settings.changes("slayer"), 0, "reset")
Settings.load(saved)
eq(Settings.variantLine(), line, "save and load")

-- Every line patches into the real variants, at every choice of every option.
local variants = {
    slayer = read("tools/tests/fixtures/settings/slayer_default.mglo"),
    ctf = read("tools/tests/fixtures/settings/ctf_default.mglo"),
}
for mode, bytes in pairs(variants) do
    for _, o in ipairs(Settings.OPTIONS) do
        local opt = Settings.option(o.id, mode)
        for _ = 1, #opt.choices do
            Settings.step(opt, 1)
            local settings = VariantSettings.forMode(VariantSettings.parse(Settings.variantLine()), mode)
            local patched, err = VariantSettings.apply(bytes, settings)
            assert(patched, mode .. " " .. opt.label .. " " .. Settings.text(opt) .. ": " .. tostring(err))
        end
    end
end

print("Game settings: defaults, stepping, per-mode scores, save/load, describe and every choice patch cleanly")

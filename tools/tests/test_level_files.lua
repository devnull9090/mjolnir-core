-- Plain checks for MJOLNIRLevelLoader's level_files.lua (a level file
-- decoded once per map); run with stock Lua from the repository root.
package.path = "mods/MJOLNIRLevelLoader/Scripts/?.lua;" .. package.path
local LevelFiles = require("level_files")

local decodes = 0
local function decode(raw)
    decodes = decodes + 1
    if raw == "bad" then error("parse error at 1") end
    return { text = raw, lights = 1 }
end

-- The travel decodes and keeps it; the load takes the same table.
local files = LevelFiles.new(decode)
local ok, peek = files.decode("TMB/level.json", "{tmb}", false)
assert(ok and peek.text == "{tmb}" and decodes == 1)
local ok2, taken = files.decode("TMB/level.json", "{tmb}", true)
assert(ok2 and taken == peek and decodes == 1, "the load reuses the travel's decode")

-- The load changes what it took (landscapeLight): the next reader must not
-- get that table again, scaled twice.
taken.lights = taken.lights * 2
local _, again = files.decode("TMB/level.json", "{tmb}", true)
assert(again ~= taken and again.lights == 1 and decodes == 2, "taken once: the next load decodes afresh")

-- A file rewritten between the travel and the load (the launcher puts the
-- hub's back) is decoded again.
files.decode("TMB/level.json", "{old}", false)
local _, fresh = files.decode("TMB/level.json", "{new}", true)
assert(fresh.text == "{new}" and decodes == 4)

-- Another map's file is not this one.
files.decode("BGL/level.json", "{same}", false)
local _, other = files.decode("TMB/level.json", "{same}", true)
assert(decodes == 6 and other.text == "{same}", "decoded for its own path")

-- A file that does not parse fails as pcall would, and is not kept.
local okBad, err = files.decode("X/level.json", "bad", false)
assert(not okBad and tostring(err):find("parse error"))
local okBad2 = files.decode("X/level.json", "bad", true)
assert(not okBad2 and decodes == 8, "a failed decode is not kept")

-- Peeks (two travels' hooks for one map) share the one decode.
local base = decodes
files.decode("ZAN/level.json", "{zan}", false)
files.decode("ZAN/level.json", "{zan}", false)
files.decode("ZAN/level.json", "{zan}", true)
assert(decodes == base + 1, "one decode for the map")

print("test_level_files: ok")

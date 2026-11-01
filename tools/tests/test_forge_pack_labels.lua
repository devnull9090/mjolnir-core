-- Run from the repository root with Lua 5.4, or Python + lupa:
-- python -c "from lupa import LuaRuntime; LuaRuntime().execute(open('tools/tests/test_forge_pack_labels.lua', encoding='utf-8').read())"
local Hud = dofile("mods/MJOLNIRForge/Scripts/hud.lua")
local Json = dofile("mods/MJOLNIRLevelLoader/Scripts/json.lua")
assert(loadfile("mods/MJOLNIRForge/Scripts/main.lua"))
local checks = 0
local function eq(actual, expected)
    checks = checks + 1
    assert(actual == expected, "expected " .. tostring(expected) .. ", got " .. tostring(actual))
end

local inventory = Json.decode([[
{"schema_version":1,"packs":[
  {"slug":"foundry","name":"Foundry","forge_pack":{"schema_version":1,"id":"foundry","blocks":[
    {"id":"block","name":"Alloy Block 2 m","category":"building_blocks","tag":"objects\\mjolnir\\forge\\foundry\\block"},
    {"id":"magnum","name":"Heavy Support","category":"supports","tag":"objects\\mjolnir\\forge\\foundry\\magnum"}
  ]}},
  {"slug":"aerie","name":"Aerie","forge_pack":{"schema_version":1,"id":"aerie","blocks":[
    {"id":"block","name":"Stone Block 2 m","category":"blocks","tag":"objects\\mjolnir\\forge\\aerie\\block"}
  ]}}
]}]])
Hud.setPackInventory(inventory)
local foundry = "objects\\mjolnir\\forge\\foundry\\block"
local aerie = "objects\\mjolnir\\forge\\aerie\\block"
eq(Hud.prettyName("block", foundry), "Alloy Block 2 m")
eq(Hud.prettyName("block", aerie), "Stone Block 2 m")
eq(Hud.prettyName(foundry), "Alloy Block 2 m")
eq(Hud.prettyName("block"), "Block") -- never guess a pack from a leaf ID
eq(Hud.prettyName("magnum"), "Magnum") -- ordinary shipped weapon stays unchanged
eq(Hud.prettyName("magnum", "objects\\mjolnir\\forge\\foundry\\magnum"), "Heavy Support")
eq(Hud.packCategory(foundry), "FOUNDRY · BUILDING BLOCKS")
eq(Hud.packCategory(aerie), "AERIE · BLOCKS")
eq(Hud.packCategory("block"), nil)
eq(Hud.prettyName(nil), "Object")

local palette = Hud.parsePalette("0\t0\tweap\tmagnum\t1\n"
    .. "0\t1\tweap\tassault_rifle_legacy\t0\t2\t10\t5\n"
    .. "3\t0\tbloc\tblock\t1\t1\t25\t10\t" .. foundry .. "\n"
    .. "3\t1\tbloc\tblock\t1\t0\t25\t10\t" .. aerie .. "\n")
eq(#palette, 4)
eq(palette[1].maximum, 0)
eq(palette[1].full_tag, nil)
eq(Hud.paletteName(palette[1]), "Magnum")
eq(Hud.paletteCategory(palette[1]), "WEAPONS")
eq(palette[2].maximum, 10)
eq(palette[2].placed, 2)
eq(palette[2].price, 5)
eq(palette[2].placeable, false)
eq(palette[3].full_tag, foundry)
eq(palette[3].palette, 3)
eq(palette[3].entry, 0)
eq(Hud.paletteName(palette[3]), "Alloy Block 2 m")
eq(Hud.paletteName(palette[4]), "Stone Block 2 m")
eq(Hud.paletteCategory(palette[3]), "FOUNDRY · BUILDING BLOCKS")
eq(Hud.paletteCategory(palette[4]), "AERIE · BLOCKS")

-- Removal or a broken inventory clears stale labels. A bad namespace or
-- duplicate identity cannot silently rename another pack's model.
Hud.setPackInventory(nil)
eq(Hud.prettyName("block", foundry), "Block")
Hud.setPackInventory({ schema_version = 2, packs = inventory.packs })
eq(Hud.packBlock(foundry), nil)
inventory.packs[2].forge_pack.blocks[1].tag = foundry
Hud.setPackInventory(inventory)
eq(Hud.prettyName("block", foundry), "Alloy Block 2 m")
eq(Hud.prettyName("block", aerie), "Block")
inventory.packs[1].forge_pack.blocks[1].name = "  Alloy\nBlock\t2 m  "
Hud.setPackInventory(inventory)
eq(Hud.prettyName("block", foundry), "Alloy Block 2 m")
table.insert(inventory.packs, inventory.packs[1])
Hud.setPackInventory(inventory)
eq(Hud.packBlock(foundry), nil)
eq(Hud.prettyName("block", foundry), "Block")
local refused = "load failed: pack palette changed; use the map version this layout was saved on"
eq(Hud.notice(refused, "Object"), string.upper(refused))
local failedSave = "save failed: cannot commit layout; previous save preserved"
eq(Hud.notice(failedSave, "Object"), string.upper(failedSave))
local failedRevert = "revert failed: cannot move saved layout to history"
eq(Hud.notice(failedRevert, "Object"), string.upper(failedRevert))
eq(Hud.layoutWarning("BGL: own layout, saved one refused: needs foundry 1.0.0; restart through the launcher"),
    "SAVED FORGE LAYOUT NOT LOADED\nneeds foundry 1.0.0; restart through the launcher\nPlaying the map's original layout.")
eq(Hud.layoutWarning("BGL: saved layout, 4 objects"), nil)
eq(Hud.layoutWarning("BGL: the map's own layout"), nil)
print("Forge pack labels: " .. checks .. " checks passed")

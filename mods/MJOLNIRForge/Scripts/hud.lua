-- MJOLNIR Forge: the HUD of a FORGE game, WBP_MJOLNIRForge (docs/forge.md).
--
-- The widget is layout only (unreal/MJOLNIRMaterials/Scripts/build_mjolnir_ui.py,
-- build_forge_hud), cooked into its own container, pakchunk980-MJOLNIRFORGEUI.
-- This module fills it from the editor's state (native\forge_state.txt):
--
--   ForgeBadge   FORGE, the mode (MONITOR / SPARTAN) and the map
--   Reticle      the Monitor's cursor, tinted: idle, on an object, holding one
--   TargetCard   what the cursor is on, or what you hold: its category, a
--                readable name, the game's own silhouette for a weapon, what
--                the keys do to it, and while holding how far out it is
--   ControlBar   every key, dimmed when it does nothing right now
--   PaletteSize  in the Monitor, the palette: the category between its keys,
--                the object Insert places with its picture, and a window of
--                the category around it (dimmed: the map cannot place one)
--   Toast        what the last key did, then fades
--
-- The palette panel came with CE runtime 1.15.0. With an older HUD a toast
-- names the selected object instead.
--
-- Everything here runs on the game thread. Hud.render returns false when the
-- widget cannot be made (no container, no player controller yet), and
-- main.lua then shows its text panel instead.

local Hud = {}

local CLASS = "/Game/MJOLNIR/ForgeUI/WBP_MJOLNIRForge.WBP_MJOLNIRForge_C"
local ICON_MATERIAL = "/Game/UI/Hud/GrenadeCradle/Materials/MI_HUDCradleIcon_FragGrenade"
local WEAPON_DIR = "/Game/UI/Hud/WeaponCradle/Textures/"
local GRENADE_DIR = "/Game/UI/Hud/GrenadeCradle/Textures/"

local COLLAPSED, HIT_TEST_INVISIBLE = 1, 3
local TOAST_SECONDS = 2.2
local FADE_STEPS = 5
local DISTANCE_MIN, DISTANCE_MAX = 1, 60
local DISTANCE_TRACK = 280
local CARD_HINTS = 3
local CONTROLS = 6
local PALETTE_ROWS = 7
local ICON_W, ICON_H = 120, 40 -- the icon boxes' size in the widget, the most a picture takes
local CENTRE = 2 -- EHorizontalAlignment / EVerticalAlignment

local ACCENT = { R = 0.46, G = 0.79, B = 0.94, A = 1 }
local WHITE = { R = 0.88, G = 0.95, B = 1, A = 1 }
local GOLD = { R = 1, G = 0.80, B = 0.35, A = 1 }
local GREEN = { R = 0.45, G = 1, B = 0.62, A = 1 }
local RETICLE_IDLE = { R = 0.46, G = 0.79, B = 0.94, A = 0.85 }
local GREY = { R = 0.46, G = 0.61, B = 0.70, A = 1 }
local ROW_SELECTED = { R = 0.46, G = 0.79, B = 0.94, A = 0.22 }
local ROW_PLAIN = { R = 0, G = 0, B = 0, A = 0 }

-- Tag groups by four-CC.
local CATEGORIES = {
    weap = "WEAPON", vehi = "VEHICLE", scen = "SCENERY", eqip = "EQUIPMENT", bipd = "CHARACTER",
    mach = "MACHINE", ctrl = "CONTROL", bloc = "CRATE", proj = "PROJECTILE", ssce = "SOUND",
    crea = "CREATURE", efsc = "EFFECT", gint = "GIANT", term = "TERMINAL",
}

-- A palette category by its tag group.
local SHELVES = {
    weap = "WEAPONS", vehi = "VEHICLES", scen = "SCENERY", eqip = "EQUIPMENT", bipd = "CHARACTERS",
    mach = "MACHINES", ctrl = "CONTROLS", bloc = "CRATES",
}

-- Tag names a plain title-casing would leave odd.
local NAMES = {
    player_spawn = "Spawn Point", health_pack_spot = "Health Pack", flag_stand = "Flag Stand",
    teleporter_sender = "Teleporter Sender", teleporter_receiver = "Teleporter Receiver",
    teleporter_2way = "Two-Way Teleporter", magnum = "Magnum", smg = "SMG",
    rocket_launcher = "Rocket Launcher", fuel_rod_cannon = "Fuel Rod Gun", active_camouflage = "Active Camo",
    over_shield = "Overshield", assault_rifle_legacy = "Assault Rifle", flak_cannon = "Fuel Rod Gun",
    beam_rifle = "Beam Rifle", assault_rifle_ammo = "Assault Rifle Ammo", pistol_ammo = "Magnum Ammo",
    sniper_rifle_ammo = "Sniper Ammo", rocket_launcher_ammo = "Rocket Ammo",
}

-- The game's silhouettes by tag name (the kill feed's catalogue, keyed by tag).
local ICONS = {
    assault_rifle = WEAPON_DIR .. "T_UI_AssaultRifle_WeaponIcon",
    assault_rifle_legacy = WEAPON_DIR .. "T_UI_AssaultRifle_WeaponIcon",
    battle_rifle = WEAPON_DIR .. "T_UI_BattleRifle_WeaponIcon",
    sniper_rifle = WEAPON_DIR .. "T_UI_SniperRifle_WeaponIcon",
    shotgun = WEAPON_DIR .. "T_UI_Shotgun_WeaponIcon",
    magnum = WEAPON_DIR .. "T_UI_Pistol_WeaponIcon",
    pistol = WEAPON_DIR .. "T_UI_Pistol_WeaponIcon",
    smg = WEAPON_DIR .. "T_UI_SMG_WeaponIcon",
    plasma_rifle = WEAPON_DIR .. "T_UI_PlasmaRifleIcon",
    plasma_pistol = WEAPON_DIR .. "T_UI_PlasmaPistol_WeaponIcon",
    needler = WEAPON_DIR .. "T_UI_Needler_WeaponIcon",
    rocket_launcher = WEAPON_DIR .. "T_UI_SPNKR_WeaponIcon",
    flak_cannon = WEAPON_DIR .. "T_UI_FuelRod_WeaponIcon",
    fuel_rod_cannon = WEAPON_DIR .. "T_UI_FuelRod_WeaponIcon",
    energy_sword = WEAPON_DIR .. "T_UI_EnergySword_WeaponIcon",
    frag_grenade = GRENADE_DIR .. "T_UI_FragGrenade_WeaponIcon",
    plasma_grenade = GRENADE_DIR .. "T_UI_PlasmaGrenade_WeaponIcon",
    ghost = WEAPON_DIR .. "T_UI_Ghost_WeaponIcon",
    banshee = WEAPON_DIR .. "T_UI_BansheeDualCannon_WeaponIcon",
    scorpion = WEAPON_DIR .. "T_IU_ScorpionMainGun_Icon",
    wraith = WEAPON_DIR .. "T_UI_WraithMainGun_Icon",
    warthog = WEAPON_DIR .. "T_UI_WarthogTurret_Icon",
}

local ctx = nil
local W = nil
local nextTry = 0
local missingClass = false
local loaded = {}
local toast = { id = nil, generation = 0 }
local lastTarget = nil
local lastChoice = nil
local packBlocks = {}

--------------------------------------------------------------------------------
-- Helpers
--------------------------------------------------------------------------------

local function valid(o)
    local ok, v = pcall(function() return o and o:IsValid() end)
    return ok and v == true
end

local function load(path)
    local full = path:find("%.") and path or (path .. "." .. path:match("([^/]+)$"))
    local hit = loaded[full]
    if hit ~= nil then
        if hit == false or valid(hit) then return hit or nil end
    end
    local ok, obj = pcall(function()
        local ksl = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
        return ksl:LoadAsset_Blocking(ksl:Conv_SoftObjPathToSoftObjRef(ksl:MakeSoftObjectPath(full)))
    end)
    loaded[full] = (ok and valid(obj)) and obj or false
    return loaded[full] or nil
end

local function setText(block, text)
    pcall(function() block:SetText(FText(text)) end)
end

local function setTextColor(block, c)
    pcall(function() block:SetColorAndOpacity({ SpecifiedColor = c, ColorUseRule = 0 }) end)
end

local function setVisible(w, on)
    pcall(function() w:SetVisibility(on and HIT_TEST_INVISIBLE or COLLAPSED) end)
end

local function setOpacity(w, a)
    pcall(function() w:SetRenderOpacity(a) end)
end

local function face(block, family, typeface, spacing)
    local font = load("/Game/Fonts/Font_" .. family)
    if not font then return end
    pcall(function()
        local size = block.Font.Size
        block:SetFont({ FontObject = font, TypefaceFontName = FName(typeface), Size = size,
            LetterSpacing = spacing or 0, SkewAmount = 0, OutlineSettings = { OutlineSize = 0 } })
    end)
end

-- Inventory is data from the launcher's verified archive catalog. Look up
-- full tag paths only: separate packs commonly use the same leaf IDs.
function Hud.setPackInventory(inventory)
    local blocks = {}
    local function label(value, maxBytes)
        if type(value) ~= "string" or #value > maxBytes then return nil end
        local text = value:gsub("[%z\1-\31\127]", " "):match("^%s*(.-)%s*$")
        return text ~= "" and text or nil
    end
    if type(inventory) == "table" and inventory.schema_version == 1 and type(inventory.packs) == "table" then
        for _, pack in ipairs(inventory.packs) do
            local catalog = type(pack) == "table" and pack.forge_pack or nil
            local slug = type(pack) == "table" and pack.slug or nil
            local packName = type(pack) == "table" and label(pack.name, 480) or nil
            if type(slug) == "string" and #slug >= 2 and #slug <= 64 and slug:match("^[a-z0-9][a-z0-9%-]*$")
                and packName and type(catalog) == "table" and catalog.schema_version == 1 and catalog.id == slug
                and type(catalog.blocks) == "table" then
                for _, block in ipairs(catalog.blocks) do
                    if type(block) == "table" then
                        local id, name, category = block.id, label(block.name, 320), block.category
                        if type(id) == "string" and #id <= 64 and id:match("^[a-z0-9][a-z0-9_%-]*$")
                            and name and type(category) == "string" and #category <= 64
                            and category:match("^[a-z0-9][a-z0-9_%-]*$") then
                            local tag = "objects\\mjolnir\\forge\\" .. slug .. "\\" .. id
                            if block.tag == tag then
                                -- Even malformed local inventories cannot let the last
                                -- duplicate silently change an object's displayed identity.
                                if blocks[tag] ~= nil then blocks[tag] = false
                                else blocks[tag] = { name = name, pack = packName, category = category } end
                            end
                        end
                    end
                end
            end
        end
    end
    packBlocks = blocks
end

function Hud.packBlock(fullTag)
    return type(fullTag) == "string" and packBlocks[fullTag] or nil
end

--- "assault_rifle" -> "Assault Rifle"; pack models use their authored name.
function Hud.prettyName(tag, fullTag)
    local block = Hud.packBlock(fullTag or tag)
    if block then return block.name end
    if not tag or tag == "" then return "Object" end
    tag = tag:match("([^\\/]+)$") or tag
    if NAMES[tag] then return NAMES[tag] end
    return (tag:gsub("[_%-]", " "):gsub("(%a)([%w]*)", function(a, b) return string.upper(a) .. b end))
end

function Hud.paletteName(row)
    return Hud.prettyName(row.tag, row.full_tag)
end

function Hud.packCategory(fullTag)
    local block = Hud.packBlock(fullTag)
    if not block then return nil end
    return string.upper(block.pack) .. " · " .. string.upper(block.category:gsub("[_%-]", " "))
end

function Hud.paletteCategory(row)
    return Hud.packCategory(row.full_tag) or SHELVES[row.group] or Hud.category(row.group)
end

function Hud.layoutWarning(layout)
    if type(layout) ~= "string" then return nil end
    local why = layout:match("^[^:]+: own layout, saved one refused: (.+)$")
    if not why then return nil end
    return "SAVED FORGE LAYOUT NOT LOADED\n" .. why .. "\nPlaying the map's original layout."
end

-- Old DLLs publish five/eight fields; the new ninth field is the full path.
-- Keep palette/group boundaries exactly as the native navigation counts them.
function Hud.parsePalette(text)
    local rows = {}
    for line in (text or ""):gmatch("[^\r\n]+") do
        local p, e, group, tag, ok, rest = line:match("^(%d+)\t(%d+)\t([^\t]*)\t([^\t]*)\t(%d)(.*)$")
        if p then
            local placed, maximum, price, tail = rest:match("^\t(%-?%d+)\t(%-?%d+)\t(%-?%d+)(.*)$")
            local fullTag = tail and tail:match("^\t([^\t]+)") or nil
            rows[#rows + 1] = { palette = tonumber(p), entry = tonumber(e), group = group, tag = tag,
                placeable = ok == "1", placed = tonumber(placed) or 0, maximum = tonumber(maximum) or 0,
                price = tonumber(price) or 0, full_tag = fullTag }
        end
    end
    return rows
end

--- The target's Forge properties after its name: "  ·  RED  ·  ctf_flag_return".
function Hud.properties(s, keys)
    local parts = {}
    local physics = Hud.physicsName(s.physics)
    if physics then parts[#parts + 1] = physics end
    if s.team and s.team ~= "neutral" then parts[#parts + 1] = string.upper(s.team) end
    if s.label and s.label ~= "" then parts[#parts + 1] = s.label end
    if s.channel then
        local hint = keys and keys.channel and (" [" .. Hud.keyLabel(keys.channel) .. "]") or ""
        parts[#parts + 1] = "CHANNEL " .. string.upper(s.channel) .. hint
    end
    if #parts == 0 then return "" end
    return "  ·  " .. table.concat(parts, "  ·  ")
end

function Hud.category(group)
    return CATEGORIES[group or ""] or "OBJECT"
end

--- A UE4SS key name as the key cap shows it: PAGE_UP -> PG UP.
function Hud.keyLabel(name)
    local pretty = { PAGE_UP = "PG UP", PAGE_DOWN = "PG DN", DEL = "DEL", INS = "INS", SPACE = "SPACE",
        LEFT_ARROW = "←", RIGHT_ARROW = "→", UP_ARROW = "↑", DOWN_ARROW = "↓", OEM_COMMA = ",", OEM_PERIOD = "." }
    return pretty[name] or (tostring(name):gsub("_", " "))
end

-- Only present settings that the native editor actually reported. In
-- particular, an old/missing snapshot must not imply Normal or snapping off.
function Hud.physicsName(mode)
    return ({ normal = "NORMAL", fixed = "FIXED", phased = "PHASED" })[mode]
end

function Hud.gridName(value)
    local n = tonumber(value)
    if n == 0 then return "OFF" end
    if n == 0.25 or n == 0.5 or n == 1 or n == 2 or n == 4 then return string.format("%g m", n) end
    return nil
end

function Hud.rotationName(value)
    local n = tonumber(value)
    if n == 0 then return "OFF" end
    if n == 90 or n == 45 or n == 30 or n == 15 or n == 5 then return string.format("%d°", n) end
    return nil
end

-- Three short lines fit the existing 380 px palette panel. The same text
-- serves the fallback panel; no additional widget or class is needed.
function Hud.editSettings(s, keys)
    local lines = {}
    local grid, rotation = Hud.gridName(s.grid_m), Hud.rotationName(s.rotation_snap)
    if grid then lines[#lines + 1] = "[" .. Hud.keyLabel(keys.grid) .. "] GRID " .. grid end
    if rotation then
        lines[#lines + 1] = "[" .. Hud.keyLabel(keys.rotation_snap) .. "] SNAP " .. rotation
        lines[#lines + 1] = "[" .. Hud.keyLabel(keys.rotate_left) .. " / " .. Hud.keyLabel(keys.rotate_right)
            .. "] TURN " .. (rotation == "OFF" and "22.5°" or rotation)
    end
    return table.concat(lines, "\n")
end

--------------------------------------------------------------------------------
-- The widget
--------------------------------------------------------------------------------

local function build()
    if valid(W) then return W end
    if missingClass or os.clock() < nextTry then return nil end
    nextTry = os.clock() + 2
    local pc = ctx.pc()
    if not pc then return nil end
    local cls
    local okC = pcall(function()
        local ksl = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
        cls = ksl:LoadClassAsset_Blocking(ksl:Conv_SoftClassPathToSoftClassRef(ksl:MakeSoftClassPath(CLASS)))
    end)
    if not (okC and valid(cls)) then
        missingClass = true
        ctx.log("HUD: " .. CLASS .. " is not installed (pakchunk980-MJOLNIRFORGEUI); the text panel stands in")
        return nil
    end
    cls = ctx.retainClass(CLASS, cls)
    if not cls then return nil end
    local ok, w = pcall(function()
        local wbl = StaticFindObject("/Script/UMG.Default__WidgetBlueprintLibrary")
        local created = wbl:Create(pc, cls, pc)
        created:AddToViewport(40)
        return created
    end)
    if not (ok and valid(w)) then return nil end
    W = w
    face(W.ForgeTitle, "Oxanium", "Bold", 220)
    face(W.ForgeMode, "Oxanium", "Bold", 160)
    face(W.ForgeMap, "NormativePro", "Medium")
    face(W.TargetCategory, "Oxanium", "Bold", 180)
    face(W.TargetName, "NormativePro", "Bold")
    face(W.DistanceLabel, "Oxanium", "Bold", 160)
    face(W.DistanceValue, "Oxanium", "Bold")
    face(W.ToastText, "NormativePro", "Bold")
    if valid(W.PaletteSize) then
        face(W.PaletteTitle, "Oxanium", "Bold", 220)
        face(W.PaletteCount, "Oxanium", "Bold")
        face(W.PaletteGroup, "Oxanium", "Bold", 180)
        face(W.PaletteName, "NormativePro", "Bold")
        for i = 0, PALETTE_ROWS - 1 do face(W["PaletteRow" .. i .. "Name"], "NormativePro", "Medium") end
        for _, cap in ipairs({ "PalettePrev", "PaletteNext", "PaletteHint0", "PaletteHint1" }) do
            face(W[cap .. "Key"], "Oxanium", "Bold")
            face(W[cap .. "Act"], "Oxanium", "Bold", 120)
        end
        -- The category's keys are caps alone.
        setVisible(W.PalettePrevAct, false)
        setVisible(W.PaletteNextAct, false)
    end
    for i = 0, CARD_HINTS - 1 do
        face(W["Target" .. i .. "Key"], "Oxanium", "Bold")
        face(W["Target" .. i .. "Act"], "Oxanium", "Bold", 120)
    end
    for i = 0, CONTROLS - 1 do
        face(W["Control" .. i .. "Key"], "Oxanium", "Bold")
        face(W["Control" .. i .. "Act"], "Oxanium", "Bold", 120)
    end
    ctx.log("HUD up")
    return W
end

--- Keys in slots: { { key = "B", act = "SPARTAN", on = true }, ... }.
local function fillKeys(prefix, count, rows)
    for i = 0, count - 1 do
        local slot = W[prefix .. i]
        local row = rows[i + 1]
        if row then
            setText(W[prefix .. i .. "Key"], row.key)
            setText(W[prefix .. i .. "Act"], row.act)
            setOpacity(slot, row.on == false and 0.35 or 1)
            setVisible(slot, true)
        else
            setVisible(slot, false)
        end
    end
end

local function weaponIcon(tag, box, image)
    box, image = box or W.TargetIconBox, image or W.TargetIcon
    local path = ICONS[tag or ""]
    local tex = path and load(path)
    local material = tex and load(ICON_MATERIAL)
    if not (tex and material) then
        setVisible(box, false)
        return
    end
    -- As the kill feed draws them (MJOLNIRHud feed.lua): Empty 0 and
    -- Equipped 1, or the material draws the red of an empty weapon.
    local ok = pcall(function()
        image:SetBrushFromMaterial(material)
        local mid = image:GetDynamicMaterial()
        mid:SetTextureParameterValue(FName("InputTexture"), tex)
        mid:SetScalarParameterValue(FName("Empty"), 0)
        mid:SetScalarParameterValue(FName("Equipped"), 1)
        image:SetColorAndOpacity({ R = 1, G = 1, B = 1, A = 1 })
    end)
    -- Each silhouette has its own shape (a rifle is long, the Banshee's
    -- taller than wide): fit it in the box at its own aspect, centred, rather
    -- than stretch it, so the name beside it stays put.
    local okSize, w, h = pcall(function() return tex:Blueprint_GetSizeX(), tex:Blueprint_GetSizeY() end)
    local aspect = (okSize and type(w) == "number" and type(h) == "number" and h > 0) and w / h or ICON_W / ICON_H
    local width = math.min(ICON_W, ICON_H * aspect)
    pcall(function()
        image:SetDesiredSizeOverride({ X = width, Y = width / aspect })
        image.Slot:SetHorizontalAlignment(CENTRE)
        image.Slot:SetVerticalAlignment(CENTRE)
    end)
    setVisible(box, ok)
end

local function showToast(text, color)
    toast.generation = toast.generation + 1
    local generation = toast.generation
    setText(W.ToastText, text)
    pcall(function() W.ToastAccent:SetBrushColor(color) end)
    setOpacity(W.Toast, 1)
    setVisible(W.Toast, true)
    for step = 1, FADE_STEPS do
        ExecuteInGameThreadWithDelay(math.floor(TOAST_SECONDS * 1000) + step * 70, function()
            if toast.generation ~= generation or not valid(W) then return end
            local a = 1 - step / FADE_STEPS
            setOpacity(W.Toast, a)
            if step == FADE_STEPS then setVisible(W.Toast, false) end
        end)
    end
end

-- What the DLL says it did -> the toast's words and colour.
function Hud.notice(last, name, keys)
    keys = keys or {}
    -- A pack binding refusal includes the recovery action. Do not replace
    -- it with the generic "no palette entry" message below.
    if last:match("^%a+ failed:") then return string.upper(last), GOLD end
    if last == "monitor" then return "FORGE MONITOR", ACCENT end
    if last == "biped" then return "BACK TO YOUR SPARTAN", ACCENT end
    if last == "grabbed" then return "PICKED UP  " .. name, GREEN end
    if last == "released" then return "DROPPED  " .. name, ACCENT end
    if last == "deleted" then return "DELETED  " .. name, GOLD end
    if last == "duplicated" then return "DUPLICATED  " .. name, GREEN end
    local placed = last:match("^placed (.+)$")
    if placed then return "PLACED  " .. Hud.prettyName(placed), GREEN end
    local refused = last:match("^cannot place ([%w_]+)$")
    if refused then return "THIS MAP CAN'T PLACE ANOTHER  " .. Hud.prettyName(refused), GOLD end
    local saved = last:match("^saved layout %S+, (%d+) objects$")
    if saved then return "LAYOUT SAVED  " .. saved .. " OBJECTS", GREEN end
    local reloaded = last:match("^loaded layout %S+, (%d+) objects$")
    if reloaded then return "LAYOUT LOADED  " .. reloaded .. " OBJECTS", GREEN end
    local restored = last:match("^restored layout %S+, (%d+) objects$")
    if restored then return "SAVED LAYOUT RESTORED  " .. restored .. " OBJECTS", GREEN end
    if last == "press again: saved layout goes to history" or last == "press again: map's own layout" then
        local key = Hud.keyLabel(keys.revert or "F2")
        local cost = last:find("history", 1, true) and "YOUR SAVE GOES TO HISTORY" or "UNSAVED OBJECTS ARE LOST"
        return "PRESS " .. key .. " AGAIN FOR THE MAP'S OWN LAYOUT  " .. cost, GOLD
    end
    if last == "reverted: saved layout moved to history" then
        return "THE MAP'S OWN LAYOUT  " .. Hud.keyLabel(keys.load or "F6") .. " BRINGS YOUR SAVE BACK", ACCENT
    end
    if last == "reverted to the map's own layout" then return "THE MAP'S OWN LAYOUT", ACCENT end
    local team = last:match("^team (%a+)$")
    if team then return "TEAM  " .. string.upper(team), ACCENT end
    local label = last:match("^label (.+)$")
    if label then return "LABEL  " .. label, ACCENT end
    local respawn = last:match("^respawn (%d+) s$")
    if respawn then return "RESPAWN  " .. respawn .. " S", ACCENT end
    local facing = last:match("^facing (%-?%d+)$")
    if facing then return "FACING  " .. facing .. "°", ACCENT end
    local order = last:match("^spawn order (%-?%d+)$")
    if order then return "SPAWN ORDER  " .. order, ACCENT end
    local channel = last:match("^channel ([%w]+)$")
    if channel then return "TELEPORTER CHANNEL  " .. string.upper(channel), ACCENT end
    local physics = Hud.physicsName(last:match("^physics (%a+)$"))
    if physics then return "PHYSICS  " .. physics, ACCENT end
    if last:match("^grid ") or last:match("^rotation snap ") then return string.upper(last), ACCENT end
    if last == "this map has no Forge palette" then return "This map has no Forge palette", GOLD end
    if last:find("palette") then return "This map has no Forge palette entry for that yet", GOLD end
    return string.upper(last), GOLD
end

--------------------------------------------------------------------------------
-- Rendering
--------------------------------------------------------------------------------

-- The rows of `palette` in `row`'s category (one palette, one tag group, as
-- the DLL counts them), and where `row` is among them.
local function categoryOf(palette, row)
    local members, at = {}, nil
    for _, r in ipairs(palette) do
        if r.palette == row.palette and r.group == row.group then
            members[#members + 1] = r
            if r == row then at = #members end
        end
    end
    return members, at or 1
end

-- The palette panel, or a toast where the HUD has none (CE runtime 1.14.0).
local function drawPalette(palette, row, keys, editing, budgetOf)
    local panel = valid(W.PaletteSize) and W.PaletteSize or nil
    if not (editing and row) then
        if panel then setVisible(panel, false) end
        lastChoice = nil
        return
    end
    local choice = row.palette .. ":" .. row.entry
    if not panel then
        if lastChoice and choice ~= lastChoice then
            showToast(string.format("%s  %s", Hud.paletteCategory(row), Hud.paletteName(row)), ACCENT)
        end
        lastChoice = choice
        return
    end
    lastChoice = choice
    local members, at = categoryOf(palette, row)
    setText(W.PaletteCount, string.format("%d / %d", at, #members))
    setText(W.PaletteGroup, Hud.paletteCategory(row))
    setText(W.PalettePrevKey, Hud.keyLabel(keys.prev_category))
    setText(W.PaletteNextKey, Hud.keyLabel(keys.next_category))
    -- A quota and a price, where the map sets them (docs/forge.md, Budgets).
    local extra = ""
    if (row.maximum or 0) > 0 then extra = extra .. string.format("  %d/%d", row.placed or 0, row.maximum) end
    if (row.price or 0) > 0 then extra = extra .. string.format("  $%d", row.price) end
    setText(W.PaletteName, Hud.paletteName(row) .. extra)
    local budget = tonumber(budgetOf.budget or "") or 0
    local title = budget > 0 and string.format("PALETTE  $%s / $%d", budgetOf.spent or "0", budget) or "PALETTE"
    local settings = Hud.editSettings(budgetOf, keys)
    setText(W.PaletteTitle, title .. (settings ~= "" and ("\n" .. settings) or ""))
    setTextColor(W.PaletteName, row.placeable and WHITE or GREY)
    weaponIcon(Hud.packBlock(row.full_tag) and "" or row.tag, W.PaletteIconBox, W.PaletteIcon)
    -- A window of the list with the selection in its middle where it can be.
    local first = math.max(1, math.min(at - math.floor(PALETTE_ROWS / 2), #members - PALETTE_ROWS + 1))
    for i = 0, PALETTE_ROWS - 1 do
        local line = W["PaletteRow" .. i]
        local r = members[first + i]
        if r then
            local selected = first + i == at
            setText(W["PaletteRow" .. i .. "Name"], Hud.paletteName(r))
            setTextColor(W["PaletteRow" .. i .. "Name"], selected and WHITE or GREY)
            pcall(function() line:SetBrushColor(selected and ROW_SELECTED or ROW_PLAIN) end)
            setOpacity(line, r.placeable and 1 or 0.4)
            setVisible(line, true)
        else
            setVisible(line, false)
        end
    end
    setText(W.PaletteHint0Key, Hud.keyLabel(keys.prev_item) .. " / " .. Hud.keyLabel(keys.next_item))
    setText(W.PaletteHint1Key, Hud.keyLabel(keys.place))
    setOpacity(W.PaletteHint1, row.placeable and 1 or 0.35)
    setVisible(panel, true)
end

--- deps: { log, pc, retainClass }.
function Hud.init(deps)
    ctx = deps
end

--- Show the editor's state `s` (forge_state.txt's fields), with the key
--- names `keys`, the map's title, the palette's rows and the selected one.
--- False when the widget is not there.
function Hud.render(s, keys, mapTitle, palette, choice)
    local active = s.forge == "1" and s.player ~= nil and s.player ~= "-1"
    if not active then
        if valid(W) then setVisible(W, false) end
        return valid(W) or not missingClass
    end
    if not build() then return false end
    setVisible(W, true)

    local editing = s.editing == "1"
    local holding = editing and s.held ~= nil and s.held ~= "ffffffff"
    local aiming = editing and not holding and s.cursor ~= nil and s.cursor ~= "ffffffff"
    local tag = holding and s.held_tag or (aiming and s.cursor_tag or nil)
    local fullTag = holding and s.held_path or (aiming and s.cursor_path or nil)
    local group = holding and s.held_group or (aiming and s.cursor_group or nil)
    local name = tag and Hud.prettyName(tag, fullTag) or nil
    if name then lastTarget = name end

    -- The badge.
    setText(W.ForgeMode, editing and "MONITOR" or "SPARTAN")
    setTextColor(W.ForgeMode, editing and ACCENT or WHITE)
    setText(W.ForgeMap, mapTitle or "")

    -- The cursor (the Spartan has the game's own crosshair).
    setVisible(W.ReticleBox, editing)
    pcall(function()
        W.Reticle:SetColorAndOpacity(holding and GREEN or (aiming and WHITE or RETICLE_IDLE))
    end)

    -- The target card.
    if name then
        setText(W.TargetCategory, Hud.packCategory(fullTag) or Hud.category(group))
        setTextColor(W.TargetCategory, holding and GREEN or ACCENT)
        setText(W.TargetName, name .. Hud.properties(s, keys))
        weaponIcon(Hud.packBlock(fullTag) and "" or tag)
        local distance = Hud.keyLabel(keys.farther) .. " / " .. Hud.keyLabel(keys.nearer)
        if holding then
            fillKeys("Target", CARD_HINTS, {
                { key = Hud.keyLabel(keys.grab), act = "DROP" },
                { key = distance, act = "DISTANCE" },
                { key = Hud.keyLabel(keys.delete), act = "DELETE" },
            })
            local d = tonumber(s.distance or "") or DISTANCE_MIN
            local share = math.max(0, math.min(1, (d - DISTANCE_MIN) / (DISTANCE_MAX - DISTANCE_MIN)))
            pcall(function() W.DistanceFill:SetWidthOverride(math.floor(DISTANCE_TRACK * share + 0.5)) end)
            setText(W.DistanceValue, string.format("%.1f m", d))
            setVisible(W.DistanceRow, true)
        else
            fillKeys("Target", CARD_HINTS, {
                { key = Hud.keyLabel(keys.grab), act = "PICK UP" },
                { key = Hud.keyLabel(keys.duplicate), act = "DUPLICATE" },
                { key = Hud.keyLabel(keys.delete), act = "DELETE" },
            })
            setVisible(W.DistanceRow, false)
        end
        setVisible(W.TargetCard, true)
    else
        -- Clear content as well as visibility: a partial/missing target must
        -- never leave the previous object's properties on the next card.
        setText(W.TargetName, "")
        setText(W.TargetCategory, "")
        setVisible(W.DistanceRow, false)
        setVisible(W.TargetCard, false)
    end

    -- The control bar.
    if editing and (s.grid_m ~= nil or s.rotation_snap ~= nil or s.physics ~= nil) then
        local physics, grid, rotation = Hud.physicsName(s.physics), Hud.gridName(s.grid_m), Hud.rotationName(s.rotation_snap)
        fillKeys("Control", CONTROLS, {
            { key = Hud.keyLabel(keys.toggle), act = "SPARTAN" },
            { key = Hud.keyLabel(keys.grab), act = holding and "DROP" or "PICK UP", on = holding or aiming },
            { key = Hud.keyLabel(keys.physics), act = physics and ("PHYSICS " .. physics) or "PHYSICS", on = (holding or aiming) and physics ~= nil },
            { key = Hud.keyLabel(keys.grid), act = "GRID " .. (grid or "—"), on = grid ~= nil },
            { key = Hud.keyLabel(keys.rotation_snap), act = "SNAP " .. (rotation or "—"), on = rotation ~= nil },
            { key = Hud.keyLabel(keys.place), act = "PLACE", on = choice ~= nil and choice.placeable },
        })
    elseif editing then
        fillKeys("Control", CONTROLS, {
            { key = Hud.keyLabel(keys.toggle), act = "SPARTAN" },
            { key = Hud.keyLabel(keys.grab), act = holding and "DROP" or "PICK UP", on = holding or aiming },
            { key = Hud.keyLabel(keys.duplicate), act = "DUPLICATE", on = aiming or holding },
            { key = Hud.keyLabel(keys.delete), act = "DELETE", on = aiming or holding },
            s.channel and { key = Hud.keyLabel(keys.channel), act = "CHANNEL", on = holding or aiming }
                or { key = Hud.keyLabel(keys.farther) .. " / " .. Hud.keyLabel(keys.nearer), act = "DISTANCE", on = holding },
            { key = Hud.keyLabel(keys.place), act = "PLACE", on = choice ~= nil and choice.placeable },
        })
    else
        fillKeys("Control", CONTROLS, {
            { key = Hud.keyLabel(keys.toggle), act = "FORGE MONITOR" },
            { key = Hud.keyLabel(keys.save), act = "SAVE LAYOUT" },
            { key = Hud.keyLabel(keys.load), act = "LOAD LAYOUT" },
            { key = Hud.keyLabel(keys.revert), act = "MAP'S OWN LAYOUT" },
        })
    end

    drawPalette(palette or {}, choice, keys, editing, s)

    -- The toast, once per thing the DLL did.
    if s.last_id and s.last_id ~= toast.id then
        local first = toast.id == nil
        toast.id = s.last_id
        if not first and s.last and s.last ~= "" then
            local text, color = Hud.notice(s.last, lastTarget or "Object", keys)
            showToast(text, color)
        end
    end
    return true
end

--- Hide the HUD (a game ended, the mod turned it off). Never removed: removing
--- a widget from the viewport hung the game once.
function Hud.hide()
    if valid(W) then setVisible(W, false) end
end

return Hud

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

--- "assault_rifle" -> "Assault Rifle".
function Hud.prettyName(tag)
    if not tag or tag == "" then return "Object" end
    if NAMES[tag] then return NAMES[tag] end
    return (tag:gsub("_", " "):gsub("(%a)([%w]*)", function(a, b) return string.upper(a) .. b end))
end

function Hud.category(group)
    return CATEGORIES[group or ""] or "OBJECT"
end

--- A UE4SS key name as the key cap shows it: PAGE_UP -> PG UP.
function Hud.keyLabel(name)
    local pretty = { PAGE_UP = "PG UP", PAGE_DOWN = "PG DN", DEL = "DEL", INS = "INS", SPACE = "SPACE",
        LEFT_ARROW = "←", RIGHT_ARROW = "→", UP_ARROW = "↑", DOWN_ARROW = "↓" }
    return pretty[name] or (tostring(name):gsub("_", " "))
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
local function toastFor(last, name)
    if last == "monitor" then return "FORGE MONITOR", ACCENT end
    if last == "biped" then return "BACK TO YOUR SPARTAN", ACCENT end
    if last == "grabbed" then return "PICKED UP  " .. name, GREEN end
    if last == "released" then return "DROPPED  " .. name, ACCENT end
    if last == "deleted" then return "DELETED  " .. name, GOLD end
    if last == "duplicated" then return "DUPLICATED  " .. name, GREEN end
    local placed = last:match("^placed (.+)$")
    if placed then return "PLACED  " .. Hud.prettyName(placed), GREEN end
    local refused = last:match("^cannot place (.+)$")
    if refused then return "THIS MAP CAN'T PLACE ANOTHER  " .. Hud.prettyName(refused), GOLD end
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
local function drawPalette(palette, row, keys, editing)
    local panel = valid(W.PaletteSize) and W.PaletteSize or nil
    if not (editing and row) then
        if panel then setVisible(panel, false) end
        lastChoice = nil
        return
    end
    local choice = row.palette .. ":" .. row.entry
    if not panel then
        if lastChoice and choice ~= lastChoice then
            showToast(string.format("%s  %s", SHELVES[row.group] or "PALETTE", Hud.prettyName(row.tag)), ACCENT)
        end
        lastChoice = choice
        return
    end
    lastChoice = choice
    local members, at = categoryOf(palette, row)
    setText(W.PaletteCount, string.format("%d / %d", at, #members))
    setText(W.PaletteGroup, SHELVES[row.group] or Hud.category(row.group))
    setText(W.PalettePrevKey, Hud.keyLabel(keys.prev_category))
    setText(W.PaletteNextKey, Hud.keyLabel(keys.next_category))
    setText(W.PaletteName, Hud.prettyName(row.tag))
    setTextColor(W.PaletteName, row.placeable and WHITE or GREY)
    weaponIcon(row.tag, W.PaletteIconBox, W.PaletteIcon)
    -- A window of the list with the selection in its middle where it can be.
    local first = math.max(1, math.min(at - math.floor(PALETTE_ROWS / 2), #members - PALETTE_ROWS + 1))
    for i = 0, PALETTE_ROWS - 1 do
        local line = W["PaletteRow" .. i]
        local r = members[first + i]
        if r then
            local selected = first + i == at
            setText(W["PaletteRow" .. i .. "Name"], Hud.prettyName(r.tag))
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

--- deps: { log, pc }.
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
    local group = holding and s.held_group or (aiming and s.cursor_group or nil)
    local name = tag and Hud.prettyName(tag) or nil
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
        setText(W.TargetCategory, Hud.category(group))
        setTextColor(W.TargetCategory, holding and GREEN or ACCENT)
        setText(W.TargetName, name)
        weaponIcon(tag)
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
        setVisible(W.TargetCard, false)
    end

    -- The control bar.
    if editing then
        fillKeys("Control", CONTROLS, {
            { key = Hud.keyLabel(keys.toggle), act = "SPARTAN" },
            { key = Hud.keyLabel(keys.grab), act = holding and "DROP" or "PICK UP", on = holding or aiming },
            { key = Hud.keyLabel(keys.duplicate), act = "DUPLICATE", on = aiming or holding },
            { key = Hud.keyLabel(keys.delete), act = "DELETE", on = aiming or holding },
            { key = Hud.keyLabel(keys.farther) .. " / " .. Hud.keyLabel(keys.nearer), act = "DISTANCE", on = holding },
            { key = Hud.keyLabel(keys.place), act = "PLACE", on = choice ~= nil and choice.placeable },
        })
    else
        fillKeys("Control", CONTROLS, { { key = Hud.keyLabel(keys.toggle), act = "FORGE MONITOR" } })
    end

    drawPalette(palette or {}, choice, keys, editing)

    -- The toast, once per thing the DLL did.
    if s.last_id and s.last_id ~= toast.id then
        local first = toast.id == nil
        toast.id = s.last_id
        if not first and s.last and s.last ~= "" then
            local text, color = toastFor(s.last, lastTarget or "Object")
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

-- MJOLNIR HUD: the pictures the kill feed draws (docs/multiplayer_hud.md).
--
-- Weapons are the game's own silhouettes, the ones its weapon cradle shows
-- (ui/Hud/WeaponCradle, ui/Hud/GrenadeCradle). They are channel-packed masks,
-- so they are drawn through the game's own icon material
-- (M_HUDCradleIcon, by way of a frag grenade's instance), with the mask as
-- its InputTexture: the cyan of the game's HUD.
--
-- Everything else is one of MJOLNIR's own glyphs, white, tinted per line:
-- T_MJHud_<Name> in /Game/MJOLNIR/UI/Icons (tools/ue/draw_hud_icons.py),
-- cooked with WBP_MJOLNIRKillFeed into chunk 984.
--
-- The catalogue is plain data; the loaders need the game.

local Icons = {}

local WEAPON_DIR = "/Game/UI/Hud/WeaponCradle/Textures/"
local GRENADE_DIR = "/Game/UI/Hud/GrenadeCradle/Textures/"
local GLYPH_DIR = "/Game/MJOLNIR/UI/Icons/"
local ICON_MATERIAL = "/Game/UI/Hud/GrenadeCradle/Materials/MI_HUDCradleIcon_FragGrenade"
local FONT_DIR = "/Game/Fonts/"

--- Blam.DamageReporting.Type.<name> -> the game's silhouette for it.
Icons.WEAPONS = {
    AssaultRifle = WEAPON_DIR .. "T_UI_AssaultRifle_WeaponIcon",
    BattleRifle = WEAPON_DIR .. "T_UI_BattleRifle_WeaponIcon",
    BeamRifle = WEAPON_DIR .. "T_UI_BeamRifle_WeaponIcon",
    EnergyBlade = WEAPON_DIR .. "T_UI_EnergySword_WeaponIcon",
    PlasmaCannon = WEAPON_DIR .. "T_UI_FuelRod_WeaponIcon",
    FlakCannon = WEAPON_DIR .. "T_UI_FuelRod_WeaponIcon",
    MagnumPistol = WEAPON_DIR .. "T_UI_Pistol_WeaponIcon",
    NeedleRifle = WEAPON_DIR .. "T_UI_NeedleRifle_WeaponIcon",
    Needler = WEAPON_DIR .. "T_UI_Needler_WeaponIcon",
    PlasmaPistol = WEAPON_DIR .. "T_UI_PlasmaPistol_WeaponIcon",
    PlasmaRifle = WEAPON_DIR .. "T_UI_PlasmaRifleIcon",
    PlasmaRepeater = WEAPON_DIR .. "T_UI_PlasmaRifleIcon",
    RocketLauncher = WEAPON_DIR .. "T_UI_SPNKR_WeaponIcon",
    SentinelBeam = WEAPON_DIR .. "T_UI_SentinelBeam_WeaponIcon",
    Shotgun = WEAPON_DIR .. "T_UI_Shotgun_WeaponIcon",
    Smg = WEAPON_DIR .. "T_UI_SMG_WeaponIcon",
    SniperRifle = WEAPON_DIR .. "T_UI_SniperRifle_WeaponIcon",
    SpikeRifle = WEAPON_DIR .. "T_UI_SpikerRifle_WeaponIcon",
    FragGrenade = GRENADE_DIR .. "T_UI_FragGrenade_WeaponIcon",
    PlasmaGrenade = GRENADE_DIR .. "T_UI_PlasmaGrenade_WeaponIcon",
    Ghost = WEAPON_DIR .. "T_UI_Ghost_WeaponIcon",
    Banshee = WEAPON_DIR .. "T_UI_BansheeDualCannon_WeaponIcon",
    BansheeBomb = WEAPON_DIR .. "T_UI_BansheeBomb_WeaponIcon",
    Scorpion = WEAPON_DIR .. "T_IU_ScorpionMainGun_Icon",
    ScorpionGunner = WEAPON_DIR .. "T_UI_ScorpionTurret_Icon",
    Tank = WEAPON_DIR .. "T_IU_ScorpionMainGun_Icon",
    ShadeTurret = WEAPON_DIR .. "T_UI_ShadeTurret_Icon",
    PlasmaTurret = WEAPON_DIR .. "T_UI_ShadeTurret_Icon",
    WarthogGunner = WEAPON_DIR .. "T_UI_WarthogTurret_Icon",
    WarthogGunnerGauss = WEAPON_DIR .. "T_UI_WarthogTurret_Icon",
    WarthogGunnerRocket = WEAPON_DIR .. "T_UI_WarthogTurret_Icon",
    HumanTurret = WEAPON_DIR .. "T_UI_WarthogTurret_Icon",
    Wraith = WEAPON_DIR .. "T_UI_WraithMainGun_Icon",
    WraithAntiInfantry = WEAPON_DIR .. "T_UI_WraithTurret_Icon",
    Seraph = WEAPON_DIR .. "T_UI_SeraphTurret_Icon",
}

--- Damage with no silhouette of the game's: one of our glyphs in the
--- weapon's place.
Icons.DAMAGE_GLYPHS = {
    Melee = "Melee",
    FallingDamage = "Fall",
    KnownGuardians = "Guardians",
    Teleporter = "Telefrag",
    Explosion = "Explosion",
    BombExplosion = "Explosion",
    BirthdayPartyExplosion = "Explosion",
    CollisionDamage = "Splatter",
    WarthogDriver = "Splatter",
    Mongoose = "Splatter",
    Flag = "Flag",
}

-- EBlamDamageReportingModifier
local HEADSHOT, SILENT_MELEE, COLLISION, ATTACHED, ASSASSINATION = 1, 2, 3, 4, 5

--- The glyph a modifier adds after the weapon.
Icons.MODIFIERS = { [HEADSHOT] = "Headshot", [COLLISION] = "Splatter", [ATTACHED] = "Stuck" }

--- "Blam.DamageReporting.Type.AssaultRifle" -> "AssaultRifle"; nil for the
--- Invalid type an incident without damage carries.
function Icons.damageType(tag)
    local tail = type(tag) == "string" and tag:match("([%w_]+)$")
    if not tail or tail == "Invalid" or tail == "None" then return nil end
    return tail
end

--- "AssaultRifle" -> "Assault Rifle".
function Icons.label(kind)
    if not kind then return nil end
    return (kind:gsub("(%l)(%u)", "%1 %2"):gsub("_", " "))
end

--- What a kill line shows between the names: { weapon = texture path (the
--- game's), glyph = our glyph in the weapon's place, mod = our glyph after
--- it, note = the weapon's name when there is no picture for it }.
function Icons.forKill(damageTag, modifier)
    local kind = Icons.damageType(damageTag)
    local shown = {}
    if modifier == SILENT_MELEE or modifier == ASSASSINATION then
        shown.glyph = "Assassination"
    elseif kind and Icons.WEAPONS[kind] then
        shown.weapon = Icons.WEAPONS[kind]
    elseif kind and Icons.DAMAGE_GLYPHS[kind] then
        shown.glyph = Icons.DAMAGE_GLYPHS[kind]
    elseif kind then
        shown.note = Icons.label(kind)
    end
    shown.mod = Icons.MODIFIERS[modifier]
    -- A splatter by a vehicle with no silhouette already shows the splat.
    if shown.mod == "Splatter" and shown.glyph == "Splatter" then shown.mod = nil end
    if not (shown.weapon or shown.glyph or shown.note) then
        shown.glyph = shown.mod or "Skull"
        if shown.glyph == shown.mod then shown.mod = nil end
    end
    return shown
end

--------------------------------------------------------------------------------
-- Loading (in the game)
--------------------------------------------------------------------------------

local missing = {}     -- object path -> true once a load failed
local found = {}       -- object path -> the object, while it is valid

local function valid(o)
    local ok, v = pcall(function() return o and o:IsValid() end)
    return ok and v == true
end

--- "/Game/A/B/T_X" -> "/Game/A/B/T_X.T_X".
local function objectPath(path)
    if path:find("%.") then return path end
    return path .. "." .. path:match("([^/]+)$")
end

--- The asset at `path`, loaded once. The object found is kept and checked
--- with IsValid before each use: StaticFindObject by path costs ~2 ms in
--- UE4SS (19 ms the first time), and a feed line needs half a dozen, so
--- finding them every time held the game thread 50-80 ms per kill (two
--- PCs, 2026-10-17). An object no brush holds may still be collected; it is
--- then found, or loaded, again.
function Icons.load(path)
    local full = objectPath(path)
    local hit = found[full]
    if hit and valid(hit) then return hit end
    if missing[full] then return nil end
    local ok, obj = pcall(StaticFindObject, full)
    if not (ok and valid(obj)) then
        ok, obj = pcall(function()
            local ksl = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
            return ksl:LoadAsset_Blocking(ksl:Conv_SoftObjPathToSoftObjRef(ksl:MakeSoftObjectPath(full)))
        end)
    end
    if ok and valid(obj) then
        found[full] = obj
        return obj
    end
    missing[full] = true
    return nil
end

function Icons.glyph(name)
    return name and Icons.load(GLYPH_DIR .. "T_MJHud_" .. name) or nil
end

--- The game's icon material, for a weapon Image's brush.
function Icons.material()
    return Icons.load(ICON_MATERIAL)
end

--- A texture's width over its height (the weapon silhouettes are wide).
function Icons.aspect(tex)
    local ok, w, h = pcall(function() return tex:Blueprint_GetSizeX(), tex:Blueprint_GetSizeY() end)
    if ok and type(w) == "number" and type(h) == "number" and h > 0 then return w / h end
    return 1
end

--- The game's fonts: Oxanium (the menus' squared face) and Normative Pro.
function Icons.font(name)
    return Icons.load(FONT_DIR .. "Font_" .. name)
end

return Icons

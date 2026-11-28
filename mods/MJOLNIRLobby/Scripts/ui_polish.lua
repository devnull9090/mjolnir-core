-- MJOLNIR Lobby: native Halo typography, crystalline UI audio, and 60fps
-- pure-time micro-motion across all MJOLNIR menu screens.
--
-- Pure-Lua helpers (easing, cue mapping, font specs, track stepping) run
-- without Unreal so tools/tests/test_ui_polish.lua can cover them directly.
-- Every Unreal call is guarded and degrades silently on older UI containers
-- that lack new widgets or SoundWave cues.

local M = {}

local FONT_PATHS = {
    Oxanium = "/Game/Fonts/Font_Oxanium.Font_Oxanium",
    NormativePro = "/Game/Fonts/Font_NormativePro.Font_NormativePro",
}

local SOUND_ROOT = "/Game/MJOLNIR/UI/Sounds/SW_MJUI_"

M.VOLUMES = {
    Hover = 0.28,
    Select = 0.42,
    Primary = 0.52,
    Back = 0.36,
    Tab = 0.34,
    Vote = 0.46,
    Tick = 0.26,
    Open = 0.30,
}

M.HOVER_DEBOUNCE = 0.042
M.ENTER_DURATION = 0.24
M.HOVER_DURATION = 0.11
M.PREVIEW_DURATION = 0.14
M.PULSE_DURATION = 0.20
M.HOVER_SHIFT = 7.0

local function clamp01(p)
    if p < 0 then return 0 elseif p > 1 then return 1 end
    return p
end

local function easeOutCubic(p)
    p = clamp01(p)
    local q = 1 - p
    return 1 - q * q * q
end

local function easeOutBack(p)
    p = clamp01(p)
    local c = 1.4
    local q = p - 1
    return 1 + (c + 1) * q * q * q + c * q * q
end

M.easeOutCubic = easeOutCubic
M.easeOutBack = easeOutBack

-------------------------------------------------------------------------------
-- Event -> audio cue mapping (pure)
-------------------------------------------------------------------------------

function M.cueForEvent(event)
    if type(event) ~= "string" or event == "" then return nil end
    if event:find("^btn_unhover:") or event == "unhover" or event:find("^unhover:")
        or event:find("^modeunhover:") or event:find("^vunhover:")
        or event == "search" then
        return nil
    end
    if event:find("^btn_hover:") or event:find("^hover:") or event:find("^modehover:")
        or event:find("^vhover:") then
        return "Hover"
    end
    if event == "start" or event == "select" or event == "join" or event == "quickjoin"
        or event == "download" then
        return "Primary"
    end
    if event == "back" or event == "lobby" or event == "cancel" or event == "report_cancel"
        or event == "search_clear" then
        return "Back"
    end
    if event:find("^vote:") then
        return "Vote"
    end
    if event:find("^tab:") or event:find("^filter:") or event:find("^sort:")
        or event:find("^page:") or event:find("^variant:") or event:find("^mode:")
        or event == "maxdown" or event == "maxup" or event == "maxplayers"
        or event == "listing" or event:find("^prev:") or event:find("^next:") then
        return "Tab"
    end
    return "Select"
end

-------------------------------------------------------------------------------
-- Native Halo font role tables (pure)
-------------------------------------------------------------------------------

-- { widgetName, family, typeface, letterSpacing, [count] }
-- When `count` is set, applies to `<prefix>0 .. <prefix><count-1>`.
-- When `suffix` (5th element string) is set with `count` (6th), applies to
-- `<prefix>0<suffix> .. <prefix><count-1><suffix>`.
local COMMON_FONTS = {
    { "Subtitle", "Oxanium", "Bold", 150 },
    { "Title", "Oxanium", "SemiBold", 65 },
    { "Status", "NormativePro", "Regular", 20 },
    { "Watermark", "Oxanium", "Medium", 120 },
    { "DiscordLabel", "Oxanium", "Bold", 90 },
    { "DiscordLink", "NormativePro", "Regular", 0 },
    { "HintKey", "Oxanium", "Bold", 80, nil, 4 },
    { "HintAct", "Oxanium", "Medium", 75, nil, 4 },
}

local SCREEN_FONTS = {
    lobby = {
        { "StartLabel", "Oxanium", "Bold", 90 },
        { "InviteLabel", "Oxanium", "SemiBold", 80 },
        { "ChangeMapLabel", "Oxanium", "SemiBold", 80 },
        { "GameTypeLabel", "Oxanium", "SemiBold", 80 },
        { "GameSettingsLabel", "Oxanium", "SemiBold", 80 },
        { "ListingLabel", "Oxanium", "SemiBold", 80 },
        { "FindGamesLabel", "Oxanium", "SemiBold", 80 },
        { "BackLabel", "Oxanium", "SemiBold", 80 },
        { "MaxPlayersCaption", "Oxanium", "Bold", 100 },
        { "MaxPlayersValue", "Oxanium", "Bold", 40 },
        { "MaxPlayersDownLabel", "Oxanium", "Bold", 0 },
        { "MaxPlayersUpLabel", "Oxanium", "Bold", 0 },
        { "MapKicker", "Oxanium", "Bold", 130 },
        { "ModeKicker", "Oxanium", "Bold", 130 },
        { "RulesKicker", "Oxanium", "Bold", 130 },
        { "MapTileChange", "Oxanium", "Bold", 110 },
        { "ModeTileChange", "Oxanium", "Bold", 110 },
        { "RulesChange", "Oxanium", "Bold", 110 },
        { "MapTitle", "Oxanium", "SemiBold", 45 },
        { "ModeTitle", "Oxanium", "SemiBold", 45 },
        { "MapMeta", "NormativePro", "Regular", 10 },
        { "MatchFormat", "Oxanium", "Medium", 90 },
        { "RulesNone", "Oxanium", "Medium", 60 },
        { "Rules", "NormativePro", "Regular", 0 },
        { "Rule", "NormativePro", "Regular", 0, "Label", 10 },
        { "Rule", "Oxanium", "SemiBold", 30, "Value", 10 },
        { "PlayersHeading", "Oxanium", "Bold", 140 },
        { "FFAHeading", "Oxanium", "Bold", 120 },
        { "RedHeading", "Oxanium", "Bold", 120 },
        { "BlueHeading", "Oxanium", "Bold", 120 },
        { "UnassignedHeading", "Oxanium", "Bold", 120 },
        { "FFAPlayer", "NormativePro", "Medium", 0, nil, 16 },
        { "RedPlayer", "NormativePro", "Medium", 0, nil, 16 },
        { "BluePlayer", "NormativePro", "Medium", 0, nil, 16 },
        { "UnassignedPlayer", "NormativePro", "Medium", 0, nil, 16 },
        { "TeamHint", "NormativePro", "Regular", 0 },
    },
    mapselect = {
        { "ListCount", "Oxanium", "Bold", 120 },
        { "SearchClearLabel", "Oxanium", "Bold", 80 },
        { "FilterGameCaption", "Oxanium", "Bold", 90 },
        { "FilterGameValue", "Oxanium", "SemiBold", 50 },
        { "FilterSourceCaption", "Oxanium", "Bold", 90 },
        { "FilterSourceValue", "Oxanium", "SemiBold", 50 },
        { "FilterInstalledCaption", "Oxanium", "Bold", 90 },
        { "FilterInstalledValue", "Oxanium", "SemiBold", 50 },
        { "MapTitle", "Oxanium", "SemiBold", 45 },
        { "MapTags", "Oxanium", "Medium", 80 },
        { "MapDescription", "NormativePro", "Regular", 0 },
        { "MapMeta", "NormativePro", "Regular", 10 },
        { "ModeName", "Oxanium", "Bold", 70 },
        { "ModeDescription", "NormativePro", "Regular", 0 },
        { "ModeFormat", "Oxanium", "Medium", 90 },
        { "SelectLabel", "Oxanium", "Bold", 90 },
        { "BackLabel", "Oxanium", "SemiBold", 80 },
        { "Mode", "Oxanium", "Bold", 60, "Label", 7 },
        { "Variant", "Oxanium", "SemiBold", 50, "Label", 5 },
        { "Map", "NormativePro", "Medium", 0, "Label", 80 },
        { "Map", "Oxanium", "Bold", 80, "Game", 80 },
        { "Map", "Oxanium", "Bold", 80, "Tag", 80 },
    },
    gametype = {
        { "ListCount", "Oxanium", "Bold", 120 },
        { "ModeKicker", "Oxanium", "Bold", 140 },
        { "ModeTitle", "Oxanium", "SemiBold", 55 },
        { "ModeDescription", "NormativePro", "Regular", 0 },
        { "MatchFormat", "Oxanium", "Medium", 100 },
        { "VariantKicker", "Oxanium", "Bold", 140 },
        { "MapKicker", "Oxanium", "Bold", 140 },
        { "MapTitle", "Oxanium", "SemiBold", 45 },
        { "MapHint", "NormativePro", "Regular", 0 },
        { "SelectLabel", "Oxanium", "Bold", 90 },
        { "BackLabel", "Oxanium", "SemiBold", 80 },
        { "Mode", "Oxanium", "SemiBold", 60, "Label", 7 },
        { "Mode", "NormativePro", "Regular", 15, "Format", 7 },
        { "Mode", "Oxanium", "Bold", 100, "Current", 7 },
        { "Variant", "Oxanium", "SemiBold", 60, "Label", 5 },
        { "Variant", "Oxanium", "Medium", 80, "Line", 5 },
    },
    findgames = {
        { "ListCount", "Oxanium", "Bold", 120 },
        { "ListOrder", "Oxanium", "Medium", 80 },
        { "FilterTypeCaption", "Oxanium", "Bold", 90 },
        { "FilterTypeValue", "Oxanium", "SemiBold", 50 },
        { "FilterMapCaption", "Oxanium", "Bold", 90 },
        { "FilterMapValue", "Oxanium", "SemiBold", 50 },
        { "FilterFullLabel", "Oxanium", "Bold", 85 },
        { "FilterMatchLabel", "Oxanium", "Bold", 85 },
        { "FilterHaveLabel", "Oxanium", "Bold", 85 },
        { "HeadNameLabel", "Oxanium", "Bold", 100 },
        { "HeadMapLabel", "Oxanium", "Bold", 100 },
        { "HeadTypeLabel", "Oxanium", "Bold", 100 },
        { "HeadPlayersLabel", "Oxanium", "Bold", 100 },
        { "HeadPingLabel", "Oxanium", "Bold", 100 },
        { "HeadStateLabel", "Oxanium", "Bold", 100 },
        { "HeadNameSort", "Oxanium", "Bold", 0 },
        { "HeadMapSort", "Oxanium", "Bold", 0 },
        { "HeadTypeSort", "Oxanium", "Bold", 0 },
        { "HeadPlayersSort", "Oxanium", "Bold", 0 },
        { "HeadPingSort", "Oxanium", "Bold", 0 },
        { "HeadStateSort", "Oxanium", "Bold", 0 },
        { "GameKicker", "Oxanium", "Bold", 130 },
        { "GameTitle", "Oxanium", "SemiBold", 45 },
        { "GameHost", "NormativePro", "Medium", 0 },
        { "GameDetails", "NormativePro", "Regular", 0 },
        { "InfoMapLabel", "Oxanium", "Bold", 100 },
        { "InfoMapValue", "Oxanium", "SemiBold", 35 },
        { "InfoTypeLabel", "Oxanium", "Bold", 100 },
        { "InfoTypeValue", "Oxanium", "SemiBold", 35 },
        { "InfoPlayersLabel", "Oxanium", "Bold", 100 },
        { "InfoPlayersValue", "Oxanium", "SemiBold", 35 },
        { "InfoPingLabel", "Oxanium", "Bold", 100 },
        { "InfoPingValue", "Oxanium", "SemiBold", 35 },
        { "InfoRegionLabel", "Oxanium", "Bold", 100 },
        { "InfoRegionValue", "NormativePro", "Medium", 0 },
        { "InfoVersionLabel", "Oxanium", "Bold", 100 },
        { "InfoVersionValue", "Oxanium", "Medium", 35 },
        { "JoinLabel", "Oxanium", "Bold", 90 },
        { "QuickJoinLabel", "Oxanium", "Bold", 85 },
        { "RefreshLabel", "Oxanium", "SemiBold", 80 },
        { "BackLabel", "Oxanium", "SemiBold", 80 },
        { "Empty", "NormativePro", "Regular", 0 },
        { "Game", "NormativePro", "Medium", 0, "Label", 40 },
        { "GameMap", "Oxanium", "SemiBold", 35, nil, 40 },
        { "GameType", "NormativePro", "Regular", 0, nil, 40 },
        { "GamePlayers", "Oxanium", "SemiBold", 30, nil, 40 },
        { "GamePing", "Oxanium", "SemiBold", 25, nil, 40 },
        { "GameState", "Oxanium", "Bold", 60, nil, 40 },
        { "GameNameNote", "NormativePro", "Regular", 0, nil, 40 },
        { "GameMapNote", "NormativePro", "Regular", 0, nil, 40 },
        { "GameTypeNote", "NormativePro", "Regular", 0, nil, 40 },
        { "GamePlayersNote", "NormativePro", "Regular", 0, nil, 40 },
        { "GameStateNote", "NormativePro", "Regular", 0, nil, 40 },
    },
    settings = {
        { "ModeLine", "Oxanium", "Bold", 120 },
        { "Page", "Oxanium", "Bold", 85, "Label", 5 },
        { "HelpTitle", "Oxanium", "Bold", 130 },
        { "HelpValue", "Oxanium", "SemiBold", 45 },
        { "HelpText", "NormativePro", "Regular", 0 },
        { "ResetLabel", "Oxanium", "SemiBold", 80 },
        { "BackLabel", "Oxanium", "Bold", 85 },
        { "Row", "Oxanium", "Medium", 50, "Label", 12 },
        { "Row", "Oxanium", "Bold", 45, "Value", 12 },
        { "Row", "Oxanium", "Bold", 0, "PrevLabel", 12 },
        { "Row", "Oxanium", "Bold", 0, "NextLabel", 12 },
    },
    postgame = {
        { "ResultsKicker", "Oxanium", "Bold", 140 },
        { "Winner", "Oxanium", "Bold", 55 },
        { "Summary", "Oxanium", "Medium", 80 },
        { "TabLabel", "Oxanium", "Bold", 110, nil, 3 },
        { "NameH", "Oxanium", "Bold", 110 },
        { "ScoreH", "Oxanium", "Bold", 110 },
        { "KillsH", "Oxanium", "Bold", 110 },
        { "DeathsH", "Oxanium", "Bold", 110 },
        { "MedalsH", "Oxanium", "Bold", 110 },
        { "Marker", "Oxanium", "Bold", 90, nil, 20 },
        { "Name", "NormativePro", "Medium", 0, nil, 20 },
        { "Score", "Oxanium", "SemiBold", 25, nil, 20 },
        { "Kills", "Oxanium", "Regular", 20, nil, 20 },
        { "Deaths", "Oxanium", "Regular", 20, nil, 20 },
        { "Medals", "Oxanium", "SemiBold", 20, nil, 20 },
        { "ResultsHint", "Oxanium", "Medium", 80 },
        { "VoteKicker", "Oxanium", "Bold", 140 },
        { "VoteTimer", "Oxanium", "SemiBold", 50 },
        { "VoteTally", "Oxanium", "Medium", 70 },
        { "VoteSeconds", "Oxanium", "ExtraBold", 20 },
        { "StartLabel", "Oxanium", "Bold", 90 },
        { "LobbyLabel", "Oxanium", "SemiBold", 80 },
        { "VoteHint", "NormativePro", "Regular", 0 },
        { "Vote", "Oxanium", "Bold", 50, "Label", 4 },
        { "VoteMode", "Oxanium", "Medium", 75, nil, 4 },
        { "VoteTagText", "Oxanium", "Bold", 90, nil, 4 },
        { "VoteMineText", "Oxanium", "Bold", 90, nil, 4 },
        { "VoteCount", "Oxanium", "Bold", 30, nil, 4 },
        { "MineKicker", "Oxanium", "Bold", 130 },
        { "Mine", "NormativePro", "Medium", 0, "Cap", 9 },
        { "MineNote", "NormativePro", "Regular", 0 },
        { "ChartKicker", "Oxanium", "Bold", 130 },
        { "ChartMax", "Oxanium", "Medium", 20 },
        { "ChartStart", "Oxanium", "Medium", 20 },
        { "ChartEnd", "Oxanium", "Medium", 20 },
        { "Legend", "NormativePro", "Medium", 0, nil, 4 },
        { "BarsKicker", "Oxanium", "Bold", 130 },
        { "BarsNote", "NormativePro", "Regular", 0 },
        { "BarsStart", "Oxanium", "Medium", 20 },
        { "BarsEnd", "Oxanium", "Medium", 20 },
        { "Best", "Oxanium", "Bold", 110, "Label", 4 },
        { "Best", "Oxanium", "ExtraBold", 30, "Value", 4 },
        { "Best", "NormativePro", "Medium", 0, "Name", 4 },
        { "Pod", "Oxanium", "Bold", 80, "Place", 3 },
        { "Pod", "NormativePro", "Bold", 0, "Name", 3 },
        { "Pod", "Oxanium", "Bold", 30, "Score", 3 },
        { "Pod", "NormativePro", "Regular", 0, "Line", 3 },
        { "ReportKicker", "Oxanium", "Bold", 140 },
        { "ReportName", "Oxanium", "SemiBold", 40 },
        { "ReportCount", "NormativePro", "Regular", 0 },
        { "ReasonKicker", "Oxanium", "Bold", 130 },
        { "Reason", "Oxanium", "SemiBold", 70, "Label", 7 },
        { "DetailKicker", "Oxanium", "Bold", 130 },
        { "ReportStatus", "NormativePro", "Regular", 0 },
        { "ReportSendLabel", "Oxanium", "Bold", 90 },
        { "ReportCancelLabel", "Oxanium", "SemiBold", 80 },
    },
    download = {
        { "Kicker", "Oxanium", "Bold", 140 },
        { "MapTitle", "Oxanium", "SemiBold", 50 },
        { "Reason", "NormativePro", "Regular", 0 },
        { "InfoAuthorLabel", "Oxanium", "Bold", 100 },
        { "InfoAuthorValue", "NormativePro", "Medium", 0 },
        { "InfoRatingLabel", "Oxanium", "Bold", 100 },
        { "InfoRatingValue", "Oxanium", "SemiBold", 35 },
        { "InfoDownloadsLabel", "Oxanium", "Bold", 100 },
        { "InfoDownloadsValue", "Oxanium", "SemiBold", 35 },
        { "InfoSizeLabel", "Oxanium", "Bold", 100 },
        { "InfoSizeValue", "Oxanium", "SemiBold", 35 },
        { "InfoVersionLabel", "Oxanium", "Bold", 100 },
        { "InfoVersionValue", "Oxanium", "Medium", 35 },
        { "MapDescription", "NormativePro", "Regular", 0 },
        { "ProgressText", "Oxanium", "SemiBold", 55 },
        { "DownloadLabel", "Oxanium", "Bold", 90 },
        { "CancelLabel", "Oxanium", "SemiBold", 80 },
    },
}

local ENTRANCE_ZONES = {
    lobby = { "MenuSize", "Card", "Roster", "FooterBarWrap" },
    mapselect = { "ListPanel", "Details", "Actions", "FooterBarWrap" },
    gametype = { "ListPanel", "Details", "Actions", "FooterBarWrap" },
    findgames = { "ListPanel", "Details", "FooterBarWrap" },
    settings = { "PagesSize", "Options", "Help", "FooterBarWrap" },
    postgame = { "Results", "Vote", "FooterBarWrap" },
    download = { "Card", "FooterBarWrap" },
}

function M.screenKind(classPath)
    if type(classPath) ~= "string" then return nil end
    if classPath:find("WBP_MJOLNIRLobby", 1, true) then return "lobby" end
    if classPath:find("WBP_MJOLNIRMapSelect", 1, true) then return "mapselect" end
    if classPath:find("WBP_MJOLNIRGameTypeSelect", 1, true) then return "gametype" end
    if classPath:find("WBP_MJOLNIRFindGames", 1, true) then return "findgames" end
    if classPath:find("WBP_MJOLNIRGameSettings", 1, true) then return "settings" end
    if classPath:find("WBP_MJOLNIRPostGame", 1, true) then return "postgame" end
    if classPath:find("WBP_MJOLNIRMapDownload", 1, true) then return "download" end
    return nil
end

-------------------------------------------------------------------------------
-- Instance factory
-------------------------------------------------------------------------------

function M.new(deps)
    deps = deps or {}
    local valid = deps.valid or function(o)
        local ok, v = pcall(function() return o and o:IsValid() end)
        return ok and v
    end
    local now = deps.clock or os.clock
    local pcFn = deps.playerController or function() return nil end
    local log = deps.log or function() end

    local self = {}
    local fontCache = {}
    local soundCache = {}
    local staticsCache = nil
    local kslCache = nil
    local lastHoverAt = -10
    local hoverStep = 0
    local tracks = {}          -- key -> animation track
    local adopted = {}         -- widget address -> true (fonts applied once)
    local voteState = nil      -- { screen, left, leftAt, total, held, barWidth, lastTick }
    local pump = { scheduled = false, errors = 0 }
    local loggedInit = false

    local function ksl()
        if not valid(kslCache) then
            local ok, o = pcall(StaticFindObject, "/Script/Engine.Default__KismetSystemLibrary")
            kslCache = ok and valid(o) and o or nil
        end
        return kslCache
    end

    local function statics()
        if not valid(staticsCache) then
            local ok, o = pcall(StaticFindObject, "/Script/Engine.Default__GameplayStatics")
            staticsCache = ok and valid(o) and o or nil
        end
        return staticsCache
    end

    local function loadAsset(path)
        if deps.loadAsset then return deps.loadAsset(path) end
        local lib = ksl()
        if not lib then return nil end
        local ok, asset = pcall(function()
            return lib:LoadAsset_Blocking(lib:Conv_SoftObjPathToSoftObjRef(lib:MakeSoftObjectPath(path)))
        end)
        return ok and valid(asset) and asset or nil
    end

    local function getFont(family)
        local cached = fontCache[family]
        if cached == false then return nil end
        if cached and valid(cached) then return cached end
        local path = FONT_PATHS[family]
        local f = path and loadAsset(path) or nil
        fontCache[family] = f or false
        return f
    end

    local function getSound(cue)
        local cached = soundCache[cue]
        if cached == false then return nil end
        if cached and valid(cached) then return cached end
        local wave = loadAsset(SOUND_ROOT .. cue .. ".SW_MJUI_" .. cue)
        soundCache[cue] = wave or false
        return wave
    end

    local function applyRoleList(screen, roles)
        for _, role in ipairs(roles) do
            local prefix, family, face, spacing, suffix, count =
                role[1], role[2], role[3], role[4], role[5], role[6]
            local font = getFont(family)
            if font then
                if count then
                    for i = 0, count - 1 do
                        local key = suffix and (prefix .. i .. suffix) or (prefix .. i)
                        local okB, block = pcall(function() return screen[key] end)
                        if okB and valid(block) then
                            pcall(function()
                                local size = block.Font and block.Font.Size
                                if type(size) ~= "number" then return end
                                block:SetFont({
                                    FontObject = font,
                                    TypefaceFontName = FName(face),
                                    Size = size,
                                    LetterSpacing = spacing or 0,
                                    SkewAmount = 0,
                                    OutlineSettings = { OutlineSize = 0 },
                                })
                            end)
                        end
                    end
                else
                    local okB, block = pcall(function() return screen[prefix] end)
                    if okB and valid(block) then
                        pcall(function()
                            local size = block.Font and block.Font.Size
                            if type(size) ~= "number" then return end
                            block:SetFont({
                                FontObject = font,
                                TypefaceFontName = FName(face),
                                Size = size,
                                LetterSpacing = spacing or 0,
                                SkewAmount = 0,
                                OutlineSettings = { OutlineSize = 0 },
                            })
                        end)
                    end
                end
            end
        end
    end

    --- Apply native Halo Campaign Evolved fonts (Oxanium + Normative Pro) to a screen.
    function self.applyFonts(screen, kind)
        if not valid(screen) then return end
        applyRoleList(screen, COMMON_FONTS)
        if kind and SCREEN_FONTS[kind] then
            applyRoleList(screen, SCREEN_FONTS[kind])
        end
    end

    --- Play a UI sound cue if available in chunk 984.
    function self.sound(cue, pitchOverride)
        if not cue then return false end
        local t = now()
        if cue == "Hover" then
            if t - lastHoverAt < M.HOVER_DEBOUNCE then return false end
            lastHoverAt = t
            hoverStep = (hoverStep + 1) % 5
        end
        local volume = M.VOLUMES[cue] or 0.35
        local pitch = pitchOverride or (cue == "Hover" and (0.97 + hoverStep * 0.015) or 1.0)
        if deps.playSound then
            return deps.playSound(cue, volume, pitch) ~= false
        end
        local wave = getSound(cue)
        local pc = pcFn()
        local gs = statics()
        if not (wave and valid(pc) and gs) then return false end
        local ok = pcall(function()
            gs:SpawnSound2D(pc, wave, volume, pitch, 0.0, nil, false, true)
        end)
        return ok
    end

    ---------------------------------------------------------------------------
    -- Pure-time animation tracks
    ---------------------------------------------------------------------------

    local function trackKey(widget, prop)
        local okA, addr = pcall(function() return widget:GetAddress() end)
        return tostring(okA and addr or widget) .. ":" .. prop
    end

    local function setTrack(widget, prop, spec)
        if not valid(widget) then return end
        spec.widget = widget
        spec.prop = prop
        tracks[trackKey(widget, prop)] = spec
        self.ensureFrameHook()
    end

    local function applyPose(tr, p)
        local w = tr.widget
        if not valid(w) then return false end
        local e = tr.back and easeOutBack(p) or easeOutCubic(p)
        if tr.tx0 ~= nil or tr.ty0 ~= nil then
            local x = (tr.tx0 or 0) + ((tr.tx1 or 0) - (tr.tx0 or 0)) * e
            local y = (tr.ty0 or 0) + ((tr.ty1 or 0) - (tr.ty0 or 0)) * e
            pcall(function() w:SetRenderTranslation({ X = x, Y = y }) end)
        end
        if tr.a0 ~= nil then
            local a = tr.a0 + (tr.a1 - tr.a0) * clamp01(easeOutCubic(p))
            pcall(function() w:SetRenderOpacity(a) end)
        end
        if tr.sx0 ~= nil or tr.sy0 ~= nil then
            local sx = (tr.sx0 or 1) + ((tr.sx1 or 1) - (tr.sx0 or 1)) * e
            local sy = (tr.sy0 or 1) + ((tr.sy1 or 1) - (tr.sy0 or 1)) * e
            pcall(function() w:SetRenderScale({ X = sx, Y = sy }) end)
        end
        if tr.pulse then
            -- Smooth up-and-settle tactile bounce (1.0 -> 1.0 + amp -> 1.0)
            local s = 1 + tr.pulse * math.sin(math.pi * clamp01(p))
            pcall(function() w:SetRenderScale({ X = s, Y = s }) end)
        end
        return true
    end

    --- Entrance choreography for a newly pushed screen.
    function self.animateEnter(screen, kind)
        if not valid(screen) then return end
        -- Never drop widgets to opacity 0 unless the frame pump is confirmed armed.
        if not self.ensureFrameHook() then return end
        local t = now()
        local okH, header = pcall(function() return screen.Header end)
        if okH and valid(header) then
            setTrack(header, "enter", {
                at = t, dur = 0.22,
                tx0 = -24, tx1 = 0, ty0 = 0, ty1 = 0,
                a0 = 0, a1 = 1,
            })
            applyPose(tracks[trackKey(header, "enter")], 0)
        end
        local okR, ruleW = pcall(function() return screen.HeaderRuleWidth end)
        if okR and valid(ruleW) then
            pcall(function() ruleW:SetRenderTransformPivot({ X = 0.0, Y = 0.5 }) end)
            setTrack(ruleW, "rule", {
                at = t + 0.03, dur = 0.28,
                sx0 = 0.12, sx1 = 1.0, sy0 = 1.0, sy1 = 1.0,
            })
            applyPose(tracks[trackKey(ruleW, "rule")], 0)
        end
        local zones = ENTRANCE_ZONES[kind] or {}
        for idx, name in ipairs(zones) do
            local okW, w = pcall(function() return screen[name] end)
            if okW and valid(w) then
                local tr = {
                    at = t + 0.025 + (idx - 1) * 0.035,
                    dur = M.ENTER_DURATION,
                    tx0 = 0, tx1 = 0, ty0 = 14, ty1 = 0,
                    a0 = 0, a1 = 1,
                }
                setTrack(w, "enter", tr)
                applyPose(tr, 0)
            end
        end
    end

    --- Tactile hover micro-motion: horizontal label glide on left-aligned sidebar
    --- buttons (Lobby / Game Settings), gentle scale lift on centered action buttons
    --- so centered labels stay dead-center between their twin focus pips.
    function self.hoverButton(screen, key, entered, kind)
        if not (valid(screen) and key) then return end
        local sidebar = (kind == nil or kind == "lobby" or kind == "settings")
        if not sidebar then
            local okBtn, btn = pcall(function() return screen[key] end)
            if not (okBtn and valid(btn)) then return end
            local t = now()
            pcall(function() btn:SetRenderTransformPivot({ X = 0.5, Y = 0.5 }) end)
            local k = trackKey(btn, "hover_scale")
            local existing = tracks[k]
            local curS = 1.0
            if existing then
                local p = clamp01((t - existing.at) / existing.dur)
                curS = existing.sx0 + (existing.sx1 - existing.sx0) * easeOutCubic(p)
            else
                curS = entered and 1.0 or 1.022
            end
            setTrack(btn, "hover_scale", {
                at = t, dur = M.HOVER_DURATION,
                sx0 = curS, sx1 = entered and 1.022 or 1.0,
                sy0 = curS, sy1 = entered and 1.022 or 1.0,
            })
            return
        end
        local okL, target = pcall(function() return screen[key .. "Label"] end)
        if not (okL and valid(target)) then return end
        local t = now()
        local k = trackKey(target, "hover")
        local existing = tracks[k]
        local curX = 0
        if existing then
            local p = clamp01((t - existing.at) / existing.dur)
            curX = existing.tx0 + (existing.tx1 - existing.tx0) * easeOutCubic(p)
        else
            curX = entered and 0 or M.HOVER_SHIFT
        end
        setTrack(target, "hover", {
            at = t, dur = M.HOVER_DURATION,
            tx0 = curX, tx1 = entered and M.HOVER_SHIFT or 0,
            ty0 = 0, ty1 = 0,
        })
    end

    --- Subtle settle transition when switching previewed map, mode, or tab.
    function self.previewPop(widget)
        if not valid(widget) then return end
        local t = now()
        local tr = {
            at = t, dur = M.PREVIEW_DURATION,
            tx0 = 0, tx1 = 0, ty0 = 6, ty1 = 0,
            a0 = 0.65, a1 = 1.0,
        }
        setTrack(widget, "preview", tr)
        applyPose(tr, 0)
    end

    --- Quick tactile scale bounce (e.g. casting a map vote).
    function self.pulse(widget, amp)
        if not valid(widget) then return end
        local t = now()
        pcall(function() widget:SetRenderTransformPivot({ X = 0.5, Y = 0.5 }) end)
        setTrack(widget, "pulse", {
            at = t, dur = M.PULSE_DURATION,
            pulse = amp or 0.026,
        })
    end

    --- Continuous 60fps Post-Game vote countdown bar + glowing tip spark.
    function self.trackVote(screen, opts)
        if not (valid(screen) and opts and opts.active) then
            voteState = nil
            return
        end
        local prevTick = voteState and voteState.screen == screen and voteState.lastTick or nil
        voteState = {
            screen = screen,
            left = opts.left or 0,
            leftAt = opts.leftAt or now(),
            total = math.max(1, opts.total or 20),
            held = opts.held == true,
            barWidth = opts.barWidth or 900,
            lastTick = prevTick,
        }
        self.ensureFrameHook()
    end

    --- Adopt a newly opened/activated screen: fonts + open sound + entrance motion.
    function self.adopt(screen, classPath)
        if not valid(screen) then return end
        local kind = M.screenKind(classPath)
        local okA, addr = pcall(function() return screen:GetAddress() end)
        local key = okA and addr or screen
        if not adopted[key] then
            adopted[key] = true
            self.applyFonts(screen, kind)
        end
        local played = self.sound("Open")
        self.animateEnter(screen, kind)
        if not loggedInit then
            loggedInit = true
            log(string.format("UI polish: kind=%s oxanium=%s normative=%s sfx=%s",
                tostring(kind), tostring(fontCache.Oxanium and true or false),
                tostring(fontCache.NormativePro and true or false), tostring(played)))
        end
    end

    --- Handle audio & micro-motion for any MJ_Event. Returns true if the event
    --- was a pure polish event (`btn_hover:` / `btn_unhover:`) that callers
    --- should not forward to gameplay logic.
    function self.onEvent(screen, event, kind)
        if type(event) ~= "string" then return false end
        local hoverKey = event:match("^btn_hover:(.+)$")
        if hoverKey then
            self.sound("Hover")
            self.hoverButton(screen, hoverKey, true, kind)
            return true
        end
        local unhoverKey = event:match("^btn_unhover:(.+)$")
        if unhoverKey then
            self.hoverButton(screen, unhoverKey, false, kind)
            return true
        end

        local cue = M.cueForEvent(event)
        if cue then self.sound(cue) end

        if valid(screen) then
            if event:find("^vote:(%d+)$") then
                local idx = event:match("^vote:(%d+)$")
                local okV, tile = pcall(function() return screen["VoteRow" .. idx] end)
                if okV and valid(tile) then self.pulse(tile, 0.025) end
            elseif event:find("^tab:%d+$") then
                local okP, pages = pcall(function() return screen.Pages end)
                if okP and valid(pages) then self.previewPop(pages) end
            elseif kind == "gametype" and (event:find("^mode:%d+$") or event:find("^hover:%d+$") or event:find("^variant:%d+$")) then
                local okH, hero = pcall(function() return screen.ModeHero end)
                if okH and valid(hero) then self.previewPop(hero) end
            elseif kind == "mapselect" and (event:find("^map:%d+$") or event:find("^hover:%d+$")) then
                local okD, img = pcall(function() return screen.MapImage end)
                if okD and valid(img) then self.previewPop(img) end
            end
        end
        return false
    end

    --- Advance all active UI motion tracks at timestamp `t`. Zero work at rest.
    function self.frame(t)
        t = t or now()
        for k, tr in pairs(tracks) do
            if not valid(tr.widget) then
                tracks[k] = nil
            elseif t >= tr.at then
                local p = clamp01((t - tr.at) / math.max(0.001, tr.dur))
                local alive = applyPose(tr, p)
                if not alive or p >= 1 then
                    tracks[k] = nil
                end
            end
        end

        local vs = voteState
        if vs then
            if not valid(vs.screen) then
                voteState = nil
            else
                local left = vs.left
                if not vs.held then left = math.max(0, left - (t - vs.leftAt)) end
                local frac = clamp01(left / vs.total)
                local width = math.floor(vs.barWidth * frac + 0.5)
                pcall(function() vs.screen.VoteBarFillSize:SetWidthOverride(width) end)
                local okSp, spark = pcall(function() return vs.screen.VoteBarSpark end)
                if okSp and valid(spark) then
                    local shown = not vs.held and width > 6
                    pcall(function()
                        spark:SetVisibility(shown and 3 or 1)
                        if shown then
                            spark:SetRenderTranslation({ X = width - 48, Y = 0 })
                            local late = left <= 5.0
                            local breath = late and (0.75 + 0.25 * math.sin(t * 14.0)) or 0.92
                            spark:SetRenderOpacity(breath)
                        end
                    end)
                end
                local sec = math.ceil(left)
                if not vs.held and sec >= 1 and sec <= 5 and sec ~= vs.lastTick then
                    vs.lastTick = sec
                    self.sound("Tick", 0.96 + (6 - sec) * 0.03)
                end
                if left <= 0 and not vs.held then
                    voteState = nil
                end
            end
        end
    end

    function self.busy()
        return next(tracks) ~= nil or voteState ~= nil
    end

    local function settleAllTracks()
        for k, tr in pairs(tracks) do
            pcall(applyPose, tr, 1)
            tracks[k] = nil
        end
        voteState = nil
    end

    local function stepPump()
        pump.scheduled = false
        if not self.busy() then return end
        local okF, err = pcall(self.frame, now())
        if not okF then
            pump.errors = pump.errors + 1
            if pump.errors >= 10 then
                log("UI motion paused after repeated errors: " .. tostring(err))
                settleAllTracks()
                return
            end
        else
            pump.errors = 0
        end
        if self.busy() then
            self.ensureFrameHook()
        end
    end

    --- Arm the self-pausing game-thread animation pump (~60fps while tracks or
    --- vote countdown are active, 0.00ms when idle). Works identically on the
    --- Frontend (where BP_MeteoritePlayerController_C does not exist) and in-game.
    function self.ensureFrameHook()
        if deps.noFrameHook then return true end
        if pump.scheduled then return true end
        local sched = deps.schedule or ExecuteInGameThreadWithDelay
        if type(sched) ~= "function" then return false end
        pump.scheduled = true
        local ok = pcall(sched, 16, stepPump)
        if not ok then
            pump.scheduled = false
            return false
        end
        return true
    end

    return self
end

return M

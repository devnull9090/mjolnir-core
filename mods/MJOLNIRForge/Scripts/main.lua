-- MJOLNIR Forge: Halo Reach's Forge, still inside the simulation, driven from
-- the keyboard (docs/re/forge_engine.md).
--
-- A FORGE game (MJOLNIRLobby's game type of that name) starts the map under
-- the simulation's sandbox engine. There, each player can turn into the
-- Monitor, fly, and grab, move, duplicate and delete the map's objects: the
-- engine does all of it, through the requests a Reach Forge session sent.
-- Nothing in this game binds the controls that send them, so this mod does:
--
--   * native\mjolnir_forge.dll (native/forge) hooks a routine the sandbox
--     engine runs every tick and turns each command below into the engine's
--     own request, on the simulation's thread;
--   * this script binds the keys, and shows what the editor is doing in a
--     small panel while a Forge game runs.
--
-- Keys (defaults; keys.txt next to this mod overrides them, one
-- `action=KEY` per line, KEY a UE4SS Key name such as B or PAGE_UP):
--
--   B          toggle: the Monitor, and back to your Spartan
--   V          grab: pick up what the cursor is on, or drop what you hold
--   N          duplicate: copy the target at the cursor (needs a palette entry)
--   Delete     delete: the target (what you hold, else what you aim at)
--   Page Down / Page Up   nearer / farther: pull a held object in, or push it out
--   Insert     place: a new object from the palette, at the cursor, held
--   Left / Right   the palette's previous / next category
--   Up / Down      the previous / next object in the category
--
-- The Monitor moves with the game's own controls. A key typed into match
-- chat is ignored here, and the DLL drops a command the simulation did not
-- act on within 0.75 s (the pause menu stops it ticking).

local function modDirectory()
    local source = debug.getinfo(1, "S").source or ""
    local root = source:gsub("^@", ""):gsub("/", "\\")
    for _ = 1, 2 do
        root = root:match("^(.*)\\[^\\]*$") or root
    end
    return root .. "\\"
end

local MOD = modDirectory()
local DLL = MOD .. "native\\mjolnir_forge.dll"
local STATE = MOD .. "native\\forge_state.txt"
local PALETTE = MOD .. "native\\forge_palette.txt"
local STATUS = MOD .. "native\\status.txt"
local KEYS_FILE = MOD .. "keys.txt"

local POLL_MS = 100

-- Keys the Blam keyboard preset leaves free (read in game through
-- BlamInputMapper:GetKeyForAction, 2026-10-24): G and C throw grenades, Z
-- and X zoom, E, Q, F and R are taken too.
local DEFAULT_KEYS = {
    toggle = "B",
    grab = "V",
    duplicate = "N",
    delete = "DEL",
    nearer = "PAGE_DOWN",
    farther = "PAGE_UP",
    place = "INS",
    prev_category = "LEFT_ARROW",
    next_category = "RIGHT_ARROW",
    prev_item = "UP_ARROW",
    next_item = "DOWN_ARROW",
}

local LABELS = {
    toggle = "Monitor",
    grab = "grab / drop",
    duplicate = "duplicate",
    delete = "delete",
    nearer = "nearer",
    farther = "farther",
    place = "place",
    prev_category = "category",
    next_category = "category",
    prev_item = "object",
    next_item = "object",
}

local ORDER = { "toggle", "grab", "duplicate", "delete", "nearer", "farther", "place",
    "prev_category", "next_category", "prev_item", "next_item" }

local function log(text)
    print("[MJOLNIR Forge] " .. tostring(text) .. "\n")
end

local function readFile(path)
    local f = io.open(path, "rb")
    if not f then return nil end
    local text = f:read("a")
    f:close()
    return text
end

--------------------------------------------------------------------------------
-- The native half
--------------------------------------------------------------------------------

local native = {}

local function loadNative()
    if native.pump then return true end
    if not (package and package.loadlib) then
        log("this Lua has no package.loadlib; the native half cannot load")
        return false
    end
    local loaded = {}
    local names = { "open", "pump" }
    for _, action in ipairs(ORDER) do names[#names + 1] = action end
    for _, name in ipairs(names) do
        local f, err = package.loadlib(DLL, "mjolnir_forge_" .. name)
        if not f then
            log("cannot load " .. DLL .. ": " .. tostring(err))
            return false
        end
        loaded[name] = f
    end
    native = loaded
    return true
end

--------------------------------------------------------------------------------
-- Keys
--------------------------------------------------------------------------------

local function keyNames()
    local keys = {}
    for action, name in pairs(DEFAULT_KEYS) do keys[action] = name end
    for line in (readFile(KEYS_FILE) or ""):gmatch("[^\r\n]+") do
        local action, name = line:match("^%s*([%w_]+)%s*=%s*([%w_]+)%s*$")
        if action and DEFAULT_KEYS[action] then keys[action] = string.upper(name) end
    end
    return keys
end

-- MJOLNIRHud's chat box: a key typed there is not a Forge command.
local chat = { widget = nil, nextFind = 0 }

local function typingInChat()
    local w = chat.widget
    if not (w and w:IsValid()) then
        if os.clock() < chat.nextFind then return false end
        chat.nextFind = os.clock() + 2
        w = FindFirstOf("WBP_MJOLNIRChat_C")
        chat.widget = (w and w:IsValid()) and w or nil
        if not chat.widget then return false end
    end
    local ok, focused = pcall(function() return w.ChatInput:HasKeyboardFocus() end)
    return ok and focused == true
end

-- A bind can fire twice for one press.
local lastPress = {}

local function bind(action, keyName)
    local key = Key and Key[keyName]
    if not key then
        log("no UE4SS key named " .. tostring(keyName) .. " for " .. action)
        return false
    end
    local ok = pcall(RegisterKeyBind, key, {}, function()
        local now = os.clock()
        if lastPress[action] and now - lastPress[action] < 0.2 then return end
        lastPress[action] = now
        if typingInChat() then return end
        if native[action] then pcall(native[action]) end
    end)
    if not ok then log("could not bind " .. keyName .. " to " .. action) end
    return ok
end

--------------------------------------------------------------------------------
-- The panel: a UMG text block made from Lua (the one route to the screen in
-- this Shipping build), hidden, never removed (removing one hung the game).
--------------------------------------------------------------------------------

local PANEL_X, PANEL_Y = 40, 360
local PANEL_SCALE = 1.2
local VISIBLE_NO_HIT_TEST = 3
local COLLAPSED = 1

local panel = { widget = nil, text = nil, shown = nil }

local function panelWidget()
    local w, t = panel.widget, panel.text
    if w and t and w:IsValid() and t:IsValid() then
        if not w:IsInViewport() then
            pcall(function()
                w:AddToViewport(1000)
                w:SetPositionInViewport({ X = PANEL_X, Y = PANEL_Y }, false)
            end)
        end
        if w:IsInViewport() then return w, t end
    end
    w, t = nil, nil
    local built = pcall(function()
        local UEHelpers = require("UEHelpers")
        local pc = UEHelpers.GetPlayerController()
        if not pc or not pc:IsValid() then error("no player controller") end
        local library = StaticFindObject("/Script/UMG.Default__WidgetBlueprintLibrary")
        w = library:Create(pc, StaticFindObject("/Script/UMG.UserWidget"), pc)
        local tree = w.WidgetTree
        t = StaticConstructObject(StaticFindObject("/Script/UMG.TextBlock"), tree, FName("MJOLNIRForgeText"))
        tree.RootWidget = t
        t:SetColorAndOpacity({ SpecifiedColor = { R = 0.55, G = 0.85, B = 1, A = 1 }, ColorUseRule = 0 })
        t:SetShadowOffset({ X = 1.5, Y = 1.5 })
        t:SetShadowColorAndOpacity({ R = 0, G = 0, B = 0, A = 0.9 })
        t:SetRenderTransformPivot({ X = 0, Y = 0 })
        t:SetRenderScale({ X = PANEL_SCALE, Y = PANEL_SCALE })
        w:AddToViewport(1000)
        w:SetPositionInViewport({ X = PANEL_X, Y = PANEL_Y }, false)
    end)
    if not built or not w or not w:IsValid() then return nil end
    panel.widget, panel.text = w, t
    return w, t
end

-- Game thread only.
local function showPanel(text)
    if text == panel.shown then return end
    if not text then
        if panel.widget and panel.widget:IsValid() then
            pcall(function() panel.widget:SetVisibility(COLLAPSED) end)
        end
        panel.shown = nil
        return
    end
    local w, t = panelWidget()
    if not w then return end
    local ok = pcall(function()
        t:SetText(FText(text))
        w:SetVisibility(VISIBLE_NO_HIT_TEST)
    end)
    if ok then panel.shown = text end
end

--------------------------------------------------------------------------------
-- The editor's state, from the DLL
--------------------------------------------------------------------------------

local function parseState(text)
    local s = {}
    for k, v in (text or ""):gmatch("([%w_]+)=([^\r\n]*)") do s[k] = v end
    return s
end

-- forge_palette.txt: one row per palette entry, in the DLL's order.
local function parsePalette(text)
    local rows = {}
    for line in (text or ""):gmatch("[^\r\n]+") do
        local p, e, group, tag, ok = line:match("^(%d+)\t(%d+)\t([^\t]*)\t([^\t]*)\t(%d)$")
        if p then
            rows[#rows + 1] = { palette = tonumber(p), entry = tonumber(e), group = group, tag = tag,
                placeable = ok == "1" }
        end
    end
    return rows
end

-- The selected row of `palette` (rows from parsePalette) for state `s`.
local function selectedRow(s, palette)
    local i = tonumber(s.selected or "")
    return i and palette[i + 1] or nil
end

local function describe(s, keys, palette)
    if s.forge ~= "1" or s.player == "-1" then return nil end
    local hint = {}
    if s.editing == "1" then
        for _, action in ipairs(ORDER) do
            if not action:find("^prev_") and not action:find("^next_") then
                hint[#hint + 1] = string.format("[%s] %s", keys[action], action == "toggle" and "Spartan" or LABELS[action])
            end
        end
    else
        hint[1] = string.format("[%s] %s", keys.toggle, LABELS.toggle)
    end
    local lines = { "FORGE" .. (s.editing == "1" and " - MONITOR" or ""), table.concat(hint, "   ") }
    if s.editing == "1" then
        if s.held ~= "ffffffff" then
            lines[#lines + 1] = string.format("Holding: %s  (%s m)", s.held_tag ~= "" and s.held_tag or "object", s.distance or "?")
        elseif s.cursor ~= "ffffffff" then
            lines[#lines + 1] = "Aiming at: " .. (s.cursor_tag ~= "" and s.cursor_tag or "object")
        else
            lines[#lines + 1] = "Aiming at: nothing"
        end
        local row = selectedRow(s, palette)
        if row then
            lines[#lines + 1] = string.format("Palette: %s%s  [%s/%s] object  [%s/%s] category",
                row.tag, row.placeable and "" or " (cannot place)", keys.prev_item, keys.next_item,
                keys.prev_category, keys.next_category)
        end
    end
    if s.last and s.last ~= "" then lines[#lines + 1] = s.last end
    return table.concat(lines, "\n")
end

--------------------------------------------------------------------------------
-- Start
--------------------------------------------------------------------------------

local keys = keyNames()
local bound = 0
for _, action in ipairs(ORDER) do
    if bind(action, keys[action]) then bound = bound + 1 end
end

-- The HUD (Scripts/hud.lua, WBP_MJOLNIRForge), with the text panel above as
-- its stand-in when the HUD's container is not installed.
local Hud = dofile(MOD .. "Scripts\\hud.lua")
Hud.init({
    log = log,
    pc = function()
        local ok, pc = pcall(function() return require("UEHelpers").GetPlayerController() end)
        return (ok and pc and pc:IsValid()) and pc or nil
    end,
})

-- The map's title, from MJOLNIRLevelLoader's running.txt ("CODE\tforge\tTitle").
local function mapTitle()
    local raw = readFile(MOD .. "..\\MJOLNIRLevelLoader\\running.txt")
    local code, title = (raw or ""):match("^([^\t]*)\t[^\t]*\t([^\r\n]*)")
    if not code then return "" end
    return string.upper(title ~= "" and title or code)
end

-- Game thread only.
local function render(s, title, palette)
    if Hud.render(s, keys, title, palette, selectedRow(s, palette)) then
        showPanel(nil)
    else
        showPanel(describe(s, keys, palette))
    end
end

local lastStatus = nil
local lastState = false
local palette = {}
local paletteVersion = nil
ExecuteInGameThreadWithDelay(5000, function()
    if not loadNative() then return end
    pcall(native.open)
    LoopAsync(POLL_MS, function()
        pcall(native.pump)
        local status = readFile(STATUS)
        if status and status ~= lastStatus then
            lastStatus = status
            log("native: " .. status)
        end
        -- The HUD changes only when the editor's state does; the game
        -- thread hears about it only then.
        local raw = readFile(STATE) or ""
        if raw ~= lastState then
            lastState = raw
            local s = parseState(raw)
            local title = s.forge == "1" and mapTitle() or ""
            if s.palette_version and s.palette_version ~= paletteVersion then
                paletteVersion = s.palette_version
                palette = parsePalette(readFile(PALETTE))
            end
            local rows = palette
            ExecuteInGameThread(function() render(s, title, rows) end)
        end
        return false
    end)
end)

log(string.format("loaded, %d of %d keys bound (toggle %s); FORGE games are started from MULTIPLAYER",
    bound, #ORDER, keys.toggle))

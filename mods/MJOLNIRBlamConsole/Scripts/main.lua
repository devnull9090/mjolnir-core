-- MJOLNIR Blam Console
--
-- Type Blam console commands and HS script at the Unreal console, and get
-- answers back.
--
-- The simulation DLL still carries the classic console: the HS compiler, all
-- 1,695 engine functions, the cheats, `help`, `script_doc`. Nothing on the
-- Unreal side feeds it text, so out of the box every one of them is "Command
-- not recognized". This mod is the missing wire:
--
--   * native/mjolnir_blam_console.dll runs the text through the engine's own
--     compile-and-evaluate on the simulation thread, and reports the result
--     value, or the compile error, back.
--   * This script loads that DLL with package.loadlib, owns the console
--     commands, and prints what comes back.
--
-- Commands:
--   <blam function or global> ...   anything the engine knows, by name:
--                                   `cheat_all_weapons`, `game_speed 0.5`,
--                                   `player_teleport player0 ...`
--   blam <text>                     the same, and the only way to type a
--                                   parenthesised expression: `blam (+ 1 2)`
--   blam !<text>                    run even with no game in progress
--   help [prefix]                   list functions and globals, with signatures
--   blam_status                     is the native half installed, and where
--   blam_overlay on|off             show answers on screen (default on)
--
-- Where answers go: the UE4SS console and log always, and an on-screen
-- panel in the top-left corner while the overlay is on. They cannot go to
-- the Unreal console itself: the answer arrives from the simulation thread
-- a tick later, after Unreal has discarded the command's output device, and
-- the simulation only ticks while the game thread is free, so waiting for
-- it inside the command handler would deadlock. What the handler can still
-- do synchronously it does: `help`, `blam_status`, the stub warnings and an
-- acknowledgement of each command are written to the Unreal console.

local defs
local dllOpen, dllPump
local nativeDir
local lastId = math.floor(os.time() % 100000) * 100
local waiting = nil  -- { id = n, text = s, since = clock }
local POLL_MS = 50
local TIMEOUT_S = 5

--------------------------------------------------------------------------------
-- Paths
--------------------------------------------------------------------------------

--- <ue4ss>\Mods\MJOLNIRBlamConsole\Scripts\main.lua -> <ue4ss>\Mods\MJOLNIRBlamConsole\
local function modDirectory()
    local source = debug.getinfo(1, "S").source or ""
    local path = source:gsub("^@", ""):gsub("/", "\\")
    local root = path
    for _ = 1, 2 do
        root = root:match("^(.*)\\[^\\]*$") or root
    end
    return root .. "\\"
end

local MOD = modDirectory()
nativeDir = MOD .. "native\\"
local DLL = nativeDir .. "mjolnir_blam_console.dll"
local REQUEST = nativeDir .. "request.txt"
local RESPONSE = nativeDir .. "response.txt"
local STATUS = nativeDir .. "status.txt"

local function readFile(path)
    local f = io.open(path, "rb")
    if not f then return nil end
    local text = f:read("a")
    f:close()
    return text
end

local function writeFile(path, text)
    local f = io.open(path, "wb")
    if not f then return false end
    f:write(text)
    f:close()
    return true
end

--------------------------------------------------------------------------------
-- Output
--
-- Three places, because no single one works for everything:
--   * the UE4SS console and log, always;
--   * the Unreal console, for whatever is known while its output device is
--     still alive (see the header);
--   * an on-screen panel: a plain UMG text block created from Lua and added
--     to the viewport. PrintString is a no-op in this Shipping build, the
--     Blueprint HUD never fires its draw event, and none of the Unreal
--     console's scrollback is reflected, so this is the one route to the
--     screen that works, and it uses only engine classes, nothing from the
--     game. The panel is hidden, never removed: removing a widget from the
--     viewport is the one call that has hung the game in testing.
--------------------------------------------------------------------------------

local OVERLAY_SETTING = MOD .. "overlay.txt"   -- "off" turns the panel off
local OVERLAY_KEEP = 10                        -- lines kept on screen
local OVERLAY_BURST = 8                        -- lines one answer may add
local OVERLAY_SECONDS = 15                     -- panel lifetime after the last answer
local OVERLAY_X, OVERLAY_Y = 40, 420           -- top-left, below the objective text, in DPI-scaled units
local OVERLAY_SCALE = 1.3                      -- the default text block is small at 720p

local VISIBLE_NO_HIT_TEST = 3                  -- ESlateVisibility::HitTestInvisible
local COLLAPSED = 1                            -- ESlateVisibility::Collapsed

local overlay = { lines = {}, pending = {}, flushScheduled = false, widget = nil, text = nil, generation = 0 }
local currentAr = nil                          -- the Unreal console's output device, inside a handler

local function overlayEnabled()
    local s = readFile(OVERLAY_SETTING)
    return not (s and s:match("^%s*off"))
end

--- The panel widget, built on first use and rebuilt if the engine dropped it.
--- Game thread only. Returns nil with no player controller (frontend).
local function overlayWidget()
    local w, t = overlay.widget, overlay.text
    if w and t and w:IsValid() and t:IsValid() then
        if not w:IsInViewport() then
            pcall(function()
                w:AddToViewport(1000)
                w:SetPositionInViewport({ X = OVERLAY_X, Y = OVERLAY_Y }, false)
            end)
        end
        if w:IsInViewport() then return w, t end
    end
    w, t = nil, nil
    local ok = pcall(function()
        local UEHelpers = require("UEHelpers")
        local pc = UEHelpers.GetPlayerController()
        if not pc or not pc:IsValid() then error("no player controller") end
        local library = StaticFindObject("/Script/UMG.Default__WidgetBlueprintLibrary")
        local widgetClass = StaticFindObject("/Script/UMG.UserWidget")
        local textClass = StaticFindObject("/Script/UMG.TextBlock")
        w = library:Create(pc, widgetClass, pc)
        local tree = w.WidgetTree
        t = StaticConstructObject(textClass, tree, FName("MJOLNIRBlamConsoleText"))
        tree.RootWidget = t
        t:SetColorAndOpacity({ SpecifiedColor = { R = 1, G = 0.85, B = 0.2, A = 1 }, ColorUseRule = 0 })
        t:SetShadowOffset({ X = 1.5, Y = 1.5 })
        t:SetShadowColorAndOpacity({ R = 0, G = 0, B = 0, A = 0.9 })
        -- Scale about the top-left corner, or the text grows off the left edge.
        t:SetRenderTransformPivot({ X = 0, Y = 0 })
        t:SetRenderScale({ X = OVERLAY_SCALE, Y = OVERLAY_SCALE })
        w:AddToViewport(1000)
        w:SetPositionInViewport({ X = OVERLAY_X, Y = OVERLAY_Y }, false)
    end)
    if not ok or not w or not w:IsValid() then return nil end
    overlay.widget, overlay.text = w, t
    return w, t
end

local function overlayHide()
    if overlay.widget and overlay.widget:IsValid() then
        pcall(function() overlay.widget:SetVisibility(COLLAPSED) end)
    end
    overlay.lines = {}
end

--- Everything said since the last flush goes on screen as one block. Game
--- thread only.
local function overlayFlush()
    overlay.flushScheduled = false
    local burst = overlay.pending
    overlay.pending = {}
    if #burst == 0 or not overlayEnabled() then return end
    local w, t = overlayWidget()
    if not w then return end
    if #burst > OVERLAY_BURST then
        local cut = {}
        for i = 1, OVERLAY_BURST - 1 do cut[i] = burst[i] end
        cut[OVERLAY_BURST] = string.format("  ... %d more lines on the UE4SS console (Ctrl+O)", #burst - (OVERLAY_BURST - 1))
        burst = cut
    end
    for _, line in ipairs(burst) do overlay.lines[#overlay.lines + 1] = line end
    while #overlay.lines > OVERLAY_KEEP do table.remove(overlay.lines, 1) end
    local ok = pcall(function()
        t:SetText(FText(table.concat(overlay.lines, "\n")))
        w:SetVisibility(VISIBLE_NO_HIT_TEST)
    end)
    if not ok then return end
    overlay.generation = overlay.generation + 1
    local generation = overlay.generation
    ExecuteInGameThreadWithDelay(OVERLAY_SECONDS * 1000, function()
        if overlay.generation == generation then overlayHide() end
    end)
end

local function overlayPush(line)
    overlay.pending[#overlay.pending + 1] = line
    if overlay.flushScheduled then return end
    overlay.flushScheduled = true
    ExecuteInGameThread(overlayFlush)
end

--- One line of output, everywhere it can go.
local function say(text)
    print("[Blam] " .. text .. "\n")
    if currentAr then pcall(function() currentAr:Log("[Blam] " .. text) end) end
    overlayPush(text)
end

--- For the mod's own housekeeping: the UE4SS console only.
local function log(text)
    print("[Blam] " .. text .. "\n")
end

--------------------------------------------------------------------------------
-- Definitions
--------------------------------------------------------------------------------

local ok, loaded = pcall(dofile, MOD .. "Scripts\\defs.lua")
if ok and type(loaded) == "table" then
    defs = loaded
else
    defs = { functions = {}, globals = {} }
    say("defs.lua missing or broken (" .. tostring(loaded) .. "); help will be empty")
end

local function signature(name, f)
    if f.text then return "(" .. name .. " " .. f.text .. ")" end
    local parts = {}
    for _, t in ipairs(f.params) do parts[#parts + 1] = "<" .. t .. ">" end
    local s = "(" .. name
    if #parts > 0 then s = s .. " " .. table.concat(parts, " ") end
    s = s .. ")"
    if f.returns ~= "void" and f.returns ~= "passthrough" then
        s = s .. " -> " .. f.returns
    end
    if f.overloads then s = s .. string.format("   (+%d overloads by argument count)", f.overloads - 1) end
    if f.stub then s = s .. "   [compiled out]" end
    return s
end

local function help(prefix)
    prefix = (prefix or ""):lower()
    local names = {}
    for name in pairs(defs.functions) do
        if prefix == "" or name:sub(1, #prefix) == prefix or name:find(prefix, 1, true) then
            names[#names + 1] = name
        end
    end
    table.sort(names)
    local globals = {}
    for name in pairs(defs.globals) do
        if prefix == "" or name:sub(1, #prefix) == prefix or name:find(prefix, 1, true) then
            globals[#globals + 1] = name
        end
    end
    table.sort(globals)

    if prefix == "" then
        local nf, ng, stubs, dead = 0, 0, 0, 0
        for _, f in pairs(defs.functions) do nf = nf + 1; if f.stub then stubs = stubs + 1 end end
        for _, g in pairs(defs.globals) do ng = ng + 1; if g.dead then dead = dead + 1 end end
        say(string.format("%d functions (%d of them compiled out of this build) and %d globals (%d without storage).", nf, stubs, ng, dead))
        say("`help <prefix>` lists matches: `help player_`, `help object_create`, `help ai_place`.")
        say("Type a name with its arguments (`player_teleport player0 ...`), or `blam (expr)` for script.")
        return
    end
    if #names == 0 and #globals == 0 then
        say("nothing matches '" .. prefix .. "'")
        return
    end
    local shown = 0
    for _, name in ipairs(names) do
        if shown >= 60 then
            say(string.format("... and %d more; narrow the prefix", #names - shown))
            break
        end
        say("  " .. signature(name, defs.functions[name]))
        shown = shown + 1
    end
    for _, name in ipairs(globals) do
        local g = defs.globals[name]
        say(string.format("  %s  (global %s)%s", name, g.type, g.dead and "   [no storage in this build]" or ""))
    end
end

--------------------------------------------------------------------------------
-- Native half
--------------------------------------------------------------------------------

local function loadNative()
    if dllOpen and dllPump then return true end
    if not package or not package.loadlib then
        say("this Lua has no package.loadlib; the native half cannot load")
        return false
    end
    local f, err = package.loadlib(DLL, "mjolnir_blam_open")
    if not f then
        say("cannot load " .. DLL .. ": " .. tostring(err))
        say("build it with native\\blam_console\\build.ps1 and reinstall the mod")
        return false
    end
    dllOpen = f
    dllPump = package.loadlib(DLL, "mjolnir_blam_pump")
    return dllPump ~= nil
end

local function status()
    return (readFile(STATUS) or "no status file"):gsub("%s+$", "")
end

--- Install the hook. Safe to call repeatedly; the DLL refuses to install twice.
local function ensureInstalled()
    if not loadNative() then return false end
    dllOpen()
    local s = status()
    if s:sub(1, 2) == "ok" then return true end
    say(s)
    return false
end

--------------------------------------------------------------------------------
-- Sending and receiving
--------------------------------------------------------------------------------

local function checkResponse()
    if not waiting then return end
    dllPump()
    local text = readFile(RESPONSE)
    if text then
        local id, body = text:match("^(%-?%d+)\n(.*)$")
        if tonumber(id) == waiting.id then
            say(waiting.text)
            for line in (body or ""):gmatch("[^\n]+") do say("  " .. line) end
            waiting = nil
            return
        end
    end
    if os.clock() - waiting.since > TIMEOUT_S then
        say(waiting.text .. "  -- no answer after " .. TIMEOUT_S .. "s. Is the simulation ticking? (blam_status)")
        waiting = nil
    end
end

local function send(text, force)
    text = (text or ""):gsub("^%s+", ""):gsub("%s+$", "")
    if text == "" then return end
    if text:sub(1, 1) == "!" then
        force = true
        text = text:sub(2):gsub("^%s+", "")
    end
    if not ensureInstalled() then return end
    local head = text:match("^%(?%s*([^%s()]+)")
    if head then
        local f, g = defs.functions[head:lower()], defs.globals[head:lower()]
        if f and f.stub then
            say(head .. " is compiled out of this build of the game: the engine will accept it and do nothing")
        elseif g and g.dead and not f then
            say(head .. " has no storage in this build of the game: it reads as zero and ignores writes")
        end
    end
    if waiting then
        say("still waiting on: " .. waiting.text)
        return
    end
    lastId = lastId + 1
    if not writeFile(REQUEST, string.format("%d %d\n%s\n", lastId, force and 1 or 0, text)) then
        say("cannot write " .. REQUEST)
        return
    end
    if currentAr then
        local where = overlayEnabled() and "on screen and on the UE4SS console" or "on the UE4SS console (Ctrl+O)"
        pcall(function() currentAr:Log("[Blam] " .. text .. "  -> sent to the simulation; the answer follows " .. where) end)
    end
    waiting = { id = lastId, text = text, since = os.clock() }
    dllPump()
    LoopAsync(POLL_MS, function()
        checkResponse()
        return waiting == nil
    end)
end

--------------------------------------------------------------------------------
-- Console commands
--------------------------------------------------------------------------------

local function rest(full)
    return (full:match("^%S+%s*(.*)$") or "")
end

--- Runs a handler with the Unreal console's output device available to
--- `say`, for as long as it is: the handler's own duration.
local function withConsole(ar, body)
    currentAr = ar
    local ok, err = pcall(body)
    currentAr = nil
    if not ok then log("error: " .. tostring(err)) end
    return true
end

RegisterConsoleCommandHandler("blam", function(full, _, ar)
    return withConsole(ar, function() send(rest(full)) end)
end)

RegisterConsoleCommandHandler("help", function(full, _, ar)
    return withConsole(ar, function() help(rest(full)) end)
end)

RegisterConsoleCommandHandler("blam_status", function(_, _, ar)
    return withConsole(ar, function()
        loadNative()
        if dllOpen then dllOpen() end
        say("dll " .. DLL)
        say(status())
    end)
end)

RegisterConsoleCommandHandler("blam_overlay", function(full, _, ar)
    return withConsole(ar, function()
        local arg = rest(full):lower():gsub("%s+$", "")
        if arg == "on" or arg == "off" then
            writeFile(OVERLAY_SETTING, arg .. "\n")
            if arg == "off" then ExecuteInGameThread(overlayHide) end
        elseif arg ~= "" then
            say("usage: blam_overlay on|off")
        end
        say("on-screen overlay is " .. (overlayEnabled() and "on" or "off"))
    end)
end)

--- Anything the engine knows by name goes to it, so `cheat_all_weapons` works
--- without a prefix. This UE4SS has no catch-all console handler, so every
--- name gets its own; Unreal never sees these, which is why the few Blam
--- names that shadow an Unreal command are left alone, as is `help`, which
--- this mod answers itself.
local SHADOWED = { open = true, exit = true, quit = true, stat = true, pause = true, help = true, blam = true }
local registered = 0
local function forward(full, _, ar)
    return withConsole(ar, function() send(full) end)
end
for name in pairs(defs.functions) do
    if name:match("^[%a_][%w_]*$") and not SHADOWED[name] then
        RegisterConsoleCommandHandler(name, forward)
        registered = registered + 1
    end
end
for name in pairs(defs.globals) do
    if name:match("^[%a_][%w_]*$") and not SHADOWED[name] and not defs.functions[name] then
        RegisterConsoleCommandHandler(name, forward)
        registered = registered + 1
    end
end

-- The simulation DLL is loaded some time after UE4SS starts, so install lazily
-- on the first command, and once here in case it is already there.
ExecuteInGameThreadWithDelay(8000, function()
    if loadNative() then
        dllOpen()
        log(status())
    end
end)

log(string.format("loaded, %d names registered. `help` lists them; `blam_status` says whether the native half is installed.", registered))

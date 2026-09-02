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
--
-- Output goes to the UE4SS console and log, not the Unreal console: the
-- answer arrives from the simulation thread a tick later, after Unreal's
-- output device for the command is gone.

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

local function say(text)
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

RegisterConsoleCommandHandler("blam", function(full)
    send(rest(full))
    return true
end)

RegisterConsoleCommandHandler("help", function(full)
    help(rest(full))
    return true
end)

RegisterConsoleCommandHandler("blam_status", function()
    loadNative()
    if dllOpen then dllOpen() end
    say("dll " .. DLL)
    say(status())
    return true
end)

--- Anything the engine knows by name goes to it, so `cheat_all_weapons` works
--- without a prefix. This UE4SS has no catch-all console handler, so every
--- name gets its own; Unreal never sees these, which is why the few Blam
--- names that shadow an Unreal command are left alone, as is `help`, which
--- this mod answers itself.
local SHADOWED = { open = true, exit = true, quit = true, stat = true, pause = true, help = true, blam = true }
local registered = 0
local function forward(full)
    send(full)
    return true
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
        say(status())
    end
end)

say(string.format("loaded, %d names registered. `help` lists them; `blam_status` says whether the native half is installed.", registered))

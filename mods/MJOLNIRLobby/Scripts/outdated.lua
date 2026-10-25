-- MJOLNIR Lobby: "your game is out of date" at the main menu
-- (docs/update_check.md).
--
-- Each time the game reaches its main menu (at start, and back from a match)
-- it asks the MJOLNIR launcher what is out of date: the launcher is run
-- without a window by the native half (`--check-updates`), checks the code
-- mods against the signed set, the runtime and every installed hub mod (the
-- CE runtime pack, maps) against the hub, looks for mods MJOLNIR did not
-- install, and writes native\update_check.json:
--
--   { "checked_at": unix seconds,
--     "items": [ { "kind": "core|code|content", "id", "name", "installed",
--                  "latest", "release_id", "repair" } ],
--     "unreachable": [ "the hub: ..." ],
--     "unsupported": [ { "kind": "pak|ue4ss", "name", "files", "bytes" } ] }
--
-- Anything found shows a screen over the main menu. UPDATE AND RESTART opens
-- the launcher with mjolnir://update (it waits for this game to close,
-- updates, and starts it again) and quits the game. The check reaches the
-- network only through the launcher, which already holds the signed sets'
-- keys: this game gains no client of its own.

local Outdated = {}

local RECHECK_SECONDS = 600   -- a result this old is asked for again
local ARRIVAL_GAP = 10        -- seconds without a frontend poll: a new visit
local CHECK_TIMEOUT = 180     -- no answer in this long: give up until next visit
local QUIT_DELAY_MS = 2500    -- time for the launcher to start before the game goes
local SHOWN_ITEMS = 6

local Json, UI, log, nativeDir
local state = {
    lastTick = nil,      -- os.time() of the previous tick
    asked = nil,         -- os.time() a check was started, while it runs
    result = nil,        -- the last answer, with `got` (os.time() it arrived)
    shownVisit = false,  -- shown already on this visit to the main menu
    screen = nil,        -- the screen record while it is up
}

local function readFile(path)
    local f = io.open(path, "rb")
    if not f then return nil end
    local data = f:read("*a")
    f:close()
    return data
end

local function writeFile(path, text)
    local f = io.open(path, "wb")
    if not f then return false end
    f:write(text)
    f:close()
    return true
end

--- Ask the launcher: `verb` is "check" or "update". true, or false and why.
local function askLauncher(verb)
    if not writeFile(nativeDir .. "launcher_request.txt", verb .. "\n") then
        return false, "cannot write the request"
    end
    local dll = nativeDir .. "mjolnir_lobby.dll"
    local fn = package and package.loadlib and package.loadlib(dll, "mjolnir_launcher")
    if not fn then return false, "the native half has no mjolnir_launcher (update MJOLNIR Lobby)" end
    local ok, err = pcall(fn)
    if not ok then return false, tostring(err) end
    local reply = readFile(nativeDir .. "launcher_reply.txt") or ""
    if reply:match("^ok") then return true end
    return false, (reply:match("^error (.-)%s*$") or "no answer from the native half")
end

--- What a result calls for: { items, unsupported } of what to show, or nil
--- when there is nothing.
function Outdated.findings(result)
    if type(result) ~= "table" then return nil end
    local items = type(result.items) == "table" and result.items or {}
    local unsupported = type(result.unsupported) == "table" and result.unsupported or {}
    if #items == 0 and #unsupported == 0 then return nil end
    return { items = items, unsupported = unsupported }
end

local KIND_NOTE = { core = "MJOLNIR core", code = "mod", content = "hub" }

--- One line for an out-of-date item.
function Outdated.itemLine(o)
    local name = tostring(o.name or o.id or "?")
    if o.repair then return name .. "   (FILES MISSING)" end
    local note = KIND_NOTE[o.kind]
    local label = note and note ~= name and (name .. " (" .. note .. ")") or name
    local from = type(o.installed) == "string" and o.installed or "?"
    return string.format("%s   %s > %s", label, from, tostring(o.latest or "?"))
end

--- The screen's title and description for a result's findings.
function Outdated.describe(found)
    local lines = {}
    local n = #found.items
    if n > 0 then
        lines[#lines + 1] = "Your MJOLNIR install is out of date. Multiplayer games need everyone on the same versions."
        lines[#lines + 1] = ""
        for i = 1, math.min(n, SHOWN_ITEMS) do lines[#lines + 1] = Outdated.itemLine(found.items[i]) end
        if n > SHOWN_ITEMS then lines[#lines + 1] = string.format("and %d more", n - SHOWN_ITEMS) end
    end
    local u = #found.unsupported
    if u > 0 then
        if #lines > 0 then lines[#lines + 1] = "" end
        lines[#lines + 1] = string.format(
            "%d mod%s MJOLNIR did not install %s in your game folder. Mods from elsewhere can stop a multiplayer game from starting, or desync it for everyone. The launcher can move them aside while you play.",
            u, u == 1 and "" or "s", u == 1 and "is" or "are")
    end
    lines[#lines + 1] = ""
    lines[#lines + 1] = (n > 0 and "UPDATE AND RESTART" or "OPEN LAUNCHER AND RESTART")
        .. " closes the game, lets the MJOLNIR launcher fix it, and starts it again."
    local title = n > 0 and "UPDATE AVAILABLE" or "UNSUPPORTED MODS"
    return title, table.concat(lines, "\n")
end

--- Whether this tick starts a new visit to the frontend: the poll that calls
--- it runs every 1.5 s there and not at all in a match.
function Outdated.arrived(now, lastTick)
    return lastTick == nil or now - lastTick > ARRIVAL_GAP
end

local function quitGame()
    local pc = UI.playerController()
    local world = pc and pc:GetWorld()
    local ksl = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
    local ok = pcall(function() ksl:QuitGame(world, pc, 0, false) end)
    if not ok then pcall(function() ksl:ExecuteConsoleCommand(world, "quit", pc) end) end
end

local function show(found)
    local title, text = Outdated.describe(found)
    local updating = false
    local rec
    rec = UI.push({
        title = title,
        subtitle = "MJOLNIR",
        description = text,
        buttons = {
            {
                label = #found.items > 0 and "UPDATE AND RESTART" or "OPEN LAUNCHER AND RESTART",
                description = text,
                onClick = function()
                    if updating then return end
                    local ok, why = askLauncher("update")
                    if not ok then
                        log("update: " .. tostring(why))
                        if rec then UI.describe(rec, "Could not open the MJOLNIR launcher: " .. tostring(why)
                            .. "\n\nOpen it yourself and update there.") end
                        return
                    end
                    updating = true
                    log("update: the launcher is open; quitting so it can update")
                    if rec then UI.describe(rec, "Opening the MJOLNIR launcher. The game closes in a moment, and starts again once the update is done.") end
                    ExecuteInGameThreadWithDelay(QUIT_DELAY_MS, quitGame)
                end,
            },
            {
                label = "NOT NOW",
                description = text,
                onClick = function()
                    if rec then UI.pop(rec) end
                    state.screen = nil
                end,
            },
        },
    })
    state.screen = rec
    log(string.format("out of date: %d update(s), %d unsupported mod(s)", #found.items, #found.unsupported))
end

--- The main menu is the screen on top: nothing of ours, the post-game or a
--- join is over it.
local function menuOnTop(menu)
    if not UI.valid(menu) then return false end
    local ok, active = pcall(function() return menu:IsActivated() end)
    if ok then return active == true end
    return true
end

--- From the main menu's poll while signed in and in the frontend; `menu` is
--- the main menu widget, or nil when it is not up.
function Outdated.tick(menu)
    local now = os.time()
    if Outdated.arrived(now, state.lastTick) then
        state.shownVisit = false
        local stale = not state.result or now - state.result.got > RECHECK_SECONDS
        if stale and not state.asked then
            local ok, why = askLauncher("check")
            if ok then
                state.asked = now
            else
                log("update check: " .. tostring(why))
            end
        end
    end
    state.lastTick = now

    if state.asked then
        local raw = readFile(nativeDir .. "update_check.json")
        if raw then
            state.asked = nil
            local ok, result = pcall(Json.decode, raw)
            if ok and type(result) == "table" then
                result.got = now
                state.result = result
                local found = Outdated.findings(result)
                log(found and string.format("update check: %d update(s), %d unsupported mod(s)",
                    #found.items, #found.unsupported) or "update check: up to date")
                for _, u in ipairs(type(result.unreachable) == "table" and result.unreachable or {}) do
                    log("update check: could not check " .. tostring(u))
                end
            else
                log("update check: unreadable answer")
            end
        elseif now - state.asked > CHECK_TIMEOUT then
            state.asked = nil
            log("update check: no answer from the launcher")
        end
    end

    if state.shownVisit or not state.result or (state.screen and UI.valid(state.screen.screen)) then return end
    local found = Outdated.findings(state.result)
    if found and menuOnTop(menu) then
        state.shownVisit = true
        show(found)
    end
end

--- deps: { json, ui, log, nativeDir }.
function Outdated.init(deps)
    Json, UI, log, nativeDir = deps.json, deps.ui, deps.log, deps.nativeDir
end

return Outdated

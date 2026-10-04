-- MJOLNIR Lobby: match history uploads (docs/match_stats.md).
--
-- MJOLNIRHud records each public match its host runs, and a participant's
-- claim of its seat, as files beside itself, and names each one in
-- match_outbox.txt once it is ready. This sends them to the hub, one at a
-- time, through the same native hub call public games use (games.lua), so
-- the launcher's key signs them and nothing here sees it:
--
--   match <id>   match_<id>.json  -> POST /matches         (the host)
--   claim <id>   claim_<id>.json  -> POST /matches/claims  (a participant)
--
-- A file goes once the hub has it, or once the hub says it never will (a
-- bad or conflicting report). Anything else, no connection or an old
-- sign-in, keeps it for a later try; a sign-in fixed later still sends it.

local Matches = {}

local INTERVAL = 15           -- seconds between looks at the outbox
local RETRY = 60              -- after no answer, or the hub busy
local RETRY_SIGN_IN = 600     -- after 401/403: until the launcher signs in again
-- The hub has taken it, or will never take it. Not 404: a hub without
-- these routes yet answers that, and the record should wait for it.
local DONE = { [200] = true, [201] = true, [400] = true, [409] = true, [413] = true, [422] = true }

local KINDS = {
    match = { file = "match_", path = "/matches" },
    claim = { file = "claim_", path = "/matches/claims" },
}

local hudDir, Games, log
local busy = false
local nextLook = 0
local waitUntil = {}          -- "<kind> <id>" -> os.time() before which it waits
local lastProblem = nil

local function readFile(path)
    local f = io.open(path, "rb")
    if not f then return nil end
    local data = f:read("*a")
    f:close()
    return data
end

local function fileOf(entry)
    return hudDir .. KINDS[entry.kind].file .. entry.id .. ".json"
end

local function exists(path)
    local f = io.open(path, "rb")
    if not f then return false end
    f:close()
    return true
end

--- The outbox's entries whose files are still there, in order, once each;
--- the outbox is rewritten to just those when any have gone.
local function pending()
    local text = readFile(hudDir .. "match_outbox.txt")
    if not text then return {} end
    local entries, seen, stale = {}, {}, false
    for kind, id in text:gmatch("(%a+) (%x+)") do
        local key = kind .. " " .. id
        if KINDS[kind] and not seen[key] then
            seen[key] = true
            local entry = { kind = kind, id = id, key = key }
            if exists(fileOf(entry)) then entries[#entries + 1] = entry else stale = true end
        else
            stale = true
        end
    end
    if stale then
        -- MJOLNIRHud only appends, and both mods run on the game thread, so
        -- nothing lands between this read and this write.
        local lines = {}
        for _, e in ipairs(entries) do lines[#lines + 1] = e.key .. "\n" end
        local f = io.open(hudDir .. "match_outbox.txt", "wb")
        if f then
            f:write(table.concat(lines))
            f:close()
        end
    end
    return entries
end

local function problem(text)
    if text ~= lastProblem then log("matches: " .. text) end
    lastProblem = text
end

local function send(entry)
    local body = readFile(fileOf(entry))
    if not body or body == "" then
        os.remove(fileOf(entry))
        return
    end
    busy = true
    Games.call("POST", KINDS[entry.kind].path, body, function(status, data)
        busy = false
        if DONE[status] then
            os.remove(fileOf(entry))
            waitUntil[entry.key] = nil
            if status == 200 or status == 201 then
                log(string.format("matches: %s %s sent%s", entry.kind, entry.id,
                    data and data.linked and " (seat linked)" or ""))
            else
                log(string.format("matches: the hub refused %s %s (%d: %s); dropped", entry.kind, entry.id,
                    status, tostring(data and (data.message or data.error) or "?")))
            end
            lastProblem = nil
            nextLook = os.time() + 2
        elseif status == 401 or status == 403 then
            waitUntil[entry.key] = os.time() + RETRY_SIGN_IN
            problem("not sent: " .. Games.explain(status, data))
        elseif status == 404 then
            waitUntil[entry.key] = os.time() + RETRY_SIGN_IN
            problem("not sent yet: the hub does not take match reports yet")
        else
            waitUntil[entry.key] = os.time() + (status == 429 and RETRY * 5 or RETRY)
            problem("not sent yet: " .. Games.explain(status, data))
        end
    end)
end

local function tick()
    if busy or os.time() < nextLook then return end
    nextLook = os.time() + INTERVAL
    for _, entry in ipairs(pending()) do
        if os.time() >= (waitUntil[entry.key] or 0) then
            send(entry)
            return
        end
    end
end

--- deps: { modDir, games, log }.
function Matches.init(deps)
    hudDir = (deps.modDir:match("^(.*)\\[^\\]*$") or deps.modDir) .. "\\MJOLNIRHud\\"
    Games, log = deps.games, deps.log
    nextLook = os.time() + 10
    local function loop()
        local ok, err = pcall(tick)
        if not ok then
            busy = false
            log("matches: " .. tostring(err))
        end
        ExecuteInGameThreadWithDelay(1000, loop)
    end
    ExecuteInGameThreadWithDelay(1000, loop)
end

return Matches

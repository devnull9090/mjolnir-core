-- Deliberately small file shared with the Lobby Lua state, never a network
-- payload. Counts are the observed incidents, not authoritative match totals.
local Snapshot = {}

local function line(value)
    return tostring(value or ""):gsub("[%c]", " "):sub(1, 160)
end

function Snapshot.encode(match, localIndex, session, at)
    local rows = { "session=" .. line(session), "at=" .. tostring(at), "active=" .. (match and "1" or "0") }
    if match then
        local player = match.players[localIndex] or {}
        local count = 0
        for _, p in pairs(match.players) do if not p.left then count = count + 1 end end
        rows[#rows + 1] = "code=" .. line(match.code)
        rows[#rows + 1] = "title=" .. line(match.title)
        rows[#rows + 1] = "mode=" .. line(match.variant)
        rows[#rows + 1] = "kills=" .. tostring(player.rawKills or 0)
        rows[#rows + 1] = "deaths=" .. tostring(player.deaths or 0)
        rows[#rows + 1] = "players=" .. tostring(count)
        rows[#rows + 1] = "started=" .. tostring(match.presenceStarted or at)
        rows[#rows + 1] = "over=" .. (match.over and "1" or "0")
    end
    return table.concat(rows, "\n") .. "\n"
end

function Snapshot.new(modDir)
    local last, hadMatch = 0, false
    local marker = modDir .. "\\..\\MJOLNIRLobby\\native\\discord_session.txt"
    return function(match, index)
        local at = os.time()
        if at == last and hadMatch == (match ~= nil) then return end
        last, hadMatch = at, match ~= nil
        local f = io.open(marker, "rb")
        local session = f and f:read(160)
        if f then f:close() end
        if not session then return end
        local out = io.open(modDir .. "\\discord_match.txt", "wb")
        if out then out:write(Snapshot.encode(match, index, session, at)); out:close() end
    end
end

return Snapshot

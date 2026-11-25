-- MJOLNIR Level Loader: a level file decoded once per map.
--
-- A travel reads the map's level file (the multiplayer switch, on the host
-- and on every client), and the load that follows read it again: decoding
-- Timberland's 2.2 MB took 120-200 ms each time. The last file decoded is
-- kept with the path and text it came from. The load takes the switch's
-- table when the file's text is unchanged (read again and compared: under a
-- millisecond), and takes it for itself, since loading changes it
-- (landscapeLight scales its lights): the next reader decodes afresh.
--
-- A player who joins a match under way gets the load first and the switch
-- after, so the switch decoded the file again (92 ms for PWR on PC 3,
-- 2026-11-25). The load's table is kept as well, and a reader that only reads
-- (the switch) may share it while the file's text is unchanged
-- (LevelFiles.shared).

local LevelFiles = {}

--- `decode(text)` returns the table or raises.
function LevelFiles.new(decode)
    local cache = { path = nil, raw = nil, level = nil }
    -- The table a load took, which it may have changed (its lights only).
    local taken = { path = nil, raw = nil, level = nil }
    --- The file at `path` whose text is `raw`, decoded: ok, level (or ok
    --- false and the error), as pcall(decode, raw) would. `take` true hands
    --- over the kept table (and keeps nothing); false keeps what it returns
    --- for the next reader.
    function cache.decode(path, raw, take)
        if cache.level and cache.path == path and cache.raw == raw then
            local level = cache.level
            if take then
                cache.path, cache.raw, cache.level = nil, nil, nil
                taken.path, taken.raw, taken.level = path, raw, level
            end
            return true, level
        end
        local ok, level = pcall(decode, raw)
        if take or not ok then
            cache.path, cache.raw, cache.level = nil, nil, nil
        else
            cache.path, cache.raw, cache.level = path, raw, level
        end
        if take and ok then taken.path, taken.raw, taken.level = path, raw, level end
        return ok, level
    end
    --- The table a load took for the file at `path` whose text is `raw`, for
    --- a reader that only reads it; nil when there is none for that text.
    function cache.shared(path, raw)
        if taken.level and taken.path == path and taken.raw == raw then return taken.level end
        return nil
    end
    return cache
end

return LevelFiles

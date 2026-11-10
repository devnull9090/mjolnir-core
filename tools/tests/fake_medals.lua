-- A stand-in for MJOLNIRLobby's medal exports (native/lobby/medals_runtime.h)
-- for Lua tests that run without the DLL. The catalogue is read from
-- native/lobby/medals_core.h itself, so titles and glyphs are the real ones;
-- the settling is the C core's in short (test_medals.c tests the real one):
-- hiding within one take for the same player, then best first.
--
--   local Fake = dofile("tools/tests/fake_medals.lua")
--   local exports = Fake.new()          -- exports[name] = function
--   package.loadlib = function(_, name) return exports[name] end

local Fake = {}

local CLASSES = { MEDAL_MULTIKILL = 0, MEDAL_SPREE = 1, MEDAL_OBJECTIVE = 2, MEDAL_SPECIAL = 3,
    MEDAL_ROLE_SPREE = 4, MEDAL_FINESSE = 5, MEDAL_CIRCUMSTANCE = 6 }
local SHOWS = { MEDAL_HIDDEN = 0, MEDAL_CALLOUT = 1, MEDAL_FEED = 2 }

--- name -> { name, title, glyph, colour, class, rank, show, hides = { } }
function Fake.catalogue(path)
    local f = assert(io.open(path or "native/lobby/medals_core.h", "rb"))
    local text = f:read("a")
    f:close()
    local defs = {}
    -- Entries may wrap their hides onto a second line.
    text = text:gsub(",%s*\n%s*{", ", {")
    for name, title, glyph, colour, class, rank, show, hides in
        text:gmatch('{"([%w_]+)", "([^"]+)", "(%w+)", "(%w+)", (MEDAL_[%u_]+), (%d+), (MEDAL_%u+),%s*(%b{})}') do
        local list = {}
        for h in hides:gmatch('"([%w_]+)"') do list[#list + 1] = h end
        defs[name] = { name = name, title = title, glyph = glyph, colour = colour, class = CLASSES[class],
            rank = tonumber(rank), show = SHOWS[show], hides = list }
    end
    return defs
end

function Fake.new(path)
    local defs = Fake.catalogue(path)
    local pending, seq = {}, 0
    local exports = {}

    exports.mjolnir_medal_info = function(name)
        local d = defs[name]
        if not d then return nil end
        return d.title, d.glyph, d.colour, d.show, d.class, d.rank
    end

    exports.mjolnir_medal_incident = function(name, cause, effect, at)
        if not defs[name] then return false end
        seq = seq + 1
        pending[#pending + 1] = { def = defs[name], cause = cause, effect = effect, at = at, seq = seq }
        return true
    end

    exports.mjolnir_medals_take = function()
        local ready, first = {}, {}
        for _, e in ipairs(pending) do
            first[e.cause] = math.min(first[e.cause] or math.huge, e.seq)
            local hidden = false
            for _, by in ipairs(pending) do
                if by ~= e and by.cause == e.cause then
                    for _, h in ipairs(by.def.hides) do hidden = hidden or h == e.def.name end
                end
            end
            if not hidden then ready[#ready + 1] = e end
        end
        pending = {}
        table.sort(ready, function(a, b)
            if first[a.cause] ~= first[b.cause] then return first[a.cause] < first[b.cause] end
            if a.def.class ~= b.def.class then return a.def.class < b.def.class end
            if a.def.rank ~= b.def.rank then return a.def.rank > b.def.rank end
            return a.seq < b.seq
        end)
        local lines = {}
        for _, e in ipairs(ready) do
            local d = e.def
            lines[#lines + 1] = string.format("%s|%d|%d|%s|%s|%s|%d\n", d.name, e.cause, e.effect, d.title, d.glyph,
                d.colour, d.show)
        end
        return table.concat(lines)
    end

    exports.mjolnir_medals_reset = function()
        pending = {}
    end

    return exports
end

return Fake

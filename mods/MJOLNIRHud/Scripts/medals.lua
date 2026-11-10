-- MJOLNIR HUD: medals, decided by MJOLNIRLobby's DLL (native/lobby/
-- medals_core.h has the catalogue and the rules, docs/re/medals.md where they
-- come from) and taken through its exports without files (lua_channel.h).
--
-- The HUD hands every incident it takes to `add` (anything not a medal is
-- refused there) and asks `take` once a drain for what to show: each award
-- with its title, glyph, colour and whether it is a feed line for everyone
-- or a callout for the earner only. A sniper headshot's plain headshot and
-- the like are already gone, and one kill's medals come best first.
--
-- Without the DLL's exports (an older MJOLNIRLobby) there are no medals, and
-- the log says why once.

local Medals = {}

Medals.HIDDEN, Medals.CALLOUT, Medals.FEED = 0, 1, 2
-- A medal waits this long (s) for one that hides it, arriving a moment after.
Medals.HOLD = 0.05

--- The awards in `packed` (medals_pack's lines), as
--- { name, cause, effect, title, glyph, colour, show }.
function Medals.decode(packed)
    local out = {}
    if type(packed) ~= "string" then return out end
    for line in packed:gmatch("[^\n]+") do
        local name, cause, effect, title, glyph, colour, show =
            line:match("^([%w_]+)|(-?%d+)|(-?%d+)|([^|]+)|(%w+)|(%w+)|(%d)$")
        if name then
            out[#out + 1] = { name = name, cause = tonumber(cause), effect = tonumber(effect), title = title,
                glyph = glyph, colour = colour, show = tonumber(show) }
        end
    end
    return out
end

--- Medals over the DLL at `dll`; `loadlib` is package.loadlib (a stand-in in
--- tests), `log` a line logger.
function Medals.new(dll, loadlib, log)
    local self = {}
    local fns, loaded
    local known = {}
    log = log or function() end

    local function load()
        if loaded ~= nil then return loaded end
        loaded = false
        if not loadlib then
            log("medals: none (this Lua has no package.loadlib)")
            return false
        end
        fns = {}
        for _, name in ipairs({ "mjolnir_medal_info", "mjolnir_medal_incident", "mjolnir_medals_take",
            "mjolnir_medals_reset" }) do
            local fn, err = loadlib(dll, name)
            if not fn then
                log("medals: none (MJOLNIRLobby's DLL has no " .. name .. ": " .. tostring(err) .. ")")
                return false
            end
            fns[name] = fn
        end
        loaded = true
        return true
    end

    --- { title, glyph, colour, show } for medal incident `name`; nil for
    --- anything else. Asked once per name.
    function self.info(name)
        if type(name) ~= "string" then return nil end
        local cached = known[name]
        if cached ~= nil then return cached or nil end
        if not load() then return nil end
        local ok, title, glyph, colour, show = pcall(fns.mjolnir_medal_info, name)
        local info = ok and title and { title = title, glyph = glyph, colour = colour, show = show } or false
        known[name] = info
        return info or nil
    end

    --- Whether incident `name` is a medal.
    function self.known(name)
        return self.info(name) ~= nil
    end

    --- Hands incident `inc` ({ name, cause, effect, at }) over; true when it
    --- was a medal.
    function self.add(inc)
        if not (inc and self.known(inc.name)) then return false end
        local ok, taken = pcall(fns.mjolnir_medal_incident, inc.name, inc.cause or -1, inc.effect or -1, inc.at or 0)
        return ok and taken == true
    end

    --- The awards settled by `t` (Medals.decode's form).
    function self.take(t)
        if not load() then return {} end
        local ok, packed = pcall(fns.mjolnir_medals_take, t, Medals.HOLD)
        if not ok then return {} end
        return Medals.decode(packed)
    end

    --- A new match: nothing held from the last.
    function self.reset()
        if load() then pcall(fns.mjolnir_medals_reset) end
    end

    return self
end

return Medals

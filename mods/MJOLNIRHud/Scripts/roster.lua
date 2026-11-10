-- MJOLNIR HUD: every player's place, read from the simulation by MJOLNIRLobby's
-- DLL (native/lobby/roster_runtime.h, roster_core.h has the packed form) and
-- taken through its exports without files (lua_channel.h).
--
-- The markers read other players from actors before: twelve to nineteen
-- reflection calls a player, five times a second in King and Juggernaut, and
-- on a fireteam client a remote player's actor could sit where they spawned
-- while the client's simulation followed them to 2 cm
-- (docs/lua_native_audit.md, "Player roster from the simulation"). Every peer
-- reads its own simulation. When the DLL has no roster (an older one, a build
-- it does not know, the simulation not ticking) `read` says why and the
-- markers read actors as they did.

local Roster = {}

Roster.VERSION = 1
Roster.HEADER = 12
Roster.RECORD = 40
Roster.SEATS = 16
-- string.pack forms, little-endian: version, record size, count, 0, tick;
-- then each record: index, flags, local user, team, salt, 0, unit handle,
-- x y z (cm), velocity x y z (cm/s), the handle the place was read from.
Roster.HEADER_FORM = "<I2I2I2I2i4"
Roster.RECORD_FORM = "<BBbbI2I2I4ffffffI4"
-- A place carried on by its velocity for at most this long (s): the
-- simulation moves 60 times a second, the markers are drawn every frame.
Roster.CARRY_S = 0.05

-- UE4SS's Lua is 5.4; the lint runs as LuaJIT with 5.2's library.
local unpack = string.unpack -- luacheck: ignore 143

local function bit(flags, value)
    return math.floor(flags / value) % 2 == 1
end

--- The packed roster as { tick, count, seats = { [index] = seat } }, each seat
--- { index, alive, seated, here (this machine's), user, team, salt, unit,
--- at = { X, Y, Z }, velocity = { X, Y, Z }, placedBy }; nil and why for a
--- string that is not one.
function Roster.decode(packed)
    if type(packed) ~= "string" or #packed < Roster.HEADER then return nil, "not a roster" end
    local version, size, count, _, tick = unpack(Roster.HEADER_FORM, packed)
    if version ~= Roster.VERSION then return nil, "roster version " .. tostring(version) end
    if size < Roster.RECORD or count > Roster.SEATS or #packed ~= Roster.HEADER + count * size then
        return nil, string.format("roster of %d bytes for %d records of %d", #packed, count, size)
    end
    local seats = {}
    for i = 0, count - 1 do
        local index, flags, user, team, salt, _, unit, x, y, z, vx, vy, vz, placedBy =
            unpack(Roster.RECORD_FORM, packed, Roster.HEADER + 1 + i * size)
        seats[index] = {
            index = index,
            alive = bit(flags, 1),
            seated = bit(flags, 2),
            here = bit(flags, 4),
            user = user,
            team = team,
            salt = salt,
            unit = unit,
            at = { X = x, Y = y, Z = z },
            velocity = { X = vx, Y = vy, Z = vz },
            placedBy = placedBy,
        }
    end
    return { tick = tick, count = count, seats = seats }
end

--- A reader over the DLL at `dll` (MJOLNIRLobby\native\mjolnir_lobby.dll).
--- `loadlib` is package.loadlib (a test's stand-in in tests), `log` a line
--- logger. The first roster and each new reason there is none are logged
--- once, so a log shows whether the markers read the simulation or actors.
function Roster.new(dll, loadlib, log)
    local self = {}
    local read, readAt, loaded
    local said, engaged = {}, false
    log = log or function() end

    local function sayOnce(why)
        why = tostring(why)
        if said[why] then return end
        said[why] = true
        log("roster: none (" .. why .. "); the markers read actors")
    end

    local function load()
        if loaded ~= nil then return loaded end
        loaded = false
        if not loadlib then
            sayOnce("this Lua has no package.loadlib")
            return false
        end
        local fn, err = loadlib(dll, "mjolnir_roster")
        if not fn then
            sayOnce("MJOLNIRLobby's DLL has no mjolnir_roster: " .. tostring(err))
            return false
        end
        read = fn
        readAt = loadlib(dll, "mjolnir_roster_at") or nil
        loaded = true
        return true
    end

    --- The roster now (Roster.decode's form), or nil and why.
    function self.read()
        if not load() then return nil, "no export" end
        local ok, packed, why = pcall(read)
        if not ok then
            sayOnce("the call failed: " .. tostring(packed))
            return nil, packed
        end
        if not packed then
            sayOnce(why or "no reason given")
            return nil, why
        end
        local roster, bad = Roster.decode(packed)
        if not roster then
            sayOnce(bad)
            return nil, bad
        end
        if not engaged then
            engaged = true
            local alive = 0
            for _, seat in pairs(roster.seats) do
                if seat.alive then alive = alive + 1 end
            end
            log(string.format("roster: reading the simulation (tick %d, %d player(s), %d alive)",
                roster.tick, roster.count, alive))
        end
        return roster
    end

    --- Seat `index`'s place { X, Y, Z } while they are alive, else nil: one
    --- seat, for a marker that follows a player every frame. The copy is the
    --- last simulation tick's, so the place is carried on by the velocity
    --- for the copy's age (Roster.CARRY_S at most).
    function self.at(index)
        if not (load() and readAt) or type(index) ~= "number" then return nil end
        local ok, x, y, z, alive, vx, vy, vz, age = pcall(readAt, index)
        if not (ok and x and alive) then return nil end
        local t = type(age) == "number" and math.max(0, math.min(age, Roster.CARRY_S)) or 0
        return { X = x + (vx or 0) * t, Y = y + (vy or 0) * t, Z = z + (vz or 0) * t }
    end

    return self
end

return Roster

-- MJOLNIRHud's roster reader (Scripts/roster.lua). lua5.4 tools/tests/test_roster.lua [roster.bin]
--
-- Rosters packed here as the DLL packs them (native/lobby/roster_core.h), and
-- the roster native/lobby/test_roster.c packs from its own tables:
-- tools/tests/fixtures/roster_eight_players.bin, which test-roster.ps1 checks
-- the C side against byte for byte (or another file, given as the argument).

local function eq(got, want, what)
    if got ~= want then error(what .. ": got " .. tostring(got) .. ", want " .. tostring(want), 2) end
end
local function near(got, want, what)
    if type(got) ~= "number" or math.abs(got - want) > 0.05 then
        error(what .. ": got " .. tostring(got) .. ", want " .. tostring(want), 2)
    end
end

local Roster = dofile("mods/MJOLNIRHud/Scripts/roster.lua")

local function record(t)
    return string.pack(Roster.RECORD_FORM, t.index, t.flags or 0, t.user or -1, t.team or 0, t.salt or 0, 0,
        t.unit or 0xffffffff, t.x or 0, t.y or 0, t.z or 0, t.vx or 0, t.vy or 0, t.vz or 0, t.placedBy or 0xffffffff)
end
local function packed(records, tick, size, version)
    size = size or Roster.RECORD
    local body = {}
    for i, r in ipairs(records) do body[i] = r .. string.rep("\0", size - #r) end
    return string.pack(Roster.HEADER_FORM, version or 1, size, #records, 0, tick or 7) .. table.concat(body)
end

eq(#record({ index = 0 }), Roster.RECORD, "a record is 40 bytes")
eq(#string.pack(Roster.HEADER_FORM, 1, 40, 0, 0, 0), Roster.HEADER, "the header is 12 bytes")

local r = assert(Roster.decode(packed({
    record({ index = 0, flags = 5, user = 0, team = 0, salt = 0xe9a1, unit = 0xe2c3000a, x = 100, y = -200, z = 50,
        placedBy = 0xe2c3000a }),
    record({ index = 3, flags = 3, team = 1, x = 3048, y = -6096, z = 152.4, vx = 10, placedBy = 0xe3000014 }),
    record({ index = 9 }),
}, 1234)))
eq(r.tick, 1234, "tick")
eq(r.count, 3, "count")
local me = r.seats[0]
eq(me.alive, true, "alive")
eq(me.here, true, "this machine's")
eq(me.seated, false, "on foot")
eq(me.user, 0, "local user")
eq(me.salt, 0xe9a1, "salt")
eq(me.unit, 0xe2c3000a, "unit")
near(me.at.X, 100, "x")
near(me.at.Y, -200, "y")
near(me.at.Z, 50, "z")
local driver = r.seats[3]
eq(driver.alive and driver.seated and not driver.here, true, "a remote driver")
eq(driver.user, -1, "another machine's")
eq(driver.team, 1, "team")
near(driver.velocity.X, 10, "velocity")
eq(driver.placedBy, 0xe3000014, "placed by the vehicle")
eq(r.seats[9].alive, false, "dead")
eq(r.seats[1], nil, "an empty seat")

-- A newer DLL's longer records: the first 40 bytes of each are read.
local longer = assert(Roster.decode(packed({ record({ index = 2, flags = 1, x = 5 }), record({ index = 4 }) }, 1, 48)))
near(longer.seats[2].at.X, 5, "a 48-byte record")
eq(longer.seats[4].alive, false, "the next 48-byte record")

-- Not rosters.
eq(Roster.decode(nil), nil, "nil")
eq(Roster.decode("short"), nil, "short")
eq(Roster.decode(packed({}, 1, 40, 2)), nil, "another version")
eq(Roster.decode(packed({ record({ index = 0 }) }, 1, 32)), nil, "records too short")
eq(Roster.decode(packed({ record({ index = 0 }) }) .. "x"), nil, "a byte too many")
eq(Roster.decode(packed({ record({ index = 0 }) }):sub(1, -2)), nil, "a byte short")
eq(Roster.decode(packed({}, 5)).count, 0, "nobody")

-- The reader: an export it cannot load, nil and a reason, a roster.
local lines = {}
local function log(line) lines[#lines + 1] = line end
local none = Roster.new("x.dll", function() return nil, "not found" end, log)
eq(none.read(), nil, "no export")
eq(none.read(), nil, "still none")
eq(#lines, 1, "said once")
assert(lines[1]:find("no mjolnir_roster", 1, true), lines[1])

lines = {}
local reply = { nil, "no copy yet" }
local atReply = { nil, "nobody in that seat" }
local function fakeLoad(_, name)
    if name == "mjolnir_roster" then return function() return reply[1], reply[2] end end
    if name == "mjolnir_roster_at" then return function() return table.unpack(atReply) end end
end
local reader = Roster.new("lobby.dll", fakeLoad, log)
eq(reader.read(), nil, "no copy yet")
eq(reader.read(), nil, "no copy yet again")
eq(#lines, 1, "a reason said once")
reply = { packed({ record({ index = 1, flags = 1, x = 1, y = 2, z = 3 }) }, 99) }
local got = assert(reader.read())
near(got.seats[1].at.Z, 3, "read")
eq(#lines, 2, "the first roster said")
assert(lines[2]:find("tick 99, 1 player(s), 1 alive", 1, true), lines[2])
reader.read()
eq(#lines, 2, "and only the first")
reply = { "garbage" }
eq(reader.read(), nil, "a bad string")
eq(#lines, 3, "said")
eq(reader.at(1), nil, "nobody in that seat")
atReply = { 10, 20, 30, false }
eq(reader.at(1), nil, "dead")
atReply = { 10, 20, 30, true }
near(reader.at(1).Y, 20, "one seat, an older DLL's four values")
atReply = { 10, 20, 30, true, 100, -200, 0, 0.02 }
near(reader.at(1).X, 12, "carried on by velocity for the copy's age")
near(reader.at(1).Y, 16, "y too")
atReply = { 10, 20, 30, true, 100, 0, 0, 2.0 }
near(reader.at(1).X, 10 + 100 * Roster.CARRY_S, "a stale copy is carried no further than CARRY_S")
atReply = { 10, 20, 30, true, 100, 0, 0, -1 }
near(reader.at(1).X, 10, "a negative age carries nothing")
eq(reader.at("1"), nil, "not an index")
local throws = Roster.new("lobby.dll", function() return function() error("boom") end end, log)
eq(throws.read(), nil, "a call that throws")

-- The roster test_roster.c packed: eight players, as its tables hold them.
local path = arg and arg[1] or "tools/tests/fixtures/roster_eight_players.bin"
if path then
    local f = assert(io.open(path, "rb"))
    local bytes = f:read("a")
    f:close()
    local c = assert(Roster.decode(bytes))
    eq(c.tick, 1234, "C tick")
    eq(c.count, 8, "C count")
    eq(c.seats[0].here and c.seats[0].alive and not c.seats[0].seated, true, "C: this machine's, on foot")
    near(c.seats[0].at.X, 38.9 * 304.8, "C: x in cm")
    near(c.seats[0].at.Y, 81.087 * 304.8, "C: y flipped")
    near(c.seats[0].velocity.Y, 0.25 * 304.8, "C: velocity y flipped")
    eq(c.seats[1].seated and c.seats[1].alive and not c.seats[1].here, true, "C: a remote driver")
    near(c.seats[1].at.X, 3048, "C: the vehicle's place")
    eq(c.seats[1].team, 1, "C: team")
    for i = 2, 6 do eq(c.seats[i].alive, false, "C: seat " .. i .. " not alive") end
    eq(c.seats[7].alive and c.seats[7].seated, true, "C: a gunner on a turret")
    print("ok (with " .. path .. ")")
else
    print("ok")
end

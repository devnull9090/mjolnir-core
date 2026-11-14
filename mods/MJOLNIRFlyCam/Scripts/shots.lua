-- Numbered camera shots, one JSON file per map. Pure Lua: no Unreal or UE4SS
-- globals, so tools/tests/test_flycam_shots.lua runs it with plain Lua.
--
-- A shot is a camera pose (Unreal world centimetres and degrees, plus the
-- horizontal field of view) with a stable number from 1 to 99 and an optional
-- name. The file is meant to be read and edited by people and tools alike:
--
--   {
--     "version": 1,
--     "map": "ZAN",
--     "shots": [
--       {"n": 1, "name": "overview", "x": 1200.5, "y": -340, "z": 2210,
--        "pitch": -18.2, "yaw": 45, "roll": 0, "fov": 78},
--       ...
--     ]
--   }
--
-- Numbers stay put when other shots are deleted, so "shot 4" means the same
-- framing on every build of a map: that is what before/after comparisons rely
-- on.

local Shots = {}

Shots.MAX = 99

local Json -- set by Shots.init (the decoder lives beside this file)

local FIELDS = { "x", "y", "z", "pitch", "yaw", "roll", "fov" }

function Shots.init(json)
    Json = json
    return Shots
end

local function finite(n)
    return type(n) == "number" and n == n and n > -math.huge and n < math.huge
end

function Shots.validName(name)
    return type(name) == "string" and #name >= 1 and #name <= 48
        and name:match("^[A-Za-z][A-Za-z0-9_-]*$") ~= nil
end

function Shots.validMap(code)
    return type(code) == "string" and code:match("^[A-Za-z0-9_-]+$") ~= nil and #code <= 64
end

--- A shot table from loose values (numbers or numeric strings); nil, why.
function Shots.make(n, name, pose)
    n = tonumber(n)
    if not n or n ~= math.floor(n) or n < 1 or n > Shots.MAX then
        return nil, "shot numbers run from 1 to " .. Shots.MAX
    end
    if name ~= nil and name ~= "" and not Shots.validName(name) then
        return nil, "shot names start with a letter and use letters, digits, _ or -"
    end
    local shot = { n = n, name = (name ~= "" and name) or nil }
    for _, key in ipairs(FIELDS) do
        local v = tonumber(pose[key])
        if not finite(v) then return nil, key .. " must be a finite number" end
        local limit = (key == "x" or key == "y" or key == "z") and 10000000 or 36000
        if math.abs(v) > limit then return nil, key .. " is out of range" end
        shot[key] = v
    end
    if shot.fov < 5 or shot.fov > 170 then return nil, "fov must be between 5 and 170 degrees" end
    return shot
end

function Shots.empty(map)
    return { version = 1, map = map, shots = {} }
end

local function sortShots(list)
    table.sort(list, function(a, b) return a.n < b.n end)
end

--- Parse a shots file. Unknown keys are ignored; a bad shot fails the whole
--- file, so a save never overwrites shots it could not read.
function Shots.decode(text, map)
    if text == nil or text:match("^%s*$") then return Shots.empty(map) end
    local ok, data = pcall(Json.decode, text)
    if not ok then return nil, tostring(data) end
    if type(data) ~= "table" or type(data.shots) ~= "table" then return nil, "no \"shots\" array" end
    local result, seen = Shots.empty(map), {}
    for i, raw in ipairs(data.shots) do
        if type(raw) ~= "table" then return nil, "shot " .. i .. " is not an object" end
        local name = raw.name
        if type(name) ~= "string" then name = nil end
        local shot, err = Shots.make(raw.n, name, raw)
        if not shot then return nil, "shot " .. tostring(raw.n or i) .. ": " .. err end
        if seen[shot.n] then return nil, "shot " .. shot.n .. " appears twice" end
        if shot.name then
            for _, other in ipairs(result.shots) do
                if other.name == shot.name then return nil, "name " .. shot.name .. " appears twice" end
            end
        end
        seen[shot.n] = true
        result.shots[#result.shots + 1] = shot
    end
    sortShots(result.shots)
    return result
end

local function num(v)
    local s = string.format("%.4f", v):gsub("0+$", ""):gsub("%.$", "")
    if s == "-0" then s = "0" end
    return s
end

local function str(s)
    return '"' .. s:gsub('[%c"\\]', function(c)
        return string.format("\\u%04x", c:byte())
    end) .. '"'
end

--- One shot per line, so a diff of two maps' files reads well.
function Shots.encode(data)
    local lines = {}
    for _, s in ipairs(data.shots) do
        local parts = { '"n": ' .. s.n }
        if s.name then parts[#parts + 1] = '"name": ' .. str(s.name) end
        for _, key in ipairs(FIELDS) do parts[#parts + 1] = '"' .. key .. '": ' .. num(s[key]) end
        lines[#lines + 1] = "    {" .. table.concat(parts, ", ") .. "}"
    end
    return "{\n  \"version\": 1,\n  \"map\": " .. str(tostring(data.map or "")) .. ",\n  \"shots\": [\n"
        .. table.concat(lines, ",\n") .. (#lines > 0 and "\n" or "") .. "  ]\n}\n"
end

--- The shot a reference names: its number ("3") or its name.
function Shots.find(data, ref)
    local n = tonumber(ref)
    for i, s in ipairs(data.shots) do
        if (n and s.n == n) or (not n and s.name == ref) then return s, i end
    end
    return nil
end

function Shots.nextFree(data)
    local used = {}
    for _, s in ipairs(data.shots) do used[s.n] = true end
    for n = 1, Shots.MAX do
        if not used[n] then return n end
    end
    return nil
end

--- Store a pose. n nil: the shot already called `name`, else the lowest free
--- number. Replacing a numbered shot keeps its name unless a new one is given.
function Shots.put(data, pose, n, name)
    if name == "" then name = nil end
    if n == nil and name then
        local existing = Shots.find(data, name)
        if existing then n = existing.n end
    end
    if n == nil then
        n = Shots.nextFree(data)
        if not n then return nil, "all " .. Shots.MAX .. " shot numbers are used" end
    end
    local old, index = Shots.find(data, tostring(n))
    if old and not name then name = old.name end
    if name then
        local clash = Shots.find(data, name)
        if clash and clash.n ~= tonumber(n) then
            return nil, "shot " .. clash.n .. " is already called " .. name
        end
    end
    local shot, err = Shots.make(n, name, pose)
    if not shot then return nil, err end
    if index then data.shots[index] = shot else data.shots[#data.shots + 1] = shot end
    sortShots(data.shots)
    return shot
end

function Shots.remove(data, ref)
    local shot, index = Shots.find(data, ref)
    if not shot then return nil end
    table.remove(data.shots, index)
    return shot
end

--- One line describing a shot, for the console and the overlay.
function Shots.describe(s)
    return string.format("%2d %-14s %9.1f %9.1f %8.1f   p %6.1f  y %6.1f  r %4.1f   fov %5.1f",
        s.n, s.name or "-", s.x, s.y, s.z, s.pitch, s.yaw, s.roll, s.fov)
end

return Shots

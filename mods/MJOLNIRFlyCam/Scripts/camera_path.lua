-- Pure camera-path math and pose records. No Unreal or UE4SS globals.
local Path = {}

local fields = { "X", "Y", "Z", "Pitch", "Yaw", "Roll", "FOV" }

local function finite(n)
    return type(n) == "number" and n == n and n > -math.huge and n < math.huge
end

function Path.validName(name)
    return type(name) == "string" and #name >= 1 and #name <= 48
        and name:match("^[A-Za-z][A-Za-z0-9_-]*$") ~= nil
end

function Path.pose(values)
    if type(values) ~= "table" then return nil, "pose must be a table" end
    local result = {}
    for _, key in ipairs(fields) do
        local value = tonumber(values[key])
        if not finite(value) then return nil, key .. " must be a finite number" end
        local limit = (key == "X" or key == "Y" or key == "Z") and 10000000 or 36000
        if math.abs(value) > limit then return nil, key .. " is out of range" end
        result[key] = value
    end
    if result.FOV < 5 or result.FOV > 170 then return nil, "FOV must be between 5 and 170 degrees" end
    return result
end

-- Linear angles follow the shortest direction across the +/-180 seam.
local function angle(a, b, t)
    return a + ((b - a + 180) % 360 - 180) * t
end

function Path.create(poses, names, seconds, easing)
    seconds = tonumber(seconds)
    if not finite(seconds) or seconds < 0.1 or seconds > 3600 then
        return nil, "seconds per segment must be between 0.1 and 3600"
    end
    if easing ~= "linear" and easing ~= "smooth" then return nil, "easing must be linear or smooth" end
    if type(names) ~= "table" or #names < 2 or #names > 32 then
        return nil, "supply 2 to 32 pose names"
    end
    local frames = {}
    for _, name in ipairs(names) do
        if not Path.validName(name) or not poses[name] then return nil, "unknown pose: " .. tostring(name) end
        local pose, err = Path.pose(poses[name])
        if not pose then return nil, "invalid pose " .. name .. ": " .. err end
        frames[#frames + 1] = pose -- immutable snapshot, even if the saved pose is edited
    end
    return { frames = frames, seconds = seconds, easing = easing, elapsed = 0 }
end

function Path.sample(path, elapsed)
    local frames, seconds = path.frames, path.seconds
    local total = seconds * (#frames - 1)
    if elapsed <= 0 then return Path.pose(frames[1]), false end
    if elapsed >= total then return Path.pose(frames[#frames]), true end
    local segment = math.floor(elapsed / seconds) + 1
    local t = (elapsed - (segment - 1) * seconds) / seconds
    if path.easing == "smooth" then t = t * t * (3 - 2 * t) end
    local a, b = frames[segment], frames[segment + 1]
    local result = {}
    for _, key in ipairs(fields) do
        if key == "Pitch" or key == "Yaw" or key == "Roll" then
            result[key] = angle(a[key], b[key], t)
        else
            result[key] = a[key] + (b[key] - a[key]) * t
        end
    end
    return result, false
end

function Path.advance(path, dt)
    if not finite(dt) or dt < 0 then return nil, false, "invalid tick delta" end
    path.elapsed = math.min(path.elapsed + dt, path.seconds * (#path.frames - 1))
    return Path.sample(path, path.elapsed)
end

-- Append-only, non-executable text. Last record for a name wins on reload.
function Path.record(name, values)
    if not Path.validName(name) then return nil, "pose names must start with a letter and use letters, digits, _ or -" end
    local pose, err = Path.pose(values)
    if not pose then return nil, err end
    return string.format("pose1,%s,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g\n",
        name, pose.X, pose.Y, pose.Z, pose.Pitch, pose.Yaw, pose.Roll, pose.FOV)
end

function Path.parse(text)
    if type(text) ~= "string" or #text > 2 * 1024 * 1024 then return nil, "pose file is invalid or exceeds 2 MiB" end
    if #text > 0 and text:sub(-1) ~= "\n" then return nil, "pose file ends with an incomplete record" end
    local poses, count = {}, 0
    for rawLine in text:gmatch("([^\n]*)\n") do
        local line = rawLine:gsub("\r$", "")
        if line ~= "" then
            local parts = {}
            for item in (line .. ","):gmatch("([^,]*),") do parts[#parts + 1] = item end
            if #parts ~= 9 or parts[1] ~= "pose1" or not Path.validName(parts[2]) then
                return nil, "invalid pose record"
            end
            local values = {}
            for i, key in ipairs(fields) do values[key] = parts[i + 2] end
            local pose, err = Path.pose(values)
            if not pose then return nil, "invalid pose " .. parts[2] .. ": " .. err end
            if not poses[parts[2]] then count = count + 1 end
            if count > 512 then return nil, "pose file contains more than 512 names" end
            poses[parts[2]] = pose
        end
    end
    return poses
end

return Path

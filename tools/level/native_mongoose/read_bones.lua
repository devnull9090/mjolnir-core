-- In-game reader for the skinned Mongoose. Run through game_lua with
--   dofile([[<this file>]]); return bones_read()     -- class, mesh, every bone
--   return bones_mark()                              -- remember this pose
--   return bones_moved()                             -- what moved since the mark
-- Reads only: the two named actor classes, no component scans, no stored handles.
--
-- Every value is in the vehicle's own axes, so turning or driving the whole
-- vehicle changes nothing here: only a bone moving on the vehicle does. A row is
-- position (forward, right, up) in cm, then the bone's X axis and Z axis in the
-- same frame, then "rest", how far it sits from its bind place in cm. A spinning
-- wheel shows in the axes, suspension in the position.
local NATIVE = "BP_NMGMongoose_C"
local SHIPPED = "BP_VHTMongoose_C"

-- Each bone's bind place from bones.json: forward, right, up, in cm.
local REST = {
    ["Pedestal"] = { 0.000, 0.000, 0.000 },
    ["frame_hull"] = { -21.558, 0.000, 107.234 },
    ["frame_lb_suspension"] = { -74.930, -35.898, 81.231 },
    ["frame_lf_suspension"] = { 35.221, -35.536, 74.950 },
    ["frame_rb_suspension"] = { -74.930, 35.848, 81.231 },
    ["frame_rf_suspension"] = { 35.221, 35.589, 74.950 },
    ["frame_steering"] = { 52.624, -0.081, 141.309 },
    ["frame_lb_engine"] = { -131.702, -40.284, 53.133 },
    ["frame_lf_engine"] = { 99.584, -39.922, 53.133 },
    ["frame_rb_engine"] = { -131.702, 39.567, 53.133 },
    ["frame_rf_engine"] = { 99.584, 39.307, 53.134 },
    ["frame_lb_tire"] = { -131.702, -69.780, 53.133 },
    ["frame_lf_tire"] = { 99.584, -69.417, 53.133 },
    ["frame_rb_tire"] = { -131.702, 69.596, 53.133 },
    ["frame_rf_tire"] = { 99.584, 69.337, 53.134 },
}

local mark = nil

local function full(o)
    if o and o:IsValid() then return o:GetFullName() end
    return "none"
end

-- The SkeletalMesh property is a deprecated mirror that need not be filled in:
-- ask the getter first.
local function meshOf(c)
    for _, read in ipairs({
        function() return c:GetSkeletalMeshAsset() end,
        function() return c.SkinnedAsset end,
        function() return c.SkeletalMesh end,
    }) do
        local ok, mesh = pcall(read)
        if ok and mesh and mesh:IsValid() then return mesh end
    end
    return nil
end

-- The placed actor, never the class default, whose component is a template.
local function placed(class)
    for _, a in ipairs(FindAllOf(class) or {}) do
        if a:IsValid() and not a:GetFullName():find("Default__", 1, true) then
            local m = a.hull
            if m and m:IsValid() then return a, m end
            return a, nil
        end
    end
    return nil, nil
end

local function dot(a, b)
    return a[1] * b.X + a[2] * b.Y + a[3] * b.Z
end

-- A rotator's X and Z axes, in degrees as Unreal stores it.
local function axes(r)
    local p, y, l = math.rad(r.Pitch), math.rad(r.Yaw), math.rad(r.Roll)
    local sp, cp, sy, cy, sr, cr = math.sin(p), math.cos(p), math.sin(y), math.cos(y), math.sin(l), math.cos(l)
    return { cp * cy, cp * sy, sp },
        { -(cr * sp * cy + sr * sy), cy * sr - cr * sp * sy, cr * cp }
end

local function headline(class, a, m, out)
    out[#out + 1] = class .. " " .. full(a)
    if not m then
        out[#out + 1] = "  no hull component: this reader's property name is wrong, not the test"
        return
    end
    out[#out + 1] = "  mesh " .. full(meshOf(m))
    local ok, anim = pcall(function() return m.AnimClass end)
    out[#out + 1] = "  anim class " .. (ok and full(anim) or "unreadable")
    out[#out + 1] = "  anim instance " .. full(m:GetAnimInstance())
    out[#out + 1] = "  bones " .. tostring(m:GetNumBones())
    local visible, shown = pcall(function() return m:IsVisible() end)
    out[#out + 1] = "  visible " .. (visible and tostring(shown) or "unreadable")
    local counted, slots = pcall(function() return m:GetNumMaterials() end)
    if counted then
        for i = 0, slots - 1 do
            out[#out + 1] = "  material " .. i .. " " .. full(m:GetMaterial(i))
        end
    end
end

-- Every bone the mesh has, by its own list, so a name that differs still shows.
local function pose(a, m)
    local at = a:K2_GetActorLocation()
    local f, r, u = a:GetActorForwardVector(), a:GetActorRightVector(), a:GetActorUpVector()
    local rows = {}
    for i = 0, m:GetNumBones() - 1 do
        local bone = m:GetBoneName(i)
        local name = bone:ToString()
        local p = m:GetSocketLocation(bone)
        local x, z = axes(m:GetSocketRotation(bone))
        local d = { p.X - at.X, p.Y - at.Y, p.Z - at.Z }
        rows[#rows + 1] = {
            name = name,
            v = { dot(d, f), dot(d, r), dot(d, u), dot(x, f), dot(x, r), dot(x, u), dot(z, f), dot(z, r), dot(z, u) },
        }
    end
    return rows
end

local function fromRest(row)
    local rest = REST[row.name]
    if not rest then return nil end
    local a, b, c = row.v[1] - rest[1], row.v[2] - rest[2], row.v[3] - rest[3]
    return math.sqrt(a * a + b * b + c * c)
end

local ROW = "%-22s %8.2f %8.2f %8.2f | %6.3f %6.3f %6.3f | %6.3f %6.3f %6.3f | rest %s"

function bones_read()
    local out = {}
    local a, m = placed(NATIVE)
    if not a then return NATIVE .. ": no actor" end
    headline(NATIVE, a, m, out)
    if m then
        local missing = {}
        local seen = {}
        for _, row in ipairs(pose(a, m)) do
            seen[row.name] = true
            local rest = fromRest(row)
            local text = rest and string.format("%.2f", rest) or "UNKNOWN BONE"
            local v = row.v
            out[#out + 1] = string.format(ROW, row.name, v[1], v[2], v[3], v[4], v[5], v[6], v[7], v[8], v[9], text)
        end
        for name in pairs(REST) do
            if not seen[name] then missing[#missing + 1] = name end
        end
        table.sort(missing)
        out[#out + 1] = "bones missing from the mesh: " .. (#missing > 0 and table.concat(missing, ", ") or "none")
    end
    local b, n = placed(SHIPPED)
    if b then headline(SHIPPED, b, n, out) else out[#out + 1] = SHIPPED .. ": no actor" end
    return table.concat(out, "\n")
end

function bones_mark()
    local a, m = placed(NATIVE)
    if not (a and m) then return NATIVE .. ": no actor" end
    mark = pose(a, m)
    return "marked " .. #mark .. " bones"
end

function bones_moved()
    if not mark then return "bones_mark() first" end
    local a, m = placed(NATIVE)
    if not (a and m) then return NATIVE .. ": no actor" end
    local out = {}
    for i, row in ipairs(pose(a, m)) do
        local was = mark[i].v
        local move, turn = 0, 0
        for k = 1, 3 do move = move + (row.v[k] - was[k]) ^ 2 end
        for k = 4, 9 do turn = math.max(turn, math.abs(row.v[k] - was[k])) end
        out[#out + 1] = string.format("%-22s moved %7.2f cm, axes changed %5.3f", row.name, math.sqrt(move), turn)
    end
    return table.concat(out, "\n")
end

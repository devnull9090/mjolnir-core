-- MJOLNIRHud's hill marker: lua5.4 tools/tests/test_hill_marker.lua
local Hill = dofile("mods/MJOLNIRHud/Scripts/hill.lua")

local function eq(got, want, what)
    if got ~= want then error(what .. ": got " .. tostring(got) .. ", want " .. tostring(want), 2) end
end

local hills = Hill.parse('{"modes": ["koth"], "koth_hills": [\n  [100.5, -200, 30, 800.0],\n  [1, 2, 3, 4]\n], "x": [[9, 9, 9, 9]]}')
eq(#hills, 2, "hills in the list")
eq(hills[1].x, 100.5, "first x")
eq(hills[2].r, 4, "second radius")
eq(#Hill.parse('{"modes": ["slayer"]}'), 0, "no hills")
eq(#Hill.parse(nil), 0, "no file")

local hill = { x = 0, y = 0, z = 0, r = 500 }
eq(Hill.describe(hill, { X = 100, Y = 0, Z = 10 }, 0), "ON THE HILL", "standing on it")
eq(Hill.describe(hill, { X = 100, Y = 0, Z = 900 }, 0), "HILL BELOW", "over it")
eq(Hill.describe(hill, { X = -2500, Y = 0, Z = 0 }, 0), "HILL 20 M AHEAD", "facing it")
eq(Hill.describe(hill, { X = -2500, Y = 0, Z = 0 }, 180), "HILL 20 M BEHIND", "back to it")
eq(Hill.describe(hill, { X = 0, Y = -2500, Z = 0 }, 0), "HILL 20 M RIGHT", "Unreal: +Y is to the right of +X")
eq(Hill.describe(hill, { X = 0, Y = 2500, Z = 0 }, 0), "HILL 20 M LEFT", "and -Y to the left")
eq(Hill.describe(hill, { X = -2500, Y = 0, Z = -1000 }, 0), "HILL 20 M AHEAD ABOVE", "a floor up")

local panels = Hill.panels({ x = 100, y = 200, z = 0, r = 800 })
eq(#panels, 34, "a panel about every 150 cm")
eq(math.floor(math.sqrt((panels[1].x - 100) ^ 2 + (panels[1].y - 200) ^ 2) + 0.5), 800, "on the circle")
eq(#Hill.panels({ x = 0, y = 0, z = 0, r = 100 }), 16, "a small hill stays round")
eq(#Hill.panels({ x = 0, y = 0, z = 0, r = 7800 }), 64, "the widest hill stays cheap")

eq(Hill.smooth({ 3, 0, 0, 0 })[2], 1, "smoothing averages neighbours")
eq(Hill.smooth({ 3, 0, 0, 0 })[4], 1, "and the ring closes")

local function at(x, z) return { X = x, Y = 0, Z = z or 0 } end
eq(Hill.holder(hill, {}), "empty", "nobody")
eq(Hill.holder(hill, { { at = at(900) } }), "empty", "outside")
eq(Hill.holder(hill, { { at = at(0, 900) } }), "empty", "a floor up")
eq(Hill.holder(hill, { { at = at(0), me = true } }), "you", "alone on it")
eq(Hill.holder(hill, { { at = at(0) }, { at = at(900), me = true } }), "other", "someone else")
eq(Hill.holder(hill, { { at = at(0) }, { at = at(100), me = true } }), "contested", "two in free for all")
eq(Hill.holder(hill, { { at = at(0), team = "Red" }, { at = at(100), team = "Red" } }), "Red", "one team")
eq(Hill.holder(hill, { { at = at(0), team = "Red" }, { at = at(100), team = "Blue" } }), "contested", "two teams")

local marker = Hill.new(function() return '"koth_hills": [[0,0,0,1],[5,5,5,1]]' end)
eq(marker.start("ABC"), 2, "start")
marker.moved(1)
eq(marker.live, 2, "second hill")
marker.moved(9)
eq(marker.live, 2, "a place past the list changes nothing")

-- Exercise the UE bridge boundary: pooled meshes must keep distinct wall and
-- beacon materials, including after a MID expires or an older pack is loaded.
local FIELD = "/Game/MJOLNIR/KOTH/M_KOTH_Field.M_KOTH_Field"
local BEACON = "/Game/MJOLNIR/KOTH/M_KOTH_Beacon.M_KOTH_Beacon"
local PLASMA = "/Game/MJOLNIR/CETrial/M_CE_Plasma.M_CE_Plasma"
local PLANE = "/Engine/BasicShapes/Plane.Plane"
local CYLINDER = "/Engine/BasicShapes/Cylinder.Cylinder"
local function object(fields)
    local o = fields or {}
    o.valid = true
    function o:IsValid() return self.valid end
    return o
end
local function noop() end
local function scene(available, failCreate)
    local s = { actors = {}, mids = {}, loads = 0, available = available }
    local system = {}
    function system:MakeSoftObjectPath(path) return path end
    function system:Conv_SoftObjPathToSoftObjRef(path) return path end
    function system:LoadAsset_Blocking(path)
        s.loads = s.loads + 1
        if available[path] then return object({ path = path }) end
    end
    function system:LineTraceSingle() end
    local materials = {}
    function materials:CreateDynamicMaterialInstance(_, master)
        if failCreate and failCreate[master.path] then return end
        local mid = object({ master = master.path, params = {} })
        function mid:SetVectorParameterValue(name, value) self.params[name] = value end
        s.mids[#s.mids + 1] = mid
        return mid
    end
    local widgets = {}
    function widgets:Create()
        local w = object({ WidgetTree = {} })
        w.AddToViewport, w.SetAnchorsInViewport, w.SetAlignmentInViewport = noop, noop, noop
        function w:SetVisibility(value) self.visibility = value end
        return w
    end
    _G.FName, _G.FText = function(x) return x end, function(x) return x end
    _G.StaticFindObject = function(path)
        if path == "/Script/Engine.Default__KismetSystemLibrary" then return system end
        if path == "/Script/Engine.Default__KismetMaterialLibrary" then return materials end
        if path == "/Script/UMG.Default__WidgetBlueprintLibrary" then return widgets end
        if path == "/Script/Engine.Default__KismetMathLibrary" then
            return { MakeRotFromZX = function(_, z, x) return { z = z, x = x } end }
        end
        return object({ path = path })
    end
    _G.StaticConstructObject = function()
        local t = object()
        t.SetColorAndOpacity, t.SetShadowOffset, t.SetShadowColorAndOpacity = noop, noop, noop
        function t:SetText(value) self.text = value end
        return t
    end
    s.world = object()
    function s.world:SpawnActor()
        local comp = object()
        function comp:SetStaticMesh(mesh) self.mesh = mesh end
        function comp:SetCollisionEnabled(value) self.collision = value end
        function comp:SetCastShadow(value) self.shadows = value end
        function comp:SetMaterial(_, mid) self.material = mid end
        local actor = object({ StaticMeshComponent = comp })
        function actor:K2_SetActorLocation(value) self.location = value end
        function actor:K2_SetActorRotation(value) self.rotation = value end
        function actor:SetActorScale3D(value) self.scale = value end
        function actor:SetActorHiddenInGame(value) self.hidden = value end
        s.actors[#s.actors + 1] = actor
        return actor
    end
    local pawn = object()
    function pawn:K2_GetActorLocation() return { X = 0, Y = 0, Z = 0 } end
    s.pc = object({ Pawn = pawn })
    function s.pc:GetWorld() return s.world end
    function s.pc:GetControlRotation() return { Yaw = 0 } end
    s.marker = Hill.new(function() return '"koth_hills": [[0,0,0,500],[2000,3000,400,200]]' end)
    s.marker.start("ABC")
    return s
end
local function contested()
    return { { at = at(0), me = true }, { at = at(100) } }
end

local s = scene({ [FIELD] = true, [BEACON] = true, [PLANE] = true, [CYLINDER] = true })
local m = s.marker
m.tick(0, s.pc, false, contested)
eq(m.holographic, true, "dedicated materials selected")
eq(m.mid.master, FIELD, "boundary master")
eq(m.beaconMid.master, BEACON, "beacon master")
assert(m.mid ~= m.beaconMid, "the beacon has its own instance")
eq(m.parts[1].StaticMeshComponent.material, m.mid, "boundary binds its material")
eq(m.beacon.StaticMeshComponent.material, m.beaconMid, "beacon binds its material")
eq(m.anchor.StaticMeshComponent.material, m.beaconMid, "anchor shares beacon material")
eq(m.anchor.location.Z, 5, "anchor sits just above the ground")
eq(m.anchor.rotation.Pitch, 0, "anchor stays horizontal")
eq(m.anchor.StaticMeshComponent.collision, 0, "anchor never blocks gameplay")
eq(#s.actors, #m.parts + 2, "one beacon and one anchor accompany the boundary")
eq(m.mid.params.FieldState.R, 1, "contested reaches boundary shader")
eq(m.beaconMid.params.FieldState.R, 1, "contested reaches beacon shader")
eq(m.mid.params.PlasmaBrightness, nil, "dedicated shader owns its animated brightness")
eq(m.text.text, "HILL CONTESTED", "HUD remains consistent with contested state")
eq(m.parts[1].StaticMeshComponent.collision, 0, "boundary never blocks gameplay")
local actorsBefore = #s.actors
local oldField, oldBeacon = m.mid, m.beaconMid
oldBeacon.valid = false
m.tick(1, s.pc, false, contested)
eq(#s.actors, actorsBefore, "recreating materials keeps pooled actors")
assert(m.mid ~= oldField and m.beaconMid ~= oldBeacon, "expired pair is recreated")
for _, actor in ipairs(m.parts) do
    eq(actor.StaticMeshComponent.material, m.mid, "every pooled boundary is rebound")
end
eq(m.beacon.StaticMeshComponent.material, m.beaconMid, "pooled beacon is rebound")
eq(m.anchor.StaticMeshComponent.material, m.beaconMid, "pooled anchor is rebound")
local oldAnchor = m.anchor
oldAnchor.valid = false
m.tick(1.25, s.pc, false, contested)
assert(m.anchor ~= oldAnchor, "an expired anchor is replaced without waiting for a hill move")
eq(#s.actors, actorsBefore + 1, "replacing the anchor leaves the other pooled actors intact")
actorsBefore = #s.actors
m.moved(1)
m.tick(2, s.pc, false)
eq(#s.actors, actorsBefore, "moving to a smaller hill reuses geometry")
eq(m.mid.params.FieldCenter.R, 2000, "field center moves")
eq(m.beaconMid.params.FieldCenter.B, 400, "beacon center moves")
eq(m.mid.params.FieldCenter.A, 200, "radius follows the active hill")
eq(m.anchor.location.X, 2000, "anchor follows the active hill")
eq(m.anchor.location.Z, 405, "anchor follows the active hill ground height")
eq(m.mid.params.FieldState.R, 0, "new empty hill clears contested state")
eq(m.parts[#m.parts].hidden, true, "surplus boundary panels are hidden")
m.tick(3, s.pc, true)
eq(m.beacon.hidden, true, "hidden HUD hides beacon")
eq(m.anchor.hidden, true, "hidden HUD hides anchor")
m.tick(4, s.pc, false)
eq(m.beacon.hidden, false, "unhiding restores pooled beacon")
eq(m.anchor.hidden, false, "unhiding restores pooled anchor")
eq(#s.actors, actorsBefore, "unhiding does not duplicate actors")

-- Partial installs and MID creation failures use a complete fallback pair.
for _, fail in ipairs({ "missing", "instance" }) do
    local available = { [FIELD] = true, [BEACON] = fail ~= "missing", [PLASMA] = true,
                        [PLANE] = true, [CYLINDER] = true }
    s = scene(available, fail == "instance" and { [BEACON] = true } or nil)
    m = s.marker
    m.tick(0, s.pc, false, contested)
    eq(m.holographic, false, fail .. ": old runtime fallback")
    eq(m.mid.master, PLASMA, fail .. ": boundary uses CE fallback")
    eq(m.beaconMid.master, PLASMA, fail .. ": beacon uses CE fallback")
    assert(m.mid ~= m.beaconMid, fail .. ": fallback instances are independent")
    eq(m.anchor, nil, "fallback does not expose a square plasma anchor")
    assert(m.mid.params.PlasmaBrightness.R < m.beaconMid.params.PlasmaBrightness.R,
           "fallback boundary is quieter than the beacon")
    local values = {}
    for tick = 1, 8 do
        m.tick(tick * 0.25, s.pc, false, contested)
        local brightness = m.mid.params.PlasmaBrightness.R
        assert(brightness > 0.3 and brightness < 0.6, "contested fallback remains restrained")
        values[string.format("%.4f", brightness)] = true
    end
    local count = 0
    for _ in pairs(values) do count = count + 1 end
    assert(count > 2, "fallback pulse has intermediate values, not a two-state flash")
end

s = scene({ [PLANE] = true, [CYLINDER] = true })
m = s.marker
m.tick(0, s.pc, false)
eq(#s.actors, 0, "missing materials skip geometry")
eq(m.text.text, "ON THE HILL", "missing materials retain HUD guidance")
local loadsBefore = s.loads
m.tick(1, s.pc, false)
eq(s.loads, loadsBefore, "missing assets are not reloaded every update")
s.available[FIELD], s.available[BEACON] = true, true
m.tick(3.5, s.pc, false)
eq(m.holographic, true, "a later available runtime recovers")
assert(#s.actors > 0, "retry draws recovered geometry")
s.pc.valid = false
m.tick(4, s.pc, false)
eq(m.beacon.hidden, true, "invalid controller safely hides the marker")
eq(m.anchor.hidden, true, "invalid controller safely hides the anchor")
s.pc.valid = true
m.tick(4.5, s.pc, false)
s.world.valid = false
m.tick(5, s.pc, false)
eq(m.beacon.hidden, true, "invalid world safely hides the marker")
eq(m.anchor.hidden, true, "invalid world safely hides the anchor")
eq(m.widget.visibility, 1, "invalid world keeps the HUD hidden")
print("hill marker: ok")

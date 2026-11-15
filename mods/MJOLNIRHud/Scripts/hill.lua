-- MJOLNIR HUD: where King of the Hill's hill is.
--
-- No Megalo waypoint or boundary reaches Unreal (docs/game_modes.md, B4 and
-- B5), so a match shows nothing where the hill stands. The level file lists
-- the hills in rotation order (`koth_hills`: x, y, z and radius, Unreal cm,
-- tools/level/ce_objectives.py), the variant says which one is live
-- (`hill_moved`, value = its place in the rotation), and this draws the hill
-- itself, a holographic boundary round the scoring cylinder and a beacon above
-- it, and a marker on the screen (Scripts/waypoint.lua) for the way there. A
-- line under the score says what the marker cannot: ON THE HILL, HILL CONTESTED.
-- If no marker can be made, the line gives the distance and bearing instead.
-- Each game draws its own, so it needs no replication, and the sim never sees
-- these actors.
--
-- Hill.field is that drawing on its own, for anything else that marks a spot in
-- the world: Scripts/race.lua's flags and Scripts/juggernaut.lua's beacon.

local Hill = {}

--- Scripts/waypoint.lua, set by Scripts/markers.lua. Without it, lines only.
Hill.Waypoint = nil

--- The script's rule, CONTESTED_HILL_SCORES in crates/blam-megalo/src/objectives.rs:
--- flip the two together. False: a contested hill scores nothing, and shows it.
--- True: everyone on it scores (CE), so nothing is shown as contested.
Hill.CONTESTED_HILL_SCORES = false

local COLLAPSED = 1 -- ESlateVisibility
local VISIBLE_NO_HIT_TEST = 4
local EVERY = 0.2 -- seconds between updates
local CM_PER_METRE = 100
local LEVEL_DIFFERENCE_CM = 300

local FIELD_MASTER = "/Game/MJOLNIR/KOTH/M_KOTH_Field.M_KOTH_Field"
local BEACON_MASTER = "/Game/MJOLNIR/KOTH/M_KOTH_Beacon.M_KOTH_Beacon"
-- Older runtime packs have only CE plasma. Keep a quieter version as a
-- fallback; when neither pair can load the hill still has its HUD line.
local PLASMA_MASTERS = {
    "/Game/MJOLNIR/CETrial/M_CE_Plasma.M_CE_Plasma",
    "/Game/MJOLNIR/CE/M_CE_Plasma.M_CE_Plasma",
}
-- Panels, not a cylinder: BasicShapes' cylinder has a lid, which roofed the
-- hill in plasma. Both shapes are 100 cm across.
local PLANE = "/Engine/BasicShapes/Plane.Plane"
local CYLINDER = "/Engine/BasicShapes/Cylinder.Cylinder"
local MOVABLE = 2 -- EComponentMobility
local NO_COLLISION = 0 -- ECollisionEnabled
local PANEL_CM = 150
local MIN_PANELS, MAX_PANELS = 16, 64
local WALL_CM = 170
local WALL_SINK_CM = 35 -- below the ground, so a slope shows no gap
local LOWEST_CM = 250 -- a panel past a roof's edge stays near the roof
local TRACE_STARTS_CM = { 350, 1500 } -- the second for ground above the first
local TRACE_DEPTH_CM = 2500
local BEACON_RADIUS_CM = 55
local BEACON_CM = 7000
local FALLBACK_WALL_BRIGHTNESS = 0.42
local FALLBACK_BEACON_BRIGHTNESS = 0.55
local NOISE_SCALE = 0.35
local MATERIAL_RETRY_SECONDS = 3
local HILL_HEIGHT_CM = 600 -- how far above or below still counts as on it
local MARKER_HEIGHT_CM = 350 -- the screen marker's spot, above the ground the hill stands on
local PILLAR = {} -- what `drawn` holds while only the beacon stands
-- One hit-result table for every move, emptied first. UE4SS keeps the
-- FHitResult it writes into a fresh table alive, so a {} a call piles up
-- (the beacon moves every frame), and it pushes a used table's fields back
-- into the next call, three of them weak pointers it logs it cannot set.
-- LevelLoader's Current.emptyHit() does the same.
local HIT = {}
local function emptyHit()
    for k in pairs(HIT) do HIT[k] = nil end
    return HIT
end
-- The traces' other tables, made once: no actor to ignore, no debug colours.
local IGNORE = {}
local NO_COLOUR = { R = 0, G = 0, B = 0, A = 0 }

-- Engine objects by path, found once and kept. StaticFindObject costs about
-- 1 ms even for a /Script path, more in a match, and a hill move asked for two
-- per panel, for 16 to 64 panels: 30-130 ms on one poll. A kept handle is
-- checked before each use and found again if it went.
local found = {}
local function object(path)
    local o = found[path]
    if o and o:IsValid() then return o end
    o = StaticFindObject(path)
    found[path] = o
    return o
end
local COLOURS = {
    empty = { para = { 1, 0.8, 0.25 }, perp = { 1, 0.55, 0.08 } }, -- gold
    you = { para = { 0.45, 1, 0.9 }, perp = { 0.1, 0.8, 1 } }, -- cyan
    other = { para = { 1, 0.45, 0.2 }, perp = { 1, 0.15, 0.05 } }, -- orange-red
    contested = { para = { 0.95, 0.4, 1 }, perp = { 0.6, 0.1, 1 } }, -- violet
    Red = { para = { 1, 0.3, 0.25 }, perp = { 1, 0.08, 0.05 } },
    Blue = { para = { 0.35, 0.6, 1 }, perp = { 0.1, 0.3, 1 } },
}

--- The hills in a level file's text, in rotation order; or another list of
--- [x, y, z, radius] under `key`.
function Hill.parse(text, key)
    local list = type(text) == "string" and text:match('"' .. (key or "koth_hills") .. '"%s*:%s*(%b[])') or nil
    local hills = {}
    if not list then return hills end
    local n = "([-%d.eE+]+)"
    local c = "%s*,%s*"
    for x, y, z, r in list:gmatch("%[%s*" .. n .. c .. n .. c .. n .. c .. n .. "%s*%]") do
        hills[#hills + 1] = { x = tonumber(x), y = tonumber(y), z = tonumber(z), r = tonumber(r) }
    end
    return hills
end

--- Where `spot` lies from a player at `at` looking along `yaw` (degrees), in
--- the words a player would use: whether they stand inside its circle, the
--- metres to its edge, the way to turn, and " ABOVE", " BELOW" or "".
function Hill.bearing(spot, at, yaw)
    local dx, dy, dz = spot.x - at.X, spot.y - at.Y, spot.z - at.Z
    local flat = math.sqrt(dx * dx + dy * dy)
    local level = ""
    if dz > LEVEL_DIFFERENCE_CM then
        level = " ABOVE"
    elseif dz < -LEVEL_DIFFERENCE_CM then
        level = " BELOW"
    end
    local turn = (math.deg(math.atan(dy, dx)) - yaw + 540) % 360 - 180
    local way
    if math.abs(turn) <= 35 then
        way = "AHEAD"
    elseif math.abs(turn) >= 145 then
        way = "BEHIND"
    elseif turn < 0 then
        way = "LEFT"
    else
        way = "RIGHT"
    end
    -- Inside the circle on another floor the edge is no distance away: a joiner
    -- waiting to spawn under the hill read "-8 M ABOVE" (two PCs, 2026-11-07).
    return flat <= spot.r, math.max(0, math.floor((flat - spot.r) / CM_PER_METRE + 0.5)), way, level
end

--- The line for a player at `at` looking along `yaw`: the hill's distance and
--- bearing, or with a marker on the screen only what it cannot say, or nil.
function Hill.describe(hill, at, yaw, marked)
    local inside, metres, way, level = Hill.bearing(hill, at, yaw)
    if inside then
        if level == "" then return "ON THE HILL" end
        return "HILL" .. level
    end
    if marked then return nil end
    return string.format("HILL %d M %s%s", metres, way, level)
end

--- Where the screen marker for `spot` sits: above it, so it clears the wall.
function Hill.markerSpot(spot)
    return { x = spot.x, y = spot.y, z = spot.z + MARKER_HEIGHT_CM }
end

--- Whether `at` is on `spot`: in its circle and near its height.
function Hill.on(spot, at)
    local dx, dy = at.X - spot.x, at.Y - spot.y
    return dx * dx + dy * dy <= spot.r * spot.r and math.abs(at.Z - spot.z) <= HILL_HEIGHT_CM
end

--- Who has the hill: "empty", "contested", a team's name, or in free for all
--- "you" or "other". The script scores one player alone on the hill; two
--- players contest it, or in a team game both teams, and teammates never
--- contest each other. `players` lists { at, team, me } for each one alive;
--- team is nil in free for all.
function Hill.holder(hill, players)
    local on = {}
    for _, p in ipairs(players) do
        if Hill.on(hill, p.at) then on[#on + 1] = p end
    end
    if #on == 0 then return "empty" end
    if not Hill.CONTESTED_HILL_SCORES then
        for i = 2, #on do
            if not on[i].team or on[i].team ~= on[1].team then return "contested" end
        end
    end
    if on[1].team then return on[1].team end
    for _, p in ipairs(on) do
        if p.me then return "you" end
    end
    return "other"
end

--- Where a hill's wall panels stand: facing out, each a side of the polygon
--- around the scoring circle. `cx`, `cy` is the corner it starts from; the
--- next panel's is the one it ends at.
function Hill.panels(hill)
    local n = math.ceil(2 * math.pi * hill.r / PANEL_CM)
    n = math.max(MIN_PANELS, math.min(MAX_PANELS, n))
    local width = 2 * hill.r * math.tan(math.pi / n)
    local corner = hill.r / math.cos(math.pi / n)
    local panels = {}
    for i = 1, n do
        local angle = (i - 0.5) / n * 2 * math.pi
        local start = (i - 1) / n * 2 * math.pi
        panels[i] = {
            x = hill.x + hill.r * math.cos(angle),
            y = hill.y + hill.r * math.sin(angle),
            cx = hill.x + corner * math.cos(start),
            cy = hill.y + corner * math.sin(start),
            angle = angle,
            width = width,
        }
    end
    return panels
end

--- A closed ring of heights, each averaged with its neighbours. Panels turn at
--- their corners and their top edges part there, so sharp turns show as teeth.
function Hill.smooth(heights)
    local n = #heights
    local out = {}
    for i = 1, n do
        out[i] = (heights[(i - 2) % n + 1] + heights[i] + heights[i % n + 1]) / 3
    end
    return out
end

--- The ground under (x, y) near the hill's height: a trace from below a roof
--- that may stand over the hill, then from higher for a slope that rises past
--- that start (a trace starting underground hits nothing).
local function groundAt(world, x, y, z)
    local library = object("/Script/Engine.Default__KismetSystemLibrary")
    for _, above in ipairs(TRACE_STARTS_CM) do
        -- The shared hit table, emptied: a fresh {} a trace piled up.
        local hit = emptyHit()
        for k in pairs(IGNORE) do IGNORE[k] = nil end
        library:LineTraceSingle(world, { X = x, Y = y, Z = z + above },
            { X = x, Y = y, Z = z - TRACE_DEPTH_CM }, 0, false, IGNORE, 0, hit, true, NO_COLOUR, NO_COLOUR, 0)
        if hit.bBlockingHit then return math.max(hit.Location.Z, z - LOWEST_CM) end
    end
    return z
end

local function loadAsset(path)
    local library = object("/Script/Engine.Default__KismetSystemLibrary")
    local ok, asset = pcall(function()
        return library:LoadAsset_Blocking(library:Conv_SoftObjPathToSoftObjRef(library:MakeSoftObjectPath(path)))
    end)
    if ok and asset and asset:IsValid() then return asset end
end

local function vector(mid, name, r, g, b, a)
    mid:SetVectorParameterValue(FName(name), { R = r, G = g, B = b, A = a })
end

local function instance(world, master, name)
    local library = object("/Script/Engine.Default__KismetMaterialLibrary")
    local ok, mid = pcall(function()
        return library:CreateDynamicMaterialInstance(world, master, FName(name), 0)
    end)
    if ok and mid and mid:IsValid() then return mid end
end

local function plasma(world, master, name, brightness)
    local mid = instance(world, master, name)
    if not mid then return end
    vector(mid, "PlasmaBrightness", brightness, 0, 0, 0)
    vector(mid, "PlasmaNoiseA", NOISE_SCALE, 4, 0, 0)
    vector(mid, "PlasmaNoiseB", NOISE_SCALE * 0.7, -6, 0, 0)
    vector(mid, "PlasmaNoiseADir", 0.2, 0.1, 1, 0)
    vector(mid, "PlasmaNoiseBDir", -0.1, 0.2, 1, 0)
    return mid
end

local function materials(world, name)
    local fieldMaster, beaconMaster = loadAsset(FIELD_MASTER), loadAsset(BEACON_MASTER)
    if fieldMaster and beaconMaster then
        local field = instance(world, fieldMaster, name .. "_field")
        local beacon = instance(world, beaconMaster, name .. "_beacon")
        if field and beacon then return field, beacon, true end
    end
    for _, path in ipairs(PLASMA_MASTERS) do
        local master = loadAsset(path)
        if master then
            local field = plasma(world, master, name .. "_field", FALLBACK_WALL_BRIGHTNESS)
            local beacon = plasma(world, master, name .. "_beacon", FALLBACK_BEACON_BRIGHTNESS)
            if field and beacon then return field, beacon, false end
        end
    end
end

local function tint(mid, colours, holographic)
    local para, perp = colours.para, colours.perp
    vector(mid, holographic and "AccentColor" or "PlasmaParallel", para[1], para[2], para[3], 1)
    vector(mid, holographic and "FieldColor" or "PlasmaPerpendicular", perp[1], perp[2], perp[3], 1)
end

--- A panel's rotation: facing out, its bottom edge rising `rise` cm over its
--- width, so it meets both neighbours on a slope.
local function panelRotation(panel, rise)
    local library = object("/Script/Engine.Default__KismetMathLibrary")
    local slope = rise / panel.width
    local c, s = math.cos(panel.angle), math.sin(panel.angle)
    return library:MakeRotFromZX({ X = c, Y = s, Z = 0 }, { X = slope * s, Y = -slope * c, Z = 1 })
end

local function spawnPart(world, mesh, mid)
    local class = object("/Script/Engine.StaticMeshActor")
    local actor = world:SpawnActor(class, { X = 0, Y = 0, Z = 0 }, { Pitch = 0, Yaw = 0, Roll = 0 })
    local comp = actor.StaticMeshComponent
    -- SetStaticMesh refuses a registered Static component without a word.
    comp.Mobility = MOVABLE
    comp:SetStaticMesh(mesh)
    comp:SetCollisionEnabled(NO_COLLISION)
    comp:SetCastShadow(false)
    comp:SetMaterial(0, mid)
    return actor
end

local function build(pc)
    local library = object("/Script/UMG.Default__WidgetBlueprintLibrary")
    local w = library:Create(pc, object("/Script/UMG.UserWidget"), pc)
    local tree = w.WidgetTree
    local t = StaticConstructObject(object("/Script/UMG.TextBlock"), tree, FName("MJOLNIRHillText"))
    tree.RootWidget = t
    t:SetColorAndOpacity({ SpecifiedColor = { R = 1, G = 1, B = 1, A = 1 }, ColorUseRule = 0 })
    t:SetShadowOffset({ X = 1.5, Y = 1.5 })
    t:SetShadowColorAndOpacity({ R = 0, G = 0, B = 0, A = 0.9 })
    w:AddToViewport(41)
    w:SetAnchorsInViewport({ Minimum = { X = 0.5, Y = 0.135 }, Maximum = { X = 0.5, Y = 0.135 } })
    w:SetAlignmentInViewport({ X = 0.5, Y = 0 })
    return w, t
end

--- The world's drawing and the HUD's line for one marker. `name` names its
--- material instances.
function Hill.field(name)
    local self = { parts = {} }

    --- Hide, never remove: RemoveFromParent hung the game once.
    function self.hideLine()
        if self.widget and self.widget:IsValid() then
            pcall(function() self.widget:SetVisibility(COLLAPSED) end)
        end
    end

    --- Take the screen marker down.
    function self.unmark()
        if self.marker then self.marker.hide() end
    end

    --- Point the screen marker at `spot` (x, y, z) for `holder`, as `paint`
    --- takes it, with `icon` and `words`. True while there is a marker; false
    --- when it cannot be made, so the caller keeps the distance in its line.
    function self.mark(pc, spot, holder, icon, words, now)
        if not Hill.Waypoint then return false end
        self.marker = self.marker or Hill.Waypoint.new(Hill.log)
        local colours = COLOURS[holder] or COLOURS.empty
        return self.marker.point(pc, spot, colours.para, icon, words, holder == "contested", now)
    end

    --- Follow `actor` every frame: the screen marker's spot `up` cm above it
    --- and, when `beaconUp` is given, the beacon's foot that far above it.
    --- The update that marks it runs a few times a second, so without this a
    --- moving player's beacon and marker jumped behind them (#351). The actor
    --- is checked before each use, and nil stops following. `actor` can also
    --- be a function that gives the place ({ X, Y, Z }, or nil to stop): a
    --- player read from the simulation's roster (markers.lua).
    function self.track(actor, up, beaconUp)
        self.tracked, self.trackUp, self.beaconUp = actor, up or 0, beaconUp
    end

    --- Every frame: keep the marker on its spot.
    function self.frame(pc, now)
        local actor = self.tracked
        if actor then
            local ok, at = pcall(function()
                if type(actor) == "function" then return actor() end
                if actor:IsValid() then return actor:K2_GetActorLocation() end
            end)
            if ok and at then
                if self.marker then self.marker.aim(at.X, at.Y, at.Z + self.trackUp) end
                if self.beaconUp and self.drawn == PILLAR then pcall(self.pillarAt, at, self.beaconUp) end
            else
                self.tracked = nil
            end
        end
        if self.marker then self.marker.frame(pc, now) end
    end

    local function showPart(actor, shown)
        if actor and actor:IsValid() then actor:SetActorHiddenInGame(not shown) end
    end

    function self.hide()
        self.hideLine()
        self.unmark()
        self.drawn = nil
        pcall(function()
            for _, actor in pairs(self.parts) do showPart(actor, false) end
            showPart(self.beacon, false)
            showPart(self.anchor, false)
        end)
    end

    --- Forget what is drawn: a new match places everything again.
    function self.reset()
        self.drawn, self.retryAt, self.noWall = nil, nil, nil
    end

    local function noDrawing(now)
        self.hide()
        self.noWall = true
        self.retryAt = now + MATERIAL_RETRY_SECONDS
    end

    --- The materials, made again if the map change took them. False while
    --- neither pair can load.
    local function ready(world, now)
        if self.retryAt and now < self.retryAt then return false end
        if self.mid and self.mid:IsValid() and self.beaconMid and self.beaconMid:IsValid() then return true end
        self.mid, self.beaconMid, self.holographic = materials(world, name)
        self.drawn = nil
        self.colours, self.bright, self.state = nil, nil, nil
        if self.mid and self.beaconMid then return true end
        noDrawing(now)
        return false
    end

    --- Stand the wall round `spot`, whose identity is `key`. Actors are kept and
    --- moved: the map change that frees them also ends this object's match, and
    --- a new spot only re-places them.
    function self.draw(world, now, key, spot)
        if not ready(world, now) then return end
        if self.drawn == key and
           (not self.holographic or (self.anchor and self.anchor:IsValid())) then return end
        local plane = loadAsset(PLANE)
        local cylinder = loadAsset(CYLINDER)
        if not (plane and cylinder) then return noDrawing(now) end
        self.noWall, self.retryAt = nil, nil
        if self.holographic then
            for _, mid in ipairs({ self.mid, self.beaconMid }) do
                vector(mid, "FieldCenter", spot.x, spot.y, spot.z, spot.r)
                vector(mid, "FieldProfile", WALL_CM, WALL_SINK_CM, BEACON_CM, 0)
            end
        end
        local panels = Hill.panels(spot)
        local ground = {}
        for i, panel in ipairs(panels) do ground[i] = groundAt(world, panel.cx, panel.cy, spot.z) end
        ground = Hill.smooth(Hill.smooth(ground))
        for i, panel in ipairs(panels) do
            local actor = self.parts[i]
            if not (actor and actor:IsValid()) then
                actor = spawnPart(world, plane, self.mid)
                self.parts[i] = actor
            end
            -- A pooled actor can outlive its MID. Rebind on every placement.
            actor.StaticMeshComponent:SetMaterial(0, self.mid)
            local from, to = ground[i], ground[i % #panels + 1]
            local base = (from + to) / 2 - WALL_SINK_CM
            actor:K2_SetActorLocation({ X = panel.x, Y = panel.y, Z = base + WALL_CM / 2 }, false, emptyHit(), false)
            -- Not through SpawnActor: its rotation comes out wrong from UE4SS.
            actor:K2_SetActorRotation(panelRotation(panel, to - from), false)
            local length = math.sqrt(panel.width ^ 2 + (to - from) ^ 2)
            actor:SetActorScale3D({ X = WALL_CM / 100, Y = length / 100, Z = 1 })
            showPart(actor, true)
        end
        for i = #panels + 1, #self.parts do showPart(self.parts[i], false) end
        if not (self.beacon and self.beacon:IsValid()) then
            self.beacon = spawnPart(world, cylinder, self.beaconMid)
        end
        self.beacon.StaticMeshComponent:SetMaterial(0, self.beaconMid)
        self.beacon:K2_SetActorLocation({ X = spot.x, Y = spot.y, Z = spot.z + BEACON_CM / 2 }, false, emptyHit(), false)
        self.beacon:SetActorScale3D({ X = BEACON_RADIUS_CM / 50, Y = BEACON_RADIUS_CM / 50, Z = BEACON_CM / 100 })
        showPart(self.beacon, true)
        if self.holographic then
            if not (self.anchor and self.anchor:IsValid()) then
                self.anchor = spawnPart(world, plane, self.beaconMid)
            end
            self.anchor.StaticMeshComponent:SetMaterial(0, self.beaconMid)
            self.anchor:K2_SetActorLocation({
                X = spot.x, Y = spot.y, Z = groundAt(world, spot.x, spot.y, spot.z) + 5,
            }, false, emptyHit(), false)
            self.anchor:K2_SetActorRotation({ Pitch = 0, Yaw = 0, Roll = 0 }, false)
            self.anchor:SetActorScale3D({ X = 2, Y = 2, Z = 1 })
            showPart(self.anchor, true)
        else
            -- The dedicated shader masks this plane into broken rings. CE's
            -- fallback would expose the whole square.
            showPart(self.anchor, false)
        end
        self.drawn = key
    end

    --- Where a standing pillar is: its foot `up` cm above `at`.
    function self.pillarAt(at, up)
        local foot = at.Z + (up or 0)
        -- The shader measures its braid and foot from the centre.
        if self.holographic then vector(self.beaconMid, "FieldCenter", at.X, at.Y, foot, BEACON_RADIUS_CM) end
        self.beacon:K2_SetActorLocation({ X = at.X, Y = at.Y, Z = foot + BEACON_CM / 2 }, false, emptyHit(), false)
    end

    --- Take the pillar down and leave the rest (the line, the marker).
    function self.unpillar()
        if self.drawn == PILLAR then self.drawn = nil end
        pcall(showPart, self.beacon, false)
    end

    --- The beacon alone, standing `up` cm above `at` (a moving spot: X, Y, Z),
    --- no wall.
    function self.pillar(world, now, at, up)
        if not ready(world, now) then return end
        if not (self.beacon and self.beacon:IsValid()) then
            local cylinder = loadAsset(CYLINDER)
            if not cylinder then return noDrawing(now) end
            self.beacon = spawnPart(world, cylinder, self.beaconMid)
            self.drawn = nil
        end
        self.noWall, self.retryAt = nil, nil
        if self.drawn ~= PILLAR then
            self.beacon.StaticMeshComponent:SetMaterial(0, self.beaconMid)
            self.beacon:SetActorScale3D({ X = BEACON_RADIUS_CM / 50, Y = BEACON_RADIUS_CM / 50, Z = BEACON_CM / 100 })
            if self.holographic then vector(self.beaconMid, "FieldProfile", WALL_CM, WALL_SINK_CM, BEACON_CM, 0) end
            showPart(self.beacon, true)
            self.drawn = PILLAR
        end
        self.pillarAt(at, up)
    end

    --- Colour it for `holder` (as Hill.holder gives; "you", "empty" ...).
    function self.paint(holder, now)
        if not (self.mid and self.mid:IsValid() and self.beaconMid and self.beaconMid:IsValid()) then return end
        local colours = COLOURS[holder] or COLOURS.empty
        if colours ~= self.colours then
            self.colours = colours
            tint(self.mid, colours, self.holographic)
            tint(self.beaconMid, colours, self.holographic)
        end
        if self.holographic then
            if holder ~= self.state then
                self.state = holder
                local contested = holder == "contested" and 1 or 0
                vector(self.mid, "FieldState", contested, 1, 0, 0)
                vector(self.beaconMid, "FieldState", contested, 1, 0, 0)
            end
        else
            -- Older packs have no material-time pulse. Sample a slow,
            -- bounded sine instead of switching between bright flashes.
            local bright = holder == "contested" and (1 + 0.2 * math.sin(now * 2 * math.pi * 0.75)) or 1
            if bright ~= self.bright then
                self.bright = bright
                vector(self.mid, "PlasmaBrightness", FALLBACK_WALL_BRIGHTNESS * bright, 0, 0, 0)
                vector(self.beaconMid, "PlasmaBrightness", FALLBACK_BEACON_BRIGHTNESS * bright, 0, 0, 0)
            end
        end
    end

    --- The line's widget, made the first time and again if it went.
    function self.ensureLine(pc)
        if not (self.widget and self.widget:IsValid() and self.text and self.text:IsValid()) then
            self.widget, self.text = build(pc)
            self.line = nil
        end
    end

    --- Show `line` under the score.
    function self.say(line)
        if line ~= self.line then
            self.line = line
            self.text:SetText(FText(line))
        end
        self.widget:SetVisibility(VISIBLE_NO_HIT_TEST)
    end

    --- The controller's world, or nil once everything is hidden for want of one.
    function self.worldOf(pc)
        if not (pc and pc:IsValid()) then return self.hide() end
        local world = pc:GetWorld()
        if not (world and world:IsValid()) then return self.hide() end
        return world
    end

    return self
end

--- One match's marker. `read` gives a map's level file text.
function Hill.new(read)
    local self = Hill.field("mjolnir_hill")
    self.hills, self.live, self.next = {}, 1, 0

    function self.start(code)
        self.hills = Hill.parse(read(code))
        self.live, self.next = 1, 0
        self.reset()
        return #self.hills
    end

    function self.moved(place)
        if type(place) == "number" and self.hills[place + 1] then self.live = place + 1 end
    end

    function self.tick(now, pc, hidden, players)
        if #self.hills == 0 or now < self.next then return end
        self.next = now + EVERY
        if hidden then return self.hide() end
        pcall(function()
            local world = self.worldOf(pc)
            if not world then return end
            self.ensureLine(pc)
            local hill = self.hills[self.live]
            self.draw(world, now, self.live, hill)
            local holder = Hill.holder(hill, players and players() or {})
            self.paint(holder, now)
            local pawn = pc.Pawn
            if not (pawn and pawn:IsValid()) then
                self.unmark()
                return self.hideLine()
            end
            local at, yaw = pawn:K2_GetActorLocation(), pc:GetControlRotation().Yaw
            local inside, metres, _, level = Hill.bearing(hill, at, yaw)
            local marked = true
            if inside and level == "" then
                self.unmark()
            else
                marked = self.mark(pc, Hill.markerSpot(hill), holder, "Koth",
                    Hill.Waypoint and Hill.Waypoint.label(metres, level) or "", now)
            end
            local line = Hill.describe(hill, at, yaw, marked)
            if line == "ON THE HILL" and holder == "contested" then line = "HILL CONTESTED" end
            if line then self.say(line) else self.hideLine() end
        end)
    end

    return self
end

return Hill

-- MJOLNIR HUD: where King of the Hill's hill is.
--
-- No Megalo waypoint or boundary reaches Unreal (docs/game_modes.md, B4 and
-- B5), so a match shows nothing where the hill stands. The level file lists
-- the hills in rotation order (`koth_hills`: x, y, z and radius, Unreal cm,
-- tools/level/ce_objectives.py), the variant says which one is live
-- (`hill_moved`, value = its place in the rotation), and this draws one line
-- under the score, how far and which way, and the hill itself: a wall of CE's
-- plasma round the scoring cylinder and a beacon above it. Each game draws its
-- own, so it needs no replication, and the sim never sees these actors.

local Hill = {}

local COLLAPSED = 1 -- ESlateVisibility
local VISIBLE_NO_HIT_TEST = 4
local EVERY = 0.2 -- seconds between updates
local CM_PER_METRE = 100
local LEVEL_DIFFERENCE_CM = 300

-- M_CE_Plasma is in the CE runtime's trial masters (chunk 983). Without it the
-- hill has only its line.
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
local WALL_CM = 300
local WALL_SINK_CM = 80 -- below the ground, so a slope shows no gap
local LOWEST_CM = 250 -- a panel past a roof's edge stays near the roof
local TRACE_STARTS_CM = { 350, 1500 } -- the second for ground above the first
local TRACE_DEPTH_CM = 2500
local BEACON_RADIUS_CM = 60
local BEACON_CM = 7000
local BRIGHTNESS = 0.9
local NOISE_SCALE = 0.35
local CONTESTED_FLASH = 2 -- brightness on every other update
local HILL_HEIGHT_CM = 600 -- how far above or below still counts as on it
local COLOURS = {
    empty = { para = { 1, 0.8, 0.25 }, perp = { 1, 0.55, 0.08 } }, -- gold
    you = { para = { 0.45, 1, 0.9 }, perp = { 0.1, 0.8, 1 } }, -- cyan
    other = { para = { 1, 0.45, 0.2 }, perp = { 1, 0.15, 0.05 } }, -- orange-red
    contested = { para = { 0.95, 0.4, 1 }, perp = { 0.6, 0.1, 1 } }, -- violet
    Red = { para = { 1, 0.3, 0.25 }, perp = { 1, 0.08, 0.05 } },
    Blue = { para = { 0.35, 0.6, 1 }, perp = { 0.1, 0.3, 1 } },
}

--- The hills in a level file's text, in rotation order.
function Hill.parse(text)
    local list = type(text) == "string" and text:match('"koth_hills"%s*:%s*(%b[])') or nil
    local hills = {}
    if not list then return hills end
    local n = "([-%d.eE+]+)"
    local c = "%s*,%s*"
    for x, y, z, r in list:gmatch("%[%s*" .. n .. c .. n .. c .. n .. c .. n .. "%s*%]") do
        hills[#hills + 1] = { x = tonumber(x), y = tonumber(y), z = tonumber(z), r = tonumber(r) }
    end
    return hills
end

--- The line for a player at `at` looking along `yaw` (degrees): the hill's
--- distance and bearing, in the words a player would use.
function Hill.describe(hill, at, yaw)
    local dx, dy, dz = hill.x - at.X, hill.y - at.Y, hill.z - at.Z
    local flat = math.sqrt(dx * dx + dy * dy)
    local level = ""
    if dz > LEVEL_DIFFERENCE_CM then
        level = " ABOVE"
    elseif dz < -LEVEL_DIFFERENCE_CM then
        level = " BELOW"
    end
    if flat <= hill.r then
        if level == "" then return "ON THE HILL" end
        return "HILL" .. level
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
    return string.format("HILL %d M %s%s", math.floor((flat - hill.r) / CM_PER_METRE + 0.5), way, level)
end

--- Who has the hill: "empty", "contested", a team's name, or in free for all
--- "you" or "other". The script scores one player alone on the hill, and two
--- players contest it. `players` lists { at, team, me } for each one alive;
--- team is nil in free for all.
function Hill.holder(hill, players)
    local on = {}
    for _, p in ipairs(players) do
        local dx, dy = p.at.X - hill.x, p.at.Y - hill.y
        if dx * dx + dy * dy <= hill.r * hill.r and math.abs(p.at.Z - hill.z) <= HILL_HEIGHT_CM then
            on[#on + 1] = p
        end
    end
    if #on == 0 then return "empty" end
    for i = 2, #on do
        if not on[i].team or on[i].team ~= on[1].team then return "contested" end
    end
    if on[1].team then return on[1].team end
    return on[1].me and "you" or "other"
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
    local library = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
    local none = { R = 0, G = 0, B = 0, A = 0 }
    for _, above in ipairs(TRACE_STARTS_CM) do
        local hit = {}
        library:LineTraceSingle(world, { X = x, Y = y, Z = z + above },
            { X = x, Y = y, Z = z - TRACE_DEPTH_CM }, 0, false, {}, 0, hit, true, none, none, 0)
        if hit.bBlockingHit then return math.max(hit.Location.Z, z - LOWEST_CM) end
    end
    return z
end

local function loadAsset(path)
    local library = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
    local ok, asset = pcall(function()
        return library:LoadAsset_Blocking(library:Conv_SoftObjPathToSoftObjRef(library:MakeSoftObjectPath(path)))
    end)
    if ok and asset and asset:IsValid() then return asset end
end

local function plasma(world)
    local library = StaticFindObject("/Script/Engine.Default__KismetMaterialLibrary")
    for _, path in ipairs(PLASMA_MASTERS) do
        local master = loadAsset(path)
        if master then
            local mid = library:CreateDynamicMaterialInstance(world, master, FName("mjolnir_hill"), 0)
            local function set(name, r, g, b, a)
                mid:SetVectorParameterValue(FName(name), { R = r, G = g, B = b, A = a })
            end
            set("PlasmaBrightness", BRIGHTNESS, 0, 0, 0)
            set("PlasmaNoiseA", NOISE_SCALE, 4, 0, 0)
            set("PlasmaNoiseB", NOISE_SCALE * 0.7, -6, 0, 0)
            set("PlasmaNoiseADir", 0.2, 0.1, 1, 0)
            set("PlasmaNoiseBDir", -0.1, 0.2, 1, 0)
            return mid
        end
    end
end

local function tint(mid, colours)
    local para, perp = colours.para, colours.perp
    mid:SetVectorParameterValue(FName("PlasmaParallel"), { R = para[1], G = para[2], B = para[3], A = 1 })
    mid:SetVectorParameterValue(FName("PlasmaPerpendicular"), { R = perp[1], G = perp[2], B = perp[3], A = 1 })
end

--- A panel's rotation: facing out, its bottom edge rising `rise` cm over its
--- width, so it meets both neighbours on a slope.
local function panelRotation(panel, rise)
    local library = StaticFindObject("/Script/Engine.Default__KismetMathLibrary")
    local slope = rise / panel.width
    local c, s = math.cos(panel.angle), math.sin(panel.angle)
    return library:MakeRotFromZX({ X = c, Y = s, Z = 0 }, { X = slope * s, Y = -slope * c, Z = 1 })
end

local function spawnPart(world, mesh, mid)
    local class = StaticFindObject("/Script/Engine.StaticMeshActor")
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
    local library = StaticFindObject("/Script/UMG.Default__WidgetBlueprintLibrary")
    local w = library:Create(pc, StaticFindObject("/Script/UMG.UserWidget"), pc)
    local tree = w.WidgetTree
    local t = StaticConstructObject(StaticFindObject("/Script/UMG.TextBlock"), tree, FName("MJOLNIRHillText"))
    tree.RootWidget = t
    t:SetColorAndOpacity({ SpecifiedColor = { R = 1, G = 1, B = 1, A = 1 }, ColorUseRule = 0 })
    t:SetShadowOffset({ X = 1.5, Y = 1.5 })
    t:SetShadowColorAndOpacity({ R = 0, G = 0, B = 0, A = 0.9 })
    w:AddToViewport(41)
    w:SetAnchorsInViewport({ Minimum = { X = 0.5, Y = 0.135 }, Maximum = { X = 0.5, Y = 0.135 } })
    w:SetAlignmentInViewport({ X = 0.5, Y = 0 })
    return w, t
end

--- One match's marker. `read` gives a map's level file text.
function Hill.new(read)
    local self = { hills = {}, live = 1, next = 0, parts = {} }

    function self.start(code)
        self.hills = Hill.parse(read(code))
        self.live, self.next = 1, 0
        return #self.hills
    end

    function self.moved(place)
        if type(place) == "number" and self.hills[place + 1] then self.live = place + 1 end
    end

    --- Hide, never remove: RemoveFromParent hung the game once.
    function self.hideLine()
        if self.widget and self.widget:IsValid() then
            pcall(function() self.widget:SetVisibility(COLLAPSED) end)
        end
    end

    local function showPart(actor, shown)
        if actor and actor:IsValid() then actor:SetActorHiddenInGame(not shown) end
    end

    function self.hide()
        self.hideLine()
        self.drawn = nil
        pcall(function()
            for _, actor in pairs(self.parts) do showPart(actor, false) end
            showPart(self.beacon, false)
        end)
    end

    --- Stand the wall round the live hill. Actors are kept and moved: the map
    --- change that frees them also ends this object's match, and a new hill
    --- only re-places them.
    local function draw(pc)
        local world = pc:GetWorld()
        if not (self.mid and self.mid:IsValid()) then
            self.mid = plasma(world)
            self.drawn = nil
            self.colours, self.bright = nil, nil
            if not self.mid then
                self.noWall = true
                return
            end
        end
        if self.drawn == self.live then return end
        local hill = self.hills[self.live]
        local plane = loadAsset(PLANE)
        local cylinder = loadAsset(CYLINDER)
        if not (plane and cylinder) then
            self.noWall = true
            return
        end
        local panels = Hill.panels(hill)
        local ground = {}
        for i, panel in ipairs(panels) do ground[i] = groundAt(world, panel.cx, panel.cy, hill.z) end
        ground = Hill.smooth(Hill.smooth(ground))
        for i, panel in ipairs(panels) do
            local actor = self.parts[i]
            if not (actor and actor:IsValid()) then
                actor = spawnPart(world, plane, self.mid)
                self.parts[i] = actor
            end
            local from, to = ground[i], ground[i % #panels + 1]
            local base = (from + to) / 2 - WALL_SINK_CM
            actor:K2_SetActorLocation({ X = panel.x, Y = panel.y, Z = base + WALL_CM / 2 }, false, {}, false)
            -- Not through SpawnActor: its rotation comes out wrong from UE4SS.
            actor:K2_SetActorRotation(panelRotation(panel, to - from), false)
            local length = math.sqrt(panel.width ^ 2 + (to - from) ^ 2)
            actor:SetActorScale3D({ X = WALL_CM / 100, Y = length / 100, Z = 1 })
            showPart(actor, true)
        end
        for i = #panels + 1, #self.parts do showPart(self.parts[i], false) end
        if not (self.beacon and self.beacon:IsValid()) then
            self.beacon = spawnPart(world, cylinder, self.mid)
        end
        self.beacon:K2_SetActorLocation({ X = hill.x, Y = hill.y, Z = hill.z + BEACON_CM / 2 }, false, {}, false)
        self.beacon:SetActorScale3D({ X = BEACON_RADIUS_CM / 50, Y = BEACON_RADIUS_CM / 50, Z = BEACON_CM / 100 })
        showPart(self.beacon, true)
        self.drawn = self.live
    end

    function self.tick(now, pc, hidden, players)
        if #self.hills == 0 or now < self.next then return end
        self.next = now + EVERY
        if hidden then return self.hide() end
        pcall(function()
            if not (self.widget and self.widget:IsValid() and self.text and self.text:IsValid()) then
                self.widget, self.text = build(pc)
            end
            if not self.noWall then draw(pc) end
            local hill = self.hills[self.live]
            local holder = Hill.holder(hill, players and players() or {})
            if self.mid and self.mid:IsValid() then
                local colours = COLOURS[holder] or COLOURS.empty
                if colours ~= self.colours then
                    self.colours = colours
                    tint(self.mid, colours)
                end
                local bright = BRIGHTNESS
                self.flash = holder == "contested" and not self.flash
                if self.flash then bright = CONTESTED_FLASH end
                if bright ~= self.bright then
                    self.bright = bright
                    self.mid:SetVectorParameterValue(FName("PlasmaBrightness"), { R = bright, G = 0, B = 0, A = 0 })
                end
            end
            local pawn = pc.Pawn
            if not (pawn and pawn:IsValid()) then return self.hideLine() end
            local line = Hill.describe(hill, pawn:K2_GetActorLocation(), pc:GetControlRotation().Yaw)
            if line == "ON THE HILL" and holder == "contested" then line = "HILL CONTESTED" end
            if line ~= self.line then
                self.line = line
                self.text:SetText(FText(line))
            end
            self.widget:SetVisibility(VISIBLE_NO_HIT_TEST)
        end)
    end

    return self
end

return Hill

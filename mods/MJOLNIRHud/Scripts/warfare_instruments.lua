-- Pelican pilotage display. Native samples use metres per second, +Y north.
-- The broken diamond follows measured travel through the view, including sink.
local Flight = {}
local CYAN = {R=.39,G=.91,B=1,A=1}
local WHITE = {R=.92,G=.97,B=1,A=1}
local MUTED = {R=.60,G=.79,B=.83,A=1}
local AMBER = {R=1,G=.75,B=.29,A=1}
local BACK = {R=.017,G=.055,B=.073,A=.79}
local VISIBLE, HIDDEN = 3, 1 -- HitTestInvisible, Collapsed

function Flight.readout(f, clearance)
    local speed, vertical, track, height = "—", "—", "—", "—"
    if f then
        local horizontal = f.vx*f.vx + f.vy*f.vy
        speed = tostring(math.floor(math.sqrt(horizontal + f.vz*f.vz)*3.6 + .5))
        vertical = tostring(math.floor(math.abs(f.vz) + .5))
        if horizontal >= 1 then
            local heading = math.floor(math.deg(math.atan(f.vx, f.vy)) + .5) % 360
            local names = {"N","NE","E","SE","S","SW","W","NW"}
            track = string.format("%03d° %s", heading, names[math.floor((heading+22.5)/45)%8+1])
        end
    end
    if clearance then height = tostring(math.floor(clearance + .5)) end
    return speed, vertical, track, height, f and f.vz >= .5 and "CLIMB" or "SINK"
end

local function valid(w) return w and w:IsValid() end

local function canvasWidget(pc, name, width, height)
    local lib = StaticFindObject("/Script/UMG.Default__WidgetBlueprintLibrary")
    local w = lib:Create(pc, StaticFindObject("/Script/UMG.UserWidget"), pc)
    local tree = w.WidgetTree
    local c = StaticConstructObject(StaticFindObject("/Script/UMG.CanvasPanel"), tree, FName(name))
    tree.RootWidget = c
    w:AddToViewport(41)
    w:SetDesiredSizeInViewport({X=width,Y=height})
    w:SetVisibility(HIDDEN)
    return {widget=w, tree=tree, canvas=c}
end

local function child(root, class, name, x, y, width, height)
    local w = StaticConstructObject(StaticFindObject("/Script/UMG."..class), root.tree, FName(name))
    local slot = root.canvas:AddChildToCanvas(w)
    slot:SetPosition({X=x,Y=y})
    if width then slot:SetSize({X=width,Y=height}) else slot:SetAutoSize(true) end
    return w
end

local function strip(root, name, x, y, width, height, color, angle)
    local w = child(root,"Image",name,x,y,width,height)
    w:SetColorAndOpacity(color)
    if angle then w:SetRenderTransformAngle(angle) end
end

local function label(root, name, x, y, scale, color, initial)
    local t = child(root,"TextBlock",name,x,y)
    t:SetRenderTransformPivot({X=0,Y=0})
    t:SetRenderScale({X=scale,Y=scale})
    t:SetColorAndOpacity({SpecifiedColor=color,ColorUseRule=0})
    t:SetShadowOffset({X=1,Y=1})
    t:SetShadowColorAndOpacity({R=0,G=0,B=0,A=.68})
    if initial then t:SetText(FText(initial)) end
    return t
end

local function panel(pc)
    local p = canvasWidget(pc,"PWRFlightInstruments",430,262)
    p.widget:SetAnchorsInViewport({Minimum={X=.055,Y=.225},Maximum={X=.055,Y=.225}})
    p.widget:SetAlignmentInViewport({X=0,Y=0})
    p.canvas:SetRenderTransformPivot({X=0,Y=0})
    p.canvas:SetRenderScale({X=1.28,Y=1.28})
    strip(p,"Glass",0,0,430,262,BACK)
    strip(p,"LeadingEdge",0,0,5,262,CYAN)
    strip(p,"Divider",20,48,390,2,{R=.39,G=.91,B=1,A=.35})
    p.mode = label(p,"Mode",20,8,1.18,CYAN)
    p.track = label(p,"Track",235,10,.93,MUTED)
    label(p,"SpeedTitle",20,56,.85,MUTED,"SPEED / KM/H")
    p.sinkTitle = label(p,"SinkTitle",226,56,.85,MUTED)
    p.speed = label(p,"Speed",19,82,1.95,WHITE)
    p.sink = label(p,"Sink",225,82,1.95,WHITE)
    p.terrain = label(p,"Terrain",20,142,.96,MUTED)
    p.help = label(p,"Control",20,180,1.04,WHITE)
    -- During insertion: when the zones open (blank otherwise).
    p.opens = label(p,"Opens",20,218,1.04,AMBER)
    return p
end

local function flightMarker(pc)
    local r = canvasWidget(pc,"PWRFlightPath",86,50)
    r.widget:SetAlignmentInViewport({X=.5,Y=.5})
    -- Fine cyan wings and a hollow lozenge leave the terrain visible.
    strip(r,"WingLeft",2,23,28,4,CYAN)
    strip(r,"WingRight",56,23,28,4,CYAN)
    strip(r,"UpperLeft",31,18,15,3,CYAN,-45)
    strip(r,"UpperRight",41,18,15,3,CYAN,45)
    strip(r,"LowerLeft",31,28,15,3,CYAN,45)
    strip(r,"LowerRight",41,28,15,3,CYAN,-45)
    return r.widget
end

function Flight.new()
    local self = {}
    local p, marker, owner, velocity, last, markerShown
    local lastFrame, worldPoint, pixel, size, spare = 0, {}, {}, {}, {}
    local function markerVisible(on)
        if markerShown ~= on and valid(marker) then
            marker:SetVisibility(on and VISIBLE or HIDDEN)
            markerShown = on
        end
    end
    function self.hide()
        if last and p and valid(p.widget) then p.widget:SetVisibility(HIDDEN) end
        markerVisible(false)
        velocity, last = nil, nil
    end
    --- `opens`: whole seconds until the zones open (insertion), or nil.
    function self.update(pc, stage, f, clearance, jump, brake, opens)
        if owner ~= pc:GetAddress() or not p or not valid(p.widget) then
            self.hide()
            p, owner, marker = panel(pc), pc:GetAddress(), nil
            markerShown = nil
        end
        local speed, sink, track, height, vertical = Flight.readout(f,clearance)
        local mode = stage==3 and "FREEFALL" or f and f.brake and "BRAKING" or "GLIDE"
        local help = stage==3 and ((jump or "SPACE").."  DEPLOY") or ("HOLD "..(brake or "SHIFT").."  BRAKE")
        local content = {mode=mode,track="TRK  "..track,speed=speed,sink=sink,sinkTitle=vertical.." / M/S",
            terrain="TERRAIN CLR   "..height.." M",help=help,
            opens=opens and string.format("ZONES OPEN   %d:%02d",math.floor(opens/60),opens%60) or ""}
        for name,value in pairs(content) do
            if not last or last[name]~=value then p[name]:SetText(FText(value)) end
        end
        if not last or last.mode ~= mode then
            p.mode:SetColorAndOpacity({SpecifiedColor=mode=="BRAKING" and AMBER or CYAN,ColorUseRule=0})
        end
        if not last then p.widget:SetVisibility(VISIBLE) end
        last, velocity = content, f
        if not f then markerVisible(false) end
        return true
    end
    function self.frame(pc, now)
        if not velocity or now < lastFrame or pc:GetAddress() ~= owner then return end
        lastFrame = now + 1/24
        local camera = pc.PlayerCameraManager
        if not valid(camera) then markerVisible(false); return end
        local at = camera:GetCameraLocation()
        -- Use a point on the measured travel ray. Blam +Y maps to Unreal -Y.
        worldPoint.X = at.X + velocity.vx * 100
        worldPoint.Y = at.Y - velocity.vy * 100
        worldPoint.Z = at.Z + velocity.vz * 100
        for k in pairs(pixel) do pixel[k]=nil end
        local projected = pc:ProjectWorldLocationToScreen(worldPoint,pixel,false)
        if not projected then markerVisible(false); return end
        for k in pairs(size) do size[k]=nil end
        for k in pairs(spare) do spare[k]=nil end
        pc:GetViewportSize(size,spare)
        local x,y,w,h = pixel.X,pixel.Y,size.SizeX,size.SizeY
        if not (x and y and w and h and x>w*.07 and x<w*.93 and y>h*.17 and y<h*.87)
            or (x-w*.5)^2+(y-h*.5)^2 < (h*.035)^2 then
            markerVisible(false); return
        end
        if not valid(marker) then marker=flightMarker(pc); markerShown=nil end
        marker:SetPositionInViewport(pixel,true)
        markerVisible(true)
    end
    return self
end

return Flight

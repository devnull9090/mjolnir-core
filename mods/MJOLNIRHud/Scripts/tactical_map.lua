-- PWR map presentation only. Native code collects and filters the simulation
-- snapshot. No actor scans, movement writes, polling while closed, or UI focus.
local Map = {}
local ROOT = "/Game/MJOLNIR/TacticalMap/"
local CLASS = "/Game/MJOLNIR/UI/WBP_MJOLNIRTacticalMap.WBP_MJOLNIRTacticalMap_C"
local KINDS = { self=true, player=true, hog=true, tank=true, banshee=true, pelican=true, base=true, capture=true }
local LIMITS = {
    ready={0,1}, status={-32,32}, tick={0,2147483647}, sampled_ms={0,9007199254740991},
    layout={0,32767}, team={-1,7}, local_index={-1,15}, local_user={-1,3}, phase={0,3},
}
local CYAN = {R=.35,G=.86,B=.93,A=1}
local WHITE = {R=.9,G=.95,B=.96,A=1}
local YELLOW = {R=1,G=.85,B=.35,A=1}
local RED = {R=1,G=.36,B=.3,A=1}
local BLUE = {R=.3,G=.65,B=1,A=1}
local MUTED = {R=.55,G=.66,B=.69,A=1}

local function number(word, low, high, whole)
    if type(word) ~= "string" or (whole and not word:match("^%-?%d+$")) then return nil end
    local n = tonumber(word)
    if not n or n ~= n or n < low or n > high then return nil end
    return n
end

function Map.parse(raw)
    if type(raw) ~= "string" or #raw > 16384 or raw:sub(-1) ~= "\n" then return nil end
    raw = raw:gsub("\r\n", "\n")
    if raw:sub(1, 14) ~= "warfare-map 1\n" then return nil end
    local s, ids, ended = {markers={}}, {}, false
    for line in raw:sub(15):gmatch("([^\n]+)\n") do
        if ended then return nil end
        local w = {}
        for word in line:gmatch("%S+") do w[#w+1] = word end
        local key = table.remove(w, 1)
        if key ~= "marker" and s[key] ~= nil then return nil end
        if LIMITS[key] then
            if #w ~= 1 then return nil end
            s[key] = number(w[1], LIMITS[key][1], LIMITS[key][2], true)
            if s[key] == nil then return nil end
        elseif key == "instance" then
            if #w ~= 1 or not w[1]:match("^%d+$") or #w[1] > 20 then return nil end
            s.instance = w[1]
        elseif key == "bounds" then
            if #w ~= 4 then return nil end
            s.bounds = {}
            for i, expected in ipairs({-1000,-1000,1000,1000}) do
                s.bounds[i] = number(w[i], expected, expected, false)
                if not s.bounds[i] then return nil end
            end
        elseif key == "score" then
            if #w ~= 2 then return nil end
            s.score = {number(w[1],0,32767,true), number(w[2],0,32767,true)}
            if s.score[1] == nil or s.score[2] == nil then return nil end
        elseif key == "marker" then
            if #w ~= 6 or not KINDS[w[1]] or #s.markers >= 64 then return nil end
            local m = {kind=w[1], id=number(w[2],0,4294967295,true), team=number(w[3],-1,7,true),
                x=number(w[4],-100000,100000), y=number(w[5],-100000,100000), heading=number(w[6],-360,360)}
            if not (m.id and m.team and m.x and m.y and m.heading) then return nil end
            if (m.kind == "base" and m.id > 1) or (m.kind == "capture" and m.id > 2) then return nil end
            local id = m.kind .. ":" .. w[2]
            if ids[id] then return nil end
            ids[id] = true
            s.markers[#s.markers+1] = m
        elseif key == "end" then
            if #w ~= 1 or number(w[1],0,64,true) ~= #s.markers then return nil end
            ended = true
        else return nil end
    end
    if not ended or not (s.instance and s.bounds and s.score) then return nil end
    for key in pairs(LIMITS) do if s[key] == nil then return nil end end
    if s.ready == 1 and (s.status ~= 2 or s.instance == "0" or s.sampled_ms == 0
        or s.layout ~= 3 or s.team < 0 or s.team > 1 or s.local_index < 0 or s.local_user < 0) then return nil end
    -- Defence in depth: enemy players/occupied vehicles never reach the UI.
    local selves = 0
    for _, m in ipairs(s.markers) do
        if m.kind ~= "base" and m.kind ~= "capture" and m.team ~= -1 and m.team ~= s.team then return nil end
        if (m.kind == "self" or m.kind == "player" or m.kind == "pelican") and m.team ~= s.team then return nil end
        if m.kind == "self" then
            selves = selves + 1
            if selves > 1 or m.id % 65536 ~= s.local_index then return nil end
        end
    end
    return s
end

function Map.project(x, y, view)
    -- Exact authored metres. UE's Y-axis reflection is already removed by the
    -- native simulation; north is +Y and must map toward the top of the image.
    if x < -1000 or x > 1000 or y < -1000 or y > 1000 then return nil end
    local zoom, cx, cy = view and view.zoom or 1, view and view.x or 0, view and view.y or 0
    local half = 1000 / zoom
    if math.abs(x-cx)>half or math.abs(y-cy)>half then return nil end
    return 1030 + (x-cx)*.55*zoom, 760 - (y-cy)*.55*zoom
end

local function valid(w) return w and w:IsValid() end
local function text(w, value) w:SetText(FText(value)) end

local function teammateLabel(match, id)
    local p=match.players[id % 65536]
    local label=p and (p.display or p.name) or "TEAMMATE"
    return tostring(label):gsub("[%c]",""):sub(1,20)
end

local function teammateNames(s, match)
    -- Only the native snapshot's already team-filtered player IDs may supply
    -- labels. Do not enumerate the roster or reveal otherwise hidden names.
    local names={}
    if s then
        for _,m in ipairs(s.markers) do
            if m.kind=="player" then
                local label=teammateLabel(match,m.id)
                names[#names+1]=tostring(m.id)..":"..#label..":"..label
                if #names==16 then break end
            end
        end
    end
    return table.concat(names,"|")
end

local function sameContent(a,b)
    if not a or not b then return a==b end
    if a.team~=b.team or a.phase~=b.phase or a.score[1]~=b.score[1] or a.score[2]~=b.score[2]
        or #a.markers~=#b.markers then return false end
    for i,m in ipairs(a.markers) do
        local n=b.markers[i]
        if m.kind~=n.kind or m.id~=n.id or m.team~=n.team or m.x~=n.x or m.y~=n.y or m.heading~=n.heading then return false end
    end
    return true
end

function Map.new(deps)
    local self = {open=false, next=0, textures={}, items={}, zoom=1}
    local pending, snapshot, refreshed, lastKey, lastZoom

    function self.close(release)
        if valid(self.widget) then self.widget:SetVisibility(1) end
        self.open, pending, snapshot, refreshed, self.drawn, self.visible = false, nil, nil, nil, false, false
        if release then self.widget, self.items, self.match, self.zoom = nil, {}, nil, 1 end
    end

    function self.cycleZoom()
        if not self.open or deps.blocked() or deps.hidden() then return end
        local t=deps.now()
        if lastZoom and t-lastZoom<.25 then return end
        lastZoom=t
        self.zoom=self.zoom==1 and 2 or self.zoom==2 and 4 or 1
        self.next=0
    end

    function self.accept(s, now, instance, localIndex)
        if not s or s.ready ~= 1 or s.phase == 3 or s.instance ~= instance or s.local_index ~= localIndex then
            snapshot, pending, refreshed = nil, nil, nil
            return false
        end
        local previous = snapshot or pending
        if not previous or previous.instance ~= s.instance or previous.team ~= s.team
            or previous.local_index ~= s.local_index then
            snapshot, pending, refreshed = nil, s, now
            return false
        end
        if s.tick > previous.tick and s.sampled_ms > previous.sampled_ms then
            if not snapshot and now - refreshed > 2 then pending, refreshed = s, now; return false end
            snapshot, pending, refreshed = s, nil, now
            return true
        end
        if refreshed and now - refreshed > 2 then snapshot, pending, refreshed = nil, s, now end
        return false
    end

    function self.toggle()
        if deps.blocked() then return end
        local match = deps.match()
        if not match or match.code ~= "PWR" or match.variant ~= "warfare" or match.over or deps.hidden() then return end
        local t = deps.now()
        if lastKey and t - lastKey < .25 then return end
        lastKey = t
        if self.open then self.close(); return end
        if self.match ~= match then self.close(true); self.match = match end
        self.open, self.next = true, 0
    end

    local function ensure()
        if valid(self.widget) then return self.widget end
        self.widget = deps.createWidget(CLASS, 44)
        if not valid(self.widget) then return nil end
        local w = self.widget
        for i=0,63 do self.items[i+1] = {icon=w["Mark"..i],label=w["Label"..i]} end
        local ksl = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
        for kind in pairs(KINDS) do
            local name = kind == "self" and "player" or kind
            if not self.textures[name] or not self.textures[name]:IsValid() then
                self.textures[name] = ksl:LoadAsset_Blocking(ksl:Conv_SoftObjPathToSoftObjRef(
                    ksl:MakeSoftObjectPath(ROOT .. "T_PWR_" .. name .. ".T_PWR_" .. name)))
            end
        end
        return w
    end

    local function blank(w)
        for _, item in ipairs(self.items) do item.icon:SetVisibility(1); item.label:SetVisibility(1) end
        text(w.RedScore, "RED   --"); text(w.BlueScore, "BLUE  --")
        text(w.Position, ""); text(w.TeamStatus, "")
        for i=0,2 do text(w["Site"..i], string.char(65+i) .. "   /   WAITING") end
    end

    local function draw(w, s, match)
        blank(w)
        local view={zoom=self.zoom,x=0,y=0}
        if s and self.zoom>1 then
            for _,m in ipairs(s.markers) do if m.kind=="self" then
                local limit=1000-1000/self.zoom
                view.x=math.max(-limit,math.min(limit,m.x)); view.y=math.max(-limit,math.min(limit,m.y))
                break
            end end
        end
        local imageSize=1100*self.zoom
        w.Overview.Slot:SetSize({X=imageSize,Y=imageSize})
        w.Overview.Slot:SetPosition({X=550-(view.x+1000)/2000*imageSize,Y=550-(1000-view.y)/2000*imageSize})
        for i=1,4 do w["GridX"..i]:SetVisibility(self.zoom==1 and 3 or 1);w["GridY"..i]:SetVisibility(self.zoom==1 and 3 or 1) end
        for i=0,4 do w["GridCol"..i]:SetVisibility(self.zoom==1 and 3 or 1);w["GridRow"..i]:SetVisibility(self.zoom==1 and 3 or 1) end
        text(w.Scale,self.zoom==1 and "NORTH UP  /  2 KM x 2 KM" or string.format("FOLLOW %dx  /  %d M ACROSS",self.zoom,2000/self.zoom))
        if not s then text(w.LiveStatus, "ACQUIRING FIELD TELEMETRY"); return end
        text(w.LiveStatus, ({[0]="WARMUP",[1]="PELICAN INSERTION",[2]="LIVE FIELD TELEMETRY"})[s.phase])
        text(w.RedScore, string.format("RED   %03d",s.score[1]))
        text(w.BlueScore, string.format("BLUE  %03d",s.score[2]))
        text(w.TeamStatus, s.team == 0 and "RED TEAM" or "BLUE TEAM")
        for i,m in ipairs(s.markers) do
            local x,y = Map.project(m.x,m.y,view)
            if m.kind == "capture" and m.id <= 2 then
                local owner = m.team == 0 and "RED" or m.team == 1 and "BLUE" or "NEUTRAL"
                text(w["Site"..m.id], string.char(65+m.id) .. "   /   " .. owner)
                w["Site"..m.id]:SetColorAndOpacity({SpecifiedColor=m.team==0 and RED or m.team==1 and BLUE or MUTED,ColorUseRule=0})
            end
            if m.kind == "self" then text(w.Position, string.format("GRID %s%d  /  %.0f, %.0f M",
                string.char(65+math.max(0,math.min(4,math.floor((m.x+1000)/400)))),
                1+math.max(0,math.min(4,math.floor((1000-m.y)/400))),m.x,m.y)) end
            if x then
                local item = self.items[i]
                local iconKind = m.kind == "self" and "player" or m.kind
                local size = (m.kind == "capture" or m.kind == "base") and 42 or m.kind == "self" and 36 or 30
                local color = m.kind == "self" and YELLOW or (m.kind=="base" or m.kind=="capture")
                    and (m.team==0 and RED or m.team==1 and BLUE or MUTED) or m.team==-1 and WHITE or CYAN
                if item.kind ~= iconKind then item.icon:SetBrushFromTexture(self.textures[iconKind],false); item.kind=iconKind end
                item.icon.Slot:SetPosition({X=x-480-size/2,Y=y-210-size/2})
                item.icon.Slot:SetSize({X=size,Y=size})
                item.icon.Slot:SetZOrder(m.kind=="self" and 1000 or m.kind=="player" and 500 or 200)
                item.label.Slot:SetZOrder(m.kind=="self" and 1001 or 501)
                item.icon:SetColorAndOpacity(color)
                item.icon:SetRenderTransformAngle((m.kind=="base" or m.kind=="capture") and 0 or (90-m.heading))
                item.icon:SetVisibility(3)
                local label = ""
                if m.kind == "self" then label="YOU"
                elseif m.kind == "base" then label=m.team==0 and "RED BASE" or "BLUE BASE"
                elseif m.kind == "capture" then label=string.char(65+m.id)
                elseif m.kind == "player" then
                    label=teammateLabel(match,m.id)
                end
                if label ~= "" then
                    text(item.label,label)
                    item.label.Slot:SetPosition({X=math.min(x+size/2+5,1340)-480,Y=(m.kind=="base" and y-42 or y-13)-210})
                    item.label:SetColorAndOpacity({SpecifiedColor=color,ColorUseRule=0})
                    item.label:SetVisibility(3)
                end
            end
        end
    end

    function self.tick()
        if not self.open then return end
        local match, t = deps.match(), deps.now()
        if not match or match ~= self.match or match.code ~= "PWR" or match.variant ~= "warfare" then
            self.close(true); return
        end
        -- A chat/pause/HUD gate is temporary. Keep the collapsed pool for the
        -- same world instead of attaching another widget on every reopening.
        if match.over or deps.hidden() or deps.blocked() then self.close(false); return end
        if t < self.next then return end
        self.next = t + .2
        local w = ensure()
        if not w then return end
        local s
        if deps.pump then deps.pump(); s=Map.parse(deps.read()) end
        local accepted = match.warfare and match.warfare.snapshot
        self.accept(s,t,accepted and accepted.instance,deps.localIndex())
        -- Native timestamps advance even when nothing visible moved. Avoid
        -- re-invalidating the entire Slate tree for an identical map frame.
        -- HUD identity can resolve independently of native pose telemetry.
        local names=teammateNames(snapshot,match)
        if not self.drawn or self.lastZoom~=self.zoom or names~=self.lastNames or not sameContent(snapshot,self.lastDraw) then
            draw(w,snapshot,match)
            self.drawn,self.lastDraw,self.lastZoom,self.lastNames=true,snapshot,self.zoom,names
        end
        if not self.visible then w:SetVisibility(3);self.visible=true end
    end

    function self.bind()
        if RegisterKeyBind then RegisterKeyBind(0x4D,{},function()
            local ok,err=pcall(self.toggle); if not ok then deps.log("tactical map key: "..tostring(err)) end
        end)
        RegisterKeyBind(0x4E,{},function()
            local ok,err=pcall(self.cycleZoom); if not ok then deps.log("tactical map zoom: "..tostring(err)) end
        end) end
    end
    return self
end
return Map

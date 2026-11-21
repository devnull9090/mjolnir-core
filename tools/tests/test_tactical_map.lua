local Map = dofile("mods/MJOLNIRHud/Scripts/tactical_map.lua")
local checks=0
local function eq(a,b,label)
    checks=checks+1
    assert(a==b,(label or "value")..": "..tostring(a).." ~= "..tostring(b))
end
local function near(a,b,label)
    checks=checks+1
    assert(type(a)=="number" and math.abs(a-b)<1e-9,(label or "float")..": "..tostring(a).." ~= "..tostring(b))
end
local function raw(tick,extra,instance)
    return string.format("warfare-map 1\nready 1\nstatus 2\ninstance %s\ntick %d\nsampled_ms %d\nlayout 3\nteam 0\nlocal_index 0\nlocal_user 0\nphase 2\nscore 10 20\nbounds -1000 -1000 1000 1000\nmarker self 65536 0 -584 -130 90\n%s\nend %d\n",instance or "18446744073709551614",tick,10000+tick*16,extra or "marker capture 0 -1 0 0 0",2)
end
local s=assert(Map.parse(raw(1)))
eq(s.instance,"18446744073709551614","uint64 exact")
eq(s.markers[1].x,-584)
eq(Map.parse(raw(1):sub(1,-2)),nil,"partial write")
eq(Map.parse(raw(1):gsub("end 2","end 3")),nil,"torn marker count")
eq(Map.parse(raw(1).."ready 1\n"),nil,"trailing data")
eq(Map.parse(raw(1):gsub("ready 1","ready 1\nready 1")),nil,"duplicate header")
eq(Map.parse(raw(1):gsub("layout 3","layout 2")),nil,"wrong geography")
eq(Map.parse(raw(1):gsub("-584","nan")),nil,"nonfinite")
eq(Map.parse(raw(1):gsub("score 10 20","score x 20")),nil,"invalid first score")
eq(Map.parse(raw(1,"marker player 65537 1 0 0 0")),nil,"enemy player refused")
eq(Map.parse(raw(1,"marker tank 131075 1 0 0 0")),nil,"enemy occupied vehicle refused")
eq(Map.parse(raw(1,"marker pelican 131075 -1 0 0 0")),nil,"unknown carrier refused")
eq(Map.parse(raw(1,"marker capture 3 -1 0 0 0")),nil,"bounded capture identity")
eq(Map.parse(raw(1,"marker base 2 0 0 0 0")),nil,"bounded base identity")
eq(Map.parse(raw(1,"marker self 65536 0 0 0 0")),nil,"duplicate self identity")
eq(Map.parse(raw(1,"marker self 131072 0 0 0 0")),nil,"multiple local bodies")
assert(Map.parse(raw(1,"marker base 1 1 0 0 0")))
assert(Map.parse(raw(1,"marker hog 131075 -1 0 0 0")))
local x,y=Map.project(-1000,1000); eq(x,480,"NW x");eq(y,210,"NW y")
x,y=Map.project(1000,-1000);eq(x,1580,"SE x");eq(y,1310,"SE y")
x,y=Map.project(0,0);eq(x,1030);eq(y,760)
eq(Map.project(1001,0),nil,"outside points omitted, never pinned to a false border location")
local follow={zoom=2,x=250,y=-300}
x,y=Map.project(250,-300,follow);eq(x,1030,"follow centre x");eq(y,760,"follow centre y")
x,y=Map.project(-250,200,follow);eq(x,480,"2x NW viewport");eq(y,210)
x,y=Map.project(750,-800,follow);eq(x,1580,"2x SE viewport");eq(y,1310)
eq(Map.project(751,-300,follow),nil,"point beyond zoomed east edge omitted")
eq(Map.project(250,201,follow),nil,"point beyond zoomed north edge omitted")
eq(Map.project(1001,0,{zoom=4,x=900,y=0}),nil,"world bounds still apply when viewport overlaps edge")
x,y=Map.project(750,750,{zoom=4,x=750,y=750});eq(x,1030);eq(y,760)
x,y=Map.project(1000,1000,{zoom=4,x=750,y=750});eq(x,1580,"4x world northeast x");eq(y,210)

local t,blocked,hidden,reads,pumps=0,false,false,0,0
local match={code="PWR",variant="warfare",players={},warfare={snapshot={instance=s.instance}}}
local map=Map.new({now=function() return t end,match=function() return match end,
    blocked=function() return blocked end,hidden=function() return hidden end,
    localIndex=function() return 0 end,createWidget=function() return nil end,
    read=function() reads=reads+1;return raw(1) end,pump=function() pumps=pumps+1 end})
map.tick();eq(reads,0,"closed does no I/O");eq(pumps,0,"closed native pump idle")
blocked=true;map.toggle();eq(map.open,false,"M is text while typing")
blocked=false;map.toggle();eq(map.open,true,"M opens")
map.toggle();eq(map.open,true,"duplicate key debounce")
t=.3;map.toggle();eq(map.open,false,"second M closes")
t=.6;hidden=true;map.toggle();eq(map.open,false,"hidden HUD cannot open")
hidden=false;map.toggle();eq(map.open,true)
blocked=true;map.tick();eq(map.open,false,"pause/chat collapses map")
blocked=false;t=1;map.toggle();eq(map.open,true)
match={code="PWR",variant="warfare",players={}};map.tick();eq(map.open,false,"world/match change closes map")
eq(map.accept(s,1,s.instance,0),false,"disk snapshot never trusted alone")
eq(map.accept(Map.parse(raw(2)),1.2,s.instance,0),true,"advancing sample accepted")
eq(map.accept(Map.parse(raw(3)),1.4,"another world",0),false,"wrong active instance")
eq(map.accept(Map.parse(raw(4)),1.6,s.instance,1),false,"wrong local player")
eq(map.accept(s,2,s.instance,0),false)
eq(map.accept(Map.parse(raw(2)),5,s.instance,0),false,"old pending sample cannot revive stale match")
eq(map.accept(Map.parse(raw(3)),5.2,s.instance,0),true)
eq(map.accept(Map.parse(raw(4,"marker hog 2 -1 0 0 0","123")),5.4,"123",0),false,"new instance needs fresh confirmation")
-- Exercise the actual presenter with bounded fake UMG objects. These mocks
-- deliberately retain viewport attachments until simulated world teardown;
-- dropping a Lua widget handle must not hide a same-world allocation leak.
local slateWrites=0
local function fakeWidget()
    local w={visible=1,alive=true}
    function w:IsValid() return self.alive end
    function w:SetVisibility(value) slateWrites=slateWrites+1;self.visible=value end
    function w:SetText(value) slateWrites=slateWrites+1;self.text=value end
    function w:SetColorAndOpacity(value) slateWrites=slateWrites+1;self.color=value end
    function w:SetBrushFromTexture(value) slateWrites=slateWrites+1;self.texture=value end
    function w:SetRenderTransformAngle(value) slateWrites=slateWrites+1;self.angle=value end
    w.Slot={}
    function w.Slot:SetPosition(value) slateWrites=slateWrites+1;self.position=value end
    function w.Slot:SetSize(value) slateWrites=slateWrites+1;self.size=value end
    function w.Slot:SetZOrder(value) slateWrites=slateWrites+1;self.z=value end
    return w
end
local function fakeMapWidget()
    local w=fakeWidget()
    for i=0,63 do w["Mark"..i]=fakeWidget();w["Label"..i]=fakeWidget() end
    for _,key in ipairs({"RedScore","BlueScore","Position","TeamStatus","LiveStatus","Site0","Site1","Site2","Overview","Scale"}) do w[key]=fakeWidget() end
    for i=1,4 do w["GridX"..i]=fakeWidget();w["GridY"..i]=fakeWidget() end
    for i=0,4 do w["GridCol"..i]=fakeWidget();w["GridRow"..i]=fakeWidget() end
    return w
end
FText=function(value) return value end
local loaded=0
local ksl={}
function ksl:MakeSoftObjectPath(path) return path end
function ksl:Conv_SoftObjPathToSoftObjRef(path) return path end
function ksl:LoadAsset_Blocking(path) loaded=loaded+1;local o=fakeWidget();o.path=path;return o end
StaticFindObject=function(path)
    eq(path,"/Script/Engine.Default__KismetSystemLibrary","known texture library")
    return ksl
end
local renderTick,clock,typing,hudHidden,creates,renderReads,renderPumps=1,10,false,false,0,0,0
local selfX,selfY,selfHeading=-590,-130,90
local includeSelf=true
local includeTeammate=false
local liveMatch={code="PWR",variant="warfare",players={},warfare={snapshot={instance=s.instance}}}
local widgets={}
local function renderRaw()
    local head=raw(renderTick):match("^(.-)marker self")
    local rows={
        "marker hog 131073 -1 0 0 0",
        "marker tank 131074 0 200 200 -90",
        "marker banshee 131075 -1 -100 -100 180",
        "marker pelican 131076 0 300 300 45",
        "marker capture 0 -1 -232 -156 0"}
    if includeTeammate then rows[#rows+1]=string.format("marker player 65538 0 %g %g 90",selfX+10,selfY+10) end
    if includeSelf then table.insert(rows,1,string.format("marker self 65536 0 %g %g %g",selfX,selfY,selfHeading)) end
    rows[#rows+1]="end "..#rows;rows[#rows+1]=""
    return head..table.concat(rows,"\n")
end
local presenter=Map.new({
    now=function()return clock end,match=function()return liveMatch end,
    blocked=function()return typing end,hidden=function()return hudHidden end,
    localIndex=function()return 0 end,log=function(message)error(message)end,
    createWidget=function(path,z)
        eq(path,"/Game/MJOLNIR/UI/WBP_MJOLNIRTacticalMap.WBP_MJOLNIRTacticalMap_C")
        eq(z,44,"tactical overlay is above world waypoints");creates=creates+1;local w=fakeMapWidget();widgets[#widgets+1]=w;return w
    end,
    read=function()renderReads=renderReads+1;return renderRaw()end,
    pump=function()renderPumps=renderPumps+1 end,
})
presenter.tick();eq(creates,0,"closed presenter allocates nothing")
presenter.toggle();presenter.tick()
local w=widgets[1]
eq(creates,1);eq(w.LiveStatus.text,"ACQUIRING FIELD TELEMETRY")
eq(w.Overview.Slot.size.X,1100);eq(w.Overview.Slot.size.Y,1100)
eq(w.Overview.Slot.position.X,0,"overview is local to MapClip");eq(w.Overview.Slot.position.Y,0)
eq(w.Scale.text,"NORTH UP  /  2 KM x 2 KM")
eq(w.Mark0.visible,1,"pending native sample does not render markers")
eq(renderPumps,1);eq(renderReads,1)
clock=10.1;presenter.tick();eq(renderReads,1,"visible reads capped at 5Hz")
clock=10.3;renderTick=2;presenter.tick()
eq(w.Mark0.visible,3);eq(w.Label0.text,"YOU")
near(w.Mark0.Slot.position.X,410*.55-18,"self position is local to clipped marker canvas")
near(w.Mark0.Slot.position.Y,1130*.55-18)
eq(w.Mark0.angle,0,"north-facing player")
eq(w.Mark1.angle,90,"east-facing Warthog")
eq(w.Mark2.angle,180,"south-facing Scorpion")
eq(w.Mark3.angle,-90,"west-facing Banshee")
eq(w.Mark4.angle,45,"northeast-facing Pelican")
eq(w.Mark5.angle,0,"capture symbol remains upright")
eq(w.Site0.text,"A   /   NEUTRAL")
eq(w.Mark0.Slot.z,1000,"local player remains above vehicles")
eq(w.Mark0.texture.path,"/Game/MJOLNIR/TacticalMap/T_PWR_player.T_PWR_player")
eq(loaded,7,"each unique icon loaded once")
clock=10.6;presenter.toggle();eq(presenter.open,false);eq(w.visible,1)
presenter.tick();eq(renderReads,2,"closed overlay does not read native snapshot")
clock=10.9;presenter.toggle();presenter.tick();eq(creates,1,"ordinary close/reopen reuses pooled widget")
-- A stale but well-formed on-disk sample must never make live markers reappear.
eq(w.Mark0.visible,1,"reopen requires two advancing samples again")
clock=11.2;renderTick=3;presenter.tick();eq(w.Mark0.visible,3)
clock=11.5;typing=true;presenter.tick();eq(presenter.open,false);eq(w.visible,1)
clock=11.8;typing=false;presenter.toggle();presenter.tick();eq(creates,1,"chat gate retains same-world viewport widget")
clock=12.1;hudHidden=true;presenter.tick();eq(presenter.open,false)
clock=12.4;hudHidden=false;presenter.toggle();presenter.tick();eq(creates,1,"HUD-hide gate retains same-world widget")
-- Native time freezing blanks telemetry rather than pinning stale players.
clock=12.7;renderTick=4;presenter.tick();eq(w.Mark0.visible,3)
clock=15;presenter.tick();eq(w.Mark0.visible,1,"frozen native sample expires")
eq(w.LiveStatus.text,"ACQUIRING FIELD TELEMETRY")
liveMatch.over=true;clock=15.3;presenter.tick();eq(presenter.open,false);eq(w.visible,1)
eq(creates,1,"same-world match completion does not allocate")
-- Map code does not take focus, register a tick, or call native world scans.
local bound={}
RegisterKeyBind=function(key,mods,callback)
    assert(key==0x4D or key==0x4E,"Unexpected tactical key")
    eq(#mods,0);assert(not bound[key]);bound[key]=callback
end
presenter.bind();assert(bound[0x4D] and bound[0x4E])
liveMatch.over=false;typing=true;clock=15.6;bound[0x4D]();eq(presenter.open,false,"M stays ordinary chat input")
bound[0x4E]();eq(presenter.zoom,1,"N does nothing while closed/typing")
typing=false;clock=16;bound[0x4E]();eq(presenter.zoom,1,"N does not open closed map")
bound[0x4D]();presenter.tick();clock=16.3;renderTick=5;presenter.tick()
eq(presenter.zoom,1);eq(w.GridX1.visible,3);eq(w.GridCol0.visible,3)
bound[0x4E]();eq(presenter.zoom,2,"N advances 1x to 2x")
bound[0x4E]();eq(presenter.zoom,2,"repeated N is debounced")
presenter.tick()
eq(w.Overview.Slot.size.X,2200);eq(w.Overview.Slot.size.Y,2200)
eq(w.Overview.Slot.position.X,0,"2x follows west-edge player with clamped centre -500")
eq(w.Overview.Slot.position.Y,550-(1000+130)/2000*2200)
near(w.Mark0.Slot.position.X,550+(-590+500)*1.1-18)
eq(w.Mark0.Slot.position.Y,550-18,"player vertically centred inside MapMarks")
eq(w.Mark0.Slot.size.X,36,"self icon stays fixed size at 2x")
eq(w.Mark1.Slot.size.X,30,"vehicle icon stays fixed size")
eq(w.Mark2.visible,1,"vehicle outside zoomed view is omitted")
eq(w.Scale.text,"FOLLOW 2x  /  1000 M ACROSS")
for i=1,4 do eq(w["GridX"..i].visible,1);eq(w["GridY"..i].visible,1) end
for i=0,4 do eq(w["GridCol"..i].visible,1);eq(w["GridRow"..i].visible,1) end
-- The geographic texel under a marker must project to the same screen point.
local function aligned(px,py,index)
    local sx=480+w.Overview.Slot.position.X+(px+1000)/2000*w.Overview.Slot.size.X
    local sy=210+w.Overview.Slot.position.Y+(1000-py)/2000*w.Overview.Slot.size.Y
    local icon=w["Mark"..index]
    checks=checks+2
    assert(math.abs(sx-(480+icon.Slot.position.X+icon.Slot.size.X/2))<1e-8,"zoom background/marker X disagree")
    assert(math.abs(sy-(210+icon.Slot.position.Y+icon.Slot.size.Y/2))<1e-8,"zoom background/marker Y disagree")
end
aligned(selfX,selfY,0)
clock=16.6;bound[0x4E]();eq(presenter.zoom,4,"N advances 2x to 4x");presenter.tick()
eq(w.Overview.Slot.size.X,4400);eq(w.Mark0.Slot.position.X,550-18,"4x centres interior player")
eq(w.Mark0.Slot.position.Y,550-18);eq(w.Mark0.Slot.size.X,36);aligned(selfX,selfY,0)
eq(w.Mark1.visible,1,"far vehicle hidden at 4x")
eq(w.Scale.text,"FOLLOW 4x  /  500 M ACROSS")
-- At every world corner, following clamps to valid terrain; image never exposes
-- blank space, while actual edge positions remain true rather than pinned.
for _,p in ipairs({{-1000,1000},{1000,1000},{1000,-1000},{-1000,-1000}}) do
    selfX,selfY=p[1],p[2];clock=clock+.3;renderTick=renderTick+1;presenter.tick()
    aligned(selfX,selfY,0)
    local xoff,yoff=w.Overview.Slot.position.X,w.Overview.Slot.position.Y
    eq(xoff,(selfX<0) and 0 or -3300,"4x horizontal terrain-edge clamp")
    eq(yoff,(selfY>0) and 0 or -3300,"4x vertical terrain-edge clamp")
    assert(w.Label0.Slot.position.X+240<=1100,"label right edge exceeds clipped map width")
    checks=checks+1
end
typing=true;clock=clock+.3;bound[0x4E]();eq(presenter.zoom,4,"N remains text while typing")
typing=false;hudHidden=true;bound[0x4E]();eq(presenter.zoom,4,"hidden HUD blocks zoom")
hudHidden=false;clock=clock+.3;bound[0x4E]();eq(presenter.zoom,1,"N cycles 4x back to overview");presenter.tick()
eq(w.Overview.Slot.position.X,0);eq(w.Overview.Slot.position.Y,0)
eq(w.Overview.Slot.size.X,1100);eq(w.GridX1.visible,3);eq(w.GridRow0.visible,3)
eq(w.Scale.text,"NORTH UP  /  2 KM x 2 KM")
clock=clock+.3;bound[0x4E]();presenter.tick();eq(presenter.zoom,2)
clock=clock+.3;bound[0x4D]();eq(presenter.open,false);bound[0x4E]();eq(presenter.zoom,2,"closed map keeps selected zoom without changing it")
clock=clock+.3;bound[0x4D]();presenter.tick();eq(presenter.zoom,2,"same-world reopening retains zoom")
eq(creates,1,"all zoom operations reuse the 64-marker widget pool")
-- Native freshness still runs, but identical visible content must not dirty
-- any widget, slot or brush. Count every mocked Slate mutation, not just text.
clock=clock+.3;renderTick=renderTick+1;presenter.tick();eq(w.Mark0.visible,3)
local beforeWrites,beforeReads,beforePumps=slateWrites,renderReads,renderPumps
for i=1,12 do
    clock=clock+.3;renderTick=renderTick+1;presenter.tick()
    eq(slateWrites,beforeWrites,"fresh unchanged content produces zero Slate writes")
end
eq(renderReads,beforeReads+12,"unchanged content still reads fresh native snapshots")
eq(renderPumps,beforePumps+12,"unchanged content still pumps native freshness")
eq(w.Mark0.visible,3,"fresh unchanged content does not expire after 2 seconds")
selfHeading=0;clock=clock+.3;renderTick=renderTick+1;presenter.tick()
assert(slateWrites>beforeWrites,"heading change must redraw");checks=checks+1
eq(w.Mark0.angle,90,"changed heading reaches actual pooled icon")
aligned(selfX,selfY,0)
beforeWrites=slateWrites;clock=clock+.3;renderTick=renderTick+1;presenter.tick()
eq(slateWrites,beforeWrites,"new heading's identical follow-up is skipped")
-- A frozen native snapshot must clear previously drawn content exactly once.
clock=clock+2.2;presenter.tick()
assert(slateWrites>beforeWrites,"stale telemetry must redraw blank state");checks=checks+1
eq(w.Mark0.visible,1,"stale native telemetry removes the local marker")
eq(w.LiveStatus.text,"ACQUIRING FIELD TELEMETRY")
eq(w.RedScore.text,"RED   --")
beforeWrites=slateWrites;clock=clock+.3;presenter.tick()
eq(slateWrites,beforeWrites,"already blank stale state causes zero Slate writes")
-- Fresh advance restores markers after the stale pending sample.
clock=clock+.3;renderTick=renderTick+1;presenter.tick()
assert(slateWrites>beforeWrites,"fresh native advance must restore visible content");checks=checks+1
eq(w.Mark0.visible,3);eq(w.Mark0.angle,90)
-- A roster identity resolves independently of native pose/timestamps. Only
-- teammate IDs present in the authorized snapshot may affect this signature.
selfX,selfY=0,0;includeTeammate=true
clock=clock+.3;renderTick=renderTick+1;presenter.tick()
eq(w.Label6.text,"TEAMMATE","missing teammate identity has explicit fallback")
eq(w.Label6.visible,3)
beforeWrites=slateWrites
liveMatch.players[2]={name="Native Name"}
clock=clock+.3;renderTick=renderTick+1;presenter.tick()
assert(slateWrites>beforeWrites,"resolved stationary teammate name must redraw");checks=checks+1
eq(w.Label6.text,"Native Name")
beforeWrites=slateWrites
clock=clock+.3;renderTick=renderTick+1;presenter.tick()
eq(slateWrites,beforeWrites,"unchanged resolved name returns to zero Slate writes")
liveMatch.players[2].display="Hub Display"
clock=clock+.3;renderTick=renderTick+1;presenter.tick()
assert(slateWrites>beforeWrites,"new preferred display name must redraw");checks=checks+1
eq(w.Label6.text,"Hub Display")
beforeWrites=slateWrites
liveMatch.players[1]={name="Unlisted Enemy"}
liveMatch.players[7]={display="Absent Roster Entry"}
clock=clock+.3;renderTick=renderTick+1;presenter.tick()
eq(slateWrites,beforeWrites,"unlisted roster names do not enter map signature")
eq(w.Label6.text,"Hub Display")
-- Values that sanitize to the same visible label must not dirty the widget.
liveMatch.players[2].display="Hub\n Display"
clock=clock+.3;renderTick=renderTick+1;presenter.tick()
eq(slateWrites,beforeWrites,"signature uses exact sanitized displayed label")
liveMatch.players[2]=nil
clock=clock+.3;renderTick=renderTick+1;presenter.tick()
assert(slateWrites>beforeWrites,"removed name must restore fallback");checks=checks+1
eq(w.Label6.text,"TEAMMATE")
liveMatch={code="PWR",variant="warfare",players={}}
clock=clock+.3;presenter.tick();eq(presenter.open,false);eq(presenter.zoom,1,"new match resets follow zoom")
print("tactical map: "..checks.." checks passed")

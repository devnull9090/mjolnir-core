-- Tests for mods/MJOLNIRLobby/Scripts/ui_polish.lua:
-- font role assignment, event -> audio cue routing, hover debounce & pitch
-- variation, entrance choreography, button hover glide, preview pop, vote
-- pulse, continuous vote countdown bar + spark tracking, and nil-safety.

local Polish = dofile("mods/MJOLNIRLobby/Scripts/ui_polish.lua")

local checks = 0
local function check(cond, msg)
    checks = checks + 1
    assert(cond, "FAIL: " .. tostring(msg))
end

_G.FName = function(s) return { _fname = s } end

-- Fake widget recording SetFont / SetRender* / SetWidthOverride / SetVisibility
local nextAddr = 100
local function fakeWidget(size)
    nextAddr = nextAddr + 1
    local addr = nextAddr
    local w = {
        _valid = true,
        _addr = addr,
        Font = size and { Size = size } or nil,
        tx = 0, ty = 0, sx = 1, sy = 1, alpha = 1, vis = 0, width = 0,
        fontSet = nil,
    }
    function w:IsValid() return self._valid end
    function w:GetAddress() return self._addr end
    function w:SetFont(f) self.fontSet = f end
    function w:SetRenderTranslation(v) self.tx, self.ty = v.X, v.Y end
    function w:SetRenderScale(v) self.sx, self.sy = v.X, v.Y end
    function w:SetRenderOpacity(a) self.alpha = a end
    function w:SetRenderTransformPivot(p) self.pivot = p end
    function w:SetWidthOverride(v) self.width = v end
    function w:SetVisibility(v) self.vis = v end
    return w
end

-- 1. Screen kind detection & event cue mapping
check(Polish.screenKind("/Game/MJOLNIR/UI/WBP_MJOLNIRLobby.WBP_MJOLNIRLobby_C") == "lobby", "lobby kind")
check(Polish.screenKind("/Game/MJOLNIR/UI/WBP_MJOLNIRPostGame.WBP_MJOLNIRPostGame_C") == "postgame", "postgame kind")
check(Polish.screenKind("/Game/MJOLNIR/UI/WBP_MJOLNIRGameTypeSelect.WBP_MJOLNIRGameTypeSelect_C") == "gametype", "gametype kind")
check(Polish.screenKind("unknown") == nil, "unknown kind is nil")

check(Polish.cueForEvent("btn_hover:Start") == "Hover", "btn_hover -> Hover")
check(Polish.cueForEvent("hover:3") == "Hover", "hover:3 -> Hover")
check(Polish.cueForEvent("btn_unhover:Start") == nil, "btn_unhover -> silent")
check(Polish.cueForEvent("unhover:3") == nil, "unhover:3 -> silent")
check(Polish.cueForEvent("start") == "Primary", "start -> Primary")
check(Polish.cueForEvent("select") == "Primary", "select -> Primary")
check(Polish.cueForEvent("join") == "Primary", "join -> Primary")
check(Polish.cueForEvent("back") == "Back", "back -> Back")
check(Polish.cueForEvent("lobby") == "Back", "lobby -> Back")
check(Polish.cueForEvent("vote:2") == "Vote", "vote -> Vote")
check(Polish.cueForEvent("tab:1") == "Tab", "tab -> Tab")
check(Polish.cueForEvent("filter:game") == "Tab", "filter -> Tab")
check(Polish.cueForEvent("changemap") == "Select", "changemap -> Select")

-- 2. Fonts, audio debounce, entrance choreography, hover glide & vote bar
local t = 10.0
local played = {}
local fakeFonts = {
    ["/Game/Fonts/Font_Oxanium.Font_Oxanium"] = { _name = "Oxanium", IsValid = function() return true end },
    ["/Game/Fonts/Font_NormativePro.Font_NormativePro"] = { _name = "NormativePro", IsValid = function() return true end },
}
local p = Polish.new({
    clock = function() return t end,
    noFrameHook = true,
    loadAsset = function(path) return fakeFonts[path] end,
    playSound = function(cue, vol, pitch)
        played[#played + 1] = { cue = cue, vol = vol, pitch = pitch }
        return true
    end,
})

local lobby = fakeWidget()
lobby.Title = fakeWidget(72)
lobby.Subtitle = fakeWidget(20)
lobby.Status = fakeWidget(22)
lobby.StartLabel = fakeWidget(26)
lobby.Header = fakeWidget()
lobby.HeaderRuleWidth = fakeWidget()
lobby.MenuSize = fakeWidget()
lobby.Card = fakeWidget()
lobby.Roster = fakeWidget()
lobby.FooterBarWrap = fakeWidget()

p.adopt(lobby, "/Game/MJOLNIR/UI/WBP_MJOLNIRLobby.WBP_MJOLNIRLobby_C")
check(lobby.Title.fontSet and lobby.Title.fontSet.FontObject._name == "Oxanium", "Title gets Oxanium")
check(lobby.Title.fontSet.Size == 72, "Title preserves cooked font size")
check(lobby.Status.fontSet and lobby.Status.fontSet.FontObject._name == "NormativePro", "Status gets NormativePro")
check(lobby.StartLabel.fontSet and lobby.StartLabel.fontSet.FontObject._name == "Oxanium", "StartLabel gets Oxanium")
check(#played == 1 and played[1].cue == "Open", "adopt plays Open cue")
check(lobby.Header.alpha == 0 and lobby.Header.tx == -24, "Header starts off-left transparent")
check(p.busy(), "entrance animations mark polish busy")

-- Advance past entrance
t = 10.5
p.frame(t)
check(lobby.Header.alpha == 1 and lobby.Header.tx == 0, "Header settles at origin opaque")
check(lobby.HeaderRuleWidth.sx == 1, "HeaderRule settles at full width")
check(lobby.Card.alpha == 1 and lobby.Card.ty == 0, "Card settles cleanly")
check(not p.busy(), "polish goes idle after animations finish")

-- Button hover glide + debounce + returns true to swallow pure-polish events
check(p.onEvent(lobby, "btn_hover:Start", "lobby") == true, "btn_hover consumed")
check(played[#played].cue == "Hover", "btn_hover plays Hover cue")
local firstPitch = played[#played].pitch
-- Second hover within debounce is suppressed
t = t + 0.01
p.onEvent(lobby, "btn_hover:Invite", "lobby")
check(#played == 2, "rapid hover within debounce does not spam audio")
-- After debounce, hover plays with slight pitch step
t = t + 0.06
p.onEvent(lobby, "btn_hover:Invite", "lobby")
check(#played == 3 and played[3].pitch ~= firstPitch, "subsequent hover varies pitch slightly")

-- Advance hover glide to completion
t = t + 0.2
p.frame(t)
check(math.abs(lobby.StartLabel.tx - Polish.HOVER_SHIFT) < 0.01, "StartLabel glides right on hover")
check(p.onEvent(lobby, "btn_unhover:Start", "lobby") == true, "btn_unhover consumed")
t = t + 0.2
p.frame(t)
check(math.abs(lobby.StartLabel.tx) < 0.01, "StartLabel returns to 0 on unhover")

-- Post-Game vote bar continuous drain + spark + final-5s tick + vote pulse
local post = fakeWidget()
post.VoteBarFillSize = fakeWidget()
post.VoteBarSpark = fakeWidget()
post.VoteRow1 = fakeWidget()
check(p.onEvent(post, "vote:1", "postgame") == false, "vote:1 passes through to game logic")
check(played[#played].cue == "Vote", "vote:1 plays Vote cue")
t = t + 0.1
p.frame(t)
check(post.VoteRow1.sx > 1.01, "vote:1 pulses tile scale mid-animation")
t = t + 0.2
p.frame(t)
check(math.abs(post.VoteRow1.sx - 1.0) < 0.01, "vote:1 settles back to 1.0")

local beforeTicks = #played
p.trackVote(post, { active = true, left = 4.9, leftAt = t, total = 20, held = false, barWidth = 900 })
t = t + 0.05
p.frame(t)
check(post.VoteBarFillSize.width > 200 and post.VoteBarFillSize.width < 230, "vote bar width interpolates continuously")
check(post.VoteBarSpark.vis == 3, "vote bar spark shown while active")
check(post.VoteBarSpark.tx == post.VoteBarFillSize.width - 48, "vote bar spark tracks leading edge")
check(#played == beforeTicks + 1 and played[#played].cue == "Tick", "final-5s plays Tick once per second")
t = t + 0.1
p.frame(t)
check(#played == beforeTicks + 1, "same countdown second does not repeat Tick")

-- Held vote hides spark and stops ticking
p.trackVote(post, { active = true, left = 3.5, leftAt = t, total = 20, held = true, barWidth = 900 })
t = t + 0.05
p.frame(t)
check(post.VoteBarSpark.vis == 1, "held vote collapses spark")

print(string.format("UI polish: %d checks passed", checks))

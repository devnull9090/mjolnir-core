-- Run from the repository root with Lua 5.4:
--   lua5.4 tools/tests/test_player_card.lua
-- Exercises Lobby player service record card, right-click & left-click opening,
-- live hub stats formatting/caching, profile URL launch, 2-click ban, kick,
-- and lobby player reporting without Unreal.

local checks = 0
local function check(ok, msg)
    checks = checks + 1
    assert(ok, "FAIL (" .. checks .. "): " .. tostring(msg))
end

FText = function(s) return tostring(s or "") end

local Card = dofile("mods/MJOLNIRLobby/Scripts/player_card.lua")

-- Pure helpers: profileUrl, statsPath, formatStats
check(Card.profileUrl({ userId = "abc-123", name = "chief" }) == "https://mjolnircore.com/users/abc-123",
    "hub user gets /users/<id> profile url")
check(Card.profileUrl({ name = "John 117" }) == "https://mjolnircore.com/players/John%20117",
    "unlinked player gets encoded /players/<name> url")
check(Card.statsPath({ userId = "abc-123", name = "chief" }) == "/users/abc-123/match-stats",
    "hub user queries /users/<id>/match-stats")
check(Card.statsPath({ name = "John 117" }) == "/players/John%20117/stats",
    "unlinked player queries /players/<name>/stats")
check(Card.formatStats({ matches = 0 }) == nil, "zero matches returns nil")

local formatted = Card.formatStats({
    matches = 20, completed = 19, wins = 13, losses = 7, draws = 0,
    kills = 240, deaths = 120, captures = 5,
    weapons = { { weapon = "pistol", kills = 112 } },
})
check(formatted and formatted[1].value == "20", "matches count formatted")
check(formatted[2].value == "65%" and formatted[2].sub == "13W / 7L", "win rate & record formatted")
check(formatted[3].value == "2.00" and formatted[3].sub == "240K / 120D", "K/D formatted")
check(formatted[4].value == "MAGNUM" and formatted[4].sub == "112 KILLS", "top weapon humanized")
check(Card.humanWeapon("FragGrenade") == "FRAG GRENADE", "PascalCase FragGrenade humanized")
check(Card.humanWeapon("MagnumPistol") == "MAGNUM", "PascalCase MagnumPistol humanized")
check(Card.humanWeapon("RocketLauncher") == "ROCKET LAUNCHER", "PascalCase RocketLauncher humanized")

-- Harness
local function fakeWidget()
    local w = { vis = 1, text = "", enabled = true, readonly = false }
    function w:IsValid() return true end
    function w:SetVisibility(v) self.vis = v end
    function w:SetText(s) self.text = tostring(s) end
    function w:GetText() return { ToString = function() return self.text end } end
    function w:SetIsEnabled(v) self.enabled = v end
    function w:SetIsReadOnly(v) self.readonly = v end
    function w:SetBackgroundColor(c) self.bg = c end
    function w:SetColorAndOpacity(c) self.color = c end
    function w:SetKeyboardFocus() self.focused = true end
    return w
end

local lobby = fakeWidget()
for _, name in ipairs({
    "PlayerCardBackdrop", "PlayerCard", "PlayerCardKicker", "PlayerCardName", "PlayerCardSub",
    "PlayerCardAvatar", "PlayerCardStatsNote", "PlayerCardProfile", "PlayerCardReport",
    "PlayerCardReportLabel", "PlayerCardClose", "PlayerCardHostActions",
    "PlayerCardKickLabel", "PlayerCardBanLabel", "PlayerCardStatus",
    "Report", "ReportName", "ReportCount", "ReportAvatar", "ReportSend", "ReportText", "ReportStatus",
    "FFAPlayerBadge0", "FFAPlayerBadge1",
}) do
    lobby[name] = fakeWidget()
end
for i = 0, 3 do
    lobby["PlayerCardStat" .. i .. "Label"] = fakeWidget()
    lobby["PlayerCardStat" .. i .. "Value"] = fakeWidget()
    lobby["PlayerCardStat" .. i .. "Sub"] = fakeWidget()
end
for i = 0, 6 do
    lobby["Reason" .. i] = fakeWidget()
    lobby["Reason" .. i .. "Label"] = fakeWidget()
end

local t = 10.0
local isHost = true
local launched, hubCalls, kicked, banned, openedAnims, rmbCallback = {}, {}, {}, {}, 0, nil

local pc = Card.new({
    valid = function(o) return type(o) == "table" and o.IsValid and o:IsValid() end,
    alive = function() return true end,
    clock = function() return t end,
    getLobby = function() return lobby end,
    isHost = function() return isHost end,
    launchUrl = function(url) launched[#launched + 1] = url; return true end,
    hubCall = function(method, path, body, done)
        hubCalls[#hubCalls + 1] = { method = method, path = path, body = body, done = done }
    end,
    remotePlayers = function() return { { name = "SpartanTwo", pc = "remote_pc" } } end,
    kick = function(rp, why) kicked[#kicked + 1] = { rp = rp, why = why }; return true end,
    ban = function(p, rp) banned[#banned + 1] = { p = p, rp = rp }; return true end,
    onOpenCard = function() openedAnims = openedAnims + 1 end,
    registerKeyBind = function(key, mods, fn) rmbCallback = { key = key, fn = fn } end,
})

check(pc.armRightClick() == true and rmbCallback ~= nil, "arms RMB keybind")

pc.setRoster({
    ["FFA:0"] = { name = "DevNull", hubName = "devnull", userId = "u-self", reports = 0, group = "FFA", isLocal = true, isHost = true },
    ["FFA:1"] = { name = "SpartanTwo", hubName = "Emile", userId = "u-guest", reports = 2, group = "FFA", isLocal = false, isHost = false },
})
check(lobby.FFAPlayerBadge0.text == "HOST", "host row receives HOST badge")
check(lobby.FFAPlayerBadge1.text == "", "guest row badge empty")

-- Right-click while hovering guest opens PlayerCard and fetches stats
check(pc.onEvent("roster_hover:FFA:1") == true, "roster_hover consumed")
check(pc.hoveredSlot() == "FFA:1", "hovered slot recorded")
rmbCallback.fn()
check(pc.isOpen() and lobby.PlayerCard.vis == 0, "right-click opens PlayerCard")
check(lobby.PlayerCardName.text == "Emile", "PlayerCard shows hub display name")
check(lobby.PlayerCardHostActions.vis == 0, "host sees kick/ban row for guest")
check(lobby.PlayerCardReport.vis == 0 and lobby.PlayerCardReport.enabled == true, "report enabled for linked guest")
check(openedAnims == 1, "opening triggers polish callback")
check(#hubCalls == 1 and hubCalls[1].path == "/users/u-guest/match-stats", "fetches hub match-stats")

-- Deliver stats response
hubCalls[1].done(200, {
    matches = 10, completed = 10, wins = 6, losses = 4, draws = 0,
    kills = 150, deaths = 100, weapons = { { weapon = "sniper_rifle", kills = 45 } },
})
check(lobby.PlayerCardStat0Value.text == "10", "stat tile 0 updated")
check(lobby.PlayerCardStat1Value.text == "60%", "stat tile 1 updated")
check(lobby.PlayerCardStat2Value.text == "1.50", "stat tile 2 updated")
check(lobby.PlayerCardStat3Value.text == "SNIPER RIFLE", "stat tile 3 updated")

-- View profile launches /users/u-guest
check(pc.onEvent("pcard_profile") == true, "pcard_profile handled")
check(launched[1] == "https://mjolnircore.com/users/u-guest", "launches hub user profile URL")

-- Ban requires 2-click confirmation
check(pc.onEvent("pcard_ban") == true, "first ban click arms confirm")
check(#banned == 0 and lobby.PlayerCardBanLabel.text == "CONFIRM BAN?", "ban armed without executing")
check(pc.onEvent("pcard_ban") == true, "second ban click executes")
check(#banned == 1 and banned[1].p.name == "SpartanTwo", "ban callback invoked on second click")

-- Kick works
check(pc.onEvent("pcard_kick") == true, "pcard_kick handled")
check(#kicked == 1 and kicked[1].rp.name == "SpartanTwo", "kick callback invoked")

-- Report transition & submission
check(pc.onEvent("pcard_report") == true, "pcard_report transitions to report modal")
check(lobby.PlayerCard.vis == 1 and lobby.Report.vis == 0, "PlayerCard hides and Report opens")
check(lobby.ReportSend.enabled == false, "send disabled before reason chosen")
check(pc.onEvent("reason:0") == true, "reason:0 selects cheating")
check(lobby.ReportSend.enabled == true, "send enabled after reason chosen")
lobby.ReportText.text = "Aimbot in lobby test"
check(pc.onEvent("report_send") == true, "report_send fires POST")
check(#hubCalls == 2 and hubCalls[2].method == "POST" and hubCalls[2].path == "/players/reports", "POST /players/reports sent")
check(hubCalls[2].body.subject_id == "u-guest" and hubCalls[2].body.reason == "cheating", "report payload matches")
hubCalls[2].done(201, { id = "r-1" })
check(lobby.ReportStatus.text:find("REPORT SENT", 1, true) ~= nil, "report confirmation shown")
check(pc.onEvent("report_cancel") == true and not pc.isOpen(), "report_cancel closes modal")

-- Left-click on self hides host moderation & report button
check(pc.onEvent("roster_click:FFA:0") == true, "left-click opens self card")
check(lobby.PlayerCardHostActions.vis == 1, "host actions hidden for self")
check(lobby.PlayerCardReport.vis == 1, "report hidden for self")

-- Right-clicking outside (unhovered) closes open card
t = t + 0.5
check(pc.onEvent("roster_unhover:FFA:1") == true, "roster_unhover clears hover")
rmbCallback.fn()
check(not pc.isOpen() and lobby.PlayerCard.vis == 1, "right-click away closes PlayerCard")

print(string.format("Player card: %d checks passed", checks))

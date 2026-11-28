-- MJOLNIR Lobby: player service record card & context actions (right-click or
-- click any player in the lobby roster).
--
-- Shows the player's hub avatar, identity, live career stats fetched from the
-- hub (`GET /users/{id}/match-stats` or `GET /players/{name}/stats`), and
-- actions: VIEW PROFILE (opens mjolnircore.com), REPORT PLAYER (opens the
-- lobby's built-in report modal -> `POST /players/reports`), plus host-only
-- KICK and 2-click BAN controls.

local M = {}

local WEAPON_NAMES = {
    pistol = "MAGNUM",
    magnum = "MAGNUM",
    magnum_pistol = "MAGNUM",
    marksman_rifle = "DMR",
    assault_rifle = "ASSAULT RIFLE",
    smg = "SMG",
    shotgun = "SHOTGUN",
    sniper_rifle = "SNIPER RIFLE",
    rocket_launcher = "ROCKET LAUNCHER",
    flak_cannon = "FUEL ROD",
    plasma_pistol = "PLASMA PISTOL",
    plasma_rifle = "PLASMA RIFLE",
    needler = "NEEDLER",
    plasma_cannon = "FUEL ROD",
    energy_blade = "ENERGY SWORD",
    frag_grenade = "FRAG GRENADE",
    plasma_grenade = "PLASMA GRENADE",
    explosion = "EXPLOSION",
    melee = "MELEE",
    warthog = "WARTHOG",
    warthog_driver = "WARTHOG",
    ghost = "GHOST",
    banshee = "BANSHEE",
    banshee_bomb = "BANSHEE BOMB",
    scorpion = "SCORPION",
    turret = "TURRET",
    splatter = "SPLATTER",
    collision_damage = "SPLATTER",
}

local REASONS = { "cheating", "betraying", "harassment", "griefing", "quitting", "name", "other" }
local DETAIL_MAX = 1000
local STATS_TTL = 60

local NORMAL_BG = { R = 1, G = 1, B = 1, A = 1 }
local SELECTED_BG = { R = 2.6, G = 3.4, B = 3.8, A = 1 }
local WHITE = { R = 0.88, G = 0.95, B = 1, A = 1 }
local GOLD = { R = 1, G = 0.80, B = 0.35, A = 1 }

local function urlEncode(s)
    return (tostring(s or ""):gsub("([^%w%-_%.~])", function(c)
        return string.format("%%%02X", c:byte())
    end))
end

local function humanWeapon(raw)
    if type(raw) ~= "string" or raw == "" then return "—" end
    local snake = raw:gsub("(%l)(%u)", "%1_%2"):gsub("[%s%-]+", "_")
    local key = string.lower(snake)
    if WEAPON_NAMES[key] then return WEAPON_NAMES[key] end
    return string.upper((snake:gsub("_", " ")))
end

function M.profileUrl(player)
    if type(player) ~= "table" then return "https://mjolnircore.com/leaderboards" end
    if type(player.userId) == "string" and player.userId ~= "" then
        return "https://mjolnircore.com/users/" .. urlEncode(player.userId)
    end
    local name = player.hubName or player.name or ""
    if name == "" then return "https://mjolnircore.com/leaderboards" end
    return "https://mjolnircore.com/players/" .. urlEncode(name)
end

function M.statsPath(player)
    if type(player) ~= "table" then return nil end
    if type(player.userId) == "string" and player.userId ~= "" then
        return "/users/" .. urlEncode(player.userId) .. "/match-stats"
    end
    local name = player.name or player.hubName or ""
    if name == "" then return nil end
    return "/players/" .. urlEncode(name) .. "/stats"
end

function M.formatStats(st)
    if type(st) ~= "table" or (tonumber(st.matches) or 0) <= 0 then
        return nil
    end
    local matches = tonumber(st.matches) or 0
    local completed = tonumber(st.completed) or matches
    local wins = tonumber(st.wins) or 0
    local losses = tonumber(st.losses) or 0
    local draws = tonumber(st.draws) or 0
    local kills = tonumber(st.kills) or 0
    local deaths = tonumber(st.deaths) or 0
    local captures = tonumber(st.captures) or 0
    local decided = math.max(1, wins + losses + draws)
    local winPct = math.floor((wins * 100 / decided) + 0.5)
    local kd = deaths > 0 and string.format("%.2f", kills / deaths) or string.format("%.2f", kills)

    local top = type(st.weapons) == "table" and st.weapons[1] or nil
    local fourthLabel, fourthVal, fourthSub = "TOP WEAPON", "—", "NO WEAPON DATA"
    if type(top) == "table" and type(top.weapon) == "string" and top.weapon ~= "" then
        fourthVal = humanWeapon(top.weapon)
        fourthSub = string.format("%d KILL%s", tonumber(top.kills) or 0, (tonumber(top.kills) or 0) == 1 and "" or "S")
    elseif captures > 0 then
        fourthLabel = "CAPTURES"
        fourthVal = tostring(captures)
        fourthSub = "FLAGS SCORED"
    end

    return {
        { label = "MATCHES", value = tostring(matches), sub = string.format("%d COMPLETED", completed) },
        { label = "WIN RATE", value = string.format("%d%%", winPct),
          sub = draws > 0 and string.format("%dW / %dL / %dD", wins, losses, draws)
              or string.format("%dW / %dL", wins, losses) },
        { label = "K / D", value = kd, sub = string.format("%dK / %dD", kills, deaths) },
        { label = fourthLabel, value = fourthVal, sub = fourthSub },
    }
end

M.humanWeapon = humanWeapon
M.REASONS = REASONS

function M.new(deps)
    deps = deps or {}
    local valid = deps.valid or function(o)
        local ok, v = pcall(function() return o and o:IsValid() end)
        return ok and v
    end
    local now = deps.clock or os.clock
    local log = deps.log or function() end

    local self = {}
    local slots = {}          -- "Group:index" -> { name, hubName, userId, reports, group, isLocal, isHost }
    local hovered = nil       -- "Group:index" or nil
    local active = nil        -- { player, banArmed, status, loading, stats }
    local report = nil        -- { player, reason, sending, done, status }
    local reported = {}       -- [userId] = true (session dedupe)
    local statsCache = {}     -- [path] = { at, stats }
    local rmbBound = false
    local lastRmb = -10

    local function setText(w, value)
        if not valid(w) then return end
        pcall(function() w:SetText(FText(value or "")) end)
    end

    local function setShown(w, show)
        if not valid(w) then return end
        pcall(function() w:SetVisibility(show and 0 or 1) end)
    end

    local function lobby()
        return deps.getLobby and deps.getLobby() or nil
    end

    local function lobbyAlive()
        local s = lobby()
        return valid(s) and (not deps.alive or deps.alive(s))
    end

    local function groupLabel(group)
        if group == "Red" then return "RED TEAM"
        elseif group == "Blue" then return "BLUE TEAM"
        elseif group == "Unassigned" then return "AWAITING TEAM"
        end
        return "FIRETEAM"
    end

    local function drawReport()
        local s = lobby()
        if not valid(s) then return end
        local okR, panel = pcall(function() return s.Report end)
        if not (okR and valid(panel)) then return end
        setShown(s.ReportBackdrop, report ~= nil)
        setShown(panel, report ~= nil)
        if not report then return end
        local p = report.player
        setText(s.ReportName, p.hubName or p.name)
        local n = tonumber(p.reports or 0) or 0
        local seen = p.hubName and p.hubName ~= p.name and ("IN GAME AS " .. string.upper(p.name) .. "   /   ") or ""
        setText(s.ReportCount, seen .. (n == 1 and "1 REPORT" or (tostring(n) .. " REPORTS")) .. " ON THE HUB")
        if deps.showAvatar then deps.showAvatar(s.ReportAvatar, p.userId) end
        for k = 1, #REASONS do
            local chosen = report.reason == k
            pcall(function()
                s["Reason" .. (k - 1)]:SetBackgroundColor(chosen and SELECTED_BG or NORMAL_BG)
                s["Reason" .. (k - 1) .. "Label"]:SetColorAndOpacity({
                    SpecifiedColor = chosen and GOLD or WHITE, ColorUseRule = 0 })
                s["Reason" .. (k - 1)]:SetIsEnabled(not report.sending and not report.done)
            end)
        end
        pcall(function()
            s.ReportSend:SetIsEnabled(report.reason ~= nil and not report.sending and not report.done)
            s.ReportText:SetIsReadOnly(report.sending or report.done or false)
        end)
        setText(s.ReportStatus, report.status or (report.reason and "" or "PICK A REASON."))
    end

    local function drawCard()
        local s = lobby()
        if not valid(s) then return end
        local okC, card = pcall(function() return s.PlayerCard end)
        if not (okC and valid(card)) then return end
        local shown = active ~= nil
        setShown(s.PlayerCardBackdrop, shown)
        setShown(card, shown)
        if not shown then return end

        local p = active.player
        local role = p.isLocal and "YOU  /  SPARTAN SERVICE RECORD"
            or (p.isHost and "HOST  /  SPARTAN SERVICE RECORD" or "SPARTAN SERVICE RECORD")
        setText(s.PlayerCardKicker, role)
        setText(s.PlayerCardName, p.hubName or p.name)

        local parts = {}
        if p.hubName and p.hubName ~= p.name then
            parts[#parts + 1] = "IN GAME AS " .. string.upper(p.name)
        end
        parts[#parts + 1] = groupLabel(p.group)
        if p.userId then
            local n = tonumber(p.reports or 0) or 0
            parts[#parts + 1] = n == 1 and "1 REPORT" or (tostring(n) .. " REPORTS")
        else
            parts[#parts + 1] = "NO HUB ACCOUNT LINKED"
        end
        setText(s.PlayerCardSub, table.concat(parts, "   /   "))
        if deps.showAvatar then deps.showAvatar(s.PlayerCardAvatar, p.userId) end

        local cells = active.stats and M.formatStats(active.stats) or nil
        if active.loading then
            setText(s.PlayerCardStatsNote, "LOADING SERVICE RECORD...")
            for idx = 0, 3 do
                setText(s["PlayerCardStat" .. idx .. "Value"], "—")
                setText(s["PlayerCardStat" .. idx .. "Sub"], "")
            end
        elseif cells then
            setText(s.PlayerCardStatsNote, "PUBLIC MATCHES ON MJOLNIRCORE.COM")
            for idx = 0, 3 do
                local c = cells[idx + 1]
                setText(s["PlayerCardStat" .. idx .. "Label"], c.label)
                setText(s["PlayerCardStat" .. idx .. "Value"], c.value)
                setText(s["PlayerCardStat" .. idx .. "Sub"], c.sub)
            end
        else
            setText(s.PlayerCardStatsNote, "NO PUBLIC MATCHES RECORDED YET")
            local defaults = { "MATCHES", "WIN RATE", "K / D", "TOP WEAPON" }
            for idx = 0, 3 do
                setText(s["PlayerCardStat" .. idx .. "Label"], defaults[idx + 1])
                setText(s["PlayerCardStat" .. idx .. "Value"], "—")
                setText(s["PlayerCardStat" .. idx .. "Sub"], "")
            end
        end

        local canReport = (not p.isLocal) and (type(p.userId) == "string" and p.userId ~= "")
        setShown(s.PlayerCardReport, not p.isLocal)
        pcall(function() s.PlayerCardReport:SetIsEnabled(canReport) end)
        setText(s.PlayerCardReportLabel, reported[p.userId or ""] and "REPORTED" or "REPORT PLAYER")

        local isHost = deps.isHost and deps.isHost() or false
        local canModerate = isHost and not p.isLocal
        setShown(s.PlayerCardHostActions, canModerate)
        if canModerate then
            setText(s.PlayerCardKickLabel, "KICK FROM LOBBY")
            setText(s.PlayerCardBanLabel, active.banArmed and "CONFIRM BAN?" or "BAN FROM MY GAMES")
        end

        local hasStatus = type(active.status) == "string" and active.status ~= ""
        setShown(s.PlayerCardStatus, hasStatus)
        if hasStatus then setText(s.PlayerCardStatus, active.status) end
    end

    local function fetchStats(entry)
        local path = M.statsPath(entry.player)
        if not path or not deps.hubCall then
            entry.loading = false
            drawCard()
            return
        end
        local cached = statsCache[path]
        if cached and now() - cached.at < STATS_TTL then
            entry.loading = false
            entry.stats = cached.stats
            drawCard()
            return
        end
        entry.loading = true
        drawCard()
        deps.hubCall("GET", path, nil, function(status, data)
            if status == 200 and type(data) == "table" then
                statsCache[path] = { at = now(), stats = data }
            end
            if active ~= entry then return end
            entry.loading = false
            entry.stats = (status == 200 and type(data) == "table") and data or nil
            drawCard()
        end)
    end

    --- Update the roster slot table from `drawLobby` and decorate row badges.
    function self.setRoster(entries)
        slots = entries or {}
        if hovered and not slots[hovered] then hovered = nil end
        local s = lobby()
        if not valid(s) then return end
        for key, member in pairs(slots) do
            local group, idx = key:match("^([^:]+):(%d+)$")
            if group and idx then
                local badge = member.isHost and "HOST" or (member.isLocal and "YOU" or "")
                setText(s[group .. "PlayerBadge" .. idx], badge)
            end
        end
    end

    function self.open(player)
        if not (lobbyAlive() and type(player) == "table") then return false end
        report = nil
        drawReport()
        active = { player = player, banArmed = false, status = nil, loading = false, stats = nil }
        drawCard()
        local s = lobby()
        if deps.onOpenCard and valid(s) and valid(s.PlayerCard) then
            deps.onOpenCard(s.PlayerCard)
        end
        fetchStats(active)
        return true
    end

    function self.openSlot(group, idx)
        local member = slots[tostring(group) .. ":" .. tostring(idx)]
        if not member then return false end
        return self.open(member)
    end

    function self.close()
        local had = active ~= nil or report ~= nil
        active = nil
        report = nil
        drawCard()
        drawReport()
        return had
    end

    function self.isOpen()
        return active ~= nil or report ~= nil
    end

    function self.hoveredSlot()
        return hovered
    end

    function self.activePlayer()
        return active and active.player or nil
    end

    local function openLobbyReport(p)
        local s = lobby()
        if not (lobbyAlive() and p and p.userId and valid(s.Report)) then
            if active then
                active.status = "THIS PLAYER HAS NO LINKED HUB ACCOUNT TO REPORT."
                drawCard()
            end
            return
        end
        active = nil
        drawCard()
        report = { player = p }
        if reported[p.userId] then
            report.done = true
            report.status = "YOU ALREADY REPORTED THIS PLAYER THIS SESSION."
        end
        pcall(function() s.ReportText:SetText(FText("")) end)
        drawReport()
        if deps.onOpenCard and valid(s.Report) then deps.onOpenCard(s.Report) end
        pcall(function() s.ReportText:SetKeyboardFocus() end)
    end

    local function sendLobbyReport()
        if not (report and report.reason and not report.sending and not report.done) then return end
        local s = lobby()
        local detail = ""
        pcall(function() detail = s.ReportText:GetText():ToString() end)
        detail = tostring(detail or ""):gsub("^%s+", ""):gsub("%s+$", "")
        if #detail > DETAIL_MAX then detail = detail:sub(1, DETAIL_MAX) end
        local p = report.player
        local body = {
            subject_id = p.userId,
            reason = REASONS[report.reason],
            subject_name = tostring(p.name or ""):sub(1, 64),
        }
        if detail ~= "" then body.detail = detail end
        local ref = report
        ref.sending = true
        ref.status = "SENDING..."
        drawReport()
        if not deps.hubCall then
            ref.sending = false
            ref.status = "HUB UNAVAILABLE."
            drawReport()
            return
        end
        deps.hubCall("POST", "/players/reports", body, function(status, data)
            if report ~= ref then return end
            ref.sending = false
            if status == 201 or status == 409 then
                ref.done = true
                reported[p.userId] = true
                ref.status = status == 201
                    and "REPORT SENT. A MODERATOR WILL REVIEW IT. THANK YOU."
                    or "YOU ALREADY REPORTED THIS PLAYER."
                log(string.format("lobby report: %s (%s) %s",
                    tostring(p.hubName or p.name), REASONS[ref.reason],
                    status == 201 and "sent" or "already sent"))
                if deps.delay then
                    deps.delay(2200, function()
                        if report == ref then self.close() end
                    end)
                end
            else
                local msg = deps.explain and deps.explain(status, data) or ("ERROR " .. tostring(status))
                ref.status = string.upper(tostring(msg))
            end
            drawReport()
        end)
    end

    local function findRemote(player)
        if not (deps.remotePlayers and player and player.name) then return nil end
        local want = string.lower(player.name)
        for _, rp in ipairs(deps.remotePlayers()) do
            if rp.name == player.name or string.lower(rp.name or "") == want then
                return rp
            end
        end
        return nil
    end

    --- Handle Lobby MJ_Events belonging to roster rows, PlayerCard, or Lobby Report.
    --- Returns true when handled.
    function self.onEvent(event)
        if type(event) ~= "string" then return false end

        local hg, hi = event:match("^roster_hover:([^:]+):(%d+)$")
        if hg then
            hovered = hg .. ":" .. hi
            return true
        end
        local ug, ui = event:match("^roster_unhover:([^:]+):(%d+)$")
        if ug then
            if hovered == ug .. ":" .. ui then hovered = nil end
            return true
        end
        local cg, ci = event:match("^roster_click:([^:]+):(%d+)$")
        if cg then
            self.openSlot(cg, ci)
            return true
        end

        if event == "pcard_close" then
            self.close()
            return true
        elseif event == "pcard_profile" and active then
            local url = M.profileUrl(active.player)
            local ok = deps.launchUrl and deps.launchUrl(url) or false
            active.status = ok and "OPENING PROFILE IN BROWSER..." or ("VISIT " .. string.upper(url))
            drawCard()
            return true
        elseif event == "pcard_report" and active then
            openLobbyReport(active.player)
            return true
        elseif event == "pcard_kick" and active then
            if not (deps.isHost and deps.isHost()) or active.player.isLocal then return true end
            local rp = findRemote(active.player)
            if not rp then
                active.status = "PLAYER IS NO LONGER CONNECTED."
                drawCard()
                return true
            end
            local ok = deps.kick and deps.kick(rp, "You were kicked by the host.") or false
            active.status = ok and ("KICKED " .. string.upper(active.player.hubName or active.player.name))
                or "COULD NOT KICK PLAYER."
            drawCard()
            if ok and deps.delay then
                local ref = active
                deps.delay(1200, function() if active == ref then self.close() end end)
            end
            return true
        elseif event == "pcard_ban" and active then
            if not (deps.isHost and deps.isHost()) or active.player.isLocal then return true end
            if not active.banArmed then
                active.banArmed = true
                active.status = "CLICK BAN AGAIN TO CONFIRM."
                drawCard()
                return true
            end
            local rp = findRemote(active.player)
            local ok = deps.ban and deps.ban(active.player, rp) or false
            active.banArmed = false
            active.status = ok and ("BANNED " .. string.upper(active.player.hubName or active.player.name))
                or "COULD NOT BAN PLAYER."
            drawCard()
            if ok and deps.delay then
                local ref = active
                deps.delay(1200, function() if active == ref then self.close() end end)
            end
            return true
        end

        if report then
            local rk = tonumber(event:match("^reason:(%d+)$") or "")
            if rk and REASONS[rk + 1] and not report.sending and not report.done then
                report.reason = rk + 1
                report.status = nil
                drawReport()
                return true
            elseif event == "report_send" then
                sendLobbyReport()
                return true
            elseif event == "report_cancel" then
                self.close()
                return true
            end
        end

        return false
    end

    --- Handle a right-click press: opens the hovered roster player's card, or
    --- closes an open card when right-clicking elsewhere.
    function self.onRightClick()
        local t = now()
        if t - lastRmb < 0.18 then return false end
        lastRmb = t
        if not lobbyAlive() then return false end
        if hovered and slots[hovered] then
            if deps.onRightClickOpen then deps.onRightClickOpen() end
            return self.open(slots[hovered])
        elseif active and not report then
            self.close()
            return true
        end
        return false
    end

    --- Arm UE4SS right-mouse-button keybind so right-clicking any hovered
    --- roster player opens their card immediately.
    function self.armRightClick()
        if rmbBound or deps.noKeyBind then return rmbBound end
        local reg = deps.registerKeyBind or RegisterKeyBind
        if type(reg) ~= "function" then return false end
        local key = (Key and (Key.RIGHT_MOUSE_BUTTON or Key.RBUTTON)) or 0x02
        local ok = pcall(reg, key, {}, function()
            if type(ExecuteInGameThread) == "function" then
                ExecuteInGameThread(function() pcall(self.onRightClick) end)
            else
                pcall(self.onRightClick)
            end
        end)
        rmbBound = ok
        return ok
    end

    return self
end

return M

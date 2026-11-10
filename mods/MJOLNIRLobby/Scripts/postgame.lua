-- The post-game screen's left side (docs/multiplayer_postgame.md): three
-- pages under the winner. OVERVIEW has the top three as cards with their
-- medals, the local player's medals by name, and the match's bests;
-- SCOREBOARD is every player, as before; TIMELINE draws the top players'
-- scores over the match and the kills of every minute.
--
-- Everything comes from MJOLNIRHud's results (last_match.txt, which
-- main.lua's readResults reads): players in standing order with their
-- medals by incident name, their score and kills at evenly spaced moments,
-- and how long the match ran. A medal's title, glyph and class come from
-- this mod's DLL (native/lobby/medals_core.h).
--
-- The layout is the UI container's (unreal/MJOLNIRMaterials/Scripts/
-- build_mjolnir_ui.py, post_overview and post_timeline); the sizes below
-- are its. A container from before it has no `Tabs`: `available` says so
-- and main.lua draws the scoreboard with the medals as a line of text.
local M = {}

M.TABS = 3
M.POD_MEDALS = 5
M.MINE_MEDALS = 9
M.CHART = { 1096, 230 }
M.DOT = 6
M.SERIES = 4
M.POINTS = 48
M.BARS = 30
M.BAR = 96

local ICON_ROOT = "/Game/MJOLNIR/UI/Icons/T_MJHud_"
-- A medal's colour, by the key the DLL gives (MJOLNIRHud's FEED colours).
M.INK = {
    medal = { R = 1.0, G = 0.80, B = 0.35, A = 1 },
    spree = { R = 1.0, G = 0.56, B = 0.24, A = 1 },
    blood = { R = 0.95, G = 0.26, B = 0.24, A = 1 },
    headshot = { R = 1.0, G = 0.44, B = 0.32, A = 1 },
}
-- Glyphs this screen has that the feed's catalogue does not name.
local GLYPHS = {
    revenge_kill = "Revenge", assist = "Assist", emp_assist = "Assist", driver_assist_gunner = "Assist",
    killjoy = "Star", close_call = "Star", opportunist_kill = "Star", avenger = "Star", lifesaver = "Star",
    extermination = "Star", perfection = "Star", highjack = "Star", skyjack = "Star",
}
local WHITE = { R = 0.88, G = 0.95, B = 1, A = 1 }
local GREY = { R = 0.46, G = 0.61, B = 0.70, A = 1 }
local GOLD = { R = 1, G = 0.80, B = 0.35, A = 1 }

--- The numeral a medal shows in place of a glyph: a multi-kill's "x2", a
--- spree's "5"; nil for the rest.
function M.mark(name)
    local n = name:match("^multikill_x(%d+)$")
    if n then return "x" .. n end
    return name:match("^(%d+)_in_a_row$")
end

--- A player's medals for display: { name, count, title, glyph, mark, ink },
--- the rarest kind first (the DLL's class, then its rank), then the most
--- earned. `info(name)` is the DLL's: title, glyph, colour key, show, class,
--- rank; a medal it does not know keeps its incident name as a title.
function M.medals(p, info)
    local out = {}
    for _, m in ipairs(p and p.medals or {}) do
        local title, glyph, colour, _, class, rank = info(m.name)
        out[#out + 1] = {
            name = m.name, count = m.count,
            title = title or (m.name:gsub("_", " ")),
            glyph = GLYPHS[m.name] or glyph or "Medal",
            mark = M.mark(m.name),
            ink = M.INK[colour or "medal"] or M.INK.medal,
            class = class or 9, rank = rank or 0,
        }
    end
    table.sort(out, function(a, b)
        if a.class ~= b.class then return a.class < b.class end
        if a.rank ~= b.rank then return a.rank > b.rank end
        if a.count ~= b.count then return a.count > b.count end
        return a.name < b.name
    end)
    return out
end

local function number(v)
    return tonumber(v) or 0
end

--- The top three, best first, by score, then kills, then fewer deaths:
--- across both teams in a team game.
function M.podium(r)
    local list = {}
    for i, p in ipairs(r.players) do list[i] = p end
    table.sort(list, function(a, b)
        if number(a.score) ~= number(b.score) then return number(a.score) > number(b.score) end
        if number(a.kills) ~= number(b.kills) then return number(a.kills) > number(b.kills) end
        if number(a.deaths) ~= number(b.deaths) then return number(a.deaths) < number(b.deaths) end
        return (a.name or "") < (b.name or "")
    end)
    return { list[1], list[2], list[3] }
end

--- Kills over deaths as text; all kills when there were no deaths.
function M.ratio(p)
    local k, d = number(p.kills), number(p.deaths)
    return string.format("%.2f", d > 0 and k / d or k)
end

--- The match's bests: { label, value, name } each, the ones with something
--- to show.
function M.bests(r)
    local function best(value, better)
        local pick, top
        for _, p in ipairs(r.players) do
            local v = value(p)
            if v and (top == nil or better(v, top)) then pick, top = p, v end
        end
        return pick, top
    end
    local more = function(a, b) return a > b end
    local out = {}
    local function add(label, p, text)
        if p then out[#out + 1] = { label = label, value = text, name = p.hubName or p.name } end
    end
    local p, v = best(function(q) return number(q.kills) > 0 and number(q.kills) or nil end, more)
    add("MOST KILLS", p, tostring(v))
    p = best(function(q) return number(q.kills) > 0 and (number(q.kills) / math.max(number(q.deaths), 1)) or nil end, more)
    add("BEST K/D", p, p and M.ratio(p))
    p, v = best(function(q) return (q.medalCount or 0) > 0 and q.medalCount or nil end, more)
    add("MOST MEDALS", p, tostring(v))
    p, v = best(function(q) return number(q.deaths) end, function(a, b) return a < b end)
    if #r.players > 1 then add("FEWEST DEATHS", p, tostring(v)) end
    return out
end

--- m:ss.
function M.clock(seconds)
    seconds = math.max(0, math.floor(number(seconds) + 0.5))
    return string.format("%d:%02d", seconds // 60, seconds % 60)
end

--- The score chart: { max, series = { { name, points = { { x, y } } } } },
--- the top SERIES players who have a series, each point a dot's top left on
--- the plot (0, 0 at its top left). nil when the results carry none.
function M.chart(r)
    local lines = {}
    for _, p in ipairs(M.podium({ players = r.players })) do
        if p and p.series and #p.series > 1 then lines[#lines + 1] = p end
    end
    for _, p in ipairs(r.players) do
        if #lines >= M.SERIES then break end
        local listed = false
        for _, q in ipairs(lines) do listed = listed or q == p end
        if not listed and p.series and #p.series > 1 then lines[#lines + 1] = p end
    end
    if #lines == 0 then return nil end
    local max = 1
    for _, p in ipairs(lines) do
        for _, v in ipairs(p.series) do max = math.max(max, v) end
    end
    local w, h = M.CHART[1] - M.DOT, M.CHART[2] - M.DOT
    local out = { max = max, series = {} }
    for i, p in ipairs(lines) do
        local points = {}
        local n = math.min(#p.series, M.POINTS)
        for k = 1, n do
            points[k] = { math.floor(w * (k - 1) / math.max(n - 1, 1) + 0.5),
                math.floor(h * (1 - p.series[k] / max) + 0.5) }
        end
        out.series[i] = { name = p.hubName or p.name, points = points }
    end
    return out
end

--- The kills of every stretch of the match: { values, max, minutes (a bar's
--- length), bars }, at most BARS bars, each `minutes` long (1 until the
--- match is longer than BARS minutes). nil when the results carry none.
function M.bars(r)
    local total
    for _, p in ipairs(r.players) do
        if p.killsAt and #p.killsAt > 1 then
            total = total or {}
            for i, v in ipairs(p.killsAt) do total[i] = (total[i] or 0) + v end
        end
    end
    local clock = number(r.clock)
    if not total or clock <= 0 then return nil end
    local minutes = math.max(1, math.ceil(clock / 60 / M.BARS))
    local bars = math.max(1, math.min(M.BARS, math.ceil(clock / (60 * minutes))))
    -- The kills so far at `t` seconds: the point at or before it (point i is
    -- at clock * i / #total).
    local function at(t)
        local i = math.floor(t / clock * #total + 1e-6)
        return i >= 1 and total[math.min(i, #total)] or 0
    end
    local values, max = {}, 1
    for b = 1, bars do
        local from, to = (b - 1) * 60 * minutes, math.min(clock, b * 60 * minutes)
        values[b] = math.max(0, at(to) - at(from))
        max = math.max(max, values[b])
    end
    return { values = values, max = max, minutes = minutes, bars = bars }
end

--- The view over a screen. deps: setText, setShown, valid, info (the DLL's
--- medal info), avatar(image, userId) -> shown, tint(block, colour).
function M.new(deps)
    local self = { tab = 0 }
    local textures = {}

    local function texture(name)
        if textures[name] == nil or (textures[name] and not deps.valid(textures[name])) then
            local ok, tex = pcall(function()
                local ksl = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
                local path = ICON_ROOT .. name .. ".T_MJHud_" .. name
                return ksl:LoadAsset_Blocking(ksl:Conv_SoftObjPathToSoftObjRef(ksl:MakeSoftObjectPath(path)))
            end)
            textures[name] = ok and deps.valid(tex) and tex or false
        end
        return textures[name]
    end

    local function image(widget, name, colour)
        local tex = texture(name)
        pcall(function()
            if tex then widget:SetBrushFromTexture(tex, false) end
            widget:SetColorAndOpacity(colour)
            widget:SetVisibility(tex and 3 or 2)
        end)
    end

    --- Whether this screen has the pages (a UI container from before them
    --- has only the scoreboard).
    function self.available(s)
        return deps.valid(s.Tabs) and deps.valid(s.PageOverview) and deps.valid(s.PageTimeline)
    end

    --- One medal slot (`<prefix>Size` and its layers); nil empties it.
    local function medal(s, prefix, m)
        deps.setShown(s[prefix .. "Size"], m ~= nil)
        if not m then return end
        image(s[prefix .. "Disc"], "MedalDisc", { R = m.ink.R * 0.35, G = m.ink.G * 0.35, B = m.ink.B * 0.35, A = 0.92 })
        image(s[prefix .. "Ring"], "MedalRing", m.ink)
        deps.setShown(s[prefix .. "GlyphSize"], m.mark == nil)
        if m.mark then
            deps.setText(s[prefix .. "Mark"], m.mark)
            deps.tint(s[prefix .. "Mark"], m.ink)
        else
            deps.setText(s[prefix .. "Mark"], "")
            image(s[prefix .. "Glyph"], m.glyph, m.ink)
        end
        deps.setText(s[prefix .. "Count"], m.count > 1 and ("x" .. tostring(m.count)) or "")
    end

    local function overview(s, r)
        local places = { "1ST", "2ND", "3RD" }
        local top = M.podium(r)
        for k = 0, 2 do
            local p = top[k + 1]
            pcall(function() s["Pod" .. k]:SetVisibility(p and 3 or 2) end)
            if p then
                deps.setText(s["PodPlace" .. k], places[k + 1] .. (p.you and "   /   YOU" or ""))
                deps.setText(s["PodName" .. k], p.hubName or p.name)
                deps.setText(s["PodScore" .. k], tostring(p.score or ""))
                deps.setText(s["PodLine" .. k], string.format("%s KILLS   /   %s DEATHS   /   %s K/D",
                    tostring(p.kills or 0), tostring(p.deaths or 0), M.ratio(p)))
                deps.avatar(s["PodAvatar" .. k], p.userId)
                local medals = M.medals(p, deps.info)
                for j = 0, M.POD_MEDALS - 1 do medal(s, "PodMedal" .. k .. "_" .. j, medals[j + 1]) end
            end
        end
        local you
        for _, p in ipairs(r.players) do
            if p.you then you = p end
        end
        local mine = M.medals(you, deps.info)
        for j = 0, M.MINE_MEDALS - 1 do
            local m = mine[j + 1]
            deps.setShown(s["MineCell" .. j], m ~= nil)
            medal(s, "Mine" .. j, m)
            deps.setText(s["Mine" .. j .. "Cap"], m and string.upper(m.title) or "")
        end
        deps.setText(s.MineKicker, "YOUR MEDALS" .. (you and (you.medalCount or 0) > 0 and
            ("   /   " .. tostring(you.medalCount)) or ""))
        deps.setText(s.MineNote, #mine == 0 and "NONE THIS MATCH." or
            (#mine > M.MINE_MEDALS and ("AND " .. tostring(#mine - M.MINE_MEDALS) .. " MORE KINDS") or ""))
        local bests = M.bests(r)
        for k = 0, 3 do
            local b = bests[k + 1]
            deps.setShown(s["Best" .. k], b ~= nil)
            if b then
                deps.setText(s["Best" .. k .. "Label"], b.label)
                deps.setText(s["Best" .. k .. "Value"], b.value)
                deps.setText(s["Best" .. k .. "Name"], b.name)
            end
        end
    end

    local function timeline(s, r)
        local chart = M.chart(r)
        for i = 0, M.SERIES - 1 do
            local line = chart and chart.series[i + 1]
            deps.setShown(s["LegendSize" .. i], line ~= nil)
            if line then deps.setText(s["Legend" .. i], line.name) end
            for k = 0, M.POINTS - 1 do
                local dot, at = s["Dot" .. i .. "_" .. k], line and line.points[k + 1]
                deps.setShown(dot, at ~= nil)
                if at then pcall(function() dot.Slot:SetPosition({ X = at[1], Y = at[2] }) end) end
            end
        end
        deps.setText(s.ChartKicker, chart and "SCORE OVER TIME" or "SCORE OVER TIME   /   NOT RECORDED FOR THIS MATCH")
        deps.setText(s.ChartMax, chart and tostring(chart.max) or "")
        deps.setText(s.ChartEnd, (tonumber(r.clock) or 0) > 0 and M.clock(r.clock) or "")
        local bars = M.bars(r)
        for i = 0, M.BARS - 1 do
            local v = bars and bars.values[i + 1]
            deps.setShown(s["Bar" .. i .. "Size"], v ~= nil)
            if v then
                pcall(function()
                    s["Bar" .. i .. "Size"]:SetHeightOverride(math.max(2, math.floor(M.BAR * v / bars.max + 0.5)))
                end)
            end
        end
        deps.setText(s.BarsKicker, bars and bars.minutes > 1 and ("KILLS EVERY " .. bars.minutes .. " MINUTES") or
            "KILLS A MINUTE")
        deps.setText(s.BarsNote, bars and ("PEAK  " .. tostring(bars.max)) or "")
    end

    --- Shows the chosen page and marks its tab.
    function self.pages(s)
        deps.setShown(s.Tabs, true)
        for i = 0, M.TABS - 1 do
            deps.tint(s["TabLabel" .. i], i == self.tab and WHITE or GREY)
            pcall(function() s["TabInk" .. i]:SetVisibility(i == self.tab and 3 or 2) end)
        end
        deps.setShown(s.PageOverview, self.tab == 0)
        deps.setShown(s.PageBoard, self.tab == 1)
        deps.setShown(s.PageTimeline, self.tab == 2)
    end

    --- Fills the overview and the timeline from results `r` (the scoreboard
    --- page is main.lua's) and shows the chosen page.
    function self.draw(s, r)
        overview(s, r)
        timeline(s, r)
        self.pages(s)
    end

    --- A tab was clicked.
    function self.choose(s, tab)
        if tab < 0 or tab >= M.TABS then return end
        self.tab = tab
        self.pages(s)
    end

    self.gold = GOLD
    return self
end

return M

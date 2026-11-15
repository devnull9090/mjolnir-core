-- The post-game screen's pages (mods/MJOLNIRLobby/Scripts/postgame.lua): what
-- they show, from results, with no game. Run from the repository root.
local View = dofile("mods/MJOLNIRLobby/Scripts/postgame.lua")
local checks = 0
local function eq(actual, expected, label)
    checks = checks + 1
    assert(actual == expected, (label or "value") .. ": expected " .. tostring(expected) .. ", got " .. tostring(actual))
end

-- The DLL's catalogue, stood in for: title, glyph, colour, show, class, rank.
local INFO = {
    multikill_x2 = { "Double Kill", "Medal", "medal", 2, 0, 1 },
    multikill_x3 = { "Triple Kill", "Medal", "medal", 2, 0, 2 },
    ["5_in_a_row"] = { "Killing Spree", "Spree", "spree", 2, 1, 1 },
    first_blood = { "First Blood", "FirstBlood", "blood", 2, 3, 1 },
    headshot_kill = { "Headshot", "Headshot", "headshot", 1, 3, 0 },
    revenge_kill = { "Revenge", "Medal", "medal", 1, 6, 0 },
}
local function info(name)
    local i = INFO[name]
    if i then return i[1], i[2], i[3], i[4], i[5], i[6] end
end

-- A numeral stands in for the glyph on multi-kills and sprees only.
eq(View.mark("multikill_x2"), "x2"); eq(View.mark("10_in_a_row"), "10")
eq(View.mark("headshot_kill"), nil); eq(View.mark("sniper_5x"), nil)

-- A player's medals: the rarest class first, then the higher rank, then the
-- most earned; a title, a glyph and a colour each.
local p = { medals = { { name = "headshot_kill", count = 9 }, { name = "revenge_kill", count = 2 },
    { name = "multikill_x2", count = 3 }, { name = "multikill_x3", count = 1 }, { name = "5_in_a_row", count = 1 },
    { name = "mystery_medal", count = 1 } } }
local shown = View.medals(p, info)
local order = {}
for i, m in ipairs(shown) do order[i] = m.name end
eq(table.concat(order, " "), "multikill_x3 multikill_x2 5_in_a_row headshot_kill revenge_kill mystery_medal")
eq(shown[1].title, "Triple Kill"); eq(shown[1].mark, "x3"); eq(shown[2].count, 3)
eq(shown[4].glyph, "Headshot"); eq(shown[4].ink, View.INK.headshot)
eq(shown[5].glyph, "Revenge", "this screen's own glyph for it")
eq(shown[6].title, "mystery medal", "an unknown medal keeps its name"); eq(shown[6].glyph, "Medal")
eq(#View.medals(nil, info), 0); eq(#View.medals({}, info), 0)

-- The podium: by score, then kills, then fewer deaths, across both teams.
local function player(name, score, kills, deaths, more)
    local q = { name = name, score = tostring(score), kills = tostring(kills), deaths = tostring(deaths) }
    for k, v in pairs(more or {}) do q[k] = v end
    return q
end
local r = { clock = 300, players = {
    player("Kat", 9, 9, 4, { team = "Red", medalCount = 4, series = { 0, 3, 6, 9 }, killsAt = { 0, 3, 6, 9 } }),
    player("Jun", 2, 2, 9, { team = "Red", series = { 0, 0, 1, 2 }, killsAt = { 0, 0, 1, 2 } }),
    player("Six", 12, 12, 3, { team = "Blue", you = true, hubName = "Noble Six", medalCount = 7,
        series = { 2, 6, 10, 12 }, killsAt = { 2, 6, 10, 12 } }),
    player("Carter", 9, 8, 2, { team = "Blue", series = { 1, 4, 7, 9 }, killsAt = { 1, 4, 6, 8 } }),
    player("Emile", 0, 0, 5, {}),
} }
local top = View.podium(r)
eq(top[1].name, "Six"); eq(top[2].name, "Kat", "more kills breaks the tie"); eq(top[3].name, "Carter")
eq(#View.podium({ players = { r.players[1] } }), 1, "one player, one card")
eq(View.ratio(r.players[3]), "4.00"); eq(View.ratio(player("x", 3, 3, 0)), "3.00")

-- The bests.
local bests = View.bests(r)
eq(bests[1].label, "MOST KILLS"); eq(bests[1].value, "12"); eq(bests[1].name, "Noble Six")
eq(bests[2].label, "BEST K/D"); eq(bests[2].name, "Noble Six")
eq(bests[3].label, "MOST MEDALS"); eq(bests[3].value, "7")
eq(bests[4].label, "FEWEST DEATHS"); eq(bests[4].name, "Carter")
eq(#View.bests({ players = { player("Solo", 0, 0, 0) } }), 0, "nothing to boast of")

-- The clock.
eq(View.clock(0), "0:00"); eq(View.clock(75), "1:15"); eq(View.clock(3599.6), "60:00")

-- The chart: the top players' lines, scaled to the highest score, each
-- point inside the plot; the first at the left edge and the last at the right.
local chart = View.chart(r)
eq(chart.max, 12); eq(#chart.series, 4)
eq(chart.series[1].name, "Noble Six"); eq(chart.series[2].name, "Kat"); eq(chart.series[1].final, 12)
local line = chart.series[1].points
eq(#line, 4); eq(line[1][1], 0); eq(line[4][1], View.CHART[1])
eq(line[4][2], View.PAD, "the top score sits at the top, clear of the edge")
eq(line[1][2] > line[4][2], true, "lower scores lower down")
for _, s in ipairs(chart.series) do
    for _, at in ipairs(s.points) do
        assert(at[1] >= 0 and at[1] <= View.CHART[1] and at[2] >= View.PAD and at[2] <= View.CHART[2] - View.PAD)
        checks = checks + 1
    end
end
-- A line is its segments: each from one point to the next, as long as the
-- gap and turned to face it (a rising score turns it up: a negative angle).
local segs = chart.series[1].segments
eq(#segs, 3); eq(segs[1][1], line[1][1]); eq(segs[1][2], line[1][2])
for k, seg in ipairs(segs) do
    local a, b = line[k], line[k + 1]
    local rad = math.rad(seg[4])
    assert(math.abs(a[1] + seg[3] * math.cos(rad) - b[1]) < 1e-6 and math.abs(a[2] + seg[3] * math.sin(rad) - b[2]) < 1e-6,
        "segment " .. k .. " ends at the next point")
    checks = checks + 1
    eq(seg[4] <= 0, true, "a score that does not fall never points down")
end
-- A flat stretch lies flat.
eq(View.chart({ players = { player("x", 1, 1, 0, { series = { 1, 1, 1 } }) } }).series[1].segments[1][4], 0)
eq(View.chart({ players = { player("x", 1, 1, 0) } }), nil, "no series, no chart")

-- The bars: every minute's kills across all players; they add up to the total.
local bars = View.bars(r)
eq(bars.minutes, 1); eq(bars.bars, 5)
-- They span the plot, and the busiest is marked.
eq(bars.width * bars.bars + View.BAR_GAP * (bars.bars - 1) <= View.CHART[1], true)
eq(bars.values[bars.peak], bars.max)
local sum = 0
for _, v in ipairs(bars.values) do sum = sum + v end
eq(sum, 9 + 2 + 12 + 8, "every kill is in a bar")
eq(bars.max >= 1, true)
-- A long match: bars of several minutes, never more than BARS of them.
local long = { clock = 100 * 60, players = { player("x", 50, 50, 0, { killsAt = { 10, 20, 30, 40, 50 } }) } }
local wide = View.bars(long)
eq(wide.minutes, 4); eq(wide.bars, 25); eq(wide.bars <= View.BARS, true)
eq(View.bars({ clock = 0, players = r.players }), nil); eq(View.bars({ clock = 60, players = { player("x", 1, 1, 0) } }), nil)

-- The view over a screen: every widget is a table that takes the calls.
local function widget(name)
    local w = { name = name, visibility = 1, text = nil, Slot = {} }
    function w:SetVisibility(v) self.visibility = v end
    function w:SetText(t) self.text = t end
    function w:SetBrushFromTexture(t) self.texture = t end
    function w:SetColorAndOpacity(c) self.colour = c end
    function w:SetHeightOverride(h) self.height = h end
    function w.Slot:SetPosition(at) w.at = at end
    function w.Slot:SetSize(size) w.size = size end
    function w:SetRenderTransformAngle(a) self.angle = a end
    function w:SetWidthOverride(v) self.width = v end
    function w:SetBrushColor(c) self.brush = c end
    return w
end
local screen = setmetatable({}, { __index = function(t, k)
    local w = widget(k)
    rawset(t, k, w)
    return w
end })
StaticFindObject = function() -- luacheck: ignore
    return {
        MakeSoftObjectPath = function(_, path) return path end,
        Conv_SoftObjPathToSoftObjRef = function(_, path) return path end,
        LoadAsset_Blocking = function(_, path) return { path = path } end,
    }
end
FText = function(v) return v end -- luacheck: ignore
r.players[3].medals = { { name = "multikill_x2", count = 3 }, { name = "headshot_kill", count = 9 } }
local view = View.new({
    setText = function(w, t) w:SetText(t) end,
    setShown = function(w, on) w:SetVisibility(on and 0 or 1) end,
    valid = function(w) return w ~= nil end,
    info = info,
    avatar = function() return true end,
    tint = function(w, c) w.colour = c end,
})
eq(view.available(screen), true)
view.draw(screen, r)
-- The overview is the page showing, its tab marked.
eq(screen.PageOverview.visibility, 0); eq(screen.PageBoard.visibility, 1); eq(screen.PageTimeline.visibility, 1)
eq(screen.TabInk0.visibility, 3); eq(screen.TabInk1.visibility, 2)
-- The podium: the winner's card, their medals, the numeral in place of a glyph.
eq(screen.PodName0.text, "Noble Six"); eq(screen.PodPlace0.text, "1ST   /   YOU"); eq(screen.PodScore0.text, "12")
eq(screen.PodLine0.text, "12 KILLS   /   3 DEATHS   /   4.00 K/D")
eq(screen.PodMedal0_0Size.visibility, 0); eq(screen.PodMedal0_0Mark.text, "x2"); eq(screen.PodMedal0_0Count.text, "x3")
eq(screen.PodMedal0_0GlyphSize.visibility, 1, "no glyph under a numeral")
eq(screen.PodMedal0_1Glyph.texture.path:match("T_MJHud_(%w+)$"), "Headshot"); eq(screen.PodMedal0_1Count.text, "x9")
eq(screen.PodMedal0_2Size.visibility, 1, "no third medal")
eq(screen.PodMedal1_0Size.visibility, 1, "Kat's medals are a count only: none to draw")
-- Your medals, named.
eq(screen.MineCell0.visibility, 0); eq(screen.Mine0Cap.text, "DOUBLE KILL"); eq(screen.MineCell2.visibility, 1)
eq(screen.MineKicker.text, "YOUR MEDALS   /   7")
-- The chart's lines are laid out, the unused segments hidden, and each
-- line ends in a dot with the final score.
eq(screen.Seg0_0.visibility, 0); eq(screen.Seg0_0.at.X, 0); eq(screen.Seg0_0.size.Y, View.LINE)
eq(screen.Seg0_0.angle < 0, true); eq(screen.Seg0_3.visibility, 1)
eq(screen.End0.visibility, 0); eq(screen.EndLabel0.text, "12"); eq(screen.End0.at.X, View.CHART[1] - View.END)
eq(screen.Legend0.text, "Noble Six"); eq(screen.ChartMax.text, "12"); eq(screen.ChartEnd.text, "5:00")
eq(screen.Bar0Size.visibility, 0); eq(screen.Bar5Size.visibility, 1); eq(screen.Bar0Size.height >= 2, true)
eq(screen.Bar0Size.width, View.bars(r).width); eq(screen.BarsEnd.text, "5:00")
eq(screen["Bar" .. (View.bars(r).peak - 1)].brush.G, 0.80, "the busiest minute is gold")
-- A tab click turns the page.
view.choose(screen, 2)
eq(screen.PageTimeline.visibility, 0); eq(screen.PageOverview.visibility, 1); eq(screen.TabInk2.visibility, 3)
view.choose(screen, 9)
eq(screen.PageTimeline.visibility, 0, "a tab that is not there changes nothing")
print("Post-game pages: " .. checks .. " checks passed")

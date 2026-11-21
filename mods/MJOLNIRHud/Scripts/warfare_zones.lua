-- Pelican Warfare zone tiles: WBP_MJOLNIRWarfareZones (chunk 958) under the
-- match score, one tile per capture site. Everything shown comes from the
-- accepted native snapshot (warfare.lua: s.sites, packed by Megalo): owner,
-- who is standing in the zone, and capture progress in steps. Nothing here
-- infers a capture; the only local reading is whether the local player is
-- inside a zone, for the gold you-are-here rim.
--
-- tick() runs on the HUD poll (twice a second at most it sees a new sample);
-- frame() eases the capture bars and pulses a contested rim, and does nothing
-- once every bar has arrived and no zone is contested.
local Zones = {}
local CLASS = "/Game/MJOLNIR/UI/WBP_MJOLNIRWarfareZones.WBP_MJOLNIRWarfareZones_C"
local TRACK = 144          -- the bar's full width (build_pwr_warfare_zones.py)
local EASE = 0.45          -- seconds for a bar to reach a new sample
local COLLAPSED, HIDDEN_NO_HIT = 1, 3

local RED = { R = 1, G = 0.32, B = 0.28 }
local BLUE = { R = 0.3, G = 0.65, B = 1 }
local LINE = { R = 0.24, G = 0.49, B = 0.63 }
local GOLD = { R = 1, G = 0.80, B = 0.35 }
local GREY = { R = 0.46, G = 0.61, B = 0.70 }
local WHITE = { R = 0.88, G = 0.95, B = 1 }
local TEAM = { [1] = RED, [2] = BLUE }
local NAME = { [1] = "RED", [2] = "BLUE" }

local function rgba(c, a) return { R = c.R, G = c.G, B = c.B, A = a } end
local function mix(a, b, t)
    return { R = a.R + (b.R - a.R) * t, G = a.G + (b.G - a.G) * t, B = a.B + (b.B - a.B) * t }
end

--- What a tile says and how it looks, from one site's state. `here`: the
--- local player stands in it. Pure, for the tests.
function Zones.look(site, here, steps)
    steps = steps or 16
    local owner, red, blue, progress = site.owner, site.red, site.blue, site.progress
    local lead = (progress or 0) > 0 and 1 or (progress or 0) < 0 and 2 or 0
    local present = red and not blue and 1 or blue and not red and 2 or 0
    local look = {
        rim = owner > 0 and TEAM[owner] or LINE, rimAlpha = owner > 0 and 0.95 or 0.55,
        tint = owner > 0 and TEAM[owner] or LINE, tintAlpha = owner > 0 and 0.22 or 0,
        letter = owner > 0 and TEAM[owner] or WHITE,
        state = owner > 0 and NAME[owner] or "NEUTRAL", stateColor = owner > 0 and TEAM[owner] or GREY,
        fill = progress and math.abs(progress) / steps or (owner > 0 and 1 or 0),
        ink = lead > 0 and TEAM[lead] or (owner > 0 and TEAM[owner] or LINE),
        red = red, blue = blue, contested = red and blue,
    }
    if red and blue then
        look.state, look.stateColor = "CONTESTED", WHITE
    elseif present > 0 and owner ~= present then
        -- The team in the zone first neutralises the other's hold, then takes it.
        if owner == 0 then look.state = "CAPTURING" else look.state = "NEUTRALIZING" end
        look.stateColor = TEAM[present]
    end
    if here then look.rim, look.rimAlpha = GOLD, 1 end
    return look
end

function Zones.new(deps)
    local self = { shown = false, bars = {}, looks = {} }
    local widget

    local function part(name)
        local w = widget and widget[name]
        if w and w:IsValid() then return w end
        return nil
    end

    local function ensure()
        if widget and widget:IsValid() then return true end
        widget = deps.createWidget(CLASS, 42)
        if not widget then return false end
        for i = 0, 2 do self.bars[i] = { at = 0, from = 0, to = 0, t = 0 } end
        return true
    end

    function self.hide()
        if self.shown and widget and widget:IsValid() then
            pcall(function() widget:SetVisibility(COLLAPSED) end)
        end
        self.shown = false
    end

    local function paint(i, look)
        local p = "Zone" .. i
        pcall(function()
            part(p .. "Rim"):SetBrushColor(rgba(look.rim, look.rimAlpha))
            part(p .. "Tint"):SetBrushColor(rgba(look.tint, look.tintAlpha))
            part(p .. "Letter"):SetColorAndOpacity({ SpecifiedColor = rgba(look.letter, 1), ColorUseRule = 0 })
            part(p .. "State"):SetText(FText(look.state))
            part(p .. "State"):SetColorAndOpacity({ SpecifiedColor = rgba(look.stateColor, 1), ColorUseRule = 0 })
            part(p .. "Ink"):SetBrushColor(rgba(look.ink, 1))
            part(p .. "RedPipSize"):SetVisibility(look.red and HIDDEN_NO_HIT or COLLAPSED)
            part(p .. "BluePipSize"):SetVisibility(look.blue and HIDDEN_NO_HIT or COLLAPSED)
        end)
    end

    --- `s`: the accepted snapshot (or nil); `spots`: the three authored sites;
    --- `at`: the local player's position, or nil.
    function self.tick(s, spots, at, hidden, now)
        if hidden or not s or s.phase ~= 2 or not s.sites then return self.hide() end
        if not ensure() then return end
        if not self.shown then
            pcall(function() widget:SetVisibility(HIDDEN_NO_HIT) end)
            self.shown = true
        end
        for i = 0, 2 do
            local site = s.sites[i + 1]
            local here = at and spots and spots[i + 1] and deps.inside(spots[i + 1], at) or false
            local look = Zones.look(site, here)
            local key = table.concat({ look.state, tostring(look.red), tostring(look.blue), tostring(here),
                look.rim.R, look.ink.R, look.tintAlpha }, "|")
            if key ~= self.looks[i] then
                self.looks[i] = key
                paint(i, look)
            end
            self.contested = self.contested or {}
            self.contested[i] = look.contested and look or nil
            local bar = self.bars[i]
            if math.abs(look.fill - bar.to) > 1e-6 then
                bar.from, bar.to, bar.t = bar.at, look.fill, now
            end
        end
        self.frame(now)
    end

    --- Ease the bars toward their samples and pulse contested rims.
    function self.frame(now)
        if not self.shown then return end
        for i = 0, 2 do
            local bar = self.bars[i]
            if bar and bar.at ~= bar.to then
                local k = math.min(1, (now - bar.t) / EASE)
                bar.at = bar.from + (bar.to - bar.from) * k
                if k >= 1 then bar.at = bar.to end
                local fill = part("Zone" .. i .. "Fill")
                if fill then pcall(function() fill:SetWidthOverride(TRACK * bar.at) end) end
            end
            local look = self.contested and self.contested[i]
            if look then
                -- Red and blue both in the zone: the rim breathes between them.
                local t = 0.5 + 0.5 * math.sin(now * math.pi * 2 * 0.9)
                local rim = part("Zone" .. i .. "Rim")
                if rim then pcall(function() rim:SetBrushColor(rgba(mix(RED, BLUE, t), 1)) end) end
            end
        end
    end

    return self
end

return Zones

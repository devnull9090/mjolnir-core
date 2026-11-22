-- Pelican Warfare's warmup countdown: one large number in the middle of the
-- screen for the last seconds before insertion, then "DEPLOY" for a moment.
-- Megalo counts the warmup down in whole seconds (blam-megalo warfare.rs
-- CLOCK), so every client shows the same number. Text changes only when the
-- number does; the widget is made once and hidden, never removed (removing a
-- Lua-made widget hung the game once; see hill.lua).
--
-- Size and face: a TextBlock's font can be set from Lua only before the
-- widget first reaches the screen (Slate reads it once, at AddToViewport;
-- SetFont afterwards changes nothing, and a hand-built font struct passed to
-- SetFont crashed the game, 2026-11-22). Render scale would blur the glyphs.
-- So the font is written into the block's own struct before it is shown.
-- The face is the game's own match-start countdown's (WBP_MatchStartCountdown:
-- Font_Oxanium, Medium, its cyan); 420 pt makes a digit about a sixth of the
-- screen's height at any resolution (UI scale 0.333 at 720p, 1.0 at 2160p).
local Countdown = {}

-- Seconds of warmup shown large. Earlier seconds stay in the status line.
Countdown.BIG = 10
-- How long "DEPLOY" stays up once insertion starts.
Countdown.DEPLOY_SECONDS = 2
Countdown.FONT = "/Game/Fonts/Font_Oxanium.Font_Oxanium"
Countdown.TYPEFACE = "Medium"
Countdown.SIZE = 420

local COLLAPSED, VISIBLE_NO_HIT_TEST = 1, 3
local CYAN = { R = 0.366, G = 0.871, B = 0.929, A = 1 }
local GOLD = { R = 1, G = 0.78, B = 0.25, A = 1 }

--- What to show for a snapshot: the text and its colour, or nil.
--- `launchedAt` is when this client first saw insertion begin.
function Countdown.view(s, now, launchedAt)
    if not s then return nil end
    if s.phase == 0 then
        local left = s.globals and s.globals[4]
        if type(left) == "number" and left > 0 and left <= Countdown.BIG then
            return tostring(left), left <= 3 and GOLD or CYAN
        end
    elseif s.phase == 1 and launchedAt and now - launchedAt < Countdown.DEPLOY_SECONDS then
        return "DEPLOY", GOLD
    end
    return nil
end

-- deps.object(path), deps.construct(class, outer, name), deps.FName and
-- deps.FText default to the UE4SS globals; tests pass their own.
function Countdown.new(deps)
    deps = deps or {}
    if not deps.object then
        local found = {}
        deps.object = function(path)
            local o = found[path]
            if o and o:IsValid() then return o end
            o = StaticFindObject(path)
            found[path] = o
            return o
        end
    end
    deps.construct = deps.construct or StaticConstructObject
    deps.FName = deps.FName or FName
    deps.FText = deps.FText or FText
    local self = {}
    local widget, text, shown, launchedAt, lastPhase, instance

    local function build(pc)
        local library = deps.object("/Script/UMG.Default__WidgetBlueprintLibrary")
        local w = library:Create(pc, deps.object("/Script/UMG.UserWidget"), pc)
        local tree = w.WidgetTree
        local t = deps.construct(deps.object("/Script/UMG.TextBlock"), tree, deps.FName("MJOLNIRWarfareCountdown"))
        tree.RootWidget = t
        -- Before AddToViewport: the only time a font write takes effect.
        local font = deps.object(Countdown.FONT)
        local f = t.Font
        if font and font:IsValid() then
            f.FontObject = font
            f.TypefaceFontName = deps.FName(Countdown.TYPEFACE)
        end
        f.Size = Countdown.SIZE
        t:SetShadowOffset({ X = 3, Y = 3 })
        t:SetShadowColorAndOpacity({ R = 0, G = 0, B = 0, A = 0.7 })
        w:AddToViewport(42)
        w:SetAnchorsInViewport({ Minimum = { X = 0.5, Y = 0.36 }, Maximum = { X = 0.5, Y = 0.36 } })
        w:SetAlignmentInViewport({ X = 0.5, Y = 0.5 })
        return w, t
    end

    function self.hide()
        if shown and widget and widget:IsValid() then
            pcall(function() widget:SetVisibility(COLLAPSED) end)
        end
        shown = nil
    end

    --- Called with each HUD update (twice a second in warmup).
    function self.update(pc, s, now)
        if s and s.instance ~= instance then instance, launchedAt, lastPhase = s.instance, nil, nil end
        if s and s.phase == 1 and lastPhase == 0 then launchedAt = now end
        lastPhase = s and s.phase or nil
        local words, colour = Countdown.view(s, now, launchedAt)
        if not words then return self.hide() end
        if not (widget and widget:IsValid() and text and text:IsValid()) then
            widget, text = build(pc)
            shown = nil
        end
        if shown ~= words then
            text:SetText(deps.FText(words))
            text:SetColorAndOpacity({ SpecifiedColor = colour, ColorUseRule = 0 })
            widget:SetVisibility(VISIBLE_NO_HIT_TEST)
            shown = words
        end
    end

    return self
end

return Countdown

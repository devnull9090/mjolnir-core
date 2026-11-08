-- MJOLNIR HUD: a marker on the screen for a spot in the world.
--
-- No Megalo waypoint reaches Unreal (docs/game_modes.md, B4), so this draws its
-- own: a badge over the spot with its distance under it, which slides to the
-- edge of the screen and points the way to turn when the spot is out of view.
-- Everything is made from Lua and the game type icons, so it needs nothing
-- cooked beyond them. Scripts/hill.lua holds one per marked thing.
--
-- `point` says what to mark a few times a second. `frame` moves the badge on
-- every frame, from the camera, so it stays on the spot while the player turns:
-- reading the camera costs about 10 microseconds.

local Waypoint = {}

local COLLAPSED = 1 -- ESlateVisibility
local VISIBLE_NO_HIT_TEST = 4
local ICON_ROOT = "/Game/MJOLNIR/UI/ModeIcons/T_MJMode_"
-- What an older UI container, without these two textures, draws instead.
local ICON_STAND_INS = { Juggernaut = "Slayer", Race = "Ctf" }
local WIDTH, HEIGHT = 420, 300 -- the widget, Slate units: about 0.36 of a pixel at 720p
local BADGE_Y = 110 -- the badge's centre, down from the widget's top
local BADGE, ICON, ARROW_OFFSET = 88, 64, 100
local MARGIN_X, MARGIN_Y = 0.05, 0.14 -- of the screen: clear of the score and the weapon
local SIZE_EVERY = 1 -- seconds between looks at the viewport's size
local CENTRE_FADE = 0.1 -- of the screen's height: a marker this near the crosshair fades
local FADED = 0.35
local PULSE_HZ = 1.5
local MOVE_PIXELS = 0.4
local MAX_ERRORS = 10
local BACKING = { R = 0, G = 0, B = 0, A = 0.55 }
local WHITE = { R = 1, G = 1, B = 1, A = 1 }

local ARROW = "\u{25B2}"
local WORDS_Y = 100 -- under the badge, or over it when the arrow points down

--- The words under the badge: `metres`, and `level` as Hill.bearing gives it.
--- In words, not an arrow: the arrow on the badge says which way to turn.
function Waypoint.label(metres, level)
    return string.format("%d M%s", metres, level or "")
end

--- Whether an arrow at `angle` would land on the words under the badge.
function Waypoint.wordsOver(angle)
    return angle ~= nil and math.abs(angle) > 120
end

--- Where `target` { x, y, z } falls on a `width` by `height` screen, from a
--- camera `view` { x, y, z, pitch, yaw, fov }, degrees, fov across the width.
--- Fills `out` (x, y, seen, angle) and returns it. A spot inside the margins is
--- `seen`. Any other sits on the margin's edge, on the line from the screen's
--- centre towards it, with `angle` the way to turn: 0 up, 90 right. Behind the
--- camera, turning left or right is the answer, whatever the height, so that
--- line runs along the bottom.
function Waypoint.project(view, target, width, height, marginX, marginY, out)
    out = out or {}
    local yaw, pitch = math.rad(view.yaw), math.rad(view.pitch)
    local cy, sy, cp, sp = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch)
    local dx, dy, dz = target.x - view.x, target.y - view.y, target.z - view.z
    local ahead = dx * cp * cy + dy * cp * sy + dz * sp
    local right = dy * cy - dx * sy
    local up = dz * cp - (dx * cy + dy * sy) * sp
    local halfW, halfH = width / 2, height / 2
    local limitX, limitY = halfW - marginX, halfH - marginY
    local ex, ey
    if ahead > 1 then
        local scale = halfW / math.tan(math.rad(view.fov) / 2)
        ex, ey = right / ahead * scale, -up / ahead * scale
        if math.abs(ex) <= limitX and math.abs(ey) <= limitY then
            out.x, out.y, out.seen, out.angle = halfW + ex, halfH + ey, true, nil
            return out
        end
    else
        ex, ey = right, math.max(-ahead, 1)
    end
    local k = math.min(limitX / math.max(math.abs(ex), 1e-6), limitY / math.max(math.abs(ey), 1e-6))
    out.x, out.y, out.seen = halfW + ex * k, halfH + ey * k, false
    out.angle = math.deg(math.atan(ex, -ey))
    return out
end

--- How clear a marker at `x`, `y` should be: faded over the crosshair, so it
--- does not get in the way of aiming, and pulsing for a `pulse` at `now`.
function Waypoint.opacity(x, y, width, height, pulse, now)
    local dx, dy = x - width / 2, y - height / 2
    local near = height * CENTRE_FADE
    local alpha = dx * dx + dy * dy < near * near and FADED or 1
    if pulse then alpha = alpha * (0.7 + 0.3 * math.sin(now * 2 * math.pi * PULSE_HZ)) end
    return alpha
end

local function loadTexture(name)
    local library = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
    local ok, tex = pcall(function()
        local path = ICON_ROOT .. name .. ".T_MJMode_" .. name
        return library:LoadAsset_Blocking(library:Conv_SoftObjPathToSoftObjRef(library:MakeSoftObjectPath(path)))
    end)
    if ok and tex and tex:IsValid() then return tex end
end

local function child(canvas, tree, class, name, x, y, width, height)
    local w = StaticConstructObject(StaticFindObject("/Script/UMG." .. class), tree, FName(name))
    local slot = canvas:AddChildToCanvas(w)
    slot:SetAlignment({ X = 0.5, Y = 0.5 })
    slot:SetPosition({ X = x, Y = y })
    if width then
        slot:SetSize({ X = width, Y = height })
    else
        slot:SetAutoSize(true)
    end
    return w
end

local function text(canvas, tree, name, x, y, scale)
    local t = child(canvas, tree, "TextBlock", name, x, y)
    t:SetColorAndOpacity({ SpecifiedColor = WHITE, ColorUseRule = 0 })
    t:SetShadowOffset({ X = 1.5, Y = 1.5 })
    t:SetShadowColorAndOpacity({ R = 0, G = 0, B = 0, A = 0.9 })
    t:SetRenderScale({ X = scale, Y = scale })
    return t
end

--- `log(text)` reports a marker that cannot be made or has stopped working.
function Waypoint.new(log)
    local self = {}
    local widget, badge, icon, words, arrow
    local target, label, colour, iconName, pulse
    local width, height, sizeAt = 0, 0, 0
    local view, place = {}, {}
    local shownX, shownY, shownAngle, shownAlpha, shown, shownOver
    local errors, failed = 0, false

    local function alive()
        return widget and widget:IsValid() and icon and icon:IsValid() and words and words:IsValid()
    end

    local function build(pc)
        local library = StaticFindObject("/Script/UMG.Default__WidgetBlueprintLibrary")
        local w = library:Create(pc, StaticFindObject("/Script/UMG.UserWidget"), pc)
        local tree = w.WidgetTree
        local canvas = StaticConstructObject(StaticFindObject("/Script/UMG.CanvasPanel"), tree, FName("MJOLNIRWaypoint"))
        tree.RootWidget = canvas
        local x = WIDTH / 2
        badge = child(canvas, tree, "Image", "MJOLNIRWaypointBadge", x, BADGE_Y, BADGE, BADGE)
        badge:SetColorAndOpacity(BACKING)
        badge:SetRenderTransformAngle(45)
        icon = child(canvas, tree, "Image", "MJOLNIRWaypointIcon", x, BADGE_Y, ICON, ICON)
        arrow = text(canvas, tree, "MJOLNIRWaypointArrow", x, BADGE_Y, 3.6)
        arrow:SetText(FText(ARROW))
        words = text(canvas, tree, "MJOLNIRWaypointWords", x, BADGE_Y + WORDS_Y, 1.5)
        w:AddToViewport(40)
        w:SetDesiredSizeInViewport({ X = WIDTH, Y = HEIGHT })
        w:SetAlignmentInViewport({ X = 0.5, Y = BADGE_Y / HEIGHT })
        widget = w
        label, colour, iconName, shown, shownX, shownY, shownAngle, shownAlpha, shownOver =
            nil, nil, nil, nil, nil, nil, nil, nil, nil
    end

    local function showWidget(on)
        if on == shown or not (widget and widget:IsValid()) then return end
        shown = on
        widget:SetVisibility(on and VISIBLE_NO_HIT_TEST or COLLAPSED)
    end

    local function measure(pc, now)
        if now < sizeAt then return end
        sizeAt = now + SIZE_EVERY
        -- Both sizes come back in the first table.
        local size = {}
        pc:GetViewportSize(size, {})
        width, height = size.SizeX or 0, size.SizeY or 0
    end

    --- Hide, never remove: RemoveFromParent hung the game once.
    function self.hide()
        target = nil
        pcall(showWidget, false)
    end

    --- Mark `spot` { x, y, z }. `paint` is { R, G, B } for the icon, `name` an
    --- icon's (T_MJMode_<name>), `words` what goes under it, `flashing` for a
    --- marker that wants attention. False when no marker can be made, so the
    --- caller keeps its line of text.
    function self.point(pc, spot, paint, name, line, flashing, now)
        if failed then return false end
        local ok, err = pcall(function()
            if not alive() then build(pc) end
            measure(pc, now)
            if name ~= iconName then
                iconName = name
                local tex = loadTexture(name) or (ICON_STAND_INS[name] and loadTexture(ICON_STAND_INS[name]))
                icon:SetVisibility(tex and VISIBLE_NO_HIT_TEST or COLLAPSED)
                if tex then icon:SetBrushFromTexture(tex, false) end
            end
            if paint ~= colour then
                colour = paint
                local tint = { R = paint[1], G = paint[2], B = paint[3], A = 1 }
                icon:SetColorAndOpacity(tint)
                arrow:SetColorAndOpacity({ SpecifiedColor = tint, ColorUseRule = 0 })
            end
            if line ~= label then
                label = line
                words:SetText(FText(line))
            end
        end)
        if not ok then
            failed = true
            if log then log("waypoint off, the line stays: " .. tostring(err)) end
            return false
        end
        target = target or {}
        target.x, target.y, target.z = spot.x, spot.y, spot.z
        pulse = flashing
        return true
    end

    --- Move the spot of a marker already up, every frame for one that follows
    --- something: no widget work, and nothing when nothing is marked.
    function self.aim(x, y, z)
        if target then target.x, target.y, target.z = x, y, z end
    end

    local function move(now)
        local spot = Waypoint.project(view, target, width, height, width * MARGIN_X, height * MARGIN_Y, place)
        if not shownX or math.abs(spot.x - shownX) > MOVE_PIXELS or math.abs(spot.y - shownY) > MOVE_PIXELS then
            shownX, shownY = spot.x, spot.y
            widget:SetPositionInViewport({ X = spot.x, Y = spot.y }, true)
        end
        local angle = spot.angle
        if angle ~= shownAngle and (not angle or not shownAngle or math.abs(angle - shownAngle) > 1) then
            if not angle then
                arrow:SetVisibility(COLLAPSED)
            else
                if not shownAngle then arrow:SetVisibility(VISIBLE_NO_HIT_TEST) end
                local r = math.rad(angle)
                arrow:SetRenderTranslation({ X = math.sin(r) * ARROW_OFFSET, Y = -math.cos(r) * ARROW_OFFSET })
                arrow:SetRenderTransformAngle(angle)
            end
            shownAngle = angle
            local over = Waypoint.wordsOver(angle)
            if over ~= shownOver then
                shownOver = over
                words:SetRenderTranslation({ X = 0, Y = over and -2 * WORDS_Y or 0 })
            end
        end
        local alpha = Waypoint.opacity(spot.x, spot.y, width, height, pulse, now)
        if not shownAlpha or math.abs(alpha - shownAlpha) > 0.02 then
            shownAlpha = alpha
            widget:SetRenderOpacity(alpha)
        end
    end

    --- Every frame, from the local player's controller.
    function self.frame(pc, now)
        if not target or failed or width == 0 then return end
        local ok, err = pcall(function()
            if not alive() then return end
            local camera = pc.PlayerCameraManager
            if not (camera and camera:IsValid()) then return end
            local at, facing = camera:GetCameraLocation(), camera:GetCameraRotation()
            view.x, view.y, view.z = at.X, at.Y, at.Z
            view.pitch, view.yaw, view.fov = facing.Pitch, facing.Yaw, camera:GetFOVAngle()
            move(now)
            showWidget(true)
        end)
        if not ok then
            errors = errors + 1
            if errors >= MAX_ERRORS then
                failed = true
                self.hide()
                if log then log("waypoint off after repeated errors: " .. tostring(err)) end
            end
        end
    end

    return self
end

return Waypoint

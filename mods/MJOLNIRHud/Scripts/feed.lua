-- MJOLNIR HUD: the kill feed's rows (docs/multiplayer_hud.md).
--
-- Every line that reaches the feed (a kill, a suicide, a join, a medal ...)
-- is one entry pushed here. WBP_MJOLNIRKillFeed has a pool of ROWS rows, all
-- at one anchor; an entry borrows a row for its life and is stacked by its
-- render translation, newest at the bottom.
--
-- A row slides in from the left as it fades in, rises when a newer one
-- arrives, and fades out after HOLD seconds; when more than VISIBLE lines
-- are up, the oldest leaves at once. Every pose is a function of the time
-- alone, never of the frames between: the per-frame hook can run twice in a
-- frame (once per player controller) or not at all, and the poll draws the
-- same picture.
--
-- An entry: { lead, leadColor, leadAvatar, weapon (the game's texture path),
-- glyph, glyphColor, weaponGlyph, mod, modColor, tail, tailColor,
-- tailAvatar, note, accent, you (a gold rim: the line names the local
-- player), hold }. The avatars are textures (Scripts/hubnames.lua).

local Feed = {}

Feed.ROWS = 7          -- FeedEdge0..6
Feed.VISIBLE = 6
Feed.STEP = 48         -- a row's 40 plus its 2+2 rim, and a gap
Feed.HOLD = 6
Feed.ENTER = 0.28
Feed.EXIT = 0.5
Feed.FAST_EXIT = 0.18  -- the oldest, pushed out by a seventh line
Feed.MOVE = 0.24
Feed.FLASH = 0.8
local SLIDE_IN, SLIDE_OUT = 44, 28

local WEAPON_HEIGHT = 28
local GLYPH_SIZE = 26

-- ESlateVisibility
local SHOWN, COLLAPSED = 3, 1

local function clamp01(p)
    if p < 0 then return 0 elseif p > 1 then return 1 end
    return p
end

--- Ease out (cubic): fast, then settling.
function Feed.ease(p)
    p = clamp01(p)
    local q = 1 - p
    return 1 - q * q * q
end
local ease = Feed.ease

function Feed.new()
    local free = {}
    for i = 0, Feed.ROWS - 1 do free[#free + 1] = i end
    return { entries = {}, free = free, hide = {} }
end

local function yOf(e, t)
    local target = -e.slot * Feed.STEP
    if not e.moveAt then return target end
    local p = (t - e.moveAt) / Feed.MOVE
    if p >= 1 then return target end
    return e.moveFrom + (target - e.moveFrom) * ease(p)
end

--- Newest at the bottom: slot 0 is the newest entry.
local function relayout(state, t)
    local n = #state.entries
    for i, e in ipairs(state.entries) do
        local slot = n - i
        if e.slot == nil then
            e.slot = slot
        elseif e.slot ~= slot then
            e.moveFrom = yOf(e, t)
            e.moveAt = t
            e.slot = slot
        end
    end
end

local function release(state, index)
    local e = table.remove(state.entries, index)
    state.free[#state.free + 1] = e.row
    state.hide[#state.hide + 1] = e.row
end

--- Adds a line now (`t`). Returns the entry.
function Feed.push(state, e, t)
    -- No row left: the oldest goes at once.
    if #state.free == 0 then release(state, 1) end
    e.at = t
    e.leaveAt = t + (e.hold or Feed.HOLD)
    e.row = table.remove(state.free, 1)
    e.fresh = true
    state.entries[#state.entries + 1] = e
    -- Past VISIBLE lines on screen, the oldest still up starts to leave.
    local up = 0
    for i = #state.entries, 1, -1 do
        local o = state.entries[i]
        if t < o.leaveAt then
            up = up + 1
            if up > Feed.VISIBLE then
                o.leaveAt = t
                o.exit = Feed.FAST_EXIT
            end
        end
    end
    relayout(state, t)
    return e
end

--- Drops the lines that have finished leaving; the rest close up.
function Feed.step(state, t)
    local removed = false
    for i = #state.entries, 1, -1 do
        local e = state.entries[i]
        if t >= e.leaveAt + (e.exit or Feed.EXIT) then
            release(state, i)
            removed = true
        end
    end
    if removed then relayout(state, t) end
end

--- Where an entry is drawn: x, y (render translation), opacity, flash (1 when
--- it has just arrived, to 0).
function Feed.pose(e, t)
    local x, alpha = 0, 1
    local pin = (t - e.at) / Feed.ENTER
    if pin < 1 then
        local k = ease(pin)
        x, alpha = -SLIDE_IN * (1 - k), k
    end
    if t >= e.leaveAt then
        local p = clamp01((t - e.leaveAt) / (e.exit or Feed.EXIT))
        alpha = alpha * (1 - p)
        x = x - SLIDE_OUT * p * p
    end
    local flash = 1 - clamp01((t - e.at) / Feed.FLASH)
    return x, yOf(e, t), alpha, flash
end

--- Whether anything is moving: entering, rising, flashing or leaving.
function Feed.busy(state, t)
    if #state.hide > 0 then return true end
    for _, e in ipairs(state.entries) do
        if e.fresh or t - e.at < Feed.FLASH or (e.moveAt and t - e.moveAt < Feed.MOVE) or t >= e.leaveAt then
            return true
        end
    end
    return false
end

--------------------------------------------------------------------------------
-- Drawing
--------------------------------------------------------------------------------

local CLEAR = { R = 1, G = 1, B = 1, A = 0 }
local RIM = { R = 1.0, G = 0.80, B = 0.35, A = 0.85 }
local FILL = { R = 0.012, G = 0.03, B = 0.045, A = 0.70 }
local FLASH_FILL = { R = 0.16, G = 0.30, B = 0.40, A = 0.88 }
local FLASH_YOU = { R = 0.40, G = 0.30, B = 0.08, A = 0.88 }
local ACCENT = { R = 0.46, G = 0.79, B = 0.94, A = 1 }
local WHITE = { R = 0.92, G = 0.95, B = 1, A = 1 }

local function call(w, method, ...)
    if not w then return false end
    local args = { ... }
    return pcall(function() return w[method](w, table.unpack(args)) end)
end

local function color(c)
    return { SpecifiedColor = c or WHITE, ColorUseRule = 0 }
end

local function text(w, value, c)
    local shown = value ~= nil and value ~= ""
    call(w, "SetVisibility", shown and SHOWN or COLLAPSED)
    if shown then
        call(w, "SetText", FText(value))
        call(w, "SetColorAndOpacity", color(c))
    end
end

--- Our glyph on an Image (a plain texture brush), tinted.
local function glyphOn(image, Icons, name, tint)
    local tex = Icons.glyph(name)
    if not tex then return false end
    call(image, "SetBrushFromTexture", tex, false)
    call(image, "SetColorAndOpacity", tint or WHITE)
    call(image, "SetRenderScale", { X = 1, Y = 1 })
    return true
end

--- The game's weapon silhouette on an Image, through the game's icon
--- material, mirrored to face the victim. Returns the texture's aspect.
local function weaponOn(image, Icons, path)
    local tex = Icons.load(path)
    local mi = Icons.material()
    if not (tex and mi) then return nil end
    call(image, "SetBrushFromMaterial", mi)
    local ok, mid = call(image, "GetDynamicMaterial")
    if not (ok and mid) then return nil end
    call(mid, "SetTextureParameterValue", FName("InputTexture"), tex)
    call(mid, "SetScalarParameterValue", FName("Empty"), 0)
    call(mid, "SetScalarParameterValue", FName("Equipped"), 1)
    call(image, "SetColorAndOpacity", { R = 1, G = 1, B = 1, A = 1 })
    call(image, "SetRenderScale", { X = -1, Y = 1 })
    return Icons.aspect(tex)
end

local function box(w, name, i)
    return w[name .. i .. "Box"], w[name .. i]
end

--- A player's hub avatar beside their name (round, from the widget's
--- brush); the slot closes up without one.
local function avatarOn(w, name, i, tex)
    local slot, image = box(w, name, i)
    if tex then call(image, "SetBrushFromTexture", tex, false) end
    call(slot, "SetVisibility", tex and SHOWN or COLLAPSED)
end

--- Writes an entry's content into row `i` of the feed widget `w`.
function Feed.paint(w, i, e, Icons)
    call(w["FeedEdge" .. i], "SetBrushColor", e.you and RIM or CLEAR)
    call(w["FeedAccent" .. i], "SetBrushColor", e.accent or ACCENT)

    local glyphBox, glyph = box(w, "FeedGlyph", i)
    local hasGlyph = e.glyph and glyphOn(glyph, Icons, e.glyph, e.glyphColor)
    call(glyphBox, "SetVisibility", hasGlyph and SHOWN or COLLAPSED)

    avatarOn(w, "FeedLeadAvatar", i, e.lead and e.leadAvatar)
    text(w["FeedLead" .. i], e.lead, e.leadColor)

    local weaponBox, weapon = box(w, "FeedWeapon", i)
    local width = nil
    if e.weapon then
        local aspect = weaponOn(weapon, Icons, e.weapon)
        if aspect then width = WEAPON_HEIGHT * aspect end
    end
    if not width and e.weaponGlyph and glyphOn(weapon, Icons, e.weaponGlyph, e.weaponColor) then
        width = GLYPH_SIZE + 2
    end
    call(weaponBox, "SetVisibility", width and SHOWN or COLLAPSED)
    if width then
        call(weaponBox, "SetWidthOverride", width)
        call(weaponBox, "SetHeightOverride", e.weapon and WEAPON_HEIGHT or GLYPH_SIZE + 2)
    end

    local modBox, mod = box(w, "FeedMod", i)
    local hasMod = e.mod and glyphOn(mod, Icons, e.mod, e.modColor)
    call(modBox, "SetVisibility", hasMod and SHOWN or COLLAPSED)

    avatarOn(w, "FeedTailAvatar", i, e.tail and e.tailAvatar)
    text(w["FeedTail" .. i], e.tail, e.tailColor)
    text(w["FeedNote" .. i], e.note, e.noteColor)
end

--- One frame: hides released rows, paints new ones, and poses every row
--- that is moving. `t` is now.
function Feed.draw(state, w, t, Icons)
    Feed.step(state, t)
    for _, row in ipairs(state.hide) do
        local taken = false
        for _, e in ipairs(state.entries) do
            if e.row == row then taken = true end
        end
        if not taken then call(w["FeedEdge" .. row], "SetVisibility", COLLAPSED) end
    end
    state.hide = {}
    for _, e in ipairs(state.entries) do
        local edge = w["FeedEdge" .. e.row]
        if e.fresh then
            e.fresh = false
            Feed.paint(w, e.row, e, Icons)
            call(edge, "SetVisibility", SHOWN)
            e.drawn = nil
        end
        local x, y, alpha, flash = Feed.pose(e, t)
        local d = e.drawn
        if not d or math.abs(d.x - x) > 0.05 or math.abs(d.y - y) > 0.05 then
            call(edge, "SetRenderTranslation", { X = x, Y = y })
        end
        if not d or math.abs(d.alpha - alpha) > 0.004 then
            call(edge, "SetRenderOpacity", alpha)
        end
        if not d or d.flash ~= flash then
            local hot = e.you and FLASH_YOU or FLASH_FILL
            local k = flash * flash
            call(w["FeedRow" .. e.row], "SetBrushColor", {
                R = FILL.R + (hot.R - FILL.R) * k, G = FILL.G + (hot.G - FILL.G) * k,
                B = FILL.B + (hot.B - FILL.B) * k, A = FILL.A + (hot.A - FILL.A) * k })
        end
        e.drawn = { x = x, y = y, alpha = alpha, flash = flash }
    end
end

return Feed

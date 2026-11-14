-- FlyCam's on-screen panels, built from UMG widgets at run time (no cooked
-- widget): the shot list card (Tab / F6) and a short toast after a save,
-- delete, undo or redo. In the Shipping build a UserWidget made from Lua is
-- the only screen route (docs: memory note on UE4SS screen output); this
-- builds a CanvasPanel tree inside one. Panels are hidden, never removed:
-- RemoveFromParent has hung this game.
--
-- Everything is created once per level and updated in place; a refresh only
-- sets texts, colours and visibility.

local Panel = {}
Panel.__index = Panel

local COLLAPSED, HIT_TEST_INVISIBLE = 1, 3
local MAX_ROWS = 20
local S = 1.5 -- overall size: sizes below are at this scale

local C = {
    card = { R = 0.015, G = 0.02, B = 0.03, A = 0.84 },
    accent = { R = 0.30, G = 0.78, B = 1.00, A = 1 },
    good = { R = 0.35, G = 0.90, B = 0.50, A = 1 },
    warn = { R = 1.00, G = 0.62, B = 0.25, A = 1 },
    text = { R = 0.92, G = 0.95, B = 1.00, A = 1 },
    dim = { R = 0.55, G = 0.62, B = 0.70, A = 1 },
    faint = { R = 0.36, G = 0.40, B = 0.46, A = 1 },
    badgeEmpty = { R = 0.16, G = 0.18, B = 0.22, A = 1 },
    rowNone = { R = 0, G = 0, B = 0, A = 0 },
    rowHere = { R = 0.30, G = 0.78, B = 1.00, A = 0.20 },
    rowFlash = { R = 0.35, G = 0.90, B = 0.50, A = 0.28 },
    black = { R = 0, G = 0, B = 0, A = 1 },
}

local function slate(c) return { SpecifiedColor = c, ColorUseRule = 0 } end
local function pad(l, t, r, b) return { Left = l * S, Top = t * S, Right = (r or l) * S, Bottom = (b or t) * S } end

function Panel.new(isValid)
    return setmetatable({ isValid = isValid, built = false, failed = false }, Panel)
end

function Panel:widget(cls, name)
    self.serial = (self.serial or 0) + 1
    return StaticConstructObject(StaticFindObject("/Script/UMG." .. cls), self.tree,
        FName("MJOLNIRFlyCam" .. name .. self.serial))
end

function Panel:text(str, size, color, bold)
    local t = self:widget("TextBlock", "Text")
    t:SetText(FText(str or ""))
    t:SetColorAndOpacity(slate(color or C.text))
    t:SetShadowOffset({ X = 1, Y = 1 })
    t:SetShadowColorAndOpacity({ R = 0, G = 0, B = 0, A = 0.6 })
    pcall(function()
        local f = t.Font
        f.Size = math.floor((size or 16) * S + 0.5)
        if bold then f.TypefaceFontName = FName("Bold") end
        t:SetFont(f)
    end)
    return t
end

function Panel:box(color, padding, radius)
    local b = self:widget("Border", "Box")
    b:SetBrushColor(color)
    b:SetPadding(padding or pad(0, 0))
    if radius then
        pcall(function()
            local brush = b.Background
            brush.DrawAs = 4 -- RoundedBox
            local px = radius * S
            brush.OutlineSettings.CornerRadii = { X = px, Y = px, Z = px, W = px }
            brush.OutlineSettings.RoundingType = 0
            b:SetBrush(brush)
        end)
    end
    return b
end

function Panel:sized(child, width)
    local s = self:widget("SizeBox", "Size")
    s:SetWidthOverride(width * S)
    s:SetContent(child)
    return s
end

local function addV(vbox, child, padding)
    local s = vbox:AddChildToVerticalBox(child)
    if padding then s:SetPadding(padding) end
    return s
end

local function addH(hbox, child, padding)
    local s = hbox:AddChildToHorizontalBox(child)
    s:SetVerticalAlignment(2) -- centre
    if padding then s:SetPadding(padding) end
    return s
end

function Panel:build(pc)
    local lib = StaticFindObject("/Script/UMG.Default__WidgetBlueprintLibrary")
    self.root = lib:Create(pc, StaticFindObject("/Script/UMG.UserWidget"), pc)
    self.tree = self.root.WidgetTree
    local canvas = self:widget("CanvasPanel", "Canvas")
    self.tree.RootWidget = canvas

    -- The card, top left.
    self.card = self:box(C.card, pad(22, 18, 22, 16), 14)
    local cs = canvas:AddChildToCanvas(self.card)
    cs:SetAutoSize(true)
    cs:SetPosition({ X = 40, Y = 110 })
    local v = self:widget("VerticalBox", "Card")
    self.card:SetContent(v)

    local head = self:widget("HorizontalBox", "Head")
    addV(v, head)
    addH(head, self:text("FLYCAM", 22, C.accent, true))
    self.map = self:text("", 22, C.text, true)
    addH(head, self.map, pad(12, 0, 0, 0))
    self.lockBox = self:box(C.good, pad(8, 2), 6)
    self.lockText = self:text("", 12, C.black, true)
    self.lockBox:SetContent(self.lockText)
    addH(head, self.lockBox, pad(16, 0, 0, 0))

    self.cam = self:text("", 14, C.dim)
    addV(v, self.cam, pad(0, 8, 0, 2))
    self.lens = self:text("", 14, C.dim)
    addV(v, self.lens, pad(0, 0, 0, 10))

    self.rows = {}
    for i = 1, MAX_ROWS do
        local row = self:box(C.rowNone, pad(6, 3, 10, 3), 6)
        local h = self:widget("HorizontalBox", "Row")
        row:SetContent(h)
        local badge = self:box(C.badgeEmpty, pad(0, 1), 5)
        local key = self:text("", 14, C.black, true)
        pcall(function() key:SetJustification(1) end) -- centre
        badge:SetContent(key)
        addH(h, self:sized(badge, 30))
        local name = self:text("", 16, C.text, true)
        addH(h, self:sized(name, 230), pad(12, 0, 0, 0))
        local info = self:text("", 13, C.dim)
        addH(h, info, pad(8, 0, 0, 0))
        addV(v, row, pad(0, 1))
        self.rows[i] = { row = row, badge = badge, key = key, name = name, info = info }
    end

    self.more = self:text("", 13, C.faint)
    addV(v, self.more, pad(0, 4, 0, 0))
    self.hints = self:text("", 13, C.faint)
    addV(v, self.hints, pad(0, 10, 0, 0))

    -- The toast, top centre.
    self.toast = self:box(C.card, pad(20, 10), 12)
    local th = self:widget("HorizontalBox", "Toast")
    self.toast:SetContent(th)
    self.toastDot = self:box(C.good, pad(6, 6), 6)
    addH(th, self.toastDot)
    self.toastText = self:text("", 18, C.text, true)
    addH(th, self.toastText, pad(12, 0, 0, 0))
    self.toastHint = self:text("", 14, C.dim)
    addH(th, self.toastHint, pad(14, 0, 0, 0))
    local ts = canvas:AddChildToCanvas(self.toast)
    ts:SetAutoSize(true)
    ts:SetAnchors({ Minimum = { X = 0.5, Y = 0 }, Maximum = { X = 0.5, Y = 0 } })
    ts:SetAlignment({ X = 0.5, Y = 0 })
    ts:SetPosition({ X = 0, Y = 70 })

    self.card:SetVisibility(COLLAPSED)
    self.toast:SetVisibility(COLLAPSED)
    self.root:SetVisibility(HIT_TEST_INVISIBLE)
    self.root:AddToViewport(1001)
    self.built = true
    self.cardShown, self.toastShown, self.toastLeft = false, false, 0
end

--- The panel for this level, built on first use. false if it cannot be.
function Panel:ensure(pc)
    if self.built and self.isValid(self.root) and self.isValid(self.card) then
        local ok, inViewport = pcall(function() return self.root:IsInViewport() end)
        if ok and not inViewport then pcall(function() self.root:AddToViewport(1001) end) end
        return true
    end
    if not pc then return false end
    self.built = false
    local ok, err = pcall(function() self:build(pc) end)
    if not ok then
        if not self.failed then print("[MJOLNIR FlyCam] panel could not be built: " .. tostring(err) .. "\n") end
        self.failed = true
        return false
    end
    return true
end

--- Forget widgets from a level that is going away.
function Panel:reset()
    self.built, self.root, self.card, self.toast = false, nil, nil, nil
    self.cardShown, self.toastShown = false, false
end

function Panel:hideCard()
    if self.cardShown and self.isValid(self.card) then pcall(function() self.card:SetVisibility(COLLAPSED) end) end
    self.cardShown = false
end

function Panel:hideToast()
    if self.toastShown and self.isValid(self.toast) then pcall(function() self.toast:SetVisibility(COLLAPSED) end) end
    self.toastShown, self.toastLeft = false, 0
end

local function keyLabel(n)
    if n == 10 then return "0" end
    return tostring(n)
end

--- model: map, locked, lockNote, cam {X,Y,Z}, rot {Pitch,Yaw,Roll}, fov,
--- speed, shots (sorted list or nil), shotsError, here (shot number the
--- camera sits at), flash (shot number just changed), canUndo, canRedo.
function Panel:showCard(pc, model)
    if not self:ensure(pc) then return false end
    local ok, err = pcall(function()
        self.map:SetText(FText(model.map or "?"))
        self.lockBox:SetBrushColor(model.locked and C.good or C.warn)
        self.lockText:SetText(FText(model.locked and "PLAYER LOCKED" or "PLAYER NOT LOCKED"))
        self.cam:SetText(FText(string.format("X %.0f   Y %.0f   Z %.0f     pitch %.1f   yaw %.1f",
            model.cam.X, model.cam.Y, model.cam.Z, model.rot.Pitch, model.rot.Yaw)))
        self.lens:SetText(FText(string.format("FOV %.1f     speed %d cm/s%s", model.fov,
            math.floor(model.speed + 0.5), model.locked and "" or ("     " .. tostring(model.lockNote or "")))))

        -- Slots 1-10 always (they are the number keys), then any higher shots.
        local byN, extra = {}, {}
        for _, s in ipairs(model.shots or {}) do
            byN[s.n] = s
            if s.n > 10 then extra[#extra + 1] = s end
        end
        local list = {}
        for n = 1, 10 do list[#list + 1] = { n = n, shot = byN[n] } end
        for _, s in ipairs(extra) do list[#list + 1] = { n = s.n, shot = s } end

        for i, r in ipairs(self.rows) do
            local item = list[i]
            if not item or model.shotsError then
                r.row:SetVisibility(COLLAPSED)
            else
                r.row:SetVisibility(HIT_TEST_INVISIBLE)
                local s = item.shot
                r.key:SetText(FText(item.n <= 10 and keyLabel(item.n) or tostring(item.n)))
                r.badge:SetBrushColor(s and C.accent or C.badgeEmpty)
                r.key:SetColorAndOpacity(slate(s and C.black or C.faint))
                if s then
                    r.name:SetText(FText(s.name or ("Shot " .. s.n)))
                    r.name:SetColorAndOpacity(slate(C.text))
                    r.info:SetText(FText(string.format("FOV %.0f    %.0f, %.0f, %.0f", s.fov, s.x, s.y, s.z)))
                else
                    r.name:SetText(FText("empty"))
                    r.name:SetColorAndOpacity(slate(C.faint))
                    r.info:SetText(FText(item.n <= 10 and ("Ctrl+" .. keyLabel(item.n) .. " to save") or ""))
                end
                local bg = C.rowNone
                if model.flash == item.n then bg = C.rowFlash elseif s and model.here == item.n then bg = C.rowHere end
                r.row:SetBrushColor(bg)
            end
        end
        local hidden = #list - #self.rows
        if model.shotsError then
            self.more:SetText(FText("Shots file problem: " .. model.shotsError))
            self.more:SetColorAndOpacity(slate(C.warn))
        else
            self.more:SetText(FText(hidden > 0 and ("+" .. hidden .. " more (mjolnir_camera shots)") or ""))
            self.more:SetColorAndOpacity(slate(C.faint))
        end
        self.hints:SetText(FText("1-0 go     PgUp/PgDn fly     Ctrl+1-0 save     Ctrl+Z undo" .. (model.canRedo and "     Ctrl+Y redo" or "")
            .. "     Z/X zoom     R reset     F6 pin"))
        if not self.cardShown then self.card:SetVisibility(HIT_TEST_INVISIBLE) end
    end)
    if not ok then
        print("[MJOLNIR FlyCam] panel update failed: " .. tostring(err) .. "\n")
        return false
    end
    self.cardShown = true
    return true
end

--- kind: "good" (saved, redo), "warn" (overwrote, deleted, undo), "info".
function Panel:showToast(pc, message, hint, kind, seconds)
    if not self:ensure(pc) then return false end
    local ok = pcall(function()
        self.toastText:SetText(FText(message))
        self.toastHint:SetText(FText(hint or ""))
        self.toastDot:SetBrushColor(kind == "warn" and C.warn or (kind == "info" and C.accent or C.good))
        if not self.toastShown then self.toast:SetVisibility(HIT_TEST_INVISIBLE) end
    end)
    if ok then self.toastShown, self.toastLeft = true, seconds or 3.0 end
    return ok
end

function Panel:tick(dt)
    if self.toastShown then
        self.toastLeft = self.toastLeft - dt
        if self.toastLeft <= 0 then self:hideToast() end
    end
end

return Panel

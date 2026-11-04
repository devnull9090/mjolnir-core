-- MJOLNIR HUD: where King of the Hill's hill is.
--
-- No Megalo waypoint or boundary reaches Unreal (docs/game_modes.md, B4 and
-- B5), so a match shows nothing where the hill stands. The level file lists
-- the hills in rotation order (`koth_hills`: x, y, z and radius, Unreal cm,
-- tools/level/ce_objectives.py), the variant says which one is live
-- (`hill_moved`, value = its place in the rotation), and this draws one line
-- under the score: how far, and which way.

local Hill = {}

local COLLAPSED = 1 -- ESlateVisibility
local VISIBLE_NO_HIT_TEST = 4
local EVERY = 0.2 -- seconds between updates
local CM_PER_METRE = 100
local LEVEL_DIFFERENCE_CM = 300

--- The hills in a level file's text, in rotation order.
function Hill.parse(text)
    local list = type(text) == "string" and text:match('"koth_hills"%s*:%s*(%b[])') or nil
    local hills = {}
    if not list then return hills end
    local n = "([-%d.eE+]+)"
    local c = "%s*,%s*"
    for x, y, z, r in list:gmatch("%[%s*" .. n .. c .. n .. c .. n .. c .. n .. "%s*%]") do
        hills[#hills + 1] = { x = tonumber(x), y = tonumber(y), z = tonumber(z), r = tonumber(r) }
    end
    return hills
end

--- The line for a player at `at` looking along `yaw` (degrees): the hill's
--- distance and bearing, in the words a player would use.
function Hill.describe(hill, at, yaw)
    local dx, dy, dz = hill.x - at.X, hill.y - at.Y, hill.z - at.Z
    local flat = math.sqrt(dx * dx + dy * dy)
    local level = ""
    if dz > LEVEL_DIFFERENCE_CM then
        level = " ABOVE"
    elseif dz < -LEVEL_DIFFERENCE_CM then
        level = " BELOW"
    end
    if flat <= hill.r then
        if level == "" then return "ON THE HILL" end
        return "HILL" .. level
    end
    local turn = (math.deg(math.atan(dy, dx)) - yaw + 540) % 360 - 180
    local way
    if math.abs(turn) <= 35 then
        way = "AHEAD"
    elseif math.abs(turn) >= 145 then
        way = "BEHIND"
    elseif turn < 0 then
        way = "LEFT"
    else
        way = "RIGHT"
    end
    return string.format("HILL %d M %s%s", math.floor((flat - hill.r) / CM_PER_METRE + 0.5), way, level)
end

local function build(pc)
    local library = StaticFindObject("/Script/UMG.Default__WidgetBlueprintLibrary")
    local w = library:Create(pc, StaticFindObject("/Script/UMG.UserWidget"), pc)
    local tree = w.WidgetTree
    local t = StaticConstructObject(StaticFindObject("/Script/UMG.TextBlock"), tree, FName("MJOLNIRHillText"))
    tree.RootWidget = t
    t:SetColorAndOpacity({ SpecifiedColor = { R = 1, G = 1, B = 1, A = 1 }, ColorUseRule = 0 })
    t:SetShadowOffset({ X = 1.5, Y = 1.5 })
    t:SetShadowColorAndOpacity({ R = 0, G = 0, B = 0, A = 0.9 })
    w:AddToViewport(41)
    w:SetAnchorsInViewport({ Minimum = { X = 0.5, Y = 0.135 }, Maximum = { X = 0.5, Y = 0.135 } })
    w:SetAlignmentInViewport({ X = 0.5, Y = 0 })
    return w, t
end

--- One match's marker. `read` gives a map's level file text.
function Hill.new(read)
    local self = { hills = {}, live = 1, next = 0 }

    function self.start(code)
        self.hills = Hill.parse(read(code))
        self.live, self.next = 1, 0
        return #self.hills
    end

    function self.moved(place)
        if type(place) == "number" and self.hills[place + 1] then self.live = place + 1 end
    end

    --- Hide, never remove: RemoveFromParent hung the game once.
    function self.hide()
        if self.widget and self.widget:IsValid() then
            pcall(function() self.widget:SetVisibility(COLLAPSED) end)
        end
    end

    function self.tick(now, pc, hidden)
        if #self.hills == 0 or now < self.next then return end
        self.next = now + EVERY
        if hidden then return self.hide() end
        pcall(function()
            if not (self.widget and self.widget:IsValid() and self.text and self.text:IsValid()) then
                self.widget, self.text = build(pc)
            end
            local pawn = pc.Pawn
            if not (pawn and pawn:IsValid()) then return self.hide() end
            local line = Hill.describe(self.hills[self.live], pawn:K2_GetActorLocation(),
                pc:GetControlRotation().Yaw)
            if line ~= self.line then
                self.line = line
                self.text:SetText(FText(line))
            end
            self.widget:SetVisibility(VISIBLE_NO_HIT_TEST)
        end)
    end

    return self
end

return Hill

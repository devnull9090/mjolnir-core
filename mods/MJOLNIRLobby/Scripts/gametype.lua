-- A game type choice is a draft until SELECT. CommonUI's Back/Escape can
-- deactivate the screen at any time without changing the hosted game.
--
-- The list on the left is game type families (modes.lua), each naming its
-- variants, and the family that is chosen shows them as buttons on the right,
-- so no choice hides behind a repeat click.
--
-- The UI container ships apart from this mod. One from before Variant0 has six
-- tiles and no other button: there each tile is an engine, a click on the chosen
-- tile steps through its variants, and its format line names the one it stands for.
local M = {}
local CLASS = "/Game/MJOLNIR/UI/WBP_MJOLNIRGameTypeSelect.WBP_MJOLNIRGameTypeSelect_C"
local ICON_ROOT = "/Game/MJOLNIR/UI/ModeIcons/T_MJMode_"
local ICONS = { slayer = "Slayer", team_slayer = "TeamSlayer", ctf = "Ctf",
    oddball = "Oddball", team_oddball = "Oddball", juggernaut = "Juggernaut",
    stalker = "Juggernaut", reverse_tag = "Juggernaut",
    koth = "Koth", crazy_king = "Koth", team_koth = "Koth",
    race = "Race", team_race = "Race", rally = "Race", team_rally = "Race", forge = "Forge" }
-- What an older UI container, without these two textures, draws instead.
local ICON_STAND_INS = { Juggernaut = "Slayer", Race = "Ctf" }
local OLD_TILES, FAMILY_TILES, VARIANT_BUTTONS = 6, 7, 5
local NORMAL = { R = 1, G = 1, B = 1, A = 1 }
local CHOSEN = { R = 2.0, G = 2.8, B = 3.0, A = 1 }
local WHITE = { R = 0.88, G = 0.95, B = 1, A = 1 }
local CYAN = { R = 0.46, G = 0.79, B = 0.94, A = 1 }
local GREY = { R = 0.46, G = 0.61, B = 0.70, A = 1 }
local GOLD = { R = 1, G = 0.80, B = 0.35, A = 1 }
local function text(w, value)
    pcall(function() w:SetText(FText(value or "")) end)
end
local function format(mode)
    if not mode then return "" end
    return mode.forge and "SANDBOX" or (mode.teams and "RED TEAM  /  BLUE TEAM" or "FREE FOR ALL")
end
local function names(tile)
    local list = {}
    for i, mode in ipairs(tile.variants) do list[i] = mode.name end
    return table.concat(list, "  /  ")
end

function M.new(deps)
    local Modes = deps.modes
    local self = { class = CLASS }
    local screen, mapCode, selected, hovered, modes, tiles, currentId, split
    local available, textures = nil, {}

    function self.available()
        if available == nil then available = deps.loadClass(CLASS) ~= nil end
        return available
    end

    function self.active()
        return deps.alive(screen)
    end

    local function texture(name)
        if name and (textures[name] == nil or (textures[name] and not deps.valid(textures[name]))) then
            local ok, tex = pcall(function()
                local ksl = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
                local path = ICON_ROOT .. name .. ".T_MJMode_" .. name
                return ksl:LoadAsset_Blocking(ksl:Conv_SoftObjPathToSoftObjRef(ksl:MakeSoftObjectPath(path)))
            end)
            textures[name] = ok and deps.valid(tex) and tex or false
        end
        return name and textures[name]
    end

    local function icon(image, mode)
        if not deps.valid(image) then return false end
        local name = mode and ICONS[mode.id]
        local tex = texture(name) or texture(ICON_STAND_INS[name])
        pcall(function()
            image:SetVisibility(tex and 3 or 2)
            if tex then image:SetBrushFromTexture(tex, false) end
        end)
        return tex ~= nil and tex ~= false
    end

    -- The lobby uses the same icon mapping and texture cache as the picker.
    self.showIcon = icon

    local function preview(mode)
        text(screen.ModeTitle, mode and mode.name or "NO GAME TYPES AVAILABLE")
        text(screen.ModeDescription, mode and mode.description or "No installed game type supports this map.")
        text(screen.MatchFormat, format(mode))
        icon(screen.ModeIcon, mode)
    end

    --- The tile's line under its name: its variants, or on an older container
    --- the one it stands for.
    local function tileLine(tile, mode)
        if #tile.variants < 2 then return format(mode) end
        if split then return names(tile) end
        return string.format("%s  /  VARIANT %d OF %d", mode.name, Modes.position(tile, mode.id), #tile.variants)
    end

    --- The tile `selected` belongs to, or nil.
    local function chosenTile()
        return selected and Modes.tileOf(tiles, selected.id) or nil
    end

    --- `tile`'s variants as `target`'s buttons, with `chosen` lit and the
    --- `hostedId` marked. A family of one, or none, has nothing to
    --- choose: the block is hidden, not collapsed, so what is below stays put.
    --- Map select's buttons have a gold bar and no second line, this screen's
    --- the other way round.
    local function drawVariants(target, tile, chosen, hostedId)
        local several = tile ~= nil and #tile.variants > 1
        pcall(function() target.VariantBlock:SetVisibility(several and 0 or 2) end)
        for i = 0, VARIANT_BUTTONS - 1 do
            local mode = several and tile.variants[i + 1] or nil
            local key = "Variant" .. i
            pcall(function() target[key]:SetVisibility(mode and 0 or 1) end)
            if mode then
                local lit = chosen ~= nil and chosen.id == mode.id
                local current = hostedId == mode.id
                local line = mode.teams and "TEAMS" or "FREE FOR ALL"
                pcall(function()
                    target[key .. "Label"]:SetText(FText(mode.name))
                    target[key]:SetBackgroundColor(lit and CHOSEN or NORMAL)
                    target[key .. "Label"]:SetColorAndOpacity({ SpecifiedColor = lit and CYAN or WHITE, ColorUseRule = 0 })
                end)
                pcall(function() target[key .. "Mark"]:SetVisibility(lit and 3 or 2) end)
                pcall(function()
                    target[key .. "Line"]:SetText(FText(current and line .. "  /  CURRENT" or line))
                    target[key .. "Line"]:SetColorAndOpacity({ SpecifiedColor = current and GOLD or GREY, ColorUseRule = 0 })
                end)
            end
        end
    end

    -- Map select draws the same buttons.
    self.showVariants = drawVariants

    local function draw()
        for i = 0, (split and FAMILY_TILES or OLD_TILES) - 1 do
            local tile, button = tiles[i + 1], screen["Mode" .. i]
            pcall(function() button:SetVisibility(tile and 0 or 1) end)
            if tile then
                local mode = Modes.shown(tile, selected)
                local chosen = selected and selected.id == mode.id
                text(screen["Mode" .. i .. "Label"], tile.name)
                text(screen["Mode" .. i .. "Format"], tileLine(tile, mode))
                text(screen["Mode" .. i .. "Current"], Modes.position(tile, currentId) and "CURRENT" or "")
                icon(screen["Mode" .. i .. "Icon"], mode)
                pcall(function()
                    button:SetBackgroundColor(chosen and CHOSEN or NORMAL)
                    screen["Mode" .. i .. "Label"]:SetColorAndOpacity({ SpecifiedColor = chosen and CYAN or WHITE, ColorUseRule = 0 })
                end)
            end
        end
        local count = split and #modes or #tiles
        text(screen.ListCount, string.format("%d GAME TYPE%s %s", count, count == 1 and "" or "S",
            split and "ON THIS MAP" or "AVAILABLE"))
        pcall(function() screen.Select:SetIsEnabled(selected ~= nil and deps.isHost()) end)
        text(screen.SelectLabel, selected and "SELECT " .. selected.name or "SELECT")
        text(screen.Status, (split and "Pick a game type on the left and a variant on the right, then SELECT. "
            or "Choose a game type, click it again for its variants, then SELECT. ")
            .. "BACK keeps your current game type.")
        if split then drawVariants(screen, chosenTile(), selected, currentId) end
        preview(hovered or selected)
    end

    local function close()
        pcall(function() screen:DeactivateWidget() end)
        screen, selected, hovered = nil, nil, nil
        deps.focusLobby()
    end

    function self.open()
        local map, mode = deps.current()
        if not (map and deps.isHost()) then return false end
        if self.active() then return true end
        if not self.available() then deps.fallback(); return false end
        screen = deps.pushScreen(CLASS)
        if not deps.valid(screen) then
            deps.note("Could not open the game type screen.")
            return false
        end
        mapCode, currentId, hovered = map.code, mode and mode.id, nil
        modes, selected = deps.modesFor(map), nil
        local okSplit, hasVariants = pcall(function() return deps.valid(screen.Variant0) end)
        split = okSplit and hasVariants == true
        tiles = split and Modes.families(modes) or Modes.engines(modes)
        for _, candidate in ipairs(modes) do
            if candidate.id == currentId then selected = candidate end
        end
        selected = selected or (tiles[1] and tiles[1].variants[1])
        local focus = 0
        for i, tile in ipairs(tiles) do
            if selected and Modes.position(tile, selected.id) then focus = i - 1 end
        end
        text(screen.MapTitle, deps.titleOf(map))
        deps.showCover(screen, map.code)
        draw()
        pcall(function() (selected and screen["Mode" .. focus] or screen.Back):SetFocus() end)
        return true
    end

    function self.onEvent(event, source)
        if not self.active() then return end
        if source and not deps.sameWidget(source, screen) then return end
        if event == "back" then close(); return end
        local map = deps.current()
        if not deps.isHost() or not map or map.code ~= mapCode then
            close()
            deps.note("The lobby changed. Open GAME TYPE again to choose a mode.")
            return
        end
        local verb, index = event:match("^(%a+):(%d+)$")
        local tile = index and tiles[tonumber(index) + 1]
        local mode = tile and Modes.shown(tile, selected)
        -- A variant button's index is into the chosen family, not the list.
        local family = split and chosenTile() or nil
        local variant = index and family and #family.variants > 1 and family.variants[tonumber(index) + 1] or nil
        if verb == "mode" and tile then
            selected, hovered = (split and Modes.open or Modes.step)(tile, selected), nil
            draw()
        elseif verb == "variant" and variant then
            selected, hovered = Modes.pick(family, variant), nil
            draw()
        elseif (verb == "hover" and mode) or (verb == "vhover" and variant) then
            hovered = verb == "hover" and mode or variant
            preview(hovered)
        elseif verb == "unhover" or verb == "vunhover" then
            if hovered == (verb == "unhover" and mode or variant) then hovered = nil end
            preview(hovered or selected)
        elseif event == "select" and selected then
            -- Availability can change while the picker is open. Resolve by
            -- id against the current map, never trust a stale row index.
            local chosen
            for _, candidate in ipairs(deps.modesFor(map)) do
                if candidate.id == selected.id then chosen = candidate; break end
            end
            if not chosen then
                text(screen.Status, "That game type is no longer available. Go BACK and choose again.")
                pcall(function() screen.Select:SetIsEnabled(false) end)
                return
            end
            deps.commit(chosen)
            close()
        end
    end

    return self
end

return M

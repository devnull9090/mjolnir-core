-- A game type choice is a draft until SELECT. CommonUI's Back/Escape can
-- deactivate the screen at any time without changing the hosted game.
--
-- Each tile is an engine (modes.lua). The cooked screen has six tiles and no
-- other button, so a click on the chosen tile steps through its variants, and
-- the tile's format line names the one it stands for.
local M = {}
local CLASS = "/Game/MJOLNIR/UI/WBP_MJOLNIRGameTypeSelect.WBP_MJOLNIRGameTypeSelect_C"
local ICON_ROOT = "/Game/MJOLNIR/UI/ModeIcons/T_MJMode_"
-- Only these six textures are cooked. Race borrows the flag until it has its own.
local ICONS = { slayer = "Slayer", team_slayer = "TeamSlayer", ctf = "Ctf",
    oddball = "Oddball", team_oddball = "Oddball", juggernaut = "Slayer",
    koth = "Koth", crazy_king = "Koth", team_koth = "Koth",
    race = "Ctf", team_race = "Ctf", rally = "Ctf", team_rally = "Ctf", forge = "Forge" }
local NORMAL = { R = 1, G = 1, B = 1, A = 1 }
local CHOSEN = { R = 2.0, G = 2.8, B = 3.0, A = 1 }
local WHITE = { R = 0.88, G = 0.95, B = 1, A = 1 }
local CYAN = { R = 0.46, G = 0.79, B = 0.94, A = 1 }
local function text(w, value)
    pcall(function() w:SetText(FText(value or "")) end)
end
local function format(mode)
    if not mode then return "" end
    return mode.forge and "SANDBOX  /  SOLO HOST" or (mode.teams and "RED TEAM  /  BLUE TEAM" or "FREE FOR ALL")
end

function M.new(deps)
    local Modes = deps.modes
    local self = { class = CLASS }
    local screen, mapCode, selected, hovered, modes, tiles, currentId
    local available, textures = nil, {}

    function self.available()
        if available == nil then available = deps.loadClass(CLASS) ~= nil end
        return available
    end

    function self.active()
        return deps.alive(screen)
    end

    local function icon(image, mode)
        if not deps.valid(image) then return false end
        local name = mode and ICONS[mode.id]
        if name and (textures[name] == nil or (textures[name] and not deps.valid(textures[name]))) then
            local ok, tex = pcall(function()
                local ksl = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
                local path = ICON_ROOT .. name .. ".T_MJMode_" .. name
                return ksl:LoadAsset_Blocking(ksl:Conv_SoftObjPathToSoftObjRef(ksl:MakeSoftObjectPath(path)))
            end)
            textures[name] = ok and deps.valid(tex) and tex or false
        end
        local tex = name and textures[name]
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

    --- The tile's line under its name: the variant it stands for, when it has
    --- more than one.
    local function tileLine(tile, mode)
        if #tile.variants < 2 then return format(mode) end
        return string.format("%s  /  VARIANT %d OF %d", mode.name, Modes.position(tile, mode.id), #tile.variants)
    end

    local function draw()
        for i = 0, 5 do
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
        text(screen.ListCount, string.format("%d GAME TYPE%s AVAILABLE", #tiles, #tiles == 1 and "" or "S"))
        pcall(function() screen.Select:SetIsEnabled(selected ~= nil and deps.isHost()) end)
        text(screen.Status, "Choose a game type, click it again for its variants, then SELECT. "
            .. "BACK keeps your current game type.")
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
        tiles = Modes.engines(modes)
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
        if verb == "mode" and tile then
            selected, hovered = Modes.step(tile, selected), nil
            draw()
        elseif verb == "hover" and mode then
            hovered = mode
            preview(mode)
        elseif verb == "unhover" then
            if hovered == mode then hovered = nil end
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

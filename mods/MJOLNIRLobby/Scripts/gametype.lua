-- A game type choice is a draft until SELECT. CommonUI's Back/Escape can
-- deactivate the screen at any time without changing the hosted game.
local M = {}
local CLASS = "/Game/MJOLNIR/UI/WBP_MJOLNIRGameTypeSelect.WBP_MJOLNIRGameTypeSelect_C"
local ICON_ROOT = "/Game/MJOLNIR/UI/ModeIcons/T_MJMode_"
local ICONS = { slayer = "Slayer", team_slayer = "TeamSlayer", ctf = "Ctf",
    oddball = "Oddball", koth = "Koth", forge = "Forge" }
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
    local self = { class = CLASS }
    local screen, mapCode, selected, hovered, modes, currentId
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

    local function draw()
        for i = 0, 5 do
            local mode, button = modes[i + 1], screen["Mode" .. i]
            pcall(function() button:SetVisibility(mode and 0 or 1) end)
            if mode then
                local chosen = selected and selected.id == mode.id
                text(screen["Mode" .. i .. "Label"], mode.name)
                text(screen["Mode" .. i .. "Format"], format(mode))
                text(screen["Mode" .. i .. "Current"], currentId == mode.id and "CURRENT" or "")
                icon(screen["Mode" .. i .. "Icon"], mode)
                pcall(function()
                    button:SetBackgroundColor(chosen and CHOSEN or NORMAL)
                    screen["Mode" .. i .. "Label"]:SetColorAndOpacity({ SpecifiedColor = chosen and CYAN or WHITE, ColorUseRule = 0 })
                end)
            end
        end
        text(screen.ListCount, string.format("%d GAME TYPE%s AVAILABLE", #modes, #modes == 1 and "" or "S"))
        pcall(function() screen.Select:SetIsEnabled(selected ~= nil and deps.isHost()) end)
        text(screen.Status, "Choose a game type, then SELECT to apply it. BACK keeps your current game type.")
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
        local focus = 0
        for i, candidate in ipairs(modes) do
            if candidate.id == currentId then selected, focus = candidate, i - 1 end
        end
        selected = selected or modes[1]
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
        local mode = index and modes[tonumber(index) + 1]
        if verb == "mode" and mode then
            selected, hovered = mode, nil
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

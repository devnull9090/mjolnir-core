-- MJOLNIR Lobby: the game's fireteam panel past four players.
--
-- The panel at the top right of the main menu (WBP_SquadWidget) lists
-- MeteoriteSquadLobbyViewModel.SquadMembers, which always holds exactly four
-- slots: the players first, then blank INVITE + rows. A fifth player is in
-- the game but never gets a row, and the header reads "n/4". The panel's
-- blueprint rebuilds its list on BackingDataChanged and writes the header in
-- UpdateHeader. After either, and on the lobby's poll, this gives every
-- player in the game state a row, keeps one INVITE + row while there is room
-- and writes the real limit in the header.
--
-- A player the view model left out gets a MeteoritePlayerViewModel of our
-- own: name, platform and player state are all the row widget reads, and its
-- player menu acts on that player state (docs/fireteam_join_and_cap.md).

local SquadPanel = {}

local WIDGET = "/Game/UI/Shared/Widgets/Squad/WBP_SquadWidget.WBP_SquadWidget_C"
local PLAYER_VIEW_MODEL = "/Script/Meteorite.MeteoritePlayerViewModel"
local ITEM = "/Script/Meteorite.MeteoriteSquadLobbyViewItemData"
local ROW_PLAYER, ROW_BLANK = 0, 2

local ours = {}       -- list item address -> true, for the rows added here
local hooked = false

local function valid(o)
    local ok, v = pcall(function() return o and o:IsValid() end)
    return ok and v
end

local function addressOf(o)
    local ok, a = pcall(function() return o:GetAddress() end)
    return ok and a or nil
end

local function nameOf(ps)
    local ok, n = pcall(function() return ps:GetPlayerName():ToString() end)
    return ok and n or nil
end

--- The panel on screen. FindFirstOf returns the class default, whose
--- sub-widgets are null; the live one is outered to the transient package.
local function liveWidget()
    for _, w in ipairs(FindAllOf("WBP_SquadWidget_C") or {}) do
        if valid(w) and w:GetFullName():find("/Engine/Transient", 1, true) then return w end
    end
    return nil
end

local function players(widget)
    local out = {}
    pcall(function()
        widget:GetWorld().GameState.PlayerArray:ForEach(function(_, e)
            local ps = e:get()
            if valid(ps) then out[#out + 1] = ps end
        end)
    end)
    return out
end

-- A row's widget class travels with its item, in a native field the view
-- model fills in; the list's EntryWidgetClass is only the fallback for an
-- item without one, read whenever the list gets round to building the row.
-- So a player row is constructed from one of the view model's own player
-- items as its template, which carries the class, and the fallback is held
-- at the blank class for the INVITE + rows built here.

local function addPlayerRow(list, vm, ps, template, platform)
    local pvm = StaticConstructObject(StaticFindObject(PLAYER_VIEW_MODEL), vm)
    pvm.DisplayName = nameOf(ps) or "?"
    pvm.PlayerState = ps
    pvm.bIsLeader = false
    if platform then pvm.PlatformType = platform end
    local item = StaticConstructObject(StaticFindObject(ITEM), list, FName("None"), 0, 0, false, false, template)
    item.FireteamRowType = ROW_PLAYER
    item.PlayerViewModel = pvm
    item.MuteDelegateBoundPlayerViewModel = pvm
    list:AddItem(item)
    ours[addressOf(item)] = true
end

local function addBlankRow(list, vm)
    local item = StaticConstructObject(StaticFindObject(ITEM), list)
    item.FireteamRowType = ROW_BLANK
    list.EntryWidgetClass = vm.BlankWidgetClass
    list:AddItem(item)
    ours[addressOf(item)] = true
end

--- Bring the panel up to date with the game state, for a fireteam of `size`.
function SquadPanel.refresh(size)
    local widget = liveWidget()
    local vm = FindFirstOf("MeteoriteSquadLobbyViewModel")
    if not (widget and valid(vm)) then return end
    local list = widget.SquadListView
    if not valid(list) then return end
    local everyone = players(widget)
    if #everyone == 0 then return end
    local present = {}
    for _, ps in ipairs(everyone) do present[addressOf(ps)] = true end

    -- The rows as they stand. Player rows count by player state and by name
    -- (the view model's player state can be a previous world's). The view
    -- model's rows come first; ours go when their player has left or the
    -- view model shows that player itself.
    local rows = {}
    for i = 0, list:GetNumItems() - 1 do
        local item = list:GetItemAt(i)
        if valid(item) then
            local row = { item = item, mine = ours[addressOf(item)], kind = item.FireteamRowType }
            if row.kind == ROW_PLAYER then
                local pvm = item.PlayerViewModel
                local ps = valid(pvm) and pvm.PlayerState
                row.key = valid(ps) and addressOf(ps) or nil
                pcall(function() row.name = pvm.DisplayName:ToString() end)
                pcall(function() row.platform = pvm.PlatformType end)
            end
            rows[#rows + 1] = row
        end
    end
    local shown, shownName, blanks, stale, ourBlanks, template, platform = {}, {}, 0, {}, {}, nil, nil
    for _, row in ipairs(rows) do
        if row.kind == ROW_PLAYER and not row.mine then
            if row.key then shown[row.key] = true end
            if row.name then shownName[row.name] = true end
            template, platform = template or row.item, platform or row.platform
        end
    end
    for _, row in ipairs(rows) do
        if row.kind == ROW_PLAYER and row.mine then
            if row.key and present[row.key] and not shown[row.key] and not shownName[row.name or ""] then
                shown[row.key] = true
                if row.name then shownName[row.name] = true end
            else
                stale[#stale + 1] = row.item
            end
        elseif row.kind == ROW_BLANK then
            blanks = blanks + 1
            if row.mine then ourBlanks[#ourBlanks + 1] = row.item end
        end
    end

    local missing = {}
    for _, ps in ipairs(everyone) do
        if not shown[addressOf(ps)] and not shownName[nameOf(ps) or ""] then missing[#missing + 1] = ps end
    end
    if not template then missing = {} end
    for _, item in ipairs(stale) do
        list:RemoveItem(item)
        ours[addressOf(item)] = nil
    end
    -- INVITE + stays last: ours comes out before new player rows go in, and
    -- whenever the fireteam is full.
    if #missing > 0 or #everyone >= size then
        for _, item in ipairs(ourBlanks) do
            list:RemoveItem(item)
            ours[addressOf(item)] = nil
            blanks = blanks - 1
        end
    end
    for _, ps in ipairs(missing) do addPlayerRow(list, vm, ps, template, platform) end
    if blanks == 0 and #everyone < size then addBlankRow(list, vm) end

    local text = string.format("Fireteam %d/%d", #everyone, size)
    pcall(function()
        if widget.FireteamHeader:GetText():ToString() ~= text then widget.FireteamHeader:SetText(FText(text)) end
    end)
end

--- Refresh after the panel's own rebuild and header update. The blueprint
--- class loads with the main menu, and RegisterHook on a blueprint class that
--- is not loaded fails silently, so this waits for it.
function SquadPanel.hook(size)
    if hooked or not valid(StaticFindObject(WIDGET)) then return end
    hooked = true
    local function later()
        ExecuteInGameThreadWithDelay(50, function() pcall(SquadPanel.refresh, size) end)
    end
    for _, fn in ipairs({ "BackingDataChanged", "UpdateHeader" }) do
        pcall(function() RegisterHook(WIDGET .. ":" .. fn, later) end)
    end
end

return SquadPanel

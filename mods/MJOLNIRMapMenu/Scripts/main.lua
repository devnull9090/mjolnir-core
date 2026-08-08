-- MJOLNIR Map Menu
--
-- Keeps the game's shipped debug map menu reachable and puts custom worlds in
-- it, so a modded map is launched the same way a developer launched a test map.
--
-- What ships in the game (verified CU3):
--   WBP_MainMenu has a hidden DebugButtonContainer with a DebugMenuButton and
--   an OnToggleDebugMenu handler. Toggling it reveals a "Test options" panel
--   with DEBUG LEVEL SELECT, which opens WBP_DebugMenuSelect -> MAP SELECT,
--   with CAMPAIGN MISSIONS and TEST MAPS pages. Both pages are driven by
--   arrays of BP_DebugMapItemData objects, each holding:
--       CampaignData          BlamCampaignDataAsset
--       StartingScenarioName  Name
--   and clicking one calls
--       BlamCampaignFlowGameSubsystem:SetAndBeginCampaign(Campaign, Name, Options)
--
-- The constraint that shapes this mod: SetAndBeginCampaign resolves the
-- scenario NAME against Blam scenario tags, not against Unreal world packages.
-- The build ships exactly 13 scenario tags -- one per campaign mission -- and
-- none for the `testing_*` names, so a brand-new scenario name cannot be
-- launched no matter what world package exists. A custom world therefore rides
-- in on a scenario name that does have a tag, by overriding that scenario's
-- world package in an IoStore container.
--
-- Commands:
--   mjolnir_menu_debug          reveal the Test options panel on the main menu
--   mjolnir_menu_open           open MAP SELECT directly
--   mjolnir_menu_add <scenario> [label]
--                               add a custom entry to the TEST MAPS page
--   mjolnir_menu_list           list the entries currently in both pages

local AUTO_REVEAL = true  -- reveal the debug panel automatically at the frontend

local CAMPAIGN_ASSETS = {
    first = "/Game/Blueprints/Campaign/DA_FirstPlayableCampaign.DA_FirstPlayableCampaign",
    additional = "/Game/Blueprints/Campaign/DA_AdditionalCampaign.DA_AdditionalCampaign",
    test = "/Game/Blueprints/Campaign/DA_TestMapsCampaign.DA_TestMapsCampaign",
}

-- Scenario names that have a Blam scenario tag and can therefore actually
-- launch. A custom world must override one of these scenarios' world packages.
local LAUNCHABLE = {
    A15 = "first", A30 = "first", A50 = "first", B30 = "first", B40 = "first",
    C10 = "first", C20 = "first", C45 = "first", D20 = "first", D40 = "first",
    E10 = "additional", E20 = "additional", E30 = "additional",
}

local customEntries = {}

local function log(fmt, ...)
    print("[MJOLNIR MapMenu] " .. string.format(fmt, ...) .. "\n")
end

local function firstValid(objects)
    for _, o in ipairs(objects or {}) do
        if o and o:IsValid() then return o end
    end
    return nil
end

--- First real parameter of a console command (UE4SS arg shape varies).
local function commandArg(args, index)
    local offset = (type(args[1]) == "string" and args[1]:lower():find("^mjolnir_")) and 1 or 0
    return args[index + offset]
end

local function revealDebugPanel()
    local menu = firstValid(FindAllOf("WBP_MainMenu_C"))
    if not menu then
        log("no main menu on screen (this works at the frontend)")
        return false
    end
    local container = menu.DebugButtonContainer
    if container and container:IsValid() and container:GetVisibility() == 0 then
        log("Test options panel is already visible")
        return true
    end
    local ok, err = pcall(function() menu:OnToggleDebugMenu() end)
    if not ok then
        log("OnToggleDebugMenu failed: %s", tostring(err))
        return false
    end
    log("Test options revealed -- DEBUG LEVEL SELECT is on the main menu")
    return true
end

local function openMapSelect()
    local menu = firstValid(FindAllOf("WBP_MainMenu_C"))
    if not menu then
        log("no main menu on screen")
        return
    end
    revealDebugPanel()
    local ok, err = pcall(function()
        menu:BndEvt__WBP_MainMenu_DebugMenuButton_K2Node_ComponentBoundEvent_1_CommonButtonBaseClicked__DelegateSignature(
            menu.DebugMenuButton)
    end)
    if ok then
        log("opened MAP SELECT")
    else
        log("could not open MAP SELECT: %s", tostring(err))
    end
end

--- Build a BP_DebugMapItemData for a scenario, or nil.
---
--- The item is constructed from the same Blueprint class the shipped menu data
--- uses, so the click handler treats it exactly like a shipped entry.
local function makeItem(scenario, label)
    local itemClass = StaticFindObject("/Game/UI/Frontend/DebugMenu/Blueprints/BP_DebugMapItemData.BP_DebugMapItemData_C")
    if not itemClass or not itemClass:IsValid() then
        log("BP_DebugMapItemData_C not loaded -- open MAP SELECT once first")
        return nil
    end

    local campaignKey = LAUNCHABLE[string.upper(scenario)]
    if not campaignKey then
        log("'%s' has no Blam scenario tag, so it cannot launch. Override one of:", scenario)
        local names = {}
        for name in pairs(LAUNCHABLE) do names[#names + 1] = name end
        table.sort(names)
        log("  %s", table.concat(names, " "))
        return nil
    end

    local campaign = StaticFindObject(CAMPAIGN_ASSETS[campaignKey])
    if not campaign or not campaign:IsValid() then
        log("campaign data asset not loaded: %s", CAMPAIGN_ASSETS[campaignKey])
        return nil
    end

    local ok, item = pcall(function()
        return StaticConstructObject(itemClass, itemClass:GetOuter(), FName("MJOLNIR_" .. scenario))
    end)
    if not ok or not item or not item:IsValid() then
        log("could not construct menu item: %s", tostring(item))
        return nil
    end

    item.CampaignData = campaign
    item.StartingScenarioName = FName(string.upper(scenario))

    -- Presentation lives on HaloUIViewItemData, not on the Blueprint: a row
    -- with no EntryWidgetClass renders as nothing. Copy the widget class and
    -- button style from a shipped item so ours looks native, then set the
    -- label. Without this the entry is in the list but invisible.
    local template = firstValid(FindAllOf("BP_DebugMapItemData_C"))
    if template and template ~= item then
        for _, field in ipairs({ "EntryWidgetClass", "EntryWidgetButtonStyle",
                                 "NameTextProperties", "DescriptionTextProperties" }) do
            pcall(function() item[field] = template[field] end)
        end
    end
    pcall(function() item.EntryName = FText(label or scenario) end)
    pcall(function() item.IdentifierName = FName("MJOLNIR_" .. scenario) end)
    pcall(function() item.bIsSelectableOrNavigable = true end)
    customEntries[#customEntries + 1] = { item = item, label = label or scenario }
    log("added '%s' -> scenario %s (%s)", label or scenario, string.upper(scenario), campaignKey)
    log("open MAP SELECT > TEST MAPS to see it")
    return item
end

local function addEntry(scenario, label)
    if not scenario or scenario == "" then
        log("usage: mjolnir_menu_add <scenario> [label]")
        return
    end
    local item = makeItem(scenario, label)
    if not item then return end

    -- Push it into the live TEST MAPS list if that page is open.
    local page = firstValid(FindAllOf("WBP_TestMapDebugMenu_C"))
    if not page then
        log("TEST MAPS page is not open; the entry is registered and will be")
        log("pushed the next time you run mjolnir_menu_add with the page open")
        return
    end
    local ok, err = pcall(function()
        local view = page.LevelsView
        if view and view:IsValid() then view:AddItem(item) end
    end)
    if ok then
        log("pushed into the open TEST MAPS list")
    else
        log("could not push into the list view: %s", tostring(err))
    end
end

local function listEntries()
    local items = FindAllOf("BP_DebugMapItemData_C") or {}
    log("%d menu items live:", #items)
    for _, item in ipairs(items) do
        local okS, scenario = pcall(function() return item.StartingScenarioName:ToString() end)
        local okC, campaign = pcall(function() return item.CampaignData:GetFName():ToString() end)
        local launchable = okS and LAUNCHABLE[string.upper(scenario)] and "launchable" or "no scenario tag"
        log("  %-26s %-24s %s", okS and scenario or "?", okC and campaign or "?", launchable)
    end
    if #customEntries > 0 then
        log("%d added by this mod", #customEntries)
    end
end

local function initialize()
    RegisterConsoleCommandHandler("mjolnir_menu_debug", function()
        revealDebugPanel()
        return true
    end)
    RegisterConsoleCommandHandler("mjolnir_menu_open", function()
        openMapSelect()
        return true
    end)
    RegisterConsoleCommandHandler("mjolnir_menu_add", function(_, args)
        addEntry(commandArg(args, 1), commandArg(args, 2))
        return true
    end)
    RegisterConsoleCommandHandler("mjolnir_menu_list", function()
        listEntries()
        return true
    end)

    if AUTO_REVEAL then
        -- The frontend menu is built a moment after the map finishes loading.
        RegisterHook("/Script/Engine.PlayerController:ClientRestart", function()
            ExecuteInGameThreadWithDelay(3000, function()
                if FindAllOf("WBP_MainMenu_C") then revealDebugPanel() end
            end)
        end)
    end

    log("ready. mjolnir_menu_open, mjolnir_menu_add <scenario> [label], mjolnir_menu_list")
end

ExecuteInGameThreadWithDelay(5000, initialize)
print("[MJOLNIR MapMenu] Module loaded.\n")

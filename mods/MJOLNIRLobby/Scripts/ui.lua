-- MJOLNIR Lobby: a small kit for menu screens made from the game's own widgets.
--
-- A screen is an instance of the campaign menu's screen class
-- (WBP_CampaignMenu_C: header, sub-header, a button column, a description and
-- the fireteam panel) pushed onto the UI layout's ContentStack, with its own
-- buttons swapped for ours. CommonUI then gives it everything a native screen
-- has: focus, keyboard/controller/mouse navigation, the Back action.
--
-- Clicks. A CommonUI button reports a click only through its
-- OnButtonBaseClicked delegate, called natively, so nothing on the button
-- itself is hookable, and UE4SS's Lua cannot bind a delegate. The native half
-- (native/lobby) binds each of our buttons' delegate to a "clicker": a hidden
-- WBP_MeteoriteHyperlink whose Blueprint function SetHyperlinkText takes no
-- parameters and only sets its own text. The hook on that function is the
-- click. Each clicker is parked, collapsed, in its button's named slot, so it
-- lives exactly as long as the button, and is armed a moment after creation
-- because construction calls SetHyperlinkText too.
--
-- Hook only Blueprint-scripted functions here: a hook on a native function
-- with parameters crashed inside UE4SS's argument marshalling (2026-10-01).

local UI = {}

local BUTTON_CLASS = "/Game/UI/Shared/Widgets/Buttons/WBP_MeteoriteStandaloneButtonDefault.WBP_MeteoriteStandaloneButtonDefault_C"
local CLICKER_CLASS = "/Game/UI/Shared/Widgets/Buttons/WBP_MeteoriteHyperlink.WBP_MeteoriteHyperlink_C"
local CLICKER_FUNCTION = "SetHyperlinkText"
local SCREEN_CLASS = "/Game/UI/Frontend/CampaignMenu/Widgets/WBP_CampaignMenu.WBP_CampaignMenu_C"
local WIDGET_LIBRARY = "/Script/UMG.Default__WidgetBlueprintLibrary"

-- ESlateVisibility
local VISIBLE, COLLAPSED = 0, 1

-- The screen's own buttons, hidden on ours.
local NATIVE_BUTTONS = { "ResumeCampaignButton", "ResumeRemixButton", "ResumeDLCButton", "NewGameButton",
                         "NewLASOButton", "AdditionalMissionsButton" }

local log = function(msg) print("[MJOLNIR Lobby] " .. tostring(msg) .. "\n") end
local nativeDir, bind
local clickers = {}   -- clicker address -> { name, fn, armed }
local screens = {}    -- screen address -> screen record
local hooked = false

local function valid(o)
    local ok, v = pcall(function() return o and o:IsValid() end)
    return ok and v
end

local function addressOf(o)
    local ok, a = pcall(function() return o:GetAddress() end)
    return ok and a or nil
end

local function nameOf(o)
    local ok, n = pcall(function() return o:GetFName():ToString() end)
    return ok and n or nil
end

--- The local player's controller, read through the engine (its first local
--- player): a few property reads. After a world change FindFirstOf can
--- return the previous world's controller, and FindAllOf walks every object
--- in the game, ~20 ms on a converted map (200,000 objects, 2026-10-02).
local Engine = nil
function UI.playerController()
    if not valid(Engine) then
        Engine = FindFirstOf("GameEngine")
        if not valid(Engine) then return nil end
    end
    local ok, pc = pcall(function()
        return Engine.GameViewport.GameInstance.LocalPlayers[1].PlayerController
    end)
    if ok and valid(pc) then return pc end
    return nil
end

--- The live instance of a widget class. After a level and back, FindFirstOf
--- can return the previous frontend's widget: still a UObject until the next
--- garbage collection, but its Slate widgets are gone, and pushing a screen
--- onto that UI layout read through a null (crash on MULTIPLAYER, 2026-10-01).
--- `alive(widget)` tells the live one apart; class defaults are skipped.
function UI.liveWidget(className, alive)
    for _, w in ipairs(FindAllOf(className) or {}) do
        if valid(w) and not (nameOf(w) or "Default__"):find("^Default__") then
            local ok, yes = pcall(alive, w)
            if ok and yes then return w end
        end
    end
    return nil
end

--- The UI layout on screen (the one in the viewport).
function UI.layout()
    return UI.liveWidget("WBP_MeteoriteUILayout_C", function(w) return w:IsInViewport() end)
end

--- A Blueprint class by object path, loading its package the first time:
--- the frontend loads most screens' classes only when they are first opened.
function UI.ensureClass(classPath)
    local cls = StaticFindObject(classPath)
    if valid(cls) then return cls end
    -- LoadAsset takes the asset's object path (Package.Asset), not the
    -- package alone and not the generated class.
    pcall(function() LoadAsset((classPath:gsub("_C$", ""))) end)
    cls = StaticFindObject(classPath)
    if valid(cls) then return cls end
    return nil
end

local function create(owner, classPath)
    local cls = UI.ensureClass(classPath)
    if not cls then return nil, "class not loaded: " .. classPath end
    local widget = StaticFindObject(WIDGET_LIBRARY):Create(owner, cls, UI.playerController())
    if not valid(widget) then return nil, "could not create " .. classPath end
    return widget
end

--- Bind each { widget, target } pair's click delegate through the native half.
local function bindClicks(pairs_)
    if not bind then return false, "native half not loaded" end
    local f = io.open(nativeDir .. "lobby_request.txt", "w")
    if not f then return false, "cannot write the request file" end
    for _, p in ipairs(pairs_) do
        f:write(string.format("%d OnButtonBaseClicked %d %s\n", addressOf(p[1]), addressOf(p[2]), CLICKER_FUNCTION))
    end
    f:close()
    bind()
    local r = io.open(nativeDir .. "lobby_reply.txt", "r")
    if not r then return false, "no reply from the native half" end
    local reply = r:read("*a")
    r:close()
    local failures = {}
    for line in reply:gmatch("[^\n]+") do
        if not line:find("^ok ") then failures[#failures + 1] = line end
    end
    if #failures > 0 then return false, table.concat(failures, "; ") end
    return true
end

local function hookClickers()
    if hooked then return end
    local ok, err = pcall(function()
        RegisterHook(CLICKER_CLASS .. ":" .. CLICKER_FUNCTION, function(self)
            local clicker = self:get()
            local entry = clickers[addressOf(clicker)]
            -- An address can be reused after garbage collection: the
            -- object's unique name has to match too.
            if not entry or not entry.armed or entry.name ~= nameOf(clicker) then return end
            -- A real click comes from a button the player is on: under the
            -- mouse, or holding keyboard/controller focus. The game also
            -- calls this function on every hyperlink when its UI refreshes
            -- (a player leaving), which clicked every armed button at once,
            -- END GAME and RETURN TO LOBBY included (two PCs, 2026-10-03).
            local okOn, on = pcall(function()
                local b = entry.button
                return b:IsVisible() and (b:IsHovered() or b:HasAnyUserFocus() or b:HasFocusedDescendants())
            end)
            if not (okOn and on) then
                log("click ignored (not on its button): " .. tostring(entry.label))
                return
            end
            log("click: " .. tostring(entry.label))
            ExecuteInGameThread(function()
                local okFn, errFn = pcall(entry.fn)
                if not okFn then log("click handler failed: " .. tostring(errFn)) end
            end)
        end)
    end)
    hooked = ok
    if not ok then log("could not hook the clicker: " .. tostring(err)) end
end

--- A button of the main menu's kind, with `fn` run on click.
--- `owner` is the screen or menu it belongs to.
function UI.button(owner, label, fn)
    local button, err = create(owner, BUTTON_CLASS)
    if not button then return nil, err end
    local clicker
    clicker, err = create(owner, CLICKER_CLASS)
    if not clicker then return nil, err end
    hookClickers()
    local okBind, bindErr = bindClicks({ { button, clicker } })
    if not okBind then return nil, bindErr end
    -- Parked inside the button: lives as long as it does, takes no space.
    pcall(function() button.LeafNamedSlot:SetContent(clicker) end)
    pcall(function() clicker:SetVisibility(COLLAPSED) end)
    pcall(function() button.bInteractableWhenSelected = true end)
    local entry = { name = nameOf(clicker), fn = fn, armed = false, label = label, button = button }
    clickers[addressOf(clicker)] = entry
    ExecuteInGameThreadWithDelay(300, function() entry.armed = true end)
    return { widget = button, clicker = clicker, label = label }
end

--- Label a button; a label set before the button is constructed is lost,
--- so callers set it again once the button is on screen.
function UI.label(b, text)
    pcall(function() b.widget:SetButtonLabelText(FText(text)) end)
end

--- Load the native half from the mod's native directory.
function UI.init(modDir)
    nativeDir = modDir .. "\\native\\"
    if package and package.loadlib then
        bind = package.loadlib(nativeDir .. "mjolnir_lobby.dll", "mjolnir_lobby_bind")
    end
    if not bind then log("native\\mjolnir_lobby.dll not loaded: buttons cannot be clicked") end
    return bind ~= nil
end

-------------------------------------------------------------------------------
-- Screens
-------------------------------------------------------------------------------

local function treeChild(screen, name)
    local ok, w = pcall(function()
        return StaticFindObject(screen.WidgetTree:GetFullName():match("^%S+ (.*)$") .. "." .. name)
    end)
    if ok and valid(w) then return w end
    return nil
end

local function showWithParents(widget, stopAt)
    local w = widget
    for _ = 1, 8 do
        if not valid(w) or (stopAt and addressOf(w) == addressOf(stopAt)) then break end
        pcall(function() if w:GetVisibility() == COLLAPSED then w:SetVisibility(VISIBLE) end end)
        local ok, parent = pcall(function() return w:GetParent() end)
        w = ok and parent or nil
    end
end

local function setDescription(rec, text)
    local d = treeChild(rec.screen, "RemixDiscription")
    if not d then return end
    pcall(function() d:SetText(FText(text or "")) end)
    if text and text ~= "" then showWithParents(d, rec.screen) end
end

--- Put the screen's texts, buttons and focus in place. Run after the push and
--- again whenever the screen is activated, because the campaign menu's own
--- activation logic resets its buttons and texts.
local function apply(rec)
    local s = rec.screen
    if not valid(s) then return end
    local header, sub = treeChild(s, "HeaderLabel"), treeChild(s, "SubHeaderLabel")
    if header then pcall(function() header:SetText(FText(rec.spec.title or "")) end) end
    if sub then pcall(function() sub:SetText(FText(rec.spec.subtitle or "")) end) end
    for _, n in ipairs(NATIVE_BUTTONS) do
        pcall(function() local w = s[n] if valid(w) then w:SetVisibility(COLLAPSED) end end)
    end
    pcall(function() s.WBP_ResumeCampaignInfoPanel:SetVisibility(COLLAPSED) end)
    for _, b in ipairs(rec.buttons) do
        UI.label(b, b.label)
        pcall(function() b.widget:SetVisibility(VISIBLE) end)
    end
    setDescription(rec, rec.spec.description)
    if rec.buttons[1] then
        pcall(function() s.MainButtonContainer:SetInitialFocus(true) end)
        pcall(function() rec.buttons[1].widget:SetFocus() end)
    end
end

--- Push a screen: { title, subtitle, description, buttons = { { label, description, onClick } },
--- layout (optional: the UI layout to push onto; in a match the game runs two,
--- and the pause menu is on one of them) }.
function UI.push(spec)
    local layout = spec.layout or UI.layout()
    if not valid(layout) then
        log("screen '" .. tostring(spec.title) .. "': no UI layout")
        return nil
    end
    local cls = UI.ensureClass(SCREEN_CLASS)
    if not cls then
        log("screen '" .. tostring(spec.title) .. "': screen class not loaded")
        return nil
    end
    UI.installScreenHooks()
    local screen = layout.ContentStack:BP_AddWidget(cls)
    if not valid(screen) then
        log("screen '" .. tostring(spec.title) .. "': push failed")
        return nil
    end
    local rec = { screen = screen, spec = spec, buttons = {} }
    screens[addressOf(screen)] = rec

    -- Our buttons go into the container's own slots (replacing a slot keeps
    -- its button group consistent; an appended button after hidden native
    -- ones left the selection on a hidden button), then any extra are added.
    local container = screen.MainButtonContainer
    local slots = 0
    pcall(function() slots = container:GetChildrenCount() end)
    for i, b in ipairs(spec.buttons or {}) do
        local made, err = UI.button(screen, b.label, b.onClick)
        if not made then
            log("button '" .. tostring(b.label) .. "': " .. tostring(err))
        else
            made.description = b.description
            if i <= slots then
                container:ReplaceButtonContainerChildAt(i - 1, made.widget)
            else
                container:AddChildToButtonContainer(made.widget)
            end
            rec.buttons[#rec.buttons + 1] = made
        end
    end
    ExecuteInGameThreadWithDelay(60, function() apply(rec) end)
    return rec
end

--- Change a pushed screen's description (e.g. a status line).
function UI.describe(rec, text)
    rec.spec.description = text
    setDescription(rec, text)
end

--- Pop the top screen, as Back does.
function UI.pop(rec)
    pcall(function() rec.screen:DeactivateWidget() end)
end

--- Hooks that keep pushed screens ours: re-apply after the campaign menu's
--- own activation logic, and show each button's description on selection.
local screenHooks = false
function UI.installScreenHooks()
    if screenHooks then return end
    screenHooks = true
    pcall(function()
        RegisterHook(SCREEN_CLASS .. ":BP_OnActivated", function(self)
            local rec = screens[addressOf(self:get())]
            if rec then ExecuteInGameThreadWithDelay(30, function() apply(rec) end) end
        end)
    end)
    pcall(function()
        RegisterHook(SCREEN_CLASS .. ":BndEvt__WBP_CampaignMenu_MainButtonContainer_K2Node_ComponentBoundEvent_12_SimpleButtonBaseGroupDelegate__DelegateSignature",
            function(self, button)
                local rec = screens[addressOf(self:get())]
                if not rec then return end
                local a = addressOf(button:get())
                for _, b in ipairs(rec.buttons) do
                    if addressOf(b.widget) == a then
                        setDescription(rec, b.description or rec.spec.description)
                        return
                    end
                end
            end)
    end)
end

--- Log a loop run that held the game thread past 50 ms, at most once every
--- 30 s per loop: a CTF host froze ~250 ms every 3.24 s in Lua, and nothing
--- said which loop it was (playtest, 2026-10-03). `started` is os.clock()
--- at the run's start.
local slowAt = {}
function UI.reportSlow(name, started)
    local took = os.clock() - started
    if took > 0.05 and started - (slowAt[name] or -100) > 30 then
        slowAt[name] = started
        log(string.format("slow: the %s loop held the game thread %.0f ms", name, took * 1000))
    end
end

UI.log = log
UI.valid = valid
UI.addressOf = addressOf
return UI

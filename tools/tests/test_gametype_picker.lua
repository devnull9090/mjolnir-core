-- Run from the repository root with Lua 5.4, or Python + lupa:
-- python -c "from lupa import LuaRuntime; LuaRuntime().execute(open('tools/tests/test_gametype_picker.lua').read())"
-- Exercises the real picker through its screen events. No game or files are
-- changed: the commit callback represents the lobby's save/broadcast boundary.
local function eq(actual, expected, label)
    assert(actual == expected, (label or "value") .. ": expected " .. tostring(expected) .. ", got " .. tostring(actual))
end

FText = function(value) return value end
StaticFindObject = function() return nil end -- Missing icons must not prevent selection.
local GameType = dofile("mods/MJOLNIRLobby/Scripts/gametype.lua")
local Modes = dofile("mods/MJOLNIRLobby/Scripts/modes.lua")

local MODES = {
    { id = "slayer", name = "SLAYER", description = "Every Spartan for themselves." },
    { id = "team_slayer", name = "TEAM SLAYER", teams = true, description = "Kills score for your team." },
    { id = "koth", name = "KING OF THE HILL", description = "Hold the hill to score." },
    { id = "oddball", name = "ODDBALL", description = "Hold the skull to score." },
    { id = "ctf", name = "CAPTURE THE FLAG", teams = true, description = "Take the enemy flag to your base." },
    { id = "forge", name = "FORGE", forge = true, description = "Build and edit the map." },
}

local function harness(families)
    local h = {
        map = { code = "BGL", title = "Blood Gulch" }, mode = MODES[2], modes = MODES,
        host = true, hasClass = true, screens = {}, commits = {}, notes = {}, covers = {},
        fallbacks = 0, focusReturns = 0,
    }
    local nextAddress = 0
    local function widget()
        nextAddress = nextAddress + 1
        local address = nextAddress
        return {
            IsValid = function(self) return not self.invalid end,
            GetAddress = function() return address end,
            SetText = function(self, value) self.text = value end,
            SetVisibility = function(self, value) self.visibility = value end,
            SetIsEnabled = function(self, value) self.enabled = value end,
            SetFocus = function(self) h.focus = self end,
            SetBackgroundColor = function(self, value) self.background = value end,
            SetColorAndOpacity = function(self, value) self.color = value end,
            SetBrushFromTexture = function(self, value) self.texture = value end,
            SetBrushTintColor = function(self, value) self.tint = value end,
            SetOpacity = function(self, value) self.opacity = value end,
        }
    end
    local function screen()
        local s = widget()
        s.active = true
        s.IsActivated = function(self) return self.active end
        s.DeactivateWidget = function(self) self.active = false end
        for _, key in ipairs({ "ModeTitle", "ModeDescription", "MatchFormat", "ModeIcon", "MapTitle",
                               "ListCount", "Status", "Select", "Back", "MapImage", "MapImageNote" }) do
            s[key] = widget()
        end
        for i = 0, families and 6 or 5 do
            s["Mode" .. i] = widget()
            for _, suffix in ipairs({ "Label", "Format", "Icon", "Current" }) do
                s["Mode" .. i .. suffix] = widget()
            end
        end
        -- The UI container from before the variant buttons has none of these.
        if families then
            s.SelectLabel, s.VariantBlock = widget(), widget()
            for i = 0, 4 do
                s["Variant" .. i] = widget()
                s["Variant" .. i .. "Label"], s["Variant" .. i .. "Line"] = widget(), widget()
            end
        end
        return s
    end
    Modes.memory = {}
    h.picker = GameType.new({
        modes = Modes,
        valid = function(value) return type(value) == "table" and not value.invalid end,
        alive = function(value) return value ~= nil and value.active == true end,
        sameWidget = function(a, b) return a:GetAddress() == b:GetAddress() end,
        loadClass = function() return h.hasClass and {} or nil end,
        pushScreen = function()
            local s = screen()
            h.screens[#h.screens + 1] = s
            return s
        end,
        current = function() return h.map, h.mode end,
        modesFor = function() return h.modes end,
        isHost = function() return h.host end,
        titleOf = function(map) return string.upper(map.title) end,
        showCover = function(s, code) h.covers[#h.covers + 1] = { screen = s, code = code } end,
        commit = function(mode)
            h.commits[#h.commits + 1] = mode
            h.mode = mode
        end,
        fallback = function() h.fallbacks = h.fallbacks + 1 end,
        focusLobby = function() h.focusReturns = h.focusReturns + 1 end,
        note = function(text) h.notes[#h.notes + 1] = text end,
    })
    function h.open()
        h.picker.open()
        return h.screens[#h.screens]
    end
    function h.event(event, source) h.picker.onEvent(event, source or h.screens[#h.screens]) end
    return h
end

-- Opening preserves the current mode; all six supported modes are reachable.
local h = harness()
eq(h.picker.available(), true, "new screen available")
local s = h.open()
eq(h.picker.active(), true, "picker active")
eq(#h.commits, 0, "opening does not save")
eq(s.ModeTitle.text, "TEAM SLAYER", "current mode shown")
eq(s.MapTitle.text, "BLOOD GULCH", "current map shown")
eq(h.covers[1].code, "BGL", "current map cover requested")
eq(h.focus, s.Mode1, "current mode receives focus")
eq(s.Mode5Label.text, "FORGE", "sixth mode visible")
eq(s.Select.enabled, true, "valid selection enabled")

-- Hover is only a preview and unhover restores the pending choice.
-- UE4SS can wrap the same native UObject in a different Lua userdata for
-- self:get() in a hook. Identity must use its native address.
local sourceWrapper = { GetAddress = function() return s:GetAddress() end }
assert(sourceWrapper ~= s, "test uses a distinct wrapper for the same screen")
h.event("hover:3", sourceWrapper)
eq(s.ModeTitle.text, "ODDBALL", "hover previews")
eq(h.mode.id, "team_slayer", "hover leaves lobby unchanged")
h.event("unhover:3")
eq(s.ModeTitle.text, "TEAM SLAYER", "unhover restores selection")
h.event("mode:4")
eq(s.ModeTitle.text, "CAPTURE THE FLAG", "click selects pending mode")
eq(h.mode.id, "team_slayer", "pending choice leaves lobby unchanged")
eq(#h.commits, 0, "preview does not save or broadcast")
h.event("hover:0")
h.event("select")
eq(#h.commits, 1, "Select commits once")
eq(h.commits[1].id, "ctf", "Select uses pending choice, not hover")
eq(h.picker.active(), false, "Select closes picker")
eq(h.focusReturns, 1, "Select returns focus to lobby")
h.event("select", s)
eq(#h.commits, 1, "late double-click cannot commit twice")

-- Back and CommonUI's own Escape/B deactivation both discard pending choices.
h = harness()
s = h.open()
h.event("mode:5")
h.event("back")
eq(#h.commits, 0, "Back does not save")
eq(h.picker.active(), false, "Back closes")
eq(h.focusReturns, 1, "Back returns focus")
s = h.open()
eq(s.ModeTitle.text, "TEAM SLAYER", "reopen discards canceled choice")
h.event("mode:0")
s:DeactivateWidget()
h.event("select", s)
eq(#h.commits, 0, "Escape does not allow a queued confirmation")
local old = s
s = h.open()
eq(s.ModeTitle.text, "TEAM SLAYER", "reopen after Escape uses lobby choice")
h.event("mode:4", old)
h.event("select", old)
eq(#h.commits, 0, "events from previous screen ignored")
eq(s.ModeTitle.text, "TEAM SLAYER", "old screen cannot change pending choice")
eq(h.picker.active(), true, "stale event cannot close new screen")
h.event("mode:99")
h.event("hover:99")
eq(s.ModeTitle.text, "TEAM SLAYER", "out-of-range events ignored")

-- Authority and map changes while the picker is open cannot overwrite the lobby.
h = harness()
h.open()
h.event("mode:4")
h.host = false
h.event("select")
eq(#h.commits, 0, "former host cannot confirm")
h = harness()
h.open()
h.event("mode:4")
h.map = { code = "WIZ", title = "Wizard" }
h.event("select")
eq(#h.commits, 0, "choice for a previous map cannot commit")

-- Resolve the chosen ID against current availability, not its old row index.
h = harness()
h.open()
h.event("mode:4")
h.modes = { MODES[5], MODES[1] }
h.event("select")
eq(#h.commits, 1, "reordered availability still permits choice")
eq(h.commits[1].id, "ctf", "mode identity survives list reorder")
h = harness()
h.open()
h.event("mode:4")
h.modes = { MODES[1] }
h.event("select")
eq(#h.commits, 0, "removed mode cannot be confirmed")

-- A saved mode no longer offered selects the first available mode provisionally.
h = harness()
h.modes = { MODES[3], MODES[4] }
s = h.open()
eq(s.ModeTitle.text, "KING OF THE HILL", "unavailable current mode has a valid fallback")
eq(#h.commits, 0, "fallback is still provisional")
h.event("select")
eq(h.commits[1].id, "koth", "fallback can be explicitly confirmed")
h = harness()
h.open()
h.event("mode:5")
h.event("select")
eq(h.commits[1].id, "forge", "sixth mode can be confirmed")

-- A tile is an engine: a click on the chosen tile steps through its variants,
-- and SELECT commits the variant, never the engine.
local KING = {}
for _, field in ipairs({ { "koth", "KING" }, { "crazy_king", "CRAZY KING" }, { "team_koth", "TEAM KING", true } }) do
    KING[#KING + 1] = { id = field[1], engine = "koth", name = field[2], teams = field[3], description = field[2] }
end
h = harness()
h.modes = { MODES[1], KING[1], KING[2], KING[3] }
h.mode = KING[2]
s = h.open()
eq(s.ListCount.text, "2 GAME TYPES AVAILABLE", "variants share a tile")
eq(s.Mode1Label.text, "KING OF THE HILL", "the tile names the engine")
eq(s.Mode1Format.text, "CRAZY KING  /  VARIANT 2 OF 3", "and the variant it stands for")
eq(s.Mode1Current.text, "CURRENT", "any variant of the engine marks the tile")
eq(s.ModeTitle.text, "CRAZY KING", "the current variant previews")
eq(h.focus, s.Mode1, "the current engine's tile receives focus")
eq(s.Mode2.visibility, 1, "no third tile")
h.event("mode:1")
eq(s.ModeTitle.text, "TEAM KING", "a click on the chosen tile steps")
eq(s.MatchFormat.text, "RED TEAM  /  BLUE TEAM", "and the format follows")
eq(s.Mode1Format.text, "TEAM KING  /  VARIANT 3 OF 3", "and the tile's line")
eq(#h.commits, 0, "stepping is a draft")
h.event("mode:0")
eq(s.ModeTitle.text, "SLAYER", "another tile chooses its variant")
h.event("hover:1")
eq(s.ModeTitle.text, "TEAM KING", "a tile left previews what it stands for")
h.event("unhover:1")
h.event("mode:1")
eq(s.ModeTitle.text, "TEAM KING", "and returns to it")
h.event("mode:1")
eq(s.ModeTitle.text, "KING", "the last variant wraps round")
h.event("mode:1")
h.event("select")
eq(h.commits[1].id, "crazy_king", "SELECT commits the variant")

-- The family screen: every variant is named on the left and a button on the
-- right, so nothing depends on clicking a row again. Rows are the real ones.
local function offered(...)
    local list = {}
    for _, id in ipairs({ ... }) do list[#list + 1] = Modes.byId(id) end
    return list
end
local EVERY = {}
for _, mode in ipairs(Modes) do EVERY[#EVERY + 1] = mode end

h = harness(true)
h.modes, h.mode = EVERY, Modes.byId("slayer")
s = h.open()
eq(s.ListCount.text, #EVERY .. " GAME TYPES ON THIS MAP", "the count is what can be played")
for i, name in ipairs({ "SLAYER", "CAPTURE THE FLAG", "ODDBALL", "JUGGERNAUT", "KING OF THE HILL", "RACE", "FORGE" }) do
    eq(s["Mode" .. i - 1 .. "Label"].text, name, "family " .. i)
    eq(s["Mode" .. i - 1].visibility, 0, "family " .. i .. " shown")
end
eq(s.Mode2Format.text, "ODDBALL  /  TEAM ODDBALL", "Oddball is only Oddball's own")
eq(s.Mode3Format.text, "JUGGERNAUT  /  STALKER  /  REVERSE TAG", "the hunted modes have a family")
eq(s.Mode4Format.text, "KING  /  CRAZY KING  /  TEAM KING", "a family names its variants")
eq(s.Mode1Format.text, "CTF  /  ASSAULT", "Capture the Flag names its variants too")
eq(s.Mode6Format.text, "SANDBOX", "a family of one gives its format")
eq(s.Mode0Current.text, "CURRENT", "the current family is marked")
eq(s.VariantBlock.visibility, 0, "Slayer's variants show at once")
eq(s.Variant0Label.text, "SLAYER", "first variant")
eq(s.Variant0Line.text, "FREE FOR ALL  /  CURRENT", "the current variant is marked")
eq(s.Variant1Label.text, "TEAM SLAYER", "second variant")
eq(s.Variant1Line.text, "TEAMS", "and says it is teams")
eq(s.Variant2.visibility, 1, "no third button")
eq(s.SelectLabel.text, "SELECT SLAYER", "SELECT says what it will start")

-- Team King in two clicks, and a repeat click on the family changes nothing.
h.event("mode:4")
eq(s.ModeTitle.text, "KING", "a family opens on its first variant")
eq(s.Variant2Label.text, "TEAM KING", "its variants replace the buttons")
eq(s.Variant3.visibility, 1, "and only as many as it has")
h.event("mode:4")
eq(s.ModeTitle.text, "KING", "a second click on the family does not step")
h.event("variant:2")
eq(s.ModeTitle.text, "TEAM KING", "a variant button chooses it")
eq(s.SelectLabel.text, "SELECT TEAM KING", "and SELECT follows")
eq(s.MatchFormat.text, "RED TEAM  /  BLUE TEAM", "and the format")
eq(#h.commits, 0, "choosing is a draft")

-- A hover previews and leaves both the choice and the buttons alone.
h.event("vhover:1")
eq(s.ModeTitle.text, "CRAZY KING", "hovering a variant previews it")
eq(s.SelectLabel.text, "SELECT TEAM KING", "without choosing it")
h.event("vunhover:1")
eq(s.ModeTitle.text, "TEAM KING", "leaving returns to the choice")
h.event("hover:3")
eq(s.ModeTitle.text, "JUGGERNAUT", "hovering a family previews it")
eq(s.Variant2Label.text, "TEAM KING", "and the buttons stay with the chosen family")
h.event("unhover:3")
eq(s.ModeTitle.text, "TEAM KING", "leaving the family returns too")

-- A family comes back to the variant it was left on.
h.event("mode:3")
h.event("variant:1")
eq(s.ModeTitle.text, "STALKER", "Stalker has a button under Juggernaut")
h.event("mode:4")
eq(s.ModeTitle.text, "TEAM KING", "a family left keeps its variant")
h.event("mode:3")
eq(s.ModeTitle.text, "STALKER", "both ways round")

-- A family of one has no buttons, and a button index that is not there is dropped.
h.event("mode:6")
eq(s.ModeTitle.text, "FORGE", "the single variant is chosen")
eq(s.VariantBlock.visibility, 2, "no buttons, and the block keeps its space")
eq(s.Variant0.visibility, 1, "its first button is gone too")
h.event("variant:0")
h.event("vhover:0")
eq(s.ModeTitle.text, "FORGE", "an event from a hidden button changes nothing")
h.event("mode:4")
h.event("variant:4")
h.event("variant:99")
eq(s.ModeTitle.text, "TEAM KING", "out-of-range variants are ignored")
h.event("select")
eq(h.commits[1].id, "team_koth", "SELECT commits the variant")

-- A lobby already on a variant opens in its family with it chosen.
h = harness(true)
h.modes, h.mode = EVERY, Modes.byId("reverse_tag")
s = h.open()
eq(h.focus, s.Mode3, "the current family receives focus")
eq(s.ModeTitle.text, "REVERSE TAG", "the current variant shows")
eq(s.Variant2Line.text, "FREE FOR ALL  /  CURRENT", "and is marked")

-- A map with less on offer: a family named by what it has, tiles closing up.
h = harness(true)
h.modes, h.mode = offered("slayer", "stalker", "reverse_tag"), Modes.byId("stalker")
s = h.open()
eq(s.Mode1Label.text, "STALKER", "a family without its namesake goes by its first variant")
eq(s.Mode2.visibility, 1, "no third row")
eq(s.Mode6.visibility, 1, "and no seventh")
eq(s.ListCount.text, "3 GAME TYPES ON THIS MAP", "the count follows")

-- Map select draws the same buttons: no second line, nothing marked current,
-- and none at all for a map only hovered over.
h = harness(true)
h.modes, h.mode = EVERY, Modes.byId("slayer")
s = h.open()
local tiles = Modes.families(EVERY)
eq(Modes.tileOf(tiles, "stalker").id, "juggernaut", "tileOf finds the family")
eq(Modes.tileOf(tiles, "nothing"), nil, "and nothing for an id it lacks")
eq(Modes.tileOf(tiles, "koth").short, "KING", "a long family name has a short one for a tab")
eq(Modes.tileOf(tiles, "ctf").short, "CTF", "so has Capture the Flag")
eq(Modes.tileOf(tiles, "slayer").short, nil, "a short name needs none")
eq(Modes.families(offered("crazy_king", "team_koth"))[1].short, nil, "a family without its namesake drops it too")
local select = {}
for _, key in ipairs({ "VariantBlock", "Variant0", "Variant0Label", "Variant0Mark", "Variant1", "Variant1Label",
                       "Variant1Mark", "Variant2", "Variant2Label", "Variant3", "Variant3Label", "Variant4",
                       "Variant4Label" }) do
    select[key] = {
        SetVisibility = function(self, value) self.visibility = value end,
        SetText = function(self, value) self.text = value end,
        SetBackgroundColor = function(self, value) self.background = value end,
        SetColorAndOpacity = function(self, value) self.color = value end,
    }
end
h.picker.showVariants(select, Modes.tileOf(tiles, "team_race"), Modes.byId("team_race"))
eq(select.VariantBlock.visibility, 0, "map select shows a family's variants")
eq(select.Variant3Label.text, "TEAM RALLY", "all of them")
eq(select.Variant4.visibility, 1, "and only those")
assert(select.Variant1.background.R > 1 and select.Variant0.background.R == 1, "the chosen variant is lit")
eq(select.Variant1Mark.visibility, 3, "and has the gold bar")
eq(select.Variant0Mark.visibility, 2, "which the others do not")
h.picker.showVariants(select, nil, nil)
eq(select.VariantBlock.visibility, 2, "a map only hovered over has none")
eq(select.Variant0.visibility, 1, "no buttons either")
h.picker.showVariants(select, Modes.tileOf(tiles, "forge"), Modes.byId("forge"))
eq(select.VariantBlock.visibility, 2, "a family of one has none")

-- An older UI container keeps the engine tiles and the stepping.
h = harness()
h.modes, h.mode = EVERY, Modes.byId("slayer")
s = h.open()
eq(s.ListCount.text, "6 GAME TYPES AVAILABLE", "six engine tiles")
eq(s.Mode2Label.text, "ODDBALL", "the Oddball tile")
eq(s.Mode2Format.text, "ODDBALL  /  VARIANT 1 OF 5", "still holds what runs on its engine")
h.event("mode:2")
h.event("mode:2")
eq(s.ModeTitle.text, "TEAM ODDBALL", "and a repeat click steps")

-- Empty maps remain navigable, while old UI containers retain a working route.
h = harness(true)
h.modes = {}
s = h.open()
eq(s.VariantBlock.visibility, 2, "nothing to choose between")
eq(s.ListCount.text, "0 GAME TYPES ON THIS MAP", "and the count says so")
h = harness()
h.modes = {}
s = h.open()
eq(s.Select.enabled, false, "no modes disables Select")
eq(h.focus, s.Back, "empty picker focuses Back")
h.event("select")
eq(#h.commits, 0, "no modes cannot commit")
h.event("back")
eq(h.picker.active(), false, "empty picker can be dismissed")
h = harness()
h.hasClass = false
eq(h.picker.available(), false, "old container detected")
h.open()
eq(h.fallbacks, 1, "old container opens fallback")
eq(#h.screens, 0, "missing screen is not pushed")
eq(#h.commits, 0, "fallback opening does not mutate mode")
h = harness()
h.host = false
h.open()
eq(#h.screens, 0, "client cannot open picker")
eq(h.fallbacks, 0, "client cannot use fallback")
h = harness()
h.map = nil
h.open()
eq(#h.screens, 0, "no map cannot open picker")

print("Game type picker: families, variant buttons, previews, explicit selection, cancellation, stale events, host/map changes and compatibility passed")

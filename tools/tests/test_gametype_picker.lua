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

local MODES = {
    { id = "slayer", name = "SLAYER", description = "Every Spartan for themselves." },
    { id = "team_slayer", name = "TEAM SLAYER", teams = true, description = "Kills score for your team." },
    { id = "koth", name = "KING OF THE HILL", description = "Hold the hill to score." },
    { id = "oddball", name = "ODDBALL", description = "Hold the skull to score." },
    { id = "ctf", name = "CAPTURE THE FLAG", teams = true, description = "Take the enemy flag to your base." },
    { id = "forge", name = "FORGE", forge = true, description = "Build and edit the map." },
}

local function harness()
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
        for i = 0, 5 do
            s["Mode" .. i] = widget()
            for _, suffix in ipairs({ "Label", "Format", "Icon", "Current" }) do
                s["Mode" .. i .. suffix] = widget()
            end
        end
        return s
    end
    h.picker = GameType.new({
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

-- Empty maps remain navigable, while old UI containers retain a working route.
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

print("Game type picker: six modes, previews, explicit selection, cancellation, stale events, host/map changes and compatibility passed")

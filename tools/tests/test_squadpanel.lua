-- Run from the repository root with Lua 5.4, or Python + lupa:
-- python -c "from lupa import LuaRuntime; LuaRuntime().execute(open('tools/tests/test_squadpanel.lua').read())"
--
-- Drives MJOLNIRLobby's squadpanel.lua against a minimal FIRETEAM panel. The
-- list builds a row's widget later than AddItem, from the item's own class
-- when it carries one and otherwise from the list's EntryWidgetClass at that
-- moment, which is how the game's HaloUIListView behaves.
local function eq(actual, expected, label)
    assert(actual == expected, (label or "value") .. ": expected " .. tostring(expected) .. ", got " .. tostring(actual))
end

local nextAddress = 0
local function object(fields)
    nextAddress = nextAddress + 1
    local o = fields or {}
    local address = nextAddress
    o.IsValid = function() return true end
    o.GetAddress = function() return address end
    return o
end
local function str(s) return { ToString = function() return s end } end

local PLAYER, BLANK = "WBP_SquadPlayerListViewItem_C", "WBP_SquadBlankListViewItem_C"
local players = {}
local function player(name)
    local ps = object({ GetPlayerName = function() return str(name) end })
    players[#players + 1] = ps
    return ps
end

-- A view model player row as the game makes it: its class rides with it.
local function viewModelItem(kind, ps)
    local item = object({ FireteamRowType = kind, native = kind == 0 and PLAYER or BLANK })
    if ps then
        item.PlayerViewModel = object({ PlayerState = ps, DisplayName = ps:GetPlayerName(), PlatformType = 2 })
    end
    return item
end

local list = object({ items = {}, EntryWidgetClass = PLAYER })
function list:GetNumItems() return #self.items end
function list:GetItemAt(i) return self.items[i + 1] end
function list:AddItem(item) self.items[#self.items + 1] = item end
function list:RemoveItem(item)
    for i, it in ipairs(self.items) do
        if it == item then table.remove(self.items, i); return end
    end
end
--- The end of a frame: rows without a widget get one.
function list:build()
    for _, it in ipairs(self.items) do it.built = it.built or it.native or self.EntryWidgetClass end
end
function list:names()
    local out = {}
    for _, it in ipairs(self.items) do
        if it.FireteamRowType == 0 then out[#out + 1] = it.PlayerViewModel.DisplayName:ToString() .. ":" .. it.built
        else out[#out + 1] = "INVITE:" .. it.built end
    end
    return table.concat(out, ", ")
end

local header = object({ text = "Fireteam 1/4" })
function header:GetText() return str(self.text) end
function header:SetText(v) self.text = v end

local widget = object({ SquadListView = list, FireteamHeader = header })
widget.GetFullName = function() return "WBP_SquadWidget_C /Engine/Transient.GameEngine.WBP_SquadWidget_C_1" end
widget.GetWorld = function()
    return { GameState = { PlayerArray = { ForEach = function(_, fn)
        for i, ps in ipairs(players) do fn(i, { get = function() return ps end }) end
    end } } }
end
local vm = object({ PlayerWidgetClass = PLAYER, BlankWidgetClass = BLANK })

-- UE4SS, as far as the module uses it.
function FindAllOf(class) return class == "WBP_SquadWidget_C" and { widget } or {} end
function FindFirstOf(class) return class == "MeteoriteSquadLobbyViewModel" and vm or nil end
function StaticFindObject(path) return { path = path } end
function FName(s) return s end
function FText(s) return s end
function ExecuteInGameThreadWithDelay() end
function RegisterHook() end
function StaticConstructObject(class, _, _, _, _, _, _, template)
    local o = object({ class = class.path })
    if template then o.native = template.native end
    -- A StrProperty reads back as an FString.
    return setmetatable(o, { __newindex = function(t, k, v)
        rawset(t, k, (k == "DisplayName" and type(v) == "string") and str(v) or v)
    end })
end

local SquadPanel = dofile("mods/MJOLNIRLobby/Scripts/squadpanel.lua")

--- The panel's own rebuild: the view model's four slots, players first.
local function rebuild()
    list.items = {}
    local shown = 0
    for i = 1, math.min(#players, 4) do list:AddItem(viewModelItem(0, players[i])); shown = i end
    for _ = shown + 1, 4 do list:AddItem(viewModelItem(2)) end
    list.EntryWidgetClass = PLAYER
    list:build()
end

-- Fewer than four players: the view model's own rows, the real limit.
player("host"); player("venus")
rebuild(); SquadPanel.refresh(16); list:build()
eq(list:names(), "host:" .. PLAYER .. ", venus:" .. PLAYER .. ", INVITE:" .. BLANK .. ", INVITE:" .. BLANK)
eq(header.text, "Fireteam 2/16")

-- Four players: the slots are full, so one INVITE + is added.
player("g1"); player("g2")
rebuild(); SquadPanel.refresh(16); list:build()
eq(#list.items, 5); eq(list.items[5].FireteamRowType, 2); eq(list.items[5].built, BLANK, "added INVITE +")
eq(header.text, "Fireteam 4/16")

-- A fifth player gets a player row, built as one even though the blank
-- class is the list's fallback, and INVITE + stays last.
player("g3")
rebuild(); SquadPanel.refresh(16); list:build()
eq(list:names(), "host:" .. PLAYER .. ", venus:" .. PLAYER .. ", g1:" .. PLAYER .. ", g2:" .. PLAYER
    .. ", g3:" .. PLAYER .. ", INVITE:" .. BLANK)
eq(header.text, "Fireteam 5/16")

-- Refreshing again changes nothing.
SquadPanel.refresh(16); list:build()
eq(#list.items, 6, "idempotent")

-- A sixth player without a rebuild (the view model's four slots did not
-- change): its row goes above INVITE +.
player("g4")
SquadPanel.refresh(16); list:build()
eq(list.items[6].PlayerViewModel.DisplayName:ToString(), "g4"); eq(list.items[6].built, PLAYER)
eq(list.items[7].FireteamRowType, 2); eq(#list.items, 7)

-- A player who leaves loses the row added for them.
table.remove(players, 5)   -- g3
SquadPanel.refresh(16); list:build()
eq(list:names(), "host:" .. PLAYER .. ", venus:" .. PLAYER .. ", g1:" .. PLAYER .. ", g2:" .. PLAYER
    .. ", g4:" .. PLAYER .. ", INVITE:" .. BLANK)
eq(header.text, "Fireteam 5/16")

-- When the view model shows a player that has a row of ours, ours goes.
table.remove(players, 2)   -- venus: g4 moves into the view model's slots
list.items[2] = viewModelItem(0, players[4]); list.items[2].built = PLAYER
SquadPanel.refresh(16); list:build()
eq(list:names(), "host:" .. PLAYER .. ", g4:" .. PLAYER .. ", g1:" .. PLAYER .. ", g2:" .. PLAYER
    .. ", INVITE:" .. BLANK)

-- A full fireteam has no INVITE + row.
SquadPanel.refresh(4); list:build()
eq(list.items[#list.items].FireteamRowType, 0, "full")
eq(header.text, "Fireteam 4/4")

print("Squad panel: four slots, extra players, INVITE + placement, leaving, duplicates and a full fireteam passed")

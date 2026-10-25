-- MJOLNIR HUD: match chat (docs/multiplayer_hud.md, "Chat").
--
-- T opens all chat, Y team chat (all chat in free for all), Home (the game's
-- own chat key, whose party chat never connects in our games) all chat.
-- ENTER sends, ESC cancels. While the box is open the player does not move:
-- the Blam simulation takes its keys from the game viewport, and a key the
-- text box does not use (W, Space, G...) bubbles up to it. The box puts the
-- game in UI-only input, which makes the viewport ignore input, as the
-- Unreal console does while it is open, and gives game input back when it
-- closes (two PCs, 2026-10-17). Neither the pause menu's SetUIActive gate
-- nor emptying GameInput's keyboard readings stopped it.
--
-- The host relays every line, so it can keep the record moderators read
-- when a player is reported (docs/player_identity.md):
--
--   client -> host   ServerExecRPC "MJOLNIR|say|<a|t>|<text>"; the sender
--                    is the controller the RPC came in on, never the text
--   host -> clients  ClientMessage "MJOLNIR|chat|<a|t>|<Red|Blue|->|<index>|<name>|<text>"
--                    to everyone, or only the sender's team for team chat
--
-- The host writes its record beside this mod as chat_<match id>.json and
-- names it in match_outbox.txt when the match ends; MJOLNIRLobby sends it
-- to the hub (POST /matches/chat). Private matches are recorded too: a
-- report cites the match id whether the game was listed or not.

local Chat = {}

Chat.SAY = "MJOLNIR|say|"
Chat.LINE = "MJOLNIR|chat|"
Chat.MAX_BYTES = 160
Chat.ROWS = 10            -- build_mjolnir_ui.py CHAT_ROWS
Chat.SHOW_SECONDS = 9     -- a line stays up this long with the box closed
Chat.FADE_SECONDS = 1.5
Chat.HISTORY = 40
Chat.RATE = { count = 5, seconds = 6 }   -- per sender, on the host
Chat.MAX_RECORD = 5000

local CLASS = "/Game/MJOLNIR/UI/WBP_MJOLNIRChat.WBP_MJOLNIRChat_C"

--- The chat rules a player agrees to before their first line. Agreeing is
--- remembered beside this mod (chat_rules.txt holds the version agreed to);
--- a new RULES.version asks again.
local RULES = {
    version = 1,
    body = "Everything said in match chat is recorded and logged to your player account. "
        .. "Public matches post their chat logs to the MJOLNIR hub with the match, and moderators "
        .. "read the chat when a player is reported.",
    list = "Keep it civil:\n"
        .. "  -  No harassment, bullying, threats or hate speech: nothing aimed at anyone's race, ethnicity, "
        .. "religion, nationality, gender, sexuality or disability.\n"
        .. "  -  No slurs, sexual content, or graphic or violent content.\n"
        .. "  -  No spam, flooding, scams or advertising.\n"
        .. "  -  No one's personal information, your own included.\n"
        .. "  -  No impersonating other players, hosts or moderators.\n"
        .. "  -  No cheating, exploits or selling accounts.\n"
        .. "Trash talk about the game is fine. Taking it out on a person is not.",
    note = "Breaking the rules can get you reported, kicked by the host, and banned from public matches. "
        .. "You can always leave chat closed: T opens it, and nothing you don't send is recorded.",
}
local SHOWN, HIDDEN, COLLAPSED, VISIBLE = 3, 2, 1, 0
local PASS = 4 -- SelfHitTestInvisible
local GREY = { R = 0.62, G = 0.74, B = 0.82, A = 1 }
local WHITE = { R = 1, G = 1, B = 1, A = 1 }
local ACCENT = { R = 0.46, G = 0.79, B = 0.94, A = 1 }

--------------------------------------------------------------------------------
-- Text and the wire (no engine calls: tools/tests/test_multiplayer_ui.lua)
--------------------------------------------------------------------------------

--- `text` fit to send: no control characters, no "|", trimmed, at most
--- MAX_BYTES on a character boundary. "" when nothing is left.
function Chat.clean(text)
    if type(text) ~= "string" then return "" end
    text = text:gsub("[%c]", " "):gsub("|", "/"):gsub("^%s+", ""):gsub("%s+$", ""):gsub("%s%s+", " ")
    if #text > Chat.MAX_BYTES then
        text = text:sub(1, Chat.MAX_BYTES)
        -- Drop a character cut in half: trailing continuation bytes and the
        -- lead byte they belong to.
        local cut = #text
        while cut > 0 and text:byte(cut) >= 0x80 and text:byte(cut) < 0xC0 do cut = cut - 1 end
        if cut > 0 and text:byte(cut) >= 0xC0 then
            local lead = text:byte(cut)
            local need = lead >= 0xF0 and 4 or lead >= 0xE0 and 3 or 2
            if #text - cut + 1 < need then text = text:sub(1, cut - 1) end
        end
    end
    return text
end

function Chat.encodeSay(channel, text)
    return Chat.SAY .. (channel == "team" and "t" or "a") .. "|" .. Chat.clean(text)
end

--- channel, text of a client's line; nil when `msg` is not one.
function Chat.decodeSay(msg)
    if type(msg) ~= "string" or msg:sub(1, #Chat.SAY) ~= Chat.SAY then return nil end
    local ch, text = msg:sub(#Chat.SAY + 1):match("^([at])|(.*)$")
    if not ch then return nil end
    text = Chat.clean(text)
    if text == "" then return nil end
    return ch == "t" and "team" or "all", text
end

function Chat.encodeLine(l)
    local name = tostring(l.name or "?"):gsub("[|%c]", "/")
    local team = (l.team == "Red" or l.team == "Blue") and l.team or "-"
    return string.format("%s%s|%s|%d|%s|%s", Chat.LINE, l.channel == "team" and "t" or "a",
        team, tonumber(l.index) or -1, name, Chat.clean(l.text))
end

function Chat.decodeLine(msg)
    if type(msg) ~= "string" or msg:sub(1, #Chat.LINE) ~= Chat.LINE then return nil end
    local ch, team, index, name, text = msg:sub(#Chat.LINE + 1):match("^([at])|([%a%-]+)|(%-?%d+)|([^|]*)|(.*)$")
    if not ch then return nil end
    index = tonumber(index)
    return { channel = ch == "t" and "team" or "all", team = (team == "Red" or team == "Blue") and team or nil,
        index = index >= 0 and index or nil, name = name, text = Chat.clean(text) }
end

--- Whether `who` may send another line at `t` (host): RATE.count lines in
--- any RATE.seconds. `seen` is the match's own table.
function Chat.allow(seen, who, t)
    local list = seen[who] or {}
    seen[who] = list
    for i = #list, 1, -1 do
        if t - list[i] >= Chat.RATE.seconds then table.remove(list, i) end
    end
    if #list >= Chat.RATE.count then return false end
    list[#list + 1] = t
    return true
end

local function jstr(s)
    return '"' .. tostring(s):gsub('[%c"\\]', function(c)
        if c == '"' then return '\\"' end
        if c == "\\" then return "\\\\" end
        return string.format("\\u%04x", c:byte())
    end) .. '"'
end

local function jopt(s)
    if s == nil or s == "" then return "null" end
    return jstr(s)
end

--- The host's record as the hub's MatchChatLog.
function Chat.encodeRecord(id, code, startedAt, lines)
    local out = {}
    for _, l in ipairs(lines) do
        out[#out + 1] = "{" .. table.concat({
            '"t_ms":' .. string.format("%d", math.max(0, math.floor(l.t_ms or 0))),
            '"index":' .. string.format("%d", l.index or -1),
            '"name":' .. jstr((l.name or "?"):sub(1, 64)),
            '"user_id":' .. jopt(l.userId),
            '"display":' .. jopt(l.display and l.display:sub(1, 64)),
            '"team":' .. jopt(l.teamName),
            '"channel":' .. jstr(l.channel == "team" and "team" or "all"),
            '"text":' .. jstr(l.text),
        }, ",") .. "}"
    end
    return "{" .. table.concat({
        '"host_match_id":' .. jstr(id),
        '"map_code":' .. jopt(code),
        '"started_at":' .. string.format("%d", startedAt or 0),
        '"lines":[' .. table.concat(out, ",") .. "]",
    }, ",") .. "}"
end

--------------------------------------------------------------------------------
-- State
--------------------------------------------------------------------------------

local ctx = nil          -- Chat.init's deps
local Commands = nil     -- Scripts/commands.lua, loaded by Chat.init
local suggest = { text = nil, list = {}, tab = nil, shown = 0 } -- the slash command list under the box
local rules = { open = false, channel = nil, agreed = nil, hooked = false } -- the rules panel
local drawSuggestions     -- set below the slash commands; close() clears the list
local W = nil            -- the widget
local nextWidgetTry = 0
local open = nil         -- "all" | "team" while the box is open
local openedAt = 0
local openKey = nil      -- the letter that opened the box, swallowed if it lands in it
local lastKey = {}       -- key -> time, against a bind firing twice
local gameUI = false     -- the game's own SetUIActive, as last set: the pause menu is up
local gateHooked = false
local lines = {}         -- shown lines { name, text, color, team?, at, system? }
local inbox = {}         -- host lines for a client, from the RPC hook
local says = {}          -- client lines for the host, from the RPC hook
local record = nil       -- the host's { lines, seen, dirty, nextWrite, startedAt }
local hinted = false
local dirty = true
local rowState = {}      -- row -> what it shows now (draw)

local function valid(o)
    local ok, v = pcall(function() return o and o:IsValid() end)
    return ok and v
end

local function setVisibility(w, v)
    pcall(function() w:SetVisibility(v) end)
end

local function setText(block, text)
    pcall(function() block:SetText(FText(text)) end)
end

--- The pause menu sets this gate when it opens and clears it when it
--- closes: the box stays shut while it is up.
local function gate()
    if gateHooked then return end
    gateHooked = pcall(RegisterHook, "/Script/BlamEngine.BlamInputProcessorLocalPlayerSubsystem:SetUIActive",
        function(_, b)
            local okB, v = pcall(function() return b:get() end)
            if okB then gameUI = v == true end
        end)
end

--- UI-only input with the box focused while typing, game input after.
--- Flushing drops keys held as the mode changes: W held when T opened the
--- box would otherwise walk on.
local function typing(on, focus)
    local pc = ctx.pc()
    if not pc then return end
    pcall(function()
        local wbl = StaticFindObject("/Script/UMG.Default__WidgetBlueprintLibrary")
        if on then
            wbl:SetInputMode_UIOnlyEx(pc, focus, 0, true)
        else
            wbl:SetInputMode_GameOnly(pc, true)
        end
    end)
end

--------------------------------------------------------------------------------
-- The widget
--------------------------------------------------------------------------------

local function ensureWidget()
    if valid(W) then return W end
    if ctx.now() < nextWidgetTry then return nil end
    nextWidgetTry = ctx.now() + 2
    W = ctx.createWidget(CLASS, 42)
    if not W then return nil end
    setVisibility(W, PASS)
    local fonts = { NormativePro = ctx.font("NormativePro") or false, Oxanium = ctx.font("Oxanium") or false }
    local function face(block, family, typeface, spacing)
        local font = fonts[family]
        if not font then return end
        pcall(function()
            local size = block.Font.Size
            block:SetFont({ FontObject = font, TypefaceFontName = FName(typeface), Size = size,
                LetterSpacing = spacing or 0, SkewAmount = 0, OutlineSettings = { OutlineSize = 0 } })
        end)
    end
    for i = 0, Chat.ROWS - 1 do
        face(W["ChatName" .. i], "NormativePro", "Bold")
        face(W["ChatText" .. i], "NormativePro", "Medium")
        face(W["ChatTag" .. i], "Oxanium", "Bold", 120)
    end
    face(W.ChatChannel, "Oxanium", "Bold", 160)
    face(W.ChatHint, "Oxanium", "Bold", 160)
    dirty = true
    ctx.log("chat widget up")
    return W
end

local function draw(t)
    if not valid(W) then return end
    local shown = {}
    for i = #lines, 1, -1 do
        local l = lines[i]
        local age = t - l.at
        if open or age < Chat.SHOW_SECONDS + Chat.FADE_SECONDS then
            table.insert(shown, 1, { l = l, alpha = open and 1 or math.min(1, (Chat.SHOW_SECONDS + Chat.FADE_SECONDS - age) / Chat.FADE_SECONDS) })
        end
        if #shown >= Chat.ROWS then break end
    end
    -- Each row is touched only when what it shows changes: a dozen engine
    -- calls a frame for nothing would add up.
    local first = Chat.ROWS - #shown
    for i = 0, Chat.ROWS - 1 do
        local row = W["ChatLine" .. i]
        local s = shown[i - first + 1]
        local state = rowState[i] or {}
        rowState[i] = state
        if s then
            local l = s.l
            if dirty or state.line ~= l then
                state.line = l
                setText(W["ChatName" .. i], l.system and "" or (l.name .. ":"))
                pcall(function() W["ChatName" .. i]:SetColorAndOpacity({ SpecifiedColor = l.color, ColorUseRule = 0 }) end)
                setText(W["ChatText" .. i], l.text)
                pcall(function() W["ChatText" .. i]:SetColorAndOpacity({ SpecifiedColor = l.system and GREY or WHITE, ColorUseRule = 0 }) end)
                setVisibility(W["ChatTag" .. i], l.channel == "team" and SHOWN or COLLAPSED)
                setVisibility(W["ChatName" .. i], l.system and COLLAPSED or SHOWN)
                state.avatar, state.nextAvatar = false, nil
            end
            -- The sender's hub avatar, round, as the feed and the board show
            -- it. MJOLNIRLobby may cache the picture after the line arrives,
            -- so a row without one asks again, once a second, for a while.
            if not state.avatar and not l.system and t >= (state.nextAvatar or 0) and t - l.at < 15 then
                state.nextAvatar = t + 1
                local tex = ctx.avatar and ctx.avatar(l.index)
                if tex then
                    state.avatar = true
                    pcall(function() W["ChatAvatar" .. i]:SetBrushFromTexture(tex, false) end)
                end
                setVisibility(W["ChatAvatar" .. i .. "Box"], tex and SHOWN or COLLAPSED)
            elseif l.system and state.avatar ~= nil then
                state.avatar = nil
                setVisibility(W["ChatAvatar" .. i .. "Box"], COLLAPSED)
            end
            if state.shown ~= true then
                state.shown = true
                setVisibility(row, SHOWN)
            end
            local alpha = math.floor(s.alpha * 50 + 0.5) / 50
            if state.alpha ~= alpha then
                state.alpha = alpha
                pcall(function() row:SetRenderOpacity(alpha) end)
            end
        elseif state.shown ~= false then
            state.shown, state.line, state.alpha = false, nil, nil
            setVisibility(row, COLLAPSED)
        end
    end
    dirty = false
end

local function push(l)
    l.at = l.at or ctx.now()
    lines[#lines + 1] = l
    while #lines > Chat.HISTORY do table.remove(lines, 1) end
    dirty = true
end

--------------------------------------------------------------------------------
-- Opening, sending, closing
--------------------------------------------------------------------------------

local function close()
    if not open then return end
    open = nil
    drawSuggestions("")
    suggest.text, suggest.tab = nil, nil
    if valid(W) then
        pcall(function() W.ChatInput:SetText(FText("")) end)
        setVisibility(W.ChatInputBar, COLLAPSED)
        setVisibility(W.ChatHint, COLLAPSED)
        pcall(function() W.ChatPanel:SetBrushColor({ R = 0.005, G = 0.018, B = 0.03, A = 0.0 }) end)
    end
    typing(false)
    dirty = true
end
Chat.close = close

--------------------------------------------------------------------------------
-- The chat rules (RULES)
--------------------------------------------------------------------------------

local function rulesFile()
    return ctx.dir .. "\\chat_rules.txt"
end

local function agreed()
    if rules.agreed == nil then
        local f = io.open(rulesFile(), "rb")
        local text = f and f:read("*a") or ""
        if f then f:close() end
        rules.agreed = tonumber(text:match("^%s*(%d+)")) == RULES.version
    end
    return rules.agreed
end

local function cursor(on)
    pcall(function() ctx.pc().bShowMouseCursor = on end)
end

local openBox -- below: agreeing opens the box the player asked for

local function hideRules()
    if not rules.open then return end
    rules.open = false
    if valid(W) then setVisibility(W.ChatRules, COLLAPSED) end
    cursor(false)
end

local function agree()
    if not rules.open then return end
    local channel = rules.channel
    local f = io.open(rulesFile(), "wb")
    if f then
        f:write(tostring(RULES.version), "\n")
        f:close()
    end
    rules.agreed = true
    hideRules()
    ctx.log("chat: rules agreed")
    openBox(channel, nil)
end

local function notNow()
    if not rules.open then return end
    hideRules()
    typing(false)
end

--- Clicks on the panel's buttons arrive through the widget's MJ_Event.
local function hookRules()
    if rules.hooked then return end
    rules.hooked = pcall(RegisterHook, CLASS .. ":MJ_Event", function(_, name)
        local okN, event = pcall(function() return name:get():ToString() end)
        if not okN then return end
        ExecuteInGameThread(function()
            if event == "chat_accept" then agree() elseif event == "chat_decline" then notNow() end
        end)
    end)
end

local function showRules(w, channel)
    hookRules()
    rules.open, rules.channel = true, channel
    setText(w.ChatRulesBody, RULES.body)
    setText(w.ChatRulesList, RULES.list)
    setText(w.ChatRulesNote, RULES.note)
    setVisibility(w.ChatRules, VISIBLE)
    -- The panel takes the keyboard (Enter agrees, Esc is not now) and shows
    -- the mouse for its buttons; the viewport ignores both meanwhile.
    typing(true, w.ChatRulesAccept)
    cursor(true)
end

openBox = function(channel, key)
    if open or rules.open or not ctx.match() or gameUI then return end
    local w = ensureWidget()
    if not w then return end
    if not agreed() then
        showRules(w, channel)
        return
    end
    gate()
    if channel == "team" and not ctx.teams() then channel = "all" end
    open, openedAt, openKey = channel, ctx.now(), key
    pcall(function() w.ChatInput:SetText(FText("")) end)
    setText(w.ChatChannel, channel == "team" and "TEAM" or "ALL")
    pcall(function() w.ChatChannel:SetColorAndOpacity({ SpecifiedColor = channel == "team" and ctx.teamColor() or ACCENT, ColorUseRule = 0 }) end)
    setVisibility(w.ChatInputBar, PASS)
    setVisibility(w.ChatHint, SHOWN)
    pcall(function() w.ChatPanel:SetBrushColor({ R = 0.005, G = 0.018, B = 0.03, A = 0.55 }) end)
    typing(true, w.ChatInput)
    pcall(function() w.ChatInput:SetKeyboardFocus() end)
    dirty = true
end

--- A line from someone on this machine, as the host takes it (`sender` is
--- the platform name, from the controller the line came in on).
local function hostTake(sender, channel, text, senderPc)
    if not record then return end
    local t = ctx.now()
    if not Chat.allow(record.seen, sender, t) then
        if senderPc then
            pcall(function() senderPc:ClientMessage(Chat.encodeLine({ channel = "all", name = "", index = -1,
                text = "(slow down: chat is limited to " .. Chat.RATE.count .. " lines in " .. Chat.RATE.seconds .. " s)" }),
                FName("MJOLNIR"), 0) end)
        end
        return
    end
    local seat = ctx.seatOf(sender) or {}
    if channel == "team" and not ctx.teams() then channel = "all" end
    local l = { channel = channel, team = seat.team, index = seat.index, name = seat.display or sender, text = text }
    if #record.lines < Chat.MAX_RECORD then
        record.lines[#record.lines + 1] = { t_ms = (t - record.startedAt) * 1000, index = seat.index or -1, name = sender,
            userId = seat.userId, display = seat.display, teamName = seat.teamName, channel = channel, text = text }
        record.dirty = true
    end
    local msg = Chat.encodeLine(l)
    local kind = FName("MJOLNIR")
    for _, pc in ipairs(ctx.controllers()) do
        local okN, name = pcall(function() return pc.PlayerState:GetPlayerName():ToString() end)
        local to = okN and ctx.seatOf(name) or {}
        if channel == "all" or to.team == seat.team then
            pcall(function() pc:ClientMessage(msg, kind, 0) end)
        end
    end
    if channel == "all" or ctx.localTeam() == seat.team then
        Chat.show(l)
    end
end

local function send()
    if not open or not valid(W) then return end
    local okT, raw = pcall(function() return W.ChatInput:GetText():ToString() end)
    local channel = open
    close()
    local text = Chat.clean(okT and raw or "")
    if text == "" then return end
    if Commands and Commands.parse(text) then
        Chat.command(text)
        return
    end
    if ctx.isHost() then
        hostTake(ctx.localName() or "Host", channel, text, nil)
    else
        local pc = ctx.pc()
        if pc then pcall(function() pc:ServerExecRPC(Chat.encodeSay(channel, text)) end) end
    end
end

--------------------------------------------------------------------------------
-- Slash commands (Scripts/commands.lua)
--------------------------------------------------------------------------------

local function systemLine(text)
    push({ text = text, color = GREY, system = true })
end

--- What the commands may do, on this machine.
local function commandCx(isHost)
    return {
        isHost = isHost,
        players = ctx.players,
        kick = function(name, ban) ctx.console("mjolnir_auto " .. (ban and "ban " or "kick ") .. name) end,
        unban = function(name) ctx.console("mjolnir_auto unban " .. name) end,
        blam = function(line) Commands.queueBlam(line) end,
        setBots = ctx.setBots,
        botCount = ctx.botCount,
        -- The result comes back a minute later, as system lines.
        bench = function() return ctx.bench(function(said) for _, l in ipairs(said) do systemLine(l) end end) end,
    }
end

--- A command on the host: from its own box (`pc` nil), or from a client's
--- RPC. The client's seat must be its own: a joiner reads index 0 (the
--- host's) for a few seconds after it is seated (docs/match_stats.md), and
--- /suicide on that index would kill the host.
local function hostCommand(sender, text, pc)
    local who = { name = sender, here = pc == nil }
    if who.here then
        who.index = ctx.localIndex()
    else
        if record and not Chat.allow(record.seen, "cmd:" .. sender, ctx.now()) then return end
        local seat = ctx.seatOf(sender)
        local okI, index = pcall(function() return pc.PlayerState.BlamPlayerStateComponent.BlamAbsolutePlayerIndex end)
        if seat and type(seat.index) == "number" and seat.index ~= ctx.localIndex() and okI and index == seat.index then
            who.index = seat.index
        end
    end
    local ok, answer = pcall(Commands.run, commandCx(who.here), who, text)
    if not ok then
        ctx.log("chat command: " .. tostring(answer))
        answer = { "That command failed." }
    end
    for _, line in ipairs(answer) do
        if who.here then
            systemLine(line)
        else
            pcall(function() pc:ClientMessage(Chat.encodeLine({ channel = "all", name = "", index = -1, text = line }),
                FName("MJOLNIR"), 0) end)
        end
    end
end

--- A "/" line from this machine's box. Never chat: not relayed, not
--- recorded.
function Chat.command(text)
    local name = Commands.parse(text)
    local c = Commands.find(name)
    if ctx.isHost() then
        hostCommand(ctx.localName() or "Host", text, nil)
    elseif c and c.here then
        for _, line in ipairs(Commands.run(commandCx(false), { here = false }, text)) do systemLine(line) end
    elseif c and c.who == "host" then
        systemLine("/" .. c.name .. " is for the host.")
    elseif not c then
        systemLine("Unknown command /" .. tostring(name) .. ". Type /help for the list.")
    else
        local pc = ctx.pc()
        if pc then pcall(function() pc:ServerExecRPC(Commands.PREFIX .. text) end) end
    end
end

--- The command list under the box, for the text typed so far.
drawSuggestions = function(text)
    if not (valid(W) and Commands) then return end
    if text ~= suggest.text then
        suggest.text = text
        local names = {}
        -- Every command that names a player names someone else.
        for _, p in ipairs(ctx.players()) do
            if p.index ~= ctx.localIndex() then names[#names + 1] = p.display or p.name end
        end
        table.sort(names)
        -- Tab cycling keeps its list while the text is its own completion.
        if not (suggest.tab and suggest.tab.text == text) then
            suggest.list, suggest.tab = Commands.suggest(text or "", ctx.isHost(), names), nil
        end
    end
    local list = suggest.list
    local n = math.min(#list, Commands.ROWS)
    for i = 0, Commands.ROWS - 1 do
        local item = list[i + 1]
        if item then
            setText(W["ChatSugName" .. i], item.label)
            setText(W["ChatSugHelp" .. i], item.help or "")
            local on = suggest.tab and suggest.tab.i == i + 1
            pcall(function() W["ChatSugRow" .. i]:SetBrushColor(on and { R = 0.12, G = 0.32, B = 0.43, A = 0.9 }
                or { R = 0, G = 0, B = 0, A = 0 }) end)
            setVisibility(W["ChatSugRow" .. i], SHOWN)
        elseif i < suggest.shown then
            setVisibility(W["ChatSugRow" .. i], COLLAPSED)
        end
    end
    if (n > 0) ~= (suggest.shown > 0) then setVisibility(W.ChatSuggest, n > 0 and PASS or COLLAPSED) end
    suggest.shown = n
end

--- Tab: complete the highlighted suggestion; again, the next one.
local function complete()
    if not (open and valid(W)) or #suggest.list == 0 then return end
    local tab = suggest.tab
    local i = tab and (tab.i % #suggest.list) + 1 or 1
    local text = suggest.list[i].complete
    -- "/kick " wants a player next: the players are the new list. A finished
    -- completion keeps its list, so Tab again moves to the next one.
    suggest.tab = text:sub(-1) ~= " " and { i = i, text = text } or nil
    pcall(function() W.ChatInput:SetText(FText(text)) end)
    suggest.text = nil
end

--- A line to show here (from the host, or the host's own).
function Chat.show(l)
    local color = ctx.colorOf(l.index, l.team)
    push({ name = l.name ~= "" and l.name or nil, index = l.index, text = l.text, color = color, channel = l.channel,
        system = (l.name == nil or l.name == "") })
end

--------------------------------------------------------------------------------
-- The RPC hooks call these (off the game thread's work: they only queue)
--------------------------------------------------------------------------------

--- ServerExecRPC on the host; true when `text` was a chat line or a
--- command.
function Chat.heardSay(pc, text)
    if type(text) ~= "string" then return false end
    local isSay = text:sub(1, #Chat.SAY) == Chat.SAY
    local isCmd = Commands ~= nil and text:sub(1, #Commands.PREFIX) == Commands.PREFIX
    if not (isSay or isCmd) then return false end
    if #says < 32 then says[#says + 1] = { pc = pc, text = text, cmd = isCmd } end
    return true
end

--- ClientMessage on a client; true when `text` was a chat line.
function Chat.heardLine(text)
    if type(text) ~= "string" or text:sub(1, #Chat.LINE) ~= Chat.LINE then return false end
    if #inbox < 32 then inbox[#inbox + 1] = text end
    return true
end

--------------------------------------------------------------------------------
-- Per poll and per frame
--------------------------------------------------------------------------------

local function writeRecord(force)
    if not (record and record.id) then return end
    if not force and (not record.dirty or ctx.now() < record.nextWrite) then return end
    record.dirty, record.nextWrite = false, ctx.now() + 5
    if #record.lines == 0 then return end
    local f = io.open(ctx.dir .. "\\chat_" .. record.id .. ".json", "wb")
    if not f then return end
    f:write(Chat.encodeRecord(record.id, record.code, record.startedUnix, record.lines))
    f:close()
end

--- Each HUD poll, in a match.
function Chat.tick(match)
    gate()
    if ctx.isHost() then
        if not record then
            record = { lines = {}, seen = {}, dirty = false, nextWrite = 0, startedAt = match.startedAt,
                startedUnix = os.time(), code = match.code }
        end
        record.id = record.id or ctx.matchId()
        local heard = says
        says = {}
        for _, s in ipairs(heard) do
            local okN, sender = pcall(function() return s.pc.PlayerState:GetPlayerName():ToString() end)
            if okN and sender and sender ~= "" then
                if s.cmd then
                    local text = Chat.clean(s.text:sub(#Commands.PREFIX + 1))
                    if Commands.parse(text) then hostCommand(sender, text, s.pc) end
                else
                    local channel, text = Chat.decodeSay(s.text)
                    if channel then hostTake(sender, channel, text, s.pc) end
                end
            end
        end
        inbox = {}
        writeRecord(false)
        if Commands then
            Commands.prepareBlam()
            Commands.pumpBlam()
        end
    else
        says = {}
        local heard = inbox
        inbox = {}
        for _, text in ipairs(heard) do
            local l = Chat.decodeLine(text)
            if l and l.text ~= "" then Chat.show(l) end
        end
    end
    if not hinted then
        hinted = true
        push({ text = "Press T to chat" .. (ctx.teams() and ", Y for team chat" or ""), color = GREY, system = true })
    end
    ensureWidget()
    -- The pause menu came up over the box (ESC opens it too): the box goes.
    if open and gameUI then close() end
    if rules.open and gameUI then notNow() end
    if ctx.hidden() and valid(W) then setVisibility(W, COLLAPSED) elseif valid(W) then setVisibility(W, PASS) end
end

--- Each frame.
function Chat.frame(t)
    if open and valid(W) then
        local okT, s = pcall(function() return W.ChatInput:GetText():ToString() end)
        if okT and s then
            -- The letter that opened the box arrives in it a moment later.
            -- Only when it is all there is, and only just after opening: the
            -- letter does not always arrive (the input mode changes under
            -- it), and then a quick first "t" of the message is the player's
            -- ("test" came out "est", 2026-10-17).
            if openKey and t - openedAt < 0.15 and s:lower() == openKey then
                pcall(function() W.ChatInput:SetText(FText("")) end)
                openKey = nil
            elseif openKey and (t - openedAt >= 0.15 or #s > 1) then
                openKey = nil
            elseif #s > Chat.MAX_BYTES then
                pcall(function() W.ChatInput:SetText(FText(Chat.clean(s))) end)
            end
            drawSuggestions(s)
        end
        -- Tab moves Slate's focus on from a text box: take it back.
        pcall(function()
            if not W.ChatInput:HasKeyboardFocus() then W.ChatInput:SetKeyboardFocus() end
        end)
    end
    draw(t)
end

--- The match is over or left: close the box, write and queue the record.
function Chat.finish()
    close()
    if rules.open then
        hideRules()
        typing(false)
    end
    if record then
        record.id = record.id or ctx.matchId()
        writeRecord(true)
        if record.id and #record.lines > 0 then
            ctx.queue("chat", record.id)
            ctx.log(string.format("chat: %d line(s) of %s queued for the hub", #record.lines, record.id))
        end
    end
    record, lines, inbox, says = nil, {}, {}, {}
    hinted = false
    W, rowState = nil, {}
    dirty = true
end

--------------------------------------------------------------------------------
-- Keys
--------------------------------------------------------------------------------

local function once(key, fn)
    return function()
        local t = ctx.now()
        if lastKey[key] and t - lastKey[key] < 0.2 then return end
        lastKey[key] = t
        local ok, err = pcall(fn)
        if not ok then ctx.log("chat key: " .. tostring(err)) end
    end
end

--- deps: { dir, log, now, pc, createWidget, font, match, isHost, teams,
--- teamColor, localTeam, localName, seatOf, colorOf, controllers, matchId,
--- queue, hidden, players, localIndex, console }.
function Chat.init(deps)
    ctx = deps
    local okC, loaded = pcall(dofile, deps.dir .. "\\Scripts\\commands.lua")
    if okC and type(loaded) == "table" then
        Commands = loaded
        Commands.initBlam(deps.dir:match("^(.*)\\[^\\]*$") or deps.dir)
    else
        deps.log("chat: slash commands not loaded: " .. tostring(loaded))
    end
    if not (Key and RegisterKeyBind) then return end
    -- Synchronous binds: their callbacks run on the game thread
    -- (MJOLNIRFlyCam). A bind fires whatever has focus, so each checks the
    -- box first.
    local binds = {
        { Key.T, once("T", function() openBox("all", "t") end) },
        { Key.Y, once("Y", function() openBox("team", "y") end) },
        { Key.HOME, once("HOME", function() openBox("all", nil) end) },
        { Key.RETURN, once("RETURN", function() if open then send() elseif rules.open then agree() end end) },
        { Key.ESCAPE, once("ESCAPE", function() if open then close() elseif rules.open then notNow() end end) },
        { Key.TAB, once("TAB", function() if open then complete() end end) },
    }
    for _, b in ipairs(binds) do
        if b[1] then pcall(RegisterKeyBind, b[1], {}, b[2]) end
    end
end

Chat.SHOWN, Chat.HIDDEN, Chat.VISIBLE = SHOWN, HIDDEN, VISIBLE

return Chat

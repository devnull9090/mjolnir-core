-- MJOLNIR HUD: match chat (docs/multiplayer_hud.md, "Chat").
--
-- T opens all chat, Y team chat (all chat in free for all), Home (the game's
-- own chat key, whose party chat never connects in our games) all chat.
-- ENTER sends, ESC cancels. While the box is open the Blam simulation does
-- not read the keyboard: the pause menu's own gate,
-- BlamInputProcessorLocalPlayerSubsystem:SetUIActive, is set for as long as
-- the box is open and given back as the game last left it.
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
local W = nil            -- the widget
local nextWidgetTry = 0
local open = nil         -- "all" | "team" while the box is open
local openedAt = 0
local openKey = nil      -- the letter that opened the box, swallowed if it lands in it
local lastKey = {}       -- key -> time, against a bind firing twice
local gameUI = false     -- the game's own SetUIActive, as last set
local ours = false       -- our SetUIActive(true) is in force
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

local function gate()
    if gateHooked then return end
    gateHooked = pcall(RegisterHook, "/Script/BlamEngine.BlamInputProcessorLocalPlayerSubsystem:SetUIActive",
        function(_, b)
            local okB, v = pcall(function() return b:get() end)
            -- Ours are made with `ours` already set the way they leave it.
            if okB and not Chat.settingGate then gameUI = v == true end
        end)
end

local function setGate(active)
    local sub = FindFirstOf("BlamInputProcessorLocalPlayerSubsystem")
    if not valid(sub) then return end
    Chat.settingGate = true
    pcall(function() sub:SetUIActive(active) end)
    Chat.settingGate = false
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
    if valid(W) then
        pcall(function() W.ChatInput:SetText(FText("")) end)
        setVisibility(W.ChatInputBar, COLLAPSED)
        setVisibility(W.ChatHint, COLLAPSED)
        pcall(function() W.ChatPanel:SetBrushColor({ R = 0.005, G = 0.018, B = 0.03, A = 0.0 }) end)
    end
    if ours then
        ours = false
        -- Give the gate back as the game last left it: the pause menu may
        -- have opened over the box.
        setGate(gameUI)
    end
    pcall(function() StaticFindObject("/Script/UMG.Default__WidgetBlueprintLibrary"):SetFocusToGameViewport() end)
    dirty = true
end
Chat.close = close

local function openBox(channel, key)
    if open or not ctx.match() or gameUI then return end
    local w = ensureWidget()
    if not w then return end
    gate()
    if channel == "team" and not ctx.teams() then channel = "all" end
    open, openedAt, openKey = channel, ctx.now(), key
    setGate(true)
    ours = true
    pcall(function() w.ChatInput:SetText(FText("")) end)
    setText(w.ChatChannel, channel == "team" and "TEAM" or "ALL")
    pcall(function() w.ChatChannel:SetColorAndOpacity({ SpecifiedColor = channel == "team" and ctx.teamColor() or ACCENT, ColorUseRule = 0 }) end)
    setVisibility(w.ChatInputBar, PASS)
    setVisibility(w.ChatHint, SHOWN)
    pcall(function() w.ChatPanel:SetBrushColor({ R = 0.005, G = 0.018, B = 0.03, A = 0.55 }) end)
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
    if ctx.isHost() then
        hostTake(ctx.localName() or "Host", channel, text, nil)
    else
        local pc = ctx.pc()
        if pc then pcall(function() pc:ServerExecRPC(Chat.encodeSay(channel, text)) end) end
    end
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

--- ServerExecRPC on the host; true when `text` was a chat line.
function Chat.heardSay(pc, text)
    if type(text) ~= "string" or text:sub(1, #Chat.SAY) ~= Chat.SAY then return false end
    if #says < 32 then says[#says + 1] = { pc = pc, text = text } end
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
            local channel, text = Chat.decodeSay(s.text)
            local okN, sender = pcall(function() return s.pc.PlayerState:GetPlayerName():ToString() end)
            if channel and okN and sender and sender ~= "" then hostTake(sender, channel, text, s.pc) end
        end
        inbox = {}
        writeRecord(false)
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
    if ctx.hidden() and valid(W) then setVisibility(W, COLLAPSED) elseif valid(W) then setVisibility(W, PASS) end
end

--- Each frame.
function Chat.frame(t)
    if open and valid(W) then
        local okT, s = pcall(function() return W.ChatInput:GetText():ToString() end)
        if okT and s then
            -- The letter that opened the box arrives in it a moment later.
            if openKey and t - openedAt < 0.25 and s:sub(1, 1):lower() == openKey then
                pcall(function() W.ChatInput:SetText(FText(s:sub(2))) end)
                openKey = nil
            elseif #s > Chat.MAX_BYTES then
                pcall(function() W.ChatInput:SetText(FText(Chat.clean(s))) end)
            end
        end
    end
    draw(t)
end

--- The match is over or left: close the box, write and queue the record.
function Chat.finish()
    close()
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
--- queue, hidden }.
function Chat.init(deps)
    ctx = deps
    if not (Key and RegisterKeyBind) then return end
    -- Synchronous binds: their callbacks run on the game thread
    -- (MJOLNIRFlyCam). A bind fires whatever has focus, so each checks the
    -- box first.
    local binds = {
        { Key.T, once("T", function() openBox("all", "t") end) },
        { Key.Y, once("Y", function() openBox("team", "y") end) },
        { Key.HOME, once("HOME", function() openBox("all", nil) end) },
        { Key.RETURN, once("RETURN", function() if open then send() end end) },
        { Key.ESCAPE, once("ESCAPE", function() if open then close() end end) },
    }
    for _, b in ipairs(binds) do
        if b[1] then pcall(RegisterKeyBind, b[1], {}, b[2]) end
    end
end

Chat.SHOWN, Chat.HIDDEN, Chat.VISIBLE = SHOWN, HIDDEN, VISIBLE

return Chat

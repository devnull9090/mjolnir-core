--- The level's sounds at the player's own levels (docs/sound_mixer.md).
---
--- Every sound the loader plays is listed once, by its tag (`source`: the
--- Halo 2 or CE sound tag path; a wave's own path when a level was built
--- before sources were written): the background loops, the sound scenery's
--- loops, Halo 2's detail sounds, and the doors' and gears' one-shots.
--- `factor(key)` is what the loader multiplies a sound's volume by: the
--- sound's own level times ALL SOUNDS, in decibels. Each map's levels are
--- kept on this PC (Saved/MJOLNIR_SoundMix_<map>.json) and read again when
--- the map loads.
---
--- `/sounds` in chat (MJOLNIRHud) or the console's `mjolnir_sounds` opens
--- WBP_MJOLNIRSoundMixer (build_mjolnir_ui.py) over the match: a slider a
--- sound, a dot on the ones heard from where the player stands.
---
--- Why a loop: the panel's sliders send no events Lua can take (a cooked
--- binding passes no value), so they are read 10 times a second, and only
--- while the panel is open; shut, the loop sleeps a second at a time and
--- does nothing. A read allocates nothing; text is made only when a level
--- changes.
local Mixer = {}

Mixer.CLASS = "/Game/MJOLNIR/UI/WBP_MJOLNIRSoundMixer.WBP_MJOLNIRSoundMixer_C"
Mixer.ROWS = 12 -- build_mjolnir_ui.py MIXER_ROWS
Mixer.DB_MIN = -24
Mixer.DB_MAX = 12
Mixer.MUTE = -99
Mixer.MASTER = "*"
Mixer.OPEN_MS = 100
Mixer.SHUT_MS = 1000
Mixer.HEARD_S = 0.5
Mixer.ZORDER = 60

local VISIBLE, COLLAPSED, HIDDEN, PASS = 0, 1, 2, 3

--- dB -> the slider's 0..1: the left end mutes, then DB_MIN..DB_MAX.
local function toSlider(db)
    if db <= Mixer.MUTE then return 0.0 end
    return 0.02 + 0.98 * (db - Mixer.DB_MIN) / (Mixer.DB_MAX - Mixer.DB_MIN)
end

local function fromSlider(v)
    if v < 0.01 then return Mixer.MUTE end
    local db = Mixer.DB_MIN + (v - 0.02) / 0.98 * (Mixer.DB_MAX - Mixer.DB_MIN)
    return math.max(Mixer.DB_MIN, math.min(Mixer.DB_MAX, math.floor(db + 0.5)))
end

local function words(db)
    if db <= Mixer.MUTE then return "MUTED" end
    if db == 0 then return "0 dB" end
    return string.format("%+d dB", db)
end

local function linear(db)
    if db <= Mixer.MUTE then return 0.0 end
    return 10 ^ (db / 20)
end

--- A tag path's name for a row: its last folder that is not "details" or
--- "loop", upper case, spaces for underscores ("...\\waves2\\details\\waves2"
--- -> "WAVES2"); with `parent`, the folder above it too.
local function nameOf(key, parent)
    local parts = {}
    local path = tostring(key)
    if path:find("^/") then
        -- A wave's object path (no source): its asset name.
        path = path:match("%.([^%.]+)$") or path
        path = path:gsub("^sound_", "")
        return (path:gsub("_", " ")):upper()
    end
    for p in path:gmatch("[^\\/]+") do
        if p ~= "details" and p ~= "loop" then parts[#parts + 1] = p end
    end
    local leaf = parts[#parts] or path
    local name = leaf
    if parent and #parts >= 2 and parts[#parts - 1] ~= leaf then name = parts[#parts - 1] .. " / " .. leaf end
    return (name:gsub("_", " ")):upper()
end

--- A tiny writer for the levels file: { map, levels = { key = dB } }.
local function quote(s)
    return '"' .. tostring(s):gsub('[%c"\\]', function(c)
        if c == '"' then return '\\"' elseif c == "\\" then return "\\\\" end
        return string.format("\\u%04x", c:byte())
    end) .. '"'
end

--- deps: Log, Current, Json, getWorld, getPlayerController, getCamera,
--- applyMix (puts the loops at their new levels), retainUIClass.
function Mixer.new(d)
    local self = { items = {}, levels = {}, map = nil, page = 1, open = false, rows = {},
        factors = {}, heardAt = -100, hooked = false }

    local localAppData = os.getenv("LOCALAPPDATA")

    local function filePath(map)
        if not (localAppData and map) then return nil end
        return localAppData .. "\\Meteorite\\Saved\\MJOLNIR_SoundMix_" .. map .. ".json"
    end

    local function load(map)
        self.levels = {}
        local path = filePath(map)
        local f = path and io.open(path, "rb")
        if not f then return end
        local text = f:read("*a")
        f:close()
        local ok, data = pcall(d.Json.decode, text)
        if ok and type(data) == "table" and type(data.levels) == "table" then
            for k, v in pairs(data.levels) do
                if type(k) == "string" and type(v) == "number" then self.levels[k] = v end
            end
        end
    end

    local function save()
        if not self.dirty then return end
        local path = filePath(self.map)
        if not path then return end
        local keys = {}
        for k, v in pairs(self.levels) do
            if v ~= 0 then keys[#keys + 1] = k end
        end
        table.sort(keys)
        local out = { "{\n  \"version\": 1,\n  \"map\": ", quote(self.map), ",\n  \"levels\": {" }
        for i, k in ipairs(keys) do
            out[#out + 1] = string.format("%s\n    %s: %d", i > 1 and "," or "", quote(k), self.levels[k])
        end
        out[#out + 1] = (#keys > 0 and "\n  " or "") .. "}\n}\n"
        local f = io.open(path, "wb")
        if f then
            f:write(table.concat(out))
            f:close()
            self.dirty = false
            d.Log(string.format("sound mix: %d level(s) kept for %s", #keys, self.map))
        end
    end

    --- A new world: its map's levels (read before its sounds spawn, which
    --- ask factor first). The map is the world's name ("/Game/.../ZAN/ZAN").
    local function sync()
        local world = d.Current.worldName
        if self.world == world then return end
        self.world = world
        self.reset(world and tostring(world):match("([^/%.]+)$") or nil)
    end

    --- What multiplies the sound `key`'s volume.
    function self.factor(key)
        sync()
        local f = self.factors[key or ""]
        if f then return f end
        f = linear(self.levels[Mixer.MASTER] or 0) * linear(key and self.levels[key] or 0)
        self.factors[key or ""] = f
        return f
    end

    --- Every sound of the level, once a tag: what kind it is, how many play,
    --- and where it can be heard.
    local function build()
        local items, byKey = {}, {}
        local origin = (d.Current.level and d.Current.level.canvas or {}).origin or { 0, 0, 0 }
        local function item(key)
            local it = byKey[key]
            if not it then
                it = { key = key, placed = 0, places = {}, sets = {}, kinds = {} }
                byKey[key] = it
                items[#items + 1] = it
            end
            return it
        end
        local function place(it, pos, reach, absolute)
            local o = absolute and { 0, 0, 0 } or origin
            it.places[#it.places + 1] = { o[1] + pos[1], o[2] + pos[2], o[3] + pos[3], reach * reach }
        end
        local env = d.Current.level and d.Current.level.environment
        local sounds = type(env) == "table" and type(env.sounds) == "table" and env.sounds or {}
        for _, s in ipairs(type(sounds.background) == "table" and sounds.background or {}) do
            local it = item(s.source or s.wave)
            it.kinds.bed = true
            if s.set ~= nil then it.sets[s.set] = true else it.always = true end
        end
        for _, s in ipairs(type(sounds.emitters) == "table" and sounds.emitters or {}) do
            local it = item(s.source or s.wave)
            it.placed = it.placed + 1
            if type(s.pos) == "table" then place(it, s.pos, (s.inner or 150) + (s.falloff or 600)) end
        end
        for _, s in ipairs(type(sounds.details) == "table" and sounds.details or {}) do
            local it = item(s.source or (type(s.waves) == "table" and s.waves[1]) or "?")
            it.kinds.detail = true
            if type(s.period) == "table" then it.period = s.period end
            if type(s.pos) == "table" then
                place(it, s.pos, (s.inner or 150) + (s.falloff or 600))
            elseif s.set ~= nil then
                it.sets[s.set] = true
            else
                it.always = true
            end
        end
        local level = d.Current.level or {}
        for _, g in ipairs(type(level.gears) == "table" and level.gears or {}) do
            for _, e in ipairs(type(g.motion) == "table" and type(g.motion.events) == "table" and g.motion.events or {}) do
                item(e.source or e.wave).kinds.machine = true
            end
        end
        for _, door in ipairs(type(level.doors) == "table" and level.doors or {}) do
            for event, group in pairs(type(door.sounds) == "table" and door.sounds or {}) do
                if type(group) == "table" and type(group.paths) == "table" and group.paths[1] then
                    local it = item(group.source or group.paths[1])
                    it.kinds.door = true
                    -- Named by the door's tag and what it marks ("HOUSE GATE
                    -- OPEN"): a level built before door sounds carried their
                    -- tag has only the wave's long asset name.
                    if not group.source and door.asset then
                        it.given = nameOf(door.asset) .. " " .. tostring(event):upper()
                    end
                    if type(door.at_cm) == "table" then place(it, door.at_cm, 3000, true) end
                end
            end
        end
        -- Names; a name two tags share gets its folder too.
        local seen = {}
        for _, it in ipairs(items) do
            it.name = it.given or nameOf(it.key)
            seen[it.name] = (seen[it.name] or 0) + 1
        end
        for _, it in ipairs(items) do
            if seen[it.name] > 1 and not it.given then it.name = nameOf(it.key, true) end
            local kind = {}
            if it.kinds.bed then kind[#kind + 1] = "BACKGROUND" end
            if it.placed > 0 then kind[#kind + 1] = it.placed == 1 and "1 PLACE" or (it.placed .. " PLACES") end
            if it.kinds.detail then
                local p = it.period
                kind[#kind + 1] = p and string.format("NOW AND THEN, %d-%d S", math.floor(p[1] + 0.5), math.floor(p[2] + 0.5))
                    or "NOW AND THEN"
            end
            if it.kinds.machine then kind[#kind + 1] = "MACHINE" end
            if it.kinds.door then kind[#kind + 1] = "DOOR" end
            it.kind = table.concat(kind, "  /  ")
        end
        table.sort(items, function(a, b) return a.name < b.name end)
        table.insert(items, 1, { key = Mixer.MASTER, name = "ALL SOUNDS", kind = "EVERY SOUND BELOW, AS ONE",
            master = true, places = {}, sets = {} })
        return items
    end

    --- Whether `it` is heard from `cam` (positions) or in the zone's set.
    local function heard(it, cam)
        if it.master then return false end
        if it.always then return true end
        if d.Current.soundSet ~= nil and it.sets[d.Current.soundSet] then return true end
        if next(it.sets) ~= nil and d.Current.soundSet == nil then return true end
        if cam then
            for _, p in ipairs(it.places) do
                local dx, dy, dz = cam.X - p[1], cam.Y - p[2], cam.Z - p[3]
                if dx * dx + dy * dy + dz * dz < p[4] then return true end
            end
        end
        return false
    end

    local input -- below: UI input while the panel is open

    --- Called as the level changes: the new level's sounds and levels.
    function self.reset(map)
        -- The old world's panel is gone with it: a handle kept across the
        -- travel may point at freed memory, so it is dropped unread.
        if self.open then input(false) end
        self.open, self.w, self.rows = false, nil, {}
        save()
        self.map, self.items, self.page, self.factors = map, {}, 1, {}
        load(map)
        self.built = false
    end

    local function items()
        if not self.built or self.level ~= d.Current.level then
            self.items, self.built, self.level = build(), true, d.Current.level
        end
        return self.items
    end

    local function setText(w, text)
        pcall(function() w:SetText(FText(text)) end)
    end

    local function loadClass()
        local ok, cls = pcall(function()
            local ksl = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
            return ksl:LoadClassAsset_Blocking(ksl:Conv_SoftClassPathToSoftClassRef(ksl:MakeSoftClassPath(Mixer.CLASS)))
        end)
        if not (ok and cls and cls:IsValid()) then return nil end
        return d.retainUIClass(Mixer.CLASS, cls)
    end

    local onEvent

    --- The panel, made once a world (the viewport keeps it; it is hidden,
    --- never removed: removing such a widget hung the game once).
    local function widget()
        if self.w and self.w:IsValid() then return self.w end
        self.w = nil
        local cls = loadClass()
        if not cls then
            d.Log("sound mix: " .. Mixer.CLASS .. " is not installed (an older pakchunk984-MJOLNIRUI)")
            return nil
        end
        if not self.hooked then
            self.hooked = pcall(RegisterHook, Mixer.CLASS .. ":MJ_Event", function(_, name)
                local ok, event = pcall(function() return name:get():ToString() end)
                if ok then ExecuteInGameThread(function() pcall(onEvent, event) end) end
            end)
        end
        local pc = d.getPlayerController()
        local ok, w = pcall(function()
            local wbl = StaticFindObject("/Script/UMG.Default__WidgetBlueprintLibrary")
            return wbl:Create(pc, cls, pc)
        end)
        if not (ok and w and w:IsValid()) then return nil end
        pcall(function()
            w:AddToViewport(Mixer.ZORDER)
            w:SetVisibility(COLLAPSED)
        end)
        self.w = w
        self.rows = {}
        for i = 0, Mixer.ROWS - 1 do
            local slider = w["Row" .. i .. "Slider"]
            self.rows[i + 1] = { box = w["Row" .. i], name = w["Row" .. i .. "Name"], kind = w["Row" .. i .. "Kind"],
                slider = slider, getValue = slider.GetValue, value = w["Row" .. i .. "Value"],
                dot = w["Row" .. i .. "Heard"] }
        end
        return w
    end

    local function pages()
        return math.max(1, math.ceil(#items() / Mixer.ROWS))
    end

    --- The rows of this page.
    local function fill()
        local w = self.w
        local list = items()
        self.page = math.max(1, math.min(self.page, pages()))
        for i, row in ipairs(self.rows) do
            local it = list[(self.page - 1) * Mixer.ROWS + i]
            row.item = it
            if it then
                local db = self.levels[it.key] or 0
                row.v = toSlider(db)
                setText(row.name, it.name)
                setText(row.kind, it.kind or "")
                setText(row.value, words(db))
                pcall(function()
                    row.slider:SetValue(row.v)
                    row.box:SetVisibility(VISIBLE)
                end)
            else
                pcall(function() row.box:SetVisibility(COLLAPSED) end)
            end
        end
        setText(w.MapLine, string.format("%s  /  %d SOUND%s  /  YOUR LEVELS ARE KEPT FOR THIS MAP ON THIS PC",
            tostring(self.map or "?"), #list - 1, #list == 2 and "" or "S"))
        setText(w.PageLine, string.format("%d / %d", self.page, pages()))
        pcall(function()
            w.Prev:SetIsEnabled(self.page > 1)
            w.Next:SetIsEnabled(self.page < pages())
        end)
        setText(w.Hint, "\u{25CF} marks what you can hear from where you stand. Slide a sound to the left end to "
            .. "mute it. DONE, or /sounds again, closes this.")
        self.heardAt = -100
    end

    input = function(on)
        local pc = d.getPlayerController()
        if not pc then return end
        pcall(function()
            local wbl = StaticFindObject("/Script/UMG.Default__WidgetBlueprintLibrary")
            if on then
                wbl:SetInputMode_UIOnlyEx(pc, self.w, 0, true)
            else
                wbl:SetInputMode_GameOnly(pc, true)
            end
            pc.bShowMouseCursor = on
        end)
    end

    function self.show()
        sync()
        if not d.Current.level then
            d.Log("sound mix: no level loaded")
            return
        end
        local w = widget()
        if not w then return end
        fill()
        pcall(function() w:SetVisibility(VISIBLE) end)
        input(true)
        self.open = true
        d.Log(string.format("sound mix: open, %d sound(s)", #items() - 1))
    end

    function self.close()
        if self.w and self.w:IsValid() then pcall(function() self.w:SetVisibility(COLLAPSED) end) end
        if self.open then input(false) end
        self.open = false
        save()
    end

    function self.toggle()
        if self.open then self.close() else self.show() end
    end

    onEvent = function(event)
        if event == "done" then
            self.close()
        elseif event == "prev" or event == "next" then
            self.page = self.page + (event == "next" and 1 or -1)
            fill()
        elseif event == "reset" then
            self.levels, self.factors, self.dirty = {}, {}, true
            d.applyMix()
            fill()
        end
    end

    --- While open: read the sliders, apply what moved, mark what is heard.
    --- Returns the wait in ms.
    function self.tick(now)
        sync()
        if not self.open then return Mixer.SHUT_MS end
        if not (self.w and self.w:IsValid()) then
            self.open = false
            input(false)
            return Mixer.SHUT_MS
        end
        local moved = false
        for _, row in ipairs(self.rows) do
            local it = row.item
            if it then
                local ok, v = pcall(row.getValue, row.slider)
                if ok and type(v) == "number" and math.abs(v - row.v) > 0.004 then
                    row.v = v
                    local db = fromSlider(v)
                    if db ~= (self.levels[it.key] or 0) then
                        self.levels[it.key] = db
                        setText(row.value, words(db))
                        moved = true
                    end
                end
            end
        end
        if moved then
            self.factors, self.dirty = {}, true
            d.applyMix()
        end
        if now - self.heardAt >= Mixer.HEARD_S then
            self.heardAt = now
            local cam = d.getCamera()
            for _, row in ipairs(self.rows) do
                if row.item then
                    local on = heard(row.item, cam)
                    if on ~= row.heard then
                        row.heard = on
                        pcall(function() row.dot:SetVisibility(on and PASS or HIDDEN) end)
                    end
                end
            end
        end
        return Mixer.OPEN_MS
    end

    return self
end

-- For tools/tests: the level <-> slider mapping and names.
Mixer.toSlider, Mixer.fromSlider, Mixer.words, Mixer.nameOf = toSlider, fromSlider, words, nameOf

return Mixer

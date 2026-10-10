-- MJOLNIR Lobby: maps from the hub, while the game runs
-- (docs/live_map_install.md).
--
-- A map this PC does not have is installed without a restart, in four steps:
--
--   1. The MJOLNIR launcher installs it, run without a window by the native
--      half (`--install-map <CODE>`): the hub's hash, the platform and author
--      signatures, the same cache, state and file names as its Maps tab. It
--      reports to native\map_install_progress.json, which this polls.
--   2. Its new containers are mounted the way the engine mounts a chunk it
--      downloads (MJOLNIRLevelLoader's native half, mjolnir_mount_paks).
--   3. Its scenario is registered in memory: a DT_Scenarios row, a campaign
--      list entry and the frontend levels cache entry, the records the
--      registration container (pakchunk996) gives the maps it was cooked
--      with (mjolnir_scenario_add). The next launch cooks it in.
--   4. The menus see it at once: the launcher rewrote MJOLNIRMaps\maps.json,
--      which they read every time.
--
-- It also keeps the hub's map listings (title, author, rating, size, the
-- screenshot) for the menus, and each map's screenshot on disk in
-- MJOLNIRMaps\_covers, read into a texture when a screen shows it.

local MapLive = {}

local Json, Games, log, nativeDir, loaderNative, mapsDir, worldContext

local SCENARIOS = "/Game/Blueprints/Campaign/DT_Scenarios.DT_Scenarios"
local CAMPAIGN = "/Game/Blueprints/Campaign/DA_FirstPlayableCampaign.DA_FirstPlayableCampaign"
-- The shipped mission a live row is cloned from, as the cooked ones are
-- (blam_pack::scenario::register): its preview, insertion points and unlock tag.
local TEMPLATE = "B40"
local CATALOG_SECONDS = 600
local RETRY_SECONDS = 30
local POLL_MS = 200
local STALL_SECONDS = 120     -- no word from the launcher for this long: failed

local catalog = { byCode = {}, at = nil, loading = false, waiting = {} }
local fetching = {}            -- code -> callbacks waiting on its screenshot
local textures = {}            -- code -> { name = texture path, file = cover id }
local registered = {}          -- code -> true once its row is in this session
local job = nil                -- the install in flight

local function readFile(path)
    local f = io.open(path, "rb")
    if not f then return nil end
    local data = f:read("*a")
    f:close()
    return data
end

local function writeFile(path, text)
    local f = io.open(path, "wb")
    if not f then return false end
    f:write(text)
    f:close()
    return true
end

local function exists(path)
    local f = io.open(path, "rb")
    if f then f:close() end
    return f ~= nil
end

local function call(dll, name)
    local fn = package and package.loadlib and package.loadlib(dll, name)
    if not fn then return false, "the native half is not installed" end
    local ok, err = pcall(fn)
    if not ok then return false, tostring(err) end
    return true
end

local function valid(o)
    local ok, v = pcall(function() return o and o:IsValid() end)
    return ok and v
end

-------------------------------------------------------------------------------
-- The hub's listings
-------------------------------------------------------------------------------

--- Fetch every published map's listing (GET /maps), at most once per
--- CATALOG_SECONDS unless `force`; done(ok) when it is in.
function MapLive.refresh(done, force)
    if done then catalog.waiting[#catalog.waiting + 1] = done end
    if catalog.loading then return end
    local fresh = catalog.at and os.time() - catalog.at < CATALOG_SECONDS
    -- A hub that did not answer is asked again in a while, not on every draw.
    local resting = not catalog.at and catalog.tried and os.time() - catalog.tried < RETRY_SECONDS
    if not force and (fresh or resting) then
        local waiting = catalog.waiting
        catalog.waiting = {}
        for _, cb in ipairs(waiting) do pcall(cb, fresh and true or false) end
        return
    end
    catalog.loading = true
    catalog.tried = os.time()
    Games.call("GET", "/maps", nil, function(status, data)
        catalog.loading = false
        local ok = status == 200 and type(data) == "table" and type(data.maps) == "table"
        if ok then
            for _, m in ipairs(data.maps) do
                if type(m) == "table" and type(m.code) == "string" then catalog.byCode[m.code] = m end
            end
            catalog.at = os.time()
        end
        local waiting = catalog.waiting
        catalog.waiting = {}
        for _, cb in ipairs(waiting) do pcall(cb, ok) end
    end)
end

--- The listing already in hand for `code`, or nil.
function MapLive.cached(code)
    return code and catalog.byCode[code] or nil
end

--- A map's listing: done(listing) or done(nil, why).
function MapLive.info(code, done)
    local m = catalog.byCode[code]
    if m and catalog.at and os.time() - catalog.at < CATALOG_SECONDS then
        done(m)
        return
    end
    Games.call("GET", "/maps/" .. code, nil, function(status, data)
        if status == 200 and type(data) == "table" and data.code == code then
            catalog.byCode[code] = data
            done(data)
        elseif m then
            done(m)
        elseif status == 404 then
            done(nil, "The hub has no map " .. code .. ", so it cannot be downloaded.")
        else
            done(nil, Games.explain(status, data))
        end
    end)
end

-------------------------------------------------------------------------------
-- Screenshots
-------------------------------------------------------------------------------

local function coverFile(code) return mapsDir .. "\\_covers\\" .. code .. ".jpg" end
local function coverIdFile(code) return mapsDir .. "\\_covers\\" .. code .. ".id" end

local function mediaId(listing)
    local url = listing and listing.cover_url
    return type(url) == "string" and url:match("/media/([%w%-]+)") or nil
end

--- The map's screenshot as a file, fetched from the hub the first time and
--- again when the hub's cover changes: done(path) or done(nil). Without the
--- hub, whatever is on disk.
function MapLive.cover(code, done)
    if not code then return done(nil) end
    local path, id = coverFile(code), mediaId(catalog.byCode[code])
    local have = exists(path)
    local current = (readFile(coverIdFile(code)) or ""):match("[%w%-]+")
    if have and (not id or id == current) then return done(path) end
    if not id then return done(have and path or nil) end
    if fetching[code] then
        fetching[code][#fetching[code] + 1] = done
        return
    end
    fetching[code] = { done }
    Games.call("FILE", "/media/" .. id .. " " .. code .. ".jpg", nil, function(status, data)
        local saved = status == 200 and type(data) == "table" and data.saved == true
        if saved then
            writeFile(coverIdFile(code), id)
            textures[code] = nil
        elseif status ~= 200 then
            log("cover " .. code .. ": the hub answered " .. tostring(status))
        end
        local waiting = fetching[code] or {}
        fetching[code] = nil
        local result = (saved or have) and path or nil
        for _, cb in ipairs(waiting) do pcall(cb, result) end
    end)
end

--- The map's screenshot as a texture, read from the cached file. Kept by
--- name, never by reference: a transient texture no brush holds any more is
--- collected, and a stale handle would be read after it is freed.
function MapLive.texture(code)
    local path = code and coverFile(code)
    if not (path and exists(path)) then return nil end
    local id = readFile(coverIdFile(code)) or ""
    local known = textures[code]
    if known and known.file == id then
        local ok, tex = pcall(StaticFindObject, known.name)
        if ok and valid(tex) then return tex end
    end
    local krl = StaticFindObject("/Script/Engine.Default__KismetRenderingLibrary")
    local world = worldContext()
    if not (valid(krl) and world) then return nil end
    local ok, tex = pcall(function() return krl:ImportFileAsTexture2D(world, path) end)
    if not (ok and valid(tex)) then
        log("cover " .. code .. ": could not read " .. path)
        return nil
    end
    local okName, full = pcall(function() return tex:GetFullName() end)
    local name = okName and full and full:match("^%S+%s+(.+)$")
    if name then textures[code] = { name = name, file = id } end
    return tex
end

-------------------------------------------------------------------------------
-- Registering and mounting
-------------------------------------------------------------------------------

--- Give the running game `code`'s scenario records, unless its row is there
--- already (cooked into pakchunk996, or added earlier). true and "added" or
--- "present", or false and why.
function MapLive.register(code)
    if registered[code] then return true, "present" end
    local dt, da = StaticFindObject(SCENARIOS), StaticFindObject(CAMPAIGN)
    if not (valid(dt) and valid(da)) then return false, "the campaign tables are not loaded" end
    local okA, request = pcall(function()
        return string.format("%x %x %s %s\n", dt:GetAddress(), da:GetAddress(), code, TEMPLATE)
    end)
    if not okA or not writeFile(loaderNative .. "scenario_request.txt", request) then
        return false, "cannot write the scenario request"
    end
    os.remove(loaderNative .. "scenario_reply.txt")
    local ok, err = call(loaderNative .. "mjolnir_map_registry.dll", "mjolnir_scenario_add")
    if not ok then return false, err end
    local reply = (readFile(loaderNative .. "scenario_reply.txt") or "error no reply"):gsub("%s+$", "")
    if reply:match("^ok") then
        registered[code] = true
        if reply == "ok added" then
            log("map " .. code .. ": registered in memory")
            return true, "added"
        end
        return true, "present"
    end
    return false, reply:gsub("^error ", "")
end

--- Register every map in `codes` that is not registered yet: a map
--- installed in an earlier session and launched since without the launcher
--- (which cooks it in) has no cooked row. Returns how many were added, or
--- nil while the campaign tables are not loaded.
function MapLive.registerAll(codes)
    if not (valid(StaticFindObject(SCENARIOS)) and valid(StaticFindObject(CAMPAIGN))) then return nil end
    local added = 0
    for _, code in ipairs(codes) do
        local ok, how = MapLive.register(code)
        if not ok then
            log("map " .. code .. ": not registered (" .. tostring(how) .. ")")
        elseif how == "added" then
            added = added + 1
        end
    end
    return added
end

--- Where `code` is in this game's campaign list, or, with `index`, move it
--- there first: the index a fireteam's machines must agree on for the map to
--- start (mjolnir_scenario_place). The index, or nil and why.
function MapLive.place(code, index)
    local da = StaticFindObject(CAMPAIGN)
    if not valid(da) then return nil, "the campaign is not loaded" end
    local okA, request = pcall(function()
        return string.format("%x %s%s\n", da:GetAddress(), code, index and (" " .. tostring(math.floor(index))) or "")
    end)
    if not okA or not writeFile(loaderNative .. "place_request.txt", request) then
        return nil, "cannot write the place request"
    end
    os.remove(loaderNative .. "place_reply.txt")
    local ok, err = call(loaderNative .. "mjolnir_map_registry.dll", "mjolnir_scenario_place")
    if not ok then return nil, err end
    local reply = (readFile(loaderNative .. "place_reply.txt") or "error no reply"):gsub("%s+$", "")
    local at = tonumber(reply:match("^ok (%d+)") or "")
    if at then return at end
    return nil, reply:gsub("^error ", "")
end

--- A fireteam client: put `code` where the host has it (`index`, from the
--- host's lobby or vote message), registering it first. Quiet unless it fails.
function MapLive.follow(code, index)
    index = tonumber(index)
    if not (code and index) then return end
    local ok, why = MapLive.register(code)
    if not ok then return log("map " .. code .. ": not registered (" .. tostring(why) .. ")") end
    local at, whyNot = MapLive.place(code, index)
    if at ~= index then log("map " .. code .. ": could not take the host's index " .. index .. " (" .. tostring(whyNot) .. ")") end
end

--- Mount `paks` (the engine's relative .pak paths): true, or false and why.
function MapLive.mount(paks)
    if #paks == 0 then return true end
    if not writeFile(loaderNative .. "mount_request.txt", table.concat(paks, "\n") .. "\n") then
        return false, "cannot write the mount request"
    end
    os.remove(loaderNative .. "mount_reply.txt")
    local ok, err = call(loaderNative .. "mjolnir_map_registry.dll", "mjolnir_mount_paks")
    if not ok then return false, err end
    local reply = (readFile(loaderNative .. "mount_reply.txt") or "error no reply"):gsub("%s+$", "")
    if reply:match("^ok") then return true end
    return false, reply:gsub("^error ", "")
end

-------------------------------------------------------------------------------
-- Installing
-------------------------------------------------------------------------------

--- The install in flight: { code, event } (the last event), or nil.
function MapLive.current()
    return job and { code = job.code, event = job.event } or nil
end

local function finish(event)
    local j = job
    job = nil
    if not j then return end
    j.event = event
    log(string.format("map install %s: %s%s", j.code, event.stage, event.message and (" (" .. event.message .. ")") or ""))
    for _, cb in ipairs(j.listeners) do pcall(cb, event) end
end

local function emit(event)
    if not job then return end
    job.event = event
    for _, cb in ipairs(job.listeners) do pcall(cb, event) end
end

local function poll()
    if not job then return end
    local text = readFile(nativeDir .. "map_install_progress.json")
    local ok, p = false, nil
    if text and text ~= job.lastText then
        ok, p = pcall(Json.decode, text)
        job.lastText = text
        job.heard = os.time()
    end
    if ok and type(p) == "table" then
        if p.stage == "done" then
            emit({ stage = "installing", message = "Loading the map" })
            local paks = {}
            for _, path in ipairs(type(p.mount) == "table" and p.mount or {}) do
                if type(path) == "string" then paks[#paks + 1] = path end
            end
            local mounted, why = MapLive.mount(paks)
            if not mounted then
                return finish({ stage = "error", message = "The map installed, but could not be loaded now (" ..
                    tostring(why) .. "). It will be there after a restart." })
            end
            local reg, whyReg = MapLive.register(job.code)
            if not reg then
                return finish({ stage = "error", message = "The map installed, but could not be registered now (" ..
                    tostring(whyReg) .. "). It will be there after a restart." })
            end
            return finish({ stage = "ready", version = p.version })
        elseif p.stage == "error" then
            return finish({ stage = "error", message = tostring(p.message or "the install failed") })
        elseif p.stage == "download" then
            -- The hub streams the archive without a length; its listing has one.
            local listing = catalog.byCode[job.code]
            local total = tonumber(p.total) or
                (listing and type(listing.release) == "table" and tonumber(listing.release.file_size)) or nil
            emit({ stage = "download", received = tonumber(p.received) or 0, total = total })
        end
    end
    -- The launcher gone without a word, or silent for too long.
    if os.time() - (job.checked or 0) >= 1 then
        job.checked = os.time()
        call(nativeDir .. "mjolnir_lobby.dll", "mjolnir_map_install_status")
        local status = readFile(nativeDir .. "map_install_status.txt") or ""
        local code = status:match("^exited (%d+)")
        if code then
            -- Its last word may have landed after this poll read the file:
            -- an outcome there is the next poll's to act on.
            local last = readFile(nativeDir .. "map_install_progress.json") or ""
            if not (last:find('"stage":"done"', 1, true) or last:find('"stage":"error"', 1, true)) then
                return finish({ stage = "error", message = "The MJOLNIR launcher stopped (exit " .. code .. ")." })
            end
        end
    end
    if os.time() - (job.heard or job.started) > STALL_SECONDS then
        return finish({ stage = "error", message = "No word from the MJOLNIR launcher for two minutes." })
    end
    ExecuteInGameThreadWithDelay(POLL_MS, poll)
end

--- Install `code` from the hub. `onEvent` hears { stage = "download",
--- received, total }, { stage = "installing" }, then { stage = "ready" } or
--- { stage = "error", message }. A second call for the map already
--- installing joins it. Returns false and why when it cannot start.
function MapLive.install(code, onEvent)
    if job then
        if job.code ~= code then return false, "Another map (" .. job.code .. ") is downloading." end
        job.listeners[#job.listeners + 1] = onEvent
        if job.event then pcall(onEvent, job.event) end
        return true
    end
    if not writeFile(nativeDir .. "map_install_request.txt", code) then return false, "cannot write the request" end
    os.remove(nativeDir .. "map_install_reply.txt")
    os.remove(nativeDir .. "map_install_progress.json")
    local ok, err = call(nativeDir .. "mjolnir_lobby.dll", "mjolnir_map_install")
    if not ok then return false, err end
    local reply = (readFile(nativeDir .. "map_install_reply.txt") or "error no reply"):gsub("%s+$", "")
    if not reply:match("^ok") then return false, (reply:gsub("^error ", "")) end
    job = { code = code, listeners = { onEvent }, started = os.time(), heard = os.time(), event = { stage = "start" } }
    log("map install " .. code .. ": started")
    pcall(onEvent, job.event)
    ExecuteInGameThreadWithDelay(POLL_MS, poll)
    return true
end

--- What a size in bytes reads as.
function MapLive.size(bytes)
    bytes = tonumber(bytes)
    if not bytes then return "?" end
    if bytes >= 1024 * 1024 then return string.format("%.1f MB", bytes / (1024 * 1024)) end
    return string.format("%d KB", math.max(1, math.floor(bytes / 1024 + 0.5)))
end

function MapLive.init(deps)
    Json, Games, log = deps.Json, deps.Games, deps.log
    nativeDir, loaderNative, mapsDir = deps.nativeDir, deps.loaderNative, deps.mapsDir
    worldContext = deps.worldContext
end

return MapLive

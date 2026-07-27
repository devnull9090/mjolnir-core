-- MJOLNIR Tag Probe
--
-- Answers one question from inside the running game: did an override container
-- actually take effect?
--
-- Editing a tag and packing it into a `.utoc`/`.ucas` beside the shipped ones is
-- only half the story; nothing outside the process can tell you whether the
-- loader used your chunk or the original. This reads the values back out of the
-- live tag assets, so the answer comes from the game rather than from inference.
--
-- Commands:
--   mjolnir_tag_probe [filter]   dump loaded Blam tag assets and their properties
--   mjolnir_tag_classes          list which Blam*TagDataAsset classes are loaded
--   mjolnir_paks                 report what the mounted file tree can see
--
-- Output goes to ue4ss/MJOLNIR_TagProbe.txt as well as the console, because the
-- console scrolls and a property dump does not fit on screen.

local LOG_FILE = "ue4ss/MJOLNIR_TagProbe.txt"

-- Tag groups are wrapped in one UObject class each; this is the naming the
-- shipped data uses, confirmed by the package headers.
local TAG_ASSET_SUFFIX = "TagDataAsset"

local function log(text)
    local f = io.open(LOG_FILE, "a")
    if f then
        f:write(text, "\n")
        f:close()
    end
    print(text .. "\n")
end

local function safeName(object)
    if object == nil then return nil end
    local ok, name = pcall(function() return object:GetFullName() end)
    if ok and name then return name end
    return nil
end

local function describe(value)
    if value == nil then return "nil" end
    local kind = type(value)
    if kind == "string" or kind == "number" or kind == "boolean" then
        return tostring(value)
    end
    local name = safeName(value)
    if name then return name end
    local ok, text = pcall(function() return value:ToString() end)
    if ok and text then return text end
    return tostring(value)
end

--- Every property on an object and its parent classes, with values.
---
--- Walks up the class chain because the interesting fields on a tag asset may
--- be declared on a shared base rather than the group's own class.
local function dumpProperties(object, indent)
    local okClass, class = pcall(function() return object:GetClass() end)
    if not okClass or not class or not class:IsValid() then
        log(indent .. "[no class]")
        return
    end

    local seen = {}
    while class and class:IsValid() do
        log(indent .. "[class] " .. (safeName(class) or "?"))
        local ok = pcall(function()
            class:ForEachProperty(function(property)
                local okName, name = pcall(function()
                    return property:GetFName():ToString()
                end)
                if not okName or not name or seen[name] then return end
                seen[name] = true
                local okValue, value = pcall(function()
                    return object:GetPropertyValue(name)
                end)
                log(string.format("%s  %s = %s", indent, name,
                    okValue and describe(value) or "<unreadable>"))
            end)
        end)
        if not ok then
            log(indent .. "  [property walk failed]")
        end
        local okSuper, super = pcall(function() return class:GetSuperStruct() end)
        class = (okSuper and super and super:IsValid()) and super or nil
    end
end

--- Find loaded tag assets, optionally filtered by a substring of their name.
---
--- `FindAllOf` needs a concrete class name, so this asks for the base and falls
--- back to scanning every object when that is not registered.
local function findTagAssets(filter)
    local found = {}
    local ok, objects = pcall(FindAllOf, "BlamTagDataAsset")
    if not ok or not objects then
        objects = {}
        -- The base class may not be instantiable; try the known concrete ones.
        for _, class in ipairs({
            "BlamWeaponTagDataAsset", "BlamBipedTagDataAsset",
            "BlamVehicleTagDataAsset", "BlamProjectileTagDataAsset",
            "BlamModelTagDataAsset", "BlamEquipmentTagDataAsset",
        }) do
            local okOne, some = pcall(FindAllOf, class)
            if okOne and some then
                for _, o in ipairs(some) do objects[#objects + 1] = o end
            end
        end
    end

    for _, object in ipairs(objects) do
        local name = safeName(object)
        if name and (not filter or name:lower():find(filter:lower(), 1, true)) then
            found[#found + 1] = { object = object, name = name }
        end
    end
    return found
end

local function probe(filter)
    log("=== tag probe " .. (filter and ("filter=" .. filter) or "(no filter)"))
    local found = findTagAssets(filter)
    log(string.format("found %d loaded tag asset(s)", #found))
    for _, entry in ipairs(found) do
        log("")
        log("[asset] " .. entry.name)
        dumpProperties(entry.object, "  ")
    end
    if #found == 0 then
        log("Nothing matched. Tag assets load on demand, so try this while the")
        log("weapon is in your hands, and check mjolnir_tag_classes first.")
    end
    log("=== end")
end

--- Which tag asset classes exist and how many instances are loaded.
---
--- Cheap orientation before dumping anything: it says what is actually in
--- memory rather than what we assume should be.
local function classes()
    log("=== loaded tag asset classes")
    local ok, objects = pcall(FindAllOf, "Object")
    if not ok or not objects then
        log("could not enumerate objects")
        return
    end
    local counts = {}
    for _, object in ipairs(objects) do
        local okClass, class = pcall(function() return object:GetClass() end)
        if okClass and class and class:IsValid() then
            local name = safeName(class)
            if name and name:find(TAG_ASSET_SUFFIX, 1, true) then
                counts[name] = (counts[name] or 0) + 1
            end
        end
    end
    local any = false
    for name, n in pairs(counts) do
        any = true
        log(string.format("  %-70s %d", name, n))
    end
    if not any then log("  none loaded") end
    log("=== end")
end

--- What the mounted filesystem exposes.
---
--- An override container with an empty directory index contributes no paths, so
--- a blank result here does not mean it failed to mount. This is orientation,
--- not proof.
local function paks()
    log("=== mounted game directories")
    local ok = pcall(function()
        IterateGameDirectories(function(directory)
            local okName, name = pcall(function() return directory:GetDirName() end)
            log("  " .. (okName and name or "?"))
        end)
    end)
    if not ok then
        log("  IterateGameDirectories unavailable in this UE4SS build")
    end
    log("=== end")
end

RegisterConsoleCommandHandler("mjolnir_tag_probe", function(_, args)
    local filter = args and args[1] or nil
    ExecuteInGameThread(function() probe(filter) end)
    return true
end)

RegisterConsoleCommandHandler("mjolnir_tag_classes", function()
    ExecuteInGameThread(classes)
    return true
end)

RegisterConsoleCommandHandler("mjolnir_paks", function()
    ExecuteInGameThread(paks)
    return true
end)

print("[MJOLNIR] Tag probe ready: mjolnir_tag_classes, mjolnir_tag_probe [filter], mjolnir_paks\n")

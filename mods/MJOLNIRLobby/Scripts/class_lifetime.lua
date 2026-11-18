-- Keep only our explicitly listed widget classes alive across map travel.
-- UE4SS c838a8ac caches FProperty pointers by UClass address. After a UI
-- Blueprint is collected and reloaded, a cached field can refer to freed
-- memory (2026-11-01: the second match crashed reading Feed.Watermark).
-- A rooted, uninitialized widget retains its class without a world, player,
-- Slate tree or viewport. Never root the displayed widget or its controller.
-- This self-contained module is also shipped in MJOLNIRLobby/MJOLNIRForge.
local Lifetime = {}

function Lifetime.new(names, log)
    local allowed, ready, reported = {}, {}, {}
    for _, name in ipairs(names) do
        assert(type(name) == "string" and name:match("^WBP_MJOLNIR%w+$"), "invalid UI class name")
        allowed[name] = true
    end

    return function(path, cls)
        local key = tostring(path)
        local ok, result = pcall(function()
            assert(type(path) == "string", "UI class path is missing")
            local folder, name, className = path:match("^/Game/MJOLNIR/(%w+)/(WBP_MJOLNIR%w+)%.([%w_]+)$")
            assert((folder == "UI" or folder == "ForgeUI") and allowed[name]
                and className == name .. "_C", "UI class is not allowlisted")
            assert(cls and cls:IsValid(), "UI class is unavailable")
            if ready[path] then return cls end

            local rootFlag = assert(EInternalObjectFlags and EInternalObjectFlags.RootSet, "RootSet flag unavailable")
            local transientFlag = assert(EObjectFlags and EObjectFlags.RF_Transient, "Transient flag unavailable")
            local pinName = "MJOLNIR_UI_ClassPin_" .. name
            local pin = StaticFindObject("/Engine/Transient." .. pinName)
            if not (pin and pin:IsValid()) then
                local engine = FindFirstOf("GameEngine")
                assert(engine and engine:IsValid(), "game engine is unavailable")
                local outer = engine:GetOuter()
                assert(outer and outer:IsValid() and outer:GetFullName() == "Package /Engine/Transient",
                    "UI class pin requires the world-independent transient package")
                pin = StaticConstructObject(cls, outer, FName(pinName), transientFlag, rootFlag)
            end
            assert(pin and pin:IsValid() and pin:IsA(cls) and pin:HasAnyInternalFlags(rootFlag),
                "UI class pin was not rooted with the expected class")
            ready[path] = true
            reported[key] = nil
            return cls
        end)
        if ok then return result end
        if not reported[key] then
            reported[key] = true
            if log then log("cannot retain UI class " .. tostring(path) .. ": " .. tostring(result)) end
        end
        return nil
    end
end

return Lifetime

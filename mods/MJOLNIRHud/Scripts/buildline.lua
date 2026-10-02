-- The build line at the bottom centre of the HUD and of every MJOLNIR menu
-- screen: the multiplayer mods' versions and the game build, so that a
-- screenshot or a stream shows exactly what was running.
--
--   MJOLNIR MULTIPLAYER   /   HUD 0.2.0   LOBBY 0.1.2   LOADER 0.1.2   /   CU4 1121610
--
-- MJOLNIRHud and MJOLNIRLobby each carry an identical copy, so neither
-- depends on the other being installed. `modsDir` is the UE4SS Mods folder.

local BuildLine = {}

local MODS = { { "MJOLNIRHud", "HUD" }, { "MJOLNIRLobby", "LOBBY" }, { "MJOLNIRLevelLoader", "LOADER" } }
local cached = nil

local function readFile(path)
    local f = io.open(path, "rb")
    if not f then return nil end
    local data = f:read("*a")
    f:close()
    return data
end

--- "5.5.4-1121610+++Meteorite+Rel-i343-Meteorite-2607-CU4" -> "CU4 1121610".
function BuildLine.game(engineVersion)
    if type(engineVersion) ~= "string" then return nil end
    local changelist = engineVersion:match("^[%d%.]+%-(%d+)")
    local update = engineVersion:match("%-(CU%d+)$")
    if not changelist then return nil end
    return (update and (update .. " ") or "") .. changelist
end

function BuildLine.text(modsDir)
    if cached then return cached end
    local parts = {}
    for _, m in ipairs(MODS) do
        local raw = readFile(modsDir .. "\\" .. m[1] .. "\\mod.json") or ""
        local version = raw:match('"version"%s*:%s*"([^"]+)"')
        if version then parts[#parts + 1] = m[2] .. " " .. version end
    end
    local game
    pcall(function()
        game = BuildLine.game(StaticFindObject("/Script/Engine.Default__KismetSystemLibrary"):GetEngineVersion():ToString())
    end)
    local line = "MJOLNIR MULTIPLAYER"
    if #parts > 0 then line = line .. "   /   " .. table.concat(parts, "   ") end
    if game then line = line .. "   /   " .. game end
    cached = line
    return line
end

return BuildLine

-- MJOLNIR Level Loader: Blam script lines for the simulation.
--
-- MJOLNIRLobby's DLL, which every player has, runs them on the simulation
-- thread while a game is running (native\script.txt, then
-- mjolnir_sim_script). One counter for every caller (kill_floor.lua): the
-- DLL skips a file whose id it has already run. Script.request hands the DLL
-- any other request file the same way (lifts.lua's phantoms).

local Script = {}

local dir
-- package.loadlib's function for each export asked for, false once it is
-- known missing (an older DLL, or none).
local exports = {}
-- From the clock, so a reloaded loader does not start on the last id the DLL
-- ran (it compares each file's id with that one alone).
local id = os.time()

--- `modDir`: MJOLNIRLevelLoader's folder; MJOLNIRLobby sits beside it.
function Script.init(modDir)
    dir = modDir:gsub("[\\/]MJOLNIRLevelLoader[\\/]?$", "") .. "\\MJOLNIRLobby\\native\\"
end

local function export(name)
    if not dir then return false end
    if exports[name] == nil then
        exports[name] = package and package.loadlib and package.loadlib(dir .. "mjolnir_lobby.dll", name) or false
    end
    return exports[name]
end

--- Write `text` to the DLL's native\`file` and call its `name` export to
--- read it. False when MJOLNIRLobby's DLL, or that export, is not there.
function Script.request(file, name, text)
    local run = export(name)
    if not run then return false end
    local f = io.open(dir .. file, "wb")
    if not f then return false end
    f:write(text)
    f:close()
    pcall(run)
    return true
end

--- Run one line, or a list of lines (16 at most), in the simulation. False
--- when MJOLNIRLobby's DLL is not there.
function Script.send(lines)
    local run = export("mjolnir_sim_script")
    if not run then return false end
    if type(lines) == "string" then lines = { lines } end
    id = id + 1
    local f = io.open(dir .. "script.txt", "wb")
    if not f then return false end
    f:write(tostring(id), "\n", table.concat(lines, "\n"), "\n")
    f:close()
    pcall(run)
    return true
end

return Script

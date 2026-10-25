-- MJOLNIR Level Loader: Blam script lines for the simulation.
--
-- MJOLNIRLobby's DLL, which every player has, runs them on the simulation
-- thread while a game is running (native\script.txt, then
-- mjolnir_sim_script). One counter for every caller (kill_floor.lua,
-- lifts.lua): the DLL skips a file whose id it has already run.

local Script = {}

local dir
local run
-- From the clock, so a reloaded loader does not start on the last id the DLL
-- ran (it compares each file's id with that one alone).
local id = os.time()

--- `modDir`: MJOLNIRLevelLoader's folder; MJOLNIRLobby sits beside it.
function Script.init(modDir)
    dir = modDir:gsub("[\\/]MJOLNIRLevelLoader[\\/]?$", "") .. "\\MJOLNIRLobby\\native\\"
end

--- Run one line, or a list of lines (16 at most), in the simulation. False
--- when MJOLNIRLobby's DLL is not there.
function Script.send(lines)
    if not dir then return false end
    if run == nil then
        run = package and package.loadlib and package.loadlib(dir .. "mjolnir_lobby.dll", "mjolnir_sim_script") or false
    end
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

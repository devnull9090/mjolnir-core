-- Event-only bootstrap and two-Hz native snapshot pump. All transport,
-- capture, score and phase updates execute in native code/Megalo.
local M = { active = false }

function M.init(dir, log, every)
    if M.initialized then return end
    M.initialized, M.dir, M.log = true, dir, log
    M.nativeDir = (dir:match("^(.*)\\[^\\]+$") or dir) .. "\\MJOLNIRLobby\\native"
    if package and package.loadlib then
        local dll = M.nativeDir .. "\\mjolnir_lobby.dll"
        for _, name in ipairs({ "open", "close", "action", "pump", "controls" }) do
            M[name .. "Native"] = package.loadlib(dll, "mjolnir_warfare_" .. name)
        end
        M.putNative = package.loadlib(dll, "mjolnir_request_put")
    end
    if not (M.openNative and M.closeNative and M.actionNative and M.pumpNative) then
        log("Pelican Warfare: native transport exports unavailable; deployment will not be enabled")
        return
    end
    -- With the flight controls export the HUD tracks the local rider's
    -- remapped Jump action. Older native builds keep the keyboard fallback.
    if not M.controlsNative then
        pcall(RegisterKeyBind, 0x20, {}, function()
            if M.active then pcall(M.actionNative) end
        end)
    end
    pcall(RegisterConsoleCommandHandler, "mjolnir_warfare_jump", function()
        if M.active then pcall(M.actionNative) end
        return true
    end)
    -- warfare_state.txt is for the smoke tools (native/lobby/smoke-warfare*.mjs)
    -- on a development PC, marked by %LOCALAPPDATA%\Meteorite\Saved\
    -- mjolnir_dev.txt. A player's HUD takes the same snapshot from memory
    -- (mjolnir_warfare_snapshot), so a player's game runs no pump at all: it
    -- rewrote the file twice a second for nobody (~0.8 ms/s).
    local base = os.getenv and os.getenv("LOCALAPPDATA")
    local mark = base and io.open(base .. "\\Meteorite\\Saved\\mjolnir_dev.txt", "rb")
    if mark then
        mark:close()
        every(500, "warfare presentation", function()
            if M.active then M.pumpNative() end
        end)
    end
end

function M.select(code, variant, layout)
    local wanted = code == "PWR" and variant == "warfare"
    local compatible = type(layout) == "table" and layout.protocol == 20569 and layout.layout_revision == 3
    if wanted and not compatible then
        if not M.rejected then M.log("Pelican Warfare: map layout/protocol does not match native expansion; deployment disabled") end
        M.rejected = true
        wanted = false
    elseif wanted then M.rejected = nil end
    if not wanted then
        if M.active and M.closeNative then pcall(M.closeNative) end
        M.active = false
        return
    end
    if M.active or not M.openNative then return end
    -- In memory (mjolnir_request_put); the file for a DLL without it.
    local config = "warfare-config 2\nmap PWR\nlayout 3\nprotocol 20569\n"
    local okPut, held = false, nil
    if M.putNative then okPut, held = pcall(M.putNative, "warfare_config.txt", config) end
    if not (okPut and held == true) then
        local f, err = io.open(M.nativeDir .. "\\warfare_config.txt", "wb")
        if not f then M.log("Pelican Warfare config: " .. tostring(err)); return end
        f:write(config)
        f:close()
    end
    local ok, result = pcall(M.openNative)
    M.active = ok and result ~= false
    if not M.active then M.log("Pelican Warfare native start failed: " .. tostring(result)) end
end

return M

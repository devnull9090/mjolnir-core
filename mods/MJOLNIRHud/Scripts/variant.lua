-- The score to win from a Megalo game variant (.mglo), the file the
-- simulation itself loads (MJOLNIRLevelLoader stages variants/<mode>.mglo).
--
-- A port of crates/blam-megalo's reader up to that one field: the variant is
-- an MSB-first bitstream, and the score to win sits after the base options,
-- the traits and the string tables, whose sizes vary. Returns nil for
-- anything it does not follow (a compressed string table, player traits or
-- user options), so the HUD keeps its default.

local Variant = {}

local function reader(bytes)
    local r = { at = 0, bits = #bytes * 8 }

    --- `n` bits as an unsigned number (n <= 32).
    function r.read(n)
        if r.at + n > r.bits then error("truncated") end
        local v = 0
        for _ = 1, n do
            local byte = bytes:byte(r.at // 8 + 1)
            v = v * 2 + ((byte >> (7 - r.at % 8)) & 1)
            r.at = r.at + 1
        end
        return v
    end

    function r.skip(...)
        for _, n in ipairs({ ... }) do
            if r.at + n > r.bits then error("truncated") end
            r.at = r.at + n
        end
    end

    function r.bool() return r.read(1) == 1 end
    return r
end

local TRAITS = {
    { 4, 3, 4, 3, 4, 4, 2, 3, 2, 2 },
    { 4, 4, 8, 8, 4, 2, 2, 2, 2, 2, 2, 8 },
    { 5, 4, 4, 2 },
    { 3, 2, 2, 3, 4 },
    { 3, 3, 2 },
}

local function traits(r)
    r.skip(table.unpack(TRAITS[1]))
    r.skip(table.unpack(TRAITS[2]))
    r.skip(table.unpack(TRAITS[3]))
    if r.bool() then r.skip(9) end
    r.skip(table.unpack(TRAITS[4]))
    r.skip(table.unpack(TRAITS[5]))
end

local function strings(r, cw, ow, sw)
    local count = r.read(cw)
    for _ = 1, count do
        for _ = 1, 12 do
            if r.bool() then r.skip(ow) end
        end
    end
    if count == 0 then return end
    local size = r.read(sw)
    if r.bool() then error("a compressed string table") end
    r.skip(size * 8)
end

local function contentHeader(r)
    local kind = r.read(4) - 1
    r.skip(32, 64, 64, 64, 64, 3)
    local mode = r.read(3)
    r.skip(3, 32, 8)
    for _ = 1, 2 do
        r.skip(64, 64)
        for _ = 1, 16 do
            if r.read(8) == 0 then break end
        end
        r.skip(1)
    end
    for _ = 1, 2 do
        for _ = 1, 128 do
            if r.read(16) == 0 then break end
        end
    end
    if kind == 3 or kind == 4 then r.skip(32) elseif kind == 6 then r.skip(8) end
    if mode == 1 then r.skip(8, 2, 2, 8, 32) elseif mode == 2 then r.skip(2, 32) end
end

local function base(r)
    contentHeader(r)
    r.skip(1, 1, 1, 1, 1, 8, 5, 4, 7, 5)
    r.skip(1, 1, 1, 1, 6, 7, 8, 8, 8, 4, 4, 6)
    traits(r)
    r.skip(1, 2, 1, 1, 1, 1, 1, 6)
    traits(r)
    r.skip(8, 8)
    for _ = 1, 3 do traits(r) end
    r.skip(7, 7, 7, 3, 3, 2)
    for _ = 1, 8 do
        r.skip(4)
        strings(r, 1, 5, 6)
        r.skip(4, 1, 32, 32, 32, 5)
    end
    r.skip(2)
    for _ = 1, 30 do
        r.skip(1)
        if not r.bool() then r.skip(7) end
        r.skip(8, 8, 8, 4)
    end
end

--- The score to win in a variant's bytes, or nil.
function Variant.scoreToWin(bytes)
    if type(bytes) ~= "string" or #bytes < 8 then return nil end
    local ok, score = pcall(function()
        local r = reader(bytes)
        local version = r.read(32)
        if version ~= 0x6a and version ~= 0x6b then error("version") end
        r.skip(32)
        base(r)
        if r.read(5) ~= 0 or r.read(5) ~= 0 then error("player traits or user options") end
        strings(r, 7, 15, 15)
        r.skip(7)
        strings(r, 1, 9, 9)
        strings(r, 1, 12, 12)
        strings(r, 1, 9, 9)
        r.skip(5, 5)
        for _ = 1, r.read(6) do r.skip(16) end
        r.skip(1)
        for _ = 1, 15 do r.skip(32) end
        r.skip(1)
        return r.read(16)
    end)
    return ok and score or nil
end

return Variant

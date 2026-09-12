-- Minimal JSON decoder for MJOLNIRLevelLoader.
--
-- Decode only: the loader reads .level.json files and never writes JSON.
-- Recursive descent over the grammar, erroring with a byte offset on any
-- malformed input so a bad level file names its own problem. No encoder, no
-- metatables, no dependencies.
--
-- JSON arrays become Lua array tables, objects become string-keyed tables,
-- and null becomes Json.null (a unique sentinel) so it survives in tables.

local Json = { null = setmetatable({}, { __tostring = function() return "null" end }) }

local function fail(str, i, msg)
    error(string.format("json: %s at byte %d", msg, i), 0)
end

local function skipWs(str, i)
    local _, j = str:find("^[ \n\r\t]*", i)
    return j + 1
end

local ESCAPES = {
    ['"'] = '"', ["\\"] = "\\", ["/"] = "/",
    b = "\b", f = "\f", n = "\n", r = "\r", t = "\t",
}

local function utf8Encode(cp)
    if cp < 0x80 then
        return string.char(cp)
    elseif cp < 0x800 then
        return string.char(0xC0 + math.floor(cp / 0x40), 0x80 + cp % 0x40)
    else
        return string.char(0xE0 + math.floor(cp / 0x1000),
                           0x80 + math.floor(cp / 0x40) % 0x40,
                           0x80 + cp % 0x40)
    end
end

local function parseString(str, i)
    -- i points at the opening quote
    local out, j = {}, i + 1
    while true do
        local c = str:sub(j, j)
        if c == "" then
            fail(str, j, "unterminated string")
        elseif c == '"' then
            return table.concat(out), j + 1
        elseif c == "\\" then
            local e = str:sub(j + 1, j + 1)
            if ESCAPES[e] then
                out[#out + 1] = ESCAPES[e]
                j = j + 2
            elseif e == "u" then
                local hex = str:sub(j + 2, j + 5)
                if not hex:match("^%x%x%x%x$") then fail(str, j, "bad \\u escape") end
                out[#out + 1] = utf8Encode(tonumber(hex, 16))
                j = j + 6
            else
                fail(str, j, "bad escape '\\" .. e .. "'")
            end
        else
            out[#out + 1] = c
            j = j + 1
        end
    end
end

local function parseNumber(str, i)
    local numStr = str:match("^-?%d+%.?%d*[eE]?[+%-]?%d*", i)
    local n = numStr and tonumber(numStr)
    if not n then fail(str, i, "bad number") end
    return n, i + #numStr
end

local parseValue

local function parseArray(str, i)
    -- i points past the opening bracket
    local out = {}
    i = skipWs(str, i)
    if str:sub(i, i) == "]" then return out, i + 1 end
    while true do
        local v
        v, i = parseValue(str, i)
        out[#out + 1] = v
        i = skipWs(str, i)
        local c = str:sub(i, i)
        if c == "]" then return out, i + 1 end
        if c ~= "," then fail(str, i, "expected ',' or ']'") end
        i = skipWs(str, i + 1)
    end
end

local function parseObject(str, i)
    -- i points past the opening brace
    local out = {}
    i = skipWs(str, i)
    if str:sub(i, i) == "}" then return out, i + 1 end
    while true do
        if str:sub(i, i) ~= '"' then fail(str, i, "expected object key") end
        local key, value
        key, i = parseString(str, i)
        i = skipWs(str, i)
        if str:sub(i, i) ~= ":" then fail(str, i, "expected ':'") end
        i = skipWs(str, i + 1)
        value, i = parseValue(str, i)
        out[key] = value
        i = skipWs(str, i)
        local c = str:sub(i, i)
        if c == "}" then return out, i + 1 end
        if c ~= "," then fail(str, i, "expected ',' or '}'") end
        i = skipWs(str, i + 1)
    end
end

parseValue = function(str, i)
    local c = str:sub(i, i)
    if c == '"' then return parseString(str, i) end
    if c == "{" then return parseObject(str, i + 1) end
    if c == "[" then return parseArray(str, i + 1) end
    if c == "t" then
        if str:sub(i, i + 3) == "true" then return true, i + 4 end
    elseif c == "f" then
        if str:sub(i, i + 4) == "false" then return false, i + 5 end
    elseif c == "n" then
        if str:sub(i, i + 3) == "null" then return Json.null, i + 4 end
    elseif c == "-" or c:match("%d") then
        return parseNumber(str, i)
    end
    fail(str, i, "unexpected character '" .. c .. "'")
end

--- Decode a JSON document. Returns the value, or raises on malformed input.
function Json.decode(str)
    if type(str) ~= "string" then error("json: expected a string", 0) end
    local i = skipWs(str, 1)
    local value, j = parseValue(str, i)
    j = skipWs(str, j)
    if j <= #str then fail(str, j, "trailing garbage") end
    return value
end

return Json

-- MJOLNIR Lobby's MapLive.worlds (mods/MJOLNIRLobby/Scripts/maplive.lua):
-- whether a listed map's world is in a container here, from the level
-- loader's native half (mjolnir_worlds_known), with no game. A map in a
-- maps.json without its containers is left out of the lists, the vote and
-- the start (two PCs, 2026-11-07: a leftover --install-test maps.json put
-- Ivory Tower in the vote, and the fireteam was stranded).
local checks = 0
local function eq(actual, expected, label)
    checks = checks + 1
    assert(actual == expected, (label or "value") .. ": expected " .. tostring(expected) .. ", got " .. tostring(actual))
end

local files = {}          -- path -> contents: the native folder's request and reply files
local index = {}          -- world name -> true: what the fake native half's index holds
local exported = true     -- whether the DLL has mjolnir_worlds_known (an older one does not)
local asked = 0           -- native calls
local logs = {}
local clock = 0

local function fakeNative()
    asked = asked + 1
    local out = { "ok" }
    for name in (files["N\\world_request.txt"] or ""):gmatch("[^\n]+") do
        out[#out + 1] = name .. " " .. (index[name] and "1" or "0")
    end
    files["N\\world_reply.txt"] = table.concat(out, "\n") .. "\n"
end

local env = setmetatable({
    io = { open = function(path, mode)
        if mode:find("r", 1, true) then
            local text = files[path]
            if not text then return nil end
            return { read = function() return text end, close = function() end }
        end
        files[path] = ""
        return { write = function(_, ...) for _, v in ipairs({ ... }) do files[path] = files[path] .. tostring(v) end end,
            close = function() end }
    end },
    os = { remove = function(path) files[path] = nil end, clock = function() return clock end, time = os.time },
    package = { loadlib = function(dll, name)
        if name == "mjolnir_worlds_known" and exported then return fakeNative end
        if name == "mjolnir_mount_paks" then
            return function() files["N\\mount_reply.txt"] = "ok 1" end
        end
        return nil
    end },
}, { __index = _G })
local MapLive = assert(loadfile("mods/MJOLNIRLobby/Scripts/maplive.lua", "t", env))()

eq(MapLive.worlds({ "BGL" }), nil, "before init it cannot say")
eq(asked, 0, "and asks nothing")
MapLive.init({ log = function(m) logs[#logs + 1] = m end, loaderNative = "N\\", nativeDir = "L\\", mapsDir = "M" })

index.BGL, index.PRS = true, true
local w = MapLive.worlds({ "BGL", "PRS", "IVT" })
eq(asked, 1, "one native call for the whole list")
eq(files["N\\world_request.txt"], "BGL\nPRS\nIVT\n", "every code in one request")
eq(w.BGL, true, "a mounted world")
eq(w.PRS, true, "another")
eq(w.IVT, false, "a listed map with no world")
eq(#logs, 1, "the missing world is logged")
assert(logs[1]:find("IVT", 1, true) and logs[1]:find("no container", 1, true), logs[1])

-- The lists ask several times a second: answered from what was asked.
clock = 5
w = MapLive.worlds({ "BGL", "IVT" })
eq(asked, 1, "within the window: no native call")
eq(w.IVT, false, "still missing")
eq(#logs, 1, "logged once")
-- A code not asked about yet is asked at once.
w = MapLive.worlds({ "BGL", "NIG" })
eq(asked, 2, "a new code asks again")
eq(w.NIG, false, "NIG is not in the index")
-- A start asks afresh.
index.NIG = true
w = MapLive.worlds({ "NIG" }, true)
eq(asked, 3, "fresh asks")
eq(w.NIG, true, "NIG mounted since")
-- After the window, asked again.
clock = 20
MapLive.worlds({ "BGL" })
eq(asked, 4, "the window ran out")
-- A mount (a live install) changes the index: asked again next time.
MapLive.mount({ "../../../Meteorite/Content/Paks/x.pak" })
MapLive.worlds({ "BGL" })
eq(asked, 5, "a mount drops the answers")
-- Names that are no world name are never sent, and need no answer.
MapLive.worlds({ "BGL", "a b", 7 })
eq(files["N\\world_request.txt"], "BGL\n", "only names")

-- An MJOLNIRLevelLoader from before the export: it cannot say, so every map
-- is kept, and the DLL is not asked again on every list.
exported = false
clock = 40
eq(MapLive.worlds({ "BGL", "IVT" }), nil, "an older native half cannot say")
local warned = #logs
eq(logs[warned]:find("cannot check", 1, true) ~= nil, true, "said once")
clock = 41
eq(MapLive.worlds({ "BGL", "ZZZ" }), nil, "still cannot say")
eq(#logs, warned, "not said again")
-- The index not built yet (the loader opens it a moment after start).
exported = true
files = {}
local early = function() asked = asked + 1; files["N\\world_reply.txt"] = "error the world index is not open\n" end
env.package.loadlib = function(_, name) return name == "mjolnir_worlds_known" and early or nil end
clock = 60
eq(MapLive.worlds({ "BGL" }), nil, "no index yet: cannot say")
env.package.loadlib = function(_, name) return name == "mjolnir_worlds_known" and fakeNative or nil end
clock = 61
eq(MapLive.worlds({ "BGL" }), nil, "not asked again within the window")
clock = 75
w = MapLive.worlds({ "BGL", "IVT" })
eq(w and w.BGL, true, "answers once the index is there")
eq(w and w.IVT, false, "and knows what is missing")
print("Map worlds: " .. checks .. " checks passed")

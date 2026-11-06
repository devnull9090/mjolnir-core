-- MJOLNIR Lobby: the game types, one row per variant file.
--
-- The rows gather into tiles. The game type and map select screens show
-- families (`Modes.families`) with every variant on show: a family is what a
-- player thinks of the game as, so the engine a row happens to run on, Oddball
-- under Juggernaut, stays out of sight. An older UI container has six tiles, one
-- per engine, and a tile steps through its variants. A row is offered when the
-- map lists its engine (or `Modes.derive` adds it), its variants\<id>.mglo is
-- installed, and the container it `needs` is. A level's own modes list only
-- engine ids (slayer, ctf, koth, oddball, race), so hub manifests stay
-- within their eight.
--
-- A variant's `id` is its identity everywhere: pending_variant.txt on the
-- host, field 2 of the `lobby` message, field 3 of `starting`, the listing's
-- game_type and the post-game vote. Clients and joiners write it to the level
-- loader's match_variant.txt (`Modes.follow`), which the loader prefers to the
-- slot (VariantSettings.exactVariant).
--
-- `slot` is the insertion point a game of this type starts at. The host's
-- travel carries that index to every fireteam client, so it names the engine
-- for a client whose exact id never came: slayer 0, ctf 1, team_slayer 2, the
-- King family 3, the Oddball family 4, forge 5, the Race family 6. Keep in
-- step with MJOLNIRLevelLoader's GAME_TYPE_SLOTS and
-- VariantSettings.VARIANT_SLOTS (tools/tests/test_game_variants.lua). A map
-- has eight insertion point copies, so 6 needs no rebake.
--
-- CTF's blue flag is a tag of its own in the CE runtime pack, and on a PC
-- without it the simulation wipes a CTF script that names it: a match with no
-- flags (docs/game_modes.md 2.2).
local Modes = {
    { id = "slayer", engine = "slayer", slot = 0, name = "SLAYER",
        description = "Free for all. Every kill scores a point; the first to the score limit wins." },
    { id = "team_slayer", engine = "slayer", slot = 2, name = "TEAM SLAYER", teams = true,
        description = "Red against Blue. Kills score for your team." },
    { id = "ctf", engine = "ctf", slot = 1, name = "CTF", teams = true, scoreHeading = "CAPTURES",
        description = "Take the enemy flag to your base.",
        needs = "pakchunk990-MJOLNIRFLAGB_P" },
    { id = "oddball", engine = "oddball", slot = 4, name = "ODDBALL",
        description = "Hold the skull to score." },
    { id = "team_oddball", engine = "oddball", slot = 4, name = "TEAM ODDBALL", teams = true,
        description = "Red against Blue. Time with the skull scores for your team." },
    { id = "juggernaut", engine = "oddball", family = "juggernaut", slot = 4, name = "JUGGERNAUT",
        description = "The first kill makes you the Juggernaut. Kill the Juggernaut to take over; only the Juggernaut's kills and kills on the Juggernaut score." },
    { id = "stalker", engine = "oddball", family = "juggernaut", slot = 4, name = "STALKER",
        description = "The first kill makes you the Stalker: invisible and fast, while everyone else takes half damage. Kill the Stalker to take over; only the Stalker's kills and kills on the Stalker score." },
    { id = "reverse_tag", engine = "oddball", family = "juggernaut", slot = 4, name = "REVERSE TAG",
        description = "The first kill makes you it. Whoever is it moves slowly and scores a point a second; kill them to take over." },
    { id = "koth", engine = "koth", slot = 3, name = "KING",
        description = "Hold the hill to score. The hill stays where it is." },
    { id = "crazy_king", engine = "koth", slot = 3, name = "CRAZY KING",
        description = "Hold the hill to score. Every minute the hill moves somewhere new." },
    { id = "team_koth", engine = "koth", slot = 3, name = "TEAM KING", teams = true,
        description = "Red against Blue. Hold the moving hill to score for your team." },
    { id = "race", engine = "race", slot = 6, name = "RACE", scoreHeading = "LAPS",
        description = "Touch the flags in order. Each full circuit is a lap." },
    { id = "team_race", engine = "race", slot = 6, name = "TEAM RACE", teams = true, scoreHeading = "LAPS",
        description = "Red against Blue. Every lap scores for your team." },
    { id = "rally", engine = "race", slot = 6, name = "RALLY", scoreHeading = "FLAGS",
        description = "One flag is live. Touch it first to score, and it moves." },
    { id = "team_rally", engine = "race", slot = 6, name = "TEAM RALLY", teams = true, scoreHeading = "FLAGS",
        description = "Red against Blue. Touch the live flag to score for your team." },
    -- Forge has no variant file: MJOLNIRLevelLoader starts the map under the
    -- sandbox engine, and MJOLNIRForge binds the editor's keys. It is offered
    -- on every map once MJOLNIRForge's native half and the CE runtime's
    -- monitor fix are installed. Its own slot, 5, tells fireteam clients to
    -- start the sandbox engine too (before 2026-11-01 it shared Slayer's 0,
    -- and Forge was host only).
    { id = "forge", engine = "forge", slot = 5, name = "FORGE", forge = true,
        description = "Turn into the Monitor and grab, move, duplicate and delete the map's objects.",
        needs = "pakchunk990-MJOLNIRFORGEMON_P" },
}

-- The tiles' names. The rows above are in menu order, and a tile sits where its
-- first offered row does.
local TILE_NAMES = { slayer = "SLAYER", ctf = "CAPTURE THE FLAG", oddball = "ODDBALL",
    juggernaut = "JUGGERNAUT", koth = "KING OF THE HILL", race = "RACE", forge = "FORGE" }

-- A tile's name where it has one line to itself: map select's tabs.
local TILE_SHORT_NAMES = { ctf = "CTF", koth = "KING" }

--- The file in the level loader's folder that names the match's exact variant.
Modes.CHOICE_FILE = "match_variant.txt"

-- What a listed engine brings with it. None of these needs anything a map has
-- to place beyond its engine's own (Juggernaut, Stalker and Reverse Tag only
-- spawn), and the released maps' lists predate them.
local DERIVED = {
    slayer = { "team_slayer", "juggernaut", "stalker", "reverse_tag" },
    koth = { "crazy_king", "team_koth" },
    oddball = { "team_oddball" },
    race = { "team_race", "rally", "team_rally" },
}

--- The row for `id`, or nil.
function Modes.byId(id)
    for _, mode in ipairs(Modes) do
        if mode.id == id then return mode end
    end
    return nil
end

--- The insertion point for `id`, or nil for a game type this Lobby lacks.
function Modes.slot(id)
    local mode = Modes.byId(id)
    return mode and mode.slot
end

--- `listed` (id -> true) with every variant its engines bring.
function Modes.derive(listed)
    for engine, ids in pairs(DERIVED) do
        if listed[engine] then
            for _, id in ipairs(ids) do listed[id] = true end
        end
    end
    return listed
end

--- `list` (offered rows) as tiles, in menu order: { id, name, short, variants }, one
--- per `keyOf(mode)`. A tile without its namesake (Juggernaut and its kin where
--- only Slayer is listed) goes by its first variant's name.
local function tilesBy(list, keyOf)
    local byKey, tiles = {}, {}
    for _, mode in ipairs(list or {}) do
        local id = keyOf(mode)
        if not byKey[id] then
            byKey[id] = { id = id, name = TILE_NAMES[id] or mode.name, short = TILE_SHORT_NAMES[id], variants = {} }
            tiles[#tiles + 1] = byKey[id]
        end
        local variants = byKey[id].variants
        variants[#variants + 1] = mode
    end
    for _, tile in ipairs(tiles) do
        if not Modes.position(tile, tile.id) then tile.name, tile.short = tile.variants[1].name, nil end
    end
    return tiles
end

--- One tile per engine: the six on an older UI container's screens.
function Modes.engines(list)
    return tilesBy(list, function(mode) return mode.engine or mode.id end)
end

--- One tile per family.
function Modes.families(list)
    return tilesBy(list, function(mode) return mode.family or mode.engine or mode.id end)
end

--- Where `id` sits in `tile`, or nil.
function Modes.position(tile, id)
    for i, mode in ipairs(tile.variants) do
        if mode.id == id then return i end
    end
    return nil
end

--- The tile in `tiles` holding `id`, or nil.
function Modes.tileOf(tiles, id)
    for _, tile in ipairs(tiles) do
        if Modes.position(tile, id) then return tile end
    end
    return nil
end

-- The variant each tile last showed, by engine, so a tile the host left
-- comes back to it. Only ever a draft: the game changes on SELECT.
Modes.memory = {}

--- The variant `tile` stands for while `current` is the choice: `current` when
--- it is one of the tile's, else the one the tile last showed, else its first.
function Modes.shown(tile, current)
    local at = current and Modes.position(tile, current.id)
    if at then return tile.variants[at] end
    local last = Modes.position(tile, Modes.memory[tile.id])
    return tile.variants[last or 1]
end

--- The choice after a click on `tile`: a click on the chosen tile moves to its
--- next variant, a click on another tile chooses what that tile shows.
function Modes.step(tile, current)
    local at = current and Modes.position(tile, current.id)
    local mode = at and tile.variants[at % #tile.variants + 1] or Modes.shown(tile, current)
    Modes.memory[tile.id] = mode.id
    return mode
end

--- The choice after a click on `tile`'s own name, where its variants have
--- buttons of their own: what the tile shows, so a second click changes nothing.
function Modes.open(tile, current)
    local mode = Modes.shown(tile, current)
    Modes.memory[tile.id] = mode.id
    return mode
end

--- The choice after a click on `mode`, one of `tile`'s variants.
function Modes.pick(tile, mode)
    Modes.memory[tile.id] = mode.id
    return mode
end

--- Name the match's variant for the level loader, as "CODE<TAB>id". `loaderDir`
--- has no trailing backslash.
function Modes.writeChoice(loaderDir, code, id)
    local path = loaderDir .. "\\" .. Modes.CHOICE_FILE
    local line = tostring(code) .. "\t" .. tostring(id) .. "\n"
    local old = io.open(path, "rb")
    if old then
        local same = old:read("*a") == line
        old:close()
        if same then return end
    end
    local f = io.open(path, "wb")
    if not f then return end
    f:write(line)
    f:close()
end

--- A client or joiner: the host's exact game type for map `code`. A PC without
--- the variant's file cannot run the host's rules, so that is logged, and
--- `Modes.missing` holds it for the lobby to say. The loader then falls back
--- to the slot. An id that is not one (an old host sends none) is ignored.
function Modes.follow(loaderDir, code, id, log)
    if type(code) ~= "string" or code == "" or type(id) ~= "string" or not id:match("^[a-z_]+$") then return end
    Modes.writeChoice(loaderDir, code, id)
    local have = id == "forge"
    if not have then
        local f = io.open(loaderDir .. "\\variants\\" .. id .. ".mglo", "rb")
        if f then f:close() end
        have = f ~= nil
    end
    if have then
        Modes.missing = nil
        return
    end
    if Modes.missing ~= id then
        log("the host's game type " .. id .. " has no variants\\" .. id .. ".mglo on this PC: "
            .. "update MJOLNIR in the launcher to play it")
    end
    Modes.missing = id
end

--- What a client's lobby says about `Modes.missing`, or "".
function Modes.missingNote()
    if not Modes.missing then return "" end
    local mode = Modes.byId(Modes.missing)
    return "THIS PC LACKS THE HOST'S GAME TYPE, " .. (mode and mode.name or string.upper(Modes.missing))
        .. "   /   UPDATE MJOLNIR IN THE LAUNCHER"
end

return Modes

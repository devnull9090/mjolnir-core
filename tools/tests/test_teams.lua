-- Run from the repository root with Lua 5.4, or Python + lupa:
-- python -c "from lupa import LuaRuntime; LuaRuntime(encoding=None).execute(open('tools/tests/test_teams.lua','rb').read())"
--
-- MJOLNIRLevelLoader's teams.lua (docs/game_modes.md 2.2 and 2.3): a flag's
-- team from its model variant, a player's team from the team component's
-- string, the enemy a first-person flag belongs to, the stand a flag at home
-- is pinned to, and where the blue flag's container is looked for. Loading
-- the module must not need UE4SS: nothing here defines its globals.
local Teams = dofile("mods/MJOLNIRLevelLoader/Scripts/teams.lua")

local function eq(actual, expected, label)
    assert(actual == expected, (label or "value") .. ": expected " .. tostring(expected) .. ", got " .. tostring(actual))
end

-- A flag's team is its tag's model variant: "blue" is blue, any other name
-- red, and no name yet (before the actor's first update) no team at all.
eq(Teams.flagTeam("blue"), "blue", "blue variant")
eq(Teams.flagTeam("default"), "red", "the red flag's variant")
eq(Teams.flagTeam("Blue"), "blue", "a name read back in another case")
eq(Teams.flagTeam("DEFAULT"), "red", "default in another case")
eq(Teams.flagTeam("red"), "red", "any other name")
eq(Teams.flagTeam(""), nil, "empty: not synced yet")
eq(Teams.flagTeam("None"), nil, "NAME_None: not synced yet")
eq(Teams.flagTeam("none"), nil, "none in another case")
eq(Teams.flagTeam(nil), nil, "no component")
eq(Teams.flagTeam(7), nil, "not a string")

-- The team component's string: the multiplayer half only.
eq(Teams.parseTeam("EBlamAllegianceTeam::None|EBlamMultiplayerTeam::Red"), "red", "red player")
eq(Teams.parseTeam("EBlamAllegianceTeam::None|EBlamMultiplayerTeam::Blue"), "blue", "blue player")
eq(Teams.parseTeam("EBlamAllegianceTeam::None|EBlamMultiplayerTeam::Green"), "green", "a third team")
eq(Teams.parseTeam("EBlamAllegianceTeam::Player|EBlamMultiplayerTeam::None"), nil, "on no team yet")
eq(Teams.parseTeam("EBlamAllegianceTeam::Player"), nil, "no multiplayer half")
eq(Teams.parseTeam(""), nil, "empty")
eq(Teams.parseTeam(nil), nil, "unreadable")

-- Only enemies pick a flag up, so the flag in first person is the enemy's.
eq(Teams.enemyOf("red"), "blue", "red carries blue")
eq(Teams.enemyOf("blue"), "red", "blue carries red")
eq(Teams.enemyOf("green"), nil, "no enemy outside two teams")
eq(Teams.enemyOf(nil), nil, "team unknown: no colour, not a default")

-- Stand teams as level files give them.
eq(Teams.standTeam("red"), "red", "named stand")
eq(Teams.standTeam("Blue"), "blue", "named stand in another case")
eq(Teams.standTeam(0), "red", "numbered stand 0")
eq(Teams.standTeam(1), "blue", "numbered stand 1")
eq(Teams.standTeam(2), nil, "no third stand")

-- A flag is pinned only by its own team's stand, within PIN_CM.
local stands = {
    { team = "red", pos = { 1000, 0, 100 }, yaw = 90 },
    { team = "blue", pos = { -1000, 0, 100 }, yaw = -90 },
}
eq(Teams.PIN_CM, 150, "pin radius")
eq(Teams.homeStand(stands, "red", { X = 1000, Y = 0, Z = 100 }), stands[1], "red flag on the red stand")
eq(Teams.homeStand(stands, "red", { X = 1100, Y = 50, Z = 120 }), stands[1], "red flag settled off its stand")
eq(Teams.homeStand(stands, "red", { X = 1149, Y = 0, Z = 100 }), stands[1], "just inside")
eq(Teams.homeStand(stands, "red", { X = 1151, Y = 0, Z = 100 }), nil, "just outside")
eq(Teams.homeStand(stands, "red", { X = 1000, Y = 0, Z = 260 }), nil, "above the stand counts in 3D")
eq(Teams.homeStand(stands, "red", { X = -1000, Y = 0, Z = 100 }), nil, "red flag dropped on the blue stand")
eq(Teams.homeStand(stands, "blue", { X = -990, Y = 10, Z = 100 }), stands[2], "blue flag home")
eq(Teams.homeStand(stands, "blue", { -990, 10, 100 }), stands[2], "a plain triple")
eq(Teams.homeStand(stands, nil, { X = 1000, Y = 0, Z = 100 }), nil, "no team, no stand")
eq(Teams.homeStand(stands, "red", { X = 1300, Y = 0, Z = 100 }, 400), stands[1], "a wider radius")
eq(Teams.homeStand(nil, "red", { X = 1000, Y = 0, Z = 100 }), nil, "no stands")
local numbered = { { team = 1, pos = { 0, 0, 0 } }, { team = 0, pos = { 50, 0, 0 } } }
eq(Teams.homeStand(numbered, "red", { X = 10, Y = 0, Z = 0 }), numbered[2], "a numbered stand, the flag's own")

-- The Paks folder from a mod's folder, for both store builds.
eq(Teams.paksDir("C:\\Games\\Halo Campaign Evolved\\Meteorite\\Binaries\\Win64\\ue4ss\\Mods\\MJOLNIRLevelLoader"),
    "C:\\Games\\Halo Campaign Evolved\\Meteorite\\Content\\Paks", "Steam layout")
eq(Teams.paksDir("D:\\XboxGames\\Halo- Campaign Evolved\\Content\\Meteorite\\binaries\\WinGDK\\ue4ss\\Mods\\MJOLNIRLobby"),
    "D:\\XboxGames\\Halo- Campaign Evolved\\Content\\Meteorite\\Content\\Paks", "Xbox layout, any case")
eq(Teams.paksDir("C:\\somewhere\\else"), nil, "not a game folder")
eq(Teams.paksDir(nil), nil, "no folder")

-- The launcher's hub state: the blue flag's container under its original
-- name, in a mod enabled in the active profile.
local stem = Teams.BLUE_FLAG_CONTAINER
eq(stem, "pakchunk990-MJOLNIRFLAGB_P", "the blue flag's container")
local function state(containers, enabled, active)
    return {
        active = active or "Default",
        profiles = {
            { name = "Default", entries = { { slug = "mjolnir-ce-runtime", enabled = enabled ~= false },
                { slug = "ce-blood-gulch", enabled = true } } },
            { name = "Other", entries = { { slug = "mjolnir-ce-runtime", enabled = true } } },
        },
        installed = {
            { slug = "ce-blood-gulch", containers = { "pakchunk990-MJOLNIRFLAGB_P_maps_only_in_name" } },
            { slug = "mjolnir-ce-runtime", containers = containers },
        },
    }
end
eq(Teams.hubMounts(state({ "pakchunk990-MJOLNIRFLAG_P", stem, "pakchunk990-MJOLNIRMOTL_P" }), stem), true,
    "a runtime pack with the blue flag")
eq(Teams.hubMounts(state({ "pakchunk990-MJOLNIRFLAG_P", "pakchunk990-MJOLNIRMOTL_P" }), stem), false,
    "a runtime pack from before the blue flag")
eq(Teams.hubMounts(state({ stem }, false), stem), false, "the runtime pack switched off")
eq(Teams.hubMounts(state({ stem }, false, "Other"), stem), true, "on in the active profile only")
eq(Teams.hubMounts(state({ stem }, true, "Missing"), stem), false, "no such profile: nothing mounts")
eq(Teams.hubMounts(state(nil), stem), false, "a record without its containers")
eq(Teams.hubMounts({}, stem), false, "an empty state")
eq(Teams.hubMounts(nil, stem), false, "no state")

-- The game types played by teams.
eq(Teams.TEAM_GAMES.ctf, true, "CTF is a team game")
eq(Teams.TEAM_GAMES.team_slayer, true, "Team Slayer is a team game")
eq(Teams.TEAM_GAMES.slayer, nil, "Slayer is not")

print("Teams: flag teams from model variants, player teams, the first-person flag's enemy, the pin "
    .. "rule, the Paks folder, the blue flag's container in the hub state")

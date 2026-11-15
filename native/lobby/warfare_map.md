The tactical map reads native simulation state; it does not reveal remote enemy positions to the Lua presenter.

`warfare_tactical_tick(tls, snapshot)` runs after the validated PWR/warfare simulation update. It gathers at most every 200 ms, walks at most 4096 native object-header slots, accepts at most 32 matching stock vehicles, and publishes an independently locked fixed-size snapshot. No UObject scan, allocation, filesystem operation, HS evaluation or gameplay mutation occurs in the collector.

`mjolnir_warfare_map_pump` is a separate exported Lua entry point. Call it only while the M overlay is open; it writes `warfare_map.txt` beside the existing native files using a temporary file and atomic replacement. The existing 2 Hz HUD pump is unchanged. A snapshot more than 1000 ms old is emitted as `ready 0`, `status -5`, with no markers. Invalid mode/world, disable, close and caught simulation exceptions clear the tactical snapshot.

Every file has this complete versioned form (all header fields mandatory):

```text
warfare-map 1
ready 1
status 2
instance 1234567890123456
tick 120
sampled_ms 1234567
layout 3
team 0
local_index 0
local_user 0
phase 2
score 12 8
bounds -1000 -1000 1000 1000
marker self 589824 0 -590.000 -130.000 90.000
marker base 0 0 -590.000 -130.000 0.000
end 2
```

The sample above illustrates syntax only; actual files include both bases, all three captures and the eligible live markers. `instance` is an opaque uint64 and should remain a string in Lua. Marker IDs are unsigned32-bit integers. Player IDs use the participant salt and absolute slot, so unit respawns retain the participant ID; object IDs are exact salted vehicle handles. Base IDs are 0/1, capture IDs 0/1/2. Key markers by kind and ID. Kinds are `self`, `player`, `hog`, `tank`, `banshee`, `pelican`, `base`, `capture`.

Coordinates are authored metres, +X east and +Y north. Heading is degrees from +X toward +Y, in [-180,180]. A rider uses the parent's world origin and forward direction instead of relative seat coordinates. A nearly vertical direction has heading0. The marker bound is64; the current maximum from16 players+32 vehicles+5 fixed markers is53. A parser must validate the final `end` count, completeness, finiteness, bounds, uniqueness and advancing instance/tick/sample time before updating the overlay. Do not infer the current world from a stale file alone.

Status2 means ready. Status1 means inactive/unavailable. Status-2 means no unique valid primary local viewpoint; -3 means invalid bounded input; -5 means expired at pump time. When not ready, no markers are valid. Primary local_user0 is preferred; user1 is used only when user0 is absent. An unassigned primary local team does not fall back to a remote player's team. This initial presenter exports one local viewpoint, not separate split-screen views.

Only alive same-team player units are exported. Native health is section0 current vitality at the validated object damage-section offset, following the existing game-state reader. Salt, allocation size, section bounds, presence and finite positive vitality are checked. No guessed unit-health float or corpse location is used.

Empty ground vehicles are public/neutral (team-1). An occupied vehicle is shown as friendly only when every biped occupant resolves to a same-team player. Enemy/unknown occupants, broken salted links, cycles, more than64 direct children, and mixed teams hide the vehicle. A second player-parent pass catches an incompletely replicated child list. Attached cannon/weapon children do not count as passengers. An empty host Pelican is shown only if the established carrier handle binds it to the local team; on clients an unbound empty Pelican remains hidden until friendly occupancy proves it. Known enemy-team Pelicans stay hidden. Both fixed team bases and all capture ownership are intentional public information; capture owner0/1/2 maps to team-1/0/1.

The tactical resolver permits a bounded host self-index in replicated object headers while validating the local occupied slot and salt. The existing `fd_object` helper still requires self-index equality, a separate known remote insertion limitation; this feature does not alter that shared helper or claim new remote insertion acceptance.

Validation: `powershell -NoProfile -File native/lobby/test-warfare-map.ps1`, the existing `test-warfare.ps1`, and full `cl /W4 /WX /MD /Zs native/lobby/mjolnir_lobby.c` passed before handoff. Live map rendering, native pump output, occupied friendly/enemy vehicles and a second machine remain runtime acceptance tasks.

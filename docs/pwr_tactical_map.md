# Pelican Warfare tactical overview

Press **M** during Pelican Warfare to open or close the north-up map. It shows
your heading, living teammates, available and friendly occupied Warthogs,
Scorpions and Banshees, the friendly Pelican, both bases, and capture sites A–C
with their current owners. The side panel shows the control score and legend.
The map remains a read-only overlay; movement and the match continue.
Press **N** while it is open to cycle the full overview, 2× and 4× views.
Zoomed views follow your position; map edges are clamped to the actual terrain.

Chat, chat rules, pause menus and a hidden HUD suppress the map. It closes on
travel and at the end of a match. Enemy players and enemy occupied vehicles
are excluded by native code; known base locations and capture ownership are
public. Unknown vehicle occupants are treated conservatively. Empty vehicles
use neutral icons. Dead bodies do not appear as teammates.

The background is generated from the shipped runtime heightfield, graded road
polygons, water mask, actual tree positions and base geometry. Its extent is
the 2 km × 2 km playable terrain; decorative distant mountains are outside it.
Authoring/native metre coordinates map to `u=(x+1000)/2000`,
`v=(1000-y)/2000`. The image and markers share those exact bounds. The source
and reproducible generator are in `levels/warfare/pwr/tactical-map`.

`native/lobby/warfare_map_core.h` implements the bounded visibility policy;
`warfare_map.h` reads salted native simulation handles at 5 Hz. The native
map pump publishes a versioned snapshot only while the overlay requests it.
The existing 2 Hz warfare HUD protocol remains unchanged. Lua only parses and
places a fixed pool of 64 UMG icons; it performs no world actor scans or gameplay
writes. Two advancing snapshots from the HUD's current match instance are
required, and stale samples clear the icons.

The standalone widget builder is
`unreal/MJOLNIRMaterials/Scripts/build_pwr_tactical_map.py`. Chunk 958 owns
`/Game/MJOLNIR/UI/WBP_MJOLNIRTacticalMap` and the eight overview and marker
textures under `/Game/MJOLNIR/TacticalMap`. The class-lifetime allowlist retains its Blueprint
class across travel, as for the existing HUD. Temporary hiding reuses the same
widget pool.

After the widget import and Unreal cook, run
`python levels/warfare/pwr/tactical-map/package.py` to verify the generated
class, marker pool and textures and stage chunk 958 under
`out/pwr/tactical-map-ui-v2/cooked`.

Validation commands:

```powershell
powershell -File native/lobby/test-warfare-map.ps1
lua tools/tests/test_tactical_map.lua
lua tools/tests/test_ui_class_lifetime.lua
```

Live verification must include M toggle/reopen, movement and heading updates,
chat/pause suppression, vehicle positions, capture ownership, and map travel.
Multiplayer teammate filtering has portable regression coverage; a live remote
teammate requires a second connected player and should be reported separately.

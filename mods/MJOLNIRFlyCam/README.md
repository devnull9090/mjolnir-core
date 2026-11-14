# MJOLNIR FlyCam

FlyCam detaches an Unreal camera for screenshots and video. `F8` toggles it.
While it is on, the player stands still: the game's HUD, MJOLNIR HUD and
first-person gun/arms are hidden, and WASD and the mouse fly the camera the way
the Forge Monitor flies, without moving your Spartan.

## Controls

| Key | While FlyCam is on |
| --- | --- |
| **F8** | FlyCam on / off |
| **W A S D** (or numpad 8 4 2 6) | Fly where you look / strafe |
| **Space**, **E** (numpad 9) | Up |
| **C**, **Q** (numpad 3) | Down (not Left Ctrl, which is the save modifier) |
| **Shift** / **Left Alt** | Fast (×3) / slow (×¼) |
| **Mouse wheel**, numpad **+ / −**, **] / [** | Base speed up / down (starts at 750 cm/s, about the Monitor's) |
| **Z** / **X** (hold) | Zoom in / out (field of view, 5–170°) |
| **R** | Field of view back to 90°, roll to 0 |
| **1**–**9**, **0** | Jump to shot 1–10 |
| **Ctrl + 1**–**9**, **0** | Save the current view as shot 1–10 |
| **Tab** (hold) | Show the shot list and the camera's coordinates |
| **F6** | Pin the shot list on screen until F6 again |
| **F7** | HUD on / off |
| **F9**, numpad **0** | Mouse look on / off |
| numpad **5** | Snap the camera to the player |

Mouse look slows as you zoom in, so a narrow lens stays easy to aim. Starting
and stopping eases in and out over a fraction of a second.

The shot list is a plain text panel that is off unless Tab is held or F6 pins
it, so it is never in a screenshot by accident. Recalling a shot from the
console (`mjolnir_camera go`) unpins it.

### How the player stays still

The Spartan is a unit in the original Blam simulation, which reads its own
copy of the keyboard and mouse; nothing on the Unreal side stops it. FlyCam's
native half, `native/mjolnir_flycam.dll` (source in
[`native/flycam`](../../native/flycam/mjolnir_flycam.c)), blanks the
simulation's input while FlyCam is on and gives it back when FlyCam goes off.
Unreal still sees every key, which is what the camera flies on. If the DLL is
missing or a game update moves the code it looks for, FlyCam says so when it
turns on (`PLAYER NOT LOCKED` in the shot list) and still works, but WASD then
moves the player too; use the numpad.

The Forge Monitor itself cannot be used for this outside a Forge game: it is
a simulation unit that exists only under the sandbox (Forge) engine and with
the Monitor pack, and it has no field of view and does not survive a level
change. FlyCam copies its feel instead.

## Shots

A shot is a camera position, rotation and field of view with a number from 1
to 99 and an optional name. Shots are saved per map, so the same numbers work
on every build of that map — the remaster and the original — for before/after
comparisons. Each map has one JSON file in the game's Saved folder:

```text
%LOCALAPPDATA%\Meteorite\Saved\MJOLNIR_FlyCam_shots_<MAP>.json
```

```json
{
  "version": 1,
  "map": "ZAN",
  "shots": [
    {"n": 1, "name": "overview_east", "x": 6000, "y": -2000, "z": 5000, "pitch": -20.898, "yaw": -180, "roll": 0, "fov": 80}
  ]
}
```

Coordinates are Unreal world centimetres and degrees; `fov` is the horizontal
field of view. The file is re-read on every command, so it can be edited by
hand or by a tool while the game runs. A file FlyCam cannot read is reported
and never overwritten. The map code is the running scenario's codename (`ZAN`
for Zanzibar), else the world's name.

From the Unreal console (`~`) or the project's bridge (`game_console`):

```text
mjolnir_camera shots                 list this map's shots
mjolnir_camera save                  save the view as the lowest free number
mjolnir_camera save 4                save it as shot 4 (keeps shot 4's name)
mjolnir_camera save 4 tower          ... and name it
mjolnir_camera save tower            save over the shot called tower, or as a new number
mjolnir_camera go 4                  jump to shot 4 (or: go tower)
mjolnir_camera delete 4              delete shot 4; other numbers stay put
mjolnir_camera map                   show the map code (map ZAN / map auto to override)
```

`go` turns FlyCam on with no blend if needed and treats the jump as a camera
cut, so motion blur and temporal anti-aliasing do not smear the previous view
into the new one. Leave it a couple of seconds before capturing so streaming
and exposure settle.

Composing a view without keys:

```text
mjolnir_camera pos X Y Z             place the camera (cm)
mjolnir_camera rot PITCH YAW ROLL    aim it (degrees)
mjolnir_camera move FWD RIGHT UP     nudge it, camera-relative (cm)
mjolnir_camera look DYAW DPITCH      turn it (degrees)
mjolnir_camera fov DEG               field of view
mjolnir_camera speed CM_PER_S        base flying speed
mjolnir_camera where                 print the pose, map and lock state
mjolnir_camera body hide|show        hide the player's own body from the camera
mjolnir_camera overlay on|off        pin / unpin the shot list
mjolnir_camera lock                  the input lock's state
```

### Before/after captures

[`tools/flycam/capture.mjs`](../../tools/flycam/capture.mjs) recalls each
shot and captures it at full resolution without taking the desktop's focus;
[`tools/flycam/compare.py`](../../tools/flycam/compare.py) compares two
folders of captures and writes side-by-side pairs:

```bash
node tools/flycam/capture.mjs captures/zan-remaster --hide-body
node tools/flycam/capture.mjs captures/zan-original --hide-body
python tools/flycam/compare.py captures/zan-original captures/zan-remaster --side-by-side captures/zan-pairs
```

Two captures of the same build land on identical framing (tested on ZAN: zero
pixel shift on all ten shots across a game restart). What still differs is
whatever moves on its own — water, wind in the grass, turning machinery,
particles — so expect a few percent of pixels to change even between two runs
of one build. Use the same window size for both builds. The player's body
appears in a shot it stands in; `--hide-body` (or `body hide`) removes it.

## Named poses and camera paths

The older named poses still work and are kept in
`%LOCALAPPDATA%\Meteorite\Saved\MJOLNIR_FlyCam_poses.txt` (shared across
maps, so use map-prefixed names):

```text
mjolnir_camera capture entrance_a
mjolnir_camera set tst_entrance_b 3000 2000 250 0 90 0 80
mjolnir_camera goto entrance_a
mjolnir_camera list | reload
```

Names start with a letter and use letters, digits, `_` or `-`. A corrupt or
incomplete record makes save/reload fail without overwriting earlier records.

A path flies between two to 32 shots or poses:

```text
mjolnir_camera play 8 smooth 1 4 tower
mjolnir_camera stop
```

The number is **seconds per segment**. `linear` moves at constant speed;
`smooth` eases in and out at each point. Location, field of view and each
angle are interpolated along the shortest arc. Shot numbers and names are
looked up first, then poses. During playback the keys cannot move the camera;
`stop` leaves FlyCam at its current pose, and `F8` or `mjolnir_camera off`
cancels playback and restores the player view. Move times use the game tick,
so a game pause stops the camera. FlyCam itself does not record video; see
[`docs/game_automation.md`](../../docs/game_automation.md#silent-local-video-capture-experimental).

## Notes

- On a multiplayer host only the owning local player controller's tick moves
  the camera; if ownership cannot be verified, FlyCam stops rather than
  controlling another player. A level change turns FlyCam off and gives the
  player their input back.
- Tests that drive the player through the in-game input route
  (`mjolnir_test_input.dll`) must load it while FlyCam is off: it looks for
  the simulation's input slot untouched. Once it is loaded, FlyCam's lock
  works over it and blanks injected keys too.
- FlyCam reads its keys from Unreal's player input, which the Unreal console
  and chat box take over while open, so typing a number there should not jump
  to a shot.

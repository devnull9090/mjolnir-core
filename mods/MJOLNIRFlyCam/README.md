# MJOLNIR FlyCam

FlyCam detaches an Unreal camera for screenshots and video. `F8` toggles it;
the game's HUD, MJOLNIR HUD and first-person gun/arms are hidden while it is
enabled. `F7` toggles the HUD, `F9` or Numpad 0 toggles mouse look, numpad
8/2/4/6 moves, 9/3 moves vertically, and 5 returns to the player. Numpad +/−
or [/] changes speed and Shift boosts. **WASD and the mouse still control the
player through the Blam simulation**, so park the player safely while filming.

## Save camera poses

Open the Unreal console with `~`, or use the project's MJOLNIR Bridge to send
the same commands. Enable FlyCam, compose a shot and capture its pose:

```text
mjolnir_camera on
mjolnir_camera capture entrance_a
mjolnir_camera capture entrance_b
mjolnir_camera list
```

Move and reframe between the two capture commands. Names are case-sensitive,
start with a letter, and contain only letters, digits, `_` or `-`. The camera
stores position, rotation and field of view. They are appended as non-executable
text to `%LOCALAPPDATA%\Meteorite\Saved\MJOLNIR_FlyCam_poses.txt`; repeated
names replace the earlier value when loading. A corrupt or incomplete record
causes reload/save to fail without overwriting earlier records. The file is
shared across maps on this computer, so use map-prefixed names.

For a pose with known Unreal world coordinates (centimetres, rotation in
degrees, FOV in degrees), define it directly:

```text
mjolnir_camera set tst_entrance_a 1000 2000 250 0 90 0 80
mjolnir_camera set tst_entrance_b 3000 2000 250 0 90 0 80
mjolnir_camera goto tst_entrance_a
```

The final FOV is optional: it defaults to the current FlyCam FOV (90 before
FlyCam first activates). `goto` enables FlyCam if needed and cancels a running
path. `list` displays named coordinates in the console/UE4SS log; `reload`
re-reads the pose file and preserves current poses if the file is invalid.

## Record a move

With a map loaded, position the camera at the first pose, wait for the initial
view-target blend to settle, and start your screen recorder. Then play a path:

```text
mjolnir_camera goto tst_entrance_a
mjolnir_camera play 8 smooth tst_entrance_a tst_entrance_b
mjolnir_camera stop
```

The number is **seconds per segment**. `linear` moves at constant interpolated
speed; `smooth` uses smoothstep for an ease-in/ease-out at each pose. Both
interpolate location, FOV and each rotation angle along its shortest arc.
Add more saved names after the second to join up to 32 poses:

```text
mjolnir_camera play 6 linear tst_entrance_a tst_center tst_entrance_b
```

Each segment takes six seconds, for twelve seconds total in this example.
Linear paths can change direction abruptly at intermediate poses; smooth paths
come to rest there. For independent angles or longer holds, record separate takes
and cut them together in a video editor. Move times use the game tick, so game
pauses stop the camera and video capture frame rate is set by the recorder.

During playback mouse-look and numpad movement cannot alter the camera. `stop`
leaves FlyCam at its current pose; normal camera input resumes afterward.
Completing a path leaves it detached at the final pose. `mjolnir_camera off`
or `F8` cancels playback and restores the player view. A level change cancels a
path if the camera actor is lost. This uses the existing game-thread tick hook;
it does not dispatch per-frame asynchronous Lua tasks. On a multiplayer host,
only the owning local player controller's tick advances the path; remote-player
ticks are ignored. If ownership cannot be verified, FlyCam stops rather than
controlling an arbitrary player. This does not intercept player movement input.

The feature is source implementation with offline tests; it still needs a live
game check on the installed build. It does not record or assemble video itself.

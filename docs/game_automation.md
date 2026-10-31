# Driving the Game From Outside

**Status:** Working. Verified end to end on 2026-07-27 against
`2026.06.26.1097863.1-Rel-i343-Meteorite-2606-CU2` (Steam).

> **Build label:** this note is stamped CU2; the installed build is CU4
> (`2026.08.11.1121610.2-Rel-i343-Meteorite-2607-CU4`). The tools have driven CU4 since
> 2026-08-18; the Hazards below say what changed. See [`build_lock.md`](build_lock.md) for
> what else has been re-verified against CU4.

Every experiment in this repository used to end at the same place: build the thing, then sit in
front of the game and type at it. Load a level, alt-tab, run a command, read a number off the
screen, write it down. That is slow, it is easy to get wrong, and it means no experiment can be
repeated cheaply enough to be worth repeating.

This is the fix. The game becomes something a tool can drive: launch it, start a mission, run
console commands, evaluate Lua inside the process, send keys and mouse, and take screenshots.

## The shape of it

Three transports, because no single one reaches everything.

| | Reaches | Where |
|---|---|---|
| **Bridge mod** | Lua and console commands inside the process | [`mods/MJOLNIRBridge`](../mods/MJOLNIRBridge/Scripts/main.lua) |
| **capture.ps1** | What is on screen | [`tools/mcp/game/capture.ps1`](../tools/mcp/game/capture.ps1) |
| **input.ps1** | Menus, anything needing real input (player movement unverified on CU4, see Hazards) | [`tools/mcp/game/input.ps1`](../tools/mcp/game/input.ps1) |

[`tools/mcp/game/game.mjs`](../tools/mcp/game/game.mjs) is the tools themselves.
[`server.mjs`](../tools/mcp/game/server.mjs) serves them over MCP and
[`cli.mjs`](../tools/mcp/game/cli.mjs) runs them from a shell. Both are thin, so anything one
can do the other can too — which matters when something breaks and you need to run a single
step by hand.

**Prefer the bridge over screenshots.** A value read by reflection is exact. A value read off
pixels is a guess about pixels, and the guess is usually right, which is what makes it
dangerous.

## Setup

```bash
node tools/mcp/game/cli.mjs status
```

If it says the bridge mod is not installed:

```powershell
.\scripts\install-bridge.ps1
```

That copies the mod into the game's UE4SS `Mods` folder, enables it in `mods.txt` above the
`Keybinds` entry that has to stay last, and creates the directory the bridge talks through.
Nothing shipped is modified; deleting the mod folder and its `mods.txt` line undoes all of it.
Re-run it after editing the Lua — UE4SS reads mods from disk at startup, so copy and restart is
the whole edit loop.

The tools find a Steam install from Steam's own library index. Set `MJOLNIR_GAME_DIR` for any
other; for the Xbox app (Game Pass) it is the install's `Content` folder, whose binaries are
`WinGDK`. `install-bridge.ps1` handles Steam (`Win64`) installs only.

`.mcp.json` registers the MCP server. Claude Code loads it at session start, so a session
already running will not see it until it restarts.

## The tools

| Tool | Does |
|---|---|
| `game_status` | Install, process, bridge heartbeat, current world and pawn |
| `game_launch` | Start it and wait until the bridge answers |
| `game_quit` | Close it |
| `game_display` | Window mode, or restore the user's own settings |
| `game_console` | A UE console command through the local `PlayerController` |
| `game_lua` | Evaluate Lua on the game thread, return what it printed |
| `game_travel` | `open` a level — see the hazard below |
| `game_screenshot` | Photograph the window |
| `game_input` | Keyboard and mouse: key, hold, mouse button, relative `move`, absolute `click`, `wait` steps |
| `game_log` | Tail `UE4SS.log` |

`game_lua` is the one that matters. Tag values, ammo, pawn state and loaded assets are all
reachable by reflection but not through any fixed command, so the useful shape is an eval rather
than a menu of verbs. Helpers are pre-bound: `mj.pc()`, `mj.pawn()`, `mj.world()`,
`mj.find(class)`, `mj.props(obj)`, `mj.name(obj)`, `mj.console(cmd)`. UE4SS reflection —
`FindAllOf`, `StaticFindObject`, `FName` — is there too. The sandbox persists between calls, so
a helper defined once stays defined.

Long scripts come from stdin:

```bash
node tools/mcp/game/cli.mjs lua --timeout=60000 < scan.lua
```

## The wire

UE4SS's Lua has no sockets, so the bridge uses files both sides can open, in
`<install>/Meteorite/Binaries/Win64/ue4ss/mjolnir-bridge/`. Length-prefixed bodies, LF only, so
a body can contain anything including the header delimiter:

```
mjolnir-bridge 1
id 42
op lua
bytes 17
--
print("hello")
```

`request.txt` in, `response.txt` out, and `status.txt` as a heartbeat written about once a
second. The heartbeat is what makes failures legible: `now` is stamped by the poll thread and
`refreshed` by the game thread, so the gap between them says whether the game is hung, loading,
or fine. A caller that times out can tell the difference between "the mod is not loaded" and
"the game thread is busy", which are very different problems.

## What is verified

Run on 2026-07-27, in this order, all of it without touching the keyboard:

1. `game_launch` → Steam → title screen, bridge answering in about 90 seconds.
2. `game_screenshot` → the title screen, captured by `PrintWindow` **without stealing focus**.
3. `game_input` Enter, Enter → through login and into mission A30 from the resume slot.
4. `game_lua` → 37,409 loaded objects enumerated, pawn and world named.
5. `game_console` → `stat fps`, dispatched via the Kismet fallback, visible in the next capture.
6. `game_input` → fire and reload, and the HUD reflected it.

The capture path is worth calling out, and the 2026-07-27 reading of it was too generous.

**`PrintWindow` captures the UI layer only — the 3D scene comes back black.** Verified
2026-08-03 in a live A30 mission: the default capture returned a correct HUD (objective text,
reticle, radar, ammo) over a completely black frame, while `game_screenshot` with
`foreground: true` — the `CopyFromScreen` path — showed the actual forest, cliffs and weapon
model in the same instant. The D3D12 swapchain is not in what `PrintWindow` composites; Slate is.

This matters more than it sounds, because a black frame with a working HUD reads exactly like a
rendering failure in the game. It cost the custom-world investigation a documented "runtime-
spawned geometry does not render" dead end that was never real. **When a capture is meant to
show the world rather than the interface, pass `foreground: true`** and accept the focus steal.
`CopyFromScreen` needs the window genuinely frontmost; if the frame comes back showing desktop
or another window, send any `game_input` step first to raise it, then capture.

Screenshots are for looking at the world. For anything countable, `game_lua` is exact.

Screenshots default to **800 px wide**, from a game launched at 1280x720. Cost scales with area,
so the difference between 800 and 1600 is four times the tokens for the same frame; 800 is still
comfortably enough to read HUD counters. Raise `max_width` for genuinely small text.

### Silent local video capture (experimental)

For a moving-camera study, `tools/mcp/game/record_game.py` records the visible game
client rectangle to a local MP4. It uses FFmpeg's `gdigrab` desktop source because
this game's D3D12 world is not reliably present in window-DC capture. It selects
the game's `UnrealWindow` by class and process, as `capture.ps1` does, and checks
that the window remains in the foreground at the same position and size. It
does not change OBS, stream, capture audio, or draw the pointer. The existing
MJOLNIRFlyCam F8 control hides the HUD and first-person rig for clean footage;
F8 again restores them.

Install the optional FFmpeg executable only in the ignored working directory,
then create a new destination for each take:

```powershell
python -m pip install --target .dream-loop/video-deps imageio-ffmpeg==0.6.0
New-Item -ItemType Directory -Force .dream-loop/video-test | Out-Null
python tools/mcp/game/record_game.py .dream-loop/video-test/shot-001.mp4 `
  --duration 10 --fps 60 --encoder h264_nvenc --start-delay 5 `
  --ready-file .dream-loop/video-test/shot-001.ready.json
```

Switch to the game during the five-second delay and leave it visible and in
front until recording ends. Use `--encoder libx264` on a machine without a
working NVIDIA encoder. An explicit `--ffmpeg` path or a PATH installation may
be used instead of `video-deps`. The optional ready file is created only after
the first encoded frame; a camera driver can wait for that file before starting
its path. Use a fresh ready-file name per take and confirm the recorder is still
running: a ready file left by an interrupted take is not proof of success.

Output and ready files must not already exist. The recorder writes a uniquely
named partial MP4 first and publishes the requested name only after FFmpeg exits
successfully and a frame can be decoded. Losing focus, minimizing, moving or
resizing the game stops the recording and leaves the partial file for diagnosis.
The foreground check runs every 50 ms, so it is not a privacy boundary: system
overlays or notifications can appear in the recorded rectangle, and a brief focus
change may be captured before detection. Review a clip before sharing. Check the
actual image and frame cadence; requested FPS is not a guarantee, especially for
4K GDI capture under load. A private TST beta test recorded a HUD-free moving
camera at 1280×720 with NVENC and a 30 FPS request; framing was inspected at
several points. Higher resolutions, sustained frame cadence and other display
configurations still need verification.

## Hazards

**`open` from the frontend menu crashes the game — and solo-to-solo travel does too.**
Verified: `EXCEPTION_ACCESS_VIOLATION` reading `0x1c`, a couple of minutes into the load.
`open` skips the setup the campaign flow performs. `game_travel` refuses from the frontend
unless forced, but the 2026-08-02 resize experiment hit the identical crash travelling
`open a30` from *inside* mission A15, so treat solo-to-solo travel as unsafe too. Start
missions through the menus with `game_input`: the resume slot is two Enters from launch, and
mission select is Campaign → New Game → difficulty → mission → two Enters through the skulls
screen (Enter is "start" there — Space toggles the hovered skull, so keep the cursor off
Bandana). That was CU2. **On CU4 the frontend menu's items ignore Enter and take only the
mouse** (2026-08-18): use `{"click":[x,y]}` steps, which place the cursor absolutely in
window-client pixels, so scale up from the 800 px screenshot. Relative `move` steps go through
pointer acceleration and miss. The two-PC harness signs in with Enter, a click at the window
centre, then Space (`SIGN_IN` in [`tools/remote/jip-test.mjs`](../tools/remote/jip-test.mjs)).

The multiplayer notes had already flagged `mjolnir_travel` as unverified and recommended
reusing the official campaign flow. This is that prediction coming true.

**Long work on the game thread freezes the game.** Walking every property of all 37,000 loaded
objects ran past three minutes and the game was unresponsive throughout. It recovers, and the
heartbeat keeps ticking because the poll thread is separate, but scans should be narrowed to
candidate classes first.

**A hung game thread fails fast.** The game window belongs to the game thread, so
`game_screenshot` and `game_input` refuse when the heartbeat shows that thread 15 s behind,
rather than block on it. A capture script still running after 20 s is killed, and an input
script 20 s past its own waits and holds. A bridge call returns as soon as the game process is
gone, rather than waiting out its timeout.

**`game_input` steals focus, and needs an unlocked machine.** The game reads RawInput, which only
sees what the OS input queue actually delivered, so posted messages do not work and the window has
to be in front. Windows also refuses `SetForegroundWindow` to a process that does not already own
the foreground, so the tool taps Alt and attaches to the foreground window's input queue to get
around it, retrying as the window settles.

None of that helps if the workstation is **locked, on a screensaver, or a disconnected Remote
Desktop session**: the interactive desktop is switched away, `GetForegroundWindow` returns 0, and
no synthetic input can reach the game. RDP is the one that bites in practice — the session locks
on idle timeout, and since the automation is doing the work nobody is touching the machine to keep
it alive. Expect to hit this on any run longer than the timeout.
`game_input` reports this as a focus warning rather than pretending it worked. Screenshots keep
working throughout, because `PrintWindow` does not need focus — so a locked machine looks like
"I can see the game but cannot touch it".

**Player movement through `game_input` is unverified on CU4.** The fire-and-reload run above was
CU2. A CU4 session on 2026-09-11 recorded `game_input` as driving menus only and left player
movement to be tried by hand, but its explanation (gameplay reads GameInput, which never sees
injected keys) was overturned on 2026-10-17, when Blam turned out to take its keys from the game
viewport. Whether injected keys move the player is open. Do not judge it by `mj.pawn()`: that is
the UE pawn, whose location stays constant, so it cannot show whether the player moved. A player
who does not move under `game_input` says nothing about the map; check at a real keyboard.

~~There is no reflection-driven substitute yet.~~ **Superseded 2026-08-02:** there is one.
`BlamCampaignFlowGameSubsystem:SetAndBeginCampaign(Campaign, ScenarioName, Options)` starts a
mission from pure reflection — verified launching A15 from the frontend and traveling A15→A30
mid-mission on CU3. It validates assets synchronously and returns `false` instead of crashing
when a world is missing, which also retires the frontend-`open` hazard for mission starts. The
game's own hidden debug menu (`WBP_MainMenu:OnToggleDebugMenu`) drives the same path. See
[`multiplayer_investigation_notes.md`](multiplayer_investigation_notes.md) for the full recipe;
`mjolnir_mission` in `MJOLNIRMultiplayer` wraps it.

**Update 2026-10-21:** on CU4 (found 2026-08-19), from the frontend, `mjolnir_mission` is
accepted and the world loads, but the Blam session never comes up and the mission never starts
([`multiplayer_investigation_notes.md`](multiplayer_investigation_notes.md)); `mjolnir level
bake` prints the same warning. So the frontend hazard stands for cold starts: start campaign
missions through the game's own menu with `game_input` clicks. Multiplayer maps start from
MJOLNIRLobby (see "Matches and a second PC" below).

**Ammo is not in UE reflection.** Neither the pawn, the first-person weapon actor, nor any HUD
object holds the round counts the HUD displays; a scan for the literal reserve value across
every loaded object found nothing. It lives in the Blam simulation, consistent with tag payloads
being opaque blobs parsed natively. Read it from a screenshot, or find the native path.

**`game_launch` edits `GameUserSettings.ini`** to force windowed mode, because that is the only
lever that works whatever route the game starts by — Steam's `rungameid` URL is not a reliable
way to pass `-windowed`. The original is copied to `GameUserSettings.ini.mjolnir-backup` on the
first change; `game_display` with `mode: restore` puts it back.

**The Steam app id is 2806050**, per `apps/launcher` and Steam's own `appmanifest_2806050.acf`.
The README carried 2993530 for a while, which is a different app and gets "game not found" on
launch; it has been corrected.

## Matches and a second PC

MJOLNIRLobby answers `mjolnir_auto <verb>` at the console and writes its answer to
`native\auto_state.txt` in the mod's folder, so a script can host and join without anyone at
the menus: `state`, `host <CODE> <mode> [private]`, `public on|off`, `join [host]`,
`download <CODE>` and `install <CODE>`. `host` lists the game publicly unless given `private`,
and a listed game is joinable by anyone on the hub, so solo tests use `private`.

[`tools/remote/remote.mjs`](../tools/remote/remote.mjs) drives a second PC's game through
[`tools/remote/mjolnir-agent.ps1`](../tools/remote/mjolnir-agent.ps1) running there: status,
Lua, console, input, `mjolnir_auto` and files, over the LAN with a token (`MJOLNIR_REMOTE` and
`MJOLNIR_REMOTE_TOKEN`, or `%USERPROFILE%\.mjolnir-remote.json`).
[`tools/remote/jip-test.mjs`](../tools/remote/jip-test.mjs) runs the two-PC join-in-progress
test end to end with both.

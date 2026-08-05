# Driving the Game From Outside

**Status:** Working. Verified end to end on 2026-07-27 against
`2026.06.26.1097863.1-Rel-i343-Meteorite-2606-CU2` (Steam).

> **Build label:** this note is stamped CU2; the installed build is CU3. See
> [`build_lock.md`](build_lock.md) for what has been re-verified against CU3 and for a
> caveat about CU2-stamped notes dated after 2026-08-01.

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
| **input.ps1** | Menus, movement, anything needing real input | [`tools/mcp/game/input.ps1`](../tools/mcp/game/input.ps1) |

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
| `game_input` | Keyboard and mouse |
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

The capture path is worth calling out. `PrintWindow` with `PW_RENDERFULLCONTENT` returns real
frames from this D3D12 title, so screenshots do not need the window focused or on top. The
`CopyFromScreen` fallback exists for when that stops being true, and the blankness check decides
between them on evidence rather than assumption.

Screenshots default to **800 px wide**, from a game launched at 1280x720. Cost scales with area,
so the difference between 800 and 1600 is four times the tokens for the same frame; 800 is still
comfortably enough to read HUD counters. Raise `max_width` for genuinely small text.

## Hazards

**`open` from the frontend menu crashes the game — and solo-to-solo travel does too.**
Verified: `EXCEPTION_ACCESS_VIOLATION` reading `0x1c`, a couple of minutes into the load.
`open` skips the setup the campaign flow performs. `game_travel` refuses from the frontend
unless forced, but the 2026-08-02 resize experiment hit the identical crash travelling
`open a30` from *inside* mission A15, so treat solo-to-solo travel as unsafe too. Start
missions through the menus with `game_input`: the resume slot is two Enters from launch, and
mission select is Campaign → New Game → difficulty → mission → two Enters through the skulls
screen (Enter is "start" there — Space toggles the hovered skull, so keep the cursor off
Bandana).

The multiplayer notes had already flagged `mjolnir_travel` as unverified and recommended
reusing the official campaign flow. This is that prediction coming true.

**Direct-exe launch fails platform login and can never leave the title screen.** Verified 2026-08-04
on CU3. `Start-Process` on `HaloCampaignEvolved.exe` reaches the frontend and the bridge answers
normally, but pressing start raises

> **LOGIN FAILED** — We couldn't sign you in. Make sure you're logged into your platform account and
> try again. Error code: Alpha

and confirming it drops back to the title screen, indefinitely. Steam being already running does not
help; the game has to be started *by* Steam.

Earlier the same day this looked like a hang — not responding, one core spinning, ~6.5 GB resident —
because input could not be delivered at the time, so the modal was never seen or dismissed and the
attempts piled up against it. Two direct-exe runs behaved identically, one with extra command-line
arguments and one without (2124s vs 2139s CPU, 6496 MB vs 6505 MB), which ruled out the arguments
but wrongly implicated the launch route itself. The login dialog is the actual cause.

This is why `game_launch` defaults to `via: "steam"`. The `exe` route is only for work that never
leaves the frontend.

**To launch with command-line switches, use the Steam URL.** `game_launch` has no passthrough, and
direct-exe cannot get past login, so:

```powershell
Start-Process ("steam://run/2806050//" + [uri]::EscapeDataString("-YourSwitch=Value"))
```

Verified to deliver the argument intact. Confirm it arrived from inside the game rather than assuming
— otherwise "the switch did nothing" is indistinguishable from "the switch never arrived":

```lua
local ksl = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
print(ksl:GetCommandLine():ToString())
```

**Two reads of the same UObject property are not `==` to each other.** Reflection returns a fresh
wrapper per read, so identity comparison silently answers "different object" for the same object:

```lua
local a, b = comp.CurrentExperience, comp.CurrentExperience
a == b            --> false
```

Compare `GetFullName()` instead. A name is unique within a world, which is the only scope these
comparisons span. This is easy to miss because the wrong answer is plausible — a mod that checks
"did my value stick?" this way reports failure while working perfectly.

**There are two PlayerControllers in a loaded mission.** A pawnless `BP_FrontendPlayerController_C`
survives alongside the real `BP_MeteoritePlayerController_C`, **and it sorts first**. Taking
`FindAllOf("PlayerController")[1]` gets the frontend one, finds no pawn, and concludes there is no
player. Pick the controller that actually possesses something:

```lua
for _, pc in ipairs(FindAllOf("PlayerController") or {}) do
    if pc and pc:IsValid() and pc.Pawn and pc.Pawn:IsValid() then return pc end
end
```

**`mj.props()` on a Blueprint CDO with authored array data can kill the game.** The native
`Default__BlamExperienceDefinition` dumps fine. `Default__BP_BlamExperienceDefault_C` — the same
class with real content behind it — took the process down. Read named fields individually with
`pcall`, and prefer `GetArrayNum()` over stringifying an array whole.

**`StaticFindObject` returns a non-null garbage pointer for paths that do not exist, and reading
properties off one kills the process.** Verified 2026-08-04 on CU3. A loop that looked up
`/Script/<module>.<name>` for five module names and four class names printed `FOUND` for all
twenty combinations — including modules that plainly do not own those classes. The return value
is not a valid object; it is not null either. Calling `mj.props()` on one took the game down with
no Lua error, only a silent process exit and a `UECC-Windows-*` crash dump.

Always validate before touching the result:

```lua
local o = StaticFindObject(path)
local ok, full = pcall(function() return o and o:GetFullName() end)
if not (ok and full) then return end   -- not a real object, do not go further
```

A real hit prints a real full name (`Class /Script/BlamExperience.BlamExperienceDefinition`). A
phantom prints nothing, which is the tell — the crash above was preceded in the log by
`/Script/BlamExperience.Default__BlamExperienceSettings -> [no name]`.

Treat any conclusion drawn from an unvalidated `StaticFindObject` as worthless, including "class X
exists in module Y". Module membership in particular cannot be established this way.

**Long work on the game thread freezes the game.** Walking every property of all 37,000 loaded
objects ran past three minutes and the game was unresponsive throughout. It recovers, and the
heartbeat keeps ticking because the poll thread is separate, but scans should be narrowed to
candidate classes first.

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

There is no reflection-driven substitute yet. `BPFL_CampaignMenuHelpers` exposes lobby setters
(`SetClientLobbyMission`, `SetClientLobbyDifficulty`, `StartCountdown`) but no plain "start the
mission" entry point, so starting a mission still needs real input. Finding one would make the
whole harness immune to this, and is the single highest-value thing left to add.

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

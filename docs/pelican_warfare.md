# Pelican Warfare prototype

PWR uses the existing Blam simulation and native Megalo interpreter. Unreal
renders the authored map, objective fields and cosmetic parachute. Lua stages
the mode, handles a Space key event and presents a bounded native snapshot;
it does not implement movement, captures, respawns, scoring or match timers.

## Current alpine expansion

The v5 world has a **2 × 2 km playable terrain** with three Forerunner sites,
connected vehicle roads, four crossings, a descending river and a lake.
Its surrounding 8 km mountain field is a render-only backdrop. The gameplay
area has not expanded to 8 km. Gaea supplies eroded terrain; Unreal Landscape,
Nanite scenery and baked PCG instances render it. Blam retains authoritative
collision, vehicles and the native Warfare rules.

The current visual build uses `levels/warfare/pwr/upgrade-v5-visual5.json` and
the isolated `world-v5-visual5` conversion. Its forest contains 4,470 trees,
804 rocks and 279,388 grass instances. Water uses native Fluid Flux surfaces
and saved flow/depth/foam states; this is baked playback, not a map-wide
real-time fluid simulation. See [water integration](flux_water.md),
[surface materials](pwr_surface_materials.md),
[mature pine](pwr_mature_pine.md) and
[terrain preservation](pwr_terrain_preservation.md) for their build contracts.

The original basin commands and acceptance history below describe the first
prototype. Do not apply its `prepare_runtime.py` step to the expansion:
the expansion uses `refresh_native_probes.py` with
`vehicle-spawn-policy-v1.json` to preserve verified vehicle spawn heights and
bind probes to the newly compiled collision. Local installation receipts and
fresh native acceptance evidence live under `out/pwr/world-v5`.

## Play the installed preview

Select map **PWR / Pelican Warfare** and mode **PELICAN WARFARE** in the
MJOLNIR lobby, then start a private match. The installed preview starts with
one player after a five-second warmup. Press **Space** to leave the Pelican
and again to deploy the parachute. Exit from the Pelican is automatic at the end
of its flight; the parachute is not. A player who never pulls it, or pulls it
too late, meets the ground faster than 20 m/s and dies (`WARFARE_SPLAT_SINK`).
Stand on A, B or C on foot for fifteen seconds to capture a neutral site.
Owned uncontested sites score once per second. After a death you respawn at
your base and board your team's waiting Pelican, which leaves with everyone
aboard on the next minute of combat; the target is 500 control points.

## Rules and build

`mjolnir megalo write --mode warfare --vehicle-label-pool --out warfare.mglo`
builds the variant. Install it in `MJOLNIRLevelLoader/variants/warfare.mglo`.
The bundled `mode_descriptors.lua` registers the mode only for PWR and shares
its lobby, loader and scoreboard metadata. The installed variant controls
the score threshold; persisted settings from another mode cannot change it.
Warfare opts into a same-mode postgame rotation on its supported maps. With
only PWR installed, no ballots replay PWR Warfare; LOBBY returns to manual
map/mode selection. Other modes retain the existing mixed-map, mixed-mode vote.

Defaults are two connected players, 60 seconds of warmup, 60 seconds of
insertion, first to 500 control points, or 20 minutes of combat. The three
neutral `koth_hill` markers use spawn sequences 0, 1 and 2, matching the
three `koth_hills` entries in `level.json`. Living players on foot capture;
vehicle occupants do not. One side alone takes a neutral site in fifteen
seconds; changing an enemy site takes fifteen seconds to neutralize and
fifteen more to capture (`--capture-seconds`, 8 before 2026-11-22).
Covenant alone take a neutral site in thirty (`--covenant-capture-seconds`). Extra teammates do not accelerate capture. Opposing
presence stops capture and scoring. An owned empty site continues to earn
one point per second. Kills do not score. Each death respawns the player at
their permanent Red or Blue home after five seconds, with unlimited lives
and no suicide/betrayal delay; the native adapter then puts them aboard the
next reinforcement wave (see [waves and reinforcements](pelican_warfare_waves.md)).
A wave leaves every `reinforcement.interval_seconds` (60) of combat and flies
`flight_seconds` (30) of the insertion route, both from `layout.json`.

CLI flags allow explicit development variants: `--minimum-players`,
`--warmup-seconds`, `--insertion-seconds`, `--capture-seconds`,
`--warfare-minutes` and `--score`. The lobby's fixed settings describe the
shipped defaults; development timing variants are not editable lobby rules.

## Original basin build and installation

Run these commands from the repository root in PowerShell 7. They require
the project's existing Rust/MSVC, Python, Blender, HEK and Unreal 5.5 toolchains.
The commands use the Steam install and the PWR conversion/work directories
in `levels/warfare/pwr/upgrade.json`; change those explicit paths for another
installation. See [the PWR source README](../levels/warfare/pwr/README.md) for
the isolated HEK build and initial CE conversion that produce `pwr.level.json`.

Build the CLI, the map/canopy helper executables and both native DLLs:

```powershell
cargo build --release -p blam-cli
cargo build --release -p ue-asset --examples
cargo build --release -p blam-pack --examples
cargo build --release -p ue-iostore --example extract_file
pwsh -NoProfile -File native/lobby/build.ps1
pwsh -NoProfile -File native/map_registry/build.ps1
$env:MJOLNIR = (Resolve-Path target/release/mjolnir.exe).Path
$env:EXAMPLES = (Resolve-Path target/release/examples).Path
```

The `ue-asset` examples include `mesh_rewrite` and `retarget_package`; the
`blam-pack` examples include `package_add` and `native_material_clone`.
`extract_file` belongs to `ue-iostore`. Keep both environment variables set
in the PowerShell session used below: the bake stage otherwise defaults to
an older server-list worktree CLI and `C:/haloce/target/debug/examples`, which
can silently mix tools from different checkouts. Reapply these assignments
when resuming a stage in a fresh terminal.

The map-registry build also rebuilds and links `mjolnir-mglo-cabi`. It must
match the variant grammar in this checkout. Replacing only the Lobby DLL
leaves the installed map-registry staging validator at its old version.

Build the Pelican and original canopy into staging directories, then patch,
cook and assemble the map's private visual upgrade:

```powershell
$pwrGame = 'C:\Program Files (x86)\Steam\steamapps\common\Halo Campaign Evolved'
$pwrPaks = Join-Path $pwrGame 'Meteorite\Content\Paks'
pwsh -NoProfile -File tools/level/build_warfare_pelican.ps1 -Paks $pwrPaks -OutDir out/pwr/pelican
python levels/warfare/pwr/canopy/build.py --paks $pwrPaks --preview
python levels/warfare/pwr/prepare_runtime.py --level C:/haloce/ce_conversions/warfare/PWR/converted/pwr.level.json
python levels/warfare/pwr/upgrade.py --stages land,foliage,swap,collision
python levels/warfare/pwr/upgrade.py --stages editor,cook,bake,assemble
```

Current private container assignments are canopy 964, landscape 965 and
Pelican 971. The runtime installer takes the generated container names;
it does not hard-code a stale chunk number. Preserve the map's capture
markers, permanent team spawns and named flags when rebaking.

Close the game before installing. The map install is local and creates no
hub listing. The runtime installer copies the complete Loader, Lobby and HUD
`Scripts` trees, both native DLLs, the variant plus its layout and the staged
Pelican/canopy containers. This is a single compatible runtime: copying only
the new Warfare scripts onto an older release can leave missing helper APIs.

```powershell
python levels/warfare/pwr/upgrade.py --stages install --local-install
pwsh -NoProfile -File levels/warfare/pwr/install_runtime.ps1 -Game $pwrGame -SoloPreview
```

`-SoloPreview` builds a one-player, five-second warmup variant for the private
test. Omit that flag to restore the normal two-player, 60-second warmup.
The user's current local installation uses `-SoloPreview` with the default
500-point target, recorded in
[`out/pwr/runtime-20261108-224928/install-receipt.json`](../out/pwr/runtime-20261108-224928/install-receipt.json).
The five-point variants below were acceptance-test artifacts, not the final
installed score limit.
The installer writes `out/pwr/runtime-<timestamp>/install-receipt.json` and
backs up each replaced runtime file before copying it. Standalone variant
generation and validation, without installation, are:

```powershell
New-Item -ItemType Directory -Force out/pwr/variants | Out-Null
target/release/mjolnir.exe megalo write --mode warfare --vehicle-label-pool --out out/pwr/variants/warfare.mglo
target/release/mjolnir.exe megalo validate out/pwr/variants/warfare.mglo
target/release/mjolnir.exe megalo read out/pwr/variants/warfare.mglo
```

Launch and sign in at the frontend, then explicitly host a private PWR test:

```powershell
node tools/mcp/game/cli.mjs launch
node native/lobby/smoke-warfare.mjs --host --jump --respawn --capture-a --seconds=90
```

The probe waits for frontend sign-in and requests `host PWR warfare private`.
Its explicit flags request jump/deployment, kill the landed test player once
to verify respawn, and teleport that player to capture A. It writes JSONL
evidence under `out/pwr/`. To observe an already running match without those
actions, use `node native/lobby/smoke-warfare.mjs --seconds=50`.

After insertion, `node native/lobby/smoke-warfare-vehicles.mjs --drive --screenshots`
checks a private active layout-2 match with exactly one local player, then boards
the home fleet's Warthog, Scorpion and Banshee through the installed probe volumes.
It verifies each actual salted vehicle parent before four bounded one-second W
inputs and records body displacement and player/vehicle health. `--team=blue`
selects the other fleet; `--seconds=3..5` adjusts total input time.
`--banshee-ascend` additionally holds Space and requires upward displacement;
that input binding still needs a live check. The harness leaves the final
Banshee occupied, does not end the match, and makes no game calls without
`--drive`. JSONL evidence and optional screenshots go to `out/pwr/`.

## Native bridge and presentation

The loader requires level metadata `warfare: {protocol: 20569, layout_revision: 3}`
and opens `MJOLNIRLobby/native/mjolnir_lobby.dll` with a configuration
containing `warfare-config 2`, `map PWR`, `layout 3` and `protocol 20569`.
That number is the map's layout protocol; the Megalo rules publish their own
revision in slot 2 (20571), so a rules change needs no new map.
Its four exported Lua entrypoints
are `mjolnir_warfare_open`, `close`, `action` and `pump` (all with the
`mjolnir_warfare_` prefix). Space sends only a jump/deploy request. The native
adapter validates the simulation build, scenario, engine, instance,
Megalo protocol and the four baked flight endpoint positions before acting.
The endpoint check rejects an old PWR scenario even if its JSON was updated.
Movement remains on the owning simulation
peer; the host controls the named transports. Late joins and later
respawns board the next reinforcement wave from the home base.

Global number slots are phase 0, phase age in ticks 1, rules magic 20571
at 2, the clock 3, connected count before combat and the defeat clock from
combat on 4, scratch 5–6, Red/Blue
score 7–8 and A/B/C site states 9–11. Phases are warmup 0, insertion 1, combat 2
and complete 3. A site state packs `owner + 4 × (red present + 2 × blue present)
+ 16 × (progress + 17)`: owner neutral 0, Red 1, Blue 2 in the low two bits, and
capture progress in sixteenths toward Red (+16) or Blue (−16), counted against
thresholds fixed when the variant is built (`SiteState` in `warfare.rs`). Steps,
not ticks, keep the replicated value from changing every tick. A value under 16
is an owner alone (older variants, or before combat). Slot 3, the clock,
counts the warmup down in whole seconds in phase 0 (-1 while fewer than the
minimum players are connected), publishes the configured insertion duration
in phase 1, then resets to zero and counts combat seconds in phase 2; the
reinforcement schedule is derived from it, and the HUD shows it as MATCH TIME.
Phase, age, magic, clock,
scores, owners and slot 4 (the connected count, then the defeat clock) have high
replication priority,
and scratch remains local. Native code reads this state; Megalo owns it.
An absent team's native score operand is -1 in the supported build; the
published score mirror clamps that sentinel to zero without creating or
changing the absent team's engine score.

### The Covenant can win

If the Covenant hold all three sites (owner 3) for `covenant_hold_seconds`
(default 60; `mjolnir megalo write --covenant-hold-seconds`, 0 turns it off),
the match ends and both teams lose. Slot 4 carries it from combat on: the full
hold when combat starts, one less each combat second while every chosen site is
the Covenant's, back to the full hold the second any site is not, and -1 when
the rule is off. At 0 the host sets phase 3 and ends the round; the end trigger
checks the three owners again, so a stray 0 cannot end a match. The HUD's line
says THE COVENANT HOLD EVERY ZONE with the time left while it runs, OPERATION
FAILED at the end, and the post-game title is THE COVENANT WIN
(`Match.winnerTitle`, read by `Scoreboard.winner`). Rules revision 20571 began
this: the HUD and DLL reject an older variant, so HUD, DLL and variant ship
together.

`levels/warfare/pwr/layout.json` generates `native/lobby/warfare_layout.h`.
The native build regenerates it; the portable test runner rejects stale output.
Layout 2 uses a 2 km scenario, a ±950 m play area and 240 m flight altitude.
The host projects desired world velocity into the verified full 3D vehicle
axes, corrects bounded route/altitude error and caps speed at 30 m/s.
Default automatic exit occurs at 54 of 60 seconds; explicit development
durations scale the exit time without exceeding that speed cap. Descent
has a 90-second timeout and accepts settled landings at any height inside
the play volume. Slopes keep the canopy state until vertical movement settles.

The parachute opens only when the player pulls it; nothing opens it for them.
The descent stays protected from falling damage, and the host decides the
landing at the first real ground contact:
- if the descent controller's sink is above `WARFARE_SPLAT_SINK` (20 m/s), it
  sends `WF_SPLAT`, a host-authority `(unit_kill (player_get N))`;
- freefall reaches 55-63 m/s;
- a canopy settles at 10.5-18.5 m/s, so an open canopy always lands.

`test_warfare.c` covers the outcomes:
- with no pull, the 550 m exit hits at about 53 m/s after 10.7 s, at every
  tick rate;
- a pull 0.4 s out still dies;
- a pull 4 s out lands.
- a joiner under canopy lands on the host (`test_remote_landing`).

The splat is judged from the body's own last airborne sink, not the host's
simulation of the descent. The host is told only of a joiner's cabin jump,
never their parachute pull, so its controller copy stays in freefall; judged
from that, every joiner died on landing (caught in review before release).

Before 2026-11-24 the chute opened itself near 76 m; the user asked for the
fall to be the player's responsibility. Bots are AI bipeds, not players, and
never ride.
These expansion changes require live validation independently of the smaller
prototype's successful insertion tests recorded below.

The loader publishes `MJOLNIRLobby/native/warfare_state.txt` every 500 ms;
the HUD reads at the same interval. The `warfare-state 3` format includes
the reinforcement timing, layout revision and configured insertion duration.
The HUD checks the complete format,
ready/status flags, mirrored globals, exact uint64 instance text and current
PWR world. Two advancing tick/time samples are required before accepting
a file or a new instance. Live samples expire after two seconds without
advancing; a verified final snapshot remains usable during stopped postgame
and the engine's brief same-instance round reset before lobby travel.
Malformed or stale files cannot change score. Team CONTROL totals and the
winner come from accepted native scores, never summed player incidents.
Individual control cells show a dash; kills and deaths remain visible.
Final standings allow 1.5 seconds for the final publication to arrive.

The status line gives the warmup countdown, boarding, Space-to-jump, exiting,
Space-to-deploy, canopy, landing/active and failed-deployment information, and
for a waiting reinforcement rider the time to departure and whom they watch.
During insertion every line ends with ZONES OPEN IN 0:23 (from the published
insertion length and its tick count, `Warfare.insertionLeft`), and once a rider
has landed the line is ZONES OPEN IN 0:23 / PREPARE TO CAPTURE A, B AND C. The
last ten seconds of warmup, and of insertion, also count down large in the
middle of the screen (`warfare_countdown.lua`), then DEPLOY or CAPTURE for two
seconds. During combat it
gives way to three slim zone bars stacked in the top left (`WBP_MJOLNIRWarfareZones`,
chunk 958 beside the tactical map with its two hexagon badge textures from
`tools/ue/draw_zone_badges.py`, filled by `warfare_zones.lua`). Each row is a
hexagon badge with the zone's letter in the owner's colour (purple for the
Covenant), then the state word (NEUTRAL / RED / BLUE / COVENANT / CAPTURING /
NEUTRALIZING / UNDER ATTACK / OVERRUN / CLEARING / CONTESTED) with a pip for each
team standing in the zone, over the capture bar. The badge's outline turns gold on
the zone the local player stands in.
A site changing hands puts "Red team captured zone B" (or "… neutralized zone B")
in the kill feed on every client from its own snapshot. Three fixed holographic
fields and A/B/C waypoints still mark the sites in the world. Contest and progress
come from Megalo's published site state, never from rendered positions.

`warfare_canopy.lua` uses the original
`/Game/MJOLNIR/Maps/PWR/SM_PWR_Parachute.SM_PWR_Parachute` mesh, a 274.4 cm
relative Z offset and uniform scale 4.1166 from the canopy build metadata.
It disables collision and shadows and attaches once to an existing validated
cached biped. Unreal follows the attachment without a Lua movement loop.
Only native stage 4 displays it; landing, death, missing/stale state and map
exit hide it. Native drop stages currently exist for owning local players,
so remote canopy visibility needs a verified replicated stage channel before
it can be claimed. The cosmetic asset is optional for gameplay.

A loaded mesh is held only as a handle. Once no parachute uses it, the garbage
collector frees it, so a dead handle is loaded again. Before that fix, a
respawn's drop fell back to the legacy canopy (2026-11-24).

### Voice (local testing only)

`MJOLNIRHud/Scripts/warfare_voice.lua` gives Warfare two voices: Cortana talks
the player through the match, and the announcer names the game, the zones and
the result. Every line comes from a change between two accepted warfare
snapshots, inside the existing HUD tick, with no loop of its own. Each machine
decides from replicated state, so a joiner hears its own match:

| When | Who | Line |
|---|---|---|
| warmup begins / 20 s left | announcer / Cortana | "Pelican Warfare!" / gear up |
| insertion launches, 3 s in | Cortana | wheels up; the briefing (after the launch line) |
| seated 11 s in an insertion Pelican | Cortana | "that's your stop", after the briefing (riders are put out when the flight ends) |
| freefall below 320 m / 170 m | Cortana | "pretty close to the ground" / "Chief! Pull your chute!" |
| out of the air, still falling faster than 20 m/s, under 30 m (the splat) | Cortana | "Well. I tried to warn you." / "That's going to leave a mark." / "I'll log that as a hard landing." |
| combat begins | announcer | "Capture the zones!" |
| 10 s before a Covenant wave | Cortana | the first always; later ones only while no Covenant stand in a zone (a wave at the cap is skipped) |
| Covenant step into a zone | announcer / Cortana | "Zone X contested!" if it is ours, else "Contact!" after 20 s of quiet |
| a zone changes hands | announcer / Cortana | secured, lost, the enemy took it, the Covenant took it, retaken |
| the Covenant hold two / all three / 10 s left / broken | Cortana | escalating warnings (the all-zones line replaces that update's single-zone line) |
| a reinforcement Pelican boards | Cortana | "Your ride's here" |
| the end | announcer, Cortana | Victory / Defeat; "Not bad, Chief"; "We've lost the island" |

Mechanics:

- **One at a time.** One line plays at a time, through `SpawnSound2D` at the dialogue slider.
- **Turns with the announcer.** The loader's announcer queue (`MJOLNIRLevelLoader/Scripts/announcer.lua`) and this voice share `MJOLNIR.voiceUntil`. A calm line waits for the other voice; the player's own fall does not.
- **Urgency.** A more urgent line cuts a calmer one off (priority 3 is the player's own fall).
- **Staleness.** A line that waits past its time-to-live is dropped.
- **Baselines.** A new instance, or the first sample after the state went stale, only sets a baseline.

The loader no longer announces Warfare at the first spawn. Its start event
used to say "King of the Hill"; `startEvent` is now `warfare_game_start`,
which has no `events.json` row.

The waves are generated by local voice models (`tools/voice/README.md`):
- they live under `/Game/MJOLNIR/Sounds/Warfare`;
- they are cooked into `pakchunk950` by `unreal/MJOLNIRMaterials/Scripts/build_warfare_voice.py`;
- `warfare_voice_lines.lua` lists them with their lengths.

**They are not shipped.** Without the container, the first wave fails to load,
the voice logs that once, and it stays silent for the session.

Solo on PC 1 (2026-11-24), these lines played on their triggers, as logged:
- the title and warmup;
- the launch and briefing;
- the two altitude warnings and the auto-chute line;
- zones open, secured, contested, lost and taken;
- the first wave;
- two zones, all three, ten seconds, and the Covenant win.

That run's build preceded four fixes, which are unit-tested only: the
all-zones line replacing the third zone's, "jump now" timed from boarding
and queued behind the briefing, reinforcements seen at 2 Hz, and the canopy
reload. In game, nothing has yet triggered:
- "jump now" (that build called it too late);
- a later wave's warning, or a landing on a zone nobody holds;
- a retake, or breaking the defeat clock;
- an enemy capture;
- reinforcements;
- victory or defeat by score.

Not yet checked: a client's view, and the lines heard by ear for level and
timing (the log shows what played, not how it sounded).

## Validation and remaining runtime checks

The private solo acceptance run passed all seven recorded milestones:
native bridge ready, Pelican seated, canopy deployed, landed, respawned,
site scoring and round ended. The local receipt is
[`out/pwr/smoke-2026-11-09T05-27-03-197Z.jsonl`](../out/pwr/smoke-2026-11-09T05-27-03-197Z.jsonl).
It used a short test variant with a five-point target; the verified terminal
snapshot has phase 3, Red 5–Blue 0 and capture A owned by Red. Screenshot
events include seated, canopy, landed and end; the final screen showed Red
winning 5–0. The tested native DLL SHA-256 is
`4073f89c8d51bbf7229e7571613fdb0b79ef12a87bb533c5e200d2b3e8fa8068`.
The earlier absent-team -1 score sentinel is now covered by the publishing
clamp and a behavioral regression test.

A subsequent private test with two local player slots also passed, recorded
in [`out/pwr/smoke-2026-11-09T05-30-30-841Z.jsonl`](../out/pwr/smoke-2026-11-09T05-30-30-841Z.jsonl).
Red player 0 and Blue player 1 boarded their respective transports, exited
automatically, deployed canopies and landed. Native landing positions in
metres were Red `(172.518, -62.345, 0.244)` and Blue
`(-176.537, 64.270, 0.588)`. Red then died, respawned, captured A and won
the short five-point test 5–0. Both slots ran in one local game process;
this establishes the local two-team transport flow, not remote networking.

After the spawn-palette correction, the installed 500-point solo variant
passed the keyboard and transport-lifecycle run in
[`out/pwr/smoke-2026-11-09T05-46-27-499Z.jsonl`](../out/pwr/smoke-2026-11-09T05-46-27-499Z.jsonl).
It observed ready, seated, canopy, landing, respawn and scoring, plus early
exit from an actual Space key input. Named transport counts were zero in
warmup, two during insertion and zero after cleanup. This used the
`4073f89c...` native DLL above. No round end was expected during this short
500-point run; the earlier five-point tests cover that transition.

A live visual comparison found that passenger seat `pelican_p_l04` avoids
the large gray polygons visible from `pelican_p_l01`. The native boarding
order now prefers `l04, l05, r04, r05, l01, l02, l03, r01, r02, r03`, retaining
all ten passenger seats. Only l04's view has been visually verified; the
other nine seats have not been visually certified. The updated native DLL
build and portable tests passed with SHA-256
`498aa411f354124f9a79ab7f48d5c08f97acd960eb88510c5c2194340200624b`.
That DLL is in the latest installation receipt above. Its final private live
run passed in
[`out/pwr/smoke-2026-11-09T05-50-20-538Z.jsonl`](../out/pwr/smoke-2026-11-09T05-50-20-538Z.jsonl):
ready, seated, canopy, landing, death/respawn, capture scoring, actual Space
exit before the automatic fallback, and transport counts 0 / 2 / 0. The
in-flight seated screenshot confirms the improved l04 view. This 90-second
run retained the installed 500-point target and did not require a match end;
the earlier five-point runs separately verified victory.

`cargo test -p blam-megalo --lib --test warfare_behavior` validates typed and
independent grammar roundtrips plus deterministic warmup, capture, contested
scoring, on-foot eligibility and victory behavior. Lua tests
`test_warfare_bootstrap.lua`, `test_warfare_hud.lua` and
`test_warfare_canopy.lua` cover bootstrap, freshness, score authority,
persisted settings, presentation and canopy attachment lifecycle.
`test_lobby_postgame.lua` covers the scoped Warfare rotation and the unchanged
ordinary rotation. The latest Warfare-only postgame rotation has been unit
tested but has not yet been verified in a live postgame vote. The HUD
regression preserves a verified terminal result
when the engine starts resetting its round before frontend travel.

Integration is ongoing. Remote host/client replication, remote seating and
drop, remote canopy visibility, join-in-progress, a full 16-player match,
full vehicle combat remain unverified. Opposing teams
contesting a capture site is covered by the deterministic VM tests, not a
live contested-site test. The historical runs above used the original
400 × 300 metre basin; they do not certify the current expansion's terrain,
scenery or performance. The expansion requires its own installed-build
checks. No increased player cap or third team is implemented.

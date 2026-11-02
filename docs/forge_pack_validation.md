# Foundry Forge pack validation

Evidence recorded on **2026-11-01**, using CU4 and a private, isolated local
`FPK` map fixture. This tests the original 18-piece Foundry set and the new
pack-aware Forge pipeline. See [forge_packs.md](forge_packs.md) for the build and
distribution contract.

## Observed in the game

| Check | Result |
| --- | --- |
| Load custom tags | 72 namespaced tags loaded: 18 piece types × collision, physics, model and crate |
| Place pieces through Forge | All 18 types placed; native object counts confirmed the placements |
| Render the custom actor | The cube and doorway rendered using their new actors and meshes |
| Authored labels | Forge displayed the pack and block labels from the installed catalog |
| Grab and move | The placed cube's position changed through Forge movement |
| Rotate | Rotate-right changed the cube's rotation by 22.5° |
| Save, delete and reload | Reload restored the saved position and rotation after deletion |
| Save pack identities | The `.mvar.packs` file contained 18 bindings with the exact installed archive hash |
| Missing sidecar | Removing the sidecar caused the layout to be refused |
| Changed installed hash | A mismatched inventory hash caused refusal with `needs foundry 0.1.0` |
| Restart and automatic loading | A full game restart restored all 18 custom pieces and the spawn marker from the saved layout |
| Player standing collision | The Spartan settled at Z 4.97 wu on the cube at Z 4.32 wu, matching its 2 m height; remained stable, then fell to Z 0.02 after walking off |
| Floor collision | The Spartan settled at Z 0.69 wu on Floor 2 x 2 at Z 0.52 wu, matching its 0.5 m thickness |
| Ramp traversal | Walking up the ramp raised the Spartan from Z 1.11 to 1.22 and 1.36 wu as Y increased, matching the 1:2 slope |
| Doorway opening and lintel | The player fell through the open centre below the lintel; a drop from above settled on the lintel at Z 11.58 wu, matching its 3 m height above Z 10.60 |

![Representative Foundry cube placed in Forge](../forge-packs/foundry/art/game-first-placement.png)

All 18 types were placed and counted; the cube and doorway received representative
visual review in game. The Blender contact sheet and Crosswalk
assembly show the authored geometry and material design. The game build uses
stock material references on the original geometry, so those Blender renders
do not establish the final in-game surface appearance.

## Automated and offline evidence

| Area | Completed checks |
| --- | --- |
| Collision geometry | 9,950 rays against generated collision and the source triangles, including face probes and axis sweeps |
| Launcher | 90 tests passed; 5 ignored. Includes a local HTTP fixture for exact-version dependency download and refusal to replace a live pack |
| Hub | 40 tests passed; type check and focused lint passed. Includes upload/scan/catalog visibility and version validation |
| CLI | 8 focused Forge tests passed; 2 new-tag tests passed. Includes signatures, malformed containers, custom scenario preloads and hyphenated namespaces |
| Live tag lookup | 14 tag-table tests passed; the generated-scenario alias was also verified by live field writes during collision testing |
| Lua | 39 checks passed; 62 Lua files passed syntax/lint checks |
| Native Forge | 684 portable checks passed, including identity guards, paired-file failure injection and BLF marker handling; `/WX` build passed |

The HTTP tests use local fixtures. They establish dependency behavior without
claiming that a Foundry release has been published on the production Hub. The
native file tests cover rollback and preservation of previous layout bytes on
save failures; those failure cases were exercised in the portable harness.

## Pending game checks

- Full visual review, floor/ramp joins, stairs, horizontal doorway traversal,
  window openings and vehicle traversal.
- A fresh launcher profile fetching a published Foundry release and its map.
- Multiplayer placement and saved-layout behavior with a second machine.

Offline ray agreement and the representative standing check do not establish
every traversal case or multiplayer behavior.

The local test installation was removed afterward. Seven pre-existing files
were restored and hash-checked, 230 temporary game files were removed, and the
game's display settings were restored. Generated content and captured test
layouts remain in ignored local build/evidence directories.

## Foundry 0.2 and the playable map templates

The follow-up adds 24 Foundry pieces and two actual standalone map archives:
[Forge Canvas and Crossline](../forge-maps/README.md). Separate private local
sessions loaded `FBK` in Forge and `FRB` in Team Slayer on CU4, with CE runtime
1.17.0. These archives are local, unsigned candidates, not published releases.

| Check | Observed result |
| --- | --- |
| Empty canvas | A 64 × 64 m deck with a 2 m grid loaded; the Spartan remained at floor Z=0. The palette contained all 24 Foundry entries plus spawn/sender/receiver/two-way utilities. |
| Crossline assembly | All 98 Foundry placements loaded alongside eight spawn and two teleporter markers. |
| Raised route | Walking from the blue base along the side catwalk retained Z=1.48 wu, matching the 4.5 m deck surface. The paired central ramps supported walking down and back up through their join. Dropping to the lower route settled at Z=0. |
| Teleporter route | Walking onto the flush pad transported the Spartan between the two bases in both directions. Leaving the destination trigger and re-entering re-armed the route. |
| Forge utility creation | Insert created a two-way marker with the expected cylinder dimensions (0.35 wu radius, 0.6 above, 0.1 below); P changed its channel from alpha to bravo. |
| Attached lights | Eight real point-light components existed in Team Slayer: four coloured and two warm pylons at 7,000 cd / 8 m radius, and two strips at 2,500 cd / 6 m radius. Component positions matched each actor and its declared offset. |
| Visible illumination | With the canvas sun/sky temporarily disabled for diagnosis, the warm pylon produced a visible pool on the floor. Coloured lights illuminated Crossline's walls and the player's weapon. |
| Light cleanup | Reverting the canvas removed the placed pylon's point-light component while its pooled actor became hidden. |
| Kill floor | Walking beyond Crossline's floor triggered the loader's -600 cm kill floor and the multiplayer respawn sequence. |
| Map travel | A fresh process completed Crossline → lobby → Forge Canvas → lobby → Crossline with working HUDs and eight lights recreated on Crossline. |
| Final canvas picking | A cold launch with the normal Forge DLL selected and moved both a block and the narrow red pylon using the rebuilt canvas. No diagnostic patch was active. |
| Pylon save/reload | Saved the moved/rotated pylon, deleted it, and loaded the save. Its transform was restored with exactly one attached 7,000 cd light. Deletion hid the pooled actor and removed its attached light. Returning after a Crossline session automatically restored the saved pylon and light. The sidecar recorded the final Foundry archive hash. |
| Chat while editing | Typing B into chat entered text and left Monitor mode active, confirming inactive class placeholders do not mask the live chat widget. |

Playtesting corrected the sky's atmosphere-sun/physical-skylight settings,
raised the lamps from their initially ineffective brightness, and caught
reversed red/blue scenario team names. Red uses `defender`, blue `attacker`.
Portals sit behind the spawn line so approaching from the arena side leaves
the destination facing into play. The central lower landing has a 0.5 m lip;
returning from the surrounding floor requires a jump.

Travel testing also exposed a stale UE4SS UI-property cache after class
collection. The bounded class-retention mitigation and discovery guards are
documented in [custom_ui.md](custom_ui.md#class-lifetime-during-map-travel).
The canvas initially rendered and supported standing but could not select
objects above the floor: the native loader recomputed query bounds from the
slab's vertices. Adding two unreferenced shell vertices expands that envelope
without adding collision surfaces. A temporary bounding-box-only diagnostic
proved the cause; the final cold-launch check used the rebuilt assets and
normal DLL. See [forge_canvas.md](forge_canvas.md).

Offline checks now cover 13,328 Foundry collision probes and 13,068 probes for
each canvas BSP; 24 pieces, 49 convex hulls and 580 collision triangles.
The follow-up passes 92 launcher tests (5 ignored), 41 Hub tests, 13 level
tests, 5 Forge CLI tests, 5 map-builder tests, 1,473 light lifecycle checks,
42 Forge HUD checks, 73 UI class-retention/discovery checks and 1,753 native
Forge checks. The native DLL builds with `/WX`. All 24 emitted model bounds
enclose their authored visual and collision geometry; decoded package
references and extraction integrity checks passed.
Both map archives preserve their authored JSON and pin `foundry =0.2.0` and
`mjolnir-ce-runtime ^1.17.0`; neither embeds a private save or shared map
registration override.

The Blender previews use the actual source placements and original authoring
materials. Runtime meshes currently reference shipped materials; preview
surface appearance is not evidence of the game's final material appearance.
Second-machine play and downloading a published release into a fresh launcher
profile remain pending.

Initial playable candidates (unsigned), before the enclosure follow-up:

| Archive | SHA-256 |
| --- | --- |
| Foundry 0.2.0 | `e136236363744be1b19d3f45898d3bb25f07d0e2ca0534b8bfca5f2fc9375dee` |
| Forge Canvas 0.1.0 | `76a306b560f54794ea9fb5a89ecae621d858003928cfbfce0eea8e07b1b940f2` |
| Crossline 0.1.0 | `1b5e0cf022bff2b23598966caeab408b58db81098e2e20b926f009195c5c9e44` |

The follow-up test installation was removed afterward: twelve pre-existing
game files were restored and hash-checked, temporary map/pack containers and
metadata were removed, and display settings were restored. Test layouts and
diagnostic evidence remain in ignored local directories. Both CI workflows
passed for implementation commit `2a6f014e`.

## Enclosed Crossline and photo session

Crossline now appends 96 existing Full Wall pieces to the original layout:
three 3 m courses form a continuous 9 m perimeter, with overlapping corners.
The original 108 simulation objects, routes, spawns and teleporters remain
unchanged. There are now 194 Foundry placements plus ten gameplay markers.
Forge Canvas remains empty.

Six map-builder tests pass. The enclosure regression uses transformed
collision hulls to check coverage along all four sides at every height band,
corner overlap, and spawn/teleporter clearance. In a fresh private Team Slayer
session, walking east stopped at X=3.60 wu; another 900 ms of movement left X
unchanged. Walking south reached the corner at Y=-6.22 wu. Jumping into the
side wall left the player inside, and the player remained on the lower floor.
Live inspection counted all 194 Foundry pieces.

The [four new gameplay photos](../forge-maps/README.md#gallery) are unedited
1920 × 1080 captures using the existing FlyCam to hide the HUD. They show the
overview, red base, lower route and perimeter. Blender previews are labelled
separately and regenerated from the same enclosed layout.

Latest local archives remain unsigned:

| Archive | SHA-256 |
| --- | --- |
| Foundry 0.2.0, wall-guide README update only | `50107e14652d40e8978ca7401de5bd419fe041c45defb46083f9ea2f9e56e373` |
| Enclosed Crossline 0.1.0 | `77dfd4bfd9588ddcdc5901eb3213c16ed9b47af310bba29089a54080569595f1` |

All 194 Foundry container members are unchanged by that README-only repack.
The original game files, camera poses and display settings were restored and
verified after the session; the temporary installation was removed.

## Roadworks 0.1 validation

The ten-piece [Roadworks kit](../forge-packs/roadworks/README.md) and separate
[Roadworks Circuit / RWC](../forge-maps/roadworks/README.md) were built locally
on 2026-11-01 (final build report `20261102T012552Z-87e4971b`). The map has
18 connected loop pieces, a guarded spur, three test-pad decks, two stock
Warthogs and four player starts. Its road surface is 3 m above the original
160 m canvas, rising to 7 m, so the recovery floor cannot mask road-collision
gaps. The existing Forge Canvas and Crossline level files are unchanged.

| Offline check | Result |
| --- | --- |
| Source geometry | 196 convex hulls / 2,352 triangles; 3,430 road-surface probes passed |
| Native collision | 9,774 rays passed across all ten generated collision tags |
| Model visibility bounds | All ten emitted models decode to a 300 m `render_distance` (98.425194 wu), replacing the inherited zero/default value that selected 91.44 m. The cold-launch check below verifies visibility across roughly 120 m of the course; 300 m was not tested live. |
| Map assembly | Nine builder tests passed, including real-triangle surface checks, connector/deck-edge closure, reversed descent, guard seams, pit access and vehicle spawn surfaces |
| Canvas | 13,068 collision probes passed for the 160 × 160 m slab and expanded playable bounds |
| Packaging | Exact pack palettes and container bytes verified; authored JSON preserved, `vehicles: true`, Slayer/Forge modes, no private layout or shared registration override |

The map pins `foundry =0.2.0`, `roadworks =0.1.0` and
`mjolnir-ce-runtime ^1.17.0`. The retained build report records every input
hash; both archives below were rehashed against the finished files.

| Local unsigned archive | Bytes | SHA-256 |
| --- | ---: | --- |
| Roadworks 0.1.0 | 601,379 | `8a5e7869a5f73866804c3f6d5abf0fe43f50baf8161ccb6116ec68b96f3f7acf` |
| Roadworks Circuit 0.1.0 | 112,962 | `8fc7b93374ecfe054ecedfe3e36cd57b28370f43e634c2f549a3bc38ca4a869b` |

The [circuit preview](../forge-maps/art/roadworks-circuit.png) is a Blender
render of the generated level and original pack geometry. Its provenance
receipt and the bake agree on level SHA-256
`44af8c27d83ad60365df3bb28c0522544d047bb9b5b195671cc694fc3dac3854`.
The preview uses authoring materials and omits the stock Warthogs and player
markers. It is not an in-game capture or vehicle-scale photograph. The
[scale measurements](../forge-packs/roadworks/SCALE.md) come from installed
stock tags; no extracted stock models are shipped in the authored pack.

### First private Slayer drive

The pit Warthog drove onto the spur, crossed the 12/24 m straight joins, a
90° bend and the joints between paired 45° bends. Its native position stayed
at approximately Z=0.98 wu (3 m), with full 500 health. A second stock Warthog
completed the raised route, also retaining full health:

| Ramp position, authored Y | Observed vehicle Z | Road stage |
| ---: | ---: | --- |
| 10.91 m | 1.73 wu / 5.27 m | Climbing |
| -4.94 m | 2.29 wu / 6.98 m | High deck |
| -24.45 m | 1.60 wu / 4.88 m | Descending |
| -39.35 m | 0.98 wu / 2.99 m | Back on the low road |

These drives used ordinary gameplay inputs without live physics or position
patches. The final map archive is byte-identical to the first candidate;
the Roadworks pack changed its model render-distance fields.

The [three gameplay photos](../forge-maps/README.md#roadworks-gameplay-photos)
show the real Spartan and Warthog beside a two-metre ground scale bar, the
course overview and the ramp. The detached FlyCam required temporarily
changing native `CullByBlamVisibility` from 1 to 0 for the overview and ramp
photos so objects culled relative to the native player camera remained
visible. This setting changes visibility only; it did not repair or modify
geometry or collision. It was restored to 1 before every drive and before
quitting the first session.

### Final cold launch, Forge and restoration

A fresh process loaded a private RWC Forge session. Insert placed a
`straight_24`; V grabbed it, D moved it, two period presses rotated it and V
dropped it. F5 saved 67 objects, including the added straight at native
position `(2.50, 11.81, 1.72)` wu and yaw -37.5°. Insert then placed a separate
`curve_90`. F6 removed that unsaved curve and recreated the saved straight at
the identical transform.

The saved `RWC.mvar.packs` bound both releases to their exact installed
archive hashes: Foundry 0.2.0
`50107e14652d40e8978ca7401de5bd419fe041c45defb46083f9ea2f9e56e373`
and Roadworks 0.1.0
`8a5e7869a5f73866804c3f6d5abf0fe43f50baf8161ccb6116ec68b96f3f7acf`.

This final session used the default `CullByBlamVisibility=1` throughout,
without FlyCam. Ordinary S movement took the Monitor to
`(5.87, -20.86, 1.50)` wu, or authored Y=-63.6 m. Readback showed the north
guarded straights at authored Y=56 m with `bHidden=false`, and a screenshot
showed the far road. This establishes cross-course visibility at roughly
120 m; it does not establish the full 300 m render-distance limit.

After quitting, `.dream-loop/roadworks/session.ps1 -Action restore` restored
23 original file states with hash verification and removed the temporary
test packs and maps. Played layouts were retained in the ignored
`played-layouts` evidence directory.

Formal guardrail-impact and two-car passing tests, published Hub installation
and second-machine play remain pending for these candidates.

### Roadworks frame-time investigation

The user's later RWC session exposed repeated hitches and a flashing Forge
HUD. At 2560 × 1440, process 35964 recorded 954 hitches over 5 minutes
55 seconds: median frame time 5 ms, p95 8 ms, p99 91 ms and worst 190 ms.
The largest recurring stalls coincided with the half-second pack-light poll.

Direct timing isolated the cost: the shared world lookup took about 20 ms,
and each of four Blueprint `StaticFindObject` lookups took 15–16 ms.
Actor enumeration and four active-actor checks together took only 0–1 ms.
The final adapter follows the current local player through the process's
`GameEngine` and resolves Blueprint classes afresh through the nonloading
`Conv_SoftClassReferenceToClass` conversion. It caches only native classes
and defaults, never Blueprint classes or departing controllers, and does
not load pack assets in the frontend or during travel. The combined lookup
probe measured 0–1 ms warmed, with an initial 5 ms result.

The HUD flashing was a separate consequence of the stall: a native 100 ms
poll advertised `forge=0` whenever it saw no new simulation snapshot.
It now allows one second without progress before declaring Forge inactive;
repeated polls cannot extend that deadline. Forge HUD and pack-light work
also report through `MJOLNIR.work`, so future hitch logs can attribute their
cost. The focused light suite passed 1,531 checks and the native suites
passed 1,788 checks, including the heartbeat timeout and wrap boundaries.

The user's 66-object layout was saved, preserved and loaded again in cold
process 48988. With the Monitor palette visible at the same 2560 × 1440
quality settings, a 61-second sample covered 9,815 frames: median 6 ms,
p95 7 ms, p99 7 ms and worst 34 ms. It recorded 21 hitches, all below 50 ms;
the recurring 90 ms stalls were absent in this window. Pack-light work
averaged 0.5 ms per second, with a worst individual run of 1 ms. Four
7,000 cd point-light components still reported `visible=true`.

A separate 45.0456-second state-file sample contained 712 valid `forge=1`
observations and no `forge=0` observations; five partial reads were ignored.
This is a short, roughly one-minute performance check with a different
camera position from the user's baseline, not a claim of zero hitches or
long-session performance. The game was left open in Monitor mode for the
user with the saved layout loaded.

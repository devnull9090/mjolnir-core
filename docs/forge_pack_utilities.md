# Forge pack utility metadata

Pack utilities are bounded catalog data. They do not install scripts from a
community archive. The Hub scanner, CLI packer and launcher validate the same
fields; the launcher preserves them in `MJOLNIRForgePacks/installed.json`.
Old packs can omit them or use `null`.

## Gravity lifts

A block can carry this optional specification, in its authored local axes and
metres (right-handed, Z up):

```json
"lift": {
  "offset_m": [0, 0, 0.45],
  "size_m": [4, 4, 3.5],
  "direction": [0, 0, 1],
  "acceleration_m_s2": 20,
  "max_speed_m_s": 4.5,
  "negates_gravity": true
}
```

`offset_m` is the trigger's bottom centre; `size_m` is its full box size.
The trigger follows the piece's live translation and full rotation, independently
of its visual mesh normalization. The example overlaps a 0.5 m deck by 5 cm to
avoid a floating-point gap. It is a proposed four-metre-rise preset: its nominal
column ends at 3.95 m, with an additional ballistic rise after exiting. Live
trajectory and landing verification remain necessary; the speed is not a
guaranteed landing height. Horizontal steering is preserved.

Offsets are limited to ±100 m per axis; sizes to 0.1–100 m. Direction must be a
unit vector (squared-length tolerance 0.001). Acceleration is 0.1–100 m/s²,
speed 0.1–30 m/s, and `negates_gravity` must be a boolean. Unknown fields are
rejected. Runtime discovery uses at most 16 class definitions, selected by
sorted class path, and 64 active lift actors; additional definitions are ignored.

`MJOLNIRLevelLoader/Scripts/pack_lifts.lua` converts these boxes to the existing
Halo 2 phantom format. `lifts.lua` uses the same tested acceleration, gravity
compensation and `object_set_velocity` script transport as Lockout's lifts.
Each peer pushes only its own locally controlled Spartan bipeds, in Forge
and Slayer. Saved-layout actors and later duplicates are discovered from their
current Blam bindings; hidden or pooled actors without a binding do nothing.

Discovery uses Unreal's native actor-class lists and nonloading soft-class
resolution, at 500 ms while idle and 50 ms near a lift. It never performs a
periodic UE4SS global object scan or retains a Blueprint class/actor wrapper
between calls. Travel clears the carried velocity and pending world state.
The existing LevelLoader script writer remains shared with static Halo 2
lifts and kill floors.

## Automatic doors

Panels may declare:

```json
"door": {
  "travel_m": 4,
  "speed_m_s": 4,
  "trigger_size_m": [8, 16, 6],
  "hold_open_s": 2
}
```

Travel is along local +Z. Travel must be positive and at most 16 m, speed
positive and at most 8 m/s, trigger dimensions positive and at most 32 m,
and hold time 0–10 seconds. Door panel `dimensions_m` may not exceed 64 m
on any axis. Unknown fields are rejected. The infantry preset above travels
4 m; the vehicle preset travels 6 m with a `[12,20,8]` trigger, the same
4 m/s speed and two-second hold.

### Native behavior — development build

Use **MJOLNIRForge 0.4.0**, **MJOLNIRLobby 0.19.2** and
**MJOLNIRLevelLoader 0.9.8** or newer together. Lobby checks the Forge native
utility API marker and waits for a compatible native Forge module before
animating. It refuses door automation with an older loaded Forge
DLL, whose save path would otherwise serialize the animated position.

`native/lobby/forge_doors_runtime.h` runs on the authoritative simulation
thread in Forge and ordinary multiplayer modes, including Slayer. It operates
on the native crate and its collision body through the engine's transform
setter, rather than moving only its Unreal visual. Players approaching the
rotated local trigger request opening along the panel's local +Z. After they
leave, the panel waits for `hold_open_s` and closes. **Fixed** and **Phased**
enable automation; **Normal** disables it and leaves ordinary physics in control.
Fresh scenario construction and **Revert** seed installed door panels to Fixed,
because scenario placements do not encode this physics choice. This happens
before the objects are created. Loading a saved layout replaces those defaults
with its saved properties, including an explicit Normal choice; other pieces
and existing Fixed/Phased choices are unchanged.

The runtime checks a conservative sphere against the panel's swept box before
closing. Bipeds, vehicles and movable Normal crates can keep a door open or reopen it.
Opening also stops beneath a dynamic obstacle. Entering Monitor mode, or
requesting an edit, attempts to close the panel only if its entire closing
path is clear. A parked vehicle can therefore leave the panel raised while
editing. Grabbing, duplicating, rotating or changing the physics of that raised
panel is deferred with a message to clear the doorway; unrelated objects remain
editable. These checks do not test
the static world, Fixed/Phased construction pieces, or unparented crates whose
native physics model contains only fixed bodies. The last classification is
cached per world and salted tag; keyframed, mixed and unknown bodies remain
obstacles. Authors must leave
space above and beside the panel for its full travel.

Motion advances once per changed simulation tick, using the native tick rate;
paused redraws do not consume hold time. Catch-up frames advance at most one
tick. There are at most 128 active automated panels and 256 installed door
definitions. The adapter scans native object arrays once per tick, with no
Unreal global-object polling. It accepts only supported CU4 builds and rejects
parented panels, invalid transforms, stale object handles and unmatched pack
identities. Unsupported builds or invalid inventory disable automation.

### Editing, saves and multiplayer limits

Forge's native update reapplies each map-variant pose every tick. The adapter
therefore publishes the animated position in the live map variant and keeps
the authored closed pose in a private cache, keyed by world instance, full
object handle and entry identity. Deletion, travel and replaced objects discard
stale cache entries; an external authored pose change establishes a new baseline.

**F5** projects verified closed poses into Forge's temporary serialization copy.
Saving does not close the live door or modify the active animation. If a panel
has no verified closed baseline, saving is deferred rather than recording its
raised pose. This includes enabled door panels on fireteam clients. Ordinary
layouts without those panels retain the existing client-save behavior.

A client that becomes host cannot reconstruct the closed origin of a door it
joined while open. Automation and saves requiring that missing baseline remain
disabled until the game is rehosted. Closed-origin state is not separately
replicated. The engine's object-transform updates are used in Slayer; map-variant
dirty updates apply in Forge. Client visual/collision replication, host migration
and driving a vehicle beneath an operating gate still require in-game
verification. The
[validation record](forge_pack_validation.md) reports the narrower local
save/reload, visible opening/closing and nearby-vehicle obstruction results.
The implementation and portable tests are not live evidence.

### Installed companion

The launcher emits a companion `MJOLNIRForgePacks/doors.txt` for the native
reader. Its header is `forge-doors 1`; each row has ten tab-separated fields:
tag, travel, speed, trigger X/Y/Z, hold time, panel width/depth/height. All
measurements are metres or seconds, using decimal dots. There are at most
256 definitions across enabled packs. The native reader must match each
tag against current `installed.txt` bindings. Panel dimensions come from the
validated catalog, not a guessed donor bound. The trigger is centred on the
panel in X/Y, with its vertical interval from −0.5 m to trigger Z above the
authored bottom origin.

The launcher prepares all inventory files before replacing each atomically,
publishing the identity bindings last. Disabling/uninstalling packs also
rewrites the companion; no door entries leaves a header-only file.

## Surface profiles

`surfaces` is an optional list of up to 16 strict `{slot, profile}` objects.
Slots are unique integers 0–15. Profiles are the fixed names `glass_cyan`
and `teleporter_green`; arbitrary material paths or code are not accepted.
The material implementation supplies the approved textures, animation and
shader parameters. The green visual does not replace native teleporter
sender/receiver/two-way markers and their channel settings.

The CLI packer and Hub scanner require these cooked packages inside the
archive's installed `content/` containers, under `/Game/MJOLNIR/Forge/<pack-id>`:

| Profile | Required package paths below the pack root |
|---|---|
| `glass_cyan` | `Materials/M_ForgeGlassCyan` |
| `teleporter_green` | `Materials/M_ForgePortalGreen`, `Textures/T_PortalDust`, `Textures/T_PortalMask`, `Materials/T_CE_BlackCube` |

The check uses Unreal package IDs and requires export-bundle chunks; bulk-only
chunks, another pack's copies and containers outside `content/` do not satisfy
it. Packs without surface profiles do not need these assets. The Hub's bounded
package-ID hash and the Rust implementation share 15 test vectors spanning
minimum, ordinary and maximum pack slug lengths.

This is a presence check, not proof of valid material exports, complete shader
code, matching mesh slots or gameplay collision. Door/lift metadata validators
check their bounded data shapes; they do not decode tag payloads to prove a
compatible native crate and Blueprint binding. The authored cook checks and
live runtime checks remain necessary, as does testing the installed pack.

## Checks

Portable tests cover transformed trigger planes, source-to-Unreal coordinates,
the standing-deck overlap, player ownership, actor pooling, class lookup cost
boundaries, world travel and use of the shared script writer. Existing Halo 2
math tests remain unchanged. Hub/CLI/launcher tests cover schema limits,
unknown keys, normalized inventory round trips, companion fields and stale-row
removal. These are code checks, not claims of a completed live utility test.

`native/lobby/test-forge-doors.ps1` runs the portable door parser and movement
tests with MSVC warnings treated as errors. They cover field limits, rejected
row isolation, translated/rotated triggers, sphere-versus-swept-panel clearance,
opening/closing, hold time and paused or invalid time steps. The same C test
also builds with a C11 compiler on other platforms. CI runs it alongside the
three lift Lua suites and the launcher Forge inventory tests.

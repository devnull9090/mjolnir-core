# Forge mode in the tag editor

**Status:** design, 2026-11-03. Nothing here is built unless a line says so.
It builds on [forge_layout_sharing.md](forge_layout_sharing.md): the layout
library, the validator and the publishing flow.

Forge in the game is one player with a cursor. The tag editor can show the
whole map at once. Forge mode lets a builder place, move, turn and delete
a layout's objects in the editor's 3D view, with real meshes and grid
snapping. While the game runs a FORGE game on the same map, each edit
appears in the game on the next tick, and objects moved in the game move in
the editor. With the two windows side by side, the editor is the floor
plan and the game is the walk-through.

## What exists

| Piece | Today | Where |
|---|---|---|
| World view | BSP collision, a scenario's placements with real textured meshes (tag → `BP_` → `SM_`/`SK_`), trigger volumes, spawns; click to select; three.js `TransformControls` move/rotate; edits written to the scenario tag through `set_field` | `apps/tag-editor/src/components/ScenarioViewer.tsx`; `src-tauri/src/geometry.rs`; `lib.rs` `read_scenario_layout` 2692 |
| Meshes | Nanite or classic LOD decode, base-colour textures; the catalog indexes every top-level container in Paks, so the launcher's `MJOLNIRHUB` pack containers should be included | `lib.rs` `read_mesh` 2503; `src/lib/render-mesh.ts` `loadRenderGroup`; `catalog.rs` 303 |
| Live | attaches to the game with ReadProcessMemory/WriteProcessMemory and pokes tag fields | `src-tauri/src/live.rs`; `crates/blam-live` |
| Live objects | `blam_live::world::objects` reads every object's position, forward, up and scale; `mapvar_probe` reads the live map variant (`[TLS+0x250]+0x308`, 651 entries of 0x4c bytes from `+0x14fc`) | `crates/blam-live/src/world.rs` 254; `examples/mapvar_probe.rs` |
| `.mvar` codec | decodes and re-encodes a whole map variant as a tree (277 of 277 MCC files round-trip); world positions only in an example; no `.mvar` writer, no object API | `crates/blam-megalo/src/raw.rs` 1065, 1084, 1399; `examples/mvar_summary.rs` |
| Forge DLL | every command acts on the local player's held or aimed-at object; no outside command | `native/forge/mjolnir_forge.c` 159-184, `place_entry` 1466, `finish_grid_drop` 1573 |

What the editor lacks: it has no idea of maps by code or of Forge packs, it
doesn't read the scenario's `map variant palettes`, and it doesn't link
`blam-megalo`.

## The parts

### 1. A layout model in `blam-megalo`

A `layout` module over the existing tree:

```rust
pub struct Layout { pub header: Header, pub bounds: Bounds, pub objects: Vec<Placement>, /* the rest kept as tree */ }
pub struct Placement {
    pub entry: u16,            // 0..651, stable across edits
    pub palette: u8,           // flat index across `map variant palettes`
    pub variant: Option<u8>,
    pub position: [f32; 3],    // world units
    pub yaw: f32,              // radians
    pub up: Option<u32>,       // packed, carried as read (see below)
    pub flags: u8,
    pub properties: Properties, // physics, team, spawn order, label... carried exactly
}
impl Layout { fn decode(mvar: &[u8]) -> Result<Self>; fn encode(&self) -> Result<Vec<u8>>; }
```

- **Positions:** decode with the widths `position_widths` already computes,
  `lo + span / 2^bits × (raw + 0.5)`. Encoding is the inverse, rounded,
  so a position moves by at most half a step. That is under a millimetre
  on a Forge map, as in the game.
- **Turning:** yaw is 14 bits (radians = raw × 0.000383495 − 3.141401). The
  20-bit `up` vector (`0x3f57d0`) is not modelled, so an edited object
  keeps its `up` as read. The game turns about the vertical only, so
  nothing is lost.
- **File writer:** the envelope the DLL writes (`_blf` 1.2, `mvar` 31.1 with a
  zero hash, `fpk1`, `_eof`). The sidecar writer uses the launcher's
  format.
- **Every save passes the validator** in the layout sharing design, so the
  editor can never write a file the game refuses.
- **Tests:** decode → encode is byte-identical on every MJOLNIR save and
  every MCC map variant. Moving one object changes only that entry. The
  DLL's own reader (`test_layout_bounds.c`) accepts what the writer
  produces.

### 2. The Forge view (offline)

- **Open a map by code.**
  - The editor reads the installed maps the way the game does
    (`ue4ss\MJOLNIRMaps\maps.json`, then the loader's `maps.json`).
  - It finds the map's scenario in the catalog and shows its world as
    the World view does.
  - MJOLNIR's own Forge maps also have floors that MJOLNIRLevelLoader
    spawns at runtime from `map/level.json` (`decor`: Crossline's slab,
    Forge Canvas's deck). Forge mode draws those as plain shapes, so the
    map isn't floating in space.
- **Palette.** The scenario's `map variant palettes` block, read in
  `geometry.rs`, gives each flat index a tag.
  - Pack pieces are named from `MJOLNIRForgePacks\installed.json` and
    grouped by pack and category, as in the game's palette.
  - Each piece's mesh comes from `loadRenderGroup`. If a pack mesh doesn't
    resolve, its catalog box (`dimensions_m`) stands in, so a missing mesh
    never hides a piece.
- **Open a layout.** Choose a library entry, the active layout, or the
  map's own. Objects are drawn at their decoded transforms and selected by
  click or from a list, with a box select.
- **Edit.**
  - Move with the gizmo, on a grid of 0.25 to 4 m (the game's steps), and
    turn by the game's angle steps.
  - Duplicate, delete, and place from the palette.
  - Physics mode, team, spawn order and label use the same values as the
    game's property keys.
  - Undo goes through the editor's existing journal.
- **Budgets.** The palette shows placed and maximum counts and the price,
  as the game's HUD does, and refuses a placement over the maximum.
- **Save.** Saving goes to a library entry (Save, or Save as), never
  straight over the active layout. In the game, Use or F6 puts it on the
  map.

### 3. The live link

**Reading needs no game change.** While the game runs a FORGE game on the
same map:

- The editor reads the live entry table about ten times a second, through
  `blam-live` as `mapvar_probe` does.
- It moves its copies of anything that changed, so an object the player
  carries in the game moves in the editor.
- It marks the object the player is holding (`forge_state.txt` names it)
  and locks it against editing while it's held.

**Writing needs the game thread.** Writing the entry table from outside
would not move the objects, because the engine moves them through
`object_set_pose` and its dirty marks. It would also race the simulation.
So the Forge DLL gains a small command server:

| Piece | Design |
|---|---|
| Transport | a named pipe, `\\.\pipe\mjolnir-forge-<pid>`, created by the DLL with an ACL for the current user only. One client at a time |
| Operations | `snapshot` (entries with palette, transform, flags, and a generation number); `move <entry> <pos> <yaw>`; `place <palette> <pos> <yaw>`; `delete <entry>`; `highlight <entry>` |
| Execution | a reader thread queues operations, and the sandbox tick runs them (the slot 113 hook, as Lua's commands do), at most a few per tick |
| Reuse | `place` uses `place_entry`. `move` uses the pose sequence of `finish_grid_drop`: `0x5ec880` pre-move, `0x59f600` set pose, `0x59f470` modified, the entry's position, forward and up, then `mv_entry_dirty(entry, 2)`. `delete` is engine request 1 |
| Answers | each operation replies with the entry's pose as the engine left it. Fixed and Phased objects take the pose exactly, while Normal physics may settle |
| Guards | host only, FORGE games only, refused on a fireteam client. An operation names the layout generation it was made against, and the DLL bumps the generation when a layout is replaced (F6, F2, Use), so stale edits are refused. Nothing runs while the player holds that object |

Why not MJOLNIRBridge: players don't have it enabled, and it runs any Lua
it's sent. A pipe with five typed operations, local to the user, is much
narrower.

**Conflicts.** The last writer wins for each entry. The editor shows the
game's version whenever its snapshot disagrees with an edit that hasn't
been answered yet.

**Camera.** "Follow the game" moves the editor's camera to the player's
view (the player unit's position and aim, read through `blam-live`). It's
optional and comes later.

### 4. Publishing

The editor already pairs with `mods:write` and signs releases
(`src-tauri/src/hub.rs`, `keystore.rs`). Publish layout builds the
archive described in the layout sharing design from a library entry.
That makes the editor the first working path for publishing.

## Phases

| Phase | Ships as | Test |
|---|---|---|
| E1 codec and validator | crate only | byte-identical round trips on every MJOLNIR save and MCC map variant; single-entry edits; the DLL's reader accepts the writer's files |
| E2 offline Forge view | tag editor release | open Crossline, Forge Canvas and Roadworks Circuit by code; pack meshes draw; move, place and delete, save to a library entry, then F6 in game shows the same layout |
| E3 live read | tag editor release | carry a wall in game and watch it move in the editor; the held object is locked |
| E4 live write | mods release (Forge DLL) + tag editor | on Crossline, move a wall, place a ramp and delete a crate from the editor, and see each in game on the next tick; Fixed/Phased exact, Normal settles; stale generation refused after F6; refused on a fireteam client |
| E5 publish | tag editor release + hub layout type | publish a library entry to a test account; install it with a clean launcher profile |

E1 is shared with layout sharing's Phase 2. Building it first serves both.

## Risks

- **Pack meshes:** pack pieces are expected to draw through the catalog,
  but nobody has tried it. The box fallback keeps the view usable either
  way.
- **Map coverage:** MJOLNIR maps whose floors are runtime decor need their
  `level.json` shapes drawn. Converted CE maps also have a terrain mesh in
  their Unreal world that the World view doesn't load. Forge mode shows
  their BSP collision instead.
- **The live move sequence:** the order of calls `finish_grid_drop` uses
  works for a held object being dropped. Moving an object nobody holds by
  that path is untested; E4's first in-game test settles it.
- **One game at a time:** the pipe is per process, and the editor attaches
  to one game.

## Questions for the owner

1. Is a named pipe from the Forge DLL acceptable as the live channel, or
   should it be files beside `forge_state.txt`, as the Forge HUD's are?
2. Should Forge mode be a mode of the existing World view, or a separate
   Forge tab that starts from a map code?

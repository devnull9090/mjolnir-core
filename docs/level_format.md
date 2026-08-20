# The MJOLNIR level format (`.level.json`)

The interchange format of the level authoring pipeline: what the Blender exporter writes, what
`mjolnir level bake` turns into a scenario override, and what the `MJOLNIRLevelLoader` UE4SS mod
reads at runtime. One file describes one custom level.

Custom levels v1 are **map variants**: a shipped campaign scenario's world and BSP stay as the
canvas, and the level is everything placed on top. That split exists because the Blam simulation
collides only with its own world — BSP plus Blam objects — and ignores Unreal geometry entirely
(verified 2026-08-19, [multiplayer_investigation_notes.md](multiplayer_investigation_notes.md)).
The format therefore carries two kinds of content:

| Lane | Section | Spawned by | Solid? |
|---|---|---|---|
| Blam objects | `blam.*` | the sim, from the baked `scnr` override | **yes** — pawns, vehicles, projectiles all collide |
| Unreal decor | `decor` | `MJOLNIRLevelLoader` at runtime | no — visuals only |

Anything the player must stand on, drive over, hide behind, or shoot goes in `blam.*`.
Anything that only needs to look right can go in `decor`.

## Units, axes, angles

The file stores **UE-native values**: centimeters, Unreal's left-handed Z-up axes, rotations in
degrees as `[pitch, yaw, roll]`. The Lua loader consumes them conversion-free; the two converters
live at the edges:

| Edge | Conversion |
|---|---|
| Blender → file (exporter) | meters → cm (×100); **negate Y**; Blender Z-up right-handed → UE Z-up left-handed |
| file → Blam (`level bake`) | cm → world units (÷304.8); **negate Y**; rotation mapping is verified against live spawns during bake development |

Worked example: a Blender object at `(2.0 m, 3.0 m, 0.5 m)` exports as `[200, -300, 50]` UE cm.
Baked to Blam (with origin `[0,0,0]`): `(0.656, 0.984, 0.164)` wu — the double Y-negation means
**Blam Y equals Blender Y**. Sign bugs live here; when in doubt, spawn something and read the
engine position back (the proven check: a weapon placed at Blam `(8.0, 47.0, 65.5)` appears at
engine `(800, -4700, 6551)` relative cm — see [tag_data_pipeline.md](tag_data_pipeline.md)).

All positions in the file are **relative to `canvas.origin`** (a UE-space point on the canvas
map). Author around your own origin in Blender; move the whole level by editing one value.

## Top-level shape

```jsonc
{
  "schema_version": 1,
  "name": "proving_ground",          // slug: [a-z0-9_]+, used in filenames
  "title": "Proving Ground",         // display name
  "canvas": {
    "scenario": "B40",               // one of the 13 shipped scenario names
    "origin": [76200, -30480, 1800]  // UE cm, absolute; all positions below are relative to it
  },

  "environment": {                   // spawned by the loader; the bake ignores it
    "sun":       { "pitch": -50, "yaw": 30, "intensity": 8.0 },
    "skylight":  { "intensity": 3.0 },
    "atmosphere": true
  },

  "blam": {                          // consumed by `mjolnir level bake`, ignored by the Lua loader
    "clear": {                       // neutralize the host mission
      "squads": true,                // zero AI squads
      "bipeds": true,                // remove placed bipeds
      "weapons": true,               // remove the mission's own weapon placements
      "vehicles": true,              // remove the mission's own vehicle placements
      "scripts": true                // stub the mission's HSC scripts
    },
    "player_starts": [               // >= 2 for co-op
      { "pos": [0, 0, 0],    "yaw": 0 },
      { "pos": [4000, 0, 0], "yaw": 180 }
    ],
    "vehicles": [
      { "type": "warthog", "pos": [800, 600, 0], "yaw": 90 }
    ],
    "weapons": [
      { "type": "assault_rifle", "pos": [200, 0, 50], "yaw": 0 }
    ],
    "equipment": [                   // pickups: grenades, powerups, ammo
      { "type": "active_camouflage", "pos": [2000, 0, 0] }
    ],
    "objects": [                     // the structures lane — these are SOLID
      { "tag": "objects\\props\\covenant\\cov_portable_shield\\cov_portable_shield",
        "group": "scenery",
        "pos": [1000, 0, 0], "rot": [0, 45, 0] }
    ]
  },

  "decor": [                         // consumed by MJOLNIRLevelLoader, ignored by bake — NOT solid
    { "id": "banner_l",
      "mesh": "/Engine/BasicShapes/Cube.Cube",
      "pos": [0, -2000, 300], "rot": [0, 0, 0], "scale": [0.2, 6, 4],
      "tint": [0.8, 0.2, 0.2, 1.0] }
  ],

  "markers": [                       // named points for future game modes; spawns nothing today
    { "name": "flag_red", "pos": [0, 0, 0] }
  ]
}
```

The JSON Schema is [`defs/level/level.schema.json`](../defs/level/level.schema.json); validate
with `mjolnir level validate <file>`.

## Section notes

### `canvas`

`scenario` must be one of the 13 launchable names (`A15 A30 A50 B30 B40 C10 C20 C45 D20 D40
E10 E20 E30`) — scenario names are gated by Blam tags and new ones cannot launch. The default
canvas for the pipeline is **B40** (fullest vehicle palette, large flat canyon floors).
`origin` should sit on walkable BSP: the level's playable area must lie on the canvas map's
Blam collision, because that is the only floor the sim knows.

### `environment`

Sun, skylight and atmosphere, spawned by `MJOLNIRLevelLoader` when the world
arrives. It exists because `blam.clear` is now the default for an exported
level: once the host mission's own placements are gone, so is anything that was
lighting them, and an unlit canvas reads as a black void rather than a level.

All three keys are optional and each falls back to the shown default. `sun`
becomes a `DirectionalLight`, `skylight` a real-time-capture `SkyLight`, and
`atmosphere: false` suppresses the `SkyAtmosphere`. The bake never reads this
section, so lighting changes are a `mjolnir_level_reload` away — no re-bake, no
restart.

`MJOLNIRWorldBuilder` stands down for any world that has a level file, so its
auto-built sun and floor pad cannot land on top of an authored environment.

### `blam.vehicles` / `blam.weapons` / `blam.equipment` — `type` values

Friendly names resolve through [`defs/level/palette-map.json`](../defs/level/palette-map.json)
to tag paths. v1 requires the resolved tag to already be in the canvas scenario's palette
(B40 ships warthog, ghost, scorpion, banshee, wraith, shade; palette contents for all 13 are in
the palette map). Growing a palette means appending a palette block element — supported by the
bake once block-append lands, but the referenced vehicle's assets may not be streamed for that
map; treat cross-map palette grafts as experimental.

### `blam.objects` — the structures lane

Each entry becomes a `scenery` or `crates` placement in the scnr (palette entry appended as
needed, element cloned from a donor and re-pointed). Object tags bring their own collision and
render models, so this is how ramps, walls, bases, and cover are built. Block capacity is
generous (scenery 2000, crates 1536, palettes 256 each). Restrictions v1: groups `scenery` and
`crates` only (machines/controls need device-group wiring); tag paths must exist in the shipped
tag set (`mjolnir list --paks ... --group scenery_object`).

### `blam.clear`

The host mission keeps running under the variant — its AI, objectives, and scripting are noise
for an arena level. The bake runs its placement passes **first** and the clears afterwards, so each
clone still has a shipped donor to copy from; the clear then keeps only the
elements this bake appended (`Op::KeepLast`) and drops the mission's prefix.
`clear` empties the relevant placement blocks (counts set to zero or
elements disabled) and `scripts: true` swaps the scenario's HSC source for a neutral stub
(mechanism proven — script sections already resize through `blam-tag::write::Edits`). Expect
per-mission iteration on how much clearing a mission tolerates before something native asserts.

### `decor`

`mesh` is a full UE object path: `/Engine/BasicShapes/*` or any shipped `SM_` package
(catalog via `mjolnir mesh list`). The loader spawns `StaticMeshActor`s with `Mobility=Movable`
(the `SetStaticMesh`-refuses-when-Static edge is handled) and applies `tint` through a dynamic
material instance when the base material exposes a color parameter (BasicShapeMaterial does;
WorldGridMaterial does not). Decor never blocks anything — do not fake floors or walls with it.

### `markers`

Inert named points, carried so game-mode work (see
[multiplayer_ctf_plan.md](multiplayer_ctf_plan.md)) can consume them later without a format
change. Names follow the MapKit convention (`flag_red`, `hill_1`, ...).

## File placement and flow

```
Blender (+ addon)                        tools/blender/mjolnir_level
   └─ exports <name>.level.json
        ├─ mjolnir level bake <file>     → scnr override container (_P .utoc/.ucas [+ stub .pak])
        │                                   installs to Meteorite/Content/Paks for testing
        └─ copied verbatim               → .../ue4ss/Mods/MJOLNIRLevelLoader/levels/<SCENARIO>.level.json
                                            read by the loader when that scenario's world arrives
```

Launch the canvas mission through the game's own menu (CAMPAIGN → mission select, or the debug
map menu — `mjolnir_mission` does not cold-start the simulation on current builds; see the
2026-08-19 investigation notes). The loader detects the world, spawns decor, reports via
`mjolnir_level_status`.

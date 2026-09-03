# Making a custom level

The MJOLNIR level pipeline is this game's answer to the old Halo Editing Kit:
author a level in Blender, place vehicles and weapons like Sapien's scenario
editor, bake it like Tool, and play it in the real game. This guide walks the
whole loop. The file format reference is [level_format.md](level_format.md).

## What a custom level is (and isn't) — read this first

A v1 custom level is a **map variant**: it runs on top of one of the 13
shipped campaign maps (the *canvas*), whose world and collision stay loaded.
That's not a stopgap aesthetic choice — it follows from how the game works:

- The Blam simulation owns all gameplay collision, and it **collides only
  with its own world**: the canvas map's BSP plus Blam objects. Unreal
  geometry — cooked or runtime-spawned — is walk-through, drive-through and
  shoot-through, always (verified 2026-08-19,
  [multiplayer_investigation_notes.md](multiplayer_investigation_notes.md)).
- Solid structures are therefore built the way the original Forge community
  built them: from **placed Blam objects** (scenery and crates), which carry
  their own collision. The bake turns your structures into scenario-tag
  placements.
- Unreal meshes still have a place — as **decor**: any of the game's ~12k
  static meshes, tinted engine shapes, skyline dressing. They render; they do
  not exist to the simulation.

Everything solid comes from the scenario override; everything cosmetic comes
from a runtime mod reading your level file. One `.level.json` describes both.

## Setup (once)

| What | How |
|---|---|
| `mjolnir` CLI | `cargo build --release -p blam-cli` (or a release build) |
| Blender 4.0+ addon | install `tools/blender/mjolnir_level` ([its README](../tools/blender/mjolnir_level/README.md)) |
| `MJOLNIRLevelLoader` mod | `scripts\install-bridge.ps1 -Mods MJOLNIRLevelLoader` |
| Mesh catalog (for the decor library) | `mjolnir mesh list --paks <Paks> --out mesh-catalog.json` (~3 min) |

`<Paks>` is `<game>\Meteorite\Content\Paks`; set `HCE_PAKS` once and drop the
`--paks` flags.

## 1 — Author in Blender

Open Blender, sidebar (`N`) → **MJOLNIR**:

1. Set the level slug, the **canvas scenario** (B40 has the fullest vehicle
   palette: warthog, ghost, scorpion, banshee, wraith, shade), and the
   **origin** — the UE-centimeter point on the canvas map where Blender's
   world origin lands. Build around your origin; relocating the level later is
   a one-field edit.
2. Lay the level out in meters, Z-up, as usual. Give every gameplay object a
   **Role** in the object panel:
   - **Player start** ×2+ (co-op needs two)
   - **Vehicle / Weapon / Equipment** with a type (`warthog`,
     `sniper_rifle`, `overshield`, … — the full list is
     `defs/level/palette-map.json`, which also says what each canvas already
     carries)
   - **Structure** with a Blam tag path and group (`scenery`/`crates`) — your
     ramps, walls and cover; these are the solid ones
   - **Decor mesh** for visuals (use *Place shipped mesh…* to browse the
     catalog as real-size proxy boxes)
3. **Export .level.json**.

Keep the playable area on the canvas map's real ground: the simulation's
floor is the BSP, wherever your meshes are. Yaw-only rotations are the safe
kind; compound rotations compose differently between the engines.

## 2 — Bake and install

```
mjolnir level validate my_level.level.json
mjolnir level bake my_level.level.json --install-test
```

`bake` clones shipped placements and re-points them (position, palette entry,
a fresh unique id — never a novel string id, which the native parser rejects),
grows palettes when a structure's tag isn't in them yet, rewrites the
insertion-point-0 player starts, and writes the result through the same
byte-exact container verification `mjolnir pack` uses. `--install-test` puts
the three `pakchunk998-MJOLNIRLEVEL-*` files in `Paks` and copies the level
file to the loader's `levels/` directory.

To iterate on **decor only**, edit the level file in place and run
`mjolnir_level_reload` in the in-game console — no restart. Scenario-side
changes (starts, vehicles, weapons, structures) need a re-bake and a game
restart.

To uninstall: delete the three `pakchunk998-MJOLNIRLEVEL-*` files.

## 3 — Play

Start the game and launch the canvas mission **through the game's own menu**
(Campaign → mission select, or the debug map menu via `mjolnir_debug_ui`).
Do not use `mjolnir_mission` for a cold start — on current builds it loads
the world but never starts the simulation (see the 2026-08-19 investigation
notes).

In-game console (`~`):

- `mjolnir_level_status` — what the loader found and spawned
- `mjolnir_level_reload` — re-read the level file, respawn decor
- `mjolnir_level_clear` — remove spawned decor

Two-player: the second player joins through the normal invite co-op flow and
spawns at your second player start.

## Limits (v1, honest)

- **The canvas mission still runs underneath** — its AI, objectives and music.
  `blam.clear` can empty squads/bipeds/weapons/vehicles, but the mission's
  scripts still reference them; script stubbing is the next planned piece.
  Until then, build away from the mission's hot spots or embrace the chaos.
- Vehicle/weapon/equipment types must already be in the canvas scenario's
  palette (structures grow their palettes automatically; cross-map palette
  grafts are untested — the referenced BP assets may not be streamed for that
  map).
- Rotation conventions beyond yaw are provisional until verified in-game.
- New *worlds* (own BSP, own lighting) need Blam collision generation —
  tracked separately; this pipeline's map variants don't attempt it.

## How it hangs together

```
Blender (+ mjolnir_level addon)
   └─ my_level.level.json
        ├─ mjolnir level bake ──► scnr override container (_P) ──► Paks
        │        solid: starts, vehicles, weapons, equipment, structures
        └─ copied verbatim ─────► ue4ss/Mods/MJOLNIRLevelLoader/levels/
                 cosmetic: decor meshes, spawned on world load
```

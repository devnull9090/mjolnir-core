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

A standalone bake (`mjolnir level bake --standalone CODE`) ships the result as a new launchable
scenario instead of an override of the canvas, and can give it a structure BSP (`--bsp`) and an
Unreal world (`--world`) of its own; the converted CE maps are built that way
([ce_map_conversion.md](ce_map_conversion.md)).

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
      "equipment": true,             // remove the mission's own equipment placements
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
      "tint": [0.8, 0.2, 0.2, 1.0],
      "materials": ["", "/Game/.../MI_Ground.MI_Ground"] }   // slot 0, slot 1, ...
  ],

  "markers": [                       // named points for future game modes; spawns nothing today
    { "name": "flag_red", "pos": [0, 0, 0] }
  ]
}
```

[`defs/level/level.schema.json`](../defs/level/level.schema.json) is a JSON Schema for the
format, but it has fallen behind the keys below and nothing in the repository reads it.
`mjolnir level validate <file>` checks a file the way the bake reads it (`LevelFile` in
`crates/blam-cli/src/level.rs`): no unknown keys, one of the 13 canvas scenarios, a slug `name`,
known palette types, and `scenery` or `crates` objects. The keys a remastered map adds for the
loader alone are unknown to it (see *Keys a converted map adds*).

## Section notes

### `canvas`

`scenario` must be one of the 13 launchable names (`A15 A30 A50 B30 B40 C10 C20 C45 D20 D40
E10 E20 E30`) — the canvas has to be a shipped scenario; a new launchable name comes from a
standalone bake, which registers its codename (`pakchunk996-MJOLNIRREG_P`). The default
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

A converted CE map also carries `post` (a fixed exposure, docs/re/fork_renderer.md)
and may carry `light_scale` (default 256). With a fixed exposure, the loader
multiplies the sun and skylight by the scale and lowers the exposure by
log2 of it. The CE materials divide the exposure back out, so the level looks
the same, while the game's own physical lights (headlights, muzzle flashes,
effects) come down to their designed strength next to it. At scale 1 a
Warthog headlight was 160 times the sun and turned whatever it reached white.
`mjolnir_light_scale <k>` tries a value live; `default` hands it back to the file.

Two more keys come from a CE map's sky and BSP:

- `sky_fog: { color, start, density, height }`. A CE sky with no model,
  such as Coldsnap's, draws as its outdoor fog colour. The loader spawns an
  `ExponentialHeightFog` that starts at `start` (cm, CE's opaque distance),
  so everything farther away turns `color`, the empty sky included. `color`
  is linear and is raised by the light scale like a light. `density`
  defaults to 0.5. `height` (default 400,000 cm) is how far above the canvas
  origin the fog sits.
- `weather: { system, copies, params, follow }`. A Niagara system the game
  ships, `copies` of it (1 to 16), each given `params` (user parameters by
  name, floats). The PNW snow fills a box around its component, not around
  the view, so the copies are spawned in the world at the camera and follow
  it (checked ten times a second, moved once the camera has gone half a
  metre) unless `follow` is false. Attaching them to the camera draws
  nothing, because the camera manager is a hidden actor. `roofs`
  (`{ cell, reach, cells }`, written by `gen_ce_level.py`) lists the
  ceilings over the level by cell; while one is within `reach` above the
  camera the copies are hidden, as CE's weather polygons kept snow out from
  under Coldsnap's roofs.

`MJOLNIRWorldBuilder` stands down for any world that has a level file, so its
auto-built sun and floor pad cannot land on top of an authored environment.

### `blam.vehicles` / `blam.weapons` / `blam.equipment` — `type` values

Friendly names resolve through [`defs/level/palette-map.json`](../defs/level/palette-map.json)
to tag paths. A type the canvas palette lacks gets a palette entry of its own, cloned from entry
0 and re-pointed (B40 has no shotgun or fuel rod, for example); the canvas needs at least one
placement and one palette entry of that kind to clone from. The palette map records what each of
the 13 canvases already carries (B40: warthog, ghost, scorpion, banshee, wraith, shade, pelican).
The added object's assets may still not be streamed for that map; treat cross-map placements as
experimental.

### `blam.objects` — the structures lane

Each entry becomes a `scenery`, `crates` or `machines` placement in the scnr (palette entry
appended as needed, element cloned from a donor and re-pointed). Object tags bring their own
collision and render models, so this is how ramps, walls, bases, and cover are built. Block
capacity is generous (scenery 2000, crates 1536, palettes 256 each). A machine is cut loose
from the donor's device groups (power and position group `none`), so it runs on its own: a
gear turns from the map's start. Controls need device-group wiring and are not supported. Tag
paths must exist in the shipped tag set (`mjolnir list --paks ... --group scenery`, or `--group
crate` for crates) or in a container installed beside the map (Halo 2's machines,
`tools/level/h2_machines.py`).

### `blam.clear`

The host mission keeps running under the variant — its AI, objectives, and scripting are noise
for an arena level. The bake runs its placement passes **first** and the clears afterwards, so each
clone still has a shipped donor to copy from; the clear then keeps only the
elements this bake appended (`Op::KeepLast`) and drops the mission's prefix.
`clear` empties the relevant placement blocks (counts set to zero or
elements disabled; `equipment` covers the mission's equipment placements, and `blocks` names any
other root block to empty, e.g. `["machines", "scenario kill triggers"]`) and `scripts: true`
swaps the scenario's HSC source for one startup script (mechanism proven — script sections already resize through `blam-tag::write::Edits`). Expect
per-mission iteration on how much clearing a mission tolerates before something native asserts.

That startup script is not optional dressing. A Blam map boots faded to black with the HUD
hidden and **every player input faded out**; the mission's own script hands them back, and this
engine's missions do it through `f_insertion_fade_to_gameplay` (decompile any shipped scenario
with `mjolnir script --tag B40 --decompile`): wait for `(game_all_players_active)`, then
`(player_control_fade_in_all_input 1.0)`, `(chud_cinematic_fade 1.0 30)`, `(fade_in 0 0 0 30)`
and `(unit_raise_weapon player0 30)`. A stub that only fades the screen in and calls
`player_enable_input` leaves the player able to look around but not move, shoot or switch
weapons — a cutscene lock with no cutscene. The stub the bake writes does the full handoff.

### `blam.world_bounds`, `blam.set`, `blam.active_bsps`, `blam.single_bsp`, `blam.map_variant`, `blam.cutscene_flags`

- `world_bounds`: `[{ "bsp": 8, "min": [x, y, z], "max": [x, y, z] }]`, Halo
  wu. Sets a structure BSP's box in the scenario; the boxes decide which BSP a
  point belongs to, and a point outside every box is outside the world.
- `set`: `{ "field path": "value" }` for any other scenario field, in the form
  the inspector prints (`"type": "multiplayer"`). Applied last.
- `active_bsps`: `[8]` makes the starting zone set (zone set 0) load only these
  BSPs, and trims its PVS to match. A map on its own BSP needs this: every other
  canvas BSP left active claims its own space. Each kept BSP's PVS clusters
  keep their bit vectors and seam cluster references for the kept BSPs only.
- `single_bsp`: `8` (the BSP `active_bsps` lists) makes that BSP the
  scenario's only one, at index 0. The bake applies it after `--bsp`, so
  `--bsp` and `world_bounds` still name the canvas index. The per-BSP tables
  keep its element; only zone set 0 and its PVS and audibility entries stay;
  the designs, soft ceilings, seams, other insertion points and their player
  starts go; and every placement's origin BSP becomes 0. The BSP tag must be
  built for index 0 (`level collision --own-bsp --bsp-index 0`).
- `map_variant`: `true` adds the `map variant palettes`: one per category
  (weapons, vehicles, equipment, scenery), listing every tag the level places
  and every kind `defs/level/palette-map.json` knows (not the pelican, space
  banshee or seraph), with no quota. Under a multiplayer (Megalo) engine,
  objects whose tags carry multiplayer data exist only through the map
  variant, which the simulation builds from the palette-listed placements; in
  Forge the palettes are what the Monitor places from
  ([forge.md](forge.md)).
- `cutscene_flags`: `[{ "pos": [x, y, z], "yaw": 0 }]` moves the canvas's first
  cutscene flags to these points, so their names stay valid for
  `player_teleport` / `object_teleport` from the Blam console.

A `blam.objects`, `vehicles`, `weapons` or `equipment` element also takes `set`:
fields of the placement, relative to its element
(`"multiplayer data.owner team": "neutral"`).

### `blam.bots` — AI bots ([bots.md](bots.md))

```jsonc
"bots": {
  "squad": "insertion_cov_elites", // the canvas squad each bot is cloned from
  "count": 15,                     // squads bot_0 .. bot_14 (default: one per spawn)
  "spawns": [{ "pos": [x, y, z], "yaw": 0 }], // cycled; default: player_starts
  "weapon": "plasma_rifle",        // a weapon palette entry's path, by substring
  "spacing": 2.5,                  // firing position grid, wu (widened to fit 2048)
  "areas": 16,                     // the firing positions' grid of areas
  "types": [                       // kinds of bot, `count` squads each: <name>_<k>
    { "name": "spartan", "character": "objects\\characters\\spartans\\ai\\mjolnir_bot_spartan",
      "weapon": "assault_rifle", "team": "covenant" },
    { "name": "elite", "character": "elite\\ai\\elite", "weapon": "plasma_rifle" }
  ]
}
```

A type's `character` is a substring of a `character palette` entry, or a full
character tag path, which the bake adds to the palette; `weapon` falls back to
`bots.weapon`, `weapons` (a list) hands its entries out in turn across the
kind's squads, and `team` sets the squads' team. Without `types` there is one
kind, `bot_<k>`, from the donor squad.

The bake clones, before the clears (which keep them): one single-actor squad
per bot, one zone (`mjolnir_bots`) whose firing positions cover the walkable
ground the spawns stand on, one objective (`mjolnir_bots`: task `hunt` over
every area, then `area_<k>` per area, all with `magic player sight`), and one
`ai user hint data` element with every hint list emptied: the AI reads element
0 without checking the block has one, and a map that cleared it crashed.

After `single_bsp` it writes the kept BSP's `ai pathfinding data`, generated
from the `--bsp` payload's collision shell (`blam_sbsp::pathfinding`), and
clears that BSP's `no default structure pathfinding` flag. So `bots` needs the
level's BSP named by `single_bsp` (or `active_bsps`) and given with `--bsp`.

### `multiplayer`

Top-level `"multiplayer": true` asks MJOLNIRLevelLoader to start the level
under the simulation's Megalo engine rather than the campaign
([re/megalo_engine.md](re/megalo_engine.md)). The bake ignores it.

### Keys a converted map adds

A converted CE map's level file carries more. All but `modes` are read by `MJOLNIRLevelLoader`,
and the loader's comments beside each are the reference.

- Accepted by `level bake` and passed over: `variant` (the Megalo game type the map starts
  with), `modes` (the game types the multiplayer menu offers, listed in the `maps.json` an
  install writes), `vehicle_sets` (CE's vehicle sets, from which the loader picks the labels a
  game type requires), `ctf` (Capture the Flag's look: the flag mesh, its materials, the
  stands), `health_pack` (the CE health pack's look) and `foliage` (the game's grass, tufts and
  stones, from a file beside the level).
- Written by `tools/level/upgrade_ce_map.py` for a remastered map, and unknown to
  `level validate` and `level bake`: `landscape` (an Unreal Landscape for the ground), `flux`
  (Fluid Flux over rivers and the sea), `decals` (the game's decal materials), `lights` (CE's
  placed lights as shadowed point lights), `effects` (the game's Niagara ambient life),
  `slot_meshes` (translucent terrain slots as meshes of their own), `shadow_shell` and
  `waterfalls`.
- Under `environment`, beside the keys above: `haze` (Unreal's height fog as distance haze),
  `clouds` (volumetric clouds), `water` (CE water drawn as rolling, reflecting water),
  `sun_mask` (a cooked mask of where the sun reaches the terrain), `sounds` (CE's or Halo 2's
  background sound and sound scenery; an entry's optional `pitch` is a playback rate
  multiplier) and `fade_in` (`false` opts out of the fade-in the loader asks the Blam console
  for).

### `decor`

`mesh` is a full UE object path: `/Engine/BasicShapes/*`, any shipped `SM_` package
(catalog via `mjolnir mesh list`), or one of our own packages under `/Game/MJOLNIR/`. The loader
spawns `StaticMeshActor`s with `Mobility=Movable` (the `SetStaticMesh`-refuses-when-Static edge
is handled) and applies `tint` through a dynamic
material instance when the base material exposes a color parameter (BasicShapeMaterial does;
WorldGridMaterial does not). Decor never blocks anything — do not fake floors or walls with it.

`materials` assigns a material per slot, in order, an empty entry leaving a slot alone. An entry
is a material path (a shipped instance, or one of our own cooked materials) or a runtime
material, `{ "parent", "textures", "scalars", "vectors", "linear" }`, which the loader makes into
a dynamic instance of `parent`. They go on the **component**, not the mesh: a mesh whose
geometry was written into a donor package (see [ue_mesh_write.md](ue_mesh_write.md)) still reports the
donor's single slot however many the package declares, while `SetMaterial` grows the
component's override list to as many sections as the render data names. That is what makes a
transplanted mesh come out textured rather than default grey — Blood Gulch's terrain is one
decor entry with three. `mesh_rewrite --material` prints the list to paste here.

A converted map's decor also uses `cast_shadow` (false on level geometry whose shadows are
baked), `sort_priority` (translucent sort order, for the sky), `pulse` (one runtime-material
scalar driven by a CE periodic function), `scalars` (values on the mesh's own materials),
`static` (no world-position offset), `capture_only` (seen by the Fluid Flux ground capture,
then hidden) and `motion` (a Halo 2 gear that turns: `pivot_cm` from the actor, `period` in
seconds, `keys` as `[seconds, yaw degrees]`, linear between them; with `axis`, a unit vector,
the keys are degrees about it instead of yaw; `events`, `{t, wave, gain, inner, falloff}`,
are one-shots played at the pivot as the turn passes `t`; `follow`, `{class, pos}`, names a
machine of the simulation's own (its Unreal Blueprint class and position, from the canvas
origin) whose collision turns with the part: the loader attaches the mesh to that actor's
turning part once it finds it, and fits the turn's phase, for the sounds, to what the part
does; meshes with the same `entry` (a part's opaque and translucent ones) share that actor,
and each other part claims its own; until then, and without `follow`, the loader turns the actor about the pivot on the
world's clock); see the loader's `spawnDecorItem`.

### `markers`

Inert points, carried so game-mode work (see
[multiplayer_ctf_plan.md](multiplayer_ctf_plan.md)) can consume them later without a format
change. An authored level names them, following the MapKit convention (`flag_red`, `hill_1`,
...); a converted CE map lists its netgame flags as `{ "type", "team", "pos", "yaw" }`
(`ctf_flag`, `hill`, `oddball`, ..., from `defs/level/ce-tag-map.json`). Nothing reads them yet.

## File placement and flow

```
Blender (+ addon)                        tools/blender/mjolnir_level
   └─ exports <name>.level.json
        ├─ mjolnir level bake <file>     → canvas override: pakchunk998-MJOLNIRLEVEL-<name>_P .utoc/.ucas
        │  … --standalone CODE           → a new scenario: pakchunk997-MJOLNIRMAP-<CODE>_P, plus the
        │                                   shared registration container pakchunk996-MJOLNIRREG_P
        │                                   (--install-test writes either to Meteorite/Content/Paks,
        │                                   with a stub .pak)
        └─ copied verbatim               → .../ue4ss/Mods/MJOLNIRLevelLoader/levels/<KEY>.level.json
                                            KEY = the canvas scenario, or CODE for a standalone map;
                                            read by the loader when that world arrives
```

A map installed from a map pack lives at `ue4ss/MJOLNIRMaps/<CODE>/level.json`, which the loader
reads in preference to `levels/` ([map_distribution.md](map_distribution.md)).

Launch the canvas mission through the game's own menu (CAMPAIGN → mission select, or the debug
map menu — `mjolnir_mission` does not cold-start the simulation on current builds; see the
2026-08-19 investigation notes). The loader detects the world, spawns decor, reports via
`mjolnir_level_status`.

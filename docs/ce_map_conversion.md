# Converting a Classic CE Map

**Status:** 2026-09-30. Verified in game on Blood Gulch and Sidewinder,
started from the menu with nothing done by hand: own collision at CE
coordinates, terrain mesh, spawns, vehicles and weapons, the Megalo engine and
the Slayer script (loaded, and the interpreter shown running it; a kill has not
been scored, since that needs a second player).

A classic Halo CE `.map` becomes a standalone multiplayer mission in Halo:
Campaign Evolved: its own scenario, its own collision, its players, vehicles
and weapons placed where CE put them, running under the simulation's Megalo
multiplayer engine.

```bash
export HCE_PAKS=".../Halo Campaign Evolved/Meteorite/Content/Paks"
tools/level/convert_ce_map.sh maps/bloodgulch.map BGL out/bgl --install
```

`CODE` is the new scenario's three-character codename. `--install` writes the
containers into the game and the level file into MJOLNIRLevelLoader; without
it everything lands in the output folder.

## What the command does

| Step | Tool | Result |
|---|---|---|
| 1 | `halo2ue-export` (HalcyonRing) | the `.map` staged: collision BSP, placements, netgame flags |
| 2 | `merge_ce_collision.py`, `mjolnir level collision --own-bsp` | the structure BSP, scenery collision included |
| 3 | `merge_ce_scene.py`, `ce_material_spec.py`, `build_terrain_meshes.py` (`mesh_rewrite` + `package_override`), `unreal/MJOLNIRMaterials` | the terrain, scenery and sky as two meshes (over `/Engine/BasicShapes/Cylinder` and `Cone`), and their CE materials and bitmaps (`pakchunk988-MJOLNIRMAT`) |
| 4 | `tools/level/gen_ce_level.py` | the level file |
| 5 | `mjolnir level bake --standalone CODE --bsp 8=…` | scenario and registration containers, on the map's own empty Unreal world |
| 6 | `tools/level/build_spawn_point.sh` | the spawn-point and teleporter scenery every converted map places |

**The world must be a Blam world.** Step 5 gives the bare MapKit world
`BlamWorldSettings` with a `DefaultScenario` path (`blam_world_settings` in
`crates/blam-cli/src/level.rs`). Four world subsystems are created only when
the glue engine subsystem accepts the world (CU4 `+0x7b93a50`: the settings
are a `BlamWorldSettings` whose `DefaultScenario` soft path is set):

- `HaloMaterialResponseWorldSubsystem`
- `BlamMapGlueOuterSubsystem`
- `BlamSynchronizationPrecreateObjectActorWorldSubsystem`
- `BlamBreakableSurfaceSaveGameSubsystem`

On plain `WorldSettings` none of them existed, and bullet impacts, tracers
and surface footsteps were missing. A shipped level points `DefaultScenario`
at its `BlamScenario` actor. Ours names `PersistentLevel.BlamScenario`, which
the gate does not resolve, and with it the world has the same 35 subsystems
as B40.

Build the tools first: `cargo build --release -p blam-cli -p ue-asset --example
mesh_rewrite -p blam-pack --example package_override`.

### The structure BSP (step 2)

Built on `BSP_03_1_Chasm_old`, a small shipped BSP with one kd supernode, one
cluster and one instance, of which only the file format is kept
(`blam_sbsp::convert::convert_own`, [ce_terrain_collision.md](ce_terrain_collision.md)):

- the CE collision tree goes into the **world shell**, which decides what is
  inside the world;
- and into **definition 0 behind instance 0**, which the collision queries
  test (the instance is listed at the collision kd hierarchy's root);
- the BSP's static Havok body, **`structure_physics`**, is recompiled with one
  key per CE surface. This is what players, vehicles and items stand on;
  nothing rebuilds it at load.

The map keeps its CE coordinates. It is built for **index 0**
(`level collision --bsp-index 0`): every kd hierarchy header and instance
shape names the BSP's index, and the donor's own say 7.

**A scenario of its own.** The scenario is still cloned from B40's, but the
bake leaves none of B40 in it (`blam.single_bsp`, applied after `--bsp 8=`
has pointed slot 8 at the map's BSP):

- `structure bsps`, `ai pathfinding data`, `scenario cluster data` and each
  PVS's and audibility's per-BSP mappings keep slot 8's element, now index 0.
  The cluster data's BSP reference names the map's own BSP.
- Only zone set 0 stays, with its PVS and audibility entries. Its masks,
  each PVS cluster's bit vectors and its seam cluster references name BSP 0
  alone.
- The designs (B40's soft ceilings), the soft ceilings and both seams
  references are cleared, as are B40's other insertion points and their 36
  player starts.
- Every placement's origin BSP is 0 and it may attach to BSP 0.
- B40's mission content goes with the rest of the clears: crates (on BSP 0
  they would spawn in the map), device groups, object names, cutscene flags,
  cinematics, AI objectives, reference frames, UI objectives, AI hints and the
  script point sets (the last two name B40's BSPs by index).

The baked scenario shrinks from 7.1 MB to about 0.27 MB. `CANVAS_BSPS=1
convert_ce_map.sh` keeps the canvas's BSPs (index 8, `blam.active_bsps` only).

**Scenery collision.** The game ships no Blam rocks or trees whose collision a
placement could borrow, so `tools/level/merge_ce_collision.py` adds the
scenery's own collision models to the BSP's collision first:

- the exporter stages each scenery tag's collision triangles
  (`collision/*.json`);
- every placement's triangles go in as standalone two-sided surfaces;
- the compiled MOPP gives every surface a key, so players and vehicles stand
  on and run into rocks and trees as in CE;
- no BSP leaf references the added surfaces, so queries that walk the BSP
  tree, such as projectiles, pass through them.

**Surface materials.** The game picks footstep sounds, tire dust and bullet
impacts from each collision surface's material. Each surface keeps its CE
collision material (`convert::Options::keep_materials`), and `mjolnir level
collision` writes the BSP's `collision materials` block with one entry per CE
material. Each entry's render method is the game's own `shaders\<material>`,
and its runtime global material index is that shader's `material name` looked
up in `globals`.

| CE shader `material type` (header +34) | game material |
|---|---|
| dirt, sand, stone, snow | `tough_terrain_dirt`, `_sand`, `hard_terrain_stone`, `soft_terrain_snow` |
| wood, leaves | `tough_organic_wood`, `soft_organic_plant` |
| metal hollow / thin, metal thick | `hard_metal_thin`, `hard_metal_thick` |
| rubber, glass, force field, water, ice | `tough_inorganic_rubber`, `brittle_glass`, `energy_hologram`, `liquid_thin_water`, `hard_terrain_ice` |
| anything else | `default_material` |

`merge_ce_collision.py` adds two corrections before the conversion:

- **Grass.** CE has no grass type. Blood Gulch's ground is one "sand" shader,
  blended, whose secondary detail map is grass. Each of its surfaces is
  sampled through the render geometry: the base map's alpha at the surface's
  points (low alpha shows the secondary detail). Surfaces that are mostly
  grass get `tough_terrain_grass`, 1,178 of 2,423 on Blood Gulch.
- **Scenery** carries no shader, so its material comes from its name: rock,
  wood or plant.

Gephyrophobia has more than 8,191 surfaces, so its `structure_physics` uses
one whole-instance key (see above). Havok contacts there may report one
material even though the surfaces carry theirs. Untested.

### The terrain, scenery and sky (step 3)

`tools/level/merge_ce_scene.py` puts everything static into the BSP's glTF.

- **Scenery:** every scenery placement's model goes in at its CE position and
  rotation. CE lights an object from the lightmap under it, so each
  placement's vertices take the lightmap UV of the BSP point below its origin.
- **Sky:** the sky model (dome, ring, clouds, horizon) goes in with its
  origin, the viewer, at the map's centre. It is scaled so its nearest layer
  is 3 km away (the ring ends up about 46 km out).

The scene becomes two meshes, written into shipped basic shapes in the game's
own serialisation ([ue_mesh_write.md](ue_mesh_write.md)). Each is normalised
into its donor's bounds, and MJOLNIRLevelLoader spawns it at the position and
scale that undo the normalisation.

| Mesh | Donor | Container | Holds |
|---|---|---|---|
| Opaque | `/Engine/BasicShapes/Cylinder` | `pakchunk989-MJOLNIRMESH` | terrain and scenery |
| Transparent | `/Engine/BasicShapes/Cone` | `pakchunk987-MJOLNIRMESHT` | sky, lights, teleporter fields |

A rewritten mesh enters Unreal's translucency pass only through its single
donor slot ([re/fork_renderer.md](re/fork_renderer.md)), so the transparent
mesh's slot 0 is its first section, the sky.

Each mesh carries:

- one section per glTF material, i.e. per (CE shader, lightmap page);
- the CE lightmap UVs as a second UV channel (`--lightmap-uvs`);
- CE's bump tangents;
- the incident radiosity vector, in each vertex's tangent frame, as the
  vertex colour: the unit direction in rgb, and in alpha its length, which
  weights the bumped-lightmap term.

CE's bitmaps import with their own mip chains (DDS). CE's detail maps fade
their smaller levels to neutral grey, which is what keeps detail tiling from
showing at a distance; a regenerated chain would not.

### Materials (step 3)

The terrain draws with real materials that reproduce CE's shaders.

**How they're built and shipped.** The Unreal project in
[`unreal/MJOLNIRMaterials`](../unreal/MJOLNIRMaterials) (UE 5.5) builds and
cooks them:

1. `tools/level/ce_material_spec.py` lists every bitmap a surface samples,
   lightmap pages and cube maps included, and one material per mesh section
   with the CE shader's fields as parameters.
2. `Scripts/build_ce_materials.py` builds the master materials.
3. `Scripts/build_ce_level.py` imports the level's bitmaps.
4. `tools/ue/cook.ps1` cooks them into `pakchunk988-MJOLNIRMAT`.
5. At load, MJOLNIRLevelLoader makes a dynamic instance of a master per mesh
   slot and sets that slot's textures and parameters.

Cooked material instances are not used: the game crashes loading one.

**What it took to make a stock-cooked material draw in the fork.** See
[re/fork_renderer.md](re/fork_renderer.md):

- the fork's uniform buffer layouts;
- its 44-float4 GPU-scene primitive stride;
- `r.CompileShadersForDevelopment=0`.

The project's `MjolnirForkLayouts` plugin recreates the first two before
anything compiles.

**The shading.** It is CE's fixed-function math, done in the bitmaps' own
gamma space as the hardware did.

| Pass | What the material does |
|---|---|
| Texture | Base map, then the primary/secondary detail blend: by the base map's alpha for *blended* shaders, by the secondary map's alpha for *normal* ones. Then the micro detail. Each with its function: 0 `2·B·D`, 1 `B·D`, 2 `B + 2D − 1`. Each step clamped. |
| Lightmap | `lightmap × material colour × mix(1, N·L, incident weight)`. N is the bump normal, L the baked incident direction. Plus self-illumination: primary, secondary and plasma channels, each animated between its off and on colour by CE's periodic functions. |
| Frame | lightmap pass × texture pass, no 2× |
| Specular lightmap | Shaders with the "lightmap" specular flag. `mix(parallel, perpendicular colour, N·E) × brightness × lightmap luminance × (R·L)⁸`; ³² for "extra shiny", ×2 for "overbright". |
| Reflection | The cube map, in D3D face order, sampled along the eye vector reflected about the bump normal (the vertex normal for a flat cube map). `mix(c⁸, c, tint) × brightness`, where tint and brightness go from their parallel to their perpendicular values by the squared view term. Added, masked by bump alpha × the texture pass's specular mask. |
| Alpha test | On the bump map's alpha: `> 0x7F` passes. |
| Fog | The sky's outdoor atmospheric fog: `max density × saturate((depth − start) / (opaque − start))` towards its colour. |

Transparent chicago shaders (lights, the teleporter field) work like this:

- up to four maps, each with its own UV scale, offset, rotation and
  scrolling animation;
- each stage folds the next map in with its colour and alpha functions
  (current, next, multiply, double multiply, add, add-signed, subtract,
  blend by alpha);
- the result is drawn with the shader's framebuffer blend: alpha blend, add,
  or multiply. Subtract, min and max have no Unreal blend mode and fall back
  to alpha blending.

**Colour reaching the screen unchanged.** Each material:

1. decodes its result to linear;
2. divides out the camera's exposure (`EyeAdaptationInverse`);
3. hands the tonemapper CE's own colour.

The level's post-process volume (`environment.post`) turns the filmic curve,
gamut expansion and blue correction off, so the tonemapper leaves it as it is.

**Where the data comes from.** `halo2ue-export` stages:

- the lightmap vertices: in a cache file they follow the rendered vertices
  in the same blob;
- cube maps as six faces, plus the specular colours, the three
  self-illumination channels, every chicago stage and the sky's fog;
- each vehicle's per-game-type spawn flags, so the level places only the
  game type's default vehicle set (`gen_ce_level.py --game-type`).

Without the Unreal editor (`CE_COOK=0`) the converter falls back to
`tools/level/ce_textures.py`: one composited texture per shader on a shipped
material, with no lightmaps.

### Ambient sound (step 3)

The game ships none of CE's ambience as Blam sound tags. Its 163 looping
sounds are material, vehicle and weapon loops, and the remake's ambience
lives in its own Unreal levels. CE's sounds therefore come from CE's files
and play through Unreal's own audio engine, which the game runs beside its
own.

1. **Extract.** `tools/level/ce_sounds.py <map> <sounds.map> <staging> <out>`
   reads a Custom Edition map (cache version 609). Its sound tags are
   indexed: `sounds.map` holds each whole tag as `<path>` and its samples as
   `<path>__permutations`; the docstring has the layouts. The script
   extracts:
   - the **sound scenery** (halo2ue's `sound_scenery` placements), such as
     the teleporter hum;
   - the **background sound**, the looping sounds the BSP block depends on;
   - each looping sound's **tracks** and detail sounds.

   Xbox ADPCM is decoded to WAV and Ogg is kept as is. A loop's permutations
   are joined into one `_loop` file, because CE plays them back to back.
2. **Import.** `unreal/MJOLNIRMaterials/Scripts/build_ce_sounds.py` imports
   them under `/Game/MJOLNIR/Levels/<map>/Sounds`, which cooks into
   `pakchunk988`. Loops are marked looping, and the compression is ADPCM:
   the default, Bink, needs a decoder the game may not ship.
3. **Play.** `gen_ce_level.py --sounds` writes `environment.sounds`, and
   MJOLNIRLevelLoader plays it:
   - background loops in 2D, map-wide;
   - emitters in 3D at the CE positions, falling off linearly over CE's
     distance bounds.

Detail sounds (random one-shots) are extracted but not yet played.

**Event sounds.** The game engine still has Reach's event list:
`game_engine_globals` holds 510 events, each with a sound and announcer line,
and `megalogamengine_sounds` names 95 mode announcements. But 336 of the 339
sound tags the events name were cut from the build, and 94 of the 95
announcements are empty. The events themselves still fire, and they reach
Unreal as `BlamIncident`s on the game state's
`BPC_MeteoriteIncidentHandlerComponent` (`OnIncident_Event`, which can be
hooked), for example:

- `teleporter_used`
- `respawn_tick`, `respawn_final_tick`
- `death`, `suicide`, `player_spawn`

`ce_sounds.py --events <sounds.map> <out>` extracts every CE announcer line
(Ogg Vorbis; Unreal's importer decodes it) and the UI sounds the events need,
and writes `mods/MJOLNIRLevelLoader/events.json` (event name to waves).
`build_ce_sounds.py` imports them under `/Game/MJOLNIR/Sounds/Events`, and
the loader plays an event's sound on converted multiplayer levels only.
Personal events (teleport, respawn ticks, multikills and sprees) play only
for the player who caused them, taken to be absolute index 0, the host's
first local player. A networked client's index is not exposed to scripts
yet.

The waves are loaded when the level is furnished, and the hook only queues
the event; a 100 ms game-thread loop plays it. Loading and playing inside
the hook froze the game on the first teleport. No game-start event is
raised on a converted map, so the game type's announcement ("Slayer",
"King of the Hill" and so on) plays once per match, picked by the variant
the menu started. It plays when the player's pawn first exists, because the
opening spawn raises no `player_spawn` (only respawns do), or at the first
`player_spawn` if that comes sooner.

### The level file (step 4)

- **Spawn points.** Under a multiplayer engine players spawn only at scenery
  whose multiplayer type is *player spawn location*; the scenario's player
  starts are not read. One is placed at every CE start (neutral team).
- **Vehicles, weapons, pickups** through `defs/level/ce-tag-map.json`; each CE
  tag maps to the first equivalent the game has a type for
  (`defs/level/palette-map.json`). The bake adds a type the canvas palette
  lacks: the shotgun and the fuel rod (Reach's `flak_cannon`) are not in
  B40's. What has no equivalent is reported as dropped: the flamethrower
  (none ships).
- **Map variant palette** (`blam.map_variant`). Objects with multiplayer data
  exist only through the map variant, which is built from the placements whose
  tags a palette lists. A model variant gets an entry of its own. Grenades,
  the overshield and camouflage also need the game variant's map options
  (grenades, equipment and powerups on map), which `megalo write` sets.
- **Vehicles:** every vehicle the CE scenario places (`--game-type all`), as
  CE's "all vehicles" sets did. Most Ghosts, Banshees, Scorpions and rocket
  Warthogs are in no game type's default set (spawn flags `0xf00`), so a
  default set left the big maps nearly empty; no stock map stacks two
  vehicles on one spot. The rocket Warthog is the Warthog with its `rocket`
  model variant (`permutation data.variant name`); its turret has no Unreal
  actor of its own. Banshees start 0.3 wu above CE's height and fall into
  place (`VEHICLE_LIFT`): at CE's height on Blood Gulch's roofs they started
  inside them and were thrown on their sides.
- **Respawn times.** Each weapon and pickup respawns after CE's time: its
  placement's, else its item collection's (halo2ue's
  `collection_spawn_time`), else 30 s. Vehicles respawn after 30 s and are
  given back 30 s after being left away from their spot. A map variant object
  with spawn time 0 never came back.
- **Teleporters:** a sender at every CE "teleport from" flag and a receiver at
  every "teleport to" flag. The simulation keeps Reach's multiplayer
  teleporters, which pair ends by channel. CE numbers a map's channels freely
  (Gephyrophobia uses 2–7, 13 and 14; Infinity 11–24), so the generator
  renumbers each map's channels from alpha in CE order, across the scenario's
  26 (alpha to zulu), and warns about a channel missing either end. Chiron
  TL-34 has 30 channels, more than the enum names. The first version kept
  only channels 0–5 and dropped the rest silently, which left Gephyrophobia
  with half its pads.
  The two games turn the player differently:
  - **CE** turns the player to the "teleport to" flag's facing.
  - **Reach** keeps the facing relative to the sender, whose front faces the
    player walking in.

  With CE's flag facings, players had to walk in backwards to exit the right
  way. So each sender is turned 180° from its CE flag, and walking in head-on
  exits facing the receiver's direction, as in CE.
- **The post-process volume** (`environment.post`): fixed exposure, no local
  exposure, no filmic curve. The CE materials then show CE's colours
  ([re/fork_renderer.md](re/fork_renderer.md)).
- `"multiplayer": true`, `blam.active_bsps`, `blam.single_bsp`, the scenario
  `type` set to multiplayer.

### Capture the Flag

A map whose CE scenario has a CTF flag for each team offers CTF in the
multiplayer menu (`"modes": ["slayer", "ctf"]`). No CTF ships in this build:
there is no variant, no flag object and no flag mesh, so each piece is ours.

- **The rules** are a Megalo variant, `variants/ctf.mglo`
  (`mjolnir megalo write --mode ctf`, `crates/blam-megalo/src/ctf.rs`). The
  script makes each team's flag on its stand, scores a capture when the
  carrier stands in their own stand's boundary while their own flag is home,
  returns a dropped flag when its own team touches it or after 30 s, and ends
  the round at 3 captures. The flag incidents (`flag_grabbed` 110,
  `flag_dropped` 112, `flag_scored` 116, `flag_reset` 118, `flag_recovered`
  119) carry the flag's team as their value (Unreal's `CustomValue`), so
  the loader plays CE's team lines ("Red team has the flag", "Blue team
  score", "Red team flag returned"). The action and condition encodings
  match ReachVariantTool's opcode list; they are checked against the CU4
  decoder in [re/megalo_variant_format.md](re/megalo_variant_format.md).
- **Teams.** Each CE start is labelled `ctf_spawn_red`, `ctf_spawn_blue` or
  `ctf_spawn_none` and placed neutral. The variant gives the red and blue
  spawn points their teams, and parks the rest on a team no player is on.
  It waits 2 s before the first spawn (the loadout camera time), so the
  first tick has set the teams up; a spawn on tick 0 used them neutral.
- **The flag** (`tools/level/build_ctf_flag.sh`) is a weapon cloned from the
  assault bomb, which ships whole and is carried the same way. It is entry
  18 of the multiplayer object type list, which the script needs before it
  can create one. The bomb binds no Unreal actor, so the flag borrows the
  oddball's `BP_SkullActor`. MJOLNIRLevelLoader hides the skull, removes its
  fire effect and whispering audio, and attaches CE's own flag mesh in its
  team's colours. The mesh is exported by halo2ue and rewritten into
  `/Game/MJOLNIR/CTF/SM_CE_Flag`; its textures come from
  `tools/level/ce_flag_textures.py`. The stand needs no mesh: CE's own flag
  base scenery sits at each flag and comes in with the map.
- **Armour colours.** In a team game the loader gives each Spartan's armour,
  and the local player's first-person arms, legs and shadow, a dynamic
  instance with `Armor Color` set to red or blue. The parameter is read at
  global association with index **0**: the plain setter writes index -1,
  which this layered material never reads, so it must be set by info. A
  respawn reuses the actor and puts the stock armour back, so the loader
  re-tints after every spawn.

### Health packs

This game ships no health pack (no object, no Unreal asset, none placed in
the campaign), and its health never recharges, as CE's did not. So every
variant the loader ships carries CE's health packs as Megalo script
(`crates/blam-megalo/src/powerups.rs`, on by default in
`mjolnir megalo write`):

- Each CE health pack becomes a spot, invisible scenery labelled
  `ce_health_pack` (`objects\multi\powerups\health_pack_spot`).
- Each tick, a spot with no pack whose countdown has run out creates one: the
  equipment `objects\multi\powerups\health_pack`, multiplayer object type list
  entry 19, which nobody can pick up.
- A living player whose biped comes within reach of the pack (8 feet, origin
  to origin, by the Get Distance action) and whose health is under 100% is
  healed to full (Modify Object Health); the pack goes, and comes back after
  30 s. Shields are left alone.
- The pickup raises Race's `lap_complete` incident, and the loader plays CE's
  `pickup_health` to that player. `recharge_health` would be the natural
  incident, but the simulation never hands it to Unreal.
- The pack is cloned from the battle rifle ammo pickup (no CE map places
  battle rifle ammo), and the loader puts CE's health pack mesh
  (`/Game/MJOLNIR/CE/Powerups/SM_CE_HealthPack`) on that actor in place of
  its own.

The actions are Reach's (54/55 get shields/health, 64/65 modify, 66 get
distance), at the same numbers in CU4's decoder.

## Playing it

CAMPAIGN → NEW GAME → the map (the last mission). `"multiplayer": true` tells
MJOLNIRLevelLoader's native half to switch the simulation to the Megalo engine
when that mission starts, and back before any other mission; `"variant":
"slayer"` makes it install `variants/slayer.mglo` (written by `--install`)
where the simulation's variant loader reads it. It needs
`native/mjolnir_map_registry.dll` built from this revision. The patches and
why each is needed are in [re/megalo_engine.md](re/megalo_engine.md); the
manual form of the engine switch, without the variant, is:

```bash
mjolnir live engine --launch-engine 2 --map-variant-gate skip --map-variant-reset skip   # at the main menu
```

The level spawns its terrain once the player pawn exists, so the first
seconds after the loading screen are dark.

## Limits

- **Visuals.** No decals, lens flares or weather yet. Dynamic lights
  (muzzle flashes, the flashlight) do not light the terrain: it is unlit,
  lit by its lightmaps as in CE. Scenery takes the lightmap colour under its
  origin; CE's per-object directional terms are not reproduced. One converted
  map installed at a time: its meshes override the two donor shapes.
- **Scenery collision** stops players and vehicles, not projectiles.
- **Approximations in the materials.** CE's noise, jitter and wander
  functions are a value noise; the variable-period functions use their
  nominal period. The plasma self-illumination band's width and the
  "add signed" chicago functions are estimates. The reflection's view term
  uses the per-pixel eye vector where CE used the camera's forward vector.
  Water (`swat`), glass (`sgla`) and the reflection lightmap mask are not
  reproduced.
- **One standalone map installed at a time:** each ships its own override of
  `DT_Scenarios`.
- **More than 8,191 surfaces** (Sidewinder, Infinity, Death Island, ...): the
  static body lists the terrain as one whole-instance key instead of one key
  per surface. Verified on Sidewinder: players walk and vehicles rest on it.
- **One BSP per map.** Coldsnap's second BSP is not converted.
- **The canvas palette.** Weapons and vehicles the canvas mission never
  places (shotgun, flamethrower, fuel rod, health packs) are dropped.
- **Extent.** Keep a map inside the canvas level's overall extent: lifted 800 wu
  above B40, Havok flung objects hundreds of wu.
- **Game modes.** Slayer only (`mjolnir megalo write --mode slayer --score N
  --out .../MJOLNIRLevelLoader/variants/slayer.mglo` changes the score to
  win). Without the file the map runs the empty default variant: players
  spawn, nothing scores. `--mode tick` scores every player every tick, a
  smoke test for the interpreter. CTF, Oddball and King need their scripts
  written.

# Blam Tag Data in Halo Campaign Evolved

**Status:** Active research
**Last verified:** 2026-07-26
**Game build:** `2026.06.26.1097863.1-Rel-i343-Meteorite-2606-CU2`
**Host SHA-256:** `0670FAA751E2553940B90DF6BE43D3B0FF59EA87F22155CF3C3FE9D439367F1D`

> **Build label:** this note is stamped CU2; the installed build is CU3. See
> [`build_lock.md`](build_lock.md) for what has been re-verified against CU3 and for a
> caveat about CU2-stamped notes dated after 2026-08-01.

## Question

Does Halo Campaign Evolved run on real Blam tag data like the classic games, or are bipeds,
weapons, vehicles, and levels ordinary Unreal Engine assets with Halo-themed names?

## Answer

**Verified: both, split by responsibility.**

The shipping build contains `12,328` genuine Blam tag files spanning `101` classic tag groups.
Every sampled payload carries the `BLAM` tag-file signature and a group four-character code that
matches its filename. Simulation-side definitions — bipeds, weapons, vehicles, projectiles, AI
characters, squads, animation graphs, collision models, physics models, damage effects, Megalo,
multiplayer variant settings — are real tags.

Rendering is entirely Unreal. **Zero** `render_model` tags and **zero** `bitmap` tags ship. The
classic Blam render pipeline is absent; visual representation is bound through UE5 Blueprint actors
referenced from the tag packages.

## Evidence Labels

- **Verified:** reproduced by an executable check against the installed build.
- **Observed:** present in an artifact, but runtime reachability is not proven.
- **Hypothesis:** a testable interpretation that still needs a discriminating check.

## Packaging Layout

**Verified:** all `28` IoStore containers under `Meteorite/Content/Paks` parse as UE 5.5 TOC
version `8` (`ReplaceIoChunkHashWithIoHash`), Oodle-compressed, indexed, and not encrypted. The
directory index lists `132,091` entries.

| Extension | Count |
|---|---:|
| `.uasset` | 89,685 |
| `.ubulk` | 28,151 |
| `.umap` | 14,240 |
| `.ushaderbytecode` | 15 |

There are no `ExternalFile` chunks and no loose tag or `.map` cache files anywhere in the install.
Every tag is packaged as a normal cooked Unreal package.

**Verified:** `24,618` index entries live under `Meteorite/Content/Tags`, split into `12,328`
`.uasset` headers (`8.5 MiB` total) and `12,290` `.ubulk` payloads (`5,648.6 MiB` total). Each tag
is one Unreal package whose bulk-data segment is the raw Blam tag file.

Naming convention: the Blam path `objects\characters\elite\elite.biped` becomes the Unreal package
`/Game/Tags/objects/characters/elite/elite-biped`. The group separator changed from `.` to `-`
because Unreal reserves `.` for the object path separator.

## Tag Container Format

**Verified across `168` sampled payloads covering all `101` shipped groups:** every `.ubulk` begins
with a `0x4C`-byte header, and `header + payload_size == chunk_size` holds for every sample.

| Offset | Size | Field | Evidence |
|---:|---:|---|---|
| `0x00` | `0x24` | Zero in every sample. | Verified |
| `0x24` | 4 | `0x00000001` in every sample. | Verified |
| `0x28` | 4 | `0x00000002` in every sample. | Verified |
| `0x2C` | 4 | `0xFFFFFFFF` in every sample. | Verified |
| `0x30` | 4 | Group four-CC, little-endian (`bipd`, `weap`, `vehi`, `sbsp`, ...). Matches the filename group in `168/168` samples. | Verified |
| `0x34` | 4 | Small integer, group-constant (`bipd`=3, `weap`=2, `sbsp`=5, `coll`=10). | Observed |
| `0x38` | 4 | Per-tag 32-bit value, differs between tags of the same group. | Observed |
| `0x3C` | 4 | `BLAM` signature, stored as the little-endian uint32 `0x4D414C42`. | Verified |
| `0x40` | 4 | `tag!` signature, stored as `0x21676174`. | Verified |
| `0x44` | 4 | Zero in every sample. | Verified |
| `0x48` | 4 | Payload size. Equals `chunk_size - 0x4C` in `168/168` samples. | Verified |
| `0x4C` | — | Tag body begins. | Verified |

**Hypothesis:** the value at `0x34` is a tag-group version number. It is constant per group and its
magnitude tracks group complexity, but no discriminating check has been run.

The body opens with additional group-invariant marker dwords (`blay`, then `4444`, `CCCC`, `wwww`
in a `weapon` sample), followed by a per-group value and a table of record counts. **Superseded
2026-07-26:** the markers are fixed ASCII fill constants and the count table is a manifest for the
twelve definition tables, checked against them for all 12,290 tags. See
[`tag_body_format.md`](tag_body_format.md).

## Unreal Wrapper Classes

**Verified** by resolving the global `ScriptObjects` chunk in `global.utoc` (`54,825` script
objects) and parsing the zen package header:

```text
/Game/Tags/objects/characters/elite/elite-biped
  export[0] elite-biped
    class    = /Script/BlamSynchronization/BlamBipedTagDataAsset
    template = /Script/BlamSynchronization/Default__BlamBipedTagDataAsset
    serial   = 104 bytes            (tag body lives in the 49,702-byte .ubulk)
```

`/Script/BlamSynchronization` declares `176` `Blam*TagDataAsset` classes; `101` of them have shipped
instances. Examples: `BlamBipedTagDataAsset`, `BlamWeaponTagDataAsset`, `BlamVehicleTagDataAsset`,
`BlamScenarioTagDataAsset`, `BlamScenarioStructureBspTagDataAsset`, `BlamModelAnimationGraphTagDataAsset`,
`BlamMultiplayerGlobalsTagDataAsset`, `BlamMegaloStringIdTableTagDataAsset`.

The class list also declares render-side wrappers that **never ship data**, including
`BlamRenderModelTagDataAsset`, `BlamBitmapTagDataAsset`, `BlamPixelShaderTagDataAsset`, and
`BlamVertexShaderTagDataAsset`. Their presence is a source-level artifact of the shared plugin, not
evidence that Blam rendering is reachable.

## Simulation-vs-Presentation Split

**Verified** from the cooked package import tables.

`elite-biped` imports `26` packages. They fall into two groups:

- Blam tags: `elite-model`, `needle_rifle-weapon`, `hologram_elite-biped`,
  `biped_player-collision_damage`, `assassination-damage_effect`,
  `biped_assassination_camera-camera_track`, and similar.
- Unreal presentation: `/Game/Blueprints/Synchronization/Characters/BP_EliteBipedActor`,
  `/Game/Blueprints/FX/BipedEffects/Covenant/BP_EliteCovenantBipedEffects`, and FluidFlux
  interaction components.

`elite-model` (`hlmt`) imports `16` packages, **all of them Blam tags**:
`elite-collision_model`, `elite-physics_model`, `elite-skeleton_model`,
`elite-model_animation_graph`, plus shield effects and impacts. It references no mesh, no material,
and no texture.

This is the load-bearing result. The Blam `model` tag retains the classic collision, physics,
skeleton, and animation-graph chain that the simulation needs, and delegates everything visible to a
Blueprint actor named at the object-definition level.

## Shipped Tag Inventory

Counts are `.uasset` headers, which equal tag count.

| Subtree | Tags |
|---|---:|
| `Tags/sound` | 6,125 |
| `Tags/objects` | 3,928 |
| `Tags/FX` | 397 |
| `Tags/ai` | 388 |
| `Tags/multiplayer` | 319 |
| `Tags/levels` | 319 |
| `Tags/UI` | 304 |
| `Tags/globals` | 241 |
| `Tags/firefight` | 184 |
| `Tags/Cinematics` | 50 |
| `Tags/Shaders` | 29 |
| `Tags/camera` | 23 |
| `Tags/default` | 20 |

Selected groups:

| Group | Four-CC | Count |
|---|---|---:|
| `sound` | `snd!` | 5,895 |
| `effect` | `effe` | 884 |
| `skeleton_model` | `skel` | 460 |
| `model` | `hlmt` | 451 |
| `collision_model` | `coll` | 424 |
| `physics_model` | `phmo` | 421 |
| `squad_template` | `sqtm` | 343 |
| `model_animation_graph` | `jmad` | 176 |
| `character` | `char` | 132 |
| `scenario_structure_bsp` | `sbsp` | 122 |
| `multiplayer_variant_settings_interface_definition` | `goof` | 89 |
| `weapon` | `weap` | 75 |
| `projectile` | `proj` | 61 |
| `biped` | `bipd` | 32 |
| `vehicle` | `vehi` | 25 |
| `equipment` | `eqip` | 20 |
| `scenario` | `scnr` | 13 |
| `render_model` | `mode` | **0** |
| `bitmap` | `bitm` | **0** |

## Level Pipeline

**Verified:** `312` tags live under a `_Generated_` directory, and they are exactly the world
geometry groups.

| Group | Count |
|---|---:|
| `scenario_structure_bsp` | 122 |
| `scenario_structure_lighting_info` | 122 |
| `structure_design` | 42 |
| `scenario` | 13 |
| `structure_seams` | 13 |

The `13` generated `scenario` tags correspond one-to-one with the `13` root Halo world packages
under `/Game/Levels/Halo1/Solo`:

```text
Tags/Levels/Halo1/Solo/A30/_Generated_/a30-scenario
Tags/Levels/Halo1/Solo/A30/_Generated_/holdouts-scenario_structure_bsp
Tags/Levels/Halo1/Solo/A30/_Generated_/holdout_softceiling-structure_design
Tags/Levels/Halo1/Solo/A30/_Generated_/A30-structure_seams
```

**Hypothesis:** levels are authored in Unreal and the Blam scenario, BSP, seam, and soft-ceiling
tags are emitted from the Unreal world at cook time, giving the simulation the collision and
structure representation it requires. The `_Generated_` directory name and the absence of any
hand-authored scenario tag support this, but the cooker itself has not been observed.

**Verified 2026-08-07:** the shipped `sbsp` payloads carry no render geometry, only its skeleton.
Walking `holdouts-scenario_structure_bsp` (143.1 MiB) in full shows the tag is dominated by
collision data — winged-edge collision BSPs for 754 instanced-geometry definitions (~110 MiB),
Havok mopp code, and kd/supernode hierarchies — while `render geometry` holds 755 mesh
descriptors and compression-info bounds with an `api resource` body of **zero bytes**, and both
`resource interface` pageable resources are likewise unattached (section magic third byte NUL).
The same holds for per-object tags: `collision_model` and `skeleton_model` payloads are complete,
but no vertex or index buffer exists anywhere in the Blam data. Mesh data ships only as Unreal
`SK_*`/`SM_*` packages (593 skeletal-mesh and 22,610 static-mesh packages in the index).
Reproduce with `cargo run --example probe_geometry -- scenario_structure_bsp holdouts` and
`--example probe_meshes -- elite` in `apps/tag-editor/src-tauri`.

**Verified 2026-08-08 — the game uses Nanite.** Static-mesh `.ubulk` payloads open with the
`NFM` fixup magic: they are Nanite cluster pages, and the "cooked out" LOD0 slots in
`FStaticMeshRenderData` are the LODs Nanite replaced. What remains readable classically is the
inline Nanite **fallback** mesh (correct shape and materials, reduced density) — that is what the
tag editor's mesh viewer shows for `SM_` assets. Skeletal meshes do not use Nanite and keep full
detail. The `ue-asset` crate reads the whole chain — usmap reflection schemas (dumped from the
running game via UE4SS `DumpUSMAP`, `defs/ue/Meteorite-2607-CU3.usmap`), zen package structure,
unversioned properties, StaticMesh buffers, and MaterialInstance texture parameters — a 1,200
package soak parses 99.25%.

**Verified 2026-08-19 — an object tag reaches its render mesh through its actor Blueprint.**
The tag's `.uasset` imports name `BP_*` actor packages; each Blueprint's mesh component
templates (SCS `SkeletalMeshComponent` / `StaticMeshComponent` exports) carry the `SK_`/`SM_`
package as an object property, plus `RelativeLocation`/`RelativeRotation`/`RelativeScale3D` in
actor space. The warthog resolves to `SK_Warthog_01` + antenna + chaingun this way; the tag
editor's Model and World views draw the chase's results (`render_mesh_refs` in
`apps/tag-editor/src-tauri/src/lib.rs`). Three caveats, all verified against the install:

- **Characters bind placeholders.** A biped's Blueprint binds an anim-dynamics helper
  (`SK_Sacristan_AnimDynamics_PLY`, 2 triangles) and picks the body at runtime. The route to
  the real body is the `Blam*MeshSynchronizationDataAsset` packages: 62 ship, each importing
  exactly one hlmt (`ModelTag`), anchoring the model tag to its asset folder —
  `DA_Elite_MeshSynchronization` → `/Game/characters/Elite/Common` → `Mesh/SK_Elite_Common_Body`
  (236 cm tall) + head. The editor uses these as fallbacks when no Blueprint-bound mesh is
  readable.
- **The unit constant is 1 wu = 304.8 cm** (the classic 10-foot world unit): the elite body's
  236 cm over its 0.79 wu collision shell, and the Blam skeleton overlaying the SK bind pose
  exactly at that scale in the Model view. The engine negates Y between Blam and Unreal space,
  so a mesh drawn among tag data mirrors Y back.
- **Some meshes stay unreadable classically.** Skeletal-Nanite meshes (weapons, most Covenant
  vehicles) hold placeholder triangles; and vehicles like the warthog keep only the suspension
  in their SK — the hull ships as ~40 per-region rig statics (`Mesh/Static/SM_Warthog_*`,
  bone-local frames, matching Blam region names) attached at runtime. Assembling those rigs is
  open work; affected objects fall back to their collision shells.

**Verified 2026-08-19 — a vehicle's hull is rig statics on the SK's skeleton.** The warthog's
`SK_Warthog_01` carries only the suspension geometry (one `InteriorWheelsShocks` material); the
hull, panels, wheels and accessories ship as ~60 statics under the SK's sibling
`Mesh/Static/` folder, in bone-local frames, attached at runtime. No shipped data records the
piece-to-bone binding (the `SkeletalMeshSocket` exports on `SKEL_Warthog_01` are character-IK
and VFX attach points, and the MeshSynchronization data assets hold only `ModelTag`), so the
binding is by name convention, loosely spelled: `SM_Warthog_Tire_Back_Left` ↔ bone
`Wheel_Back_Left`, `SM_Warthog_Base_Axle_*` ↔ `Axle_Base_*`, `SM_Warthog_Hood` ↔ `Hood_Base`.
Token-set matching with a handful of synonyms places every named piece; what the rig does not
name (side panels, windshield, accessories) sits in the chassis frame — attaching those to the
`Body` bone lands them exactly inside the vehicle envelope. The assembled warthog spans
613×325×243 cm, matching its 1.92 wu posed collision shell. Implemented as `rig_static_refs`
in `apps/tag-editor/src-tauri/src/lib.rs`; `probe_rig_match` reproduces the match table.

**Verified 2026-08-19 — the material library's colour is in vector parameters, not textures.**
Vehicle materials (`MI_Warthog_GreenHull`, …) are layered: their `CO`/`COH` texture maps are
channel-packed masks (decoding one as albedo paints the mesh purple), and the visible colour
lives in `VectorParameterValues` — `Color Top/Mid/Bottom` is the paint gradient (the warthog's
olive is `Color Top` = 0.397, 0.397, 0.216), `BaseColor` per layer index is near-black primer,
`Color Tint` is a multiplier. The mesh viewers now carry that flat colour per material slot as
the stand-in when no albedo texture resolves. Also fixed on the way: package and texture
lookups are mount-aware (`/HaloMaterialLibrary/...` plugin content resolves, not just
`/Game/...`), which the parent chain of every vehicle material needs.

**Verified 2026-08-19 — `object_model_ref` regressed on CU4-era layouts.** The `model` tag
reference is nested (`vehicle` → `unit` → `object`), so the flat root-field lookup found
nothing and the World view's collision proxies all drew as boxes; the walk now descends
struct values (`find_model_ref` in `geometry.rs`).

**Verified 2026-08-07 — scenario placements drive the runtime spawn.** An override built with
`mjolnir pack --group scenario --tag a30 --set "weapons[1].object data.position=(8.0, 47.0, 65.5)"`
moved the shipped assault-rifle placement (shipped `(4.671514, 50.428234, 63.94416)`). On a fresh
a30 start the `BP_AssaultRifle_WeaponActor_C` for that placement spawned at engine location
`(8.00, -47.00, 65.51)` world units — magnitudes matching the edit exactly, Y negated as the
engine negates it for every placement (the shipped rifle likewise reads `(4.67, -50.43, …)` live).
So a Blam `scnr` placement edit is authoritative over where the object appears in the Unreal
world; this is the write path the tag editor's World view uses. Caveat: vehicle placements are
consumed at level load and their runtime actor sits at a fix-up location, so a vehicle move is not
observable by reading the live actor — but it rides the same `scnr` field, so the pack/verify path
proves the edit lands even where the runtime read does not.

## Why the DLL Is Named `tag_release`

**Verified:** the host executable contains the reflected enumeration
`EBlamEngineBuildConfiguration` with the members `TagPlay`, `TagProfile`, `TagRelease`, and
`TagTest`. The shipped module `HaloSimulation_tag_release.dll` is therefore the `TagRelease`
configuration of the Blam engine.

In classic Blam terminology a *tag build* consumes loose tag files directly rather than a compiled
cache map. The shipped data layout is consistent with that: individual tag files, no `.map` cache,
no cache-relative offsets in the container.

**Observed, not Verified:** the runtime path that maps an Unreal package back to a tag path has not
yet been traced through the simulation DLL.

## Multiplayer Relevance

**Verified:** `319` multiplayer tags ship, of which `308` are under
`Tags/multiplayer/game_variant_settings`. Also present: `multiplayer_globals-multiplayer_globals`,
`globals-multiplayer_object_type_list`, `game_engine_settings-game_engine_settings_definition`,
`team_names`, `random_player_names`, `global_multiplayer_messages`,
`in_game_multiplayer_messages`, a Megalo subtree, and a Sandbox subtree.

This supersedes the earlier string-derived claim in
[`multiplayer_investigation_notes.md`](multiplayer_investigation_notes.md) with a file-level
inventory. It still does **not** prove the shipping UI or UE5 bridge can launch a competitive
variant. No multiplayer `scenario` tag and no competitive world package exists in this build.

## Reproduction

Tooling is checked in under `tools/iostore`. It is read-only against the installed game and needs an
Oodle decompressor; UE 5.5+ statically links Oodle, so the game ships no `oo2core` DLL. Any
`oo2core_9_win64.dll` from a local Unreal Engine install works.

```powershell
$paks  = "C:\Program Files (x86)\Steam\steamapps\common\Halo Campaign Evolved\Meteorite\Content\Paks"
$oodle = "C:\Program Files\Epic Games\UE_5.6\Engine\Binaries\DotNET\AutomationTool\oo2core_9_win64.dll"

# 1. Container headers only.
python tools\iostore\dump_index.py --paks $paks --summary

# 2. Full path index with extension statistics.
python tools\iostore\dump_index.py --paks $paks --ext-stats --out out\iostore_paths.tsv

# 3. Verify the BLAM header on one payload per tag group.
python tools\iostore\inspect_tags.py --paks $paks --oodle $oodle --per-group 1

# 4. Resolve the Unreal class that owns a tag package.
python tools\iostore\zen_class.py --paks $paks --oodle $oodle `
  --package "../../../Meteorite/Content/Tags/objects/Characters/Elite/elite-biped.uasset"

# 5. List every declared tag wrapper class.
python tools\iostore\zen_class.py --paks $paks --oodle $oodle --grep-scripts "TagDataAsset$"

# 6. Dump tags as <name>.<group> files, with header verification.
python tools\iostore\extract_tags.py --paks $paks --oodle $oodle `
  --group vehicle --out <local-dir> --verify
```

`extract_tags.py` produces copyrighted game content. Keep the output local, keep it out of source
control, and do not redistribute it. The repository `.gitignore` blocks `tagdump/` and `*.ubulk`.

## Next Checks

1. ~~Decode the tag body past `0x4C` and confirm whether the classic `tag_block` / `tag_data` /
   `tag_reference` field layout is intact.~~ **Superseded 2026-07-26.** The body is a
   self-describing `blay` layout section carrying its own string blob and field table. See
   [`tag_body_format.md`](tag_body_format.md).
2. Test the `0x34` group-version hypothesis against a known Reach or Halo 4 tag definition set.
   **Partly resolved:** the value varies per group and is stable within a group, consistent with a
   per-group definition version; it is independent of the `blay` section version, which is `2` in
   all 101 groups.
3. ~~Resolve the `blay` / `4444` / `CCCC` / `wwww` markers.~~ **Superseded 2026-07-26.** `blay` is
   the layout section four-CC at body `0x00`; `4444` / `CCCC` / `wwww` are fixed ASCII fill
   constants at body `0x10`-`0x18`; body `0x28`-`0x58` is a record-count manifest for the twelve
   definition tables. Two words at `0x20`-`0x28` and the per-group value at `0x1C` are still
   unidentified. See [`tag_body_format.md`](tag_body_format.md).
4. Trace the simulation-side loader that resolves an Unreal package to a tag, starting from shell
   primary slot 2 (see [`halosimulation_tag_release.md`](halosimulation_tag_release.md)).
5. Read `game_engine_settings-game_engine_settings_definition` and
   `globals-multiplayer_object_type_list` to enumerate which competitive variants the shipped data
   actually defines.
6. Determine whether the tag-to-Blueprint binding in `BlamBipedTagDataAsset` is a hard reference or
   a soft object path, which decides whether new objects can be added without a cook.
7. ~~Assemble the per-region rig statics onto the SK reference skeleton by bone name.~~
   **Done 2026-08-19** — see "a vehicle's hull is rig statics" above; the warthog assembles
   whole (60/60 pieces placed, 613×325×243 cm, matching its 1.92 wu collision shell).
8. ~~Fix the static-mesh reader on the packages that fail with `mesh data ends early` (the
   `Nanite/SM_LifePod_Body_*` family, the Seraph hull fragments — ~50 crates), which read as
   misaligned property walks rather than missing data.~~
   **Done 2026-08-19** — the reader stopped each LOD at the main index buffer, so any mesh
   with a second real LOD misparsed. The block continues with reversed/depth-only index
   buffers, a ray-tracing blob and per-section triangle samplers (strip-flag gated), and
   closes with `FStaticMeshBuffersSize`; with those consumed, all 11,920 shipped `SM_`
   packages with a StaticMesh export parse (`dump_mesh --soak 1`).

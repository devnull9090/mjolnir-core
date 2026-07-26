# Blam Tag Data in Halo Campaign Evolved

**Status:** Active research
**Last verified:** 2026-07-26
**Game build:** `2026.06.26.1097863.1-Rel-i343-Meteorite-2606-CU2`
**Host SHA-256:** `0670FAA751E2553940B90DF6BE43D3B0FF59EA87F22155CF3C3FE9D439367F1D`

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
in a `weapon` sample). These are recorded as **Observed** and are not yet interpreted.

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

1. Decode the tag body past `0x4C` and confirm whether the classic `tag_block` / `tag_data` /
   `tag_reference` field layout is intact.
2. Test the `0x34` group-version hypothesis against a known Reach or Halo 4 tag definition set.
3. Resolve the `blay` / `4444` / `CCCC` / `wwww` markers.
4. Trace the simulation-side loader that resolves an Unreal package to a tag, starting from shell
   primary slot 2 (see [`halosimulation_tag_release.md`](halosimulation_tag_release.md)).
5. Read `game_engine_settings-game_engine_settings_definition` and
   `globals-multiplayer_object_type_list` to enumerate which competitive variants the shipped data
   actually defines.
6. Determine whether the tag-to-Blueprint binding in `BlamBipedTagDataAsset` is a hard reference or
   a soft object path, which decides whether new objects can be added without a cook.

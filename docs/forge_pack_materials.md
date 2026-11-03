# Forge pack materials

Foundry Wide 0.2 adds two self-contained surface profiles to the existing seven
shipped-material mappings. The original eighteen Wide pieces keep their previous
mesh/material path. New glass and portal pieces use their own cooked masters,
textures and shader library; they do not require the TST map to be installed.

## Inputs and provenance

The canonical profile data is
[`material_profiles.json`](../mods/MJOLNIRForge/Scripts/material_profiles.json).
`glass_cyan` is an original two-sided, lit translucent material: RGB
`[0.12, 0.55, 0.65]`, opacity `0.24`, roughness `0.12`, specular `0.7`.
Its pane collision stays solid regardless of opacity.

`teleporter_green` reproduces the Halo CE shader tag
`levels\test\tutorial\shaders\example_tutorial_teleporter`, using the existing
[`shader_transparent_chicago` graph](../unreal/MJOLNIRMaterials/Scripts/build_ce_materials.py).
The numeric stage parameters were taken from the local TST conversion's
`materials.spec.json`, produced by
[`ce_material_spec.py`](../tools/level/ce_material_spec.py). Four stages sample
two textures: dust in stages 0/1 and mask in stages 2/3. The profile retains
their UV animation functions, periods, phases, scales and color/alpha combiners;
TST's map-specific fog parameters are omitted. Animation uses GPU material time,
not a Lua timer. The visual field has no collision and does not itself teleport
a player; native gameplay markers provide travel.

The material cook requires these **local** CE-conversion DDS files in the
directory supplied to `--ce-textures`. They are the bitmap/mip-chain exports
described in [CE map conversion](ce_map_conversion.md), not Blender previews or
replacement PNGs:

| Filename | Reference SHA-256 |
| --- | --- |
| `scenery_teleporter_shield_bitmaps_teleporter_shield_dust.dds` | `087075684f5f8793ccc68df8f9032f8e493fffa51f32a008225875636009704d` |
| `scenery_teleporter_shield_bitmaps_teleporter_shield_mask.dds` | `84a9e25d316c8707f275b92aa9c1492cdc2a35cb3fafe9bded658fca844bcd31` |

The repository's original geometry and implementation are MIT-licensed. The CE
texture inputs retain their separate game-asset provenance; the repository's
MIT license is not a license grant for those textures. No proprietary texture
files are checked into the authoring source. The built archive **does** include
the converted portal textures. The design concept image is generated artwork;
the contact sheet is a Blender render. Neither is evidence of native rendering.

## Build and distribute

Use the project's Unreal 5.5 editor and fork shader/layout plugins. A fresh
checkout needs the `MeteoriteEditor Win64 Development` and
`Meteorite Win64 Shipping` targets built for
`unreal/MJOLNIRMaterials/Meteorite.uproject` before the commandlets run. The
`mjolnir` CLI must be built too: `tools/ue/cook.ps1` retargets the cooked material
properties into the game's layout and the builder rejects a failed retarget.
Blender exports and native collision/physics are separate prerequisites, as
described in [Forge packs](forge_packs.md).

From the repository root, with local paths substituted:

```powershell
$ceTextures = 'C:/local/CE-conversion/staging/textures'
$basePaks = 'C:/local/base-and-runtime-paks'
# Preparation alone writes a reviewable input specification.
python tools/forge/build_materials.py forge-packs/foundry-wide --ce-textures $ceTextures --chunk 967
# Import, cook, retarget, and fingerprint the material container.
python tools/forge/build_materials.py forge-packs/foundry-wide --ce-textures $ceTextures --chunk 967 --cook
python tools/forge/build_pack.py forge-packs/foundry-wide --paks $basePaks
target/debug/mjolnir.exe forge pack forge-packs/foundry-wide/build/game/all/mjolnir.json `
  --content forge-packs/foundry-wide/build/game/all/content `
  --readme forge-packs/foundry-wide/README.md `
  --changes forge-packs/foundry-wide/build/game/all/changes.json `
  --out forge-packs/foundry-wide/build/foundry-wide-0.2.0.mjolnir --sign
```

Reserve an unused shader chunk in `900..999`. Foundry Wide uses **967**; its
number must stay in `pakchunk967-MJOLNIRFORGEMAT-foundry-wide_P`, because Unreal
opens the matching numbered shader library. A different pack needs its own
reserved number. Asset paths are derived from the validated pack slug:
`/Game/MJOLNIR/Forge/<slug>/Materials/` and `.../Textures/`.

The launcher checks this numeric reservation before installing an enabled
surface pack, applying a profile, launching, or copying live dependencies.
Different slugs do not make the same shader number safe. A conflicting active
pack or unrelated `.pak`/`.utoc`/`.ucas` in Paks is refused without modifying
game files. The same pack's existing container triple and updates are allowed.
Offline profile application can retire old launcher-managed files, but two
conflicting packs in the resulting profile are still refused. This check is
specific to `MJOLNIRFORGEMAT` libraries; ordinary pack load ordering is unchanged.

`build/materials/materials.spec.json` records profile values, source paths and
DDS hashes. `receipt.json` records the specification/profile hashes and the
three cooked sibling-file hashes. `build_pack.py` requires a matching, complete
receipt before including surfaces. A changed profile or specification,
modified/missing file, wrong slug, or mismatched shader chunk is rejected.
Changes to the graph implementation also require a fresh cook; the receipt
does not hash Python source files. Unreal-generated IDs may change across
cooks, so receipts identify a particular output, not a promise of identical
binary hashes on every machine.

Local build output contains `.utoc`, `.ucas` and the empty `.pak` mount sibling.
The `.mjolnir` archive stores the `.utoc/.ucas` pairs; the launcher creates the
mount siblings on installation. Keep the material pair and all visual/tag pairs
together. The Forge runtime must also include `materials.lua` and
`material_profiles.json` beside `main.lua`; the JSON is runtime data, not an
optional authoring file. Pack metadata carries only approved profile IDs and
slots, never executable code or arbitrary material paths.

## Runtime lifecycle and verification

The runtime reads the launcher's actual nested inventory:
`packs[].forge_pack.blocks[]`. It requires catalog schema 1, a matching
`forge_pack.id`/release `slug`, and the exact namespaced block tag. Profiles are
assigned on the existing retained game-thread callback, at the 500 ms surface
scan cadence. Both masters already contain their intended defaults, including
the portal textures and animation, so newly spawned pieces do not wait for a
Lua assignment to acquire their basic appearance.

Assignment identity includes world, actor address/name and the salted native
object binding. Hidden or unbound pooled actors are skipped. A reactivated
actor or changed binding receives a fresh material instance. Polling retains
only string keys and booleans for these objects: no Blueprint class, actor,
component, material instance or texture wrapper crosses a poll. Native engine
classes/CDOs are cached; Blueprint classes use the non-loading soft-reference
resolver instead of a global UObject scan.

Work is bounded to 64 surface classes and 256 active actors per poll. A failed
assignment suppresses that class until inventory or world changes and logs
once; this includes a temporarily unavailable component. Existing/baked master
materials remain in place. This avoids repeated loading on a broken catalog or
missing container, but is not a general background asset-retry mechanism.

Portable checks:

```powershell
python -m unittest discover -s tools/forge -p test_build_materials.py
lua tools/tests/test_forge_materials.lua
lua tools/tests/test_forge_dispatch.lua
cargo test -p ue-asset --lib
```

Foundry Wide contains eight material/texture packages, with all `/Game/`
imports inside its own pack namespace. The glass and portal masters are
two-sided translucent/additive respectively. Each surface mesh declares nine
slots in both its reflected `StaticMaterials` and native arrays, including
slots 7/8. `mesh_rewrite --asset-imports` writes both arrays and uses the old
reflected entries as an exact format guard ([serialization details](ue_mesh_write.md)).
Component overrides alone do not establish translucent renderer relevance.

Cold-load tests verified transparency and solid collision from both sides of
the glass, plus visible green-field animation and native teleport travel in
both directions. Appearance while moving, pooling and restoring surface
placements remains a separate live check. See the
[validation record](forge_pack_validation.md) for the tested artifacts and images.

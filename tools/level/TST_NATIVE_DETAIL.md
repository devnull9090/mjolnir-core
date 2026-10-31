# TST native facility detail: experimental conversion

The full Blender-exported TST JMS exceeds the classic CE BSP render-cluster
limit. A local diagnostic compiled its structure after moving the facility's
render-only metal triangles into a separate native mesh. This path preserves
all selected triangles and the complementary CE geometry. An early private
in-game preview exposed an older duplicate cliff mesh blocking the entrances.
A later preview using matching post-upgrade cooked assets cleared both sides
and was walked from red to blue. The newer entry and panel cleanup still needs
a fresh game build and collision, lighting, shadow and performance checks
before publishing.

1. Export the full TST JMS from the authored Blender source. Keep that file:
   both outputs must come from the same export.
2. Create a new partition directory:

   ```powershell
   python tools/level/partition_tst_facility.py `
     --source <full-tst.JMS> --surfaces levels/test/tst/surfaces.json `
     --out-dir <new-partition-directory>
   ```

   This writes `tst-ce-structure.JMS`, `tst-facility-detail.gltf`, its external
   `.bin`, and `manifest.json`. The predicate moves only `tst_metal_*!`
   triangles in the documented facility bounds. The CE output keeps collision,
   amber/cyan lenses, water, teleporters, and all other triangles. Source JMS
   remains untouched; selected vertices, normals, UV0, winding and roles are
   copied into the glTF. `mesh_rewrite` derives a tangent frame from the UVs.
   The manifest also records each palette-relative owned texture and its
   SHA-256. Textures must remain inside the palette directory and cannot be
   links; missing, escaped, or modified files invalidate the partition.
3. Compile the partition's CE structure, scenario, lightmaps and cache. Save a
   frozen HEK input manifest with hashes for the actual `jms`, pre-lightmap
   `bsp`, and `surfaces` inputs. Preserve the actual input JMS, pre-lightmap BSP,
   structure log, scenario round-trip log, lightmap log/bitmap and cache log.
4. After all stages succeed, create a **new** build receipt:

   ```powershell
   python tools/level/make_tst_facility_receipt.py `
     --partition-dir <new-partition-directory> `
     --detail <new-partition-directory>/tst-facility-detail.gltf `
     --source-jms <full-tst.JMS> --surfaces levels/test/tst/surfaces.json `
     --map <built-tst.map> --input-manifest <frozen-input-manifest.json> `
     --hek-input-jms <actual-HEK-input.JMS> --frozen-bsp <pre-lightmap-BSP> `
     --structure-log <structure.log> --scenario-log <scenario.log> `
     --lightmap-log <lightmaps.log> --lightmap-bitmap <tst.bitmap> `
     --cache-log <cache.log> --out <new-build-receipt.json>
   ```

   The tool compares all input hashes, checks the structure/scenario/lightmap/
   cache success records and attests the final map hash. These checks document
   supplied evidence; they cannot prove that an arbitrary log was produced by
   a particular compiler. Keep the full inputs and logs together.
5. Set `CE_NATIVE_DETAIL`, `CE_NATIVE_SOURCE_JMS`, `CE_NATIVE_BUILD_RECEIPT`,
   and `CE_SURFACE_LIBRARY` to the corresponding absolute paths, then run the
   normal TST conversion with `CE_COOK=1`. The converter refuses a mismatched
   partition, map, external buffer, palette or owned texture bytes both before
   staging and after generating the material spec, and refuses direct `--install`.
   It validates the generated material spec and writes a conversion receipt
   binding that spec hash before mesh rewriting.

The native mesh is appended **after** auto-generated water so the existing TST
water ID `_terrain_3` remains stable. Its ten material sections reference the
same authored PBR masters; unknown roles cannot silently become fallback
materials. The loader spawns it as non-colliding decor over the CE collision.
It requests actor shadow casting because these faces were absent from the CE
lightmap bake. The current full detail subset is about **145,000 triangles**:
runtime lighting, shadow casting, acne and FPS must be checked in game. The
existing structural shadow proxy and environment lights may not match Blender's
area-light study. Do not publish this experimental output without that review.

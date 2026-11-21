# PWR mature pine import and standalone cook

The original assembled source is `out/pwr/visual-v5/outcrops-v4/trees/mature-pine-a.glb`, SHA256 `68bdcb09e0af2dc2030b50b543f45d28a7284264bd7ce188484759b320cdf405`. It contains 111,147 triangles, three UV channels and native data colors. The root is authored at Z=0; the lowest modeled roots extend 1.95227m below ground. Total mesh bounds are 30.91241m high, with the highest needles at 28.96014m above the authored root.

UE5.5's glTF reader only imports `TEXCOORD_0/1`. The first real Interchange trial was rejected because it dropped UV2. `BuildAttributedStaticMesh` is a separate full-attribute MeshDescription builder; the legacy `BuildStaticMesh` remains unchanged. It preserves source normals, all UV channels and original FColor bytes, generates Mikk tangents and disables lightmap UV generation. `FromSRGBColor` counteracts MeshBuilder's final `ToFColor(true)`. Python constructs FColor with named `r/g/b/a` fields because its positional reflection order is BGRA.

The mesh uses Nanite with all source triangles, explicit tangents, area preservation, and 1/64cm position precision. Its full-fidelity classic fallback exists for attribute readback. UE triangle collision cooking and navigation are disabled; the separately authored Blam trunk hull remains authoritative. HISM disables WPO through the existing foliage path.

Only the mesh is shipped in `pakchunk959-MJOLNIRPWRMATUREPINE_P`. Native material imports are exactly:

- `/Game/Env/Bio/Tree/Pine/Tree_Windswept/Materials/MI_Pine_Tree_Mat_LOD0`
- `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Materials/MI_Branch_Mat_LOD0_TwoSided`

Their editor stand-ins and parent materials are under never-cooked `/Game/Env`. A **recursive** priority1000 PrimaryAssetLabel assigns the mesh only to959. Recursive management is necessary even though only one mesh is explicitly selected: UE5.5 `AssetManager.cpp` sends nonrecursive labels to `NoReferenceManagementMap` and processes them after the priority passes. The initial nonrecursive label therefore let LPW's HISM world also claim the mesh in965; the ownership guard correctly rejected that full-map cook. `assign_pwr_pine_chunk.py` repairs the label without rebuilding or changing the frozen pine package. Native material dependencies remain NeverCook.

The config fragment declares `required_external_assets` alongside `extra_containers`; `owned_map_cook.py` rejects a missing standalone dependency or a duplicate in the map-owned/landscape chunks, and seals the external hashes into the owned-cook receipt. It does not strip native mesh bulk after cooking.

Run from the worktree root with exclusive ownership of the shared UE project. Build the plugin after changing its C++ implementation:

```powershell
& 'C:/Program Files/Epic Games/UE_5.5/Engine/Build/BatchFiles/Build.bat' MeteoriteEditor Win64 Development -Project="$PWD/unreal/MJOLNIRMaterials/Meteorite.uproject" -WaitMutex -NoHotReloadFromIDE
powershell -NoProfile -File tools/ue/editor_cmd.ps1 -Script Scripts/build_pwr_mature_pine.py
$env:MJOLNIR = (Resolve-Path out/pwr/toolchain-mesh-attrs-v2/mjolnir.exe).Path
powershell -NoProfile -File tools/ue/cook.ps1 -Classes 'Material,MaterialInstanceConstant,StaticMesh,BodySetup'
```

Require successful `editor-import.receipt.json`, `BUILD SUCCESSFUL`, and no retarget errors. After cooking, copy `global.utoc/ucas` and `pakchunk959-Windows.utoc/ucas` from the staged Paks directory into `out/pwr/visual-v5/outcrops-v4/trees/native/audit-paks`. Export with the attribute-aware CLI, then audit and package:

```powershell
$pine = 'out/pwr/visual-v5/outcrops-v4/trees'
$staged = 'unreal/MJOLNIRMaterials/Saved/StagedBuilds/Windows/Meteorite/Content/Paks'
& $env:MJOLNIR mesh export --paks "$pine/native/audit-paks" --asset SM_PWR_MaturePine_A --out "$pine/native/roundtrip.glb"
uv run --python 3.12 --with-requirements tools/level/requirements-alpine.txt python tools/level/verify_pwr_pine.py --source "$pine/mature-pine-a.glb" --cooked "$pine/native/roundtrip.glb" --out "$pine/native/parity.receipt.json"
uv run --python 3.12 --with-requirements tools/level/requirements-alpine.txt python tools/level/package_pwr_pine.py --audit "$pine/native" --staged "$staged" --map-chunk 43579 --cli "$env:MJOLNIR" --stub-pak 'C:/Program Files (x86)/Steam/steamapps/common/Halo Campaign Evolved/Meteorite/Content/Paks/pakchunk115-Windows.pak'
```

Use the actual map spec chunk for `--map-chunk`; 43579 is the current PWR editor chunk, later distributed under the map-owned name. The package helper re-exports the isolated container and checks that its bytes produce the audited GLB before sealing the final package. It never installs anything.

The November9 cooked proof passed all111,147 triangles including winding and multiplicity: all three classic UV channels and every RGBA byte have zero error; classic positions differ by at most0.00191mm, normals by0.0000199 per component. Nanite positions differ by at most0.0783mm. Native readback contains56 Nanite pages,2440 clusters and888 full-detail clusters. BodySetup is81 bytes with `NoCollision`, `bNeverNeedsCookedCollisionData=true`, and no NavCollision export. The standalone UCAS is5,838,080 bytes. The full staged inventory showed only one pine package and no placeholder materials.

The native exporter currently exposes Nanite positions/normals/UV0, so the complete three-channel/color byte comparison applies to the classic fallback built from the same MeshDescription. This does not claim a decoded Nanite UV1/2/color audit, a live appearance pass, or an FPS result. Final game presentation and performance remain integration checks.

Receipts are under `out/pwr/visual-v5/outcrops-v4/trees/native`: `editor-import.receipt.json`, `parity.receipt.json`, `package.receipt.json`, `body-properties.txt`, `all-inventory.txt`, and `config-fragment.json`. Ten focused tests cover winding, UV2 loss, BGRA swaps, duplicate triangle replacement, missing dependencies and duplicate container ownership.

The subsequent full visual5 world cook passed after the recursive-label repair. Its snapshot is `C:/haloce/ce_conversions/warfare/PWR/expansion/world-v5-visual5/upgrade/PWR/owned-cook-cf1c29eecfa04041962f5c552e212629`. `native/ownership-final/receipt.json` verifies exactly one pine package across every staged chunk, no native stand-in packages, and byte-identical959 UToc/UCAS compared with the frozen package. Both ownership guards remained enabled. Repair reproduction is `powershell -NoProfile -File tools/ue/editor_cmd.ps1 -Script Scripts/assign_pwr_pine_chunk.py`, followed by the standard unified editor/cook run; the map pipeline intentionally rejects a cook-only run for generated map meshes.

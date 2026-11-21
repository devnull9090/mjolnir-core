# PWR Alpine surface candidate, 2026-11-09

The visual3 game images showed regular grass/path tiling, repeated diagonal
rock slabs, and blue reflective court strips. Native texture exports and the
cooked Base audit isolated these as material problems: the original Base RGBA
survived the game cook exactly. The old ground shader blended two globally
repeating UV grids, and rotated normal-map coordinates without rotating the
sampled normals back. The inherited Forerunner MIC used layer roughness
0.12/0.15/0.18 and metallic 0.93.

## Alpine2 surface sampling

`build_ce_materials.py` now uses a three-tap stochastic triangle-grid blend
only for explicit `LandAlpine.w = 2`. Each lattice vertex supplies an offset
and quarter-turn; cubic barycentric weights make triangle edges continuous.
Texture gradients are computed before layer branches, from unjittered world
coordinates, and rotated alongside the sample. Normal XY is rotated back.
Other map modes retain their prior sampling path.

Meadow colour combines native fine turf with a 29 m stochastic sample of the
same scan. Its measured linear mean is [0.37077,0.27321,0.17265];65% mean-chroma
neutralization removes the yellow bias while preserving luminance and local
colour before a muted green tint. The broad tint endpoints remain green.
The apron uses the identical sampler, balancing and macro colour at its seam.
Roads blend native Trampled Forest Path and Sandy Gravel. Rock uses
the existing Jagged Rock texture in stochastic world triplanar projections;
negligible projection weights are skipped. Geology masks, heights, triangle
topology, snow placement, and Base alpha are unchanged. No geometry or native
collision changes are introduced by this material pass.

The extra static texture is enabled by the upgrade configuration entry:

```json
"surface_detail": "levels/warfare/pwr/terrain/final-v5/terrain.geometry.json"
```

`alpine_surface.py` projects texture texel centres onto the canonical road
segments. RG stores tangent direction in UE XY, B stores signed lateral
distance over ±16 m, A fades road detail at graph junctions (8–20 m) and beyond
the carriageway. The shader places subtle wheel wear at ±3/±5 m, without
changing road alpha or surface height. `T_LandSurfaceData` uses the existing
linear, uncompressed, non-sRGB Landscape import path and a shared clamp sampler.
Its maximum signed-distance UNORM quantization error is 6.28 cm. NumPy, Pillow
and SciPy are authoring dependencies; runtime does not compute this field.
They are declared in `tools/level/requirements-alpine.txt`; run the optional
land stage inside that environment (the default machine Python may lack SciPy):

```powershell
uv run --python 3.12 --with-requirements tools/level/requirements-alpine.txt python tools/level/upgrade_ce_map.py <normal stage arguments>
```

Actual 1024² proof:

- `out/pwr/visual-v5/surface-v4/land-proof/surface-detail.receipt.json`
- Complete Base SHA256 before/after:
  `3456566b1e1110b37abce0b7ff399347fa83ce61a302adbca927e49a3d629819`
- Road alpha SHA256:
  `59bd09246f97476cce3cbdc75ec5b6b09473878ba4fbb642926ea0dda258752b`
- Road texture SHA256:
  `2ff43571391d650d024801de2d5069cdfbd1dc9a937a1248c340b9b36f6c0799`

`surface-v4/sampling-comparison.png` is a CPU albedo comparison using the
actual exported game textures, **not a game screenshot or performance proof**.
Tests cover period removal, triangle/cell continuity, inverse normal rotation,
road projection, graph-junction fading, Y reflection and exact Base preservation.

## Paving, floors and generated walls

The chunk960 native MIC clone is superseded and must not be installed.
The original nominally non-VCol Light/Mid materials also inherit VCol variants.
Generated meshes without a colour buffer receive white from UE's null colour
buffer, so their names did not prove absence of frost/COH mask dependencies.

The replacement is `/Game/MJOLNIR/CETrial/M_CE_PWRPaving.M_CE_PWRPaving`, a
small Default Lit material in the shared trial-material chunk. It uses actual
shipped `T_FR_Diagonal_01_N` and `T_FR_Diagonal_01_ORHG` mip0 exports. Normal
data imports as linear BC5 with no green flip; ORHG imports as linear masks.
There are no vertex-colour, mesh-COH, frost, wetness or displacement inputs.
World-space projection fixes scale independently of generated mesh UVs.

`levels/warfare/pwr/paving_materials.py` recreates exports and isolated bindings
under `out/pwr/visual-v5/paving-materials-v3`. `materials.json` is the court
alloy/joint pair; `material-overrides.json` replaces only generated floor and
wall slots and retains the existing cyan strip rule. Native detailed buttresses
are unchanged. Alloy/floor tiles are 4 m, walls 6 m, roughness is bounded
0.65–0.90. Parameter values and source hashes are in `receipt.json`.

The new Desert Cliff geometry can opt into
`/Game/MJOLNIR/CETrial/M_CE_PWRRock.M_CE_PWRRock`, with the exact binding in
`surface-v4/rock-material.json`. This small master samples only the verified
Jagged Rock D/N maps: stochastic world projection, 6.5 m tiles, grey tint and
roughness0.85. Projected normal perturbations are converted into world axes;
the material disables tangent-space normals to avoid a second transform.
It has no finite Landscape UV, vertex-mask, snow or displacement dependency.
Existing verified stock rock materials do not need replacement.

## Validation status

Final full cook succeeded with zero shader errors. Read-only audit of owned
cook `owned-cook-017bffa6738742b6b5f9fc4464e8281f` passed:
`out/pwr/visual-v5/surface-v4/cooked-final/receipt.json`. Both1024² Landscape
textures match every source RGBA byte, with linear/non-sRGB uncompressed data.
Approved Base geology and road-alpha hashes remain identical. Paving normal
is linear BC5, with maximum RG decode error2/1 bytes; its mask texture remains
linear with green mean error0.799byte (maximum52bytes, corresponding to at most
0.0245 roughness change under the shader's0.12 range). Both new materials are
packaged and explicitly use world-space normals. Paving imports its two owned
textures; rock intentionally imports defaults and receives native Jagged D/N
from the runtime material binding.965matches the owned-cook seal and all source
containers were unchanged before/after the audit. Live appearance and updated
frame time remain separate acceptance gates.

Editor material creation of the initial stochastic/paving pass completed with
zero errors. Actual editor texture
readback confirms linear/nonvirtual data, correct compression and no normal
green flip (`surface-v4/editor-readback.json`). The commandlet reports zero
material statistics, so it does **not** establish cooked shader cost. Game
images and repeated frame-time capture remain required. The previous visual3
baseline was about 13.72 ms at 4K/Epic;
the new pass must be measured in that same view before accepting its GPU cost.

The first full cook exposed a real HLSL syntax issue: `sample` is reserved.
The helper and its25 call sites were renamed `tileBlend`. The original failure
was reproduced against Unreal's generated shader, and all38 dumped variants
then compiled with SDK DXC after that sole substitution, covering Landscape,
Ground, Nanite, shadow, Lumen and ray-tracing stages. The receipt is
`surface-v4/compiler-proof/permutations/receipt.json`. A focused DXC test now
compiles the actual nested helper, in addition to CPU sampling tests. This
compiler replay was followed by the successful complete Unreal cook above.

Reproduction and focused checks:

```powershell
python levels/warfare/pwr/paving_materials.py
uv run --with numpy --with pillow --with scipy python -m unittest discover -s tools/level -p test_alpine_surface.py
uv run --with numpy python -m unittest discover -s tools/level -p test_alpine_sampling.py
$env:MJ_CE_ROOT='/Game/MJOLNIR/CETrial'
$env:MJ_CE_CHUNK='983'
powershell -File tools/ue/editor_cmd.ps1 -Script Scripts/build_ce_materials.py
powershell -File tools/ue/editor_cmd.ps1 -Script Scripts/verify_pwr_surfaces.py
```

Editor/cook commands must hold the shared project mutex and be coordinated
with the task's current UE writer. The root integration owns configuration,
cook, installation and live acceptance.

The final read-only cooked verifier is `tools/level/verify_pwr_surface_cook.py`.
After the root supplies the final paths, invoke it with explicit inputs:

```powershell
uv run --python 3.12 --with-requirements tools/level/requirements-alpine.txt python tools/level/verify_pwr_surface_cook.py `
  --cook <final-owned-cook-directory> `
  --land-stem <final-pakchunk965-stem-without-extension> `
  --material-stem <final-pakchunk983-stem-without-extension> `
  --source-land <final-land-bake-directory> `
  --out <new-isolated-audit-directory>
```

It checks965 against the owned-cook receipt, copies only explicit containers
plus global metadata, and seals originals before and after. Both Landscape
data textures must be1024² uncompressed linear RGBA with every source pixel
unchanged. Base additionally retains the recorded geology RGB and road alpha
hashes. Paving BC5/mask textures are checked for size, classic payload and
linear flags; their compression errors are reported rather than falsely called
lossless. Both new material packages must exist and use world-space normals;
paving must import its two owned textures. The receipt does not claim live
appearance or shader performance. Focused tests cover stale container seals,
gamma/compression rejection, import parsing and one-byte road-alpha mutation.

The subsequent **surface-v5 candidate is offline and not yet cooked or visually
accepted**. Visual4's live material readback confirmed the intended Jagged
RockD/N and 650 cm tile on both Landscape and apron, ruling out fallback
textures. However, the actual shipped normal's 1×1 mip is RG=(135,126): its
nonzero decoded slope is (+0.05882,−0.01176). Rotating that constant slope per
stochastic tile can retain a lighting pattern after fine texture detail has
mipped away. The candidate subtracts the texture's mean slope and fades only
subpixel normal detail using explicit UV derivatives. It also uses the same
native rock scan at a stable 23 m scale for visible fractures. This is a
specific, testable explanation; a live normal-only A/B remains necessary.

`tools/level/alpine_ecology.py` derives an optional linear RGBA texture from
the exact runtime terrain and selected tree roots: moisture, canopy litter,
exposed colluvium, and road runoff weathering. It has no random noise, terrain
mutation, or native water simulation. The first candidate uses the existing
4,264 roots; regenerate it after the new clustered stands are accepted.
`--ecology` requires LPW, the exact heightfield and Alpine2 geology. The loader
binds it once, and other maps retain their previous path. The authored Base
file and road alpha remain byte-identical; the real copied-bake receipt is
`out/pwr/visual-v5/surface-v5/proof/land/ecology.receipt.json`.

```powershell
uv run --python 3.12 --with-requirements tools/level/requirements-alpine.txt python tools/level/alpine_ecology.py `
  --master levels/warfare/pwr/terrain/runtime-v5/runtime-master.json `
  --trees out/pwr/visual-v5/outcrops-v3/trees.selected.json `
  --out out/pwr/visual-v5/surface-v5/ecology
```

The isolated config fragment is `surface-v5/config-fragment.json`; root owns
integration. The apron additionally binds `ApronEcology` to
`/Game/MJOLNIR/Landscape/LPW/T_LandEcology.T_LandEcology` and sets
`ApronEcologyInfo=[1,0,0,0]`, blending only across its existing seam collar.
The cooked verifier automatically requires exact Ecology pixels and linear
flags when the final Landscape document enables that texture.

Road wear now varies in width, lateral drift and continuity with world-stable
patches/runoff; shoulder breakup stays within the existing alpha feather.
Signed road distance and junction fading still use the verified static field.
Paving now combines its shipped fine N/ORHG maps with original staggered
chamfered plates, inset joints and triangular service panels. `PavingLayout`
is `[width_cm,length_cm,joint_width_cm,strength]`; the new material fragment is
`out/pwr/visual-v5/paving-materials-v4/receipt.json`. No vertex colours, COH,
raised geometry or collision changes are introduced.

CPU illustrations are in `surface-v5/proof/{ecology,paving}-comparison.png`.
They demonstrate masks/albedo only, not Unreal lighting. Focused tests compile
the actual nested sampler, complete paving HLSL and complete apron HLSL with
DXC; the full Unreal cook remains required. Macro rock adds three albedo taps
per active projection nearby, while distant fine samples and subpixel normals
are pruned. One shared-clamp Ecology lookup is added only to enabled Alpine2.
No performance improvement is claimed; repeat the established 4K frame-time
capture after integration.

For final visual5 integration, use the focused helper rather than overwriting
the provisional ecology by hand. The expected tree path below is pending the
world agent's accepted placement file; substitute the actual final path if it
changes. Run from this worktree's repository root:

```powershell
uv run --python 3.12 --with-requirements tools/level/requirements-alpine.txt python levels/warfare/pwr/finalize_surface_ecology.py `
  --trees out/pwr/visual-v5/outcrops-v4/trees/stands.selected.json `
  --source-land C:/haloce/ce_conversions/warfare/PWR/expansion/world-v5/upgrade/PWR/land `
  --out out/pwr/visual-v5/surface-v5/final
```

`--trees` is required. The default master is the accepted runtime-v5 manifest
with SHA `cfa587ac8c9bc565270c035ee3a281b8611c8197fb7c6c0833990b1b6c4ee45f`.
The helper rejects stale terrain, duplicate IDs, count mismatches, non-tree
records, out-of-bounds roots, and root Z deviations over5cm. It does not move
trees. It also verifies the paving receipt's shader/input hashes and checks
all input seals again after generation. `--source-land` is optional: when
provided, only a copied Base is modified in the output proof directory, and
the receipt verifies that both original Base and road alpha remain unchanged.
The helper launches no applications and edits no upgrade configuration.

Outputs are `final/ecology/ecology.json`, `final/config-fragment.json`, and
`final/receipt.json`. Root should merge only the appropriate fragment fields:
`ecology` into the candidate upgrade config, the `paving_materials` receipt
into runtime assembly, and `apron_material_additions` into the apron material.
The latter two are integration instructions, not new upgrade-schema keys.
A successful helper run is CPU readiness, not cooked/live acceptance. A test
run on the existing4,264 roots is preserved in `surface-v5/helper-proof`; its
maximum root/triangle discrepancy is0.000000768m.

Final acceptance proceeds in this order:

1. Confirm `final/receipt.json` names the accepted final tree file and master,
   then run the normal-regression and full HLSL syntax tests:

   ```powershell
   uv run --python 3.12 --with-requirements tools/level/requirements-alpine.txt python -m unittest discover -s tools/level -p 'test_alpine*.py'
   ```

   The current shader seal is
   `7f29002a07dfb460251b1351508675e4ec73390b2923f89be37a201bec186507`.
   Root's actual complete Unreal cook must succeed without shader errors;
   a successful editor script or these DXC tests alone is insufficient.

2. After root supplies the final owned-cook path and freezes the explicit
   staged965/983 stems, run the read-only audit with strict Ecology enabled:

   ```powershell
   uv run --python 3.12 --with-requirements tools/level/requirements-alpine.txt python tools/level/verify_pwr_surface_cook.py `
     --cook <final-owned-cook-directory> `
     --land-stem <final-pakchunk965-stem-without-extension> `
     --material-stem <final-pakchunk983-stem-without-extension> `
     --source-land <final-land-bake-directory> `
     --paving-source out/pwr/visual-v5/paving-materials-v4 `
     --require-ecology `
     --out out/pwr/visual-v5/surface-v5/cooked-final
   ```

   The audit directory must be new. It must report exact1024² Base,
   SurfaceData and Ecology pixels, `SRGB=false`, compression5, and unchanged
  965/983/global seals. Base alpha must remain
   `59bd09246f97476cce3cbdc75ec5b6b09473878ba4fbb642926ea0dda258752b`.
   Paving retains its owned linear normal/data texture imports and world-space
   normal flag. The compressed native maps have measured bounded decode error;
   they are not claimed lossless.

3. In root's subsequent live readback, require Landscape `Ecology` to resolve
   to `T_LandEcology`, `EcologyInfo.x=1`, apron `ApronEcology` to the same asset
   and `ApronEcologyInfo.x=1`. Read `PavingLayout` as well as `PavingParams`
   against the selected recipe; alloy is `[1000,1500,30,1]`. Keep the verified
   Jagged RockD/N bindings and650cm fine tile. Cooked masks/imports cannot
   establish that the normal correction looks right: inspect the actual
   distant rock lighting at the same camera and compare to visual4, then
   repeat the stable4K/Epic frame-time capture. An isolated normal-only causal
   A/B has not been performed. Neither shader performance nor final visual
   quality is implied by the offline receipts.
# Final visual5 cooked data acceptance

`out/pwr/visual-v5/surface-v5/cooked-final/receipt.json` verifies the final owned snapshot `owned-cook-cf1c29eecfa04041962f5c552e212629` under the `world-v5-visual5` upgrade. Actual cooked `T_LandBase`, `T_LandSurfaceData`, and `T_LandEcology` are1024², linear (`SRGB=false`, compression5), and every RGBA byte matches its source. Approved Base RGB and road alpha hashes are unchanged. Paving normal/data remain explicitly linear native-compressed textures; measured compression error is recorded rather than called lossless. `M_CE_PWRPaving` imports both owned textures; PWR paving/rock world-normal flags are present. Staged965/983 and global source seals were unchanged across readback. This is a cooked-data/reference acceptance, not a live appearance or performance result.

# Visual6 material candidate: actual mountain zoning and restrained alloy panels

The installed visual5 screenshots were rejected for art readiness. Its outer
snow threshold was still calibrated to an earlier scaled rim:88.4% of the
actual outer field was below the520m snow start. Open low meadow decoded to
only1.0% mean soil contribution, and the paving used10×15m panels with30cm
joints, chamfers proportional to panel size, and conspicuous finish changes.
These are measured source/material causes; this candidate does not change
terrain, roads, collision, placements or the saved Fluid Flux states.

`tools/level/alpine_surface_v6.py` generates separate material inputs under
`out/pwr/visual-v6/surface`. The outer mask uses the real8km Gaea height,
Flow/Wear/Deposits and the final sampled join in
`visual-v5/apron-v4/harmonic-field.npz`. Sheltered drainage retains connected
snow, while convex exposed ridges remain rock. The current CPU weights are
61.82% outer rock,9.49% outer snow, and30.12% snow on flanks above400m.
These are blend weights, not claims about final pixel coverage. The existing
150m inner collar still overrides these masks with the exact Landscape
geology/ecology, so the playable boundary has the same material inputs.

The meadow stage preserves the ecology codec and tree provenance. It uses
actual24m/80m terrain curvature, hydrology and canopy litter to produce an8%
mean soil contribution in the representative open-meadow region. Road,
water and foundation masks suppress new soil contribution. No procedural
noise or height modifications are involved. The generator verifies the
unchanged Base alpha against the approved hash above.

Paving keeps the verified native fine normal/ORHG scans, but its original
macro design is now20–36m alloy plates with3–3.5cm joints,25–30cm chamfers,
at most±3% finish variation and sparse service lines. `PavingPattern` means
`[chamfer_cm, finish_variation, seam_darkening, service_fraction]`. Both
runtime material slots must come from the new recipe; the dark joint slot
has `PavingLayout.w=0`, so it cannot reintroduce the patio pattern. Generated
floor and wall overrides use the same explicit parent and compatible scale.

The source shader seal for this candidate is
`31efda921968648d8900d07e4b9c62598f3ea95184b7bacd6dc86827bda061f1`.
The new `ApronField` texture is linear, uncompressed RGBA data. It is opt-in
through `ApronFieldInfo.x=1`; other maps retain the disabled default. The
`apron_geology` upgrade key validates the full source/texture projection and
passes `MJ_PWR_APRON_FIELD` to the existing shared-material editor build.
Owned-cook input seals include the manifest and PNG, so a changed outer mask
invalidates a previous cook receipt.

The current4470-tree ecology is **provisional**. Once the new fringe selection
is accepted, regenerate its raw ecology, then derive the final meadow input.
Run from this worktree; the optional path uses the pinned CPU dependencies
in `requirements-alpine.txt`, including SciPy:

```powershell
uv run --python 3.12 --with-requirements tools/level/requirements-alpine.txt python levels/warfare/pwr/finalize_surface_ecology.py `
  --trees out/pwr/visual-v6/scenery/trees/trees.selected.json `
  --paving out/pwr/visual-v6/surface/paving/receipt.json `
  --source-land C:/haloce/ce_conversions/warfare/PWR/expansion/world-v5-visual5/upgrade/PWR/land `
  --out out/pwr/visual-v6/source-ecology
uv run --python 3.12 --with-requirements tools/level/requirements-alpine.txt python tools/level/alpine_surface_v6.py `
  --ecology out/pwr/visual-v6/source-ecology/ecology/ecology.json `
  --trees out/pwr/visual-v6/scenery/trees/trees.selected.json
uv run --python 3.12 --with-requirements tools/level/requirements-alpine.txt python tools/level/preview_alpine_surface_v6.py
```

`--trees` rejects a raw ecology file from a different selection, even if its
tree count is unchanged. The final receipt must have `ecology_provisional`
false and the accepted tree hash. The generator does not move those roots.
The fragment contains upgrade inputs `ecology` and `apron_geology`, plus
assembly instructions `paving_materials` and `apron_material_additions`.
Root owns merging them into the isolated upgrade/runtime documents. The
three preview PNGs show CPU masks and analytical macro albedo only; they
omit native fine scans, lighting and the actual game renderer.

Focused tests cover source seals, exact world projection/+Y reflection,
linear128 encoding for0.5 masks, protected terrain, the8% soil decoder,
final tree identity, and disabled defaults for other maps. DXC also compiles
the actual Landscape, apron, paving and nested sampling HLSL. A full Unreal
cook and live camera review are still required.

After that cook, extend the established read-only verifier command with
the new source inputs:

```powershell
uv run --python 3.12 --with-requirements tools/level/requirements-alpine.txt python tools/level/verify_pwr_surface_cook.py `
  --cook <final-owned-cook-directory> `
  --land-stem <final-pakchunk965-stem> `
  --material-stem <final-pakchunk983-stem> `
  --source-land <final-land-directory> `
  --paving-source out/pwr/visual-v6/surface/paving `
  --apron-geology out/pwr/visual-v6/surface/apron/geology.json `
  --require-ecology --out out/pwr/visual-v6/surface/cooked-final
```

This requires exact1024² `T_PWR_ApronField` RGBA bytes, `SRGB=false`,
compression5 and an actual `M_CE_AlpineApron` import, alongside the existing
Base/SurfaceData/Ecology checks. It seals source textures and staged
containers before/after. Apron keeps its tangent-space normal contract;
PWR paving/rock retain explicit world-space normals. Neither this readback
nor the CPU previews establish visual quality or frame-time cost. Final
acceptance must inspect mountain zoning/seams, both paving slots and the
meadow from ground and concept-matched aerial cameras, then repeat the
stable4K frame-time test after shader startup.


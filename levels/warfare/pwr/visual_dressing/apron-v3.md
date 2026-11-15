The apron-v3 candidate fixes the boundary pleats seen in the second v5 game
review. The old join extended each boundary sample and slope independently
along a radial ray for about 500 m. This repeated every small gully as a long
ridge. A two-dimensional clamped thin-plate displacement now joins the exact
runtime boundary to one continuous Gaea field. Boundary-crossing stencils
constrain both the height and slope; the actual discretized slope differences
are recorded, rather than claiming exact C1 continuity.

The source is the unchanged `terrain/gaea-v5c/source.json`. A strictly monotonic
mapping, `source_axis = 1000*tanh(world_axis/1500)/tanh(4000/1500)`, puts its
eroded ridge belt closer to the battlefield: source 706–820 m appears at world
1.3–1.7 km. It does not reflect the field, add synthetic mountains, or change
the accepted playable master. Height is `70 + (source_height - 70)*2.45` outside
the 500 m join. The square extends to ±4 km, exclusively outside the playable
±1 km boundary. The final mesh is render-only and adds no native collision.

The candidate has 117,936 vertices and 231,336 triangles. All 4,032 source seam
vertices are exact; maximum planar triangle edge length is 88.117 m. Isolated
native package readback measured 0.716 mm maximum position difference and
0.279 mm at the seam, below the explicit 1 mm gate. Its manifold audit found
only the expected inner and outer open boundaries, and no triangle entering
the playable square. These are geometry results, not live visual acceptance.

Reproduce the field offline, then build the actual mesh and preview through
the running Blender MCP connection:

```powershell
uv run levels/warfare/pwr/visual_dressing/build_apron_v3.py solve
$apronPreview = (Resolve-Path levels/warfare/pwr/visual_dressing/preview_apron_v3.py).Path.Replace('\', '/')
@{ code = "import runpy`nrunpy.run_path('$apronPreview', run_name='__main__')"; user_prompt = 'Build and preview the isolated apron-v3 geometry; preserve the playable scene.' } | ConvertTo-Json | Set-Content -Encoding utf8 out/pwr/visual-v5/apron-v3/mcp-preview.args.json
uvx --from mcp-for-blender==2.2.7 python tools/blender/mcp_client.py execute_blender_code --args-file out/pwr/visual-v5/apron-v3/mcp-preview.args.json --out out/pwr/visual-v5/apron-v3/mcp-preview.receipt.json --timeout 300
```

The args file executes `preview_apron_v3.py` through `runpy`. That script saves
dirty scene state to an isolated copy, appends the preserved preview scene,
constructs the new apron and saves `apron-v3-preview.blend`. It renders the
normal valley view, the requested 58°/65° target view, and identical-camera
uniform-clay before/after geometry comparisons. Their materials and lighting
are Blender approximations. The original v2 preview, package and rollback
artifacts are retained; preliminary v3 comparisons are in `harmonic-draft`
and `linear-draft` under the isolated output directory.

Package using the existing world-space material binding:

```powershell
python levels/warfare/pwr/visual_dressing/package_apron.py --master levels/warfare/pwr/terrain/runtime-v5/runtime-master.json --out out/pwr/visual-v5/apron-v3 --apron-dir out/pwr/visual-v5/apron-v3 --material-spec out/pwr/visual-v5/material-review/alpine-apron.material.json
```

For independent native readback, copy only the game's `global.utoc` and
`global.ucas` plus the candidate `.utoc/.ucas` to an isolated `audit-paks`
directory. Then run:

```powershell
target/release/mjolnir.exe mesh export --paks out/pwr/visual-v5/apron-v3/audit-paks --asset SM_PWR_DistantApron --out out/pwr/visual-v5/apron-v3/roundtrip.glb
python levels/warfare/pwr/visual_dressing/verify_apron_v2.py --out out/pwr/visual-v5/apron-v3 --maximum-error-m 0.001
```

Parent integration inputs are `runtime_decor.json` and
`pakchunk963-MJOLNIRPWRVISTA_P.{utoc,ucas,pak}` in the isolated apron-v3 folder.
`integration.receipt.json` pins the geometry, native package, preview and
readback receipts. No generator installs these files or edits configuration.
The combined geology shader, forests, apron material transition and actual
game camera still need live visual review. Broad distant shoulders remain in
the far field; the preview is not a fidelity approval for the whole level.

The follow-on material candidate is `runtime_decor.geology.json`. Reproduce it
with `python levels/warfare/pwr/visual_dressing/bind_apron_geology.py`. This
first verifies the actual Base RGB PNG against the current geology source,
then binds that same linear, clamped LPW texture using the exact landscape
world rectangle. Rock, retained snow, soil and grass weights match the edge
and fade to the outer material over 150 m. It does not gamma-decode the masks.
`geology-seam.receipt.json` pins the input texture, source and new binding.

The candidate also moves the outer snow transition to 0–750 m outside the
tile, with a 520–760 m outer snowline and opt-in world-space retention patches.
This addresses the ridge belt's closer position; the previous 1–2.5 km
transition whitened those nearer mountains. Exact edge geology overrides the
outer retention. The new shared apron shader must be cooked before this
binding is used. Geometry and collision packages are unchanged. These checks
prove mask/UV/encoding consistency; final color, lighting, fine soil response
and actual rendered seam continuity still require the live camera review.

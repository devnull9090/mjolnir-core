The V8 foothill candidate adds render-only scenery outside the full1,050m
gameplay exclusion square. It preserves the original27 cliff placements,
playable terrain, apron mesh,4702 gameplay trees,1072 gameplay rocks, native
collision, roads, bases, and Flux inputs. It is a cook candidate, not final art
or an installed performance result.

The final inputs are under `out/pwr/visual-v8/foothills/clustered-final/`:

- `render-only-hism.json`:96 cliff instances in33 spatial groups (1.25km),
  31,358,964 instanced source triangles. The9 new major shoulders have
  overlapping side faces and low toe shelves, with drainage gaps between them.
- `render-only-pines.json`:500 mature native pines and100 native saplings in35
  groups (500m). Original native material slots are retained; no material
  overrides, collision, navigation or WPO. Draw culling is2.5–3.5km.
- `contacts.receipt.json`: final post-PCG roots clear rock AABBs by at least
  5.54m. Original27 poses remain exact; no native collision is added.
- `receipt.json`: actual UE5.5 PCG selection/repeat, exclusion fixtures,
  packaged-apron grounding and source provenance.

`preview-clustered/` contains the saved Blender scene and matched before/after
valley, target, north and east cameras. Materials are approximate; the mature
pine retains native UV/albedo. The old Uluwatu inspection GLB predates the
native-winding exporter fix: only its Blender triangle order is repaired,
explicitly recorded in the preview receipt. The shipped mesh and native
placement are unchanged. The preceding `preview/`, `preview-corrected/`,
`full-grounded/`, `selected/`, and `clustered-selected/` are intermediate
comparisons, not integration inputs.

Reproduction uses the retained immutable initial CPU plans. Output generators
reject overwriting an existing proof; use a new revision directory for another
iteration. The final sequence is:

```powershell
uv run --python 3.12 --with-requirements tools/level/requirements-alpine.txt python levels/warfare/pwr/visual_dressing/prepare_foothill_clusters_v8.py
powershell -NoProfile -File tools/ue/run_pwr_pcg.ps1 -Request out/pwr/visual-v8/foothills/clustered/request.json
uv run --python 3.12 --with-requirements tools/level/requirements-alpine.txt python levels/warfare/pwr/visual_dressing/finish_foothills_v8.py --input out/pwr/visual-v8/foothills/clustered --out out/pwr/visual-v8/foothills/clustered-selected
uv run --python 3.12 --with-requirements tools/level/requirements-alpine.txt python levels/warfare/pwr/visual_dressing/repair_foothill_contacts_v8.py
powershell -NoProfile -File tools/ue/run_pwr_pcg.ps1 -Request out/pwr/visual-v8/foothills/clustered-contact/request.json
uv run --python 3.12 --with-requirements tools/level/requirements-alpine.txt python levels/warfare/pwr/visual_dressing/finish_foothills_v8.py --input out/pwr/visual-v8/foothills/clustered-contact --out out/pwr/visual-v8/foothills/clustered-final
```

The final PCG pass retains all69 cliff anchors,600 tree anchors, and rejects
both excluded fixtures per population; deterministic repeats match. Final
rotation/scale is regrounded against the actual packaged apron triangles,
including a bounding-box fallback for long thin adaptive triangles. Two
exterior roots were relocated after final rock yaw/scale contact testing and
then selected by PCG again. Gameplay roots were never moved.

Integration is opt-in. `foliage_bake.py --render-only-hism ... --render-only-pines
...` appends both sources separately from `swap.decor`. `render_only_pines.py`
validates the exact mesh palette, root datum, source hashes, native slot names,
full bounds, cull and budget. Its `cook_inputs(path, work)` binds the final
sidecar transforms and saved editor receipt. The legacy cliff grouping stays
500m unless a new manifest explicitly requests1.25km.

The stock/retargeted/final-world verifier accepts `--pines-manifest` and reports
the600 exterior instances separately from the original4702 gameplay pines.
The final world must preserve83 forced LOD0 courtyard components among256,
native two-slot materials without overrides, and unique frozen959 ownership.
The optional native Canyon MIC's separate966 ownership proof is root-owned.
Final cooked/readback, installed visuals, streaming, and4K/Epic frame timing
remain required before claiming the candidate ready.

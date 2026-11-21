# Forerunner bases — Blender authoring package

Three modelled bases for PWR: a red master, an exact X-reflected blue counterpart with team material overrides, and a green citadel with an extended rear arcade. The architecture has an open vehicle hall, connected cover galleries, roof-access ramps, recessed armor fields, illuminated interior ribs, layered fins and a removable rooftop socket. Both galleries now end in authored recessed bulkheads; native pillar trims and corridor panels remain.

Open [forerunner_bases.blend](C:/Users/will/.codex/worktrees/pelican-warfare/haloce/levels/warfare/pwr/bases_v1/forerunner_bases.blend). This package is an offline art study; game integration and vehicle physics testing are deferred at the user's request.

## Scale and layout

Coordinates are metres, Z up, with the front facing −Y. The final architecture uses `ART_SCALE = 0.65`; the reference Warthog retains its native size. Floor datum is Z = 0.2 m.

| Feature | Current dimension |
|---|---:|
| Main hall width at floor | 16.9 m nominal |
| Rear vehicle opening width | 5.85 m nominal |
| Minimum sampled covered headroom | 6.880 m above floor |
| Covered hall length | 32.5 m nominal |
| Roof deck datum | Z = 10.5675 m |
| Central roof reservation | 19.5 × 19.5 m |
| Removable octagonal socket | 13 m nominal diameter |
| Conservative vehicle proxy | 7 × 3.5 × 4.5 m, unscaled |

The complete red/blue assembly, including ramp armor, measures approximately 76.44 × 52.63 m in plan. The socket's nominal diameter is not a verified cannon fit. The exact Danger Canyon “light cannon”/emitter identity remains unconfirmed; no cannon has been built or installed. Identify the intended asset or reference before fitting it, and retain the adjustable mount.

Collections `01_RED`, `02_BLUE` and `03_GREEN` have presentation centers `(0,0,0)`, `(135,0,0)` and `(0,150,0)`. Blue uses `translate(135,0,0) × reflectX` and the same mesh datablocks as red; only `TEAM` material slots change. Clone provenance is stored in `mirror_source_object`. Green shares the master and adds its own rear piers, arcade, gallery and parapet. `90_PRESENTATION` contains the review environment. Intended world placement remains collection metadata; these presentation copies are not installed into the map.

## Source and iteration

The source directory is `C:/Users/will/.codex/worktrees/pelican-warfare/haloce/levels/warfare/pwr/bases_v1`.

- [build_bases.py](C:/Users/will/.codex/worktrees/pelican-warfare/haloce/levels/warfare/pwr/bases_v1/build_bases.py): master shell, open routes, ramps, roof mount, height profile, scale, materials and clones.
- [sculpted_facade.py](C:/Users/will/.codex/worktrees/pelican-warfare/haloce/levels/warfare/pwr/bases_v1/sculpted_facade.py), [sculpted_fins.py](C:/Users/will/.codex/worktrees/pelican-warfare/haloce/levels/warfare/pwr/bases_v1/sculpted_fins.py), [detail_kit.py](C:/Users/will/.codex/worktrees/pelican-warfare/haloce/levels/warfare/pwr/bases_v1/detail_kit.py): authored armor, channels and interior details.
- [citadel_details.py](C:/Users/will/.codex/worktrees/pelican-warfare/haloce/levels/warfare/pwr/bases_v1/citadel_details.py): green-only rear architecture.
- [finishing_materials.py](C:/Users/will/.codex/worktrees/pelican-warfare/haloce/levels/warfare/pwr/bases_v1/finishing_materials.py): final native normal/roughness maps, authored material nodes and metric planar UVs. The generated atlas belongs to early iterations; final material provenance is recorded in [native-finish-provenance.json](C:/Users/will/.codex/worktrees/pelican-warfare/haloce/levels/warfare/pwr/bases_v1/textures/native-finish-provenance.json).
- [stock_interior.py](C:/Users/will/.codex/worktrees/pelican-warfare/haloce/levels/warfare/pwr/bases_v1/stock_interior.py), [staging.py](C:/Users/will/.codex/worktrees/pelican-warfare/haloce/levels/warfare/pwr/bases_v1/staging.py): cached native detail assets and presentation scene; provenance is in [ASSET_SOURCES.md](C:/Users/will/.codex/worktrees/pelican-warfare/haloce/levels/warfare/pwr/bases_v1/ASSET_SOURCES.md).
- [validate_bases.py](C:/Users/will/.codex/worktrees/pelican-warfare/haloce/levels/warfare/pwr/bases_v1/validate_bases.py), [render_views.py](C:/Users/will/.codex/worktrees/pelican-warfare/haloce/levels/warfare/pwr/bases_v1/render_views.py): evaluated geometry checks and repeatable review cameras.

Blender **5.3.0** and **mcp-for-blender 2.2.7** were updated/verified this session. The add-on handshake verified protocol 15 on localhost:9876; [toolchain receipts](C:/Users/will/.codex/worktrees/pelican-warfare/haloce/out/pwr/base-art/toolchain/installation-receipt.json) record the installed binary and version evidence.

Edit the Python source for reproducible changes. Save any manual Blender edits separately before rebuilding: `build_bases.py` clears the current scene and regenerates this `.blend`. With the Blender MCP server running in the intended authoring session, the existing build request can be executed through the project client:

```powershell
$taskRoot = 'C:/Users/will/.codex/worktrees/pelican-warfare/haloce'
uvx --from mcp-for-blender==2.2.7 python "$taskRoot/tools/blender/mcp_client.py" execute_blender_code --args-file "$taskRoot/out/pwr/base-art/build-request.json" --out "$taskRoot/out/pwr/base-art/rebuild-receipt.json" --timeout 900
```

For validation, send `execute_blender_code` a JSON payload with `code` running `runpy.run_path` on the absolute `validate_bases.py` path and `run_name='__main__'`. Render selected views by importing/reloading `render_views` in that session and calling `render_views.render_views(version='v16', views=('red','blue','blue-oblique','green','green-rear','interior','gallery','passage-left','passage-right','roof'))`. Rendering restores collection transforms and visibility afterward.

## Evidence and export limits

The v16 [validation receipt](C:/Users/will/.codex/worktrees/pelican-warfare/haloce/out/pwr/base-art/validation-receipt-v16.json) and [geometry report](C:/Users/will/.codex/worktrees/pelican-warfare/haloce/out/pwr/base-art/geometry-validation.json) record no failed checks. Red/blue paired **773 objects** with **19 team material slots**; maximum measured coordinate difference was **0.0000143071 m**. Green had **815 mesh objects**. These are evaluated Blender meshes; presentation terrain and vehicles are excluded.

| Check | Evaluated scope and result |
|---|---|
| Main vehicle hall | Red and green air envelopes passed; blue matched red geometry |
| Lateral cross-gallery route | Red and green air envelopes passed |
| Two side-front entrances | Both red air envelopes passed; blue matched red geometry |
| Main-route floor and cover | Red and green passed; 235 floor samples each, none unsupported; minimum headroom 6.8802498 m |
| Central rooftop reservation | Red and green 19.5 m square sky volumes passed |
| Roof-access ramps | Both red endpoint, landing and overhead checks passed |
| Linked red/blue mirror | All 773 pairs passed geometry and material checks |
| Floating-detail heuristic | No warning objects |

Main-route floor samples range from Z = 0.1350 to 0.2000 m within the 0.08 m contact allowance. The two roof landings measure Z = 10.6260 m, 0.0585 m above the roof datum, within the validator's 0.12 m connection tolerance. Roof ramps average a 33.4% grade; vehicle handling remains untested.

Each side-front entrance was checked with the full unscaled vehicle proxy along X = ±21.45 m, Y = −23.4 to −6.5 m. Both air-clearance volumes passed without intersections; side-route floor support and driving dynamics are not asserted by those checks.

The evaluated art has **925,167 vertices / 1,327,262 triangles per red/blue base** and **972,415 vertices / 1,419,798 triangles for green**. This is not a runtime budget or FPS result. Before export, choose module boundaries and instance reuse, bake/verify UVs and material maps, apply mirrored transforms with correct winding/tangents, and create collision from separate wall, floor and roof solids around the open tunnels. Preserve native mesh/material attributes where native assets are reused; do not convex-fill the whole building. Nanite suitability, LODs, collision cooking and native vehicle behavior still require their own integration work.

The primary [concept](C:/Users/will/.codex/worktrees/pelican-warfare/haloce/.dream-loop/bases-v1/concept-team-base.png) was generated from the existing project screenshot. The [refined concept](C:/Users/will/.codex/worktrees/pelican-warfare/haloce/.dream-loop/bases-v1/concept-team-refined.png) used an actual Blender render to guide further modelling. These are imagegen targets. The [primary prompt](C:/Users/will/.codex/worktrees/pelican-warfare/haloce/.dream-loop/bases-v1/prompt-team-base.txt), [refinement prompt](C:/Users/will/.codex/worktrees/pelican-warfare/haloce/.dream-loop/bases-v1/prompt-team-refined.txt) and [early atlas prompt](C:/Users/will/.codex/worktrees/pelican-warfare/haloce/.dream-loop/bases-v1/prompt-alloy-atlas.txt) are retained. Images under `C:/Users/will/.codex/worktrees/pelican-warfare/haloce/out/pwr/base-art/renders` are actual Blender renders of the authored scene, not generated replacements presented as model output.

All ten v16 actual-model views are complete: [red hero](C:/Users/will/.codex/worktrees/pelican-warfare/haloce/out/pwr/base-art/renders/red-hero-v16.png), [blue front](C:/Users/will/.codex/worktrees/pelican-warfare/haloce/out/pwr/base-art/renders/blue-v16.png), [blue oblique](C:/Users/will/.codex/worktrees/pelican-warfare/haloce/out/pwr/base-art/renders/blue-oblique-v16.png), [green front](C:/Users/will/.codex/worktrees/pelican-warfare/haloce/out/pwr/base-art/renders/green-v16.png), [green rear](C:/Users/will/.codex/worktrees/pelican-warfare/haloce/out/pwr/base-art/renders/green-rear-v16.png), [roof](C:/Users/will/.codex/worktrees/pelican-warfare/haloce/out/pwr/base-art/renders/roof-v16.png), [main interior](C:/Users/will/.codex/worktrees/pelican-warfare/haloce/out/pwr/base-art/renders/interior-v16.png), [gallery](C:/Users/will/.codex/worktrees/pelican-warfare/haloce/out/pwr/base-art/renders/gallery-v16.png), [left passage](C:/Users/will/.codex/worktrees/pelican-warfare/haloce/out/pwr/base-art/renders/passage-left-v16.png) and [right passage](C:/Users/will/.codex/worktrees/pelican-warfare/haloce/out/pwr/base-art/renders/passage-right-v16.png).

[R9](C:/Users/will/.codex/worktrees/pelican-warfare/haloce/.dream-loop/bases-v1/judge-r9.txt) reviewed all ten v16 views at **8.1/10, Tier 3**, meeting the dream-loop numeric exit threshold of 8. The review accepts the continuous passage floors and paired recessed bulkheads. Tier 4 remains incomplete: finer crown overlaps and a clearer sequence of short-passage fixtures are still refinement opportunities. This is an architecture-only visual result; runtime and FPS remain excluded at the user's request.

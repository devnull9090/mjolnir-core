# Blender base art loop — 2026-11-10

Scope: user explicitly paused in-game checks and requested all three bases be developed in Blender first. No game or Unreal checks, exports, installations or gameplay changes are part of this loop. FPS is deferred under that instruction.

Reference research used the CE architecture artist analysis, Danger Canyon map reference, beam-emitter reference and a Halo Infinite environment artist portfolio. Links and asset provenance are in `levels/warfare/pwr/bases_v1/ASSET_SOURCES.md`.

Built-in image generation produced the initial concept from the existing project's base screenshot, a refinement using the actual Blender model render plus that concept, and an alloy/trim texture atlas. Inputs and prompts are kept alongside this log. The refined concept remains the judging target; renders are actual Blender Cycles outputs.

Toolchain verified and updated side-by-side: Blender 5.3.0 stable, mcp-for-blender 2.2.7, matching addon protocol 15. Existing Blender 5.2.3, preferences and old assets were preserved. All scene builds and renders run through the Blender MCP bridge on localhost:9876. Installation and hash receipts are in `out/pwr/base-art/toolchain/`.

| Review | Actual render | Score | Result and response |
|---|---|---|---|
| R1 | v4 | 2.7 | Shape failed: rebuilt the complete facade with deep angular shoulders, linked side portals and broader inset fields. |
| R2 | v6 | 2.9 | Shape still blocked by thin ramps and obscured tunnel. Replaced ramp edges with substantial interlocking retaining armor, lowered camera and corrected fin layering. |
| R3 | v8 | 4.0 | Shape passed. Added warm directional light, darker tunnel paving, local lighting, real recessed channels, a deeper soffit and a narrow framed rear exit. |
| R4 | v9 | 5.3 | Shape and broad lighting passed. Material response remained too uniform. Authentic local 2K Forerunner normal/roughness maps selected for a new surface finish; ceiling cassettes, facade crown overlaps, articulated ramp plates and fixture pools added. |

The Boolean facade channels are evaluated geometry. A compound overlapping cutter initially erased a field; this was corrected by applying each closed cutter segment separately and asserting nonempty fields. The corrected image is the saved v9 render.

Evaluated BVH checks pass through v9: full 7 × 3.5 × 4.5 m vehicle envelope in the main passage and cross gallery, supported floor, roof reservation, ramp endpoints and continuous landing, exact shared-mesh red/blue reflection. These are geometry checks, not physics or driving tests. Final revision checks and visual review remain recorded separately.

| Later review | Actual render | Score | Result and response |
|---|---|---|---|
| R5 | v10 | 6.4 | Armor finish improved; ramp seams, fitted apron slabs and darker channel interiors required. Added actual traction plates, deterministic slab finish variation and shadowed channel bottoms. |
| R6 | v11, multiple views | 6.8 | Main tunnel structure established from ground level. Blue revealed coplanar roof tears; close floor and native gallery shading still blocked. Rebuilt flush full-thickness paving, corrected native normals and separated roof surfaces. |
| R7 | v12, including blue oblique | 6.9 | Floor, gallery shading and clipped rear portal passed. Oblique view found remaining facade-cap/roof intersections. Rebuilt those junctions and supported corner plates; replaced fragmented roof-hole construction with a true Boolean aperture. |
| R8 | v14, ten views | 7.8, Tier 3 passed | Roof integrity, native finish and main tunnel passed. Local side-passage threshold, fixture rhythm and a residual native shading patch remained. V15 addresses those localized issues. |

The native wall and pillar imports had predominantly inverted custom corner normals (approximately 98–99% negative face alignment). Their authored smoothing is retained while correcting orientation; remaining minority hemisphere outliers are corrected separately. Per-mesh before/after diagnostics are stored in the Blender collection manifest. Mesh positions and topology are unchanged by the repair.

The final gallery approach is paved to the same nominal floor elevation as the room. New low wall fixtures are attached to the sloped wall, with separated local pools rather than increased global exposure. The main-tunnel and side-front protected air volumes, roof reservation and exact red/blue shared-data reflection continue to be checked after geometry revisions.

**Final R9 result: 8.1/10, Tier 3 passed**, reviewing ten actual v16 Blender views. This reaches the skill's visual exit threshold. Crown overlap articulation and the short-passage fixture rhythm remain optional Tier 4 polish, not complete pixel-level concept matching. Game/FPS validation remains deferred under the user's explicit instruction.

V15 corrected the side threshold elevations and added low wall fixtures. A residual view-dependent artifact in one native rear wall sheet persisted after normal correction. V16 replaces the two large rear gallery sheets with authored recessed, chamfered bulkheads, while retaining native flanking pillars and smaller corridor modules. The replacement is visible in both passage views and is recorded in source provenance.

Final evaluated geometry passes: 773 red/blue mesh pairs sharing the same mesh data, 815 green mesh objects, 1,327,262 evaluated triangles per red/blue base. The 7 × 3.5 × 4.5 m conservative vehicle envelope remains clear on the main, cross-gallery and both side-front routes. Minimum main covered headroom remains 6.880 m. No game export, runtime changes or in-game checks were performed during this task.

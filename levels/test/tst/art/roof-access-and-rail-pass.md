# Roof access and railing joints — 21 October 2026

Scope: address the user's two Blender screenshots. No game launch, bake, export,
installation or upload. Existing gameplay layout and opposing base rotation stay
intact.

## Built design

The central railing support gets its own reserved assembly bay. Neighboring cap
plates, inset panels and borders terminate before that bay, leaving a deliberate
joint. One chamfered saddle replaces the previous overlapping crown strips.
The solid support still joins the collision shell underneath.

Both roof ramps now reach 6.40 m at local y=4 and remain level to y=8: a four-metre
landing. A broad opening in the roof rim and a continuous platform bridge the old
roof-coffer gasket, providing a flush left turn onto the inset roof deck. The
incline is approximately 21 degrees. A short outer curb and landing end curb
frame the exposed edge; the route onto the roof stays open. An inset support
panel breaks up the solid landing side.

The imagegen study informed the landing, short curbs and faceted support. Its
slope direction differs from the existing approach, which the Blender build
preserves. It is design exploration, not evidence of implemented geometry.

## Generated concept and provenance

[Roof access concept](reference/roof_access_landing_concept.png) was created with
the built-in imagegen tool from the user's second annotated screenshot. It is
not a Blender render and is not used as a map texture.

Exact prompt:

> Use case: precise-object-edit. Edit target: attached Blender view of our existing Halo-inspired Forerunner base. Create a practical architectural design visualization of the SAME base and camera. Preserve roof, building mass, team blue trim, cliffs, balcony and surrounding layout. Remove red annotation text/arrows and all Blender wire overlays. Redesign only the ramp along the RIGHT side of the pictured base: a broad straight inclined metal walkway rises from ground at the far end to a substantial HORIZONTAL landing at the near upper end. The last approximately 4 metres are flat, exactly flush with the roof's walking surface. The landing turns left into the roof through a broad 3 metre gap in its rim; no jump, curb or vertical step at the join. Keep an obvious continuous walkable slope to flat landing to roof. Integrate a faceted Forerunner support underneath the landing, restrained dark inset side panel and pale chamfered edges, short low outer safety kerbs that stop at the roof connection. Satin titanium and charcoal matches existing architecture. No staircases, extra buildings, floating platforms, enormous rails, or elaborate clutter. Bright coastal daylight, realistic achievable Blender render. The landing must look built into the base, not a wedge that terminates in midair. Landscape composition.

## Repeatable checks

`inspect_layout.py` checks floor height and horizontal normal at 36 additional
landing samples on the two bases, alongside the existing ramp and player-envelope
checks. `inspect_architecture.py` checks finished railing module bounds against
all three central support bays, in addition to tower symmetry and tree clearance.
These are Blender checks; runtime collision and export validation remain pending.

## Actual Blender result (R16)

- [Railing support close-up](review/forerunner-rail-joint.png)
- [Blue base landing and roof connection](review/forerunner-blue-roof-access.png)
- [Blue ramp and level landing](review/forerunner-blue-ramp-approach.png)
- [Matching red base](review/forerunner-red-roof-access.png)
- [Validation report](review/forerunner-validation.json)

All 206 sampled route points pass, including 36 horizontal landing samples at
6.400 m. Native rock clearance reports no issues. All 192 checked railing modules
stay outside the support bays. The source contains 403 closed detail meshes;
light-atlas and engraved-face checks pass. No runtime FPS or game testing is
claimed. The local complete preview is
`.dream-loop/blender-preview/forerunner-r16/preview.blend` from the repository root.

# TST Proving Ground: community reference map

Approved direction, October 20, 2026: expand the original test map into a
150 × 90 m enclosed arena with readable Forerunner architecture, lit interiors,
three routes, a pond, cliff, controlled tree examples, rock cover, vehicles,
and useful teleporters. Keep the source understandable enough to teach.

The [approved concept](art/reference/approved_coastal_concept.png) is a generated
target, not a game screenshot. `.dream-loop/baseline.png` is the live starting
point. Working captures are ignored; the source includes final visual studies
with [provenance](art/README.md). Community documentation should distinguish
generated references, Blender design renders and actual-game captures.

The subsequent user direction replaces the open coast with a fully enclosed
basin: continuous cliffs on the south, east and west, meeting a full-length
Forerunner retaining wall on the north. The generated
[wall study](art/reference/enclosed_basin_wall_concept.png) explores this change
over the actual Blender overview. It is a design target, not a runtime capture.

The current enclosed source footprint is 150 × 84 m. Both bases sit at
x=-54/+54 m, four metres inward from the previous layout, making room for
thicker native cliff formations behind their roof routes. The southern apron
extends to y=-44 m. Native geometry clearance checks cover starts, objectives,
teleporters, balcony exits and both roof ramps; actual movement still needs
an in-game test.

The wall spans the 150 m northern boundary and rises 24 m, with a taller central
spine. An inset balcony has a 7.2 m floor, sheltered arrivals at x=-48/+48 m,
segmented parapets and offset sightline screens. New one-way channels 2 and 3
connect ground pads at (-44,22) and (44,22) to these alcoves. Two exit terraces
descend through 4.8 m and 2.4 m levels. Their fall damage, teleporter behavior,
visibility from flags, and competitive value require in-game playtests.

The cliff foundation closes the arena even with PCG disabled. Rock surfaces
permit ground/cliff dressing subject to existing slope and clearance rules;
the wall, balcony, screens and terraces use NONE. The northern tree and one
rock were moved clear of the new terraces. No power weapon or objective has
been added to the balcony before its sightlines are tested.

Primary target: 4v4 CTF and Slayer, with distributed neutral starts and a
contested center suitable for Oddball and moving hills. Geometry and objective
markers do not establish mode support: each advertised mode needs working
runtime rules and a multiplayer acceptance result.

The current Blender art pass adds an enclosed lower facility beneath the
balcony: mirrored entrances on the same arena-facing wall connect through
indoor doglegs around a central pier. Sealed decorative service doors imply
inaccessible rooms; there is no rear exit or second outdoor area. See the
[facility authoring notes](art/facility-build.md) for dimensions, excavation,
native-asset exclusions and the Blender-only validation workflow. This revision
uses `--no-export`; its facility has not yet been baked or tested in game.

## Layout goals

- Symmetric base positions and equivalent gameplay distances; scenery can differ.
- Two entrances per base; no flag-room dead end; protected starts and escape routes.
- Middle route trades speed for exposure. Rear route uses cliff cover. Southern
  route uses the pond edge and corresponding cover on the opposite side.
- Teleporters lead to side routes, with exposed and readable exits. No free
  flag-to-flag transport. One Warthog on each side.
- Terrain and authored rocks break long firing lanes. Trees do not replace cover.
- Keep three matching tree instances for controlled foliage comparison.
- Warm neutral interior lights, cool exterior fill, restrained red/blue trim.
- Outer terrain hides rectangular map edges and sky seams from playable cameras.

## Community deliverables

An editable `.blend`, reproducible generator, JMS, placement JSON, scenario
source, upgrade configuration, inspected package staging, and the
[step-by-step walkthrough](../../../docs/custom_map_walkthrough.md).
Document the regeneration/hand-edit choice so artists do not lose changes.
Stock assets remain external dependencies with explicit references.

## Acceptance

Use repeatable Blender overview, top-down, side and interior renders for the
visual iteration loop, with authored-structure clearance checks after geometry
changes. Export and run the full game pipeline at visual milestones.

Use actual game captures for overview, each interior, pond, cliff route, and
under-tree detail. Compare to the target with the dream-loop art judge and
record frame time/FPS at player height. Run both-direction CTF, repeated
respawns, collision/teleporter checks, a second-client playtest, then a clean
launcher install. A source archive must rebuild without the author's personal
paths. Record unresolved items honestly before a public beta.

# Modular Forge pack design

The first pack, **Foundry**, is an original 18-piece industrial construction kit.
It provides a repeatable vocabulary for floors, elevation changes, enclosure,
cover and trim. The models use no extracted Halo assets. Construction shape
families are inspired by the usefulness of Halo's Forge palettes, not by copied
mesh geometry or textures.

## Reference research

Reach's structure palette groups building blocks, bridges/platforms, buildings,
decorative objects, walls/openings, inclines and natural objects. Its block family
spans several footprints and thicknesses; bridge lengths, corners and ramps let
players connect those footprints. The [Reach structure catalog][reach-catalog]
and [Bungie's original palette screenshots mirrored on ForgeHub][palette] provide
concrete examples of the categories. The original catalogue is an Xbox 360
reference, so it is not an exhaustive list of later MCC additions.

In a [2010 developer Q&A][ferrex], Bungie systems designer Tyson Green explained
that pieces were intended to abut, which avoids overlapping-surface flicker.
He also described inventory limits shared by object families. Both details
support investing in compatible dimensions and useful reusable pieces before
large one-off decorative prefabs.

The [official MCC July 2020 announcement][mcc] documents Halo 3's rotation snap,
coordinate snap, precision edits and world/local rotation axes. Reach received
axis toggling plus expanded Forge World and Tempest palettes. These are useful
editing expectations for our kit; exact MCC world dimensions have not been
assumed or copied.

The [Reach manual published by Microsoft][manual] says Bungie's own Forge World
variants use the same tools and objects as players. Community examples such as
[Tension Span][tension] use multilevel bridgework; [Pinnacle][pinnacle] illustrates
towers, ramps, landing platforms and a central structure. Our demonstration
level should similarly show the kit assembled into traversable play space.

## Foundry construction contract

The following dimensions are this project's design choices, not measurements
claimed for MCC objects. One module is 2 m; placement snap is 0.5 m. All assets
use metre coordinates, Z-up and a bottom-centre origin. Keep 90-degree turns and
cardinal docking planes predictable; do not place decoration outside the nominal
bounds. Small bevels soften the image while collision remains simple and exact.

| ID | Piece | Width × length × height (m) |
| --- | --- | --- |
| `block_1x1` | Cube block | 2 × 2 × 2 |
| `block_1x2` | Long block | 2 × 4 × 2 |
| `floor_1x1` | Floor tile | 2 × 2 × 0.5 |
| `floor_1x2` | Long floor | 2 × 4 × 0.5 |
| `floor_2x2` | Large floor | 4 × 4 × 0.5 |
| `bridge_straight` | Marked bridge deck | 2 × 4 × 0.5 |
| `bridge_corner` | L-shaped bridge | 4 × 4 × 0.5 |
| `ramp` | 1:2 ramp | 2 × 4 × 2 |
| `ramp_shallow` | 1:4 ramp | 2 × 8 × 2 |
| `wall` | Full wall | 4 × 0.5 × 3 |
| `wall_half` | Half-height wall | 4 × 0.5 × 1.5 |
| `wall_corner` | L-shaped wall | 2 × 2 × 3 |
| `doorway` | Open doorway | 4 × 0.5 × 3 |
| `window` | Open window wall | 4 × 0.5 × 3 |
| `railing` | Open guardrail | 4 × 0.25 × 1 |
| `column` | Support column | 1 × 1 × 4 |
| `cover` | Low cover | 2 × 0.75 × 1 |
| `stairs` | Eight-step staircase | 2 × 4 × 2 |

The material system uses warm concrete, dark gunmetal frames, inset deck panels
and amber markers. Colour is carried by four reusable PBR materials, avoiding a
texture dependency for the first release. Markers on ramps are separate adjacent
surface strips, not coplanar decals. Door/window openings remain empty in both
the visual geometry and the compound collision geometry.

Source scripts, portable JSON geometry and the rebuild instructions live in
[`forge-packs/foundry`](../forge-packs/foundry/README.md). Blender 5.2.3 LTS was
verified locally and against the [official release page][blender]. Direct
background Python automation is sufficient; no MCP update is needed for the
generator. Generated `.blend`, GLBs, collision exports and the actual rendered
contact sheet are kept in that folder's ignored `build/` directory.

## Further visual sets

These are design directions, not delivered model packs:

| Set | Visual direction | Suitable spaces |
| --- | --- | --- |
| Relay | Pale alloy, dark inset panels, narrow cyan channels and angular cuts | Elevated platforms, clean sci-fi arenas |
| Frontier | Weathered basalt, oxidized braces and muted ochre panels | Outdoor ruins, excavation sites, rugged outposts |

Reuse the same module, origins and docking planes across sets so creators can mix
them. A second set should change silhouettes and material treatment while keeping
the same traversal clearances and connector heights.

## Demonstration and runtime checks

A small two-height arena can exercise the kit: two facing platforms, a bridge,
a lower flanking route, two ramps, cover and rails. Verify floor seams by walking
and driving over them; walk through the doorway and fire through the window;
test ramp endpoints and stairs; duplicate, rotate, save, reload and delete parts.
Finally load the variant on a client without the pack, confirm the pinned pack
downloads before loading, and confirm missing/corrupt dependencies produce an
actionable failure instead of silently dropping placed pieces.

The source validator proves the mesh/collision construction invariants. The
render proves the exported geometry and material appearance. Neither is a claim
of in-game or multiplayer validation; record that separately after running it.

[reach-catalog]: https://www.halopedia.org/Forge_objects_in_Halo:_Reach/Structure
[palette]: https://archive.forgehub.com/threads/forgeworld-official-object-list.103039/
[ferrex]: https://halo.bungie.org/misc/ferrex_forgeworld_answers_20100722.html
[mcc]: https://store.steampowered.com/news/posts/?appids=976730&enddate=1604930433&feed=steam_community_announcements
[manual]: https://download.microsoft.com/download/F/9/9/F99AB8F0-5191-4EDD-B312-7A9B9E4784FA/HaloReach_MNL_EN-US.pdf
[tension]: https://forgehub.com/assets/27447
[pinnacle]: https://www.halopedia.org/Pinnacle
[blender]: https://www.blender.org/releases/5-2/

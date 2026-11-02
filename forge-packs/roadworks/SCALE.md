# Roadworks scale reference

Roadworks uses metres. These references come from the installed CU4 game tags,
read on 2026-11-01, and the repository's assembled stock Warthog mesh audit.
One Blam world unit is **3.048 m**; level JSON positions use Unreal centimetres.
These are game measurements, not measurements of a fictional real-world vehicle.

| Reference | Metres | Source |
| --- | ---: | --- |
| Warthog assembled visual length × width × height | 6.13 × 3.25 × 2.43 | [Stock mesh assembly audit](../../docs/tag_data_pipeline.md), including attached body, wheels and accessories |
| Warthog primary rigid-body collision AABB | 5.789 × 2.833 × 1.651 | `warthog` physics model, `lists[0].aabb half extents × 2` |
| Warthog wheelbase | 3.914 | Front/back `vh_wheel_*` skeleton marker X separation |
| Warthog front / rear wheel track | 2.500 / 2.561 | Left/right `vh_wheel_*` marker Y separation |
| Spartan standing collision height | 1.981 | `spartans` biped, `physics.height standing = 0.65` |
| Spartan standing collision diameter | 1.067 | `physics.radius = 0.175`, doubled |
| Spartan normal standing camera height | 1.890 | `standing camera height = 0.62` |
| Spartan crouching collision / camera height | 1.524 / 1.280 | `physics.height crouching = 0.5`; camera `0.42` |

The Warthog's primary rigid body is a MOPP over a five-child list: the body
polyhedron and four corner boxes. Its list half extents are
`(0.949568, 0.464677, 0.270773)` WU, centred at
`(-0.002968, 0.000001, 0.484560)` WU. This is **not the entire vehicle**:
there is also a separate root proxy, wheel contact data, and visible parts
outside that body. Use the larger visual envelope for road and overhead clearance.

The wheel contact markers are on identity node `pedestal`:

| Marker | X, Y, Z (Blam WU) |
| --- | --- |
| `vh_wheel_front_left` | `0.663215, 0.410186, 0.222678` |
| `vh_wheel_front_right` | `0.663215, -0.410187, 0.222678` |
| `vh_wheel_back_left` | `-0.620845, 0.420094, 0.222678` |
| `vh_wheel_back_right` | `-0.620846, -0.420095, 0.222678` |

An 8 m clear deck leaves about 2.375 m on each side of one centred Warthog.
Two visual widths consume 6.5 m, leaving 1.5 m total for both outer clearances
and the gap between vehicles. This alone does not prove comfortable two-way
driving. Rails sit outside the nominal clear width. On the polygonal curves,
the minimum facet-normal clearance is approximately 7.996 m.

The 20 m centreline curve radius is intentionally gentle. Stock steering tuning
allows 80 degrees at zero speed and 35 degrees at full speed; those limits are
not measured turning radii. Likewise, the `0.25` WU friction-point radius and
`0.125` WU ground-depth tuning do not establish static ground clearance.
Suspension, tyre contact, chassis clearance at the ramp crest, steering and
two-vehicle passing need actual in-game driving tests.

## Reproducing the tag measurements

Run these against the owner's installed `Meteorite/Content/Paks` directory:

```powershell
$paks = 'C:\Program Files (x86)\Steam\steamapps\common\Halo Campaign Evolved\Meteorite\Content\Paks'
target\debug\mjolnir.exe values --paks $paks --group physics_model --tag 'human/warthog/warthog-' --json --elements 256
target\debug\mjolnir.exe values --paks $paks --group skeleton_model --tag 'human/warthog/warthog-' --json --elements 256
target\debug\mjolnir.exe values --paks $paks --group vehicle --tag 'human/warthog/warthog-' --json --elements 256
target\debug\mjolnir.exe values --paks $paks --group biped --tag 'Spartans/spartans-' --json --elements 256
```

The exact Warthog prefix avoids accidentally selecting a bumper or other
detached part. No stock meshes or raw tag exports are redistributed in this pack.

## Driving fixture

A level can place the stock vehicle directly, without adding it to the road kit:

```json
{"blam":{"vehicles":[{"type":"warthog","pos":[0,0,100],"yaw":0}]}}
```

The palette resolves this to `objects\vehicles\human\warthog\warthog` and
includes it in Forge's vehicle category. Vehicle placements remain dynamic in
Forge. Use `B` to return from the Monitor to the Spartan before entering the
driver seat. The stock driver's seat is `warthog_d`, with entry marker
`driver_enter`; use the game's displayed interaction binding at that seat.

Validate the straight and curve joins, both directions across the ramp ends
and crest, braking and turning near the rails, and the far end of each long
piece. Each curve segment has its own convex hull so the bend's inside remains
open. The largest guarded curve has 72 hulls, below the cooker limit of 256;
its Havok list tests children individually, so live driving is also the relevant
performance check. Offline geometry checks alone do not establish vehicle
handling or collision quality.

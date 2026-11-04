# MJOLNIR Level — Blender addon

Author Halo: Campaign Evolved custom levels (map variants) in Blender and
export them as `.level.json` for `mjolnir level bake`. The full pipeline is
documented in [docs/level_authoring.md](../../../docs/level_authoring.md); the
file format in [docs/level_format.md](../../../docs/level_format.md).

## Install

Blender 4.0+ (tested on 5.1). Either:

- run `scripts\install-blender-tools.ps1` from the repository, which installs
  and enables this addon (and blender-mcp, downloaded from GitHub) in the
  newest Blender under Program Files; pass `-BlenderExe` for another, or
- zip the `mjolnir_level` folder and install it via
  *Edit → Preferences → Add-ons → Install…*, or
- for development, add `tools/blender` to `sys.path` and
  `import mjolnir_level; mjolnir_level.register()`.

## Use

Everything lives in the 3D Viewport sidebar (`N`) under **MJOLNIR**:

1. **Scene panel**: set the level slug/title, the canvas scenario (default
   B40), and the origin — where Blender's world origin lands on the canvas
   map, in UE centimeters. Build the level around your own origin; move the
   whole thing later by editing this one value.
2. Select any object and give it a **Role** in the object panel:
   - *Player start*, *Vehicle*, *Weapon*, *Equipment* — solid, baked into the
     scenario tag (types come from `defs/level/palette-map.json`)
   - *Structure* — a scenery/crate placement: solid Blam objects, the only way
     to add geometry the simulation collides with
   - *Decor mesh* — a runtime-spawned UE mesh: **visuals only, never solid**
   - *Marker* — a named point for future game modes
3. **Place shipped mesh…** drops a wireframe proxy box (real dimensions) for
   any of the game's ~12k static meshes; generate the catalog once with
   `mjolnir mesh list --paks <Paks> --out mesh-catalog.json` and point the
   scene panel at it.
4. **Export .level.json**, then bake and install:

   ```
   mjolnir level bake my_level.level.json --paks <Paks> --install-test
   ```

   The export owns the whole world. It writes a default sun, skylight and
   atmosphere for the loader to spawn, and clears the canvas mission's own
   vehicles, weapons, equipment and placed bipeds (`blam.clear`), so only the
   scene's content remains. The mission's AI squads and script stay; add
   `squads` and `scripts` to `blam.clear` by hand to remove them
   ([docs/level_format.md](../../../docs/level_format.md)).

Blender works in meters, Z-up; the exporter converts to UE centimeters and
negates Y and every rotation angle. Compound (multi-axis) rotations can differ
in composition order between the engines — prefer yaw-only rotations for
placements.

All operators work headless (`blender --background --python …`) and through
blender-mcp.

## Actual game mesh references

**Load actual game mesh…** extracts real geometry instead of a proxy box. Set
the MJOLNIR CLI executable, installed game's `Meteorite/Content/Paks` directory
and a local cache directory. Enter an exact mesh name or UE asset path. Static
meshes and skeletal rest-pose references are supported. These imports are
reference objects, excluded from this add-on's level exporter.

Native extraction supplies geometry and material slots, not Unreal shader
graphs. **Load local glTF reference…** also accepts converted CE models such as
`characters_cyborg_mp_cyborg_mp__bipd.gltf`. It applies no arbitrary height scaling.
Scene unit scale is respected, including TST's 3.048 metres per Blender unit.

Keep reference imports in a separate preview `.blend` when working with the
Halo JMS exporter: that third-party exporter does not understand MJOLNIR's
exclusion properties. Do not export the generated preview scene as a CE BSP.

## PCG surface permissions

Select mesh faces in Edit Mode, then **Assign PCG permission**. In Object Mode
the same action sets an object default. The face integer attribute
`mjolnir_pcg_policy` is independent of shader names. Resolution order is explicit
face permission, object default, material default, automatic. Face value 0
inherits; use **Ground + cliff** to override an inherited prohibition.

| Permission | Ground scatter | Cliff cladding |
|---|---|---|
| Inherit / automatic | Existing rules | Existing rules |
| No procedural dressing | Off | Off |
| Ground scatter only | Allowed | Off |
| Cliff dressing only | Off | Allowed |
| Ground + cliff | Allowed | Allowed |

These are permissions, not forced placement. Biome, slope, support, sea height
and playable-clearance checks still apply. A rock material can be bare or dressed.
Authored door trim can be **No procedural dressing**. Rock walls can use **Cliff
dressing only**, or **Ground + cliff** if suitable tops should grow turf.

Switch to Object Mode and **Export PCG surface permissions** to a
`.surfaces.json` sidecar. Add its repository-relative path as `surface_policy`
in `tools/level/ce_upgrade_maps.json`. The upgrade passes it to
`scatter_foliage.py --surface-policy`. It tests candidate surface positions
before grass lift or cliff inset, using Blender world metres converted from
UE centimetres with Y flipped. Overlapping permissions use the most restrictive
result. Unmarked or unmatched surfaces retain automatic rules. Permissions apply
at placement origins; existing clearance tests govern the generated asset's extent.
The mask itself does not define collision. The existing later collision stage
handles supported rocks, trunks and reachable cladding; playtest the final result.

Re-export the sidecar after geometry changes. Export the matching JMS at the next
build milestone; a sidecar does not update game terrain by itself. TST's generator
assigns ground, both and none as material defaults and writes `tst.surfaces.json`.
Hand-painted overrides belong to the hand-edited workflow; regeneration recreates
the scene. `render_preview.py --views pcg` renders an isolated color review:
green = ground, cyan = both, purple = cliff, grey = none. Source materials stay intact.

## Native scenery in the TST design preview

`tools/blender/prepare_native_preview.py` uses the runtime's `scenery_swap.py`
recipes with current source placements. It assembles each Lrg_A tree's trunk,
branches and attached leaf clusters, and exports native rocks from the user's
installation. TST caches 22 unique meshes, shared across instances. Explicit
local albedo/normal bindings approximate the materials; they do not reproduce
layered UE shaders, wind or game lighting. Blender does not execute UE PCG graphs.

```powershell
python tools/blender/prepare_native_preview.py `
  --placements levels/test/tst/placements.json `
  --scene C:/haloce/ce_conversions/community/TST `
  --staging C:/haloce/ce_conversions/community/TST/staging `
  --cli target/release/mjolnir.exe `
  --paks 'C:/Program Files (x86)/Steam/steamapps/common/Halo Campaign Evolved/Meteorite/Content/Paks' `
  --cache .dream-loop/game-assets --out .dream-loop/native-preview
```

Add `--native-assets .dream-loop/native-preview/native-preview.json` to the
TST render command. Add `--cyborg <local-cyborg.gltf>` for the character reference.
The renderer rejects stale placement manifests. It reports the imported model
height: 2.15 m for the tested CE cyborg. This is not the movement collision capsule.
Its textures remain local references.

The cache corrects triangle winding when exported faces consistently oppose
their authored normals, recording a `.winding.json` receipt. BC5 X/Y normal maps
receive reconstructed Z and DirectX green-channel conversion in the Blender
shader. Source game files are never modified. Rebuild the cache after game updates.

Do not put extracted models, textures or the resulting preview `.blend` in a
community source download. Distribute this add-on, recipes, source geometry and
asset references; each author builds a local cache from their installation.
`.mjolnir-cache/` and `.dream-loop/` are ignored by Git.

### Actual PCG instances

TST's `levels/test/tst/preview-native.ps1` runs the full prepared preview workflow.
The source adapter exports current Blender triangles to the runtime scatterer,
using exported per-face permissions and an unbaked neutral lightmap. The grass
and cliff-cladding records load through `pcg_scene.py` as shared Geometry Nodes
instances. Mesh export supports both `SM_` and Megascans `S_` names. Nonzero LODs
are excluded so their cards/shells cannot overlap the visible mesh. Native grass
uses packed ART red for opacity, green for roughness and reconstructed BC5 normals.

The separate authored rock recipe passes through `scenery_swap.py` in both
preview and runtime. Source/placement/decor hashes detect stale preparation.
Unreal layered shaders are approximated; Blender does not execute Unreal PCG
graphs or wind. Wild grass, short groundcover, leafy weeds/clover/dandelions
and cliff cladding are the current preview scope. Native plant cutouts use
verified packed ART opacity; preparation validates the added material slots.
All extracted data and generated preview scenes stay local and ignored.

## Validation

Run `tools/blender/test_authoring.py` in background Blender to check registration,
face assignment, CE-unit conversion and reference exclusion. The pure Python
`tools/level/test_surface_policy.py` covers triangle matching and permissions.

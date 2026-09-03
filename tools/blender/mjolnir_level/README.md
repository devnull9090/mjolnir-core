# MJOLNIR Level — Blender addon

Author Halo: Campaign Evolved custom levels (map variants) in Blender and
export them as `.level.json` for `mjolnir level bake`. The full pipeline is
documented in [docs/level_authoring.md](../../../docs/level_authoring.md); the
file format in [docs/level_format.md](../../../docs/level_format.md).

## Install

Blender 4.0+ (tested on 5.1). Either:

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

Blender works in meters, Z-up; the exporter converts to UE centimeters and
negates Y and every rotation angle. Compound (multi-axis) rotations can differ
in composition order between the engines — prefer yaw-only rotations for
placements.

All operators work headless (`blender --background --python …`) and through
blender-mcp.

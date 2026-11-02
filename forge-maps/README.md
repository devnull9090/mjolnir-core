# Forge Canvas, Crossline and Roadworks Circuit

Forge Canvas is an empty 64 × 64 metre deck with a two-metre grid and open sky.
Crossline **0.2.0** is a **48 × 80 metre** Red versus Blue arena with raised bases, ramps, side walkways,
linked teleporters and coloured lights, intended for two to eight players.
A continuous perimeter of 96 Foundry Wide full walls encloses Crossline: three
courses make a 9 m boundary, extending 4.5 m above the raised decks. Interior
railings and openings lead to other playable areas. The eighteen-piece
[Foundry Wide pack](../forge-packs/foundry-wide/README.md) doubles structural
footprints while preserving their heights. Portal frames, pads and lights use
the original Foundry pack at their existing size. Forge Canvas stays empty.

The separate [Roadworks Circuit / RWC](roadworks/README.md) is now version
**0.2.0**: a **731 m** Warthog circuit with **16 m clear lanes**, 24/48 m
straights, R40 curves and gradual ramps on a 320 × 320 m recovery deck. Its
horizontal dimensions are double the original Roadworks layout; road heights
remain 3 m and 7 m. Three full-size Warthogs include two facing opposite
directions on the approach straight, plus one beside the pit's player starts.
The two-metre scale bar and Foundry pieces retain their original sizes.
Roadworks and Foundry remain separate pack dependencies. Forge Canvas retains
its existing dimensions and version 0.1.0. Updating Crossline does not resize
the Foundry pieces used by Roadworks or earlier saved maps.

![Roadworks Circuit Blender layout preview](art/roadworks-circuit.png)

This Blender preview uses the generated road placements and authoring
materials. Stock Warthogs and player markers are omitted; it is not an
in-game capture.

These are standalone map archives, with their own collision, world and map
codes: **Forge Canvas / FBK**, **Crossline / FRB** and **Roadworks Circuit / RWC**. The editable JSON files
are source templates; installing a map does not install a private saved layout.
The initial versions are local development builds until published through the
Hub. A source build alone does not mean the current public launcher or mods
already include the required pack support.

## Gallery

**Crossline 0.2:** the enlarged arena from a normal Spartan camera, with
ordinary visibility culling. This build passed live ramp traversal,
teleporting in both directions, and Wide piece placement/save/reload checks.

![Crossline 0.2 enlarged walkways in game](art/crossline-wide-game.png)

**Historical Crossline 0.1 captures:** these actual game images show the
original 24 × 40 m arena, before the 0.2 footprint enlargement.

| Overview | Red base |
| --- | --- |
| ![Crossline overview in game](art/crossline-overview-game.png) | ![Red base and teleporter in game](art/crossline-red-base-game.png) |
| **Lower route** | **Perimeter walls** |
| ![Crossline lower route in game](art/crossline-lower-route-game.png) | ![Crossline solid perimeter in game](art/crossline-perimeter-game.png) |

### Roadworks gameplay photos

**Historical Roadworks 0.1 captures:** these show the original 8 m lanes,
160 m recovery deck and two-car layout. They establish the original scale
and driving checks; enlarged 0.2 photographs and driving evidence are pending.

The real Spartan and Warthog on the test pad; the orange ground scale bar is
**2 m long**, with a centre tick at 1 m:

![Spartan and Warthog beside the two-metre scale bar](art/roadworks-scale-game.png)

| Course overview | Gradual ramp |
| --- | --- |
| ![Roadworks Circuit in game](art/roadworks-overview-game.png) | ![Warthog on the Roadworks ramp](art/roadworks-ramp-game.png) |

The overview and ramp use the detached FlyCam with native player-camera
visibility culling temporarily disabled for photography. Normal culling was
restored before driving; geometry and collision were unchanged. The live
drives crossed the pit connection, straight/curve joins and the full raised
route. See the [recorded checks](../docs/forge_pack_validation.md#roadworks-01-validation).

### Blender layout previews

These Blender previews use the actual level placements and authored materials.
They show the enclosed layout; game lighting and materials can look different.

![Crossline enclosed layout, elevated view](art/crossline.png)

[Opposite elevated view](art/crossline-opposite.png) ·
[Overhead layout](art/crossline-top.png) ·
[Blank Forge Canvas](art/forge_canvas.png)

The [wall-piece guide](../forge-packs/foundry/README.md#walls-and-boundaries)
lists full walls, half walls, corners, doorways, windows and railings with
their dimensions and clear openings.

## Play and build

Once the compatible launcher, mods and map releases are published, install
each map from its Hub listing. The launcher downloads its exact pack releases
and the compatible CE runtime dependency first. Restart the game if
the launcher needs to replace an already mounted pack.

Choose **Forge Canvas → Forge** to start from the empty deck, or
**Crossline → Team Slayer** to play the Red versus Blue layout. Crossline also
offers Slayer and Forge. Choose **Roadworks Circuit → Slayer** to drive or
**Roadworks Circuit → Forge** to edit its road pieces. Forge remains a solo/host authoring mode while its
multiplayer editing path is under development.

In Forge, press **B** to become the Monitor. Use **Left/Right** to choose a
category, **Up/Down** to choose an item, and **Insert** to place it. **V** grabs
or drops a piece, **Page Up/Down** changes its distance, **comma/period** rotates
it, **N** duplicates it, and **Delete** removes it. Foundry pieces display their
authored names. The utility palette contains spawn points and teleporters;
**P** changes a teleporter's channel, which must match its destination.

**New controls in development, not yet released:** aim at or hold a piece
and press **F3** to cycle **Normal / Fixed / Phased**. Normal uses the
object's usual physics and can fall after release. Fixed holds it where
placed; Phased also allows overlap with other geometry. Choose Fixed or
Phased for suspended platforms. These are native Forge object properties.

**F4** cycles MJOLNIR's position grid through **off, 0.25, 0.5, 1, 2 and
4 m**. Placement and drop align the object's origin to the nearest grid
point, measured from the map's world origin; this does not automatically
join piece edges. **F10** cycles rotation snapping through **off, 90°, 45°,
30°, 15° and 5°**. Comma/period request the next angle on that world yaw grid;
with snapping off, they turn by **22.5°**. Use **Phased** for precise
construction: collision can resist a held Fixed object's turn, and the
game's hold motion can leave a small angle difference even in Phased mode.
Check the pose after dropping. The Monitor HUD shows these settings and
the target's physics mode. Live checks cover weapons, a Wide floor and a
spawn marker; see the [validation record](../docs/forge_pack_validation.md)
for their results and limits.

Press **F5** to save, **F6** to reload the saved layout, or **F2** to restore the
map's authored starting layout. Saved layouts also apply when the map is
played outside Forge. Keep both `<MAP>.mvar` and `<MAP>.mvar.packs` together
when copying a save; the second file records its exact pack and palette
bindings. The launcher resolves missing saved-layout packs before launch.
See [Forge controls](../docs/forge.md) and [pack dependencies](../docs/forge_packs.md).

## Rebuild the maps

Run `python forge-maps/generate.py` to regenerate the editable levels from the
layout source and current Foundry / Foundry Wide catalogs. Make changes there or in a copy of
the level JSON. A new published map needs its own three-character map code
and Hub slug; keep palette ordering stable when updating an existing map.

Build the [Foundry content pack](../forge-packs/foundry/README.md),
[Foundry Wide](../forge-packs/foundry-wide/README.md) for Crossline, and the
[canvas BSPs](../docs/forge_canvas.md) first. The default collision files
are `forge-packs/foundry/build/canvas/blank.sbsp` (64 × 64 metres) and
`forge-packs/foundry-wide/build/canvas/crossline.sbsp` (48 × 80 metres),
with their generated `.canvas.json` receipts.
The build uses the repository's minimal `defs/level/empty_world.umap`; the
baker adds the scenario settings and assigns each map its own world name.
Sky and lighting come from the level JSON.

Create a read-only Paks view containing the game, the tested CE runtime, and
the required packs' newly built `.utoc`/`.ucas` files. Then run:

```powershell
python tools/forge/build_maps.py --paks C:/path/to/combined-paks --runtime '^1.17.0' --only crossline
```

Use the runtime range actually tested for the release. Optional arguments:
`--only blank` or `--only crossline`, `--version 0.1.0`, `--cli`, `--world`,
`--collision-dir`, `--pack-manifest`, and `--out`. Default manifests are read
from `forge-packs/<slug>/build/game/all/mjolnir.json` for each required pack.
The builder refuses a Paks view whose pack container bytes differ from the built releases, or a level
whose pack palette or canvas dimensions no longer match its inputs.

Use `--only blank` or `--only crossline` to build either of these maps without
Roadworks. With no selection the builder includes every map; see the
[Roadworks build instructions](roadworks/README.md#rebuild) for its additional
pack and canvas inputs. `--pack-manifest` can be repeated when supplying
several exact built pack releases.

The default map versions are Roadworks Circuit **0.2.0**, Forge Canvas
**0.1.0** and Crossline **0.2.0**. `--version` explicitly overrides the version
for the selected build.

Every run creates a new retained directory under `forge-maps/build/`. It
contains each map's level snapshot, standalone bake, registration record,
`.mjolnir` archive, command log and a report of input/archive hashes. Nothing
is installed into the game. The archives contain the map data and containers;
the launcher generates the shared registration container at installation.
Foundry, Foundry Wide and Roadworks stay separate exact-version dependencies, so maps share
the same installed pack releases.

Local test archives are unsigned. For a Hub submission, pass `--sign` using a
registered device key, or `--sign-seed <file>` using a registered publisher
key. Do not alter an archive after signing. Follow the normal
[map publishing workflow](../docs/map_distribution.md); a successful upload
can still require review. The editable source lives here, separately from
the player archives and locally extracted game data.

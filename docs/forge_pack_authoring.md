# Create a community Forge pack

A Forge pack adds your models to the pieces a map can offer in Forge. You can
contribute **model sources** and work with a maintainer on integration, or build
a complete **`.mjolnir` content archive** yourself. A small, well-tested set of
floors, walls and ramps is a useful first contribution.

The Hub's Forge catalog lists packs, and the launcher resolves the published
releases a map or saved layout requires. This guide takes your source models
through the build, test, signing and submission workflow. If you want to focus
on modelling, a source pull request lets you work with a maintainer on the
remaining steps.

For building a level with existing pieces, start with the
[Forge building guide](forge_guide.md). This page is for making the pieces.

## Design a set that fits together

Choose a module and keep mating faces exact. Foundry uses a 2 m module;
[Foundry Wide](../forge-packs/foundry-wide/README.md) uses 4 m. A useful Wide-scale
starter set might contain an 8 × 8 m floor, an 8 m wall, a doorway and an
8 m-wide ramp. Make the ramp end at an existing floor height. A 0.5 m floor
edge can block walking even when the player fits on top; use a flush transition
or a shallow access ramp.

Author in **metres, right-handed Z up**. Bottom-centre origins work well for
buildings: the bottom face is Z = 0, and adjoining pieces share predictable
coordinates. Roads may use an entry connector as their origin; document that
choice and keep it consistent. Use a separate presentation layout for renders
so a contact sheet's scale never becomes the exported asset's scale.

Check clear space against actual game scale. The standing Spartan collision
shape is about **1.98 m high and 1.07 m across**. The assembled Warthog visual
envelope is about **6.13 × 3.25 × 2.43 m**; roads also need turning room and
space beside the vehicle. The [scale reference](../forge-packs/roadworks/SCALE.md)
records the measurements. An opening that barely fits a static box is not a
verified drivable route.

Keep the visible mesh and collision separate. A doorway needs separate jamb
and header hulls, not one solid box around its outside. Use closed, outward-wound
convex collision hulls and retain real holes between them. Small bevels and trim
can remain visual details while collision faces meet exactly. The current
collision cooker accepts at most 4,096 triangles per piece; the physics builder
accepts at most 256 convex hulls, with additional plane/vector bounds. Start
well below those limits and test the shapes you actually ship.

The catalog's `snap_m` is a suggestion, not automatic connector docking or a
per-piece editor setting. Forge's position grid and rotation controls are
described in the [building guide](forge_guide.md).

## Contribute models without building the runtime pack

Open a source pull request with a small folder under `forge-packs/<your-slug>/`.
Include the editable model source or reproducible generator, a preview, intended
dimensions and origin, and a short explanation of how the pieces join. Keep
authoring sources outside ignored `build/` directories. If native collision or
the exporter is unfinished, say so in the PR; a model contribution can be reviewed
without pretending it is already an installable pack.

State who made the geometry, which assets you reused, and their licenses. The
reference geometry and implementation use the repository's MIT license. A game
texture's presence in an installed game does not make it part of that license.
Separate original art from game-derived build inputs, and keep extracted game
files out of the source contribution. Preview images should say whether they
are Blender renders or actual gameplay captures.

Use [Foundry's generator and exporter](../forge-packs/foundry/README.md) as a
working reference, and [Foundry Wide](../forge-packs/foundry-wide/README.md) for
larger pieces. The existing Blender scripts regenerate their source meshes;
editing their generated `.blend` alone will not change the next build. A custom
Blender workflow needs an exporter that produces the inputs below. There is no
general-purpose `.blend` drag-and-drop importer into the game.

## Give the pack stable identities

Choose your own namespace rather than changing a reference pack's ID. For
example, a one-piece `courtyard-kit` catalog could begin as follows:

```json
{
  "schema_version": 1,
  "name": "Courtyard Kit",
  "version": "0.1.0",
  "type": "content",
  "summary": "Modular courtyard floors and boundaries",
  "forge_pack": {
    "schema_version": 1,
    "id": "courtyard-kit",
    "blocks": [
      {
        "id": "floor_8x8",
        "name": "Courtyard Floor 8 x 8",
        "tag": "objects\\mjolnir\\forge\\courtyard-kit\\floor_8x8",
        "category": "floors",
        "dimensions_m": [8, 8, 0.5],
        "snap_m": 0.5
      }
    ]
  }
}
```

This is metadata, not a complete model. Save the authoring catalog as
`catalog.json`; the builder writes the release manifest as `mjolnir.json`.
The pack ID must match its eventual Hub slug: 2–64 lowercase letters, digits
or hyphens, starting with a letter or digit. Block IDs and categories also
allow underscores and may be 1–64 characters. Block names are nonblank and at
most 80 characters. Dimensions and optional snap are finite positive metres.

Every block tag must be exactly `objects\mjolnir\forge\<pack-id>\<block-id>`.
Keep IDs stable, and add new entries after existing ones when maintaining a
map's palette. Every change gets a new semantic version; versions cannot
contain `+build` metadata, and published bytes never change under the same
version.

Plan updates as SemVer lines ([updating a pack](forge_packs.md#updating-a-pack)).
Maps and saved layouts built with a release keep working with any later
release in its line, so within a line keep every existing piece's ID, kind,
dimensions, snap, origin and join heights. Fix a piece's look or collision
within that shape, or add pieces, in the next release of the line: a patch
release before 1.0 (`0.2.0` to `0.2.1`), a minor or patch one after it. To
change or remove a piece, start a new line (`0.3.0`, or `2.0.0`), and expect
maps and layouts that use it to be rebuilt. The Hub refuses a release that
drops or resizes a piece of an earlier release in its line.

Catalog entries are building blocks for now. `kind` names are reserved for
scenery, weapons, vehicles, equipment and bipeds, and a `requires` list for
features later launchers add; packs using either are refused until MJOLNIR
supports them ([entry kinds](forge_packs.md#entry-kinds)).

Ordinary pieces need no behavior metadata. Optional lights, lifts, doors and
approved glass/portal surfaces are described in the
[utility contract](forge_pack_utilities.md). These fields select bounded runtime
features; they do not let a pack install arbitrary Lua, DLLs or actor paths.
A decorative teleporter housing still needs native gameplay markers and a
channel. New executable behavior belongs in a separate
[reviewed code contribution](contributing_code_mods.md).

## Build a complete local pack

First reproduce the [Foundry build recipe](forge_packs.md#build-the-foundry-content)
with the supported game/runtime files. It builds the CLI and its helper tools,
exports Blender models, and cooks the native collision and physics.
The current builder is a developer tool, not a one-click modeling application.

For a custom pack, provide these matching inputs:

| Input | Purpose |
| --- | --- |
| `catalog.json` | Release identity and block catalog |
| `source/geometry.json` | `units: "meters"`, `axes: "right_handed_z_up"`, and matching piece IDs with visual meshes and collision |
| `build/models/<id>.gltf` and its buffers | Exported metre-scale visual mesh; the reference Blender exporter writes standard Y-up glTF |
| `build/blam-collision/<id>.collision_model` | Cooked native triangle collision |
| `build/blam-collision/<id>.physics_model` | Cooked native convex physics |

The source geometry contains a `pieces` list. Each piece supplies visual
components and an aggregate collision mesh plus its individual convex hulls.
Follow the reference generators' format rather than renaming an arbitrary glTF
and assuming collision will be inferred. The ordinary builder maps its known
material names (`concrete`, `deck`, `gunmetal`, `amber`, and light lenses) to
shipped materials. Custom Blender shaders do not automatically become game
materials. Approved glass and portal profiles require the separate
[material cook](forge_pack_materials.md), including a nonconflicting shader chunk.

Once your source geometry and visual exports exist, these are the actual
custom-pack cooking commands. Run from the repository root and substitute your
pack and local input paths. `$paks` must contain the supported game and runtime
donors; keep it separate from build output. The builder uses hardlinks, so its
input view and output need to be on the same filesystem volume.

```powershell
$slug = 'courtyard-kit'
$pack = "forge-packs/$slug"
$paks = 'C:/local/base-and-runtime-paks'
$cli = 'target/debug/mjolnir.exe'

& $cli extract --paks $paks --group collision_model --filter crate_space_a `
  --shipped-only --verify --out "$pack/build/donors"
$donor = "$pack/build/donors/objects/props/covenant/crate_space_a/crate_space_a.collision_model"
cargo run -p blam-sbsp --example forge_collision -- `
  "$pack/source/geometry.json" $donor "$pack/build/blam-collision"
python tools/forge/build_collision.py "$pack/source/geometry.json" `
  "$pack/build/blam-physics" --mjolnir $cli --paks $paks --pack-id $slug `
  --payload-out "$pack/build/blam-collision"
python tools/forge/build_pack.py $pack --paks $paks

& $cli forge pack "$pack/build/game/all/mjolnir.json" `
  --content "$pack/build/game/all/content" --readme "$pack/README.md" `
  --changes "$pack/build/game/all/changes.json" `
  --out "$pack/build/courtyard-kit-0.1.0.mjolnir"
```

The final command creates an **unsigned local test archive**. It does not
install files or upload anything. `build_pack.py --only <block-id>` builds a
small diagnostic set under `build/game/<block-id>/`; do not publish that subset
as though it were the complete pack. Builders retain outputs, so use a fresh
build workspace when changing input versions or removing pieces.

## Make a test map and test the result

A map must explicitly declare the pack version and block IDs in
`blam.forge_packs`, then be baked as a standalone map with those cooked pack
containers in its input view. Follow [adding a pack to a map](forge_packs.md#add-a-pack-to-a-map)
and [level authoring](level_authoring.md). Installing a pack alone does not add
its pieces to an existing map, and there is no automatic map rebake.

A pack can describe 1–256 pieces, but a map can select at most 200 custom
references from at most 63 packs, within the engine's 255 total palette entries.
The selected subset and order belong to the map. The launcher accepts at most
4,096 enabled catalog blocks across a profile. Those are different limits;
making a larger catalog does not increase a map's palette capacity.

In a private test map, check rendering, scale, visible and physical openings,
ramp joins, and ordinary walking onto raised pieces. Try placing, grabbing,
rotating, duplicating, deleting and reloading each type. Test the intended game
modes too: free-for-all needs neutral spawn scenery, not only red/blue markers
or campaign starting locations. Record what passed and what remains untested.
The [reference validation record](forge_pack_validation.md) separates offline
checks, Blender previews and live-game evidence.

Map archives depend on the line of each pack they were baked with (`^0.2.0`).
Saved layouts use both `.mvar` and `.mvar.packs`; keep the pair together. The
launcher resolves missing published releases before launch and refuses a pack
outside the line a map or layout needs. A changed installed
pack requires a restart. Include a clean launcher profile in release testing
so you also check downloads and dependency resolution.

## Sign and submit a release

For a release, rerun `mjolnir forge pack` with **`--sign`**. This uses the device
key created by the tag editor, run as the same Windows user. Its public key
must be registered to the Hub account that uploads the release. Registration
is part of the editor's configured publishing flow; creating a local key alone
does not register it. Advanced builds may use `--sign-seed <file>` instead, with
that public key registered first. Keep private seeds and credentials out of
the contribution. See [archive signing](mod_signing_design.md).

Create a content listing on the Hub's **New mod** page (`/mods/new`), with the
Forge pack category and the same slug as `forge_pack.id`. Create the matching version on
its manage page and upload the signed `.mjolnir` archive. The scanner verifies
the signature, identity, archive contents, catalog and required surface packages;
scan failures must be fixed before publication. Selecting a category alone does
not create a valid Forge pack.

Source PRs receive maintainer review. Hub releases follow the site's scan and
moderation rules; the current automatic prepublication review queue applies to
maps from new/untrusted authors, not every content pack. Publish a small tested release with
clear provenance and limitations, then expand it while preserving the identities
that other people's maps and layouts depend on.

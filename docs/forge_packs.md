# Community Forge packs

A Forge pack is a normal `.mjolnir` **content** release with a validated catalog
of namespaced building pieces. The Hub lists these releases at `/forge`; the
launcher downloads their containers and exposes their catalog to Forge. A map
declares which pieces it supports when its scenario is baked. A saved layout
records the exact pack releases and palette bindings it used.

The first authored set is [Foundry](../forge-packs/foundry/README.md): 24 original
industrial pieces on a 2 m module, with a 0.5 m suggested placement snap.
Version 0.2 adds a portal frame, teleporter pad, light strip and three light
pylons to the 18-piece set tested below.
[Roadworks](../forge-packs/roadworks/README.md) is a separate vehicle kit:
ten original road pieces with 8 m clear decks, 12/24 m straights, 45/90-degree
curves and eased ramps, with guarded and unguarded variants. Its entry-anchored
origins and connector data are documented with the sources; current Forge
placement does not automatically snap road connectors. The Roadworks Circuit
fixture depends on both packs and includes stock Warthogs for scale and driving.
[Design research](forge_pack_design.md) explains the piece selection and future
sets. A private CU4 fixture loaded and placed all 18 types, exercised movement,
rotation, save/reload, restart persistence and identity refusal, and checked
cube/floor collision, ramp climbing and the doorway opening. See
[validation evidence and remaining checks](forge_pack_validation.md). Full visual
and traversal review, and multiplayer behavior, remain separate checks.

## Release contract

`mjolnir.json` keeps `type: "content"` so existing archive download and signature
handling applies. Its optional `forge_pack` block identifies the catalog:

```json
{
  "schema_version": 1,
  "name": "Foundry",
  "version": "0.1.0",
  "type": "content",
  "summary": "Modular industrial construction pieces",
  "forge_pack": {
    "schema_version": 1,
    "id": "foundry",
    "blocks": [
      {
        "id": "floor_2x2",
        "name": "Floor 2 x 2",
        "tag": "objects\\mjolnir\\forge\\foundry\\floor_2x2",
        "category": "floors",
        "dimensions_m": [4, 4, 0.5],
        "snap_m": 0.5
      }
    ]
  }
}
```

- The pack ID must equal the Hub mod slug: 2–64 lowercase letters, digits or
  hyphens, beginning with a letter or digit.
- Block IDs and categories are 1–64 lowercase letters, digits, hyphens or
  underscores, beginning with a letter or digit. IDs are unique within a pack.
  Names contain 1–80 characters and cannot be blank.
- Every tag is exactly `objects\mjolnir\forge\<pack-id>\<block-id>`. It names a
  crate (`bloc`) with its associated model, physics and collision tags.
- A catalog contains 1–256 blocks. Dimensions and optional snap are finite,
  positive metres. They describe authoring metadata; they do not change engine
  collision or configure the editor's global snap setting.
- Release versions are exact SemVer, at most 96 bytes. Hub versions exclude `+build`
  metadata. Changing a piece's geometry or collision requires a new release.
- Optional `deps` use the existing `{ "slug": "other-pack", "range": "=1.2.3" }`
  format. The launcher supports Rust SemVer requirements such as `^1.2.3`,
  `~1.2.3` and `>=1.2.3, <2.0.0`; a bare complete version is an exact pin.

A block may also contain a data-only `light` object (omit it for ordinary
pieces; `null` is also treated as absent):

```json
"light": {
  "offset_m": [0, 0, 3.1],
  "color_rgb": [1, 0.05, 0.03],
  "intensity_cd": 70,
  "radius_m": 8
}
```

Offsets are relative to the piece's bottom-centred authored origin, in the
same right-handed Z-up metres as its geometry. Each component must be finite
and within −100..100 m. Linear RGB components are within 0..1. Intensity is
positive and at most 10,000 candelas; radius is positive and at most 100 m.
Unknown light fields are rejected. Hub, packer and launcher validate the same
bounds. Forge derives the actor class from the pack/block IDs, attaches a
movable inverse-square point light to its root, and converts metres to Unreal
centimetres with Y reflected. It does not execute pack code or accept an
arbitrary actor path. Illumination is capped at 64 active fixtures, is currently
shadowless, and has no exposure multiplier. Deleted/pooled actors and world
changes remove their attached lights. See [Forge utilities](forge.md#pack-lights).

The archive contains `mjolnir.json`, cooked `.utoc`/`.ucas` pairs under
`content/`, optional `docs/README.md` and `changes.json`, and author signatures
when signed. Source `.blend`, glTF and collision JSON files are authoring inputs,
not directly installable content. The launcher generates container `.pak` stubs.
The generated Foundry release uses original visual geometry and collision with
game-specific actor/tag templates and shipped material references; its cooked
outputs require the supported game installation.

The Hub validates the catalog during the normal upload/scan/publish flow and
stores it on the release. `GET /api/v1/releases/{id}/forge-pack` returns the
published catalog, release version, archive SHA-256 and dependencies. The mod
detail page displays piece names, dimensions and snap. Choosing the Forge
category alone does not put an unvalidated archive in the Forge catalog.
Publishing still uses the existing registered author-key requirements and
review rules; this work does not deploy the Hub or publish a release.

## Build the Foundry content

Run these commands from the repository root. `$paks` is a developer's installed
game directory, and generated donors/cooked content remain local under ignored
`build/` directories. The examples use the debug tool builds for iteration.

```powershell
$paks = 'C:\Program Files (x86)\Steam\steamapps\common\Halo Campaign Evolved\Meteorite\Content\Paks'
$cli = 'target\debug\mjolnir.exe'

cargo build -p blam-cli
cargo build -p ue-asset --example mesh_rewrite --example forge_actor
cargo build -p blam-pack --example package_add

python forge-packs/foundry/generate.py
python forge-packs/foundry/validate.py
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --background --factory-startup `
  --python forge-packs/foundry/build_blender.py -- --render

& $cli extract --paks $paks --group collision_model --filter crate_space_a `
  --shipped-only --verify --out forge-packs/foundry/build/donors
cargo run -p blam-sbsp --example forge_collision -- `
  forge-packs/foundry/source/geometry.json `
  forge-packs/foundry/build/donors/objects/props/covenant/crate_space_a/crate_space_a.collision_model `
  forge-packs/foundry/build/blam-collision
python tools/forge/build_collision.py forge-packs/foundry/source/geometry.json `
  forge-packs/foundry/build/blam-physics --mjolnir $cli --paks $paks `
  --payload-out forge-packs/foundry/build/blam-collision

python tools/forge/build_pack.py forge-packs/foundry --paks $paks
& $cli forge pack forge-packs/foundry/build/game/all/mjolnir.json `
  --content forge-packs/foundry/build/game/all/content `
  --readme forge-packs/foundry/README.md `
  --changes forge-packs/foundry/build/game/all/changes.json `
  --out forge-packs/foundry/build/foundry-0.2.0.mjolnir --sign
```

`--sign` uses the existing local author device key registered with the Hub.
`--sign-seed <file>` uses an explicitly supplied key instead. Omit signing for an
offline build; the Hub does not accept an unsigned public upload. The packer
validates the catalog, container pairing and basic IoStore structure before it
writes the archive. The Hub independently scans the submitted archive.

`build_pack.py --only <block-id>` produces a reduced diagnostic inventory in
`build/game/<block-id>/`; package that directory only for local tests. Do not
publish a reduced diagnostic build with the same version as the full set. Use
a fresh output directory when changing the set's inventory: these development
builders retain prior outputs.

The visual cooker writes a namespaced mesh and synchronized actor per piece.
Blender/glTF geometry is converted to the game's units; the actor restores each
piece's bottom-centred authored transform after mesh normalization. Actor visual
collision is disabled so the simulation owns collision. The collision cooker
builds triangle collision BSPs/MOPPs and fixed Havok polyhedra from the same
source hulls. Composite pieces keep separate hulls so doors and windows remain
open. The pack builder then creates namespaced collision, physics, model and
crate tags and packages their visual dependencies.

## Add a pack to a map

Add the desired subset to the level JSON before a `level bake --standalone`
build. Forge pack palettes currently require a standalone map; canvas overrides
are rejected because they do not install the new package preloads. Keep the
pack's cooked containers available in the bake's input Paks view so tag
references and preload dependencies resolve.

```json
{
  "blam": {
    "map_variant": true,
    "forge_packs": [
      {
        "slug": "foundry",
        "version": "0.1.0",
        "blocks": [
          {
            "id": "floor_2x2",
            "tag": "objects\\mjolnir\\forge\\foundry\\floor_2x2"
          }
        ]
      }
    ]
  }
}
```

This is a fragment to merge with the existing level definition. The bake adds
one custom Forge palette in the authored pack/block order. There is **no global
slot assignment**: independent maps choose their own subset and order. At most
63 packs and 200 custom references are accepted, and the completed palette must
fit the engine's 255-entry total including standard objects. The baker checks both
limits. It also adds each custom crate to the scenario wrapper's preload list,
dependency bundle and container package-store imports, preserving the donor
wrapper. A declared crate absent from the input Paks fails the bake.

Package the newly baked map with the existing `mjolnir map pack` command.
It preserves `blam.forge_packs` in the archived level JSON and adds exact
`=0.1.0` dependencies for the listed packs. Installing the map through the
launcher resolves those dependencies, selecting a compatible published release
rather than blindly installing each dependency's latest version. The launcher
validates the enabled profile's dependencies before mounting content. A first
live map installation can mount new Forge pack dependencies before the map;
replacing an already installed pack requires a restart.

Installing a pack does **not** add slots to an already baked map. Such a map
must be rebaked and repackaged with `blam.forge_packs` before those pieces can be
placed. There is no automatic rebake or arbitrary runtime palette injection in
this implementation. Keep pack/block ordering stable when updating a map if
its existing layouts should continue to load.

## Saved layouts and downloads

The launcher writes generated catalog files beneath
`ue4ss/MJOLNIRForgePacks/`: `installed.json` for the editor's display metadata and
`installed.txt` for the native identity check. These represent enabled,
verified releases and include exact archive SHA-256 values. Forge labels match
full tag paths, so two packs may use the same block ID without ambiguity.
At most 4,096 catalog blocks may be enabled across a profile, matching the
native inventory reader's bound; each map still has its smaller palette limit.

Saving a layout writes both `<MAP>.mvar` and `<MAP>.mvar.packs` beneath
`ue4ss/Mods/MJOLNIRForge/layouts/`. Keep the pair together when copying or sharing
a layout. The sidecar starts with `forge-packs 1`; each following tab-separated
row contains:

```text
flat-palette-index    full-tag-path    pack-slug    exact-version    archive-sha256
```

Only custom pieces actually used by the layout produce rows. Every new `.mvar`
contains an `fpk1` marker, including saves with no custom pieces, so removing
its sidecar cannot make it appear to be a legacy layout. Old layouts without
the marker remain usable when they do not reference custom pack tags.

Before launch, the launcher reads saved-layout pack requirements and downloads
missing exact releases through the normal verified Hub install flow. It checks
the sidecar fingerprint against the published archive and enables the dependency
closure. Conflicting versions required by saved layouts or enabled maps stop
launch with an explanation; move the affected layout pair aside or use
compatible map/pack versions. The launcher does not silently reinterpret old
placements using a newer pack.
Orphan sidecars without a matching `.mvar` and files in layout history do not
trigger downloads.

Before the engine recreates saved objects, native Forge checks each recorded
flat palette index against the current full tag path and installed pack version
and hash. Missing inventory, a different palette binding, a missing sidecar on
a new save, or changed release bytes refuse the layout. These checks prevent a
saved custom index from becoming an unrelated object after a profile or map
change. They do not migrate a layout to a different palette.

Downloads happen at launcher installation/launch time. Opening an incompatible
layout while the game is already running reports the dependency problem and
requires a launcher restart; the native DLL does not access the network.
Standalone Hub publishing of `.mvar` layout pairs and automatic map rebaking
remain follow-up work.

## Verification

The repository tests cover manifest/catalog rejection and Hub release
visibility, exact dependency selection and a local HTTP download fixture,
signature/archive round trips, IoStore bounds, and native identity mismatches.
Useful focused commands are:

```powershell
cargo test -p blam-cli forge
cargo test --manifest-path apps/launcher/src-tauri/Cargo.toml --lib
& native/forge/test-pack-bindings.ps1
python forge-packs/foundry/validate.py
```

Run the Hub's `npm test` and `npm run typecheck` from `hub/` when changing that
component. Geometry validation and the collision builder's ray checks verify
authored shapes offline. Before publishing
a playable pack, verify in game that each piece renders at its declared size,
ramps and platforms support players, apertures stay open, placement/duplication
and save/reload work, and a clean launcher profile fetches the exact dependencies.

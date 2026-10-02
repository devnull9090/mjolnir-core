# Distributing converted maps

**Status:** 2026-10-02. Format v1 is proven with Blood Gulch: a pack built by
`mjolnir map pack`, installed as the launcher will install it and registered
by `mjolnir level register`, plays CTF. Phases 1 to 3 are done: the hub takes
map packs with a review queue, and the launcher installs them with their
dependencies and registers them (`apps/launcher/src-tauri/src/maps.rs`). Of
Phase 4, `map pack`, `map runtime` and `build_ce_runtime.sh` are done; the
packs are not published yet. The tag editor's map publishing remains: see
[Phases](#phases).

Converted Halo CE maps ([ce_map_conversion.md](ce_map_conversion.md)) reach
players the way texture swaps and tag edits do. Each map is baked ahead of
time, uploaded through the mod hub, stored in R2, and installed by the
launcher. Players can publish their own maps the same way.

Three rules shape everything below:

- **No game-derived bytes in git.** A baked map clones shipped tags (the
  canvas scenario, the donor BSP, object definitions) and carries CE's
  geometry, textures and sounds. These bytes live only in R2, behind the
  hub. The repository holds the tools, the code mods and the design.
- **No Unreal Editor on a player's machine.** Baking needs the editor today
  (the materials and sounds cook), so maps ship pre-baked. Player
  publishing waits on the Rust cook ([Phase 5](#phases)).
- **Anything executable still ships only from signed CI.** A map pack is
  data: containers, JSON, textures and Megalo variants (bytecode the game's
  own interpreter runs, sandboxed like a game type). The loader and lobby
  that read it are code mods, released by `release-mods.yml` as before.

## The pieces

| Piece | Kind | Published by | Holds |
|---|---|---|---|
| A map, e.g. `ce-blood-gulch` | hub `map` | map author | the map's containers, level file, registration record |
| `mjolnir-ce-runtime` | hub `content` | us | everything every converted map shares |
| MJOLNIRLevelLoader, MJOLNIRLobby | code mods | signed CI | the loader, the multiplayer menu, the game types (`.mglo`) |

### A map pack

A `.mjolnir` archive ([mjolnir_format.md](mjolnir_format.md)) of type `map`:

```
mjolnir.json                  manifest: type "map", plus the map block below
signature.json                added when the tag editor publishes it
content/
  MJOLNIRMAP-<CODE>_P.utoc     the scenario, its BSP, and the map's own world
  MJOLNIRMAP-<CODE>_P.ucas
  MJOLNIRMESH-<CODE>_P.utoc    the terrain mesh
  MJOLNIRMESH-<CODE>_P.ucas
  MJOLNIRCOOK-<CODE>_P.utoc    the map's cooked CE textures, lightmaps and
  MJOLNIRCOOK-<CODE>_P.ucas    ambient sounds
map/
  level.json                  the level file the loader reads
  registration.json           the bake's registration record (below)
docs/README.md                optional
```

Format rules (version 1):

- Every package a map adds lives under `/Game/MJOLNIR/Maps/<CODE>/`, so two
  maps never claim the same package. The level file names only `/Game`
  paths: either the map's own, or the runtime pack's.
- A map cooks into a chunk of its own, `10000 + int(CODE, 36)` (Blood Gulch,
  `BGL`, is 24853). A `PrimaryAssetLabel` at the map's root sets it, so the
  map's cook never mixes with the runtime pack's chunk 988.
- No `.mglo`, no loose textures and no code. A `map/preview.png` is
  [Phase 6](#phases).

The manifest's map block:

```json
{
  "schema_version": 1,
  "name": "Blood Gulch",
  "version": "1.0.0",
  "type": "map",
  "map": { "code": "BGL", "title": "Blood Gulch", "modes": ["slayer", "ctf"] },
  "compat": { "min_build": "2026.06.26.1097863.1" },
  "deps": [{ "slug": "mjolnir-ce-runtime", "range": "^1.0.0" }]
}
```

- `code` is the three-character scenario codename. It is unique across the
  hub, which rejects a second map claiming a code someone else's map holds.
- `modes` lists the game types the multiplayer menu offers. Each one must be
  a variant the loader ships (`slayer`, `ctf`, ...).
- The registration record is what `mjolnir level bake --standalone` writes
  beside its output as `<CODE>.registration.json`: the codename, the canvas
  scenario it was cloned from, the title, the description and the world
  path. The launcher
  builds the shared registration container from these records
  ([below](#the-registration-container)).

A map pack carries no `.mglo`. Game types are code-reviewed scripts the
loader ships, so a map can only name them. Custom game types per map are
[Phase 6](#phases).

### The CE runtime pack

This pack is published once by us and updated rarely. It holds everything
converted maps share. `tools/level/build_ce_runtime.sh` builds it:

| Container | Holds |
|---|---|
| `pakchunk988-MJOLNIRMAT-Windows` | the CE material masters (`/Game/MJOLNIR/CE/M_CE_*`) and their shader library; the CTF flag's textures (`/Game/MJOLNIR/CE/CTF`); the announcer and event sounds (`/Game/MJOLNIR/Sounds/Events`) |
| `pakchunk990-MJOLNIRCTFMESH_P` | the CE flag mesh (`/Game/MJOLNIR/CTF/SM_CE_Flag`) |
| `pakchunk990-MJOLNIRFLAG_P`, `-STAND_P`, `-MOTL_P` | the CTF flag weapon, its stand, and the object-type-list override that adds the flag |
| `pakchunk994-MJOLNIRSPAWN_P`, `993-MJOLNIRTELES_P`, `992-MJOLNIRTELER_P` | the spawn point and both teleporter ends |
| `pakchunk990-MJOLNIRHPACK_P`, `-HPSPOT_P`, `-HPMESH_P` | the health pack, its spawn spot and its mesh |
| `pakchunk984-MJOLNIRUI-Windows` | the multiplayer screens and HUD widgets ([custom_ui.md](custom_ui.md)) |

A map's ambient sounds are not shared. They cook into the map's own chunk,
under `/Game/MJOLNIR/Maps/<CODE>/Sounds`, so a map ships only the sounds it
plays.

Its containers are content containers, so they install like any content
mod. Its version moves when a shared piece changes; maps depend on a
compatible range. `mjolnir map runtime <out dir> --version X --sign`
packages the builder's output as the `mjolnir-ce-runtime` content mod.

## Installing

### Where things go

| What | Where |
|---|---|
| Map and runtime containers | `Meteorite/Content/Paks`, named by the launcher (`pakchunk{9xx}-MJOLNIRHUB-<slug>-<n>_P`), with stub `.pak` siblings |
| Map data (`map/`) | `Binaries/<Win64\|WinGDK>/ue4ss/MJOLNIRMaps/<CODE>/` |
| The map list | `ue4ss/MJOLNIRMaps/maps.json`, generated |
| The registration container | `Paks/pakchunk996-MJOLNIRREG_P.{utoc,ucas,pak}`, generated |

A container that carries a shader library keeps its own chunk number in
the name the launcher gives it (`pakchunk988-MJOLNIRHUB-…`), not a load
order number. UE opens a mounted pak's shader library by the number it
reads off the file name (`ShaderCodeLibrary.cpp`, `OnPakFileMounted`), so
the CE material masters renamed to `pakchunk9NN` would mount without
their shaders.

Map data lives **outside** `Mods/MJOLNIRLevelLoader`. The launcher digests
each code mod's folder to detect tampering, so files written into the loader's
folder would make it read as "Modified". The loader reads
`ue4ss/MJOLNIRMaps` first and still falls back to its own `levels/` folder,
so maps converted locally with `--install` keep working.

### The registration container

The simulation builds its map list at boot from the cooked `DT_Scenarios`
table and the campaign's `ScenarioList`
([new_scenario_loading.md](new_scenario_loading.md)). So one container must
list every installed map. A map cannot ship its own copy: two maps would
claim the same chunks, and only one would win. The container is also a
modified copy of shipped data.

The launcher therefore builds it locally after every map install, uninstall,
enable or disable. The build is `mjolnir level register`:

1. read every enabled map's `registration.json`;
2. clone `DT_Scenarios` and `DA_FirstPlayableCampaign` from the player's
   own game files, and add one row and one handle per map
   (`blam_pack::scenario::register`);
3. write `pakchunk996-MJOLNIRREG_P` and `maps.json`.

The launcher links `blam-pack` for this, so it never runs the CLI. It
rebuilds only when the set of enabled maps or the game build changed since
the last rebuild, which it records in `MJOLNIRMaps/.mjolnirhub-registered.json`.
The game build is a fingerprint of the shipped containers' names, sizes and
times. Launching the game checks it, so a game update gets a new
registration before the game reads the old one. A rebuild takes under a
second. A registration built by hand (`mjolnir level register`, no record)
is left alone until the launcher has a map to register.

Map folders the launcher writes carry a `.mjolnirhub` marker. It removes
only those. Uninstalling UE4SS from the launcher also removes the
registration container it built.

### Dependencies

Installing a map installs what it depends on first. Its manifest's `deps`
come from the hub (the CE runtime pack; its newest release, as the version
range is not enforced yet). The code mods are implied by type `map`:
MJOLNIRCore, MJOLNIRLevelLoader, MJOLNIRLobby and MJOLNIRHud. Each is
installed when missing, updated when the launcher installed it and nobody
edited it, and switched on in `mods.txt`. A map whose code another
installed map holds is refused.

**Install multiplayer** (the launcher's Multiplayer page,
`hub::install_multiplayer`) runs this for every official map (`GET
/maps?official=1`), then materializes and registers once. Maps already at
their newest release are skipped, so running it again is an update.

## Publishing

### Our maps

```bash
tools/level/convert_ce_map.sh maps/bloodgulch.map BGL out/bgl
mjolnir map pack out/bgl --code BGL --version 1.0.0 --sign
```

- `map pack` collects the conversion's containers (`*-<CODE>_P`), its level
  file and its registration record into the archive, and writes the
  manifest. `--sign` signs it with this machine's device key (the tag
  editor's, under DPAPI), which the hub requires.
- The tag editor publishes it, as it publishes content mods: it signs the
  archive with the publisher's device key, then creates or updates the hub
  mod and uploads the release (`POST /mods`, `POST /mods/{slug}/releases`,
  `PUT /releases/{id}/archive`, `POST /releases/{id}/complete`).
- CI cannot bake, since it has no copy of the game, so maps are published
  from a maintainer's machine.

### Players' maps

Players publish the same way. Until the Rust cook lands, they need the
Unreal Editor and the MJOLNIRMaterials project, which in practice means us.

**Review.** A `map` release does not go live on a passing scan. It waits in
a review queue (`pending_review`) until a moderator approves it, because a
map carries game-derived bytes and names game types the loader will run.
Content releases keep auto-publishing.

## Hub changes

- `mods.type` accepts `map`; `POST /mods` takes it from the request.
- The scanner, for type `map`:
  - allows `map/level.json` and `map/registration.json`;
  - validates both JSON files against their schemas;
  - requires the `map` block, and rejects a `code` another mod already holds;
  - raises the size limit to 128 MiB (a map's containers are 7 to 8 MB, its
    cooked textures about 15 MB, and loose textures would be much larger).
- The release status gains `pending_review`; moderators approve or reject.
- `deps` are recorded in `release_deps` and returned with the release.

## Phases

1. **Map data outside the loader.** The loader and the lobby read
   `ue4ss/MJOLNIRMaps`; `mjolnir level register` builds the registration
   container and `maps.json` from the records there.
2. **Map packs.** `mjolnir map pack`; the tag editor's map publishing; the
   hub's `map` type, scanner rules and review queue.
3. **The launcher (done).** It installs maps, resolves dependencies, and
   builds the registration container on every change.
4. **The CE runtime pack, and our maps.** The shared containers move into the
   runtime pack, and each map's textures and sounds cook into a chunk of its
   own. Then we publish Blood Gulch, Gephyrophobia and the rest of the stock
   maps.
5. **The Rust cook.** Textures and sounds are written as cooked packages by
   rewriting shipped ones, as meshes already are
   ([ue_mesh_write.md](ue_mesh_write.md)). `mjolnir map build <ce.map>` then
   converts a map end to end with no Unreal Editor, and players can publish
   their own.
6. **Later.** Custom game types per map (reviewed `.mglo` in a map pack),
   map previews (`map/preview.png`) in the menu and on the hub, and
   collections ("CE classics").

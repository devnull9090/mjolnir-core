# Distributing converted maps

**Status:** 2026-10-21. Format v1 is proven with Blood Gulch: a pack built by
`mjolnir map pack`, installed as the launcher will install it and registered
by `mjolnir level register`, plays CTF. Phases 1 to 4 are done, but for the
tag editor's map publishing: the hub takes map packs with a review queue, the
launcher installs them with their dependencies and registers them
(`apps/launcher/src-tauri/src/maps.rs`), and the 19 classic maps and the CE
runtime pack are published, the remastered maps as 2.x releases of the same
listings. The tag editor's map publishing and the Rust cook (Phase 5)
remain: see [Phases](#phases).

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
| A map, e.g. `ce-blood-gulch` | hub `content`, with a map listing | map author | the map's containers, level file, registration record |
| `mjolnir-ce-runtime` | hub `content` | us | everything every converted map shares |
| MJOLNIRLevelLoader, MJOLNIRLobby | code mods | signed CI | the loader, the multiplayer menu, the game types (`.mglo`) |

### A map pack

A `.mjolnir` archive ([mjolnir_format.md](mjolnir_format.md)) of type `map`:

```
mjolnir.json                  manifest: type "map", plus the map block below
signature.json                added by `mjolnir map pack --sign` (below)
content/
  pakchunk997-MJOLNIRMAP-<CODE>_P.utoc    the scenario, its BSP, and the map's own world
  pakchunk997-MJOLNIRMAP-<CODE>_P.ucas
  pakchunk986-MJOLNIRMESH-<CODE>_P.utoc   the terrain mesh
  pakchunk986-MJOLNIRMESH-<CODE>_P.ucas
  pakchunk985-MJOLNIRCOOK-<CODE>_P.utoc   the map's cooked CE textures, lightmaps and
  pakchunk985-MJOLNIRCOOK-<CODE>_P.ucas   ambient sounds
  pakchunk<N>-MJOLNIRLAND-<CODE>_P.utoc   a remastered map's landscape world; it has a
  pakchunk<N>-MJOLNIRLAND-<CODE>_P.ucas   shader library, so it keeps its chunk number
map/
  level.json                  the level file the loader reads
  registration.json           the bake's registration record (below)
  bots.json                   where the bot squads stand, for MJOLNIRHud (a map with bots; docs/bots.md)
  <foliage file>              the foliage placements the level file names
  decals/*.png                its decals' textures
docs/README.md                optional
```

Format rules (version 1):

- Every package a map adds lives under `/Game/MJOLNIR/Maps/<CODE>/`, so two
  maps never claim the same package. The level file names only `/Game`
  paths: either the map's own, or the runtime pack's.
- A map cooks into a chunk of its own, `10000 + int(CODE, 36)` (Blood Gulch,
  `BGL`, is 24853). A `PrimaryAssetLabel` at the map's root sets it, so the
  map's cook never mixes with the runtime pack's chunk 988.
- No `.mglo` and no code. The only loose files are the level's own data
  under `map/`, which the mods read beside the level file: the foliage file
  the level names (a remastered map's `foliage.bin`), its decals' textures,
  and a map with bots' `bots.json` (`mjolnir map pack` takes it from the
  bake's `<CODE>.bots.json`). A map's preview is its hub listing's cover
  image, not a file in the pack.

The manifest's map block:

```json
{
  "schema_version": 1,
  "name": "Blood Gulch",
  "version": "1.0.0",
  "type": "map",
  "map": {
    "code": "BGL",
    "title": "Blood Gulch",
    "modes": ["slayer", "ctf"],
    "size": "large",
    "players": { "min": 4, "max": 16 },
    "vehicles": true,
    "game": "halo1"
  },
  "compat": { "min_build": "2026.06.26.1097863.1" },
  "deps": [{ "slug": "mjolnir-ce-runtime", "range": "^1.0.0" }]
}
```

- `code` is the three-character scenario codename. It is unique across the
  hub, which rejects a second map claiming a code someone else's map holds.
- `modes` lists the game types the multiplayer menu offers. Each one must be
  a variant the loader ships (`slayer`, `ctf`, ...).
- `size`, `players`, `vehicles`, `origin` and `game` are optional catalog metadata,
  what players filter the hub's map list by ([below](#the-catalog)). A
  release that leaves one out keeps the value the listing already has.
  `origin` is `custom_edition` or `original`; `classic` is set by
  moderators only. `game` is the game the map comes from, `halo1` (Halo CE)
  or `halo2` (Halo 2). Field rules are in [mjolnir_format.md](mjolnir_format.md#map-archives).
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
converted maps share. `tools/level/build_ce_runtime.sh` builds most of it:

| Container | Holds |
|---|---|
| `pakchunk988-MJOLNIRMAT-Windows` | the CE material masters (`/Game/MJOLNIR/CE/M_CE_*`) and their shader library; the CTF flag's textures (`/Game/MJOLNIR/CE/CTF`); the announcer and event sounds (`/Game/MJOLNIR/Sounds/Events`) |
| `pakchunk990-MJOLNIRCTFMESH_P` | the CE flag mesh (`/Game/MJOLNIR/CTF/SM_CE_Flag`) |
| `pakchunk990-MJOLNIRFLAG_P`, `-FLAGB_P`, `-STAND_P`, `-MOTL_P` | the red and blue CTF flag weapons (model variants `default` and `blue`, which the loader colours them by), their stand, and the object-type-list override that adds them as entries 18 and 20 |
| `pakchunk994-MJOLNIRSPAWN_P`, `993-MJOLNIRTELES_P`, `992-MJOLNIRTELER_P`, `991-MJOLNIRTELE2_P` | the spawn point and the teleporter sender, receiver and 2-way |
| `pakchunk990-MJOLNIRHPACK_P`, `-HPSPOT_P`, `-HPMESH_P` | the health pack, its spawn spot and its mesh |
| `pakchunk990-MJOLNIRSPARTAN_P` | the Spartan model with its body material on the body damage section (shipped on the head section, every bullet hit was a headshot) |
| `pakchunk990-MJOLNIRFLUX_P` | Fluid Flux's infinite sea (`NS_InfiniteSurfaceMesh`) with fixed bounds 10 km tall: the shipped ones are 50 m round Z 0, and a sea far below it (Yoyorast's, -256 m) was culled whole when the top of the view was level. Byte offsets, so it is rebuilt for every game update |
| `pakchunk984-MJOLNIRUI-Windows` | the multiplayer screens and HUD widgets ([custom_ui.md](custom_ui.md)) |
| `pakchunk981-MJOLNIRH2-Windows` | the Halo 2 masters (`/Game/MJOLNIR/H2`, `Scripts/build_h2_materials.py`): `M_H2_PlasmaAlpha`, which converted Halo 2 maps' plasma draws with ([h2_map_conversion.md](h2_map_conversion.md)) |
| `pakchunk985-MJOLNIRMENU_P` | the main menu with its own MULTIPLAYER button ([multiplayer_menu.md](multiplayer_menu.md)). It replaces the shipped menu, so it is rebuilt for every game update |
| `pakchunk983-MJOLNIRCETRIAL-Windows` | the trial masters the remastered maps draw with (`/Game/MJOLNIR/CETrial`, `Scripts/build_ce_materials.py`) and their tessellated cliffs (`Scripts/build_ce_cliffs.py`). `tools/level/upgrade_ce_map.py` cooks it, not `build_ce_runtime.sh`, and looks it up among the installed runtime's containers |

`tools/level/pack_remastered.py` leaves the water masters (`M_CE_Ocean`,
chunk 982, `Scripts/build_ce_water.py`) out of the map packs: like the trial
masters, they go in the runtime pack.

A map's ambient sounds are not shared. They cook into the map's own chunk,
under `/Game/MJOLNIR/Maps/<CODE>/Sounds`, so a map ships only the sounds it
plays.

Its containers are content containers, so they install like any content
mod. Its version moves when a shared piece changes; maps depend on a
compatible range. `mjolnir map runtime <out dir> --version X --sign`
packages the builder's output as the `mjolnir-ce-runtime` content mod.

The CTF variant the loader ships names the object types it creates, and
the simulation wipes a variant naming one the installed object type list
lacks (`0x409c40` -> `0x40a310`): CTF then has no rules at all. So the
runtime release that adds `-FLAGB_P` and the list's entry 20 goes out
before, or with, the mods release whose `ctf.mglo` creates the blue flag
(type 20). The lobby offers CTF only when the blue flag's container is
installed, and `mjolnir megalo write --mode ctf --single-flag` still
writes the one-type script for a list without entry 20
([game_modes.md](game_modes.md), 2.2).

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
come from the hub (the CE runtime pack, at its newest release). Only a
range's floor is enforced: since launcher 0.14.0 a dependency that is
installed but older than the floor (the `1.8.0` of a `^1.8.0`) is updated
first. The code mods are implied by type `map`:
MJOLNIRCore, MJOLNIRLevelLoader, MJOLNIRLobby and MJOLNIRHud. Each is
installed when missing, updated when the launcher installed it and nobody
edited it, and switched on in `mods.txt`. A map whose code another
installed map holds is refused.

**Install multiplayer** (the launcher's Multiplayer page,
`hub::install_multiplayer`) runs this for every official map (`GET
/maps?official=1`), then materializes and registers once. Maps already at
their newest release are skipped, so running it again is an update. Since
launcher 0.14.1 a map whose cache lacks a file its level names (its foliage
file, `decals/`) is fetched again rather than skipped.

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

**Update 2026-10-21:** the tag editor still publishes only its own project
(`project_publish`), and no tool in this repository uploads a map pack or
uses the hub's upload in parts ([below](#on-the-hub)). The remastered maps
are staged and packed by `tools/level/pack_remastered.py <CODES> --version
2.x.y --runtime <range> --sign`, which takes each map's cooked textures from
its installed hub release and hands the folder to `mjolnir map pack`.

### Players' maps

Players publish the same way. Until the Rust cook lands, they need the
Unreal Editor and the MJOLNIRMaterials project, which in practice means us.

**Review.** A map release from a new author does not go live on a passing
scan. The release stays `pending` with a row in `release_reviews` until a
moderator approves it (`/moderation/releases`), because a map carries
game-derived bytes and names game types the loader will run. Moderators and
authors at trust level 2 or higher skip the queue. Content releases keep
auto-publishing.

## On the hub

A map is a `content` mod. `mods.type` is a trust tier and stays `content`;
what makes a mod a map is its row in `map_listings` (migration 0012), keyed
by the mod and holding the code, title, game types, whether it is an
official classic, and the catalog metadata (migration 0017). `GET
/mods/{slug}` reports a map pack as `type: "map"` with its `map_code`.

- The scanner, for a manifest of type `map`:
  - requires the `map` block, and only a map archive may carry one;
  - requires `map/level.json` and `map/registration.json`, as valid JSON;
  - warns about containers not named for the map (`-<CODE>_P`);
  - rejects a `code` another mod already holds (`map_code_taken`).
- The archive limits are those of any content release. One request
  (`PUT /releases/{id}/archive`) takes up to 90 MiB, under Cloudflare's
  100 MB request body. A bigger archive, up to 400 MiB, goes up in parts:
  `POST /releases/{id}/archive/multipart`, parts of 5 to 64 MiB, then
  `.../multipart/{upload_id}/complete` joins them. The release's
  `POST /releases/{id}/complete` then scans the stored archive from R2 as a
  stream. A remastered map with its foliage runs past one request
  (Timberland 2.1.0 is 117 MiB).
- A passing map release writes its `map_listings` row; a held one
  ([review](#players-maps)) writes it too, but the listing stays out of
  the catalog until the mod is published.
- `deps` are recorded in `release_deps`.

### The catalog

`GET /api/v1/maps` lists published maps with their newest release, cover
image, and metadata:

| Field | Values |
|---|---|
| `size` | `small`, `medium`, `large`, or null |
| `players_min`, `players_max` | 1 to 16, or null |
| `vehicles` | true, false, or null |
| `origin` | `classic` (the converted stock maps), `custom_edition`, `original`, or null |
| `game` | `halo1` (Halo CE), `halo2` (Halo 2), or null |

Migration 0017 fills these for the 19 Halo CE classics, and migration 0023
sets `game` to `halo1` on every map published before it. Authors set them in the
manifest, and the mod's owner, its authors and moderators change them with
`PATCH /api/v1/maps/{code}` (only moderators may set or change `classic`).

With no parameters, `/maps` returns every map (up to 500), from every
game, in one list: the official classics first, then by title. The game's
map list relies on that form, so filters and paging are opt-in. The
launcher's **Install multiplayer** asks for `/maps?official=1&game=halo1`,
the official Halo CE maps, and its optional **Install Halo 2 maps** for
`/maps?official=1&game=halo2`. An older launcher asks for
`/maps?official=1`, which lists the official maps of both games.

| Parameter | Effect |
|---|---|
| `official` | `1` official maps only, `0` community maps only |
| `mode` | maps offering this game type |
| `q` | title, code or summary contains this (up to 80 characters) |
| `size`, `vehicles`, `origin`, `game` | exact match; a map that never declared the field is left out |
| `players` | maps whose player range includes this count; a map with no range is kept |
| `sort` | `newest`, `downloads`, `rating` or `title`; absent keeps official first, then title |
| `limit`, `cursor` | page size 1 to 100, and the `next_cursor` of the previous page |

The response is `{ maps, next_cursor }`. `next_cursor` is null on the last
page. The website's `/maps` page is built on the same query. `GET /mods`
takes `map=0` to leave map packs out (the website's `/mods` page does) and
`map=1` to list only them; every mod carries `cover_url` and `map_code` for
its card.

### Launcher links

The website hands off to the desktop launcher through the `mjolnir://`
scheme, which launcher 0.13.0 and newer register:

| Link | Opens |
|---|---|
| `mjolnir://map/<CODE>` | the map, ready to install (map cards and map pages) |
| `mjolnir://mod/<slug>` | a mod's page in the launcher (mod pages) |
| `mjolnir://join/<lobby id>` | joins a listed game (`/games`, and the live strip on `/matches`) |

## Phases

1. **Map data outside the loader.** The loader and the lobby read
   `ue4ss/MJOLNIRMaps`; `mjolnir level register` builds the registration
   container and `maps.json` from the records there.
2. **Map packs.** `mjolnir map pack`; the tag editor's map publishing; the
   hub's map listings, scanner rules and review queue.
3. **The launcher (done).** It installs maps, resolves dependencies, and
   builds the registration container on every change.
4. **The CE runtime pack, and our maps (done).** The shared containers move into the
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
   collections ("CE classics"). Map previews landed another way: the game
   and the launcher show each map's hub cover image (`cover_url`; PR #165
   and #166), and nothing reads a `map/preview.png`.

# Container numbers and load order

Status: the engine behaviour proven in game on 2026-11-11 (PC 1, Steam CU4);
rollout steps 1 to 4 built in the launcher the same day (see *What was built*).
Steps 5 and 6 and the shared-library move remain (see *Remaining*).

## The problem

A container's file name starts `pakchunk<N>`. Today that one number does three
jobs:

1. **Shader library name.** The engine opens a mounted pak's shader library
   by the number in the file name: `pakchunk978…` opens
   `Meteorite_Chunk978`. A container with a library has to keep the number
   it was cooked with.
2. **Load order.** The launcher names hub containers `pakchunk9NN`, with
   `NN` the mod's place in the profile's load order, on the assumption that
   a higher number wins.
3. **Ownership.** The launcher treats `pakchunk9NN-MJOLNIR…` as ours and
   sets every other non-game container aside as an unsupported mod.

That gives every author, every tool and every installed mod one shared space
of 100 numbers:

- 966 to 999 are taken by our own shipped containers, and 969 to 979 by the
  eleven CE remasters. There is no number left for a twelfth.
- Hub load-order numbers start at 900 and PC 1 is at 965. The next installs
  reuse numbers our shipped libraries own.
- `order_number` clamps at 999, so every mod past the hundredth gets the same
  number.
- Two authors who cook a library under the same number cannot be installed
  together, and nothing tells them which numbers are free.

## What the engine actually does

Read from UE 5.5 source, then checked in game.

| Fact | Source | In game |
| --- | --- | --- |
| The number after `pakchunk` can have any number of digits. | `GenericPlatformMisc.cpp` `GetPakchunkIndexFromPakFile` | A container named `pakchunk20001…` mounts and its library opens. |
| A library's chunk ID is CityHash64 of lower-cased UTF-16 `<Project>_Chunk<N>-<format>`. Shader code chunks are keyed by content hash and do not depend on `N`. | `ShaderCodeArchive.cpp` `GetShaderCodeArchiveChunkId` | The computed ID matches the library chunk in all eleven remaster containers (format `PCD3D_SM6-PCD3D_SM6`). |
| So a library can be renamed to another number by rewriting one chunk ID in the `.utoc`. The `.ucas` is untouched. | n/a | TST's library renamed 968 → 20001 and mounted as `pakchunk20001…`: the map draws fully. The same file mounted as `pakchunk20002…` draws the default checker material on the same building. Blood Gulch's library cannot show this: its shader maps are in other installed libraries too. |
| Load priority is the folder's base order plus `100 × (v + 1)` for a name ending `_<v>_P` (plain `_P` counts as `v = 0`). The same value orders the IoStore containers. | `IPlatformFilePak.cpp` `FPakPlatformFile::Mount` | Two containers holding the same map: the one with the higher suffix loads, whichever has the higher chunk number: `_9_P` over `_P` both ways round, and `_3000_P` over `_2000_P` with the loser being the name that wins a plain tie. |
| With equal priority, the container mounted last wins, and files mount in reverse name order. So the name that sorts **lower** wins. | `IoDispatcherFileBackend.cpp` `FFileIoStore::Mount` | `pakchunk940-…_P` beat `pakchunk997-…_P` (twice), and the same container renamed `pakchunk900-…_P` beat `pakchunk940-…_P`. |
| A failed library open is retried on the next mount with that number. | `ShaderCodeLibrary.cpp` `OnPakFileMounted` | Not tested. |

The last-but-one row means the launcher's "higher number wins" assumption is
backwards. Today the mod listed **first** in a profile wins a conflict, and
any hub container beats our `99x` overrides on a shared chunk. This matches
the 2026-11-06 finding that a hub copy at 920 beat a local 996.

The launcher already uses the suffix once: a live update is written as
`…_<n>_P` beside the container the game holds open (`patch_name` in hub.rs).

The in-game check for "which copy loaded" scans the game's memory for byte
windows unique to each container's data file; it read 12 of 12 for the winner
and 0 of 12 for the loser in every run.

## Design

Split the three jobs.

### 1. Load order is the `_<v>_P` suffix

The launcher names each hub container `…_<v>_P`, where `v` comes from the
profile's load order: later in the list, higher `v`. This is the engine's own
priority field and it does not depend on name sorting. Thousands of mods fit.

Our shipped overrides (`990` to `999`: registration, flags, spawns,
teleporters) were to get suffixes chosen to reproduce what wins today. What
wins today was measured (next section) before choosing.

### 2. The chunk number is assigned on the player's machine

When the launcher writes a profile into Paks it gives every container a
number of its own from a wide local range (for example 10000 upward), and
for a container with a shader library rewrites the library's chunk ID to
match (`ue_iostore::shader_library::renumber`). The number an author cooked
with stops mattering once the container is installed:

- No registry, no reserved bands for authors, no coordination between games.
  Two mods cooked under the same number install side by side.
- A container without a library can share one number; it has nothing to open.
- Uniqueness only has to hold among the containers mounted on one machine,
  and the launcher sees all of them.

Our own runtime containers that Lua or tools name by number (980, 984, 985,
988 and the rest) keep their numbers. Those are a short fixed list in the
repo, checked by a test for duplicates.

### 3. Ownership is the `MJOLNIR` marker

`is_mjolnir_container` accepts any chunk number, and keeps requiring the
`-MJOLNIR` marker.

### 4. Remasters stop shipping duplicate libraries

Measured on PC 1: the eleven remaster libraries (969 to 979) hold two shader
maps between them. One is in all eleven, the other in five. Neither is in a
runtime container today. Shipping those two once in the runtime pack would
leave a remaster whose materials add nothing new with no library and no
number at all. Whether a Halo 2 remaster cooks to the same two maps has not
been checked. `shader_lib_overlap` reports this for any Paks folder.

## What wins today, measured

Measured 2026-11-11 on PC 1's active profile (55 entries, 582 cached
containers) plus every loose `MJOLNIR` container in Paks: every chunk two
containers share, with the bytes compared, and the winner by the rule above
(equal `_P` priority, lower name wins).

Where the shipped overrides live. On a player's machine the flag, spawn,
teleporter, bot and menu containers (`990` to `995`, `985`) are not loose:
they are containers of the `mjolnir-ce-runtime` hub mod, written into Paks
as `pakchunk900-MJOLNIRHUB-mjolnir-ce-runtime-<j>_P` (libraries at their
cooked 966, 981, 982, 983, 988). The only loose `99x` container the launcher
writes is the registration, `pakchunk996-MJOLNIRREG_P` (`maps.rs`). The other
`99x` writers (`build_ce_runtime.sh`, `convert_ce_map.sh`, `upgrade_ce_map.py`
local installs, `build_spawn_point.sh`, `build_ctf_flag.sh`, `blam-cli` `ue`
and `level` commands) install loose files on developer machines only.

| Shared chunks | Between | Bytes | Wins today | Why |
| --- | --- | --- | --- | --- |
| 11 packages (`M_CE_Ocean`, `M_CE_CliffTess`, `M_CE_Environment`, 8 textures) | runtime `WATER`/`CETRIAL`/`MAT` (982/983/988) and TST `COOK` (968) | differ: a 16-byte GUID, and in the materials a 20-byte shader-map hash | **TST** (the map) | 968 sorts below 982 |
| 128 packages (`MI_LTT_swap_*`) | TST `LAND` (969, library) and TST `ROCK` (no library) | differ: 598-byte stubs in LAND, full native clones in ROCK | **ROCK** | ROCK took load-order number 923, below 969 |
| 5 packages | TST `COOK` and TST `LAND` | identical | n/a | |
| none | `MJOLNIRREG` and any hub container | n/a | n/a | |
| any | a hub container and a loose `99x` `_P` override (developer install) | n/a | **hub** | 9NN below 99x; the 2026-11-06 "hub copy at 920 beat a local 996" |
| 1 package + library | runtime `H2` (981, fixed) and a loose `pakchunk981-MJOLNIRH2TEST_P` (a hand-placed test build on PC 1) | differ | **loose** | same number, and `MJOLNIRH2…` sorts below `MJOLNIRHUB…` |

Everything else that overlaps is between a hub copy and a loose copy of the
same container that another session placed by hand on PC 1, where the hub
copy wins today.

So, reproduced on purpose:

- **Later profile entry wins.** The runtime is entry 0, maps come after it,
  so the map's copies of the runtime materials keep winning. This is also
  what the profile list in the UI says ("later entries win", "the lower
  entry wins them") and what `Profile`'s doc comment said; the launcher's
  9NN numbers did the reverse for containers without a library.
- **Within one entry, the later container wins** (TST: `ROCK`, index 2,
  over `LAND`, index 1).
- **Every hub container sits above loose `_P` containers**: `v` starts at
  1000, and a loose `_P` is `v = 0`. The registration never overlaps a hub
  container, so it stays loose at `v = 0`. This reproduces every hub-vs-loose
  case but one: a loose test build that shares a *fixed* number with a hub
  container and has a marker sorting below `MJOLNIRHUB` (PC 1's
  `pakchunk981-MJOLNIRH2TEST_P`) beat the hub copy by name, and now loses.
  Plain `_P` keeps losing on purpose. Local development wins by being
  installed as a local build (next section), and anything still loose that
  loses is named by `mjolnir dev list` and in the launcher.

## Local builds take precedence over hub content

Decided 2026-11-11: local development must have a good way to win over
published hub content. A local build is
`pakchunk<N>-MJOLNIRDEV-<name>_<v>_P`:

| | Load-order suffix `v` | Chunk number `N` |
| --- | --- | --- |
| Loose `_P` (registration, hand copies) | 0 | as named |
| Hub containers (launcher) | 1,000 to 999,996, plus 3 for live updates | 10,000 to 4,999,999 |
| Local builds (`mjolnir dev install`) | 1,000,000 to 1,999,999, each install above the last | 5,000,000 to 5,999,999 |

The bands live in one place, `ue_iostore::paks`, with compile-time checks
that they do not overlap and that `100 × (v + 1)` stays inside the engine's
int32 priority. The launcher's `chunk_numbers` takes its hub values from it.

- `mjolnir dev install <container> --name <name>` writes the build above
  every hub container and every earlier build, replacing an earlier build of
  the same name (it keeps that build's number). A shader library is renamed
  to the build's own number, so it opens beside the hub copy's. The name is
  letters, digits and dashes; one carrying `MJOLNIRHUB` is refused (the
  launcher deletes those). With no `--name` the container's own name after
  its number is used, refused when it says nothing about which map
  (`pakchunk978-MJOLNIRLAND-Windows`).
- `mjolnir dev remove <name>`, `mjolnir dev list [--json]`. Install and
  remove change nothing while the game holds a file they would replace.
- `dev install` and `dev list` print every loose MJOLNIR container that
  loses chunks with different bytes to a hub container or local build
  (`paks::shadowed_loose`; byte-identical chunks are counted apart, shader
  code and container headers are left out, a library under the same number
  counts). This is the silent failure seen twice (a hub copy at 920 over a
  local 996, and H2TEST).
- The launcher never sets a local build aside, never renames or deletes
  one, and lists them under *Local builds* in the Library's content-mod
  panel with a Remove button, beside the same "loses to" warnings
  (`local_builds.rs`, `LocalBuildsPanel.tsx`).
- `tools/level/dev_paks.py` is the Python side: the install and remove
  commands, and the glob for the launcher's copy of a hub container under
  either name. `upgrade_ce_map.py`'s install stages use it: a local install
  of a new map, `--install` over an existing hub map (map, mesh and
  landscape), and the shared trial and water masters all go in as local
  builds instead of being copied over the hub's files.
  `tst_preview_swap.py` installs the staged TST containers as builds named
  `TST-PREVIEW-*`, swaps and backs up the map's data files as before, and
  restore removes the builds.
- A local build shadows the hub copy; it cannot delete it. A package the hub
  copy has and the build does not still loads from the hub. Overwriting the
  hub's files used to drop such packages; that no longer works anyway, since
  the launcher renames hub files and rewrites their libraries.

Checked in game 2026-11-11 (PC 1, Steam), with the hub profile written under
the new names and the same GUID memory scan as above (11 packages the
runtime and TST both carry):

| Paks | Copy that loaded |
| --- | --- |
| hub only | TST (later entry), 8 of 11, runtime 0 |
| + runtime's WATER, CETRIAL, MAT as local builds at 1,000,000 to 1,000,002 | runtime, 8 of 11, TST 0: the bottom of the band beats the hub |
| + a placeholder at 1,999,998, then TST's COOK as a local build, which took 1,999,999 | TST, 8 of 11, runtime 0: the top beats the bottom, no overflow |
| TST's hub entry off, its five containers as local builds (libraries 968 → 5,000,000 and 969 → 5,000,001) | TST loads and draws textured; COOK's 13 shader maps are in no other library |

`mjolnir dev list` on that Paks named PC 1's `pakchunk981-MJOLNIRH2TEST_P`
as losing to the runtime's 981 container, the case it exists for. The
launcher's panel was not looked at in the running app.

## What was built

`ue-iostore`: `pack::rekey` and `shader_library::{library_id, renumber}`,
with the examples `renumber_container`, `shader_lib_id`, `shader_lib_overlap`.

Launcher (`apps/launcher/src-tauri/src`):

- `unsupported.rs`: `is_mjolnir_container` accepts `pakchunk<any>-MJOLNIR…`.
- `chunk_numbers.rs`: the numbers. A container's *position* is its place in
  the active profile, counting every entry's containers in order, disabled
  entries included, so enabling a mod or installing one (appended) renames
  nothing already mounted.
  - Suffix `v = 1000 + 4 × position`, capped at 999,996, below the local
    builds' band. The gap of 4 holds three live updates.
  - Chunk number `N = 10000 + position`, capped below the local builds' numbers: every container its own number.
  - `config/fixed_chunks.json`: the containers that keep their cooked number
    because Lua, a tool or the launcher names them by it (966 KOTH, 980
    FORGEUI, 981 H2, 982 WATER, 983 CETRIAL, 984 UI, 985 MENU, 988 MAT, the
    990 to 995 runtime overrides, 996 REG). A test fails on a name listed
    twice, two libraries under one number, or a number in the local range.
- `hub.rs`: `mount_plan` names each container
  `pakchunk<N>-MJOLNIRHUB-<slug>-<j>_<v>_P`. A container with a shader
  library named for its cooked number gets its library renamed to `N` as it
  is written into Paks (`Mount::utoc`); one whose library is not named for
  the number in its own file name keeps that number, as before. The cache is
  never changed, so `verify_installed` and the quick verify (which hash the
  cache) are unaffected; `paks_gaps` checks presence and `paks_strays` names,
  neither size nor bytes.
- Live updates (`patch_name`): a container the game holds open is replaced by
  `…_<v + n>_P`, n from 1, above the old one and below the next container. A
  library written while the game runs is refused when another mod's
  container in Paks already has its number (`forge_shaders::library_free`).
- `forge_shaders.rs`: the Forge material check runs on the numbers assigned
  in Paks. Two packs cooked under the same number now install side by side;
  the 900 to 999 requirement is gone.

### Checked in game, 2026-11-11 (PC 1, Steam)

The active profile (53 entries; `h2-elongation` and `h2-turf` left out
because another session had their containers aside) was written into Paks by
this code (`mount_plan` plus `Mount::write`, the copy loop `materialize`
runs), with the game's own and hand-placed containers left in place:

- **TST draws textured** with its two libraries renamed 968 → 10158 and
  969 → 10159.
- **All 48 hub maps load** (hosted in turn with `mjolnir_auto host <CODE>
  slayer private`, each reaching "world <CODE> has level"), including the
  remasters whose libraries moved from 970–979 to 100xx and the Forge maps
  with `foundry-wide`'s material library at 10263. The remasters' and
  TST's screenshots show no default checker material. The Forge maps'
  pieces are plain grey either way, so the screenshots do not show whether
  `foundry-wide`'s one shader map found in no other library (per
  `shader_lib_overlap` on the cache) is in use; its `.utoc` renumbers
  cleanly (`a_cooked_library_renumbers`).
- **A conflict resolves by profile order, not by name.** The 11 packages
  shared by the runtime and TST (above) carry different GUIDs, so a scan of
  the game's memory tells which copy loaded. In the profile's own order
  (runtime first) TST's copies loaded: 8 of 11 of TST's GUIDs resident, none
  of the runtime's. With the runtime moved after TST it reversed: 8 of 11 of
  the runtime's, none of TST's. In that second layout TST's names
  (`pakchunk10120…`) sort below the runtime's (`pakchunk966…`), so name order
  alone would have kept TST: the suffix decided.

Not checked in game: live updates (`patch_name`, `library_free`), the
registration rebuild path of a full `materialize` (`sync_maps`, unchanged by
this work), suffixes above about 3,300, and the Game Pass build.

## The launcher gate and release order

Decided 2026-11-11: content that only works with local chunk numbers must
not reach a player on an older launcher silently; they get "update your
launcher" instead.

What needs a newer launcher. A release carrying a shader library cooked
under a number outside 900 to 999 (launchers before local numbers set that
container aside as unsupported), or under the same number as another mod's
library (they open only one of the two). The hub measures this when it scans
a release and records it as the release's `requires` list, entry
`local-chunk-numbers`; authors do not declare it. A library number already
used by another mod's ungated release gates the newcomer, never the
original.

What each launcher does.

- **This launcher and later** send `User-Agent: MJOLNIR-Launcher/<version>`,
  `X-MJOLNIR-Launcher: <version>` and `X-MJOLNIR-Features:
  local-chunk-numbers` on every hub request (`hub.rs`, `launcher_headers`).
  A release whose `requires` names a feature the launcher lacks is never
  chosen, never offered as an update, and refused at install or enable with
  "needs a newer MJOLNIR launcher … Update the launcher, then try again"
  (`needs_newer_launcher`). The feature list is compiled in
  (`LAUNCHER_FEATURES`), as Forge packs' `requires` is.
- **Launchers up to 0.23.0** send no User-Agent and no headers, which is how
  the hub tells them from browsers. The hub leaves gated releases out of
  their release lists and map listings, so they install the newest release
  they can use. When a mod has nothing else, the newest gated release stays
  listed and `GET /releases/{id}` reports its status as a sentence telling
  them to update the launcher, which they show as "Release is …, not
  published"; the download itself is refused. Browsers and other clients
  with a User-Agent see everything as before.
- **Not covered.** A player on an old launcher who joins a host running a
  gated release by its exact id reads "That release is not published". The
  test for an old launcher is the missing User-Agent: anything else that
  calls the hub without one is treated the same way. Releases scanned
  before the hub change is deployed carry no `requires` until scanned again.

Release order, for content cooked under a new number (Halo 2, Reach and
later remasters, community maps with their own libraries):

1. Ship this launcher (`launcher-v*`) and let it be adopted. Which version
   number that is, is the release's call; nothing stores it.
2. Deploy the hub with the `requires` scan and filtering.
3. Only then publish such content. Content cooked under 900 to 999 with a
   number nobody else uses needs no gate and works on every launcher.

## Rollout

1. `ue-iostore`: `pack::rekey` and `shader_library::renumber` (written,
   proven in game). **Built.**
2. Launcher: accept any chunk number as ours. This has to reach players
   before any content uses a new name, because older launchers set unknown
   names aside. Gate new-style content on a minimum launcher version.
   **Built** (the gate is not: see *Remaining*).
3. Launcher: suffix-based load order, with the shipped-override table.
   Decide which way the profile list reads and say so in the UI, since the
   order players have today is the reverse of what was intended. **Built:**
   later wins, which the UI already said.
4. Launcher: local numbering with the library rewrite; `forge_shaders`'s
   duplicate check moves to after numbering. **Built.**
5. Tools that install containers by hand (`upgrade_ce_map.py`,
   `pack_local_map`, the CLI install path, live map mount in Lua) take their
   names from one shared helper.
6. New remasters (Halo 2 first) cook to any number; the installer renumbers.

## Remaining

- **Tools not moved to local builds.** `tools/level/ce_vehicle.py` and
  `ce_vehicle_name.py` copy any `pakchunk997-MJOLNIRMAP-*_P.pak` from Paks as
  a stub, which a machine with only hub maps does not have. The build
  scripts that copy runtime overrides in by hand (`build_ce_runtime.sh`,
  `convert_ce_map.sh`, `build_spawn_point.sh`, `build_ctf_flag.sh`, the
  `blam-cli` `ue` and `level` writers) still write plain `_P` names, which
  lose to the hub's runtime; `mjolnir dev list` names them.
  `pack_local_map.py` only packages archives and needed nothing. Tools that
  read Paks through `ue_iostore::load_all` do not apply mount priority when
  two containers hold one package. A comment in
  `mods/MJOLNIRLobby/Scripts/main.lua` still describes the old `pakchunk9NN`
  names (Lua finds hub containers by their cached names in
  `hub_state.json`, so its behaviour does not change).
- **Minimum launcher version gate** for content cooked under numbers outside
  9NN (older launchers set those aside as unsupported).
- **The two shared landscape shader maps** (design step 4): move them into
  the runtime pack so remasters ship no library.
- **Hub server**: nothing changed; the conflict preview (`/conflicts/check`)
  returns pairs and the UI already reads "the lower entry wins".
- Fixed numbers match by cached container name in any mod, so a community
  pack shipping a container named `pakchunk988-MJOLNIRMAT-…` would keep 988
  and share our library's number. Restrict the match to the runtime mod's
  slug if that matters.
- `install_stock_modes.ps1` matches `^pakchunk\d+(-MJOLNIRHUB-.+)$` and keeps
  working; comments in `teams.lua` and the Lobby's `main.lua` still describe
  `pakchunk9NN` names.
- A live update that changes how many containers a mod has shifts the
  positions of every later mod. Already mounted containers keep their
  priority until the next launch, which renames them; a library that would
  land on a number another mod has open is refused (`library_free`).

## Open

- Whether live-mounted containers (maps mounted without a restart) take the
  same suffix priority. Not tested.
- The Game Pass build shares the engine but was not tested here.
- Upper bound on open shader libraries: each installed library costs memory
  at launch whether or not its map is played. Step 4 of the design removes
  most of them; measure before thousands are installed.

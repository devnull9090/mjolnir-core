# Forge layout sharing

**Status:** design, 2026-11-03. Nothing here is built unless a line says so.
Phase 0 (checking layout files) is built and tested in game on branch
`work/forge-mvar-bounds`.

Players build with Forge today, but a build stays on their PC: F5 keeps one
layout per map, and the only way to give one to someone is to copy two files
by hand. This document plans several named layouts per map, a lobby choice
of which one a match starts with, a hub listing that players publish to and
download from, and an in-game layouts menu.

## What exists

| Piece | Today | Where |
|---|---|---|
| Save, load, revert | F5, F6, F2 in a FORGE game only (the sandbox tick runs them) | `native/forge/mjolnir_forge.c` `layout_save` 1083, `layout_load` 1154, `layout_revert` 1175; `hooked_tick` 1999 |
| Files | `Mods\MJOLNIRForge\layouts\<CODE>.mvar` and `<CODE>.mvar.packs`; the previous pair moves to `layouts\history\<CODE>-<time>-<serial>` | `derive_paths` 315, `layout_history_paths` 718; two-file commits in `layout_files.h` |
| Sidecar | `forge-packs 1`, then `flat⇥tag⇥slug⇥version⇥sha256` for each pack palette entry used | `layout_packs` 795; `pack_bindings.h` 148 |
| Match start | the host's DLL reads `<CODE>.mvar` at new-map (any game type) and adopts it; clients never read a file, the engine replicates the objects | `layout_new_map` 1197 |
| Pack check | same major, not older (the caret line); refused with a reason shown for 10 s | `forge_version_accepts` in `pack_bindings.h` 104; `Hud.layoutWarning` |
| Launcher | before a launch, installs the packs every top-level `layouts\*.mvar.packs` names; two sidecars pinning different lines of one pack fail the launch | `apps/launcher/src-tauri/src/hub.rs` `saved_layout_pins` 632 (`read_dir`, not recursive); `forge_packs.rs` `merge_layout_pin` 352 |
| Hub | no layout type. The manifest allows `content` and `map` only, the scanner refuses `.mvar` and any release without a container, and uploads must be signed | `hub/src/lib/api/manifest.ts` 28; `scan.ts` 39, 344, 424; `wrangler.jsonc` 42 |
| Game ↔ hub | the lobby DLL's WinHTTP worker sends JSON with the launcher's key; downloads only go to `MJOLNIRMaps\_covers`; installs run the launcher (`--install-map`) | `native/lobby/mjolnir_lobby.c` 4560, 4754; `mods/MJOLNIRLobby/Scripts/maplive.lua` |
| Credentials | the launcher's device key has `mods:read`, `ratings:write`, `comments:write`, `lobbies:write`; the tag editor pairs with `mods:write` and signs with a DPAPI Ed25519 key | `hub/src/lib/api/device.ts` 40; `apps/tag-editor/src-tauri/src/hub.rs` 113, `keystore.rs` |

## Phase 0: checking layout files (built)

A hub hands everyone who downloads a layout a file its author chose, so every
reader checks a layout before the game sees it:

- **Forge DLL** (built): `native/forge/layout_bounds.h` checks a layout's
  labels and label names, and Forge refuses a malformed file with the reason.
- **Hub and launcher** (planned): the validator below, on upload and on
  install.

## The validator

One Rust function, `blam_megalo::layout::validate(bytes) -> Result<Summary>`,
used by the hub (built to WebAssembly), the launcher and the tag editor
(native). A second implementation in TypeScript would be a second grammar to
keep in step.

It accepts a file when:

1. The envelope is the one Forge writes: `_blf` 1.2, one `mvar` 31.1 with a
   payload of at most 0x7000 bytes (the DLL's buffer), an optional `fpk1`
   1.0, `_eof`, then only zero padding.
2. The payload decodes completely with `crates/blam-megalo/grammar/megalo_cu4.json`,
   with fewer than 8 bits left over.
3. Content type 5 (map variant) and encoding version 31.
4. At most 256 labels, at most 0x1000 bytes of label names (the declared
   size, the compressed stream's prefix and the inflated bytes), and at
   most 256 quotas.
5. It encodes back to the same bytes, so nothing the grammar does not name
   travels in it.
6. Every placed object's palette index is inside the palette (to confirm
   against the decoder before relying on it).

`Summary` carries what the hub and launcher store: title, description, map
id, object count, labels, and the palette entries used. The sidecar is parsed
by the parser the launcher already has (`forge_packs::layout_pins`).

**WebAssembly on the hub works.** A spike on 2026-11-03 built `blam-megalo` for
`wasm32-unknown-unknown` (382 KB, grammar included) and imported the `.wasm`
from a route. OpenNext bundled it, `wrangler dev` ran it on workerd, and the
route returned the right label counts for a MJOLNIR save (0) and Reach's
Asylum (13), about 2 ms a file. A local Cloudflare build on Windows needs
`pnpm install --config.node-linker=hoisted`, because OpenNext's file copy
cannot create pnpm's symlinks without Developer Mode. CI builds on Linux and
is unaffected.

## Phase 1: named layouts

### Files

```
Mods\MJOLNIRForge\layouts\
  FRB.mvar, FRB.mvar.packs      active: what every match on FRB starts with (unchanged)
  FRB.active                    the library entry the active pair came from, if any
  history\...                   unchanged
  library\FRB\<id>\
    layout.mvar
    layout.mvar.packs
    layout.json                 title, description, created, updated, map version,
                                source (local, or hub slug + version + release id)
    preview.png                 optional
```

The active pair keeps its name, so everything that reads it today (match
start, F6, the launcher's pins, history) is unchanged. The launcher scans
`layouts\` without recursing, so library entries never take part in the
launch-time pins. A downloaded layout built against a newer pack line
cannot block a launch. An entry whose packs are missing or on another
line is refused when it is loaded, by the same caret check, with "restart
through the launcher".

### Operations

| Action | What happens |
|---|---|
| Save (F5) | as today; if `FRB.active` names an entry, the entry is updated too |
| Save as | F5, then the active pair is copied into a new entry; the id comes from the title plus a number, and the title can be changed later without moving files |
| Use | the active pair goes to history, the entry's pair becomes active, `FRB.active` names it; in a FORGE game the objects are replaced as F6 does |
| Original (F2) | as today; `FRB.active` is cleared |
| Rename, delete | `layout.json` only, or the entry's folder |

The DLL does the file work, because `layout_files.h` already commits two
files safely and never overwrites. Its exports take no arguments, so the
menu writes a request (`layouts\request.txt`: an operation, map code, entry
id and title, one per line) and calls a new `library` export. The DLL
answers in `layouts\library.txt`: one line per entry, with id, title,
objects, packs and when it was saved. Library requests run from `pump`
rather than the sandbox tick, so the lobby can use them outside a FORGE
game. Use, F5 and F6 still need the sandbox.

### The lobby choice

The map select shows **Layout: Original** and the map's library entries
when the chosen map has any. START GAME makes the choice active before
`startGame` writes `pending_variant.txt`, so the existing match-start path
does the rest. The lobby broadcast gains a seventh field, the layout's
title. Older clients read six fields by position and ignore it. The vote
after a match keeps each option's layout.

## Phase 2: the hub and the launcher

### Archive

```
mjolnir.json        type "layout", a `layout` block, deps
layout/layout.mvar
layout/layout.mvar.packs
layout/preview.png  (or .jpg / .webp, at most 1 MiB)
docs/README.md      optional
signature.json
```

`mjolnir.json`:

```json
{
  "schema_version": 1,
  "type": "layout",
  "name": "Crossline Towers",
  "version": "1.0.0",
  "summary": "Two towers over the vehicle lane.",
  "layout": { "map": "FRB", "objects": 312 },
  "deps": [
    { "slug": "crossline", "range": "^0.3.0" },
    { "slug": "foundry-wide", "range": "^0.2.0" }
  ]
}
```

The base map is the dependency whose map listing has the code in `layout.map`.
Every pack in the sidecar must be a dependency at the caret line it names.

### Hub

| Change | Where |
|---|---|
| Manifest | `type` gains `"layout"`; the `layout` block is required for it alone (`manifest.ts` 28, 74) |
| Scanner | for a layout only: allow the four `layout/` files and skip the container rule (`scan.ts` 39, 344, 424); run the validator; compare the manifest's map and object count with the file's; check the sidecar against `deps`; cap the archive at 2 MiB |
| Validator | `blam-megalo` built to `.wasm`, imported by `scan.ts` |
| Complete | category forced to `layouts`; deps into `release_deps`; a `layout_listings` row (`publish.ts` 693-738) |
| Schema | migration `0025_forge_layouts.sql`, additive: `layout_listings (mod_id PK, map_code, base_slug, title, objects, packs JSON, updated_at)` and an index on `map_code`. Apply it before the merge |
| API | `GET /maps/{code}/layouts` and `GET /layouts?map=&sort=`, for the website, the launcher and the game |
| Website | a Layouts section on a map's page (`hub/src/app/mods/[slug]/page.tsx`), Community layouts on `/forge`, and `layouts` in `/mods/new`'s categories. The manage page's single PUT already fits |

**Review hold: a decision for the owner.** A layout carries bytes that
the engine decodes, which is a map's risk rather than a texture's.

- **Hold new authors** (as maps do: trust level below 2 waits for a
  moderator). Safe whatever the validator misses. Moderators would see
  the scanner's summary. The catch: `trust_level` has no writer in the hub
  today, so every new author waits on a person.
- **Publish on a pass** (as content does). Faster for players. It rests
  entirely on the validator: the full decode, the caps and the
  re-encode. Reports and yanking stay available.

The validator design favours publishing on a pass. Holding new authors
for the first releases is the cautious start.

### Launcher

- `install_one_as` (`hub.rs` 1085) learns the manifest type `layout`. A
  layout's hub mod is a `content` mod, so the trust-tier check (1112)
  already passes. For a layout it skips the container rule (1320) and runs
  the same validator natively before writing anything.
- It writes `library\<CODE>\hub-<slug>\` with `layout.json` naming the
  release, and installs the map and packs through the usual deps.
- Uninstalling removes the entry. If that entry is active, the active
  pair stays and `FRB.active` is cleared, so a match is never left without
  its layout.
- Library entries get a best-effort pin pass. Their packs are installed
  when they don't conflict with the active layouts. A conflict is noted on
  the Updates screen rather than failing the launch.
- `--install-layout <slug> [--release <id>] --progress <file>`, gated by
  `layouts` in `launcher_features.txt`, as `--install-map` is. Nothing
  needs mounting. A pack the game has not loaded still needs a restart,
  which the menu says.
- `mjolnir://layout/<slug>` opens the layout's page in Browse Hub, as
  `mod/` and `map/` links do (`links.rs` 79).

## Phase 3: the in-game menu

`WBP_MJOLNIRForgeLayouts` is a cooked widget in the Forge UI container
(`pakchunk980-MJOLNIRFORGEUI`, `build_forge_hud` in
`unreal/MJOLNIRMaterials/Scripts/build_mjolnir_ui.py`), so it ships in a CE
runtime release.

- **Opening it:** in a FORGE game, from a FORGE LAYOUTS item in the pause
  menu (the HOST MENU pattern, `MJOLNIRLobby/Scripts/main.lua` 3969) and from
  a key still to be chosen. F7-F9 belong to MJOLNIRFlyCam.
- **The list:** this map's entries in ten authored rows that slide over the
  list, the palette's pattern. Each row shows title, objects, packs and
  date, and the active one is marked.
- **Buttons:** Load, Save as, Rename, Delete, Use for matches, Publish, Get
  more.
- **Names:** an `EditableTextBox`, focused the way chat focuses its input
  (`MJOLNIRHud/Scripts/chat.lua` 433). Forge ignores its own keys while it
  has focus (`typingInChat`).
- **Get more:** lists the hub's layouts for the map
  (`GET /maps/{code}/layouts` through `Games.call`) with their covers (the
  existing `FILE` download into `_covers`), and installs through
  `--install-layout`.

## Phase 4: publishing

The game can't publish on its own. It holds no key that can write, and the
lobby DLL sends only JSON.

1. **Publish** in the menu writes `layouts\publish_request.json` (map,
   entry) and starts the launcher through the lobby DLL's existing launcher
   action, with `--publish-layout <CODE>/<id>`, window shown.
2. The launcher shows a publish form: title, summary, version (the next
   patch for an update), the preview, and what the layout depends on.
   Nothing is sent until the player confirms.
3. It builds the archive and signs it with a launcher signing key. That key
   is DPAPI-protected Ed25519, as the tag editor's `keystore.rs`, and
   registered once through `POST /account/signing-keys`. Then it uploads
   with the existing four calls.
4. **A new scope, `layouts:write`**, offered when the launcher pairs and
   shown on the device approval page. `requireScoped` accepts it only for a
   mod whose category is `layouts`, and `/complete` refuses anything but a
   `layout` manifest for a key that has only this scope. Giving the
   launcher `mods:write` instead would let every paired launcher publish
   any mod.

Two existing gaps this depends on:

- `POST /account/signing-keys` only authenticates (`account.ts` 224),
  despite its comment. It should require `mods:write` or `layouts:write`.
- Nothing checks that a joiner has the packs the host's layout uses. The
  lobby broadcast should carry the active layout's pins, and a client
  missing a pack should be told before the match, as for a missing map.

The tag editor can already publish with `mods:write`. A Publish layout
button there is the quickest working path, and it belongs with the
editor's Forge mode.

## Order and testing

| Phase | Ships as | Test |
|---|---|---|
| 0 | MJOLNIRForge 0.4.1 (mods 0.43.1) | done in game, and in `native/forge/test_layout_bounds.c` |
| 1 | mods release (Forge, Lobby) | save as, use, rename, delete; START GAME with a chosen layout as Slayer and FORGE; F2 back to the original; the launcher still launches with conflicting library entries |
| 2 | hub deploy + migration, launcher release | validator tests on every MCC map variant, every MJOLNIR save and malformed files; scanner tests (`hub/scripts/test-scan.mts`); publish with a temporary key; a clean launcher profile installs a layout and its map and packs |
| 3 | CE runtime release (chunk 980) + mods | menu at 16:9 and 16:10; text entry beside chat; Get more installs without a restart when the packs are present |
| 4 | launcher + hub | publish from the game on a test account; refused for a key without the scope |

## Questions for the owner

1. Review hold for layouts from new authors, or publish on a pass?
2. Publishing from the game through the launcher (the new scope), or
   through the tag editor first?
3. The preview: should the launcher take a screenshot of the game window
   when the player publishes, or ask for an image?
4. Which key opens the layouts menu in a FORGE game?

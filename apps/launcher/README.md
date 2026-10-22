# MJOLNIR Launcher

Tauri 2 + React + TypeScript. Installs and manages mods for Halo Campaign Evolved.

```bash
pnpm install
pnpm tauri dev
```

## The three views

Each answers one question, and none answers two:

| View | Question | Contains |
| --- | --- | --- |
| **My Mods** | What is installed? | Content mods (hub) with their load order, and script mods (UE4SS) with their toggles |
| **Browse Hub** | What exists? | The community catalogue in three tabs (content mods, maps, and the signed code-mod set), with full mod pages |
| **Updates** | What is out of date? | Every source at once — launcher, core install, content mods, script mods, tools |

That split is deliberate. Installed mods used to appear under both My Mods
(UE4SS scripts) and the Hub tab (content mods), with neither mentioning the
other, and "update available" lived in four unrelated corners of the UI.

Multiplayer, Tools and Settings sit outside that loop. **Multiplayer** lists the
classic maps and has the one button that installs everything they need: every
official map pack, the CE runtime pack they share, and the code mods that put
MULTIPLAYER on the main menu (`hub::install_multiplayer`). Running it again
updates what moved on. Community maps install one at a time from Browse Hub's
Maps tab, or in game when a lobby needs one; a `mjolnir://join/<lobby>` link
opens this view to join. **Tools** installs companion apps such as the tag
editor. **Settings** holds the game location, the launch method, the UE4SS
console switch, install verification and the list of recent crashes.

The update manager (`src/updates/useUpdates.ts`) normalises all five sources
into one list of items, each carrying how to apply itself. It applies them
sequentially — they write to the same game directory — with the launcher's own
update last, because that one restarts the process.

## How the hub side is put together

| Layer | Where | What it does |
| --- | --- | --- |
| Community UI | `hub/src/kit` | Cards, galleries, ratings, reviews, comments, release lists, profile summaries — the same components mjolnircore.com renders |
| API client | `hub/src/kit/client.ts` | Typed calls; the launcher supplies a Tauri transport (`src/hub/client.ts`) |
| Local library | `src-tauri/src/hub.rs` | Installs, profiles, load order, updates, integrity, pairing |

Two rules explain most of the structure:

- **The webview never holds a credential.** Every hub request goes through the `hub_api` command,
  which attaches the paired API key in Rust. The command refuses any path that could point at
  another host.
- **Nothing installs unverified.** Content archives are hashed against the hub's record before
  they land anywhere permanent, every unpacked container's hash is recorded so a later verify can
  detect a cache that changed underneath, and any release signature that is present must verify
  against the key compiled into the binary. Code mods go further: they only ever install from the
  Ed25519-signed set (`keys/mod-signing.pub`).

Point the launcher at a local hub with `MJOLNIR_HUB_URL=http://localhost:3000/api/v1`.

## The rest of the Rust side

| Where | What it does |
| --- | --- |
| `src-tauri/src/maps.rs` | Installed map packs, and the one registration container in `Paks` rebuilt from all of them (`blam_pack::maps::rebuild`, the same code as `mjolnir level register`) |
| `src-tauri/src/links.rs` | `mjolnir://mod/<slug>`, `mjolnir://map/<CODE>` and `mjolnir://join/<lobby>` links from the website (the scheme is registered in `tauri.conf.json`) |
| `src-tauri/src/crash.rs`, `minidump.rs` | Crash reports: watches the folders UE's crash handler writes into, keeps the log, and sends a small bundle to the hub when the player says so; a slimmed dump follows only if the hub wants it and the player agrees again ([docs/crash_reports.md](../../docs/crash_reports.md)) |
| `src-tauri/src/transfer.rs` | Byte counts for the Updates screen's progress bars and speed graph |
| `src-tauri/src/tools.rs` | Companion tools such as the tag editor, installed on demand from their own manifests |
| `src-tauri/src/changelog.rs` | Release notes for the What's new dialog, from the hub's `/api/changelog` |

The game is found and started on Steam (`Meteorite/Binaries/Win64`) and on the
Xbox app (`Meteorite/Binaries/WinGDK`, started through `shell:AppsFolder`).

## Tests

```bash
cd src-tauri && cargo test
```

The end-to-end hub test is `#[ignore]`d because it needs the game installed, a reachable hub, and
a published mod:

```bash
MJOLNIR_HUB_URL=http://localhost:3000/api/v1 cargo test hub_install_round_trip -- --ignored --nocapture
```

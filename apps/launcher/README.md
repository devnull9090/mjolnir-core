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
| **Browse Hub** | What exists? | The community catalogue and the signed code-mod set, with full mod pages |
| **Updates** | What is out of date? | Every source at once — launcher, core install, content mods, script mods, tools |

That split is deliberate. Installed mods used to appear under both My Mods
(UE4SS scripts) and the Hub tab (content mods), with neither mentioning the
other, and "update available" lived in four unrelated corners of the UI.

The update manager (`src/updates/useUpdates.ts`) normalises all five sources
into one list of items, each carrying how to apply itself. It applies them
sequentially — they write to the same game directory — with the launcher's own
update last, because that one restarts the process.

## How the hub side is put together

| Layer | Where | What it does |
| --- | --- | --- |
| Community UI | `hub/src/kit` | Cards, galleries, ratings, reviews, comments, release lists — the same components mjolnircore.com renders |
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

## Tests

```bash
cd src-tauri && cargo test
```

The end-to-end hub test is `#[ignore]`d because it needs the game installed, a reachable hub, and
a published mod:

```bash
MJOLNIR_HUB_URL=http://localhost:3000/api/v1 cargo test hub_install_round_trip -- --ignored --nocapture
```

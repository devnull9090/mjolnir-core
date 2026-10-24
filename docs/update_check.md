# Update checks, the launch check and unsupported mods

Three pieces keep a player's game in step with what the hub ships, so a
fireteam is never split by versions or by somebody else's mods:

1. **The launch check.** Launch in the launcher checks for updates, checks
   the installed files, looks for mods MJOLNIR did not install, and only
   then starts the game.
2. **The in-game prompt.** At the main menu, the game asks the launcher what
   is out of date. If anything is, it offers UPDATE AND RESTART.
3. **Unsupported mods.** Pak and UE4SS mods from elsewhere are found and,
   on the player's say-so, moved aside for the session and moved back after.

## What counts as out of date

`preflight::check` (apps/launcher/src-tauri/src/preflight.rs) asks three
sources side by side and reports each one it could not reach:

| Source | Compared | Out of date when |
| --- | --- | --- |
| Code mods (`hub::code_mods_outdated`) | each MJOLNIR mod in `ue4ss/Mods` that is in the signed set: its own `mod.json` version | the signed set's version is newer. A newer version on disk (a development build) is not out of date. |
| Runtime bundle (`modpack_update`) | the cached runtime manifest | the bucket publishes another version |
| Hub mods (`hub::check_updates`) | each installed hub mod: the CE runtime pack and every map | the hub has a newer release, or a map's install is missing files (the same release again) |

The Updates screen asks the same sources. It judges code mods by this
launcher's install record, not by `mod.json`, so it can offer a few more.

## The launch check

Every Launch goes through `launch/PreflightProvider.tsx`. So does a
`mjolnir://join` link that has to start the game. A join the running game
picks up skips it, since nothing can change under a running game.

1. If the game is already running, it launches at once. Steam only brings
   the game forward.
2. It runs `preflight_check` (above) and `preflight_verify` together.
   `preflight_verify` needs no network:
   - **runtime bundle:** each file against the cached manifest
     (`verify_install`). The player's own config files are skipped.
   - **hub mods:** each cached container against the `container_hashes`
     recorded at install (`hub::verify_installed`).
   - **code mods:** each mod's file tree against the digest recorded when
     this launcher installed it (`hub::code_mods_modified`). A mod whose
     `mod.json` names a different version than the record is skipped.
3. When nothing is found, it launches. Otherwise a dialog lists:
   - the updates;
   - the damaged installs (a repair reinstalls the same release);
   - the unsupported mods, with *Move them aside while the game runs*
     ticked;
   - any source it could not check.

   The buttons are **Update and launch**, **Launch without updating** and
   **Cancel**.
4. The steps run one at a time, since they write to the same game folder.
   A failure stops the launch and offers **Launch anyway**.

Being offline never blocks a launch. A source that can't be reached is
listed, and Launch still works.

Paks gaps (a hub container deleted by hand) are not reported. `launch_game`
puts them back from the cache anyway (`hub::prepare_launch`).

## The in-game prompt

`mods/MJOLNIRLobby/Scripts/outdated.lua` runs from the main menu's poll in
`main.lua`. That poll runs every 1.5 s in the frontend and not at all in a
match.

- **When it checks.** A poll after a gap of more than 10 s starts a new
  visit: the first main menu after start, or the return from a match. A visit
  asks for a check unless the last answer is under 10 minutes old.
- **How it asks.** It writes `check` to `native\launcher_request.txt` and
  calls the native export `mjolnir_launcher`. The native half starts the
  launcher with no window: `--check-updates --out
  native\update_check.json`. The launcher writes the `preflight::check`
  answer there, whole (a temporary file renamed over it). The game polls for
  it and gives up after 180 s.
- **What it shows.** When there are updates or unsupported mods, it pushes
  a screen with the campaign-menu kit (`UI.push`, no cooked widget needed),
  at most once a visit, and only while the main menu is the top screen. The
  screen lists up to six items and counts the rest. Its buttons are
  **UPDATE AND RESTART** (**OPEN LAUNCHER AND RESTART** when only unsupported
  mods were found) and **NOT NOW**.
- **UPDATE AND RESTART.** It writes `update` and calls `mjolnir_launcher`,
  which starts the launcher with the link `mjolnir://update`. That reaches a
  launcher that is already open too (the single-instance hand-over). The
  game quits 2.5 s later, from the frontend only: quitting from a match
  hangs.
- **In the launcher**, the link goes to Updates and runs the launch check in
  update mode:
  1. It waits for the game to close.
  2. It applies every update and repair without asking. It asks only when
     there are unsupported mods to move.
  3. It starts the game again.

The game reaches the network only through the launcher, which already holds
the signed sets' keys. The game process gains no network client.

### Launcher features

An older launcher would ignore both requests and open its window. So
`hub::record_exe_path` now also writes `launcher_features.txt` beside
`launcher_exe.txt`, one word a line: `check-updates`, `update-link`. The
native half starts the launcher for a request only when its word is listed;
otherwise the request fails with "the MJOLNIR launcher is too old". It is a
separate file because an older MJOLNIR Lobby reads `launcher_exe.txt` whole
as the path.

### The check's file

```json
{
  "checked_at": 1792825712,
  "items": [
    { "kind": "code", "id": "MJOLNIRLobby", "name": "MJOLNIRLobby",
      "installed": "0.14.0", "latest": "0.15.0", "release_id": null, "repair": false }
  ],
  "unreachable": ["the hub: ..."],
  "unsupported": [
    { "kind": "pak", "name": "z_Mod_P", "files": ["Meteorite/Content/Paks/z_Mod_P.pak"], "bytes": 123 }
  ]
}
```

`kind` is `core`, `code` or `content`. `release_id` is the hub release to
install, for `content`.

## Unsupported mods

`apps/launcher/src-tauri/src/unsupported.rs`.

**In `Meteorite/Content/Paks`**, every `.pak`, `.utoc`, `.ucas` and `.sig`
is looked at, subfolders included: the engine mounts `~mods` and `LogicMods`
too. Names are compared case-insensitively. These are known:

- **the game's own:** `pakchunk<N>[optional]-Windows` or `-WinGDK`, and
  `global.utoc`/`global.ucas`, in Paks itself only. No store puts a file list
  in the install, so this is a name rule, and both stores' paks follow it.
- **MJOLNIR's:** `pakchunk9NN-MJOLNIR…`. That covers the hub's containers
  (`pakchunk9NN-MJOLNIRHUB-<slug>-<j>_P`, and their `_<n>_P` patch names)
  and those MJOLNIR's tools place (MJOLNIRREG, MJOLNIRMENU, MJOLNIRLAND, …).

Everything else is unsupported. A container's files are grouped by name.

**In `ue4ss/Mods`**, a folder UE4SS would start (`mods.txt` says `1`, or
it has `enabled.txt`) is unsupported unless it is one of these:

- named `MJOLNIR…`;
- a code mod this launcher installed;
- a folder of the runtime bundle (from the cached manifest);
- one of the mods UE4SS itself ships (BPModLoaderMod, Keybinds, shared, …).

**Moving aside** is a rename into
`<install>/MJOLNIR-set-aside/<unix time>/<same relative path>`:

- It stays on the game's own volume, so it is instant and cannot half-copy a
  large container. Nothing in the game reads that folder.
- Each move is written to `set_aside.json` in the launcher's config folder
  (`%APPDATA%\com.devnull9090.mjolnir-launcher`) before the next one, and
  logged to `set_aside.log` there.
- A file the game holds open is left in place and reported.
- Nothing is ever deleted.

**Moving back** happens three ways:

- **When the game exits.** `launch_game` starts a watcher whenever the
  ledger has entries. It waits up to 5 minutes for the game to appear, then
  for it to go.
- **On the next launcher start**, if the game is not running. This covers a
  launcher that was closed or crashed while the game ran.
- **Before every launch check**, with the `unsupported_restore` command, so
  the check sees the mods and no late watcher moves them back under the
  next game. Moves aside and back hold one lock, so two never overlap.

A move back that would land on a file of the same name (the player put the
mod back by hand) keeps the set-aside copy and its ledger entry, and says
so. Folders the moves emptied are removed with `remove_dir`, which only ever
removes an empty folder.

## Testing

- `cargo test` in `apps/launcher/src-tauri`. The `unsupported` tests cover
  the name rules against this PC's real Paks listing, a scan, and a move
  aside and back that will not overwrite (with a scratch ledger).
  `links` covers `mjolnir://update`.
- `lua5.4 tools/tests/test_outdated.lua`. It checks when the prompt asks,
  what it shows, that it shows once a visit and not over another screen,
  and the update request.
- By hand: run `mjolnir-launcher.exe --check-updates --out check.json` and
  read the file.

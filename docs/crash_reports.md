# Crash reports

When the game crashes, the launcher notices, asks the player whether to send
a report, and uploads a small bundle to the hub. The hub groups reports by
where the game crashed, and asks for the full memory dump only for crashes it
has not seen enough of. Status as of 2026-10-17: both sides are built, the
launcher in `apps/launcher/src-tauri/src/crash.rs` and the hub in
`hub/src/lib/api/crashes.ts` (migration 0019, admin section on
`/moderation`). Tested end to end against a local hub with this PC's real
crashes; not deployed, and the real launcher has not run it yet.

## Where crashes land

| Location | What is there |
|---|---|
| `%LOCALAPPDATA%\Meteorite\Saved\Crashes\UECC-Windows-<GUID>_<n>\` | One folder per crash, from UE's crash handler: `CrashContext.runtime-xml`, `UEMinidump.dmp`, `CrashReportClient.ini`, for GPU crashes `Breadcrumbs_*.txt` and a `.nv-gpudmp`, and an 8-byte `.film-unreal` whose name carries the mode and map |
| `%LOCALAPPDATA%\Packages\Microsoft.198377053870B_8wekyb3d8bbwe\LocalCache\Local\Meteorite\Saved\Crashes\` | The same, if the Xbox app's build is sandboxed. Unverified: the dev box has the Xbox build's `Saved\Config\WinGDK` in the plain folder above, so both are scanned |
| `...\Binaries\Win64\ue4ss\crash_*.dmp` | UE4SS's own dump. Not collected: UE's folder has the same crash |
| `C:\ProgramData\Microsoft\Windows\WER\ReportArchive\AppCrash_HaloCampaignEvol_*` | Windows' record of the crashes UE's handler missed, no dump. Not collected |
| `...\Binaries\Win64\ue4ss\UE4SS.log` | The only useful log (`Saved\Logs\Meteorite.log` is near empty in Shipping). Overwritten on every launch |

UE never deletes crash folders: the dev box had 117 of them, 19 GB. The game's
own crash reporter posts to 343's BugSplat (`DataRouterUrl` in
`CrashReportClient.ini`); the launcher leaves that alone. Whether a successful
BugSplat send deletes the folder is unverified, since every send on the dev
box failed.

What the files are worth:

- **The XML call stack is junk**: frame 0 is "UE4SS", then `ntdll+160e44`
  over and over. The useful facts are `CrashType`, `ErrorMessage`,
  `BuildVersion`, `SecondsSinceStart` and `TimeOfCrash` (UTC .NET ticks).
- **The minidump** (~172 MB, flags `0x201045`: data segments, indirectly
  referenced memory, handle data) is almost all MemoryList. The thread stacks
  are about 0.6 MB of it. Its exception record and module list give the
  faulting module and offset, which is what groups crashes. It also carries
  the XML again, as a UTF-16 user stream (type `0x10000`).
- **Asserts and GPU crashes** fault inside `KERNELBASE.dll` (UE raises them
  with `RaiseException`, codes `0x4000` and `0x8000`), so their address says
  nothing; their `ErrorMessage` does.
- The XML carries `MachineId`, `LoginId` and `EpicAccountId`.

## The launcher

**Detection.** The launcher starts the game through `steam://` or the Xbox
app, so it has no process to watch. It scans the crash folders instead: once
at startup and every 10 seconds while open. A folder counts once its files
have stopped changing for 15 seconds. Crashes are remembered in
`crash_reports.json` in the launcher's config folder. On the first run every
crash already on disk is recorded as old, so only crashes after that prompt.

**The log.** `UE4SS.log` is copied into `crash-reports\<crash id>\` as soon as
the crash is seen, and again checked in `launch_game` before the game starts.
It is taken only when it belongs to the crashed session: its first line
(local time, converted with the offset between its last line and its
modified time) is no later than the crash, and it was last written after that
session started (`TimeOfCrash - SecondsSinceStart`).

**The prompt.** A banner names the crash ("The game crashed 3 minutes into a
multiplayer game on BCK") and offers Send report and Not now. Nothing is sent
without that click. Sending needs the launcher signed in to the hub. Settings
lists recent crashes with a Send button each, for one dismissed earlier.

**The bundle** (`crash-<id>.zip`, typically well under 1 MB):

| File | Contents |
|---|---|
| `report.json` | The summary below, plus launcher version, installed hub mods (slug, version, enabled), code mods and versions, `mods.txt` |
| `CrashContext.runtime-xml` | With `MachineId`, `LoginId`, `EpicAccountId` emptied and Windows user names masked in paths |
| `UEMinidump-slim.dmp` | The dump with every memory range dropped except thread stacks, the handle data and the XML user stream removed, and user names masked in module paths. Same layout and size, the dropped bytes zeroed, so it still opens in WinDbg and compresses to almost nothing |
| `UE4SS.log` | The crashed session's log, last 4 MiB, user names masked |
| `Breadcrumbs_*.txt` | GPU crashes only |

User names are masked as `C:\Users\<user>\` (either slash) in the text files,
and as underscores of the same length inside the dump (module paths, and path
strings found on the kept stacks, ASCII or UTF-16).

The bundle is built as soon as the crash is seen and kept in
`crash-reports\<id>\` with the crash's summary in `crash_reports.json`. If the
game's crash reporter deletes the folder before the player answers, the report
can still go; only the full dump cannot. While the folder is there, sending
builds the bundle again, since the log may have been kept since.

**The signature** groups crashes:

```text
build_version | crash_type | fault
```

`fault` is `MODULE.dll+0xOFFSET (0xCODE)` for a `Crash` outside
`KERNELBASE.dll`, and otherwise the `ErrorMessage` with user names masked and
hex numbers replaced by `0x?` (asserts and GPU crashes). `signature` is the first 16 hex digits of
the SHA-256 of that string. The game's offsets move every CU, hence the build.

## Hub API

`hub/src/lib/api/crashes.ts`. All under `/api/v1`, with the launcher's paired
key. Any valid key will do: there is no crash scope, so every launcher signed
in before this existed can send. Each key has an hourly budget: 20 reports,
40 bundle uploads, 6 dump uploads (admins have none).

### `POST /crashes`

```json
{
  "crash_id": "UECC-Windows-A13FF88D473CDE7854D7F18E02EFDA14_0000",
  "signature": "ccfab15f14e59877",
  "build_version": "2026.08.11.1121610.2-Rel-i343-Meteorite-2607-CU4",
  "crash_type": "Crash",
  "fault": "UE4SS.dll+0x2580d7 (0xc0000005)",
  "error_message": "Unhandled Exception: EXCEPTION_ACCESS_VIOLATION reading address 0x0000000000000018",
  "crashed_at": "2026-10-17T04:28:33Z",
  "seconds_since_start": 175,
  "mode": "multiplayer",
  "map": "bck",
  "role": "server",
  "launcher_version": "0.14.0",
  "bundle_bytes": 327222,
  "bundle_sha256": "<hex>",
  "dump_bytes": 176604251
}
```

`error_message`, `mode`, `map`, `role` and `launcher_version` are cut to
length rather than refused. `crash_id` is the folder name, unique per crash,
so a retried send gets `200` with the report already made instead of a
second one. A new report gets `201`:

```json
{
  "id": "<report id>",
  "bundle_upload": { "method": "PUT", "url": "/crashes/<id>/bundle", "max_bytes": 8388608 },
  "wants_dump": true,
  "dump_upload": { "method": "PUT", "url": "/crashes/<id>/dump", "max_bytes": 94371840 }
}
```

`bundle_upload` is left out when the bundle is already stored. `wants_dump`
is true when the launcher has a dump (`dump_bytes` > 0) and the hub holds
fewer than three full dumps for that signature and build. A dump a player
declined does not count, so the next player is asked. `dump_upload` is
present only then. Its `url` is a hub path (the launcher adds its key) or an
absolute presigned URL (sent without the key); the hub uses paths today.

### `PUT /crashes/{id}/bundle`

The zip, `Content-Type: application/zip`, at most 8 MiB. Only the report's
owner may upload it; anyone else gets `404`. Refused with `400` when it is
not a zip or its SHA-256 is not `bundle_sha256`. `200 {sha256, bytes}`.

### `PUT /crashes/{id}/dump`

The untouched `UEMinidump.dmp` zipped (deflate, about 30% of its size: 52 MB
for a 176 MB dump), at most 90 MiB (`MAX_ARCHIVE_BYTES`). The launcher sends
it only after a second, separate yes from the player, because the full dump
is a copy of the game's memory. `409` when the hub did not ask this report
for it or already has it. `200 {sha256, bytes}`.

### Reading them (admins)

- `GET /admin/crashes`: signatures grouped by signature and build, most
  recently filed first, with report, player and dump counts, maps, first and
  last seen. `?build=` narrows to one build.
- `GET /admin/crashes/{signature}?build=`: its reports, newest first.
- `GET /admin/crash-reports/{id}/bundle` and `/dump`: the files, as
  downloads.

Admins only, not moderators: a bundle carries a player's log and a dump is
their game's memory. The page is the Crash reports section of `/moderation`,
shown to admins.

### Storage

A `crash_reports` row per report (migration 0019), and R2 objects in
MODS_BUCKET under `crashes/<id>/bundle.zip` and `crashes/<id>/dump.zip`.
Nothing serves that bucket directly. Each new report also sweeps up to 50
reports older than 90 days, rows and objects. An account deleted from
`users` takes its rows with it (cascade) but leaves its objects, so an R2
lifecycle rule on the `crashes/` prefix (about 100 days) is the backstop
once this is deployed.

### Testing locally

`pnpm db:migrate`, seed a user and an API key into the local D1, run
`pnpm dev`, then send this PC's newest crash from the launcher code:

```bash
MJOLNIR_CRASH_HUB=http://localhost:3000/api/v1 MJOLNIR_CRASH_KEY=mjc_... cargo test --lib real_crashes -- --ignored --nocapture
```

Without the two variables the same test sends to a stand-in hub inside the
test and checks every request against this contract.

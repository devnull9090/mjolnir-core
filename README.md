<p align="center">
  <a href="https://mjolnircore.com">
    <img src="hub/public/logo-transparent.png" alt="MJOLNIR Core Logo" width="160" height="160">
  </a>
</p>

<h1 align="center">MJOLNIR Core</h1>

<p align="center">
  <strong>The Open-Source Modding Framework & Platform for Halo Campaign Evolved</strong>
</p>

<p align="center">
  <a href="https://github.com/devnull9090/mjolnir-core/actions/workflows/ci.yml"><img src="https://github.com/devnull9090/mjolnir-core/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/devnull9090/mjolnir-core/actions/workflows/deploy-hub.yml"><img src="https://github.com/devnull9090/mjolnir-core/actions/workflows/deploy-hub.yml/badge.svg" alt="Deploy Hub"></a>
  <a href="https://github.com/devnull9090/mjolnir-core/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-gold.svg" alt="License: MIT"></a>
  <a href="https://discord.gg/9gxYZsByW9"><img src="https://img.shields.io/badge/Discord-Join%20Community-5865F2?logo=discord&logoColor=white" alt="Discord"></a>
  <a href="https://store.steampowered.com/app/2993530/Halo_Campaign_Evolved/"><img src="https://img.shields.io/badge/Platform-Windows-0078D4?logo=windows&logoColor=white" alt="Platform"></a>
  <a href="https://www.unrealengine.com/"><img src="https://img.shields.io/badge/Engine-Unreal%205.5-313131?logo=unrealengine&logoColor=white" alt="UE5"></a>
  <a href="https://mjolnircore.com"><img src="https://img.shields.io/badge/Hosted%20on-Cloudflare-F38020?logo=cloudflare&logoColor=white" alt="Cloudflare"></a>
  <a href="https://tauri.app"><img src="https://img.shields.io/badge/Launcher-Tauri%202-24C8D8?logo=tauri&logoColor=white" alt="Tauri"></a>
</p>

<p align="center">
  🌐 <a href="https://mjolnircore.com"><strong>mjolnircore.com</strong></a> · 💬 <a href="https://discord.gg/9gxYZsByW9"><strong>Join Discord</strong></a> · 📦 <a href="https://mjolnircore.com/download"><strong>Download Launcher</strong></a>
</p>

---

## Repository Structure

```
mjolnir-core/
├── mods/                        # UE4SS Lua mods
│   ├── MJOLNIRCore/             # Core runtime & UEHelpers library
│   ├── MJOLNIRFlyCam/           # Free debug camera with WASD, mouse look, HUD toggle
│   ├── MJOLNIRConsoleEnabler/   # Developer console enabler (~ / Tab / F10)
│   ├── MJOLNIRMultiplayer/      # Experimental map travel & admin commands
│   ├── MJOLNIRDiscovery/        # UFunction dumper & travel logging
│   └── MJOLNIRTagProbe/         # Read loaded Blam tag assets in game
├── signatures/                  # UE4SS AOB scan overrides for HCE
├── native/                      # C source for FName trampoline DLL
├── config/                      # Reference UE4SS-settings.ini
├── tools/ghidra/                # Ghidra reverse-engineering scripts
├── tools/iostore/               # UE5 IoStore + Blam tag readers (Python)
├── crates/                      # Rust workspace
│   ├── ue-iostore/              # UE5 .utoc/.ucas reader, TOC writer, container packer
│   ├── blam-defs/               # Tag definition model & JSON corpus loader
│   ├── blam-tag/                # Blam tag reader, writer and editor
│   └── blam-cli/                # `mjolnir` command-line tool
├── apps/
│   ├── launcher/                # Tauri desktop mod manager
│   └── tag-editor/              # Guerilla-style tag browser and editor
└── hub/                         # Cloudflare mod community platform
```

---

## Mods

### MJOLNIRFlyCam
Smooth free-flying debug camera with continuous WASD movement, mouse viewport look, and HUD overlay toggle.

| Hotkey | Action |
| :--- | :--- |
| `F8` | Toggle FlyCam ON/OFF (auto-hides HUD) |
| `F7` | Toggle HUD overlay |
| `F9` | Toggle mouse look |
| `W/A/S/D` | Move camera (forward/left/back/right) |
| `Space / Ctrl` | Ascend / Descend |
| `Left Shift` | Boost speed (3x) |
| `[ / ]` | Decrease / Increase base speed |

### MJOLNIRConsoleEnabler
Enables the UE5 developer console in the shipping build.

### MJOLNIRMultiplayer
Experimental travel probes for verified campaign package paths, listen-server loading, and player
administration. Runtime travel and session preservation still require in-game verification.

| Command | Purpose |
| :--- | :--- |
| `mjolnir_maps` | List verified CU2 root world package keys and paths |
| `mjolnir_travel a15` | Dispatch plain travel to the A15 campaign world |
| `mjolnir_listen a15` | Dispatch travel to A15 with `?listen` |
| `mjolnir_scan_blam` | Dump live BlamEngine classes, functions, and candidate instances |
| `mjolnir_scan_worlds` | Dump loaded Halo world objects |
| `mjolnir_trace_network` | Hook co-op session, lobby, and travel lifecycle functions |
| `mjolnir_dump_state` | Snapshot live variant and Blam network component properties |

### MJOLNIRCore
Core framework initialization and `UEHelpers` utility library.

---

## Quick Start

### Prerequisites
- [Halo Campaign Evolved](https://store.steampowered.com/app/2993530/Halo_Campaign_Evolved/) (Steam)
- [RE-UE4SS v3.0.1 experimental](https://github.com/UE4SS-RE/RE-UE4SS/releases) (`dwmapi.dll` proxy)

### Installation
1. Install UE4SS into `Meteorite/Binaries/Win64/ue4ss/`
2. Copy the `mods/` folder contents into `ue4ss/Mods/`
3. Copy the `signatures/` folder contents into `ue4ss/UE4SS_Signatures/`
4. Copy `config/UE4SS-settings.ini` to `ue4ss/UE4SS-settings.ini`
5. Add mod entries to `ue4ss/Mods/mods.txt`:
   ```
   MJOLNIRCore : 1
   MJOLNIRConsoleEnabler : 1
   MJOLNIRFlyCam : 1
   ```
6. Launch the game via Steam

### Reloading Mods
UE4SS reads `mods.txt` and loads Lua scripts during process startup in the tested configuration.
Restart HCE after adding, enabling, or changing a mod; MJOLNIR Core does not currently install a
`CTRL+R` reload binding.

---

## Development

### Reverse Engineering
Ghidra Java scripts for the simulation factory and host loader path:
```powershell
analyzeHeadless.bat <project_dir> HaloSimulation `
  -import "HaloSimulation_tag_release.dll" `
  -scriptPath "tools/ghidra" `
  -postScript AnalyzeBlamShell.java <output_dir>

analyzeHeadless.bat <project_dir> HCE_Analysis `
  -process "HaloCampaignEvolved.exe" `
  -noanalysis `
  -scriptPath "tools/ghidra" `
  -postScript AnalyzeBlamLoader.java <output_dir>

analyzeHeadless.bat <project_dir> HCE_Analysis `
  -process "HaloCampaignEvolved.exe" `
  -noanalysis `
  -scriptPath "tools/ghidra" `
  -postScript AnalyzeMultiplayerRuntime.java <output_dir>
```

Ghidra 12.1 does not run Python scripts through `analyzeHeadless` unless it is launched through
PyGhidra. Use the Java probes above for standard headless runs.

### Game Data Analysis
Read-only IoStore readers for the shipped `.utoc`/`.ucas` containers live in `tools/iostore`. They
need an `oo2core_9_win64.dll` from a local Unreal Engine install, since UE 5.5 statically links
Oodle and the game ships no separate DLL.

```powershell
$paks  = "<install>\Meteorite\Content\Paks"
$oodle = "<UE install>\Engine\Binaries\DotNET\AutomationTool\oo2core_9_win64.dll"

python tools/iostore/dump_index.py   --paks $paks --ext-stats --out out/iostore_paths.tsv
python tools/iostore/inspect_tags.py --paks $paks --oodle $oodle --per-group 1
python tools/iostore/zen_class.py    --paks $paks --oodle $oodle --grep-scripts "TagDataAsset$"
python tools/iostore/extract_tags.py --paks $paks --oodle $oodle --group vehicle --out <dir> --verify
```

`extract_tags.py` output is copyrighted game content. Keep it local and never commit it.
See [`docs/tag_data_pipeline.md`](docs/tag_data_pipeline.md) for the findings these tools produced.

### Tag Definitions

Halo Campaign Evolved tag files are **self-describing**: each one carries a `blay` layout section
holding its own field names, type names, and enum option names — the same strings Guerilla showed.
Definitions for all 101 shipped groups are recoverable from the game data alone, with no need to
recover them from the engine binary. See [`docs/tag_body_format.md`](docs/tag_body_format.md), and
[`docs/tag_editing_guide.md`](docs/tag_editing_guide.md) for a practical guide to reading and
editing tags with the CLI and the editor.

The Rust workspace in `crates/` reads containers and layouts natively:

| Crate | Purpose |
|---|---|
| `ue-iostore` | UE 5.5 IoStore `.utoc`/`.ucas` reader (TOC v2–8, Oodle, zlib, partitions) |
| `blam-defs` | Shared tag definition model and JSON corpus format |
| `blam-tag` | Container header, `blay` layout, `bdat` values: read, decode, edit, write |
| `blam-cli` | The `mjolnir` command-line tool |

```powershell
$env:HCE_PAKS = "<install>\Meteorite\Content\Paks"
$env:OODLE    = "<UE install>\Engine\Binaries\DotNET\AutomationTool\oo2core_9_win64.dll"

cargo run --release -p blam-cli -- groups                            # every group + tables
cargo run --release -p blam-cli -- fields --group weapon             # resolved field list
cargo run --release -p blam-cli -- layout --group camera_track --tables
cargo run --release -p blam-cli -- types                             # field type vocabulary
cargo run --release -p blam-cli -- validate --all                    # invariants, all 12,290 tags
cargo run --release -p blam-cli -- sections                          # tgly tables + blay preamble
cargo run --release -p blam-cli -- data --group weapon --trace       # decode one tag's values
cargo run --release -p blam-cli -- values --group weapon             # fields with decoded values
cargo run --release -p blam-cli -- roundtrip --all                   # re-serialise, compare bytes
cargo run --release -p blam-cli -- recode --all                      # decode/encode identity
cargo run --release -p blam-cli -- toc-roundtrip                     # rewrite every .utoc, compare bytes
cargo run --release -p blam-cli -- chunk --path assault_rifle-weapon.uasset   # hexdump any chunk
cargo run --release -p blam-cli -- pack --group weapon --tag assault_rifle-weapon --set "magazines[0].rounds loaded maximum=200" --out-dir mod
cargo run --release -p blam-cli -- set --group camera_track --field "control points[0].position" --value "(1,2,3)"
cargo run --release -p blam-cli -- defs                              # export the corpus
```

`mjolnir validate --all` passes every structural invariant across all **12,290 shipped tags**,
resolves a root struct size for **100%** of them, and decodes the field values of **99.9%** into a
byte-exact value tree. `mjolnir roundtrip --all` then writes every one of those trees back out
and confirms **12,281 / 12,281** reproduce the original bytes exactly, across 5.77 GB.
`mjolnir defs` writes
`defs/hce/tag-definitions.json` — 101 groups, 1,779 structs, 13,250 fields — which the hub renders
as a searchable reference at [`/docs/tags`](https://mjolnircore.com/docs/tags).

Only schema is exported: field names, types, offsets, and enum option names. Tag values are game
content and are never written. Nothing is written to disk by the inspection commands.

The launcher is excluded from the root Cargo workspace on purpose, so it keeps its own target
directory and release pipeline. Build it from `apps/launcher` as before.

### Tag Editor

`apps/tag-editor` is a Guerilla-style tag browser and editor built on the same stack as the
launcher: Tauri 2, React 19, Vite, and Tailwind 4. It reads tags from your own installation —
nothing is bundled, and the installation is never modified.

```powershell
cd apps/tag-editor
pnpm install
pnpm tauri dev
```

The Paks folder and Oodle DLL are auto-detected on first run, with a manual picker as a fallback.

It renders the tag tree and, for each tag, its fields with their **decoded values** — enum and
bitfield options resolved to names, tag references as group and path, colours as hex, vectors and
bounds as numbers — with blocks and arrays expanding to their elements.

Fields are editable: click a value, type a new one, press Enter. Edits are validated before they
are kept, marked in the tree, and individually undoable. They are held in memory and leave through
**Export patched tag…**, because the game loads tags from read-only IoStore containers and there is
nowhere to save them back to — writing those containers is not implemented yet, so an exported tag
cannot currently be loaded by the game.

Exported tags are copyrighted game content. Keep them local; `.gitignore` blocks `*.ubulk`.

See [`docs/tag_editing_guide.md`](docs/tag_editing_guide.md) for a walkthrough of both the editor
and the `mjolnir` command line, and [`docs/iostore_packaging.md`](docs/iostore_packaging.md) for
what it would take to get an edited tag loading in game.

### Coming Soon
- **MJOLNIR Tag Editor**: Guerilla-style tag browser and inspector (Tauri, in progress)
- **MJOLNIR Hub**: Community platform for mods and tools, with submission and moderation
- **Player Tracker**: Multiplayer stats and leaderboards

---

## Community

- 💬 **Discord**: [https://discord.gg/9gxYZsByW9](https://discord.gg/9gxYZsByW9)
- 🐛 **Issues**: [GitHub Issues](https://github.com/devnull9090/mjolnir-core/issues)

## License

Open Source under MIT License.

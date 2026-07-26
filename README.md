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
│   └── MJOLNIRDiscovery/        # UFunction dumper & travel logging
├── signatures/                  # UE4SS AOB scan overrides for HCE
├── native/                      # C source for FName trampoline DLL
├── config/                      # Reference UE4SS-settings.ini
├── tools/ghidra/                # Ghidra reverse-engineering scripts
├── launcher/                    # (Coming Soon) Tauri desktop mod manager
└── hub/                         # (Coming Soon) Cloudflare mod community platform
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

### Coming Soon
- **MJOLNIR Launcher**: Tauri desktop app for one-click mod management
- **MJOLNIR Hub**: Community mod platform (browse, upload, download mods)
- **Player Tracker**: Multiplayer stats and leaderboards

---

## Community

- 💬 **Discord**: [https://discord.gg/9gxYZsByW9](https://discord.gg/9gxYZsByW9)
- 🐛 **Issues**: [GitHub Issues](https://github.com/devnull9090/mjolnir-core/issues)

## License

Open Source under MIT License.

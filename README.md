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
│   ├── MJOLNIRMultiplayer/      # Session hosting & admin commands
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
Session hosting, server travel, kick/ban commands via `!kick`, `!ban`, `!travel`.

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

### Hot Reload
Press **`CTRL + R`** in-game to reload all Lua mods without restarting.

---

## Development

### Reverse Engineering
Ghidra scripts for analyzing `HaloCampaignEvolved.exe`:
```bash
# Headless analysis
analyzeHeadless.bat <project_dir> MJOLNIR_Proj \
  -import "HaloCampaignEvolved.exe" \
  -scriptPath "tools/ghidra" \
  -postScript extract_signatures.py
```

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

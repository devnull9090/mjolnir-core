# MJOLNIR Core - Halo Campaign Evolved Modding Framework

[![Discord](https://img.shields.io/discord/100000000000000000?color=7289da&logo=discord&logoColor=white&label=Discord)](https://discord.gg/9gxYZsByW9)

**MJOLNIR Core** is an open-source modding framework designed for *Halo Campaign Evolved*, built on top of the **RE-UE4SS** (Unreal Engine 4/5 C++ and Lua Scripting System) architecture with Ghidra reverse-engineering tooling integration.

Join our community on **[Discord](https://discord.gg/9gxYZsByW9)** to discuss mod development, reverse engineering, and updates!

---

## Features & Modules

- **MJOLNIRCore**: Core runtime initialization and `UEHelpers` library for safe UObject queries.
- **MJOLNIRFlyCam**: Smooth 3D free camera with WASD/IJKL continuous movement, mouse look, speed boosting, and HUD toggle (`F7` / `F8` / `F9`).
- **MJOLNIRConsoleEnabler**: Developer console hook (`~` / `Tab` / `F10`) for in-game console commands.
- **MJOLNIRMultiplayer**: Session hosting, map travel, and admin RPC hooks.
- **MJOLNIRDiscovery**: Diagnostic UFunction dumper and netcode travel logging.

---

## Directory Structure

```
c:\haloce\
├── mods.json                     # Primary UE4SS mod loader manifest
├── mods.txt                      # Fallback mod loader manifest
├── UE4SS-settings.ini            # Engine configuration & hook settings (HotReload: Ctrl+R)
├── Mods/
│   ├── MJOLNIRCore/              # Core runtime initialization & UEHelpers library
│   │   └── Scripts/
│   ├── MJOLNIRFlyCam/            # Free debug camera & HUD toggle mod
│   │   └── Scripts/
│   ├── MJOLNIRConsoleEnabler/    # Console enabler mod
│   │   └── Scripts/
│   ├── MJOLNIRMultiplayer/       # Session hosting & travel hooks
│   │   └── Scripts/
│   └── MJOLNIRDiscovery/         # Diagnostic UFunction dumper
│       └── Scripts/
└── tools/
    └── ghidra/                   # Ghidra headless scripts for symbol & signature analysis
```

---

## Hotkeys

| Hotkey | Description |
| :--- | :--- |
| **`F8`** | Toggle **FlyCam** ON / OFF (Auto-hides HUD) |
| **`F7`** | Toggle **HUD Overlay** ON / OFF |
| **`F9`** | Toggle **Mouse Look** ON / OFF |
| **`CTRL + R`** | **Hot-Reload All Mods** in-game |
| **`~` / `Tab` / `F10`** | Open **Developer Console** |

---

## Community & Discord

Join our Discord server for support, mod creation, and discussion:
👉 **[https://discord.gg/9gxYZsByW9](https://discord.gg/9gxYZsByW9)**

---

## License

Open Source under MIT License.

# MJOLNIR Core - Halo Campaign Evolved Modding Framework

**MJOLNIR Core** is an open-source modding framework designed for *Halo Campaign Evolved*, built on top of the **RE-UE4SS** (Unreal Engine 4/5 C++ and Lua Scripting System) architecture with Ghidra reverse-engineering tooling integration.

## Targets

- **Game Directory**: `C:\Program Files (x86)\Steam\steamapps\common\Halo Campaign Evolved`
- **Engine Binary**: `Meteorite\Binaries\Win64\HaloCampaignEvolved.exe`
- **Simulation Layer**: `Meteorite\Binaries\Win64\HaloSimulation_tag_release.dll`

## Architecture & Framework Modules

```
c:\haloce\
├── mods.json                     # Primary UE4SS mod loader manifest
├── mods.txt                      # Fallback mod loader manifest
├── UE4SS-settings.ini            # Engine configuration & hook settings
├── Mods/
│   ├── MJOLNIRCore/              # Core runtime initialization & UEHelpers library
│   │   └── Scripts/
│   │       ├── main.lua
│   │       └── UEHelpers.lua
│   ├── MJOLNIRMultiplayer/       # Session hosting, map travel, & admin RPC hooks
│   │   └── Scripts/
│   │       └── main.lua
│   └── MJOLNIRDiscovery/         # Diagnostic UFunction dumper & netcode URL logging
│       └── Scripts/
│           └── main.lua
└── tools/
    └── ghidra/
        └── extract_signatures.py # Ghidra headless script for symbol & signature analysis
```

## Installation & Deployment

1. Copy `UE4SS.dll`, `dwmapi.dll` (or proxy DLL of choice), `UE4SS-settings.ini`, `mods.json`, and the `Mods` directory into:
   `C:\Program Files (x86)\Steam\steamapps\common\Halo Campaign Evolved\Meteorite\Binaries\Win64\`
2. Launch *Halo Campaign Evolved*.
3. Press `Ctrl + O` to open the UE4SS Live View Inspector and console.

## Ghidra Reverse Engineering

To execute headless symbol extraction using local Ghidra (`C:\tools\ghidra_12.1.2_PUBLIC`):

```cmd
C:\tools\ghidra_12.1.2_PUBLIC\support\analyzeHeadless.bat C:\ghidra_proj MJOLNIR_Proj -import "C:\Program Files (x86)\Steam\steamapps\common\Halo Campaign Evolved\Meteorite\Binaries\Win64\HaloCampaignEvolved.exe" -scriptPath "C:\haloce\tools\ghidra" -postScript extract_signatures.py
```

## License

Open Source under MIT License.

# scenario_probe

Throwaway native probes used on 2026-09-03 to find out why a brand-new
scenario package would not launch (see `docs/new_scenario_loading.md`). They
are research instruments, not mods: hard-coded RVAs for the CU4 host exe
(PE timestamp `0x8a03f777`), file-based request/response next to the DLL, and
`HeapAlloc` buffers the engine later frees (expect an exit crash).

Build (any x64 MSVC 2022 developer prompt, or `vcvars64.bat` first):

```
cl /nologo /O2 /W4 /MD /LD store_probe.c  /Fe:store_probe.dll  /link /NOLOGO /Brepro
cl /nologo /O2 /W4 /MD /LD tagrefs_probe.c /Fe:tagrefs_probe.dll /link /NOLOGO /Brepro
```

Load from the game's UE4SS Lua sandbox (the MJOLNIR bridge `game_lua` tool):

```lua
local f = package.loadlib("C:\\path\\store_probe.dll", "probe_open"); f()
```

Both DLLs refuse to install on a different exe build. Exports and request
files are listed in `docs/new_scenario_loading.md`.

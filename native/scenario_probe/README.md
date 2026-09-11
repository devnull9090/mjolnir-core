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

Added 2026-09-11, when the question became why a brand-new *world* package
bounced (same doc, "The world gate, found and passed"):

- `chunk_probe.c` — wraps `DoesChunkExist` (vtable slot 7) on every
  IoDispatcher backend and logs watched package ids: shows what the loader
  asks the containers, and that it never asked for the new world.
- `gate_probe.c` — redirects the `call rel32` sites of the campaign flow's
  tag gate, `StartScenario` and the travel request to logging wrappers
  (no prologue relocation needed), and wraps the tag object's slot 3. Showed
  the tag gate passing and the travel URL carrying the world's short name.
- `ar_probe.c` — logs the AssetRegistry vtable (address handed over in
  `ar_addr.txt` from Lua) and wraps `GetFirstPackageByName` (slot 30): the
  miss for `BGL` that refuses the travel. `ar_fix.c` was the same hook
  answering from `ar_map.txt`, the experiment that proved the fix and grew
  into `native/map_registry/`.

Build each like the two above; load with `probe_open`, arm `ar_probe` with
`probe_arm`.

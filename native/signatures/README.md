# Experimental signatures — not shipped

These AOB signatures belong to the FName injector track in this directory
(`fname_trampoline.c`, "MJOLNIR FName Injector v3"), **not** to the runtime
that ships today.

`FName_Constructor.lua` here matches a `MJOL`/`NIR!` marker that
`fname_trampoline.c` emits as multi-byte NOP operands at the start of its
injected trampoline. The trampoline registers itself in the PE exception
table via `RtlAddFunctionTable`, and the signature finds it by that marker.

Nothing builds the injector. CI builds four other DLLs from `native/`
(`blam_console`, `map_registry`, `lobby`, `frame_times`; `.github/workflows/ci.yml`
and `release-mods.yml`), but no workflow references `fname_trampoline.c`, so the
trampoline is never injected, so these signatures cannot resolve against a stock
game binary. They lived in `signatures/` until 2026-08-01, where they were one
edit to `scripts/build-modpack.ps1` away from shipping and breaking every
install — the build only avoided it by overwriting them with upstream's
copies immediately after copying them in.

They are kept because the injector work is real and worth resuming. They are
moved here so that a build can only pick them up deliberately.

The signatures that actually ship live in `/signatures`. See that directory's
README for the rules about RIP-relative displacements and match uniqueness.

Consequently `tools/pe/aob_scan.py` reports this directory as mostly failing,
and that is the expected result, not a regression:

```
$ python tools/pe/aob_scan.py "<Win64>/HaloCampaignEvolved.exe" --signatures native/signatures
NO MATCH       ConsoleManager
NO MATCH       FName_Constructor
AMBIGUOUS x3   GameEngineTick
OK             GUObjectArray
OK             GUObjectHashTables
```

The two `OK` lines are coincidental byte matches against unrelated SSE code, not
real resolutions. Point the tool at `/signatures` — its default — to check the
set that ships.

`port_rvas.py` (added 2026-10-10, PR #179) is the exception: it is not a
signature, and it is in use. It finds the Steam exe's functions and globals in
another build of the game (the Xbox app's exe, or the next update) by their
code. That is how `native/map_registry`'s Game Pass addresses were found
(`docs/game_pass.md` has the recipe).

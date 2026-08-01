# Code mod submission

<!-- For UE4SS Lua / native mods under mods/. Delete for other PRs.
     Full pipeline and review criteria: docs/contributing_code_mods.md -->

## What it does

<!-- One paragraph, player-facing. -->

## Capabilities used

<!-- Check everything the mod touches, and justify each checked item.
     An undeclared capability found in review is an automatic return. -->

- [ ] File I/O (`io.*`, reading/writing files) — why:
- [ ] Process / OS access (`os.execute`, `os.getenv`, …) — why:
- [ ] Native code (`package.loadlib`, `require` of a C module) — why:
- [ ] Dynamic code (`load`, `loadstring`, `dofile`) — why:
- [ ] Network access — why:
- [ ] Input hooks / key binds — which:
- [ ] Console commands registered — which:
- [ ] None of the above

## How to test

<!-- Mission, steps, expected observable result. A reviewer will do this. -->

## Checklist

- [ ] `luacheck` passes locally with the flags from `.github/workflows/release-mods.yml`
- [ ] No prebuilt binaries anywhere in the diff
- [ ] No code is fetched, generated, or evaluated at runtime
- [ ] I've read the review criteria in `docs/contributing_code_mods.md`

# Contributing a Code Mod

**Scope:** UE4SS Lua mods (and, case by case, native DLLs). For content
mods — tags, textures, maps, sounds — you don't need any of this: upload a
[`.mjolnir` archive](mjolnir_format.md) at
[mjolnircore.com/mods/new](https://mjolnircore.com/mods/new).

## Why code is different

A Lua mod running under UE4SS has `io`, `os.execute` and
`package.loadlib` — it can write files and load native libraries, which
makes it exactly as powerful as a DLL. There is no reliable way to scan
that power away, so we do not pretend to: **everything that executes ships
from this repository**, where it arrived as a pull request someone read,
was built by CI, and is covered by a signature the launcher checks
([`docs/hub_architecture.md`](hub_architecture.md) §2).

The trade is real: you cannot ship a script mod in five minutes. In
exchange, every player who installs one knows a human read every line.

## The pipeline

1. **Fork and branch.** Your mod lives at `mods/<YourModName>/` following
   the layout of the existing mods (`scripts/main.lua`, optional
   `mods.json` metadata).
2. **Lint clean.** CI runs luacheck over `mods/`; the release workflow
   treats warnings as fatal. Run it locally first.
3. **Open a pull request** using the code-mod template. Fill in what the
   mod does, every capability it uses (file I/O, network, input hooks,
   console commands), and how to test it in game.
4. **Review.** A maintainer reads the code — all of it. Obfuscated,
   minified, or needlessly clever code is returned, not debated. Budget a
   round or two of feedback.
5. **Release.** Merged mods ship in the next `mods-v*` tag.
   `release-mods.yml` builds every mod into a versioned zip, writes a
   manifest with each artifact's SHA-256, signs the manifest with the
   release key, and publishes to GitHub Releases and
   `releases.mjolnircore.com/mods/`. The launcher pins
   [`keys/mod-signing.pub`](../keys/mod-signing.pub) and installs nothing
   that fails verification.

## Review criteria

Written down so the bar is legible, not vibes:

- **Capabilities must be declared.** Any use of `io`, `os`, `package`,
  `loadstring`/`load`, `require` beyond the UE4SS API, or network access
  must be listed in the PR and justified by the mod's stated purpose. An
  undeclared capability is an automatic return, however innocent.
- **No fetched code.** A mod may not download, generate, or otherwise
  acquire code at runtime. What ships is what runs.
- **No obfuscation.** If a reviewer cannot read it, it does not merge.
- **Smallest footprint that works.** Hooks are scoped, polling is
  justified, nothing rummages outside the game and the mod's own
  directory.
- **Plays well with the set.** Mods ship together; a mod that breaks
  another mod, or the base game outside its stated purpose, is returned.

Native DLLs add: source must build reproducibly in CI from what is in the
repo, with no prebuilt binaries in the tree, and the bar for accepting one
at all is materially higher — expect "can this be Lua?" as the first
question.

## Versioning

The set version (`mods-vX.Y.Z`) is the unit of release; individual mods
declare their own version in their metadata and it appears in the
manifest. Yanking a bad set is a new tag, never a mutated old one.

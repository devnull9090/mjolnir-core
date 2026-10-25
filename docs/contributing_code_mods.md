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
   the layout of the existing mods (`Scripts/main.lua`, plus a `mod.json`
   declaring `version`, `summary` and `category` — the release workflow
   fails without all three). `slug` and `default` are optional; see
   [Shipping by default](#shipping-by-default) before reaching for the
   latter.
2. **Lint and test clean.** CI runs luacheck over `mods/` and
   `signatures/` but only reports; the release workflow runs the same
   check and treats warnings as fatal, so run it locally first. CI also
   runs the Lua tests in `tools/tests/` (`lua5.4 tools/tests/<test>.lua`),
   and those do fail a pull request.
3. **Open a pull request** using the code-mod template. Fill in what the
   mod does, every capability it uses (file I/O, network, input hooks,
   console commands), and how to test it in game.
4. **Review.** A maintainer reads the code — all of it. Obfuscated,
   minified, or needlessly clever code is returned, not debated. Budget a
   round or two of feedback.
5. **Release.** Merged mods ship in the next `mods-v*` tag.
   `release-mods.yml` builds the native halves and the Megalo game types
   from source, refuses a tag with no changelog entry
   (`changelog/mods/<version>.md`), builds every mod into a versioned
   zip, writes a manifest with each artifact's SHA-256, signs the manifest
   with the release key, publishes to GitHub Releases and
   `releases.mjolnircore.com/mods/`, and refreshes each mod's hub page.
   The launcher pins
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

A native half keeps its C source and a `build.ps1` in `native/<name>/`.
The build writes the DLL into `mods/<Mod>/native/`, where the Lua side
loads it from, and `.gitignore` keeps it out of the tree. CI builds it on
every pull request and `release-mods.yml` builds it again from the tag,
so adding one means adding its DLL to `.gitignore`, its build and upload
to the `build-native` jobs in both `ci.yml` and `release-mods.yml`, and
its download and check to the release job.

## Shipping by default

`"default": true` in a mod's `mod.json` puts it in the set the launcher
installs during setup, without asking. A map is the other way in:
installing a map pack, or the official maps from the Multiplayer page,
also installs the mods a map plays through (`MJOLNIRCore`,
`MJOLNIRLevelLoader`, `MJOLNIRLobby`, `MJOLNIRHud`). Everything else in
the set is opt-in from My Mods, which lists the whole set so nothing is
hidden — just not installed.

The bar is "a MJOLNIR install does not work without this", not "this is
good and people would like it". Being useful is an argument for being in
the set, not for being installed unasked. In particular, a mod that opens
a channel into the running game, dumps engine internals, or is labelled
experimental does not take the flag no matter how convenient it is for
the people developing it — `MJOLNIRBridge` evaluates arbitrary Lua on the
game thread, and is exactly the kind of mod that stays opt-in.

Adding the flag is a reviewed change to a file in this repository like
any other, and it is reviewed as a decision about every player's machine.

## Versioning

The set version (`mods-vX.Y.Z`) is the unit of release; individual mods
declare their own version in their metadata and it appears in the
manifest. Yanking a bad set is a new tag, never a mutated old one.

Bump `version` in the `mod.json` of every mod a pull request changes,
a change to its native half included. The launcher offers a mod's update
only when that version changes, so a changed mod that keeps its number
ships in the set but never reaches anyone who already has it.

# Packaging the CLI

How `mjolnir` reaches a machine that has no Rust toolchain on it — on any of the
three desktop operating systems.

Everything here is driven by [`.github/workflows/release-cli.yml`](../.github/workflows/release-cli.yml),
which runs on a `cli-v*` tag. Nothing in this directory is built by hand.

| Channel | Command | Set up? | Who has to approve |
| --- | --- | --- | --- |
| GitHub release | download an archive | ✅ works now | nobody |
| CDN | `releases.mjolnircore.com/cli/latest/…` | ✅ works now | nobody |
| Scoop (Windows) | `scoop install mjolnir` | ✅ works now | nobody |
| Homebrew (macOS, Linux) | `brew install mjolnir` | ✅ works now | nobody |
| `.deb` (Debian, Ubuntu) | `sudo dpkg -i mjolnir_*.deb` | ✅ works now | nobody |
| `.rpm` (Fedora, RHEL, SUSE) | `sudo rpm -i mjolnir-*.rpm` | ✅ works now | nobody |
| WinGet | `winget install MJOLNIRCore.CLI` | needs `WINGET_TOKEN` | Microsoft, per release |
| Chocolatey | `choco install mjolnir-cli` | needs `CHOCO_API_KEY` | Chocolatey, first release |
| Cargo | `cargo install --git …` | ✅ works now | nobody, but needs Rust |

The release workflow skips the WinGet and Chocolatey jobs when their credential
is missing, so a release does not fail over a channel nobody has set up yet.

## Rehearsing a release

Run the **Release CLI** workflow by hand and give it the tag you are about to
push. It runs the changelog gate, checks the tag against the crate version,
builds all three platforms and smoke-tests each binary — then stops. Nothing is
released, uploaded, committed or announced.

Worth doing before the first tag, and before any release that changes this
pipeline. A release is the one run everybody is watching, and it should not also
be the first run.

---

## What gets built

| Platform | Artifact | Notes |
| --- | --- | --- |
| Windows x64 | `mjolnir-<v>-windows-x64.zip` | MSVC target |
| Linux x64 | `mjolnir-<v>-linux-x64.tar.gz` | **static musl** — no glibc requirement at all |
| macOS | `mjolnir-<v>-macos-universal.tar.gz` | one file, Intel **and** Apple Silicon |
| Debian/Ubuntu | `mjolnir_<v>_amd64.deb` | built by fpm from the static binary |
| Fedora/RHEL/SUSE | `mjolnir-<v>-1.x86_64.rpm` | same |

**Why static musl for Linux.** A glibc build made on the CI runner refuses to
start on any distribution older than the runner — which is most of the ones
people actually run a game library on. The static build has no such floor: the
same file runs on CentOS 7, Debian, Ubuntu, Alpine and everything since. Every
crate in the tool is pure Rust, so nothing is given up for it.

**Why a universal macOS binary.** Two separate downloads means a "which Mac do I
have" question that a beginner gets wrong, and an Intel build silently running
under Rosetta on Apple Silicon. `lipo` fuses both into one file, which is also
the only artifact the smoke test has to run.

**Where files land.** Archives keep everything in one directory. The `.deb`,
`.rpm` and Homebrew installs use the FHS layout:

```
/usr/bin/mjolnir                              (or <brew prefix>/bin/mjolnir)
/usr/share/mjolnir/defs/hce/scripting.json
/usr/share/doc/mjolnir/LICENSE
```

The binary looks for its scripting corpus in both layouts by resolving relative
to its own executable, so no packaging-specific code exists anywhere in the tool.

---

## Scoop — already working

Scoop reads manifests straight out of a git repository, which is why this is the
one Windows package manager that needed no account, no submission and no
moderator: the bucket is [`bucket/`](../bucket) in this repository, and the
release workflow commits the new manifest to `main` at the end of a release.

```powershell
scoop bucket add mjolnir https://github.com/devnull9090/mjolnir-core
scoop install mjolnir
```

## Homebrew — already working

A tap is a git repository too, so macOS and Linux get the same deal. The formula
lives in [`HomebrewFormula/`](../HomebrewFormula), which is the directory brew
looks in for a repository that is not *only* a tap.

```bash
brew tap devnull9090/core https://github.com/devnull9090/mjolnir-core
brew install mjolnir
```

The formula serves the universal binary on macOS and the static binary on Linux,
each pinned to that release's SHA-256.

## Debian and RPM packages — already working

Both are built by [fpm](https://fpm.readthedocs.io) from one staged tree, which
is why it is worth a Ruby dependency in CI: the alternative is two packaging
tools that disagree about everything except the file layout.

They are attached to the GitHub release and mirrored on the CDN. They are *not*
in any distribution's repositories — getting into Debian or Fedora proper is a
months-long process with a package maintainer, and it is not something CI can
do. Installing the file directly is the supported route:

```bash
sudo dpkg -i mjolnir_0.1.0_amd64.deb     # Debian, Ubuntu, Mint, Pop!_OS
sudo rpm -i mjolnir-0.1.0-1.x86_64.rpm   # Fedora, RHEL, CentOS, openSUSE
```

## WinGet — one-time setup, then automatic

`winget install MJOLNIRCore.CLI` requires the package to exist in Microsoft's
[winget-pkgs](https://github.com/microsoft/winget-pkgs) repository, which takes a
pull request per release. The workflow raises that PR for you, but it cannot
create the package the first time and it cannot authenticate as you.

**One-time, by a maintainer:**

1. Fork `microsoft/winget-pkgs` to the account that will own the submissions.
2. Create a classic personal access token with the `public_repo` scope, and add
   it to this repository as the secret `WINGET_TOKEN`.
3. Submit the first version by hand, once, from a Windows machine with a CLI
   release already published:

   ```powershell
   winget install wingetcreate
   wingetcreate new https://github.com/devnull9090/mjolnir-core/releases/download/cli-v0.1.0/mjolnir-0.1.0-windows-x64.zip
   ```

   Use the identifier `MJOLNIRCore.CLI` and the moniker `mjolnir`. It is a zip,
   so `wingetcreate` will ask for the nested installer: the type is `portable`
   and the relative path is `mjolnir-<version>-windows-x64\mjolnir.exe`.
   Microsoft reviews new packages; expect a day or two.

After that first submission is merged, every `cli-v*` tag opens its own update
PR automatically and no one has to touch this again.

## Chocolatey — one-time setup, then automatic

`choco install mjolnir-cli` needs the package pushed to chocolatey.org.

**One-time, by a maintainer:**

1. Create an account on [chocolatey.org](https://chocolatey.org), open your
   account page, and copy the API key.
2. Add it to this repository as the secret `CHOCO_API_KEY`.

The first push goes into moderation and a human reads it — that is normal for a
new package, and it is why [`pack.ps1`](chocolatey/pack.ps1) writes a
`VERIFICATION.txt` explaining how to confirm the embedded `mjolnir.exe` against
the published release checksum. Later versions of an approved package are
usually auto-approved.

The binary is embedded in the package rather than downloaded during install. It
is our own MIT-licensed build, so the license allows it, and it means the package
cannot install something other than what the moderator reviewed.

To inspect the package before any of this, on a Windows machine with a release
archive to hand:

```powershell
./packaging/chocolatey/pack.ps1 -ZipDir <folder with the release zip> -Version 0.1.0
```

Without `-Push` it only builds the `.nupkg` and prints where it went.

## Cargo

`cargo install --git https://github.com/devnull9090/mjolnir-core blam-cli`
works today and always has. It is not on crates.io: publishing there would mean
publishing the seven workspace libraries under names nobody would recognise, and
keeping every one of their versions in step for the sake of one binary that
already ships prebuilt.

---

## Not built, and why

- **ARM Linux** (`aarch64-unknown-linux-musl`). One more matrix entry and a
  `ubuntu-24.04-arm` runner. Left out because nobody has asked and every added
  target is another thing that can fail a release; add it the day someone wants
  it.
- **32-bit anything.** The game is 64-bit.
- **AUR, Flatpak, Snap, Nix.** Each is a separate packaging idiom with its own
  review culture, for a command-line tool whose users are already comfortable
  unpacking a tarball. The static binary works everywhere in the meantime.

## What a release actually publishes

For tag `cli-v<version>`:

```
GitHub release
  mjolnir-<version>-windows-x64.zip
  mjolnir-<version>-linux-x64.tar.gz
  mjolnir-<version>-macos-universal.tar.gz
  mjolnir_<version>_amd64.deb
  mjolnir-<version>-1.x86_64.rpm
  checksums-cli-v<version>.txt

releases.mjolnircore.com
  cli/<version>/…                          the same files, kept forever
  cli/latest/mjolnir-windows-x64.zip       stable names for linking
  cli/latest/mjolnir-linux-x64.tar.gz
  cli/latest/mjolnir-macos-universal.tar.gz
  cli/latest/mjolnir-amd64.deb
  cli/latest/mjolnir-x86_64.rpm
  cli/latest/checksums.txt

this repository, on main
  bucket/mjolnir.json                      the Scoop manifest
  HomebrewFormula/mjolnir.rb               the Homebrew formula
```

Each archive holds one directory containing `mjolnir`, `LICENSE`, and
`defs/hce/scripting.json` — the recovered scripting function table that
`mjolnir compile` needs, which the binary looks for next to itself.

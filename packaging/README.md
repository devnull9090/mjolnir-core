# Packaging the CLI

How `mjolnir` reaches a machine that has no Rust toolchain on it.

Everything here is driven by [`.github/workflows/release-cli.yml`](../.github/workflows/release-cli.yml),
which runs on a `cli-v*` tag. Nothing in this directory is built by hand.

| Channel | Command | Set up? | Who has to approve |
| --- | --- | --- | --- |
| GitHub release | download the archive | ✅ works now | nobody |
| CDN | `releases.mjolnircore.com/cli/latest/…` | ✅ works now | nobody |
| Scoop | `scoop install mjolnir` | ✅ works now | nobody |
| WinGet | `winget install MJOLNIRCore.CLI` | needs `WINGET_TOKEN` | Microsoft, per release |
| Chocolatey | `choco install mjolnir-cli` | needs `CHOCO_API_KEY` | Chocolatey, first release |
| Cargo | `cargo install --git …` | ✅ works now | nobody, but needs Rust |

The release workflow skips the WinGet and Chocolatey jobs when their credential
is missing, so a release does not fail over a channel nobody has set up yet.

## Rehearsing a release

Run the **Release CLI** workflow by hand and give it the tag you are about to
push. It runs the changelog gate, checks the tag against the crate version,
builds both platforms and smoke-tests each binary — then stops. Nothing is
released, uploaded, committed or announced.

Worth doing before the first tag, and before any release that changes this
pipeline. A release is the one run everybody is watching, and it should not also
be the first run.

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

The manifest pins the release's download URL and its SHA-256, so an install
either gets exactly what CI built or fails.

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
   wingetcreate new https://github.com/devnull9090/mjolnir-core/releases/download/cli-v0.1.0/mjolnir-0.1.0-x86_64-pc-windows-msvc.zip
   ```

   Use the identifier `MJOLNIRCore.CLI` and the moniker `mjolnir`. It is a zip,
   so `wingetcreate` will ask for the nested installer: the type is `portable`
   and the relative path is `mjolnir-<version>-x86_64-pc-windows-msvc\mjolnir.exe`.
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

## What a release actually publishes

For tag `cli-v<version>`:

```
GitHub release
  mjolnir-<version>-x86_64-pc-windows-msvc.zip
  mjolnir-<version>-x86_64-unknown-linux-gnu.tar.gz
  checksums-cli-v<version>.txt

releases.mjolnircore.com
  cli/<version>/…                       the same files, kept forever
  cli/latest/mjolnir-windows-x64.zip    stable names for linking
  cli/latest/mjolnir-linux-x64.tar.gz
  cli/latest/checksums.txt
```

Each archive holds one directory containing `mjolnir`, `LICENSE`, and
`defs/hce/scripting.json` — the recovered scripting function table that
`mjolnir compile` needs, which the binary looks for next to itself.

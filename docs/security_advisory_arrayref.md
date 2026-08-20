# Security advisory: the `arrayref` 0.3.10 supply-chain attack

On **2026-08-20** a malicious version of the widely used Rust crate `arrayref`
was published to crates.io. This repository briefly depended on it during
development. **No released MJOLNIR artifact is affected**, and the malicious
dependency never reached any branch on the remote. This note exists so the
record is public and so anyone who cloned during development can check.

Upstream advisory:
<https://blog.rust-lang.org/2026/08/20/supply-chain-attack-on-arrayref/>

## What happened

`arrayref` 0.3.10 was published at **07:15:00Z** and removed at **08:41:40Z** —
an 86-minute window. That version declared a dependency on `proc-macro1`, a
typosquat of `proc-macro2`. `proc-macro1`'s `build.rs` reassembled a hardcoded
IP from base64 fragments, disabled TLS certificate validation, downloaded a
platform-specific payload, and executed it detached from Cargo's job object so
the build appeared to succeed normally.

The second stage is a credential-stealing implant with full remote code
execution. It profiles the host — OS, installed applications, browser extension
IDs — and queries each Chrome/Brave/Edge profile's `Login Data` SQLite database
for every saved-login hostname and username. Wiz reports substantial
infrastructure overlap with DPRK-attributed campaigns.

Five other fake crates were published in the same campaign: `proc-macro-en`,
`aovine`, `arone`, `aronenao`, `tinymember`. Related compromised packages were
`append-only-vec` 0.1.9 and `internment` 0.8.7.

## How this repository was exposed

`blake3` was added to the workspace on the `level-authoring` line of work, and
`blake3` depends on `arrayref`. A local `cargo build` at **07:49:29Z** resolved
`arrayref` 0.3.10 inside the exposure window, and the dropper ran on that
developer workstation.

**The poisoned `Cargo.lock` was never pushed.** It existed only in local
commits, which have since been rewritten so no commit reachable from any branch
contains `proc-macro1`. `main` never carried `blake3` or `arrayref` at all.

## What is *not* affected

- **All published releases** — launcher, tag editor, CLI, runtime, code mods.
  The most recent release predates the exposure window by 13 hours.
- **CI runners.** The last workflow run before the window opened was at
  02:00:16Z, over five hours earlier, and no run occurred during or after it.
  No remote branch ever resolved `arrayref`, so CI could not have fetched it.
- **`apps/launcher` and `apps/tag-editor`**, which carry their own lockfiles
  and never contained the dependency.

Note that `proc-macro1`'s malicious behaviour lives entirely in its build
script. It compromises the *build machine*; it does not inject anything into
the compiled output. Even a hypothetical affected build would produce a clean
binary.

## Current state

`main` has no `arrayref` dependency at all — `blake3`, which is what pulls it
in, exists only on the in-progress level-authoring branch. That branch pins
`arrayref` **0.3.9**, the last known-good release, which has no dependencies.

## If you built this repository on 2026-08-20 between 07:15Z and 08:41Z

Treat the machine as compromised.

1. Check for the implant and its persistence:
   - `%APPDATA%\AzureKits\AzureAccount.ps1` (Windows), plus an `AzureAccount`
     entry under `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`
   - a LaunchAgent (macOS) or systemd user service (Linux)
   - `%TEMP%\rust-setup.ps1`, `rust-setup-launch.vbs`, `/tmp/rust-setup`
2. Look for cached copies of the bad crates:
   ```
   ls ~/.cargo/registry/src/*/ | grep -E 'arrayref-0.3.10|proc-macro1'
   ```
3. Rotate every credential reachable from that machine — browser-saved
   passwords, tokens, SSH and signing keys — **from a different machine**.
4. Block egress to `23.254.164.0/23` (Hostwinds).

C2 indicators: `23.254.165.112` ports 9089 and 443, `23.254.167.107:443`,
HTTP `POST /49890878`, AES-128-GCM with the hardcoded key `i am botking`.

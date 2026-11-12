# Credits: keeping them up to date

The Hub's [credits page](https://mjolnircore.com/credits) lists everything
MJOLNIR Core ships, builds with or learned from that somebody else made.
One file feeds it: `hub/src/lib/credits.ts`. A check
(`hub/scripts/test-credits.mts`, part of `pnpm test` in `hub/`, which CI
runs) fails when the list and the tree disagree.

## The rule

Credit goes in with the thing. The change that adds an asset pack, a
vendored binary, ported code or a new foundation library also adds its
entry to `hub/src/lib/credits.ts`. A reviewer who sees a new third-party
thing and no credit sends the change back.

## What needs an entry

| You are adding | Section | Also do |
| --- | --- | --- |
| A content pack to `unreal/MJOLNIRMaterials` whose assets cook into a map | `assets` | Add its `/Game/<Pack>/` folder to the entry's `contentPaths`, and to `COOKED` in `tools/level/foliage_bake.py`. The check ties the two together. |
| A binary we download and redistribute (as UE4SS in `runtime/ue4ss.lock.json`) | `runtime` | Keep its licence file in the bundle if the licence asks for it. |
| Code ported or copied from another project | `runtime` | Add it to the `NOTICE` file at the repository root too, with the files it touches. |
| A library a shipped product is built on (a framework, an engine, a renderer) | `runtime` or `site` | One entry a library. Ordinary transitive dependencies are covered by the "Rust crates" entry and the lockfiles. |
| A tool the build needs that is in no download | `tools` | — |
| A pack or project read for technique, nothing copied | `learned-from` | Say what was learned. If nothing from it ships, `status` stays `"planned"`. |
| A community map, Forge pack or mod made by someone other than its uploader | not this file | Credit the maker in the listing's description on the Hub; the page shows the uploader as author. |

Not listed: the game's own assets (maps refer to them and never carry
them), and anything of ours.

## Writing an entry

- **`name`, `by`, `url`**: as the makers give them. Link the project's own
  page or store listing, not a mirror.
- **`licence`, `licenceUrl`**: read the project's LICENSE file or the
  listing's licence line and copy the name. Do not guess from memory, and
  do not write "free": free to download is not a licence.
- **`use`**: one sentence a player can read, naming where it shows up.
- **`changes`**: required for Creative Commons attribution licences, which
  ask that changes be stated; useful for any port.
- **`status`**: `"planned"` while it is in the tree but in no release, then
  `"shipped"` in the release that first carries it. The page marks planned
  entries "Not in a release yet".

## Before using a pack at all

Check that its licence lets us redistribute cooked assets in a free
download. Creative Commons CC0 and CC BY do. The Fab Standard License's
terms on this have not been read for our case (2026-11-12): until they
are, a Standard License pack is reference only and goes under
`learned-from`. A listing marked "Allows usage with AI: No" stays
unopened by automated tooling until a person decides what that covers.

## Ports of other projects' code

A port also goes in `config/upstream_ports.json`: the source repository,
the source paths we ported from, our files, the scope we carry and the
last source commit checked. A scheduled agent (`cue4parse-nanite-sync`,
Mondays at 9 AM on the development PC) reads it, reviews what the source
changed since, ports what is in scope and opens a pull request that moves
the reviewed commit forward. It never merges. The entry on the credits
page links to our port's file with `derived`.

## Checking

```bash
cd hub && pnpm test
```

`test-credits.mts` fails when an entry lacks a name, maker, link, licence
or use; when a link is not https; when a CC BY entry has no licence link
or no `changes`; when `foliage_bake.py` cooks from a pack folder no entry
claims; and when an entry claims a folder nothing cooks from.

It cannot tell that a licence is stated correctly or that a new
dependency deserves its own entry. Those are for the author and the
reviewer.

## At release time

When a release first carries something marked `"planned"`, change it to
`"shipped"` in the same change that prepares the release, and check the
map's or product's Hub description names the same makers where the
licence asks for attribution alongside the work.

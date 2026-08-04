# Changelog

One entry per tagged release, authored here and read everywhere.

```
changelog/
  products.json          the products that release, and their tag prefixes
  <product>/<version>.md one release
```

`changelog/launcher/0.5.3.md` describes the release tagged `launcher-v0.5.3`.
The product and version are taken from the path, so they cannot disagree with
the tag they document.

## Who reads these

| Surface | What it shows |
| --- | --- |
| mjolnircore.com/changelog | every release, newest first |
| mjolnircore.com/changelog/`<product>`/`<version>` | one release, indexed by search engines |
| mjolnircore.com/changelog/rss.xml | the feed |
| `/api/changelog` | JSON, for anything that is not the website |
| Launcher | a "What's new" modal after an update completes |
| Tag editor | the same modal, on first run after it updates itself |
| GitHub release notes | the body of the release the tag creates |
| Discord | the announcement embed |

They are written once, here, because the alternative is writing them five times
and having five slightly different accounts of the same release.

## Format

````markdown
# Verifies author-signed mod archives

**Date:** 2026-08-02
**Summary:** The launcher now refuses a mod archive whose author signature does not verify, and pins each mod's signing key.

### Added

- Something a player can now do.

### Fixed

- Something that was broken and now is not.
````

- **`# Title`** — the headline, in plain language. It becomes the page `<h1>`,
  the `<title>`, the modal header and the Discord embed title. Say what changed,
  not "v0.5.3". Present tense, no trailing full stop.
- **`**Date:**`** — `YYYY-MM-DD`, the day the tag was pushed.
- **`**Summary:**`** — one sentence. It is the meta description, the RSS
  description and the modal's opening line, so write it for someone who has
  never used the thing. Aim for 100–160 characters: search engines truncate
  around there. Over 200 is rejected.
- **Sections** — `### Added`, `### Changed`, `### Fixed`, `### Security`,
  `### Known issues`. Use the ones that apply, in that order. Bullets are
  sentences, not commit subjects.

Everything else is ordinary Markdown and renders on the hub.

## Writing for a player, not for us

The entry is public. It is the first thing a search engine and a new player
read about a release.

- **Lead with what someone can now do.** "Play the game's audio in the editor",
  not "add a Wwise Vorbis decoder to the tag editor".
- **Name the visible symptom in a fix.** "0.6.0 could not play audio in a
  packaged build" tells a player whether it affected them. "Fix CSP" does not.
- **Say when a release does nothing for players.** A pipeline-only release
  should say so in one line. Inventing features for it is worse than a boring
  entry, and the history is public anyway.
- **Say when someone has to act.** A build existing installs cannot auto-update
  to, a manual reinstall, a migration — put it in the summary, not the fourth
  bullet.
- **No internal shorthand.** Tag paths, crate names and PR numbers belong in
  the commit body. If a detail is genuinely load-bearing, explain it.

## Releasing

1. Write `changelog/<product>/<version>.md`.
2. Bump the version in the product's manifest, in the same commit.
3. Merge, then tag.

`scripts/check-changelog.mjs` runs first in every release workflow and fails the
release if the pushed tag has no entry, so a release without one cannot ship.
Run it yourself before tagging:

```bash
node scripts/check-changelog.mjs launcher-v0.5.4
```

The hub snapshots these files into `hub/src/generated/changelog.json` on every
build, and CI fails if that snapshot is stale — same contract as `docs/`.

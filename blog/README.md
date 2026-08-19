# Blog

Posts for [mjolnircore.com/blog](https://mjolnircore.com/blog). One Markdown
file per post; `hub/scripts/sync-blog.mjs` snapshots the directory into the hub
at build time, and a malformed post fails the build rather than publishing half
of itself.

## Format

The file name is `YYYY-MM-DD-slug.md` — the date lives there and nowhere else,
so it cannot disagree with itself. The slug becomes the URL.

```markdown
# Post title

**Author:** MJOLNIR Core
**Summary:** One or two sentences, under 300 characters. This is the card
text, the RSS description and the meta description.
**Tags:** game-update, cu4

Body Markdown starts after the meta block...
```

`**Author:**` and `**Tags:**` are optional; `**Summary:**` is required.

## Game-update posts

The recurring post here is "what did this game update change", produced by the
update pipeline — see `docs/game_update_pipeline.md` and the
`game-update-report` skill. Everything in one of those posts must come from a
measurement the pipeline actually took (`tools/game_snapshot.py diff`,
`mjolnir tagdiff`, `tools/pe/aob_scan.py`); a claim without a measurement
behind it does not ship.

# Blog

Posts for [mjolnircore.com/blog](https://mjolnircore.com/blog). One Markdown
file per post; `hub/scripts/sync-blog.mjs` snapshots the directory into the hub
at build time, and a malformed post fails the build rather than publishing half
of itself.

## Format

The file name is `YYYY-MM-DD-slug.md` — the date lives there and nowhere else,
so it cannot disagree with itself. The slug becomes the URL. For a game-update
post the date is the day the update shipped on Steam (per SteamDB's build
history), not the day the post was written — the page dates itself by the event
it documents.

```markdown
# Post title

**Author:** MJOLNIR Core
**Summary:** One or two sentences, under 300 characters. This is the card
text, the RSS description and the meta description.
**Tags:** game-update, cu4
**Image:** /blog-images/slug/featured.jpg

Body Markdown starts after the meta block...
```

`**Author:**`, `**Tags:**` and `**Image:**` are optional; `**Summary:**` is
required. `**Image:**` is the link-preview picture (`og:image` and the wide
Twitter/Discord card): a 1200×630 file under `hub/public`, which the build
checks exists. Each
tag becomes a filter page at `/blog/tag/<tag>`, so tags are held to slug
grammar (lowercase letters, digits, hyphens) and the build fails otherwise.
Reuse existing tags before inventing one: `game-update` marks every update
report, `cu3`/`cu4`/… pin the specific update, `tag-data` marks posts built on
the tag-diff pipeline.

## Game-update posts

The recurring post here is "what did this game update change", produced by the
update pipeline — see `docs/game_update_pipeline.md` and the
`game-update-report` skill. Everything in one of those posts must come from a
measurement the pipeline actually took (`tools/game_snapshot.py diff`,
`mjolnir tagdiff`, `tools/pe/aob_scan.py`); a claim without a measurement
behind it does not ship.

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
**Summary:** One or two sentences, under 300 characters, on one line. This is the card text, the RSS description and the meta description.
**Tags:** game-update, cu4
**Image:** /blog-images/slug/featured.jpg

Body Markdown starts after the meta block...
```

`**Author:**`, `**Tags:**` and `**Image:**` are optional; `**Summary:**` is
required. Each value is one line: the block ends at the first blank line or the
first line that is not `**Label:** value`, so a wrapped summary pushes the
lines below it into the body.
`**Image:**` is the featured image: the link preview (`og:image` and
the wide Twitter/Discord card), the picture at the top of the post, and the
post's thumbnail on `/blog` and the tag pages. It is the site path of a 1200×630
`.jpg`, `.png` or `.webp` under `hub/public`, which the build checks exists;
its HTML source goes in `blog/featured/<slug>.html`, with the render command
in the file's header comment. Each
tag becomes a filter page at `/blog/tag/<tag>`, so tags are held to slug
grammar (lowercase letters, digits, hyphens) and the build fails otherwise.
Reuse existing tags before inventing one: `game-update` marks every update
report, `cu3`/`cu4`/… pin the specific update, `tag-data` marks posts built on
the tag-diff pipeline. `multiplayer` and `maps` mark the classic-map posts,
`lighting` the ones that cover how those maps are lit, and `alpha` the alpha
announcement.

New post images go in `hub/public/blog-images/<slug>/`. An image whose path
ends `?before=<path>`, as in
`![alt](/blog-images/<slug>/after.jpg?before=/blog-images/<slug>/before.jpg)`,
draws a before-and-after slider.

## Game-update posts

The recurring post here is "what did this game update change", produced by the
update pipeline — see `docs/game_update_pipeline.md` and the
`game-update-report` skill. Everything in one of those posts must come from a
measurement the pipeline actually took (`tools/game_snapshot.py diff`,
`mjolnir tagdiff`, `tools/pe/aob_scan.py`); a claim without a measurement
behind it does not ship.

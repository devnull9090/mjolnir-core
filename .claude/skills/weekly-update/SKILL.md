---
name: weekly-update
description: Draft the weekly community update for mjolnircore.com/blog and its X post — gather what shipped since the last one, verify every claim, add screenshots and doc links, and open a PR for review. Use when the weekly reminder fires, or when the user asks for the weekly update, a community update, or a recap of recent work.
---

# Weekly update

One post a week for players, map makers and modders: what changed, why it matters to
them, and where to read more. Readers are not following the repository. A commit title
is raw material, never finished text.

**Two rules make the post trustworthy.** Every claim traces to a changelog entry or a
pull request, and nothing goes in unless it has reached players. The post is a draft
until the user merges its PR, because merging to `main` deploys the blog. Never merge,
tag, publish to the hub, or post to X from this skill.

## 1. Gather

```bash
python tools/weekly/weekly_update.py gather --out <scratchpad>/digest.md
```

It starts from the newest `weekly-update` post. Pass `--since YYYY-MM-DD` for any other
window. Read the changelog entry behind each release in the digest, not only its summary
line. The digest flags a PR with no tag behind it, but an unmarked PR may only be behind
another product's tag, so check the release that really carries it. Maps and Forge packs
ship on the hub rather than in tags: confirm a map is published before announcing it.

## 2. Decide what readers care about

Group by what players experience, not by product or PR. Lead with the largest thing they
can try today.

- **Keep:** new features, maps, Forge packs and mods, fixes to bugs players met, new or
  rewritten guides, performance they can feel.
- **Drop:** test-machine tooling, CI, deploy plumbing, refactors, dependency updates
  (one line at most, when they matter).
- **Hold:** merged but unreleased work, held maps and design documents. Do not tease them
  unless the user asks.
- **Link, do not repeat:** anything that already has its own post. The digest lists them.

Public text never carries: private repository names or links, the name in the
public-text naming memory if your memory has it, how layout files are validated
beyond "checks layouts and refuses malformed ones", decompiled addresses, or weaknesses
in the game itself. Personal news about the user stays out unless they write it.

For a large window, run one agent per theme and a skeptic per theme that tries to refute
each claim against its source, then a critic that compares the result with the raw digest.

## 3. Screenshots

Every section with something to see gets a picture. Cheapest first:

1. **Already in the repo:** `hub/public/blog-images`, `hub/public/docs-images`. Reuse by
   site path. Credit nothing as new if it is not.
2. **The hub:** the `hub` launch configuration and the browser pane. The dev server has
   no production data, so shoot pages that hold real content on mjolnircore.com instead.
3. **The game:** `mjolnir-game` tools, when the user is around or has said the game is
   free. An unattended run skips this step and lists the shots it wants in the PR body.
   Launch with `windowed: false` over Steam, press Enter alone after about 18 s, wait for
   `MULTIPLAYER is on the main menu` in the log, then `mjolnir_auto host <CODE> <mode> private`.
   Always host private. Confirm `mj.world()` before shooting, and focus the window first.

Save as `hub/public/blog-images/<slug>/<name>.webp` or `.jpg`, under about 400 KB. Caption
each with what it shows, and label renders as renders.

## 4. Write

`blog/YYYY-MM-DD-weekly-update-<n>.md`, dated the day it goes out, in the format in
`blog/README.md`, tagged `weekly-update` plus topic tags already in use.

- Open with two or three plain sentences on the week. No hype words.
- A short **"Try this week"** list near the top: the things to go and do.
- `##` sections by theme, each saying what changed for the reader, then the picture, then
  links. Version numbers appear once, in a closing table with changelog links.
- Doc links come from the digest. Pages on the site use site paths; the rest use GitHub.
- End with how to get the update and where to report problems.

Featured image: 1200×630 under `hub/public/blog-images/<slug>/`, its HTML source at
`blog/featured/<slug>.html`, with the render command in the file's header comment.

## 5. X post

`blog/social/<slug>.x.txt`: at most 280 characters as X counts them, the headline changes,
and `https://mjolnircore.com/blog/<slug>`. The post's featured image is the link card. Plain
text only. A longer thread, if there is enough to say, goes below a `---` line in
`blog/social/<slug>.thread.txt`. The user posts it themselves.

## 6. Check and open the PR

```bash
python tools/weekly/weekly_update.py check blog/YYYY-MM-DD-weekly-update-<n>.md
```

```bash
pnpm --dir hub sync
```

```bash
pnpm --dir hub sync:check
```

Commit the post, its images and `hub/src/generated/blog.json`. Open the blog page in the hub
preview and look at it, then push a branch and open a PR through `devnull9090`. Leave it
unmerged. The PR body says which shots are missing and which claims need the user's eye.

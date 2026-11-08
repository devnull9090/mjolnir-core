---
name: weekly-update
description: Draft the Saturday community update for mjolnircore.com/blog and its X post — that evening's playtest with what to test, then what shipped since the last one, with every claim verified, screenshots and doc links, in a PR for review. Use when the weekly reminder fires, or when the user asks for the weekly update, a community update, or a recap of recent work.
---

# Weekly update

One post every Saturday for players, map makers and modders: when that evening's playtest is
and what we need tested, what changed and why it matters to them, and where to read more.
Readers are not following the repository. A commit title is raw material, never finished
text.

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

The digest also carries the playtest's time, read from the Discord event, as Markdown ready
to paste. If it couldn't reach Discord, open the event and write the time by hand. Never
work the time out yourself: the event is the source. The same event repeats weekly, so its
link doesn't change.

## 2. Decide what to test

This section is the reason the post goes out on the day of the playtest, so write it first.
Start from the newest `docs/playtest_*.md`, the newest `docs/two_pc_run_*.md` and the
digest's known issues: whatever has only run on one PC,
needs a second player, or shipped this week and hasn't been played. Ask the user which map
to start on if the list doesn't make it clear.

- Order it by what matters most, with the least tested first.
- Say what should happen, so a player can tell when it doesn't.
- Leave out host-only setup such as bot counts or private games. Readers are joining.
- Keep it to about nine items, and link the full checklist if there is one.
- Say what to update first, and warn about a large download.

## 3. Decide what readers care about

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

## 4. Screenshots

Every section with something to see gets a picture. Cheapest first:

1. **Already in the repo:** `hub/public/blog-images`, `hub/public/docs-images`. Reuse by
   site path. Credit nothing as new if it is not.
2. **The hub:** the `hub` launch configuration and the browser pane. The dev server has
   no production data, so shoot pages that hold real content on mjolnircore.com instead.
   Leaderboards and match pages show real players' names, so link them rather than
   picture them. Headless Chrome with `--force-device-scale-factor=1.5` gives a sharper
   frame than the pane.
3. **The game:** `mjolnir-game` tools, when the user is around or has said the game is
   free. An unattended run skips this step and lists the shots it wants in the PR body.
   `node tools/remote/pc1.mjs launch`, then `menu`, then
   `console 'mjolnir_auto host <CODE> <mode> private'`: no keys or mouse needed. Always host
   private, and confirm `mj.world()` before shooting. `tools/mcp/game/capture.ps1
   -ForceForeground -MaxWidth 3840` takes the frame.
   - **Getting there:** teleport the player, and wait 30 s before any input. Off a known
     floor, a teleport is a fatal fall.
   - **Vehicle shots:** `mjolnir_camera set <name> <x y z pitch yaw roll fov>`, then `goto`.
     It hides the HUD, but the simulation only wakes objects near the player, so move the
     player beside the vehicle first.
   - **Menus:** call the screen's own `MJ_Event` from Lua, such as `lobby:MJ_Event("gametype")`
     or `screen:MJ_Event("variant:1")`, rather than clicking.
   - **Markers:** a marker fades over the crosshair, so turn a little to one side.

Save as `hub/public/blog-images/<slug>/<name>.webp` or `.jpg`, 1600 wide and under about
400 KB. Caption each with what it shows, and label renders as renders.

## 5. Write

`blog/YYYY-MM-DD-weekly-update-<n>.md`, dated the Saturday it goes out, in the format in
`blog/README.md`, tagged `weekly-update` plus topic tags already in use.

- Open with two or three plain sentences on the week. No hype words.
- `## Saturday's playtest` comes next, with **When**, **Join us** and **Watch** lines: the
  time as the digest gives it, the Discord event, and the Twitch stream. Say the date,
  never "tonight". Under it, `### Before you join` and `### What to test`.
- `##` sections by theme, each saying what changed for the reader, then the picture, then
  links. Version numbers appear once, in a closing table with changelog links.
- Doc links come from the digest. Pages on the site use site paths; the rest use GitHub.
- End with the playtest again: how to update, how to join, and where to report problems.

The time link's title is what makes the hub show it in the reader's own zone, so keep it as
the digest writes it (`blog/README.md` has the format).

Featured image: 1200×630 under `hub/public/blog-images/<slug>/`, its HTML source at
`blog/featured/<slug>.html`, with the render command in the file's header comment.

## 6. X post

`blog/social/<slug>.x.txt`: at most 280 characters as X counts them, the headline changes,
the playtest's day and time, the Twitch link, and `https://mjolnircore.com/blog/<slug>`. The
post's featured image is the link card. Plain text only. A longer thread, if there is enough
to say, goes below a `---` line in `blog/social/<slug>.thread.txt`. The user posts it
themselves.

## 7. Check and open the PR

```bash
python tools/weekly/weekly_update.py check blog/YYYY-MM-DD-weekly-update-<n>.md
```

`check` fails if the time, the event link, the stream link or the test list is missing, or
if the time isn't the playtest after the post's date. Add `--no-playtest` only for a week
the user has said has none.

```bash
pnpm --dir hub sync
```

```bash
pnpm --dir hub sync:check
```

Commit the post, its images and `hub/src/generated/blog.json`. Open the blog page in the hub
preview and look at it, then push a branch and open a PR through `devnull9090`. Leave it
unmerged. The PR body says which shots are missing and which claims need the user's eye.
The post has to be live before the playtest at 6 PM MST that evening, so say so in the PR.

# Making Your First Mod

**Goal:** turn a tag edit into a mod on the hub that anyone can install, rate and play
**Time:** about fifteen minutes once the Tag Editor is installed
**You need:** the MJOLNIR Tag Editor (installed from the launcher's Tools tab), and a
[mjolnircore.com](https://mjolnircore.com) account (Discord sign-in) if you want to publish

This is the whole path — edit, test in game, publish — without leaving the Tag Editor.
The [getting started guide](getting_started.md) walks the same road with the command-line
tools; you do not need any of that here.

## What a mod is

A mod is a **recipe**: which tags change, which fields, and what they become. The Tag
Editor keeps that recipe in a folder you choose — the *mod project* — as two small JSON
files you can read, diff and put in git:

```
mod.json       what the mod is: name, slug, version, summary
edits.json     what it changes: one entry per edited field
README.md      yours to write; it ships with the mod
build/         baked containers and the .mjolnir archive (generated)
```

Because the recipe names tags and fields rather than byte offsets, it survives game
updates: the editor re-applies it against whatever your installation ships and tells you
if anything no longer lines up.

## 1. Start a mod

Open the Tag Editor and switch the left panel to the **mod** tab. Click **New mod…**,
give it a name (the hub address — the *slug* — fills itself in), and choose an empty
folder to keep it in.

Any edits you had already made carry over into the new mod, so it is fine to experiment
first and decide it is a mod later.

The project autosaves on every edit, and reopens automatically the next time you launch
the editor.

## 2. Edit tags

Browse to a tag and change values the way the [tag editing guide](tag_editing_guide.md)
describes: click, type, Enter. Ammunition counts, damage, physics, projectile speeds —
anything with a fixed-width value edits cleanly and works in game.

Every accepted edit lands in the mod panel's **Changes** list, shown as
`shipped value → your value` with a revert button per line. That list *is* your mod.

Two things to know:

- **Stick to values the game already knows.** Numbers are always safe, and so are tag
  references that point at other shipped tags — even ones that change the payload's length
  (that path is verified in game; ask the assault rifle that fires needler shards). The
  exception is **string id** fields: text the game has never seen makes it reject the whole
  tag, and the object simply vanishes in game. The editor warns you when a mod edits one —
  always test in game before sharing.
- If a game update removes a tag or field you edited, the change list flags it **missing**
  and export refuses until you revert it. Your mod never silently ships half its recipe.

## 3. Test it in game

Click **Test in game**. The editor bakes your recipe into an override container, verifies
it by reading it back the way the game would, and installs it into your Paks folder
(files named `pakchunk999-MJOLNIRDEV-…`, loaded after everything else).

Launch the game and look at your change. When you are done, **Remove test install** puts
your installation back exactly as it was — those files are the only thing the editor ever
writes there.

Edited more? **Update test install** re-bakes and replaces it. (Close the game first;
Windows will not let files it holds open be replaced.)

## 4. Share it

**Export .mjolnir archive** writes `build/<slug>-<version>.mjolnir` — a zip holding the
manifest and the baked containers, in exactly the format the hub validates
([the spec](mjolnir_format.md)). Anyone can install that file's published version through
the launcher's hub tab; you can also hand it to a friend directly.

One honest caveat: a baked container includes data derived from the game's own tags.
Share your mod through the hub or with people who own the game — and the recipe files
themselves (`mod.json`, `edits.json`) are always safe to share anywhere, which is one
reason they exist.

## 5. Publish to the hub

Publishing runs from the mod panel's **Publish** section:

1. **Get an API key** (first time only). The panel links to your hub account page —
   create a key with the `mods:write` scope and paste it in. It is stored on your machine
   only. Publishing is deliberately not enabled for the launcher's device pairing; the
   key is your explicit opt-in.
2. Optionally write a changelog for this version.
3. Click **Publish**. The editor bakes a fresh archive, uploads it, and the hub scans it —
   checking the zip layout, the manifest, and every container — then indexes which chunks
   your mod overrides so conflicts with other mods are visible on its page.

The verdict comes back into the panel: **published**, with a link to your mod's page — or
**rejected**, with the scanner's findings telling you exactly what to fix.

To ship an update: bump the **version** in the mod panel (each version publishes once),
make your changes, publish again. Players see the update in their launcher.

## Where this is going

- **Texture swaps** are the most-requested next step; the editor can view and export
  textures today, and replacement is designed but not built.
- **Recipe distribution**: because mods are authored as recipes, the hub will eventually
  ship the recipe itself and let each player's launcher bake it locally against their own
  installation — smaller downloads, cleaner updates, and no game bytes in the archive.

Questions, or something in this guide did not match what you saw? Say so on the Discord —
this path is new and reports make it better.

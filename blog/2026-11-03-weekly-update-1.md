# Weekly update 1: AI bots, Halo 2 maps, Forge and everything since October 17

**Author:** MJOLNIR Core
**Summary:** Our first weekly update catches up on two and a half busy weeks: AI bots, all 25 Halo 2 maps, Forge, Team Slayer, match chat, Discord presence, a smarter launcher, faster map loads and a long list of fixes.
**Tags:** weekly-update, multiplayer, maps, forge
**Image:** /blog-images/weekly-update-1/featured.jpg

A lot of what we build disappears into changelogs, so starting today we will post an update every week: what changed, what to try, and where to read more.

This first one is a catch-up. Our last general update was [the remastered maps](/blog/ce-maps-remastered) on October 17, and a great deal has landed since. Multiplayer now has bots and 25 more maps, and you can build your own layouts in Forge.

## Try this week

Update the [launcher](/download) first. It installs everything else you need. Then:

1. **Fill a match with bots.** Host any map, open the game settings, and set BOTS on the PLAYERS page.
2. **Install the Halo 2 maps** with the Install Halo 2 maps button on the launcher's Multiplayer page.
3. **Play Team Slayer or CTF** with a few friends, now that team games start properly with three or more players.
4. **Build something in Forge.** Start with [your first Forge build](/docs/guides/forge-guide).
5. **Say hello in match chat.** Press T.

## AI bots in multiplayer

You no longer need a full fireteam to play. The host can add up to 15 bots from the PLAYERS page of the game settings, choosing Spartans, Elites, Grunts, Jackals or a mix, at Normal, Heroic or Legendary. They have names, appear on the scoreboard and in the kill feed, and respawn 5 seconds after they die. Spartan bots wear classic armour and carry a mixed arsenal, including the sniper rifle and rocket launcher where the map has them.

![A Team Slayer scoreboard on Blood Gulch with named bots on the red and blue teams, and the first kill on the board.](/blog-images/weekly-update-1/bots-scoreboard.jpg)

In team games, bots play for red and blue. Each one joins the side with fewer players, leaves its teammates alone, and fights the other side. Their kills count toward the team score, and a player who kills a bot on their own side is charged with a betrayal. Bots also come in near their own side, spread out across the map, and no longer stand still for minutes while taking fire. In Free for All they hunt players but don't fight each other.

The host can change bots mid-match in chat: `/bots 6 elites heroic`.

![A blue Spartan bot crossing the long grass at Blood Gulch.](/blog-images/weekly-update-1/bots-blood-gulch.jpg)

Bots work on all nineteen classic maps, all 25 Halo 2 maps, Yoyorast Island, Coldsnap and Night Lockout. Make sure your maps are up to date, because the BOTS setting does nothing on an older release.

**What bots can't do yet:** they walk, but they don't jump, ride lifts or use teleporters. On maps whose floors are joined only that way, such as Lockout, Boarding Action and Chiron TL-34, they stay near where they spawn. On Gemini they can't cross between the islands. Night Lockout's bots play its lower level only. The new Forge maps don't have bots yet.

Map makers can add bots to their own levels with [CLI 0.7.0](/changelog/cli/0.7.0) and the `blam.bots` section of the [level format](/docs/notes/level-format).

## All 25 Halo 2 multiplayer maps

Ascension, Backwash, Beaver Creek, Burial Mounds, Coagulation, Colossus, Containment, Desolation, District, Elongation, Foundation, Gemini, Headlong, Ivory Tower, Lockout, Midship, Relic, Sanctuary, Terminal, Tombstone, Turf, Uplift, Warlock, Waterworks and Zanzibar are all [on the Hub](/maps).

![Lockout in Halo Campaign Evolved, looking across the gap between the towers.](/blog-images/weekly-update-1/lockout.jpg)

![Zanzibar from above, with its turning wheel, sea wall and beach.](/blog-images/weekly-update-1/h2-zanzibar.jpg)

![Uplift's beach and bridge beneath the canyon, with the beam firing into the sky.](/blog-images/weekly-update-1/h2-uplift.jpg)

![Midship, the Covenant ship, from outside.](/blog-images/weekly-update-1/h2-midship.jpg)

![Containment's snowy valley from above.](/blog-images/weekly-update-1/h2-containment.jpg)

Each one offers Slayer and CTF, and the set is an optional download of about 586 MB. Moving scenery turns as it should, with working collision: Zanzibar's wheel, Ascension's antennas and Foundation's fans.

**New on November 4:** gravity lifts, jump pads and vents now work on the 14 Halo 2 maps that have them, in version 1.3.0 of those maps, so update your maps to get them. They've had less testing than we'd like, so please tell us if one throws you somewhere odd. Doors and other sliding parts don't move yet. The story of how these maps were made is in [How 25 Halo 2 maps came to Campaign Evolved](/blog/halo-2-maps).

Hosts no longer need every map installed first. SELECT MAP lists up to 80 maps, including Hub maps you don't have yet, marked DOWNLOAD. Chips filter by game and source, and a search box finds a map by name, code or game.

## Forge

Forge arrived on October 24 as a way to move a map's objects around. Ten days later, you can place new objects from the map's palette, set their team, label, respawn time and spawn order, and save your work. **F5** saves a layout, **F6** loads it, and **F2** goes back to the map's own. A saved layout starts every game you host on that map, in Slayer and CTF as well as Forge, and players who join see your objects.

![Crossline from above, built from the Foundry Wide kit.](/blog-images/forge-building/crossline-overview.webp)

Modular kits followed on November 3: Foundry, Foundry Wide and Roadworks, along with the Crossline, Forge Canvas and Roadworks Circuit maps. [Build your own battleground](/blog/forge-building) is the full tour, and there is a [pack workshop](/forge) on the Hub.

New since that post: automatic doors now open in Slayer and every other mode, not just Forge. Forge also checks saved layouts and refuses malformed ones, with the reason. The launcher now keeps a map's packs in place, and installs any packs a saved layout needs before you launch.

Forge comes from the [MJOLNIRForge mod](/mods/mjolnir-forge) on the Hub, so install it there if FORGE isn't in your list of game types. Editing is host only for now.

Reference: [Forge controls](/docs/notes/forge), [your first Forge build](/docs/guides/forge-guide), and [create a community Forge pack](/docs/guides/forge-pack-authoring).

## Game types and the lobby

- **Team Slayer** is new: Red against Blue on every map with Slayer. Teammate kills cost a point.
- **CTF flags** now carry Halo CE's red cobra and blue eagle banners, and they keep their colours when dropped or carried.
- **Team armour** is cleaner: CTF and Team Slayer put everyone in Mk V Classic in their team colour. Slayer still keeps your own armour.
- **GAME TYPE** has its own screen with icons, descriptions and team formats.
- **The lobby** shows the map and game type as two tiles side by side, with changed settings listed below.

## Match chat, Discord and the post-game vote

Press **T** for all chat or **Y** for team chat. Type `/` to see the commands you can use, and Tab completes them. Hosts get `/kick`, `/ban` and `/unban`. Chat shows its rules the first time you open it. It is logged to your player account, and a public match's chat appears on its Hub page.

Discord now shows you playing MJOLNIR Core, with your map, game type and session time. Public games with room can offer **Join Game** on your Discord profile, which can even start the game if it's closed. You'll need the Discord desktop app with activity sharing on. Joining from a second Discord account hasn't been fully verified yet, so tell us how it goes.

![The post-game screen: final standings on the left, and four map tiles to vote on with a countdown on the right. The scores here were filled in for this picture.](/blog-images/weekly-update-1/post-game-vote.jpg)

The post-game vote is now a grid of tiles with each map's picture, game type and votes. It mixes game types, so you won't get four Slayers in a row, and it only offers maps everyone has or can download. The screen also no longer stutters.

The kill feed got a full rebuild too. Rows are animated, with avatars, the game's own weapon icons, and medals from Double Kill to Killionaire. The score is now two bars that fill toward the win.

## Fixes for playing together

Most of these came straight from our October 24 playtest. Thank you to everyone who played.

- CTF and Team Slayer no longer end the moment the map loads with three or more players.
- A player rejoining after a drop no longer takes the whole fireteam down with them.
- Players who join a match in progress now hear reloads, grenades, melee and equipment, including after leaving and rejoining.
- New players no longer inherit the score of whoever left their seat.
- Fixed crashes at the start of a second match and when quitting soon after a match.
- A killing spree arriving just after a Triple Kill no longer leaves a medal stuck on screen.
- The scoreboard marks who is dead until they respawn.
- Falling into Gephyrophobia's canyon kills you again.

**Still open:** joiners crashing on a map change. We removed one likely cause, but we aren't calling it fixed until a longer playtest confirms it. [Issue #262](https://github.com/devnull9090/mjolnir-core/issues/262) tracks it.

## Smoother, faster maps

The remastered maps got a lot of attention after launch.

- **A steady stutter is gone** from the remastered maps. Walking the same route on Death Island, long frames fell from 269 in 44 seconds to 28 in 52 seconds.
- **Loading hitches shrank.** Grass, rocks and trees are now built into the map instead of placed as it loads. On Death Island, the longest frame during loading fell from 15.5 seconds to under a second. The downloads are bigger as a result.
- **Grass stopped drawing across the whole map.** Some bands never culled at any distance. Wind is now off at Low and Medium foliage, so if a remastered map runs slowly, try lowering Foliage in Video settings.
- **Occasional script stutters are gone.** The worst frame in our Death Island test fell from 54 ms to 17 ms. That test was on one PC, standing still.
- **Rivers start full.** Battle Creek's and Timberland's rivers no longer take up to a minute to fill.
- **Bullets now stop on Death Island's swapped trees and rocks**, and grass grows right up to the rocks.

These figures come from our own test PC, so your results will vary. To help us see other hardware, type `/bench` in match chat. It takes about a minute and sends us the timings with your GPU and settings. If a map stutters for you, send us the `hitches.log` file from the MJOLNIRHud folder.

## A launcher that keeps you ready to play

Fireteam games need everyone on the same versions, so the launcher now handles that for you.

- **Launch checks first.** It looks at your mods, runtime and maps, and lists anything out of date or damaged. The file check takes under a second.
- **It updates itself first**, then offers Update and launch or Cancel. Being offline never blocks a launch.
- **The game tells you too.** The main menu shows what's out of date, with UPDATE AND RESTART or NOT NOW.
- **Other mods can step aside.** Mods MJOLNIR didn't install can break a game for the whole fireteam, so the launcher offers to move them aside while you play. They come back afterwards, and nothing is deleted.
- **Intro videos are skipped by default.** On our test PC, the main menu arrived in 28 seconds instead of 49. The switch is under Settings > Troubleshooting.
- **Crash reports are opt-in.** After a crash, the launcher asks whether to send a report. Nothing goes unless you click Send report, and What's sent? shows exactly what's included.

## The Hub

![The redesigned maps page on mjolnircore.com, with filters for game mode, game, size and vehicles.](/blog-images/weekly-update-1/hub-maps.jpg)

The [Hub](/maps) has a new look, with shared cards and filters across maps, mods, players and games. The maps page can now filter by Halo CE or Halo 2. [Match history](/matches) has moved to cards with map art, winners and the top three. It lists real matches by default, and an All matches toggle shows the rest. Match pages have a new header and a ranked scoreboard.

## For modders and map makers

- **Scripts in baked levels now load.** They were being dropped at load time. [CLI 0.7.0](/changelog/cli/0.7.0) fixes this and lets a level bring its own scripts. Published maps change only when they're baked again, so test with a joiner before you release.
- **Megalo game types:** `mjolnir megalo dump` reads any game type, and `megalo validate` checks that the game can load one safely ([CLI 0.5.0](/changelog/cli/0.5.0)).
- **Three cheats are back:** `cheat_all_weapons`, `cheat_all_vehicles` and `drop_safe` work with the [MJOLNIRBlamConsole mod](/mods/mjolnir-blam-console). They've been tested in solo campaign only.
- **The docs were audited** against the code on October 21, which fixed 76 broken links. See the updated guides for [tag editing](/docs/guides/tag-editing-guide), [your first mod](/docs/guides/making-your-first-mod), [texture swapping](/docs/guides/texture-swapping) and [custom levels](/docs/guides/level-authoring).

## Versions

| Product | Now at | Notes |
| --- | --- | --- |
| Launcher | [0.21.0](/changelog/launcher/0.21.0) | From 0.14.0 |
| Code mods | [0.43.1](/changelog/mods/0.43.1) | From 0.24.0 |
| CE runtime | 1.17.0 | The launcher installs it |
| CLI | [0.7.0](/changelog/cli/0.7.0) | Scoop and Homebrew are still on 0.6.0 |
| Tag editor | [0.25.0](/changelog/tag-editor/0.25.0) | From 0.24.0 |

Every release is listed in the [changelog](/changelog).

## Tell us what you find

Grab the [latest launcher](/download), play a few matches, and tell us what breaks in our [Discord](https://discord.gg/9gxYZsByW9). See you next week.

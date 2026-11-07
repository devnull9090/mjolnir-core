# Weekly update 2: Assault, King of the Hill and Saturday's playtest

**Author:** MJOLNIR Core
**Summary:** Assault, King, Oddball and Race reach the maps, a marker points you to the objective, and Yoyorast Island gets the Mongoose. Most of it has never been played by two people, so join Saturday's playtest and help us find what breaks.
**Tags:** weekly-update, multiplayer, maps, forge
**Image:** /blog-images/weekly-update-2/featured.jpg

Weekly updates now come out on Fridays, the day before our playtest, so each one can tell you what's new and what we most need tested.

This was a big week. Assault completes Halo CE's Standard game types, and 46 maps were updated to offer them. Nearly all of it has only ever run on one PC, so this Saturday matters more than most.

## Saturday's playtest

- **When:** [Saturday, November 7, 6 PM MST](https://discord.gg/AQnRCHbmXq?event=1556902193548886056 "2026-11-08T01:00:00Z")
- **Join us:** the [Discord event](https://discord.gg/AQnRCHbmXq?event=1556902193548886056). Click Interested and Discord will tell you when it starts.
- **Watch:** [twitch.tv/devnull9090](https://www.twitch.tv/devnull9090)

We play every Saturday at this time, so if you can't make this one, come to the next.

### Before you join

1. **Open the [launcher](/download) early and let it update.** It brings your mods and maps up to date. This week's map updates come to about 1.5 GB if you have every map.
2. **Install [Yoyorast Island](/mods/ce-yoyorast-island-v2) and check it says 2.7.1.** Earlier versions don't have the map's gates and buttons.

### What to test

We'll start on Yoyorast Island and work down the list. All of this needs real players, because bots can't hold a hill, carry a ball or take over as the Juggernaut.

1. **Joining.** Everyone loads in and sees the same score. Everyone sees the two Mongooses at the top of the ramp, and a joiner hears a vehicle's engine and sees it move.
2. **Gates, shields and teleporters.** Nobody has used these with a second player yet. Press a button as a joiner. Does the gate rise for everyone, block players and vehicles, and drop after 60 seconds? Does a panic shield come up, block, and drop after a minute? If someone joins while a gate is up, do they see it up? Do the teleporters work both ways?
3. **The Mongoose.** Drive it off a high ledge onto the beach, where it should land on its wheels and drive away. Brake hard with someone watching from behind: the lamps should glow. Carry a second player on the back, and check you both see the same thing.
4. **Assault.** It has never been played by two people. One flag starts on Blue's stand. Red can take it and Blue can't. A capture moves the flag to Red's stand with Blue attacking. Five minutes with no capture sends the flag home and swaps the sides. Three captures win. Check that the flag's marker stays on it for everyone, and that ATTACK or DEFEND is right on each player's screen.
5. **Capture the Flag and Team Slayer.** You can only score while your own flag is home. A dropped flag goes back when its own team touches it. Every Warthog and Mongoose should be on the map. With three or more players, killing a teammate costs a point.
6. **King of the Hill.** A second player on the hill stops the scoring, and the hill's colour should show it. In Crazy King the hill moves every minute, so tell us if it ever lands somewhere you can't reach. In Team King, teammates shouldn't contest each other.
7. **Oddball, Juggernaut, Stalker and Reverse Tag.** Killing the carrier drops the ball. Killing the Juggernaut, the Stalker or whoever is "it" should pass the role to you, on every player's screen.
8. **Race and Rally.** Nobody has driven a lap yet. Yoyorast's is 27 flags and about 2.2 km. Take a Warthog or Mongoose round and tell us about any flag you can't reach. In Rally, touching the live flag should score and move it somewhere else.
9. **Forge.** Host Forge. The map's vehicles should be there, and a joiner should see them too. Grab one with the Monitor, move it, press F5, then host Slayer: it should start at its new spot.

If something breaks, note which item it was. Before you close the game, copy `Meteorite\Binaries\Win64\ue4ss\UE4SS.log` from your game folder and post it in our [Discord](https://discord.gg/9gxYZsByW9). The full checklist is [on GitHub](https://github.com/devnull9090/mjolnir-core/blob/main/docs/playtest_yoyorast.md).

## Assault

One flag at a time. The attackers carry it to their own base while the defenders stop them, and a capture or five minutes on the clock swaps the sides. Three captures win. It's under Capture the Flag on every map that has CTF.

![Assault on Blood Gulch: attacking Blue's base, with the flag 51 metres away and the sides swapping in 2:10.](/blog-images/weekly-update-2/assault-blood-gulch.jpg)

A line under the score says whether you're attacking or defending, and counts down to the next swap. If you join a game already running, the countdown starts at the first swap you see.

## King, Oddball and Race on 46 maps

Game types only appear on a map that carries their hills, balls and flags, so we rebuilt 46 of the 51 maps to carry them:

- **The nineteen classic maps and Yoyorast Island** have King, Oddball and Race.
- **Coldsnap and all 25 Halo 2 maps** have King and Oddball.

Each of those comes in variants: King, Crazy King and Team King; Oddball and Team Oddball; Race, Team Race, Rally and Team Rally. Three more game types are on every map with Slayer:

- **Juggernaut:** the first kill makes you the Juggernaut, and killing the Juggernaut takes over. It deals half as much damage again as everyone else, melee included.
- **Stalker:** the first kill makes you the Stalker, invisible and fast, while everyone else takes half damage. Kill the Stalker to take over.
- **Reverse Tag:** the first kill makes you it. Whoever is it moves slowly and scores a point a second until someone kills them.

That makes 17 game types on Blood Gulch alone. The same map updates also stop you respawning on a health pack's spot on the Halo CE maps.

The hill stands out from across the map. A wall of plasma rings it and a beacon rises from it, gold when it's empty, cyan when you hold it, orange-red when someone else does, and flashing violet when it's contested. One rule to know: unlike Halo CE, a contested hill scores for nobody, as in Reach.

![An empty hill on Blood Gulch: a gold wall of plasma around the hill, with a beacon rising from the middle.](/blog-images/weekly-update-2/king-hill.jpg)

![The same hill held by the player: the wall and beacon turn cyan, ON THE HILL shows under the score, and the score climbs.](/blog-images/weekly-update-2/king-on-the-hill.jpg)

## A marker that shows you the way

A badge now sits over the hill, the next Race flag or the Juggernaut, with the distance under it. Capture the Flag and Assault show one for each flag, in its team's colour, and it stays on the flag when it's dropped or carried.

![The hill's marker on Blood Gulch, 20 metres away and below the player, in front of its beacon.](/blog-images/weekly-update-2/marker-beacon.jpg)

When the spot is out of view, the badge slides to the edge of the screen and points the way to turn. It pulses when a hill is contested, and fades when it's over your crosshair so you can still aim. The Stalker never gets one.

![With the hill behind the player, the marker sits at the left edge of the screen and points the way to turn, 92 metres out.](/blog-images/weekly-update-2/marker-edge.jpg)

The line under the score now says only what the marker can't, such as ON THE HILL, HILL CONTESTED or LAP 1 OF 3.

## New game type and map screens

With this many game types, the old tiles couldn't cope. The game type screen now shows seven families, each naming its variants, and the family you pick lists them as buttons on the right. SELECT says exactly what you chose.

![The game type screen: seven families on the left, with Capture the Flag open and its Assault variant chosen on the right.](/blog-images/weekly-update-2/game-type-screen.jpg)

Map select uses the same families as tabs, and the tab you pick opens a tray with its description and variants.

![Map select's game type tabs, with Juggernaut open and its three variants below.](/blog-images/weekly-update-2/map-select-tabs.jpg)

## The Mongoose and Yoyorast Island

[Yoyorast Island](/mods/ce-yoyorast-island-v2) is the first Custom Edition map to bring its own vehicle. The Mongoose has its own engine sounds, headlights and tail lamps, and carries a driver and a passenger. Version 2.7.1 also brings the map's buttons, gates and panic shields, and it offers every game type on the list above.

![A Mongoose on Yoyorast Island, with a Spartan ahead of it and the island's tower beyond.](/blog-images/weekly-update-2/mongoose-yoyorast.jpg)

Its handling isn't final, and it still shows the Warthog's HUD icons. Tell us how it drives.

## Forge

- **A converted map's vehicles now appear in Forge.** Before, Forge showed none of them on a converted Custom Edition map. It now starts with the ones a Slayer game would place, and they stay when you load a saved layout.
- **F2 can't quietly lose your save.** One press used to move your saved layout into history with nothing on screen. It now takes two presses, and the first tells you what will happen.
- **F6 brings a reverted save back,** even after a restart. Objects you placed after your last save are still lost by a revert.

## Player pages and leaderboards

Every player's page now has a combat record: a career ring with a spoke for each match, form over time, where they killed and died on each map, their arsenal, rivals and medals.

![A combat record: career kills per death on the left, and a ring on the right with a spoke for each match, kills reaching out and deaths reaching in.](/blog-images/weekly-update-2/combat-record.jpg)

The new [leaderboards](/leaderboards) rank Kills, K/D, Wins, Win rate, Headshots and Best match, over all time, 30 days or 7 days. To place, link your account from the game. A match counts when at least two linked accounts played in it, so a board can read lower than a career total.

## A smoother launcher

- **Launching works again.** After mods 0.44.0, some launches stopped with Try again, and trying again failed the same way. Launcher 0.22.0 fixes that, updates itself, and finishes the update it couldn't complete.
- **A refused mod is left as it was.** The launcher now checks every file in a mod before it writes any of them, so a bad file can't leave a mod half-installed.
- **Update checks are quicker** on a long map list.

## For modders and map makers

- **Custom vehicles, scripts and devices.** [CLI 0.8.0](/changelog/cli/0.8.0) carries a Custom Edition map's own vehicles, scripts, buttons, gates and automatic doors into a level, and writes King, Oddball, Race and their variants. See [custom vehicles](https://github.com/devnull9090/mjolnir-core/blob/main/docs/custom_vehicles.md) and [CE map conversion](/docs/notes/ce-map-conversion).
- **Animation graphs.** [CLI 0.9.0](/changelog/cli/0.9.0) adds `mjolnir jmad`, which reads a graph, rewrites it for another skeleton, and proves a round trip byte for byte. The format is [documented](https://github.com/devnull9090/mjolnir-core/blob/main/docs/jmad_format.md).
- **Package tools.** `mjolnir ue scan` searches the game's packages and `mjolnir ue clone` copies one under your own path. Nobody has loaded a cloned package in the game yet.
- **Game types with traits.** `mjolnir megalo write` now writes game types that change a player's traits, including Stalker and Reverse Tag.
- **Vehicle sound banks.** [Launcher 0.23.0](/changelog/launcher/0.23.0) and [CLI 0.10.0](/changelog/cli/0.10.0) let a map carry Wwise banks for its own vehicles, so they follow your volume sliders. No published map uses them yet, so nothing changes today.
- **Clearer reviews.** Authors now see every release they've uploaded, and the moderator's reason for any held back.

## Versions

| Product | Now at | Notes |
| --- | --- | --- |
| Launcher | [0.23.0](/changelog/launcher/0.23.0) | From 0.21.0 |
| Code mods | [0.46.0](/changelog/mods/0.46.0) | From 0.43.1 |
| CE runtime | 1.18.0 | The launcher installs it |
| CLI | [0.10.0](/changelog/cli/0.10.0) | From 0.7.0. Scoop and Homebrew are still on 0.9.0 |
| Tag editor | [0.25.0](/changelog/tag-editor/0.25.0) | No change this week |

Every release is listed in the [changelog](/changelog).

## See you Saturday

Update the [launcher](/download) before 6 PM, [join the event](https://discord.gg/AQnRCHbmXq?event=1556902193548886056), and come break things with us. If you can't play, [watch on Twitch](https://www.twitch.tv/devnull9090) and tell us what you spot in our [Discord](https://discord.gg/9gxYZsByW9).

# Pelican Warfare: a new game mode, built entirely as a mod

**Author:** MJOLNIR Core
**Summary:** Ride a Pelican in, jump, open a parachute and fight over three capture zones on a new two-kilometre map. Pelican Warfare is a whole new way to play Halo: Campaign Evolved multiplayer, and every part of it was made with MJOLNIR's own tools.
**Tags:** multiplayer, maps
**Image:** /blog-images/pelican-warfare/featured.webp

Until now, MJOLNIR multiplayer has meant the game types Halo already had: Slayer, Capture the Flag, King of the Hill, Oddball, Race and Assault, on converted and remastered maps. Pelican Warfare is the first one that did not exist before. It has its own rules, its own map, its own way of arriving at the fight and its own screen furniture, and none of it is in the game you bought.

It is out today. Update the launcher to **0.24.1** and the mods to **0.54.0**, then install [Pelican Warfare](/mods/pelican-warfare) from the Hub.

## How a match goes

Two teams start at their own bases, each with a Pelican on the pad. Board it and it flies you over the valley. Jump when you like the look of the ground below.

You fall first. A small panel shows your speed, sink rate, heading and height above the ground. Open the parachute and you can steer and brake all the way down, so where you land is your choice: on a zone, behind it, or beside the Warthog you spotted from the air.

![The valley from the south: the river, the meadow and the range behind it.](/blog-images/pelican-warfare/valley.webp)

Three capture zones, **A**, **B** and **C**, sit between the bases. Stand in a neutral zone and it fills for your team. Stand in an enemy zone and you first take it back to neutral, then capture it. Each zone a team owns gives that team one point a second, as long as no enemy is standing in it. The first team to **500** wins; if the 20-minute combat clock runs out first, the higher score does.

Die and you are back at your base five seconds later, with a road, vehicles and the river between you and the zones.

## Reading the fight

The three tiles under the score tell you the state of every zone at a glance: who owns it, whether it is being captured, neutralized or contested, how far the capture has gone, and which teams have someone standing in it. The zone you are in gets a gold rim.

![The zone tiles: C being captured by Red, then owned by Red.](/blog-images/pelican-warfare/zone-tiles.webp)

When both teams are in a zone nobody scores from it and the tile says so on every player's screen.

![Zone A contested, as the host and a joining player see it at the same moment.](/blog-images/pelican-warfare/contested.webp)

Captures also go to the kill feed, so "Red team captured zone B" reaches you while you are busy somewhere else. Press **M** for the tactical map: the whole valley, your team, the vehicles and the zones. **N** zooms.

![The tactical map: bases, roads, the river and the three zones.](/blog-images/pelican-warfare/tactical-map.webp)

## The map

Pelican Warfare's valley is two kilometres on a side, far larger than any map the game shipped with. A river runs the length of it, over waterfalls and down to a lake in the south, with Forerunner bridges where the roads cross. There are meadows, pine forest, three Forerunner bases with lit interiors, and a mountain range all around.

![A base from the approach road.](/blog-images/pelican-warfare/citadel.webp)

It also sounds like a place. Streams and waterfalls are audible where the water actually runs, wind and forest sit behind them, and morning mist hangs low in the valley.

![Inside a base.](/blog-images/pelican-warfare/base-interior.webp)

## Why this matters: it is all a mod

We wanted to know whether MJOLNIR could carry something genuinely new, not another conversion. Pelican Warfare is the answer, and each piece of it uses a part of the framework that anyone can use:

- **The rules are a game-type script.** The game still contains the scripting engine behind Halo: Reach's custom games. `mjolnir megalo write` produces a script for it: the zones, the capture logic, scoring, the combat clock and respawns. The host's game runs it and every player sees the same match.
- **The map is a map pack.** Terrain, water, foliage, bases, sounds and lighting are built by the level tools and packed into one signed `.mjolnir` file. The launcher installs it like any other map on the Hub.
- **The HUD ships with the map.** The zone tiles and the tactical map are ordinary Unreal widgets cooked into the pack, driven by a few hundred lines of Lua in the HUD mod.
- **The drop is a small native module.** Freefall and the parachute needed physics the game does not have, so they live in the lobby mod's native code, which keeps every player's fall in step.

None of this replaces a game file. Take the mods off and the game is exactly as it was.

That is the point of the project. Classic maps were the first step and remasters the second. A mode like this, with a big map, a drop from the sky and objectives of its own, is the kind of thing people usually assume needs a new game. Here it is a download.

## Play it

1. Open the launcher and let it update itself to 0.24.1, then press **Update all** for mods 0.54.0.
2. Install [Pelican Warfare](/mods/pelican-warfare) from the Hub's [maps](/maps). It is a large download, about 685 MB.
3. In the game choose **MULTIPLAYER**, host a game, pick the **Pelican Warfare** map and the **Pelican Warfare** game type.
4. A match needs at least two players to start. Bring friends: it is at its best with full teams.

This is a first release, version 0.1.0, and we are playtesting it tonight. Tell us what breaks and what you would change on [Discord](https://discord.gg/9gxYZsByW9).

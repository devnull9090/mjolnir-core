# Weekly update 3: every medal, a new post-game screen, and Saturday's playtest

**Author:** MJOLNIR Core
**Summary:** Every medal the game awards now shows, the post-game screen has a podium and a timeline, hosts can make a match public mid-game, and hosting stutters far less. Join Saturday's playtest and help us test it with real players.
**Tags:** weekly-update, multiplayer, maps
**Image:** /blog-images/weekly-update-3/featured.jpg

This week was about what you see during and after a match, and about making hosting smoother. Multiplayer now shows all of the game's medals, and the post-game screen has a podium and a match timeline. Teams, markers and the motion tracker now agree on every PC.

Most of it was tested with two copies of the game on one PC, or with bots. Some of it hasn't had a second real player yet, so Saturday's playtest matters.

## Saturday's playtest

- **When:** [Saturday, November 14, 6 PM MST](https://discord.gg/AQnRCHbmXq?event=1556902193548886056 "2026-11-15T01:00:00Z")
- **Join us:** the [Discord event](https://discord.gg/AQnRCHbmXq?event=1556902193548886056). Click Interested and Discord will tell you when it starts.
- **Watch:** [twitch.tv/devnull9090](https://www.twitch.tv/devnull9090)

We play every Saturday at this time, so if you can't make this one, come to the next.

### Before you join

1. **Open the [launcher](/download) early and let it update.** It updates itself to 0.24.0, brings your mods to 0.51.0 and the CE runtime to 1.21.0, and updates 28 maps. If you have every map, that's about 1 GB.
2. **Check your mod order** if you changed it to work around the old behaviour. The mod lower in the list now wins, as the list always said.

### What to test

We'll start on Blood Gulch, then go to Lockout and Yoyorast Island. Most of this needs three or more players.

1. **Teams on every screen.** In Team Slayer or CTF with three or more players, everyone should be on the same team on every player's scoreboard, and nobody should sit under AWAITING ASSIGNMENT. On the motion tracker, teammates should show as friends and the other team as enemies. Players past the first two seats got this wrong until this week.
2. **Respawns away from the teleporters.** In CTF on Blood Gulch, red players should no longer respawn on the teleporter pads. The pads should still work both ways for everyone.
3. **Medals.** Get a headshot, a melee kill or a revenge kill: the medal should come up in the middle of your own screen only. Multi-kills, sprees and First Blood should show in everyone's kill feed. Joiners should see their own medals too, and a sniper headshot should show once, not twice.
4. **The post-game screen.** At the end of a match, Overview should show the top three on a podium with their medals, and the same podium on every screen. Check the Scoreboard and Timeline pages, then vote: everyone should still travel to the winning map.
5. **Joining after the host makes a match public.** The host starts a match private, then picks MAKE PUBLIC from the HOST MENU or types `/public`. It should appear in FIND GAMES, and you should be able to join it while it runs. After `/private`, it should leave FIND GAMES and everyone already in should stay.
6. **Lockout's gravity lift as a joiner.** The lift should carry a joiner up the same way it carries the host, without lagging behind.
7. **Markers that follow players.** In King, a second player on the hill should show HILL CONTESTED on every screen. In Juggernaut, the beacon should float over the Juggernaut's head and stay on them when they get into a vehicle. In Oddball, the ball has a skull marker: gold while it lies loose, orange while it's carried, and none on the carrier's own screen.
8. **Yoyorast's gates and shields with more than one player.** A raised gate should block players and vehicles, and a panic shield should block too. Someone who joins while a gate is up should see it up.
9. **The Mongoose with a passenger.** The passenger should see the same ride as the driver, and a joiner should hear its engine.

If something breaks, note which item it was. Before you close the game, copy `Meteorite\Binaries\Win64\ue4ss\UE4SS.log` from your game folder and post it in our [Discord](https://discord.gg/9gxYZsByW9).

## Every medal

The game already awarded Reach's whole set of medals, but the HUD only showed First Blood, multi-kills and killing sprees. It now shows all of them: headshots and sniper headshots, Pummel, Beat Down and Assassination, Revenge, Killjoy, Close Call, From the Grave, Avenger, Hijack and Skyjack, Splatter and Stuck, the weapon sprees, the objective medals, and multi-kills and sprees past the old cap.

Big moments go to everyone's kill feed: multi-kills, sprees, weapon sprees, objective medals and First Blood. Medals about how a kill was made, such as a headshot, a melee or a revenge, come up in the middle of your own screen, so the feed doesn't grow a line for every kill. When one kill earns several, the best come first.

Players who join a game see their medals too, and the medal case on player pages now counts hijacks and adds fourteen medals, from Pummel to Perfection. A match's page has a Medals column.

## A new post-game screen

The left side of the post-game screen now has three pages:

- **Overview** puts the top three on a podium with their medals, names every medal you earned, and lists the match's bests.
- **Scoreboard** is every player, as before.
- **Timeline** draws the top players' scores over the match and the kills in every minute.

The medals have icons of their own. The vote on the right is unchanged. The new pages come with CE runtime 1.21.0, which the launcher installs.

## Public or private mid-match

The host can now list a match while it runs. The HOST MENU has MAKE PUBLIC and MAKE PRIVATE, and the host can type `/public` or `/private` in chat. A public match shows in FIND GAMES straight away, and players can join it while it's running. A private match leaves FIND GAMES, and everyone in it stays. Forge matches stay private.

This also fixes a game that couldn't be listed until you restarted. If you started a match private and alone, switching to PUBLIC GAME afterwards said "Not listed yet: no lobby yet". Your game now stays online through a match, and the lobby tells you if it ever goes offline and how to bring it back.

## Teams, markers and the tracker agree

- **Teammates are friends on the motion tracker.** In team games the tracker drew every other player as an enemy, teammates included, on joiners' screens and on the host's.
- **Everyone on the right team.** On a joiner's scoreboard, a late joiner or anyone past the first two seats could land under AWAITING ASSIGNMENT or on the other team. Every PC now takes the teams from the host.
- **A marker on the ball in Oddball.** It's gold while the ball lies loose and orange while someone carries it.
- **Smoother markers.** The Juggernaut's beacon and the flag markers used to move ten times a second and jump along behind whoever they followed. They now move every frame, follow a player into a vehicle, and the beacon floats over the Juggernaut's head.
- **Markers read the game itself.** Who holds the hill and where the Juggernaut is now come from the game's simulation, not the character models on screen. In our tests the models could sit 2.5 m off, and the markers followed them. A player waiting to respawn no longer holds or contests the hill.
- **Bots stay in their own match.** Bots from an earlier match no longer come back on a joiner's scoreboard.

## Smoother hosting and lighter flags

- **No stutter every five seconds while hosting.** The host searched the whole game for players' connections every five seconds, even alone, and each search cost a frame of 50 to 70 ms. It now searches only when someone joins or leaves, or the map changes.
- **No freeze as the game starts.** The lobby's one-second freeze a few seconds after launch, and the smaller ones at the main menu and the first bot start, are gone.
- **Hosting with bots.** Starting bots used to freeze the host for up to a third of a second. On Blood Gulch with eight bots the HUD's longest moment went from 308 ms to 10 ms, and its share of each second from 11.6 ms to 5.0.
- **No freeze as a converted map finishes loading.** Timberland used to stop for 1.7 s, Zanzibar for 1.4 s and Blood Gulch for 1.0 s. That work is now spread over the frames while the map loads, and maps look the same.
- **Lighter flags.** CTF and Assault flags now wave on your graphics card. On Chill Out a flag at rest costs under 1 ms of each second, down from about 5, and a carried flag about 3, down from 11.
- **Halo 2's lifts push on every simulation tick.** Gravity lifts, jump pads and vents no longer trail you by up to 50 ms, and they hold their real top speed. Each player's own game pushes them, so this works for joiners as well as the host.
- **Maps with gates and shields** no longer stutter every two seconds when one of their machines goes missing.

## Teleporters don't take respawns

Every teleporter pad had been placed on the red team, so in team games red players respawned on them, sometimes right next to the enemy base. We updated 28 maps with teleporters on 8 November: 15 of the Halo CE classics, Yoyorast Island, Coldsnap, nine Halo 2 maps, Crossline and Proving Ground. The pads still work for everyone.

## A launcher that follows your mod order

[Launcher 0.24.0](/changelog/launcher/0.24.0):

- **Load order follows your list.** The list always said a mod lower down wins when two change the same thing, but for most mods the first one won. Now the one lower down wins. If you reordered mods to get around that, check your order.
- **Maps can use any shader library number.** The launcher gives each map a number of its own, so two maps built under the same number both draw correctly.
- **Content that needs a newer launcher says so.** A map or mod that needs a newer launcher now tells you to update, instead of failing quietly.

## For modders and map makers

- **Local builds.** Builds installed with `mjolnir dev install` load above everything from the hub, and show under *Local builds* on the My Mods page with a Remove button. The page also lists any container in your game folder that loses to a hub copy, so a test build that never loads is easy to spot. See [chunk numbering](https://github.com/devnull9090/mjolnir-core/blob/main/docs/chunk_numbering.md).
- **The same bake, the same bytes.** [CLI 0.11.0](/changelog/cli/0.11.0) bakes identical levels every run, adds Assault to `mjolnir megalo write`, and `map pack` stops when a level's gates, buttons or shields aren't in the pack.
- **Walkable ground.** [CLI 0.12.0](/changelog/cli/0.12.0) adds `mjolnir level navmesh`, which writes a map's walkable areas, doorways and walls as JSON. `mjolnir live objects` shows a weapon's ammunition and what a player is holding.
- **Spawns by game type.** The level loader can now give each game type its own spawn points, as CE and Halo 2 did. Maps change once they're updated; until then they play as before.
- **Several copies on one PC.** Two to four copies of the game can share one lobby and match for testing. See [multi-instance testing](https://github.com/devnull9090/mjolnir-core/blob/main/docs/multi_instance.md).

## Versions

| Product | Now at | Notes |
| --- | --- | --- |
| Launcher | [0.24.0](/changelog/launcher/0.24.0) | From 0.23.0 |
| Code mods | [0.51.0](/changelog/mods/0.51.0) | From 0.46.4, through [0.47.0](/changelog/mods/0.47.0), [0.48.0](/changelog/mods/0.48.0), [0.49.0](/changelog/mods/0.49.0) and [0.50.0](/changelog/mods/0.50.0) |
| CE runtime | 1.21.0 | From 1.19.0. The launcher installs it |
| CLI | [0.12.0](/changelog/cli/0.12.0) | From 0.10.0. Scoop and Homebrew are on 0.12.0 |
| Tag editor | [0.25.0](/changelog/tag-editor/0.25.0) | No change this week |

Every release is listed in the [changelog](/changelog).

## See you Saturday

Update the [launcher](/download) before 6 PM, [join the event](https://discord.gg/AQnRCHbmXq?event=1556902193548886056), and come play with us. If you can't play, [watch on Twitch](https://www.twitch.tv/devnull9090) and tell us what you spot in our [Discord](https://discord.gg/9gxYZsByW9).

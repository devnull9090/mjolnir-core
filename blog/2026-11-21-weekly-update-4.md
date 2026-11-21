# Weekly update 4: four Halo 2 maps remastered, a sound mixer, and Saturday's playtest

**Author:** MJOLNIR Core
**Summary:** Zanzibar, Coagulation, Containment and Ascension are remastered, /sounds gives you a slider for every sound on a map, and those four maps have Halo 2's waves, birds and wind. Join Saturday's playtest and help us test them with real players.
**Tags:** weekly-update, multiplayer, maps, lighting
**Image:** /blog-images/weekly-update-4/featured.jpg

This week was about maps. Four Halo 2 maps now have the remaster treatment the Halo CE maps got in October, with new ground, cliffs and lighting. Every remastered map was rebuilt and loads faster, and you can now set the level of each sound a map plays.

Almost all of it was tested on one PC, some of it with two copies of the game. The new maps haven't had a full match with real players yet, so Saturday's playtest is where we find out.

## Saturday's playtest

- **When:** [Saturday, November 21, 6 PM MST](https://discord.gg/AQnRCHbmXq?event=1556902193548886056 "2026-11-22T01:00:00Z")
- **Join us:** the [Discord event](https://discord.gg/AQnRCHbmXq?event=1556902193548886056). Click Interested and Discord will tell you when it starts.
- **Watch:** [twitch.tv/devnull9090](https://www.twitch.tv/devnull9090)

We play every Saturday at this time, so if you can't make this one, come to the next.

### Before you join

1. **Open the [launcher](/download) early and let it update.** It brings your mods to 0.53.1 and the CE runtime to 1.24.0, and updates 17 maps. If you have every map, that's about 1.8 GB. Ascension alone is 300 MB.
2. **Load one of the four new remasters once before the playtest**, so a problem with your install shows up early and not in the lobby.

### What to test

We'll start on Zanzibar, then go to Coagulation, Containment and Ascension.

1. **Zanzibar with a full lobby.** The map should load for everyone. The big wheel should turn and stay drawn from every angle, and the gate should open for everyone when someone presses its button. The gate and wheels should look the same on every screen, never a grey grid.
2. **The sound mixer.** Type `/sounds` in chat. A panel should open with a slider for each sound on the map. Drag one with the mouse and you should hear that sound change; the far left should mute it. DONE, or `/sounds` again, should close the panel and give you back control. Try Esc while it's open and tell us what happens. So far only the host has opened it, so joiners matter most here.
3. **Zanzibar's sounds.** Near the shore you should hear waves and the sea, and now and then gulls, birds and a distant battle. Tell us what's too loud or too quiet next to gunfire.
4. **One remaster after another.** Going from one remastered map to the next used to be able to crash the host and a joiner together. We'll play all four in a row: nobody should crash on the way in.
5. **The same map twice.** On a second match on the same map, doors and gears should keep their own materials. They used to turn into a grey grid.
6. **Containment.** The map should load without a crash. Its gates should be there, open, and not blink in and out as you move. The canyon walls should be lit, not black.
7. **Coagulation and Ascension.** Coagulation's bases should be lit red and blue inside, with shade in the corners. On Ascension you shouldn't see the undersides of the floating rocks: the fog under them is back.
8. **Death Island's horizon.** There should be no dark line where the sea meets the sky, and the bottom of the sky shouldn't flash as you look up and down.
9. **Respawns on the rebuilt maps.** Eleven Halo CE maps were rebuilt this week. In CTF on Blood Gulch, red players should still respawn away from the teleporter pads, and the pads should still work both ways.

Last week's list still stands too, above all the post-game screen and its vote with more than two players. It's in [weekly update 3](/blog/weekly-update-3).

If something breaks, note which item it was. Before you close the game, copy `Meteorite\Binaries\Win64\ue4ss\UE4SS.log` and `Meteorite\Binaries\Win64\ue4ss\Mods\MJOLNIRLevelLoader\breadcrumbs.txt` from your game folder and post them in our [Discord](https://discord.gg/9gxYZsByW9).

## Four Halo 2 maps remastered

In October the [Halo CE maps were remastered](/blog/ce-maps-remastered). The same treatment now works on Halo 2 maps, and four are on the hub:

- **Zanzibar** has new cliffs and turf, redrawn floor grates, glass you can see, and real bounced light indoors.
- **Coagulation** has new cliffs and its trees planted on the ground. Its bases are lit by Halo 2's own lights, in their team colours, with bounced light inside.
- **Containment** has snow, its own ground colours and glacial boulders, and its canyon walls are lit by bounced light.
- **Ascension** has a desert look on its slate and sandstone.

Zanzibar and Coagulation came out last weekend, Containment and Ascension on 18 November. All four keep their names and places in the map list, so the launcher updates the copies you have.

**Light that bounces indoors.** A remastered map can now be drawn in pieces the game's lighting can work on. Rooms get bounced light, shade in their corners and falloff down their stairwells, instead of an even glow. Zanzibar and Coagulation are the first maps to use it.

Turf also got an update last weekend: glass you can see and break, coloured trucks, lit signs, grass and street decoration, and sounds at Halo 2's levels.

## Your own sound mix

Type `/sounds` in chat and a panel opens over the match with a slider for every sound the map plays, plus one for all of them. A dot marks the ones you can hear from where you stand. Levels run from -24 dB to +12 dB, and the far left mutes a sound. Your levels are kept for each map on your PC, and nobody else hears your mix.

![The sound mixer open on Zanzibar, with a slider for each of the map's sounds](/docs-images/sound_mixer_zan.png)

The [sound mixer guide](https://github.com/devnull9090/mjolnir-core/blob/main/docs/sound_mixer.md) lists what each row means.

## Maps that sound like Halo 2

Halo 2 plays one-off sounds at random on top of a map's background: waves on Zanzibar's shore, gulls, birds, a distant battle, gusts of wind. Those now come through on the four remastered Halo 2 maps. Their ambient sound is louder too, so you can hear it next to the game's own mix. The other Halo 2 maps get both when they're rebuilt. If it's too much on a map, that's what the mixer is for, and we'd like to hear which sounds you turned down.

## Rebuilt maps and faster loads

Eleven remastered Halo CE maps and Proving Ground were rebuilt on 18 November: Blood Gulch, Death Island, Ice Fields, Sidewinder, Infinity, Gephyrophobia, Battle Creek, Danger Canyon, Timberland, Rat Race and Yoyorast Island.

- **Faster loads.** Rocks on the cliffs now carry their materials inside the map. Before, the game set them one by one as the map loaded, which took over a second on Ascension.
- **No black band under cliff tops.** The soil under a cliff's lip read as solid black on every remastered map. It's packed earth now.
- **No hairline down tall rocks.** A thin dark line ran down some boulders and walls where the ground above them stepped.
- **Blood Gulch's cliffs meet the ground.** The thin black crack along the foot of the cliffs is gone.
- **Death Island's horizon.** The dark line where the sea meets the sky is gone, and the bottom of the sky no longer flashes.
- **Bots and teleporters carried over.** The rebuilt maps keep their bots, and their teleporter pads still don't take respawns.

## Fixes

- **No crash after switching maps.** Going from one remastered map to another could crash host and client together.
- **A missing map part can't crash the game.** Containment 2.0.0 went out without its gates' meshes, and the game crashed a couple of seconds after the map loaded. Containment 2.0.1 put the gates back the same evening, and the loader now waits for a part's mesh instead of crashing.
- **Zanzibar's big gear stays drawn.** It disappeared from some angles, as did door parts on Containment's gate.
- **Moving parts on a second match.** Doors and gears drew in a grey grid material when a map was played twice in a row.
- **Glass you can see.** Breakable windows that blocked you and shattered, but couldn't be seen, draw again.
- **Ascension's floating rocks.** The fog under them is back, so you no longer see their undersides.

## When the game crashes

Every map load now writes a short file, `ue4ss\Mods\MJOLNIRLevelLoader\breadcrumbs.txt`, with a line before each step of the load. The game's own log is switched off in release builds, so after a crash this file is the only record of what the load was doing. If you report a crash, attach it. The [crash reports guide](https://github.com/devnull9090/mjolnir-core/blob/main/docs/crash_reports.md) says what else helps.

## For map makers and video makers

- **FlyCam flies between shots.** Page Up and Page Down fly smoothly from one saved shot to the next. Shots have their own panel with undo and redo, and FlyCam shows your real Spartan instead of a grey stand-in.
- **New lighting settings.** `sky_leak` lets a little sky light into enclosed spaces, and `lumen_cells` lists a map's lit pieces. Both are in the [level format notes](/docs/notes/level-format).
- **Halo 2's placed lights.** A Halo 2 map's own lights now come through as real lights. The [Halo 2 map conversion](https://github.com/devnull9090/mjolnir-core/blob/main/docs/h2_map_conversion.md) guide was updated this week.

## Versions

| Product | Now at | Notes |
| --- | --- | --- |
| Code mods | [0.53.1](/changelog/mods/0.53.1) | From 0.51.0, through [0.52.0](/changelog/mods/0.52.0), [0.52.1](/changelog/mods/0.52.1) and [0.53.0](/changelog/mods/0.53.0) |
| CE runtime | 1.24.0 | From 1.21.0. The launcher installs it |
| Launcher | [0.24.0](/changelog/launcher/0.24.0) | No change this week |
| CLI | [0.12.0](/changelog/cli/0.12.0) | No change this week |
| Tag editor | [0.25.0](/changelog/tag-editor/0.25.0) | No change this week |

Every release is listed in the [changelog](/changelog).

## See you Saturday

Update the [launcher](/download) before 6 PM, [join the event](https://discord.gg/AQnRCHbmXq?event=1556902193548886056), and come play with us. If you can't play, [watch on Twitch](https://www.twitch.tv/devnull9090) and tell us what you spot in our [Discord](https://discord.gg/9gxYZsByW9).

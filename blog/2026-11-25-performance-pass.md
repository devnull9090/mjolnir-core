# Chasing milliseconds: what a slower PC taught us about performance

**Author:** MJOLNIR Core
**Summary:** We tested MJOLNIR on an older PC with Windows Defender on and found our mods spending up to 57 ms of every second on the game thread. After this pass it's 3 to 6 ms, and far fewer frames stutter. Here's how we measured it.
**Tags:** multiplayer, performance

Most of MJOLNIR's development happens on a fast PC: a Ryzen 9 7950X3D with an RTX 5090. Any game runs well on it, which is exactly the problem: it hides slow code. So this week we did the opposite and ran a full performance pass on our slowest test PC.

| | Development PC | Test PC |
|---|---|---|
| CPU | Ryzen 9 7950X3D | Ryzen 9 7900X |
| GPU | RTX 5090 | GTX 1080 Ti |
| Settings | 4K | Medium, 1080p, VSync on |
| Windows Defender real-time scan | off | **on** |

That last row turned out to matter most.

## The culprit: files read right after they change

MJOLNIR is several mods (the HUD, the lobby, the level loader) plus small native libraries, all running inside the game. They talk to each other a lot: the HUD asks for the state of the Pelican Warfare zones, the lobby passes your match to Discord, joining a match hands a map name from one part to another. For a long time much of that talk went through small text files: one side writes a file, the other reads it.

On the development PC a file read costs about 0.2 ms, so nobody noticed. On a PC with Windows Defender's real-time scan, which Windows turns on by default, opening a file **a moment after it was rewritten** waits for Defender to scan it. That's about **5 ms each time**. An unchanged file still opens in 0.1 ms. It's only the read-after-write that costs, and that's exactly what a handoff through a file is.

5 ms sounds small. But the game draws a frame every 16 to 22 ms, and some of these handoffs happened eight or nine times a second.

## How we measured

- **The hitch log.** The HUD already ships one: it notes every slow frame, where you were standing, and which of our scripts ran during it. At the end of each match it prints a summary: frame times, hitches, and how many milliseconds per second each of our script loops took.
- **A file and call profiler**, for development only. It counted and timed every file our scripts opened and every call into our native code. That's what found the 5 ms reads.
- **A frame recorder**, which splits each frame into game, render and GPU time without slowing the game down. That's how we could tell our own hitches from the engine's.

For this post we ran the same scenario twice on the test PC, once with the mods as they were before this pass and once after. The development PC hosted Pelican Warfare, and the test PC joined a match already under way, played to the end, then stayed for the next full match. Same PCs, same map, same settings. Only the mods changed.

## The results

Time our scripts held the game thread, per second of play (lower is better):

| Script loop | Before | After |
|---|---|---|
| HUD | 21–49 ms | 2.6–4.5 ms |
| Lobby Discord presence | 7.5 ms | 0.1 ms |
| Everything else together | 1–2 ms | 0.6–1.6 ms |
| **Total** | **31–57 ms** | **3.2–6.2 ms** |

Frame times on the test PC (lower is better; the median is the typical frame, p95 and p99 the slowest 5% and 1%):

| | Before: join under way | Before: full match | After: join under way | After: full match |
|---|---|---|---|---|
| Length | 4 min 19 s | 6 min 49 s | 6 min 10 s | 6 min 49 s |
| Median frame | 22 ms | 20 ms | 22 ms | 21 ms |
| p95 frame | 28 ms | 31 ms | 25 ms | 25 ms |
| p99 frame | 31 ms | 32 ms | 26 ms | 26 ms |
| Hitches during play | 3 | 15 | 3 | 3 |
| Worst frame during play | 87 ms | 70 ms | 84 ms | 38 ms |

The median is 20–22 ms in all four runs: on this PC the graphics card sets the typical frame. The difference is in the slow frames. Before, p95 and p99 sat 6 to 12 ms above the median, and that gap is the file reads landing on top of a normal frame. After, the slowest 1% of frames sit 4 to 5 ms above the median. In the full match, the 15 hitches during play dropped to 3, all of them 31–38 ms frames at the Pelican launch. In both joined matches the worst one is the same: the team armour colours being applied as you join. That one is fixed too, after these runs (below). Most of the slow frames a match still has, about 16, come in its last second, at the round end.

## What we changed

**The hot paths (two handoffs that ran every second):**

| | Before | After |
|---|---|---|
| HUD reading the Warfare zone state, 8–9 times a second | 50 ms per second | read from memory, ~0 |
| Discord presence handed between the HUD and the lobby | 5.5 ms per second | in memory, ~0 |

**The hitches:**

| | Before | After |
|---|---|---|
| Post-game vote screen: a check for hidden menus | 60–72 ms frame every 1.5 s | gone |
| A kill-feed line after a player's avatar was unloaded | 26 ms | under 8 ms |
| The Pelican launch: three zone walls built at once | one 48–52 ms frame | 31 and 36 ms frames |
| Team armour colours at a match start | one 104–107 ms frame | 23 ms at most |
| Team armour colours when you join a match | one 55–63 ms frame | 8 ms at most |

**Nearly every other handoff between our mods and native code** now goes through memory: joining, the lobby, the hub, map installs, kill floors, Halo 2's lifts and bots. Costs per use on the test PC:

| Handoff | Before | After |
|---|---|---|
| Each call to mjolnircore.com (heartbeats, player names, match results) | ~11–14 ms | ~0 |
| Each retry of a joiner's sound setup | ~13 ms | ~0 |
| Placing the map when you join | ~11 ms | ~0 |
| The lobby's connection details | 5 ms | ~0 |
| Pelican Warfare's state file for test tools | 0.8 ms per second | not written on players' PCs |

Text files are still used where they belong: logs, saved settings, and anything another program reads, such as the launcher.

## What's still there

Being honest about what we didn't fix:

- **The end of every match.** There's about a second of slow frames (70–90 ms), then one long one (~285 ms) as the round ends and the world unloads. Our scripts are idle then, on both PCs; it's the game's own round end.
- **Lua garbage collection.** Our scripts' memory cleanup takes a 20–25 ms frame about three times a match.
- **Joining.** Two one-off costs of about 100 ms each remain while the join's loading screen is up: reading the map's level file once, and the game starting your side of the match. We cut the rest: re-reading the level file (92 ms to 1 ms) and the HUD's first tick (60–66 ms to 39–43 ms).

## Why it matters

The PCs we build on aren't the PCs most of you play on. Every few milliseconds we spend on the game thread comes out of your frame time, and the cost is highest on the PCs that have the least to spare. From now on we profile on the slow PC first.

These changes shipped in mods 0.57.0, alongside Pelican Warfare's reinforcement waves, the Covenant and voice lines. If you still see stutter in a match, the HUD's hitch log (`MJOLNIRHud\hitches.log`) records where and when, and it's the most useful thing you can send us.

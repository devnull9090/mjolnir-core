# CU3 in the rear-view: diffing an update after it was gone

**Author:** MJOLNIR Core
**Summary:** We pulled CU2 and CU3 back out of Steam's depot history and diffed all 12,291 tags of July's update retroactively: B40 got the biggest encounter rework of any patch yet, A30's AI was given a new objective to push, and a dozen spawns moved a few meters.
**Tags:** game-update, cu3, tag-data

Our [CU4 report](/blog/cu4-under-the-hood) exists because we started archiving game builds
the day CU4 landed. This post exists because it turns out the past wasn't gone either:
Steam's CDN still serves the depot manifests for **CU2** and **CU3**, and a recovered build
is not an approximation — the CU3 download hashed **bit-for-bit identical** to the lock we
had taken of the live install, on all 252 shipped files. So we diffed July's update
retroactively, the same way: every tag, field by field.

**CU2 → CU3** (`2026.06.26.1097863.1` → `2026.07.25.1112544.4`, landed August 1):
**1 tag added, 0 removed, 375 changed, 11,913 byte-identical** of 12,291.

## B40 got the biggest encounter rework of any update so far

Assault on the Control Room's scenario carries over 1,300 substantive field changes and a
new script (664 → 665). The flavor of it: one squad's spawn point went from no activity to
**`patrol`**, its patrol mode flipped from ping-pong to loop, and it was handed a patrol
point set it previously didn't have; other squads were reassigned to different point sets;
spawn positions were nudged. Somebody spent real time in B40's encounters for CU3.

## The rest of the campaign got surgical edits

- **A30 (Halo)** — an AI objective task gained a second area, flagged as a **goal**: an
  encounter was literally given a new place to push toward.
- **A50** — one spawn point delayed by 4 seconds and lowered ~2 units.
- **B30** — two spawn points moved about two units and given real facing angles.
- **C20** — one squad's character type swapped (`#6` → `#0`).
- **C45** — one squad template swapped. Trivia: **CU4 swapped it back** — the two diffs show
  the same value flipping away and home again.
- **E20** — squad templates renumbered across ~30 squads and scripted unit seats rebound.
- **e30** — AI pathfinding hint data adjusted in eight places.
- The **encounter remix seeds** changed in CU3 exactly as they did again in CU4 — they move
  every update, so treat reseeding as routine churn rather than a deliberate shuffle.

**The one new tag:** an animation graph for a **c40 Banshee door**
(`objects/Levels/halo1/solo/c40/banshee_door/banshee_door1_c40`).

The remaining ~330 changed tags are the same cooker noise CU4 produced: 175 animation graphs
whose bytes moved with no visible field change, level-geometry BSPs full of runtime pointer
churn, lighting checksums, seam renumbering.

## Two corrections the archaeology forced on us

Recovering old builds doesn't just add history — it audits your present claims.

First: the two level-geometry chunks our built-in Oodle decoder cannot decompress fail
**identically on CU2, CU3 and CU4**. In the CU4 post we called them a CU4 casualty; they are
in fact a long-standing gap in our decoder, sitting there since launch, and now they have a
bug on our board instead of a line in someone else's patch notes.

Second: the curious `Cinematics/020la_sword/.../jorge_turret` animation graph — a *Reach*
character's cinematic rig under a naming scheme matching no shipped mission — is present in
vanilla CU2. It is **launch-era content**, not something an update slipped in. What it is
for, we still don't know; when it changes, we'll know the same day.

## The full timeline, three builds deep

| | CU2 → CU3 | CU3 → CU4 |
|:--|:--|:--|
| Tags added | 1 (c40 banshee door graph) | 1 (A10 cryo capsule graph) |
| Tags removed | 0 | 0 |
| Tags changed | 375 | 358 |
| The headline | B40 encounter rework | AI firing-pattern rebalance |

Every build from here on gets archived the day it lands — but it's good to know the
rear-view mirror works too.

# Halo Campaign Evolved CU3: every tag the July 29 update changed

**Author:** MJOLNIR Core
**Summary:** We diffed all 12,291 tags between the Steam launch build and CU3, field by field: B40 got the biggest encounter rework of any patch yet, A30's AI was given a new objective to push, and a dozen spawns moved a few meters. Plus: why the launch build is stamped "CU2".
**Tags:** game-update, cu3, tag-data

Halo Campaign Evolved shipped its first Steam patch, **CU3**
(`2026.07.25.1112544.4-Rel-i343-Meteorite-2607-CU3`), on **July 29** — six days after
Early Access began. We snapshotted the launch build and CU3 and ran every one of the
game's **12,291 Blam tags** through a field-level diff. The verdict: **1 tag added,
0 removed, 375 changed, 11,913 byte-identical**.

## There is no CU1

The build Steam launched with is stamped `2026.06.26.1097863.1-Rel-i343-Meteorite-2606-CU2`
— "CU2", on day one. The content-update numbering predates the Steam release, so the
oldest build Steam ever shipped is CU2: it went out as the Early Access preload on
July 23, the July 28 wide release served the same depot manifest, and the depot's
manifest history contains nothing older. If you are looking for a "CU1" or a 1.0
before it, it does not exist on Steam — the CU2-stamped build *is* the original PC
release, and it is archived in our snapshot store. Every diff in this series is
anchored to it.

## B40 got the biggest encounter rework of any update so far

Assault on the Control Room's scenario carries over 1,300 substantive field changes and
a new script (664 → 665). The flavor of it: one squad's spawn point went from no
activity to **`patrol`**, its patrol mode flipped from ping-pong to loop, and it was
handed a patrol point set it previously didn't have; other squads were reassigned to
different point sets; spawn positions were nudged. Somebody spent real time in B40's
encounters for CU3.

## The rest of the campaign got surgical edits

- **A30 (Halo)** — an AI objective task gained a second area, flagged as a **goal**:
  an encounter was literally given a new place to push toward.
- **A50** — one spawn point delayed by 4 seconds and lowered ~2 units.
- **B30** — two spawn points moved about two units and given real facing angles.
- **C20** — one squad's character type swapped (`#6` → `#0`).
- **C45** — one squad's template swapped.
- **E20** — squad templates renumbered across ~30 squads and scripted unit seats rebound.
- **e30** — AI pathfinding hint data adjusted in eight places.
- Both campaign variants in `game_engine_settings` got new **encounter remix initial
  random seed** values, so remixed encounter layouts roll differently than at launch.

**The one new tag:** an animation graph for a **c40 Banshee door**
(`objects/Levels/halo1/solo/c40/banshee_door/banshee_door1_c40`).

The remaining ~330 changed tags are cooker noise, not design: 175 animation graphs
whose bytes moved with no visible field change, level-geometry BSPs full of runtime
pointer churn, lighting checksums, seam renumbering.

## Two launch-build curiosities, for the record

Diffing against launch also settles what was *already there*. The oddly named
`Cinematics/020la_sword/.../jorge_turret` animation graph — a *Reach* character's
cinematic rig under a naming scheme matching no shipped mission — is present in the
launch build. It is launch-era content, purpose unknown; when it changes, we'll know
the same day. And two level-geometry chunks defeat our built-in Oodle decoder on both
builds — a gap in our tooling that has been there since launch, not something a patch
did. (*Update, August 19: the decoder is fixed — both chunks now decode on every
build.*)

## How this post was made

Steam patches in place, but its CDN still serves older depot manifests, and a
recovered build is not an approximation: our recovered CU3 hashes **bit-for-bit
identical** to the live install, on all 252 shipped files. Both builds live in a
content-addressed snapshot store, and `mjolnir tagdiff` compared every tag and decoded
every changed one, field by field.

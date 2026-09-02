# Halo Campaign Evolved CU4 under the hood: every tag the August 17 update touched

**Author:** MJOLNIR Core
**Summary:** We diffed all 12,292 tags between CU3 and CU4, field by field: AI gunfights got a real rebalance, Jackals got new hitboxes, active camo got faster, and one new animated object appeared — a quiet gameplay pass the public patch notes never mentioned.
**Tags:** game-update, cu4, tag-data

Halo Campaign Evolved updated to **CU4** (`2026.08.11.1121610.2-Rel-i343-Meteorite-2607-CU4`)
on **August 17** — the executable's version stamp says August 11, which is when it was
built, not when Steam shipped it. We snapshotted the build the day it landed and ran
every one of the game's **12,292 Blam tags** through a field-level diff against
[CU3](/blog/cu3-in-the-rear-view). The verdict: **1 tag added, 0 removed, 358 changed,
11,931 byte-identical** — and inside those 358 is a real gameplay rebalance the patch
notes didn't mention.

## What actually changed for gameplay

**The AI got better at shooting you.** The shared AI tuning tag (`ai/generic-character`)
carries 199 field-level changes: two new firing patterns (69 → 71), and an existing pattern
rebuilt end-to-end — `rate of fire` 0 → 3, `projectile error` 0.035 → 0.009, `maximum error
angle` halved twice over, `burst duration` tightened from (0.56, 0.75) to (0.25, 0.45),
`target tracking` relaxed 0.9 → 0.5. The Flood got the same treatment:
`floodcombat_base-character` adds a firing pattern of its own and retunes over 250 values.
If firefights feel different on CU4, they are.

**Jackals have new hitboxes.** `jackal-model` drops from 10 model targets to 8, retargets
`target_elbow_r/l` to `target_hand_r/l`, flags a target as **headshot**, and rebalances
targeting relevance (one target 0.5 → 1, another 0.5 → 0.01). Aim-assist and auto-aim against
Jackals now resolve to different bones than they did on CU3.

**Active camo tolerates faster movement.** In `globals`, the camo `biped speed reference`
rose 3.25 → 3.7 — the speed at which movement degrades your camouflage moved up.

**Mission scripting was touched in three places.** Mission **E10** gained an entire new
script (526 → 527) and rewires placement scripts across a half-dozen squads' spawn points;
**e30** swaps the unit definitions bound to six scripted vehicle seats; **C45** swaps one
squad's template — back to its pre-CU3 value, undoing a CU3 edit. Targeted encounter
surgery, not a rewrite.

**The encounter remix seeds rolled again**, exactly as they did in CU3 — they move every
update, so treat reseeding as routine churn rather than a deliberate shuffle.

**One new tag in the whole update:** an animation graph for the **A10 cryo capsule**
(`objects/levels/halo1/solo/a10/unsc_cryo_capsule`) — the Pillar of Autumn's cryo bay picked
up a newly animated prop.

## What changed but doesn't matter

The other ~330 changed tags are the sound of a cooker, not a designer: 176 animation graphs
whose bytes moved without a single visible field changing, 120 level-geometry BSPs whose
differences are runtime pointers and mopp bookkeeping, 31 lighting-info checksums, and
seam-ID renumbering. Seventeen of the 31 IoStore container sets were re-cooked — some with
their directory *casing* changed, which our diff treats as the same asset. Among the
re-cooks: the curious launch-era `jorge_turret` cinematic graph
[we flagged in the CU3 report](/blog/cu3-in-the-rear-view) moved bytes again without
changing a field. At the file level the update also rebuilt the host executable, the
simulation DLL and a sweep of third-party libraries (nine `boost` DLLs, `libHttpClient`,
`OpenColorIO`, `tbb`).

## The stack still works

Re-verified on CU4, in order of how much we were braced for it to break: all four UE4SS
signatures resolve uniquely; all 13 MJOLNIR mods load with zero Lua errors and the in-game
bridge answers; the tag reader parses the CU4 containers clean and round-trips them
byte-for-byte; live tag patching still locates payloads in the running game. The tag
*schema* is untouched — 101 groups, 1,779 structs, 13,250 fields, byte-identical
definitions — so every MJOLNIR tool carries over. The two level-geometry chunks our
Oodle decoder couldn't decompress fail identically here as on every build since launch —
a long-standing gap in our tooling, not a CU4 regression. (*Update, August 19: the
decoder is fixed — both chunks now decode on every build.*)

## The timeline so far

| | Launch (CU2) → CU3 | CU3 → CU4 |
|:--|:--|:--|
| Shipped | July 29 | August 17 |
| Tags added | 1 (c40 banshee door graph) | 1 (A10 cryo capsule graph) |
| Tags removed | 0 | 0 |
| Tags changed | 375 | 358 |
| The headline | B40 encounter rework | AI firing-pattern rebalance |

## How this post was made

CU4 overwrote CU3 in place, as Steam updates do — but CU3 was already in our
content-addressed snapshot store, recovered bit-for-bit from Steam's depot history and
verified against a lock of the live install. `mjolnir tagdiff` compared every tag and
decoded every changed one. Every build from here on gets archived the day it lands, so
the next one of these posts is a `tagdiff` away.

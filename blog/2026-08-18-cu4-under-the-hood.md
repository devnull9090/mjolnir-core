# CU4 under the hood: what the August update changed

**Author:** MJOLNIR Core
**Summary:** CU4 rebuilt 49 of the game's 255 shipped files but left the tag format completely untouched — every MJOLNIR tool still works. Two new animation graphs hint at unannounced cinematic content, and from this update on we can diff every tag field-by-field.
**Tags:** game-update, cu4, tag-data

Halo Campaign Evolved updated to **CU4** (`2026.08.11.1121610.2-Rel-i343-Meteorite-2607-CU4`)
on August 11. We re-measured the install against our CU3 build lock and re-verified the whole
MJOLNIR stack on the new build. The short version: **everything still works**, and the update
is bigger on the inside than the patch notes suggest.

## The file-level picture

Our [build lock](/docs/notes/build-lock) records a SHA-256 for all 255 files the game ships.
Verifying CU3's lock against the CU4 install shows **49 files changed and none added or
removed**:

- `HaloCampaignEvolved.exe` — the 230 MB host, rebuilt as every update does.
- `HaloSimulation_tag_release.dll` — the Blam simulation core, rebuilt.
- **17 of the 31 IoStore container sets** (`.utoc`/`.ucas`) were re-cooked, including
  `global`, `pakchunk0`, and a dozen level chunks.
- The supporting cast: nine `boost` DLLs, `libHttpClient`, `OpenColorIO`, `tbb`,
  `CrashReportClient` — third-party churn from a toolchain bump, not gameplay.

## The tag format didn't move

The part that matters if you mod this game: we regenerated the full tag definition corpus
from the CU4 containers and compared it against the shipped one —
**101 tag groups, 1,779 structs, 13,250 fields, byte-for-byte identical definitions**.
Whatever i343 changed in those re-cooked containers, the *schema* the tag data follows is
exactly the schema we documented. Every group still parses, and every tag in our validation
sample re-serialises byte-for-byte.

Re-verified on CU4, in order of how much we were braced for it to break:

- **All four UE4SS signatures** resolve uniquely on the new executable. Addresses drifted
  by a few hundred bytes; every scan still lands on exactly one match.
- **All 13 MJOLNIR mods** load with zero Lua errors, and the in-game bridge answers.
- **The tag reader** parses the CU4 containers clean, and round-trips every tag it checked.
- **Live tag patching** — see below.

One tally did move: the game now ships **12,292 Blam tags**, and the
`model_animation_graph` group grew from **176 to 178 tags**. Which brings us to the
interesting part.

## Two new animation graphs, and a name that shouldn't exist

The CU4 containers carry an animation graph at a path that matches no shipped mission:

```
Tags/Cinematics/020la_sword/objects/020la_sword_013/jorge_turret-model_animation_graph.ubulk
```

Every campaign cinematic folder in the game is named for its mission — `A30`, `B40`, `D40`,
`e10`. There is no mission `020la_sword` in Campaign Evolved, and there is no character
named **Jorge** in Halo 1. Jorge-052 is *Reach's* heavy-weapons Spartan; `020la_sword` reads
like a cinematic naming convention from somewhere else entirely. We are not going to
speculate further than the file names do — but a cooked cinematic rig for a Reach character
inside a Halo 1 remake's shipping containers is exactly the kind of thing a field-level diff
exists to catch.

## Why this post can't show you more — and the next one will

The honest limitation: CU4 overwrote CU3 in place, as Steam updates do. We can prove *that*
17 container sets changed (the hashes say so) but not *what* changed inside them, because
the CU3 bytes are gone. A hash can tell you a thing changed; only a copy can tell you how.

So as of this update, the pipeline keeps copies:

- **Every build gets snapshotted** into a content-addressed store the moment we see it —
  the full 74 GiB install, deduplicated so each future update costs only what it touched.
- **`mjolnir tagdiff`** compares two builds tag-by-tag and, for changed tags, decodes both
  payloads and reports the difference *field by field* — "the pistol's rate of fire went
  from 3.5 to 3.0", not "pakchunk0 changed".

CU4 is the baseline. When CU5 lands, the post about it will name every tag the update
touched and every field inside them.

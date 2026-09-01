# Locating loaded tags in the running game: sweep today, pointer-chase tomorrow

Live mode has to answer two questions about the running game:

1. **Which tags are loaded, and what level is this?**
2. **Where is a given tag's data buffer, so a field can be poked?**

Today both are answered by the census — one ~13 GB scan of the process's
writable memory that fingerprints every loaded tag by its own bytes
(`blam_live::census`, `apps/tag-editor/src-tauri/src/census.rs`). It works and
is cached, but a scan is a blunt instrument. This note records what we learned
about doing it the classic way instead: a known engine global plus fixed
offsets, resolved once per build and chased by pointer thereafter — no scan.

Measured 2026-09-01 against the shipped build (`…Meteorite-2607-CU3`) in mission
a30, 369 tags verified loaded.

## Finding 1 — the loaded *list* needs no scan at all

Loaded Blam tags are UE `UObject`s named `Blam<Group>TagDataAsset`
(`BlamBipedTagDataAsset`, `BlamWeaponTagDataAsset`, …). The engine keeps every
live `UObject` in **`GUObjectArray`**, which this repo already resolves with a
stable UE4SS signature (`signatures/GUObjectArray.lua`; the AOB wildcards the
RIP-relative displacement and decodes it at runtime, so it survives updates —
see `signatures/README.md`).

Enumerating them is instant. Via the game bridge (UE4SS Lua):

```
FindAllOf("BlamBipedTagDataAsset")  -- 25 biped assets, addresses in hand
```

116 asset UObjects across four classes came back with no measurable delay.

**Implication:** the tag editor (a separate process) can read `GUObjectArray`
over `ReadProcessMemory` — resolve the global once per build from the on-disk
exe (the `tools/pe/aob_scan.py` machinery already does AOB scans), walk the
`FUObjectItem` array, deref each `UObject`, read its class and object `FName`,
and filter to `*TagDataAsset`. That is a bounded read of a few MB, not a 13 GB
sweep, and it answers "what is loaded / which level" in well under a second —
and more reliably than fingerprinting the scenario tag. This is the recommended
next step and does **not** depend on Finding 2.

## Finding 2 — the pokeable buffer is *not* reachable from the UObject

The obvious hope — `UObject + fixed offset → data buffer` — does not hold.
For all 32 name-matched biped/weapon/vehicle/scenario UObjects, the census's
verified buffer address (`base`, and `base + r0` the resident-allocation start)
appears **nowhere** in the UObject's first 8 KB, and **nowhere** one pointer
hop away through any heap-pointer slot in that window. Zero of 32, both targets.

This confirms the long-standing comment in `crates/blam-live/src/lib.rs`: the
tag asset UObject holds its payload as *unloaded bulk data*. The buffer the
simulation actually reads lives in a **separate Blam-side runtime structure**,
not the UE wrapper. `GUObjectArray` gets you the list, but not the buffer.

## Finding 3 — the buffers live in scattered per-tag records that store `base`

A pointer scan (sweep for aligned 64-bit values equal to a verified buffer
address) found **259 holders covering 240 of 369 tags**. Every holder stored
`base` — the *synthetic* "payload byte 0" address (`data_start − r0`), never
`base + r0`. So the engine keeps each buffer positioned such that a field is
read at `base + file_offset`, exactly the addressing `blam_live` already uses.
That is strong independent confirmation the located address is the real thing.

The holders do **not** form one dense array (no fixed-stride table emerged).
They sit ~0x420–0x1040 bytes apart in heap regions — i.e. one runtime structure
of ~1–4 KB per loaded tag, each holding the buffer pointer plus metadata. The
8 bytes after the pointer are *not* the data-section length (`r1 − r0`); the
record layout past the pointer is not yet decoded.

## What's left to make poke scan-free

The remaining unknown is the path from something static to those per-tag
records. Two candidate routes, in order of promise:

1. **A Blam tag-cache root.** The 259 records are presumably owned by a Blam
   tag manager. Find its root (signature on the code that allocates or indexes
   these records, or a `.data` global pointing at the record pool), then index
   by tag id / path. Chase: `global → record[tag] → buffer`.
2. **A deeper UObject link.** The `UObject → buffer` path may exist but be more
   than one hop, through the UE property graph rather than raw offsets — best
   walked with UE4SS reflection, then frozen into offsets once the shape is
   known.

Until then the census sweep stays as the fallback that needs no engine
knowledge, and Finding 1 removes the sweep from the common case (knowing what
is loaded). The scan probes that produced these numbers are not committed —
they were throwaway `#[ignore]`d tests reading a JSON dump of verified hits;
this note has enough to reconstruct them.

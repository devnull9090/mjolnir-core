# Getting an Edited Tag Into the Game

**Status:** **Solved. An edited tag runs in the game.** A single-chunk override container named
with the `_P` patch suffix mounts, wins the chunk lookup, and its Blam payload is what the
simulation uses. Verified by editing the assault rifle's magazine to 99 rounds and its ammo
reserve to 900 and reading both off the HUD in mission A30.

Two caveats, both since resolved, both in the perfect hash. It used to be wrong for containers
holding more than one chunk, so multi-chunk containers silently exposed only one of their
chunks; and after that was fixed it still spilled every chunk to the unread overflow list at
power-of-two chunk counts, so a four-tag mod silently did nothing. See *A real bug found on the
way* and *A second hole in the same place* for the history and the fixes.
**Build:** `2026.06.26.1097863.1-Rel-i343-Meteorite-2606-CU2` (Steam)

Tags can be read, edited and written back byte-exactly
([`tag_body_format.md`](tag_body_format.md), [`tag_editing_guide.md`](tag_editing_guide.md)). This
note is the last step: making Halo Campaign Evolved *load* the result.

It is written as a working log, oldest first, so the reasoning stays legible — including two
conclusions that were wrong and how they were caught. If you only want the recipe, read
[`getting_started.md`](getting_started.md) instead.

> **Build label:** this note is stamped CU2; the installed build is CU3. See
> [`build_lock.md`](build_lock.md) for what has been re-verified against CU3 and for a
> caveat about CU2-stamped notes dated after 2026-08-01.

## The problem, as it stood

The game loads tags from UE5 IoStore containers — `.utoc` index plus `.ucas` data — under
`Meteorite/Content/Paks`. `crates/ue-iostore` read them; nothing wrote them.

So an edited tag had nowhere to go. It exported to a file, and that file was for inspection and
diffing, not for playing. `ue_iostore::pack` and `mjolnir pack` now close that gap — see *Step 2*.

## What is established

**Verified** by reading the shipped containers.

### The containers

| | |
|---|---|
| Containers | 28 `.utoc`/`.ucas` pairs |
| TOC version | 8 (`ReplaceIoChunkHashWithIoHash`) |
| TOC header | 144 bytes |
| Compression | Oodle, 64 KiB blocks |
| Encryption | none, and the encryption GUID is zero |
| Signing | none |

`pakchunk0-Windows` holds the bulk of the data: **122,800** chunk entries and a 7.5 MB
directory index. `global.utoc` is at the other extreme — 866 bytes, a single entry, no
directory index at all — which makes it a useful reference for what a *minimal* valid
container looks like.

### Chunk identity

A chunk ID is 12 bytes: a `u64` package ID, a `u16` chunk index, a pad byte, and a type byte.

Types present in `pakchunk0`:

| Type | Meaning | Count |
|---:|---|---:|
| 1 | `ExportBundleData` — the cooked package | 87,226 |
| 2 | `BulkData` — the tag payload | 27,102 |
| 6 | `ContainerHeader` | 1 |
| 8 | `ShaderCodeLibrary` | 2 |
| 9 | `ShaderCode` | 8,469 |

A tag is one package: a type-1 chunk holding the 104-byte cooked `.uasset`, and a **type-2
chunk holding the Blam tag file** — the thing the editor changes.

**This is the load-bearing finding for packaging.** The chunk ID of a tag's bulk data can be
read straight out of the shipped TOC. An override container does not have to *derive* an ID
from a package name or hash; it reuses the identical twelve bytes. That removes what would
otherwise be the hardest unknown.

## What a writer has to produce

Structurally, a `.utoc` is a header followed by parallel arrays. All of it is now written as
well as read — see *Step 1* below:

1. Header — magic `-==--==--==--==-`, version, header size, entry count, compressed-block
   count, block size, compression-method names, directory-index size, partition count and
   size, container ID, flags.
2. Chunk IDs, 12 bytes each.
3. Chunk offsets and lengths, 10 bytes each.
4. Perfect-hash tables, from `VER_PERFECT_HASH` onwards.
5. Compression block entries, 12 bytes each.
6. Compression method names, 32 bytes each.
7. Directory index — mount point, directories, files, string table. `global.utoc` shows this
   can be empty.

The `.ucas` is then the chunk data, in compression-block-sized pieces.

A sensible first target is an **override container holding one chunk**: the patched bulk data
for a single tag, reusing that tag's existing chunk ID, uncompressed, with no directory index.

## What is not established

These are the real unknowns, in the order they need answering.

1. **Does the game mount additional containers at all, and in what order?** UE5 mounts
   `pakchunkN` by priority, and a later mount can shadow an earlier one for the same chunk ID.
   Whether this build does that, and what priority a new container would need, has not been
   checked. If it does not, everything below is moot and the route is a loader mod instead.
   The `Paks/LogicMods` directory exists and is **empty**, so it gives no evidence either way.

2. **Does an override container need its own `ContainerHeader` (type 6)?** That chunk carries
   the package store. A container replacing only *bulk data* for a package that already exists
   may not need to declare the package at all. `global.utoc` having exactly one entry and
   `pakchunk0` exactly one type-6 chunk suggests the header is per-container rather than
   per-package, but this has not been confirmed.

3. **Will the loader accept uncompressed blocks** in a container whose siblings are all Oodle?
   The method table is per-container, so method index 0 meaning "none" should be legal, but it
   has not been tried.

4. **Is bulk data even re-read from the container at load time**, or is it resolved once at
   cook time through an offset the package header carries? The tag payload lives in a separate
   chunk from the package, which suggests the former, but that is an inference.

## Step 1: writing a TOC — done

**Verified.** `ue_iostore::toc` models the index as the format defines it, and writes it back.
`mjolnir toc-roundtrip` parses every shipped `.utoc` and re-emits it:

| Result | Count |
|---|---:|
| Reproduced **byte for byte** | **28 / 28** |
| Differ | 0 |

That covers `global.utoc` at 866 bytes and `pakchunk0-Windows.utoc` at 26 MB — 122,800 chunk
entries, 1,099,338 compression blocks and a 7.5 MB directory index — so steps 1 and 2 of the
original plan are both settled.

The test is not trivially true. Every typed field is re-encoded from its value rather than
copied, so a wrong width, a wrong byte order or a misplaced field shows up as a mismatch. It
caught one immediately: the perfect-hash seed count at byte 84 had been skipped, putting
`partition_size` four bytes early and breaking all 28 at the same offset.

Two details the round-trip pinned down, both easy to get wrong by inspection:

- A **chunk ID mixes byte orders**. The package ID is little-endian, the chunk index that
  follows it is **big**-endian, then a pad byte, then the type.
- **Chunk offsets and lengths are five-byte big-endian**, while a compression block's offset is
  five-byte *little*-endian with three-byte little-endian sizes.

Regions the round-trip does not interpret — the signature block, the directory index, and the
header padding past byte 100 — are carried verbatim, so nothing is lost by round-tripping a
container we do not fully understand. The perfect-hash tables were in that list too when this
was written; they are now generated for real, which the two sections at the end of this document
are the story of.

## Step 2: building a container — done

**Verified.** `ue_iostore::pack` composes an override container and `mjolnir pack` drives it:
apply edits to a tag, reuse the chunk ID from the shipped index, and write a `.utoc`/`.ucas`
pair. Before anything is written it reads the result back through the ordinary reader — the
same path the game would take — and confirms the edits are visible through it. A container our
own reader cannot use is not worth putting in front of the game.

Modelling the index for writing turned up one thing the reader had missed: the region after the
directory index is **24 bytes per chunk**, not a fixed file trailer. Measured across every
shipped container, from the single-chunk ones up to `pakchunk0` with 122,800 chunks. Treating
it as a trailer produced a 2.9 MB index for a one-chunk container, which is how it was caught.

### Reading one back: `mjolnir container`

Being addressed purely by chunk ID is what makes an override work, and also what makes it
opaque — it carries no directory index, so nothing inside it says which asset a chunk *is*.
The names are recoverable, because the shipped containers do carry one, and matching the IDs
back against it turns a list of hex into a list of assets:

```powershell
mjolnir container "$env:HCE_PAKS\pakchunk999-MJOLNIRDEV-super-jump_P.utoc"
```

```
pakchunk999-MJOLNIRDEV-super-jump_P.utoc
  container id 0x4d4a4f4c4e495200
  1 chunk(s)

  0x8da5079fbe947049 BulkData              51023 bytes  .../Tags/objects/characters/Spartans/spartans-biped.ubulk

  1 shipped asset(s) replaced
```

It also reports the ways a container can be silently ignored, which all look identical from
the outside — the mod simply does nothing and the shipped asset loads instead: a name without
the `_P` suffix, chunks that landed in the overflow list (see *the perfect hash* below), and
chunks matching no shipped asset at all. `--verify` additionally reads every chunk back
through the ordinary reader.

## Step 3: making the game use it — in progress

This is where the work stands. See *Current experiment* below.

## Current experiment: does an override container win?

**Answered 2026-07-27: yes, with the `_P` patch suffix.**

| Container present | `BinaryBlobSize` reads |
|---|---:|
| `pakchunk999-MJOLNIR-Windows_P.*` installed | **32640** |
| the same three files moved aside | **32620** |

Both readings come from the same save, the same mission and the same weapon in hand, differing
only by whether the three files were in `Content/Paks`. 32640 is the size our packer wrote.
The shipped chunk no longer wins.

Two things confirmed the mount independently along the way. The `.ucas` could not be moved while
the game ran — *the process cannot access the file because it is being used by another process*
— while the `.utoc` and `.pak` moved freely, which is read-index-once and hold-data-open, exactly
an IoStore mount. And the value tracks the files: put them back, it reads 32640 again.

The measurement itself no longer needs a person. It is
[`game_lua`](game_automation.md) against the running game:

```bash
node tools/mcp/game/cli.mjs lua 'for _, o in ipairs(mj.find("BlamWeaponTagDataAsset")) do
  local n = mj.name(o)
  if n:lower():find("assault", 1, true) then print(n, mj.props(o).BinaryBlobSize) end
end'
```

Which is what made the A/B cheap enough to be worth running properly rather than reasoning about.

This section is the live state of the experiment, written so it can be picked up cold.

### What is installed on the test machine

Not in the repository — these are local, and removing them undoes everything:

```
<install>/Meteorite/Content/Paks/
  pakchunk999-MJOLNIR-Windows_P.pak     339 B   stub (then a copy of pakchunk115-Windows.pak; now written, see below)
  pakchunk999-MJOLNIR-Windows_P.utoc    302 B   built by `mjolnir pack`
  pakchunk999-MJOLNIR-Windows_P.ucas    36 KB   two chunks, uncompressed

<install>/Meteorite/Binaries/Win64/ue4ss/Mods/MJOLNIRTagProbe/   (+ a line in mods.txt)
```

Nothing shipped has been modified. Deleting the three `pakchunk999-*` files reverts the game;
Steam's *Verify integrity of game files* is the backstop.

The container was built with:

```powershell
mjolnir pack --group weapon --tag "assault_rifle-weapon" `
  --set "magazines[0].rounds loaded maximum=200" `
  --set "barrels[0].firing.rounds per second=(2,2)" `
  --set "item.object.generic hud text=MJOLNIR_PROBE_MARKER" `
  --out-dir <somewhere>
```

The third edit resizes the payload from 32,620 to 32,640 bytes, which is deliberate — see the
instrument below. `pack` then also rewrites the package header chunk so its `BinaryBlobSize`
agrees.

### The instrument

Tag *values* are not reachable by reflection. Dumping every property of a loaded
`BlamWeaponTagDataAsset` and its parents yields only:

```
AssetReference, DefaultAssetReference        blueprint actors
CookedAssetsReferencedByTag                  TArray
BinaryBlobSize                               32620
NativeClass
```

The Blam payload is an opaque blob parsed natively. But `BinaryBlobSize` **is** reflected, and
`mjolnir chunk --path assault_rifle-weapon.uasset --find-u32 32620` shows it is stored in the
**package chunk** (type 1) at offset 208, in exactly one place. So changing the payload length
and the header together gives a yes/no that the game itself reports:

| `BinaryBlobSize` reads | Meaning |
|---|---|
| 32620 | the shipped chunk won |
| 32640 | our chunk was used |

Read it with the probe mod, in game, holding the weapon:

```
mjolnir_tag_probe assault_rifle
```

Output goes to `ue4ss/MJOLNIR_TagProbe.txt`. `mjolnir_tag_classes` lists which tag asset
classes are loaded, which is useful orientation first.

### What has been settled

1. **Discovery needs a `.pak` sibling.** Every shipped `pakchunkN` has one; only `global.utoc`
   does not, and that one is mounted explicitly by the engine. A `.utoc`/`.ucas` pair alone was
   never picked up. Several shipped containers pair a **339-byte stub** `.pak` with a large
   `.ucas`, so a stub is legitimate rather than a hack — and it is now written rather than
   copied (see [The stub `.pak`, written](#the-stub-pak-written)).

2. **The container does mount.** Attempting to overwrite the `.ucas` while the game ran failed
   with *device or resource busy*, while the `.utoc` overwrote freely. A process does not hold a
   handle to a file it never mounted, and read-index-once / hold-data-open is exactly an IoStore
   mount. This is the strongest evidence available without engine logging, which is compiled out
   of the shipping build (`Meteorite.log` is 0 bytes).

3. **The `_P` suffix is what makes the override win.** Without it, `BinaryBlobSize` read 32620;
   with it, 32640. This is UE's documented patch-container convention and it applies here.

4. `pakchunk999` numbering does **not** confer priority. The number identifies which content
   chunk a file is, not its mount order.

5. **A container overriding an existing package does not need its own `ContainerHeader`.** Ours
   has no type-6 chunk and is used anyway, which settles open question 2 above.

6. **Uncompressed blocks are accepted** in a container whose siblings are Oodle-compressed.
   Ours stores blocks uncompressed and the loader read them, which settles question 3.

### The bulk data chunk *is* used — once the container is built correctly

**Answered 2026-07-27.** A one-chunk container holding a 32,620-byte payload — the shipped length,
so no package header rewrite is needed — put edited values into the running game:

| Field, in `magazines[0]` | Before | Edited to | HUD showed |
|---|---:|---:|---|
| `runtime rounds inventory maximum` | 324 | **900** | reserve **900** |
| `rounds loaded maximum` | 200 | **99** | magazine **99** after a reload |
| `rounds reloaded` | 36 | 99 | one press filled the magazine |

"Before" is what the copy being edited held, not necessarily what ships: this payload already
carried an earlier edit that set `rounds loaded maximum` to 200, so the shipped magazine capacity
was never read. The other two are shipped values. Nothing here depends on knowing the difference —
900 is the number that matters, and it appears in neither.

900 is not a number that exists in the shipped game. The reserve read `900`, and after one reload
the magazine read `99` with `861` left — 900 less the 39 it took to top up from 60. That is the
edit, in the simulation, on screen.

`rounds reloaded` is the field that made every earlier ammo reading confusing: a reload adds a
fixed number of rounds rather than filling the magazine. At the shipped 36 that is why 32 became 68
and 30 became 66, and why the magazine never showed the 200 an earlier edit had already set.
Raising it alongside the maximum is what turns a reload into a clean yes/no.

#### Two things had to be right at once

Earlier runs found the payload apparently ignored — 98% of it overwritten with `0xDE` and the game
still played. That was true but misread, and a user observation caught it: with the payload
corrupted the player spawned holding the **pistol and could not switch weapons**; with it intact
the assault rifle was there as normal. The tag *was* being read. A broken one simply failed to
produce a usable weapon, and that fallback looked like "nothing happened" in screenshots that were
being read for ammo counts rather than for which gun was in shot.

No earlier run had both of these true:

1. **The bulk chunk has to be the one the perfect hash resolves to.** In the original two-chunk
   container it was not — see the hash bug below.
2. **The payload has to be the length the package header declares.** The earlier payload was 32,640
   bytes because a marker string had resized it, against a shipped header saying 32,620. Clearing
   that string returned it to 32,620 and removed the need for a package chunk at all.

So the working recipe is: **edit only fixed-width fields so the payload keeps its length, and ship
a single bulk chunk.** No package chunk, no `ContainerHeader`, no compression, and no hash
collision to worry about.

#### The runs that got there

| Container | Payload | `BinaryBlobSize` | Result |
|---|---|---:|---|
| 2 chunks, seeds `[-1, -2]` | intact, 32,640 | 32640 | plays; payload edits do **not** apply |
| 2 chunks, seeds swapped `[-2, -1]` | intact, 32,640 | 32620 | plays, assault rifle present |
| 2 chunks, seeds swapped | 98% `0xDE` | 32620 | plays, **pistol only, cannot switch** |
| 1 chunk, bulk only | 98% `0xDE` | 32620 | plays, **pistol only** |
| **1 chunk, bulk only** | **edited, 32,620** | 32620 | **99-round magazine, 900 reserve** |

Rows three and four are the ones that were misread at the time: the pistol fallback *was* the
payload taking effect, and it was recorded as "nothing happened". Row two versus row three is the
controlled pair — same checkpoint, same container shape, only the payload bytes differ.

### A real bug found on the way: the perfect hash is wrong for multi-chunk containers

**Fixed.** See the end of this section for what the fix turned out to be; the analysis below is
kept as written because the misread it documents is instructive.

[`pack.rs`](../crates/ue-iostore/src/pack.rs) wrote one seed per chunk, `-1, -2, -3, …`, on the
theory that seed *i* names entry *i*. It does not. UE picks the seed by hashing the chunk ID:

```
slot  = hash(chunk_id) % seed_count
seed  = seeds[slot]
entry = -seed - 1                      (negative seeds)
if chunk_ids[entry] != chunk_id: not found
```

Positional seeds are only correct when every chunk happens to hash to its own slot. For one chunk
that is guaranteed; for two it is a coin flip; beyond that it is vanishingly unlikely. There is no
safety net either — `chunks_without_perfect_hash` is written as 0.

**Confirmed by experiment, not by reading.** Swapping the two seed words — an eight-byte edit to a
302-byte file — flipped `BinaryBlobSize` from 32640 to 32620. That is only possible if the seed
decides which chunk is reachable, and if both of our chunk IDs land on the same slot. Our two-chunk
container was therefore only ever exposing *one* of its two chunks, and which one was luck.

This also qualifies two earlier findings. "An override needs no `ContainerHeader`" and
"uncompressed blocks are accepted" are still true, but they were only ever tested against the one
chunk that happened to win.

Fix, cheapest first — as it stood before the fix:

1. Emit no perfect hash at all (`seed_count = 0`) and let the reader build a plain map, if this
   build accepts it.
2. Otherwise list every chunk in `chunks_without_perfect_hash`, the format's own escape hatch.
3. Only if neither works, implement `HashChunkIdWithSeed` and solve for seeds.

**What was actually done (2026-08-01): option 3**, because it turned out to be verifiable
without touching the game. `hash_chunk_id_with_seed` in
[`toc.rs`](../crates/ue-iostore/src/toc.rs) is the engine's function — FNV-1a's prime over the
twelve raw ID bytes, multiply-then-xor, seeded by the offset basis or the seed itself. The two
details a reimplementation could plausibly get wrong were pinned down empirically against the
shipped tables: the downstream modulo is taken on the **full 64-bit hash** (truncating to 32
bits first resolves ~0 of pakchunk0's chunks), and the seed is sign-extended from its signed
32-bit table slot.

`Toc::find_chunk` implements the reader's lookup — seed slot by `hash(0, id) % seed_count`,
negative seed as direct index, positive seed as rehash, overflow scan as fallback — and an
ignored test (`MJOLNIR_PAKS=<Paks dir> cargo test -p ue-iostore -- --ignored`) resolves **every
chunk of every shipped container, 141,564 across 29, through that lookup**. Since those tables
were written by the engine, agreement at that scale is not luck; the hash is right.

The packer now does real placement: chunks are bucketed by `hash(0) % seed_count`, buckets
solved largest-first for a positive seed that lands every member in a distinct free slot,
single-chunk buckets stored as direct negative seeds, and unplaceable buckets (duplicate IDs)
spilled to `chunks_without_perfect_hash`. The per-chunk TOC arrays are permuted so the entry
index *is* the hash slot. A one-chunk container still comes out with the shipped shape — one
seed, `-1` — so nothing about the verified single-chunk recipe changed.

### A second hole in the same place: spilling at power-of-two chunk counts

**Found and fixed 2026-08-02**, by a three-tag mod that stopped working the moment it became a
four-tag mod.

The placement above is right, but it was only ever tried at one table size — the engine's
`seed_count = n / 2`. That size is not always solvable. The rehash hop is
`hash(seed, id) % n`, and modulo a power of two that sees only the hash's low bits, where
FNV's multiply barely diffuses. Mod 2 it does not diffuse at all:

```
hash(seed, id) % 2  ==  (seed % 2) XOR K(id)
```

`K` does not depend on the seed, so two IDs agreeing on it are inseparable by *every* seed. The
bucket search cannot succeed however long it runs — the 2²⁰-iteration cap was never the binding
constraint.

Measured on the mod that hit it (spartans biped, both fall-damage effects, globals): the four
IDs pair two-and-two under `K`, both buckets spilled, `chunks_without_perfect_hash = 4`, and
**0 of 4 chunks resolved**. In game the mod silently did nothing — the shipped tags loaded and
the edits looked as though they had never been made. The same mod at three tags worked, which is
what made it look like a tag problem rather than a packing one.

Two things changed:

1. **`generate` grows the seed table** until nothing spills, starting from the engine's `n / 2`
   so the common case still matches the shipped shape. Growing it is free — the reader takes the
   count from the header — and a bucket holding one chunk becomes a direct index that never
   rehashes, so splitting an inseparable pair into separate buckets sidesteps the dead bits
   entirely.
2. **Spilling is treated as failure, not fallback.** No shipped container populates the overflow
   list — 28 scanned, every one `without_hash = 0` — and this build gave no sign of reading it.
   `blam_pack::verify_written` now rejects a container with a non-empty overflow list and
   resolves every chunk through `Toc::find_chunk_by_hash`, the perfect hash alone.

The second point is why this shipped at all. `verify_written` searched `load_container`'s chunk
list, which proves the bytes are present and nothing about whether the tables find them; the
packer's tests resolved through `Toc::find_chunk`, whose overflow scan is more forgiving than
the game. Both oracles passed a container the game ignored. The regression tests now assert
`chunks_without_perfect_hash == 0` and cover n = 2, 4, 8, 16 and 32 alongside the four real IDs.

### Two-chunk containers verified in game — and a string-id hazard found

**Answered 2026-08-02, with the fixed perfect hash.** A two-chunk container (resized payload +
rewritten package header) built by `blam-pack` works end to end. The A/B/C, all from a fresh
mission-select A30 spawn:

| Container | `BinaryBlobSize` | In game |
|---|---:|---|
| none (vanilla) | 32620 | assault rifle in hand, normal |
| resized via a **novel string id** (`generic hud text = "MJOLNIR_RESIZE_MARKER"`, 32641 B) | **32641** | **pistol-fallback: magnum only, cannot switch** |
| resized via a **valid tag reference** (`barrels[0].projectile` → the needler shard, 32608 B) | **32608** | **assault rifle in hand, firing needler shards** |

Run three is the proof: the package chunk applied (32608 by reflection) *and* the bulk chunk
applied (pink needles on screen, magazine draining), both chunks served from one container
through the solved perfect hash. Screenshots and the cradle-widget reads came through the
[game automation](game_automation.md) bridge; the ammo counter is reachable as a live UMG
widget (`WBP_HUD_Main … WeaponCradle … CurrentAmmoCountTextBlock`), which is a better
instrument than pixels.

Run two is the discovery that replaces the old caution: **a `string id` set to text the game's
string table does not already contain makes the native parser reject the whole tag**, and a
rejected weapon degrades to the documented pistol-fallback. The 2026-07-27 marker-string
container never exposed this — with the broken hash, only its package chunk was ever served, so
the poisoned payload was never parsed. The tag editor now warns on any string-id edit at
test/export time.

### What this means for the editor

Editing a tag and shipping the result **works end to end, including resizes**. Fixed-width
fields — integers, reals, enums, flags — edit in place; string-id and tag-reference edits that
resize the payload bake into a verified two-chunk container. The one known content hazard is
the novel-string-id rejection above: reference only strings and tags the game already ships.

### Notes on measuring this

The obvious route — change a weapon value and watch the game behave differently — is a trap, for
two reasons found on 2026-07-27:

- **Ammo counts are not reachable by reflection.** Not on the pawn, not on the first-person
  weapon actor, not on any HUD object; a scan of every loaded object for the literal reserve
  value found nothing. The counts live in the Blam simulation, which is consistent with the tag
  payload being an opaque blob parsed natively. So the value has to be read off a screenshot, or
  a native path has to be found.

- **Screenshot readings were confounded by save state.** With the override the magazine reloaded
  to 68 rounds and without it to 66, but the two runs resumed from different points, so a
  two-round gap establishes nothing. Neither matched the 200 the edit set, which is itself worth
  explaining.

#### Where the two chunks live in our container

Decoding `pakchunk999-MJOLNIR-Windows_P.utoc` by hand, so the corrupt-a-chunk test can hit one
without touching the other. All 302 bytes of it:

| Region | At | Contents |
|---|---:|---|
| Header | 0 | version 8, 2 entries, 2 blocks, 64 KiB block size, container ID `MJOLNIR` |
| Chunk IDs | 144 | entry 0 type **2** (bulk), entry 1 type **1** (package) — same package ID |
| Offsets/lengths | 168 | entry 0 → logical 0, 32640 · entry 1 → logical 65536, 3628 |
| Perfect-hash seeds | 188 | two `u32`, no chunks-without-hash array |
| Compression blocks | **196** | block 0 → `.ucas` 0, 32640 · block 1 → `.ucas` 32640, 3628 |

The subtlety is that chunk offsets are **logical**, not file offsets: entry 1 sits at 65536,
past the end of a 36,272-byte file, because logical space is quantised to the 64 KiB block size.
The compression block table is what maps it down. So in the `.ucas`:

```
bytes      0 .. 32640   the Blam payload      (type 2)
bytes  32640 .. 36268   the package header    (type 1, holds BinaryBlobSize)
```

That separation is what made the answer reachable: corrupting `0..32640` leaves `BinaryBlobSize`
readable, so one run reports both whether the container still mounts *and* whether the payload is
parsed. Corrupting the payload is a better instrument than changing a value in it, because it
needs no interpretation and cannot be confounded by save state — which the ammo readings were.

The whole run, launch to measurement, is a handful of commands and about four minutes; see
[`game_automation.md`](game_automation.md). Reproduce it with:

```powershell
# game must not be running -- it holds the .ucas open while mounted
$ucas = "<install>\Meteorite\Content\Paks\pakchunk999-MJOLNIR-Windows_P.ucas"
Copy-Item $ucas "$ucas.bak"
$bytes = [System.IO.File]::ReadAllBytes($ucas)
for ($i = 512; $i -lt 32640; $i++) { $bytes[$i] = 0xDE }   # payload only
[System.IO.File]::WriteAllBytes($ucas, $bytes)
```

then launch, start A30, and read `BinaryBlobSize`. Restore from the `.bak` afterwards.

## Why not a `.pak`

The game ships both `.pak` and `.utoc`/`.ucas`, and the `.pak` files are large — 2.5 GB for
`pakchunk0`. It is tempting to think loose cooked assets in a `.pak` would override.

They will not, for the tags. The tag payloads are IoStore **chunks**, addressed by chunk ID
through the zen loader, not by file path through the pak mount. A `.pak` override would have
to reach the package store, which is what the IoStore container is for.

### The stub `.pak`, written

Every shipped stub is the same 339 bytes apart from two fields. It is an empty version-11
archive: a primary index holding the mount point `/`, zero entries, a path-hash seed, and the
offsets, sizes and SHA-1s of an empty path-hash index (8 zero bytes) and an empty full
directory index (4 zero bytes); then the `FPakInfo` footer — a zero encryption GUID, the magic
`0x5A6F12E1`, version 11, the index offset and size, the SHA-1 of the primary index, and five
empty compression-method names. Only the seed and the footer hash differ between shipped
stubs, and with no entries the seed hashes nothing. `ue_iostore::pak::write_stub` reproduces
`pakchunk115-Windows.pak` byte for byte from that file's own seed (a unit test checks it when
`HCE_PAKS` is set), and `stub_for(name)` seeds from the container name so a rebuild is
identical. The CLI, the tag editor's test install and the launcher-facing export all write it;
nothing copies a shipped file any more.

## New packages register and resolve by name

**Answered 2026-09-05** (build CU4, mission A30). A brand-new tag package — the marine's
collision model cloned under `/Game/Tags/objects/characters/marinf/marinf-collision_model` by
`mjolnir new-tag`, in a `_P` container carrying only its own `ContainerHeader`
(`blam_pack::build_addition`) — was loaded by the simulation when the marine `model` tag's
`collision model` reference was repointed at it with `mjolnir pack`. No tag imported it. The
simulation's own tag table (`mjolnir live tags --filter marinf`) listed it as the 7,056th loaded
tag, and the model's resident reference held its handle. Details in
[`tag_table_and_string_ids.md`](tag_table_and_string_ids.md).

Three earlier open items close with it: the runtime tag registry is enumerated from what is
mounted; a mod container's own `ContainerHeader` is honoured; references resolve by name on
demand. The same-length rename constraint on the wrapper is the remaining limit, and it is the
wrapper serializer's job to lift.

The tag editor exposes the same path as **New Tag From This…** (tag editor 0.18.0). The clone
is a virtual entry in the catalogue that reads as its donor; its edits are recorded under the
new name in the project's `edits.json` (`new_tags`); a bake builds each one with
`blam_pack::newtag` — shared with `mjolnir new-tag` — into an addition container beside the
override containers, named `<slug>-new_P` (then `<slug>-new-2_P`, …), one per package folder
because the container's directory index names a single directory.

**Proven in game, 2026-09-06:** the editor's own bake path (`resolved_edits` → `modpack::bake` →
`modpack::install_test`, staged by the ignored test `stage_a_new_tag_for_the_in_game_test`)
cloned the assault rifle's projectile as `assault_rifle_bullet_mk3` and repointed the rifle at
it — one resized override container plus one addition container, both with written stubs. On the
next launch of A30 the tag table listed the clone (`mjolnir live tags --filter
assault_rifle_bullet`: slot 357, handle `0xE2D90165`, 7,056 loaded tags against the shipped
7,055) and the rifle fired normally with no fallback.

## Writing the wrapper

**Measured 2026-09-05** against every `.uasset` under `Tags/` across all containers (12,332 —
the 12,290 tags plus a few dozen region string tables, Niagara systems and one Blueprint that
share the folder). `ue_asset::package::ZenPackage` parses the whole cooked package header and
serializes it again; `mjolnir zen-roundtrip` is the gate.

| Check | Result |
|---|---:|
| re-serialized byte-exact | **12,332 / 12,332** |
| bare wrappers rebuilt from `(group, path, payload length)` alone, byte-exact | **2,871 / 2,871** |
| name-batch hash = CityHash64 of the lowercased name | 12,332 / 12,332 |
| package id = CityHash64 of the lowercased UTF-16LE package name | 12,332 / 12,332 |
| export hash = the same over the object (leaf) name | every tag |
| class / CDO = ScriptImport index of `/Script/BlamSynchronization.Blam<Pascal(group)>TagDataAsset` and its `Default__` | every tag |
| one bulk entry `{0, -1, size, 66817, 0}`, size = `.ubulk` length | every tag (one shipped sound declares 4,700 bytes and ships no `.ubulk`) |
| export body framed `[00 00 00 00] … [00 00 00 00]` | every tag |
| flags `0xb / 0x80002200`; `0x1 / 0x88002200` on the five level-resident groups; `0x3` on `sound` | every tag |
| bulk map padded to 8 bytes after the name batch | 12,332 / 12,332 |

Layout details the reader had wrong or missing before: the bulk-data map is preceded by a `u64`
pad size and that many zero bytes; a package import in the import map is
`(imported package index << 32) | index into the imported public export hashes` under the type-2
tag; the imported-package-names section is a name batch **followed by one `u32` FName number per
name** (an imported `BP_Hood_10` is stored as base `BP_Hood_` + number 11), and an empty batch is
the 4-byte count alone. The cooker's import slot order interleaves package imports between the
CDO and the class and is not reproducible; it does not need to be.

`cooked_header_size` is the *legacy* header's size: `617 + 2·len(package) + len(object) +
2·len(class)` for every bare wrapper, but with imports it depends on legacy import names the zen
header does not carry. **The game does not read it for tag packages**: the marinf collision model
was reinstalled with the field set to 9999 and loaded and resolved exactly as before.

**Proven in game, 2026-09-05:** `mjolnir new-tag` built `objects\characters\marine\marine_clone`
(a collision model, path longer than any donor's) from scratch with `ZenPackage::bare_tag`, and
`mjolnir pack` repointed the marine model at it — a resizing reference edit, so the model rode a
two-chunk override with its `BinaryBlobSize` rewritten. After a relaunch into A30 the tag table
listed `marine_clone` and the model's resident reference held its handle with the longer name.
The wrapper needs no donor and no length constraint for the 47 bare groups.

### The property encoder — wrapper-bearing groups

The 54 groups whose class adds properties (`AssetReference`, `CookedAssetsReferencedByTag`,
`bSpawnPerInstance`, `ModelRegionStringTable`, `RuntimeVariants`) are covered by
`ue_asset::props` — a lossless decoder and encoder for unversioned property blocks over the value
kinds tags use (object, bool, integer, name, array, map, reflected struct, soft object path) —
and `ue_asset::tagwrap`, which builds the whole wrapper from a `WrapperSpec`: the binding, the
preload list, the variants. Measured with `mjolnir zen-roundtrip`:

| Check | Result |
|---|---:|
| export bodies decoded against the wrapper class | 12,161 / 12,162 (the one miss is the customization-globals tag, whose nested struct uses a zero mask) |
| decoded bodies re-encoded byte-exact | **12,161 / 12,161** |
| wrapper-bearing wrappers read back into a spec, rebuilt, and read again: same spec, same dependency order, same names | **9,408 / 9,456** |

The 48 that differ are the 13 `scenario` tags, whose dependency bundles the cooker orders
differently from their preload arrays (scenario authoring is deferred), and the non-tag packages
under the folder. Bytes are not compared: the cooker's import slot order is its own, and the
name map's order is cosmetic — the shipped maps put `None` first in one model and in alphabetical
position in another. `RF_Transactional` is treated as inert (2,563 sound tags ship without it).

Layout facts pinned on the way: a package import is `(imported package index << 32) | index into
the imported public export hashes`; `FName` numbers split off a trailing `_<digits>`
(`BP_Hood_10` is stored as `BP_Hood_` plus number 11); the dependency bundle lists the body's
object references base-class properties first; `None` and `none` are distinct name-map entries.

**Proven in game, 2026-09-05:** `mjolnir new-tag` built
`objects\weapons\rifle\assault_rifle\projectiles\assault_rifle_bullet_mk2` — an object-group
tag bound to `BP_AssaultRifleBulletProjectileActor`, its preload list derived from the body's
own references — and `mjolnir pack` repointed the assault rifle's barrel at it. In A30 the tag
table listed the projectile (slot 357) and the rifle fired it: a seven-round burst took the
magazine from 36 to 29 with no fallback. `new-tag` now builds every group's wrapper from scratch;
the same-length surgery is no longer needed for tags.

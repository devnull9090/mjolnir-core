# Getting an Edited Tag Into the Game

**Status:** **The override wins.** A container named with the `_P` patch suffix is mounted and
its chunk is used in place of the shipped one, confirmed by A/B measurement in the running game
— see *Current experiment*. What remains is whether the **bulk data** chunk is used too, not
whether override containers work at all.
**Build:** `2026.06.26.1097863.1-Rel-i343-Meteorite-2606-CU2` (Steam)

Tags can now be read, edited and written back byte-exactly
([`tag_body_format.md`](tag_body_format.md), [`tag_editing_guide.md`](tag_editing_guide.md)).
What is still missing is the last step: making Halo Campaign Evolved *load* the result.

This note records what is established about that, and what is not, so the work can start from
facts rather than from scratch.

## The problem

The game loads tags from UE5 IoStore containers — `.utoc` index plus `.ucas` data — under
`Meteorite/Content/Paks`. `crates/ue-iostore` reads them. Nothing writes them.

So an edited tag currently has nowhere to go. It exports to a file, and that file is for
inspection and diffing, not for playing.

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

Regions that are not yet interpreted — the perfect-hash tables, the signature block, the
directory index, and the header padding past byte 100 — are carried verbatim, so nothing is
lost by round-tripping a container we do not fully understand.

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
  pakchunk999-MJOLNIR-Windows_P.pak     339 B   stub, copied from pakchunk115-Windows.pak
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
   `.ucas`, so copying a stub is legitimate rather than a hack.

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

### What is still open

**Is the type-2 bulk data chunk used, or only the type-1 package chunk?** `BinaryBlobSize` lives
in the package chunk, which `pack` rewrites, so 32640 proves the *package* chunk is ours. It does
not prove the Blam payload beside it is being read. That is open question 4 from above, and it is
now the only one left.

Measuring it is harder than it looks. The obvious route — change a weapon value and see the game
behave differently — ran into two problems on 2026-07-27:

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

Which is exactly the separation the remaining question needs: corrupting `0..32640` leaves
`BinaryBlobSize` readable, so one run says both whether the container still mounts *and* whether
the payload is parsed.

**Attempted 2026-07-27, not completed.** 256 bytes at offset 16,384 were overwritten with `0xDE`
and the game launched and reached the frontend menu without complaint — but the frontend does not
load the assault rifle tag, and the machine locked before a mission could be started, which blocks
synthetic input. Reaching the menu proves nothing either way. The file has been restored. Redo it
by starting mission A30 and reading `BinaryBlobSize`.

Two better instruments, in order of preference:

1. **Pick a payload field that surfaces through reflection.** `BinaryBlobSize` worked precisely
   because it is a reflected property. If any other cooked property is derived from the payload,
   it can be A/B'd the same way and the answer arrives in one run.

2. **Corrupt the bulk chunk deliberately** and see whether the game breaks. If it does, the
   payload is being read; if nothing changes, it is not. That separates "not selected" from
   "selected and used" without needing to interpret a number, and unlike a subtle value change it
   cannot be confounded by save state.

Both are now cheap to run — see [`game_automation.md`](game_automation.md). A full A/B, launch to
measurement, is a handful of commands and about four minutes.

## Why not a `.pak`

The game ships both `.pak` and `.utoc`/`.ucas`, and the `.pak` files are large — 2.5 GB for
`pakchunk0`. It is tempting to think loose cooked assets in a `.pak` would override.

They will not, for the tags. The tag payloads are IoStore **chunks**, addressed by chunk ID
through the zen loader, not by file path through the pak mount. A `.pak` override would have
to reach the package store, which is what the IoStore container is for.

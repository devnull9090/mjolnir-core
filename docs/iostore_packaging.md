# Getting an Edited Tag Into the Game

**Status:** Containers can be built and the game mounts them. The override does not yet win
the chunk lookup — see *Current experiment* below, which is where to pick this up.
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

**Status as of 2026-07-27: the container mounts, but the shipped chunk still wins.**

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

3. **Our chunk does not win the lookup.** With the container mounted, `BinaryBlobSize` still
   reads 32620.

4. `pakchunk999` numbering does **not** confer priority. The number identifies which content
   chunk a file is, not its mount order.

### Next steps

**Currently awaiting a test result:** the three files were renamed to the `_P` patch suffix,
which is UE's documented way to mount on top of existing content. Re-run the probe. If
`BinaryBlobSize` is 32640, this is solved and the remaining work is generalisation.

If it still reads 32620, in order of suspicion:

1. **The 24-byte chunk-meta record.** `pack` copies the record belonging to the chunk being
   overridden. If those bytes are a content hash — plausible for version 8, which replaced the
   chunk hash with an `IoHash`, and 20 bytes of hash plus 4 of flags fits exactly — then ours is
   stale and the loader may find our chunk and reject it. Establishing the hash function is the
   fix. This is the leading theory once priority is ruled out.

2. **First mount wins rather than highest priority.** If the chunk map is built once at startup,
   an override has to be mounted *before* `pakchunk0`, not after. Testable by naming the
   container so it sorts first.

3. **The container may need its own `ContainerHeader` (type 6) chunk.** Every shipped container
   has exactly one. Ours has none, on the theory that a container overriding chunks of an
   already-declared package does not need to declare it. That theory is untested.

4. **Compression.** Ours stores blocks uncompressed while `pakchunk0` uses Oodle. `pakchunk1`
   ships uncompressed, so this is legal in general, but not proven legal for an override.

A useful non-obvious check: make the override deliberately **invalid** — corrupt bytes in our
chunk — and see whether the game breaks. If it does, our chunk is being read and the problem is
elsewhere. If nothing changes, it is not being read at all. That separates "not selected" from
"selected and rejected" in one run.

## Why not a `.pak`

The game ships both `.pak` and `.utoc`/`.ucas`, and the `.pak` files are large — 2.5 GB for
`pakchunk0`. It is tempting to think loose cooked assets in a `.pak` would override.

They will not, for the tags. The tag payloads are IoStore **chunks**, addressed by chunk ID
through the zen loader, not by file path through the pak mount. A `.pak` override would have
to reach the package store, which is what the IoStore container is for.

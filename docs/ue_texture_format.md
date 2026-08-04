# Cooked Texture2D / Virtual Texture Format in Halo Campaign Evolved

**Status:** Verified against the installed build
**Last verified:** 2026-08-03
**Game build:** `2026.06.26.1097863.1-Rel-i343-Meteorite-2606-CU2`

A shipped `Texture2D` in this build cooks one of two ways, and both are common:

- **Virtual texture** — about half the catalogue. The `.uasset` export carries
  `FVirtualTextureBuiltData`-shaped metadata and the pixel payload lives in the
  sibling `.ubulk` as fixed-size tiles addressed by Morton code.
- **Classic mip chain** — the rest. Each mip is either appended to the `.ubulk`
  in order, or carried inline in the export itself.

Decoding was verified across the whole install: 4787 of 4844 textures decode.
The other 57 ship no pixel data at all — 52 are render targets or otherwise
runtime-generated (no `PF_` name in the export), and 5 are virtual textures
whose `.ubulk` was never cooked into the paks.

> An earlier revision of this document claimed *every* texture was virtual.
> That came from a 250-asset sample which happened to miss the classic chains.

## Locating the metadata

The export's serial data begins with unversioned properties (not parsed).
Anchor on the first `FString` whose text starts with `PF_` (e.g. `PF_DXT1`) —
the pixel-format name of `FTexturePlatformData`. The twelve bytes immediately
before it are `SizeX (u32) SizeY (u32) PackedData (u32)`. `PackedData` holds
the slice count in its low 28 bits and cook flags in the top bits, so a
cubemap reads `0x80000006`.

The two `u32` straight after the string are `FirstMipToSerialize` and
`NumMips`, and **`NumMips` is what picks the branch**:

| `NumMips` | Meaning |
|---|---|
| `0` | Virtual texture; `FVirtualTextureBuiltData` follows (below) |
| `> 0` | Classic mip chain of that many mips (see [Classic mip chains](#classic-mip-chains)) |

`SizeX`/`SizeY` are the *authored* size. When the cook applied an LOD bias the
real data is smaller, by a whole number of mip levels in both axes — so treat a
mismatch as a shift to validate, not as a parse error. `T_Plant_Alien_A_D` is
authored 4096×4096 and cooked 1024×1024.

## Virtual textures

After the pixel-format string, in order (all `u32` unless noted). The first two
entries are the `FirstMipToSerialize`/`NumMips` pair described above — a virtual
texture always reads `0 0` there, which is exactly what identifies it.

| Field | Example (chief / guilty) |
|---|---|
| first mip, num mips | `0 0` in both (the virtual-texture marker) |
| unknown[3] | `1 1 1` in both |
| width in blocks | 6 / 2 (equals SizeX/SizeY aspect) |
| height in blocks | 1 / 1 |
| tile size | 128 |
| tile border | 4 |
| layers | 1 |
| tile data bytes | 9248 |
| num mips | 12 |
| width, height | 6144 1024 / 4096 2048 |
| chunk index per mip, `[num mips]` | `0 1 2 2 2 2 2 2 2 2 2 2` |
| mip offset in chunk, `[num mips]` | `4 4 4 221956 …` |
| num tables (= num mips) | 12 |
| per-mip tile offset tables | see below |

Each per-mip table is `FVirtualTextureTileOffsetData`:

```text
Width u32, Height u32          tile-grid dimensions for this mip
MaxAddress u32
nAddresses u32, addresses[n]   sorted range starts (Morton addresses)
nOffsets u32, offsets[n]       base tile offset per range; 0xFFFFFFFF = empty
```

A tile's offset is found by locating the last `addresses[i] <= address` and
computing `offsets[i] + (address - addresses[i])`; an offset of `0xFFFFFFFF`
means no tile exists there. The address of tile `(tx, ty)` is standard Morton:
x bits at even positions, y bits at odd.

After the tables comes a second copy of the pixel-format string, four floats
(the layer fallback colour — matches the texture's average colour), and one
record per chunk: `FIoHash (20 bytes)`, `chunk size in bytes (u32)`, constants
`04 00 00 00 04 04 00 00 00`, `chunk index (u32)`.

## The .ubulk payload

The `.ubulk` is the chunks concatenated in order. Each chunk is a **4-byte
header (observed zero)** followed by tiles of `tile data bytes` each.

A tile covers `tile size` (128) payload pixels plus `tile border` (4) on every
side: 136×136 px, i.e. 34×34 BC blocks = 9248 bytes for DXT1, stored plain
row-major (34 blocks of 8 bytes per row, top to bottom). To reassemble a mip:

```text
for each tile grid position (tx, ty):
    offset = table lookup of morton(tx, ty)      # skip if 0xFFFFFFFF
    tile   = chunk[4 + offset * tile_bytes ..]
    decode 34x34 blocks row-major -> 136x136 px
    copy the centre 128x128 (crop 4px border) to (tx*128, ty*128)
```

Chunk sizes check out exactly: e.g. chief mip0 = 48×8 tiles × 9248 + 4 =
3,551,236 bytes = chunk 0; mips 2–11 share chunk 2 with the mip-offset array
above pointing at each mip's first tile.

## Classic mip chains

When `NumMips > 0` the export holds an ordinary `FTexture2DMipMap` chain, one
entry per mip, largest first. Mip `i` of the chain is `SizeX >> (FirstMipToSerialize + i)`
wide — the cook drops top mips by raising `FirstMipToSerialize` rather than by
rewriting `SizeX`. Each entry is:

```text
bulk reference u32     index into the package's bulk-data map
payload                present only when the mip is stored inline
SizeX u32, SizeY u32, SizeZ u32
```

Nothing in the entry says whether the payload is inline, and the trailing
dimensions come *after* it, so a reader has to probe: if `SizeX, SizeY` sit
right at the cursor the mip lives in the `.ubulk`, and otherwise the payload is
inline and the trailer must land exactly `payload size` bytes further on. That
trailer doubles as a checksum on the whole walk — it validated on every classic
texture in the install.

The external mips are concatenated into the `.ubulk` in chain order starting at
offset 0, with no header or padding. `T_Explosion_H` (2048×2048 DXT5, 12 mips)
puts mips 0–4 in a 5,586,944-byte `.ubulk` — exactly their summed size — and
carries mips 5–11 inline.

A mip holds `SizeZ` slices for a volume texture and `PackedData`'s slice count
for a cubemap or array, all concatenated. Note that a **cubemap's mip trailer
still reports `SizeZ` of 1** even though the payload is six faces, so the two
fields have to be consulted separately. The tag editor decodes slice 0.

## Pixel formats across the whole install

Of 4844 textures: `PF_DXT1` 1867, `PF_BC7` 1209, `PF_BC5` 982, `PF_DXT5` 316,
`PF_B8G8R8A8` 128, `PF_BC4` 108, `PF_FloatRGBA` 65, `PF_BC6H` 44, `PF_G8` 32,
`PF_A32B32G32R32F` 24, `PF_R16F` 12.

Block formats scale the virtual-texture tile byte size (BC7/DXT5/BC5 are 16
bytes per block → 18,496-byte tiles). A mip smaller than one block still costs
a whole block, so a 1×1 DXT1 mip is 8 bytes.

## Writing the format back

Re-encoding an image at the shipped dimensions and pixel format lands on a
payload of *exactly* the shipped byte size — block compression is a fixed cost
per block, not a function of the picture. Every offset above therefore stays
valid, so replacing a texture is a chunk substitution rather than a re-cook, and
for a virtual texture the `.uasset` is not touched at all.

`ue-texture`'s `encode` module does this by rewriting tiles and mips in place
inside a copy of the shipped payload, which leaves anything the reader does not
model — chunk headers, alignment padding, tiles no table points at — exactly as
it was. See [`texture_swapping.md`](texture_swapping.md).

The `FIoHash` in each chunk record is *not* recomputed, and the game plays the
swapped texture regardless: those hashes are cook-time DDC keys, not a runtime
integrity check.

## A caution from the reverse-engineering

The tile byte size divided by small powers of two produces plausible-looking
"sub-tile" structure (2312-byte windows decode into locally coherent 68×68
images under a permutation). This is pure aliasing — slicing 34-block rows at
17-block boundaries — and cost this investigation several detours. The layout
really is the boring one: whole tiles, linear rows.

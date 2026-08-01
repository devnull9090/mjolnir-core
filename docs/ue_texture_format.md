# Cooked Texture2D / Virtual Texture Format in Halo Campaign Evolved

**Status:** Verified against the installed build
**Last verified:** 2026-07-31
**Game build:** `2026.06.26.1097863.1-Rel-i343-Meteorite-2606-CU2`

Every sampled shipped `Texture2D` in this build is cooked as an Unreal **virtual
texture**: the `.uasset` export carries `FVirtualTextureBuiltData`-shaped
metadata and the pixel payload lives in the sibling `.ubulk` as fixed-size
tiles addressed by Morton code. Decoding was verified by reassembling
`T_GuiltySpark_D` (4096×2048 DXT1) and `T_Chief_Armor_20thAnniv_D` (6144×1024
DXT1) into seamless images.

## Locating the metadata

The export's serial data begins with unversioned properties (not parsed).
The virtual-texture block is found by scanning for the first `FString` whose
text starts with `PF_` (e.g. `PF_DXT1`); the twelve bytes immediately before
it are `SizeX (u32) SizeY (u32) NumLayers (u32 = 1)`.

After the pixel-format string, in order (all `u32` unless noted):

| Field | Example (chief / guilty) |
|---|---|
| unknown[5] | `0 0 1 1 1` in both |
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

## Pixel formats observed (250-texture sample)

`PF_DXT1` 39%, `PF_BC7` 28%, `PF_BC5` 21%, `PF_DXT5` 7%, plus scattered
`PF_B8G8R8A8`, `PF_BC4`, `PF_FloatRGBA`, `PF_G8`, `PF_A32B32G32R32F`,
`PF_BC6H`. Block formats scale the tile byte size (BC7/DXT5/BC5 are 16 bytes
per block → 18,496-byte tiles).

## A caution from the reverse-engineering

The tile byte size divided by small powers of two produces plausible-looking
"sub-tile" structure (2312-byte windows decode into locally coherent 68×68
images under a permutation). This is pure aliasing — slicing 34-block rows at
17-block boundaries — and cost this investigation several detours. The layout
really is the boring one: whole tiles, linear rows.

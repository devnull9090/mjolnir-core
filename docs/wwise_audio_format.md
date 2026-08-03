# Where the Audio Lives in Halo Campaign Evolved

**Status:** Verified against the installed build
**Last verified:** 2026-08-03
**Game build:** `2026.06.26.1097863.1-Rel-i343-Meteorite-2606-CU2`

Almost none of the game's audio is reachable through the IoStore reader. The
cooked packages in `.ucas`/`.utoc` hold Wwise *event* metadata; the samples
themselves sit in the `.pak` siblings, which are a completely different
container format. That is roughly 6 GB of content the tag editor could not see
before the `.pak` reader landed.

## What is where

| Location | Contents |
|---|---|
| IoStore, `Meteorite/Content/Audio/**.uasset` | 21,924 Wwise event/type assets and 11,698 LipSync assets. No samples. |
| IoStore, `Meteorite/Content/Audio/cinematic/**.ubulk` | 23 native UE `SoundWave` assets, cooked to **Bink Audio**. Scratch mocap VO. |
| `pakchunk0-Windows.pak` | 9,867 `.wem` + 113 `.bnk` — the language-neutral bank (SFX, music, ambience). |
| `pakchunk1..13-Windows.pak` | One language each: 15,391 `.wem` + 53 `.bnk` per pak. |

The thirteen localised paks are German, Portuguese(Brazil), Chinese(PRC),
Chinese(Taiwan), English(US), Spanish(Spain), Spanish(Mexico), French(France),
Italian, Japanese, Korean and Polish, one per `pakchunk`.

`pakchunk115` and the other high-numbered paks are 339-byte stubs with an empty
index; they are skipped.

## Pak container

Every pak is UE5 pak **version 11**, unencrypted index, compression methods
`[None, Oodle]`. Implemented in `crates/ue-iostore/src/pak.rs`.

The footer is the last 221 bytes: `FGuid` encryption key (16), `bEncryptedIndex`
(1), magic `0x5A6F12E1` (4), version (4), index offset (8), index size (8),
index hash (20), then five 32-byte compression method names.

The primary index at that offset is:

```
FString MountPoint          // e.g. "../../../Meteorite/Content/WwiseAudio/"
int32   NumEntries
uint64  PathHashSeed
int32   bHasPathHashIndex   // + offset(8) size(8) hash(20) when set
int32   bHasFullDirectoryIndex  // + offset(8) size(8) hash(20) when set
TArray<uint8> EncodedPakEntries
int32   NumFiles            // unencodable entries follow, as full FPakEntry
```

The full directory index lives at its own offset and is a plain
`TMap<FString, TMap<FString, int32>>`: directory name, file count, then each
file name and its `FPakEntryLocation`. A location `>= 0` is a byte offset into
`EncodedPakEntries`; a negative one indexes the unencoded list.

### Encoded entry bitfield

Each encoded entry starts with a `u32` whose bits say which fields were
narrowed, so records are variable length:

| Bits | Meaning |
|---|---|
| 31 | offset is 32-bit safe |
| 30 | uncompressed size is 32-bit safe |
| 29 | size is 32-bit safe |
| 28–23 | compression method index |
| 22 | encrypted |
| 21–6 | compression block count |
| 5–0 | compression block size in 2 KiB units |

Then offset, uncompressed size, and — only when a compression method is set —
the stored size, each 4 or 8 bytes per the flags above.

Block extents are **entry-relative** from pak version 9 on. A single
unencrypted block records no extent at all: it starts right after the entry's
inline `FPakEntry` header and runs for the stored size. Two or more blocks each
store a `u32` length, and encrypted payloads pad each block up to 16 bytes.

The inline header is 53 bytes (offset, size, uncompressed size, 20-byte hash,
method index, flags byte, block size), plus `16 × blocks + 4` when compressed.
Getting this size wrong shifts every payload, which is why it is asserted
against the RIFF header in the integration test.

## `.wem` media

A `.wem` is a RIFF/WAVE file. Across all 194,559 media files in the build:

- **194,085 are Wwise Vorbis** — `wFormatTag` `0xFFFF` with a 66-byte `fmt `
  chunk, 48 kHz, mono or stereo.
- **474 are PCM** with a `WAVEFORMATEXTENSIBLE` header.

Chunk order is `fmt `, `hash` (16 bytes, Wwise 2021+), `data`.

The extended `fmt ` body carries Wwise's own fields. The one this reader uses is
the decoded length in samples at **`fmt + 0x18`**, cross-checked against
`nAvgBytesPerSec`: for `100018565.wem`, 728,342 samples at 48 kHz is 15.17 s,
and 310,629 stored bytes at 20,437 B/s is 15.20 s.

That offset is only meaningful for Wwise's own codecs. In a
`WAVEFORMATEXTENSIBLE` header `0x18` is still inside the channel mask and
subformat GUID, so the sample count is read only when the tag is Wwise Vorbis
or Wwise Opus; PCM falls back to the exact bit-rate calculation.

## Not implemented yet

**Playback.** Wwise Vorbis is not plain Ogg Vorbis: the codebooks are stripped
and the packet framing is Wwise's own, so the Ogg headers have to be rebuilt
(the job `ww2ogg` does) before any decoder will touch it. Until that lands the
editor reports headers and exports the raw `.wem`.

**Bink Audio.** The 23 native `SoundWave` assets are a separate format again —
the `.ubulk` opens with a `SEEK` chunk and the name map carries `BINKA`. They
are not surfaced in the browser yet.

**Sound banks.** `.bnk` files are listed and exportable but not parsed; the
event graph inside them is what maps a readable name onto these numeric IDs.

## Verification

`catalog::tests::every_shipped_wem_header_parses` reads every shipped `.wem`
header through the pak reader and asserts the declared RIFF size matches the
size the pak entry claims to have stored. Ignored by default; run it with:

```
MJOLNIR_PAKS="<install>/Meteorite/Content/Paks" cargo test --release --lib every_shipped_wem -- --ignored --nocapture
```

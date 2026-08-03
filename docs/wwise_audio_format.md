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

## Recovering readable names

Wwise names media by numeric short ID, so the pak side alone can only show
`1000519664.wem`. The readable names survive on the IoStore side: each cooked
`UAkAudioEvent` package's **name map** contains the event name, the
`Media/<bucket>/<id>.wem` paths it plays, and the authored `.wav` sources.

```
2581487812.bnk
Environment\A15\Positionals\AMB_ENV_A15_ComputerBeeps_A_01.wav
… (20 sources)
Media/10/1060715316.wem
… (19 media)
Play_AMB_ENV_A15_ComputerBeeps_A
SFX
/Game/Audio/Audio_FI/…/WwiseEvents/Play_AMB_ENV_A15_ComputerBeeps_A
```

Reading only the name map is enough to map media ID to event name; no export
parsing is needed. Implemented in `apps/tag-editor/src-tauri/src/wwise.rs`.

**Coverage is partial: 3,619 media IDs, from 997 of ~24,000 packages.**
Unnamed media falls back to its ID.

### Why the sound banks cannot close the gap

The obvious next step is the `.bnk` files, and the structure is all there.
`bnk.rs` parses `HIRC` and resolves the whole graph: events point at actions,
actions at a container or a sound, and every node carries a parent pointer, so
media can be walked back to the event that plays it. 746 of 749 banks yield a
readable graph.

It does not help, because **a bank contains no names**. Wwise reduces every
object name to a 32-bit FNV-1 hash of its lowercased form — that is why banks
and media are numbered on disk. Names survive only in the cooked packages, and
the game ships packages for barely 1% of its events:

| | |
|---|---|
| Events defined across all banks | 195,215 |
| Events with a name from a package | **1,621** |
| Banks whose own name is recoverable | 35 of 749 |

So the bank graph can only re-attribute media to events that are *already*
named, which adds ~100 media IDs — and those turn out to be sounds embedded in
the bank's `DATA` section rather than separate `.wem` files, so the browsable
catalog does not change at all.

`Catalog::names` therefore does **not** walk the banks: it costs seconds and
names nothing new. `bnk::parse` and `NameIndex::add_bank` are kept and tested,
ready for the day a name list exists.

Bank names are recovered by hash rather than by guessing at name-map ordering:
a package references `<id>.bnk` and carries the readable name separately, and
`event_id(name) == id` confirms the pairing. Verified — `AMB_A10` hashes to
`2581487812`, which is the bank's filename.

The remaining names are simply not in the shipped data. Recovering them would
mean reversing FNV-1 against a guessed wordlist, which produces plausible
guesses rather than facts.

`catalog::tests::banks_cannot_name_what_the_game_does_not_ship` records this
ceiling so it can be re-checked against a future build.

The export blob does appear to pair each media ID with a specific source: the
records read `80 0f 14 <media id u32> <u8> … <u8>`, where the trailing bytes
look like name-map indices. That pairing is unverified and not relied on.

## Playback

Wwise Vorbis is not plain Ogg Vorbis: the packet framing is Wwise's own and the
codebooks are stripped, so the Ogg headers must be rebuilt before any decoder
will touch it.

The codebooks here are **external**, confirmed by decoding a setup packet: it is
228 bytes and begins with a count of 44 followed by 10-bit codebook IDs that
come out as clean sequential indices (50, 51, 52 … max 462), with no inline
codebook sync (`0x564342`) anywhere — 44 inline codebooks could not fit in 228
bytes. So the codebook library is needed, and it is *not* in the `.wem` files;
the game keeps it inside `HaloCampaignEvolved.exe`, where the Wwise sound
engine is statically linked.

Rather than extract it from the game or vendor a blob, the editor depends on
the [`ww2ogg`](https://crates.io/crates/ww2ogg) crate (BSD-3-Clause), a Rust
port of hcs64's ww2ogg that embeds both the standard and aoTuV 6.03 codebook
libraries. `apps/tag-editor/src-tauri/src/decode.rs` rebuilds the stream; the
webview decodes the resulting Ogg natively, so no samples are decoded in Rust.

A file does not record which codebook library it was encoded against, and the
wrong choice yields a stream that is well-formed but decodes to noise. Both are
tried, aoTuV first, and the result is decoded with `lewton` far enough to prove
it is really audio before being handed to the UI.

The ~474 extensible-PCM files are already a valid `.wav` and are passed through
untouched rather than pushed down the Vorbis path.

### Verification

`catalog::tests::shipped_media_converts_to_playable_ogg` converts a sample
spread across the whole catalog and asserts the rebuilt stream reports the same
channel count and sample rate the `.wem` header declared. 400 of 400 convert —
396 as aoTuV Vorbis, 4 as pass-through PCM.

## Not implemented yet

**Bink Audio.** The 23 native `SoundWave` assets are a separate format again —
the `.ubulk` opens with a `SEEK` chunk and the name map carries `BINKA`. They
are not surfaced in the browser yet.

**Sound banks.** Parsed for their event graph (see above) but not otherwise
surfaced; the embedded audio in their `DATA` section is not browsable.

## Verification

`catalog::tests::every_shipped_wem_header_parses` reads every shipped `.wem`
header through the pak reader and asserts the declared RIFF size matches the
size the pak entry claims to have stored. Ignored by default; run it with:

```
MJOLNIR_PAKS="<install>/Meteorite/Content/Paks" cargo test --release --lib every_shipped_wem -- --ignored --nocapture
```

//! A Halo 2 MCC map's sound, staged as tools/level/ce_sounds.py stages a
//! Custom Edition map's (`sounds_out/sounds.json` and `sounds_out/sounds/`),
//! so the importer (unreal/MJOLNIRMaterials/Scripts/build_ce_sounds.py), the
//! level generator (`gen_ce_level.py --sounds`) and MJOLNIRLevelLoader play
//! it as they play CE's: the BSP's background loops, the sound scenery, the
//! loops placed objects carry, and the one-shots a turning machine's
//! animation raises (Ascension's antennas).
//!
//! The samples are not in the maps: they sit in headerless `sounds_*.dat`
//! files beside them, which the tags index by absolute offset.
//!
//! - `snd!` (0x1C): flags u16 0x00 (0x0800 plays only in remastered mode),
//!   class u8 0x02, codec index i8 0x03, playback index i16 0x06, first
//!   pitch range i16 0x08, pitch range count i8 0x0A. Its indices are into
//!   the `ugh!` (sound gestalt) of the cache file that holds the `snd!`.
//! - `ugh!` blocks: codecs 0x00 (3 bytes: rate 0 22050, 1 44100, 2 32000,
//!   3 48000; encoding 0 mono, 1 stereo; compression 0 big-endian PCM,
//!   1 Xbox ADPCM, 3 little-endian PCM, 4 WMA, 5 Opus), playback 0x08 (0x38:
//!   minimum and maximum distance 0x00 and 0x04 in world units, gain dB
//!   0x10, random pitch bounds i16 x 2 in cents 0x18), pitch ranges 0x28
//!   (0x0C: first permutation i16 0x08, count i16 0x0A), permutations 0x30
//!   (0x10: per language {u32 PCM bytes, i16 first chunk, i16 chunk count}
//!   at 0x08) and permutation chunks 0x60 (one block per language, 0x10
//!   each: i32 offset in the .dat, u32 size in the low 24 bits).
//! - The .dat: `sounds_remastered.dat` for a remastered-only sound,
//!   `sounds_en.dat` for a class the sound classes tag marks multilingual
//!   (`sound\sound_classes`, 0x78 each, internal flag bit 7 at 0x08),
//!   `sounds_neutral.dat` otherwise. The rule held for every chunk of
//!   shared, Ascension and Lockout.
//! - Opus (48 kHz): a chunk is `[i16 length][packet]` repeated, the last
//!   length stored negative. A permutation's chunks are one stream. The
//!   packets go into an Ogg Opus file as they are (RFC 7845), which the
//!   editor's sound factory imports: no decoder here.
//! - Xbox ADPCM: 36-byte blocks per channel, 65 samples each, decoded to
//!   16-bit WAV as ce_sounds.py does.
//! - `lsnd` (0x34): distance bounds 0x14, tracks 0x24 (0x58: gain dB 0x08,
//!   fade in and out 0x0C and 0x10, in / loop / out / alternate loop /
//!   alternate out references 0x14, 0x1C, 0x24, 0x2C, 0x34), detail sounds
//!   0x2C (0x34: sound 0x04, random period 0x0C, yaw / pitch / distance
//!   bounds 0x1C, 0x24, 0x2C).
//!
//! The research behind the layouts (every Opus decode matched its tag's byte
//! count, every chunk its file) is in docs/h2_cache_format.md, "Sound".

use std::collections::{BTreeMap, BTreeSet};
use std::fs::File;
use std::io::{Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};

use serde_json::{json, Value};

use crate::h2::{Cache, Group, Struct, Tag};
use crate::Error;

const UGH: Group = Group::new(b"ugh!");
const SNCL: Group = Group::new(b"sncl");
const REMASTERED_ONLY: u16 = 0x0800;
/// Classes the sound classes tag marks multilingual, when it cannot be read.
const MULTILINGUAL: [usize; 7] = [19, 44, 45, 46, 47, 48, 53];

/// dB to a linear gain.
fn linear(db: f32) -> f32 {
    if db.is_finite() { 10f32.powf(db / 20.0) } else { 1.0 }
}

/// A name as ce_sounds.py's `safe` makes it.
fn safe(path: &str) -> String {
    path.replace(['\\', ' ', '.'], "_").to_lowercase()
}

/// The Ogg page CRC (polynomial 0x04C11DB7, unreflected, initial 0).
fn ogg_crc(data: &[u8]) -> u32 {
    let mut crc = 0u32;
    for &b in data {
        crc ^= (b as u32) << 24;
        for _ in 0..8 {
            crc = if crc & 0x8000_0000 != 0 { (crc << 1) ^ 0x04C1_1DB7 } else { crc << 1 };
        }
    }
    crc
}

fn ogg_page(serial: u32, sequence: u32, granule: u64, packets: &[&[u8]], flags: u8) -> Vec<u8> {
    let mut lacing = Vec::new();
    for p in packets {
        lacing.extend(std::iter::repeat(255u8).take(p.len() / 255));
        lacing.push((p.len() % 255) as u8);
    }
    let mut page = b"OggS".to_vec();
    page.push(0);
    page.push(flags);
    page.extend(granule.to_le_bytes());
    page.extend(serial.to_le_bytes());
    page.extend(sequence.to_le_bytes());
    page.extend([0u8; 4]);
    page.push(lacing.len() as u8);
    page.extend(lacing);
    for p in packets {
        page.extend_from_slice(p);
    }
    let crc = ogg_crc(&page);
    page[22..26].copy_from_slice(&crc.to_le_bytes());
    page
}

/// Samples (at 48 kHz) an Opus packet decodes to, from its TOC byte.
fn opus_samples(packet: &[u8]) -> u64 {
    let Some(&toc) = packet.first() else { return 0 };
    let config = toc >> 3;
    let frame = match config {
        0..=11 => [480, 960, 1920, 2880][(config & 3) as usize],
        12..=15 => [480, 960][(config & 1) as usize],
        _ => [120, 240, 480, 960][(config & 3) as usize],
    };
    let frames = match toc & 3 {
        0 => 1,
        1 | 2 => 2,
        _ => packet.get(1).map(|b| (b & 0x3F) as u64).unwrap_or(1),
    };
    frame * frames
}

/// Opus packets in an Ogg Opus file (RFC 7845): the identification and
/// comment headers, then the packets, at most 255 lacing values a page,
/// each page's granule position the samples decoded through it.
pub fn ogg_opus(packets: &[Vec<u8>], channels: u8, serial: u32) -> Vec<u8> {
    let mut head = b"OpusHead".to_vec();
    head.extend([1, channels]);
    head.extend(0u16.to_le_bytes()); // pre-skip: the tag's lengths count every sample
    head.extend(48_000u32.to_le_bytes());
    head.extend(0i16.to_le_bytes());
    head.push(0); // mapping family 0: mono or stereo
    let mut tags = b"OpusTags".to_vec();
    tags.extend(7u32.to_le_bytes());
    tags.extend(b"MJOLNIR");
    tags.extend(0u32.to_le_bytes());
    let mut out = ogg_page(serial, 0, 0, &[&head], 2);
    out.extend(ogg_page(serial, 1, 0, &[&tags], 0));
    let (mut sequence, mut granule, mut i) = (2u32, 0u64, 0usize);
    while i < packets.len() {
        let (mut group, mut lacing) = (Vec::new(), 0usize);
        while i < packets.len() && lacing + packets[i].len() / 255 < 255 {
            lacing += packets[i].len() / 255 + 1;
            granule += opus_samples(&packets[i]);
            group.push(packets[i].as_slice());
            i += 1;
        }
        let last = i >= packets.len();
        out.extend(ogg_page(serial, sequence, granule, &group, if last { 4 } else { 0 }));
        sequence += 1;
    }
    out
}

/// A chunk's Opus packets: `[i16 length][packet]` until a negative length.
fn opus_packets(data: &[u8]) -> Option<Vec<Vec<u8>>> {
    let mut out = Vec::new();
    let mut at = 0;
    while at + 2 <= data.len() {
        let n = i16::from_le_bytes([data[at], data[at + 1]]);
        let len = n.unsigned_abs() as usize;
        if len == 0 || at + 2 + len > data.len() {
            return None;
        }
        out.push(data[at + 2..at + 2 + len].to_vec());
        at += 2 + len;
        if n < 0 {
            return (at == data.len()).then_some(out);
        }
    }
    None
}

const IMA_STEPS: [i32; 89] = [
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97, 107,
    118, 130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724, 796, 876, 963,
    1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358, 5894,
    6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794,
    32767,
];
const IMA_INDEX: [i32; 16] = [-1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8];

/// Xbox IMA ADPCM to interleaved 16-bit PCM: per channel a 4-byte header
/// (the first sample, the step index) and 32 bytes of nibbles in 4-byte
/// words interleaved across the channels, 65 samples a block.
fn xbox_adpcm(data: &[u8], channels: usize) -> Vec<i16> {
    let block = 36 * channels;
    let mut out = Vec::with_capacity(data.len() / block * 65 * channels);
    for b0 in (0..data.len() / block).map(|k| k * block) {
        let mut chans: Vec<Vec<i16>> = Vec::with_capacity(channels);
        for c in 0..channels {
            let h = b0 + 4 * c;
            let mut pred = i16::from_le_bytes([data[h], data[h + 1]]) as i32;
            let mut idx = (data[h + 2] as i32).clamp(0, 88);
            let mut samples = vec![pred as i16];
            for w in 0..8 {
                let at = b0 + 4 * channels + (w * channels + c) * 4;
                for &byte in &data[at..at + 4] {
                    for nib in [byte & 0x0F, byte >> 4] {
                        let step = IMA_STEPS[idx as usize];
                        let mut diff = step >> 3;
                        if nib & 1 != 0 { diff += step >> 2; }
                        if nib & 2 != 0 { diff += step >> 1; }
                        if nib & 4 != 0 { diff += step; }
                        if nib & 8 != 0 { diff = -diff; }
                        pred = (pred + diff).clamp(-32768, 32767);
                        idx = (idx + IMA_INDEX[nib as usize]).clamp(0, 88);
                        samples.push(pred as i16);
                    }
                }
            }
            chans.push(samples);
        }
        for i in 0..65 {
            for ch in &chans {
                out.push(ch[i]);
            }
        }
    }
    out
}

fn wav(pcm: &[i16], rate: u32, channels: u16) -> Vec<u8> {
    let data = (pcm.len() * 2) as u32;
    let mut out = b"RIFF".to_vec();
    out.extend((36 + data).to_le_bytes());
    out.extend(b"WAVEfmt ");
    out.extend(16u32.to_le_bytes());
    out.extend(1u16.to_le_bytes());
    out.extend(channels.to_le_bytes());
    out.extend(rate.to_le_bytes());
    out.extend((rate * channels as u32 * 2).to_le_bytes());
    out.extend((channels * 2).to_le_bytes());
    out.extend(16u16.to_le_bytes());
    out.extend(b"data");
    out.extend(data.to_le_bytes());
    for s in pcm {
        out.extend(s.to_le_bytes());
    }
    out
}

/// One permutation's samples as read: Opus packets, or PCM.
enum Samples {
    Opus(Vec<Vec<u8>>),
    Pcm(Vec<i16>),
}

/// The map's sound as it is staged: every `snd!` asked for written once,
/// every `lsnd` read once.
pub struct Sounds<'c> {
    cache: &'c Cache,
    /// Where the `sounds_*.dat` files are (the maps' folder).
    dats: PathBuf,
    out: PathBuf,
    multilingual: BTreeSet<usize>,
    open: BTreeMap<PathBuf, Option<File>>,
    sounds: BTreeMap<String, Value>,
    loops: BTreeMap<String, Value>,
    emitters: Vec<Value>,
    background: Vec<String>,
    pub notes: Vec<String>,
}

impl<'c> Sounds<'c> {
    /// `out` is the staging's `sounds_out`.
    pub fn new(cache: &'c Cache, out: &Path) -> Sounds<'c> {
        let dats = cache.map.path.parent().map(Path::to_path_buf).unwrap_or_default();
        let mut multilingual = BTreeSet::new();
        let classes = cache
            .shared
            .as_ref()
            .and_then(|f| f.tags.iter().find(|e| e.group == SNCL && e.address.is_some()).map(|e| (f, e.datum)))
            .and_then(|(f, d)| cache.tag(f, d));
        if let Some(t) = classes {
            for (i, c) in t.root.block(0x00, 0x78).iter().enumerate() {
                if c.u16(0x08) & 0x80 != 0 {
                    multilingual.insert(i);
                }
            }
        }
        if multilingual.is_empty() {
            multilingual.extend(MULTILINGUAL);
        }
        Sounds {
            cache,
            dats,
            out: out.to_path_buf(),
            multilingual,
            open: BTreeMap::new(),
            sounds: BTreeMap::new(),
            loops: BTreeMap::new(),
            emitters: Vec::new(),
            background: Vec::new(),
            notes: Vec::new(),
        }
    }

    fn read(&mut self, dat: &Path, offset: i32, size: usize) -> Option<Vec<u8>> {
        let f = self.open.entry(dat.to_path_buf()).or_insert_with(|| File::open(dat).ok()).as_mut()?;
        f.seek(SeekFrom::Start(u64::try_from(offset).ok()?)).ok()?;
        let mut buf = vec![0u8; size];
        f.read_exact(&mut buf).ok()?;
        Some(buf)
    }

    /// Stage a `snd!`: as a loop (its permutations joined into one
    /// `<name>_loop` file, as CE plays a loop's permutations back to back)
    /// or as one-shots (one `<name>_v<k>` file a permutation). Its path, or
    /// `None` with a note.
    pub fn sound(&mut self, tag: &Tag<'_>, looped: bool) -> Option<String> {
        let path = tag.name().to_string();
        if let Some(e) = self.sounds.get(&path) {
            if !looped || e.get("loop").is_some() {
                return Some(path);
            }
        }
        let root = tag.root;
        let (flags, class) = (root.u16(0x00), root.u8(0x02) as usize);
        let gestalt = tag
            .file
            .tags
            .iter()
            .find(|e| e.group == UGH && e.address.is_some())
            .and_then(|e| self.cache.tag(tag.file, e.datum));
        let Some(g) = gestalt else {
            self.notes.push(format!("{path}: no sound gestalt in {}", tag.file.path.display()));
            return None;
        };
        let g = g.root;
        let codec = g.block(0x00, 3).get(root.u8(0x03) as i8 as usize)?;
        let rate = [22050, 44100, 32000, 48000].get(codec.u8(0) as usize).copied().unwrap_or(22050);
        let channels: u16 = match codec.u8(1) {
            0 => 1,
            1 => 2,
            n => {
                self.notes.push(format!("{path}: encoding {n} (mono and stereo only)"));
                return None;
            }
        };
        let compression = codec.u8(2);
        let (mut min, mut max, mut gain_db, mut cents) = (0.0, 0.0, 0.0, 0.0);
        if let Some(p) = usize::try_from(root.i16(0x06)).ok().and_then(|i| g.block(0x08, 0x38).get(i)) {
            (min, max, gain_db) = (p.f32(0x00), p.f32(0x04), p.f32(0x10));
            cents = (p.i16(0x18) as f32 + p.i16(0x1A) as f32) / 2.0;
        }
        let dat = self.dats.join(if flags & REMASTERED_ONLY != 0 {
            "sounds_remastered.dat"
        } else if self.multilingual.contains(&class) {
            "sounds_en.dat"
        } else {
            "sounds_neutral.dat"
        });
        let chunks = g.block(0x60, 8).get(0).map(|l| l.block(0x00, 0x10));
        let ranges = g.block(0x28, 0x0C);
        let perms = g.block(0x30, 0x10);
        let first = root.i16(0x08).max(0) as usize;
        let mut read: Vec<Samples> = Vec::new();
        for r in first..first + root.u8(0x0A) as usize {
            let Some(range) = ranges.get(r) else { continue };
            let p0 = range.i16(0x08).max(0) as usize;
            for p in p0..p0 + range.i16(0x0A).max(0) as usize {
                let Some(language) = perms.get(p).and_then(|perm| perm.block(0x08, 8).get(0)) else { continue };
                let (c0, n) = (language.i16(0x04).max(0) as usize, language.i16(0x06).max(0) as usize);
                let mut packets = Vec::new();
                let mut pcm = Vec::new();
                for q in c0..c0 + n {
                    let Some(chunk) = chunks.and_then(|c| c.get(q)) else { continue };
                    let Some(data) = self.read(&dat, chunk.u32(0) as i32, (chunk.u32(4) & 0x00FF_FFFF) as usize) else {
                        self.notes.push(format!("{path}: chunk {q} not in {}", dat.display()));
                        return None;
                    };
                    match compression {
                        5 => match opus_packets(&data) {
                            Some(p) => packets.extend(p),
                            None => {
                                self.notes.push(format!("{path}: chunk {q} is not an Opus packet chain"));
                                return None;
                            }
                        },
                        1 => pcm.extend(xbox_adpcm(&data, channels as usize)),
                        3 => pcm.extend(data.chunks_exact(2).map(|b| i16::from_le_bytes([b[0], b[1]]))),
                        0 => pcm.extend(data.chunks_exact(2).map(|b| i16::from_be_bytes([b[0], b[1]]))),
                        c => {
                            self.notes.push(format!("{path}: compression {c} (WMA) is not read"));
                            return None;
                        }
                    }
                }
                read.push(if compression == 5 { Samples::Opus(packets) } else { Samples::Pcm(pcm) });
            }
        }
        if read.is_empty() {
            self.notes.push(format!("{path}: no permutations"));
            return None;
        }
        let dir = self.out.join("sounds");
        if let Err(e) = std::fs::create_dir_all(&dir) {
            self.notes.push(format!("{}: {e}", dir.display()));
            return None;
        }
        let name = safe(&path);
        let serial = name.bytes().fold(0x4D4A_4F4Cu32, |h, b| h.rotate_left(5) ^ b as u32);
        let ext = if compression == 5 { "opus" } else { "wav" };
        let write = |file: &str, samples: &[&Samples]| -> std::io::Result<()> {
            let bytes = match samples.first() {
                Some(Samples::Opus(_)) => {
                    let all: Vec<Vec<u8>> = samples
                        .iter()
                        .flat_map(|s| match s { Samples::Opus(p) => p.clone(), Samples::Pcm(_) => Vec::new() })
                        .collect();
                    ogg_opus(&all, channels as u8, serial)
                }
                _ => {
                    let all: Vec<i16> = samples
                        .iter()
                        .flat_map(|s| match s { Samples::Pcm(p) => p.clone(), Samples::Opus(_) => Vec::new() })
                        .collect();
                    wav(&all, rate, channels)
                }
            };
            std::fs::write(dir.join(file), bytes)
        };
        let mut entry = self.sounds.remove(&path).unwrap_or_else(|| {
            json!({
                "rate": if compression == 5 { 48000 } else { rate }, "channels": channels,
                "compression": compression, "class": class,
                "min_distance": min, "max_distance": max,
                "gain": linear(gain_db), "pitch": 2f32.powf(cents / 1200.0),
                "files": [],
            })
        });
        let result = if looped {
            let file = format!("{name}_loop.{ext}");
            let r = write(&file, &read.iter().collect::<Vec<_>>());
            entry["loop"] = json!(file);
            if let Some(files) = entry["files"].as_array_mut() {
                files.push(json!(file));
            }
            r
        } else {
            let mut r = Ok(());
            for (k, s) in read.iter().enumerate() {
                let file = format!("{name}_v{k}.{ext}");
                r = r.and(write(&file, &[s]));
                if let Some(files) = entry["files"].as_array_mut() {
                    files.push(json!(file));
                }
            }
            r
        };
        if let Err(e) = result {
            self.notes.push(format!("{path}: {e}"));
            return None;
        }
        self.sounds.insert(path.clone(), entry);
        Some(path)
    }

    /// Read a `lsnd` and stage each track's loop. Its path.
    pub fn looping(&mut self, tag: &Tag<'_>) -> String {
        let path = tag.name().to_string();
        if self.loops.contains_key(&path) {
            return path;
        }
        let root = tag.root;
        let mut follow = |s: Struct<'_>, off: usize, looped: bool, stage: bool| -> Value {
            let Some(t) = s.tagref(off).and_then(|r| self.cache.follow(r)) else { return Value::Null };
            match stage {
                true => self.sound(&t, looped).map(Value::from).unwrap_or(Value::Null),
                false => json!(t.name()),
            }
        };
        let mut tracks = Vec::new();
        for t in root.block(0x24, 0x58).iter() {
            tracks.push(json!({
                "gain": linear(t.f32(0x08)), "fade_in": t.f32(0x0C), "fade_out": t.f32(0x10),
                "start": follow(t, 0x14, false, false), "loop": follow(t, 0x1C, true, true),
                "end": follow(t, 0x24, false, false), "alternate_loop": follow(t, 0x2C, false, false),
                "output_effect": t.i16(0x3C),
            }));
        }
        let mut details = Vec::new();
        for d in root.block(0x2C, 0x34).iter() {
            details.push(json!({
                "sound": follow(d, 0x04, false, false),
                "period": [d.f32(0x0C), d.f32(0x10)],
                "yaw": [d.f32(0x1C), d.f32(0x20)], "pitch": [d.f32(0x24), d.f32(0x28)],
                "distance": [d.f32(0x2C), d.f32(0x30)],
            }));
        }
        let (lo, hi) = (root.f32(0x14), root.f32(0x18));
        self.loops.insert(path.clone(), json!({
            "min_distance": lo, "max_distance": hi, "tracks": tracks, "details": details,
        }));
        path
    }

    /// The looping sounds an object carries (object attachments, +0x94:
    /// 0x18 each, reference 0x00, marker 0x08, primary scale function
    /// 0x10), as emitters at its origin. One its function scales is left
    /// out: it sounds only while the object drives it (the jump pads'
    /// launch loop, `phantom_power`, at 200 world units).
    pub fn object(&mut self, object: &Tag<'_>, pos: [f32; 3], rot: [f32; 3]) {
        for a in object.root.block(0x94, 0x18).iter() {
            let Some(t) = a.tagref(0x00).filter(|r| r.group == Group::new(b"lsnd")).and_then(|r| self.cache.follow(r)) else {
                continue;
            };
            let scale = a.sid(0x10);
            if !scale.is_empty() {
                self.notes.push(format!("{} on {}: scaled by {scale}, not played", t.name(), object.name()));
                continue;
            }
            let sound = self.looping(&t);
            self.emitters.push(json!({"pos": pos, "rot": rot, "sound": sound, "attached_to": object.name(),
                                      "marker": a.sid(0x08)}));
        }
    }

    /// The scenario's sound scenery (0xD8, 0x50 each: palette index 0x00,
    /// position 0x08, rotation 0x14, distance override 0x3C; palette 0xE0,
    /// 0x28 each, the `ssce` at 0x00) and the BSP's background sounds
    /// (clusters 0x9C, 0xB0 each, background index i16 0x72, into the
    /// palette at 0xD4, 0x64 each, its `lsnd` at 0x20).
    pub fn scenario(&mut self, scnr: &Tag<'_>, sbsp: &Tag<'_>) {
        let palette = scnr.root.block(0xE0, 0x28);
        for s in scnr.root.block(0xD8, 0x50).iter() {
            let Some(ssce) = usize::try_from(s.i16(0x00))
                .ok()
                .and_then(|i| palette.get(i))
                .and_then(|p| p.tagref(0x00))
                .and_then(|r| self.cache.follow(r))
            else {
                continue;
            };
            let before = self.emitters.len();
            self.object(&ssce, s.vec3(0x08), s.vec3(0x14));
            let (lo, hi) = (s.f32(0x3C), s.f32(0x40));
            if hi > 0.0 {
                for e in &mut self.emitters[before..] {
                    e["distance"] = json!([lo, hi]);
                }
            }
        }
        let palette = sbsp.root.block(0xD4, 0x64);
        for c in sbsp.root.block(0x9C, 0xB0).iter() {
            let Some(t) = usize::try_from(c.i16(0x72))
                .ok()
                .and_then(|i| palette.get(i))
                .and_then(|p| p.tagref(0x20))
                .and_then(|r| self.cache.follow(r))
            else {
                continue;
            };
            let path = self.looping(&t);
            if !self.background.contains(&path) {
                self.background.push(path);
            }
        }
    }

    /// Write `sounds.json`; the number of sounds staged.
    pub fn finish(self) -> Result<(usize, Vec<String>), Error> {
        if self.sounds.is_empty() {
            return Ok((0, self.notes));
        }
        let manifest = json!({
            "source": "halo2_mcc",
            "emitters": self.emitters, "background": self.background,
            "loops": self.loops, "sounds": self.sounds,
        });
        let path = self.out.join("sounds.json");
        let text = serde_json::to_string_pretty(&manifest).map_err(|e| Error::Format(e.to_string()))?;
        std::fs::write(&path, text).map_err(|e| Error::Io(path, e))?;
        Ok((manifest["sounds"].as_object().map(|o| o.len()).unwrap_or(0), self.notes))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The page CRC of RFC 3533 (an empty page's known value) and an Ogg
    /// Opus file's shape: two header pages, then the audio with its
    /// granule at the samples decoded and the last page flagged.
    #[test]
    fn opus_packets_go_into_ogg_as_they_are() {
        assert_eq!(ogg_crc(b"123456789"), 0x89A1_897F);
        // Ascension's antennas: CELT fullband, 5 ms, mono (0xE8).
        let packets: Vec<Vec<u8>> = (0..600).map(|k| vec![0xE8, k as u8, 0x55]).collect();
        let ogg = ogg_opus(&packets, 1, 7);
        assert_eq!(&ogg[0..4], b"OggS");
        assert_eq!(&ogg[28..36], b"OpusHead");
        let mut pages = Vec::new();
        let mut at = 0;
        while at < ogg.len() {
            let n = ogg[at + 26] as usize;
            let body: usize = ogg[at + 27..at + 27 + n].iter().map(|&b| b as usize).sum();
            pages.push((ogg[at + 5], u64::from_le_bytes(ogg[at + 6..at + 14].try_into().unwrap())));
            at += 27 + n + body;
        }
        assert_eq!(at, ogg.len());
        assert_eq!(pages.len(), 2 + 3);
        assert_eq!(*pages.last().unwrap(), (4, 600 * 240));
        assert_eq!(opus_samples(&[0xEC]), 240);
        assert_eq!(opus_samples(&[0xF9]), 960 * 2);
    }

    #[test]
    fn opus_chunks_end_on_a_negative_length() {
        let chunk = [3u8, 0, 0xE8, 0xFF, 0xFE, 0xFE, 0xFF, 0xE8, 1];
        assert_eq!(opus_packets(&chunk), Some(vec![vec![0xE8, 0xFF, 0xFE], vec![0xE8, 1]]));
        assert_eq!(opus_packets(&chunk[..7]), None);
    }

    #[test]
    fn adpcm_blocks_decode_to_65_samples() {
        let mut block = vec![0u8; 36];
        block[0..2].copy_from_slice(&100i16.to_le_bytes());
        let pcm = xbox_adpcm(&block, 1);
        assert_eq!(pcm.len(), 65);
        assert_eq!(pcm[0], 100);
        assert_eq!(safe(r"sound\ambience\ascension\ascension"), "sound_ambience_ascension_ascension");
        assert!((linear(-6.0) - 0.501).abs() < 1e-3);
    }
}

//! Wwise `.wem` header reading.
//!
//! A `.wem` is a RIFF/WAVE file with Wwise's own codec tags and a few private
//! chunks. Everything the browser shows — codec, channel count, rate, duration —
//! comes from the `fmt ` chunk, so a listing never pays to read the payload.
//!
//! Campaign Evolved encodes with Wwise Vorbis (`fmt ` tag `0xFFFF`, 66 bytes).
//! Decoding the payload is a separate job; this module only reports.

use serde::Serialize;

/// Bytes of a `.wem` worth reading to describe it: RIFF header plus the
/// leading chunks. `data` is always last, so its declared size is reachable
/// well inside this.
pub const HEADER_BYTES: usize = 512;

/// What a `.wem` header says about its audio.
#[derive(Debug, Serialize, PartialEq)]
pub struct WemInfo {
    /// Human-readable codec name.
    pub codec: String,
    /// Raw `wFormatTag`, so an unrecognised codec is still identifiable.
    pub format_tag: u16,
    pub channels: u16,
    pub sample_rate: u32,
    pub avg_bytes_per_sec: u32,
    /// Decoded length in samples per channel, when the header records it.
    pub sample_count: Option<u32>,
    /// Playing time, from the sample count where possible and the bit rate
    /// otherwise. `None` when neither is usable.
    pub duration_secs: Option<f32>,
    /// Size of the `data` chunk.
    pub data_size: u32,
    /// Chunk ids in order, for the detail panel.
    pub chunks: Vec<String>,
}

/// Name a `wFormatTag`. Wwise reuses the WAVE registry and adds its own.
fn codec_name(tag: u16, fmt_size: u32) -> String {
    match tag {
        0x0001 => "PCM".to_string(),
        0x0002 => "ADPCM".to_string(),
        0x0011 => "IMA ADPCM".to_string(),
        0x0161 => "WMA v2".to_string(),
        0x0162 => "WMA Pro".to_string(),
        0x0165 => "XMA".to_string(),
        0x0166 => "XMA2".to_string(),
        0x3039 => "Wwise IMA ADPCM".to_string(),
        0x3040 | 0x3041 => "Wwise Opus".to_string(),
        0xFFFE => "PCM (extensible)".to_string(),
        // Wwise writes the catch-all tag for its own Vorbis; the oversized
        // `fmt ` chunk carrying the setup data is what distinguishes it.
        0xFFFF if fmt_size >= 0x42 => "Wwise Vorbis".to_string(),
        0xFFFF => "Wwise (unknown)".to_string(),
        other => format!("unknown ({other:#06x})"),
    }
}

fn u16_at(b: &[u8], at: usize) -> Option<u16> {
    Some(u16::from_le_bytes(b.get(at..at + 2)?.try_into().unwrap()))
}

fn u32_at(b: &[u8], at: usize) -> Option<u32> {
    Some(u32::from_le_bytes(b.get(at..at + 4)?.try_into().unwrap()))
}

/// Parse the header of a `.wem`. `data` may be a truncated prefix of the file.
pub fn parse_wem(data: &[u8]) -> Result<WemInfo, String> {
    if data.len() < 20 || &data[0..4] != b"RIFF" || &data[8..12] != b"WAVE" {
        return Err("not a RIFF/WAVE file".to_string());
    }

    let mut fmt: Option<&[u8]> = None;
    let mut data_size = 0u32;
    let mut chunks = Vec::new();

    // Walk the chunk list. A truncated prefix simply stops the walk early.
    let mut at = 12;
    while at + 8 <= data.len() {
        let id = &data[at..at + 4];
        let size = u32_at(data, at + 4).ok_or("chunk header ends early")?;
        let name = String::from_utf8_lossy(id).trim_end().to_string();
        if !name.chars().all(|c| c.is_ascii_graphic() || c == ' ') {
            return Err(format!("chunk id {id:02x?} is not printable"));
        }
        chunks.push(name);
        match id {
            b"fmt " => fmt = data.get(at + 8..at + 8 + size as usize),
            b"data" => data_size = size,
            _ => {}
        }
        // The payload of `data` is the audio itself; nothing follows it.
        if id == b"data" {
            break;
        }
        // Chunks are padded to an even length.
        at += 8 + size as usize + (size as usize & 1);
    }

    let fmt = fmt.ok_or("no fmt chunk")?;
    let fmt_size = fmt.len() as u32;
    if fmt_size < 16 {
        return Err(format!("fmt chunk is only {fmt_size} bytes"));
    }
    let format_tag = u16_at(fmt, 0).unwrap();
    let channels = u16_at(fmt, 2).unwrap();
    let sample_rate = u32_at(fmt, 4).unwrap();
    let avg_bytes_per_sec = u32_at(fmt, 8).unwrap();

    // Wwise puts the decoded length 24 bytes into its extended `fmt ` body,
    // past the channel layout word. Only Wwise's own codecs have it: at that
    // offset a `WAVEFORMATEXTENSIBLE` header is still in its channel mask and
    // subformat GUID, which would read as a nonsense sample count.
    let is_wwise = matches!(format_tag, 0x3040 | 0x3041) || (format_tag == 0xFFFF && fmt_size >= 0x42);
    let sample_count = if is_wwise && fmt_size >= 0x1C {
        u32_at(fmt, 0x18).filter(|n| *n > 0)
    } else {
        None
    };

    let duration_secs = match (sample_count, sample_rate) {
        (Some(n), r) if r > 0 => Some(n as f32 / r as f32),
        // Fall back to the bit rate, which is all a plain PCM header offers.
        _ if avg_bytes_per_sec > 0 && data_size > 0 => {
            Some(data_size as f32 / avg_bytes_per_sec as f32)
        }
        _ => None,
    };

    Ok(WemInfo {
        codec: codec_name(format_tag, fmt_size),
        format_tag,
        channels,
        sample_rate,
        avg_bytes_per_sec,
        sample_count,
        duration_secs,
        data_size,
        chunks,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Build a RIFF/WAVE file from chunk bodies.
    fn riff(chunks: &[(&[u8; 4], Vec<u8>)]) -> Vec<u8> {
        let mut body = b"WAVE".to_vec();
        for (id, data) in chunks {
            body.extend_from_slice(*id);
            body.extend_from_slice(&(data.len() as u32).to_le_bytes());
            body.extend_from_slice(data);
            if data.len() % 2 == 1 {
                body.push(0);
            }
        }
        let mut out = b"RIFF".to_vec();
        out.extend_from_slice(&(body.len() as u32).to_le_bytes());
        out.extend_from_slice(&body);
        out
    }

    /// A Wwise Vorbis `fmt ` body: 16 standard bytes, then the extension.
    fn wwise_fmt(channels: u16, rate: u32, avg: u32, samples: u32) -> Vec<u8> {
        let mut f = Vec::new();
        f.extend_from_slice(&0xFFFFu16.to_le_bytes());
        f.extend_from_slice(&channels.to_le_bytes());
        f.extend_from_slice(&rate.to_le_bytes());
        f.extend_from_slice(&avg.to_le_bytes());
        f.extend_from_slice(&0u16.to_le_bytes()); // block align
        f.extend_from_slice(&0u16.to_le_bytes()); // bits per sample
        f.extend_from_slice(&48u16.to_le_bytes()); // cbSize
        f.extend_from_slice(&0u16.to_le_bytes()); // reserved
        f.extend_from_slice(&0x0000_3102u32.to_le_bytes()); // channel layout
        f.extend_from_slice(&samples.to_le_bytes()); // @0x18
        f.resize(66, 0);
        f
    }

    #[test]
    fn reads_a_wwise_vorbis_header() {
        let file = riff(&[
            (b"fmt ", wwise_fmt(2, 48000, 20437, 728_342)),
            (b"hash", vec![0; 16]),
            (b"data", vec![0; 64]),
        ]);
        let info = parse_wem(&file).unwrap();
        assert_eq!(info.codec, "Wwise Vorbis");
        assert_eq!(info.channels, 2);
        assert_eq!(info.sample_rate, 48000);
        assert_eq!(info.sample_count, Some(728_342));
        assert_eq!(info.chunks, vec!["fmt", "hash", "data"]);
        assert_eq!(info.data_size, 64);
        // 728342 samples at 48 kHz is a little over 15 seconds.
        let secs = info.duration_secs.unwrap();
        assert!((secs - 15.17).abs() < 0.01, "got {secs}");
    }

    #[test]
    fn a_truncated_header_still_describes_the_audio() {
        // Reading only the first 512 bytes must not lose the fmt chunk.
        let mut file = riff(&[
            (b"fmt ", wwise_fmt(1, 48000, 15284, 67_718)),
            (b"data", vec![0; 100_000]),
        ]);
        file.truncate(HEADER_BYTES);
        let info = parse_wem(&file).unwrap();
        assert_eq!(info.channels, 1);
        assert_eq!(info.data_size, 100_000);
        assert_eq!(info.sample_count, Some(67_718));
    }

    #[test]
    fn falls_back_to_the_bit_rate_without_a_sample_count() {
        let mut fmt = Vec::new();
        fmt.extend_from_slice(&1u16.to_le_bytes()); // PCM
        fmt.extend_from_slice(&2u16.to_le_bytes());
        fmt.extend_from_slice(&44100u32.to_le_bytes());
        fmt.extend_from_slice(&176_400u32.to_le_bytes());
        fmt.extend_from_slice(&4u16.to_le_bytes());
        fmt.extend_from_slice(&16u16.to_le_bytes());
        let file = riff(&[(b"fmt ", fmt), (b"data", vec![0; 352_800])]);
        let info = parse_wem(&file).unwrap();
        assert_eq!(info.codec, "PCM");
        assert_eq!(info.sample_count, None);
        assert_eq!(info.duration_secs, Some(2.0));
    }

    #[test]
    fn an_extensible_pcm_header_is_timed_by_its_bit_rate() {
        // WAVEFORMATEXTENSIBLE is 40 bytes, so offset 0x18 lands inside the
        // subformat GUID. Reading it as a sample count would invent a
        // duration; the bit rate is exact for PCM anyway.
        let mut fmt = Vec::new();
        fmt.extend_from_slice(&0xFFFEu16.to_le_bytes());
        fmt.extend_from_slice(&2u16.to_le_bytes());
        fmt.extend_from_slice(&48_000u32.to_le_bytes());
        fmt.extend_from_slice(&192_000u32.to_le_bytes());
        fmt.extend_from_slice(&4u16.to_le_bytes());
        fmt.extend_from_slice(&16u16.to_le_bytes());
        fmt.extend_from_slice(&22u16.to_le_bytes()); // cbSize
        fmt.resize(40, 0xAB); // channel mask and subformat GUID
        let file = riff(&[(b"fmt ", fmt), (b"data", vec![0; 96_000])]);
        let info = parse_wem(&file).unwrap();
        assert_eq!(info.codec, "PCM (extensible)");
        assert_eq!(info.sample_count, None);
        assert_eq!(info.duration_secs, Some(0.5));
    }

    #[test]
    fn rejects_input_that_is_not_a_wem() {
        assert!(parse_wem(b"").is_err());
        assert!(parse_wem(&[0u8; 64]).is_err());
        // RIFF but not WAVE.
        let mut avi = b"RIFF".to_vec();
        avi.extend_from_slice(&8u32.to_le_bytes());
        avi.extend_from_slice(b"AVI LIST");
        assert!(parse_wem(&avi).is_err());
    }

    #[test]
    fn reports_an_unknown_codec_by_tag() {
        let mut fmt = vec![0u8; 16];
        fmt[0..2].copy_from_slice(&0x1234u16.to_le_bytes());
        let file = riff(&[(b"fmt ", fmt), (b"data", vec![0; 16])]);
        let info = parse_wem(&file).unwrap();
        assert_eq!(info.codec, "unknown (0x1234)");
        assert_eq!(info.duration_secs, None);
    }
}

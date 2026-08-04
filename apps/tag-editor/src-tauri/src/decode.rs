//! Turning a Wwise `.wem` into something a browser can play.
//!
//! The game's audio is Wwise Vorbis: standard Vorbis packets, but with the
//! codebooks stripped out and Wwise's own framing instead of Ogg pages. The
//! codebooks live in a fixed library the encoder shared across every file, so
//! rebuilding a playable stream means re-inserting them and re-paging the
//! packets. See `docs/wwise_audio_format.md`.
//!
//! Once that is done the result is ordinary Ogg Vorbis, which the webview
//! decodes natively — no sample-level decoding happens here.

use std::io::Cursor;

use ww2ogg::{CodebookLibrary, WwiseRiffVorbis};

/// A stream a browser can play, built from one `.wem`.
#[derive(Debug)]
pub struct Playable {
    pub bytes: Vec<u8>,
    /// MIME type for the `<audio>` element.
    pub mime: &'static str,
    /// How it was produced, for the detail panel.
    pub via: &'static str,
}

/// Make one `.wem` playable.
///
/// Most of the library is Wwise Vorbis and needs rebuilding. A small number of
/// files are plain PCM in a RIFF/WAVE container, which is already a `.wav` —
/// those are handed over untouched rather than pushed through a Vorbis path
/// that will only reject them.
pub fn to_playable(wem: &[u8]) -> Result<Playable, String> {
    let info = crate::sounds::parse_wem(wem)?;
    if !info.codec.starts_with("Wwise Vorbis") {
        return if info.codec.starts_with("PCM") {
            Ok(Playable {
                bytes: wem.to_vec(),
                mime: "audio/wav",
                via: "PCM, played as-is",
            })
        } else {
            Err(format!("{} is not supported yet", info.codec))
        };
    }
    let converted = to_ogg(wem)?;
    Ok(Playable {
        bytes: converted.ogg,
        mime: "audio/ogg",
        via: converted.codebooks,
    })
}

/// A converted Vorbis stream.
pub struct Converted {
    pub ogg: Vec<u8>,
    /// Which codebook library produced it, for the detail panel.
    pub codebooks: &'static str,
}

/// Convert one Wwise Vorbis `.wem` to Ogg Vorbis.
///
/// Wwise shipped two codebook libraries and the file does not say which one it
/// was encoded against, so the wrong choice yields a stream that still parses
/// but decodes to noise. Both are tried and the output is decoded far enough to
/// confirm it is really audio before being returned.
pub fn to_ogg(wem: &[u8]) -> Result<Converted, String> {
    let mut last = String::new();
    // aoTuV first: it is what this build encodes with, so the common case
    // succeeds on the first attempt.
    for (label, load) in [
        ("aoTuV 6.03", CodebookLibrary::aotuv_codebooks as fn() -> _),
        ("standard", CodebookLibrary::default_codebooks as fn() -> _),
    ] {
        let books = match load() {
            Ok(b) => b,
            Err(e) => {
                last = format!("{label} codebooks unavailable: {e}");
                continue;
            }
        };
        match convert_with(wem, books) {
            Ok(ogg) => {
                return Ok(Converted {
                    ogg,
                    codebooks: label,
                })
            }
            Err(e) => last = format!("{label}: {e}"),
        }
    }
    Err(if last.is_empty() {
        "conversion failed".to_string()
    } else {
        last
    })
}

fn convert_with(wem: &[u8], books: CodebookLibrary) -> Result<Vec<u8>, String> {
    let mut converter = WwiseRiffVorbis::new(Cursor::new(wem), books).map_err(|e| e.to_string())?;
    let mut ogg = Vec::with_capacity(wem.len());
    converter
        .generate_ogg(&mut ogg)
        .map_err(|e| e.to_string())?;
    // A stream built against the wrong codebooks still has valid Ogg framing,
    // so paging alone proves nothing; the headers have to actually decode.
    decodes(&ogg)?;
    Ok(ogg)
}

/// Read the stream's headers and first audio packets, so a stream that only
/// looks well-formed is rejected here rather than as noise in the user's ears.
fn decodes(ogg: &[u8]) -> Result<(), String> {
    use lewton::inside_ogg::OggStreamReader;

    let mut reader =
        OggStreamReader::new(Cursor::new(ogg)).map_err(|e| format!("headers not valid: {e}"))?;
    if reader.ident_hdr.audio_channels == 0 || reader.ident_hdr.audio_sample_rate == 0 {
        return Err("stream declares no channels or no sample rate".to_string());
    }
    // A handful of packets is enough to catch a codebook mismatch, which fails
    // as soon as a residue partition reads an undecodable value.
    for _ in 0..8 {
        match reader.read_dec_packet_itl() {
            Ok(Some(_)) => {}
            Ok(None) => break,
            Err(e) => return Err(format!("audio does not decode: {e}")),
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The packaged build must allow the webview to load the audio we hand it.
    ///
    /// A `tauri dev` run loads from the Vite server and never applies the app
    /// CSP, so a policy that blocks audio looks completely fine in development
    /// and ships broken: the player reports "ready" and then plays silence,
    /// because the `<audio>` element's source was refused. That is exactly what
    /// 0.6.0 did — `img-src` had been given `data:` for the texture viewer, but
    /// there was no `media-src` at all, so it fell back to `default-src 'self'`.
    #[test]
    fn the_csp_lets_the_webview_play_what_the_backend_sends() {
        let conf = std::fs::read_to_string(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/tauri.conf.json"
        ))
        .expect("tauri.conf.json is readable");
        let json: serde_json::Value = serde_json::from_str(&conf).expect("valid JSON");
        let csp = json["app"]["security"]["csp"]
            .as_str()
            .expect("a CSP is configured");

        let media = csp
            .split(';')
            .map(str::trim)
            .find(|d| d.starts_with("media-src"))
            .unwrap_or_else(|| panic!("no media-src directive; audio will not load:\n  {csp}"));
        // Playback uses a blob URL built from the base64 the backend sends.
        for source in ["blob:", "data:"] {
            assert!(
                media.contains(source),
                "media-src must allow {source} or playback silently fails:\n  {media}"
            );
        }
    }

    #[test]
    fn rubbish_input_is_rejected_not_returned() {
        assert!(to_ogg(b"").is_err());
        assert!(to_ogg(&[0u8; 256]).is_err());
        assert!(to_playable(b"").is_err());
        // A RIFF header with nothing behind it must not produce a "stream".
        let mut riff = b"RIFF".to_vec();
        riff.extend_from_slice(&4u32.to_le_bytes());
        riff.extend_from_slice(b"WAVE");
        assert!(to_ogg(&riff).is_err());
        assert!(to_playable(&riff).is_err());
    }

    /// Build a RIFF/WAVE file with the given `fmt ` body.
    fn riff(fmt: Vec<u8>, data: usize) -> Vec<u8> {
        let mut body = b"WAVE".to_vec();
        for (id, chunk) in [(b"fmt ", fmt), (b"data", vec![0; data])] {
            body.extend_from_slice(id);
            body.extend_from_slice(&(chunk.len() as u32).to_le_bytes());
            body.extend_from_slice(&chunk);
        }
        let mut out = b"RIFF".to_vec();
        out.extend_from_slice(&(body.len() as u32).to_le_bytes());
        out.extend_from_slice(&body);
        out
    }

    #[test]
    fn pcm_is_handed_over_untouched_rather_than_run_through_vorbis() {
        let mut fmt = Vec::new();
        fmt.extend_from_slice(&1u16.to_le_bytes()); // PCM
        fmt.extend_from_slice(&2u16.to_le_bytes());
        fmt.extend_from_slice(&44_100u32.to_le_bytes());
        fmt.extend_from_slice(&176_400u32.to_le_bytes());
        fmt.extend_from_slice(&4u16.to_le_bytes());
        fmt.extend_from_slice(&16u16.to_le_bytes());
        let wem = riff(fmt, 64);
        let out = to_playable(&wem).unwrap();
        assert_eq!(out.mime, "audio/wav");
        assert_eq!(out.bytes, wem, "PCM must not be re-encoded");
    }

    #[test]
    fn an_unsupported_codec_says_so_by_name() {
        let mut fmt = vec![0u8; 16];
        fmt[0..2].copy_from_slice(&0x0166u16.to_le_bytes()); // XMA2
        let err = to_playable(&riff(fmt, 64)).unwrap_err();
        assert!(err.contains("XMA2"), "got {err}");
    }

    #[test]
    fn an_ogg_that_is_not_vorbis_does_not_pass_validation() {
        assert!(decodes(b"OggS not really").is_err());
        assert!(decodes(&[]).is_err());
    }
}

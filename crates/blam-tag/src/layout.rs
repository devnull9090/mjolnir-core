//! The `blay` layout section: the tag's own description of its fields.
//!
//! Structure, offsets relative to the start of the tag body (file `0x4C`):
//!
//! ```text
//! 0x00  'blay'  four-CC                       Verified, 101/101 groups
//! 0x04  u32     section version, always 2      Verified
//! 0x08  u32     section size from 0x00         Verified
//! 0x0C  u32     0xFFFFFFFF                     Verified
//! 0x10  'wwwwCCCC4444' fixed ASCII fill        Verified
//! 0x1C  u32     per-group constant             Observed
//! 0x20  ..0x58  count/size table               Observed
//! 0x58  'tgly'  container section header       Verified
//! 0x64  'str*'  string blob section header     Verified
//! 0x70  blob    NUL-separated UTF-8 strings    Verified
//!       'x+zs'  option table marker            Verified
//!       u32     zero                           Verified
//!       u32     option entry count             Observed
//!       [u32]   string offsets, one per option Observed
//!       [12B]   field records                  Observed
//! ```
//!
//! See `docs/tag_body_format.md` for evidence and reproduction.

/// Offsets within the tag body.
const OFF_BLAY_MAGIC: usize = 0x00;
const OFF_BLAY_VERSION: usize = 0x04;
const OFF_BLAY_SIZE: usize = 0x08;
const OFF_TGLY: usize = 0x58;
const OFF_STR_MAGIC: usize = 0x64;
const OFF_STR_SIZE: usize = 0x6C;
const OFF_STR_BLOB: usize = 0x70;

/// Section magics as they appear on disk. Stored little-endian, so a `blay`
/// four-CC reads as the bytes `y a l b`.
const MAGIC_BLAY: [u8; 4] = *b"yalb";
const MAGIC_TGLY: [u8; 4] = *b"ylgt";
const MAGIC_STR: [u8; 4] = *b"*rts";
/// Literal bytes `x+zs` that delimit the end of the string blob.
const MARKER_OPTIONS: [u8; 4] = *b"x+zs";

/// A record from the field definition table.
///
/// **Provisional.** A fixed 12-byte stride reads correctly at the start of the
/// table but desynchronizes partway through: later names resolve to byte-shifted
/// substrings (`ong flags` for `long flags`, `bject` for `object`). The records
/// are therefore variable-length, with some field types carrying trailing inline
/// payload. Treat [`Layout::fields`] as a diagnostic aid, not ground truth, and
/// use [`Layout::field_table`] to re-parse once the encoding is settled.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct FieldRecord {
    /// Byte offset of the field name within the string blob.
    pub name_offset: u32,
    /// On-disk type code. Mapping to semantic types is still being established.
    pub type_code: u32,
    /// Auxiliary word; meaning is discriminated by `type_code`.
    pub aux: u32,
}

/// Provisional stride for [`FieldRecord`]. See the type's documentation.
pub const FIELD_RECORD_SIZE: usize = 12;

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("body is {0} bytes, too short for a blay header")]
    TooShort(usize),
    #[error("expected blay magic at body 0x00, found {0:?}")]
    NotBlay([u8; 4]),
    #[error("unsupported blay section version {0} (expected 2)")]
    BadVersion(u32),
    #[error("expected tgly magic at body 0x58, found {0:?}")]
    NotTgly([u8; 4]),
    #[error("expected str* magic at body 0x64, found {0:?}")]
    NotStr([u8; 4]),
    #[error("string blob of {size} bytes overruns the {body} byte body")]
    BlobOverrun { size: usize, body: usize },
    #[error("expected the x+zs option marker at body {0:#x}")]
    NoOptionMarker(usize),
}

fn u32_at(buf: &[u8], off: usize) -> Option<u32> {
    buf.get(off..off + 4)
        .map(|b| u32::from_le_bytes(b.try_into().unwrap()))
}

fn magic_at(buf: &[u8], off: usize) -> [u8; 4] {
    buf.get(off..off + 4)
        .map(|b| <[u8; 4]>::try_from(b).unwrap())
        .unwrap_or_default()
}

/// A parsed `blay` layout section borrowed from the tag body.
#[derive(Debug)]
pub struct Layout<'a> {
    pub version: u32,
    pub size: u32,
    /// The `blay` count/size table at body `0x20`..`0x58`, still uninterpreted.
    pub header_words: [u32; 14],
    /// NUL-separated UTF-8 string blob. Referenced elsewhere by byte offset.
    pub blob: &'a [u8],
    /// Body offset at which the blob begins.
    pub blob_start: usize,
    /// String-blob offsets for every enum and bitfield option, in order.
    pub option_offsets: Vec<u32>,
    /// Entry count declared by the option table header.
    pub declared_option_count: u32,
    /// True when the declared option count overruns the layout section. Some
    /// groups (`chud_definition`, `achievements`) hit this, so the count word's
    /// semantics are not yet fully settled. See `docs/tag_body_format.md`.
    pub options_truncated: bool,
    /// Provisional decode of the field definition table. See [`FieldRecord`].
    pub fields: Vec<FieldRecord>,
    /// The raw field table bytes, for re-parsing once the encoding is settled.
    pub field_table: &'a [u8],
}

impl<'a> Layout<'a> {
    pub fn parse(body: &'a [u8]) -> Result<Self, Error> {
        if body.len() < OFF_STR_BLOB {
            return Err(Error::TooShort(body.len()));
        }

        let magic = magic_at(body, OFF_BLAY_MAGIC);
        if magic != MAGIC_BLAY {
            return Err(Error::NotBlay(magic));
        }
        let version = u32_at(body, OFF_BLAY_VERSION).unwrap();
        if version != 2 {
            return Err(Error::BadVersion(version));
        }
        let size = u32_at(body, OFF_BLAY_SIZE).unwrap();

        let tgly = magic_at(body, OFF_TGLY);
        if tgly != MAGIC_TGLY {
            return Err(Error::NotTgly(tgly));
        }
        let strm = magic_at(body, OFF_STR_MAGIC);
        if strm != MAGIC_STR {
            return Err(Error::NotStr(strm));
        }

        let mut header_words = [0u32; 14];
        for (i, w) in header_words.iter_mut().enumerate() {
            *w = u32_at(body, 0x20 + i * 4).unwrap_or(0);
        }

        let blob_size = u32_at(body, OFF_STR_SIZE).unwrap() as usize;
        let blob_end = OFF_STR_BLOB + blob_size;
        if blob_end > body.len() {
            return Err(Error::BlobOverrun {
                size: blob_size,
                body: body.len(),
            });
        }
        let blob = &body[OFF_STR_BLOB..blob_end];

        // The option table follows the blob immediately. The blob is byte
        // packed, so this offset is frequently not dword aligned.
        if body.get(blob_end..blob_end + 4) != Some(&MARKER_OPTIONS[..]) {
            return Err(Error::NoOptionMarker(blob_end));
        }
        let declared_option_count = u32_at(body, blob_end + 8).unwrap_or(0);
        let options_start = blob_end + 12;
        let layout_end = (OFF_BLAY_MAGIC + size as usize).min(body.len());

        // Clamp to whichever comes first: the declared count, the end of the
        // layout section, or the end of the body.
        let available = layout_end.saturating_sub(options_start) / 4;
        let take = (declared_option_count as usize).min(available);
        let options_truncated = (declared_option_count as usize) > available;

        let mut option_offsets = Vec::with_capacity(take);
        for i in 0..take {
            match u32_at(body, options_start + i * 4) {
                Some(v) => option_offsets.push(v),
                None => break,
            }
        }

        // Field records run from the end of the option table to the end of the
        // layout section.
        let fields_start = options_start + option_offsets.len() * 4;
        let field_table = body.get(fields_start..layout_end).unwrap_or(&[]);
        let mut fields = Vec::new();
        for chunk in field_table.chunks_exact(FIELD_RECORD_SIZE) {
            fields.push(FieldRecord {
                name_offset: u32::from_le_bytes(chunk[0..4].try_into().unwrap()),
                type_code: u32::from_le_bytes(chunk[4..8].try_into().unwrap()),
                aux: u32::from_le_bytes(chunk[8..12].try_into().unwrap()),
            });
        }

        Ok(Layout {
            version,
            size,
            header_words,
            blob,
            blob_start: OFF_STR_BLOB,
            option_offsets,
            declared_option_count,
            options_truncated,
            fields,
            field_table,
        })
    }

    /// Resolve a string-blob byte offset to its NUL-terminated string.
    pub fn string_at(&self, offset: u32) -> Option<&'a str> {
        let start = offset as usize;
        if start >= self.blob.len() {
            return None;
        }
        let end = self.blob[start..]
            .iter()
            .position(|b| *b == 0)
            .map(|p| start + p)
            .unwrap_or(self.blob.len());
        std::str::from_utf8(&self.blob[start..end]).ok()
    }

    /// Every string in the blob, paired with its byte offset.
    pub fn strings(&self) -> Vec<(u32, &'a str)> {
        let mut out = Vec::new();
        let mut off = 0usize;
        while off < self.blob.len() {
            let end = self.blob[off..]
                .iter()
                .position(|b| *b == 0)
                .map(|p| off + p)
                .unwrap_or(self.blob.len());
            if let Ok(s) = std::str::from_utf8(&self.blob[off..end]) {
                out.push((off as u32, s));
            }
            off = end + 1;
        }
        out
    }

    /// Resolve the option table to strings, in declaration order.
    pub fn options(&self) -> Vec<&'a str> {
        self.option_offsets
            .iter()
            .filter_map(|o| self.string_at(*o))
            .collect()
    }

    /// Resolve field records to `(name, type_code, aux)`.
    pub fn named_fields(&self) -> Vec<(&'a str, u32, u32)> {
        self.fields
            .iter()
            .map(|f| {
                (
                    self.string_at(f.name_offset).unwrap_or(""),
                    f.type_code,
                    f.aux,
                )
            })
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn magic_constants_match_the_documented_byte_order() {
        // Reading a four-CC means reversing the on-disk bytes.
        let read = |m: [u8; 4]| -> String {
            m.iter().rev().map(|b| *b as char).collect()
        };
        assert_eq!(read(MAGIC_BLAY), "blay");
        assert_eq!(read(MAGIC_TGLY), "tgly");
        assert_eq!(read(MAGIC_STR), "str*");
    }

    /// Build a minimal but structurally valid layout section.
    fn synth(strings: &[&str], options: &[u32], fields: &[FieldRecord]) -> Vec<u8> {
        let mut blob = Vec::new();
        for s in strings {
            blob.extend_from_slice(s.as_bytes());
            blob.push(0);
        }

        let mut body = vec![0u8; OFF_STR_BLOB];
        body[OFF_BLAY_MAGIC..4].copy_from_slice(&MAGIC_BLAY);
        body[OFF_BLAY_VERSION..OFF_BLAY_VERSION + 4].copy_from_slice(&2u32.to_le_bytes());
        body[OFF_TGLY..OFF_TGLY + 4].copy_from_slice(&MAGIC_TGLY);
        body[OFF_STR_MAGIC..OFF_STR_MAGIC + 4].copy_from_slice(&MAGIC_STR);
        body[OFF_STR_SIZE..OFF_STR_SIZE + 4].copy_from_slice(&(blob.len() as u32).to_le_bytes());
        body.extend_from_slice(&blob);

        body.extend_from_slice(&MARKER_OPTIONS);
        body.extend_from_slice(&0u32.to_le_bytes());
        body.extend_from_slice(&(options.len() as u32).to_le_bytes());
        for o in options {
            body.extend_from_slice(&o.to_le_bytes());
        }
        for f in fields {
            body.extend_from_slice(&f.name_offset.to_le_bytes());
            body.extend_from_slice(&f.type_code.to_le_bytes());
            body.extend_from_slice(&f.aux.to_le_bytes());
        }

        let size = body.len() as u32;
        body[OFF_BLAY_SIZE..OFF_BLAY_SIZE + 4].copy_from_slice(&size.to_le_bytes());
        body
    }

    #[test]
    fn round_trips_strings_options_and_fields() {
        let fields = [
            FieldRecord {
                name_offset: 0,
                type_code: 4,
                aux: 0,
            },
            FieldRecord {
                name_offset: 5,
                type_code: 11,
                aux: 2,
            },
        ];
        // Blob offsets: "item" at 0, "flags" at 5, "never" at 11.
        let body = synth(&["item", "flags", "never"], &[5, 11], &fields);
        let l = Layout::parse(&body).unwrap();

        assert_eq!(l.version, 2);
        assert_eq!(l.string_at(0), Some("item"));
        assert_eq!(l.string_at(5), Some("flags"));
        assert_eq!(l.strings().len(), 3);
        assert_eq!(l.options(), vec!["flags", "never"]);
        assert_eq!(l.fields, fields);
        assert_eq!(l.named_fields()[1], ("flags", 11, 2));
    }

    #[test]
    fn rejects_a_body_without_blay_magic() {
        let mut body = synth(&["a"], &[], &[]);
        body[0..4].copy_from_slice(b"zzzz");
        assert!(matches!(Layout::parse(&body), Err(Error::NotBlay(_))));
    }

    #[test]
    fn rejects_a_missing_option_marker() {
        let mut body = synth(&["a"], &[], &[]);
        let blob_end = OFF_STR_BLOB + 2;
        body[blob_end..blob_end + 4].copy_from_slice(b"zzzz");
        assert!(matches!(
            Layout::parse(&body),
            Err(Error::NoOptionMarker(_))
        ));
    }

    #[test]
    fn rejects_a_blob_that_overruns_the_body() {
        let mut body = synth(&["a"], &[], &[]);
        body[OFF_STR_SIZE..OFF_STR_SIZE + 4].copy_from_slice(&9999u32.to_le_bytes());
        assert!(matches!(
            Layout::parse(&body),
            Err(Error::BlobOverrun { .. })
        ));
    }
}

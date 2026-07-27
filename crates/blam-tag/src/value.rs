//! Decode one field's fixed-width value out of packed element bytes.
//!
//! [`crate::data`] recovers the *structure* of a tag's values: which blocks hold
//! how many elements, and where each element's bytes are. This turns those bytes
//! into typed values, driven by the type names the tag carries in its own
//! `blay` layout, so there is nothing hardcoded per group.
//!
//! Values are reported as stored. In particular an `angle` is left in radians
//! rather than converted to the degrees Guerilla displayed, because this is the
//! layer an editor writes back through, and a silent unit change here would be a
//! silent corruption there.
//!
//! See `docs/tag_body_format.md` for the type vocabulary.

use crate::layout::{FieldEntry, Layout};

/// A decoded fixed-width field value.
#[derive(Debug, Clone, PartialEq)]
pub enum Scalar {
    /// Any integer type, widened. Signed types keep their sign.
    Int(i64),
    Real(f32),
    /// Vectors, colours, bounds and planes: two to four reals.
    Reals(Vec<f32>),
    /// Two to four small integers, for `rectangle 2d` and integer bounds.
    Ints(Vec<i64>),
    /// An enum, with the option name if the value indexes one.
    Enum { raw: i64, option: Option<String> },
    /// A bitfield, with the names of the bits that are set.
    Flags { raw: u64, set: Vec<String> },
    /// An index into a block, or `None` when it is the -1 "unset" sentinel.
    BlockIndex(Option<i64>),
    /// A NUL-padded fixed-width string.
    Text(String),
    /// A four-character code, such as a `tag` group.
    FourCc(String),
    /// A reference to another tag: its group four-CC and its path.
    Reference { group: String, path: String },
    /// A packed colour, as `#rrggbb` or `#aarrggbb`.
    Color(String),
    /// A type with no fixed-width payload worth showing, or bytes not yet
    /// interpreted. Carries the raw bytes so nothing is hidden.
    Raw(Vec<u8>),
    /// The field occupies no bytes, or its bytes were not available.
    Empty,
}

impl Scalar {
    /// A short human-readable rendering, the same one the CLI prints.
    pub fn display(&self) -> String {
        match self {
            Scalar::Int(v) => v.to_string(),
            Scalar::Real(v) => format_real(*v),
            Scalar::Reals(v) => {
                let parts: Vec<String> = v.iter().map(|r| format_real(*r)).collect();
                format!("({})", parts.join(", "))
            }
            Scalar::Ints(v) => {
                let parts: Vec<String> = v.iter().map(|i| i.to_string()).collect();
                format!("({})", parts.join(", "))
            }
            Scalar::Enum { raw, option } => match option {
                Some(name) => format!("{name} ({raw})"),
                None => format!("{raw}"),
            },
            Scalar::Flags { raw, set } => {
                if set.is_empty() {
                    format!("none (0x{raw:x})")
                } else {
                    format!("{} (0x{raw:x})", set.join(" | "))
                }
            }
            Scalar::BlockIndex(Some(i)) => format!("#{i}"),
            Scalar::BlockIndex(None) => "none".to_string(),
            Scalar::Text(s) => format!("{s:?}"),
            Scalar::FourCc(s) => s.clone(),
            Scalar::Reference { group, path } if path.is_empty() => format!("none ({group})"),
            Scalar::Reference { group, path } => format!("{path} ({group})"),
            Scalar::Color(s) => s.clone(),
            Scalar::Raw(b) if b.is_empty() => String::new(),
            Scalar::Raw(b) => b
                .iter()
                .take(16)
                .map(|x| format!("{x:02x}"))
                .collect::<Vec<_>>()
                .join(" "),
            Scalar::Empty => String::new(),
        }
    }

    /// Is there anything worth showing next to the field name?
    pub fn is_empty(&self) -> bool {
        matches!(self, Scalar::Empty) || matches!(self, Scalar::Raw(b) if b.is_empty())
    }
}

/// Trim trailing zeros so a table of reals stays readable.
fn format_real(v: f32) -> String {
    if v == 0.0 {
        // Also catches -0.0, which would otherwise print as "-0".
        return "0".to_string();
    }
    if v.is_nan() || v.is_infinite() {
        return format!("{v}");
    }
    let s = format!("{v:.6}");
    let s = s.trim_end_matches('0').trim_end_matches('.');
    s.to_string()
}

fn i(bytes: &[u8], n: usize, signed: bool) -> Option<i64> {
    let slice = bytes.get(..n)?;
    let mut raw = 0u64;
    for (k, b) in slice.iter().enumerate() {
        raw |= (*b as u64) << (8 * k);
    }
    if signed {
        let shift = 64 - n * 8;
        Some(((raw << shift) as i64) >> shift)
    } else {
        Some(raw as i64)
    }
}

fn f32_at(bytes: &[u8], at: usize) -> Option<f32> {
    let b = bytes.get(at..at + 4)?;
    Some(f32::from_le_bytes(b.try_into().unwrap()))
}

fn reals(bytes: &[u8], n: usize) -> Option<Scalar> {
    let mut out = Vec::with_capacity(n);
    for k in 0..n {
        out.push(f32_at(bytes, k * 4)?);
    }
    Some(Scalar::Reals(out))
}

fn shorts(bytes: &[u8], n: usize) -> Option<Scalar> {
    let mut out = Vec::with_capacity(n);
    for k in 0..n {
        out.push(i(bytes.get(k * 2..)?, 2, true)?);
    }
    Some(Scalar::Ints(out))
}

fn text(bytes: &[u8]) -> Scalar {
    let end = bytes.iter().position(|b| *b == 0).unwrap_or(bytes.len());
    Scalar::Text(String::from_utf8_lossy(&bytes[..end]).into_owned())
}

/// Decode `field` from the packed element bytes starting at the field's offset.
///
/// `bytes` must start at the field, not at the element. Returns [`Scalar::Empty`]
/// when the field has no fixed-width payload or the bytes are short.
pub fn read(layout: &Layout<'_>, field: &FieldEntry, bytes: &[u8]) -> Scalar {
    let type_name = layout.type_name_of(field);
    decode(type_name, bytes, || layout.field_options(field))
}

/// Decode by type name. `options` is called only for enum and bitfield types.
fn decode<'a>(
    type_name: &str,
    bytes: &[u8],
    options: impl Fn() -> Vec<&'a str>,
) -> Scalar {
    let signed_int = |n: usize| i(bytes, n, true).map(Scalar::Int).unwrap_or(Scalar::Empty);
    let unsigned_int = |n: usize| i(bytes, n, false).map(Scalar::Int).unwrap_or(Scalar::Empty);

    match type_name {
        // Integers. Halo's `byte`, `word` and `dword` integers are unsigned;
        // `char`, `short`, `long` and `int64` are signed.
        "char integer" => signed_int(1),
        "short integer" => signed_int(2),
        "long integer" => signed_int(4),
        "int64 integer" => signed_int(8),
        "byte integer" => unsigned_int(1),
        "word integer" => unsigned_int(2),
        "dword integer" => unsigned_int(4),

        // Block indices use -1 as "unset".
        "char block index" => block_index(bytes, 1),
        "short block index" | "custom short block index" => block_index(bytes, 2),
        "long block index" | "custom long block index" => block_index(bytes, 4),

        "char enum" => enum_of(bytes, 1, &options()),
        "short enum" => enum_of(bytes, 2, &options()),
        "long enum" => enum_of(bytes, 4, &options()),

        "byte flags" => flags_of(bytes, 1, &options()),
        "word flags" => flags_of(bytes, 2, &options()),
        "long flags" | "long block flags" => flags_of(bytes, 4, &options()),

        "real" | "real fraction" | "angle" => {
            f32_at(bytes, 0).map(Scalar::Real).unwrap_or(Scalar::Empty)
        }
        "real bounds" | "angle bounds" | "fraction bounds" | "real point 2d"
        | "real vector 2d" | "real euler angles 2d" => {
            reals(bytes, 2).unwrap_or(Scalar::Empty)
        }
        "real point 3d" | "real vector 3d" | "real euler angles 3d" | "real rgb color"
        | "real plane 2d" => reals(bytes, 3).unwrap_or(Scalar::Empty),
        "real argb color" | "real plane 3d" | "real quaternion" => {
            reals(bytes, 4).unwrap_or(Scalar::Empty)
        }

        "short integer bounds" => shorts(bytes, 2).unwrap_or(Scalar::Empty),
        "rectangle 2d" => shorts(bytes, 4).unwrap_or(Scalar::Empty),

        "rgb color" => color(bytes, false),
        "argb color" => color(bytes, true),

        "string" | "long string" => text(bytes),
        "tag" => four_cc(bytes),

        // These carry their payload in a trailing section; the inline bytes are
        // a handle the reader does not need, so show them raw rather than
        // inventing a meaning.
        "string id" | "data" | "tag reference" | "block" | "api interop"
        | "pageable resource" => Scalar::Raw(bytes.to_vec()),

        // Structural: no value of their own.
        "struct" | "array" | "pad" | "custom" | "terminator X" => Scalar::Empty,

        _ => Scalar::Raw(bytes.to_vec()),
    }
}

fn block_index(bytes: &[u8], n: usize) -> Scalar {
    match i(bytes, n, true) {
        Some(v) if v < 0 => Scalar::BlockIndex(None),
        Some(v) => Scalar::BlockIndex(Some(v)),
        None => Scalar::Empty,
    }
}

fn enum_of(bytes: &[u8], n: usize, options: &[&str]) -> Scalar {
    let Some(raw) = i(bytes, n, false) else {
        return Scalar::Empty;
    };
    let option = usize::try_from(raw)
        .ok()
        .and_then(|k| options.get(k))
        .map(|s| s.to_string());
    Scalar::Enum { raw, option }
}

fn flags_of(bytes: &[u8], n: usize, options: &[&str]) -> Scalar {
    let Some(raw) = i(bytes, n, false) else {
        return Scalar::Empty;
    };
    let raw = raw as u64;
    let mut set = Vec::new();
    for bit in 0..(n * 8) {
        if raw & (1 << bit) != 0 {
            match options.get(bit) {
                Some(name) => set.push(name.to_string()),
                None => set.push(format!("bit {bit}")),
            }
        }
    }
    Scalar::Flags { raw, set }
}

/// A packed colour word. Stored little-endian, so the bytes read b, g, r, a.
fn color(bytes: &[u8], with_alpha: bool) -> Scalar {
    let Some(b) = bytes.get(..4) else {
        return Scalar::Empty;
    };
    if with_alpha {
        Scalar::Color(format!("#{:02x}{:02x}{:02x}{:02x}", b[3], b[2], b[1], b[0]))
    } else {
        Scalar::Color(format!("#{:02x}{:02x}{:02x}", b[2], b[1], b[0]))
    }
}

/// Split a `tag reference` section's content into its group and path.
///
/// The content is a four-CC, stored reversed like every other magic, followed
/// by the tag path: `lloc` + `fx\holograms\hologram_01` is the
/// `collision_model` at that path. An empty section means no reference.
pub fn reference(content: &[u8]) -> Scalar {
    if content.is_empty() {
        return Scalar::Empty;
    }
    let Some(cc) = content.get(..4) else {
        return Scalar::Raw(content.to_vec());
    };
    let group: String = cc
        .iter()
        .rev()
        .map(|c| if (32..127).contains(c) { *c as char } else { '.' })
        .collect();
    let rest = &content[4..];
    let end = rest.iter().position(|c| *c == 0).unwrap_or(rest.len());
    Scalar::Reference {
        group,
        path: String::from_utf8_lossy(&rest[..end]).into_owned(),
    }
}

/// A four-CC, stored reversed like every other magic in the format.
fn four_cc(bytes: &[u8]) -> Scalar {
    let Some(b) = bytes.get(..4) else {
        return Scalar::Empty;
    };
    if b.iter().all(|c| *c == 0) {
        return Scalar::Empty;
    }
    Scalar::FourCc(
        b.iter()
            .rev()
            .map(|c| if (32..127).contains(c) { *c as char } else { '.' })
            .collect(),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn none() -> Vec<&'static str> {
        Vec::new()
    }

    #[test]
    fn signed_and_unsigned_integers_differ_on_the_high_bit() {
        assert_eq!(decode("char integer", &[0xFF], none), Scalar::Int(-1));
        assert_eq!(decode("byte integer", &[0xFF], none), Scalar::Int(255));
        assert_eq!(decode("short integer", &[0xFF, 0xFF], none), Scalar::Int(-1));
        assert_eq!(decode("word integer", &[0xFF, 0xFF], none), Scalar::Int(65535));
        assert_eq!(
            decode("long integer", &[0x00, 0x00, 0x00, 0x80], none),
            Scalar::Int(i32::MIN as i64)
        );
    }

    #[test]
    fn a_block_index_of_minus_one_reads_as_unset() {
        assert_eq!(
            decode("short block index", &[0xFF, 0xFF], none),
            Scalar::BlockIndex(None)
        );
        assert_eq!(
            decode("short block index", &[0x03, 0x00], none),
            Scalar::BlockIndex(Some(3))
        );
    }

    #[test]
    fn an_enum_resolves_its_option_name() {
        let opts = || vec!["default", "never", "always", "blur"];
        assert_eq!(
            decode("short enum", &[2, 0], opts),
            Scalar::Enum {
                raw: 2,
                option: Some("always".into())
            }
        );
        // Out of range stays honest rather than guessing.
        assert_eq!(
            decode("short enum", &[9, 0], opts),
            Scalar::Enum {
                raw: 9,
                option: None
            }
        );
    }

    #[test]
    fn flags_name_every_set_bit_in_order() {
        let opts = || vec!["early mover", "does not cast shadow", "super_sinker"];
        let v = decode("word flags", &[0b101, 0], opts);
        assert_eq!(
            v,
            Scalar::Flags {
                raw: 0b101,
                set: vec!["early mover".into(), "super_sinker".into()]
            }
        );
        assert_eq!(v.display(), "early mover | super_sinker (0x5)");
    }

    #[test]
    fn an_unnamed_bit_is_reported_by_index() {
        let opts = || vec!["only one"];
        assert_eq!(
            decode("byte flags", &[0b10], opts),
            Scalar::Flags {
                raw: 0b10,
                set: vec!["bit 1".into()]
            }
        );
    }

    #[test]
    fn vectors_decode_to_the_right_arity() {
        let mut b = Vec::new();
        for v in [1.0f32, 2.0, 3.0, 4.0] {
            b.extend_from_slice(&v.to_le_bytes());
        }
        assert_eq!(decode("real point 2d", &b, none), Scalar::Reals(vec![1.0, 2.0]));
        assert_eq!(
            decode("real vector 3d", &b, none),
            Scalar::Reals(vec![1.0, 2.0, 3.0])
        );
        assert_eq!(
            decode("real quaternion", &b, none),
            Scalar::Reals(vec![1.0, 2.0, 3.0, 4.0])
        );
        assert_eq!(
            decode("real vector 3d", &b, none).display(),
            "(1, 2, 3)"
        );
    }

    #[test]
    fn a_fixed_width_string_stops_at_the_first_nul() {
        let mut b = vec![0u8; 32];
        b[..5].copy_from_slice(b"elite");
        assert_eq!(decode("string", &b, none), Scalar::Text("elite".into()));
    }

    #[test]
    fn a_tag_four_cc_reads_reversed_like_every_other_magic() {
        assert_eq!(decode("tag", b"paew", none), Scalar::FourCc("weap".into()));
        assert_eq!(decode("tag", &[0, 0, 0, 0], none), Scalar::Empty);
    }

    #[test]
    fn a_tag_reference_splits_into_group_and_path() {
        // As shipped in `hologram_01-model`: `lloc` reversed is `coll`.
        let mut content = b"lloc".to_vec();
        content.extend_from_slice(b"fx\\holograms\\hologram_01");
        let v = reference(&content);
        assert_eq!(
            v,
            Scalar::Reference {
                group: "coll".into(),
                path: "fx\\holograms\\hologram_01".into()
            }
        );
        assert_eq!(v.display(), "fx\\holograms\\hologram_01 (coll)");
    }

    #[test]
    fn an_empty_tag_reference_is_no_reference() {
        assert_eq!(reference(&[]), Scalar::Empty);
    }

    #[test]
    fn colors_render_as_hex() {
        // Stored little-endian, so bytes are b, g, r, a.
        assert_eq!(
            decode("rgb color", &[0x33, 0x22, 0x11, 0xff], none),
            Scalar::Color("#112233".into())
        );
        assert_eq!(
            decode("argb color", &[0x33, 0x22, 0x11, 0xff], none),
            Scalar::Color("#ff112233".into())
        );
    }

    #[test]
    fn structural_types_have_no_value() {
        for t in ["struct", "array", "pad", "custom", "terminator X"] {
            assert_eq!(decode(t, &[1, 2, 3, 4], none), Scalar::Empty, "{t}");
        }
    }

    #[test]
    fn short_bytes_do_not_panic() {
        assert_eq!(decode("long integer", &[1, 2], none), Scalar::Empty);
        assert_eq!(decode("real vector 3d", &[0; 4], none), Scalar::Empty);
        assert_eq!(decode("tag", &[], none), Scalar::Empty);
    }

    #[test]
    fn reals_print_without_trailing_noise() {
        assert_eq!(format_real(0.0), "0");
        assert_eq!(format_real(-0.0), "0");
        assert_eq!(format_real(1.5), "1.5");
        assert_eq!(format_real(2.0), "2");
    }
}

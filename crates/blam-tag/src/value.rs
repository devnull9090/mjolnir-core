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
    /// An index into a block. Negative means unset; -1 is the usual sentinel,
    /// but the shipped data also carries other negatives, so the raw value is
    /// kept rather than collapsed.
    BlockIndex(i64),
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
            Scalar::BlockIndex(i) if *i == -1 => "none".to_string(),
            Scalar::BlockIndex(i) if *i < 0 => format!("none ({i})"),
            Scalar::BlockIndex(i) => format!("#{i}"),
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

/// Why a value could not be written back into a field.
#[derive(Debug, thiserror::Error, PartialEq)]
pub enum WriteError {
    #[error("a {type_name} field cannot hold {value}")]
    WrongKind {
        type_name: String,
        value: &'static str,
    },
    #[error("{value} does not fit a {type_name}")]
    OutOfRange { type_name: String, value: String },
    #[error("a {type_name} takes {want} value(s), got {got}")]
    WrongArity {
        type_name: String,
        want: usize,
        got: usize,
    },
    #[error("a {type_name} needs {want} bytes, the field has {got}")]
    Short {
        type_name: String,
        want: usize,
        got: usize,
    },
    #[error("{type_name} values are not editable in place")]
    NotEditable { type_name: String },
}

/// Encode `value` into `bytes`, the field's own slice of the packed element.
///
/// The exact inverse of [`read`], and deliberately strict: a value that does not
/// fit its field is rejected rather than truncated, because the caller is about
/// to write this into somebody's game data. Writes nothing on error.
///
/// Only the fixed-width part is written. A field whose payload lives in a
/// trailing section — a `string id`, `data`, `tag reference` — is rejected here,
/// because changing those resizes the tag rather than overwriting bytes in
/// place.
pub fn write(
    layout: &Layout<'_>,
    field: &FieldEntry,
    value: &Scalar,
    bytes: &mut [u8],
) -> Result<(), WriteError> {
    encode(layout.type_name_of(field), value, bytes)
}

/// [`write`], by type name. The inverse of `decode`.
pub fn encode(type_name: &str, value: &Scalar, bytes: &mut [u8]) -> Result<(), WriteError> {
    let type_name = type_name.to_string();
    let width = width_of(&type_name);

    if let Some(want) = width {
        if bytes.len() < want {
            return Err(WriteError::Short {
                type_name,
                want,
                got: bytes.len(),
            });
        }
    }

    match (&type_name[..], value) {
        // Integers, block indices and enums all land as one little-endian
        // integer of the type's width; only their range checks differ.
        ("char integer", Scalar::Int(v)) => put_int(bytes, *v, 1, true, &type_name),
        ("short integer", Scalar::Int(v)) => put_int(bytes, *v, 2, true, &type_name),
        ("long integer", Scalar::Int(v)) => put_int(bytes, *v, 4, true, &type_name),
        ("int64 integer", Scalar::Int(v)) => put_int(bytes, *v, 8, true, &type_name),
        ("byte integer", Scalar::Int(v)) => put_int(bytes, *v, 1, false, &type_name),
        ("word integer", Scalar::Int(v)) => put_int(bytes, *v, 2, false, &type_name),
        ("dword integer", Scalar::Int(v)) => put_int(bytes, *v, 4, false, &type_name),

        ("char block index", Scalar::BlockIndex(v)) => put_int(bytes, *v, 1, true, &type_name),
        ("short block index" | "custom short block index", Scalar::BlockIndex(v)) => {
            put_int(bytes, *v, 2, true, &type_name)
        }
        ("long block index" | "custom long block index", Scalar::BlockIndex(v)) => {
            put_int(bytes, *v, 4, true, &type_name)
        }

        ("char enum", Scalar::Enum { raw, .. }) => put_int(bytes, *raw, 1, false, &type_name),
        ("short enum", Scalar::Enum { raw, .. }) => put_int(bytes, *raw, 2, false, &type_name),
        ("long enum", Scalar::Enum { raw, .. }) => put_int(bytes, *raw, 4, false, &type_name),

        ("byte flags", Scalar::Flags { raw, .. }) => {
            put_int(bytes, *raw as i64, 1, false, &type_name)
        }
        ("word flags", Scalar::Flags { raw, .. }) => {
            put_int(bytes, *raw as i64, 2, false, &type_name)
        }
        ("long flags" | "long block flags", Scalar::Flags { raw, .. }) => {
            put_int(bytes, *raw as i64, 4, false, &type_name)
        }

        ("real" | "real fraction" | "angle", Scalar::Real(v)) => {
            bytes[..4].copy_from_slice(&v.to_le_bytes());
            Ok(())
        }
        (_, Scalar::Reals(v)) if width.is_some() => {
            let want = width.unwrap() / 4;
            if v.len() != want {
                return Err(WriteError::WrongArity {
                    type_name,
                    want,
                    got: v.len(),
                });
            }
            for (k, r) in v.iter().enumerate() {
                bytes[k * 4..k * 4 + 4].copy_from_slice(&r.to_le_bytes());
            }
            Ok(())
        }
        (_, Scalar::Ints(v)) if width.is_some() => {
            let want = width.unwrap() / 2;
            if v.len() != want {
                return Err(WriteError::WrongArity {
                    type_name,
                    want,
                    got: v.len(),
                });
            }
            for (k, n) in v.iter().enumerate() {
                put_int(&mut bytes[k * 2..], *n, 2, true, &type_name)?;
            }
            Ok(())
        }

        ("rgb color" | "argb color", Scalar::Color(s)) => put_color(bytes, s, &type_name),
        ("string" | "long string", Scalar::Text(s)) => put_text(bytes, s, &type_name),
        ("tag", Scalar::FourCc(s)) => put_four_cc(bytes, s, &type_name),

        // Section-backed and structural types.
        (
            "string id" | "data" | "tag reference" | "block" | "struct" | "array"
            | "pageable resource" | "api interop" | "pad" | "custom" | "terminator X",
            _,
        ) => Err(WriteError::NotEditable { type_name }),

        (_, v) => Err(WriteError::WrongKind {
            type_name,
            value: kind_name(v),
        }),
    }
}

/// Fixed width of a type, where it has one.
fn width_of(type_name: &str) -> Option<usize> {
    Some(match type_name {
        "char integer" | "byte integer" | "char block index" | "char enum" | "byte flags" => 1,
        "short integer" | "word integer" | "short block index" | "custom short block index"
        | "short enum" | "word flags" => 2,
        "long integer" | "dword integer" | "long block index" | "custom long block index"
        | "long enum" | "long flags" | "long block flags" | "real" | "real fraction" | "angle"
        | "rgb color" | "argb color" | "tag" => 4,
        "int64 integer" | "real bounds" | "angle bounds" | "fraction bounds" | "real point 2d"
        | "real vector 2d" | "real euler angles 2d" => 8,
        "short integer bounds" => 4,
        "rectangle 2d" => 8,
        "real point 3d" | "real vector 3d" | "real euler angles 3d" | "real rgb color"
        | "real plane 2d" => 12,
        "real argb color" | "real plane 3d" | "real quaternion" => 16,
        "string" => 32,
        "long string" => 256,
        _ => return None,
    })
}

fn kind_name(v: &Scalar) -> &'static str {
    match v {
        Scalar::Int(_) => "an integer",
        Scalar::Real(_) => "a real",
        Scalar::Reals(_) => "a real vector",
        Scalar::Ints(_) => "an integer vector",
        Scalar::Enum { .. } => "an enum",
        Scalar::Flags { .. } => "flags",
        Scalar::BlockIndex(_) => "a block index",
        Scalar::Text(_) => "text",
        Scalar::FourCc(_) => "a four-CC",
        Scalar::Reference { .. } => "a tag reference",
        Scalar::Color(_) => "a colour",
        Scalar::Raw(_) => "raw bytes",
        Scalar::Empty => "no value",
    }
}

fn put_int(
    bytes: &mut [u8],
    v: i64,
    n: usize,
    signed: bool,
    type_name: &str,
) -> Result<(), WriteError> {
    let fits = if signed {
        // At 8 bytes the range is the whole of i64, and computing the bound
        // would overflow while checking it.
        if n >= 8 {
            true
        } else {
            let bits = n * 8 - 1;
            v >= -(1i64 << bits) && v < (1i64 << bits)
        }
    } else {
        let max = if n >= 8 { u64::MAX } else { (1u64 << (n * 8)) - 1 };
        v >= 0 && (v as u64) <= max
    };
    if !fits {
        return Err(WriteError::OutOfRange {
            type_name: type_name.to_string(),
            value: v.to_string(),
        });
    }
    let raw = v as u64;
    for (k, b) in bytes.iter_mut().take(n).enumerate() {
        *b = (raw >> (8 * k)) as u8;
    }
    Ok(())
}

/// `#rgb` forms, written back into the little-endian b, g, r, a order.
fn put_color(bytes: &mut [u8], s: &str, type_name: &str) -> Result<(), WriteError> {
    let hex = s.trim_start_matches('#');
    let bad = || WriteError::OutOfRange {
        type_name: type_name.to_string(),
        value: s.to_string(),
    };
    let n = |at: usize| u8::from_str_radix(hex.get(at..at + 2).ok_or_else(bad)?, 16).map_err(|_| bad());
    match hex.len() {
        6 => {
            bytes[0] = n(4)?;
            bytes[1] = n(2)?;
            bytes[2] = n(0)?;
            // The alpha byte is left as it was; a `#rrggbb` says nothing about it.
            Ok(())
        }
        8 => {
            bytes[0] = n(6)?;
            bytes[1] = n(4)?;
            bytes[2] = n(2)?;
            bytes[3] = n(0)?;
            Ok(())
        }
        _ => Err(bad()),
    }
}

fn put_text(bytes: &mut [u8], s: &str, type_name: &str) -> Result<(), WriteError> {
    // One byte is reserved for the terminator, as the shipped data does.
    if s.len() >= bytes.len() {
        return Err(WriteError::OutOfRange {
            type_name: type_name.to_string(),
            value: format!("{} bytes of text", s.len()),
        });
    }
    bytes[..s.len()].copy_from_slice(s.as_bytes());
    // Terminate, then leave the rest of the field alone. The shipped data keeps
    // whatever was in the tail of a fixed-width string — 80 `long string`
    // fields carry non-zero bytes past their terminator — and readers stop at
    // the NUL, so clearing the tail would rewrite bytes nobody asked to change.
    bytes[s.len()] = 0;
    Ok(())
}

fn put_four_cc(bytes: &mut [u8], s: &str, type_name: &str) -> Result<(), WriteError> {
    if s.len() != 4 || !s.is_ascii() {
        return Err(WriteError::OutOfRange {
            type_name: type_name.to_string(),
            value: s.to_string(),
        });
    }
    for (k, c) in s.bytes().rev().enumerate() {
        bytes[k] = c;
    }
    Ok(())
}

/// Parse typed text into a value for a field, ready for [`write`].
///
/// Accepts what [`Scalar::display`] produces, so a value can be copied out of
/// the inspector, edited, and put back. Enums and bitfields accept option names
/// as well as raw numbers.
pub fn parse(layout: &Layout<'_>, field: &FieldEntry, text: &str) -> Result<Scalar, ParseError> {
    parse_as(layout.type_name_of(field), text, &layout.field_options(field))
}

#[derive(Debug, thiserror::Error, PartialEq)]
pub enum ParseError {
    #[error("{text:?} is not a valid {type_name}")]
    Invalid { type_name: String, text: String },
    #[error("{text:?} is not one of the options for this {type_name}")]
    NoSuchOption { type_name: String, text: String },
    #[error("{type_name} values cannot be set as text")]
    Unsupported { type_name: String },
}

/// [`parse`], by type name.
pub fn parse_as(type_name: &str, text: &str, options: &[&str]) -> Result<Scalar, ParseError> {
    let t = text.trim();
    let invalid = || ParseError::Invalid {
        type_name: type_name.to_string(),
        text: text.to_string(),
    };

    // `(1, 2, 3)` and `1 2 3` are both accepted for vectors.
    let parts = |s: &str| -> Vec<String> {
        s.trim_matches(|c| c == '(' || c == ')')
            .split([',', ' '])
            .filter(|p| !p.trim().is_empty())
            .map(|p| p.trim().to_string())
            .collect()
    };

    Ok(match type_name {
        "char integer" | "short integer" | "long integer" | "int64 integer" | "byte integer"
        | "word integer" | "dword integer" => {
            Scalar::Int(t.parse::<i64>().map_err(|_| invalid())?)
        }

        "char block index" | "short block index" | "long block index"
        | "custom short block index" | "custom long block index" => {
            if t.eq_ignore_ascii_case("none") {
                Scalar::BlockIndex(-1)
            } else {
                Scalar::BlockIndex(
                    t.trim_start_matches('#').parse::<i64>().map_err(|_| invalid())?,
                )
            }
        }

        "char enum" | "short enum" | "long enum" => {
            let raw = match options.iter().position(|o| o.eq_ignore_ascii_case(t)) {
                Some(k) => k as i64,
                None => t.parse::<i64>().map_err(|_| ParseError::NoSuchOption {
                    type_name: type_name.to_string(),
                    text: text.to_string(),
                })?,
            };
            let option = usize::try_from(raw)
                .ok()
                .and_then(|k| options.get(k))
                .map(|s| s.to_string());
            Scalar::Enum { raw, option }
        }

        "byte flags" | "word flags" | "long flags" | "long block flags" => {
            let raw = if let Some(hex) = t.strip_prefix("0x") {
                u64::from_str_radix(hex, 16).map_err(|_| invalid())?
            } else if t.is_empty() || t.eq_ignore_ascii_case("none") {
                0
            } else {
                let mut bits = 0u64;
                for name in t.split('|').map(str::trim).filter(|n| !n.is_empty()) {
                    let bit = options
                        .iter()
                        .position(|o| o.eq_ignore_ascii_case(name))
                        .ok_or_else(|| ParseError::NoSuchOption {
                            type_name: type_name.to_string(),
                            text: name.to_string(),
                        })?;
                    bits |= 1 << bit;
                }
                bits
            };
            let set = (0..64)
                .filter(|b| raw & (1 << b) != 0)
                .map(|b| match options.get(b) {
                    Some(n) => n.to_string(),
                    None => format!("bit {b}"),
                })
                .collect();
            Scalar::Flags { raw, set }
        }

        "real" | "real fraction" | "angle" => {
            Scalar::Real(t.parse::<f32>().map_err(|_| invalid())?)
        }
        "real bounds" | "angle bounds" | "fraction bounds" | "real point 2d"
        | "real vector 2d" | "real euler angles 2d" | "real point 3d" | "real vector 3d"
        | "real euler angles 3d" | "real rgb color" | "real plane 2d" | "real argb color"
        | "real plane 3d" | "real quaternion" => Scalar::Reals(
            parts(t)
                .iter()
                .map(|p| p.parse::<f32>().map_err(|_| invalid()))
                .collect::<Result<_, _>>()?,
        ),

        "short integer bounds" | "rectangle 2d" => Scalar::Ints(
            parts(t)
                .iter()
                .map(|p| p.parse::<i64>().map_err(|_| invalid()))
                .collect::<Result<_, _>>()?,
        ),

        "rgb color" | "argb color" => {
            let hex = t.trim_start_matches('#');
            if !matches!(hex.len(), 6 | 8) || !hex.chars().all(|c| c.is_ascii_hexdigit()) {
                return Err(invalid());
            }
            Scalar::Color(format!("#{hex}"))
        }

        // Quotes are optional, so a value pasted from the inspector works too.
        "string" | "long string" => {
            Scalar::Text(t.trim_matches('"').to_string())
        }
        "tag" => Scalar::FourCc(t.to_string()),

        other => {
            return Err(ParseError::Unsupported {
                type_name: other.to_string(),
            })
        }
    })
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
        Some(v) => Scalar::BlockIndex(v),
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
            Scalar::BlockIndex(-1)
        );
        assert_eq!(decode("short block index", &[0xFF, 0xFF], none).display(), "none");
        assert_eq!(
            decode("short block index", &[0x03, 0x00], none),
            Scalar::BlockIndex(3)
        );
        // The shipped data carries negatives other than -1; keeping the raw
        // value is what makes write-back lossless for them.
        assert_eq!(
            decode("custom short block index", &[0xFE, 0xFF], none),
            Scalar::BlockIndex(-2)
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

    /// The property that makes editing safe: decoding a field and writing the
    /// same value straight back must not disturb a single byte. Anything that
    /// fails here would corrupt untouched fields on save.
    #[test]
    fn decode_then_encode_leaves_the_bytes_alone() {
        let cases: &[(&str, &[u8])] = &[
            ("char integer", &[0xF3]),
            ("byte integer", &[0xC7]),
            ("short integer", &[0x34, 0xF2]),
            ("word integer", &[0x34, 0xF2]),
            ("long integer", &[1, 2, 3, 0x84]),
            ("dword integer", &[1, 2, 3, 0x84]),
            ("int64 integer", &[1, 2, 3, 4, 5, 6, 7, 0x81]),
            ("short block index", &[0xFF, 0xFF]),
            ("custom short block index", &[0xFE, 0xFF]),
            ("custom short block index", &[0x00, 0x80]),
            ("short block index", &[0x07, 0x00]),
            ("char block index", &[0xFF]),
            ("long block index", &[9, 0, 0, 0]),
            ("char enum", &[3]),
            ("short enum", &[2, 0]),
            ("long enum", &[4, 0, 0, 0]),
            ("byte flags", &[0b1011]),
            ("word flags", &[0x81, 0x02]),
            ("long flags", &[0x11, 0x22, 0x33, 0x44]),
            ("real", &[0xCD, 0xCC, 0x8C, 0x3F]),
            ("angle", &[0xDB, 0x0F, 0x49, 0x40]),
            ("real point 2d", &[0, 0, 0x80, 0x3F, 0, 0, 0, 0x40]),
            ("real vector 3d", &[0, 0, 0x80, 0x3F, 0, 0, 0, 0x40, 0, 0, 0x40, 0x40]),
            (
                "real quaternion",
                &[0, 0, 0x80, 0x3F, 0, 0, 0, 0x40, 0, 0, 0x40, 0x40, 0, 0, 0x80, 0x40],
            ),
            ("short integer bounds", &[0x01, 0x00, 0xFF, 0xFF]),
            ("rectangle 2d", &[1, 0, 2, 0, 3, 0, 4, 0]),
            ("argb color", &[0x33, 0x22, 0x11, 0xFF]),
            ("tag", b"paew"),
        ];

        for (type_name, original) in cases {
            let decoded = decode(type_name, original, none);
            let mut buf = original.to_vec();
            encode(type_name, &decoded, &mut buf)
                .unwrap_or_else(|e| panic!("{type_name}: {e}"));
            assert_eq!(&buf, original, "{type_name} changed on write-back");
        }
    }

    #[test]
    fn a_rgb_color_leaves_the_alpha_byte_alone() {
        // `#rrggbb` says nothing about alpha, so it must not clear it.
        let mut buf = [0x33, 0x22, 0x11, 0xAB];
        encode("rgb color", &Scalar::Color("#445566".into()), &mut buf).unwrap();
        assert_eq!(buf, [0x66, 0x55, 0x44, 0xAB]);
    }

    #[test]
    fn a_value_that_does_not_fit_is_refused_not_truncated() {
        let mut buf = [0u8; 1];
        let err = encode("char integer", &Scalar::Int(200), &mut buf).unwrap_err();
        assert!(matches!(err, WriteError::OutOfRange { .. }), "{err}");
        // Nothing was written.
        assert_eq!(buf, [0]);

        let mut buf = [0u8; 1];
        assert!(encode("byte integer", &Scalar::Int(-1), &mut buf).is_err());
        assert!(encode("byte integer", &Scalar::Int(255), &mut buf).is_ok());
    }

    #[test]
    fn a_wrong_kind_or_arity_is_refused() {
        let mut buf = [0u8; 12];
        assert!(matches!(
            encode("real vector 3d", &Scalar::Reals(vec![1.0, 2.0]), &mut buf),
            Err(WriteError::WrongArity { want: 3, got: 2, .. })
        ));
        assert!(matches!(
            encode("long integer", &Scalar::Text("no".into()), &mut buf),
            Err(WriteError::WrongKind { .. })
        ));
    }

    #[test]
    fn section_backed_types_are_not_editable_in_place() {
        let mut buf = [0u8; 16];
        for t in ["string id", "data", "tag reference", "block", "struct"] {
            assert!(
                matches!(
                    encode(t, &Scalar::Text("x".into()), &mut buf),
                    Err(WriteError::NotEditable { .. })
                ),
                "{t} should not be editable in place"
            );
        }
    }

    #[test]
    fn a_string_longer_than_its_field_is_refused() {
        // A `string` field is 32 bytes, so 31 characters plus a terminator fit.
        let mut buf = [0xAAu8; 32];
        assert!(encode("string", &Scalar::Text("a".repeat(31)), &mut buf).is_ok());
        assert_eq!(buf[31], 0, "the field must still be terminated");
        assert!(encode("string", &Scalar::Text("a".repeat(32)), &mut buf).is_err());
    }

    #[test]
    fn a_shorter_string_terminates_without_rewriting_the_tail() {
        let mut buf = [0u8; 32];
        encode("string", &Scalar::Text("assault_rifle".into()), &mut buf).unwrap();
        encode("string", &Scalar::Text("smg".into()), &mut buf).unwrap();
        // What a reader sees is the new value...
        assert_eq!(decode("string", &buf, none), Scalar::Text("smg".into()));
        assert_eq!(buf[3], 0, "must be terminated");
        // ...and the tail is left as it was, which is what makes writing a
        // decoded value straight back a true identity.
        assert_eq!(&buf[4..13], b"ult_rifle");
    }

    #[test]
    fn a_short_field_is_refused_before_anything_is_written() {
        let mut buf = [0u8; 2];
        assert!(matches!(
            encode("long integer", &Scalar::Int(1), &mut buf),
            Err(WriteError::Short { want: 4, got: 2, .. })
        ));
        assert_eq!(buf, [0, 0]);
    }

    #[test]
    fn reals_print_without_trailing_noise() {
        assert_eq!(format_real(0.0), "0");
        assert_eq!(format_real(-0.0), "0");
        assert_eq!(format_real(1.5), "1.5");
        assert_eq!(format_real(2.0), "2");
    }
}

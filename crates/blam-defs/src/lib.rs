//! Blam tag definition model.
//!
//! Halo Campaign Evolved ships self-describing tag files: each carries a `blay`
//! layout section with field names, type names, and enum/bitfield option names.
//! See `docs/tag_body_format.md`. This crate is the shared vocabulary that the
//! extractor writes and the reader and editor consume; it deliberately holds no
//! parsing logic of its own.
//!
//! Unrecognised type codes are preserved rather than dropped, so a partially
//! understood group still renders as raw bytes instead of disappearing.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("io error: {0}")]
    Io(#[from] std::io::Error),
    #[error("json error: {0}")]
    Json(#[from] serde_json::Error),
}

/// A four-character group code such as `weap`, stored in reading order.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
pub struct FourCc(pub [u8; 4]);

impl FourCc {
    /// Decode from the little-endian dword the tag header stores.
    pub fn from_le_u32(v: u32) -> Self {
        let b = v.to_le_bytes();
        FourCc([b[3], b[2], b[1], b[0]])
    }

    pub fn as_str(&self) -> String {
        self.0
            .iter()
            .map(|b| {
                if (32..127).contains(b) {
                    *b as char
                } else {
                    '.'
                }
            })
            .collect()
    }
}

impl std::fmt::Display for FourCc {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.as_str())
    }
}

/// Semantic field kind.
///
/// The mapping from the on-disk `type_code` to these variants is still being
/// established against the round-trip oracle, so `Unknown` is a first-class
/// outcome and carries the raw code for display.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum FieldKind {
    Int8,
    Int16,
    Int32,
    UInt8,
    UInt16,
    UInt32,
    Float,
    Angle,
    Fraction,
    Real,
    String32,
    StringId,
    Point2D,
    Point3D,
    Vector2D,
    Vector3D,
    Quaternion,
    Euler2D,
    Euler3D,
    Plane2D,
    Plane3D,
    RgbColor,
    ArgbColor,
    Rectangle2D,
    Bounds {
        of: Box<FieldKind>,
    },
    /// Named constants; `options` are in declaration order.
    Enum {
        width: u8,
        options: Vec<String>,
    },
    /// Named bits; `bits` are in bit order from least significant.
    Bitfield {
        width: u8,
        bits: Vec<String>,
    },
    /// Reference to another tag, optionally restricted to certain groups.
    TagReference {
        groups: Vec<FourCc>,
    },
    /// Inline nested struct.
    Struct {
        type_name: String,
    },
    /// Variable-length array of a nested struct (a classic `tag_block`).
    Block {
        type_name: String,
        max_count: Option<u32>,
    },
    /// Variable-length untyped payload (a classic `tag_data`).
    Data,
    /// Explicit padding, never shown to the user.
    Pad {
        size: u32,
    },
    /// Recognised as a field but its type code is not yet mapped.
    Unknown {
        type_code: u32,
        aux: u32,
    },
}

impl FieldKind {
    /// Fixed on-disk size in bytes, when known.
    pub fn fixed_size(&self) -> Option<u32> {
        use FieldKind::*;
        Some(match self {
            Int8 | UInt8 => 1,
            Int16 | UInt16 => 2,
            Int32 | UInt32 | Float | Angle | Fraction | Real | StringId => 4,
            Point2D | Vector2D | Euler2D => 8,
            Point3D | Vector3D | Euler3D | RgbColor => 12,
            Quaternion | Plane3D | ArgbColor | Rectangle2D => 16,
            Plane2D => 12,
            String32 => 32,
            Enum { width, .. } | Bitfield { width, .. } => *width as u32,
            Bounds { of } => of.fixed_size()? * 2,
            Pad { size } => *size,
            _ => return None,
        })
    }

    /// Whether the editor should render this as an interactive control.
    pub fn is_editable(&self) -> bool {
        !matches!(self, FieldKind::Pad { .. } | FieldKind::Unknown { .. })
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct FieldDef {
    /// Human-readable name exactly as shipped in the tag's string blob.
    pub name: String,
    pub kind: FieldKind,
    /// Byte offset from the start of the containing struct, once resolved.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub offset: Option<u32>,
    /// Raw on-disk type code, retained for diagnostics and round-tripping.
    pub type_code: u32,
    /// Raw auxiliary word, meaning discriminated by `type_code`.
    #[serde(default, skip_serializing_if = "is_zero")]
    pub aux: u32,
}

fn is_zero(v: &u32) -> bool {
    *v == 0
}

#[derive(Debug, Clone, PartialEq, Default, Serialize, Deserialize)]
pub struct StructDef {
    pub name: String,
    pub fields: Vec<FieldDef>,
    /// Total size in bytes when every field is resolved.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub size: Option<u32>,
}

impl StructDef {
    /// Assign running byte offsets and compute the total size. Returns `None`
    /// if any field has an unknown size, leaving offsets unset.
    pub fn resolve(&mut self) -> Option<u32> {
        let mut offset = 0u32;
        for field in &mut self.fields {
            let size = field.kind.fixed_size()?;
            field.offset = Some(offset);
            offset += size;
        }
        self.size = Some(offset);
        Some(offset)
    }
}

/// The complete definition for one tag group.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct TagGroupDef {
    pub group: FourCc,
    /// Directory name the group ships under, e.g. `weapon`.
    pub name: String,
    /// Per-group definition version from container header `0x34`.
    pub group_version: u32,
    /// The root struct, plus any nested structs it references by name.
    pub root: StructDef,
    #[serde(default)]
    pub structs: BTreeMap<String, StructDef>,
    /// Fields whose type code is not yet mapped, for coverage reporting.
    #[serde(default)]
    pub unmapped_type_codes: BTreeMap<u32, u32>,
}

impl TagGroupDef {
    /// Fraction of fields with a mapped type, in `0.0..=1.0`.
    pub fn coverage(&self) -> f32 {
        let all: Vec<&FieldDef> = std::iter::once(&self.root)
            .chain(self.structs.values())
            .flat_map(|s| s.fields.iter())
            .collect();
        if all.is_empty() {
            return 1.0;
        }
        let known = all
            .iter()
            .filter(|f| !matches!(f.kind, FieldKind::Unknown { .. }))
            .count();
        known as f32 / all.len() as f32
    }
}

/// A corpus of group definitions, keyed by group code.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct DefCorpus {
    pub generator: String,
    pub groups: BTreeMap<String, TagGroupDef>,
}

impl DefCorpus {
    pub fn load(path: impl AsRef<std::path::Path>) -> Result<Self, Error> {
        let text = std::fs::read_to_string(path)?;
        Ok(serde_json::from_str(&text)?)
    }

    pub fn save(&self, path: impl AsRef<std::path::Path>) -> Result<(), Error> {
        if let Some(parent) = path.as_ref().parent() {
            std::fs::create_dir_all(parent)?;
        }
        std::fs::write(path, serde_json::to_string_pretty(self)?)?;
        Ok(())
    }

    pub fn get(&self, group: FourCc) -> Option<&TagGroupDef> {
        self.groups.get(&group.as_str())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fourcc_decodes_little_endian_header_dword() {
        // `weap` is stored on disk as the bytes `p a e w`, i.e. LE 0x77656170.
        assert_eq!(FourCc::from_le_u32(0x7765_6170).as_str(), "weap");
    }

    #[test]
    fn struct_resolve_assigns_running_offsets() {
        let mut s = StructDef {
            name: "t".into(),
            fields: vec![
                FieldDef {
                    name: "a".into(),
                    kind: FieldKind::Int16,
                    offset: None,
                    type_code: 4,
                    aux: 0,
                },
                FieldDef {
                    name: "b".into(),
                    kind: FieldKind::Float,
                    offset: None,
                    type_code: 9,
                    aux: 0,
                },
            ],
            size: None,
        };
        assert_eq!(s.resolve(), Some(6));
        assert_eq!(s.fields[0].offset, Some(0));
        assert_eq!(s.fields[1].offset, Some(2));
    }

    #[test]
    fn resolve_bails_on_unknown_field_size() {
        let mut s = StructDef {
            name: "t".into(),
            fields: vec![FieldDef {
                name: "a".into(),
                kind: FieldKind::Unknown {
                    type_code: 99,
                    aux: 0,
                },
                offset: None,
                type_code: 99,
                aux: 0,
            }],
            size: None,
        };
        assert_eq!(s.resolve(), None);
    }
}

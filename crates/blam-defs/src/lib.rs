//! Serializable Blam tag definition model.
//!
//! Halo Campaign Evolved ships self-describing tag files: each carries its own
//! field names, type names, and enum option names. See `docs/tag_body_format.md`.
//! This crate is the shared vocabulary that the extractor writes and the reader,
//! editor, and public reference consume. It holds no parsing logic.
//!
//! What this models is **schema**, not content: field names, types, offsets, and
//! option names. Actual tag values are game content and are never written here.

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
            .map(|b| if (32..127).contains(b) { *b as char } else { '.' })
            .collect()
    }
}

impl std::fmt::Display for FourCc {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.as_str())
    }
}

/// A single field within a struct.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct FieldDef {
    /// Field name exactly as shipped. Empty for padding and terminators.
    pub name: String,
    /// Type name exactly as shipped, e.g. `real vector 3d`.
    #[serde(rename = "type")]
    pub type_name: String,
    /// Byte offset within the containing struct, when every preceding field
    /// has a known size.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub offset: Option<u32>,
    /// On-disk width in bytes.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub size: Option<u32>,
    /// Named constants for enum and bitfield types, in declaration order.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub options: Vec<String>,
    /// For `block` fields, the block's name and element limit.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub block: Option<BlockRef>,
    /// For `struct` and `array` fields, the index of the referenced struct.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub struct_index: Option<usize>,
    /// For `array` fields, the number of repetitions.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub array_count: Option<u32>,
}

impl FieldDef {
    /// Fields the editor should render as interactive controls. Padding and
    /// terminators are structural and carry no user-visible value.
    pub fn is_visible(&self) -> bool {
        !matches!(self.type_name.as_str(), "pad" | "terminator X" | "custom")
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct BlockRef {
    pub name: String,
    /// Element limit Guerilla enforced.
    pub max_count: u32,
}

/// A struct definition: a named, ordered run of fields.
#[derive(Debug, Clone, PartialEq, Default, Serialize, Deserialize)]
pub struct StructDef {
    pub name: String,
    /// Definition GUID from the shipped struct table.
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub guid: String,
    /// Total on-disk size, when every field resolves.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub size: Option<u32>,
    pub fields: Vec<FieldDef>,
}

impl StructDef {
    /// Fields worth showing in a reference or an editor.
    pub fn visible_fields(&self) -> impl Iterator<Item = &FieldDef> {
        self.fields.iter().filter(|f| f.is_visible())
    }
}

/// The complete definition for one tag group.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct TagGroupDef {
    /// Four-character group code, e.g. `weap`.
    pub group: String,
    /// Directory name the group ships under, e.g. `weapon`.
    pub name: String,
    /// Per-group definition version from the container header.
    pub version: u32,
    /// Number of tags of this group in the shipped build.
    pub tag_count: usize,
    /// Struct definitions, root first.
    pub structs: Vec<StructDef>,
}

impl TagGroupDef {
    pub fn root(&self) -> Option<&StructDef> {
        self.structs.first()
    }

    /// Total field count across every struct.
    pub fn field_count(&self) -> usize {
        self.structs.iter().map(|s| s.fields.len()).sum()
    }

    /// Field count excluding padding and terminators.
    pub fn visible_field_count(&self) -> usize {
        self.structs
            .iter()
            .map(|s| s.visible_fields().count())
            .sum()
    }

    /// Fraction of fields whose size resolved, in `0.0..=1.0`.
    pub fn coverage(&self) -> f32 {
        let all: usize = self.structs.iter().map(|s| s.fields.len()).sum();
        if all == 0 {
            return 1.0;
        }
        let known: usize = self
            .structs
            .iter()
            .map(|s| s.fields.iter().filter(|f| f.size.is_some()).count())
            .sum();
        known as f32 / all as f32
    }
}

/// A corpus of group definitions, keyed by directory name.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct DefCorpus {
    /// Tool and build that produced this corpus.
    pub generator: String,
    /// Game build fingerprint the definitions were extracted from.
    #[serde(default)]
    pub build: String,
    pub groups: BTreeMap<String, TagGroupDef>,
}

impl DefCorpus {
    pub fn load(path: impl AsRef<std::path::Path>) -> Result<Self, Error> {
        Ok(serde_json::from_str(&std::fs::read_to_string(path)?)?)
    }

    pub fn save(&self, path: impl AsRef<std::path::Path>) -> Result<(), Error> {
        if let Some(parent) = path.as_ref().parent() {
            std::fs::create_dir_all(parent)?;
        }
        std::fs::write(path, serde_json::to_string_pretty(self)?)?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn field(name: &str, type_name: &str, size: Option<u32>) -> FieldDef {
        FieldDef {
            name: name.into(),
            type_name: type_name.into(),
            offset: None,
            size,
            options: Vec::new(),
            block: None,
            struct_index: None,
            array_count: None,
        }
    }

    #[test]
    fn fourcc_decodes_little_endian_header_dword() {
        // `weap` is stored on disk as the bytes `p a e w`, i.e. LE 0x77656170.
        assert_eq!(FourCc::from_le_u32(0x7765_6170).as_str(), "weap");
    }

    #[test]
    fn padding_and_terminators_are_not_visible() {
        assert!(field("position", "real vector 3d", Some(12)).is_visible());
        assert!(!field("", "pad", Some(3)).is_visible());
        assert!(!field("", "terminator X", Some(0)).is_visible());
        assert!(!field("", "custom", Some(0)).is_visible());
    }

    #[test]
    fn coverage_counts_fields_with_a_known_size() {
        let g = TagGroupDef {
            group: "trak".into(),
            name: "camera_track".into(),
            version: 2,
            tag_count: 23,
            structs: vec![StructDef {
                name: "root".into(),
                guid: String::new(),
                size: Some(28),
                fields: vec![
                    field("position", "real vector 3d", Some(12)),
                    field("orientation", "real quaternion", Some(16)),
                    field("mystery", "array", None),
                ],
            }],
        };
        assert_eq!(g.field_count(), 3);
        assert_eq!(g.visible_field_count(), 3);
        assert!((g.coverage() - 2.0 / 3.0).abs() < 1e-6);
    }

    #[test]
    fn corpus_round_trips_through_json() {
        let mut corpus = DefCorpus {
            generator: "test".into(),
            build: "abc".into(),
            groups: BTreeMap::new(),
        };
        corpus.groups.insert(
            "camera_track".into(),
            TagGroupDef {
                group: "trak".into(),
                name: "camera_track".into(),
                version: 2,
                tag_count: 23,
                structs: vec![StructDef {
                    name: "root".into(),
                    guid: "abcd".into(),
                    size: Some(12),
                    fields: vec![field("control points", "block", Some(12))],
                }],
            },
        );

        let json = serde_json::to_string(&corpus).unwrap();
        let back: DefCorpus = serde_json::from_str(&json).unwrap();
        assert_eq!(back.groups["camera_track"].structs[0].fields[0].name, "control points");
        assert_eq!(back.build, "abc");
    }
}

//! Unversioned property blocks, decoded losslessly and **encoded** again.
//!
//! [`crate::unversioned`] walks a block to pull values out; this module keeps
//! every byte's meaning so the block can be rebuilt — the mirror image
//! `UObject::Serialize` reads. It covers the value kinds the tag wrappers use
//! (measured over all shipped tag wrappers by `mjolnir zen-roundtrip`): object
//! references, bools, integers, names, arrays, maps, soft object paths and
//! reflected structs. Native-serialized structs (`FVector` and friends) are
//! refused rather than guessed; nothing under `/Game/Tags` needs them.
//!
//! A tag export body is
//!
//! ```text
//! 00 00 00 00        two empty fragments the tag cooker writes and the loader skips
//! fragments          the block header: skip / value-count runs, the last flagged
//! values             present values in slot order
//! 00 00 00 00        UObject::Serialize's "has guid" bool
//! ```
//!
//! Absent properties are simply skipped; the zero mask (a value present but
//! all zeros) is not used by any tag export, so decoding one is an error here.

use crate::usmap::{PropType, Usmap};

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("property data ends early at {0:#x}")]
    Eof(usize),
    #[error("no usmap schema for {0:?}")]
    NoSchema(String),
    #[error("{class}: no property at unversioned slot {slot}")]
    NoSlot { class: String, slot: u16 },
    #[error("{class}.{prop}: {ty:?} is not a kind this encoder models")]
    Unsupported {
        class: String,
        prop: String,
        ty: PropType,
    },
    #[error("{class}: the header carries a zero mask, which no tag export uses")]
    ZeroMask { class: String },
    #[error("{class}: a fragment runs past the {total} slots of the schema")]
    Overrun { class: String, total: u16 },
    #[error("a tag export body must start with four zero bytes and end with four zero bytes")]
    Frame,
    #[error("{0} trailing byte(s) after the property block")]
    Trailing(usize),
}

/// An `FMappedName` as stored: an index into the package name map and an
/// FName number (0 = none, n = `_{n-1}`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct Name {
    pub index: u32,
    pub number: u32,
}

/// One property value, byte for byte.
#[derive(Debug, Clone, PartialEq)]
pub enum Val {
    Bool(bool),
    Byte(u8),
    Int(i32),
    UInt32(u32),
    Name(Name),
    /// An `FPackageIndex`: `<0` import `-n-1`, `>0` export `n-1`, `0` null.
    Object(i32),
    /// `FSoftObjectPath`: top-level asset path (two names) plus a sub-path.
    SoftObject {
        package: Name,
        asset: Name,
        sub: String,
    },
    Array(Vec<Val>),
    /// Key/value pairs; the "removed" prefix is always empty in a cook.
    Map(Vec<(Val, Val)>),
    /// A reflected struct: another unversioned block, with no guid guard.
    Struct(Block),
}

/// The present properties of one object or struct, by flat schema slot.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct Block {
    /// `(slot, value)` in ascending slot order.
    pub values: Vec<(u16, Val)>,
}

impl Block {
    pub fn get(&self, slot: u16) -> Option<&Val> {
        self.values.iter().find(|(s, _)| *s == slot).map(|(_, v)| v)
    }

    /// Set or replace a slot's value, keeping slot order.
    pub fn set(&mut self, slot: u16, value: Val) {
        match self.values.binary_search_by_key(&slot, |(s, _)| *s) {
            Ok(i) => self.values[i].1 = value,
            Err(i) => self.values.insert(i, (slot, value)),
        }
    }

    /// Every object reference in the block, depth first, in serialization
    /// order — the order the dependency bundle lists them in.
    pub fn object_refs(&self) -> Vec<i32> {
        fn walk(v: &Val, out: &mut Vec<i32>) {
            match v {
                Val::Object(i) => out.push(*i),
                Val::Array(items) => items.iter().for_each(|i| walk(i, out)),
                Val::Map(pairs) => pairs.iter().for_each(|(k, v)| {
                    walk(k, out);
                    walk(v, out);
                }),
                Val::Struct(b) => b.values.iter().for_each(|(_, v)| walk(v, out)),
                _ => {}
            }
        }
        let mut out = Vec::new();
        self.values.iter().for_each(|(_, v)| walk(v, &mut out));
        out
    }

    /// Every name in the block, depth first.
    pub fn names(&self) -> Vec<Name> {
        fn walk(v: &Val, out: &mut Vec<Name>) {
            match v {
                Val::Name(n) => out.push(*n),
                Val::SoftObject { package, asset, .. } => {
                    out.push(*package);
                    out.push(*asset);
                }
                Val::Array(items) => items.iter().for_each(|i| walk(i, out)),
                Val::Map(pairs) => pairs.iter().for_each(|(k, v)| {
                    walk(k, out);
                    walk(v, out);
                }),
                Val::Struct(b) => b.values.iter().for_each(|(_, v)| walk(v, out)),
                _ => {}
            }
        }
        let mut out = Vec::new();
        self.values.iter().for_each(|(_, v)| walk(v, &mut out));
        out
    }
}

struct Cursor<'a> {
    b: &'a [u8],
    at: usize,
}

impl<'a> Cursor<'a> {
    fn bytes(&mut self, n: usize) -> Result<&'a [u8], Error> {
        let s = self
            .b
            .get(self.at..self.at + n)
            .ok_or(Error::Eof(self.at))?;
        self.at += n;
        Ok(s)
    }
    fn u8(&mut self) -> Result<u8, Error> {
        Ok(self.bytes(1)?[0])
    }
    fn u16(&mut self) -> Result<u16, Error> {
        Ok(u16::from_le_bytes(self.bytes(2)?.try_into().unwrap()))
    }
    fn u32(&mut self) -> Result<u32, Error> {
        Ok(u32::from_le_bytes(self.bytes(4)?.try_into().unwrap()))
    }
    fn name(&mut self) -> Result<Name, Error> {
        Ok(Name {
            index: self.u32()?,
            number: self.u32()?,
        })
    }
    fn fstring(&mut self) -> Result<String, Error> {
        let len = self.u32()? as i32;
        if len == 0 {
            return Ok(String::new());
        }
        if len < 0 {
            let raw = self.bytes((-len) as usize * 2)?;
            let units: Vec<u16> = raw
                .chunks_exact(2)
                .map(|c| u16::from_le_bytes([c[0], c[1]]))
                .collect();
            Ok(String::from_utf16_lossy(&units)
                .trim_end_matches('\0')
                .to_string())
        } else {
            let raw = self.bytes(len as usize)?;
            Ok(String::from_utf8_lossy(raw)
                .trim_end_matches('\0')
                .to_string())
        }
    }
}

fn put_fstring(out: &mut Vec<u8>, s: &str) {
    if s.is_empty() {
        out.extend_from_slice(&0u32.to_le_bytes());
    } else if s.is_ascii() {
        out.extend_from_slice(&((s.len() + 1) as u32).to_le_bytes());
        out.extend_from_slice(s.as_bytes());
        out.push(0);
    } else {
        let units: Vec<u16> = s.encode_utf16().chain(std::iter::once(0)).collect();
        out.extend_from_slice(&(-(units.len() as i32)).to_le_bytes());
        for u in units {
            out.extend_from_slice(&u.to_le_bytes());
        }
    }
}

fn put_name(out: &mut Vec<u8>, n: Name) {
    out.extend_from_slice(&n.index.to_le_bytes());
    out.extend_from_slice(&n.number.to_le_bytes());
}

/// Decode one unversioned block against `class`'s flattened schema.
pub fn decode(usmap: &Usmap, class: &str, data: &[u8]) -> Result<Block, Error> {
    let mut c = Cursor { b: data, at: 0 };
    let block = decode_block(usmap, class, &mut c)?;
    if c.at != data.len() {
        return Err(Error::Trailing(data.len() - c.at));
    }
    Ok(block)
}

fn decode_block(usmap: &Usmap, class: &str, c: &mut Cursor<'_>) -> Result<Block, Error> {
    if !usmap.structs.contains_key(class) {
        return Err(Error::NoSchema(class.to_string()));
    }
    let total = usmap.total_slots(class);
    // Header: (skip:7, has_zeroes:1, is_last:1, value_count:7+) fragments.
    let mut runs: Vec<(u16, u16)> = Vec::new();
    loop {
        let packed = c.u16()?;
        if packed & 0x80 != 0 {
            return Err(Error::ZeroMask {
                class: class.to_string(),
            });
        }
        runs.push((packed & 0x7F, packed >> 9));
        if packed & 0x100 != 0 {
            break;
        }
    }
    let mut block = Block::default();
    let mut slot = 0u16;
    for (skip, values) in runs {
        slot += skip;
        for _ in 0..values {
            if slot >= total {
                return Err(Error::Overrun {
                    class: class.to_string(),
                    total,
                });
            }
            let (_, prop) = usmap.resolve(class, slot).ok_or_else(|| Error::NoSlot {
                class: class.to_string(),
                slot,
            })?;
            let value = decode_value(usmap, class, &prop.name, &prop.ty, c)?;
            block.values.push((slot, value));
            slot += 1;
        }
    }
    Ok(block)
}

fn decode_value(
    usmap: &Usmap,
    class: &str,
    prop: &str,
    ty: &PropType,
    c: &mut Cursor<'_>,
) -> Result<Val, Error> {
    use PropType as T;
    Ok(match ty {
        T::Bool => Val::Bool(c.u8()? != 0),
        T::Byte => Val::Byte(c.u8()?),
        T::Int => Val::Int(c.u32()? as i32),
        T::UInt32 => Val::UInt32(c.u32()?),
        T::Name => Val::Name(c.name()?),
        T::Object | T::Interface => Val::Object(c.u32()? as i32),
        T::SoftObject | T::AssetObject => Val::SoftObject {
            package: c.name()?,
            asset: c.name()?,
            sub: c.fstring()?,
        },
        T::Array(inner) => {
            let count = c.u32()? as usize;
            if count > 0x0100_0000 {
                return Err(Error::Eof(c.at));
            }
            let mut items = Vec::with_capacity(count);
            for _ in 0..count {
                items.push(decode_value(usmap, class, prop, inner, c)?);
            }
            Val::Array(items)
        }
        T::Map(key, value) => {
            let removed = c.u32()?;
            if removed != 0 {
                return Err(Error::Unsupported {
                    class: class.to_string(),
                    prop: prop.to_string(),
                    ty: ty.clone(),
                });
            }
            let count = c.u32()? as usize;
            let mut pairs = Vec::with_capacity(count);
            for _ in 0..count {
                let k = decode_value(usmap, class, prop, key, c)?;
                let v = decode_value(usmap, class, prop, value, c)?;
                pairs.push((k, v));
            }
            Val::Map(pairs)
        }
        T::Struct(name) => match name.as_str() {
            "SoftObjectPath" | "SoftClassPath" => Val::SoftObject {
                package: c.name()?,
                asset: c.name()?,
                sub: c.fstring()?,
            },
            _ if usmap.structs.contains_key(name) && !NATIVE_STRUCTS.contains(&name.as_str()) => {
                Val::Struct(decode_block(usmap, name, c)?)
            }
            _ => {
                return Err(Error::Unsupported {
                    class: class.to_string(),
                    prop: prop.to_string(),
                    ty: ty.clone(),
                })
            }
        },
        other => {
            return Err(Error::Unsupported {
                class: class.to_string(),
                prop: prop.to_string(),
                ty: other.clone(),
            })
        }
    })
}

/// Structs the engine serializes natively rather than as reflected blocks.
/// Nothing in a tag wrapper uses one; listed so they are refused by name.
const NATIVE_STRUCTS: &[&str] = &[
    "Vector",
    "Rotator",
    "Vector3f",
    "Vector2D",
    "Vector2f",
    "Vector4",
    "Quat",
    "Plane",
    "Vector4f",
    "Quat4f",
    "Color",
    "LinearColor",
    "IntPoint",
    "IntVector",
    "IntVector4",
    "Guid",
    "FrameNumber",
    "PerPlatformFloat",
    "PerPlatformInt",
    "PerPlatformBool",
    "DateTime",
    "Timespan",
    "TopLevelAssetPath",
];

impl Block {
    /// Encode against `class`'s schema: the fragment header, then the values.
    pub fn encode(&self, usmap: &Usmap, class: &str) -> Result<Vec<u8>, Error> {
        let total = usmap.total_slots(class);
        if !usmap.structs.contains_key(class) {
            return Err(Error::NoSchema(class.to_string()));
        }
        // Header. Absent slots accumulate as a skip; a present slot after a
        // skip starts a fragment, consecutive present slots extend it (127 at
        // most), and the next absent slot closes it. Trailing absent slots need
        // no fragment — unless nothing was present at all, when a single
        // all-skip fragment says so. The last fragment carries the flag.
        let mut fragments: Vec<u16> = Vec::new();
        let mut skip = 0u16;
        let mut values = 0u16;
        for slot in 0..total {
            let present = self.values.iter().any(|(s, _)| *s == slot);
            if present {
                if values == 127 {
                    fragments.push(skip | (values << 9));
                    skip = 0;
                    values = 0;
                }
                values += 1;
            } else {
                if values > 0 {
                    fragments.push(skip | (values << 9));
                    skip = 0;
                    values = 0;
                }
                skip += 1;
                if skip == 127 {
                    fragments.push(skip);
                    skip = 0;
                }
            }
        }
        if values > 0 || fragments.is_empty() {
            fragments.push(skip | (values << 9));
        }
        if let Some(last) = fragments.last_mut() {
            *last |= 0x100;
        }
        let mut out = Vec::new();
        for f in fragments {
            out.extend_from_slice(&f.to_le_bytes());
        }
        for (slot, value) in &self.values {
            if *slot >= total {
                return Err(Error::Overrun {
                    class: class.to_string(),
                    total,
                });
            }
            let (_, prop) = usmap.resolve(class, *slot).ok_or_else(|| Error::NoSlot {
                class: class.to_string(),
                slot: *slot,
            })?;
            encode_value(usmap, class, &prop.name, &prop.ty, value, &mut out)?;
        }
        Ok(out)
    }
}

fn encode_value(
    usmap: &Usmap,
    class: &str,
    prop: &str,
    ty: &PropType,
    value: &Val,
    out: &mut Vec<u8>,
) -> Result<(), Error> {
    use PropType as T;
    let mismatch = || Error::Unsupported {
        class: class.to_string(),
        prop: prop.to_string(),
        ty: ty.clone(),
    };
    match (ty, value) {
        (T::Bool, Val::Bool(b)) => out.push(*b as u8),
        (T::Byte, Val::Byte(b)) => out.push(*b),
        (T::Int, Val::Int(i)) => out.extend_from_slice(&i.to_le_bytes()),
        (T::UInt32, Val::UInt32(i)) => out.extend_from_slice(&i.to_le_bytes()),
        (T::Name, Val::Name(n)) => put_name(out, *n),
        (T::Object | T::Interface, Val::Object(i)) => out.extend_from_slice(&i.to_le_bytes()),
        (
            T::SoftObject | T::AssetObject,
            Val::SoftObject {
                package,
                asset,
                sub,
            },
        )
        | (
            T::Struct(_),
            Val::SoftObject {
                package,
                asset,
                sub,
            },
        ) => {
            put_name(out, *package);
            put_name(out, *asset);
            put_fstring(out, sub);
        }
        (T::Array(inner), Val::Array(items)) => {
            out.extend_from_slice(&(items.len() as u32).to_le_bytes());
            for item in items {
                encode_value(usmap, class, prop, inner, item, out)?;
            }
        }
        (T::Map(key, val), Val::Map(pairs)) => {
            out.extend_from_slice(&0u32.to_le_bytes());
            out.extend_from_slice(&(pairs.len() as u32).to_le_bytes());
            for (k, v) in pairs {
                encode_value(usmap, class, prop, key, k, out)?;
                encode_value(usmap, class, prop, val, v, out)?;
            }
        }
        (T::Struct(name), Val::Struct(block)) => {
            out.extend_from_slice(&block.encode(usmap, name)?);
        }
        _ => return Err(mismatch()),
    }
    Ok(())
}

/// Decode a tag wrapper's export body: the two empty fragments, the block,
/// and the guid guard.
pub fn decode_tag_body(usmap: &Usmap, class: &str, body: &[u8]) -> Result<Block, Error> {
    if body.len() < 8 || body[..4] != [0; 4] || body[body.len() - 4..] != [0; 4] {
        return Err(Error::Frame);
    }
    decode(usmap, class, &body[4..body.len() - 4])
}

/// Encode a tag wrapper's export body.
pub fn encode_tag_body(usmap: &Usmap, class: &str, block: &Block) -> Result<Vec<u8>, Error> {
    let mut out = vec![0u8; 4];
    out.extend_from_slice(&block.encode(usmap, class)?);
    out.extend_from_slice(&[0; 4]);
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::usmap::{Prop, Schema};
    use std::collections::HashMap;

    /// A hand-made usmap with the wrapper classes' shapes.
    fn usmap() -> Usmap {
        let mut structs = HashMap::new();
        let prop = |i: u16, name: &str, ty: PropType| Prop {
            schema_index: i,
            array_dim: 1,
            name: name.into(),
            ty,
        };
        structs.insert(
            "Object".into(),
            Schema {
                name: "Object".into(),
                super_name: None,
                prop_count: 0,
                props: vec![],
            },
        );
        structs.insert(
            "DataAsset".into(),
            Schema {
                name: "DataAsset".into(),
                super_name: Some("Object".into()),
                prop_count: 1,
                props: vec![prop(0, "NativeClass", PropType::Object)],
            },
        );
        structs.insert(
            "BlamTagDataAssetBase".into(),
            Schema {
                name: "BlamTagDataAssetBase".into(),
                super_name: Some("DataAsset".into()),
                prop_count: 2,
                props: vec![
                    prop(
                        0,
                        "CookedAssetsReferencedByTag",
                        PropType::Array(Box::new(PropType::Object)),
                    ),
                    prop(1, "BinaryBlobSize", PropType::UInt32),
                ],
            },
        );
        structs.insert(
            "BlamBaseEffectTagDataAsset".into(),
            Schema {
                name: "BlamBaseEffectTagDataAsset".into(),
                super_name: Some("BlamTagDataAssetBase".into()),
                prop_count: 3,
                props: vec![
                    prop(0, "AssetReference", PropType::Object),
                    prop(1, "bSpawnPerInstance", PropType::Bool),
                    prop(2, "DefaultAssetReference", PropType::Object),
                ],
            },
        );
        structs.insert(
            "BlamVariant".into(),
            Schema {
                name: "BlamVariant".into(),
                super_name: None,
                prop_count: 2,
                props: vec![
                    prop(0, "VariantName", PropType::Name),
                    prop(
                        1,
                        "Permutations",
                        PropType::Map(Box::new(PropType::Name), Box::new(PropType::Name)),
                    ),
                ],
            },
        );
        structs.insert(
            "BlamModelTagDataAsset".into(),
            Schema {
                name: "BlamModelTagDataAsset".into(),
                super_name: Some("BlamTagDataAssetBase".into()),
                prop_count: 6,
                props: vec![
                    prop(0, "ModelRegionStringTable", PropType::Object),
                    prop(1, "RegionTable", PropType::Array(Box::new(PropType::Name))),
                    prop(
                        2,
                        "Permutations_EMPTY",
                        PropType::Array(Box::new(PropType::Name)),
                    ),
                    prop(
                        3,
                        "Variants",
                        PropType::Array(Box::new(PropType::Struct("BlamVariant".into()))),
                    ),
                    prop(
                        4,
                        "RuntimeVariants",
                        PropType::Array(Box::new(PropType::Struct("BlamVariant".into()))),
                    ),
                    prop(5, "ObjectTagDataAsset", PropType::Object),
                ],
            },
        );
        Usmap {
            enums: HashMap::new(),
            structs,
        }
    }

    #[test]
    fn the_bare_body_is_one_all_skip_fragment() {
        let u = usmap();
        let body = encode_tag_body(&u, "BlamTagDataAssetBase", &Block::default()).unwrap();
        assert_eq!(body, [0, 0, 0, 0, 0x03, 0x01, 0, 0, 0, 0]);
        assert_eq!(
            decode_tag_body(&u, "BlamTagDataAssetBase", &body).unwrap(),
            Block::default()
        );
    }

    #[test]
    fn a_leading_value_drops_the_trailing_skips() {
        // collision_damage-effect as shipped: AssetReference = import 1, nothing else.
        let u = usmap();
        let mut b = Block::default();
        b.set(0, Val::Object(-2));
        let body = encode_tag_body(&u, "BlamBaseEffectTagDataAsset", &b).unwrap();
        assert_eq!(
            body,
            [0, 0, 0, 0, 0x00, 0x03, 0xfe, 0xff, 0xff, 0xff, 0, 0, 0, 0]
        );
        assert_eq!(
            decode_tag_body(&u, "BlamBaseEffectTagDataAsset", &body).unwrap(),
            b
        );
    }

    #[test]
    fn gaps_between_values_become_fragments() {
        let u = usmap();
        let mut b = Block::default();
        b.set(0, Val::Object(-2));
        b.set(1, Val::Bool(true));
        b.set(3, Val::Array(vec![Val::Object(-4), Val::Object(-6)]));
        let body = encode_tag_body(&u, "BlamBaseEffectTagDataAsset", &b).unwrap();
        // fragment 1: skip 0, 2 values; fragment 2: skip 1, 1 value, last.
        assert_eq!(&body[4..8], &[0x00, 0x04, 0x01, 0x03]);
        assert_eq!(
            decode_tag_body(&u, "BlamBaseEffectTagDataAsset", &body).unwrap(),
            b
        );
        assert_eq!(b.object_refs(), vec![-2, -4, -6]);
    }

    #[test]
    fn variants_round_trip_through_nested_blocks_and_maps() {
        let u = usmap();
        let n = |i: u32| {
            Val::Name(Name {
                index: i,
                number: 0,
            })
        };
        let variant = |name: u32, perms: &[(u32, u32)]| {
            let mut v = Block::default();
            v.set(0, n(name));
            v.set(
                1,
                Val::Map(perms.iter().map(|(k, v)| (n(*k), n(*v))).collect()),
            );
            Val::Struct(v)
        };
        let mut b = Block::default();
        b.set(0, Val::Object(-2));
        b.set(
            4,
            Val::Array(vec![variant(3, &[(4, 5), (6, 7)]), variant(8, &[])]),
        );
        b.set(6, Val::Array(vec![Val::Object(-4)]));
        let body = encode_tag_body(&u, "BlamModelTagDataAsset", &b).unwrap();
        let back = decode_tag_body(&u, "BlamModelTagDataAsset", &body).unwrap();
        assert_eq!(back, b);
        assert_eq!(b.names().len(), 6);
        assert_eq!(b.object_refs(), vec![-2, -4]);
    }

    #[test]
    fn a_zero_mask_is_refused_not_guessed() {
        let u = usmap();
        // skip 0, has_zeroes, 1 value, last: 0x0380
        let body = [0, 0, 0, 0, 0x80, 0x03, 0x01, 0, 0, 0, 0];
        assert!(matches!(
            decode_tag_body(&u, "BlamBaseEffectTagDataAsset", &body),
            Err(Error::ZeroMask { .. })
        ));
    }
}

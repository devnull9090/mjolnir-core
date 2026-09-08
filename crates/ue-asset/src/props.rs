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
//! Absent properties are simply skipped. A value present but all zeros can
//! ride in the header's zero mask instead of the value stream — no tag
//! export does that, but material instances and components do — and comes
//! back as [`Val::Zeroed`], which encodes to the same mask bit.

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
    #[error("{class}.{prop}: a native {name} value must be {want} bytes, not {got}")]
    NativeSize {
        class: String,
        prop: String,
        name: String,
        want: usize,
        got: usize,
    },
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
    Int8(i8),
    Int16(i16),
    UInt16(u16),
    Int(i32),
    UInt32(u32),
    Int64(i64),
    UInt64(u64),
    Float(f32),
    Double(f64),
    Name(Name),
    /// An `FPackageIndex`: `<0` import `-n-1`, `>0` export `n-1`, `0` null.
    Object(i32),
    /// `FSoftObjectPath`: top-level asset path (two names) plus a sub-path.
    SoftObject {
        package: Name,
        asset: Name,
        sub: String,
    },
    Str(String),
    /// An `FText`, kept as the bytes the cook wrote.
    Text(Vec<u8>),
    /// A natively serialized struct (`FVector`, `FLinearColor`, `FGuid`…),
    /// byte for byte.
    Native(Vec<u8>),
    Array(Vec<Val>),
    Set(Vec<Val>),
    /// Key/value pairs; the "removed" prefix is always empty in a cook.
    Map(Vec<(Val, Val)>),
    /// A reflected struct: another unversioned block, with no guid guard.
    Struct(Block),
    /// Present, but flagged in the header's zero mask: all zeros, no bytes.
    Zeroed,
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
                Val::Array(items) | Val::Set(items) => items.iter().for_each(|i| walk(i, out)),
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
                Val::Array(items) | Val::Set(items) => items.iter().for_each(|i| walk(i, out)),
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
    fn u64(&mut self) -> Result<u64, Error> {
        let b = self.bytes(8)?;
        Ok(u64::from_le_bytes(b.try_into().unwrap()))
    }
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
    let (block, used) = decode_prefix(usmap, class, data)?;
    if used != data.len() {
        return Err(Error::Trailing(data.len() - used));
    }
    Ok(block)
}

/// Decode the block at the head of `data` and say how many bytes it took —
/// for an export whose native serialization follows its properties.
pub fn decode_prefix(usmap: &Usmap, class: &str, data: &[u8]) -> Result<(Block, usize), Error> {
    let mut c = Cursor { b: data, at: 0 };
    let block = decode_block(usmap, class, &mut c)?;
    Ok((block, c.at))
}

/// The zero mask's byte count for a number of masked values, as
/// `FUnversionedHeader` sizes it.
fn zero_mask_bytes(zero_bits: usize) -> usize {
    if zero_bits == 0 {
        0
    } else if zero_bits <= 8 {
        1
    } else if zero_bits <= 16 {
        2
    } else {
        zero_bits.div_ceil(32) * 4
    }
}

fn decode_block(usmap: &Usmap, class: &str, c: &mut Cursor<'_>) -> Result<Block, Error> {
    if !usmap.structs.contains_key(class) {
        return Err(Error::NoSchema(class.to_string()));
    }
    let total = usmap.total_slots(class);
    // Header: (skip:7, has_zeroes:1, is_last:1, value_count:7+) fragments,
    // then one mask bit per value of every fragment flagged as having zeros.
    let mut runs: Vec<(u16, u16, bool)> = Vec::new();
    let mut zero_bits = 0usize;
    loop {
        let packed = c.u16()?;
        let zeroes = packed & 0x80 != 0;
        let values = packed >> 9;
        if zeroes {
            zero_bits += values as usize;
        }
        runs.push((packed & 0x7F, values, zeroes));
        if packed & 0x100 != 0 {
            break;
        }
    }
    let mask = c.bytes(zero_mask_bytes(zero_bits))?.to_vec();
    let bit = |i: usize| mask[i / 8] & (1 << (i % 8)) != 0;
    let mut block = Block::default();
    let mut slot = 0u16;
    let mut zero_index = 0usize;
    for (skip, values, zeroes) in runs {
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
            let zeroed = zeroes && bit(zero_index);
            if zeroes {
                zero_index += 1;
            }
            let value = if zeroed {
                Val::Zeroed
            } else {
                decode_value(usmap, class, &prop.name, &prop.ty, c)?
            };
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
        T::Int8 => Val::Int8(c.u8()? as i8),
        T::Int16 => Val::Int16(c.u16()? as i16),
        T::UInt16 => Val::UInt16(c.u16()?),
        T::Int => Val::Int(c.u32()? as i32),
        T::UInt32 => Val::UInt32(c.u32()?),
        T::Int64 => Val::Int64(c.u64()? as i64),
        T::UInt64 => Val::UInt64(c.u64()?),
        T::Float => Val::Float(f32::from_bits(c.u32()?)),
        T::Double => Val::Double(f64::from_bits(c.u64()?)),
        // An enum serializes as its underlying numeric type.
        T::Enum(inner, _) => decode_value(usmap, class, prop, inner, c)?,
        T::Str => Val::Str(c.fstring()?),
        T::Text => {
            let start = c.at;
            let _flags = c.u32()?;
            let history = c.u8()? as i8;
            match history {
                -1 => {
                    if c.u32()? != 0 {
                        c.fstring()?;
                    }
                }
                0 => {
                    c.fstring()?;
                    c.fstring()?;
                    c.fstring()?;
                }
                11 => {
                    c.name()?;
                    c.fstring()?;
                }
                _ => {
                    return Err(Error::Unsupported {
                        class: class.to_string(),
                        prop: prop.to_string(),
                        ty: ty.clone(),
                    })
                }
            }
            Val::Text(c.b[start..c.at].to_vec())
        }
        T::LazyObject => Val::Native(c.bytes(16)?.to_vec()),
        T::Name => Val::Name(c.name()?),
        T::Object | T::Interface | T::WeakObject => Val::Object(c.u32()? as i32),
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
        T::Set(inner) => {
            let removed = c.u32()?;
            if removed != 0 {
                return Err(Error::Unsupported {
                    class: class.to_string(),
                    prop: prop.to_string(),
                    ty: ty.clone(),
                });
            }
            let count = c.u32()? as usize;
            if count > 0x0100_0000 {
                return Err(Error::Eof(c.at));
            }
            let mut items = Vec::with_capacity(count);
            for _ in 0..count {
                items.push(decode_value(usmap, class, prop, inner, c)?);
            }
            Val::Set(items)
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
            _ if crate::unversioned::native_struct_size(name).is_some() => {
                let n = crate::unversioned::native_struct_size(name).unwrap();
                Val::Native(c.bytes(n)?.to_vec())
            }
            // Custom serializers this encoder does not model; refused by
            // name rather than misread as a reflected block.
            "InstancedPropertyBag" | "NiagaraVariable" | "NiagaraVariableBase" => {
                return Err(Error::Unsupported {
                    class: class.to_string(),
                    prop: prop.to_string(),
                    ty: ty.clone(),
                })
            }
            // Eight native bytes, then the reflected block; kept raw as one
            // value, since nothing here edits Nanite overrides.
            "MaterialOverrideNanite" => {
                let start = c.at;
                c.bytes(8)?;
                decode_block(usmap, name, c)?;
                Val::Native(c.b[start..c.at].to_vec())
            }
            // The container's custom serializer: a name array, kept raw.
            "GameplayTagContainer" => {
                let start = c.at;
                let count = c.u32()? as usize;
                if count > 0x0010_0000 {
                    return Err(Error::Eof(c.at));
                }
                for _ in 0..count {
                    c.name()?;
                }
                Val::Native(c.b[start..c.at].to_vec())
            }
            _ if usmap.structs.contains_key(name) => Val::Struct(decode_block(usmap, name, c)?),
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
        // all-skip fragment says so. The last fragment carries the flag. A
        // fragment holding any zeroed value is flagged, and contributes one
        // mask bit per value.
        struct Fragment {
            skip: u16,
            values: u16,
            zeroed: Vec<bool>,
        }
        let mut fragments: Vec<Fragment> = Vec::new();
        let mut skip = 0u16;
        let mut values = 0u16;
        let mut zeroed: Vec<bool> = Vec::new();
        for slot in 0..total {
            let present = self.values.iter().find(|(s, _)| *s == slot).map(|(_, v)| v);
            if let Some(v) = present {
                if values == 127 {
                    fragments.push(Fragment {
                        skip,
                        values,
                        zeroed: std::mem::take(&mut zeroed),
                    });
                    skip = 0;
                    values = 0;
                }
                values += 1;
                zeroed.push(matches!(v, Val::Zeroed));
            } else {
                if values > 0 {
                    fragments.push(Fragment {
                        skip,
                        values,
                        zeroed: std::mem::take(&mut zeroed),
                    });
                    skip = 0;
                    values = 0;
                }
                // A fragment's skip is seven bits; one that has reached 127
                // may still take values, so it only closes when another
                // absent slot follows.
                if skip == 127 {
                    fragments.push(Fragment {
                        skip,
                        values: 0,
                        zeroed: Vec::new(),
                    });
                    skip = 0;
                }
                skip += 1;
            }
        }
        if values > 0 || skip > 0 || fragments.is_empty() {
            fragments.push(Fragment {
                skip,
                values,
                zeroed,
            });
        }
        // Trailing skip fragments are dropped, except that a block with no
        // value at all keeps its first one — one fragment skipping every
        // slot, as the cook writes it.
        while fragments.len() > 1 && fragments.last().is_some_and(|f| f.values == 0) {
            fragments.pop();
        }
        let last = fragments.len() - 1;
        let mut out = Vec::new();
        let mut mask_bits: Vec<bool> = Vec::new();
        for (i, f) in fragments.iter().enumerate() {
            let has_zeroes = f.zeroed.iter().any(|z| *z);
            let mut packed = f.skip | (f.values << 9);
            if has_zeroes {
                packed |= 0x80;
                mask_bits.extend_from_slice(&f.zeroed);
            }
            if i == last {
                packed |= 0x100;
            }
            out.extend_from_slice(&packed.to_le_bytes());
        }
        let mut mask = vec![0u8; zero_mask_bytes(mask_bits.len())];
        for (i, bit) in mask_bits.iter().enumerate() {
            if *bit {
                mask[i / 8] |= 1 << (i % 8);
            }
        }
        out.extend_from_slice(&mask);
        for (slot, value) in &self.values {
            if matches!(value, Val::Zeroed) {
                continue;
            }
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
        (T::Int8, Val::Int8(i)) => out.push(*i as u8),
        (T::Int16, Val::Int16(i)) => out.extend_from_slice(&i.to_le_bytes()),
        (T::UInt16, Val::UInt16(i)) => out.extend_from_slice(&i.to_le_bytes()),
        (T::Int, Val::Int(i)) => out.extend_from_slice(&i.to_le_bytes()),
        (T::UInt32, Val::UInt32(i)) => out.extend_from_slice(&i.to_le_bytes()),
        (T::Int64, Val::Int64(i)) => out.extend_from_slice(&i.to_le_bytes()),
        (T::UInt64, Val::UInt64(i)) => out.extend_from_slice(&i.to_le_bytes()),
        (T::Float, Val::Float(f)) => out.extend_from_slice(&f.to_bits().to_le_bytes()),
        (T::Double, Val::Double(f)) => out.extend_from_slice(&f.to_bits().to_le_bytes()),
        (T::Enum(inner, _), v) => encode_value(usmap, class, prop, inner, v, out)?,
        (T::Str, Val::Str(s)) => put_fstring(out, s),
        (T::Text, Val::Text(bytes)) | (T::LazyObject, Val::Native(bytes)) => out.extend_from_slice(bytes),
        (T::Name, Val::Name(n)) => put_name(out, *n),
        (T::Object | T::Interface | T::WeakObject, Val::Object(i)) => {
            out.extend_from_slice(&i.to_le_bytes())
        }
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
        (T::Set(inner), Val::Set(items)) => {
            out.extend_from_slice(&0u32.to_le_bytes());
            out.extend_from_slice(&(items.len() as u32).to_le_bytes());
            for item in items {
                encode_value(usmap, class, prop, inner, item, out)?;
            }
        }
        (T::Struct(name), Val::Native(bytes))
            if matches!(name.as_str(), "MaterialOverrideNanite" | "GameplayTagContainer") =>
        {
            out.extend_from_slice(bytes);
        }
        (T::Struct(name), Val::Native(bytes)) => {
            let want = crate::unversioned::native_struct_size(name).ok_or_else(mismatch)?;
            if bytes.len() != want {
                return Err(Error::NativeSize {
                    class: class.to_string(),
                    prop: prop.to_string(),
                    name: name.clone(),
                    want,
                    got: bytes.len(),
                });
            }
            out.extend_from_slice(bytes);
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

    /// Against the installed game: the blocks of material instances, data
    /// assets and Blueprint packages decode and encode byte for byte, with
    /// the class's native tail split off exactly where the walker says.
    #[test]
    fn shipped_material_and_blueprint_blocks_round_trip() {
        let Ok(paks) = std::env::var("HCE_PAKS") else {
            return;
        };
        let containers = ue_iostore::load_all(&paks).unwrap();
        let global = containers
            .iter()
            .find(|c| c.utoc_path.file_name().is_some_and(|n| n == "global.utoc"))
            .unwrap();
        let script_chunk = global
            .chunks
            .iter()
            .find(|c| c.type_name() == "ScriptObjects")
            .unwrap();
        let scripts = crate::zen::ScriptObjects::parse(
            &ue_iostore::read_chunk(global, script_chunk, None, &[]).unwrap(),
        )
        .unwrap();
        static USMAP: &[u8] = include_bytes!("../../../defs/ue/Meteorite-2607-CU3.usmap");
        let u = Usmap::parse(USMAP).unwrap();
        let limit: usize = std::env::var("PROPS_TEST_LIMIT")
            .ok()
            .and_then(|v| v.parse().ok())
            .unwrap_or(400);
        // class -> (exact, mismatched, unsupported)
        let mut by_class: std::collections::BTreeMap<String, (usize, usize, usize)> = Default::default();
        let mut first_by_class: std::collections::BTreeMap<String, String> = Default::default();
        let hex = |b: &[u8]| b.iter().take(40).map(|x| format!("{x:02x}")).collect::<Vec<_>>().join(" ");
        let mut first_problem: Option<String> = None;
        for prefix in ["MI_", "DA_", "BP_"] {
            let mut seen = 0usize;
            'containers: for c in &containers {
                let mut names: Vec<&String> = c.files.keys().collect();
                names.sort();
                for rel in names {
                    let full = c.full_path(rel);
                    let leaf = full.rsplit('/').next().unwrap_or("");
                    if !leaf.starts_with(prefix) || !full.ends_with(".uasset") || full.contains("/Tags/") {
                        continue;
                    }
                    if seen >= limit {
                        break 'containers;
                    }
                    seen += 1;
                    let data = ue_iostore::read_chunk(c, &c.chunks[c.files[rel]], None, &[]).unwrap();
                    let Ok(pkg) = crate::package::ZenPackage::parse(&data) else {
                        continue;
                    };
                    for (ei, e) in pkg.export_map.iter().enumerate() {
                        let Some(class) = scripts.leaf(crate::zen::ObjectIndex(e.class)) else {
                            continue;
                        };
                        let Some(bytes) = pkg.export_bytes(ei) else { continue };
                        let entry = by_class.entry(class.to_string()).or_default();
                        match decode_prefix(&u, class, bytes) {
                            Ok((block, used)) => match block.encode(&u, class) {
                                Ok(back) if back == bytes[..used] => entry.0 += 1,
                                Ok(back) => {
                                    entry.1 += 1;
                                    let at = back.iter().zip(&bytes[..used]).position(|(a, b)| a != b).unwrap_or(back.len().min(used));
                                    let msg = format!(
                                        "{leaf} [{ei}] {class}: re-encoded bytes differ at {at} of {used} (got {})
    was {}
    now {}",
                                        back.len(), hex(bytes), hex(&back)
                                    );
                                    first_by_class.entry(class.to_string()).or_insert_with(|| msg.clone());
                                    first_problem.get_or_insert(msg);
                                }
                                Err(err) => {
                                    entry.2 += 1;
                                    first_by_class.entry(class.to_string()).or_insert_with(|| format!("{leaf} [{ei}]: encode: {err}"));
                                    first_problem.get_or_insert_with(|| format!("{leaf} [{ei}] {class}: encode: {err}"));
                                }
                            },
                            Err(err) => {
                                entry.2 += 1;
                                first_by_class.entry(class.to_string()).or_insert_with(|| format!("{leaf} [{ei}]: {err}"));
                                if class == "MaterialInstanceConstant" {
                                    first_problem.get_or_insert_with(|| format!("{leaf} [{ei}] {class}: {err}"));
                                }
                            }
                        }
                    }
                }
            }
        }
        let (mut exact, mut mismatched, mut unsupported) = (0, 0, 0);
        for (class, (a, b, c)) in &by_class {
            eprintln!("{a:6} exact {b:4} mismatched {c:4} unsupported  {class}");
            if let Some(f) = first_by_class.get(class) {
                if *b + *c > 0 {
                    eprintln!("        {f}");
                }
            }
            exact += a;
            mismatched += b;
            unsupported += c;
        }
        eprintln!("{exact} exact, {mismatched} mismatched, {unsupported} unsupported");
        if let Some(p) = &first_problem {
            eprintln!("first problem: {p}");
        }
        assert_eq!(mismatched, 0, "a decoded block re-encoded differently");
        let mic = by_class.get("MaterialInstanceConstant").copied().unwrap_or_default();
        assert!(mic.0 > 0 && mic.2 == 0, "material instances: {mic:?}");
        assert!(exact * 10 >= (exact + unsupported) * 9, "under 90% of blocks are modelled");
    }

    #[test]
    fn a_zero_mask_round_trips_as_zeroed() {
        let u = usmap();
        // skip 0, has_zeroes, 1 value, last: 0x0380; mask bit 0 set.
        let body = [0, 0, 0, 0, 0x80, 0x03, 0x01, 0, 0, 0, 0];
        let block = decode_tag_body(&u, "BlamBaseEffectTagDataAsset", &body).unwrap();
        assert_eq!(block.values, vec![(0, Val::Zeroed)]);
        let back = encode_tag_body(&u, "BlamBaseEffectTagDataAsset", &block).unwrap();
        assert_eq!(back, body);
    }
}

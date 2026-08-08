//! `.usmap` reflection mappings, as dumped by UE4SS from the running game.
//!
//! Cooked UE5 packages serialize object properties *unversioned*: no names or
//! types in the data, just values in schema order. The schema lives in the
//! game binary's reflection data, and a `.usmap` is that reflection data
//! written to disk — struct property lists, enum entries, and the name table
//! they share. Everything the unversioned walker does starts here.

use std::collections::HashMap;

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("not a usmap file (bad magic {0:#06x})")]
    Magic(u16),
    #[error("usmap version {0} is newer than this reader")]
    Version(u8),
    #[error("usmap uses compression method {0}, which this reader does not decode")]
    Compression(u8),
    #[error("usmap data ends early at {0:#x}")]
    Eof(usize),
    #[error("name index {0} out of range")]
    Name(u32),
}

/// One property type, as the usmap describes it.
#[derive(Debug, Clone, PartialEq)]
pub enum PropType {
    Byte,
    Bool,
    Int,
    Float,
    Object,
    Name,
    Delegate,
    Double,
    Array(Box<PropType>),
    Struct(String),
    Str,
    Text,
    Interface,
    MulticastDelegate,
    WeakObject,
    LazyObject,
    AssetObject,
    SoftObject,
    UInt64,
    UInt32,
    UInt16,
    Int64,
    Int16,
    Int8,
    Map(Box<PropType>, Box<PropType>),
    Set(Box<PropType>),
    Enum(Box<PropType>, String),
    FieldPath,
    Optional(Box<PropType>),
    Unknown(u8),
}

/// One serializable property of a struct schema.
#[derive(Debug, Clone)]
pub struct Prop {
    /// First schema slot this property occupies; a fixed array of N occupies
    /// N consecutive slots.
    pub schema_index: u16,
    pub array_dim: u8,
    pub name: String,
    pub ty: PropType,
}

#[derive(Debug, Clone)]
pub struct Schema {
    pub name: String,
    pub super_name: Option<String>,
    /// Total schema slots this struct's own properties occupy.
    pub prop_count: u16,
    pub props: Vec<Prop>,
}

impl Schema {
    /// The property occupying a schema slot of this struct (not its supers).
    pub fn prop_at(&self, slot: u16) -> Option<&Prop> {
        self.props
            .iter()
            .find(|p| slot >= p.schema_index && slot < p.schema_index + p.array_dim as u16)
    }
}

#[derive(Debug, Default)]
pub struct Usmap {
    /// Enum entries as `(value, name)` pairs, in declared order.
    pub enums: HashMap<String, Vec<(i64, String)>>,
    pub structs: HashMap<String, Schema>,
}

impl Usmap {
    pub fn parse(data: &[u8]) -> Result<Usmap, Error> {
        let mut r = Reader { data, pos: 0 };
        let magic = r.u16()?;
        if magic != 0x30C4 {
            return Err(Error::Magic(magic));
        }
        let version = r.u8()?;
        if version > 4 {
            return Err(Error::Version(version));
        }
        if version >= 1 {
            let has_versioning = r.i32()?;
            if has_versioning != 0 {
                // FPackageFileVersion + custom version container + net CL.
                r.skip(8)?;
                let custom = r.i32()?;
                r.skip(custom as usize * 20)?;
                r.skip(4)?;
            }
        }
        let method = r.u8()?;
        if method != 0 {
            return Err(Error::Compression(method));
        }
        let _compressed = r.u32()?;
        let _decompressed = r.u32()?;

        // Name table. LongFName (version 2) widened the length to 16 bits.
        let name_count = r.u32()?;
        let mut names = Vec::with_capacity(name_count as usize);
        for _ in 0..name_count {
            let len = if version >= 2 { r.u16()? as usize } else { r.u8()? as usize };
            names.push(String::from_utf8_lossy(r.bytes(len)?).into_owned());
        }
        let name = |idx: u32| -> Result<String, Error> {
            if idx == u32::MAX {
                return Ok(String::new());
            }
            names
                .get(idx as usize)
                .cloned()
                .ok_or(Error::Name(idx))
        };

        // Enums. LargeEnums (version 3) widened the entry count to 16 bits;
        // version 4 gave every entry an explicit 64-bit value (sparse enums).
        let mut out = Usmap::default();
        let enum_count = r.u32()?;
        for _ in 0..enum_count {
            let enum_name = name(r.u32()?)?;
            let entry_count = if version >= 3 { r.u16()? as usize } else { r.u8()? as usize };
            let mut entries = Vec::with_capacity(entry_count);
            for _ in 0..entry_count {
                let value = if version >= 4 { r.i64()? } else { entries.len() as i64 };
                entries.push((value, name(r.u32()?)?));
            }
            out.enums.insert(enum_name, entries);
        }

        // Structs.
        let struct_count = r.u32()?;
        for _ in 0..struct_count {
            let struct_name = name(r.u32()?)?;
            let super_idx = r.u32()?;
            let super_name = if super_idx == u32::MAX {
                None
            } else {
                Some(name(super_idx)?).filter(|s| !s.is_empty())
            };
            let prop_count = r.u16()?;
            let serializable = r.u16()?;
            let mut props = Vec::with_capacity(serializable as usize);
            for _ in 0..serializable {
                let schema_index = r.u16()?;
                let array_dim = r.u8()?;
                let prop_name = name(r.u32()?)?;
                let ty = read_type(&mut r, &name)?;
                props.push(Prop {
                    schema_index,
                    array_dim,
                    name: prop_name,
                    ty,
                });
            }
            out.structs.insert(
                struct_name.clone(),
                Schema {
                    name: struct_name,
                    super_name,
                    prop_count,
                    props,
                },
            );
        }
        Ok(out)
    }

    /// The property at a flat unversioned slot for a class: the class's own
    /// slots come first, then each super's in turn.
    pub fn resolve<'a>(&'a self, class: &str, mut slot: u16) -> Option<(&'a Schema, &'a Prop)> {
        let mut current = self.structs.get(class)?;
        loop {
            if slot < current.prop_count {
                return current.prop_at(slot).map(|p| (current, p));
            }
            slot -= current.prop_count;
            current = self.structs.get(current.super_name.as_deref()?)?;
        }
    }

    /// Total unversioned slots across a class and its supers.
    pub fn total_slots(&self, class: &str) -> u16 {
        let mut total = 0u16;
        let mut current = self.structs.get(class);
        while let Some(s) = current {
            total = total.saturating_add(s.prop_count);
            current = s.super_name.as_deref().and_then(|n| self.structs.get(n));
        }
        total
    }
}

fn read_type(
    r: &mut Reader<'_>,
    name: &dyn Fn(u32) -> Result<String, Error>,
) -> Result<PropType, Error> {
    let tag = r.u8()?;
    Ok(match tag {
        0 => PropType::Byte,
        1 => PropType::Bool,
        2 => PropType::Int,
        3 => PropType::Float,
        4 => PropType::Object,
        5 => PropType::Name,
        6 => PropType::Delegate,
        7 => PropType::Double,
        8 => PropType::Array(Box::new(read_type(r, name)?)),
        9 => PropType::Struct(name(r.u32()?)?),
        10 => PropType::Str,
        11 => PropType::Text,
        12 => PropType::Interface,
        13 => PropType::MulticastDelegate,
        14 => PropType::WeakObject,
        15 => PropType::LazyObject,
        16 => PropType::AssetObject,
        17 => PropType::SoftObject,
        18 => PropType::UInt64,
        19 => PropType::UInt32,
        20 => PropType::UInt16,
        21 => PropType::Int64,
        22 => PropType::Int16,
        23 => PropType::Int8,
        24 => {
            let key = read_type(r, name)?;
            let value = read_type(r, name)?;
            PropType::Map(Box::new(key), Box::new(value))
        }
        25 => PropType::Set(Box::new(read_type(r, name)?)),
        26 => {
            let inner = read_type(r, name)?;
            PropType::Enum(Box::new(inner), name(r.u32()?)?)
        }
        27 => PropType::FieldPath,
        28 => PropType::Optional(Box::new(read_type(r, name)?)),
        other => PropType::Unknown(other),
    })
}

struct Reader<'a> {
    data: &'a [u8],
    pos: usize,
}

impl<'a> Reader<'a> {
    fn bytes(&mut self, n: usize) -> Result<&'a [u8], Error> {
        let out = self
            .data
            .get(self.pos..self.pos + n)
            .ok_or(Error::Eof(self.pos))?;
        self.pos += n;
        Ok(out)
    }
    fn skip(&mut self, n: usize) -> Result<(), Error> {
        self.bytes(n).map(|_| ())
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
    fn i32(&mut self) -> Result<i32, Error> {
        Ok(i32::from_le_bytes(self.bytes(4)?.try_into().unwrap()))
    }
    fn i64(&mut self) -> Result<i64, Error> {
        Ok(i64::from_le_bytes(self.bytes(8)?.try_into().unwrap()))
    }
}

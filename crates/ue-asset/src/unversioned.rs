//! Unversioned property data, walked against usmap schemas.
//!
//! Cooked UE5 packages write object properties with no names or types in the
//! stream: a header of fragments says which schema slots are present (and
//! which are zero), then the present, non-zero values follow in slot order.
//! Walking it requires the exact schema — that is what the usmap provides —
//! and byte-exact knowledge of every value's serialized size.
//!
//! Struct values without a native serializer recurse into this same format
//! with their own header. Structs *with* native serializers (FVector and
//! friends) are a fixed table below; an unknown case fails loudly with the
//! property's name so the table can grow deliberately.

use crate::usmap::{PropType, Usmap};
use std::collections::HashMap;

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("data ends early at {0:#x}")]
    Eof(usize),
    #[error("no usmap schema for {0:?}")]
    NoSchema(String),
    #[error("{class}: no property at unversioned slot {slot}")]
    NoSlot { class: String, slot: u16 },
    #[error("{class}.{prop}: unsupported type {ty:?} at {at:#x}")]
    Unsupported {
        class: String,
        prop: String,
        ty: PropType,
        at: usize,
    },
    #[error("{class}.{prop}: FText history {0} is not supported", .history)]
    Text {
        class: String,
        prop: String,
        history: i8,
    },
}

/// A property value the walker chose to keep.
#[derive(Debug, Clone, PartialEq)]
pub enum Value {
    Bool(bool),
    Int(i64),
    Float(f64),
    /// A resolved FName.
    Name(String),
    /// An FPackageIndex: >0 export `n-1`, <0 import `-n-1`, 0 null.
    Object(i32),
    Str(String),
    Array(Vec<Value>),
    Struct(HashMap<String, Value>),
    /// Present but not captured in detail.
    Opaque,
    /// In the zero mask: the value is all-zeros / false / empty.
    Zeroed,
}

impl Value {
    pub fn as_object(&self) -> Option<i32> {
        match self {
            Value::Object(i) => Some(*i),
            _ => None,
        }
    }
    pub fn as_str(&self) -> Option<&str> {
        match self {
            Value::Name(s) | Value::Str(s) => Some(s),
            _ => None,
        }
    }
}

/// Which properties a walk should keep values for.
#[derive(Clone, Copy)]
pub enum Keep<'k> {
    None,
    All,
    Names(&'k [&'k str]),
}

impl Keep<'_> {
    fn wanted(&self, name: &str) -> bool {
        match self {
            Keep::None => false,
            Keep::All => true,
            Keep::Names(list) => list.iter().any(|k| *k == name),
        }
    }
}

/// Everything a walk needs beyond the bytes.
pub struct Ctx<'a> {
    pub usmap: &'a Usmap,
    /// The package name map, for FName resolution.
    pub names: &'a [String],
}

pub struct Walker<'a> {
    ctx: &'a Ctx<'a>,
    data: &'a [u8],
    pub pos: usize,
    /// Print each property as it is walked, for empirical format work.
    pub trace: bool,
}

impl<'a> Walker<'a> {
    pub fn new(ctx: &'a Ctx<'a>, data: &'a [u8]) -> Walker<'a> {
        Walker {
            ctx,
            data,
            pos: 0,
            trace: std::env::var_os("UE_ASSET_TRACE").is_some(),
        }
    }

    /// Walk one object's unversioned property blob (as UObject::Serialize
    /// writes it), keeping the properties named in `keep`. Leaves the cursor
    /// at the first byte after the properties and the 4-byte guid guard —
    /// where a class's native serialization begins.
    pub fn read_object(
        &mut self,
        class: &str,
        keep: Keep<'_>,
    ) -> Result<HashMap<String, Value>, Error> {
        let out = self.read_unversioned(class, keep)?;
        // UObject::Serialize ends with a 4-byte "has guid" bool.
        let has_guid = self.u32()?;
        if has_guid != 0 {
            self.skip(16)?;
        }
        Ok(out)
    }

    /// One unversioned blob: fragment header, zero mask, values.
    pub fn read_unversioned(
        &mut self,
        class: &str,
        keep: Keep<'_>,
    ) -> Result<HashMap<String, Value>, Error> {
        struct Fragment {
            skip: u16,
            values: u16,
            zeroes: bool,
        }
        let mut fragments = Vec::new();
        let mut zero_bits = 0usize;
        loop {
            let packed = self.u16()?;
            let f = Fragment {
                skip: packed & 0x7F,
                zeroes: packed & 0x80 != 0,
                values: packed >> 9,
            };
            if f.zeroes {
                zero_bits += f.values as usize;
            }
            let last = packed & 0x100 != 0;
            fragments.push(f);
            if last {
                break;
            }
        }
        let mask_bytes = if zero_bits == 0 {
            0
        } else if zero_bits <= 8 {
            1
        } else if zero_bits <= 16 {
            2
        } else {
            zero_bits.div_ceil(32) * 4
        };
        let mask_at = self.pos;
        let mask = self.bytes(mask_bytes)?;
        let bit = |i: usize| mask[i / 8] & (1 << (i % 8)) != 0;
        let _ = mask_at;

        let mut out = HashMap::new();
        let mut slot = 0u16;
        let mut zero_index = 0usize;
        for f in &fragments {
            slot += f.skip;
            for _ in 0..f.values {
                let (_, prop) = self
                    .ctx
                    .usmap
                    .resolve(class, slot)
                    .ok_or_else(|| Error::NoSlot {
                        class: class.to_string(),
                        slot,
                    })?;
                let zeroed = f.zeroes && bit(zero_index);
                if f.zeroes {
                    zero_index += 1;
                }
                let wanted = keep.wanted(&prop.name);
                if self.trace {
                    eprintln!(
                        "  @{:#06x} {class} slot {slot} {} {:?}{}",
                        self.pos,
                        prop.name,
                        prop.ty,
                        if zeroed { " [zero]" } else { "" }
                    );
                }
                if zeroed {
                    if wanted {
                        out.insert(prop.name.clone(), Value::Zeroed);
                    }
                } else {
                    let name = prop.name.clone();
                    let ty = prop.ty.clone();
                    let value = self.read_value(class, &name, &ty, wanted)?;
                    if wanted {
                        out.insert(name, value);
                    }
                }
                slot += 1;
            }
        }
        Ok(out)
    }

    fn read_value(
        &mut self,
        class: &str,
        prop: &str,
        ty: &PropType,
        keep: bool,
    ) -> Result<Value, Error> {
        use PropType as T;
        Ok(match ty {
            T::Bool => Value::Bool(self.u8()? != 0),
            T::Int8 => Value::Int(self.u8()? as i8 as i64),
            T::Byte => Value::Int(self.u8()? as i64),
            T::Int16 => Value::Int(self.u16()? as i16 as i64),
            T::UInt16 => Value::Int(self.u16()? as i64),
            T::Int => Value::Int(self.u32()? as i32 as i64),
            T::UInt32 => Value::Int(self.u32()? as i64),
            T::Int64 | T::UInt64 => Value::Int(self.u64()? as i64),
            T::Float => Value::Float(f32::from_bits(self.u32()?) as f64),
            T::Double => Value::Float(f64::from_bits(self.u64()?)),
            T::Enum(inner, _) => {
                // Serialized as the underlying numeric type.
                self.read_value(class, prop, inner, false)?;
                Value::Opaque
            }
            T::Name => Value::Name(self.fname()?),
            T::Object | T::Interface => Value::Object(self.u32()? as i32),
            T::WeakObject => Value::Object(self.u32()? as i32),
            T::LazyObject => {
                self.skip(16)?;
                Value::Opaque
            }
            T::SoftObject | T::AssetObject => {
                // FSoftObjectPath: FTopLevelAssetPath (two FNames) + subpath.
                let package = self.fname()?;
                let asset = self.fname()?;
                let _sub = self.fstring()?;
                Value::Str(format!("{package}.{asset}"))
            }
            T::Str => Value::Str(self.fstring()?),
            T::Text => {
                let _flags = self.u32()?;
                let history = self.u8()? as i8;
                match history {
                    -1 => {
                        let has = self.u32()?;
                        if has != 0 {
                            self.fstring()?;
                        }
                    }
                    0 => {
                        // Base: namespace, key, source string.
                        self.fstring()?;
                        self.fstring()?;
                        self.fstring()?;
                    }
                    other => {
                        return Err(Error::Text {
                            class: class.to_string(),
                            prop: prop.to_string(),
                            history: other,
                        })
                    }
                }
                Value::Opaque
            }
            T::Array(inner) => {
                let count = self.u32()? as usize;
                if count > 0x0100_0000 {
                    return Err(Error::Eof(self.pos));
                }
                let mut values = Vec::new();
                for _ in 0..count {
                    let v = self.read_value(class, prop, inner, keep)?;
                    if keep {
                        values.push(v);
                    }
                }
                if keep {
                    Value::Array(values)
                } else {
                    Value::Opaque
                }
            }
            T::Set(inner) => {
                let removed = self.u32()?;
                debug_assert_eq!(removed, 0);
                let count = self.u32()? as usize;
                for _ in 0..count {
                    self.read_value(class, prop, inner, false)?;
                }
                Value::Opaque
            }
            T::Map(key, value) => {
                let removed = self.u32()? as usize;
                for _ in 0..removed {
                    self.read_value(class, prop, key, false)?;
                }
                let count = self.u32()? as usize;
                for _ in 0..count {
                    self.read_value(class, prop, key, false)?;
                    self.read_value(class, prop, value, false)?;
                }
                Value::Opaque
            }
            T::Struct(name) => self.read_struct(class, prop, name, keep)?,
            other => {
                return Err(Error::Unsupported {
                    class: class.to_string(),
                    prop: prop.to_string(),
                    ty: other.clone(),
                    at: self.pos,
                })
            }
        })
    }

    /// A struct value: the native table first, else unversioned recursion
    /// with the struct's own schema.
    fn read_struct(
        &mut self,
        class: &str,
        prop: &str,
        name: &str,
        keep: bool,
    ) -> Result<Value, Error> {
        // Native serializers, sized for a UE5 cook (double-based vectors).
        // Only core primitives belong here: reflected composites like
        // BoxSphereBounds recurse as unversioned blobs of these, verified
        // byte-by-byte against shipped meshes.
        let fixed = match name {
            "Vector" | "Rotator" => Some(24),
            "Vector3f" => Some(12),
            "Vector2D" => Some(16),
            "Vector2f" => Some(8),
            "Vector4" | "Quat" | "Plane" => Some(32),
            "Vector4f" | "Quat4f" => Some(16),
            "Color" => Some(4),
            "LinearColor" => Some(16),
            "IntPoint" => Some(8),
            "IntVector" => Some(12),
            "IntVector4" => Some(16),
            "Guid" => Some(16),
            "FrameNumber" => Some(4),
            "PerPlatformFloat" | "PerPlatformInt" | "PerPlatformBool" => Some(8),
            "DateTime" | "Timespan" => Some(8),
            _ => None,
        };
        if let Some(n) = fixed {
            let at = self.pos;
            let raw = self.bytes(n)?;
            return Ok(if keep {
                match name {
                    "Vector" => Value::Array(
                        raw.chunks_exact(8)
                            .map(|c| Value::Float(f64::from_le_bytes(c.try_into().unwrap())))
                            .collect(),
                    ),
                    "Vector3f" => Value::Array(
                        raw.chunks_exact(4)
                            .map(|c| {
                                Value::Float(f32::from_le_bytes(c.try_into().unwrap()) as f64)
                            })
                            .collect(),
                    ),
                    _ => {
                        let _ = at;
                        Value::Opaque
                    }
                }
            } else {
                Value::Opaque
            });
        }
        match name {
            "PerQualityLevelInt" => {
                // bCooked (4) + default (4) + per-quality map (4 + pairs).
                self.skip(8)?;
                let count = self.u32()? as usize;
                self.skip(count * 8)?;
                Ok(Value::Opaque)
            }
            "SoftObjectPath" | "SoftClassPath" => {
                let package = self.fname()?;
                let asset = self.fname()?;
                let _sub = self.fstring()?;
                Ok(Value::Str(format!("{package}.{asset}")))
            }
            "TopLevelAssetPath" => {
                let package = self.fname()?;
                let asset = self.fname()?;
                Ok(Value::Str(format!("{package}.{asset}")))
            }
            _ => {
                // Schema recursion: another unversioned blob.
                if !self.ctx.usmap.structs.contains_key(name) {
                    return Err(Error::Unsupported {
                        class: class.to_string(),
                        prop: prop.to_string(),
                        ty: PropType::Struct(name.to_string()),
                        at: self.pos,
                    });
                }
                let inner =
                    self.read_unversioned(name, if keep { Keep::All } else { Keep::None })?;
                Ok(if keep { Value::Struct(inner) } else { Value::Opaque })
            }
        }
    }

    // -- primitives ---------------------------------------------------------

    pub fn bytes(&mut self, n: usize) -> Result<&'a [u8], Error> {
        let out = self
            .data
            .get(self.pos..self.pos + n)
            .ok_or(Error::Eof(self.pos))?;
        self.pos += n;
        Ok(out)
    }
    pub fn skip(&mut self, n: usize) -> Result<(), Error> {
        self.bytes(n).map(|_| ())
    }
    pub fn u8(&mut self) -> Result<u8, Error> {
        Ok(self.bytes(1)?[0])
    }
    pub fn u16(&mut self) -> Result<u16, Error> {
        Ok(u16::from_le_bytes(self.bytes(2)?.try_into().unwrap()))
    }
    pub fn u32(&mut self) -> Result<u32, Error> {
        Ok(u32::from_le_bytes(self.bytes(4)?.try_into().unwrap()))
    }
    pub fn u64(&mut self) -> Result<u64, Error> {
        Ok(u64::from_le_bytes(self.bytes(8)?.try_into().unwrap()))
    }
    pub fn f32(&mut self) -> Result<f32, Error> {
        Ok(f32::from_bits(self.u32()?))
    }

    /// An FMappedName: index + number into the package name map.
    pub fn fname(&mut self) -> Result<String, Error> {
        let index = self.u32()? & ((1 << 30) - 1);
        let number = self.u32()?;
        let base = self
            .ctx
            .names
            .get(index as usize)
            .cloned()
            .unwrap_or_default();
        Ok(if number != 0 {
            format!("{base}_{}", number - 1)
        } else {
            base
        })
    }

    /// An FString: length-prefixed, negative length meaning UTF-16.
    pub fn fstring(&mut self) -> Result<String, Error> {
        let len = self.u32()? as i32;
        if len == 0 {
            return Ok(String::new());
        }
        if len < 0 {
            let n = (-len) as usize;
            let raw = self.bytes(n * 2)?;
            let units: Vec<u16> = raw
                .chunks_exact(2)
                .map(|c| u16::from_le_bytes([c[0], c[1]]))
                .collect();
            let mut s = String::from_utf16_lossy(&units);
            s.truncate(s.trim_end_matches('\0').len());
            Ok(s)
        } else {
            let raw = self.bytes(len as usize)?;
            let s = String::from_utf8_lossy(raw);
            Ok(s.trim_end_matches('\0').to_string())
        }
    }
}
